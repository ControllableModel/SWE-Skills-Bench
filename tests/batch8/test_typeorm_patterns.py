"""
Tests for the `typeorm-patterns` skill task (variant ext8):
    "Build a Concurrency-Safe Inventory Layer".

The agent must add, under `test/functional/inventory-concurrency/`, a self-contained
TypeORM functional feature that rejects stale concurrent writes using the ORM's own
automatically-managed record-revision indicator (a `@VersionColumn`), verified through
the repo's public API against an in-memory SQLite database:

  - entity/StockItem.ts             (id auto-generated, sku:string, quantity:int,
                                      + an ORM-managed revision column that auto-increments
                                      on every successful update)
  - inventory-service.ts            (addItem / getItem / adjustQuantity) built on a DataSource
  - inventory-concurrency.test.ts   (functional test wiring the above via createTestingConnections)

This pytest verifies the deliverables two ways:
  1. L1 — the three files exist and are minimally well-formed (entity is a decorated
     TypeORM entity with a generated PK and an ORM-managed revision column; service
     exports the three operations; test restricts to the SQLite driver family).
  2. L2 — DYNAMIC EXECUTION against the real TypeORM toolchain: it ensures an
     ormconfig.json restricted to the better-sqlite3 driver, compiles the repo
     (`pnpm run compile`), runs the agent's own compiled functional test under mocha,
     and then runs INDEPENDENT driver scripts (written by THIS test) against the agent's
     compiled StockItem/InventoryService to deep-validate real behavior:
        * addItem returns an item with a populated revision indicator
        * the revision is an ORM-managed column at the DB level (auto-increments on update)
        * two reads share a revision; first adjustQuantity(rev) succeeds & advances revision
        * a second adjustQuantity using the now-stale revision FAILS (rejected/throws) and
          leaves the quantity at the value the first adjustment left it
        * a successful adjustQuantity strictly increases the revision indicator
        * getItem(<missing id>) returns null (not a throw)

A naive solution that ignores the revision on update (lets a stale write overwrite a
newer one), hand-maintains its own counter the service mutates by itself, or hardcodes
"success" must fail at least one assertion.
"""

import json
import os
import subprocess
import textwrap

import pytest

REPO_DIR = "/workspace/typeorm"
FEATURE_DIR = os.path.join(REPO_DIR, "test/functional/inventory-concurrency")
ENTITY_DIR = os.path.join(FEATURE_DIR, "entity")
STOCKITEM_TS = os.path.join(ENTITY_DIR, "StockItem.ts")
SERVICE_TS = os.path.join(FEATURE_DIR, "inventory-service.ts")
TEST_TS = os.path.join(FEATURE_DIR, "inventory-concurrency.test.ts")

COMPILED_TEST_JS = os.path.join(
    REPO_DIR,
    "build/compiled/test/functional/inventory-concurrency/inventory-concurrency.test.js",
)
COMPILED_FEATURE_DIR = os.path.join(
    REPO_DIR, "build/compiled/test/functional/inventory-concurrency"
)

# Build/compile is heavy in this repo.
COMPILE_TIMEOUT = 1200
RUN_TIMEOUT = 600

# Directory (under REPO_DIR, picked up by tsc include "test") where this pytest drops
# its own independent driver scripts so they compile next to the agent's emitted code.
PROBE_OUT_DIR = os.path.join(
    REPO_DIR, "build/compiled/test/functional/inventory-concurrency/__probe__"
)


# ---------------------------------------------------------------------------
# module-scope setup: deps + ormconfig(better-sqlite3) + one compile, shared by L2
# ---------------------------------------------------------------------------

_COMPILE_STATE = {"done": False, "ok": False, "stderr": ""}


def _have(cmd):
    return (
        subprocess.run(
            ["bash", "-lc", f"command -v {cmd}"],
            capture_output=True,
            text=True,
        ).returncode
        == 0
    )


