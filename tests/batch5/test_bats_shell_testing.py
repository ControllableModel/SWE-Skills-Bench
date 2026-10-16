"""Tests for the `bats-shell-testing` skill task (variant ext5): a key/value split helper.

Skill: bats-shell-testing
Task (ext5): Add a `bats_split_key_value <key-out-var> <value-out-var> <token>` helper
to `lib/bats-core/common.bash`, plus a `@test bats_split_key_value` block in
`test/common.bats`.

Contract under test (from the variant requirement doc):
  * Splits `<token>` on the FIRST `=` only: "a=b=c" -> key "a", value "b=c".
  * Key must be non-empty: a token like "=value" is rejected.
  * Value MAY be empty: "KEY=" -> key "KEY", value "" (success).
  * A token with no `=` at all is rejected.
  * Glob chars / spaces in the value are preserved verbatim: "p=a b*c" -> "a b*c".
  * Exactly three arguments are required; any other count fails.
  * On any rejection: writes an error naming the offending token to stderr, returns
    non-zero, and does NOT assign to either output variable.
  * Pure / self-contained: no cut/awk/sed/python/perl, no fs/network.

Verification strategy:
  * L1: deliverable files exist; the function definition and the @test block are
    present; the new function body uses no external splitter program.
  * L2: an INDEPENDENT harness sources common.bash and calls bats_split_key_value
    directly in an isolated subshell, reading back BOTH output variables and the
    exit code for every Expected-Functionality scenario. This does not trust the
    agent's own .bats test. We also run the native `bin/bats test/common.bats`
    suite (the task's acceptance command) so the agent's new @test passes alongside
    the existing suite, and confirm pre-existing helpers are unchanged.

A naive solution (split on the LAST '=', accept empty keys, assign outputs before
validating, ignore arg count, or hardcode results) fails the L2 cases below.
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

    # A sentinel used to detect "output variable was NOT assigned". It must not
    # collide with any legitimate value the helper would ever produce.
    SENTINEL = "__UNSET_SENTINEL__"

    # ------------------------------------------------------------------ helpers

    def _split(self, *args, preset=True):
        """Source common.bash and invoke bats_split_key_value in an isolated
        subshell, returning (returncode, key_value, val_value, stderr).

        The output variables `k` and `v` are pre-seeded with SENTINEL so that,
        after the call, an UNCHANGED variable proves the helper did not assign to
        it (required behaviour on rejection). The call runs inside a `( ... )`
        child shell so an implementation that uses `exit` on error (like the
        existing bats_check_valid_version) cannot kill our harness; we therefore
        read the variables back via a separate marker mechanism: we print them
        from inside the child only on success, and rely on the sentinel-in-parent
        for the rejection cases.

        To capture variable values reliably for BOTH success and (potential)
        failure, the helper is invoked in the SAME shell as the readback (not a
        subshell), but we guard against `exit` by running the whole thing under a
        nested `bash -c` whose exit does not matter to us -- we read the markers
        from its stdout regardless of its return code.
        """
        quoted = " ".join("'%s'" % a for a in args)
        preset_line = ""
        if preset:
            preset_line = "k='%s'; v='%s'\n" % (self.SENTINEL, self.SENTINEL)
        script = (
            "set +e\n"
            "source '%s'\n"
            "%s"
            "bats_split_key_value k v %s\n"
            "rc=$?\n"
            "printf '__RC__=%%s\\n' \"$rc\"\n"
            "printf '__K__=[%%s]\\n' \"${k-%s}\"\n"
            "printf '__V__=[%%s]\\n' \"${v-%s}\"\n"
            % (
                self.COMMON_BASH,
                preset_line,
                quoted,
                self.SENTINEL,
                self.SENTINEL,
            )
        )
        proc = subprocess.run(
            ["bash", "-c", script],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=60,
        )
        rc = self._marker_int(proc.stdout, "__RC__", proc)
        key = self._marker_bracket(proc.stdout, "__K__")
        val = self._marker_bracket(proc.stdout, "__V__")
        return rc, key, val, proc.stderr

    @staticmethod
    def _marker_int(stdout, name, proc):
        m = re.search(r"%s=(-?\d+)" % re.escape(name), stdout)
        assert m is not None, (
            "could not find marker %s; stdout=%r stderr=%r"
            % (name, stdout, proc.stderr)
        )
        return int(m.group(1))

    @staticmethod
    def _marker_bracket(stdout, name):
        m = re.search(r"%s=\[(.*)\]" % re.escape(name), stdout)
        if m is None:
            return None
        return m.group(1)

    def _rc(self, *args):
        return self._split(*args)[0]

    # --------------------------------------------------------------------- L1

    def test_repo_and_files_present(self):
        """L1: REPO_DIR and the two deliverable files (plus bats runner) exist."""
        assert os.path.isdir(self.REPO_DIR), "missing repo dir %s" % self.REPO_DIR
        assert os.path.isfile(self.COMMON_BASH), "missing %s" % self.COMMON_BASH
        assert os.path.isfile(self.COMMON_BATS), "missing %s" % self.COMMON_BATS
        assert os.path.isfile(self.BATS_BIN), "missing bats runner %s" % self.BATS_BIN

    def test_function_defined_in_common_bash(self):
        """L1: a `bats_split_key_value` function definition was added to common.bash."""
        with open(self.COMMON_BASH) as f:
            content = f.read()
        assert re.search(
            r"(?m)^\s*(function\s+)?bats_split_key_value\s*\(\s*\)",
            content,
        ), "no bats_split_key_value function definition found in common.bash"

    def test_new_test_block_present(self):
        """L1: a `@test bats_split_key_value` block was added to common.bats."""
        with open(self.COMMON_BATS) as f:
            content = f.read()
        assert re.search(
            r'@test\s+(bats_split_key_value\b|"bats_split_key_value"|'
            r"'bats_split_key_value')",
            content,
        ), "no `@test bats_split_key_value` block found in common.bats"

    def test_helper_is_self_contained(self):
        """L1: the new function body uses no external splitter program."""
        with open(self.COMMON_BASH) as f:
            content = f.read()
        m = re.search(
            r"(?ms)^\s*(?:function\s+)?bats_split_key_value\s*\(\s*\).*?\n\}",
            content,
        )
        assert m is not None, "could not isolate bats_split_key_value body"
        body = m.group(0)
        for forbidden in (
            "cut ",
            "awk",
            "sed ",
            "python",
            "perl",
            "/dev/",
            "curl",
            "wget",
        ):
            assert forbidden not in body, (
                "helper must be pure; found forbidden token %r in its body" % forbidden
            )

    def test_helper_is_sourceable(self):
        """L1/L2 bridge: common.bash sources cleanly and exposes the new function."""
        script = (
            "source '%s'\n"
            "type -t bats_split_key_value\n" % self.COMMON_BASH
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
            "bats_split_key_value is not a defined function after sourcing; got %r"
            % proc.stdout
        )

    # --------------------------------------------------------------------- L2

    def test_basic_split_assigns_both_outputs(self):
        """L2: 'FOO=bar' -> key 'FOO', value 'bar', success (rc 0)."""
        rc, key, val, _err = self._split("FOO=bar")
        assert rc == 0, "basic split should succeed, rc=%d" % rc
        assert key == "FOO", "key output must be 'FOO', got %r" % key
        assert val == "bar", "value output must be 'bar', got %r" % val

    def test_splits_on_first_equals_only(self):
        """L2: 'a=b=c' -> key 'a', value 'b=c' (only the FIRST '=' separates).

        A naive split-on-last-'=' implementation gives key 'a=b', value 'c' and
        fails here."""
        rc, key, val, _err = self._split("a=b=c")
        assert rc == 0, "multi-'=' token should split successfully, rc=%d" % rc
        assert key == "a", "first-'=' split must yield key 'a', got %r" % key
        assert val == "b=c", "first-'=' split must yield value 'b=c', got %r" % val

    def test_empty_value_is_allowed(self):
        """L2: 'KEY=' -> key 'KEY', value '' (empty value is valid, rc 0)."""
        rc, key, val, _err = self._split("KEY=")
        assert rc == 0, "trailing-'=' token should succeed with empty value, rc=%d" % rc
        assert key == "KEY", "key output must be 'KEY', got %r" % key
        assert val == "", "value output must be empty string, got %r" % val

    def test_value_preserved_verbatim(self):
        """L2: 'p=a b*c' -> key 'p', value 'a b*c' verbatim (spaces + glob char
        preserved, no globbing / no word-splitting)."""
        rc, key, val, _err = self._split("p=a b*c")
        assert rc == 0, "token with spaces/glob should succeed, rc=%d" % rc
        assert key == "p", "key output must be 'p', got %r" % key
        assert val == "a b*c", (
            "value must be preserved verbatim as 'a b*c' (no glob/word-split), got %r"
            % val
        )

    def test_empty_key_rejected_and_outputs_untouched(self):
        """L2: '=value' is rejected (empty key); error names the token; neither
        output variable is assigned."""
        rc, key, val, err = self._split("=value")
        assert rc != 0, "empty-key token '=value' must be rejected, rc=%d" % rc
        assert "=value" in err, (
            "stderr must name the offending token '=value'; got %r" % err
        )
        assert key == self.SENTINEL, (
            "key output must NOT be assigned on rejection; got %r" % key
        )
        assert val == self.SENTINEL, (
            "value output must NOT be assigned on rejection; got %r" % val
        )

    def test_no_separator_rejected_and_outputs_untouched(self):
        """L2: 'novalue' (no '=') is rejected; error names the token; outputs
        untouched."""
        rc, key, val, err = self._split("novalue")
        assert rc != 0, "token without '=' must be rejected, rc=%d" % rc
        assert "novalue" in err, (
            "stderr must name the offending token 'novalue'; got %r" % err
        )
        assert key == self.SENTINEL, (
            "key output must NOT be assigned on rejection; got %r" % key
        )
        assert val == self.SENTINEL, (
            "value output must NOT be assigned on rejection; got %r" % val
        )

    def test_wrong_argument_count_rejected(self):
        """L2: any argument count other than exactly three must fail.

        Too many: 'a=b' with an extra arg. Too few: just the two output-var names
        with no token, and a single argument. These use a raw invocation harness
        that does not auto-prepend the output-variable names."""
        assert self._raw_argc_rc("k", "v", "a=b", "extra") != 0, (
            "four-argument call (one extra) must fail"
        )
        assert self._raw_argc_rc("k", "v") != 0, "two-argument call must fail"
        assert self._raw_argc_rc("k") != 0, "one-argument call must fail"
        assert self._raw_argc_rc() != 0, "zero-argument call must fail"

    def _raw_argc_rc(self, *args):
        """Invoke bats_split_key_value with EXACTLY the given args (no auto k/v
        prepending), returning just the exit code. Used for arg-count cases."""
        quoted = " ".join("'%s'" % a for a in args)
        script = (
            "set +e\n"
            "source '%s'\n"
            "( bats_split_key_value %s )\n"
            "printf '__RC__=%%s\\n' \"$?\"\n" % (self.COMMON_BASH, quoted)
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
            "could not read rc; stdout=%r stderr=%r" % (proc.stdout, proc.stderr)
        )
        return int(m.group(1))

    def test_rejection_distinct_from_success_codes(self):
        """L2: every rejection path is non-zero and every accept path is zero, so
        the three success scenarios and three rejection scenarios are cleanly
        separated by exit code (no implementation that always returns 0)."""
        successes = [
            self._rc("FOO=bar"),
            self._rc("a=b=c"),
            self._rc("KEY="),
        ]
        rejections = [
            self._rc("=value"),
            self._rc("novalue"),
            self._raw_argc_rc("k", "v"),  # wrong arg count
        ]
        assert all(c == 0 for c in successes), (
            "all valid tokens must return 0; got %r" % successes
        )
        assert all(c != 0 for c in rejections), (
            "all rejections must return non-zero; got %r" % rejections
        )

    def test_existing_helpers_unchanged(self):
        """L2: pre-existing helpers still behave correctly after the edit, proving
        the change did not break shared code.

        Spot-check bats_version_lt's documented tri-state (0=lt, 1=gt, 2=eq) and
        bats_trim's whitespace trimming."""
        script = (
            "set +e\n"
            "source '%s'\n"
            "( bats_version_lt 1.0.0 2.0.0 ); printf 'LT=%%s\\n' \"$?\"\n"
            "( bats_version_lt 2.0.0 1.0.0 ); printf 'GT=%%s\\n' \"$?\"\n"
            "( bats_version_lt 1.0.0 1.0.0 ); printf 'EQ=%%s\\n' \"$?\"\n"
            "bats_trim trimmed '  abc  '; printf 'TRIM=[%%s]\\n' \"$trimmed\"\n"
            % self.COMMON_BASH
        )
        proc = subprocess.run(
            ["bash", "-c", script],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=60,
        )
        out = proc.stdout
        assert "LT=0" in out, "bats_version_lt 1.0.0<2.0.0 must return 0:\n%s" % out
        assert "GT=1" in out, "bats_version_lt 2.0.0>1.0.0 must return 1:\n%s" % out
        assert "EQ=2" in out, "bats_version_lt 1.0.0==1.0.0 must return 2:\n%s" % out
        assert "TRIM=[abc]" in out, "bats_trim must still trim to 'abc':\n%s" % out

    def test_native_new_test_block_passes(self):
        """L2: the agent's new @test bats_split_key_value passes under the real
        bats runner (filtered to just that block, so it actually executes)."""
        proc = subprocess.run(
            [self.BATS_BIN, "--filter", "bats_split_key_value", "test/common.bats"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=300,
        )
        out = proc.stdout + proc.stderr
        assert proc.returncode == 0, (
            "native `bats --filter bats_split_key_value test/common.bats` failed "
            "(rc=%d):\n%s" % (proc.returncode, out)
        )
        assert re.search(r"(?m)^ok \d+ bats_split_key_value\b", out), (
            "new @test bats_split_key_value did not run/pass under bats:\n%s" % out
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
        assert "bats_split_key_value" in out, (
            "the new test must appear in the suite output:\n%s" % out
        )
        assert "not ok" not in out, "no test in the suite may fail:\n%s" % out
        oks = re.findall(r"(?m)^ok \d+ ", out)
        assert len(oks) >= 10, (
            "expected >=10 passing tests in common.bats, saw %d:\n%s"
            % (len(oks), out)
        )
