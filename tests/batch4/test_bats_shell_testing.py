"""Tests for the `bats-shell-testing` skill task (variant ext4): an
order-preserving array deduplication helper.

Skill: bats-shell-testing
Task: Add a `bats_array_unique <result-array-name> <values...>` helper to
`lib/bats-core/common.bash` (mirroring the `bats_sort` calling convention) that
populates the named result array with the input values, removing duplicates
while preserving first-seen order. Also add a `@test bats_array_unique` block to
`test/common.bats` exercising the helper's full behavior.

Verification strategy, against the real repo at REPO_DIR:
  * L1: the two deliverable files exist; the `bats_array_unique` function is
    defined in common.bash; a `@test bats_array_unique` block exists in
    common.bats; the helper is self-contained (no sort/uniq/awk/etc.) and
    sourceable.
  * L2: dynamic behavior, by sourcing common.bash and calling the helper
    DIRECTLY in an isolated subshell, capturing the resulting array's length and
    each element verbatim (via a NUL-free unambiguous marker), for every
    Expected Functionality scenario in the doc: order-preserving dedup, input-
    order-not-sorted, empty input -> length 0, distinct strings (1 vs 1.0),
    space-containing elements kept whole, empty-string collapse, exact (non-glob)
    equality, array reset across calls, and exit status 0. The native
    `bin/bats test/common.bats` acceptance command is also run so the agent's
    own @test block passes alongside the rest of the suite.

The direct-execution L2 cases are written independently of the agent's own .bats
test, so a stub that merely adds a passing-looking @test (or a function that
sorts, or appends instead of resetting, or ignores values) fails here.
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

    # Unambiguous element delimiters that cannot appear in our test inputs.
    _SEP = "<|SEP|>"
    _LEN = "__LEN__="
    _RC = "__RC__="

    # ------------------------------------------------------------------ helpers

    def _run_unique(self, *values):
        """Source common.bash, call `bats_array_unique out <values...>` in an
        isolated subshell, and return (returncode, length, elements_list).

        The resulting array is emitted element-by-element joined by a distinctive
        separator so elements containing spaces / shell-special chars / empty
        strings round-trip verbatim. The helper call is wrapped in `( ... )` so an
        implementation that uses `exit` cannot kill the harness shell, and its
        exit status is captured separately.
        """
        quoted = " ".join("'%s'" % v.replace("'", "'\\''") for v in values)
        script = (
            "set +e\n"
            "source '%(bash)s'\n"
            "out=(SHOULD_BE_OVERWRITTEN PRIOR_LEAK)\n"  # pre-seed to catch non-reset
            "( bats_array_unique out %(args)s ); rc=$?\n"
            "printf '%(rc)s%%d\\n' \"$rc\"\n"
            "printf '%(len)s%%d\\n' \"${#out[@]}\"\n"
            "joined=\"\"\n"
            "for ((i=0; i<${#out[@]}; i++)); do\n"
            "  if ((i>0)); then joined+='%(sep)s'; fi\n"
            "  joined+=\"${out[i]}\"\n"
            "done\n"
            "printf '__ELEMS__=%%s\\n' \"$joined\"\n"
            % {
                "bash": self.COMMON_BASH,
                "args": quoted,
                "rc": self._RC,
                "len": self._LEN,
                "sep": self._SEP,
            }
        )
        proc = subprocess.run(
            ["bash", "-c", script],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=60,
        )
        rc_m = re.search(re.escape(self._RC) + r"(-?\d+)", proc.stdout)
        len_m = re.search(re.escape(self._LEN) + r"(\d+)", proc.stdout)
        assert rc_m is not None and len_m is not None, (
            "could not parse helper output; stdout=%r stderr=%r"
            % (proc.stdout, proc.stderr)
        )
        rc = int(rc_m.group(1))
        length = int(len_m.group(1))
        elems_m = re.search(r"__ELEMS__=(.*)", proc.stdout, re.S)
        raw = elems_m.group(1) if elems_m else ""
        # Trailing newline from printf; strip exactly one.
        if raw.endswith("\n"):
            raw = raw[:-1]
        if length == 0:
            elements = []
        else:
            elements = raw.split(self._SEP)
        # Defensive: reconcile reported length with parsed elements.
        assert len(elements) == length, (
            "element count %d disagrees with reported length %d (raw=%r)"
            % (len(elements), length, raw)
        )
        return rc, length, elements

    # --------------------------------------------------------------------- L1

    def test_repo_and_files_present(self):
        """L1: REPO_DIR, the two deliverable files, and the bats runner exist."""
        assert os.path.isdir(self.REPO_DIR), "missing repo dir %s" % self.REPO_DIR
        assert os.path.isfile(self.COMMON_BASH), "missing %s" % self.COMMON_BASH
        assert os.path.isfile(self.COMMON_BATS), "missing %s" % self.COMMON_BATS
        assert os.path.isfile(self.BATS_BIN), "missing bats runner %s" % self.BATS_BIN

    def test_function_defined_in_common_bash(self):
        """L1: a `bats_array_unique` function definition was added to common.bash."""
        with open(self.COMMON_BASH) as f:
            content = f.read()
        assert re.search(
            r"(?m)^\s*(function\s+)?bats_array_unique\s*\(\s*\)",
            content,
        ), "no bats_array_unique function definition found in common.bash"

    def test_new_test_block_present(self):
        """L1: a `@test bats_array_unique` block was added to common.bats."""
        with open(self.COMMON_BATS) as f:
            content = f.read()
        assert re.search(
            r'@test\s+(bats_array_unique\b|"bats_array_unique"|'
            r"'bats_array_unique')",
            content,
        ), "no `@test bats_array_unique` block found in common.bats"

    def test_helper_is_self_contained(self):
        """L1: the helper body uses no external dedup programs (sort/uniq/awk/...)."""
        with open(self.COMMON_BASH) as f:
            content = f.read()
        m = re.search(
            r"(?ms)^\s*(?:function\s+)?bats_array_unique\s*\(\s*\).*?\n\}",
            content,
        )
        assert m is not None, "could not isolate bats_array_unique function body"
        body = m.group(0)
        for forbidden in ("sort", "uniq", "awk", "python", "perl", "tr ", "sed"):
            assert forbidden not in body, (
                "helper must be self-contained/pure; found external use of %r" % forbidden
            )

    def test_helper_is_sourceable(self):
        """L1/L2 bridge: common.bash sources cleanly and exposes the new function."""
        script = (
            "source '%s'\n"
            "type -t bats_array_unique\n" % self.COMMON_BASH
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
            "bats_array_unique is not a defined function after sourcing; got %r"
            % proc.stdout
        )

    # --------------------------------------------------------------------- L2

    def test_basic_dedup_preserves_first_seen_order(self):
        """L2: `out a b a c b` -> (a b c), each distinct value at first occurrence."""
        rc, length, elems = self._run_unique("a", "b", "a", "c", "b")
        assert rc == 0, "helper must return status 0, got %d" % rc
        assert length == 3, "expected 3 distinct elements, got %d (%r)" % (length, elems)
        assert elems == ["a", "b", "c"], (
            "first-seen order not preserved; expected [a,b,c], got %r" % elems
        )

    def test_output_is_input_ordered_not_sorted(self):
        """L2: `out c b a` -> (c b a). Proves output follows input order, NOT a sort
        (a sorting implementation would yield [a,b,c] and fail here)."""
        rc, length, elems = self._run_unique("c", "b", "a")
        assert rc == 0, "helper must return status 0, got %d" % rc
        assert length == 3, "expected 3 elements, got %d (%r)" % (length, elems)
        assert elems == ["c", "b", "a"], (
            "output must be input-ordered, not sorted; expected [c,b,a], got %r" % elems
        )

    def test_empty_input_yields_empty_array(self):
        """L2: with no values the result array is empty (length 0) and rc 0.

        Also confirms the pre-seeded `out` was reset rather than left intact."""
        rc, length, elems = self._run_unique()
        assert rc == 0, "no-value call must return status 0, got %d" % rc
        assert length == 0, "expected empty result, got length %d (%r)" % (length, elems)
        assert elems == [], "expected empty array, got %r" % elems

    def test_distinct_strings_not_numeric(self):
        """L2: `out 1 1.0 1` -> (1 1.0). 1 and 1.0 are DISTINCT strings; the trailing
        duplicate 1 collapses."""
        rc, length, elems = self._run_unique("1", "1.0", "1")
        assert rc == 0, "helper must return status 0, got %d" % rc
        assert length == 2, "1 and 1.0 are distinct; expected 2, got %d (%r)" % (
            length, elems,
        )
        assert elems == ["1", "1.0"], (
            "expected [1, 1.0] (distinct strings, dup 1 removed), got %r" % elems
        )

    def test_space_containing_elements_kept_whole(self):
        """L2: `out "a b" "a b" x` -> ("a b" x). Space-containing value is one
        element and its duplicate collapses; a naive word-splitting impl would
        explode "a b" into two elements and fail."""
        rc, length, elems = self._run_unique("a b", "a b", "x")
        assert rc == 0, "helper must return status 0, got %d" % rc
        assert length == 2, (
            "space-containing element must stay whole; expected 2 elements, got %d (%r)"
            % (length, elems)
        )
        assert elems == ["a b", "x"], (
            "expected ['a b', 'x']; got %r" % elems
        )

    def test_empty_string_collapse(self):
        """L2: `out "" "" y` -> ("" y). Two empty-string values collapse to one
        retained empty element, followed by y."""
        rc, length, elems = self._run_unique("", "", "y")
        assert rc == 0, "helper must return status 0, got %d" % rc
        assert length == 2, (
            "two empty strings must collapse to one element; expected 2, got %d (%r)"
            % (length, elems)
        )
        assert elems == ["", "y"], (
            "expected ['', 'y'] (single retained empty string then y); got %r" % elems
        )

    def test_single_empty_string_retained(self):
        """L2: a single empty-string value is retained as exactly one element."""
        rc, length, elems = self._run_unique("")
        assert rc == 0, "helper must return status 0, got %d" % rc
        assert length == 1, (
            "single empty string must be retained as one element; got length %d (%r)"
            % (length, elems)
        )
        assert elems == [""], "expected [''], got %r" % elems

    def test_exact_equality_not_glob(self):
        """L2: duplicate detection is exact string equality, not glob matching.
        `* * a b` -> only the literal `*` collapses; `*` must NOT match `a`/`b`."""
        rc, length, elems = self._run_unique("*", "*", "a", "b")
        assert rc == 0, "helper must return status 0, got %d" % rc
        assert length == 3, (
            "glob '*' must match only literal '*'; expected 3 elements, got %d (%r)"
            % (length, elems)
        )
        assert elems == ["*", "a", "b"], (
            "expected ['*', 'a', 'b'] (exact equality, no glob expansion); got %r"
            % elems
        )

    def test_all_duplicates_collapse_to_one(self):
        """L2: `out z z z z` -> (z), a single element."""
        rc, length, elems = self._run_unique("z", "z", "z", "z")
        assert rc == 0, "helper must return status 0, got %d" % rc
        assert length == 1, "all-duplicate input must collapse to one; got %d (%r)" % (
            length, elems,
        )
        assert elems == ["z"], "expected ['z'], got %r" % elems

    def test_result_array_is_reset_across_calls(self):
        """L2: the result array is fully reset each call; a value present from a
        prior call (or pre-existing in the variable) must NOT leak.

        Two sequential calls into the same variable: the second result must equal
        only the second call's distinct values, with no residue from the first.
        """
        script = (
            "set +e\n"
            "source '%(bash)s'\n"
            "bats_array_unique out a b c\n"
            "bats_array_unique out x y\n"  # second call must drop a,b,c entirely
            "printf '%(len)s%%d\\n' \"${#out[@]}\"\n"
            "joined=\"\"\n"
            "for ((i=0; i<${#out[@]}; i++)); do\n"
            "  if ((i>0)); then joined+='%(sep)s'; fi\n"
            "  joined+=\"${out[i]}\"\n"
            "done\n"
            "printf '__ELEMS__=%%s\\n' \"$joined\"\n"
            % {
                "bash": self.COMMON_BASH,
                "len": self._LEN,
                "sep": self._SEP,
            }
        )
        proc = subprocess.run(
            ["bash", "-c", script],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=60,
        )
        len_m = re.search(re.escape(self._LEN) + r"(\d+)", proc.stdout)
        assert len_m is not None, (
            "could not parse reset-test output; stdout=%r stderr=%r"
            % (proc.stdout, proc.stderr)
        )
        length = int(len_m.group(1))
        elems_m = re.search(r"__ELEMS__=(.*)", proc.stdout, re.S)
        raw = (elems_m.group(1) if elems_m else "")
        if raw.endswith("\n"):
            raw = raw[:-1]
        elements = [] if length == 0 else raw.split(self._SEP)
        assert length == 2, (
            "second call must reset; expected length 2 (x,y), got %d (%r) -- "
            "leaked prior values?" % (length, elements)
        )
        assert elements == ["x", "y"], (
            "result array not reset across calls; expected ['x','y'], got %r" % elements
        )

    def test_always_returns_zero_status(self):
        """L2: the helper always exits 0 across representative inputs (empty,
        single, duplicates, special chars)."""
        for args in ([], [""], ["a"], ["a", "a"], ["a b", "*", ""], ["1", "1.0"]):
            rc, _len, _elems = self._run_unique(*args)
            assert rc == 0, "bats_array_unique must return 0 for args=%r, got %d" % (
                args, rc,
            )

    def test_native_new_test_block_passes(self):
        """L2: the agent's new `@test bats_array_unique` passes under the real bats
        runner (filtered to just that block, and confirmed to actually run)."""
        proc = subprocess.run(
            [self.BATS_BIN, "--filter", "bats_array_unique", "test/common.bats"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=300,
        )
        out = proc.stdout + proc.stderr
        assert proc.returncode == 0, (
            "native `bats --filter bats_array_unique test/common.bats` failed "
            "(rc=%d):\n%s" % (proc.returncode, out)
        )
        assert re.search(r"(?m)^ok \d+ bats_array_unique\b", out), (
            "new @test bats_array_unique did not run/pass under bats:\n%s" % out
        )

    def test_native_full_common_bats_suite_passes(self):
        """L2: the full `bin/bats test/common.bats` acceptance command exits 0 with
        every test (including the new one) passing and none failing."""
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
        assert "bats_array_unique" in out, (
            "the new test must appear in the suite output:\n%s" % out
        )
        assert "not ok" not in out, "no test in the suite may fail:\n%s" % out
        # sanity: the original 11 documented tests + the new one should report >=12.
        oks = re.findall(r"(?m)^ok \d+ ", out)
        assert len(oks) >= 12, (
            "expected >=12 passing tests in common.bats, saw %d:\n%s"
            % (len(oks), out)
        )
