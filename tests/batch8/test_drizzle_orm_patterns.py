"""
Test for 'drizzle-orm-patterns' skill (variant ext8) — In-Memory Reward Rule Store
with Typed Conditions (dub monorepo).

Verifies that the Agent built a self-contained, in-process reward-rule store under
apps/web/lib/partners/reward-store/ backed by an embedded better-sqlite3 database and
queried through drizzle-orm. The store must expose a relation-aware schema (programs
+ rules, one-to-many) and a RewardStore API created via a factory
(createRewardStore). Rules carry an event constrained to {"click","lead","sale"},
a non-negative integer `amount`, an integer `priority`, and a structured JSON
`conditions` object ({ minQuantity?: number; country?: string }) that must round-trip
as a typed object (never an opaque blob).

Strategy
--------
L1 checks verify the deliverable files exist, are minimally well-formed, and that
apps/web/package.json declares drizzle-orm.

L2 checks DO NOT trust the agent's own test file. Instead we drop an independent
TypeScript probe spec into apps/web/tests/rewards/ (vitest's configured test dir, see
vitest.config.ts `dir: "./tests"`), import the store from
"@/lib/partners/reward-store" (the `@/lib/*` -> `lib/*` tsconfig alias), seed
deterministic data, and run the repo's native command:

    cd apps/web && pnpm vitest run tests/rewards/<probe>.test.ts

asserting on the store's *real* behavior:
  * typed `conditions` JSON round-trip (populated AND empty-default {});
  * priority-DESC ordering with deterministic ascending-id tie-break;
  * event-constrained filtering (click/lead/sale only);
  * single-round-trip nested getProgramWithRules;
  * countRulesByEvent including 0-count event kinds;
  * negative-amount and invalid-program rejection inserting nothing;
  * unknown program id -> [] / null (never throws);
  * store isolation between factory instances.

A hardcoded or shallow solution (returns fixed values, ignores inputs, stores
conditions as an opaque/untyped blob, computes ordering/counts in JS instead of via
the DB query, or skips persistence) cannot pass these because the probe drives the
public API with novel data and checks concrete values. The agent's own suite is also
run separately for the documented acceptance command.
"""

import json
import os
import subprocess

import pytest


