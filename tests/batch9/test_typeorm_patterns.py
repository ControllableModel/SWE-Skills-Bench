"""
Tests for the `typeorm-patterns` skill task (ext9): "Build an Order-Line Composite-Key Layer".

The agent must add, under `test/functional/order-lines/`, a self-contained TypeORM
functional feature whose line items are identified by a MULTI-COLUMN primary key:

  - entity/Order.ts          (id auto-generated, customer string; owns many OrderLines)
  - entity/OrderLine.ts      (composite identity = (orderId, lineNo); product string,
                              quantity int; belongs to one Order)
  - order-line-service.ts    (createOrder / addLine / getLine / linesOf / removeLine)
                              built on a DataSource
  - order-lines.test.ts      (functional test wiring the above through createTestingConnections,
                              restricted to the SQLite driver family)

This pytest verifies the deliverables two ways:
  1. L1 — the four files exist and are minimally well-formed (composite PK present,
     service ops declared, sqlite-only testing connections).
  2. L2 — DYNAMIC EXECUTION against the real TypeORM toolchain: it ensures an
     ormconfig.json restricted to the better-sqlite3 driver, compiles the repo
     (`pnpm run compile`), runs the agent's own compiled functional test under mocha,
     and then runs INDEPENDENT node driver scripts (written by THIS test) against the
     agent's compiled Order/OrderLine/OrderLineService to deep-validate real behavior:
        * createOrder persists with a DB-generated id
        * addLine persists a line keyed by (orderId, lineNo)
        * the SAME lineNo coexists under two DIFFERENT orders (composite key, not single)
        * re-adding an existing (orderId, lineNo) pair is REJECTED and leaves the
          original line unchanged
        * getLine(exact key) returns the line; getLine(missing) returns null
        * linesOf(orderId) returns that order's lines ordered by lineNo asc, none from
          other orders
        * removeLine deletes EXACTLY the one composite-keyed line, leaving siblings intact
        * the DB table actually has a 2-column primary key (PRAGMA table_info pk flags)

A naive solution that identifies lines by a single globally-unique column (e.g. a single
PrimaryGeneratedColumn on lineNo, or a single-column PK) must fail at least one assertion:
the cross-order coexistence case and/or the composite-PK PRAGMA check.
"""

import json
import os
import subprocess
import textwrap

import pytest

REPO_DIR = "/workspace/typeorm"
FEATURE_DIR = os.path.join(REPO_DIR, "test/functional/order-lines")
ENTITY_DIR = os.path.join(FEATURE_DIR, "entity")
ORDER_TS = os.path.join(ENTITY_DIR, "Order.ts")
ORDERLINE_TS = os.path.join(ENTITY_DIR, "OrderLine.ts")
SERVICE_TS = os.path.join(FEATURE_DIR, "order-line-service.ts")
TEST_TS = os.path.join(FEATURE_DIR, "order-lines.test.ts")

COMPILED_TEST_JS = os.path.join(
    REPO_DIR, "build/compiled/test/functional/order-lines/order-lines.test.js"
)
COMPILED_FEATURE_DIR = os.path.join(
    REPO_DIR, "build/compiled/test/functional/order-lines"
)

# Build/compile is heavy in this repo.
COMPILE_TIMEOUT = 1200
RUN_TIMEOUT = 600

