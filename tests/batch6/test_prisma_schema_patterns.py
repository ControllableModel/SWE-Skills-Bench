"""
Test for 'prisma-schema-patterns' skill (variant ext6) — generator-block validator.

The variant task asks the agent to add a pure validator module
`packages/prisma/generator-validate.ts` exporting
`validateClientGenerator(generator: { provider?: string; output?: string })`,
plus a Vitest unit test `packages/prisma/generator-validate.test.ts`.

Contract (from the requirement doc):
  - returns `{ valid: boolean, errors: string[] }`.
  - `provider` must be one of `prisma-client` or `prisma-client-js`; any other
    value (database provider name, empty string, or absent) is invalid and the
    error names the offending provider.
  - when provider === `prisma-client`, a non-empty `output` is REQUIRED
    (whitespace-only counts as missing); for `prisma-client-js`, output is
    optional.
  - `valid === true` only when `errors` is empty.
  - the function is pure (no I/O, no env reads), never throws, and equal inputs
    produce deep-equal outputs.
  - both-problem cases yield one error entry per distinct problem.

Verification strategy: independently of the agent's own test file, we inject a
grader-owned Vitest spec into the prisma package that imports the agent's
`validateClientGenerator` and exercises every rule above through the repo's
native `yarn vitest run` toolchain. A naive/stub implementation (always-valid,
ignores provider, never requires output, or throws) fails the spec.

L1 -> deliverable files exist + minimally well-formed + structurally pure.
L2 -> dynamic execution of the real validator via native vitest.
"""

import os
import re
import subprocess

import pytest

REPO_DIR = "/workspace/cal.com"
PRISMA_DIR = os.path.join(REPO_DIR, "packages", "prisma")
VALIDATE_TS = os.path.join(PRISMA_DIR, "generator-validate.ts")
VALIDATE_TEST_TS = os.path.join(PRISMA_DIR, "generator-validate.test.ts")

# A vitest spec the grader owns. It imports the agent's validator from the
# sibling module and asserts the required behaviour. We control its contents so
# a naive validator cannot pass by editing the agent-authored test.
VERIFY_SPEC_NAME = "generator-validate.benchverify.test.ts"
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
    """Verify the Prisma generator-block validator deliverable (ext6)."""

    REPO_DIR = "/workspace/cal.com"

    # ------------------------------------------------------------------ #
    # Module / spec lifecycle
    # ------------------------------------------------------------------ #
    @classmethod
    def setup_class(cls):
        """Install our own verification vitest spec into the prisma package."""
        cls._spec_written = False
        if os.path.isdir(PRISMA_DIR) and os.path.isfile(VALIDATE_TS):
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
// Import the agent-authored validator. Importing this file alone must not pull
// in the generated prisma client / driver adapter / pg (purity contract).
import { validateClientGenerator } from "./generator-validate";

