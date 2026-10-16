"""Tests for the `bats-shell-testing` skill task (variant ext8): an integer clamp helper.

Skill: bats-shell-testing
Task: Add a `bats_clamp_int <output-variable> <value> <min> <max>` helper to
`lib/bats-core/common.bash` plus a `@test bats_clamp_int` block in
`test/common.bats`.

Contract under test (re-derived from the ext8 requirement doc):
  * `bats_clamp_int out <value> <min> <max>` writes into the variable named by
    the FIRST argument the value clamped to the inclusive range [min, max]:
    min if value < min, max if value > max, otherwise value unchanged; rc 0.
  * The result is written through the caller-supplied variable name, NOT printed
    to stdout (output-variable pattern, like the existing bats_trim).
  * All of value/min/max must be integers (optional leading `-`). Non-integers
    (letters, decimal point, internal spaces, empty) are rejected.
  * min > max is an invalid range and rejected.
  * Exactly four arguments are required; any other count fails.
  * Every rejection writes an error to stderr, does NOT assign the output
    variable, and returns non-zero.
  * Comparisons are numeric, not lexical (-10 < -2).

Verification strategy:
  * L1: deliverable files exist; the function definition and the `@test
    bats_clamp_int` block are present; the helper sources cleanly and is
    self-contained (no expr/bc/awk/external tools).
  * L2: an INDEPENDENT harness sources common.bash and drives bats_clamp_int
    directly in isolated subshells for every Expected-Functionality scenario,
    asserting concrete clamped values, the not-assigned-on-rejection invariant,
    numeric (non-lexical) comparison, the output-variable (not stdout)
    discipline, and that the pre-existing helpers are untouched. Finally the
    native acceptance command `bin/bats test/common.bats` must exit 0 with the
    new block actually running.

Because the L2 cases call the function directly rather than trusting the agent's
own @test, a stub that merely adds a passing-looking @test without a correct
implementation (or one that ignores an input / hardcodes output / prints to
stdout / skips validation) will fail here.
"""

import os
import re
import subprocess

import pytest


