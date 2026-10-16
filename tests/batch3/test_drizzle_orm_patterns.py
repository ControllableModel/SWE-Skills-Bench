"""
Test for 'drizzle-orm-patterns' skill (variant ext3) — In-Memory Folder Hierarchy
and Permission Store (dub monorepo).

Verifies that the Agent built a self-contained, in-process folder/permission store
under apps/web/lib/folder/folder-store/ backed by an embedded better-sqlite3 database
opened with ":memory:" and queried through drizzle-orm. The store must expose a
relation-aware schema (self-referencing folders + folder_access grants) and a
FolderStore API created via createFolderStore():
    addFolder / grantAccess / revokeAccess /
    getChildren / getDescendantIds / getAccessibleFolders / getEffectiveRole

Strategy
--------
L1 checks verify the deliverable files exist, are minimally well-formed, and that
apps/web/package.json declares drizzle-orm.

L2 checks DO NOT trust the agent's own test file. Instead we drop an independent
TypeScript probe spec into apps/web/tests/folders/ (vitest's configured test dir),
import the store from "@/lib/folder/folder-store", seed a deterministic folder tree
and grants, and run the repo's native command:

    cd apps/web && pnpm vitest run tests/folders/<probe>.test.ts

asserting on the store's *real* behavior:
  - self-referencing children ordered by name
  - multi-level descendant traversal computed IN-DATABASE (recursive), not by JS
    walking — verified for trees several levels deep, and empty for a leaf
  - role-constrained grants with upsert-on-conflict (no duplicate grant rows)
  - no-op revoke of a non-existent grant
  - accessible-folder listing paired with role, ordered by name
  - getEffectiveRole returning null when no grant exists
  - invalid-parent rejection that creates no row
  - store isolation between factory instances
  - unknown ids -> empty list / null, never throw

A hardcoded or shallow solution cannot pass these because the probe drives the public
API with novel data. The agent's own suite is also run separately for the acceptance
command (test_l2_agent_acceptance_suite_passes).
"""

import json
import os
import subprocess

import pytest


