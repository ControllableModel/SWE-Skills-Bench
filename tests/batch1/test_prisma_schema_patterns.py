"""
Test for 'prisma-schema-patterns' skill — Prisma connection-config resolver.

The task asks the agent to introduce a pure, self-contained resolver module
`packages/prisma/connection-config.ts` exporting `resolveConnectionConfig(env)`,
add a Vitest unit test, and refactor `packages/prisma/index.ts` to consume it
while preserving runtime behaviour.

These tests verify the deliverable independently of the agent's own test file:
they write a focused Vitest spec into the prisma package that imports the
agent's `resolveConnectionConfig` and exercise every resolution / pooling /
fallback / validation / purity rule from the requirement doc via the repo's
native `yarn vitest run` toolchain.

L1 -> file existence + basic well-formedness.
L2 -> dynamic execution against the real resolver behaviour.
"""

import os
import re
import subprocess

import pytest

REPO_DIR = "/workspace/cal.com"
PRISMA_DIR = os.path.join(REPO_DIR, "packages", "prisma")
CONFIG_TS = os.path.join(PRISMA_DIR, "connection-config.ts")
CONFIG_TEST_TS = os.path.join(PRISMA_DIR, "connection-config.test.ts")
INDEX_TS = os.path.join(PRISMA_DIR, "index.ts")

# A vitest spec we (the grader) own. It imports the agent's resolver from the
# sibling module and asserts the required behaviour. We control its contents so
# a naive / hardcoded resolver cannot pass by editing the agent-authored test.
VERIFY_SPEC_NAME = "connection-config.benchverify.test.ts"
VERIFY_SPEC_PATH = os.path.join(PRISMA_DIR, VERIFY_SPEC_NAME)

PG_URL = "postgresql://u:p@localhost:5432/main"
PG_URL2 = "postgres://u:p@db-direct:5432/direct"
PG_URL3 = "postgresql://u:p@replica:5432/ro"


def _run_vitest(spec_filename, timeout=600):
    """Run a single vitest spec scoped to the prisma package; return CompletedProcess."""
    rel = os.path.join("packages", "prisma", spec_filename)
    env = dict(os.environ)
    env["TZ"] = "UTC"
    env.pop("PYTHONPATH", None)
    # Avoid yarn's interactive / network prompts where possible.
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
    """Verify the Prisma connection-config resolver deliverable."""

    REPO_DIR = "/workspace/cal.com"

    # ------------------------------------------------------------------ #
    # Module / spec lifecycle
    # ------------------------------------------------------------------ #
    @classmethod
    def setup_class(cls):
        """Install our own verification vitest spec into the prisma package."""
        cls._spec_written = False
        if os.path.isdir(PRISMA_DIR) and os.path.isfile(CONFIG_TS):
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
// Import the agent-authored resolver. Importing this file alone must not pull
// in the generated prisma client / driver adapter / pg (purity contract).
import { resolveConnectionConfig } from "./connection-config";

const PG = "postgresql://u:p@localhost:5432/main";
const PG_DIRECT = "postgres://u:p@db-direct:5432/direct";
const PG_RO = "postgresql://u:p@replica:5432/ro";

