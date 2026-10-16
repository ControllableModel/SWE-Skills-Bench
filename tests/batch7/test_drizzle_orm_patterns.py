"""
Test for 'drizzle-orm-patterns' skill (variant ext7) — In-Memory Commission Ledger
with Running Balances (dub monorepo).

Verifies that the Agent built a self-contained, in-process commission ledger under
apps/web/lib/partners/commission-ledger/ backed by an embedded better-sqlite3 database
and queried through drizzle-orm. The ledger must expose a relation-aware schema and a
CommissionLedger API created via a factory (createCommissionLedger):
  addPartner / appendEntry / recordPayout / getBalance / getStatement / getBalances.

Data model (in the embedded DB):
  partners(id PK, name)        — one partner has many entries
  entries(id PK, partnerId FK, kind in {accrual|reversal|payout}, amount int>0, createdAt)
  accrual adds to balance; reversal and payout subtract.

Strategy
--------
L1 checks verify the deliverable files exist, are minimally well-formed, that
package.json declares drizzle-orm, and that index.ts surfaces the factory.

L2 checks DO NOT trust the agent's own test file. Instead we drop an independent
TypeScript probe spec into apps/web/tests/commissions/ (vitest's configured test
dir is ./tests) that imports the ledger from "@/lib/partners/commission-ledger",
seeds deterministic data, and runs the repo's native command:

    cd apps/web && pnpm vitest run tests/commissions/<probe>.test.ts

asserting on the ledger's *real* behavior: signed balance, the in-database ordered
running balance whose final value equals the standalone balance, the atomic
balance-checked payout (rejecting overdraw and inserting nothing), zero-balance
partners surfaced by getBalances(), non-positive-amount and invalid-partner
rejection, ledger isolation between instances, and unknown-id zero/empty results.

A naive/stub implementation cannot pass: e.g. one that iterates rows in JS instead
of computing the running balance in the DB will still be checked against the exact
[100,150,120,100] sequence and final==getBalance invariant; one that skips the atomic
balance check will let an overdraw payout through; one that hardcodes outputs will
fail the isolation and novel-seed probes. The agent's own suite is also run
separately for the acceptance command.
"""

import json
import os
import subprocess

import pytest


