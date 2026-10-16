"""
Test for 'drizzle-orm-patterns' skill (variant ext5) — In-Memory Partner Payout
Aggregation Store (dub monorepo).

Verifies that the Agent built a self-contained, in-process payout-aggregation store under
apps/web/lib/payouts/payout-store/ backed by an embedded better-sqlite3 (":memory:")
database and queried through drizzle-orm. The store must expose a relation-aware schema
and a PayoutStore API obtained via createPayoutStore():
    addPartner / addPayout / getPartnerTotals / getTotalsByStatus /
    getPartnersOwedAtLeast / getPartnerWithPayouts

Strategy
--------
L1 checks verify the deliverable files exist, are minimally well-formed, and that
apps/web/package.json declares drizzle-orm.

L2 checks DO NOT trust the agent's own test file. Instead we drop an independent
TypeScript probe spec into apps/web/tests/payouts/ (vitest's configured test dir),
import the store from "@/lib/payouts/payout-store", seed deterministic data, and run
the repo's native command:

    cd apps/web && pnpm vitest run tests/payouts/<probe>.test.ts

asserting on the store's *real* behavior: in-database sum/count aggregation, zero-payout
partners reported with total/count 0, per-status breakdown omitting empty statuses, the
owed-at-least threshold filter (non-completed only, descending order, excluding
completed-only and below-threshold partners), single-round-trip nested partner+payouts
loading, negative-amount and invalid-partner rejection (insert nothing), unknown-id
empty/null results, and store isolation. A hardcoded or shallow solution (one that
hardcodes totals, sums in JS, forgets zero-payout partners, or includes completed
payouts in "owed") cannot pass because the probe drives the public API with novel data.
The agent's own suite is also run separately for the acceptance command.
"""

import json
import os
import subprocess

import pytest