class TestBatsShellTesting:
    REPO_DIR = "/workspace/bats-core"

    COMMON_BASH = os.path.join(REPO_DIR, "lib", "bats-core", "common.bash")
    COMMON_BATS = os.path.join(REPO_DIR, "test", "common.bats")
    BATS_BIN = os.path.join(REPO_DIR, "bin", "bats")

    # ------------------------------------------------------------------ helpers

    def _clamp(self, *args, outvar="out"):
        """Source common.bash, call `bats_clamp_int <outvar> <args...>` in an
        isolated subshell, and report what happened.

        Returns (rc, value, stdout, stderr) where:
          * rc     -- exit status of the helper call
          * value  -- the contents of the output variable AFTER the call, or the
                      sentinel "__UNSET__" if the variable was never assigned.
          * stdout -- helper stdout with our markers stripped (should be empty:
                      the result must go through the variable, not stdout).
          * stderr -- helper stderr (error messages on rejection).

        The call is wrapped in `( ... )` so an implementation that uses `exit`
        (as some existing helpers do) cannot kill our marker echoes. We probe the
        variable inside that same subshell because the assignment must be visible
        to the caller's scope.
        """
        quoted_args = " ".join("'%s'" % a for a in args)
        # Pre-set the output var to a sentinel so we can detect "not assigned".
        script = (
            "set +e\n"
            "source '%s'\n"
            "( %s='__UNSET__'\n"
            "  bats_clamp_int %s %s\n"
            "  rc=$?\n"
            "  printf '__RC__=%%s\\n' \"$rc\"\n"
            "  printf '__VAL__=%%s\\n' \"${%s-__UNSET__}\"\n"
            ")\n"
            % (self.COMMON_BASH, outvar, outvar, quoted_args, outvar)
        )
        proc = subprocess.run(
            ["bash", "-c", script],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=60,
        )
        m_rc = re.search(r"__RC__=(-?\d+)", proc.stdout)
        m_val = re.search(r"__VAL__=(.*)", proc.stdout)
        assert m_rc is not None, (
            "could not determine helper exit code; stdout=%r stderr=%r"
            % (proc.stdout, proc.stderr)
        )
        assert m_val is not None, (
            "could not read output variable; stdout=%r stderr=%r"
            % (proc.stdout, proc.stderr)
        )
        rc = int(m_rc.group(1))
        value = m_val.group(1)
        clean_out = re.sub(r"__RC__=-?\d+\n?", "", proc.stdout)
        clean_out = re.sub(r"__VAL__=.*\n?", "", clean_out)
        return rc, value, clean_out, proc.stderr

    # --------------------------------------------------------------------- L1

    def test_repo_and_files_present(self):
        """L1: REPO_DIR and the two deliverable files (plus the bats runner) exist."""
        assert os.path.isdir(self.REPO_DIR), "missing repo dir %s" % self.REPO_DIR
        assert os.path.isfile(self.COMMON_BASH), "missing %s" % self.COMMON_BASH
        assert os.path.isfile(self.COMMON_BATS), "missing %s" % self.COMMON_BATS
        assert os.path.isfile(self.BATS_BIN), "missing bats runner %s" % self.BATS_BIN

    def test_function_defined_in_common_bash(self):
        """L1: a `bats_clamp_int` function definition was added to common.bash."""
        with open(self.COMMON_BASH) as f:
            content = f.read()
        assert re.search(
            r"(?m)^\s*(function\s+)?bats_clamp_int\s*\(\s*\)",
            content,
        ), "no bats_clamp_int function definition found in common.bash"

    def test_new_test_block_present(self):
        """L1: a `@test bats_clamp_int` block was added to common.bats."""
        with open(self.COMMON_BATS) as f:
            content = f.read()
        assert re.search(
            r'@test\s+(bats_clamp_int\b|"bats_clamp_int"|\'bats_clamp_int\')',
            content,
        ), "no `@test bats_clamp_int` block found in common.bats"

    def test_no_external_arithmetic_tools(self):
        """L1: the helper is pure -- no expr/bc/awk/external program for arithmetic
        or comparison inside the new function body."""
        with open(self.COMMON_BASH) as f:
            content = f.read()
        m = re.search(
            r"(?ms)^\s*(?:function\s+)?bats_clamp_int\s*\(\s*\).*?\n\}",
            content,
        )
        assert m is not None, "could not isolate bats_clamp_int body"
        body = m.group(0)
        for forbidden in ("expr", "bc", "awk", "python", "perl", "sort -n"):
            assert not re.search(r"(?<![\w-])%s(?![\w-])" % re.escape(forbidden), body), (
                "helper must not use external program %r; use bash arithmetic" % forbidden
            )

    def test_helper_is_sourceable(self):
        """L1/L2 bridge: common.bash sources cleanly and defines bats_clamp_int."""
        script = (
            "source '%s'\n"
            "type -t bats_clamp_int\n" % self.COMMON_BASH
        )
        proc = subprocess.run(
            ["bash", "-c", script],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert proc.returncode == 0, "sourcing common.bash failed: %s" % proc.stderr
        assert proc.stdout.strip() == "function", (
            "bats_clamp_int is not a defined function after sourcing; got %r"
            % proc.stdout
        )

    # --------------------------------------------------------------------- L2

    def test_in_range_passthrough(self):
        """L2: a value strictly inside [min,max] is returned unchanged, rc 0."""
        rc, val, out, _err = self._clamp("5", "0", "10")
        assert rc == 0, "in-range call should succeed, rc=%d" % rc
        assert val == "5", "in-range value must pass through unchanged, got %r" % val
        assert out.strip() == "", (
            "result must go through the output variable, not stdout; stdout=%r" % out
        )

    def test_clamp_up_to_min(self):
        """L2: a value below min clamps UP to min (concrete value, not a sentinel)."""
        rc, val, _out, _err = self._clamp("-3", "0", "10")
        assert rc == 0, "clamp-up call should succeed, rc=%d" % rc
        assert val == "0", "value below min must clamp to min (0), got %r" % val

    def test_clamp_down_to_max(self):
        """L2: a value above max clamps DOWN to max."""
        rc, val, _out, _err = self._clamp("99", "0", "10")
        assert rc == 0, "clamp-down call should succeed, rc=%d" % rc
        assert val == "10", "value above max must clamp to max (10), got %r" % val

    def test_bounds_inclusive(self):
        """L2: a value exactly equal to min or max is in range and unchanged."""
        rc_lo, val_lo, _o1, _e1 = self._clamp("0", "0", "10")
        assert rc_lo == 0 and val_lo == "0", (
            "lower bound is inclusive: clamp 0 in [0,10] -> 0, got rc=%d val=%r"
            % (rc_lo, val_lo)
        )
        rc_hi, val_hi, _o2, _e2 = self._clamp("10", "0", "10")
        assert rc_hi == 0 and val_hi == "10", (
            "upper bound is inclusive: clamp 10 in [0,10] -> 10, got rc=%d val=%r"
            % (rc_hi, val_hi)
        )

    def test_negative_numeric_comparison(self):
        """L2: negative bounds/values compare numerically, not lexically.

        -5 is inside [-10,-2] -> unchanged. A lexical compare ("-5" vs "-10")
        would mis-handle this; a hardcoded/stub impl cannot satisfy all four
        of these together."""
        rc, val, _out, _err = self._clamp("-5", "-10", "-2")
        assert rc == 0, "negative in-range call should succeed, rc=%d" % rc
        assert val == "-5", "-5 is in [-10,-2] numerically and must be unchanged, got %r" % val
        # below the negative min clamps up to -10
        rc2, val2, _o2, _e2 = self._clamp("-50", "-10", "-2")
        assert rc2 == 0 and val2 == "-10", (
            "-50 below min -10 must clamp to -10, got rc=%d val=%r" % (rc2, val2)
        )
        # above the negative max clamps down to -2
        rc3, val3, _o3, _e3 = self._clamp("5", "-10", "-2")
        assert rc3 == 0 and val3 == "-2", (
            "5 above max -2 must clamp to -2, got rc=%d val=%r" % (rc3, val3)
        )

    def test_min_greater_than_max_rejected(self):
        """L2: min > max is an invalid range -> rejected, stderr message, var
        left unassigned, non-zero rc."""
        rc, val, _out, err = self._clamp("5", "10", "0")
        assert rc != 0, "min>max must be rejected (got rc 0)"
        assert val == "__UNSET__", (
            "rejected call must NOT assign the output variable; got %r" % val
        )
        assert err.strip() != "", "rejection must write an error message to stderr"

    def test_non_integer_value_rejected(self):
        """L2: a non-integer value (decimal point) is rejected without assigning."""
        for bad in ("1.5", "abc", "5x", "", " 3", "+5"):
            rc, val, _out, err = self._clamp(bad, "0", "10")
            assert rc != 0, "non-integer value %r must be rejected (rc=%d)" % (bad, rc)
            assert val == "__UNSET__", (
                "rejected value %r must leave output variable unassigned, got %r"
                % (bad, val)
            )
            assert err.strip() != "", (
                "rejecting %r must emit a stderr message" % bad
            )

    def test_non_integer_bounds_rejected(self):
        """L2: a malformed value in the min OR max position is rejected too."""
        rc_min, val_min, _o1, err_min = self._clamp("5", "x", "10")
        assert rc_min != 0, "non-integer min must be rejected"
        assert val_min == "__UNSET__", "non-integer min must not assign output var"
        assert err_min.strip() != "", "non-integer min must emit stderr"

        rc_max, val_max, _o2, err_max = self._clamp("5", "0", "1.0")
        assert rc_max != 0, "non-integer max must be rejected"
        assert val_max == "__UNSET__", "non-integer max must not assign output var"
        assert err_max.strip() != "", "non-integer max must emit stderr"

    def test_wrong_argument_count_rejected(self):
        """L2: exactly four arguments are required; other counts fail and do not
        assign the output variable."""
        # three args (missing max) -- via _clamp which passes outvar + these 3
        rc3, val3, _o3, _e3 = self._clamp("5", "0", outvar="out")
        assert rc3 != 0, "call with three total args must fail"
        assert val3 == "__UNSET__", "wrong-arg-count call must not assign output var"
        # five args (one extra)
        rc5, val5, _o5, _e5 = self._clamp("5", "0", "10", "20")
        assert rc5 != 0, "call with five total args must fail"
        assert val5 == "__UNSET__", "too-many-args call must not assign output var"

    def test_negative_signed_integers_accepted(self):
        """L2: a leading '-' sign is a valid integer in all positions (regression
        against an over-eager validator that rejects negatives)."""
        rc, val, _out, _err = self._clamp("-7", "-100", "100")
        assert rc == 0, "signed integers must be accepted, rc=%d" % rc
        assert val == "-7", "-7 in [-100,100] must pass through, got %r" % val

    def test_existing_helpers_unchanged(self):
        """L2: pre-existing helpers still behave correctly after the edit.

        Spot-check bats_trim (the same output-variable pattern) and the tri-state
        bats_version_lt (0=lt, 1=gt, 2=eq) so a solution that mangles shared code
        is caught."""
        script = (
            "set +e\n"
            "source '%s'\n"
            "bats_trim T '  hi  '; echo \"TRIM=[$T]\"\n"
            "( bats_version_lt 1.0.0 2.0.0 ); echo \"LT=$?\"\n"
            "( bats_version_lt 2.0.0 1.0.0 ); echo \"GT=$?\"\n"
            "( bats_version_lt 1.0.0 1.0.0 ); echo \"EQ=$?\"\n" % self.COMMON_BASH
        )
        proc = subprocess.run(
            ["bash", "-c", script],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert "TRIM=[hi]" in proc.stdout, (
            "bats_trim must still trim correctly; got %r" % proc.stdout
        )
        assert "LT=0" in proc.stdout, "bats_version_lt 1.0.0<2.0.0 must return 0"
        assert "GT=1" in proc.stdout, "bats_version_lt 2.0.0>1.0.0 must return 1"
        assert "EQ=2" in proc.stdout, "bats_version_lt 1.0.0==1.0.0 must return 2"

    def test_native_new_test_block_passes(self):
        """L2: the agent's new @test bats_clamp_int passes under the real bats
        runner (filtered to just that block, and it actually ran)."""
        proc = subprocess.run(
            [self.BATS_BIN, "--filter", "bats_clamp_int", "test/common.bats"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=300,
        )
        out = proc.stdout + proc.stderr
        assert proc.returncode == 0, (
            "native run of `bats --filter bats_clamp_int test/common.bats` "
            "failed (rc=%d):\n%s" % (proc.returncode, out)
        )
        assert re.search(r"(?m)^ok \d+ bats_clamp_int\b", out), (
            "new @test bats_clamp_int did not run/pass under bats:\n%s" % out
        )

    def test_native_full_common_bats_suite_passes(self):
        """L2: the full `bin/bats test/common.bats` suite (the task's acceptance
        command) exits 0 with every test passing, including the new one."""
        proc = subprocess.run(
            [self.BATS_BIN, "test/common.bats"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=300,
        )
        out = proc.stdout + proc.stderr
        assert proc.returncode == 0, (
            "`bin/bats test/common.bats` must exit 0; rc=%d\n%s"
            % (proc.returncode, out)
        )
        assert "bats_clamp_int" in out, (
            "the new test must appear in the suite output:\n%s" % out
        )
        assert "not ok" not in out, "no test in the suite may fail:\n%s" % out
        oks = re.findall(r"(?m)^ok \d+ ", out)
        assert len(oks) >= 10, (
            "expected >=10 passing tests in common.bats, saw %d:\n%s"
            % (len(oks), out)
        )