def _ensure_deps():
    """Install node_modules if missing (prefer pnpm, the repo's package manager)."""
    if os.path.isdir(os.path.join(REPO_DIR, "node_modules", "chai")) and os.path.isdir(
        os.path.join(REPO_DIR, "node_modules", "better-sqlite3")
    ):
        return
    try:
        from _dependency_utils import ensure_npm_dependencies  # type: ignore

        ensure_npm_dependencies(REPO_DIR)
    except Exception:
        pass
    if os.path.isdir(os.path.join(REPO_DIR, "node_modules", "better-sqlite3")):
        return
    if _have("pnpm"):
        installer = "pnpm install --frozen-lockfile || pnpm install"
    elif _have("yarn"):
        installer = "yarn install"
    else:
        installer = "npm install"
    subprocess.run(
        ["bash", "-lc", installer],
        cwd=REPO_DIR,
        capture_output=True,
        text=True,
        timeout=COMPILE_TIMEOUT,
    )


def _ensure_ormconfig():
    """Create ormconfig.json restricted to the better-sqlite3 driver (CI pattern)."""
    sample = os.path.join(REPO_DIR, "ormconfig.sample.json")
    target = os.path.join(REPO_DIR, "ormconfig.json")
    with open(sample) as f:
        data = json.load(f)
    sqlite_like = {"better-sqlite3", "sqlite", "sqljs"}
    filtered = [c for c in data if c.get("type") in sqlite_like]
    bsq = [c for c in filtered if c.get("type") == "better-sqlite3"]
    chosen = bsq if bsq else filtered
    assert chosen, "ormconfig.sample.json has no sqlite-family driver entry"
    with open(target, "w") as f:
        json.dump(chosen, f, indent=2)


def _compile():
    if _COMPILE_STATE["done"]:
        return
    _COMPILE_STATE["done"] = True
    _ensure_deps()
    _ensure_ormconfig()
    if _have("pnpm"):
        cmd = "pnpm run compile"
    else:
        cmd = "npx gulp clean && npx tsc"
    proc = subprocess.run(
        ["bash", "-lc", cmd],
        cwd=REPO_DIR,
        capture_output=True,
        text=True,
        timeout=COMPILE_TIMEOUT,
    )
    _COMPILE_STATE["ok"] = proc.returncode == 0
    _COMPILE_STATE["stderr"] = (proc.stdout or "") + "\n" + (proc.stderr or "")


@pytest.fixture(scope="module", autouse=True)
def _module_setup():
    try:
        _compile()
    except Exception as exc:  # pragma: no cover
        _COMPILE_STATE["ok"] = False
        _COMPILE_STATE["stderr"] = f"compile raised: {exc!r}"
    yield


def _require_compiled():
    assert _COMPILE_STATE["done"], "compile step did not run"
    assert _COMPILE_STATE["ok"], (
        "`pnpm run compile` (gulp clean && tsc) failed; the deliverables must "
        "compile cleanly:\n" + _COMPILE_STATE["stderr"][-4000:]
    )


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


# ---------------------------------------------------------------------------
# Helpers to build & run an independent node driver against the compiled code
# ---------------------------------------------------------------------------

def _write_probe(rel_name, ts_source):
    """Write a TS probe under the compiled-friendly probe dir and return its .js path.

    The probe is compiled in place (CommonJS, decorators enabled) so the relative `./`
    imports resolve to the agent's already-compiled StockItem/InventoryService modules.
    """
    os.makedirs(PROBE_OUT_DIR, exist_ok=True)
    ts_path = os.path.join(PROBE_OUT_DIR, rel_name + ".ts")
    with open(ts_path, "w", encoding="utf-8") as f:
        f.write(ts_source)
    tsc = (
        "npx tsc "
        + ts_path
        + " --module commonjs --target ES2021 --experimentalDecorators "
        "--emitDecoratorMetadata --moduleResolution node "
        "--esModuleInterop --skipLibCheck --resolveJsonModule "
        "--strict false --noImplicitAny false"
    )
    proc = subprocess.run(
        ["bash", "-lc", tsc],
        cwd=REPO_DIR,
        capture_output=True,
        text=True,
        timeout=COMPILE_TIMEOUT,
    )
    js_path = os.path.join(PROBE_OUT_DIR, rel_name + ".js")
    assert proc.returncode == 0 and os.path.isfile(js_path), (
        "failed to compile probe driver:\n" + proc.stdout + "\n" + proc.stderr
    )
    return js_path


def _run_node(js_path):
    return subprocess.run(
        ["bash", "-lc", "node " + js_path],
        cwd=REPO_DIR,
        capture_output=True,
        text=True,
        timeout=RUN_TIMEOUT,
    )


