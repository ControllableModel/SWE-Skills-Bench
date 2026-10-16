"""
Test for 'prisma-schema-patterns' skill (variant ext8) — provider-capability lookup.

The variant task asks the agent to add a pure capability-lookup module
`packages/prisma/provider-capabilities.ts` exporting
`getProviderCapabilities(provider: string)`, plus a Vitest unit test
`packages/prisma/provider-capabilities.test.ts`.

`getProviderCapabilities` returns a plain object with the boolean fields
`supportsEnums`, `supportsScalarLists`, `usesSqlDriverAdapter`,
`requiresDirectUrl`, consistent with this provider table:

    postgresql  -> enums Y, scalarLists Y, sqlAdapter Y, directUrl Y
    cockroachdb -> enums Y, scalarLists Y, sqlAdapter Y, directUrl Y
    mysql       -> enums Y, scalarLists N, sqlAdapter Y, directUrl N
    sqlite      -> enums N, scalarLists N, sqlAdapter Y, directUrl N
    sqlserver   -> enums N, scalarLists N, sqlAdapter Y, directUrl N
    mongodb     -> enums Y, scalarLists Y, sqlAdapter N, directUrl N

Matching is case-insensitive; an unrecognized/empty provider throws an Error
naming the provider; results are fresh per call and deep-equal for equal inputs;
the module must be pure (no I/O, no env reads) and must not import the generated
prisma client / adapter / pg.

Verification strategy: rather than trusting the agent's own test file, this
grader writes its OWN Vitest spec into the prisma package that imports the
agent's `getProviderCapabilities` and asserts every cell of the table plus the
edge cases via the repo's native `yarn vitest run` toolchain.

L1 -> deliverable files exist + minimally well-formed + purity import guard.
L2 -> dynamic execution against the real lookup behaviour.
"""

import os
import re
import subprocess

import pytest

REPO_DIR = "/workspace/cal.com"
PRISMA_DIR = os.path.join(REPO_DIR, "packages", "prisma")
CAPS_TS = os.path.join(PRISMA_DIR, "provider-capabilities.ts")
CAPS_TEST_TS = os.path.join(PRISMA_DIR, "provider-capabilities.test.ts")

# A vitest spec we (the grader) own. It imports the agent's lookup from the
# sibling module and asserts the required behaviour. We control its contents so
# a naive / hardcoded lookup cannot pass by editing the agent-authored test.
VERIFY_SPEC_NAME = "provider-capabilities.benchverify.test.ts"
VERIFY_SPEC_PATH = os.path.join(PRISMA_DIR, VERIFY_SPEC_NAME)


def _run_vitest(spec_filename, timeout=600):
    """Run a single vitest spec scoped to the prisma package; return CompletedProcess."""
    rel = os.path.join("packages", "prisma", spec_filename)
    env = dict(os.environ)
    env["TZ"] = "UTC"
    env["CI"] = "true"
    env.pop("PYTHONPATH", None)
    cmd = ["yarn", "vitest", "run", rel]
    return subprocess.run(
        cmd,
        cwd=REPO_DIR,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )


class TestPrismaSchemaPatterns:
    """Verify the Prisma provider-capability lookup deliverable."""

    REPO_DIR = "/workspace/cal.com"

    # ------------------------------------------------------------------ #
    # Module / spec lifecycle
    # ------------------------------------------------------------------ #
    @classmethod
    def setup_class(cls):
        """Install our own verification vitest spec into the prisma package."""
        cls._spec_written = False
        if os.path.isdir(PRISMA_DIR) and os.path.isfile(CAPS_TS):
            with open(VERIFY_SPEC_PATH, "w") as fh:
                fh.write(cls._verify_spec_source())
            cls._spec_written = True
        cls._vitest_cache = {}

    @classmethod
    def teardown_class(cls):
        """Remove our verification spec so we don't pollute the repo."""
        if getattr(cls, "_spec_written", False):
            try:
                os.remove(VERIFY_SPEC_PATH)
            except OSError:
                pass

    @staticmethod
    def _verify_spec_source():
        return r"""
import { describe, it, expect } from "vitest";
// Import the agent-authored lookup. Importing this file alone must not pull in
// the generated prisma client / driver adapter / pg (purity contract).
import { getProviderCapabilities } from "./provider-capabilities";

// Canonical expected table from the requirement doc.
const TABLE: Record<
  string,
  {
    supportsEnums: boolean;
    supportsScalarLists: boolean;
    usesSqlDriverAdapter: boolean;
    requiresDirectUrl: boolean;
  }
> = {
  postgresql: { supportsEnums: true, supportsScalarLists: true, usesSqlDriverAdapter: true, requiresDirectUrl: true },
  cockroachdb: { supportsEnums: true, supportsScalarLists: true, usesSqlDriverAdapter: true, requiresDirectUrl: true },
  mysql: { supportsEnums: true, supportsScalarLists: false, usesSqlDriverAdapter: true, requiresDirectUrl: false },
  sqlite: { supportsEnums: false, supportsScalarLists: false, usesSqlDriverAdapter: true, requiresDirectUrl: false },
  sqlserver: { supportsEnums: false, supportsScalarLists: false, usesSqlDriverAdapter: true, requiresDirectUrl: false },
  mongodb: { supportsEnums: true, supportsScalarLists: true, usesSqlDriverAdapter: false, requiresDirectUrl: false },
};

function check(provider: string) {
  const exp = TABLE[provider];
  const got = getProviderCapabilities(provider);
  expect(got.supportsEnums).toBe(exp.supportsEnums);
  expect(got.supportsScalarLists).toBe(exp.supportsScalarLists);
  expect(got.usesSqlDriverAdapter).toBe(exp.usesSqlDriverAdapter);
  expect(got.requiresDirectUrl).toBe(exp.requiresDirectUrl);
}

describe("benchverify getProviderCapabilities", () => {
  it("[T01] postgresql capability set", () => {
    check("postgresql");
  });

  it("[T02] cockroachdb capability set", () => {
    check("cockroachdb");
  });

  it("[T03] mysql capability set (no scalar lists, no direct url)", () => {
    check("mysql");
    const c = getProviderCapabilities("mysql");
    expect(c.supportsScalarLists).toBe(false);
    expect(c.requiresDirectUrl).toBe(false);
  });

  it("[T04] sqlite capability set; supportsEnums === false", () => {
    check("sqlite");
    expect(getProviderCapabilities("sqlite").supportsEnums).toBe(false);
  });

  it("[T05] sqlserver capability set; supportsEnums === false", () => {
    check("sqlserver");
    expect(getProviderCapabilities("sqlserver").supportsEnums).toBe(false);
  });

  it("[T06] mongodb capability set; usesSqlDriverAdapter === false", () => {
    check("mongodb");
    const c = getProviderCapabilities("mongodb");
    expect(c.usesSqlDriverAdapter).toBe(false);
    // MongoDB still supports enums + scalar lists per the table.
    expect(c.supportsEnums).toBe(true);
    expect(c.supportsScalarLists).toBe(true);
  });

  it("[T07] returns the four boolean fields and nothing non-boolean for them", () => {
    const c = getProviderCapabilities("postgresql");
    for (const k of [
      "supportsEnums",
      "supportsScalarLists",
      "usesSqlDriverAdapter",
      "requiresDirectUrl",
    ]) {
      expect(typeof (c as any)[k]).toBe("boolean");
    }
  });

  it("[T08] case-insensitive lookup matches canonical lower-case", () => {
    for (const variant of ["PostgreSQL", "POSTGRESQL", "PoStGrEsQl"]) {
      expect(getProviderCapabilities(variant)).toEqual(getProviderCapabilities("postgresql"));
    }
    expect(getProviderCapabilities("MongoDB")).toEqual(getProviderCapabilities("mongodb"));
    expect(getProviderCapabilities("SQLite")).toEqual(getProviderCapabilities("sqlite"));
  });

  it("[T09] unknown provider throws an Error naming the provider", () => {
    let msg = "";
    let threw = false;
    try {
      getProviderCapabilities("oracle");
    } catch (e: any) {
      threw = true;
      msg = String(e && e.message);
    }
    expect(threw).toBe(true);
    expect(msg.length).toBeGreaterThan(0);
    expect(msg.toLowerCase()).toContain("oracle");
  });

  it("[T10] empty / whitespace / nonsense providers throw", () => {
    expect(() => getProviderCapabilities("")).toThrow();
    expect(() => getProviderCapabilities("   ")).toThrow();
    expect(() => getProviderCapabilities("not-a-db")).toThrow();
  });

  it("[T11] results are fresh objects per call; mutation does not leak", () => {
    const a = getProviderCapabilities("postgresql");
    const b = getProviderCapabilities("postgresql");
    // Distinct object identities.
    expect(a).not.toBe(b);
    // Deep-equal for equal inputs.
    expect(a).toEqual(b);
    // Mutating one must not affect a freshly fetched result.
    (a as any).supportsEnums = false;
    (a as any).injected = 123;
    const c = getProviderCapabilities("postgresql");
    expect(c.supportsEnums).toBe(true);
    expect((c as any).injected).toBeUndefined();
  });

  it("[T12] purity: equal inputs -> deep-equal outputs; process.env untouched", () => {
    const before = JSON.stringify(process.env);
    const r1 = getProviderCapabilities("mongodb");
    const r2 = getProviderCapabilities("mongodb");
    const after = JSON.stringify(process.env);
    expect(r2).toEqual(r1);
    expect(after).toBe(before);
  });

  it("[T13] full-table consistency across every canonical provider", () => {
    for (const provider of Object.keys(TABLE)) {
      check(provider);
    }
  });

  it("[T14] not every provider is identical (lookup actually discriminates)", () => {
    // A stub returning a constant object for all inputs must fail here.
    const pg = getProviderCapabilities("postgresql");
    const sqlite = getProviderCapabilities("sqlite");
    const mongo = getProviderCapabilities("mongodb");
    expect(pg).not.toEqual(sqlite);
    expect(pg).not.toEqual(mongo);
    expect(sqlite).not.toEqual(mongo);
  });
});
"""

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _vitest_verify(self):
        """Run the grader-owned spec once; cache the CompletedProcess."""
        if "verify" not in self._vitest_cache:
            assert getattr(type(self), "_spec_written", False), (
                "Verification spec was not written — provider-capabilities.ts is "
                "missing, so the lookup deliverable does not exist."
            )
            self._vitest_cache["verify"] = _run_vitest(VERIFY_SPEC_NAME)
        return self._vitest_cache["verify"]

    def _require_vitest_passed(self):
        proc = self._vitest_verify()
        combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
        assert proc.returncode == 0, (
            "grader vitest spec failed (rc=%s).\n--- stdout ---\n%s\n--- stderr ---\n%s"
            % (proc.returncode, (proc.stdout or "")[-4000:], (proc.stderr or "")[-4000:])
        )
        return combined

    # ------------------------------------------------------------------ #
    # L1 — deliverable files exist and are minimally well-formed
    # ------------------------------------------------------------------ #
    def test_l1_repo_present(self):
        """The prisma package directory must exist in the container."""
        assert os.path.isdir(PRISMA_DIR), f"{PRISMA_DIR} not found"

    def test_l1_capabilities_module_exists(self):
        """packages/prisma/provider-capabilities.ts must be created and non-empty."""
        assert os.path.isfile(CAPS_TS), "provider-capabilities.ts not found"
        assert os.path.getsize(CAPS_TS) > 0, "provider-capabilities.ts is empty"

    def test_l1_exports_lookup_symbol(self):
        """provider-capabilities.ts must export a `getProviderCapabilities` function."""
        with open(CAPS_TS) as fh:
            src = fh.read()
        assert "getProviderCapabilities" in src, "getProviderCapabilities not referenced"
        assert re.search(
            r"export\s+(async\s+)?function\s+getProviderCapabilities|"
            r"export\s+const\s+getProviderCapabilities\s*=|"
            r"export\s*\{[^}]*\bgetProviderCapabilities\b",
            src,
        ), "getProviderCapabilities is not exported from provider-capabilities.ts"

    def test_l1_module_is_self_contained(self):
        """Lookup must not import the generated client, the pg-adapter, or pg.

        Structural guard for the purity / self-containment contract; the
        behavioural purity is exercised in L2.
        """
        with open(CAPS_TS) as fh:
            src = fh.read()
        forbidden = [
            r"""from\s+['"]pg['"]""",
            r"""from\s+['"]@prisma/adapter-pg['"]""",
            r"""from\s+['"]\.?/?generated/prisma""",
            r"""from\s+['"]\./generated""",
            r"""from\s+['"]\.\/client['"]""",
            r"""from\s+['"]@prisma/client['"]""",
        ]
        for pat in forbidden:
            assert not re.search(pat, src), (
                f"provider-capabilities.ts must not import {pat!r}; it must be a pure module"
            )

    def test_l1_agent_test_exists(self):
        """packages/prisma/provider-capabilities.test.ts must be created by the agent."""
        assert os.path.isfile(CAPS_TEST_TS), "provider-capabilities.test.ts not found"
        assert os.path.getsize(CAPS_TEST_TS) > 0, "provider-capabilities.test.ts is empty"

    # ------------------------------------------------------------------ #
    # L2 — dynamic execution of the real lookup via native vitest
    # ------------------------------------------------------------------ #
    def test_l2_vitest_suite_passes_overall(self):
        """The grader-owned vitest spec for the lookup passes end-to-end."""
        combined = self._require_vitest_passed()
        assert "benchverify" in combined or "passed" in combined.lower(), (
            "vitest output does not reference the grader spec; suite may not have run"
        )

    def test_l2_sql_providers_capability_sets(self):
        """[T01][T02][T03] postgresql / cockroachdb / mysql capability rows hold."""
        out = self._require_vitest_passed()
        assert "T01" in out and "T02" in out and "T03" in out, "SQL provider rows did not run"

    def test_l2_sqlite_sqlserver_no_enums(self):
        """[T04][T05] sqlite & sqlserver have supportsEnums === false."""
        out = self._require_vitest_passed()
        assert "T04" in out and "T05" in out, "sqlite/sqlserver enum cases did not run"

    def test_l2_mongodb_no_sql_adapter(self):
        """[T06] mongodb usesSqlDriverAdapter === false but still supports enums/lists."""
        out = self._require_vitest_passed()
        assert "T06" in out, "mongodb no-SQL-adapter case did not run"

    def test_l2_all_fields_boolean(self):
        """[T07] the four capability fields are present and boolean-typed."""
        out = self._require_vitest_passed()
        assert "T07" in out, "field-type case did not run"

    def test_l2_case_insensitive_lookup(self):
        """[T08] mixed-case provider strings resolve to the canonical row."""
        out = self._require_vitest_passed()
        assert "T08" in out, "case-insensitivity case did not run"

    def test_l2_unknown_and_empty_throw(self):
        """[T09][T10] unknown / empty / whitespace providers throw a naming Error."""
        out = self._require_vitest_passed()
        assert "T09" in out and "T10" in out, "unknown/empty throw cases did not run"

    def test_l2_fresh_objects_and_purity(self):
        """[T11][T12] fresh object per call, mutation isolation, env untouched."""
        out = self._require_vitest_passed()
        assert "T11" in out and "T12" in out, "freshness/purity cases did not run"

    def test_l2_full_table_and_discrimination(self):
        """[T13][T14] full-table consistency + provider rows actually differ."""
        out = self._require_vitest_passed()
        assert "T13" in out and "T14" in out, "full-table/discrimination cases did not run"

    def test_l2_naive_lookup_would_fail(self):
        """Meta-guard: the spec encodes 14 discriminative cases beyond existence.

        A hardcoded lookup (constant object for all inputs, or one that never
        throws, or that returns shared mutable singletons) cannot satisfy the
        per-provider table + throw + freshness assertions, so a green vitest
        run is meaningful. We assert all 14 tagged cases executed.
        """
        out = self._require_vitest_passed()
        ran = {t for t in re.findall(r"T\d{2}", out)}
        expected = {f"T{i:02d}" for i in range(1, 15)}
        missing = expected - ran
        assert not missing, f"these lookup cases did not appear in vitest output: {sorted(missing)}"
