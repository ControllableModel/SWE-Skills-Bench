"""
Test for 'drizzle-orm-patterns' skill (variant ext6) — In-Memory Short-Link Key Registry
with Upsert (dub monorepo, apps/web).

Verifies that the Agent built a self-contained, in-process short-link **key registry**
under apps/web/lib/links/key-registry/ backed by an embedded better-sqlite3 database and
queried through drizzle-orm. The registry must expose a table/index schema (with inferred
row types) and a KeyRegistry API created via a factory:

    createKeyRegistry()  ->  { reserve, upsert, release, resolve, existsBatch, listByDomain }

modeling one entity `link_keys` (id PK; domain, key, destinationUrl, updatedAt) with a
UNIQUE(domain, key) constraint and a supporting index.

Strategy
--------
L1 checks verify the deliverable files exist, are minimally well-formed, that index.ts
re-exports the factory, and that apps/web/package.json declares drizzle-orm.

L2 checks DO NOT trust the agent's own test file. Instead we drop an INDEPENDENT
TypeScript probe spec into apps/web/tests/links/ (vitest's configured test dir),
import the registry from "@/lib/links/key-registry", seed deterministic data and run the
repo's native command:

    cd apps/web && pnpm vitest run tests/links/<probe>.test.ts

asserting on the registry's *real* behavior: duplicate-reserve rejection with no overwrite,
conflict-handling upsert (insert-or-update, never a duplicate), no-op release, indexed
resolve returning null when absent, single-query batch existence (incl. the empty case),
per-domain listing ordered by key ascending, independence of pairs that share only one of
the two components, and registry isolation. A hardcoded / read-then-branch / stubbed
implementation cannot pass these because the probe drives the public API with novel data.
The agent's own suite is also run separately for the acceptance command.
"""

import json
import os
import subprocess

import pytest