def _import_paths():
    """Relative imports (from the probe's compiled location) to the agent modules."""
    # Probe sits at build/compiled/test/functional/inventory-concurrency/__probe__/X.js
    # Agent compiled modules sit one dir up.
    return {
        "stockitem": "../entity/StockItem",
        "service": "../inventory-service",
        "datasource": "../../../../../src",  # build/compiled/src
    }


_DRIVER_PREAMBLE = """
"use strict";
const {{ DataSource }} = require("{datasource}");
const StockItemMod = require("{stockitem}");
const ServiceMod = require("{service}");

function pickClass(mod, names) {{
    for (const n of names) if (mod[n]) return mod[n];
    for (const k of Object.keys(mod)) {{
        if (typeof mod[k] === "function") return mod[k];
    }}
    if (mod.default) return mod.default;
    throw new Error("could not locate export in module");
}}

const StockItem = pickClass(StockItemMod, ["StockItem", "default"]);
const ServiceExport = pickClass(
    ServiceMod,
    ["InventoryService", "Inventory", "createInventoryService", "default"],
);

function makeService(ds) {{
    // Support `new Class(ds)` and a factory `fn(ds)`.
    try {{
        const s = new ServiceExport(ds);
        if (s && typeof s.adjustQuantity === "function") return s;
    }} catch (e) {{ /* fall through to factory */ }}
    return ServiceExport(ds);
}}

async function newDataSource() {{
    const ds = new DataSource({{
        type: "better-sqlite3",
        database: ":memory:",
        entities: [StockItem],
        synchronize: true,
        dropSchema: true,
    }});
    await ds.initialize();
    return ds;
}}

function out(obj) {{ process.stdout.write("RESULT_JSON:" + JSON.stringify(obj) + "\\n"); }}

// Run `fn` and report whether it rejected/threw, without crashing the process.
async function tryCall(fn) {{
    try {{
        const value = await fn();
        return {{ rejected: false, value: value === undefined ? null : value }};
    }} catch (e) {{
        return {{ rejected: true, error: String((e && e.message) || e) }};
    }}
}}
"""


def _driver(body):
    paths = _import_paths()
    preamble = _DRIVER_PREAMBLE.format(
        datasource=paths["datasource"],
        stockitem=paths["stockitem"],
        service=paths["service"],
    )
    return preamble + "\n" + textwrap.dedent(body) + "\n"


def _parse_result(proc):
    assert proc.returncode == 0, (
        "driver script exited non-zero:\nSTDOUT:\n"
        + proc.stdout
        + "\nSTDERR:\n"
        + proc.stderr
    )
    line = None
    for ln in proc.stdout.splitlines():
        if ln.startswith("RESULT_JSON:"):
            line = ln[len("RESULT_JSON:") :]
    assert line is not None, (
        "driver did not emit RESULT_JSON line:\nSTDOUT:\n"
        + proc.stdout
        + "\nSTDERR:\n"
        + proc.stderr
    )
    return json.loads(line)


# ===========================================================================
# L1 — deliverable files exist and are minimally well-formed
# ===========================================================================


