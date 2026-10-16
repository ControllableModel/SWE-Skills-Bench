"""
Tests for the `typeorm-patterns` skill task (variant ext5):
"Build an Account Transfer Layer with Atomic Guarantees".

The agent must add, under `test/functional/account-transfer/`, a self-contained
TypeORM functional feature:
  - entity/Account.ts        (id auto-generated, owner:string, balance:int minor units)
  - entity/LedgerEntry.ts    (id auto-generated, references its Account, signed delta:int, memo:string)
  - transfer-service.ts      (openAccount / transfer / balanceOf / ledgerFor) built on a DataSource
  - account-transfer.test.ts (functional test wiring the above through createTestingConnections)

The defining requirement of THIS variant is ATOMICITY: a `transfer(fromId, toId, amount)`
must debit the source, credit the destination, and write one ledger entry per side as a
single all-or-nothing unit of work. If the source would go negative the whole operation
must roll back -- no partial debit, no orphan ledger entry -- and signal failure to the
caller (rejected promise / thrown error).

This pytest verifies the deliverables two ways:
  1. L1 -- the four files exist and are minimally well-formed (entities decorated with a
     DB-generated PK, the service exports the four named operations, the functional test
     restricts itself to the sqlite driver family).
  2. L2 -- DYNAMIC EXECUTION against the real TypeORM toolchain: it pins an ormconfig.json
     restricted to the better-sqlite3 driver, compiles the repo (`pnpm run compile`), runs
     the agent's own compiled functional test under mocha, and then runs INDEPENDENT driver
     scripts (written by THIS test, not the agent) against the agent's compiled
     Account/LedgerEntry/TransferService to deep-validate real behavior:
        * openAccount persists with a generated id and the requested balance
        * a successful transfer moves exactly `amount`, conserving total money, and writes
          exactly two ledger entries (one signed per side)
        * ledgerFor() returns entries ordered by id asc, and the sum of an account's deltas
          equals its balance change from the initial balance
        * an OVERDRAW transfer rejects AND leaves both balances and the ledger table fully
          unchanged (verified by direct SQL row counts, bypassing the service) -- this is the
          discriminating case a non-atomic debit/credit/insert sequence cannot pass
        * balanceOf reads the live persisted balance

A naive solution that performs the two balance updates and two ledger inserts as
independent, non-atomic statements (leaving a partial effect after an overdraw) must fail
at least one assertion.
"""

import json
import os
import subprocess
import textwrap

import pytest

REPO_DIR = "/workspace/typeorm"
FEATURE_DIR = os.path.join(REPO_DIR, "test/functional/account-transfer")
ENTITY_DIR = os.path.join(FEATURE_DIR, "entity")
ACCOUNT_TS = os.path.join(ENTITY_DIR, "Account.ts")
LEDGER_TS = os.path.join(ENTITY_DIR, "LedgerEntry.ts")
SERVICE_TS = os.path.join(FEATURE_DIR, "transfer-service.ts")
TEST_TS = os.path.join(FEATURE_DIR, "account-transfer.test.ts")

COMPILED_TEST_JS = os.path.join(
    REPO_DIR,
    "build/compiled/test/functional/account-transfer/account-transfer.test.js",
)
COMPILED_FEATURE_DIR = os.path.join(
    REPO_DIR, "build/compiled/test/functional/account-transfer"
)

# Build/compile is heavy in this repo.
COMPILE_TIMEOUT = 1200
RUN_TIMEOUT = 600

