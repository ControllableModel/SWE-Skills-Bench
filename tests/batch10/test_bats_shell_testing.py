"""Tests for the `bats-shell-testing` skill task (variant ext10): a
duration-to-seconds parsing helper.

Skill: bats-shell-testing
Task: Add a `bats_duration_to_seconds <output-variable> <duration>` helper to
`lib/bats-core/common.bash` plus a `@test bats_duration_to_seconds` block in
`test/common.bats`.

The helper parses a compact human-readable duration string composed of one or
more `<number><unit>` segments (units `h`=3600s, `m`=60s, `s`=1s), sums them in
order, and writes the total number of seconds into the caller-supplied variable
name (it must NOT print the result to stdout, like the existing `bats_trim`).
On any rejection it must write an error message naming the offending input to
stderr, must NOT assign the output variable, and must return non-zero.

Verification strategy, against the real repo at REPO_DIR:
  * L1: the deliverable files exist; the new function definition and the new
        `@test` block are present; the helper sources cleanly and stays
        self-contained (no external programs date/awk/sed/python/perl).
  * L2: dynamic behavior, by sourcing common.bash and calling the helper
        directly in an isolated subshell, capturing the assigned output-variable
        value, the exit code, and stderr for every Expected Functionality
        scenario (conversions, repeated-unit summation, missing-unit /
        unknown-unit / empty / wrong-arg-count rejections, and the "result goes
        to the variable, not stdout" contract), AND by running the native
        `bin/bats test/common.bats` acceptance command so the agent's new
        `@test` block actually passes alongside the rest of the suite.

The direct-execution L2 cases are written independently of the agent's own
.bats test, so a solution that merely adds a passing-looking @test, hardcodes a
single value, ignores the input, or prints to stdout will fail here.
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

    def _run_raw(self, script):
        """Run a bash script in REPO_DIR, returning the CompletedProcess."""
        return subprocess.run(
            ["bash", "-c", script],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=60,
        )

    def _convert(self, duration):
        """Source common.bash and invoke
        `bats_duration_to_seconds RESULT <duration>` in an isolated subshell.

        Returns (returncode, result_value_or_None, stdout_payload, stderr).

        We deliberately PRE-SET the output variable to a sentinel before the
        call so we can detect whether the helper assigned to it. On a rejection
        the helper must leave it unassigned (still the sentinel). The call is
        wrapped in `( ... )` so an implementation that uses `exit` (like the
        repo's existing bats_check_valid_version) does not kill our harness.

        Because the result must be written THROUGH the named variable (not to
        stdout), we echo the variable explicitly via a marker line. We also
        capture any incidental stdout the function itself produced so we can
        assert it does not leak the result to stdout.
        """
        sentinel = "__UNSET_SENTINEL__"
        script = (
            "set +e\n"
            "source '%s'\n"
            "RESULT='%s'\n"
            "FUNC_STDOUT=$( ( bats_duration_to_seconds RESULT %s ) )\n"
            "RC=$?\n"
            "printf '__RC__=%%s\\n' \"$RC\"\n"
            "printf '__RESULT__=%%s\\n' \"$RESULT\"\n"
            "printf '__FUNC_STDOUT__=%%s\\n' \"$FUNC_STDOUT\"\n"
            % (self.COMMON_BASH, sentinel, self._q(duration))
        )
        proc = self._run_raw(script)
        m_rc = re.search(r"__RC__=(-?\d+)", proc.stdout)
        assert m_rc is not None, (
            "could not determine helper exit code; stdout=%r stderr=%r"
            % (proc.stdout, proc.stderr)
        )
        rc = int(m_rc.group(1))

        m_res = re.search(r"__RESULT__=(.*)", proc.stdout)
        raw_result = m_res.group(1) if m_res else ""
        result = None if raw_result == sentinel else raw_result

        m_fout = re.search(r"__FUNC_STDOUT__=(.*)", proc.stdout)
        func_stdout = m_fout.group(1) if m_fout else ""

        return rc, result, func_stdout, proc.stderr

    @staticmethod
    def _q(s):
        """Single-quote a value for safe embedding in the bash script."""
        return "'" + s.replace("'", "'\\''") + "'"

    def _convert_argv(self, *args):
        """Invoke the helper with an EXPLICIT argument vector (used to exercise
        wrong-argument-count cases). Returns (rc, stderr)."""
        quoted = " ".join(self._q(a) for a in args)
        script = (
            "set +e\n"
            "source '%s'\n"
            "( bats_duration_to_seconds %s )\n"
            "printf '__RC__=%%s\\n' \"$?\"\n" % (self.COMMON_BASH, quoted)
        )
        proc = self._run_raw(script)
        m = re.search(r"__RC__=(-?\d+)", proc.stdout)
        assert m is not None, "no rc marker; stdout=%r stderr=%r" % (
            proc.stdout,
            proc.stderr,
        )
        return int(m.group(1)), proc.stderr

    # --------------------------------------------------------------------- L1

    def test_repo_and_files_present(self):
        """L1: REPO_DIR, the two deliverable files, and the bats runner exist."""
        assert os.path.isdir(self.REPO_DIR), "missing repo dir %s" % self.REPO_DIR
        assert os.path.isfile(self.COMMON_BASH), "missing %s" % self.COMMON_BASH
        assert os.path.isfile(self.COMMON_BATS), "missing %s" % self.COMMON_BATS
        assert os.path.isfile(self.BATS_BIN), "missing bats runner %s" % self.BATS_BIN

    def test_function_defined_in_common_bash(self):
        """L1: a `bats_duration_to_seconds` function definition was added."""
        with open(self.COMMON_BASH) as f:
            content = f.read()
        assert re.search(
            r"(?m)^\s*(function\s+)?bats_duration_to_seconds\s*\(\s*\)",
            content,
        ), "no bats_duration_to_seconds function definition found in common.bash"

    def test_new_test_block_present(self):
        """L1: a `@test bats_duration_to_seconds` block was added to common.bats."""
        with open(self.COMMON_BATS) as f:
            content = f.read()
        assert re.search(
            r'@test\s+(bats_duration_to_seconds\b|"bats_duration_to_seconds"|'
            r"'bats_duration_to_seconds')",
            content,
        ), "no `@test bats_duration_to_seconds` block found in common.bats"

    def test_helper_is_self_contained(self):
        """L1: the new function body uses no external programs (pure bash)."""
        with open(self.COMMON_BASH) as f:
            content = f.read()
        m = re.search(
            r"(?ms)^\s*(?:function\s+)?bats_duration_to_seconds\s*\(\s*\).*?\n\}",
            content,
        )
        assert m is not None, "could not isolate bats_duration_to_seconds body"
        body = m.group(0)
        # Match these as whole words so e.g. an unrelated substring won't trip us.
        for forbidden in ("date", "awk", "sed", "python", "perl", "expr", "bc"):
            assert not re.search(r"(?<![\w-])%s(?![\w-])" % re.escape(forbidden), body), (
                "helper must be pure bash; found external program %r in body"
                % forbidden
            )

    def test_helper_is_sourceable(self):
        """L1/L2 bridge: common.bash sources cleanly and exposes the function."""
        proc = self._run_raw(
            "source '%s'\n type -t bats_duration_to_seconds\n" % self.COMMON_BASH
        )
        assert proc.returncode == 0, "sourcing common.bash failed: %s" % proc.stderr
        assert proc.stdout.strip() == "function", (
            "bats_duration_to_seconds is not a defined function after sourcing; got %r"
            % proc.stdout
        )

    # --------------------------------------------------------------------- L2

    def test_multi_segment_conversion(self):
        """L2: `1h30m` -> 5400 written into the output variable, rc 0."""
        rc, result, _o, err = self._convert("1h30m")
        assert rc == 0, "1h30m must succeed, rc=%d stderr=%r" % (rc, err)
        assert result == "5400", "1h30m must be 5400 seconds, got %r" % result

    def test_minutes_plus_seconds_conversion(self):
        """L2: `2m15s` -> 135, rc 0."""
        rc, result, _o, err = self._convert("2m15s")
        assert rc == 0, "2m15s must succeed, rc=%d stderr=%r" % (rc, err)
        assert result == "135", "2m15s must be 135 seconds, got %r" % result

    def test_single_segment_seconds(self):
        """L2: `45s` -> 45, rc 0. (A stub hardcoding 5400 fails here.)"""
        rc, result, _o, err = self._convert("45s")
        assert rc == 0, "45s must succeed, rc=%d stderr=%r" % (rc, err)
        assert result == "45", "45s must be 45 seconds, got %r" % result

    def test_full_h_m_s_combination(self):
        """L2: `1h1m1s` -> 3661, rc 0."""
        rc, result, _o, err = self._convert("1h1m1s")
        assert rc == 0, "1h1m1s must succeed, rc=%d stderr=%r" % (rc, err)
        assert result == "3661", "1h1m1s must be 3661 seconds, got %r" % result

    def test_repeated_unit_summation(self):
        """L2: repeated units are summed in order: `1m1m` -> 120."""
        rc, result, _o, err = self._convert("1m1m")
        assert rc == 0, "1m1m must succeed, rc=%d stderr=%r" % (rc, err)
        assert result == "120", "1m1m must sum to 120 seconds, got %r" % result
        # A larger multi-segment mix that is order-independent in value.
        rc2, result2, _o2, _e2 = self._convert("2h3m10s")
        assert rc2 == 0 and result2 == str(2 * 3600 + 3 * 60 + 10), (
            "2h3m10s must be %d, got rc=%d result=%r"
            % (2 * 3600 + 3 * 60 + 10, rc2, result2)
        )

    def test_result_written_to_variable_not_stdout(self):
        """L2: the result is delivered THROUGH the named variable, not printed to
        stdout. An implementation that `echo`s the answer would leak it here."""
        rc, result, func_stdout, _err = self._convert("1h30m")
        assert rc == 0 and result == "5400", (
            "precondition: 1h30m must convert to 5400 in the variable"
        )
        assert func_stdout.strip() == "", (
            "helper must not print the result to stdout; saw stdout=%r" % func_stdout
        )

    def test_custom_output_variable_name(self):
        """L2: the helper honors an arbitrary caller-supplied variable name (it
        must use the first argument as the target, not a fixed name)."""
        # Run the call in the SAME shell (no subshell) so the assignment persists,
        # then echo the variable. We must not use a subshell here.
        script = (
            "set +e\n"
            "source '%s'\n"
            "MY_TOTAL=BEFORE\n"
            "bats_duration_to_seconds MY_TOTAL 2m15s\n"
            "printf '__RC__=%%s\\n' \"$?\"\n"
            "printf '__MY_TOTAL__=%%s\\n' \"$MY_TOTAL\"\n" % self.COMMON_BASH
        )
        proc = self._run_raw(script)
        m_rc = re.search(r"__RC__=(-?\d+)", proc.stdout)
        m_val = re.search(r"__MY_TOTAL__=(.*)", proc.stdout)
        assert m_rc and int(m_rc.group(1)) == 0, (
            "conversion into MY_TOTAL must succeed; stdout=%r stderr=%r"
            % (proc.stdout, proc.stderr)
        )
        assert m_val and m_val.group(1) == "135", (
            "result must land in the caller-named variable MY_TOTAL (expected 135); "
            "got %r" % (m_val.group(1) if m_val else None)
        )

    def test_missing_unit_rejected_naming_input(self):
        """L2: a bare integer `90` (no unit) is rejected; stderr names the input;
        the output variable is NOT assigned; rc is non-zero."""
        rc, result, _o, err = self._convert("90")
        assert rc != 0, "bare integer 90 (no unit) must be rejected"
        assert result is None, (
            "rejected input must NOT assign the output variable; got %r" % result
        )
        assert "90" in err, "stderr must name the offending input '90'; got %r" % err

    def test_unknown_unit_rejected(self):
        """L2: an unknown unit `5d` is rejected; output var untouched; rc non-zero."""
        rc, result, _o, err = self._convert("5d")
        assert rc != 0, "unknown unit 5d must be rejected"
        assert result is None, (
            "rejected input must NOT assign the output variable; got %r" % result
        )
        assert "5d" in err, "stderr must name the offending input '5d'; got %r" % err

    def test_empty_input_rejected(self):
        """L2: an empty duration string is rejected; output var untouched; rc != 0."""
        rc, result, _o, _err = self._convert("")
        assert rc != 0, "empty input must be rejected"
        assert result is None, (
            "rejected empty input must NOT assign the output variable; got %r" % result
        )

    def test_unit_without_number_rejected(self):
        """L2: a unit with no preceding number (`m30s`) and trailing garbage
        (`30sx`) are both rejected, output var untouched."""
        rc1, result1, _o1, _e1 = self._convert("m30s")
        assert rc1 != 0, "leading unit with no number (m30s) must be rejected"
        assert result1 is None, "m30s must not assign the output variable; got %r" % result1

        rc2, result2, _o2, _e2 = self._convert("30sx")
        assert rc2 != 0, "trailing garbage (30sx) must be rejected"
        assert result2 is None, "30sx must not assign the output variable; got %r" % result2

    def test_wrong_argument_count_rejected(self):
        """L2: the helper must be called with exactly two arguments; one-arg and
        three-arg (and zero-arg) calls must fail."""
        rc_one, _e1 = self._convert_argv("out")  # only output var, no duration
        assert rc_one != 0, "single-argument call must fail"
        rc_zero, _e0 = self._convert_argv()  # no args at all
        assert rc_zero != 0, "zero-argument call must fail"
        rc_three, _e3 = self._convert_argv("out", "1h", "30m")  # too many args
        assert rc_three != 0, "three-argument call must fail"

    def test_existing_helpers_unchanged(self):
        """L2: pre-existing helpers still behave correctly after the edit.

        Spot-check `bats_trim` (the closest sibling: same output-variable idiom)
        and `bats_version_lt`'s tri-state so a solution that mangles shared code
        to make its own test pass is caught."""
        script = (
            "set +e\n"
            "source '%s'\n"
            "TRIMMED=x\n"
            "bats_trim TRIMMED '   hello world   '\n"
            "printf 'TRIM=[%%s]\\n' \"$TRIMMED\"\n"
            "( bats_version_lt 1.0.0 2.0.0 ); printf 'LT=%%s\\n' \"$?\"\n"
            "( bats_version_lt 2.0.0 1.0.0 ); printf 'GT=%%s\\n' \"$?\"\n"
            "( bats_version_lt 1.0.0 1.0.0 ); printf 'EQ=%%s\\n' \"$?\"\n"
            % self.COMMON_BASH
        )
        proc = self._run_raw(script)
        assert "TRIM=[hello world]" in proc.stdout, (
            "bats_trim must still strip surrounding whitespace; stdout=%r stderr=%r"
            % (proc.stdout, proc.stderr)
        )
        assert "LT=0" in proc.stdout, "bats_version_lt 1.0.0<2.0.0 must return 0"
        assert "GT=1" in proc.stdout, "bats_version_lt 2.0.0>1.0.0 must return 1"
        assert "EQ=2" in proc.stdout, "bats_version_lt 1.0.0==1.0.0 must return 2"

    def test_native_new_test_block_passes(self):
        """L2: the agent's new @test bats_duration_to_seconds passes under the real
        bats runner (filtered to just that block, and confirmed to have run)."""
        proc = subprocess.run(
            [self.BATS_BIN, "--filter", "bats_duration_to_seconds", "test/common.bats"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=300,
        )
        out = proc.stdout + proc.stderr
        assert proc.returncode == 0, (
            "native run of `bats --filter bats_duration_to_seconds test/common.bats` "
            "failed (rc=%d):\n%s" % (proc.returncode, out)
        )
        assert re.search(r"(?m)^ok \d+ bats_duration_to_seconds\b", out), (
            "new @test bats_duration_to_seconds did not run/pass under bats:\n%s" % out
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
        assert "bats_duration_to_seconds" in out, (
            "the new test must appear in the suite output:\n%s" % out
        )
        assert "not ok" not in out, "no test in the suite may fail:\n%s" % out
        # sanity: the original 9 documented tests + the new one = at least 10.
        oks = re.findall(r"(?m)^ok \d+ ", out)
        assert len(oks) >= 10, (
            "expected >=10 passing tests in common.bats, saw %d:\n%s"
            % (len(oks), out)
        )
