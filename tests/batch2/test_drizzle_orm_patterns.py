"""
Test for 'drizzle-orm-patterns' skill (variant ext2) — In-Memory Tag-to-Link Tagging Store
(dub monorepo, apps/web).

Verifies that the Agent built a self-contained, in-process tagging store under
apps/web/lib/links/tag-store/ backed by an embedded better-sqlite3 database and queried
through drizzle-orm. The store models a many-to-many relationship between links and tags
via a link_tags association table, and exposes a TagStore API:

    createTagStore()
    addLink / addTag
    tagLink / untagLink / setLinkTags
    getTagsForLink / getLinksForTag / getLinkWithTags / countLinksPerTag

Strategy
--------
L1 checks verify the deliverable files exist, are minimally well-formed, and that
apps/web/package.json declares drizzle-orm.

L2 checks DO NOT trust the agent's own test file. Instead we drop an independent
TypeScript probe spec into apps/web/tests/links/ (the configured vitest `dir: ./tests`),
import the store from "@/lib/links/tag-store", seed deterministic data, and run the repo's
native command:

    cd apps/web && pnpm vitest run tests/links/<probe>.test.ts

asserting on the store's *real* behavior: many-to-many navigation in both directions with
specified ordering, single-round-trip nested loading, idempotent tagLink, no-op untagLink,
atomic setLinkTags (including rollback when a tag id is missing), zero-link tags appearing
in countLinksPerTag with count 0, unique tag-name rejection, store isolation, and
unknown-id empty/null results. A hardcoded or shallow solution (returns fixed values,
ignores inputs, computes in JS instead of SQL, skips rollback) cannot pass because the
probe drives the public API with novel data and asserts concrete values, ordering, and
error/rollback behavior. The agent's own suite is also run separately for the acceptance
command.
"""

import json
import os
import subprocess

import pytest