class TestDrizzleOrmPatterns:
    """Verify the in-memory folder hierarchy + permission store (drizzle-orm + better-sqlite3)."""

    REPO_DIR = "/workspace/dub"
    WEB_DIR = os.path.join(REPO_DIR, "apps", "web")
    STORE_DIR = os.path.join(WEB_DIR, "lib", "folder", "folder-store")
    PROBE_NAME = "zz_folderstore_probe.test.ts"
    PROBE_PATH = os.path.join(WEB_DIR, "tests", "folders", PROBE_NAME)
    AGENT_TEST = os.path.join(WEB_DIR, "tests", "folders", "folder-store.test.ts")

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
            ["pnpm", "vitest", "run", f"tests/folders/{self.PROBE_NAME}"],
            cwd=self.WEB_DIR,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    # Deterministic tree used by most probes:
    #   root -> a -> b -> c   and   root -> d
    # Children of root by name: [a, d].
    # Descendants of root: {a, b, c, d}. Descendants of c: {}.
    _SEED = (
        'function seed() {\n'
        '  const s = createFolderStore();\n'
        '  s.addFolder({ id: "root", name: "Root", parentId: null });\n'
        '  // insert children out of alphabetical order to prove DB ordering, not insert order\n'
        '  s.addFolder({ id: "d", name: "Delta", parentId: "root" });\n'
        '  s.addFolder({ id: "a", name: "Alpha", parentId: "root" });\n'
        '  s.addFolder({ id: "b", name: "Bravo", parentId: "a" });\n'
        '  s.addFolder({ id: "c", name: "Charlie", parentId: "b" });\n'
        '  s.grantAccess("a", "u1", "viewer");\n'
        '  s.grantAccess("b", "u1", "editor");\n'
        '  s.grantAccess("root", "u2", "owner");\n'
        '  return s;\n'
        '}\n'
    )

    def _drive(self, assertions_ts: str, timeout=420):
        """
        Build a probe that imports the store, defines the deterministic seed, runs the
        provided TS assertion body inside a single `it(...)`, executes it natively, and
        returns the CompletedProcess. Assertions use vitest `expect`.
        """
        probe = (
            'import { describe, it, expect } from "vitest";\n'
            'import { createFolderStore } from "@/lib/folder/folder-store";\n'
            '\n'
            + self._SEED +
            '\n'
            'describe("folderstore probe", () => {\n'
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
        """schema.ts, store.ts and index.ts must exist under lib/folder/folder-store/."""
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
        """The agent's vitest suite for the folder-store must exist and be non-empty."""
        assert os.path.isfile(self.AGENT_TEST), \
            "expected tests/folders/folder-store.test.ts"
        assert os.path.getsize(self.AGENT_TEST) > 0, "folder-store.test.ts is empty"

    def test_l1_index_reexports_factory(self):
        """index.ts must re-export the factory so the module is importable from the package root."""
        with open(os.path.join(self.STORE_DIR, "index.ts")) as f:
            content = f.read()
        assert "createFolderStore" in content, (
            "index.ts must surface createFolderStore"
        )

    def test_l1_schema_derives_row_types_from_tables(self):
        """schema.ts must derive row types from the table defs (drizzle $inferSelect/$inferInsert),
        not hand-written interfaces that can drift from the columns."""
        with open(os.path.join(self.STORE_DIR, "schema.ts")) as f:
            content = f.read()
        assert ("$inferSelect" in content) or ("$inferInsert" in content) or \
               ("InferSelectModel" in content) or ("InferInsertModel" in content), (
            "schema.ts must derive row types from the table definitions "
            "(e.g. table.$inferSelect / InferSelectModel), not hand-written interfaces"
        )

    # ------------------------------------------------------------------
    # L2 — dynamic behavior via independent native probe
    # ------------------------------------------------------------------

    def test_l2_module_importable_and_factory_returns_store(self):
        """The module must build & import from @/lib/folder/folder-store and expose the full API."""
        self._ensure_deps()
        result = self._drive(
            '    const s = createFolderStore();\n'
            '    expect(typeof s.addFolder).toBe("function");\n'
            '    expect(typeof s.grantAccess).toBe("function");\n'
            '    expect(typeof s.revokeAccess).toBe("function");\n'
            '    expect(typeof s.getChildren).toBe("function");\n'
            '    expect(typeof s.getDescendantIds).toBe("function");\n'
            '    expect(typeof s.getAccessibleFolders).toBe("function");\n'
            '    expect(typeof s.getEffectiveRole).toBe("function");\n'
        )
        self._assert_passed(result, "import/factory")

    def test_l2_get_children_ordered_by_name(self):
        """getChildren('root') -> [a, d] ordered by name (Alpha < Delta), regardless of insert order;
        a leaf folder returns an empty list."""
        self._ensure_deps()
        result = self._drive(
            '    const s = seed();\n'
            '    const kids = s.getChildren("root").map((f:any)=>f.id);\n'
            '    expect(kids).toEqual(["a", "d"]);\n'
            '    // each returned row is a real folder with name + parentId\n'
            '    const named = s.getChildren("root").map((f:any)=>f.name);\n'
            '    expect(named).toEqual(["Alpha", "Delta"]);\n'
            '    for (const f of s.getChildren("root") as any[]) {\n'
            '      expect(f.parentId).toBe("root");\n'
            '    }\n'
            '    // leaf folder has no children\n'
            '    expect(s.getChildren("c")).toEqual([]);\n'
        )
        self._assert_passed(result, "get-children")

    def test_l2_descendant_ids_multilevel(self):
        """getDescendantIds('root') -> {a,b,c,d} at all depths; excludes root itself;
        getDescendantIds('a') -> {b,c}; getDescendantIds('c') (leaf) -> []."""
        self._ensure_deps()
        result = self._drive(
            '    const s = seed();\n'
            '    const all = [...s.getDescendantIds("root")].sort();\n'
            '    expect(all).toEqual(["a", "b", "c", "d"]);\n'
            '    expect(all).not.toContain("root");\n'
            '    const fromA = [...s.getDescendantIds("a")].sort();\n'
            '    expect(fromA).toEqual(["b", "c"]);\n'
            '    expect(s.getDescendantIds("c")).toEqual([]);\n'
        )
        self._assert_passed(result, "descendant-ids")

    def test_l2_descendant_ids_deep_chain(self):
        """A deep chain n0->n1->...->n7 must be traversed fully in-database (recursive),
        not capped at one or two levels: descendants of n0 == {n1..n7}."""
        self._ensure_deps()
        result = self._drive(
            '    const s = createFolderStore();\n'
            '    s.addFolder({ id: "n0", name: "n0", parentId: null });\n'
            '    for (let i = 1; i <= 7; i++) {\n'
            '      s.addFolder({ id: "n" + i, name: "n" + i, parentId: "n" + (i - 1) });\n'
            '    }\n'
            '    const desc = [...s.getDescendantIds("n0")].sort();\n'
            '    expect(desc).toEqual(["n1","n2","n3","n4","n5","n6","n7"]);\n'
            '    // mid-chain node sees only what is below it\n'
            '    const mid = [...s.getDescendantIds("n5")].sort();\n'
            '    expect(mid).toEqual(["n6","n7"]);\n'
            '    // deepest leaf has no descendants\n'
            '    expect(s.getDescendantIds("n7")).toEqual([]);\n'
        )
        self._assert_passed(result, "descendant-deep-chain")

    def test_l2_grant_upsert_no_duplicate(self):
        """grantAccess twice for the same (folder,user) updates the role in place (no duplicate row);
        getEffectiveRole reflects the latest role."""
        self._ensure_deps()
        result = self._drive(
            '    const s = createFolderStore();\n'
            '    s.addFolder({ id: "a", name: "A", parentId: null });\n'
            '    s.grantAccess("a", "u1", "viewer");\n'
            '    s.grantAccess("a", "u1", "owner");\n'
            '    // exactly one accessible folder for u1, with the updated role\n'
            '    const acc = s.getAccessibleFolders("u1") as any[];\n'
            '    const forA = acc.filter((r:any)=> (r.id ?? r.folderId) === "a");\n'
            '    expect(forA.length).toBe(1);\n'
            '    expect(s.getEffectiveRole("a", "u1")).toBe("owner");\n'
        )
        self._assert_passed(result, "grant-upsert")

    def test_l2_effective_role_null_when_no_grant(self):
        """getEffectiveRole returns the granted role, or null when the user has no grant
        on that folder; revokeAccess removes the grant."""
        self._ensure_deps()
        result = self._drive(
            '    const s = seed();\n'
            '    expect(s.getEffectiveRole("a", "u1")).toBe("viewer");\n'
            '    expect(s.getEffectiveRole("b", "u1")).toBe("editor");\n'
            '    // u1 has no grant on the root folder\n'
            '    expect(s.getEffectiveRole("root", "u1")).toBeNull();\n'
            '    // unknown folder / unknown user -> null, never throws\n'
            '    expect(s.getEffectiveRole("nope", "u1")).toBeNull();\n'
            '    expect(s.getEffectiveRole("a", "ghost")).toBeNull();\n'
            '    s.revokeAccess("a", "u1");\n'
            '    expect(s.getEffectiveRole("a", "u1")).toBeNull();\n'
        )
        self._assert_passed(result, "effective-role-null")

    def test_l2_revoke_is_noop_when_absent(self):
        """revokeAccess on a (folder,user) with no grant is a no-op and does not throw or
        disturb other grants."""
        self._ensure_deps()
        result = self._drive(
            '    const s = createFolderStore();\n'
            '    s.addFolder({ id: "a", name: "A", parentId: null });\n'
            '    s.grantAccess("a", "keep", "editor");\n'
            '    // revoking a grant that never existed must not throw\n'
            '    expect(() => s.revokeAccess("a", "never")).not.toThrow();\n'
            '    expect(() => s.revokeAccess("ghostfolder", "never")).not.toThrow();\n'
            '    // the unrelated grant is untouched\n'
            '    expect(s.getEffectiveRole("a", "keep")).toBe("editor");\n'
        )
        self._assert_passed(result, "revoke-noop")

    def test_l2_accessible_folders_with_role_ordered(self):
        """getAccessibleFolders(u1) lists only folders u1 has grants on, each paired with the
        user's role, ordered by folder name; excludes folders granted to other users."""
        self._ensure_deps()
        result = self._drive(
            '    const s = createFolderStore();\n'
            '    // names chosen so name-order differs from id/insert order\n'
            '    s.addFolder({ id: "z", name: "Apple",  parentId: null });\n'
            '    s.addFolder({ id: "y", name: "Mango",  parentId: null });\n'
            '    s.addFolder({ id: "x", name: "Cherry", parentId: null });\n'
            '    s.addFolder({ id: "w", name: "Other",  parentId: null });\n'
            '    s.grantAccess("y", "u1", "owner");\n'
            '    s.grantAccess("z", "u1", "viewer");\n'
            '    s.grantAccess("x", "u1", "editor");\n'
            '    s.grantAccess("w", "u2", "owner");   // belongs to a different user\n'
            '    const rows = s.getAccessibleFolders("u1") as any[];\n'
            '    const ids = rows.map((r:any)=> r.id ?? r.folderId);\n'
            '    // ordered by name: Apple(z) < Cherry(x) < Mango(y)\n'
            '    expect(ids).toEqual(["z", "x", "y"]);\n'
            '    expect(ids).not.toContain("w");\n'
            '    // role is paired with each folder\n'
            '    const byId: Record<string,string> = {};\n'
            '    for (const r of rows) byId[r.id ?? r.folderId] = r.role;\n'
            '    expect(byId["z"]).toBe("viewer");\n'
            '    expect(byId["x"]).toBe("editor");\n'
            '    expect(byId["y"]).toBe("owner");\n'
        )
        self._assert_passed(result, "accessible-folders")

    def test_l2_invalid_parent_rejected_no_row(self):
        """addFolder with a non-null parentId that references a missing folder must throw and
        create NO row."""
        self._ensure_deps()
        result = self._drive(
            '    const s = createFolderStore();\n'
            '    s.addFolder({ id: "root", name: "Root", parentId: null });\n'
            '    let threw = false;\n'
            '    try {\n'
            '      s.addFolder({ id: "orphan", name: "Orphan", parentId: "does-not-exist" });\n'
            '    } catch (e) { threw = true; }\n'
            '    expect(threw).toBe(true);\n'
            '    // no orphan row was created: it must not appear anywhere\n'
            '    expect(s.getDescendantIds("root")).toEqual([]);\n'
            '    expect(s.getChildren("does-not-exist")).toEqual([]);\n'
            '    // a valid sibling can still be added afterwards (store not corrupted)\n'
            '    s.addFolder({ id: "ok", name: "Ok", parentId: "root" });\n'
            '    expect(s.getChildren("root").map((f:any)=>f.id)).toEqual(["ok"]);\n'
        )
        self._assert_passed(result, "invalid-parent")

    def test_l2_add_folder_returns_inserted_row(self):
        """addFolder returns the inserted folder with its id/name/parentId echoed back."""
        self._ensure_deps()
        result = self._drive(
            '    const s = createFolderStore();\n'
            '    const root = s.addFolder({ id: "r", name: "R", parentId: null }) as any;\n'
            '    expect(root.id).toBe("r");\n'
            '    expect(root.name).toBe("R");\n'
            '    expect(root.parentId).toBeNull();\n'
            '    const child = s.addFolder({ id: "ch", name: "Child", parentId: "r" }) as any;\n'
            '    expect(child.id).toBe("ch");\n'
            '    expect(child.parentId).toBe("r");\n'
        )
        self._assert_passed(result, "add-folder-returns")

    def test_l2_store_isolation_between_instances(self):
        """Two factory-created stores are fully isolated: data in one is invisible to the other."""
        self._ensure_deps()
        result = self._drive(
            '    const a = createFolderStore();\n'
            '    const b = createFolderStore();\n'
            '    a.addFolder({ id: "root", name: "Root", parentId: null });\n'
            '    a.addFolder({ id: "kid", name: "Kid", parentId: "root" });\n'
            '    a.grantAccess("root", "u", "owner");\n'
            '    // b knows nothing of a\'s data\n'
            '    expect(b.getChildren("root")).toEqual([]);\n'
            '    expect(b.getDescendantIds("root")).toEqual([]);\n'
            '    expect(b.getEffectiveRole("root", "u")).toBeNull();\n'
            '    expect(b.getAccessibleFolders("u")).toEqual([]);\n'
            '    // a is intact\n'
            '    expect(a.getChildren("root").map((f:any)=>f.id)).toEqual(["kid"]);\n'
            '    expect(a.getEffectiveRole("root", "u")).toBe("owner");\n'
        )
        self._assert_passed(result, "isolation")

    def test_l2_unknown_ids_empty_and_null(self):
        """Unknown folder/user ids yield empty lists / null and never throw."""
        self._ensure_deps()
        result = self._drive(
            '    const s = seed();\n'
            '    expect(s.getChildren("nope")).toEqual([]);\n'
            '    expect(s.getDescendantIds("nope")).toEqual([]);\n'
            '    expect(s.getAccessibleFolders("ghost")).toEqual([]);\n'
            '    expect(s.getEffectiveRole("nope", "ghost")).toBeNull();\n'
        )
        self._assert_passed(result, "unknown-ids")

    def test_l2_agent_acceptance_suite_passes(self):
        """The acceptance command must pass: pnpm vitest run tests/folders/folder-store.test.ts."""
        self._ensure_deps()
        assert os.path.isfile(self.AGENT_TEST), "agent folder-store.test.ts missing"
        result = subprocess.run(
            ["pnpm", "vitest", "run", "tests/folders/folder-store.test.ts"],
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
