"""Tests for the `bats-shell-testing` skill task (ext2 variant): a version-string
normalizer helper.

Skill: bats-shell-testing
Variant task: Add a `bats_version_normalize <output-variable> <version>` helper to
`lib/bats-core/common.bash` plus a `@test bats_version_normalize` block in
`test/common.bats`.

Contract under test (re-derived from tasks/ext2/bats-shell-testing.md):
  * `bats_version_normalize out <version>` canonicalizes a 1-, 2- or 3-component
    dotted numeric version into strict `<major>.<minor>.<patch>` form, filling
    missing trailing components with `0`, and WRITES the result into the variable
    named by its first argument (NOT stdout), returning 0 on success.
      - `1`      -> `1.0.0`
      - `1.4`    -> `1.4.0`
      - `2.10.3` -> `2.10.3` (unchanged)
      - `01.2.3` -> `01.2.3` (digits preserved verbatim, no numeric reduction)
  * It REJECTS (non-zero rc, error message naming the offending input on stderr,
    and no assignment to the output variable):
      - too many components (`1.2.3.4`)
      - an empty component (`1..3`, leading/trailing dot)
      - a non-digit component (`1.x`)
      - a wrong argument count (not exactly two args)
  * It must be self-contained (no sed/awk/cut/python/perl) and must not alter the
    behavior of the existing helpers in common.bash.

Verification strategy:
  * L1: deliverable files exist; the function definition and the new `@test`
        block are present; the helper sources cleanly; the new function body uses
        no external programs.
  * L2: dynamic behavior, by sourcing common.bash and calling the helper directly
        in an isolated subshell for every Expected Functionality scenario. The
        harness reads back the value the helper wrote into a caller-supplied
        variable, so a stub that prints to stdout or ignores its input FAILS.
        We also run the native `bin/bats test/common.bats` suite so the agent's
        new @test block must pass alongside the pre-existing 9 tests.

The direct-execution L2 cases are authored independently of the agent's own .bats
test, so a solution that merely adds a passing-looking @test without a correct
function implementation will fail here.
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

    # A sentinel pre-set value for the output variable. If the helper rejects an
    # input it must NOT assign to the output variable, so the sentinel must
    # survive unchanged on failure.
    SENTINEL = "UNSET_SENTINEL_XYZ"

    # ------------------------------------------------------------------ helpers

    def _normalize(self, *args, preset=None):
        """Source common.bash and invoke `bats_version_normalize` in an isolated
        subshell. Returns (returncode, out_value, stderr).

        `out_value` is the value of the caller-supplied output variable AFTER the
        call. The first element of *args is treated as the output-variable name
        (when present); we pre-seed that variable with SENTINEL so we can detect
        "no assignment on rejection". The variable's post-call value is emitted on
        a marker line which we parse out, deliberately separate from the helper's
        own stdout, so an implementation that prints to stdout instead of writing
        the variable is NOT credited.

        The call is wrapped in `( ... )` so an implementation that uses `exit`
        (like the existing bats_check_valid_version) does not kill the harness,
        while still propagating the child exit status.
        """
        quoted = " ".join("'%s'" % a for a in args)
        out_var = args[0] if args else None
        preset_val = self.SENTINEL if preset is None else preset
        lines = ["set +e", "source '%s'" % self.COMMON_BASH]
        if out_var:
            # Only pre-seed when the first arg looks like a usable variable name;
            # otherwise leave it out (e.g. a numeric "version" as sole arg).
            if re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", out_var):
                lines.append("%s='%s'" % (out_var, preset_val))
        lines.append("( bats_version_normalize %s )" % quoted)
        lines.append('echo "__RC__=$?"')
        if out_var and re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", out_var):
            lines.append('echo "__VAL__=${%s}"' % out_var)
        script = "\n".join(lines) + "\n"

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
        vm = re.search(r"__VAL__=(.*)", proc.stdout)
        out_value = vm.group(1) if vm else None
        return rc, out_value, proc.stderr

    # --------------------------------------------------------------------- L1

    def test_repo_and_files_present(self):
        """L1: REPO_DIR and the two deliverable files (plus the bats runner) exist."""
        assert os.path.isdir(self.REPO_DIR), "missing repo dir %s" % self.REPO_DIR
        assert os.path.isfile(self.COMMON_BASH), "missing %s" % self.COMMON_BASH
        assert os.path.isfile(self.COMMON_BATS), "missing %s" % self.COMMON_BATS
        assert os.path.isfile(self.BATS_BIN), "missing bats runner %s" % self.BATS_BIN

    def test_function_defined_in_common_bash(self):
        """L1: a `bats_version_normalize` function definition was added."""
        with open(self.COMMON_BASH) as f:
            content = f.read()
        assert re.search(
            r"(?m)^\s*(function\s+)?bats_version_normalize\s*\(\s*\)",
            content,
        ), "no bats_version_normalize function definition found in common.bash"

    def test_new_test_block_present(self):
        """L1: a `@test bats_version_normalize` block was added to common.bats."""
        with open(self.COMMON_BATS) as f:
            content = f.read()
        assert re.search(
            r'@test\s+(bats_version_normalize\b|"bats_version_normalize"|'
            r"'bats_version_normalize')",
            content,
        ), "no `@test bats_version_normalize` block found in common.bats"

    def test_no_external_programs_in_helper(self):
        """L1: the helper body invokes no external programs (sed/awk/cut/python/perl)."""
        with open(self.COMMON_BASH) as f:
            content = f.read()
        m = re.search(
            r"(?ms)^\s*(?:function\s+)?bats_version_normalize\s*\(\s*\).*?\n\}",
            content,
        )
        assert m is not None, "could not isolate bats_version_normalize body"
        body = m.group(0)
        for forbidden in ("sed", "awk", "cut", "python", "perl", "tr ", "grep"):
            assert not re.search(r"(?<![A-Za-z0-9_])%s" % re.escape(forbidden.strip()), body), (
                "helper must be self-contained; found external program %r in body"
                % forbidden
            )

    def test_helper_is_sourceable(self):
        """L1/L2 bridge: common.bash sources cleanly and defines the new function."""
        script = (
            "source '%s'\n"
            "type -t bats_version_normalize\n" % self.COMMON_BASH
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
            "bats_version_normalize is not a defined function after sourcing; got %r"
            % proc.stdout
        )

    # --------------------------------------------------------------------- L2

    def test_one_component_padding(self):
        """L2: `1` -> output variable becomes `1.0.0`, rc 0, nothing on stdout-as-value
        other than via the variable."""
        rc, val, _err = self._normalize("out", "1")
        assert rc == 0, "normalize '1' should succeed, rc=%d" % rc
        assert val == "1.0.0", (
            "expected output variable == '1.0.0' (single component padded), got %r" % val
        )

    def test_two_component_padding(self):
        """L2: `1.4` -> `1.4.0` written to the caller variable, rc 0."""
        rc, val, _err = self._normalize("out", "1.4")
        assert rc == 0, "normalize '1.4' should succeed, rc=%d" % rc
        assert val == "1.4.0", "expected '1.4.0', got %r" % val

    def test_three_component_unchanged(self):
        """L2: an already-complete `2.10.3` is returned unchanged, rc 0."""
        rc, val, _err = self._normalize("out", "2.10.3")
        assert rc == 0, "normalize '2.10.3' should succeed, rc=%d" % rc
        assert val == "2.10.3", "expected '2.10.3' unchanged, got %r" % val

    def test_digits_preserved_verbatim(self):
        """L2: `01.2.3` keeps its leading zero (no numeric reduction to 1.2.3).

        This discriminates a correct string-level implementation from one that
        does arithmetic (e.g. `$((10#$part))`) on the components.
        """
        rc, val, _err = self._normalize("out", "01.2.3")
        assert rc == 0, "normalize '01.2.3' should succeed, rc=%d" % rc
        assert val == "01.2.3", (
            "components must be preserved verbatim ('01' must not become '1'); got %r"
            % val
        )

    def test_writes_to_caller_variable_not_stdout(self):
        """L2: the result is delivered via the caller-supplied variable NAME.

        We use a differently-named output variable and confirm the value lands in
        THAT variable. A stub that hardcodes `out=...` or that only echoes to
        stdout fails this case.
        """
        rc, val, _err = self._normalize("myver", "3")
        assert rc == 0, "normalize into 'myver' should succeed, rc=%d" % rc
        assert val == "3.0.0", (
            "value must be written into the caller's variable 'myver'; got %r" % val
        )

    def test_pad_does_not_use_stdout(self):
        """L2: on success the canonical value must NOT be printed to stdout.

        The contract says the result goes to the variable, not stdout. We assert
        the helper's own stdout (excluding our marker lines) is empty for a
        successful padding call.
        """
        quoted = "'out' '1.4'"
        script = (
            "set +e\n"
            "source '%s'\n"
            "out='%s'\n"
            "( bats_version_normalize %s ) > /tmp/__vn_stdout 2>/dev/null\n"
            'echo "__RC__=$?"\n'
            'echo "__VAL__=${out}"\n'
            'echo "__STDOUT__=$(cat /tmp/__vn_stdout)"\n'
            % (self.COMMON_BASH, self.SENTINEL, quoted)
        )
        proc = subprocess.run(
            ["bash", "-c", script],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert "__RC__=0" in proc.stdout, "success expected; stdout=%r" % proc.stdout
        assert "__VAL__=1.4.0" in proc.stdout, (
            "variable must hold canonical value; stdout=%r" % proc.stdout
        )
        m = re.search(r"__STDOUT__=(.*)", proc.stdout)
        captured = m.group(1) if m else ""
        assert captured.strip() == "", (
            "helper must not print the canonical value to stdout; captured %r"
            % captured
        )

    def test_too_many_components_rejected(self):
        """L2: `1.2.3.4` is rejected (non-zero rc), stderr names the offending
        input, and the output variable is left untouched (sentinel survives)."""
        rc, val, err = self._normalize("out", "1.2.3.4")
        assert rc != 0, "'1.2.3.4' (4 components) must be rejected"
        assert "1.2.3.4" in err, (
            "stderr must name the offending input '1.2.3.4'; got %r" % err
        )
        assert val == self.SENTINEL, (
            "output variable must NOT be assigned on rejection; got %r" % val
        )

    def test_empty_component_rejected(self):
        """L2: an empty middle component (`1..3`) and a leading/trailing dot are
        rejected, output variable untouched."""
        rc_mid, val_mid, _e = self._normalize("out", "1..3")
        assert rc_mid != 0, "'1..3' (empty middle component) must be rejected"
        assert val_mid == self.SENTINEL, "no assignment on rejection (1..3)"

        rc_lead, _v2, _e2 = self._normalize("out", ".1.2")
        assert rc_lead != 0, "leading-dot '.1.2' must be rejected"

        rc_trail, _v3, _e3 = self._normalize("out", "1.2.")
        assert rc_trail != 0, "trailing-dot '1.2.' must be rejected"

    def test_non_digit_component_rejected(self):
        """L2: a component with a non-digit char (`1.x`) is rejected, stderr names
        the input, output variable untouched."""
        rc, val, err = self._normalize("out", "1.x")
        assert rc != 0, "'1.x' (non-digit component) must be rejected"
        assert "1.x" in err, "stderr must name the offending input '1.x'; got %r" % err
        assert val == self.SENTINEL, "no assignment on rejection (1.x)"

    def test_partial_digit_component_rejected(self):
        """L2: `1.2a` (digit run followed by a letter) is also rejected -- the
        check is a full-component match, not a prefix match. Catches an anchoring
        bug (`=~ [0-9]+` without ^...$)."""
        rc, val, _err = self._normalize("out", "1.2a")
        assert rc != 0, "'1.2a' must be rejected (component is not all digits)"
        assert val == self.SENTINEL, "no assignment on rejection (1.2a)"

    def test_wrong_argument_count_rejected(self):
        """L2: the helper must be called with exactly two arguments; any other
        count fails."""
        # One argument (just the output-var name) -> fail.
        rc_one, _v1, _e1 = self._normalize("out")
        assert rc_one != 0, "one-argument call must fail"
        # Three arguments -> fail.
        rc_three, _v3, _e3 = self._normalize("out", "1.2.3", "extra")
        assert rc_three != 0, "three-argument call must fail"
        # Zero arguments -> fail.
        rc_zero, _v0, _e0 = self._normalize()
        assert rc_zero != 0, "zero-argument call must fail"

    def test_existing_helpers_unchanged(self):
        """L2: pre-existing helpers still behave correctly after the edit.

        Spot-check bats_version_lt's documented tri-state (0=lt, 1=gt, 2=eq) so a
        solution that mangles the shared comparison/validation code is caught."""
        script = (
            "set +e\n"
            "source '%s'\n"
            '( bats_version_lt 1.0.0 2.0.0 ); echo "LT=$?"\n'
            '( bats_version_lt 2.0.0 1.0.0 ); echo "GT=$?"\n'
            '( bats_version_lt 1.0.0 1.0.0 ); echo "EQ=$?"\n' % self.COMMON_BASH
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
        """L2: the agent's new `@test bats_version_normalize` passes under the real
        bats runner (filtered to just that block, and confirmed to have run)."""
        proc = subprocess.run(
            [self.BATS_BIN, "--filter", "bats_version_normalize", "test/common.bats"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=300,
        )
        out = proc.stdout + proc.stderr
        assert proc.returncode == 0, (
            "native run of `bats --filter bats_version_normalize test/common.bats` "
            "failed (rc=%d):\n%s" % (proc.returncode, out)
        )
        assert re.search(r"(?m)^ok \d+ bats_version_normalize\b", out), (
            "new @test bats_version_normalize did not run/pass under bats:\n%s" % out
        )

    def test_native_full_common_bats_suite_passes(self):
        """L2: the task's acceptance command `bin/bats test/common.bats` exits 0
        with every test (the original 9 + the new one) passing."""
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
        assert "bats_version_normalize" in out, (
            "the new test must appear in the suite output:\n%s" % out
        )
        assert "not ok" not in out, "no test in the suite may fail:\n%s" % out
        oks = re.findall(r"(?m)^ok \d+ ", out)
        assert len(oks) >= 10, (
            "expected >=10 passing tests in common.bats (9 original + new), saw %d:\n%s"
            % (len(oks), out)
        )
