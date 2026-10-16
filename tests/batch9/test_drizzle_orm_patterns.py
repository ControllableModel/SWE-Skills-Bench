"""
Test for 'drizzle-orm-patterns' skill (variant ext9) — In-Memory Workspace Usage
Counter Store (dub monorepo).

Verifies that the Agent built a self-contained, in-process per-workspace usage
counter store under apps/web/lib/workspace-usage/ backed by an embedded
better-sqlite3 database and queried through drizzle-orm. The store must expose a
relation-aware schema and a UsageStore API created by a factory
(createUsageStore) with:

    addWorkspace / increment / incrementLinkIfUnderLimit / reset /
    getUsage / getWorkspaceUsage / getOverLimitWorkspaces

Strategy
--------
L1 checks verify the deliverable files exist, are minimally well-formed, and that
apps/web/package.json declares drizzle-orm.

L2 checks DO NOT trust the agent's own test file. Instead we drop an independent
TypeScript probe spec into apps/web/tests/workspaces/ (vitest's configured test
dir, `dir: "./tests"`), import the store from "@/lib/workspace-usage" (the
tsconfig path alias used elsewhere in the repo), seed deterministic data, and run
the repo's native command:

    cd apps/web && pnpm vitest run tests/workspaces/<probe>.test.ts

asserting on the store's *real* behavior: metric-constrained counters, atomic
auto-creating increments producing exact arithmetic sums over many calls, the
atomic limit-checked link increment (succeeding strictly under the limit, throwing
and not mutating exactly at the limit), reset-to-zero (including absent counter),
single-round-trip nested workspace+usage loading, the over-limit listing ordered
by id, store isolation, and unknown-id 0/null results.

A hardcoded or shallow solution cannot pass these because the probe drives the
public API with novel data and asserts concrete numeric/relational outcomes
(e.g. 1000 single increments must equal exactly 1000 — lost updates fail; a
limit hit at exactly the boundary must throw and leave usage unchanged). The
agent's own acceptance suite is also run separately for the acceptance command.
"""

import json
import os
import subprocess

import pytest