describe("benchverify validateClientGenerator", () => {
  it("[T01] valid prisma-client with non-empty output -> valid, no errors", () => {
    const r = validateClientGenerator({ provider: "prisma-client", output: "./generated/prisma" });
    expect(r.valid).toBe(true);
    expect(Array.isArray(r.errors)).toBe(true);
    expect(r.errors.length).toBe(0);
  });

  it("[T02] prisma-client missing output -> invalid with an output error", () => {
    const r = validateClientGenerator({ provider: "prisma-client" });
    expect(r.valid).toBe(false);
    expect(r.errors.length).toBeGreaterThanOrEqual(1);
    // The error must concern the output-path requirement, not the provider.
    const joined = r.errors.join(" | ").toLowerCase();
    expect(/output/.test(joined)).toBe(true);
  });

  it("[T03] prisma-client with empty-string output -> invalid (output error)", () => {
    const r = validateClientGenerator({ provider: "prisma-client", output: "" });
    expect(r.valid).toBe(false);
    expect(r.errors.join(" ").toLowerCase()).toContain("output");
  });

  it("[T04] prisma-client with whitespace-only output -> invalid (treated as missing)", () => {
    for (const ws of ["   ", "\t", "\n", "  \t  "]) {
      const r = validateClientGenerator({ provider: "prisma-client", output: ws });
      expect(r.valid).toBe(false);
      expect(r.errors.join(" ").toLowerCase()).toContain("output");
    }
  });

  it("[T05] valid prisma-client-js WITH output -> valid, no errors", () => {
    const r = validateClientGenerator({ provider: "prisma-client-js", output: "./client" });
    expect(r.valid).toBe(true);
    expect(r.errors.length).toBe(0);
  });

  it("[T06] valid prisma-client-js WITHOUT output -> valid, no errors (output optional)", () => {
    const r = validateClientGenerator({ provider: "prisma-client-js" });
    expect(r.valid).toBe(true);
    expect(r.errors.length).toBe(0);
    // Whitespace-only output for the legacy generator is still acceptable.
    const r2 = validateClientGenerator({ provider: "prisma-client-js", output: "   " });
    expect(r2.valid).toBe(true);
    expect(r2.errors.length).toBe(0);
  });

  it("[T07] unrecognized provider (postgresql) -> invalid, error names the provider", () => {
    const r = validateClientGenerator({ provider: "postgresql", output: "./generated/prisma" });
    expect(r.valid).toBe(false);
    expect(r.errors.length).toBeGreaterThanOrEqual(1);
    expect(r.errors.join(" ")).toContain("postgresql");
  });

  it("[T08] empty-string provider -> invalid (unrecognized provider)", () => {
    const r = validateClientGenerator({ provider: "", output: "./generated/prisma" });
    expect(r.valid).toBe(false);
    expect(r.errors.length).toBeGreaterThanOrEqual(1);
  });

  it("[T09] absent provider -> invalid (unrecognized provider)", () => {
    const r = validateClientGenerator({ output: "./generated/prisma" });
    expect(r.valid).toBe(false);
    expect(r.errors.length).toBeGreaterThanOrEqual(1);
  });

  it("[T10] combined: bad provider AND missing output -> two distinct errors", () => {
    const r = validateClientGenerator({ provider: "mysql" });
    expect(r.valid).toBe(false);
    expect(r.errors.length).toBeGreaterThanOrEqual(2);
    const joined = r.errors.join(" | ").toLowerCase();
    // one error about the provider (names it), one about the missing output.
    expect(r.errors.join(" | ")).toContain("mysql");
    expect(/output/.test(joined)).toBe(true);
  });

  it("[T11] valid tracks errors-empty for both true and false outcomes", () => {
    const ok = validateClientGenerator({ provider: "prisma-client", output: "./x" });
    expect(ok.valid).toBe(ok.errors.length === 0);
    expect(ok.valid).toBe(true);
    const bad = validateClientGenerator({ provider: "nope" });
    expect(bad.valid).toBe(bad.errors.length === 0);
    expect(bad.valid).toBe(false);
  });

  it("[T12] never throws on hostile input shapes", () => {
    const inputs: any[] = [
      {},
      { provider: undefined, output: undefined },
      { provider: "prisma-client", output: null },
      { provider: null },
      { provider: 123 as any, output: 456 as any },
    ];
    for (const inp of inputs) {
      expect(() => validateClientGenerator(inp)).not.toThrow();
      const r = validateClientGenerator(inp);
      expect(typeof r.valid).toBe("boolean");
      expect(Array.isArray(r.errors)).toBe(true);
    }
  });

  it("[T13] purity: equal inputs -> deep-equal outputs, input not mutated", () => {
    const input = { provider: "prisma-client", output: "./generated/prisma" };
    const snapshot = JSON.stringify(input);
    const r1 = validateClientGenerator({ ...input });
    const r2 = validateClientGenerator({ ...input });
    expect(r2).toEqual(r1);
    expect(JSON.stringify(input)).toBe(snapshot);

    const badInput = { provider: "postgresql" };
    const b1 = validateClientGenerator({ ...badInput });
    const b2 = validateClientGenerator({ ...badInput });
    expect(b2).toEqual(b1);
  });

  it("[T14] valid prisma-client-js with whitespace-only output stays valid (no false output error)", () => {
    const r = validateClientGenerator({ provider: "prisma-client-js", output: "  " });
    expect(r.valid).toBe(true);
    expect(r.errors.length).toBe(0);
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
                "Verification spec was not written — generator-validate.ts is "
                "missing, so the validator deliverable does not exist."
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

    def test_l1_validator_module_exists(self):
        """packages/prisma/generator-validate.ts must be created and non-empty."""
        assert os.path.isfile(VALIDATE_TS), "generator-validate.ts not found"
        assert os.path.getsize(VALIDATE_TS) > 0, "generator-validate.ts is empty"

    def test_l1_exports_validator_symbol(self):
        """generator-validate.ts must export a `validateClientGenerator` function."""
        with open(VALIDATE_TS) as fh:
            src = fh.read()
        assert "validateClientGenerator" in src, "validateClientGenerator not referenced"
        assert re.search(
            r"export\s+(async\s+)?function\s+validateClientGenerator|"
            r"export\s+const\s+validateClientGenerator\s*=|"
            r"export\s*\{[^}]*\bvalidateClientGenerator\b",
            src,
        ), "validateClientGenerator is not exported from generator-validate.ts"

    def test_l1_validator_module_is_self_contained(self):
        """Validator must not import the generated client, the pg adapter, or pg.

        Structural guard for the purity / self-containment contract; behavioural
        purity is exercised in L2.
        """
        with open(VALIDATE_TS) as fh:
            src = fh.read()
        forbidden = [
            r"""from\s+['"]pg['"]""",
            r"""from\s+['"]@prisma/adapter-pg['"]""",
            r"""from\s+['"]\.?/?generated/prisma""",
            r"""from\s+['"]\./generated""",
            r"""from\s+['"]\./client['"]""",
        ]
        for pat in forbidden:
            assert not re.search(pat, src), (
                f"generator-validate.ts must not import {pat!r}; it must be a pure module"
            )

    def test_l1_validator_does_no_file_io(self):
        """The module must not read files / env itself (pure validator contract)."""
        with open(VALIDATE_TS) as fh:
            src = fh.read()
        for forbidden in ("readFileSync", "readFile(", "process.env", "require(\"fs\")", "from \"fs\""):
            assert forbidden not in src, (
                f"generator-validate.ts must be pure: it must not use {forbidden!r}"
            )

    def test_l1_agent_test_exists(self):
        """packages/prisma/generator-validate.test.ts must be created by the agent."""
        assert os.path.isfile(VALIDATE_TEST_TS), "generator-validate.test.ts not found"
        assert os.path.getsize(VALIDATE_TEST_TS) > 0, "generator-validate.test.ts is empty"

    # ------------------------------------------------------------------ #
    # L2 — dynamic execution of the real validator via native vitest
    # ------------------------------------------------------------------ #
    def test_l2_vitest_suite_passes_overall(self):
        """The grader-owned vitest spec for the validator passes end-to-end."""
        combined = self._require_vitest_passed()
        assert "benchverify" in combined or "passed" in combined.lower(), (
            "vitest output does not reference the grader spec; suite may not have run"
        )

    def test_l2_valid_prisma_client_with_output(self):
        """[T01] A correctly-configured prisma-client generator validates clean."""
        out = self._require_vitest_passed()
        assert "T01" in out, "T01 (valid prisma-client) case did not run"

    def test_l2_prisma_client_requires_output(self):
        """[T02][T03][T04] Missing/empty/whitespace output for prisma-client is invalid."""
        out = self._require_vitest_passed()
        assert "T02" in out and "T03" in out and "T04" in out, (
            "prisma-client output-requirement cases did not run"
        )

    def test_l2_prisma_client_js_output_optional(self):
        """[T05][T06][T14] prisma-client-js is valid with or without output."""
        out = self._require_vitest_passed()
        assert "T05" in out and "T06" in out and "T14" in out, (
            "prisma-client-js output-optional cases did not run"
        )

    def test_l2_unrecognized_provider_invalid(self):
        """[T07][T08][T09] postgresql / empty / absent provider are all invalid."""
        out = self._require_vitest_passed()
        assert "T07" in out and "T08" in out and "T09" in out, (
            "unrecognized-provider cases did not run"
        )

    def test_l2_combined_two_distinct_errors(self):
        """[T10] Bad provider AND missing output -> two distinct error entries."""
        out = self._require_vitest_passed()
        assert "T10" in out, "combined two-error case did not run"

    def test_l2_valid_tracks_errors_empty(self):
        """[T11] `valid` is exactly `errors.length === 0` for both outcomes."""
        out = self._require_vitest_passed()
        assert "T11" in out, "valid/errors coupling case did not run"

    def test_l2_never_throws_and_purity(self):
        """[T12][T13] Never throws on hostile input; equal inputs deep-equal, no mutation."""
        out = self._require_vitest_passed()
        assert "T12" in out and "T13" in out, "robustness/purity cases did not run"

    def test_l2_naive_validator_would_fail(self):
        """Meta-guard: the spec encodes >=14 discriminative cases beyond existence.

        A stub (always-valid, ignores provider, never requires output, or one
        that throws) cannot satisfy the invalid-provider, required-output,
        combined-error, never-throw and purity assertions, so a green vitest run
        is meaningful. We assert all 14 tagged cases executed.
        """
        out = self._require_vitest_passed()
        ran = {t for t in re.findall(r"T\d{2}", out)}
        expected = {f"T{i:02d}" for i in range(1, 15)}
        missing = expected - ran
        assert not missing, f"these validator cases did not appear in vitest output: {sorted(missing)}"
