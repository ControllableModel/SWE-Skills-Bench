"""
Test for 'drizzle-orm-patterns' skill — In-Memory Link Click Analytics Store (dub monorepo).

Verifies that the Agent built a self-contained, in-process click-analytics store under
apps/web/lib/analytics/click-store/ backed by an embedded better-sqlite3 database and
queried through drizzle-orm. The store must expose a relation-aware schema and a
ClickAnalyticsStore API (addWorkspace / addLink / recordClicks / getLinkClickCounts /
getTopLinks / getClicksByCountry / getWorkspaceReport).

Strategy
--------
L1 checks verify the deliverable files exist, are minimally well-formed, and that
package.json declares drizzle-orm.

L2 checks DO NOT trust the agent's own test file. Instead we drop an independent
TypeScript probe spec into apps/web/tests/analytics/ (vitest's configured test dir),
import the store from "@/lib/analytics/click-store", seed deterministic data, and run
the repo's native command:

    cd apps/web && pnpm vitest run tests/analytics/<probe>.test.ts

asserting on the store's *real* behavior (counts, ordering, pagination boundaries,
country grouping, workspace isolation, unknown-workspace null/empty, unique
domain+key rejection, and all-or-nothing batch inserts). A hardcoded or shallow
solution cannot pass these because the probe drives the public API with novel data.
The agent's own suite is also run separately for the acceptance command.
"""

import json
import os
import subprocess

import pytest


