"""
Tests for the `typeorm-patterns` skill task (variant ext3):
"Build a Recoverable Document Trash Layer".

The agent must add, under `test/functional/document-trash/`, a self-contained
TypeORM functional feature:
  - entity/Document.ts       (id auto-generated, title, body:text, created & modified
                              timestamps the ORM maintains automatically, and a
                              discard timestamp that is empty while active and set
                              once discarded — i.e. a recoverable/soft-discard row)
  - trash-service.ts         (create / listActive / discard / listTrashed / restore /
                              purge) built on a DataSource
  - document-trash.test.ts   (functional test wiring the above through
                              createTestingConnections, SQLite drivers only)

Verification strategy:
  1. L1 — the three files exist and are minimally well-formed (decorated entity with a
     generated PK + a discard/delete timestamp column; service exports the six ops;
     test restricts to the sqlite driver family).
  2. L2 — DYNAMIC EXECUTION against the real TypeORM toolchain: ensure an
     ormconfig.json restricted to the better-sqlite3 driver, compile the repo
     (`pnpm run compile`), run the agent's own compiled functional test under mocha,
     and then run INDEPENDENT driver scripts (written by THIS test) against the
     agent's compiled Document/TrashService to deep-validate real behavior:
        * create() persists an active doc with generated id + creation timestamp set
          and an empty discard timestamp
        * listActive() auto-excludes discarded rows WITHOUT any caller-supplied filter
        * discard() does NOT physically delete the row (a query that explicitly
          includes discarded rows still finds it) and sets the discard timestamp
        * listTrashed() returns only discarded docs
        * restore() returns the doc to listActive(), removes it from listTrashed(),
          and clears the discard timestamp
        * purge() physically removes the row so NO query (even one including discarded
          rows) can retrieve it
        * the 3-create / discard-one scenario yields active=2, trashed=1

A naive solution that physically deletes rows on discard, or that fails to
auto-exclude discarded rows from listActive(), MUST fail at least one assertion.
"""

import json
import os
import subprocess
import textwrap

import pytest

REPO_DIR = "/workspace/typeorm"
FEATURE_DIR = os.path.join(REPO_DIR, "test/functional/document-trash")
ENTITY_DIR = os.path.join(FEATURE_DIR, "entity")
DOCUMENT_TS = os.path.join(ENTITY_DIR, "Document.ts")
SERVICE_TS = os.path.join(FEATURE_DIR, "trash-service.ts")
TEST_TS = os.path.join(FEATURE_DIR, "document-trash.test.ts")

COMPILED_TEST_JS = os.path.join(
    REPO_DIR,
    "build/compiled/test/functional/document-trash/document-trash.test.js",
)
COMPILED_FEATURE_DIR = os.path.join(
    REPO_DIR, "build/compiled/test/functional/document-trash"
)

# Build/compile is heavy in this repo.
COMPILE_TIMEOUT = 1200
RUN_TIMEOUT = 600

# Directory (under the compiled tree) where this pytest drops its own independent
# driver scripts so their relative `./` imports resolve to the agent's compiled code.
PROBE_OUT_DIR = os.path.join(
    REPO_DIR, "build/compiled/test/functional/document-trash/__probe__"
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
    """Write a TS probe under the compiled feature dir and return its .js path.

    Compiled in place (CommonJS, decorators on) so its relative `./` imports resolve
    to the agent's already-compiled Document/TrashService sibling modules.
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
    """Relative imports (from the probe's compiled location) to the agent modules.

    Probe sits at build/compiled/test/functional/document-trash/__probe__/X.js
    Agent compiled modules sit one dir up; the ORM src is build/compiled/src.
    """
    return {
        "document": "../entity/Document",
        "service": "../trash-service",
        "datasource": "../../../../../src",
    }


_DRIVER_PREAMBLE = """
"use strict";
const { DataSource, IsNull, Not } = require("{datasource}");
const DocumentMod = require("{document}");
const ServiceMod = require("{service}");

function pickClass(mod, names) {{
    for (const n of names) if (mod[n]) return mod[n];
    for (const k of Object.keys(mod)) {{
        if (typeof mod[k] === "function") return mod[k];
    }}
    if (mod.default) return mod.default;
    throw new Error("could not locate export in module");
}}

const Document = pickClass(DocumentMod, ["Document", "default"]);
const ServiceExport = pickClass(
    ServiceMod,
    ["TrashService", "DocumentTrashService", "TrashService", "createTrashService", "default"]
);

function makeService(ds) {{
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
        entities: [Document],
        synchronize: true,
        dropSchema: true,
    }});
    await ds.initialize();
    return ds;
}}