# Directory (under REPO_DIR, picked up by tsc include "test") where this pytest drops
# its own independent driver scripts so they get compiled alongside the agent's code.
PROBE_SRC_DIR = os.path.join(REPO_DIR, "test/functional/account-transfer/__probe__")
PROBE_OUT_DIR = os.path.join(
    REPO_DIR, "build/compiled/test/functional/account-transfer/__probe__"
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

        # ensure_npm_dependencies may not know pnpm; try it but don't hard-fail.
        ensure_npm_dependencies(REPO_DIR)
    except Exception:
        pass
    if os.path.isdir(os.path.join(REPO_DIR, "node_modules", "better-sqlite3")):
        return
    installer = None
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
    # Prefer better-sqlite3 only for determinism; fall back to whatever sqlite-like exists.
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
    # Best-effort; individual L2 tests assert on compile success so failures are clear.
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
    emits next to the agent's already-compiled Account/LedgerEntry/TransferService so
    the relative `./` imports in the probe resolve to real compiled modules.
    """
    os.makedirs(PROBE_OUT_DIR, exist_ok=True)
    ts_path = os.path.join(PROBE_OUT_DIR, rel_name + ".ts")
    with open(ts_path, "w", encoding="utf-8") as f:
        f.write(ts_source)
    # Compile just this probe in place (CommonJS) so imports resolve to sibling .js.
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
    """Relative imports (from the probe's compiled location) to the agent modules."""
    # Probe sits at build/compiled/test/functional/account-transfer/__probe__/X.js
    # Agent compiled modules sit one dir up.
    return {
        "account": "../entity/Account",
        "ledger": "../entity/LedgerEntry",
        "service": "../transfer-service",
        "datasource": "../../../../../src",  # build/compiled/src
    }


_DRIVER_PREAMBLE = """
"use strict";
const {{ DataSource }} = require("{datasource}");
const AccountMod = require("{account}");
const LedgerMod = require("{ledger}");
const ServiceMod = require("{service}");

function pickClass(mod, names) {{
    for (const n of names) if (mod[n]) return mod[n];
    // fall back: first exported function that looks like a class
    for (const k of Object.keys(mod)) {{
        if (typeof mod[k] === "function") return mod[k];
    }}
    if (mod.default) return mod.default;
    throw new Error("could not locate export in module");
}}

const Account = pickClass(AccountMod, ["Account", "default"]);
const LedgerEntry = pickClass(LedgerMod, ["LedgerEntry", "Ledger", "default"]);
const ServiceExport = pickClass(
    ServiceMod,
    ["TransferService", "AccountTransferService", "Transfer", "default"]
);

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
        entities: [Account, LedgerEntry],
        synchronize: true,
        dropSchema: true,
    }});
    await ds.initialize();
    return ds;
}}

function out(obj) {{ process.stdout.write("RESULT_JSON:" + JSON.stringify(obj) + "\\n"); }}

// Locate the actual table name for an entity (handles custom @Entity("name")).
function tableName(ds, EntityClass) {{
    const md = ds.getMetadata(EntityClass);
    return md.tableName;
}}
"""


def _driver(body):
    paths = _import_paths()
    preamble = _DRIVER_PREAMBLE.format(
        datasource=paths["datasource"],
        account=paths["account"],
        ledger=paths["ledger"],
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
        """All four required deliverable files exist under account-transfer/."""
        for p in (ACCOUNT_TS, LEDGER_TS, SERVICE_TS, TEST_TS):
            assert os.path.isfile(p), f"missing required deliverable file: {p}"

    def test_l1_entities_are_typeorm_entities(self):
        """Account and LedgerEntry are decorated TypeORM entities with generated PKs."""
        account = _read(ACCOUNT_TS)
        ledger = _read(LEDGER_TS)
        for name, src in (("Account", account), ("LedgerEntry", ledger)):
            assert "@Entity" in src, f"{name} is not annotated with @Entity"
            assert (
                "@PrimaryGeneratedColumn" in src
            ), f"{name} lacks a database-generated primary key"
        # Account domain fields.
        assert "owner" in account, "Account entity does not declare an `owner` field"
        assert "balance" in account, "Account entity does not declare a `balance` field"
        # LedgerEntry domain fields.
        assert "delta" in ledger, "LedgerEntry entity does not declare a `delta` field"
        assert "memo" in ledger, "LedgerEntry entity does not declare a `memo` field"

    def test_l1_ledger_references_account(self):
        """LedgerEntry declares a relation/reference back to the Account it belongs to."""
        ledger = _read(LEDGER_TS)
        assert (
            "ManyToOne" in ledger or "JoinColumn" in ledger or "Account" in ledger
        ), "LedgerEntry does not reference the Account it belongs to"
        # It must mention the Account type to model the reference.
        assert "Account" in ledger, "LedgerEntry must reference the Account entity"

    def test_l1_service_exports_required_operations(self):
        """transfer-service.ts exports the four named transfer operations."""
        src = _read(SERVICE_TS)
        for op in ("openAccount", "transfer", "balanceOf", "ledgerFor"):
            assert op in src, f"transfer-service.ts does not define `{op}`"

    def test_l1_transfer_uses_atomic_unit_of_work(self):
        """The service performs the transfer inside an atomic unit of work (transaction/queryRunner)."""
        src = _read(SERVICE_TS)
        assert (
            ".transaction" in src
            or "queryRunner" in src
            or "QueryRunner" in src
            or "createQueryRunner" in src
        ), (
            "transfer-service.ts must perform the multi-step transfer inside a single "
            "atomic unit of work (manager.transaction(...) or a QueryRunner transaction); "
            "non-atomic independent writes are not acceptable"
        )

    def test_l1_test_uses_sqlite_only_testing_connections(self):
        """The functional test restricts testing connections to the SQLite driver family."""
        src = _read(TEST_TS)
        assert "createTestingConnections" in src, (
            "account-transfer.test.ts must use createTestingConnections from "
            "../../utils/test-utils"
        )
        assert "enabledDrivers" in src, (
            "account-transfer.test.ts must restrict to SQLite-based driver(s) via "
            "enabledDrivers"
        )
        assert (
            "sqlite" in src or "sqljs" in src
        ), "enabledDrivers must name a sqlite-family driver (better-sqlite3/sqlite/sqljs)"

    # ---- L2 : build & the agent's own functional test -------------------

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
            "entity/LedgerEntry.js",
            "transfer-service.js",
        ):
            p = os.path.join(COMPILED_FEATURE_DIR, fname)
            assert os.path.isfile(p), f"expected compiled deliverable {p}"

    def test_l2_agent_functional_test_passes(self):
        """The agent's own account-transfer.test.ts passes under mocha (no failures/leaks)."""
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

    def test_l2_open_account_persists_with_generated_id(self):
        """openAccount persists a new account with a generated id and the requested balance."""
        _require_compiled()
        js = _write_probe(
            "probe_open",
            _driver(
                """
                (async () => {
                    const ds = await newDataSource();
                    const svc = makeService(ds);
                    const a = await svc.openAccount("alice", 1000);
                    // Re-read directly from the DB (bypassing the service).
                    const t = tableName(ds, Account);
                    const rows = await ds.query("SELECT * FROM " + t + " WHERE id = " + a.id);
                    out({
                        id: a.id,
                        returnedBalance: a.balance,
                        owner: a.owner,
                        dbRowCount: rows.length,
                        dbBalance: rows.length ? Number(rows[0].balance) : null,
                        dbOwner: rows.length ? rows[0].owner : null,
                    });
                    await ds.destroy();
                })().catch((e) => { console.error(e); process.exit(1); });
                """
            ),
        )
        res = _parse_result(_run_node(js))
        assert isinstance(res["id"], int) and res["id"] > 0, res
        assert res["returnedBalance"] == 1000, res
        assert res["owner"] == "alice", res
        assert res["dbRowCount"] == 1, res
        assert res["dbBalance"] == 1000, res
        assert res["dbOwner"] == "alice", res

    def test_l2_balance_of_reads_live_persisted_balance(self):
        """balanceOf(id) returns the live persisted balance, not a cached/constant value."""
        _require_compiled()
        js = _write_probe(
            "probe_balance",
            _driver(
                """
                (async () => {
                    const ds = await newDataSource();
                    const svc = makeService(ds);
                    const a = await svc.openAccount("acc", 250);
                    const b = await svc.openAccount("acc2", 999);
                    const ba = await svc.balanceOf(a.id);
                    const bb = await svc.balanceOf(b.id);
                    out({ ba: ba, bb: bb });
                    await ds.destroy();
                })().catch((e) => { console.error(e); process.exit(1); });
                """
            ),
        )
        res = _parse_result(_run_node(js))
        # Distinct, correct values prove balanceOf is not a hardcoded constant.
        assert res["ba"] == 250, res
        assert res["bb"] == 999, res

    def test_l2_successful_transfer_moves_money_and_writes_two_ledger_entries(self):
        """A successful transfer debits src, credits dst, conserves total, and writes exactly 2 ledger rows."""
        _require_compiled()
        js = _write_probe(
            "probe_transfer_ok",
            _driver(
                """
                (async () => {
                    const ds = await newDataSource();
                    const svc = makeService(ds);
                    const src = await svc.openAccount("src", 1000);
                    const dst = await svc.openAccount("dst", 200);
                    const ledgerTable = tableName(ds, LedgerEntry);
                    const before = await ds.query("SELECT COUNT(*) AS c FROM " + ledgerTable);
                    await svc.transfer(src.id, dst.id, 300);
                    const srcBal = await svc.balanceOf(src.id);
                    const dstBal = await svc.balanceOf(dst.id);
                    const after = await ds.query("SELECT COUNT(*) AS c FROM " + ledgerTable);
                    out({
                        srcBal: srcBal,
                        dstBal: dstBal,
                        total: srcBal + dstBal,
                        ledgerBefore: Number(before[0].c),
                        ledgerAfter: Number(after[0].c),
                    });
                    await ds.destroy();
                })().catch((e) => { console.error(e); process.exit(1); });
                """
            ),
        )
        res = _parse_result(_run_node(js))
        assert res["srcBal"] == 700, "source not debited by amount: " + json.dumps(res)
        assert res["dstBal"] == 500, "destination not credited by amount: " + json.dumps(res)
        # Money is conserved (1000 + 200 == 1200).
        assert res["total"] == 1200, "transfer did not conserve total money: " + json.dumps(res)
        # Exactly two new ledger entries (one per side).
        assert res["ledgerBefore"] == 0, res
        assert res["ledgerAfter"] == 2, (
            "a transfer must write exactly two ledger entries (one per account): "
            + json.dumps(res)
        )

    def test_l2_ledger_for_ordered_and_deltas_sum_to_balance_change(self):
        """ledgerFor returns entries id-asc; the sum of an account's signed deltas == its balance change."""
        _require_compiled()
        js = _write_probe(
            "probe_ledger",
            _driver(
                """
                (async () => {
                    const ds = await newDataSource();
                    const svc = makeService(ds);
                    const a = await svc.openAccount("A", 1000);
                    const b = await svc.openAccount("B", 1000);
                    // A sends out 100, then 250; A receives 40.
                    await svc.transfer(a.id, b.id, 100);
                    await svc.transfer(a.id, b.id, 250);
                    await svc.transfer(b.id, a.id, 40);
                    const entries = await svc.ledgerFor(a.id);
                    const ids = entries.map((e) => e.id);
                    const deltas = entries.map((e) => e.delta);
                    const sortedIds = ids.slice().sort((x, y) => x - y);
                    const sumDelta = deltas.reduce((s, d) => s + d, 0);
                    const bal = await svc.balanceOf(a.id);
                    out({
                        count: entries.length,
                        ids: ids,
                        ordered: JSON.stringify(ids) === JSON.stringify(sortedIds),
                        deltas: deltas,
                        sumDelta: sumDelta,
                        balanceChange: bal - 1000,
                    });
                    await ds.destroy();
                })().catch((e) => { console.error(e); process.exit(1); });
                """
            ),
        )
        res = _parse_result(_run_node(js))
        # A is involved in all three transfers -> 3 ledger entries for A.
        assert res["count"] == 3, "ledgerFor returned wrong number of entries: " + json.dumps(res)
        assert res["ordered"] is True, "ledgerFor entries are not ordered by id asc: " + json.dumps(res)
        # Signed deltas: -100, -250, +40 (order by id).
        assert res["deltas"] == [-100, -250, 40], (
            "ledger deltas are not the correct signed values in id order: " + json.dumps(res)
        )
        # Sum of deltas equals balance change from initial 1000.
        assert res["sumDelta"] == -310, res
        assert res["balanceChange"] == -310, res
        assert res["sumDelta"] == res["balanceChange"], (
            "sum of ledger deltas does not equal the account's balance change: "
            + json.dumps(res)
        )

    def test_l2_overdraw_transfer_rejects(self):
        """A transfer that would overdraw the source rejects / throws to the caller."""
        _require_compiled()
        js = _write_probe(
            "probe_overdraw_rejects",
            _driver(
                """
                (async () => {
                    const ds = await newDataSource();
                    const svc = makeService(ds);
                    const src = await svc.openAccount("src", 100);
                    const dst = await svc.openAccount("dst", 0);
                    let rejected = false;
                    try {
                        await svc.transfer(src.id, dst.id, 500);
                    } catch (e) {
                        rejected = true;
                    }
                    out({ rejected: rejected });
                    await ds.destroy();
                })().catch((e) => { console.error(e); process.exit(1); });
                """
            ),
        )
        res = _parse_result(_run_node(js))
        assert res["rejected"] is True, (
            "an overdrawing transfer must signal failure (rejected promise / thrown error)"
        )

    def test_l2_overdraw_rolls_back_completely_atomicity(self):
        """After an overdraw rejection, BOTH balances and the ledger table are fully unchanged (atomic rollback).

        This is the discriminating case: a non-atomic implementation that debits the source
        and/or inserts a ledger row before discovering the overdraw would leave a partial
        effect. We verify with direct SQL row counts and balances, bypassing the service.
        """
        _require_compiled()
        js = _write_probe(
            "probe_overdraw_rollback",
            _driver(
                """
                (async () => {
                    const ds = await newDataSource();
                    const svc = makeService(ds);
                    const src = await svc.openAccount("src", 100);
                    const dst = await svc.openAccount("dst", 50);
                    const acctTable = tableName(ds, Account);
                    const ledgerTable = tableName(ds, LedgerEntry);

                    // Do one legitimate transfer first so the ledger is non-empty baseline.
                    await svc.transfer(src.id, dst.id, 40); // src:60 dst:90, ledger=2

                    const ledgerBefore = Number(
                        (await ds.query("SELECT COUNT(*) AS c FROM " + ledgerTable))[0].c);
                    const srcBefore = Number(
                        (await ds.query("SELECT balance FROM " + acctTable + " WHERE id = " + src.id))[0].balance);
                    const dstBefore = Number(
                        (await ds.query("SELECT balance FROM " + acctTable + " WHERE id = " + dst.id))[0].balance);

                    let rejected = false;
                    try {
                        await svc.transfer(src.id, dst.id, 1000); // overdraw: src only has 60
                    } catch (e) {
                        rejected = true;
                    }

                    const ledgerAfter = Number(
                        (await ds.query("SELECT COUNT(*) AS c FROM " + ledgerTable))[0].c);
                    const srcAfter = Number(
                        (await ds.query("SELECT balance FROM " + acctTable + " WHERE id = " + src.id))[0].balance);
                    const dstAfter = Number(
                        (await ds.query("SELECT balance FROM " + acctTable + " WHERE id = " + dst.id))[0].balance);

                    out({
                        rejected: rejected,
                        ledgerBefore: ledgerBefore,
                        ledgerAfter: ledgerAfter,
                        srcBefore: srcBefore,
                        srcAfter: srcAfter,
                        dstBefore: dstBefore,
                        dstAfter: dstAfter,
                    });
                    await ds.destroy();
                })().catch((e) => { console.error(e); process.exit(1); });
                """
            ),
        )
        res = _parse_result(_run_node(js))
        # Baseline sanity from the legitimate first transfer.
        assert res["ledgerBefore"] == 2, res
        assert res["srcBefore"] == 60, res
        assert res["dstBefore"] == 90, res
        # The overdraw must have rejected...
        assert res["rejected"] is True, (
            "overdraw transfer must reject: " + json.dumps(res)
        )
        # ...and left EVERYTHING untouched (no partial debit, no orphan ledger entry).
        assert res["srcAfter"] == res["srcBefore"], (
            "source balance changed after a rejected overdraw (partial debit -> not atomic): "
            + json.dumps(res)
        )
        assert res["dstAfter"] == res["dstBefore"], (
            "destination balance changed after a rejected overdraw (partial credit -> not atomic): "
            + json.dumps(res)
        )
        assert res["ledgerAfter"] == res["ledgerBefore"], (
            "ledger gained rows from a rejected overdraw (orphan entry -> not atomic): "
            + json.dumps(res)
        )

    def test_l2_total_money_conserved_across_many_transfers(self):
        """Across a sequence of valid + rejected transfers, total money is exactly conserved."""
        _require_compiled()
        js = _write_probe(
            "probe_conservation",
            _driver(
                """
                (async () => {
                    const ds = await newDataSource();
                    const svc = makeService(ds);
                    const a = await svc.openAccount("a", 500);
                    const b = await svc.openAccount("b", 500);
                    const c = await svc.openAccount("c", 0);
                    const initialTotal = 1000;
                    const tries = [
                        [a.id, b.id, 100],
                        [b.id, c.id, 300],
                        [a.id, c.id, 5000], // overdraw -> must roll back
                        [c.id, a.id, 50],
                        [b.id, a.id, 9999], // overdraw -> must roll back
                    ];
                    let rejections = 0;
                    for (const [f, t, amt] of tries) {
                        try { await svc.transfer(f, t, amt); }
                        catch (e) { rejections++; }
                    }
                    const ba = await svc.balanceOf(a.id);
                    const bb = await svc.balanceOf(b.id);
                    const bc = await svc.balanceOf(c.id);
                    out({
                        total: ba + bb + bc,
                        initialTotal: initialTotal,
                        rejections: rejections,
                        ba: ba, bb: bb, bc: bc,
                    });
                    await ds.destroy();
                })().catch((e) => { console.error(e); process.exit(1); });
                """
            ),
        )
        res = _parse_result(_run_node(js))
        # Two of the five transfers overdraw and must be rejected.
        assert res["rejections"] == 2, (
            "expected exactly two overdraw rejections: " + json.dumps(res)
        )
        # Money conserved: 1000 throughout. Valid moves: a->b 100, b->c 300, c->a 50.
        # a: 500 -100 +50 = 450 ; b: 500 +100 -300 = 300 ; c: 0 +300 -50 = 250.
        assert res["total"] == res["initialTotal"], (
            "total money not conserved across transfers: " + json.dumps(res)
        )
        assert res["ba"] == 450, res
        assert res["bb"] == 300, res
        assert res["bc"] == 250, res

    def test_l2_schema_synthesized_by_orm(self):
        """The Account/LedgerEntry tables are derived by the ORM (synchronize), not hand-written SQL."""
        _require_compiled()
        js = _write_probe(
            "probe_schema",
            _driver(
                """
                (async () => {
                    const ds = await newDataSource();
                    const acctTable = tableName(ds, Account);
                    const ledgerTable = tableName(ds, LedgerEntry);
                    const acctCols = (await ds.query("PRAGMA table_info(" + acctTable + ")")).map((r) => r.name);
                    const ledgerCols = (await ds.query("PRAGMA table_info(" + ledgerTable + ")")).map((r) => r.name);
                    out({ acctTable, ledgerTable, acctCols, ledgerCols });
                    await ds.destroy();
                })().catch((e) => { console.error(e); process.exit(1); });
                """
            ),
        )
        res = _parse_result(_run_node(js))
        # The ORM synthesized real tables with the declared columns.
        assert "owner" in res["acctCols"], res
        assert "balance" in res["acctCols"], res
        assert "delta" in res["ledgerCols"], res
        assert "memo" in res["ledgerCols"], res