class TestDrizzleOrmPatterns:
    """Verify the in-memory tag-to-link tagging store built with drizzle-orm + better-sqlite3."""

    REPO_DIR = "/workspace/dub"
    WEB_DIR = os.path.join(REPO_DIR, "apps", "web")
    STORE_DIR = os.path.join(WEB_DIR, "lib", "links", "tag-store")
    PROBE_NAME = "zz_tagstore_probe.test.ts"
    PROBE_PATH = os.path.join(WEB_DIR, "tests", "links", PROBE_NAME)

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
            ["pnpm", "vitest", "run", f"tests/links/{self.PROBE_NAME}"],
            cwd=self.WEB_DIR,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    def _drive(self, assertions_ts: str, timeout=420):
        """
        Build a probe that imports the store, seeds a deterministic dataset, runs the
        provided TS assertion body inside a single `it(...)`, execute it natively, and
        return the CompletedProcess. The assertions use vitest `expect`.

        Seed (a fixed many-to-many graph):
          links:  l1(dub.sh/a), l2(dub.sh/b), l3(dub.sh/c)
          tags:   t1(alpha), t2(beta), t3(gamma)   [t3 attached to nobody]
          edges:  l1->{t1,t2}, l2->{t2}
        """
        probe = (
            'import { describe, it, expect } from "vitest";\n'
            'import { createTagStore } from "@/lib/links/tag-store";\n'
            '\n'
            'function seed() {\n'
            '  const s = createTagStore();\n'
            '  s.addLink({ id: "l1", domain: "dub.sh", key: "a" });\n'
            '  s.addLink({ id: "l2", domain: "dub.sh", key: "b" });\n'
            '  s.addLink({ id: "l3", domain: "dub.sh", key: "c" });\n'
            '  s.addTag({ id: "t1", name: "alpha" });\n'
            '  s.addTag({ id: "t2", name: "beta" });\n'
            '  s.addTag({ id: "t3", name: "gamma" });\n'
            '  s.tagLink("l1", "t1");\n'
            '  s.tagLink("l1", "t2");\n'
            '  s.tagLink("l2", "t2");\n'
            '  return s;\n'
            '}\n'
            '\n'
            'describe("tagstore probe", () => {\n'
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
        """schema.ts, store.ts and index.ts must exist under lib/links/tag-store/."""
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
        """The agent's vitest suite for the tag-store must exist."""
        fpath = os.path.join(self.WEB_DIR, "tests", "links", "tag-store.test.ts")
        assert os.path.isfile(fpath), "expected tests/links/tag-store.test.ts"
        assert os.path.getsize(fpath) > 0, "tag-store.test.ts is empty"

    def test_l1_index_reexports_factory(self):
        """index.ts must re-export the factory so the module is importable from the package root."""
        with open(os.path.join(self.STORE_DIR, "index.ts")) as f:
            content = f.read()
        assert "createTagStore" in content, "index.ts must surface createTagStore"

    def test_l1_schema_defines_link_tags_association(self):
        """schema.ts must define the three entities incl. the link_tags association table."""
        with open(os.path.join(self.STORE_DIR, "schema.ts")) as f:
            content = f.read().lower()
        # Minimal well-formedness: the association table must be modeled (not just links+tags).
        assert "link_tags" in content or "linktags" in content, (
            "schema.ts must define the link_tags association table"
        )

    # ------------------------------------------------------------------
    # L2 — dynamic behavior via independent native probe
    # ------------------------------------------------------------------

    def test_l2_module_importable_and_factory_returns_store(self):
        """The module must build & import from @/lib/links/tag-store and expose the API."""
        self._ensure_deps()
        result = self._drive(
            '    const s = createTagStore();\n'
            '    expect(typeof s.addLink).toBe("function");\n'
            '    expect(typeof s.addTag).toBe("function");\n'
            '    expect(typeof s.tagLink).toBe("function");\n'
            '    expect(typeof s.untagLink).toBe("function");\n'
            '    expect(typeof s.setLinkTags).toBe("function");\n'
            '    expect(typeof s.getTagsForLink).toBe("function");\n'
            '    expect(typeof s.getLinksForTag).toBe("function");\n'
            '    expect(typeof s.getLinkWithTags).toBe("function");\n'
            '    expect(typeof s.countLinksPerTag).toBe("function");\n'
        )
        self._assert_passed(result, "import/factory")

    def test_l2_add_returns_stored_rows(self):
        """addLink/addTag insert one row and return the stored row with its columns."""
        self._ensure_deps()
        result = self._drive(
            '    const s = createTagStore();\n'
            '    const link = s.addLink({ id: "l1", domain: "dub.sh", key: "a" }) as any;\n'
            '    expect(link.id).toBe("l1");\n'
            '    expect(link.domain).toBe("dub.sh");\n'
            '    expect(link.key).toBe("a");\n'
            '    const tag = s.addTag({ id: "t1", name: "alpha" }) as any;\n'
            '    expect(tag.id).toBe("t1");\n'
            '    expect(tag.name).toBe("alpha");\n'
        )
        self._assert_passed(result, "add-returns-row")

    def test_l2_get_tags_for_link_ordered_by_name(self):
        """getTagsForLink(l1) -> [t1(alpha), t2(beta)] ordered by tag name; l3 with none -> []."""
        self._ensure_deps()
        result = self._drive(
            '    const s = seed();\n'
            '    const names = s.getTagsForLink("l1").map((t:any)=>t.name);\n'
            '    expect(names).toEqual(["alpha", "beta"]);\n'
            '    const ids = s.getTagsForLink("l1").map((t:any)=>t.id);\n'
            '    expect(ids).toEqual(["t1", "t2"]);\n'
            '    expect(s.getTagsForLink("l3")).toEqual([]);\n'
        )
        self._assert_passed(result, "tags-for-link-ordered")

    def test_l2_get_links_for_tag_ordered_by_domain_key(self):
        """getLinksForTag(t2) -> [l1(dub.sh/a), l2(dub.sh/b)] ordered by domain then key."""
        self._ensure_deps()
        result = self._drive(
            '    const s = seed();\n'
            '    const ids = s.getLinksForTag("t2").map((l:any)=>l.id);\n'
            '    expect(ids).toEqual(["l1", "l2"]);\n'
            '    // t1 carries only l1\n'
            '    expect(s.getLinksForTag("t1").map((l:any)=>l.id)).toEqual(["l1"]);\n'
            '    // each returned row exposes the link columns\n'
            '    const first = s.getLinksForTag("t2")[0] as any;\n'
            '    expect(first.domain).toBe("dub.sh");\n'
            '    expect(first.key).toBe("a");\n'
        )
        self._assert_passed(result, "links-for-tag-ordered")

    def test_l2_links_for_tag_ordering_is_real_sort(self):
        """Insertion order must not leak through: domain/key sort applies regardless of add order."""
        self._ensure_deps()
        # Insert links in reverse key order; sorted output must still be ascending by domain,key.
        result = self._drive(
            '    const s = createTagStore();\n'
            '    s.addTag({ id: "t", name: "x" });\n'
            '    s.addLink({ id: "z", domain: "dub.sh", key: "z" });\n'
            '    s.addLink({ id: "m", domain: "dub.sh", key: "m" });\n'
            '    s.addLink({ id: "a", domain: "dub.sh", key: "a" });\n'
            '    s.tagLink("z", "t");\n'
            '    s.tagLink("m", "t");\n'
            '    s.tagLink("a", "t");\n'
            '    const ids = s.getLinksForTag("t").map((l:any)=>l.id);\n'
            '    expect(ids).toEqual(["a", "m", "z"]);\n'
        )
        self._assert_passed(result, "links-for-tag-real-sort")

    def test_l2_taglink_idempotent(self):
        """Calling tagLink(l1,t1) twice leaves exactly one association (no duplicate, no throw)."""
        self._ensure_deps()
        result = self._drive(
            '    const s = createTagStore();\n'
            '    s.addLink({ id: "l1", domain: "dub.sh", key: "a" });\n'
            '    s.addTag({ id: "t1", name: "alpha" });\n'
            '    s.tagLink("l1", "t1");\n'
            '    s.tagLink("l1", "t1");\n'
            '    const tags = s.getTagsForLink("l1");\n'
            '    expect(tags.length).toBe(1);\n'
            '    expect((tags[0] as any).id).toBe("t1");\n'
            '    // and from the tag side too\n'
            '    expect(s.getLinksForTag("t1").map((l:any)=>l.id)).toEqual(["l1"]);\n'
        )
        self._assert_passed(result, "taglink-idempotent")

    def test_l2_untaglink_removes_and_is_noop_when_absent(self):
        """untagLink removes an existing association and is a silent no-op when absent."""
        self._ensure_deps()
        result = self._drive(
            '    const s = seed();\n'
            '    // remove an existing edge\n'
            '    s.untagLink("l1", "t1");\n'
            '    expect(s.getTagsForLink("l1").map((t:any)=>t.id)).toEqual(["t2"]);\n'
            '    // removing again (now absent) must not throw and must not affect other edges\n'
            '    let threw = false;\n'
            '    try { s.untagLink("l1", "t1"); } catch (e) { threw = true; }\n'
            '    expect(threw).toBe(false);\n'
            '    expect(s.getTagsForLink("l1").map((t:any)=>t.id)).toEqual(["t2"]);\n'
            '    // removing a pair that never existed: still a no-op\n'
            '    s.untagLink("l3", "t3");\n'
            '    expect(s.getTagsForLink("l3")).toEqual([]);\n'
        )
        self._assert_passed(result, "untaglink-noop")

    def test_l2_set_link_tags_replaces_set_atomically(self):
        """setLinkTags replaces the entire tag set with exactly the given ids."""
        self._ensure_deps()
        result = self._drive(
            '    const s = seed();\n'
            '    // l1 currently has t1,t2 -> replace with just t2\n'
            '    s.setLinkTags("l1", ["t2"]);\n'
            '    expect(s.getTagsForLink("l1").map((t:any)=>t.id)).toEqual(["t2"]);\n'
            '    // replace with t1,t3 (order in output is by name: alpha,gamma)\n'
            '    s.setLinkTags("l1", ["t3", "t1"]);\n'
            '    expect(s.getTagsForLink("l1").map((t:any)=>t.name)).toEqual(["alpha", "gamma"]);\n'
            '    // empty set clears all tags\n'
            '    s.setLinkTags("l1", []);\n'
            '    expect(s.getTagsForLink("l1")).toEqual([]);\n'
        )
        self._assert_passed(result, "set-link-tags-replace")

    def test_l2_set_link_tags_rolls_back_on_missing_tag(self):
        """setLinkTags with a missing tag id throws and leaves the previous set intact (atomic)."""
        self._ensure_deps()
        result = self._drive(
            '    const s = seed();\n'
            '    // l1 starts with [t1,t2]\n'
            '    expect(s.getTagsForLink("l1").map((t:any)=>t.id)).toEqual(["t1", "t2"]);\n'
            '    let threw = false;\n'
            '    try {\n'
            '      // includes a nonexistent tag id -> whole call must throw & roll back\n'
            '      s.setLinkTags("l1", ["t1", "does-not-exist"]);\n'
            '    } catch (e) { threw = true; }\n'
            '    expect(threw).toBe(true);\n'
            '    // previous set unchanged: still exactly [t1,t2]\n'
            '    expect(s.getTagsForLink("l1").map((t:any)=>t.id)).toEqual(["t1", "t2"]);\n'
        )
        self._assert_passed(result, "set-link-tags-rollback")

    def test_l2_get_link_with_tags_nested_and_unknown_null(self):
        """getLinkWithTags(l1) returns the link with its tags nested; unknown link -> null."""
        self._ensure_deps()
        result = self._drive(
            '    const s = seed();\n'
            '    const withTags: any = s.getLinkWithTags("l1");\n'
            '    expect(withTags).not.toBeNull();\n'
            '    expect(withTags.id).toBe("l1");\n'
            '    expect(withTags.domain).toBe("dub.sh");\n'
            '    expect(withTags.key).toBe("a");\n'
            '    expect(Array.isArray(withTags.tags)).toBe(true);\n'
            '    const tagIds = withTags.tags.map((t:any)=>t.id).sort();\n'
            '    expect(tagIds).toEqual(["t1", "t2"]);\n'
            '    // a link with no tags -> empty nested array, still a row\n'
            '    const lonely: any = s.getLinkWithTags("l3");\n'
            '    expect(lonely).not.toBeNull();\n'
            '    expect(lonely.id).toBe("l3");\n'
            '    expect(lonely.tags).toEqual([]);\n'
            '    // unknown link id -> null\n'
            '    expect(s.getLinkWithTags("nope")).toBeNull();\n'
        )
        self._assert_passed(result, "get-link-with-tags")

    def test_l2_count_links_per_tag_includes_zero(self):
        """countLinksPerTag -> t2:2, t1:1, t3:0 (zero-link tags MUST appear with count 0)."""
        self._ensure_deps()
        result = self._drive(
            '    const s = seed();\n'
            '    const rows = s.countLinksPerTag();\n'
            '    const m: Record<string, number> = {};\n'
            '    const names: Record<string, string> = {};\n'
            '    for (const r of rows as any[]) {\n'
            '      m[r.id] = Number(r.count ?? r.linkCount);\n'
            '      names[r.id] = r.name;\n'
            '    }\n'
            '    expect(m).toEqual({ t1: 1, t2: 2, t3: 0 });\n'
            '    // every tag carries its name as well\n'
            '    expect(names["t1"]).toBe("alpha");\n'
            '    expect(names["t2"]).toBe("beta");\n'
            '    expect(names["t3"]).toBe("gamma");\n'
        )
        self._assert_passed(result, "count-links-per-tag")

    def test_l2_unique_tag_name_rejected(self):
        """addTag with a duplicate name must throw and must not create a duplicate row."""
        self._ensure_deps()
        result = self._drive(
            '    const s = createTagStore();\n'
            '    s.addTag({ id: "t1", name: "dup" });\n'
            '    let threw = false;\n'
            '    try {\n'
            '      s.addTag({ id: "t2", name: "dup" });\n'
            '    } catch (e) { threw = true; }\n'
            '    expect(threw).toBe(true);\n'
            '    // no duplicate row created: exactly one tag exists\n'
            '    const rows = s.countLinksPerTag();\n'
            '    expect(rows.length).toBe(1);\n'
            '    expect((rows[0] as any).id).toBe("t1");\n'
        )
        self._assert_passed(result, "unique-tag-name")

    def test_l2_unknown_ids_return_empty_never_throw(self):
        """Unknown link/tag ids -> [] for list methods and null for getLinkWithTags, never throw."""
        self._ensure_deps()
        result = self._drive(
            '    const s = seed();\n'
            '    let threw = false;\n'
            '    try {\n'
            '      expect(s.getTagsForLink("ghost")).toEqual([]);\n'
            '      expect(s.getLinksForTag("ghost")).toEqual([]);\n'
            '      expect(s.getLinkWithTags("ghost")).toBeNull();\n'
            '    } catch (e) { threw = true; }\n'
            '    expect(threw).toBe(false);\n'
        )
        self._assert_passed(result, "unknown-ids")

    def test_l2_store_isolation_between_instances(self):
        """Two factory-created stores are fully isolated: data in one is invisible to the other."""
        self._ensure_deps()
        result = self._drive(
            '    const a = createTagStore();\n'
            '    const b = createTagStore();\n'
            '    a.addLink({ id: "l1", domain: "dub.sh", key: "a" });\n'
            '    a.addTag({ id: "t1", name: "alpha" });\n'
            '    a.tagLink("l1", "t1");\n'
            '    // b knows nothing of l1 / t1\n'
            '    expect(b.getTagsForLink("l1")).toEqual([]);\n'
            '    expect(b.getLinksForTag("t1")).toEqual([]);\n'
            '    expect(b.getLinkWithTags("l1")).toBeNull();\n'
            '    expect(b.countLinksPerTag()).toEqual([]);\n'
            '    // b can reuse the same name without colliding with a (separate db)\n'
            '    let threw = false;\n'
            '    try { b.addTag({ id: "t1", name: "alpha" }); } catch (e) { threw = true; }\n'
            '    expect(threw).toBe(false);\n'
            '    // a still intact\n'
            '    expect(a.getTagsForLink("l1").map((t:any)=>t.id)).toEqual(["t1"]);\n'
        )
        self._assert_passed(result, "isolation")

    def test_l2_agent_acceptance_suite_passes(self):
        """The acceptance command must pass: pnpm vitest run tests/links/tag-store.test.ts."""
        self._ensure_deps()
        agent_test = os.path.join(self.WEB_DIR, "tests", "links", "tag-store.test.ts")
        assert os.path.isfile(agent_test), "agent tag-store.test.ts missing"
        result = subprocess.run(
            ["pnpm", "vitest", "run", "tests/links/tag-store.test.ts"],
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
