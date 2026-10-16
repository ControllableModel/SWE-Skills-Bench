"""
Test for 'drizzle-orm-patterns' skill (variant ext10) — In-Memory API Request
Audit Log with Cursor Pagination (dub monorepo).

Verifies that the Agent built a self-contained, in-process audit log under
apps/web/lib/api-logs/audit-store/ backed by an embedded better-sqlite3 database
and queried through drizzle-orm. The store must expose a table-derived schema and
an AuditStore API created via createAuditStore() exposing:
  record / softDelete / page / countActive / getById.

Strategy
--------
L1 checks verify the deliverable files exist, are minimally well-formed, that
package.json declares drizzle-orm, and that index.ts surfaces the factory.

L2 checks DO NOT trust the agent's own test file. Instead we drop an independent
TypeScript probe spec into apps/web/tests/misc/ (vitest's configured test dir),
import the store from "@/lib/api-logs/audit-store", seed deterministic data, and
run the repo's native command:

    cd apps/web && pnpm vitest run tests/misc/<probe>.test.ts

asserting on the store's *real* behavior: monotonic seq assignment, cursor
pagination that walks every active row exactly once across pages (with and without
soft-deleted rows in between), nextCursor becoming null at the end, limit:0 and
past-the-end cursors returning empty pages, workspace isolation, soft-delete
excluding rows from default reads and countActive, getById honoring includeDeleted,
soft-delete idempotency (unknown / already-deleted ids are no-ops), and store
isolation between factory instances.

A hardcoded or shallow solution (e.g. one that paginates in JS over all rows,
ignores soft-deletion, or returns a fixed nextCursor) cannot pass these because
the probe drives the public API with novel data and asserts exact values. The
agent's own suite is also run separately for the acceptance command.
"""

import json
import os
import subprocess

import pytest


