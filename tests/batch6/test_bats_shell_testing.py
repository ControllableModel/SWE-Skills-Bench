"""Tests for the `bats-shell-testing` skill task (variant ext6): an
array join-by-delimiter helper.

Skill: bats-shell-testing
Task (ext6): Add a `bats_join_by <output-variable> <delimiter> <elements...>`
helper to `lib/bats-core/common.bash` that concatenates the elements with
exactly one delimiter *between* consecutive elements and writes the result
into the caller-supplied variable name (the same out-variable convention used
by `bats_trim` / `bats_approx_realpath`). A new `@test bats_join_by` block is
added to `test/common.bats`.

Verification strategy, against the real repo at REPO_DIR:
  * L1: the two deliverable files exist; the function definition and the new
        `@test bats_join_by` block are present; the helper is self-contained
        (no external join programs like paste/sed/tr/awk in its body) and
        sources cleanly, exposing the function.
  * L2: dynamic behavior, by sourcing common.bash and invoking the helper for
        EVERY "Expected Functionality" scenario in the doc, asserting the exact
        resulting string is delivered THROUGH the caller's variable (captured
        independently of the agent's own .bats test). This catches naive/stub
        implementations: print-to-stdout instead of out-var, a hardcoded
        separator, dropping leading/trailing empty fields, off-by-one delimiter
        counts, or splitting elements that contain the delimiter. Finally the
        native `bin/bats test/common.bats` acceptance command is run so the
        agent's new @test passes alongside the whole pre-existing suite.

The direct-execution L2 cases are written independently of the agent's own
.bats test, so a solution that merely adds a passing-looking @test without a
correct function implementation will fail here.
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

    _SENTINEL = "<<<UNSET>>>"
    _BEGIN = "__JOINBEGIN__"
    _END = "__JOINEND__"

    def _join(self, delimiter, *elements, out_var="out"):
        """Source common.bash, call `bats_join_by <out_var> <delimiter>
        <elements...>` in an isolated subshell, and return
        (returncode, result_value, stderr).

        The result is read back from the *caller-supplied variable* (out_var),
        NOT from the helper's stdout, so an implementation that prints instead
        of assigning through the variable name is rejected. The value is framed
        with unique markers so leading/trailing whitespace and empty results
        survive transport; if the variable is never set, the sentinel reveals
        it. The call is wrapped in `( ... )` so an `exit` inside the helper
        cannot kill the harness shell.
        """
        # Pre-seed the out-var with a sentinel so "never assigned" is detectable.
        parts = ["set +e\n", "source '%s'\n" % self.COMMON_BASH]
        parts.append("%s=%s\n" % (out_var, _shq(self._SENTINEL)))
        argv = [out_var, delimiter] + list(elements)
        quoted = " ".join(_shq(a) for a in argv)
        parts.append("( bats_join_by %s )\n" % quoted)
        parts.append('rc=$?\n')
        parts.append('printf "%%s" "%s${%s-%s}%s"\n'
                     % (self._BEGIN, out_var, self._SENTINEL, self._END))
        parts.append('printf "\\n__RC__=%s\\n" "$rc"\n')
        script = "".join(parts)
        proc = subprocess.run(
            ["bash", "-c", script],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=60,
        )
        m_rc = re.search(r"__RC__=(-?\d+)", proc.stdout)
        assert m_rc is not None, (
            "could not determine helper exit code; stdout=%r stderr=%r"
            % (proc.stdout, proc.stderr)
        )
        rc = int(m_rc.group(1))
        m_val = re.search(
            re.escape(self._BEGIN) + r"(.*)" + re.escape(self._END),
            proc.stdout,
            re.DOTALL,
        )
        assert m_val is not None, (
            "could not capture out-variable framing; stdout=%r stderr=%r"
            % (proc.stdout, proc.stderr)
        )
        value = m_val.group(1)
        return rc, value, proc.stderr

    def _join_value(self, delimiter, *elements):
        rc, value, err = self._join(delimiter, *elements)
        assert rc == 0, (
            "bats_join_by must return 0 (delim=%r elems=%r); rc=%d stderr=%r"
            % (delimiter, elements, rc, err)
        )
        assert value != self._SENTINEL, (
            "bats_join_by never wrote through the caller's variable "
            "(delim=%r elems=%r) -- it must assign the result to the named "
            "output variable, not print to stdout" % (delimiter, elements)
        )
        return value

    # --------------------------------------------------------------------- L1

    def test_repo_and_files_present(self):
        """L1: REPO_DIR, the two deliverable files, and the bats runner exist."""
        assert os.path.isdir(self.REPO_DIR), "missing repo dir %s" % self.REPO_DIR
        assert os.path.isfile(self.COMMON_BASH), "missing %s" % self.COMMON_BASH
        assert os.path.isfile(self.COMMON_BATS), "missing %s" % self.COMMON_BATS
        assert os.path.isfile(self.BATS_BIN), "missing bats runner %s" % self.BATS_BIN

    def test_function_defined_in_common_bash(self):
        """L1: a `bats_join_by` function definition was added to common.bash."""
        with open(self.COMMON_BASH) as f:
            content = f.read()
        assert re.search(
            r"(?m)^\s*(function\s+)?bats_join_by\s*\(\s*\)",
            content,
        ), "no bats_join_by function definition found in common.bash"

    def test_new_test_block_present(self):
        """L1: a `@test bats_join_by` block was added to common.bats."""
        with open(self.COMMON_BATS) as f:
            content = f.read()
        assert re.search(
            r'@test\s+(bats_join_by\b|"bats_join_by"|\'bats_join_by\')',
            content,
        ), "no `@test bats_join_by` block found in common.bats"

    def test_helper_is_self_contained(self):
        """L1: the helper body uses no external join programs (paste/sed/tr/awk/
        cut/perl/python) -- it must be pure bash per the constraints."""
        with open(self.COMMON_BASH) as f:
            content = f.read()
        m = re.search(
            r"(?ms)^\s*(?:function\s+)?bats_join_by\s*\(\s*\).*?\n\}",
            content,
        )
        assert m is not None, "could not isolate bats_join_by body"
        body = m.group(0)
        for forbidden in ("paste", "sed", "tr ", "awk", "cut ", "perl", "python"):
            assert forbidden not in body, (
                "helper must be self-contained pure bash; found external "
                "program reference %r in bats_join_by body" % forbidden
            )

    def test_helper_is_sourceable(self):
        """L1/L2 bridge: common.bash sources cleanly and exposes the new
        function as a shell function."""
        script = (
            "source '%s'\n"
            "type -t bats_join_by\n" % self.COMMON_BASH
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
            "bats_join_by is not a defined function after sourcing; got %r"
            % proc.stdout
        )

    # --------------------------------------------------------------------- L2

    def test_basic_single_char_delimiter(self):
        """L2: `bats_join_by out , a b c` -> `a,b,c`."""
        assert self._join_value(",", "a", "b", "c") == "a,b,c"

    def test_multi_char_delimiter(self):
        """L2: a multi-character delimiter is placed verbatim between elements:
        `bats_join_by out " -> " x y` -> `x -> y`."""
        assert self._join_value(" -> ", "x", "y") == "x -> y"
        # also a two-char ", " delimiter across three elements
        assert self._join_value(", ", "a", "b", "c") == "a, b, c"

    def test_single_element_no_delimiter(self):
        """L2: with a single element no delimiter is added: `out` is `solo`.
        Catches an implementation that always appends a trailing delimiter."""
        assert self._join_value(",", "solo") == "solo"

    def test_no_elements_empty_result(self):
        """L2: with no elements the result is the empty string and rc is 0.
        Catches a stub that errors on or mishandles the zero-element case."""
        rc, value, err = self._join(",")
        assert rc == 0, "no-elements call must return 0; rc=%d stderr=%r" % (rc, err)
        assert value != self._SENTINEL, (
            "no-elements case must still assign the (empty) result through the "
            "caller's variable, got sentinel (variable never set)"
        )
        assert value == "", (
            "joining zero elements must yield the empty string, got %r" % value
        )

    def test_empty_delimiter_concatenates(self):
        """L2: an empty delimiter concatenates elements with nothing between:
        `bats_join_by out "" a b c` -> `abc`.

        Catches a hardcoded-separator stub (e.g. one that always uses ',')."""
        assert self._join_value("", "a", "b", "c") == "abc"

    def test_empty_elements_honored(self):
        """L2: empty-string elements are honored -- `bats_join_by out : "" a ""`
        yields `:a:` (empty leading and trailing fields around the delimiters).

        A naive split/strip-empties implementation that drops empty fields would
        produce `a` and fail here."""
        assert self._join_value(":", "", "a", "") == ":a:"

    def test_element_containing_delimiter_preserved(self):
        """L2: an element that itself contains the delimiter is copied verbatim,
        not re-split: `bats_join_by out , "a,b" c` -> `a,b,c`.

        This and the empty-elements case together pin down that the helper joins
        the *given* elements (n-1 delimiters), rather than re-splitting/merging
        the concatenation."""
        assert self._join_value(",", "a,b", "c") == "a,b,c"

    def test_exact_delimiter_count(self):
        """L2: exactly n-1 delimiters for n elements -- no leading or trailing
        delimiter. Verified with a multi-char delimiter and 4 elements so an
        off-by-one (leading/trailing extra) is unambiguous."""
        # 4 elements -> exactly 3 occurrences of the delimiter "::"
        value = self._join_value("::", "w", "x", "y", "z")
        assert value == "w::x::y::z", "expected n-1 delimiters, got %r" % value
        assert value.count("::") == 3, (
            "must place exactly n-1=3 delimiters for 4 elements; got %d in %r"
            % (value.count("::"), value)
        )
        assert not value.startswith("::"), "no leading delimiter allowed"
        assert not value.endswith("::"), "no trailing delimiter allowed"

    def test_special_characters_verbatim(self):
        """L2: elements with spaces/special characters are copied verbatim with
        no further word-splitting or globbing."""
        assert self._join_value("|", "a b", "c*d", "e\tf") == "a b|c*d|e\tf"

    def test_distinct_output_variable_name(self):
        """L2: the result is delivered through whatever variable NAME the caller
        supplies (not a fixed/hardcoded variable). Use a non-default name and
        confirm it receives the value."""
        rc, value, err = self._join(",", "p", "q", out_var="my_result")
        assert rc == 0, "rc must be 0; stderr=%r" % err
        assert value != self._SENTINEL, (
            "helper must honor the caller-supplied output variable name "
            "'my_result'; it was never assigned (printed to stdout or wrote a "
            "different fixed variable instead)"
        )
        assert value == "p,q", "out-var 'my_result' got %r, expected 'p,q'" % value

    # ------------------------------------------------------- L2: regression/native

    def test_existing_helpers_unchanged(self):
        """L2: pre-existing helpers still behave correctly after the edit.

        Spot-check bats_trim (the closest out-variable sibling) and
        bats_version_lt's tri-state so a solution that mangles shared code or
        an existing function is caught."""
        script = (
            "set +e\n"
            "source '%s'\n"
            "bats_trim t '  abc  '; printf 'TRIM=[%%s]\\n' \"$t\"\n"
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
        assert "TRIM=[abc]" in proc.stdout, (
            "bats_trim must still trim to 'abc'; output=%r" % proc.stdout
        )
        assert "LT=0" in proc.stdout, "bats_version_lt 1.0.0<2.0.0 must return 0"
        assert "GT=1" in proc.stdout, "bats_version_lt 2.0.0>1.0.0 must return 1"
        assert "EQ=2" in proc.stdout, "bats_version_lt 1.0.0==1.0.0 must return 2"

    def test_native_new_test_block_passes(self):
        """L2: the agent's new `@test bats_join_by` passes under the real bats
        runner (filtered to just that block, and confirmed to have actually
        run)."""
        proc = subprocess.run(
            [self.BATS_BIN, "--filter", "bats_join_by", "test/common.bats"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=300,
        )
        out = proc.stdout + proc.stderr
        assert proc.returncode == 0, (
            "native run of `bats --filter bats_join_by test/common.bats` failed "
            "(rc=%d):\n%s" % (proc.returncode, out)
        )
        assert re.search(r"(?m)^ok \d+ bats_join_by\b", out), (
            "new @test bats_join_by did not run/pass under bats:\n%s" % out
        )

    def test_native_full_common_bats_suite_passes(self):
        """L2: the full `bin/bats test/common.bats` suite exits 0 with every
        test (including the new one) passing -- the task's acceptance command."""
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
        assert re.search(r"(?m)^ok \d+ bats_join_by\b", out), (
            "the new test must appear and pass in the full suite output:\n%s" % out
        )
        assert "not ok" not in out, "no test in the suite may fail:\n%s" % out
        oks = re.findall(r"(?m)^ok \d+ ", out)
        assert len(oks) >= 10, (
            "expected >=10 passing tests in common.bats (existing + new), saw "
            "%d:\n%s" % (len(oks), out)
        )


def _shq(s):
    """Single-quote a string for safe embedding in a bash command."""
    return "'" + s.replace("'", "'\\''") + "'"
