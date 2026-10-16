"""
Tests for the `typeorm-patterns` skill task (variant ext10):
    "Build an Audit-Trail Layer Driven by Persistence Events".

The agent must add, under `test/functional/audit-trail/`, a self-contained TypeORM
functional feature:
  - entity/Account.ts        (id auto-generated, name, status)
  - entity/AuditLog.ts       (id auto-generated, entityId, action:"created"|"updated",
                              an ORM-set timestamp column)
  - audit-subscriber.ts      (an @EventSubscriber that listens to Account's persistence
                              lifecycle and, as a SIDE EFFECT of insert/update, writes
                              exactly one AuditLog row in the SAME persistence operation)
  - audit-service.ts         (createAccount / changeStatus / historyOf built on a DataSource)
  - audit-trail.test.ts      (functional test wiring entities + subscriber through
                              createTestingConnections against the SQLite driver)

Verification strategy
  1. L1 — the five deliverable files exist and are minimally well-formed (decorated
     entities w/ generated PKs, a real EntitySubscriberInterface implementation that
     hooks afterInsert/afterUpdate, a service exporting the three operations, and a
     functional test restricted to the sqlite driver family).
  2. L2 — DYNAMIC EXECUTION against the real TypeORM toolchain: ensure an
     ormconfig.json restricted to better-sqlite3, compile the repo (`pnpm run compile`),
     run the agent's own compiled functional test under mocha, and then run INDEPENDENT
     node driver scripts (written BY THIS pytest, not by the agent) against the agent's
     compiled Account / AuditLog / AuditSubscriber / AuditService to deep-validate:
        * createAccount writes exactly ONE "created" audit row (entityId, timestamp set)
        * changeStatus writes exactly ONE "updated" audit row, status actually mutated
        * historyOf returns rows ordered by id asc: ["created", "updated"]
        * two independent accounts each get exactly one "created" row, no cross-contam
        * the audit row is present immediately after save (same persistence op)
        * CRITICAL discriminator: with the subscriber NOT registered, the history is
          EMPTY — proving the events (not manual inserts inside the service) drive audit

A naive solution that inserts AuditLog rows manually inside the service methods (rather
than via the persistence-event subscriber) fails the "no-subscriber => empty history"
discriminator. A stub that hardcodes a single row / ignores the action / shares state
across accounts also fails.
"""

import json
import os
import subprocess
import textwrap

import pytest

REPO_DIR = "/workspace/typeorm"
FEATURE_DIR = os.path.join(REPO_DIR, "test/functional/audit-trail")
ENTITY_DIR = os.path.join(FEATURE_DIR, "entity")
ACCOUNT_TS = os.path.join(ENTITY_DIR, "Account.ts")
AUDITLOG_TS = os.path.join(ENTITY_DIR, "AuditLog.ts")
SUBSCRIBER_TS = os.path.join(FEATURE_DIR, "audit-subscriber.ts")
SERVICE_TS = os.path.join(FEATURE_DIR, "audit-service.ts")
TEST_TS = os.path.join(FEATURE_DIR, "audit-trail.test.ts")

COMPILED_TEST_JS = os.path.join(
    REPO_DIR, "build/compiled/test/functional/audit-trail/audit-trail.test.js"
)
COMPILED_FEATURE_DIR = os.path.join(
    REPO_DIR, "build/compiled/test/functional/audit-trail"
)

# Build/compile is heavy in this repo.
COMPILE_TIMEOUT = 1200
RUN_TIMEOUT = 600

