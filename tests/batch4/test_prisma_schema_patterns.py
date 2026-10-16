"""
Test for 'prisma-schema-patterns' skill (variant ext4) — Prisma pool-options builder.

The task asks the agent to introduce a pure, self-contained builder module
`packages/prisma/pool-options.ts` exporting `buildPoolOptions(env)`, plus a
Vitest unit test `packages/prisma/pool-options.test.ts`. The builder turns an
environment-variable map into a plain `{ enabled, max, idleTimeoutMillis }`
object with safe defaults and strict validation, WITHOUT importing `pg`, the
generated Prisma client, or the adapter, and without creating a pool.

These tests verify the deliverable INDEPENDENTLY of the agent's own test file:
they write a grader-owned Vitest spec into the prisma package that imports the
agent's `buildPoolOptions` and exercises every enablement / default / parsing /
validation / purity rule from the requirement doc via the repo's native
`yarn vitest run` toolchain.

A naive implementation (hardcoded `{enabled:true, max:5, idleTimeoutMillis:300000}`,
one that ignores env, never throws on invalid sizing, or accepts floats/zero/
negatives for `max`) MUST fail: the grader spec asserts concrete enablement
across USE_POOL values, default vs custom sizing, the throw cases, and purity.

L1 -> deliverable files exist + minimally well-formed + structurally pure.
L2 -> dynamic execution against the real builder behaviour via native vitest.
"""

import os
import re
import subprocess

import pytest

REPO_DIR = "/workspace/cal.com"
PRISMA_DIR = os.path.join(REPO_DIR, "packages", "prisma")
POOL_TS = os.path.join(PRISMA_DIR, "pool-options.ts")
POOL_TEST_TS = os.path.join(PRISMA_DIR, "pool-options.test.ts")

# A vitest spec we (the grader) own. It imports the agent's builder from the
# sibling module and asserts the required behaviour. We control its contents so
# a naive / hardcoded builder cannot pass by editing the agent-authored test.
VERIFY_SPEC_NAME = "pool-options.benchverify.test.ts"
VERIFY_SPEC_PATH = os.path.join(PRISMA_DIR, VERIFY_SPEC_NAME)


def _run_vitest(spec_filename, timeout=600):
    """Run a single vitest spec scoped to the prisma package; return CompletedProcess."""
    rel = os.path.join("packages", "prisma", spec_filename)
    env = dict(os.environ)
    env["TZ"] = "UTC"
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
    """Verify the Prisma pool-options builder deliverable (ext4 variant)."""

    REPO_DIR = "/workspace/cal.com"

    # ------------------------------------------------------------------ #
    # Module / spec lifecycle
    # ------------------------------------------------------------------ #
    @classmethod
    def setup_class(cls):
        """Install our own verification vitest spec into the prisma package."""
        cls._spec_written = False
        if os.path.isdir(PRISMA_DIR) and os.path.isfile(POOL_TS):
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
// Import the agent-authored builder. Importing this file alone must not pull
// in pg / the generated prisma client / the driver adapter (purity contract).
import { buildPoolOptions } from "./pool-options";