class TestDrizzleOrmPatterns:
    """Verify the in-memory partner payout aggregation store built with drizzle-orm + better-sqlite3."""

    REPO_DIR = "/workspace/dub"
    WEB_DIR = os.path.join(REPO_DIR, "apps", "web")
    STORE_DIR = os.path.join(WEB_DIR, "lib", "payouts", "payout-store")
    PROBE_NAME = "zz_payoutstore_probe.test.ts"
    PROBE_PATH = os.path.join(WEB_DIR, "tests", "payouts", PROBE_NAME)
    AGENT_TEST = os.path.join(WEB_DIR, "tests", "payouts", "payout-store.test.ts")

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
        # Install at the monorepo root so the pnpm workspace is fully linked.
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
            ["pnpm", "vitest", "run", f"tests/payouts/{self.PROBE_NAME}"],
            cwd=self.WEB_DIR,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    def _drive(self, assertions_ts: str, timeout=420):
        """
        Build a probe that imports the store, seeds a deterministic dataset, runs the
        provided TS assertion body inside a single `it(...)`, execute it natively, and
        return (CompletedProcess). The assertions use vitest `expect`.

        Seed dataset (mirrors the doc's "Expected Functionality"):
          partners: p1 "Alice", p2 "Bob", p3 "Cleo" (p3 has NO payouts)
          p1 payouts: pending 100, processing 50, completed 1000
          p2 payouts: completed 30
        """
        probe = (
            'import { describe, it, expect } from "vitest";\n'
            'import {\n'
            '  createPayoutStore,\n'
            '} from "@/lib/payouts/payout-store";\n'
            '\n'
            'function seed() {\n'
            '  const s = createPayoutStore();\n'
            '  s.addPartner({ id: "p1", name: "Alice" });\n'
            '  s.addPartner({ id: "p2", name: "Bob" });\n'
            '  s.addPartner({ id: "p3", name: "Cleo" });\n'
            '  s.addPayout({ id: "y1", partnerId: "p1", amount: 100,  status: "pending",    periodStart: 1000 });\n'
            '  s.addPayout({ id: "y2", partnerId: "p1", amount: 50,   status: "processing", periodStart: 2000 });\n'
            '  s.addPayout({ id: "y3", partnerId: "p1", amount: 1000, status: "completed",  periodStart: 3000 });\n'
            '  s.addPayout({ id: "y4", partnerId: "p2", amount: 30,   status: "completed",  periodStart: 4000 });\n'
            '  return s;\n'
            '}\n'
            '\n'
            'describe("payoutstore probe", () => {\n'
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

    def test_l1_store_dir_and_files_exist(self):
        """schema.ts, store.ts and index.ts must exist under lib/payouts/payout-store/."""
        for fname in ("schema.ts", "store.ts", "index.ts"):
            fpath = os.path.join(self.STORE_DIR, fname)
            assert os.path.isfile(fpath), f"missing deliverable: {fpath}"
            assert os.path.getsize(fpath) > 0, f"empty deliverable: {fpath}"

    def test_l1_package_declares_drizzle_orm(self):
        """apps/web/package.json must declare drizzle-orm as a (dev)dependency."""
        with open(os.path.join(self.WEB_DIR, "package.json")) as f:
            pkg = json.load(f)
        deps = {}
        for sect in ("dependencies", "devDependencies", "peerDependencies"):
            deps.update(pkg.get(sect) or {})
        assert "drizzle-orm" in deps, "drizzle-orm not declared in apps/web/package.json"

    def test_l1_agent_test_file_present(self):
        """The agent's vitest suite for the payout-store must exist."""
        assert os.path.isfile(self.AGENT_TEST), "expected tests/payouts/payout-store.test.ts"
        assert os.path.getsize(self.AGENT_TEST) > 0, "payout-store.test.ts is empty"

    def test_l1_index_reexports_factory(self):
        """index.ts must re-export the factory so the module is importable from the package root."""
        with open(os.path.join(self.STORE_DIR, "index.ts")) as f:
            content = f.read()
        assert "createPayoutStore" in content, (
            "index.ts must surface createPayoutStore"
        )

    # ------------------------------------------------------------------
    # L2 — dynamic behavior via independent native probe
    # ------------------------------------------------------------------

    def test_l2_module_importable_and_factory_returns_store(self):
        """The module must build & import from @/lib/payouts/payout-store and expose the API."""
        self._ensure_deps()
        result = self._drive(
            '    const s = createPayoutStore();\n'
            '    expect(typeof s.addPartner).toBe("function");\n'
            '    expect(typeof s.addPayout).toBe("function");\n'
            '    expect(typeof s.getPartnerTotals).toBe("function");\n'
            '    expect(typeof s.getTotalsByStatus).toBe("function");\n'
            '    expect(typeof s.getPartnersOwedAtLeast).toBe("function");\n'
            '    expect(typeof s.getPartnerWithPayouts).toBe("function");\n'
        )
        self._assert_passed(result, "import/factory")

    def test_l2_partner_totals_sum_count_and_zero_payout_partner(self):
        """getPartnerTotals() -> p1 total 1150/count 3, p2 30/1, AND p3 (no payouts) total 0/count 0."""
        self._ensure_deps()
        result = self._drive(
            '    const s = seed();\n'
            '    const rows = s.getPartnerTotals();\n'
            '    const m: Record<string, { name: string; total: number; count: number }> = {};\n'
            '    for (const r of rows as any[]) {\n'
            '      m[r.id] = { name: r.name, total: Number(r.total), count: Number(r.count) };\n'
            '    }\n'
            '    expect(m["p1"]).toEqual({ name: "Alice", total: 1150, count: 3 });\n'
            '    expect(m["p2"]).toEqual({ name: "Bob", total: 30, count: 1 });\n'
            '    // zero-payout partner MUST appear with total 0 / count 0 (LEFT JOIN, not INNER)\n'
            '    expect(m["p3"]).toEqual({ name: "Cleo", total: 0, count: 0 });\n'
            '    expect(Object.keys(m).sort()).toEqual(["p1", "p2", "p3"]);\n'
        )
        self._assert_passed(result, "partner-totals")

    def test_l2_totals_by_status_breakdown_omits_empty(self):
        """getTotalsByStatus('p1') -> pending{100,1}, processing{50,1}, completed{1000,1}; p2 only completed."""
        self._ensure_deps()
        result = self._drive(
            '    const s = seed();\n'
            '    const rows = s.getTotalsByStatus("p1");\n'
            '    const m: Record<string, { amount: number; count: number }> = {};\n'
            '    for (const r of rows as any[]) m[r.status] = { amount: Number(r.amount), count: Number(r.count) };\n'
            '    expect(m["pending"]).toEqual({ amount: 100, count: 1 });\n'
            '    expect(m["processing"]).toEqual({ amount: 50, count: 1 });\n'
            '    expect(m["completed"]).toEqual({ amount: 1000, count: 1 });\n'
            '    // p2 has ONLY completed -> pending/processing statuses must be omitted entirely\n'
            '    const r2 = s.getTotalsByStatus("p2");\n'
            '    const m2: Record<string, { amount: number; count: number }> = {};\n'
            '    for (const r of r2 as any[]) m2[r.status] = { amount: Number(r.amount), count: Number(r.count) };\n'
            '    expect(m2).toEqual({ completed: { amount: 30, count: 1 } });\n'
            '    expect(Object.keys(m2)).not.toContain("pending");\n'
            '    expect(Object.keys(m2)).not.toContain("processing");\n'
        )
        self._assert_passed(result, "totals-by-status")

    def test_l2_status_grouping_aggregates_multiple_rows(self):
        """Multiple payouts in the same status for one partner are summed/counted by the DB group-by."""
        self._ensure_deps()
        result = self._drive(
            '    const s = createPayoutStore();\n'
            '    s.addPartner({ id: "x", name: "X" });\n'
            '    s.addPayout({ id: "a", partnerId: "x", amount: 10, status: "pending", periodStart: 1 });\n'
            '    s.addPayout({ id: "b", partnerId: "x", amount: 25, status: "pending", periodStart: 2 });\n'
            '    s.addPayout({ id: "c", partnerId: "x", amount: 7,  status: "pending", periodStart: 3 });\n'
            '    const rows = s.getTotalsByStatus("x");\n'
            '    expect(rows.length).toBe(1);\n'
            '    expect((rows[0] as any).status).toBe("pending");\n'
            '    expect(Number((rows[0] as any).amount)).toBe(42);\n'
            '    expect(Number((rows[0] as any).count)).toBe(3);\n'
            '    // partner totals reflect the grouped sum too\n'
            '    const t = (s.getPartnerTotals() as any[]).find((r:any)=>r.id==="x");\n'
            '    expect(Number(t.total)).toBe(42);\n'
            '    expect(Number(t.count)).toBe(3);\n'
        )
        self._assert_passed(result, "status-grouping")

    def test_l2_owed_at_least_threshold_and_excludes_completed(self):
        """getPartnersOwedAtLeast(100) -> only p1 owed 150; p2 (completed-only -> owed 0) excluded."""
        self._ensure_deps()
        result = self._drive(
            '    const s = seed();\n'
            '    const owed = s.getPartnersOwedAtLeast(100) as any[];\n'
            '    expect(owed.length).toBe(1);\n'
            '    expect(owed[0].id).toBe("p1");\n'
            '    expect(owed[0].name).toBe("Alice");\n'
            '    // owed counts ONLY pending+processing (100+50), NOT the 1000 completed payout\n'
            '    expect(Number(owed[0].owed)).toBe(150);\n'
            '    const ids = owed.map((r:any)=>r.id);\n'
            '    expect(ids).not.toContain("p2");\n'
            '    expect(ids).not.toContain("p3");\n'
        )
        self._assert_passed(result, "owed-at-least")

    def test_l2_owed_at_least_descending_order(self):
        """getPartnersOwedAtLeast orders by owed amount DESC; below-threshold partners excluded."""
        self._ensure_deps()
        result = self._drive(
            '    const s = createPayoutStore();\n'
            '    s.addPartner({ id: "a", name: "A" });\n'
            '    s.addPartner({ id: "b", name: "B" });\n'
            '    s.addPartner({ id: "c", name: "C" });\n'
            '    // owed: a=300 (200 pending + 100 processing), b=150 (pending), c=40 (below threshold)\n'
            '    s.addPayout({ id: "a1", partnerId: "a", amount: 200, status: "pending",    periodStart: 1 });\n'
            '    s.addPayout({ id: "a2", partnerId: "a", amount: 100, status: "processing", periodStart: 2 });\n'
            '    s.addPayout({ id: "a3", partnerId: "a", amount: 999, status: "completed",  periodStart: 3 });\n'
            '    s.addPayout({ id: "b1", partnerId: "b", amount: 150, status: "pending",    periodStart: 1 });\n'
            '    s.addPayout({ id: "c1", partnerId: "c", amount: 40,  status: "pending",    periodStart: 1 });\n'
            '    const owed = s.getPartnersOwedAtLeast(50) as any[];\n'
            '    expect(owed.map((r:any)=>r.id)).toEqual(["a", "b"]);\n'
            '    expect(Number(owed[0].owed)).toBe(300);\n'
            '    expect(Number(owed[1].owed)).toBe(150);\n'
            '    // raise threshold above b: only a remains\n'
            '    const owed2 = s.getPartnersOwedAtLeast(200) as any[];\n'
            '    expect(owed2.map((r:any)=>r.id)).toEqual(["a"]);\n'
        )
        self._assert_passed(result, "owed-descending")

    def test_l2_owed_completed_only_excluded_for_any_positive_threshold(self):
        """A partner with ONLY completed payouts is owed 0 and never appears for a positive threshold."""
        self._ensure_deps()
        result = self._drive(
            '    const s = createPayoutStore();\n'
            '    s.addPartner({ id: "done", name: "Done" });\n'
            '    s.addPayout({ id: "d1", partnerId: "done", amount: 5000, status: "completed", periodStart: 1 });\n'
            '    s.addPayout({ id: "d2", partnerId: "done", amount: 9000, status: "completed", periodStart: 2 });\n'
            '    expect((s.getPartnersOwedAtLeast(1) as any[]).map((r:any)=>r.id)).not.toContain("done");\n'
            '    expect(s.getPartnersOwedAtLeast(1)).toEqual([]);\n'
        )
        self._assert_passed(result, "completed-only-excluded")

    def test_l2_partner_with_payouts_nested_relation(self):
        """getPartnerWithPayouts('p1') -> partner row with its 3 payouts nested in one round trip."""
        self._ensure_deps()
        result = self._drive(
            '    const s = seed();\n'
            '    const p: any = s.getPartnerWithPayouts("p1");\n'
            '    expect(p).not.toBeNull();\n'
            '    expect(p.id).toBe("p1");\n'
            '    expect(p.name).toBe("Alice");\n'
            '    expect(Array.isArray(p.payouts)).toBe(true);\n'
            '    expect(p.payouts.length).toBe(3);\n'
            '    const ids = p.payouts.map((x:any)=>x.id).sort();\n'
            '    expect(ids).toEqual(["y1", "y2", "y3"]);\n'
            '    // nested rows carry the real columns\n'
            '    const byId: Record<string, any> = {};\n'
            '    for (const x of p.payouts) byId[x.id] = x;\n'
            '    expect(byId["y1"].status).toBe("pending");\n'
            '    expect(Number(byId["y1"].amount)).toBe(100);\n'
            '    expect(Number(byId["y3"].amount)).toBe(1000);\n'
            '    // must NOT leak another partner\'s payouts\n'
            '    expect(ids).not.toContain("y4");\n'
        )
        self._assert_passed(result, "partner-with-payouts")

    def test_l2_partner_with_payouts_zero_and_unknown(self):
        """Zero-payout partner -> empty payouts array; unknown partner id -> null (never throws)."""
        self._ensure_deps()
        result = self._drive(
            '    const s = seed();\n'
            '    const p3: any = s.getPartnerWithPayouts("p3");\n'
            '    expect(p3).not.toBeNull();\n'
            '    expect(p3.id).toBe("p3");\n'
            '    expect(Array.isArray(p3.payouts)).toBe(true);\n'
            '    expect(p3.payouts.length).toBe(0);\n'
            '    // unknown id returns null, does not throw\n'
            '    expect(s.getPartnerWithPayouts("nope")).toBeNull();\n'
        )
        self._assert_passed(result, "partner-with-payouts-zero-unknown")

    def test_l2_unknown_partner_empty_results_no_throw(self):
        """Unknown partner id yields empty list results for status/owed reads, never throws."""
        self._ensure_deps()
        result = self._drive(
            '    const s = seed();\n'
            '    expect(s.getTotalsByStatus("nope")).toEqual([]);\n'
            '    // owed filter over a tiny threshold still excludes a non-existent partner\n'
            '    const owed = s.getPartnersOwedAtLeast(1) as any[];\n'
            '    expect(owed.map((r:any)=>r.id)).not.toContain("nope");\n'
        )
        self._assert_passed(result, "unknown-partner")

    def test_l2_negative_amount_and_invalid_partner_rejected(self):
        """addPayout with negative amount, or unknown partnerId, must throw and insert nothing."""
        self._ensure_deps()
        result = self._drive(
            '    const s = createPayoutStore();\n'
            '    s.addPartner({ id: "p", name: "P" });\n'
            '    // negative amount -> throws, nothing inserted\n'
            '    let threwNeg = false;\n'
            '    try { s.addPayout({ id: "neg", partnerId: "p", amount: -1, status: "pending", periodStart: 1 }); }\n'
            '    catch (e) { threwNeg = true; }\n'
            '    expect(threwNeg).toBe(true);\n'
            '    // non-existent partner -> throws, nothing inserted\n'
            '    let threwFk = false;\n'
            '    try { s.addPayout({ id: "orphan", partnerId: "ghost", amount: 10, status: "pending", periodStart: 1 }); }\n'
            '    catch (e) { threwFk = true; }\n'
            '    expect(threwFk).toBe(true);\n'
            '    // partner p still has zero payouts; no orphan/neg rows persisted\n'
            '    const t = (s.getPartnerTotals() as any[]).find((r:any)=>r.id==="p");\n'
            '    expect(Number(t.total)).toBe(0);\n'
            '    expect(Number(t.count)).toBe(0);\n'
            '    expect(s.getTotalsByStatus("p")).toEqual([]);\n'
        )
        self._assert_passed(result, "reject-negative-and-invalid-partner")

    def test_l2_add_payout_returns_inserted_row(self):
        """addPartner/addPayout return the inserted row; a valid payout becomes queryable."""
        self._ensure_deps()
        result = self._drive(
            '    const s = createPayoutStore();\n'
            '    const partner: any = s.addPartner({ id: "p", name: "Pat" });\n'
            '    expect(partner.id).toBe("p");\n'
            '    expect(partner.name).toBe("Pat");\n'
            '    const payout: any = s.addPayout({ id: "z", partnerId: "p", amount: 250, status: "processing", periodStart: 7 });\n'
            '    expect(payout.id).toBe("z");\n'
            '    expect(Number(payout.amount)).toBe(250);\n'
            '    expect(payout.status).toBe("processing");\n'
            '    expect(Number(payout.periodStart)).toBe(7);\n'
            '    // and it is reflected by the aggregates\n'
            '    const t = (s.getPartnerTotals() as any[]).find((r:any)=>r.id==="p");\n'
            '    expect(Number(t.total)).toBe(250);\n'
            '    expect(Number(t.count)).toBe(1);\n'
            '    expect((s.getPartnersOwedAtLeast(250) as any[]).map((r:any)=>r.id)).toEqual(["p"]);\n'
        )
        self._assert_passed(result, "add-returns-row")

    def test_l2_store_isolation_between_instances(self):
        """Two factory-created stores are fully isolated: data in one is invisible to the other."""
        self._ensure_deps()
        result = self._drive(
            '    const a = createPayoutStore();\n'
            '    const b = createPayoutStore();\n'
            '    a.addPartner({ id: "p", name: "A" });\n'
            '    a.addPayout({ id: "y", partnerId: "p", amount: 500, status: "pending", periodStart: 1 });\n'
            '    // b knows nothing of p\n'
            '    expect(b.getPartnerTotals()).toEqual([]);\n'
            '    expect(b.getPartnerWithPayouts("p")).toBeNull();\n'
            '    expect(b.getPartnersOwedAtLeast(1)).toEqual([]);\n'
            '    // a still intact\n'
            '    const at = (a.getPartnerTotals() as any[]).find((r:any)=>r.id==="p");\n'
            '    expect(Number(at.total)).toBe(500);\n'
            '    expect(Number(at.count)).toBe(1);\n'
        )
        self._assert_passed(result, "isolation")

    def test_l2_agent_acceptance_suite_passes(self):
        """The acceptance command must pass: pnpm vitest run tests/payouts/payout-store.test.ts."""
        self._ensure_deps()
        assert os.path.isfile(self.AGENT_TEST), "agent payout-store.test.ts missing"
        result = subprocess.run(
            ["pnpm", "vitest", "run", "tests/payouts/payout-store.test.ts"],
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
        # Guard against an empty/no-test pass.
        combined = (result.stdout + result.stderr).lower()
        assert "no test files found" not in combined, "vitest found no test files"