class TestTypeormPatterns:
    REPO_DIR = "/workspace/typeorm"

    # ---- L1 -------------------------------------------------------------

    def test_l1_feature_files_exist(self):
        """All three required deliverable files exist under inventory-concurrency/."""
        for p in (STOCKITEM_TS, SERVICE_TS, TEST_TS):
            assert os.path.isfile(p), f"missing required deliverable file: {p}"

    def test_l1_stockitem_is_typeorm_entity_with_fields(self):
        """StockItem is a decorated TypeORM entity with a generated PK, sku and quantity."""
        src = _read(STOCKITEM_TS)
        assert "@Entity" in src, "StockItem is not annotated with @Entity"
        assert "@PrimaryGeneratedColumn" in src, (
            "StockItem lacks a database-generated primary key (@PrimaryGeneratedColumn)"
        )
        assert "sku" in src, "StockItem entity does not declare a `sku` field"
        assert "quantity" in src, "StockItem entity does not declare a `quantity` field"

    def test_l1_stockitem_uses_orm_managed_revision_column(self):
        """The revision indicator is an ORM-managed column, not a hand-mutated counter.

        TypeORM's automatically-incremented record-revision indicator is the
        @VersionColumn decorator. Requiring it here rules out a plain @Column the
        service would have to bump by hand.
        """
        src = _read(STOCKITEM_TS)
        assert "@VersionColumn" in src, (
            "StockItem must carry an ORM-managed revision indicator that auto-increments "
            "on every update; use TypeORM's @VersionColumn rather than a hand-maintained "
            "counter"
        )

    def test_l1_service_exports_required_operations(self):
        """inventory-service.ts references the three named inventory operations."""
        src = _read(SERVICE_TS)
        for op in ("addItem", "getItem", "adjustQuantity"):
            assert op in src, f"inventory-service.ts does not define `{op}`"

    def test_l1_test_uses_sqlite_only_testing_connections(self):
        """The functional test restricts testing connections to the SQLite driver family."""
        src = _read(TEST_TS)
        assert "createTestingConnections" in src, (
            "inventory-concurrency.test.ts must use createTestingConnections from "
            "../../utils/test-utils"
        )
        assert "enabledDrivers" in src, (
            "inventory-concurrency.test.ts must restrict to SQLite-based driver(s) via "
            "enabledDrivers"
        )
        assert ("sqlite" in src) or ("sqljs" in src), (
            "enabledDrivers must name a sqlite-family driver "
            "(better-sqlite3/sqlite/sqljs)"
        )

    # ---- L2: build & agent's own test -----------------------------------

    def test_l2_repo_compiles(self):
        """`pnpm run compile` succeeds with the deliverables in place (tsc, strict)."""
        _require_compiled()
        assert os.path.isfile(COMPILED_TEST_JS), (
            "expected compiled functional test at "
            + COMPILED_TEST_JS
            + " (compile succeeded but the test file was not emitted)"
        )
        for fname in ("entity/StockItem.js", "inventory-service.js"):
            p = os.path.join(COMPILED_FEATURE_DIR, fname)
            assert os.path.isfile(p), f"expected compiled deliverable {p}"

    def test_l2_agent_functional_test_passes(self):
        """The agent's own inventory-concurrency.test.ts passes under mocha (no failures)."""
        _require_compiled()
        setup = "build/compiled/test/utils/test-setup.js"
        cmd = (
            "npx mocha --require " + setup + " --check-leaks --exit "
            "--timeout 90000 " + COMPILED_TEST_JS
        )
        proc = subprocess.run(
            ["bash", "-lc", cmd],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=RUN_TIMEOUT,
        )
        combined = proc.stdout + "\n" + proc.stderr
        assert proc.returncode == 0, (
            "agent's mocha functional test failed:\n" + combined[-4000:]
        )
        assert "passing" in combined, (
            "mocha reported no passing tests:\n" + combined[-2000:]
        )
        assert " 0 passing" not in combined, (
            "mocha collected zero passing tests:\n" + combined[-2000:]
        )

    # ---- L2: independent driver probes against the compiled code --------

    def test_l2_add_item_returns_populated_revision(self):
        """addItem persists a new item with a generated id and a populated revision."""
        _require_compiled()
        js = _write_probe(
            "probe_add",
            _driver(
                """
                (async () => {
                    const ds = await newDataSource();
                    const svc = makeService(ds);
                    const item = await svc.addItem("SKU-1", 7);
                    const fetched = await svc.getItem(item.id);
                    const revKey = Object.keys(item).find((k) =>
                        /version|revision/i.test(k));
                    out({
                        id: item.id,
                        idIsInt: Number.isInteger(item.id),
                        quantity: fetched.quantity,
                        sku: fetched.sku,
                        revKey: revKey || null,
                        rev: revKey ? item[revKey] : null,
                    });
                    await ds.destroy();
                })().catch((e) => { console.error(e); process.exit(1); });
                """
            ),
        )
        res = _parse_result(_run_node(js))
        assert res["idIsInt"] and res["id"] > 0, res
        assert res["sku"] == "SKU-1", res
        assert res["quantity"] == 7, res
        assert res["revKey"], "addItem result carries no revision indicator field: " + json.dumps(res)
        # @VersionColumn starts at 1 after the first save.
        assert isinstance(res["rev"], int) and res["rev"] >= 1, (
            "revision indicator is not a populated positive integer: " + json.dumps(res)
        )

    def test_l2_revision_is_db_managed_version_column(self):
        """The revision column is an ORM `version`-mode column at the schema level.

        We inspect the actual table metadata via the DataSource: the column must be a
        version column the ORM bumps automatically, not an ordinary numeric column.
        """
        _require_compiled()
        js = _write_probe(
            "probe_versioncol",
            _driver(
                """
                (async () => {
                    const ds = await newDataSource();
                    const meta = ds.getMetadata(StockItem);
                    const versionCols = meta.columns
                        .filter((c) => c.isVersion)
                        .map((c) => c.propertyName);
                    out({
                        table: meta.tableName,
                        versionCols: versionCols,
                        hasVersion: versionCols.length === 1,
                    });
                    await ds.destroy();
                })().catch((e) => { console.error(e); process.exit(1); });
                """
            ),
        )
        res = _parse_result(_run_node(js))
        assert res["hasVersion"] is True, (
            "StockItem must declare exactly one ORM-managed version column "
            "(isVersion); a plain @Column counter is not accepted: " + json.dumps(res)
        )

    def test_l2_successful_adjust_advances_revision_and_quantity(self):
        """adjustQuantity with the current revision applies delta and strictly advances revision."""
        _require_compiled()
        js = _write_probe(
            "probe_success",
            _driver(
                """
                (async () => {
                    const ds = await newDataSource();
                    const svc = makeService(ds);
                    const created = await svc.addItem("SKU-A", 10);
                    const before = await svc.getItem(created.id);
                    const revKey = Object.keys(before).find((k) =>
                        /version|revision/i.test(k));
                    const beforeRev = before[revKey];
                    await svc.adjustQuantity(created.id, beforeRev, 5);
                    const after = await svc.getItem(created.id);
                    out({
                        revKey: revKey,
                        beforeRev: beforeRev,
                        afterRev: after[revKey],
                        beforeQty: before.quantity,
                        afterQty: after.quantity,
                    });
                    await ds.destroy();
                })().catch((e) => { console.error(e); process.exit(1); });
                """
            ),
        )
        res = _parse_result(_run_node(js))
        assert res["beforeQty"] == 10, res
        assert res["afterQty"] == 15, (
            "successful adjustQuantity did not apply the delta: " + json.dumps(res)
        )
        assert res["afterRev"] > res["beforeRev"], (
            "revision indicator did not strictly advance after a successful update: "
            + json.dumps(res)
        )

    def test_l2_negative_delta_applied_on_success(self):
        """A negative delta with the current revision decreases the quantity."""
        _require_compiled()
        js = _write_probe(
            "probe_negdelta",
            _driver(
                """
                (async () => {
                    const ds = await newDataSource();
                    const svc = makeService(ds);
                    const created = await svc.addItem("SKU-N", 20);
                    const before = await svc.getItem(created.id);
                    const revKey = Object.keys(before).find((k) =>
                        /version|revision/i.test(k));
                    await svc.adjustQuantity(created.id, before[revKey], -8);
                    const after = await svc.getItem(created.id);
                    out({ afterQty: after.quantity });
                    await ds.destroy();
                })().catch((e) => { console.error(e); process.exit(1); });
                """
            ),
        )
        res = _parse_result(_run_node(js))
        assert res["afterQty"] == 12, (
            "negative delta was not applied correctly: " + json.dumps(res)
        )

    def test_l2_stale_revision_write_is_rejected_and_quantity_unchanged(self):
        """The core concurrency guarantee: a second adjust on a now-stale revision must fail.

        Two reads obtain the same revision. The first adjustQuantity(rev) succeeds and
        moves the revision forward. The second adjustQuantity, still using the old
        revision, must be REJECTED (rejected promise / thrown error) and must leave the
        quantity at the value the first adjustment left it. A naive implementation that
        ignores expectedRevision (lets both succeed) fails here.
        """
        _require_compiled()
        js = _write_probe(
            "probe_stale",
            _driver(
                """
                (async () => {
                    const ds = await newDataSource();
                    const svc = makeService(ds);
                    const created = await svc.addItem("SKU-C", 100);

                    // Two concurrent readers grab the SAME revision.
                    const readerA = await svc.getItem(created.id);
                    const readerB = await svc.getItem(created.id);
                    const revKey = Object.keys(readerA).find((k) =>
                        /version|revision/i.test(k));
                    const sameRev = readerA[revKey] === readerB[revKey];

                    // First writer wins: +10 with the shared revision.
                    const first = await tryCall(() =>
                        svc.adjustQuantity(created.id, readerA[revKey], 10));
                    const afterFirst = await svc.getItem(created.id);

                    // Second writer is stale: still uses the OLD revision.
                    const second = await tryCall(() =>
                        svc.adjustQuantity(created.id, readerB[revKey], 1000));
                    const afterSecond = await svc.getItem(created.id);

                    out({
                        sameRev: sameRev,
                        firstRejected: first.rejected,
                        secondRejected: second.rejected,
                        qtyAfterFirst: afterFirst.quantity,
                        qtyAfterSecond: afterSecond.quantity,
                        revAfterFirst: afterFirst[revKey],
                        revAfterSecond: afterSecond[revKey],
                    });
                    await ds.destroy();
                })().catch((e) => { console.error(e); process.exit(1); });
                """
            ),
        )
        res = _parse_result(_run_node(js))
        assert res["sameRev"] is True, (
            "two reads did not obtain the same revision: " + json.dumps(res)
        )
        assert res["firstRejected"] is False, (
            "the first (fresh-revision) adjustQuantity should succeed: " + json.dumps(res)
        )
        assert res["qtyAfterFirst"] == 110, (
            "first adjustment did not apply +10: " + json.dumps(res)
        )
        assert res["secondRejected"] is True, (
            "STALE second adjustQuantity was NOT rejected — the service ignores the "
            "expected revision and allows a stale write to overwrite a newer one: "
            + json.dumps(res)
        )
        assert res["qtyAfterSecond"] == 110, (
            "stale write changed the quantity; it must remain at the value left by the "
            "first (winning) adjustment: " + json.dumps(res)
        )

    def test_l2_retry_with_refreshed_revision_succeeds(self):
        """After a stale rejection, re-reading the current revision lets the write succeed.

        This confirms the rejection is genuinely revision-based (not a blanket "second
        write always fails"): with the FRESH revision the same operation goes through.
        """
        _require_compiled()
        js = _write_probe(
            "probe_retry",
            _driver(
                """
                (async () => {
                    const ds = await newDataSource();
                    const svc = makeService(ds);
                    const created = await svc.addItem("SKU-R", 50);
                    const r0 = await svc.getItem(created.id);
                    const revKey = Object.keys(r0).find((k) =>
                        /version|revision/i.test(k));

                    // First adjust succeeds, revision moves on.
                    await svc.adjustQuantity(created.id, r0[revKey], 5);

                    // Stale attempt fails.
                    const stale = await tryCall(() =>
                        svc.adjustQuantity(created.id, r0[revKey], 5));

                    // Re-read fresh revision and retry -> succeeds.
                    const fresh = await svc.getItem(created.id);
                    const retry = await tryCall(() =>
                        svc.adjustQuantity(created.id, fresh[revKey], 5));
                    const final = await svc.getItem(created.id);

                    out({
                        staleRejected: stale.rejected,
                        retryRejected: retry.rejected,
                        finalQty: final.quantity,
                    });
                    await ds.destroy();
                })().catch((e) => { console.error(e); process.exit(1); });
                """
            ),
        )
        res = _parse_result(_run_node(js))
        assert res["staleRejected"] is True, res
        assert res["retryRejected"] is False, (
            "retry with the freshly-read revision should succeed: " + json.dumps(res)
        )
        # 50 +5 (first) +5 (retry) = 60; the stale attempt in the middle is a no-op.
        assert res["finalQty"] == 60, (
            "final quantity wrong; stale write must be a no-op and both valid writes "
            "applied: " + json.dumps(res)
        )

    def test_l2_get_missing_item_returns_null(self):
        """getItem(<missing id>) returns null rather than throwing."""
        _require_compiled()
        js = _write_probe(
            "probe_missing",
            _driver(
                """
                (async () => {
                    const ds = await newDataSource();
                    const svc = makeService(ds);
                    await svc.addItem("SKU-X", 1);
                    const missing = await svc.getItem(987654);
                    out({
                        isNull: missing === null || missing === undefined,
                        type: missing === null ? "null" : typeof missing,
                    });
                    await ds.destroy();
                })().catch((e) => { console.error("THREW", e); process.exit(2); });
                """
            ),
        )
        proc = _run_node(js)
        assert proc.returncode == 0, (
            "getItem(missing) threw instead of returning null:\n"
            + proc.stdout
            + "\n"
            + proc.stderr
        )
        res = _parse_result(proc)
        assert res["isNull"] is True, (
            "getItem(missing) must return null: " + json.dumps(res)
        )

    def test_l2_adjust_on_missing_item_does_not_silently_succeed(self):
        """adjustQuantity against a non-existent item must not pretend success.

        A stub that always resolves "ok" (ignoring storage) would pass earlier happy-path
        cases; here there is no such row, so a correct implementation either rejects or
        leaves the store untouched (no phantom row created).
        """
        _require_compiled()
        js = _write_probe(
            "probe_adjust_missing",
            _driver(
                """
                (async () => {
                    const ds = await newDataSource();
                    const svc = makeService(ds);
                    const result = await tryCall(() =>
                        svc.adjustQuantity(424242, 1, 5));
                    const stillMissing = await svc.getItem(424242);
                    const count = await ds.query("SELECT COUNT(*) AS c FROM stock_item")
                        .catch(async () => {
                            // fall back to whatever the entity table is named
                            const meta = ds.getMetadata(StockItem);
                            return ds.query("SELECT COUNT(*) AS c FROM \\"" + meta.tableName + "\\"");
                        });
                    out({
                        rejected: result.rejected,
                        valueIsFalsy: !result.value,
                        stillMissingNull: stillMissing === null || stillMissing === undefined,
                        rowCount: Number(count[0].c),
                    });
                    await ds.destroy();
                })().catch((e) => { console.error(e); process.exit(1); });
                """
            ),
        )
        res = _parse_result(_run_node(js))
        # Either it rejects, or it returns a falsy/no-op result -- but it must NOT have
        # invented a row, and the item must still be absent.
        assert res["stillMissingNull"] is True, (
            "adjustQuantity on a missing id created a phantom item: " + json.dumps(res)
        )
        assert res["rowCount"] == 0, (
            "adjustQuantity on a missing id inserted a row instead of failing/no-op: "
            + json.dumps(res)
        )
        assert res["rejected"] is True or res["valueIsFalsy"] is True, (
            "adjustQuantity silently reported success for a non-existent item: "
            + json.dumps(res)
        )

    def test_l2_revision_increments_once_per_successful_update(self):
        """Each successful adjustQuantity advances the revision by exactly one step.

        Two sequential valid adjustments (each re-reading the current revision) must move
        the revision forward twice and accumulate both deltas. A counter the service bumps
        by itself, or one that fails to advance, is caught here.
        """
        _require_compiled()
        js = _write_probe(
            "probe_increments",
            _driver(
                """
                (async () => {
                    const ds = await newDataSource();
                    const svc = makeService(ds);
                    const created = await svc.addItem("SKU-SEQ", 0);
                    const v0 = await svc.getItem(created.id);
                    const revKey = Object.keys(v0).find((k) =>
                        /version|revision/i.test(k));

                    await svc.adjustQuantity(created.id, v0[revKey], 3);
                    const v1 = await svc.getItem(created.id);
                    await svc.adjustQuantity(created.id, v1[revKey], 4);
                    const v2 = await svc.getItem(created.id);

                    out({
                        r0: v0[revKey],
                        r1: v1[revKey],
                        r2: v2[revKey],
                        qty: v2.quantity,
                    });
                    await ds.destroy();
                })().catch((e) => { console.error(e); process.exit(1); });
                """
            ),
        )
        res = _parse_result(_run_node(js))
        assert res["r1"] == res["r0"] + 1, (
            "revision did not advance by one after the first update: " + json.dumps(res)
        )
        assert res["r2"] == res["r1"] + 1, (
            "revision did not advance by one after the second update: " + json.dumps(res)
        )
        assert res["qty"] == 7, (
            "accumulated deltas wrong (expected 0+3+4=7): " + json.dumps(res)
        )