class TestDrizzleOrmPatterns:
    """Verify the in-memory API audit-log store built with drizzle-orm + better-sqlite3."""

    REPO_DIR = "/workspace/dub"
    WEB_DIR = os.path.join(REPO_DIR, "apps", "web")
    STORE_DIR = os.path.join(WEB_DIR, "lib", "api-logs", "audit-store")
    AGENT_TEST = os.path.join(WEB_DIR, "tests", "misc", "audit-store.test.ts")
    PROBE_NAME = "zz_auditstore_probe.test.ts"
    PROBE_PATH = os.path.join(WEB_DIR, "tests", "misc", PROBE_NAME)

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
            ["pnpm", "vitest", "run", f"tests/misc/{self.PROBE_NAME}"],
            cwd=self.WEB_DIR,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    def _drive(self, assertions_ts: str, timeout=420):
        """
        Build a probe that imports the store, seeds a deterministic dataset, runs the
        provided TS assertion body inside a single `it(...)`, execute it natively, and
        return CompletedProcess. The assertions use vitest `expect`.

        seed(): builds a store with 5 active rows for "w1" (recorded in order
        -> seqs strictly increasing r1..r5) and 2 rows for "w2". The seq values
        are NOT assumed to be 1..7; tests read them from the returned rows so the
        assertions hold regardless of the store's starting seq, as long as they
        are monotonically increasing in insertion order.
        """
        probe = (
            'import { describe, it, expect } from "vitest";\n'
            'import { createAuditStore } from "@/lib/api-logs/audit-store";\n'
            '\n'
            'function seed() {\n'
            '  const s = createAuditStore();\n'
            '  const r1 = s.record({ workspaceId: "w1", method: "GET",  path: "/a", statusCode: 200 });\n'
            '  const r2 = s.record({ workspaceId: "w1", method: "POST", path: "/b", statusCode: 201 });\n'
            '  const r3 = s.record({ workspaceId: "w1", method: "GET",  path: "/c", statusCode: 404 });\n'
            '  const r4 = s.record({ workspaceId: "w1", method: "PUT",  path: "/d", statusCode: 200 });\n'
            '  const r5 = s.record({ workspaceId: "w1", method: "GET",  path: "/e", statusCode: 500 });\n'
            '  const x1 = s.record({ workspaceId: "w2", method: "GET",  path: "/x", statusCode: 200 });\n'
            '  const x2 = s.record({ workspaceId: "w2", method: "GET",  path: "/y", statusCode: 200 });\n'
            '  return { s, r1, r2, r3, r4, r5, x1, x2 };\n'
            '}\n'
            '\n'
            'describe("auditstore probe", () => {\n'
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
        """schema.ts, store.ts and index.ts must exist under lib/api-logs/audit-store/."""
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
        """The agent's vitest suite for the audit-store must exist at tests/misc/audit-store.test.ts."""
        assert os.path.isfile(self.AGENT_TEST), "expected tests/misc/audit-store.test.ts"
        assert os.path.getsize(self.AGENT_TEST) > 0, "audit-store.test.ts is empty"

    def test_l1_index_reexports_factory(self):
        """index.ts must re-export the factory so the module is importable from the package root."""
        with open(os.path.join(self.STORE_DIR, "index.ts")) as f:
            content = f.read()
        assert "createAuditStore" in content, (
            "index.ts must surface createAuditStore"
        )

    def test_l1_schema_derives_row_types(self):
        """
        schema.ts must define the audit_logs table via drizzle and derive its row
        type from the table (e.g. $inferSelect / InferSelectModel), not a hand-written
        interface that can silently drift from the columns.
        """
        with open(os.path.join(self.STORE_DIR, "schema.ts")) as f:
            content = f.read()
        assert "drizzle-orm" in content, "schema.ts must import from drizzle-orm"
        assert ("$inferSelect" in content) or ("InferSelectModel" in content) or \
               ("$inferInsert" in content) or ("InferModel" in content), (
            "schema.ts must derive row types from the table definition "
            "($inferSelect / InferSelectModel), not hand-written interfaces"
        )

    # ------------------------------------------------------------------
    # L2 — dynamic behavior via independent native probe
    # ------------------------------------------------------------------

    def test_l2_module_importable_and_factory_returns_store(self):
        """The module must build & import from @/lib/api-logs/audit-store and expose the API."""
        self._ensure_deps()
        result = self._drive(
            '    const s = createAuditStore();\n'
            '    expect(typeof s.record).toBe("function");\n'
            '    expect(typeof s.softDelete).toBe("function");\n'
            '    expect(typeof s.page).toBe("function");\n'
            '    expect(typeof s.countActive).toBe("function");\n'
            '    expect(typeof s.getById).toBe("function");\n'
        )
        self._assert_passed(result, "import/factory")

    def test_l2_record_returns_row_and_assigns_monotonic_seq(self):
        """record() returns the inserted row with deletedAt null and strictly increasing seq."""
        self._ensure_deps()
        result = self._drive(
            '    const { r1, r2, r3, r4, r5 } = seed();\n'
            '    for (const r of [r1, r2, r3, r4, r5]) {\n'
            '      expect(r.id).toBeDefined();\n'
            '      expect(r.workspaceId).toBe("w1");\n'
            '      expect(typeof r.seq).toBe("number");\n'
            '      expect(r.deletedAt === null || r.deletedAt === undefined).toBe(true);\n'
            '    }\n'
            '    // seq is strictly increasing in insertion order\n'
            '    expect(r2.seq).toBeGreaterThan(r1.seq);\n'
            '    expect(r3.seq).toBeGreaterThan(r2.seq);\n'
            '    expect(r4.seq).toBeGreaterThan(r3.seq);\n'
            '    expect(r5.seq).toBeGreaterThan(r4.seq);\n'
            '    // returned row preserves the inputs (not a stub fixed value)\n'
            '    expect(r3.method).toBe("GET");\n'
            '    expect(r3.path).toBe("/c");\n'
            '    expect(r3.statusCode).toBe(404);\n'
        )
        self._assert_passed(result, "record/monotonic-seq")

    def test_l2_page_walks_active_rows_and_nextcursor_terminates(self):
        """
        page(w1, {limit:2}) yields [r1,r2] then [r3,r4] then [r5] then an empty page
        with nextCursor null; w2's rows never appear.
        """
        self._ensure_deps()
        result = self._drive(
            '    const { s, r1, r2, r3, r4, r5 } = seed();\n'
            '    const p1 = s.page("w1", { limit: 2 });\n'
            '    expect(p1.rows.map((r:any)=>r.id)).toEqual([r1.id, r2.id]);\n'
            '    expect(p1.nextCursor).toBe(r2.seq);\n'
            '    const p2 = s.page("w1", { limit: 2, cursor: p1.nextCursor });\n'
            '    expect(p2.rows.map((r:any)=>r.id)).toEqual([r3.id, r4.id]);\n'
            '    expect(p2.nextCursor).toBe(r4.seq);\n'
            '    const p3 = s.page("w1", { limit: 2, cursor: p2.nextCursor });\n'
            '    expect(p3.rows.map((r:any)=>r.id)).toEqual([r5.id]);\n'
            '    expect(p3.nextCursor).toBe(r5.seq);\n'
            '    const p4 = s.page("w1", { limit: 2, cursor: p3.nextCursor });\n'
            '    expect(p4.rows).toEqual([]);\n'
            '    expect(p4.nextCursor).toBeNull();\n'
            '    // workspace isolation: no w2 paths anywhere\n'
            '    const allPaths = [...p1.rows, ...p2.rows, ...p3.rows].map((r:any)=>r.path);\n'
            '    expect(allPaths).not.toContain("/x");\n'
            '    expect(allPaths).not.toContain("/y");\n'
        )
        self._assert_passed(result, "page-walk/nextCursor")

    def test_l2_stable_pagination_visits_every_active_row_once(self):
        """
        Concatenating successive pages (feeding nextCursor) visits every active row
        exactly once in ascending seq order, with no gaps or repeats.
        """
        self._ensure_deps()
        result = self._drive(
            '    const { s, r1, r2, r3, r4, r5 } = seed();\n'
            '    const seen: string[] = [];\n'
            '    let cursor: number | null = null;\n'
            '    let guard = 0;\n'
            '    while (guard++ < 50) {\n'
            '      const opts: any = { limit: 2 };\n'
            '      if (cursor !== null) opts.cursor = cursor;\n'
            '      const pg = s.page("w1", opts);\n'
            '      for (const row of pg.rows) seen.push(row.id);\n'
            '      if (pg.nextCursor === null) break;\n'
            '      cursor = pg.nextCursor;\n'
            '    }\n'
            '    expect(seen).toEqual([r1.id, r2.id, r3.id, r4.id, r5.id]);\n'
            '    // no repeats\n'
            '    expect(new Set(seen).size).toBe(seen.length);\n'
        )
        self._assert_passed(result, "stable-pagination")

    def test_l2_soft_delete_excludes_from_reads_and_count(self):
        """
        Soft-deleting r3 makes page(w1,{limit:2}) yield [r1,r2] then [r4,r5];
        countActive(w1) becomes 4; the deleted row never occupies a page slot.
        """
        self._ensure_deps()
        result = self._drive(
            '    const { s, r1, r2, r3, r4, r5 } = seed();\n'
            '    expect(s.countActive("w1")).toBe(5);\n'
            '    s.softDelete(r3.id);\n'
            '    expect(s.countActive("w1")).toBe(4);\n'
            '    const p1 = s.page("w1", { limit: 2 });\n'
            '    expect(p1.rows.map((r:any)=>r.id)).toEqual([r1.id, r2.id]);\n'
            '    const p2 = s.page("w1", { limit: 2, cursor: p1.nextCursor });\n'
            '    expect(p2.rows.map((r:any)=>r.id)).toEqual([r4.id, r5.id]);\n'
            '    expect(p2.nextCursor).toBe(r5.seq);\n'
            '    const p3 = s.page("w1", { limit: 2, cursor: p2.nextCursor });\n'
            '    expect(p3.rows).toEqual([]);\n'
            '    expect(p3.nextCursor).toBeNull();\n'
            '    // r3 never appears in any page\n'
            '    const everShown = [...p1.rows, ...p2.rows].map((r:any)=>r.id);\n'
            '    expect(everShown).not.toContain(r3.id);\n'
        )
        self._assert_passed(result, "soft-delete-excludes")

    def test_l2_stable_pagination_with_deleted_in_middle(self):
        """
        After soft-deleting an interior row, walking all pages still visits every
        remaining active row exactly once with no gaps/repeats and no deleted row.
        """
        self._ensure_deps()
        result = self._drive(
            '    const { s, r1, r2, r3, r4, r5 } = seed();\n'
            '    s.softDelete(r2.id);\n'
            '    s.softDelete(r4.id);\n'
            '    const seen: string[] = [];\n'
            '    let cursor: number | null = null;\n'
            '    let guard = 0;\n'
            '    while (guard++ < 50) {\n'
            '      const opts: any = { limit: 2 };\n'
            '      if (cursor !== null) opts.cursor = cursor;\n'
            '      const pg = s.page("w1", opts);\n'
            '      for (const row of pg.rows) seen.push(row.id);\n'
            '      if (pg.nextCursor === null) break;\n'
            '      cursor = pg.nextCursor;\n'
            '    }\n'
            '    expect(seen).toEqual([r1.id, r3.id, r5.id]);\n'
            '    expect(seen).not.toContain(r2.id);\n'
            '    expect(seen).not.toContain(r4.id);\n'
            '    expect(new Set(seen).size).toBe(seen.length);\n'
        )
        self._assert_passed(result, "stable-pagination-with-deletes")

    def test_l2_limit_zero_and_past_end_cursor_empty(self):
        """limit:0 -> {rows:[], nextCursor:null}; a cursor past the last row -> empty page."""
        self._ensure_deps()
        result = self._drive(
            '    const { s, r5 } = seed();\n'
            '    const z = s.page("w1", { limit: 0 });\n'
            '    expect(z.rows).toEqual([]);\n'
            '    expect(z.nextCursor).toBeNull();\n'
            '    const beyond = s.page("w1", { limit: 10, cursor: r5.seq + 1000 });\n'
            '    expect(beyond.rows).toEqual([]);\n'
            '    expect(beyond.nextCursor).toBeNull();\n'
        )
        self._assert_passed(result, "limit0/past-end")

    def test_l2_getbyid_honors_include_deleted(self):
        """getById(r3) returns null by default for a soft-deleted row, the row when includeDeleted true."""
        self._ensure_deps()
        result = self._drive(
            '    const { s, r3 } = seed();\n'
            '    const before: any = s.getById(r3.id);\n'
            '    expect(before).not.toBeNull();\n'
            '    expect(before.id).toBe(r3.id);\n'
            '    s.softDelete(r3.id);\n'
            '    // default: deleted row hidden\n'
            '    expect(s.getById(r3.id)).toBeNull();\n'
            '    // includeDeleted: row returned, with a non-null deletedAt\n'
            '    const incl: any = s.getById(r3.id, { includeDeleted: true });\n'
            '    expect(incl).not.toBeNull();\n'
            '    expect(incl.id).toBe(r3.id);\n'
            '    expect(incl.deletedAt === null || incl.deletedAt === undefined).toBe(false);\n'
            '    // unknown id -> null, never throws\n'
            '    expect(s.getById("does-not-exist")).toBeNull();\n'
        )
        self._assert_passed(result, "getById/includeDeleted")

    def test_l2_soft_delete_idempotent_noop(self):
        """Soft-deleting an unknown id or an already-deleted row is a no-op and never throws."""
        self._ensure_deps()
        result = self._drive(
            '    const { s, r1 } = seed();\n'
            '    // unknown id: no throw, count unchanged\n'
            '    expect(() => s.softDelete("nope")).not.toThrow();\n'
            '    expect(s.countActive("w1")).toBe(5);\n'
            '    s.softDelete(r1.id);\n'
            '    expect(s.countActive("w1")).toBe(4);\n'
            '    // deleting again: still a no-op, count stays at 4\n'
            '    expect(() => s.softDelete(r1.id)).not.toThrow();\n'
            '    expect(s.countActive("w1")).toBe(4);\n'
        )
        self._assert_passed(result, "soft-delete-idempotent")

    def test_l2_workspace_isolation_count_and_page(self):
        """countActive and page are scoped per workspace; w2 has exactly its own 2 rows."""
        self._ensure_deps()
        result = self._drive(
            '    const { s, x1, x2 } = seed();\n'
            '    expect(s.countActive("w2")).toBe(2);\n'
            '    const p = s.page("w2", { limit: 10 });\n'
            '    expect(p.rows.map((r:any)=>r.id)).toEqual([x1.id, x2.id]);\n'
            '    // every returned row truly belongs to w2\n'
            '    for (const r of p.rows) expect(r.workspaceId).toBe("w2");\n'
            '    // soft-deleting a w1 row does not affect w2 count\n'
            '    const w1page = s.page("w1", { limit: 1 });\n'
            '    s.softDelete(w1page.rows[0].id);\n'
            '    expect(s.countActive("w2")).toBe(2);\n'
            '    // unknown workspace -> empty page, count 0, no throw\n'
            '    expect(s.countActive("nope")).toBe(0);\n'
            '    const empty = s.page("nope", { limit: 10 });\n'
            '    expect(empty.rows).toEqual([]);\n'
            '    expect(empty.nextCursor).toBeNull();\n'
        )
        self._assert_passed(result, "workspace-isolation")

    def test_l2_store_isolation_between_instances(self):
        """Two factory-created stores are fully isolated: data in one is invisible to the other."""
        self._ensure_deps()
        result = self._drive(
            '    const a = createAuditStore();\n'
            '    const b = createAuditStore();\n'
            '    const ra = a.record({ workspaceId: "w", method: "GET", path: "/p", statusCode: 200 });\n'
            '    expect(a.countActive("w")).toBe(1);\n'
            '    // b knows nothing of w\n'
            '    expect(b.countActive("w")).toBe(0);\n'
            '    expect(b.getById(ra.id)).toBeNull();\n'
            '    const bp = b.page("w", { limit: 10 });\n'
            '    expect(bp.rows).toEqual([]);\n'
            '    expect(bp.nextCursor).toBeNull();\n'
            '    // a still intact\n'
            '    const ap = a.page("w", { limit: 10 });\n'
            '    expect(ap.rows.length).toBe(1);\n'
            '    expect(ap.rows[0].id).toBe(ra.id);\n'
        )
        self._assert_passed(result, "store-isolation")

    def test_l2_agent_acceptance_suite_passes(self):
        """The acceptance command must pass: pnpm vitest run tests/misc/audit-store.test.ts."""
        self._ensure_deps()
        assert os.path.isfile(self.AGENT_TEST), "agent audit-store.test.ts missing"
        result = subprocess.run(
            ["pnpm", "vitest", "run", "tests/misc/audit-store.test.ts"],
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
