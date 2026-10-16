"""Tests for the `bats-shell-testing` skill task: a version-range membership helper.

Skill: bats-shell-testing
Task: Add a `bats_version_in_range <version> <min-inclusive> <max-exclusive>` helper to
`lib/bats-core/common.bash` plus a `@test bats_version_in_range` block in
`test/common.bats`.

These tests verify, against the real repo at REPO_DIR:
  * L1: the deliverable files exist and the new test block / function are present.
  * L2: dynamic behavior, by sourcing common.bash and calling the helper directly
        (in an isolated subshell, capturing exit code + stderr) for every Expected
        Functionality scenario, AND by running the native `bin/bats test/common.bats`
        suite so the agent's new @test block actually passes alongside the rest.

The direct-execution L2 cases are written independently of the agent's own .bats
test, so a solution that merely adds a passing-looking @test without a correct
function implementation will fail here.
"""

import os
import re
import subprocess
import textwrap

import pytest


class TestBatsShellTesting:
    REPO_DIR = "/workspace/bats-core"

    COMMON_BASH = os.path.join(REPO_DIR, "lib", "bats-core", "common.bash")
    COMMON_BATS = os.path.join(REPO_DIR, "test", "common.bats")
    BATS_BIN = os.path.join(REPO_DIR, "bin", "bats")

    # ------------------------------------------------------------------ helpers

    def _run_in_range(self, *args):
        """Source common.bash and invoke bats_version_in_range in an isolated
        subshell, returning (returncode, stdout, stderr).

        The call is wrapped in a child shell via `( ... )` so that an
        implementation using `exit` (like the existing bats_check_valid_version)
        does not kill our harness shell, and the child's exit status is
        propagated back as the script's exit status. Quoting each argument
        defends against empty / odd inputs.
        """
        quoted = " ".join("'%s'" % a for a in args)
        script = (
            "set +e\n"
            "source '%s'\n"
            "( bats_version_in_range %s )\n"
            "echo \"__RC__=$?\"\n" % (self.COMMON_BASH, quoted)
        )
        proc = subprocess.run(
            ["bash", "-c", script],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=60,
        )
        m = re.search(r"__RC__=(-?\d+)", proc.stdout)
        assert m is not None, (
            "could not determine helper exit code; stdout=%r stderr=%r"
            % (proc.stdout, proc.stderr)
        )
        rc = int(m.group(1))
        # strip the marker line from stdout for cleanliness
        stdout = re.sub(r"__RC__=-?\d+\n?", "", proc.stdout)
        return rc, stdout, proc.stderr

    def _in_range_rc(self, *args):
        return self._run_in_range(*args)[0]

    # --------------------------------------------------------------------- L1

    def test_repo_and_files_present(self):
        """L1: REPO_DIR and the two deliverable files exist."""
        assert os.path.isdir(self.REPO_DIR), "missing repo dir %s" % self.REPO_DIR
        assert os.path.isfile(self.COMMON_BASH), "missing %s" % self.COMMON_BASH
        assert os.path.isfile(self.COMMON_BATS), "missing %s" % self.COMMON_BATS
        assert os.path.isfile(self.BATS_BIN), "missing bats runner %s" % self.BATS_BIN

    def test_function_defined_in_common_bash(self):
        """L1: a `bats_version_in_range` function definition was added to common.bash."""
        with open(self.COMMON_BASH) as f:
            content = f.read()
        assert re.search(
            r"(?m)^\s*(function\s+)?bats_version_in_range\s*\(\s*\)",
            content,
        ), "no bats_version_in_range function definition found in common.bash"

    def test_new_test_block_present(self):
        """L1: a `@test bats_version_in_range` block was added to common.bats."""
        with open(self.COMMON_BATS) as f:
            content = f.read()
        assert re.search(
            r'@test\s+(bats_version_in_range\b|"bats_version_in_range"|'
            r"'bats_version_in_range')",
            content,
        ), "no `@test bats_version_in_range` block found in common.bats"

    def test_no_external_comparison_tools(self):
        """L1: the helper is self-contained (no sort -V / awk / python invocation
        introduced for the comparison)."""
        with open(self.COMMON_BASH) as f:
            content = f.read()
        # isolate the new function body to avoid false positives elsewhere
        m = re.search(
            r"(?ms)^\s*(?:function\s+)?bats_version_in_range\s*\(\s*\).*?\n\}",
            content,
        )
        assert m is not None, "could not isolate bats_version_in_range body"
        body = m.group(0)
        for forbidden in ("sort -V", "sort --version-sort", "awk", "python", "perl"):
            assert forbidden not in body, (
                "helper must not use external program %r for comparison" % forbidden
            )

    def test_helper_is_sourceable(self):
        """L1/L2 bridge: common.bash sources cleanly and exposes the new function."""
        script = (
            "source '%s'\n"
            "type -t bats_version_in_range\n" % self.COMMON_BASH
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
            "bats_version_in_range is not a defined function after sourcing; got %r"
            % proc.stdout
        )

    # --------------------------------------------------------------------- L2

    def test_in_range_basic_success(self):
        """L2: a version strictly inside the interval -> success (rc 0)."""
        rc = self._in_range_rc("1.5.0", "1.0.0", "2.0.0")
        assert rc == 0, "1.5.0 in [1.0.0,2.0.0) should succeed, rc=%d" % rc

    def test_lower_bound_inclusive(self):
        """L2: version equal to min-inclusive is in range (rc 0)."""
        rc = self._in_range_rc("1.0.0", "1.0.0", "2.0.0")
        assert rc == 0, "lower bound must be inclusive, rc=%d" % rc

    def test_upper_bound_exclusive(self):
        """L2: version equal to max-exclusive is NOT in range (non-zero rc)."""
        rc = self._in_range_rc("2.0.0", "1.0.0", "2.0.0")
        assert rc != 0, "upper bound must be exclusive (2.0.0 out of range)"

    def test_below_lower_bound(self):
        """L2: a version below min-inclusive is out of range (non-zero rc)."""
        rc = self._in_range_rc("0.9.0", "1.0.0", "2.0.0")
        assert rc != 0, "0.9.0 is below 1.0.0 and must be out of range"

    def test_numeric_component_comparison(self):
        """L2: comparison is numeric, not lexical: 1.2.10 is in [1.2.9, 1.3.0)."""
        rc = self._in_range_rc("1.2.10", "1.2.9", "1.3.0")
        assert rc == 0, (
            "1.2.10 must be >= 1.2.9 numerically (lexical compare would fail), rc=%d" % rc
        )
        # And the symmetric ordering fact: 1.2.9 is below 1.2.10 as a lower bound edge.
        rc2 = self._in_range_rc("1.2.9", "1.2.10", "1.3.0")
        assert rc2 != 0, "1.2.9 < 1.2.10 numerically, so it must be out of [1.2.10,1.3.0)"

    def test_empty_interval_contains_nothing(self):
        """L2: when min >= max the interval is empty -> every query out of range."""
        # min strictly greater than max
        assert self._in_range_rc("1.5.0", "2.0.0", "1.0.0") != 0, (
            "empty interval [2.0.0,1.0.0) must contain nothing"
        )
        # min equal to max (also empty, half-open)
        assert self._in_range_rc("1.0.0", "1.0.0", "1.0.0") != 0, (
            "degenerate interval [1.0.0,1.0.0) must contain nothing"
        )

    def test_invalid_version_rejected_with_message(self):
        """L2: a malformed version (1.0) is rejected, error names the string and
        the expected <major>.<minor>.<patch> format, and rc is non-zero."""
        rc, _out, err = self._run_in_range("1.0", "1.0.0", "2.0.0")
        assert rc != 0, "malformed version 1.0 must be rejected"
        assert "1.0" in err, (
            "stderr must name the offending string '1.0'; got %r" % err
        )
        assert "major" in err and "minor" in err and "patch" in err, (
            "stderr must explain the expected <major>.<minor>.<patch> format; got %r"
            % err
        )

    def test_wrong_argument_count_rejected(self):
        """L2: a call with fewer than three arguments must fail (not silently pass)."""
        rc_two, _o, _e = self._run_in_range("1.0.0", "1.0.0")
        assert rc_two != 0, "two-argument call must fail"
        rc_one, _o2, _e2 = self._run_in_range("1.0.0")
        assert rc_one != 0, "one-argument call must fail"
        rc_zero, _o3, _e3 = self._run_in_range()
        assert rc_zero != 0, "zero-argument call must fail"

    def test_out_of_range_distinct_from_bad_input(self):
        """L2: 'validly out of range' and 'bad input' use DIFFERENT non-zero codes.

        Requirement: a caller must be able to tell *why* the call failed by exit
        code alone. So the code for a well-formed out-of-range query must differ
        from the code for an invalid/malformed argument and from a wrong arg count.
        """
        oor = self._in_range_rc("2.0.0", "1.0.0", "2.0.0")  # well-formed, out of range
        bad_version = self._in_range_rc("1.0", "1.0.0", "2.0.0")  # malformed
        bad_argc = self._in_range_rc("1.0.0", "1.0.0")  # too few args

        assert oor != 0, "out-of-range must be non-zero"
        assert bad_version != 0, "malformed-version must be non-zero"
        assert bad_argc != 0, "wrong-arg-count must be non-zero"

        assert oor != bad_version, (
            "out-of-range (rc=%d) must be distinguishable from malformed-version "
            "(rc=%d) by exit code" % (oor, bad_version)
        )
        assert oor != bad_argc, (
            "out-of-range (rc=%d) must be distinguishable from wrong-arg-count "
            "(rc=%d) by exit code" % (oor, bad_argc)
        )

    def test_invalid_in_any_argument_position(self):
        """L2: a malformed value in the min or max position is also rejected as bad
        input (same failure mode as a malformed version), not treated as a normal
        in/out-of-range answer."""
        bad_min = self._in_range_rc("1.5.0", "1.0", "2.0.0")
        bad_max = self._in_range_rc("1.5.0", "1.0.0", "2")
        oor = self._in_range_rc("2.0.0", "1.0.0", "2.0.0")
        assert bad_min != 0, "malformed min-inclusive must be rejected"
        assert bad_max != 0, "malformed max-exclusive must be rejected"
        # bad input should report the same 'bad input' status, distinct from out-of-range
        assert bad_min == bad_max, (
            "all malformed-argument cases should share one 'bad input' status "
            "(min rc=%d, max rc=%d)" % (bad_min, bad_max)
        )
        assert bad_min != oor, (
            "malformed-argument status (rc=%d) must differ from out-of-range (rc=%d)"
            % (bad_min, oor)
        )

    def test_existing_helpers_unchanged(self):
        """L2: the pre-existing helpers still behave correctly after the edit.

        Spot-check bats_version_lt's documented tri-state (0=lt, 1=gt, 2=eq) so a
        solution that 'fixes' things by mangling the shared comparison code is
        caught."""
        script = (
            "set +e\n"
            "source '%s'\n"
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
        assert "LT=0" in proc.stdout, "bats_version_lt 1.0.0<2.0.0 must return 0"
        assert "GT=1" in proc.stdout, "bats_version_lt 2.0.0>1.0.0 must return 1"
        assert "EQ=2" in proc.stdout, "bats_version_lt 1.0.0==1.0.0 must return 2"

    def test_native_new_test_block_passes(self):
        """L2: the agent's new @test bats_version_in_range passes under the real
        bats runner (filtered to just that block)."""
        proc = subprocess.run(
            [self.BATS_BIN, "--filter", "bats_version_in_range", "test/common.bats"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=300,
        )
        out = proc.stdout + proc.stderr
        assert proc.returncode == 0, (
            "native run of `bats --filter bats_version_in_range test/common.bats` "
            "failed (rc=%d):\n%s" % (proc.returncode, out)
        )
        # ensure the block actually ran (was not filtered to zero tests)
        assert re.search(r"(?m)^ok \d+ bats_version_in_range\b", out), (
            "new @test bats_version_in_range did not run/pass under bats:\n%s" % out
        )

    def test_native_full_common_bats_suite_passes(self):
        """L2: the full `bin/bats test/common.bats` suite exits 0 with every test
        (including the new one) passing -- the task's acceptance command."""
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
        assert "bats_version_in_range" in out, (
            "the new test must appear in the suite output:\n%s" % out
        )
        assert "not ok" not in out, "no test in the suite may fail:\n%s" % out
        # sanity: at least the originally documented 9 + new one = 10 tests reported
        oks = re.findall(r"(?m)^ok \d+ ", out)
        assert len(oks) >= 10, (
            "expected >=10 passing tests in common.bats, saw %d:\n%s"
            % (len(oks), out)
        )