# Where this pytest drops its own independent driver scripts. We compile probes in
# place (standalone tsc) next to the agent's already-compiled modules so the relative
# `./` imports in the probe resolve to real compiled modules.
PROBE_OUT_DIR = os.path.join(
    REPO_DIR, "build/compiled/test/functional/audit-trail/__probe__"
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
    emits next to the agent's already-compiled modules so the relative `./` imports
    in the probe resolve to real compiled modules.
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

    Probe sits at build/compiled/test/functional/audit-trail/__probe__/X.js
    Agent compiled modules sit one dir up.
    """
    return {
        "account": "../entity/Account",
        "auditlog": "../entity/AuditLog",
        "subscriber": "../audit-subscriber",
        "service": "../audit-service",
        "datasource": "../../../../../src",  # build/compiled/src
    }


# The preamble resolves the agent's exported classes robustly (named or default),
# and offers two DataSource builders: one WITH the audit subscriber registered, one
# WITHOUT it (for the discriminator test). It also exposes a helper to read AuditLog
# rows straight from the DB (action + entityId) so we never trust the service's own
# bookkeeping.
_DRIVER_PREAMBLE = """
"use strict";
const { DataSource } = require("{datasource}");
const AccountMod = require("{account}");
const AuditLogMod = require("{auditlog}");
const SubscriberMod = require("{subscriber}");
const ServiceMod = require("{service}");

function pickExport(mod, names) {{
    for (const n of names) if (mod[n]) return mod[n];
    for (const k of Object.keys(mod)) {{
        if (typeof mod[k] === "function") return mod[k];
    }}
    if (mod.default) return mod.default;
    throw new Error("could not locate export in module");
}}

const Account = pickExport(AccountMod, ["Account", "default"]);
const AuditLog = pickExport(AuditLogMod, ["AuditLog", "default"]);
const AuditSubscriber = pickExport(
    SubscriberMod, ["AuditSubscriber", "AuditLogSubscriber", "AccountSubscriber", "default"]);
const ServiceExport = pickExport(
    ServiceMod, ["AuditService", "AuditTrailService", "Service", "default"]);

function makeService(ds) {{
    try {{
        return new ServiceExport(ds);
    }} catch (e) {{
        return ServiceExport(ds);
    }}
}}

async function newDataSource(withSubscriber) {{
    const opts = {{
        type: "better-sqlite3",
        database: ":memory:",
        entities: [Account, AuditLog],
        synchronize: true,
        dropSchema: true,
    }};
    if (withSubscriber) opts.subscribers = [AuditSubscriber];
    const ds = new DataSource(opts);
    await ds.initialize();
    return ds;
}}

// Read AuditLog rows directly from the DB so we don't trust the service's view.
// Resolves the physical table + column names dynamically (TypeORM may name the
// table "audit_log" or "auditLog" etc.).
async function rawAuditRows(ds) {{
    const tables = await ds.query(
        "SELECT name FROM sqlite_master WHERE type='table'");
    const tnames = tables.map((r) => r.name);
    const tname = tnames.find((n) => /audit/i.test(n) && /log/i.test(n))
        || tnames.find((n) => /audit/i.test(n));
    if (!tname) return {{ table: null, rows: [] }};
    const cols = await ds.query("PRAGMA table_info('" + tname + "')");
    const cnames = cols.map((c) => c.name);
    const actionCol = cnames.find((c) => /action/i.test(c));
    const entityCol = cnames.find((c) => /entity/i.test(c) && /id/i.test(c))
        || cnames.find((c) => /entity/i.test(c));
    const idCol = cnames.find((c) => c.toLowerCase() === "id") || cnames[0];
    const rows = await ds.query('SELECT * FROM "' + tname + '" ORDER BY "' + idCol + '" ASC');
    return {{
        table: tname,
        idCol, actionCol, entityCol,
        rows: rows.map((r) => ({{
            id: r[idCol],
            action: actionCol ? r[actionCol] : undefined,
            entityId: entityCol ? r[entityCol] : undefined,
            raw: r,
        }})),
    }};
}}

function out(obj) {{ process.stdout.write("RESULT_JSON:" + JSON.stringify(obj) + "\\n"); }}
"""


def _driver(body):
    paths = _import_paths()
    preamble = _DRIVER_PREAMBLE.format(
        datasource=paths["datasource"],
        account=paths["account"],
        auditlog=paths["auditlog"],
        subscriber=paths["subscriber"],
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
# Tests
# ===========================================================================


class TestTypeormPatterns:
    REPO_DIR = "/workspace/typeorm"

    # ---- L1 : deliverable files exist and are minimally well-formed -----

    def test_l1_feature_files_exist(self):
        """All five required deliverable files exist under audit-trail/."""
        for p in (ACCOUNT_TS, AUDITLOG_TS, SUBSCRIBER_TS, SERVICE_TS, TEST_TS):
            assert os.path.isfile(p), f"missing required deliverable file: {p}"

    def test_l1_entities_are_typeorm_entities(self):
        """Account and AuditLog are decorated TypeORM entities with generated PKs."""
        account = _read(ACCOUNT_TS)
        auditlog = _read(AUDITLOG_TS)
        for name, src in (("Account", account), ("AuditLog", auditlog)):
            assert "@Entity" in src, f"{name} is not annotated with @Entity"
            assert (
                "@PrimaryGeneratedColumn" in src
            ), f"{name} lacks a database-generated primary key"
        # Account fields.
        assert "name" in account, "Account entity does not declare a `name` field"
        assert "status" in account, "Account entity does not declare a `status` field"
        # AuditLog fields: entityId, action, and an ORM-set timestamp column.
        assert "entityId" in auditlog or "entity" in auditlog, (
            "AuditLog entity does not declare an `entityId` field"
        )
        assert "action" in auditlog, "AuditLog entity does not declare an `action` field"
        assert "CreateDateColumn" in auditlog or "@Column" in auditlog, (
            "AuditLog entity does not declare a timestamp column"
        )

    def test_l1_auditlog_has_orm_set_timestamp(self):
        """AuditLog uses an ORM-managed timestamp (CreateDateColumn) the caller never sets."""
        auditlog = _read(AUDITLOG_TS)
        assert "CreateDateColumn" in auditlog, (
            "AuditLog must use @CreateDateColumn so the ORM sets the timestamp "
            "automatically (the caller must not have to set it)"
        )

    def test_l1_subscriber_is_real_event_subscriber(self):
        """audit-subscriber.ts implements EntitySubscriberInterface and hooks insert+update."""
        src = _read(SUBSCRIBER_TS)
        assert "@EventSubscriber" in src, (
            "audit-subscriber.ts must decorate the class with @EventSubscriber()"
        )
        assert "EntitySubscriberInterface" in src, (
            "audit-subscriber.ts must implement EntitySubscriberInterface"
        )
        assert "listenTo" in src, (
            "audit-subscriber.ts must declare listenTo() targeting the Account entity"
        )
        # It must react to BOTH insert and update lifecycle events.
        assert "afterInsert" in src or "beforeInsert" in src, (
            "subscriber must hook an insert lifecycle event to record `created`"
        )
        assert "afterUpdate" in src or "beforeUpdate" in src, (
            "subscriber must hook an update lifecycle event to record `updated`"
        )

    def test_l1_service_exports_required_operations(self):
        """audit-service.ts exports createAccount / changeStatus / historyOf."""
        src = _read(SERVICE_TS)
        for op in ("createAccount", "changeStatus", "historyOf"):
            assert op in src, f"audit-service.ts does not define `{op}`"

    def test_l1_test_uses_sqlite_only_testing_connections(self):
        """The functional test restricts testing connections to the SQLite driver family."""
        src = _read(TEST_TS)
        assert "createTestingConnections" in src, (
            "audit-trail.test.ts must use createTestingConnections from "
            "../../utils/test-utils"
        )
        assert "enabledDrivers" in src, (
            "audit-trail.test.ts must restrict to SQLite-based driver(s) via "
            "enabledDrivers"
        )
        assert "sqlite" in src or "sqljs" in src, (
            "enabledDrivers must name a sqlite-family driver (better-sqlite3/sqlite/sqljs)"
        )

    # ---- L2 : build & agent's own test ----------------------------------

    def test_l2_repo_compiles(self):
        """`pnpm run compile` succeeds with the deliverables in place (tsc, strict)."""
        _require_compiled()
        assert os.path.isfile(COMPILED_TEST_JS), (
            "expected compiled functional test at "
            + COMPILED_TEST_JS
            + " (compile succeeded but the test file was not emitted)"
        )
        for fname in (
            "entity/Account.js",
            "entity/AuditLog.js",
            "audit-subscriber.js",
            "audit-service.js",
        ):
            p = os.path.join(COMPILED_FEATURE_DIR, fname)
            assert os.path.isfile(p), f"expected compiled deliverable {p}"

    def test_l2_agent_functional_test_passes(self):
        """The agent's own audit-trail.test.ts passes under mocha (no failures/leaks)."""
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

    # ---- L2 : independent driver probes against the compiled code -------

    def test_l2_create_writes_single_created_audit_row(self):
        """createAccount triggers exactly one `created` AuditLog row with the correct entityId."""
        _require_compiled()
        js = _write_probe(
            "probe_create",
            _driver(
                """
                (async () => {
                    const ds = await newDataSource(true);
                    const svc = makeService(ds);
                    const acc = await svc.createAccount("alice");
                    // Read the audit rows STRAIGHT FROM THE DB, not via the service.
                    const audit = await rawAuditRows(ds);
                    out({
                        accId: acc.id,
                        accName: acc.name,
                        accStatus: acc.status,
                        table: audit.table,
                        rowCount: audit.rows.length,
                        actions: audit.rows.map((r) => r.action),
                        entityIds: audit.rows.map((r) => Number(r.entityId)),
                    });
                    await ds.destroy();
                })().catch((e) => { console.error(e); process.exit(1); });
                """
            ),
        )
        res = _parse_result(_run_node(js))
        assert isinstance(res["accId"], int) and res["accId"] > 0, res
        assert res["accName"] == "alice", res
        assert res["accStatus"] == "active", (
            "createAccount must persist new accounts with status 'active': "
            + json.dumps(res)
        )
        assert res["table"], "no AuditLog table was created: " + json.dumps(res)
        assert res["rowCount"] == 1, (
            "createAccount must write EXACTLY ONE audit row: " + json.dumps(res)
        )
        assert res["actions"] == ["created"], res
        assert res["entityIds"] == [res["accId"]], (
            "audit row entityId must reference the new account id: " + json.dumps(res)
        )

    def test_l2_update_writes_single_updated_audit_row(self):
        """changeStatus triggers exactly one `updated` AuditLog row and mutates the status."""
        _require_compiled()
        js = _write_probe(
            "probe_update",
            _driver(
                """
                (async () => {
                    const ds = await newDataSource(true);
                    const svc = makeService(ds);
                    const acc = await svc.createAccount("bob");
                    await svc.changeStatus(acc.id, "suspended");
                    const audit = await rawAuditRows(ds);
                    // Verify the account status really changed in the DB.
                    const accRow = await ds.getRepository(Account).findOneBy({ id: acc.id });
                    out({
                        accId: acc.id,
                        statusNow: accRow ? accRow.status : null,
                        rowCount: audit.rows.length,
                        actions: audit.rows.map((r) => r.action),
                        entityIds: audit.rows.map((r) => Number(r.entityId)),
                    });
                    await ds.destroy();
                })().catch((e) => { console.error(e); process.exit(1); });
                """
            ),
        )
        res = _parse_result(_run_node(js))
        assert res["statusNow"] == "suspended", (
            "changeStatus must actually update the account status: " + json.dumps(res)
        )
        # one created + one updated, in that order
        assert res["rowCount"] == 2, (
            "expected exactly two audit rows after create+update: " + json.dumps(res)
        )
        assert res["actions"] == ["created", "updated"], (
            "audit actions must be ['created','updated'] in order: " + json.dumps(res)
        )
        assert res["entityIds"] == [res["accId"], res["accId"]], (
            "both audit rows must reference the same account id: " + json.dumps(res)
        )

    def test_l2_history_ordered_created_then_updated(self):
        """historyOf returns that account's rows ordered by id asc: created then updated."""
        _require_compiled()
        js = _write_probe(
            "probe_history",
            _driver(
                """
                (async () => {
                    const ds = await newDataSource(true);
                    const svc = makeService(ds);
                    const acc = await svc.createAccount("carol");
                    await svc.changeStatus(acc.id, "frozen");
                    const history = await svc.historyOf(acc.id);
                    out({
                        len: history.length,
                        actions: history.map((r) => r.action),
                        entityIds: history.map((r) => Number(r.entityId)),
                        idsAscending: history.every((r, i, a) =>
                            i === 0 || Number(a[i - 1].id) <= Number(r.id)),
                    });
                    await ds.destroy();
                })().catch((e) => { console.error(e); process.exit(1); });
                """
            ),
        )
        res = _parse_result(_run_node(js))
        assert res["len"] == 2, (
            "historyOf must return both audit rows: " + json.dumps(res)
        )
        assert res["actions"] == ["created", "updated"], (
            "historyOf must order rows by id asc (created then updated): "
            + json.dumps(res)
        )
        assert res["idsAscending"] is True, (
            "historyOf rows are not ordered by id ascending: " + json.dumps(res)
        )

    def test_l2_two_accounts_no_cross_contamination(self):
        """Two accounts each get their own single `created` row referencing the right id."""
        _require_compiled()
        js = _write_probe(
            "probe_two",
            _driver(
                """
                (async () => {
                    const ds = await newDataSource(true);
                    const svc = makeService(ds);
                    const a = await svc.createAccount("first");
                    const b = await svc.createAccount("second");
                    const histA = await svc.historyOf(a.id);
                    const histB = await svc.historyOf(b.id);
                    const audit = await rawAuditRows(ds);
                    out({
                        aId: a.id,
                        bId: b.id,
                        histALen: histA.length,
                        histAActions: histA.map((r) => r.action),
                        histAEntity: histA.map((r) => Number(r.entityId)),
                        histBLen: histB.length,
                        histBActions: histB.map((r) => r.action),
                        histBEntity: histB.map((r) => Number(r.entityId)),
                        totalRows: audit.rows.length,
                    });
                    await ds.destroy();
                })().catch((e) => { console.error(e); process.exit(1); });
                """
            ),
        )
        res = _parse_result(_run_node(js))
        assert res["aId"] != res["bId"], res
        assert res["histALen"] == 1 and res["histAActions"] == ["created"], res
        assert res["histBLen"] == 1 and res["histBActions"] == ["created"], res
        assert res["histAEntity"] == [res["aId"]], (
            "account A's history must reference only A's id: " + json.dumps(res)
        )
        assert res["histBEntity"] == [res["bId"]], (
            "account B's history must reference only B's id: " + json.dumps(res)
        )
        assert res["totalRows"] == 2, (
            "exactly two `created` audit rows must exist total (no extras): "
            + json.dumps(res)
        )

    def test_l2_audit_row_present_immediately_after_save(self):
        """The audit row exists right after createAccount returns (same persistence op)."""
        _require_compiled()
        js = _write_probe(
            "probe_immediate",
            _driver(
                """
                (async () => {
                    const ds = await newDataSource(true);
                    const svc = makeService(ds);
                    const acc = await svc.createAccount("dora");
                    // Immediately, with NO further flush/save by the caller, the audit
                    // row must already be in the DB.
                    const audit = await rawAuditRows(ds);
                    const created = audit.rows.filter((r) => r.action === "created"
                        && Number(r.entityId) === acc.id);
                    // Also confirm the ORM populated the timestamp column.
                    const cnames = Object.keys((audit.rows[0] || { raw: {} }).raw);
                    const tsCol = cnames.find((c) =>
                        /(created|create|timestamp|date|at)/i.test(c)
                        && !/action|entity|^id$/i.test(c));
                    const tsVal = (audit.rows[0] && tsCol) ? audit.rows[0].raw[tsCol] : null;
                    out({
                        immediateCount: created.length,
                        tsCol: tsCol || null,
                        tsSet: tsVal !== null && tsVal !== undefined && tsVal !== "",
                    });
                    await ds.destroy();
                })().catch((e) => { console.error(e); process.exit(1); });
                """
            ),
        )
        res = _parse_result(_run_node(js))
        assert res["immediateCount"] == 1, (
            "the `created` audit row must be present immediately after save: "
            + json.dumps(res)
        )
        assert res["tsCol"], (
            "AuditLog must have an ORM-set timestamp column: " + json.dumps(res)
        )
        assert res["tsSet"] is True, (
            "the ORM-managed timestamp must be populated automatically: "
            + json.dumps(res)
        )

    def test_l2_no_subscriber_means_empty_history(self):
        """DISCRIMINATOR: without the subscriber registered, no audit rows are written.

        This is THE test that fails a naive implementation which inserts AuditLog rows
        manually inside the service methods. The audit MUST be driven by the persistence
        event subscriber; with the subscriber absent the history must be empty.
        """
        _require_compiled()
        js = _write_probe(
            "probe_no_subscriber",
            _driver(
                """
                (async () => {
                    // DataSource built WITHOUT the audit subscriber.
                    const ds = await newDataSource(false);
                    const svc = makeService(ds);
                    const acc = await svc.createAccount("erin");
                    await svc.changeStatus(acc.id, "closed");
                    const audit = await rawAuditRows(ds);
                    const history = await svc.historyOf(acc.id);
                    out({
                        accStatus: acc.status,
                        rawRowCount: audit.rows.length,
                        historyLen: history ? history.length : -1,
                    });
                    await ds.destroy();
                })().catch((e) => { console.error(e); process.exit(1); });
                """
            ),
        )
        res = _parse_result(_run_node(js))
        # The service operations themselves must still work (account created/updated).
        assert res["accStatus"] == "active", res
        # ...but with no subscriber, NO audit rows may exist. A service that inserts
        # audit rows manually would produce rows here and fail.
        assert res["rawRowCount"] == 0, (
            "audit rows were written WITHOUT the subscriber registered, so the service "
            "is inserting them manually instead of via persistence events: "
            + json.dumps(res)
        )
        assert res["historyLen"] == 0, (
            "historyOf must be empty when the subscriber is not registered: "
            + json.dumps(res)
        )
