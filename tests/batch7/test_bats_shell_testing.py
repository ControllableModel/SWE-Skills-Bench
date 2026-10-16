"""Tests for the `bats-shell-testing` skill task (variant ext7):
a sorted-array occurrence counter helper.

Skill: bats-shell-testing
Task: Add a helper

    bats_count_in_sorted <output-variable> <search-value> <sorted-array-name>

to `lib/bats-core/common.bash`, plus a `@test bats_count_in_sorted` block in
`test/common.bats`. The helper writes the number of elements equal to the
search value (in an already ascending-string-sorted array referenced *by name*)
into the named output variable, and returns exit status 0 when that count is
>= 1, non-zero when the count is 0 (value absent). On the absent case the output
variable is still set to 0.

Verification strategy
---------------------
  * L1: the two deliverable files exist; the new function definition and the new
        `@test bats_count_in_sorted` block are present; the helper is
        self-contained (no grep -c / wc / awk / external programs) and sources
        cleanly, exposing the function.
  * L2: dynamic behavior, exercised INDEPENDENTLY of the agent's own .bats test.
        We source common.bash, build a real sorted array, call the helper with
        an output variable, and read back BOTH the written count and the exit
        status for every Expected-Functionality scenario from the doc:
        run-of-duplicates, first/last single occurrences, gap-absent,
        below-all absent, above-all absent, empty array, empty-string search
        value, and "reference array by name" semantics. We also run the native
        acceptance command `./bin/bats test/common.bats` and assert it exits 0
        with the new block present and no failing tests.

A naive implementation that hardcodes a count, ignores duplicates, returns
success on absent values, or fails to set the output variable to 0 on the
absent case will FAIL these direct-execution cases even if it ships a
passing-looking @test block.
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

    def _count(self, array_elems, search_value):
        """Source common.bash, declare a sorted array from `array_elems`, call
        bats_count_in_sorted writing into `cnt`, and return (returncode, count).

        `count` is the integer the helper wrote into the output variable, or
        None if it wrote nothing / something non-numeric. The helper call runs
        in the current shell (not a subshell) so the output-variable assignment
        is observable, but we still guard our harness with `set +e` so a
        non-zero return does not abort the script before we print the markers.

        Array elements and the search value are passed through argv to avoid any
        quoting surprises with empty strings or odd characters.
        """
        # argv layout: <common.bash> <search-value> <n-elems> <elem...>
        argv_elems = list(array_elems)
        script = r'''
set +e
source "$1"; shift
search_value=$1; shift
n=$1; shift
arr=()
i=0
while [ "$i" -lt "$n" ]; do
  arr+=( "$1" ); shift
  i=$((i + 1))
done
cnt=__UNSET__
bats_count_in_sorted cnt "$search_value" arr
rc=$?
printf '__CNT__=%s\n' "$cnt"
printf '__RC__=%s\n' "$rc"
'''
        cmd = [
            "bash",
            "-c",
            script,
            "bash",  # $0
            self.COMMON_BASH,  # $1
            search_value,  # search value
            str(len(argv_elems)),  # element count
        ] + argv_elems
        proc = subprocess.run(
            cmd,
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=60,
        )
        rc_m = re.search(r"__RC__=(-?\d+)", proc.stdout)
        assert rc_m is not None, (
            "could not determine helper exit code; stdout=%r stderr=%r"
            % (proc.stdout, proc.stderr)
        )
        rc = int(rc_m.group(1))
        cnt_m = re.search(r"__CNT__=(.*)", proc.stdout)
        cnt_raw = cnt_m.group(1).strip() if cnt_m else None
        count = int(cnt_raw) if cnt_raw is not None and re.fullmatch(r"-?\d+", cnt_raw) else None
        return rc, count

    # --------------------------------------------------------------------- L1

    def test_repo_and_files_present(self):
        """L1: REPO_DIR, both deliverable files, and the bats runner exist."""
        assert os.path.isdir(self.REPO_DIR), "missing repo dir %s" % self.REPO_DIR
        assert os.path.isfile(self.COMMON_BASH), "missing %s" % self.COMMON_BASH
        assert os.path.isfile(self.COMMON_BATS), "missing %s" % self.COMMON_BATS
        assert os.path.isfile(self.BATS_BIN), "missing bats runner %s" % self.BATS_BIN

    def test_function_defined_in_common_bash(self):
        """L1: a `bats_count_in_sorted` function definition was added to common.bash."""
        with open(self.COMMON_BASH) as f:
            content = f.read()
        assert re.search(
            r"(?m)^\s*(function\s+)?bats_count_in_sorted\s*\(\s*\)",
            content,
        ), "no bats_count_in_sorted function definition found in common.bash"

    def test_new_test_block_present(self):
        """L1: a `@test bats_count_in_sorted` block was added to common.bats."""
        with open(self.COMMON_BATS) as f:
            content = f.read()
        assert re.search(
            r'@test\s+(bats_count_in_sorted\b|"bats_count_in_sorted"|'
            r"'bats_count_in_sorted')",
            content,
        ), "no `@test bats_count_in_sorted` block found in common.bats"

    def test_helper_is_self_contained(self):
        """L1: the new helper uses no external programs for counting.

        The doc forbids grep -c / wc / awk and requires a pure shell impl, so we
        isolate the function body and assert none of those tools appear in it."""
        with open(self.COMMON_BASH) as f:
            content = f.read()
        m = re.search(
            r"(?ms)^\s*(?:function\s+)?bats_count_in_sorted\s*\(\s*\).*?\n\}",
            content,
        )
        assert m is not None, "could not isolate bats_count_in_sorted body"
        body = m.group(0)
        for forbidden in ("grep", "wc", "awk", "sed", "python", "perl", "sort "):
            assert forbidden not in body, (
                "helper must be pure shell; found external program %r in body"
                % forbidden
            )

    def test_helper_is_sourceable(self):
        """L1/L2 bridge: common.bash sources cleanly and exposes the new function."""
        script = (
            "source '%s'\n"
            "type -t bats_count_in_sorted\n" % self.COMMON_BASH
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
            "bats_count_in_sorted is not a defined function after sourcing; got %r"
            % proc.stdout
        )

    # --------------------------------------------------------------------- L2

    def test_run_of_duplicates_counted(self):
        """L2: (a b b b c) searched for b -> count 3, success (rc 0).

        A stub that returns presence (1) without counting consecutive duplicates
        fails here."""
        rc, count = self._count(["a", "b", "b", "b", "c"], "b")
        assert count == 3, "expected count 3 for 'b' in (a b b b c), got %r" % count
        assert rc == 0, "count>=1 must yield success (rc 0), rc=%d" % rc

    def test_first_element_single_occurrence(self):
        """L2: (a b c) searched for a (boundary, first element) -> count 1, success."""
        rc, count = self._count(["a", "b", "c"], "a")
        assert count == 1, "expected count 1 for first element 'a', got %r" % count
        assert rc == 0, "present value must yield rc 0, rc=%d" % rc

    def test_last_element_single_occurrence(self):
        """L2: (a b c) searched for c (boundary, last element) -> count 1, success."""
        rc, count = self._count(["a", "b", "c"], "c")
        assert count == 1, "expected count 1 for last element 'c', got %r" % count
        assert rc == 0, "present value must yield rc 0, rc=%d" % rc

    def test_absent_in_gap_count_zero_nonzero_status(self):
        """L2: (a c e) searched for b (falls in a gap) -> count 0 AND non-zero rc.

        Verifies both halves of the contract: the output variable is set to 0
        and the status signals absence."""
        rc, count = self._count(["a", "c", "e"], "b")
        assert count == 0, "absent value in gap must write count 0, got %r" % count
        assert rc != 0, "absent value must yield non-zero status, rc=%d" % rc

    def test_below_all_elements_absent(self):
        """L2: (b c d) searched for a (smaller than every element) -> count 0, non-zero."""
        rc, count = self._count(["b", "c", "d"], "a")
        assert count == 0, "below-all value must write count 0, got %r" % count
        assert rc != 0, "below-all value must yield non-zero status, rc=%d" % rc

    def test_above_all_elements_absent(self):
        """L2: (a b c) searched for z (larger than every element) -> count 0, non-zero."""
        rc, count = self._count(["a", "b", "c"], "z")
        assert count == 0, "above-all value must write count 0, got %r" % count
        assert rc != 0, "above-all value must yield non-zero status, rc=%d" % rc

    def test_empty_array_absent(self):
        """L2: an empty array, searched for anything -> count 0 and non-zero status."""
        rc, count = self._count([], "x")
        assert count == 0, "empty array must write count 0, got %r" % count
        assert rc != 0, "empty array must yield non-zero status, rc=%d" % rc

    def test_empty_string_search_value(self):
        """L2: the search value may be the empty string.

        With ("" "" a) the empty string occurs twice -> count 2, success; with a
        non-empty array lacking it -> count 0, non-zero. Equality is exact string
        comparison, so the empty string is a legitimate, countable value."""
        rc_present, count_present = self._count(["", "", "a"], "")
        assert count_present == 2, (
            "empty-string value occurs twice -> count 2, got %r" % count_present
        )
        assert rc_present == 0, "present empty-string must yield rc 0, rc=%d" % rc_present

        rc_absent, count_absent = self._count(["a", "b", "c"], "")
        assert count_absent == 0, (
            "empty string absent from (a b c) -> count 0, got %r" % count_absent
        )
        assert rc_absent != 0, "absent empty-string must yield non-zero rc, rc=%d" % rc_absent

    def test_all_elements_equal(self):
        """L2: an array that is entirely one value (b b b b) searched for b -> count 4.

        Stresses the consecutive-run counting at both array boundaries."""
        rc, count = self._count(["b", "b", "b", "b"], "b")
        assert count == 4, "all-equal array (b b b b) for 'b' -> count 4, got %r" % count
        assert rc == 0, "present value must yield rc 0, rc=%d" % rc

    def test_single_element_matches_and_misses(self):
        """L2: single-element arrays behave correctly for both hit and miss.

        (b) searched for b -> count 1 success; (b) searched for a or c -> count 0,
        non-zero. Discriminates an off-by-one that mishandles length-1 arrays."""
        rc_hit, c_hit = self._count(["b"], "b")
        assert c_hit == 1 and rc_hit == 0, "single-element hit -> count 1, rc 0; got %r/%d" % (c_hit, rc_hit)
        rc_lo, c_lo = self._count(["b"], "a")
        assert c_lo == 0 and rc_lo != 0, "single-element below -> count 0, non-zero; got %r/%d" % (c_lo, rc_lo)
        rc_hi, c_hi = self._count(["b"], "c")
        assert c_hi == 0 and rc_hi != 0, "single-element above -> count 0, non-zero; got %r/%d" % (c_hi, rc_hi)

    def test_reference_array_by_name_not_expanded(self):
        """L2: the helper must reference the array BY NAME, not by a value-expanded
        copy at the call site.

        We pass the *name* `arr` (as the contract requires) and confirm the count
        reflects the array's real contents. If an implementation wrongly expected
        the elements expanded inline (e.g. treated arg 3 as a literal value), the
        duplicate run below would not be counted as 3."""
        rc, count = self._count(["x", "y", "y", "y", "z"], "y")
        assert count == 3, (
            "by-name reference must see the real array contents (count 3), got %r" % count
        )
        assert rc == 0, "present value must yield rc 0, rc=%d" % rc

    def test_existing_helpers_unchanged(self):
        """L2: pre-existing sorted-array helpers still behave after the edit.

        Spot-checks bats_binary_search (found -> 0, absent -> 1) and bats_any_in
        so a solution that 'helpfully' refactors shared code without preserving
        behavior is caught."""
        script = (
            "set +e\n"
            "source '%s'\n"
            "arr=(1 2 3)\n"
            "( bats_binary_search 2 arr ); echo \"FOUND=$?\"\n"
            "( bats_binary_search 9 arr ); echo \"MISS=$?\"\n"
            "( bats_any_in arr 2 ); echo \"ANY=$?\"\n"
            "( bats_any_in arr 9 ); echo \"NOANY=$?\"\n" % self.COMMON_BASH
        )
        proc = subprocess.run(
            ["bash", "-c", script],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert "FOUND=0" in proc.stdout, "bats_binary_search must still find present value (rc 0)"
        assert "MISS=1" in proc.stdout, "bats_binary_search must still return 1 for absent value"
        assert "ANY=0" in proc.stdout, "bats_any_in must still return 0 when value present"
        assert "NOANY=1" in proc.stdout, "bats_any_in must still return 1 when value absent"

    def test_native_new_test_block_passes(self):
        """L2: the agent's new @test bats_count_in_sorted passes under the real bats
        runner (filtered to just that block)."""
        proc = subprocess.run(
            [self.BATS_BIN, "--filter", "bats_count_in_sorted", "test/common.bats"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=300,
        )
        out = proc.stdout + proc.stderr
        assert proc.returncode == 0, (
            "native run of `bats --filter bats_count_in_sorted test/common.bats` "
            "failed (rc=%d):\n%s" % (proc.returncode, out)
        )
        assert re.search(r"(?m)^ok \d+ bats_count_in_sorted\b", out), (
            "new @test bats_count_in_sorted did not run/pass under bats:\n%s" % out
        )

    def test_native_full_common_bats_suite_passes(self):
        """L2: the full `./bin/bats test/common.bats` suite exits 0 with every test
        (including the new one) passing -- the task's native acceptance command."""
        proc = subprocess.run(
            [self.BATS_BIN, "test/common.bats"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=300,
        )
        out = proc.stdout + proc.stderr
        assert proc.returncode == 0, (
            "`./bin/bats test/common.bats` must exit 0; rc=%d\n%s"
            % (proc.returncode, out)
        )
        assert "bats_count_in_sorted" in out, (
            "the new test must appear in the suite output:\n%s" % out
        )
        assert "not ok" not in out, "no test in the suite may fail:\n%s" % out
        oks = re.findall(r"(?m)^ok \d+ ", out)
        assert len(oks) >= 10, (
            "expected >=10 passing tests in common.bats, saw %d:\n%s"
            % (len(oks), out)
        )