class TestDrizzleOrmPatterns:
    """Verify the in-memory short-link key registry built with drizzle-orm + better-sqlite3."""

    REPO_DIR = "/workspace/dub"
    WEB_DIR = os.path.join(REPO_DIR, "apps", "web")
    REG_DIR = os.path.join(WEB_DIR, "lib", "links", "key-registry")
    PROBE_NAME = "zz_keyregistry_probe.test.ts"
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
        Build a probe that imports the registry factory, optionally seeds a deterministic
        dataset, runs the provided TS assertion body inside a single `it(...)`, executes it
        natively, and returns the CompletedProcess. Assertions use vitest `expect`.

        A `seed()` helper is provided that reserves a deterministic set of pairs:
          domain "d.sh": key "a" -> /a, key "b" -> /b, key "c" -> /c
          domain "e.sh": key "a" -> /e-a
        with strictly increasing updatedAt values so ordering is unambiguous.
        """
        probe = (
            'import { describe, it, expect } from "vitest";\n'
            'import {\n'
            '  createKeyRegistry,\n'
            '} from "@/lib/links/key-registry";\n'
            '\n'
            'function seed() {\n'
            '  const r = createKeyRegistry();\n'
            '  r.reserve({ id: "k1", domain: "d.sh", key: "a", destinationUrl: "https://x/a", updatedAt: 1000 });\n'
            '  r.reserve({ id: "k2", domain: "d.sh", key: "b", destinationUrl: "https://x/b", updatedAt: 2000 });\n'
            '  r.reserve({ id: "k3", domain: "d.sh", key: "c", destinationUrl: "https://x/c", updatedAt: 3000 });\n'
            '  r.reserve({ id: "k4", domain: "e.sh", key: "a", destinationUrl: "https://x/e-a", updatedAt: 4000 });\n'
            '  return r;\n'
            '}\n'
            '\n'
            'describe("keyregistry probe", () => {\n'
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

    def test_l1_registry_dir_and_files_exist(self):
        """schema.ts, store.ts and index.ts must exist under lib/links/key-registry/."""
        for fname in ("schema.ts", "store.ts", "index.ts"):
            fpath = os.path.join(self.REG_DIR, fname)
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
        """The agent's vitest suite for the key-registry must exist and be non-empty."""
        fpath = os.path.join(self.WEB_DIR, "tests", "links", "key-registry.test.ts")
        assert os.path.isfile(fpath), "expected tests/links/key-registry.test.ts"
        assert os.path.getsize(fpath) > 0, "key-registry.test.ts is empty"

    def test_l1_index_reexports_factory(self):
        """index.ts must re-export the factory so the module is importable from the package root."""
        with open(os.path.join(self.REG_DIR, "index.ts")) as f:
            content = f.read()
        assert "createKeyRegistry" in content, (
            "index.ts must surface createKeyRegistry"
        )

    def test_l1_schema_declares_unique_domain_key(self):
        """schema.ts must define the link_keys table with a unique constraint/index over domain+key.

        Minimal structural well-formedness only (the binding behavioral check is the L2
        duplicate-reserve rejection). We require that the schema references a unique
        index/constraint and the two component columns, not merely a hand-written interface.
        """
        with open(os.path.join(self.REG_DIR, "schema.ts")) as f:
            content = f.read()
        assert "drizzle-orm" in content, "schema.ts must build the table via drizzle-orm"
        assert "domain" in content and "key" in content, "schema.ts must declare domain & key columns"
        assert ("uniqueIndex" in content) or ("unique(" in content) or ("unique (" in content), (
            "schema.ts must declare a UNIQUE(domain, key) index/constraint"
        )

    # ------------------------------------------------------------------
    # L2 — dynamic behavior via independent native probe
    # ------------------------------------------------------------------

    def test_l2_module_importable_and_factory_returns_registry(self):
        """The module must build & import from @/lib/links/key-registry and expose the API."""
        self._ensure_deps()
        result = self._drive(
            '    const r = createKeyRegistry();\n'
            '    expect(typeof r.reserve).toBe("function");\n'
            '    expect(typeof r.upsert).toBe("function");\n'
            '    expect(typeof r.release).toBe("function");\n'
            '    expect(typeof r.resolve).toBe("function");\n'
            '    expect(typeof r.existsBatch).toBe("function");\n'
            '    expect(typeof r.listByDomain).toBe("function");\n'
        )
        self._assert_passed(result, "import/factory")

    def test_l2_reserve_returns_stored_row(self):
        """reserve(input) inserts and returns the stored row with all fields persisted."""
        self._ensure_deps()
        result = self._drive(
            '    const r = createKeyRegistry();\n'
            '    const row: any = r.reserve({ id: "k1", domain: "d.sh", key: "a", destinationUrl: "https://x/a", updatedAt: 1234 });\n'
            '    expect(row.id).toBe("k1");\n'
            '    expect(row.domain).toBe("d.sh");\n'
            '    expect(row.key).toBe("a");\n'
            '    expect(row.destinationUrl).toBe("https://x/a");\n'
            '    expect(Number(row.updatedAt)).toBe(1234);\n'
            '    // and it is retrievable via the indexed read path\n'
            '    const got: any = r.resolve("d.sh", "a");\n'
            '    expect(got).not.toBeNull();\n'
            '    expect(got.id).toBe("k1");\n'
            '    expect(got.destinationUrl).toBe("https://x/a");\n'
        )
        self._assert_passed(result, "reserve")

    def test_l2_duplicate_reserve_rejected_no_overwrite(self):
        """A second reserve of an existing domain+key throws, leaves one row, keeps original dest."""
        self._ensure_deps()
        result = self._drive(
            '    const r = createKeyRegistry();\n'
            '    r.reserve({ id: "k1", domain: "d.sh", key: "a", destinationUrl: "https://orig", updatedAt: 1 });\n'
            '    let threw = false;\n'
            '    try {\n'
            '      r.reserve({ id: "k2", domain: "d.sh", key: "a", destinationUrl: "https://other", updatedAt: 2 });\n'
            '    } catch (e) { threw = true; }\n'
            '    expect(threw).toBe(true);\n'
            '    // exactly one row under the domain, original destination intact\n'
            '    const all = r.listByDomain("d.sh");\n'
            '    expect(all.length).toBe(1);\n'
            '    const got: any = r.resolve("d.sh", "a");\n'
            '    expect(got.id).toBe("k1");\n'
            '    expect(got.destinationUrl).toBe("https://orig");\n'
        )
        self._assert_passed(result, "duplicate-reserve")

    def test_l2_upsert_inserts_when_free(self):
        """upsert on a free pair creates exactly one row and returns it."""
        self._ensure_deps()
        result = self._drive(
            '    const r = createKeyRegistry();\n'
            '    const row: any = r.upsert({ id: "u1", domain: "d.sh", key: "fresh", destinationUrl: "https://new", updatedAt: 10 });\n'
            '    expect(row.domain).toBe("d.sh");\n'
            '    expect(row.key).toBe("fresh");\n'
            '    expect(row.destinationUrl).toBe("https://new");\n'
            '    const all = r.listByDomain("d.sh");\n'
            '    expect(all.length).toBe(1);\n'
            '    expect((r.resolve("d.sh", "fresh") as any).destinationUrl).toBe("https://new");\n'
        )
        self._assert_passed(result, "upsert-insert")

    def test_l2_upsert_updates_existing_in_place(self):
        """upsert on an existing pair updates destinationUrl/updatedAt in place, never duplicates."""
        self._ensure_deps()
        result = self._drive(
            '    const r = createKeyRegistry();\n'
            '    r.reserve({ id: "k1", domain: "d.sh", key: "a", destinationUrl: "https://v1", updatedAt: 100 });\n'
            '    const row: any = r.upsert({ id: "ignored", domain: "d.sh", key: "a", destinationUrl: "https://v2", updatedAt: 200 });\n'
            '    expect(row.domain).toBe("d.sh");\n'
            '    expect(row.key).toBe("a");\n'
            '    expect(row.destinationUrl).toBe("https://v2");\n'
            '    expect(Number(row.updatedAt)).toBe(200);\n'
            '    // still exactly one row for the pair\n'
            '    const all = r.listByDomain("d.sh");\n'
            '    expect(all.length).toBe(1);\n'
            '    const got: any = r.resolve("d.sh", "a");\n'
            '    expect(got.destinationUrl).toBe("https://v2");\n'
            '    expect(Number(got.updatedAt)).toBe(200);\n'
        )
        self._assert_passed(result, "upsert-update")

    def test_l2_release_deletes_and_is_noop_when_absent(self):
        """release removes an existing pair; releasing a missing pair is a silent no-op."""
        self._ensure_deps()
        result = self._drive(
            '    const r = createKeyRegistry();\n'
            '    r.reserve({ id: "k1", domain: "d.sh", key: "a", destinationUrl: "https://a", updatedAt: 1 });\n'
            '    // releasing an absent pair must not throw and must change nothing\n'
            '    expect(() => r.release("d.sh", "missing")).not.toThrow();\n'
            '    expect(r.resolve("d.sh", "a")).not.toBeNull();\n'
            '    // now release the existing pair\n'
            '    r.release("d.sh", "a");\n'
            '    expect(r.resolve("d.sh", "a")).toBeNull();\n'
            '    expect(r.listByDomain("d.sh").length).toBe(0);\n'
            '    // releasing again is still a no-op\n'
            '    expect(() => r.release("d.sh", "a")).not.toThrow();\n'
        )
        self._assert_passed(result, "release")

    def test_l2_resolve_returns_null_when_absent(self):
        """resolve returns the row for a known pair and null for an unknown key/domain."""
        self._ensure_deps()
        result = self._drive(
            '    const r = seed();\n'
            '    const hit: any = r.resolve("d.sh", "a");\n'
            '    expect(hit).not.toBeNull();\n'
            '    expect(hit.id).toBe("k1");\n'
            '    expect(r.resolve("d.sh", "missing")).toBeNull();\n'
            '    expect(r.resolve("nope.sh", "a")).toBeNull();\n'
        )
        self._assert_passed(result, "resolve-null")

    def test_l2_pair_independence_shared_component(self):
        """Pairs sharing only domain (or only key) are independent and coexist."""
        self._ensure_deps()
        result = self._drive(
            '    const r = createKeyRegistry();\n'
            '    r.reserve({ id: "p1", domain: "d.sh", key: "a", destinationUrl: "https://da", updatedAt: 1 });\n'
            '    // same domain, different key -> allowed\n'
            '    r.reserve({ id: "p2", domain: "d.sh", key: "b", destinationUrl: "https://db", updatedAt: 2 });\n'
            '    // same key, different domain -> allowed\n'
            '    r.reserve({ id: "p3", domain: "e.sh", key: "a", destinationUrl: "https://ea", updatedAt: 3 });\n'
            '    expect((r.resolve("d.sh", "a") as any).id).toBe("p1");\n'
            '    expect((r.resolve("d.sh", "b") as any).id).toBe("p2");\n'
            '    expect((r.resolve("e.sh", "a") as any).id).toBe("p3");\n'
            '    expect(r.listByDomain("d.sh").length).toBe(2);\n'
            '    expect(r.listByDomain("e.sh").length).toBe(1);\n'
        )
        self._assert_passed(result, "pair-independence")

    def test_l2_list_by_domain_ordered_by_key(self):
        """listByDomain returns only that domain's rows, ordered by key ascending."""
        self._ensure_deps()
        result = self._drive(
            '    const r = createKeyRegistry();\n'
            '    // insert out of key order to prove the query sorts (not insertion order)\n'
            '    r.reserve({ id: "x", domain: "d.sh", key: "ccc", destinationUrl: "https://c", updatedAt: 1 });\n'
            '    r.reserve({ id: "y", domain: "d.sh", key: "aaa", destinationUrl: "https://a", updatedAt: 2 });\n'
            '    r.reserve({ id: "z", domain: "d.sh", key: "bbb", destinationUrl: "https://b", updatedAt: 3 });\n'
            '    r.reserve({ id: "o", domain: "e.sh", key: "aaa", destinationUrl: "https://e", updatedAt: 4 });\n'
            '    const keys = r.listByDomain("d.sh").map((row:any)=>row.key);\n'
            '    expect(keys).toEqual(["aaa", "bbb", "ccc"]);\n'
            '    // and it does not leak the other domain\n'
            '    const ids = r.listByDomain("d.sh").map((row:any)=>row.id);\n'
            '    expect(ids).not.toContain("o");\n'
            '    expect(r.listByDomain("absent.sh")).toEqual([]);\n'
        )
        self._assert_passed(result, "list-by-domain")

    def test_l2_exists_batch_subset_and_empty(self):
        """existsBatch returns only the reserved pairs; empty input -> empty result."""
        self._ensure_deps()
        result = self._drive(
            '    const r = seed();\n'
            '    // empty input -> empty output\n'
            '    expect(r.existsBatch([])).toEqual([]);\n'
            '    const present = r.existsBatch([\n'
            '      { domain: "d.sh", key: "a" },   // reserved\n'
            '      { domain: "d.sh", key: "zzz" }, // free\n'
            '      { domain: "d.sh", key: "c" },   // reserved\n'
            '      { domain: "e.sh", key: "a" },   // reserved (different domain)\n'
            '      { domain: "e.sh", key: "b" },   // free\n'
            '    ]);\n'
            '    const norm = (present as any[]).map((p)=>`${p.domain}|${p.key}`).sort();\n'
            '    expect(norm).toEqual(["d.sh|a", "d.sh|c", "e.sh|a"]);\n'
            '    // a pair sharing only domain with a reserved one is NOT reported\n'
            '    const partial = r.existsBatch([{ domain: "d.sh", key: "b-not" }, { domain: "x.sh", key: "a" }]);\n'
            '    expect(partial).toEqual([]);\n'
        )
        self._assert_passed(result, "exists-batch")

    def test_l2_registry_isolation_between_instances(self):
        """Two factory-created registries are fully isolated."""
        self._ensure_deps()
        result = self._drive(
            '    const a = createKeyRegistry();\n'
            '    const b = createKeyRegistry();\n'
            '    a.reserve({ id: "k", domain: "d.sh", key: "a", destinationUrl: "https://a", updatedAt: 1 });\n'
            '    // b sees nothing\n'
            '    expect(b.resolve("d.sh", "a")).toBeNull();\n'
            '    expect(b.listByDomain("d.sh")).toEqual([]);\n'
            '    expect(b.existsBatch([{ domain: "d.sh", key: "a" }])).toEqual([]);\n'
            '    // b can reserve the same pair independently without clashing with a\n'
            '    expect(() => b.reserve({ id: "k2", domain: "d.sh", key: "a", destinationUrl: "https://b", updatedAt: 2 })).not.toThrow();\n'
            '    expect((a.resolve("d.sh", "a") as any).destinationUrl).toBe("https://a");\n'
            '    expect((b.resolve("d.sh", "a") as any).destinationUrl).toBe("https://b");\n'
        )
        self._assert_passed(result, "isolation")

    def test_l2_upsert_does_not_touch_other_pairs(self):
        """An upsert on one pair must not alter sibling pairs in the same domain."""
        self._ensure_deps()
        result = self._drive(
            '    const r = seed();\n'
            '    // sanity: sibling exists with its original destination\n'
            '    expect((r.resolve("d.sh", "b") as any).destinationUrl).toBe("https://x/b");\n'
            '    r.upsert({ id: "n", domain: "d.sh", key: "a", destinationUrl: "https://updated-a", updatedAt: 9999 });\n'
            '    // target updated\n'
            '    expect((r.resolve("d.sh", "a") as any).destinationUrl).toBe("https://updated-a");\n'
            '    // siblings untouched\n'
            '    expect((r.resolve("d.sh", "b") as any).destinationUrl).toBe("https://x/b");\n'
            '    expect((r.resolve("d.sh", "c") as any).destinationUrl).toBe("https://x/c");\n'
            '    expect((r.resolve("e.sh", "a") as any).destinationUrl).toBe("https://x/e-a");\n'
            '    // total row count unchanged (still 4)\n'
            '    expect(r.listByDomain("d.sh").length).toBe(3);\n'
            '    expect(r.listByDomain("e.sh").length).toBe(1);\n'
        )
        self._assert_passed(result, "upsert-isolation")

    def test_l2_agent_acceptance_suite_passes(self):
        """The acceptance command must pass: pnpm vitest run tests/links/key-registry.test.ts."""
        self._ensure_deps()
        agent_test = os.path.join(self.WEB_DIR, "tests", "links", "key-registry.test.ts")
        assert os.path.isfile(agent_test), "agent key-registry.test.ts missing"
        result = subprocess.run(
            ["pnpm", "vitest", "run", "tests/links/key-registry.test.ts"],
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