class TestDrizzleOrmPatterns:
    """Verify the in-memory commission ledger built with drizzle-orm + better-sqlite3."""

    REPO_DIR = "/workspace/dub"
    WEB_DIR = os.path.join(REPO_DIR, "apps", "web")
    LEDGER_DIR = os.path.join(WEB_DIR, "lib", "partners", "commission-ledger")
    AGENT_TEST = os.path.join(WEB_DIR, "tests", "commissions", "commission-ledger.test.ts")
    PROBE_NAME = "zz_ledger_probe.test.ts"
    PROBE_PATH = os.path.join(WEB_DIR, "tests", "commissions", PROBE_NAME)

    _deps_ready = False

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    @classmethod
    def _ensure_deps(cls):
        """Install the pnpm workspace dependencies once (idempotent)."""
        if cls._deps_ready:
            return
        if os.path.isdir(os.path.join(cls.WEB_DIR, "node_modules", "drizzle-orm")) and \
           os.path.isdir(os.path.join(cls.WEB_DIR, "node_modules", "better-sqlite3")):
            cls._deps_ready = True
            return
        result = subprocess.run(
            ["pnpm", "install", "--frozen-lockfile=false"],
            cwd=cls.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=1800,
        )
        if result.returncode != 0:
            raise RuntimeError(
                "pnpm install failed:\n"
                f"stdout={result.stdout[-3000:]}\nstderr={result.stderr[-3000:]}"
            )
        cls._deps_ready = True

    def _write_probe(self, body: str):
        """Write an independent vitest probe spec into the configured tests dir."""
        os.makedirs(os.path.dirname(self.PROBE_PATH), exist_ok=True)
        with open(self.PROBE_PATH, "w") as f:
            f.write(body)

    def _run_probe(self, timeout=420):
        """Run the probe via the repo's native vitest command and return CompletedProcess."""
        return subprocess.run(
            ["pnpm", "vitest", "run", f"tests/commissions/{self.PROBE_NAME}"],
            cwd=self.WEB_DIR,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    def _drive(self, assertions_ts: str, timeout=420):
        """
        Build a probe that imports the ledger, exposes a deterministic `seedP1` helper,
        runs the provided TS assertion body inside a single `it(...)`, execute it
        natively, and return the CompletedProcess. Assertions use vitest `expect`.

        seedP1 reproduces the doc's canonical scenario for partner "p1":
          accrual 100 (t=1), accrual 50 (t=2), reversal 30 (t=3), payout 20 (t=4)
        which must yield running balances [100, 150, 120, 100] and getBalance == 100.
        """
        probe = (
            'import { describe, it, expect } from "vitest";\n'
            'import {\n'
            '  createCommissionLedger,\n'
            '} from "@/lib/partners/commission-ledger";\n'
            '\n'
            'function seedP1() {\n'
            '  const l = createCommissionLedger();\n'
            '  l.addPartner({ id: "p1", name: "Alpha" });\n'
            '  l.addPartner({ id: "p2", name: "Beta" });\n'
            '  l.appendEntry({ id: "e1", partnerId: "p1", kind: "accrual",  amount: 100, createdAt: 1 });\n'
            '  l.appendEntry({ id: "e2", partnerId: "p1", kind: "accrual",  amount: 50,  createdAt: 2 });\n'
            '  l.appendEntry({ id: "e3", partnerId: "p1", kind: "reversal", amount: 30,  createdAt: 3 });\n'
            '  l.appendEntry({ id: "e4", partnerId: "p1", kind: "payout",   amount: 20,  createdAt: 4 });\n'
            '  return l;\n'
            '}\n'
            '\n'
            'describe("commission-ledger probe", () => {\n'
            '  it("behaves as specified", () => {\n'
            + assertions_ts
            + '\n  });\n'
            '});\n'
        )
        self._write_probe(probe)
        return self._run_probe(timeout=timeout)

    def _assert_passed(self, result, ctx=""):
        ok = result.returncode == 0
        assert ok, (
            f"vitest probe failed{(' (' + ctx + ')') if ctx else ''}:\n"
            f"--- stdout ---\n{result.stdout[-4000:]}\n"
            f"--- stderr ---\n{result.stderr[-2000:]}"
        )

    def teardown_method(self, method):
        try:
            if os.path.isfile(self.PROBE_PATH):
                os.remove(self.PROBE_PATH)
        except OSError:
            pass

    # ------------------------------------------------------------------
    # L1 — deliverables exist & are minimally well-formed
    # ------------------------------------------------------------------

    def test_l1_ledger_dir_and_files_exist(self):
        """schema.ts, store.ts and index.ts must exist under lib/partners/commission-ledger/."""
        for fname in ("schema.ts", "store.ts", "index.ts"):
            fpath = os.path.join(self.LEDGER_DIR, fname)
            assert os.path.isfile(fpath), f"missing deliverable: {fpath}"
            assert os.path.getsize(fpath) > 0, f"empty deliverable: {fpath}"

    def test_l1_package_declares_drizzle_orm(self):
        """apps/web/package.json must declare drizzle-orm as a (dev/peer)dependency."""
        with open(os.path.join(self.WEB_DIR, "package.json")) as f:
            pkg = json.load(f)
        deps = {}
        for sect in ("dependencies", "devDependencies", "peerDependencies"):
            deps.update(pkg.get(sect) or {})
        assert "drizzle-orm" in deps, "drizzle-orm not declared in apps/web/package.json"

    def test_l1_agent_test_file_present(self):
        """The agent's vitest suite for the commission ledger must exist and be non-empty."""
        assert os.path.isfile(self.AGENT_TEST), (
            "expected tests/commissions/commission-ledger.test.ts"
        )
        assert os.path.getsize(self.AGENT_TEST) > 0, "commission-ledger.test.ts is empty"

    def test_l1_index_reexports_factory(self):
        """index.ts must re-export the factory so the module is importable from the package root."""
        with open(os.path.join(self.LEDGER_DIR, "index.ts")) as f:
            content = f.read()
        assert "createCommissionLedger" in content, (
            "index.ts must surface createCommissionLedger"
        )

    def test_l1_schema_models_both_entities_and_kinds(self):
        """schema.ts must mention both tables and all three entry kinds at the type level."""
        with open(os.path.join(self.LEDGER_DIR, "schema.ts")) as f:
            content = f.read()
        # Both entities present.
        assert "partner" in content.lower(), "schema.ts must define the partners table"
        assert "entr" in content.lower(), "schema.ts must define the entries table"
        # The three constrained kinds must appear in the schema/types.
        for kind in ("accrual", "reversal", "payout"):
            assert kind in content, f"schema.ts must constrain kind value '{kind}'"

    # ------------------------------------------------------------------
    # L2 — dynamic behavior via independent native probe
    # ------------------------------------------------------------------

    def test_l2_module_importable_and_factory_returns_ledger(self):
        """The module must build & import from @/lib/partners/commission-ledger and expose the API."""
        self._ensure_deps()
        result = self._drive(
            '    const l = createCommissionLedger();\n'
            '    expect(typeof l.addPartner).toBe("function");\n'
            '    expect(typeof l.appendEntry).toBe("function");\n'
            '    expect(typeof l.recordPayout).toBe("function");\n'
            '    expect(typeof l.getBalance).toBe("function");\n'
            '    expect(typeof l.getStatement).toBe("function");\n'
            '    expect(typeof l.getBalances).toBe("function");\n'
        )
        self._assert_passed(result, "import/factory")

    def test_l2_signed_balance_in_database(self):
        """getBalance(p1) == 100 (accruals 150 minus reversal 30 minus payout 20); empty partner -> 0."""
        self._ensure_deps()
        result = self._drive(
            '    const l = seedP1();\n'
            '    expect(Number(l.getBalance("p1"))).toBe(100);\n'
            '    // p2 has no entries -> balance 0, never throws\n'
            '    expect(Number(l.getBalance("p2"))).toBe(0);\n'
        )
        self._assert_passed(result, "signed-balance")

    def test_l2_running_balance_sequence_and_order(self):
        """getStatement(p1) ordered by createdAt asc -> running balances [100,150,120,100]."""
        self._ensure_deps()
        result = self._drive(
            '    const l = seedP1();\n'
            '    const stmt: any[] = l.getStatement("p1");\n'
            '    expect(stmt.length).toBe(4);\n'
            '    // entries ordered by ascending createdAt\n'
            '    const order = stmt.map((r:any)=>Number(r.createdAt));\n'
            '    expect(order).toEqual([1, 2, 3, 4]);\n'
            '    const ids = stmt.map((r:any)=>r.id);\n'
            '    expect(ids).toEqual(["e1", "e2", "e3", "e4"]);\n'
            '    // running balance annotated on each row (accept runningBalance|balance|running)\n'
            '    const running = stmt.map((r:any)=>Number(\n'
            '      r.runningBalance ?? r.running ?? r.balance ?? r.cumulative\n'
            '    ));\n'
            '    expect(running).toEqual([100, 150, 120, 100]);\n'
        )
        self._assert_passed(result, "running-balance-sequence")

    def test_l2_running_balance_final_equals_getbalance(self):
        """Invariant: the last statement row's running balance equals getBalance(partner)."""
        self._ensure_deps()
        result = self._drive(
            '    const l = createCommissionLedger();\n'
            '    l.addPartner({ id: "px", name: "X" });\n'
            '    // a different, novel sequence to defeat hardcoding\n'
            '    l.appendEntry({ id: "a", partnerId: "px", kind: "accrual",  amount: 250, createdAt: 5 });\n'
            '    l.appendEntry({ id: "b", partnerId: "px", kind: "payout",   amount: 40,  createdAt: 6 });\n'
            '    l.appendEntry({ id: "c", partnerId: "px", kind: "reversal", amount: 10,  createdAt: 7 });\n'
            '    l.appendEntry({ id: "d", partnerId: "px", kind: "accrual",  amount: 5,   createdAt: 8 });\n'
            '    const stmt: any[] = l.getStatement("px");\n'
            '    const running = stmt.map((r:any)=>Number(\n'
            '      r.runningBalance ?? r.running ?? r.balance ?? r.cumulative\n'
            '    ));\n'
            '    expect(running).toEqual([250, 210, 200, 205]);\n'
            '    const last = running[running.length - 1];\n'
            '    expect(last).toBe(Number(l.getBalance("px")));\n'
            '    expect(last).toBe(205);\n'
        )
        self._assert_passed(result, "final-equals-balance")

    def test_l2_get_balances_includes_zero_balance_partners(self):
        """getBalances() returns id/name/balance for every partner, including zero-entry ones."""
        self._ensure_deps()
        result = self._drive(
            '    const l = seedP1();\n'
            '    const rows: any[] = l.getBalances();\n'
            '    const m: Record<string, {name:string, balance:number}> = {};\n'
            '    for (const r of rows) m[r.id] = { name: r.name, balance: Number(r.balance) };\n'
            '    expect(Object.keys(m).sort()).toEqual(["p1", "p2"]);\n'
            '    expect(m["p1"]).toEqual({ name: "Alpha", balance: 100 });\n'
            '    // p2 has no entries but must still appear with balance 0\n'
            '    expect(m["p2"]).toEqual({ name: "Beta", balance: 0 });\n'
        )
        self._assert_passed(result, "get-balances-zero")

    def test_l2_record_payout_rejects_overdraw_atomically(self):
        """recordPayout(p1,1000) against balance 100 throws, inserts nothing, balance stays 100."""
        self._ensure_deps()
        result = self._drive(
            '    const l = seedP1();\n'
            '    const before: any[] = l.getStatement("p1");\n'
            '    expect(before.length).toBe(4);\n'
            '    let threw = false;\n'
            '    try { l.recordPayout("p1", 1000); } catch (e) { threw = true; }\n'
            '    expect(threw).toBe(true);\n'
            '    // no entry inserted, balance unchanged\n'
            '    const after: any[] = l.getStatement("p1");\n'
            '    expect(after.length).toBe(4);\n'
            '    expect(Number(l.getBalance("p1"))).toBe(100);\n'
        )
        self._assert_passed(result, "payout-overdraw-rejected")

    def test_l2_record_payout_succeeds_within_balance(self):
        """recordPayout(p1,40) succeeds, appends a payout entry, reduces balance 100 -> 60."""
        self._ensure_deps()
        result = self._drive(
            '    const l = seedP1();\n'
            '    const res: any = l.recordPayout("p1", 40);\n'
            '    expect(res).toBeDefined();\n'
            '    expect(res.kind).toBe("payout");\n'
            '    expect(Number(res.amount)).toBe(40);\n'
            '    expect(Number(l.getBalance("p1"))).toBe(60);\n'
            '    // statement now has 5 rows and last running balance equals 60\n'
            '    const stmt: any[] = l.getStatement("p1");\n'
            '    expect(stmt.length).toBe(5);\n'
            '    const running = stmt.map((r:any)=>Number(\n'
            '      r.runningBalance ?? r.running ?? r.balance ?? r.cumulative\n'
            '    ));\n'
            '    expect(running[running.length - 1]).toBe(60);\n'
        )
        self._assert_passed(result, "payout-success")

    def test_l2_payout_exact_balance_boundary(self):
        """recordPayout at exactly the current balance succeeds and zeroes the balance."""
        self._ensure_deps()
        result = self._drive(
            '    const l = createCommissionLedger();\n'
            '    l.addPartner({ id: "pe", name: "Edge" });\n'
            '    l.appendEntry({ id: "x", partnerId: "pe", kind: "accrual", amount: 70, createdAt: 1 });\n'
            '    // exactly equal -> allowed\n'
            '    const ok: any = l.recordPayout("pe", 70);\n'
            '    expect(ok).toBeDefined();\n'
            '    expect(Number(l.getBalance("pe"))).toBe(0);\n'
            '    // now any positive payout overdraws and must be rejected\n'
            '    let threw = false;\n'
            '    try { l.recordPayout("pe", 1); } catch (e) { threw = true; }\n'
            '    expect(threw).toBe(true);\n'
            '    expect(Number(l.getBalance("pe"))).toBe(0);\n'
        )
        self._assert_passed(result, "payout-exact-boundary")

    def test_l2_append_entry_rejects_nonpositive_amount(self):
        """appendEntry with amount<=0 throws and inserts nothing."""
        self._ensure_deps()
        result = self._drive(
            '    const l = createCommissionLedger();\n'
            '    l.addPartner({ id: "p", name: "P" });\n'
            '    for (const bad of [0, -5]) {\n'
            '      let threw = false;\n'
            '      try {\n'
            '        l.appendEntry({ id: "z" + bad, partnerId: "p", kind: "accrual", amount: bad, createdAt: 1 });\n'
            '      } catch (e) { threw = true; }\n'
            '      expect(threw).toBe(true);\n'
            '    }\n'
            '    // nothing was inserted -> empty statement, zero balance\n'
            '    expect(l.getStatement("p")).toEqual([]);\n'
            '    expect(Number(l.getBalance("p"))).toBe(0);\n'
        )
        self._assert_passed(result, "nonpositive-amount-rejected")

    def test_l2_append_entry_rejects_unknown_partner(self):
        """appendEntry referencing a non-existent partner throws and inserts nothing."""
        self._ensure_deps()
        result = self._drive(
            '    const l = createCommissionLedger();\n'
            '    l.addPartner({ id: "real", name: "R" });\n'
            '    let threw = false;\n'
            '    try {\n'
            '      l.appendEntry({ id: "e", partnerId: "ghost", kind: "accrual", amount: 10, createdAt: 1 });\n'
            '    } catch (e) { threw = true; }\n'
            '    expect(threw).toBe(true);\n'
            '    // the real partner is unaffected and the ghost never appears\n'
            '    expect(Number(l.getBalance("real"))).toBe(0);\n'
            '    const ids = l.getBalances().map((r:any)=>r.id).sort();\n'
            '    expect(ids).toEqual(["real"]);\n'
        )
        self._assert_passed(result, "unknown-partner-rejected")

    def test_l2_unknown_partner_zero_and_empty_never_throws(self):
        """Unknown partner id -> balance 0 and empty statement, never throws."""
        self._ensure_deps()
        result = self._drive(
            '    const l = seedP1();\n'
            '    expect(Number(l.getBalance("does-not-exist"))).toBe(0);\n'
            '    expect(l.getStatement("does-not-exist")).toEqual([]);\n'
        )
        self._assert_passed(result, "unknown-partner-zero")

    def test_l2_ledger_isolation_between_instances(self):
        """Two factory-created ledgers are fully isolated: data in one is invisible to the other."""
        self._ensure_deps()
        result = self._drive(
            '    const a = createCommissionLedger();\n'
            '    const b = createCommissionLedger();\n'
            '    a.addPartner({ id: "p", name: "A" });\n'
            '    a.appendEntry({ id: "e", partnerId: "p", kind: "accrual", amount: 99, createdAt: 1 });\n'
            '    // b knows nothing of p\n'
            '    expect(Number(b.getBalance("p"))).toBe(0);\n'
            '    expect(b.getStatement("p")).toEqual([]);\n'
            '    expect(b.getBalances()).toEqual([]);\n'
            '    // a still intact\n'
            '    expect(Number(a.getBalance("p"))).toBe(99);\n'
            '    expect(a.getStatement("p").length).toBe(1);\n'
        )
        self._assert_passed(result, "isolation")

    def test_l2_agent_acceptance_suite_passes(self):
        """The acceptance command must pass: pnpm vitest run tests/commissions/commission-ledger.test.ts."""
        self._ensure_deps()
        assert os.path.isfile(self.AGENT_TEST), "agent commission-ledger.test.ts missing"
        result = subprocess.run(
            ["pnpm", "vitest", "run", "tests/commissions/commission-ledger.test.ts"],
            cwd=self.WEB_DIR,
            capture_output=True,
            text=True,
            timeout=600,
        )
        assert result.returncode == 0, (
            "agent's vitest suite failed:\n"
            f"--- stdout ---\n{result.stdout[-4000:]}\n"
            f"--- stderr ---\n{result.stderr[-2000:]}"
        )
        combined = (result.stdout + result.stderr).lower()
        assert "no test files found" not in combined, "vitest found no test files"