# Directory (under REPO_DIR, picked up by tsc include "test") where this pytest drops
# its own independent driver scripts so they get compiled alongside the agent's code.
PROBE_OUT_DIR = os.path.join(
    REPO_DIR, "build/compiled/test/functional/order-lines/__probe__"
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

    We compile probes with a standalone tsc invocation (decorators enabled) that
    emits next to the agent's already-compiled Order/OrderLine/OrderLineService so
    the relative `./` imports in the probe resolve to real compiled modules.
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
    proc = subprocess.run(
        ["bash", "-lc", "node " + js_path],
        cwd=REPO_DIR,
        capture_output=True,
        text=True,
        timeout=RUN_TIMEOUT,
    )
    return proc


def _import_paths():
    """Relative imports (from the probe's compiled location) to the agent modules.

    Probe sits at build/compiled/test/functional/order-lines/__probe__/X.js
    Agent compiled modules sit one dir up; the compiled src is several dirs up.
    """
    return {
        "order": "../entity/Order",
        "orderline": "../entity/OrderLine",
        "service": "../order-line-service",
        "datasource": "../../../../../src",  # build/compiled/src
    }


_DRIVER_PREAMBLE = """
"use strict";
const {{ DataSource }} = require("{datasource}");
const OrderMod = require("{order}");
const OrderLineMod = require("{orderline}");
const ServiceMod = require("{service}");

function pickClass(mod, names) {{
    for (const n of names) if (mod[n]) return mod[n];
    for (const k of Object.keys(mod)) {{
        if (typeof mod[k] === "function") return mod[k];
    }}
    if (mod.default) return mod.default;
    throw new Error("could not locate export in module");
}}

const Order = pickClass(OrderMod, ["Order", "default"]);
const OrderLine = pickClass(OrderLineMod, ["OrderLine", "default"]);
const ServiceExport = pickClass(ServiceMod, ["OrderLineService", "OrderLines", "default"]);

function makeService(ds) {{
    // Support both `new Class(ds)` and a factory `fn(ds)`.
    try {{
        return new ServiceExport(ds);
    }} catch (e) {{
        return ServiceExport(ds);
    }}
}}

async function newDataSource() {{
    const ds = new DataSource({{
        type: "better-sqlite3",
        database: ":memory:",
        entities: [Order, OrderLine],
        synchronize: true,
        dropSchema: true,
    }});
    await ds.initialize();
    return ds;
}}

function out(obj) {{ process.stdout.write("RESULT_JSON:" + JSON.stringify(obj) + "\\n"); }}
"""


def _driver(body):
    paths = _import_paths()
    preamble = _DRIVER_PREAMBLE.format(
        datasource=paths["datasource"],
        order=paths["order"],
        orderline=paths["orderline"],
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
# Test class
# ===========================================================================


class TestTypeormPatterns:
    REPO_DIR = "/workspace/typeorm"

    # ---- L1: deliverables exist and are minimally well-formed -----------

    def test_l1_feature_files_exist(self):
        """All four required deliverable files exist under order-lines/."""
        for p in (ORDER_TS, ORDERLINE_TS, SERVICE_TS, TEST_TS):
            assert os.path.isfile(p), f"missing required deliverable file: {p}"

    def test_l1_order_is_typeorm_entity_with_generated_id(self):
        """Order is a decorated TypeORM entity with a DB-generated numeric id and customer."""
        src = _read(ORDER_TS)
        assert "@Entity" in src, "Order is not annotated with @Entity"
        assert "@PrimaryGeneratedColumn" in src, (
            "Order must have a database-generated primary key (@PrimaryGeneratedColumn)"
        )
        assert "customer" in src, "Order entity does not declare a `customer` field"

    def test_l1_orderline_has_composite_primary_key(self):
        """OrderLine declares a TWO-column primary identity: orderId AND lineNo.

        A single @PrimaryGeneratedColumn (globally-unique line id) is NOT a composite
        key and must not satisfy this. We require two distinct primary-key columns and
        the absence of a generated PK on the line itself.
        """
        src = _read(ORDERLINE_TS)
        assert "@Entity" in src, "OrderLine is not annotated with @Entity"
        # Composite keys in TypeORM are declared with @PrimaryColumn on >= 2 fields
        # (optionally one of them via @PrimaryColumn on the relation). Count them.
        primary_col_count = src.count("@PrimaryColumn")
        assert primary_col_count >= 2, (
            "OrderLine must form its identity from TWO primary columns "
            "(@PrimaryColumn on orderId and lineNo); found "
            f"{primary_col_count} @PrimaryColumn declaration(s)"
        )
        assert "@PrimaryGeneratedColumn" not in src, (
            "OrderLine must NOT have its own globally-generated primary key; its "
            "identity is the (orderId, lineNo) pair"
        )
        assert "lineNo" in src, "OrderLine does not declare a `lineNo` field"
        assert "product" in src, "OrderLine does not declare a `product` field"
        assert "quantity" in src, "OrderLine does not declare a `quantity` field"

    def test_l1_orderline_belongs_to_order(self):
        """OrderLine declares an owning many-to-one relation back to Order."""
        src = _read(ORDERLINE_TS)
        assert "ManyToOne" in src or "JoinColumn" in src, (
            "OrderLine must declare an owning relation (ManyToOne / JoinColumn) to Order"
        )

    def test_l1_service_exports_required_operations(self):
        """order-line-service.ts exports the five named composite-key operations."""
        src = _read(SERVICE_TS)
        for op in (
            "createOrder",
            "addLine",
            "getLine",
            "linesOf",
            "removeLine",
        ):
            assert op in src, f"order-line-service.ts does not define `{op}`"

    def test_l1_test_uses_sqlite_only_testing_connections(self):
        """The functional test restricts testing connections to the SQLite driver family."""
        src = _read(TEST_TS)
        assert "createTestingConnections" in src, (
            "order-lines.test.ts must use createTestingConnections from "
            "../../utils/test-utils"
        )
        assert "enabledDrivers" in src, (
            "order-lines.test.ts must restrict to SQLite-based driver(s) via enabledDrivers"
        )
        assert "sqlite" in src or "sqljs" in src, (
            "enabledDrivers must name a sqlite-family driver (better-sqlite3/sqlite/sqljs)"
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
        for fname in ("entity/Order.js", "entity/OrderLine.js", "order-line-service.js"):
            p = os.path.join(COMPILED_FEATURE_DIR, fname)
            assert os.path.isfile(p), f"expected compiled deliverable {p}"

    def test_l2_agent_functional_test_passes(self):
        """The agent's own order-lines.test.ts passes under mocha (no failures/leaks)."""
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

    def test_l2_orderline_table_has_two_column_primary_key(self):
        """The OrderLine DB table is created with a 2-column composite PRIMARY KEY.

        Uses PRAGMA table_info: a row's `pk` field is > 0 for primary-key columns. A
        composite key marks exactly two columns; a single-column PK (naive impl) marks one.
        """
        _require_compiled()
        js = _write_probe(
            "probe_pk",
            _driver(
                """
                (async () => {
                    const ds = await newDataSource();
                    // discover the OrderLine table name from metadata
                    const md = ds.getMetadata(OrderLine);
                    const table = md.tableName;
                    const cols = await ds.query("PRAGMA table_info(" + table + ")");
                    const pkCols = cols.filter((c) => Number(c.pk) > 0).map((c) => c.name);
                    out({ table: table, pkCols: pkCols, pkCount: pkCols.length });
                    await ds.destroy();
                })().catch((e) => { console.error(e); process.exit(1); });
                """
            ),
        )
        res = _parse_result(_run_node(js))
        assert res["pkCount"] == 2, (
            "OrderLine table must have a TWO-column composite PRIMARY KEY; "
            "PRAGMA reported primary-key columns: " + json.dumps(res)
        )

    def test_l2_create_order_persists_with_generated_id(self):
        """createOrder persists a new order and returns it with a DB-generated id."""
        _require_compiled()
        js = _write_probe(
            "probe_create_order",
            _driver(
                """
                (async () => {
                    const ds = await newDataSource();
                    const svc = makeService(ds);
                    const o1 = await svc.createOrder("Alice");
                    const o2 = await svc.createOrder("Bob");
                    const rows = await ds.getRepository(Order).find();
                    out({
                        id1: o1.id,
                        id2: o2.id,
                        cust1: o1.customer,
                        distinct: o1.id !== o2.id,
                        persistedCount: rows.length,
                    });
                    await ds.destroy();
                })().catch((e) => { console.error(e); process.exit(1); });
                """
            ),
        )
        res = _parse_result(_run_node(js))
        assert isinstance(res["id1"], int) and res["id1"] > 0, res
        assert isinstance(res["id2"], int) and res["id2"] > 0, res
        assert res["distinct"] is True, "createOrder did not generate distinct ids: " + json.dumps(res)
        assert res["cust1"] == "Alice", res
        assert res["persistedCount"] == 2, res

    def test_l2_same_lineNo_coexists_across_orders(self):
        """The composite key allows the SAME lineNo under two DIFFERENT orders.

        This is the discriminating case: a single-column / globally-unique lineNo
        identity would reject the second line-1 and fail here.
        """
        _require_compiled()
        js = _write_probe(
            "probe_coexist",
            _driver(
                """
                (async () => {
                    const ds = await newDataSource();
                    const svc = makeService(ds);
                    const a = await svc.createOrder("OrderA");
                    const b = await svc.createOrder("OrderB");
                    await svc.addLine(a.id, 1, "p-a1", 3);
                    await svc.addLine(a.id, 2, "p-a2", 4);
                    await svc.addLine(b.id, 1, "p-b1", 5);   // SAME lineNo=1, different order
                    const total = await ds.getRepository(OrderLine).count();
                    const la = (await svc.linesOf(a.id)).map((l) => l.lineNo);
                    const lb = (await svc.linesOf(b.id)).map((l) => l.lineNo);
                    out({ total: total, la: la, lb: lb });
                    await ds.destroy();
                })().catch((e) => { console.error(e); process.exit(1); });
                """
            ),
        )
        res = _parse_result(_run_node(js))
        assert res["total"] == 3, (
            "all three lines (incl. line-1 under both orders) must coexist: "
            + json.dumps(res)
        )
        assert res["la"] == [1, 2], res
        assert res["lb"] == [1], res

    def test_l2_duplicate_composite_key_rejected_and_original_unchanged(self):
        """addLine with an existing (orderId, lineNo) is rejected; the original line is intact."""
        _require_compiled()
        js = _write_probe(
            "probe_dup",
            _driver(
                """
                (async () => {
                    const ds = await newDataSource();
                    const svc = makeService(ds);
                    const a = await svc.createOrder("Dup");
                    await svc.addLine(a.id, 1, "first", 7);
                    let rejected = false;
                    try {
                        await svc.addLine(a.id, 1, "second", 99);  // same (orderId, lineNo)
                    } catch (e) {
                        rejected = true;
                    }
                    const line = await svc.getLine(a.id, 1);
                    const count = await ds.getRepository(OrderLine).count();
                    out({
                        rejected: rejected,
                        product: line ? line.product : null,
                        quantity: line ? line.quantity : null,
                        count: count,
                    });
                    await ds.destroy();
                })().catch((e) => { console.error(e); process.exit(1); });
                """
            ),
        )
        res = _parse_result(_run_node(js))
        assert res["rejected"] is True, (
            "re-adding an existing (orderId, lineNo) pair must fail (rejected promise/"
            "thrown error): " + json.dumps(res)
        )
        assert res["count"] == 1, "duplicate add must not insert a second row: " + json.dumps(res)
        assert res["product"] == "first", (
            "original line was overwritten by the rejected duplicate add: " + json.dumps(res)
        )
        assert res["quantity"] == 7, (
            "original line's quantity was mutated by the rejected duplicate add: "
            + json.dumps(res)
        )

    def test_l2_get_line_exact_and_missing(self):
        """getLine returns the composite-keyed line for an exact key, and null when absent."""
        _require_compiled()
        js = _write_probe(
            "probe_get",
            _driver(
                """
                (async () => {
                    const ds = await newDataSource();
                    const svc = makeService(ds);
                    const a = await svc.createOrder("Get");
                    await svc.addLine(a.id, 1, "widget", 2);
                    await svc.addLine(a.id, 5, "gadget", 8);
                    const hit = await svc.getLine(a.id, 5);
                    const missByLine = await svc.getLine(a.id, 99);
                    const missByOrder = await svc.getLine(a.id + 1000, 1);
                    out({
                        hitProduct: hit ? hit.product : null,
                        hitQty: hit ? hit.quantity : null,
                        hitLineNo: hit ? hit.lineNo : null,
                        missByLineNull: missByLine === null || missByLine === undefined,
                        missByOrderNull: missByOrder === null || missByOrder === undefined,
                    });
                    await ds.destroy();
                })().catch((e) => { console.error(e); process.exit(1); });
                """
            ),
        )
        res = _parse_result(_run_node(js))
        assert res["hitProduct"] == "gadget", res
        assert res["hitQty"] == 8, res
        assert res["hitLineNo"] == 5, res
        assert res["missByLineNull"] is True, (
            "getLine with a non-existent lineNo must return null: " + json.dumps(res)
        )
        assert res["missByOrderNull"] is True, (
            "getLine with a non-existent orderId must return null: " + json.dumps(res)
        )

    def test_l2_lines_of_ordered_and_scoped(self):
        """linesOf(orderId) returns that order's lines by lineNo asc and none from other orders."""
        _require_compiled()
        js = _write_probe(
            "probe_linesof",
            _driver(
                """
                (async () => {
                    const ds = await newDataSource();
                    const svc = makeService(ds);
                    const a = await svc.createOrder("Scoped");
                    const b = await svc.createOrder("Other");
                    // insert out of order to prove the service sorts.
                    await svc.addLine(a.id, 3, "a3", 1);
                    await svc.addLine(a.id, 1, "a1", 1);
                    await svc.addLine(a.id, 2, "a2", 1);
                    await svc.addLine(b.id, 1, "b1", 1);
                    await svc.addLine(b.id, 2, "b2", 1);
                    const lines = await svc.linesOf(a.id);
                    out({
                        lineNos: lines.map((l) => l.lineNo),
                        products: lines.map((l) => l.product),
                        count: lines.length,
                    });
                    await ds.destroy();
                })().catch((e) => { console.error(e); process.exit(1); });
                """
            ),
        )
        res = _parse_result(_run_node(js))
        assert res["count"] == 3, (
            "linesOf must return only the target order's lines (3, not "
            + str(res["count"]) + "): " + json.dumps(res)
        )
        assert res["lineNos"] == [1, 2, 3], (
            "linesOf must order lines by lineNo ascending: " + json.dumps(res)
        )
        assert res["products"] == ["a1", "a2", "a3"], res

    def test_l2_remove_line_deletes_exactly_one(self):
        """removeLine deletes exactly the composite-keyed line, leaving siblings intact."""
        _require_compiled()
        js = _write_probe(
            "probe_remove",
            _driver(
                """
                (async () => {
                    const ds = await newDataSource();
                    const svc = makeService(ds);
                    const a = await svc.createOrder("Rem");
                    const b = await svc.createOrder("Keep");
                    await svc.addLine(a.id, 1, "a1", 1);
                    await svc.addLine(a.id, 2, "a2", 1);
                    await svc.addLine(a.id, 3, "a3", 1);
                    await svc.addLine(b.id, 2, "b2", 1);   // same lineNo=2 under other order
                    await svc.removeLine(a.id, 2);
                    const remaining = (await svc.linesOf(a.id)).map((l) => l.lineNo);
                    const removed = await svc.getLine(a.id, 2);
                    const otherStill = await svc.getLine(b.id, 2);
                    const total = await ds.getRepository(OrderLine).count();
                    out({
                        remaining: remaining,
                        removedIsNull: removed === null || removed === undefined,
                        otherProduct: otherStill ? otherStill.product : null,
                        total: total,
                    });
                    await ds.destroy();
                })().catch((e) => { console.error(e); process.exit(1); });
                """
            ),
        )
        res = _parse_result(_run_node(js))
        assert res["removedIsNull"] is True, (
            "removeLine did not delete the targeted (orderId, lineNo): " + json.dumps(res)
        )
        assert res["remaining"] == [1, 3], (
            "removeLine deleted the wrong set of lines: " + json.dumps(res)
        )
        assert res["otherProduct"] == "b2", (
            "removeLine over-deleted the same lineNo under a different order: "
            + json.dumps(res)
        )
        assert res["total"] == 3, (
            "exactly one line should have been removed (4 -> 3): " + json.dumps(res)
        )

    def test_l2_remove_missing_line_is_noop(self):
        """removeLine on a non-existent composite key removes nothing (no over-deletion)."""
        _require_compiled()
        js = _write_probe(
            "probe_remove_missing",
            _driver(
                """
                (async () => {
                    const ds = await newDataSource();
                    const svc = makeService(ds);
                    const a = await svc.createOrder("NoOp");
                    await svc.addLine(a.id, 1, "a1", 1);
                    await svc.addLine(a.id, 2, "a2", 1);
                    let threw = false;
                    try {
                        await svc.removeLine(a.id, 999);   // not present
                    } catch (e) {
                        threw = true;
                    }
                    const remaining = (await svc.linesOf(a.id)).map((l) => l.lineNo);
                    out({ threw: threw, remaining: remaining });
                    await ds.destroy();
                })().catch((e) => { console.error(e); process.exit(1); });
                """
            ),
        )
        res = _parse_result(_run_node(js))
        assert res["remaining"] == [1, 2], (
            "removeLine on a missing key must not delete existing lines: " + json.dumps(res)
        )