class TestDrizzleOrmPatterns:
    """Verify the in-memory click analytics store built with drizzle-orm + better-sqlite3."""

    REPO_DIR = "/workspace/dub"
    WEB_DIR = os.path.join(REPO_DIR, "apps", "web")
    STORE_DIR = os.path.join(WEB_DIR, "lib", "analytics", "click-store")
    PROBE_NAME = "zz_clickstore_probe.test.ts"
    PROBE_PATH = os.path.join(WEB_DIR, "tests", "analytics", PROBE_NAME)

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
            ["pnpm", "vitest", "run", f"tests/analytics/{self.PROBE_NAME}"],
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
        """
        probe = (
            'import { describe, it, expect } from "vitest";\n'
            'import {\n'
            '  createClickAnalyticsStore,\n'
            '} from "@/lib/analytics/click-store";\n'
            '\n'
            'function seed() {\n'
            '  const s = createClickAnalyticsStore();\n'
            '  s.addWorkspace({ id: "w1", name: "One" });\n'
            '  s.addWorkspace({ id: "w2", name: "Two" });\n'
            '  s.addLink({ id: "l1", workspaceId: "w1", domain: "dub.sh", key: "a", createdAt: 1000 });\n'
            '  s.addLink({ id: "l2", workspaceId: "w1", domain: "dub.sh", key: "b", createdAt: 2000 });\n'
            '  s.addLink({ id: "l3", workspaceId: "w1", domain: "dub.sh", key: "c", createdAt: 3000 });\n'
            '  s.addLink({ id: "l4", workspaceId: "w2", domain: "dub.sh", key: "d", createdAt: 4000 });\n'
            '  s.recordClicks("l1", [\n'
            '    { id: "c1", country: "US", clickedAt: 10 },\n'
            '    { id: "c2", country: "US", clickedAt: 20 },\n'
            '    { id: "c3", clickedAt: 30 },\n'
            '  ]);\n'
            '  s.recordClicks("l2", [{ id: "c4", country: "CA", clickedAt: 40 }]);\n'
            '  s.recordClicks("l4", [\n'
            '    { id: "c5", country: "DE", clickedAt: 50 },\n'
            '    { id: "c6", country: "DE", clickedAt: 60 },\n'
            '  ]);\n'
            '  return s;\n'
            '}\n'
            '\n'
            'describe("clickstore probe", () => {\n'
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
        """schema.ts, store.ts and index.ts must exist under lib/analytics/click-store/."""
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
        """The agent's vitest suite for the click-store must exist."""
        fpath = os.path.join(self.WEB_DIR, "tests", "analytics", "click-store.test.ts")
        assert os.path.isfile(fpath), "expected tests/analytics/click-store.test.ts"
        assert os.path.getsize(fpath) > 0, "click-store.test.ts is empty"

    def test_l1_index_reexports_factory(self):
        """index.ts must re-export the factory so the module is importable from the package root."""
        with open(os.path.join(self.STORE_DIR, "index.ts")) as f:
            content = f.read()
        # Minimal well-formedness: re-export surface mentions the factory symbol.
        assert "createClickAnalyticsStore" in content, (
            "index.ts must surface createClickAnalyticsStore"
        )

    # ------------------------------------------------------------------
    # L2 — dynamic behavior via independent native probe
    # ------------------------------------------------------------------

    def test_l2_module_importable_and_factory_returns_store(self):
        """The module must build & import from @/lib/analytics/click-store and expose the API."""
        self._ensure_deps()
        result = self._drive(
            '    const s = createClickAnalyticsStore();\n'
            '    expect(typeof s.addWorkspace).toBe("function");\n'
            '    expect(typeof s.addLink).toBe("function");\n'
            '    expect(typeof s.recordClicks).toBe("function");\n'
            '    expect(typeof s.getLinkClickCounts).toBe("function");\n'
            '    expect(typeof s.getTopLinks).toBe("function");\n'
            '    expect(typeof s.getClicksByCountry).toBe("function");\n'
            '    expect(typeof s.getWorkspaceReport).toBe("function");\n'
        )
        self._assert_passed(result, "import/factory")

    def test_l2_link_click_counts_include_zero_and_isolate_workspace(self):
        """getLinkClickCounts(w1) -> {l1:3,l2:1,l3:0} and never includes l4 from w2."""
        self._ensure_deps()
        result = self._drive(
            '    const s = seed();\n'
            '    const rows = s.getLinkClickCounts("w1");\n'
            '    const m: Record<string, number> = {};\n'
            '    for (const r of rows) m[r.id] = Number(r.clickCount ?? (r as any).count);\n'
            '    expect(m).toEqual({ l1: 3, l2: 1, l3: 0 });\n'
            '    expect(Object.keys(m)).not.toContain("l4");\n'
            '    // every row exposes id/domain/key\n'
            '    for (const r of rows) {\n'
            '      expect(r.id).toBeDefined();\n'
            '      expect(r.domain).toBe("dub.sh");\n'
            '      expect(typeof r.key).toBe("string");\n'
            '    }\n'
        )
        self._assert_passed(result, "link-click-counts")

    def test_l2_top_links_ordering_and_pagination(self):
        """getTopLinks(w1) sorts by count desc; pagination slices: limit2/off0 -> [l1,l2]; off2 -> [l3]."""
        self._ensure_deps()
        result = self._drive(
            '    const s = seed();\n'
            '    const page1 = s.getTopLinks("w1", { limit: 2, offset: 0 }).map((r:any)=>r.id);\n'
            '    expect(page1).toEqual(["l1", "l2"]);\n'
            '    const page2 = s.getTopLinks("w1", { limit: 2, offset: 2 }).map((r:any)=>r.id);\n'
            '    expect(page2).toEqual(["l3"]);\n'
            '    const first = s.getTopLinks("w1", { limit: 1, offset: 0 })[0] as any;\n'
            '    expect(first.id).toBe("l1");\n'
            '    expect(Number(first.clickCount)).toBe(3);\n'
            '    expect(first.domain).toBe("dub.sh");\n'
        )
        self._assert_passed(result, "top-links")

    def test_l2_pagination_boundaries(self):
        """limit:0 -> []; offset beyond link count -> []."""
        self._ensure_deps()
        result = self._drive(
            '    const s = seed();\n'
            '    expect(s.getTopLinks("w1", { limit: 0, offset: 0 })).toEqual([]);\n'
            '    expect(s.getTopLinks("w1", { limit: 5, offset: 99 })).toEqual([]);\n'
        )
        self._assert_passed(result, "pagination-boundaries")

    def test_l2_createdat_tiebreak_ascending(self):
        """Equal click counts -> ordered by ascending createdAt (insertion-stable tie-break)."""
        self._ensure_deps()
        # Two zero-click links with equal counts: lower createdAt must come first.
        result = self._drive(
            '    const s = createClickAnalyticsStore();\n'
            '    s.addWorkspace({ id: "w", name: "W" });\n'
            '    s.addLink({ id: "early", workspaceId: "w", domain: "d.sh", key: "e", createdAt: 100 });\n'
            '    s.addLink({ id: "late",  workspaceId: "w", domain: "d.sh", key: "l", createdAt: 200 });\n'
            '    // give both the same nonzero count to force the tie-breaker path\n'
            '    s.recordClicks("early", [{ id: "x1", country: "US", clickedAt: 1 }]);\n'
            '    s.recordClicks("late",  [{ id: "x2", country: "US", clickedAt: 2 }]);\n'
            '    const ids = s.getTopLinks("w", { limit: 10, offset: 0 }).map((r:any)=>r.id);\n'
            '    expect(ids).toEqual(["early", "late"]);\n'
        )
        self._assert_passed(result, "createdAt-tiebreak")

    def test_l2_clicks_by_country_unknown_bucket(self):
        """getClicksByCountry(w1) -> US:2, CA:1, unknown:1 (absent country grouped as 'unknown')."""
        self._ensure_deps()
        result = self._drive(
            '    const s = seed();\n'
            '    const byCountry = s.getClicksByCountry("w1");\n'
            '    // normalize: accept array of {country,count} or a plain record\n'
            '    const m: Record<string, number> = {};\n'
            '    if (Array.isArray(byCountry)) {\n'
            '      for (const r of byCountry as any[]) m[r.country] = Number(r.count ?? r.clickCount);\n'
            '    } else {\n'
            '      for (const k of Object.keys(byCountry as any)) m[k] = Number((byCountry as any)[k]);\n'
            '    }\n'
            '    expect(m["US"]).toBe(2);\n'
            '    expect(m["CA"]).toBe(1);\n'
            '    expect(m["unknown"]).toBe(1);\n'
            '    expect(m["l4"]).toBeUndefined();\n'
            '    expect(m["DE"]).toBeUndefined();\n'
        )
        self._assert_passed(result, "clicks-by-country")

    def test_l2_workspace_report_nested_relations(self):
        """getWorkspaceReport(w2) -> w2 with l4 nested and l4.clicks reflecting exactly 2 recorded clicks."""
        self._ensure_deps()
        result = self._drive(
            '    const s = seed();\n'
            '    const rep: any = s.getWorkspaceReport("w2");\n'
            '    expect(rep).not.toBeNull();\n'
            '    expect(rep.id).toBe("w2");\n'
            '    expect(rep.name).toBe("Two");\n'
            '    expect(Array.isArray(rep.links)).toBe(true);\n'
            '    expect(rep.links.length).toBe(1);\n'
            '    const link = rep.links[0];\n'
            '    expect(link.id).toBe("l4");\n'
            '    expect(Array.isArray(link.clicks)).toBe(true);\n'
            '    expect(link.clicks.length).toBe(2);\n'
            '    const cids = link.clicks.map((c:any)=>c.id).sort();\n'
            '    expect(cids).toEqual(["c5", "c6"]);\n'
            '    // w2 must NOT leak w1 links\n'
            '    const ids = rep.links.map((l:any)=>l.id);\n'
            '    expect(ids).not.toContain("l1");\n'
        )
        self._assert_passed(result, "workspace-report")

    def test_l2_unknown_workspace_empty_and_null(self):
        """Unknown workspace id -> [] for list methods and null for getWorkspaceReport, never throws."""
        self._ensure_deps()
        result = self._drive(
            '    const s = seed();\n'
            '    expect(s.getLinkClickCounts("nope")).toEqual([]);\n'
            '    expect(s.getTopLinks("nope", { limit: 10, offset: 0 })).toEqual([]);\n'
            '    const bc = s.getClicksByCountry("nope");\n'
            '    if (Array.isArray(bc)) expect(bc).toEqual([]);\n'
            '    else expect(Object.keys(bc as any).length).toBe(0);\n'
            '    expect(s.getWorkspaceReport("nope")).toBeNull();\n'
        )
        self._assert_passed(result, "unknown-workspace")

    def test_l2_unique_domain_key_rejected(self):
        """Inserting a link with a duplicate domain+key must throw and not create a duplicate row."""
        self._ensure_deps()
        result = self._drive(
            '    const s = createClickAnalyticsStore();\n'
            '    s.addWorkspace({ id: "w", name: "W" });\n'
            '    s.addLink({ id: "a", workspaceId: "w", domain: "dub.sh", key: "dup", createdAt: 1 });\n'
            '    let threw = false;\n'
            '    try {\n'
            '      s.addLink({ id: "b", workspaceId: "w", domain: "dub.sh", key: "dup", createdAt: 2 });\n'
            '    } catch (e) { threw = true; }\n'
            '    expect(threw).toBe(true);\n'
            '    // no duplicate row was created: still exactly one link in the workspace\n'
            '    const rows = s.getLinkClickCounts("w");\n'
            '    expect(rows.length).toBe(1);\n'
            '    expect((rows[0] as any).id).toBe("a");\n'
        )
        self._assert_passed(result, "unique-domain-key")

    def test_l2_all_or_nothing_batch_insert(self):
        """A batch whose 2nd click references a missing link throws and persists NO clicks from it."""
        self._ensure_deps()
        result = self._drive(
            '    const s = createClickAnalyticsStore();\n'
            '    s.addWorkspace({ id: "w", name: "W" });\n'
            '    s.addLink({ id: "L", workspaceId: "w", domain: "dub.sh", key: "k", createdAt: 1 });\n'
            '    let threw = false;\n'
            '    try {\n'
            '      s.recordClicks("L", [\n'
            '        { id: "ok1", country: "US", clickedAt: 1 },\n'
            '        // 2nd click targets a missing link -> whole batch must roll back\n'
            '        { id: "bad", country: "US", clickedAt: 2, linkId: "MISSING" } as any,\n'
            '      ]);\n'
            '    } catch (e) { threw = true; }\n'
            '    expect(threw).toBe(true);\n'
            '    const counts = s.getLinkClickCounts("w");\n'
            '    const row = counts.find((r:any)=>r.id==="L") as any;\n'
            '    expect(Number(row.clickCount)).toBe(0);\n'
        )
        self._assert_passed(result, "all-or-nothing-missing-link")

    def test_l2_all_or_nothing_invalid_clickedat(self):
        """A batch with a non-positive clickedAt throws and leaves the click count unchanged."""
        self._ensure_deps()
        result = self._drive(
            '    const s = createClickAnalyticsStore();\n'
            '    s.addWorkspace({ id: "w", name: "W" });\n'
            '    s.addLink({ id: "L", workspaceId: "w", domain: "dub.sh", key: "k", createdAt: 1 });\n'
            '    s.recordClicks("L", [{ id: "good", country: "US", clickedAt: 5 }]);\n'
            '    let threw = false;\n'
            '    try {\n'
            '      s.recordClicks("L", [\n'
            '        { id: "ok2", country: "US", clickedAt: 6 },\n'
            '        { id: "bad2", country: "US", clickedAt: 0 },\n'
            '      ]);\n'
            '    } catch (e) { threw = true; }\n'
            '    expect(threw).toBe(true);\n'
            '    const counts = s.getLinkClickCounts("w");\n'
            '    const row = counts.find((r:any)=>r.id==="L") as any;\n'
            '    // only the original single valid click survives; the failed batch added nothing\n'
            '    expect(Number(row.clickCount)).toBe(1);\n'
        )
        self._assert_passed(result, "all-or-nothing-invalid-clickedAt")

    def test_l2_store_isolation_between_instances(self):
        """Two factory-created stores are fully isolated: data in one is invisible to the other."""
        self._ensure_deps()
        result = self._drive(
            '    const a = createClickAnalyticsStore();\n'
            '    const b = createClickAnalyticsStore();\n'
            '    a.addWorkspace({ id: "w", name: "A" });\n'
            '    a.addLink({ id: "la", workspaceId: "w", domain: "d.sh", key: "k", createdAt: 1 });\n'
            '    a.recordClicks("la", [{ id: "ca", country: "US", clickedAt: 1 }]);\n'
            '    // b knows nothing of w\n'
            '    expect(b.getLinkClickCounts("w")).toEqual([]);\n'
            '    expect(b.getWorkspaceReport("w")).toBeNull();\n'
            '    // a still intact\n'
            '    const arows = a.getLinkClickCounts("w");\n'
            '    expect(arows.length).toBe(1);\n'
            '    expect(Number((arows[0] as any).clickCount)).toBe(1);\n'
        )
        self._assert_passed(result, "isolation")

    def test_l2_agent_acceptance_suite_passes(self):
        """The acceptance command must pass: pnpm vitest run tests/analytics/click-store.test.ts."""
        self._ensure_deps()
        agent_test = os.path.join(self.WEB_DIR, "tests", "analytics", "click-store.test.ts")
        assert os.path.isfile(agent_test), "agent click-store.test.ts missing"
        result = subprocess.run(
            ["pnpm", "vitest", "run", "tests/analytics/click-store.test.ts"],
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