describe("benchverify resolveConnectionConfig", () => {
  it("[T01] DATABASE_URL set, USE_POOL unset -> primary resolved, pooling disabled, fallbacks equal primary", () => {
    const c = resolveConnectionConfig({ DATABASE_URL: PG });
    expect(c.connectionString).toBe(PG);
    expect(c.pooling.enabled).toBe(false);
    expect(c.directConnectionString).toBe(PG);
    expect(c.readonlyConnectionString).toBe(PG);
  });

  it("[T02] USE_POOL='1' -> pooling enabled with numeric max + idle timeout", () => {
    const c = resolveConnectionConfig({ DATABASE_URL: PG, USE_POOL: "1" });
    expect(c.pooling.enabled).toBe(true);
    const maxKey = "max" in c.pooling ? "max" : Object.keys(c.pooling).find((k) => /max/i.test(k));
    const idleKey = Object.keys(c.pooling).find((k) => /idle/i.test(k));
    expect(maxKey).toBeTruthy();
    expect(idleKey).toBeTruthy();
    const maxVal = (c.pooling as any)[maxKey as string];
    const idleVal = (c.pooling as any)[idleKey as string];
    expect(typeof maxVal).toBe("number");
    expect(typeof idleVal).toBe("number");
    expect(maxVal).toBeGreaterThan(0);
    expect(idleVal).toBeGreaterThan(0);
  });

  it("[T03] USE_POOL='true' -> pooling enabled", () => {
    expect(resolveConnectionConfig({ DATABASE_URL: PG, USE_POOL: "true" }).pooling.enabled).toBe(true);
  });

  it("[T04] USE_POOL='false' / '0' / '' / unrelated / ' true ' -> pooling disabled", () => {
    for (const v of ["false", "0", "", "yes", "TRUE", " true ", " 1 "]) {
      const c = resolveConnectionConfig({ DATABASE_URL: PG, USE_POOL: v });
      expect(c.pooling.enabled).toBe(false);
    }
  });

  it("[T05] absent DATABASE_URL -> throws naming the primary url", () => {
    expect(() => resolveConnectionConfig({})).toThrow();
    let msg = "";
    try {
      resolveConnectionConfig({});
    } catch (e: any) {
      msg = String(e && e.message);
    }
    expect(msg.length).toBeGreaterThan(0);
    expect(/database_url|database url|primary/i.test(msg)).toBe(true);
  });

  it("[T06] empty / whitespace-only DATABASE_URL -> throws (treated as missing)", () => {
    expect(() => resolveConnectionConfig({ DATABASE_URL: "" })).toThrow();
    expect(() => resolveConnectionConfig({ DATABASE_URL: "   " })).toThrow();
  });

  it("[T07] DATABASE_DIRECT_URL override -> direct differs, readonly still falls back", () => {
    const c = resolveConnectionConfig({ DATABASE_URL: PG, DATABASE_DIRECT_URL: PG_DIRECT });
    expect(c.directConnectionString).toBe(PG_DIRECT);
    expect(c.directConnectionString).not.toBe(c.connectionString);
    expect(c.readonlyConnectionString).toBe(PG);
  });

  it("[T08] empty/whitespace DATABASE_DIRECT_URL -> falls back to primary", () => {
    for (const v of ["", "   "]) {
      const c = resolveConnectionConfig({ DATABASE_URL: PG, DATABASE_DIRECT_URL: v });
      expect(c.directConnectionString).toBe(PG);
    }
  });

  it("[T09] INSIGHTS_DATABASE_URL override -> readonly differs, direct still falls back", () => {
    const c = resolveConnectionConfig({ DATABASE_URL: PG, INSIGHTS_DATABASE_URL: PG_RO });
    expect(c.readonlyConnectionString).toBe(PG_RO);
    expect(c.readonlyConnectionString).not.toBe(c.connectionString);
    expect(c.directConnectionString).toBe(PG);
  });

  it("[T10] empty/whitespace INSIGHTS_DATABASE_URL -> falls back to primary", () => {
    for (const v of ["", "   "]) {
      const c = resolveConnectionConfig({ DATABASE_URL: PG, INSIGHTS_DATABASE_URL: v });
      expect(c.readonlyConnectionString).toBe(PG);
    }
  });

  it("[T11] wrong-scheme primary DATABASE_URL -> throws naming the invalid url", () => {
    let msg = "";
    try {
      resolveConnectionConfig({ DATABASE_URL: "mysql://u:p@localhost:3306/db" });
    } catch (e: any) {
      msg = String(e && e.message);
    }
    expect(msg.length).toBeGreaterThan(0);
    expect(/database_url|url|scheme|postgres/i.test(msg)).toBe(true);
  });

  it("[T12] wrong-scheme direct/readonly URLs -> throw", () => {
    expect(() =>
      resolveConnectionConfig({ DATABASE_URL: PG, DATABASE_DIRECT_URL: "mysql://x/y" })
    ).toThrow();
    expect(() =>
      resolveConnectionConfig({ DATABASE_URL: PG, INSIGHTS_DATABASE_URL: "http://x/y" })
    ).toThrow();
  });

  it("[T13] both postgres:// and postgresql:// schemes accepted", () => {
    const a = resolveConnectionConfig({ DATABASE_URL: "postgres://u:p@h:5432/d" });
    const b = resolveConnectionConfig({ DATABASE_URL: "postgresql://u:p@h:5432/d" });
    expect(a.connectionString).toBe("postgres://u:p@h:5432/d");
    expect(b.connectionString).toBe("postgresql://u:p@h:5432/d");
  });

  it("[T14] purity: equal inputs -> deep-equal outputs, process.env untouched", () => {
    const input = { DATABASE_URL: PG, USE_POOL: "1", DATABASE_DIRECT_URL: PG_DIRECT };
    const before = JSON.stringify(process.env);
    const r1 = resolveConnectionConfig({ ...input });
    const r2 = resolveConnectionConfig({ ...input });
    const after = JSON.stringify(process.env);
    expect(r2).toEqual(r1);
    expect(after).toBe(before);
  });

  it("[T15] purity: resolver ignores ambient process.env", () => {
    const saved = process.env.DATABASE_URL;
    process.env.DATABASE_URL = "postgresql://AMBIENT:p@h:5432/ambient";
    try {
      const c = resolveConnectionConfig({ DATABASE_URL: PG });
      expect(c.connectionString).toBe(PG);
    } finally {
      if (saved === undefined) delete process.env.DATABASE_URL;
      else process.env.DATABASE_URL = saved;
    }
  });

  it("[T16] full combined config resolves all four fields independently", () => {
    const c = resolveConnectionConfig({
      DATABASE_URL: PG,
      DATABASE_DIRECT_URL: PG_DIRECT,
      INSIGHTS_DATABASE_URL: PG_RO,
      USE_POOL: "true",
    });
    expect(c.connectionString).toBe(PG);
    expect(c.directConnectionString).toBe(PG_DIRECT);
    expect(c.readonlyConnectionString).toBe(PG_RO);
    expect(c.pooling.enabled).toBe(true);
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
                "Verification spec was not written — connection-config.ts is "
                "missing, so the resolver deliverable does not exist."
            )
            self._vitest_cache["verify"] = _run_vitest(VERIFY_SPEC_NAME)
        return self._vitest_cache["verify"]

    def _require_vitest_passed(self):
        proc = self._vitest_verify()
        combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
        assert proc.returncode == 0, (
            "grader vitest spec failed (rc=%s).\n--- stdout ---\n%s\n--- stderr ---\n%s"
            % (proc.returncode, proc.stdout[-4000:], proc.stderr[-4000:])
        )
        return combined

    # ------------------------------------------------------------------ #
    # L1 — deliverable files exist and are minimally well-formed
    # ------------------------------------------------------------------ #
    def test_l1_repo_present(self):
        """The prisma package directory must exist in the container."""
        assert os.path.isdir(PRISMA_DIR), f"{PRISMA_DIR} not found"

    def test_l1_connection_config_exists(self):
        """packages/prisma/connection-config.ts must be created."""
        assert os.path.isfile(CONFIG_TS), "connection-config.ts not found"
        assert os.path.getsize(CONFIG_TS) > 0, "connection-config.ts is empty"

    def test_l1_exports_resolver_symbol(self):
        """connection-config.ts must export a `resolveConnectionConfig` function."""
        with open(CONFIG_TS) as fh:
            src = fh.read()
        assert "resolveConnectionConfig" in src, "resolveConnectionConfig not referenced"
        assert re.search(
            r"export\s+(async\s+)?function\s+resolveConnectionConfig|"
            r"export\s+const\s+resolveConnectionConfig\s*=|"
            r"export\s*\{[^}]*\bresolveConnectionConfig\b",
            src,
        ), "resolveConnectionConfig is not exported from connection-config.ts"

    def test_l1_resolver_module_is_self_contained(self):
        """Resolver must not import the generated client, the pg driver, or pg.

        This is a structural guard for the purity / self-containment contract;
        the behavioural purity is exercised in L2.
        """
        with open(CONFIG_TS) as fh:
            src = fh.read()
        forbidden = [
            r"""from\s+['"]pg['"]""",
            r"""from\s+['"]@prisma/adapter-pg['"]""",
            r"""from\s+['"]\.?/?generated/prisma""",
            r"""from\s+['"]\./generated""",
        ]
        for pat in forbidden:
            assert not re.search(pat, src), (
                f"connection-config.ts must not import {pat!r}; it must be a pure module"
            )

    def test_l1_agent_test_exists(self):
        """packages/prisma/connection-config.test.ts must be created by the agent."""
        assert os.path.isfile(CONFIG_TEST_TS), "connection-config.test.ts not found"
        assert os.path.getsize(CONFIG_TEST_TS) > 0, "connection-config.test.ts is empty"

    def test_l1_index_consumes_resolver(self):
        """index.ts must derive its config from resolveConnectionConfig."""
        assert os.path.isfile(INDEX_TS), "index.ts not found"
        with open(INDEX_TS) as fh:
            src = fh.read()
        assert "resolveConnectionConfig" in src, (
            "index.ts must call resolveConnectionConfig instead of inlining env parsing"
        )

    # ------------------------------------------------------------------ #
    # L2 — dynamic execution of the real resolver via native vitest
    # ------------------------------------------------------------------ #
    def test_l2_vitest_suite_passes_overall(self):
        """The grader-owned vitest spec for the resolver passes end-to-end."""
        combined = self._require_vitest_passed()
        # Sanity: vitest actually executed our spec (and not "no tests").
        assert "benchverify" in combined or "passed" in combined.lower(), (
            "vitest output does not reference the grader spec; suite may not have run"
        )

    def test_l2_pool_disabled_default_and_fallbacks(self):
        """[T01] No USE_POOL -> pooling disabled; direct/readonly equal primary."""
        out = self._require_vitest_passed()
        assert "T01" in out, "T01 (default/fallback) case did not run"

    def test_l2_pool_enabled_numeric_fields(self):
        """[T02][T03] USE_POOL truthy -> pooling.enabled with numeric max + idle."""
        out = self._require_vitest_passed()
        assert "T02" in out and "T03" in out, "pool-enabled cases did not run"

    def test_l2_pool_opt_in_strictness(self):
        """[T04] Only 'true'/'1' opt in; whitespace/casing/other values disabled."""
        out = self._require_vitest_passed()
        assert "T04" in out, "USE_POOL strictness case did not run"

    def test_l2_missing_database_url_throws(self):
        """[T05][T06] Absent/empty/whitespace DATABASE_URL throws."""
        out = self._require_vitest_passed()
        assert "T05" in out and "T06" in out, "missing-DATABASE_URL throw cases did not run"

    def test_l2_direct_url_override_and_fallback(self):
        """[T07][T08] DATABASE_DIRECT_URL override + empty fallback."""
        out = self._require_vitest_passed()
        assert "T07" in out and "T08" in out, "direct-url cases did not run"

    def test_l2_readonly_url_override_and_fallback(self):
        """[T09][T10] INSIGHTS_DATABASE_URL override + empty fallback."""
        out = self._require_vitest_passed()
        assert "T09" in out and "T10" in out, "readonly-url cases did not run"

    def test_l2_scheme_validation(self):
        """[T11][T12][T13] Non-postgres schemes throw; both pg schemes accepted."""
        out = self._require_vitest_passed()
        assert "T11" in out and "T12" in out and "T13" in out, "scheme validation cases did not run"

    def test_l2_purity_deep_equal_and_env_untouched(self):
        """[T14][T15] Equal inputs -> deep-equal outputs; process.env ignored/untouched."""
        out = self._require_vitest_passed()
        assert "T14" in out and "T15" in out, "purity cases did not run"

    def test_l2_full_combined_config(self):
        """[T16] All four fields resolve independently from a combined env."""
        out = self._require_vitest_passed()
        assert "T16" in out, "combined-config case did not run"

    def test_l2_naive_resolver_would_fail(self):
        """Meta-guard: the spec encodes >=16 discriminative cases beyond existence.

        A hardcoded resolver (e.g. one that ignores env or never throws) cannot
        satisfy the throw + override + purity assertions, so a green vitest run
        is meaningful. We assert all 16 tagged cases executed.
        """
        out = self._require_vitest_passed()
        ran = {t for t in re.findall(r"T\d{2}", out)}
        expected = {f"T{i:02d}" for i in range(1, 17)}
        missing = expected - ran
        assert not missing, f"these resolver cases did not appear in vitest output: {sorted(missing)}"