describe("benchverify buildPoolOptions", () => {
  // ---- enablement: only exactly "true" or "1" enable pooling ----
  it("[T01] USE_POOL='true' -> enabled true", () => {
    expect(buildPoolOptions({ USE_POOL: "true" }).enabled).toBe(true);
  });

  it("[T02] USE_POOL='1' -> enabled true", () => {
    expect(buildPoolOptions({ USE_POOL: "1" }).enabled).toBe(true);
  });

  it("[T03] USE_POOL='false'/'0'/''/' true '/'1 '/'TRUE'/'yes' -> enabled false", () => {
    for (const v of ["false", "0", "", " true ", "1 ", " 1", "TRUE", "True", "yes", "on", "2"]) {
      expect(buildPoolOptions({ USE_POOL: v }).enabled).toBe(false);
    }
  });

  it("[T04] absent USE_POOL -> enabled false", () => {
    expect(buildPoolOptions({}).enabled).toBe(false);
  });

  // ---- default sizing ----
  it("[T05] no DATABASE_POOL_MAX -> max defaults to 5", () => {
    expect(buildPoolOptions({}).max).toBe(5);
    expect(buildPoolOptions({ DATABASE_POOL_MAX: "" }).max).toBe(5);
  });

  it("[T06] no DATABASE_POOL_IDLE_TIMEOUT_MS -> idleTimeoutMillis defaults to 300000", () => {
    expect(buildPoolOptions({}).idleTimeoutMillis).toBe(300000);
    expect(buildPoolOptions({ DATABASE_POOL_IDLE_TIMEOUT_MS: "" }).idleTimeoutMillis).toBe(300000);
  });

  // ---- custom valid sizing (base-10 integers, numeric type) ----
  it("[T07] custom DATABASE_POOL_MAX is parsed as base-10 integer number", () => {
    const c = buildPoolOptions({ DATABASE_POOL_MAX: "20" });
    expect(c.max).toBe(20);
    expect(typeof c.max).toBe("number");
    // base-10: '010' must not be parsed as octal -> 10, not 8
    expect(buildPoolOptions({ DATABASE_POOL_MAX: "010" }).max).toBe(10);
  });

  it("[T08] custom DATABASE_POOL_IDLE_TIMEOUT_MS is parsed as base-10 integer number", () => {
    const c = buildPoolOptions({ DATABASE_POOL_IDLE_TIMEOUT_MS: "60000" });
    expect(c.idleTimeoutMillis).toBe(60000);
    expect(typeof c.idleTimeoutMillis).toBe("number");
  });

  it("[T09] idle timeout of 0 is accepted (never time out)", () => {
    expect(buildPoolOptions({ DATABASE_POOL_IDLE_TIMEOUT_MS: "0" }).idleTimeoutMillis).toBe(0);
  });

  // ---- invalid max -> throws naming the variable ----
  it("[T10] DATABASE_POOL_MAX='0' (not positive) -> throws naming the var", () => {
    let msg = "";
    expect(() => buildPoolOptions({ DATABASE_POOL_MAX: "0" })).toThrow();
    try { buildPoolOptions({ DATABASE_POOL_MAX: "0" }); } catch (e: any) { msg = String(e && e.message); }
    expect(/DATABASE_POOL_MAX/i.test(msg)).toBe(true);
  });

  it("[T11] DATABASE_POOL_MAX negative / float / non-numeric -> throws", () => {
    for (const v of ["-1", "2.5", "abc", "5x", "  ", "1e2"]) {
      expect(() => buildPoolOptions({ DATABASE_POOL_MAX: v })).toThrow();
    }
  });

  it("[T12] invalid DATABASE_POOL_MAX error names DATABASE_POOL_MAX specifically", () => {
    for (const v of ["-3", "2.5", "nope"]) {
      let msg = "";
      try { buildPoolOptions({ DATABASE_POOL_MAX: v }); } catch (e: any) { msg = String(e && e.message); }
      expect(msg.length).toBeGreaterThan(0);
      expect(/DATABASE_POOL_MAX/i.test(msg)).toBe(true);
    }
  });

  // ---- invalid idle timeout -> throws naming the variable ----
  it("[T13] DATABASE_POOL_IDLE_TIMEOUT_MS negative / float / non-numeric -> throws naming the var", () => {
    for (const v of ["-1", "1.5", "abc", "10s"]) {
      expect(() => buildPoolOptions({ DATABASE_POOL_IDLE_TIMEOUT_MS: v })).toThrow();
    }
    let msg = "";
    try { buildPoolOptions({ DATABASE_POOL_IDLE_TIMEOUT_MS: "-5" }); } catch (e: any) { msg = String(e && e.message); }
    expect(/DATABASE_POOL_IDLE_TIMEOUT_MS/i.test(msg)).toBe(true);
  });

  // ---- sizing still returned/validated when disabled ----
  it("[T14] disabled pool still returns defaults for max + idleTimeoutMillis", () => {
    const c = buildPoolOptions({ USE_POOL: "false" });
    expect(c.enabled).toBe(false);
    expect(c.max).toBe(5);
    expect(c.idleTimeoutMillis).toBe(300000);
  });

  it("[T15] disabled pool still returns provided valid custom sizing", () => {
    const c = buildPoolOptions({ USE_POOL: "0", DATABASE_POOL_MAX: "12", DATABASE_POOL_IDLE_TIMEOUT_MS: "1000" });
    expect(c.enabled).toBe(false);
    expect(c.max).toBe(12);
    expect(c.idleTimeoutMillis).toBe(1000);
  });

  it("[T16] validation still applies even when pooling disabled", () => {
    expect(() => buildPoolOptions({ USE_POOL: "false", DATABASE_POOL_MAX: "0" })).toThrow();
    expect(() => buildPoolOptions({ USE_POOL: "0", DATABASE_POOL_IDLE_TIMEOUT_MS: "-1" })).toThrow();
  });

  // ---- purity ----
  it("[T17] purity: equal inputs -> deep-equal outputs", () => {
    const input = { USE_POOL: "1", DATABASE_POOL_MAX: "9", DATABASE_POOL_IDLE_TIMEOUT_MS: "7000" };
    const r1 = buildPoolOptions({ ...input });
    const r2 = buildPoolOptions({ ...input });
    expect(r2).toEqual(r1);
    expect(r1).toEqual({ enabled: true, max: 9, idleTimeoutMillis: 7000 });
  });

  it("[T18] purity: builder ignores ambient process.env and does not mutate it", () => {
    const savedUse = process.env.USE_POOL;
    const savedMax = process.env.DATABASE_POOL_MAX;
    process.env.USE_POOL = "true";
    process.env.DATABASE_POOL_MAX = "999";
    const before = JSON.stringify(process.env);
    try {
      const c = buildPoolOptions({ DATABASE_POOL_MAX: "3" });
      // must reflect the passed-in map, NOT ambient env
      expect(c.enabled).toBe(false);
      expect(c.max).toBe(3);
      const after = JSON.stringify(process.env);
      expect(after).toBe(before);
    } finally {
      if (savedUse === undefined) delete process.env.USE_POOL; else process.env.USE_POOL = savedUse;
      if (savedMax === undefined) delete process.env.DATABASE_POOL_MAX; else process.env.DATABASE_POOL_MAX = savedMax;
    }
  });

  it("[T19] full enabled config resolves all three fields independently", () => {
    const c = buildPoolOptions({ USE_POOL: "true", DATABASE_POOL_MAX: "15", DATABASE_POOL_IDLE_TIMEOUT_MS: "0" });
    expect(c.enabled).toBe(true);
    expect(c.max).toBe(15);
    expect(c.idleTimeoutMillis).toBe(0);
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
                "Verification spec was not written — pool-options.ts is "
                "missing, so the builder deliverable does not exist."
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

    def test_l1_pool_options_exists(self):
        """packages/prisma/pool-options.ts must be created and non-empty."""
        assert os.path.isfile(POOL_TS), "pool-options.ts not found"
        assert os.path.getsize(POOL_TS) > 0, "pool-options.ts is empty"

    def test_l1_exports_builder_symbol(self):
        """pool-options.ts must export a `buildPoolOptions` function."""
        with open(POOL_TS) as fh:
            src = fh.read()
        assert "buildPoolOptions" in src, "buildPoolOptions not referenced"
        assert re.search(
            r"export\s+(async\s+)?function\s+buildPoolOptions|"
            r"export\s+const\s+buildPoolOptions\s*=|"
            r"export\s*\{[^}]*\bbuildPoolOptions\b",
            src,
        ), "buildPoolOptions is not exported from pool-options.ts"

    def test_l1_builder_module_is_self_contained(self):
        """Builder must not import pg, the generated client, or the adapter.

        Structural guard for the purity / self-containment contract; the
        builder must compute pool options without touching the DB stack.
        """
        with open(POOL_TS) as fh:
            src = fh.read()
        forbidden = [
            r"""from\s+['"]pg['"]""",
            r"""from\s+['"]@prisma/adapter-pg['"]""",
            r"""from\s+['"]\.?/?generated/prisma""",
            r"""from\s+['"]\./generated""",
            r"""new\s+Pool\s*\(""",
        ]
        for pat in forbidden:
            assert not re.search(pat, src), (
                f"pool-options.ts must not contain {pat!r}; it must be a pure, "
                "pool-free builder module"
            )

    def test_l1_agent_test_exists(self):
        """packages/prisma/pool-options.test.ts must be created by the agent."""
        assert os.path.isfile(POOL_TEST_TS), "pool-options.test.ts not found"
        assert os.path.getsize(POOL_TEST_TS) > 0, "pool-options.test.ts is empty"

    # ------------------------------------------------------------------ #
    # L2 — dynamic execution of the real builder via native vitest
    # ------------------------------------------------------------------ #
    def test_l2_vitest_suite_passes_overall(self):
        """The grader-owned vitest spec for the builder passes end-to-end."""
        combined = self._require_vitest_passed()
        assert "benchverify" in combined or "passed" in combined.lower(), (
            "vitest output does not reference the grader spec; suite may not have run"
        )

    def test_l2_enablement_true_and_one(self):
        """[T01][T02] USE_POOL exactly 'true' or '1' enables pooling."""
        out = self._require_vitest_passed()
        assert "T01" in out and "T02" in out, "enablement true/1 cases did not run"

    def test_l2_enablement_strictness(self):
        """[T03][T04] Whitespace/casing/other/absent values keep pooling disabled."""
        out = self._require_vitest_passed()
        assert "T03" in out and "T04" in out, "enablement strictness cases did not run"

    def test_l2_default_sizing(self):
        """[T05][T06] Unset/empty max and idle timeout fall back to 5 / 300000."""
        out = self._require_vitest_passed()
        assert "T05" in out and "T06" in out, "default sizing cases did not run"

    def test_l2_custom_sizing_parsed_base10(self):
        """[T07][T08][T09] Custom max/idle parsed as base-10 ints; idle 0 accepted."""
        out = self._require_vitest_passed()
        assert "T07" in out and "T08" in out and "T09" in out, "custom sizing cases did not run"

    def test_l2_invalid_max_throws(self):
        """[T10][T11][T12] Zero/negative/float/non-numeric max throws naming the var."""
        out = self._require_vitest_passed()
        assert "T10" in out and "T11" in out and "T12" in out, "invalid-max throw cases did not run"

    def test_l2_invalid_idle_timeout_throws(self):
        """[T13] Negative/float/non-numeric idle timeout throws naming the var."""
        out = self._require_vitest_passed()
        assert "T13" in out, "invalid-idle-timeout throw case did not run"

    def test_l2_sizing_when_disabled(self):
        """[T14][T15][T16] Disabled pool still returns + validates sizing."""
        out = self._require_vitest_passed()
        assert "T14" in out and "T15" in out and "T16" in out, "disabled-sizing cases did not run"

    def test_l2_purity(self):
        """[T17][T18] Equal inputs -> deep-equal outputs; ambient env ignored/untouched."""
        out = self._require_vitest_passed()
        assert "T17" in out and "T18" in out, "purity cases did not run"

    def test_l2_full_combined_config(self):
        """[T19] All three fields resolve independently from a combined env map."""
        out = self._require_vitest_passed()
        assert "T19" in out, "combined-config case did not run"

    def test_l2_naive_builder_would_fail(self):
        """Meta-guard: the spec encodes >=19 discriminative cases beyond existence.

        A hardcoded builder (always enabled, fixed 5/300000, never throwing, or
        accepting floats/zero/negatives for max) cannot satisfy the enablement +
        throw + default-vs-custom + purity assertions, so a green vitest run is
        meaningful. We assert all 19 tagged cases executed.
        """
        out = self._require_vitest_passed()
        ran = {t for t in re.findall(r"T\d{2}", out)}
        expected = {f"T{i:02d}" for i in range(1, 20)}
        missing = expected - ran
        assert not missing, f"these builder cases did not appear in vitest output: {sorted(missing)}"