class TestDrizzleOrmPatterns:
    """Verify the in-memory reward-rule store built with drizzle-orm + better-sqlite3."""

    REPO_DIR = "/workspace/dub"
    WEB_DIR = os.path.join(REPO_DIR, "apps", "web")
    STORE_DIR = os.path.join(WEB_DIR, "lib", "partners", "reward-store")
    PROBE_NAME = "zz_rewardstore_probe.test.ts"
    PROBE_PATH = os.path.join(WEB_DIR, "tests", "rewards", PROBE_NAME)

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
            ["pnpm", "vitest", "run", f"tests/rewards/{self.PROBE_NAME}"],
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

        Seed layout (program pr1 + pr2 for isolation/event coverage):
          pr1 sale rules: r_s_b (priority 5, id "b"), r_s_a (priority 5, id "a"),
                          r_s_hi (priority 10, id "hi")
                          -> priority-desc + id-asc => ["hi", "a", "b"]
          pr1 click rule: r_c1 (priority 1) with conditions {minQuantity:3,country:"US"}
          pr1 lead rules: none (so countRulesByEvent must report lead:0)
          pr2 sale rule:  r_p2 (must never appear in pr1 queries)
        """
        probe = (
            'import { describe, it, expect } from "vitest";\n'
            'import {\n'
            '  createRewardStore,\n'
            '} from "@/lib/partners/reward-store";\n'
            '\n'
            'function seed() {\n'
            '  const s = createRewardStore();\n'
            '  s.addProgram({ id: "pr1", name: "Program One" });\n'
            '  s.addProgram({ id: "pr2", name: "Program Two" });\n'
            '  // pr1 sale rules: two ties at priority 5 (ids a,b) plus a priority-10 rule\n'
            '  s.addRule({ id: "hi", programId: "pr1", event: "sale", amount: 100, priority: 10, conditions: {} });\n'
            '  s.addRule({ id: "b",  programId: "pr1", event: "sale", amount: 200, priority: 5,  conditions: {} });\n'
            '  s.addRule({ id: "a",  programId: "pr1", event: "sale", amount: 300, priority: 5,  conditions: {} });\n'
            '  // pr1 click rule carries a populated typed conditions object\n'
            '  s.addRule({ id: "c1", programId: "pr1", event: "click", amount: 50, priority: 1, conditions: { minQuantity: 3, country: "US" } });\n'
            '  // pr2 sale rule must never leak into pr1 queries\n'
            '  s.addRule({ id: "p2", programId: "pr2", event: "sale", amount: 999, priority: 7, conditions: {} });\n'
            '  return s;\n'
            '}\n'
            '\n'
            'describe("rewardstore probe", () => {\n'
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
        """schema.ts, store.ts and index.ts must exist under lib/partners/reward-store/."""
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
        """The agent's vitest suite for the reward-store must exist and be non-empty."""
        fpath = os.path.join(self.WEB_DIR, "tests", "rewards", "reward-store.test.ts")
        assert os.path.isfile(fpath), "expected tests/rewards/reward-store.test.ts"
        assert os.path.getsize(fpath) > 0, "reward-store.test.ts is empty"

    def test_l1_index_reexports_factory(self):
        """index.ts must re-export the factory so the module is importable from the package root."""
        with open(os.path.join(self.STORE_DIR, "index.ts")) as f:
            content = f.read()
        assert "createRewardStore" in content, (
            "index.ts must surface createRewardStore"
        )

    # ------------------------------------------------------------------
    # L2 — dynamic behavior via independent native probe
    # ------------------------------------------------------------------

    def test_l2_module_importable_and_factory_returns_store(self):
        """The module must build & import from @/lib/partners/reward-store and expose the API."""
        self._ensure_deps()
        result = self._drive(
            '    const s = createRewardStore();\n'
            '    expect(typeof s.addProgram).toBe("function");\n'
            '    expect(typeof s.addRule).toBe("function");\n'
            '    expect(typeof s.getRulesForEvent).toBe("function");\n'
            '    expect(typeof s.getProgramWithRules).toBe("function");\n'
            '    expect(typeof s.countRulesByEvent).toBe("function");\n'
        )
        self._assert_passed(result, "import/factory")

    def test_l2_add_program_and_rule_return_inserted_rows(self):
        """addProgram/addRule insert exactly one row each and return the inserted row."""
        self._ensure_deps()
        result = self._drive(
            '    const s = createRewardStore();\n'
            '    const p = s.addProgram({ id: "px", name: "PX" });\n'
            '    expect(p.id).toBe("px");\n'
            '    expect(p.name).toBe("PX");\n'
            '    const r = s.addRule({ id: "rx", programId: "px", event: "lead", amount: 42, priority: 3, conditions: { minQuantity: 2 } });\n'
            '    expect(r.id).toBe("rx");\n'
            '    expect(r.programId).toBe("px");\n'
            '    expect(r.event).toBe("lead");\n'
            '    expect(r.amount).toBe(42);\n'
            '    expect(r.priority).toBe(3);\n'
            '    // conditions surfaces as a typed object, not a JSON string\n'
            '    expect(typeof r.conditions).toBe("object");\n'
            '    expect(r.conditions).toEqual({ minQuantity: 2 });\n'
            '    // exactly one lead rule now exists for px\n'
            '    const leads = s.getRulesForEvent("px", "lead");\n'
            '    expect(leads.length).toBe(1);\n'
            '    expect(leads[0].id).toBe("rx");\n'
        )
        self._assert_passed(result, "insert-returns-row")

    def test_l2_conditions_typed_roundtrip_populated_and_empty(self):
        """conditions round-trips as a typed object: {minQuantity:3,country:'US'} and empty {}."""
        self._ensure_deps()
        result = self._drive(
            '    const s = seed();\n'
            '    const click = s.getRulesForEvent("pr1", "click");\n'
            '    expect(click.length).toBe(1);\n'
            '    const c = click[0];\n'
            '    // must be a real object with typed access, not a string blob\n'
            '    expect(typeof c.conditions).toBe("object");\n'
            '    expect(c.conditions).not.toBeNull();\n'
            '    expect(typeof (c.conditions as any)).not.toBe("string");\n'
            '    expect(c.conditions).toEqual({ minQuantity: 3, country: "US" });\n'
            '    expect((c.conditions as any).minQuantity).toBe(3);\n'
            '    expect((c.conditions as any).country).toBe("US");\n'
            '    // omitted conditions read back as empty object {}\n'
            '    const sale = s.getRulesForEvent("pr1", "sale");\n'
            '    for (const r of sale) {\n'
            '      expect(typeof r.conditions).toBe("object");\n'
            '      expect(r.conditions).toEqual({});\n'
            '    }\n'
        )
        self._assert_passed(result, "conditions-roundtrip")

    def test_l2_conditions_default_empty_when_omitted(self):
        """A rule inserted with no `conditions` key persists and reads back as {}."""
        self._ensure_deps()
        result = self._drive(
            '    const s = createRewardStore();\n'
            '    s.addProgram({ id: "p", name: "P" });\n'
            '    // intentionally omit conditions entirely\n'
            '    s.addRule({ id: "noc", programId: "p", event: "sale", amount: 10, priority: 1 } as any);\n'
            '    const rows = s.getRulesForEvent("p", "sale");\n'
            '    expect(rows.length).toBe(1);\n'
            '    expect(rows[0].conditions).toEqual({});\n'
            '    expect(typeof rows[0].conditions).toBe("object");\n'
        )
        self._assert_passed(result, "conditions-default-empty")

    def test_l2_get_rules_priority_desc_with_id_tiebreak(self):
        """getRulesForEvent('pr1','sale') -> priority desc, ties broken by ascending id => [hi,a,b]."""
        self._ensure_deps()
        result = self._drive(
            '    const s = seed();\n'
            '    const rows = s.getRulesForEvent("pr1", "sale");\n'
            '    const ids = rows.map((r:any)=>r.id);\n'
            '    const prios = rows.map((r:any)=>r.priority);\n'
            '    expect(prios).toEqual([10, 5, 5]);\n'
            '    // ties at priority 5: ascending id => "a" before "b"\n'
            '    expect(ids).toEqual(["hi", "a", "b"]);\n'
            '    // pr2 sale rule must NOT appear\n'
            '    expect(ids).not.toContain("p2");\n'
        )
        self._assert_passed(result, "priority-ordering-tiebreak")

    def test_l2_event_constrained_filtering(self):
        """getRulesForEvent returns only rules of the requested event kind for that program."""
        self._ensure_deps()
        result = self._drive(
            '    const s = seed();\n'
            '    const sale = s.getRulesForEvent("pr1", "sale").map((r:any)=>r.event);\n'
            '    expect(sale.length).toBe(3);\n'
            '    for (const e of sale) expect(e).toBe("sale");\n'
            '    const click = s.getRulesForEvent("pr1", "click").map((r:any)=>r.event);\n'
            '    expect(click).toEqual(["click"]);\n'
            '    // pr1 has no lead rules\n'
            '    expect(s.getRulesForEvent("pr1", "lead")).toEqual([]);\n'
        )
        self._assert_passed(result, "event-filtering")

    def test_l2_invalid_event_rejected(self):
        """Inserting a rule with an event outside {click,lead,sale} must throw and store nothing."""
        self._ensure_deps()
        result = self._drive(
            '    const s = createRewardStore();\n'
            '    s.addProgram({ id: "p", name: "P" });\n'
            '    let threw = false;\n'
            '    try {\n'
            '      s.addRule({ id: "bad", programId: "p", event: "purchase" as any, amount: 1, priority: 1, conditions: {} });\n'
            '    } catch (e) { threw = true; }\n'
            '    expect(threw).toBe(true);\n'
            '    // nothing was persisted for any event kind\n'
            '    const counts = s.countRulesByEvent("p");\n'
            '    const total = (counts.click ?? 0) + (counts.lead ?? 0) + (counts.sale ?? 0);\n'
            '    expect(Number(total)).toBe(0);\n'
        )
        self._assert_passed(result, "invalid-event-rejected")

    def test_l2_get_program_with_rules_nested_single_query(self):
        """getProgramWithRules('pr1') nests all of pr1's rules; unknown program -> null."""
        self._ensure_deps()
        result = self._drive(
            '    const s = seed();\n'
            '    const prog: any = s.getProgramWithRules("pr1");\n'
            '    expect(prog).not.toBeNull();\n'
            '    expect(prog.id).toBe("pr1");\n'
            '    expect(prog.name).toBe("Program One");\n'
            '    expect(Array.isArray(prog.rules)).toBe(true);\n'
            '    // pr1 has 3 sale + 1 click = 4 rules; pr2 rule must not leak in\n'
            '    expect(prog.rules.length).toBe(4);\n'
            '    const rids = prog.rules.map((r:any)=>r.id).sort();\n'
            '    expect(rids).toEqual(["a", "b", "c1", "hi"]);\n'
            '    expect(rids).not.toContain("p2");\n'
            '    // nested conditions are still typed objects\n'
            '    const click = prog.rules.find((r:any)=>r.id==="c1");\n'
            '    expect(click.conditions).toEqual({ minQuantity: 3, country: "US" });\n'
            '    // unknown program -> null, never throws\n'
            '    expect(s.getProgramWithRules("nope")).toBeNull();\n'
        )
        self._assert_passed(result, "program-with-rules")

    def test_l2_count_rules_by_event_includes_zero(self):
        """countRulesByEvent('pr1') reports click/lead/sale with 0 for empty kinds."""
        self._ensure_deps()
        result = self._drive(
            '    const s = seed();\n'
            '    const counts = s.countRulesByEvent("pr1");\n'
            '    expect(Number(counts.sale)).toBe(3);\n'
            '    expect(Number(counts.click)).toBe(1);\n'
            '    // lead has no rules but must still be reported as 0\n'
            '    expect("lead" in counts).toBe(true);\n'
            '    expect(Number(counts.lead)).toBe(0);\n'
            '    // pr2 rule must not be counted for pr1\n'
            '    const total = Number(counts.click) + Number(counts.lead) + Number(counts.sale);\n'
            '    expect(total).toBe(4);\n'
        )
        self._assert_passed(result, "count-by-event")

    def test_l2_negative_amount_rejected_inserts_nothing(self):
        """addRule with a negative amount must throw and insert no row."""
        self._ensure_deps()
        result = self._drive(
            '    const s = createRewardStore();\n'
            '    s.addProgram({ id: "p", name: "P" });\n'
            '    let threw = false;\n'
            '    try {\n'
            '      s.addRule({ id: "neg", programId: "p", event: "sale", amount: -1, priority: 1, conditions: {} });\n'
            '    } catch (e) { threw = true; }\n'
            '    expect(threw).toBe(true);\n'
            '    // nothing persisted\n'
            '    expect(s.getRulesForEvent("p", "sale")).toEqual([]);\n'
            '    const counts = s.countRulesByEvent("p");\n'
            '    expect(Number(counts.sale)).toBe(0);\n'
        )
        self._assert_passed(result, "negative-amount-rejected")

    def test_l2_invalid_program_reference_rejected(self):
        """addRule referencing a non-existent program must throw and insert nothing."""
        self._ensure_deps()
        result = self._drive(
            '    const s = createRewardStore();\n'
            '    // no program "ghost" exists\n'
            '    let threw = false;\n'
            '    try {\n'
            '      s.addRule({ id: "orphan", programId: "ghost", event: "click", amount: 5, priority: 1, conditions: {} });\n'
            '    } catch (e) { threw = true; }\n'
            '    expect(threw).toBe(true);\n'
            '    // the rule was not persisted anywhere\n'
            '    expect(s.getRulesForEvent("ghost", "click")).toEqual([]);\n'
            '    expect(s.getProgramWithRules("ghost")).toBeNull();\n'
        )
        self._assert_passed(result, "invalid-program-rejected")

    def test_l2_unknown_program_empty_and_null_no_throw(self):
        """Unknown program id -> [] for list/count, null for getProgramWithRules; never throws."""
        self._ensure_deps()
        result = self._drive(
            '    const s = seed();\n'
            '    expect(s.getRulesForEvent("missing", "sale")).toEqual([]);\n'
            '    expect(s.getProgramWithRules("missing")).toBeNull();\n'
            '    const counts = s.countRulesByEvent("missing");\n'
            '    // all three kinds present and zero for an unknown program\n'
            '    expect(Number(counts.click)).toBe(0);\n'
            '    expect(Number(counts.lead)).toBe(0);\n'
            '    expect(Number(counts.sale)).toBe(0);\n'
        )
        self._assert_passed(result, "unknown-program")

    def test_l2_store_isolation_between_instances(self):
        """Two factory-created stores are fully isolated: data in one is invisible to the other."""
        self._ensure_deps()
        result = self._drive(
            '    const a = createRewardStore();\n'
            '    const b = createRewardStore();\n'
            '    a.addProgram({ id: "pr1", name: "A" });\n'
            '    a.addRule({ id: "ra", programId: "pr1", event: "sale", amount: 10, priority: 1, conditions: { country: "US" } });\n'
            '    // b knows nothing of pr1\n'
            '    expect(b.getProgramWithRules("pr1")).toBeNull();\n'
            '    expect(b.getRulesForEvent("pr1", "sale")).toEqual([]);\n'
            '    // a still intact and typed\n'
            '    const arows = a.getRulesForEvent("pr1", "sale");\n'
            '    expect(arows.length).toBe(1);\n'
            '    expect(arows[0].conditions).toEqual({ country: "US" });\n'
        )
        self._assert_passed(result, "isolation")

    def test_l2_agent_acceptance_suite_passes(self):
        """The acceptance command must pass: pnpm vitest run tests/rewards/reward-store.test.ts."""
        self._ensure_deps()
        agent_test = os.path.join(self.WEB_DIR, "tests", "rewards", "reward-store.test.ts")
        assert os.path.isfile(agent_test), "agent reward-store.test.ts missing"
        result = subprocess.run(
            ["pnpm", "vitest", "run", "tests/rewards/reward-store.test.ts"],
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