class TestDrizzleOrmPatterns:
    """Verify the in-memory workspace usage counter store (drizzle-orm + better-sqlite3)."""

    REPO_DIR = "/workspace/dub"
    WEB_DIR = os.path.join(REPO_DIR, "apps", "web")
    STORE_DIR = os.path.join(WEB_DIR, "lib", "workspace-usage")
    PROBE_NAME = "zz_usagestore_probe.test.ts"
    PROBE_PATH = os.path.join(WEB_DIR, "tests", "workspaces", PROBE_NAME)
    AGENT_TEST_REL = "tests/workspaces/usage-store.test.ts"

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
            ["pnpm", "vitest", "run", f"tests/workspaces/{self.PROBE_NAME}"],
            cwd=self.WEB_DIR,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    def _drive(self, assertions_ts: str, timeout=420):
        """
        Build a probe that imports the store factory, runs the provided TS assertion
        body inside a single `it(...)`, execute it natively, and return the
        CompletedProcess. The assertions use vitest `expect`.
        """
        probe = (
            'import { describe, it, expect } from "vitest";\n'
            'import { createUsageStore } from "@/lib/workspace-usage";\n'
            '\n'
            'describe("usagestore probe", () => {\n'
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
        """schema.ts, store.ts and index.ts must exist under lib/workspace-usage/."""
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
        """The agent's vitest suite for the usage-store must exist and be non-empty."""
        fpath = os.path.join(self.WEB_DIR, self.AGENT_TEST_REL)
        assert os.path.isfile(fpath), f"expected {self.AGENT_TEST_REL}"
        assert os.path.getsize(fpath) > 0, "usage-store.test.ts is empty"

    def test_l1_index_reexports_factory(self):
        """index.ts must re-export the factory so the module is importable from the package root."""
        with open(os.path.join(self.STORE_DIR, "index.ts")) as f:
            content = f.read()
        assert "createUsageStore" in content, (
            "index.ts must surface createUsageStore"
        )

    # ------------------------------------------------------------------
    # L2 — dynamic behavior via independent native probe
    # ------------------------------------------------------------------

    def test_l2_module_importable_and_factory_returns_store(self):
        """The module must build & import from @/lib/workspace-usage and expose the full API."""
        self._ensure_deps()
        result = self._drive(
            '    const s = createUsageStore();\n'
            '    expect(typeof s.addWorkspace).toBe("function");\n'
            '    expect(typeof s.increment).toBe("function");\n'
            '    expect(typeof s.incrementLinkIfUnderLimit).toBe("function");\n'
            '    expect(typeof s.reset).toBe("function");\n'
            '    expect(typeof s.getUsage).toBe("function");\n'
            '    expect(typeof s.getWorkspaceUsage).toBe("function");\n'
            '    expect(typeof s.getOverLimitWorkspaces).toBe("function");\n'
        )
        self._assert_passed(result, "import/factory")

    def test_l2_increment_auto_creates_and_reads_back(self):
        """increment auto-creates a counter on first call; getUsage reflects it; absent -> 0."""
        self._ensure_deps()
        result = self._drive(
            '    const s = createUsageStore();\n'
            '    s.addWorkspace({ id: "w1", name: "One", linkLimit: 100 });\n'
            '    // absent counter reads as 0 (never throws)\n'
            '    expect(Number(s.getUsage("w1", "clicks"))).toBe(0);\n'
            '    s.increment("w1", "clicks");\n'
            '    expect(Number(s.getUsage("w1", "clicks"))).toBe(1);\n'
            '    s.increment("w1", "clicks", 4);\n'
            '    expect(Number(s.getUsage("w1", "clicks"))).toBe(5);\n'
            '    // a different metric is independent and still auto-creates\n'
            '    expect(Number(s.getUsage("w1", "ai"))).toBe(0);\n'
            '    s.increment("w1", "ai", 2);\n'
            '    expect(Number(s.getUsage("w1", "ai"))).toBe(2);\n'
            '    expect(Number(s.getUsage("w1", "clicks"))).toBe(5);\n'
        )
        self._assert_passed(result, "increment-auto-create")

    def test_l2_increment_exact_sum_no_lost_updates(self):
        """1000 single increments must yield exactly 1000 — atomic DB update, no lost updates."""
        self._ensure_deps()
        result = self._drive(
            '    const s = createUsageStore();\n'
            '    s.addWorkspace({ id: "w1", name: "One", linkLimit: 100000 });\n'
            '    for (let i = 0; i < 1000; i++) s.increment("w1", "links");\n'
            '    expect(Number(s.getUsage("w1", "links"))).toBe(1000);\n'
            '    // a 20x clicks loop matches the doc example exactly\n'
            '    for (let i = 0; i < 20; i++) s.increment("w1", "clicks");\n'
            '    expect(Number(s.getUsage("w1", "clicks"))).toBe(20);\n'
        )
        self._assert_passed(result, "exact-sum")

    def test_l2_increment_link_if_under_limit_succeeds_below(self):
        """incrementLinkIfUnderLimit succeeds while strictly under the limit and bumps links by 1."""
        self._ensure_deps()
        result = self._drive(
            '    const s = createUsageStore();\n'
            '    s.addWorkspace({ id: "w1", name: "One", linkLimit: 3 });\n'
            '    // bring links usage to 2 via atomic increments\n'
            '    s.increment("w1", "links", 2);\n'
            '    expect(Number(s.getUsage("w1", "links"))).toBe(2);\n'
            '    // 2 < 3 -> succeeds, usage becomes 3\n'
            '    s.incrementLinkIfUnderLimit("w1");\n'
            '    expect(Number(s.getUsage("w1", "links"))).toBe(3);\n'
        )
        self._assert_passed(result, "limit-under-succeeds")

    def test_l2_increment_link_at_limit_throws_and_no_mutation(self):
        """At exactly the limit, incrementLinkIfUnderLimit throws and leaves usage unchanged."""
        self._ensure_deps()
        result = self._drive(
            '    const s = createUsageStore();\n'
            '    s.addWorkspace({ id: "w1", name: "One", linkLimit: 3 });\n'
            '    s.increment("w1", "links", 3);\n'
            '    expect(Number(s.getUsage("w1", "links"))).toBe(3);\n'
            '    let threw = false;\n'
            '    try { s.incrementLinkIfUnderLimit("w1"); } catch (e) { threw = true; }\n'
            '    expect(threw).toBe(true);\n'
            '    // atomic: nothing changed\n'
            '    expect(Number(s.getUsage("w1", "links"))).toBe(3);\n'
            '    // a second attempt still throws and still does not mutate\n'
            '    threw = false;\n'
            '    try { s.incrementLinkIfUnderLimit("w1"); } catch (e) { threw = true; }\n'
            '    expect(threw).toBe(true);\n'
            '    expect(Number(s.getUsage("w1", "links"))).toBe(3);\n'
        )
        self._assert_passed(result, "limit-at-throws")

    def test_l2_limit_never_exceeded_under_repeated_pressure(self):
        """Repeatedly calling the limited increment can never push usage past linkLimit."""
        self._ensure_deps()
        result = self._drive(
            '    const s = createUsageStore();\n'
            '    s.addWorkspace({ id: "w1", name: "One", linkLimit: 5 });\n'
            '    let ok = 0;\n'
            '    for (let i = 0; i < 50; i++) {\n'
            '      try { s.incrementLinkIfUnderLimit("w1"); ok++; }\n'
            '      catch (e) { /* expected once at limit */ }\n'
            '    }\n'
            '    // exactly 5 succeeded; usage capped at the limit\n'
            '    expect(ok).toBe(5);\n'
            '    expect(Number(s.getUsage("w1", "links"))).toBe(5);\n'
        )
        self._assert_passed(result, "limit-never-exceeded")

    def test_l2_reset_to_zero_existing_and_absent(self):
        """reset sets a counter to 0, creating it at 0 when absent."""
        self._ensure_deps()
        result = self._drive(
            '    const s = createUsageStore();\n'
            '    s.addWorkspace({ id: "w1", name: "One", linkLimit: 100 });\n'
            '    s.increment("w1", "clicks", 7);\n'
            '    expect(Number(s.getUsage("w1", "clicks"))).toBe(7);\n'
            '    s.reset("w1", "clicks");\n'
            '    expect(Number(s.getUsage("w1", "clicks"))).toBe(0);\n'
            '    // resetting an absent counter creates it at 0 and does not throw\n'
            '    s.reset("w1", "ai");\n'
            '    expect(Number(s.getUsage("w1", "ai"))).toBe(0);\n'
            '    // increment still works after reset\n'
            '    s.increment("w1", "clicks", 2);\n'
            '    expect(Number(s.getUsage("w1", "clicks"))).toBe(2);\n'
        )
        self._assert_passed(result, "reset")

    def test_l2_get_workspace_usage_nested_relations(self):
        """getWorkspaceUsage nests all of a workspace's metric counters from a single query."""
        self._ensure_deps()
        result = self._drive(
            '    const s = createUsageStore();\n'
            '    s.addWorkspace({ id: "w1", name: "One", linkLimit: 100 });\n'
            '    s.addWorkspace({ id: "w2", name: "Two", linkLimit: 100 });\n'
            '    s.increment("w1", "links", 3);\n'
            '    s.increment("w1", "clicks", 9);\n'
            '    s.increment("w2", "ai", 1);\n'
            '    const rep: any = s.getWorkspaceUsage("w1");\n'
            '    expect(rep).not.toBeNull();\n'
            '    expect(rep.id).toBe("w1");\n'
            '    expect(rep.name).toBe("One");\n'
            '    expect(Array.isArray(rep.usage)).toBe(true);\n'
            '    const m: Record<string, number> = {};\n'
            '    for (const u of rep.usage) m[u.metric] = Number(u.used);\n'
            '    expect(m["links"]).toBe(3);\n'
            '    expect(m["clicks"]).toBe(9);\n'
            '    // w1 must not leak w2 counters\n'
            '    expect(m["ai"]).toBeUndefined();\n'
            '    expect(rep.usage.length).toBe(2);\n'
        )
        self._assert_passed(result, "workspace-usage-nested")

    def test_l2_over_limit_listing_ordered_by_id(self):
        """getOverLimitWorkspaces returns workspaces with links >= limit, ordered by id."""
        self._ensure_deps()
        result = self._drive(
            '    const s = createUsageStore();\n'
            '    // create out of id-order to prove the ORDER BY id\n'
            '    s.addWorkspace({ id: "wc", name: "C", linkLimit: 2 });\n'
            '    s.addWorkspace({ id: "wa", name: "A", linkLimit: 2 });\n'
            '    s.addWorkspace({ id: "wb", name: "B", linkLimit: 5 });\n'
            '    // wc at limit (>=): included; wa above limit: included; wb below: excluded\n'
            '    s.increment("wc", "links", 2);\n'
            '    s.increment("wa", "links", 3);\n'
            '    s.increment("wb", "links", 1);\n'
            '    const over = s.getOverLimitWorkspaces();\n'
            '    const ids = (over as any[]).map((w:any)=>w.id);\n'
            '    expect(ids).toEqual(["wa", "wc"]);\n'
            '    // a workspace strictly under its limit is never listed\n'
            '    expect(ids).not.toContain("wb");\n'
        )
        self._assert_passed(result, "over-limit-listing")

    def test_l2_unknown_workspace_zero_and_null(self):
        """Unknown ids yield 0 for getUsage and null for getWorkspaceUsage, never throw."""
        self._ensure_deps()
        result = self._drive(
            '    const s = createUsageStore();\n'
            '    s.addWorkspace({ id: "w1", name: "One", linkLimit: 10 });\n'
            '    expect(Number(s.getUsage("nope", "clicks"))).toBe(0);\n'
            '    expect(Number(s.getUsage("nope", "links"))).toBe(0);\n'
            '    expect(s.getWorkspaceUsage("nope")).toBeNull();\n'
        )
        self._assert_passed(result, "unknown-workspace")

    def test_l2_store_isolation_between_instances(self):
        """Two factory-created stores are fully isolated; data in one is invisible to the other."""
        self._ensure_deps()
        result = self._drive(
            '    const a = createUsageStore();\n'
            '    const b = createUsageStore();\n'
            '    a.addWorkspace({ id: "w", name: "A", linkLimit: 100 });\n'
            '    a.increment("w", "links", 4);\n'
            '    // b knows nothing of w\n'
            '    expect(Number(b.getUsage("w", "links"))).toBe(0);\n'
            '    expect(b.getWorkspaceUsage("w")).toBeNull();\n'
            '    // a still intact\n'
            '    expect(Number(a.getUsage("w", "links"))).toBe(4);\n'
        )
        self._assert_passed(result, "isolation")

    def test_l2_add_workspace_returns_inserted_no_usage_rows(self):
        """addWorkspace returns the inserted workspace and creates no usage rows yet."""
        self._ensure_deps()
        result = self._drive(
            '    const s = createUsageStore();\n'
            '    const w: any = s.addWorkspace({ id: "w1", name: "One", linkLimit: 7 });\n'
            '    expect(w.id).toBe("w1");\n'
            '    expect(w.name).toBe("One");\n'
            '    expect(Number(w.linkLimit)).toBe(7);\n'
            '    // no usage rows exist yet -> nested usage is empty and all metrics read 0\n'
            '    const rep: any = s.getWorkspaceUsage("w1");\n'
            '    expect(rep).not.toBeNull();\n'
            '    expect(Array.isArray(rep.usage)).toBe(true);\n'
            '    expect(rep.usage.length).toBe(0);\n'
            '    expect(Number(s.getUsage("w1", "links"))).toBe(0);\n'
        )
        self._assert_passed(result, "add-workspace-returns")

    def test_l2_agent_acceptance_suite_passes(self):
        """The acceptance command must pass: pnpm vitest run tests/workspaces/usage-store.test.ts."""
        self._ensure_deps()
        agent_test = os.path.join(self.WEB_DIR, self.AGENT_TEST_REL)
        assert os.path.isfile(agent_test), "agent usage-store.test.ts missing"
        result = subprocess.run(
            ["pnpm", "vitest", "run", self.AGENT_TEST_REL],
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