// Count document rows directly in the DB, optionally including discarded rows,
// without trusting the service. We discover the table + the soft-delete timestamp
// column from the schema so we work regardless of the agent's exact column names.
async function dbDiscoverTable(ds) {{
    const md = ds.getMetadata(Document);
    return md.tableName;
}}

function out(obj) {{ process.stdout.write("RESULT_JSON:" + JSON.stringify(obj) + "\\n"); }}
"""


def _driver(body):
    paths = _import_paths()
    preamble = _DRIVER_PREAMBLE.format(
        datasource=paths["datasource"],
        document=paths["document"],
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
        """All three required deliverable files exist under document-trash/."""
        for p in (DOCUMENT_TS, SERVICE_TS, TEST_TS):
            assert os.path.isfile(p), f"missing required deliverable file: {p}"

    def test_l1_document_is_typeorm_entity_with_generated_pk(self):
        """Document is a decorated TypeORM entity with a database-generated primary key."""
        src = _read(DOCUMENT_TS)
        assert "@Entity" in src, "Document is not annotated with @Entity"
        assert (
            "@PrimaryGeneratedColumn" in src
        ), "Document lacks a database-generated primary key"
        assert "title" in src, "Document entity does not declare a `title` field"
        assert "body" in src, "Document entity does not declare a `body` field"

    def test_l1_document_has_managed_timestamps(self):
        """Document declares ORM-managed created/modified timestamps."""
        src = _read(DOCUMENT_TS)
        assert (
            "@CreateDateColumn" in src
        ), "Document must use @CreateDateColumn for the auto-maintained creation timestamp"
        assert (
            "@UpdateDateColumn" in src
        ), "Document must use @UpdateDateColumn for the auto-maintained modified timestamp"

    def test_l1_document_has_soft_discard_timestamp(self):
        """Document declares a discard/soft-delete timestamp column (recoverable, not a hard delete)."""
        src = _read(DOCUMENT_TS)
        # The discard timestamp that is empty while active and set when discarded, and that
        # auto-excludes the row from ordinary listings, is TypeORM's @DeleteDateColumn.
        assert "@DeleteDateColumn" in src, (
            "Document must declare a soft-discard timestamp via @DeleteDateColumn so "
            "the row is retained and auto-excluded from listings when discarded"
        )

    def test_l1_service_exports_required_operations(self):
        """trash-service.ts exports the six named trash operations."""
        src = _read(SERVICE_TS)
        for op in (
            "create",
            "listActive",
            "discard",
            "listTrashed",
            "restore",
            "purge",
        ):
            assert op in src, f"trash-service.ts does not define `{op}`"

    def test_l1_test_uses_sqlite_only_testing_connections(self):
        """The functional test restricts testing connections to the SQLite driver family."""
        src = _read(TEST_TS)
        assert "createTestingConnections" in src, (
            "document-trash.test.ts must use createTestingConnections from "
            "../../utils/test-utils"
        )
        assert "enabledDrivers" in src, (
            "document-trash.test.ts must restrict to SQLite-based driver(s) via "
            "enabledDrivers"
        )
        assert (
            "sqlite" in src or "sqljs" in src
        ), "enabledDrivers must name a sqlite-family driver (better-sqlite3/sqlite/sqljs)"

    # ---- L2: build & the agent's own functional test --------------------

    def test_l2_repo_compiles(self):
        """`pnpm run compile` succeeds with the deliverables in place (tsc, strict)."""
        _require_compiled()
        assert os.path.isfile(COMPILED_TEST_JS), (
            "expected compiled functional test at "
            + COMPILED_TEST_JS
            + " (compile succeeded but the test file was not emitted)"
        )
        for fname in ("entity/Document.js", "trash-service.js"):
            p = os.path.join(COMPILED_FEATURE_DIR, fname)
            assert os.path.isfile(p), f"expected compiled deliverable {p}"

    def test_l2_agent_functional_test_passes(self):
        """The agent's own document-trash.test.ts passes under mocha (no failures/leaks)."""
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

    def test_l2_create_persists_active_with_timestamps(self):
        """create() persists an active doc with a generated id, a creation timestamp, and no discard timestamp."""
        _require_compiled()
        js = _write_probe(
            "probe_create",
            _driver(
                """
                (async () => {
                    const ds = await newDataSource();
                    const svc = makeService(ds);
                    const doc = await svc.create("Title-A", "Body of A");
                    const table = await dbDiscoverTable(ds);
                    // Pull the row directly from the DB to inspect raw timestamp state.
                    const raw = await ds.query("SELECT * FROM " + table + " WHERE id = " + doc.id);
                    const md = ds.getMetadata(Document);
                    const deleteCol = md.columns.find((c) => c.isDeleteDate);
                    const createCol = md.columns.find((c) => c.isCreateDate);
                    const deleteDbName = deleteCol ? deleteCol.databaseName : null;
                    const createDbName = createCol ? createCol.databaseName : null;
                    const row = raw[0] || {};
                    out({
                        id: doc.id,
                        title: doc.title,
                        body: doc.body,
                        hasDeleteCol: !!deleteCol,
                        hasCreateCol: !!createCol,
                        discardEmpty: deleteDbName ? (row[deleteDbName] === null || row[deleteDbName] === undefined) : null,
                        createSet: createDbName ? (row[createDbName] !== null && row[createDbName] !== undefined) : null,
                        rowCount: raw.length,
                    });
                    await ds.destroy();
                })().catch((e) => { console.error(e); process.exit(1); });
                """
            ),
        )
        res = _parse_result(_run_node(js))
        assert isinstance(res["id"], int) and res["id"] > 0, res
        assert res["title"] == "Title-A" and res["body"] == "Body of A", res
        assert res["hasDeleteCol"] is True, (
            "Document has no @DeleteDateColumn -> discard cannot be a recoverable soft delete: "
            + json.dumps(res)
        )
        assert res["hasCreateCol"] is True, res
        assert res["rowCount"] == 1, res
        assert res["createSet"] is True, "creation timestamp was not populated: " + json.dumps(res)
        assert res["discardEmpty"] is True, (
            "a freshly created document must have an EMPTY discard timestamp: "
            + json.dumps(res)
        )

    def test_l2_three_create_one_discard_split(self):
        """Create 3, discard 1 -> listActive() returns 2 and listTrashed() returns 1."""
        _require_compiled()
        js = _write_probe(
            "probe_split",
            _driver(
                """
                (async () => {
                    const ds = await newDataSource();
                    const svc = makeService(ds);
                    const a = await svc.create("A", "ba");
                    const b = await svc.create("B", "bb");
                    const c = await svc.create("C", "bc");
                    await svc.discard(b.id);
                    const active = await svc.listActive();
                    const trashed = await svc.listTrashed();
                    out({
                        activeCount: active.length,
                        activeTitles: active.map((d) => d.title).sort(),
                        trashedCount: trashed.length,
                        trashedTitles: trashed.map((d) => d.title).sort(),
                    });
                    await ds.destroy();
                })().catch((e) => { console.error(e); process.exit(1); });
                """
            ),
        )
        res = _parse_result(_run_node(js))
        assert res["activeCount"] == 2, res
        assert res["activeTitles"] == ["A", "C"], res
        assert res["trashedCount"] == 1, res
        assert res["trashedTitles"] == ["B"], res

    def test_l2_listactive_autoexcludes_without_caller_filter(self):
        """listActive() must auto-exclude discarded rows; the caller passes no 'not discarded' filter."""
        _require_compiled()
        # Discriminative: an implementation that simply returns find() (all rows) would
        # leak the discarded doc here. A genuine soft-delete-aware listing excludes it.
        js = _write_probe(
            "probe_autoexclude",
            _driver(
                """
                (async () => {
                    const ds = await newDataSource();
                    const svc = makeService(ds);
                    const keep = await svc.create("keep", "k");
                    const gone = await svc.create("gone", "g");
                    await svc.discard(gone.id);
                    const active = await svc.listActive();
                    const ids = active.map((d) => d.id);
                    out({
                        ids: ids,
                        containsDiscarded: ids.includes(gone.id),
                        containsKept: ids.includes(keep.id),
                        count: active.length,
                    });
                    await ds.destroy();
                })().catch((e) => { console.error(e); process.exit(1); });
                """
            ),
        )
        res = _parse_result(_run_node(js))
        assert res["containsKept"] is True, res
        assert res["containsDiscarded"] is False, (
            "listActive() leaked a discarded document -> it does not auto-exclude trashed rows: "
            + json.dumps(res)
        )
        assert res["count"] == 1, res

    def test_l2_discard_does_not_physically_delete_row(self):
        """discard() retains the physical row (a query that includes discarded rows still finds it) and sets the discard timestamp."""
        _require_compiled()
        # Discriminative: a naive `delete`/`remove` implementation drops the row, so a
        # raw COUNT(*) and a withDeleted lookup would both fail to find it.
        js = _write_probe(
            "probe_discard_keeps_row",
            _driver(
                """
                (async () => {
                    const ds = await newDataSource();
                    const svc = makeService(ds);
                    const doc = await svc.create("soft", "s");
                    await svc.discard(doc.id);
                    const table = await dbDiscoverTable(ds);
                    const md = ds.getMetadata(Document);
                    const deleteCol = md.columns.find((c) => c.isDeleteDate);
                    const deleteDbName = deleteCol ? deleteCol.databaseName : null;
                    // Raw DB count: the row must still physically exist.
                    const rawCount = await ds.query("SELECT COUNT(*) AS c FROM " + table + " WHERE id = " + doc.id);
                    const raw = await ds.query("SELECT * FROM " + table + " WHERE id = " + doc.id);
                    // A withDeleted ORM lookup must also still find it.
                    const repo = ds.getRepository(Document);
                    const withDeleted = await repo.findOne({ where: { id: doc.id }, withDeleted: true });
                    const row = raw[0] || {};
                    out({
                        rawRowCount: Number(rawCount[0].c),
                        withDeletedFound: !!withDeleted,
                        discardSet: deleteDbName ? (row[deleteDbName] !== null && row[deleteDbName] !== undefined) : null,
                    });
                    await ds.destroy();
                })().catch((e) => { console.error(e); process.exit(1); });
                """
            ),
        )
        res = _parse_result(_run_node(js))
        assert res["rawRowCount"] == 1, (
            "discard() physically deleted the row (raw DB count == 0); discard must be a "
            "recoverable soft delete, not a hard delete: " + json.dumps(res)
        )
        assert res["withDeletedFound"] is True, (
            "a query explicitly including discarded rows could not find the doc after discard: "
            + json.dumps(res)
        )
        assert res["discardSet"] is True, (
            "discard() did not set the discard timestamp on the row: " + json.dumps(res)
        )

    def test_l2_listtrashed_returns_only_discarded(self):
        """listTrashed() returns exactly the discarded docs and excludes active ones."""
        _require_compiled()
        js = _write_probe(
            "probe_trashed",
            _driver(
                """
                (async () => {
                    const ds = await newDataSource();
                    const svc = makeService(ds);
                    const a = await svc.create("act1", "x");
                    const b = await svc.create("trash1", "x");
                    const c = await svc.create("act2", "x");
                    const d = await svc.create("trash2", "x");
                    await svc.discard(b.id);
                    await svc.discard(d.id);
                    const trashed = await svc.listTrashed();
                    out({
                        count: trashed.length,
                        titles: trashed.map((x) => x.title).sort(),
                        ids: trashed.map((x) => x.id).sort((p, q) => p - q),
                        expectedIds: [b.id, d.id].sort((p, q) => p - q),
                    });
                    await ds.destroy();
                })().catch((e) => { console.error(e); process.exit(1); });
                """
            ),
        )
        res = _parse_result(_run_node(js))
        assert res["count"] == 2, res
        assert res["titles"] == ["trash1", "trash2"], res
        assert res["ids"] == res["expectedIds"], res

    def test_l2_restore_round_trip_clears_discard_timestamp(self):
        """restore() returns the doc to listActive(), removes it from listTrashed(), and clears the discard timestamp."""
        _require_compiled()
        js = _write_probe(
            "probe_restore",
            _driver(
                """
                (async () => {
                    const ds = await newDataSource();
                    const svc = makeService(ds);
                    const doc = await svc.create("round", "r");
                    await svc.discard(doc.id);
                    // sanity: discarded now
                    const trashedBefore = (await svc.listTrashed()).map((d) => d.id);
                    const activeBefore = (await svc.listActive()).map((d) => d.id);
                    await svc.restore(doc.id);
                    const activeAfter = (await svc.listActive()).map((d) => d.id);
                    const trashedAfter = (await svc.listTrashed()).map((d) => d.id);
                    const table = await dbDiscoverTable(ds);
                    const md = ds.getMetadata(Document);
                    const deleteCol = md.columns.find((c) => c.isDeleteDate);
                    const deleteDbName = deleteCol ? deleteCol.databaseName : null;
                    const raw = await ds.query("SELECT * FROM " + table + " WHERE id = " + doc.id);
                    const row = raw[0] || {};
                    out({
                        discardedBefore: trashedBefore.includes(doc.id) && !activeBefore.includes(doc.id),
                        activeAfter: activeAfter.includes(doc.id),
                        trashedAfter: trashedAfter.includes(doc.id),
                        discardCleared: deleteDbName ? (row[deleteDbName] === null || row[deleteDbName] === undefined) : null,
                    });
                    await ds.destroy();
                })().catch((e) => { console.error(e); process.exit(1); });
                """
            ),
        )
        res = _parse_result(_run_node(js))
        assert res["discardedBefore"] is True, (
            "precondition failed: doc was not discarded before restore: " + json.dumps(res)
        )
        assert res["activeAfter"] is True, (
            "restore() did not return the doc to listActive(): " + json.dumps(res)
        )
        assert res["trashedAfter"] is False, (
            "restore() left the doc in listTrashed(): " + json.dumps(res)
        )
        assert res["discardCleared"] is True, (
            "restore() did not clear the discard timestamp on the row: " + json.dumps(res)
        )

    def test_l2_purge_physically_removes_row(self):
        """purge() permanently deletes the row so NO query (even including discarded rows) retrieves it."""
        _require_compiled()
        js = _write_probe(
            "probe_purge",
            _driver(
                """
                (async () => {
                    const ds = await newDataSource();
                    const svc = makeService(ds);
                    const live = await svc.create("live", "l");
                    const doomed = await svc.create("doomed", "d");
                    // purge a discarded doc to prove purge reaches even trashed rows.
                    await svc.discard(doomed.id);
                    await svc.purge(doomed.id);
                    const table = await dbDiscoverTable(ds);
                    const rawCount = await ds.query("SELECT COUNT(*) AS c FROM " + table + " WHERE id = " + doomed.id);
                    const repo = ds.getRepository(Document);
                    const withDeleted = await repo.findOne({ where: { id: doomed.id }, withDeleted: true });
                    const totalRows = await ds.query("SELECT COUNT(*) AS c FROM " + table);
                    out({
                        rawRowCount: Number(rawCount[0].c),
                        withDeletedFound: !!withDeleted,
                        totalRows: Number(totalRows[0].c),
                        liveId: live.id,
                    });
                    await ds.destroy();
                })().catch((e) => { console.error(e); process.exit(1); });
                """
            ),
        )
        res = _parse_result(_run_node(js))
        assert res["rawRowCount"] == 0, (
            "purge() did not physically remove the row from the DB: " + json.dumps(res)
        )
        assert res["withDeletedFound"] is False, (
            "purge()d doc is still retrievable via a query that includes discarded rows: "
            + json.dumps(res)
        )
        # The unrelated live doc must survive -> purge is scoped, not a table wipe.
        assert res["totalRows"] == 1, (
            "purge() over-deleted (removed unrelated documents): " + json.dumps(res)
        )

    def test_l2_discarded_doc_invisible_to_listactive_until_restored(self):
        """End-to-end lifecycle: active -> discard (hidden) -> restore (visible) -> purge (gone)."""
        _require_compiled()
        js = _write_probe(
            "probe_lifecycle",
            _driver(
                """
                (async () => {
                    const ds = await newDataSource();
                    const svc = makeService(ds);
                    const doc = await svc.create("life", "x");
                    const step = {};
                    step.afterCreate = (await svc.listActive()).map((d) => d.id).includes(doc.id);
                    await svc.discard(doc.id);
                    step.activeAfterDiscard = (await svc.listActive()).map((d) => d.id).includes(doc.id);
                    step.trashedAfterDiscard = (await svc.listTrashed()).map((d) => d.id).includes(doc.id);
                    await svc.restore(doc.id);
                    step.activeAfterRestore = (await svc.listActive()).map((d) => d.id).includes(doc.id);
                    step.trashedAfterRestore = (await svc.listTrashed()).map((d) => d.id).includes(doc.id);
                    await svc.purge(doc.id);
                    step.activeAfterPurge = (await svc.listActive()).map((d) => d.id).includes(doc.id);
                    step.trashedAfterPurge = (await svc.listTrashed()).map((d) => d.id).includes(doc.id);
                    out(step);
                    await ds.destroy();
                })().catch((e) => { console.error(e); process.exit(1); });
                """
            ),
        )
        res = _parse_result(_run_node(js))
        assert res["afterCreate"] is True, "new doc not visible in listActive: " + json.dumps(res)
        assert res["activeAfterDiscard"] is False, "discarded doc still in listActive: " + json.dumps(res)
        assert res["trashedAfterDiscard"] is True, "discarded doc not in listTrashed: " + json.dumps(res)
        assert res["activeAfterRestore"] is True, "restored doc not back in listActive: " + json.dumps(res)
        assert res["trashedAfterRestore"] is False, "restored doc still in listTrashed: " + json.dumps(res)
        assert res["activeAfterPurge"] is False, "purged doc still in listActive: " + json.dumps(res)
        assert res["trashedAfterPurge"] is False, "purged doc still in listTrashed: " + json.dumps(res)
