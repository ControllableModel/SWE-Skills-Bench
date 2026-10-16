"""Tests for the `bats-shell-testing` skill task (ext3 variant): an array index-of helper.

Skill: bats-shell-testing
Task (ext3): Add a helper

    bats_array_index_of <output-variable> <search-value> <array-name>

to `lib/bats-core/common.bash`, plus a `@test bats_array_index_of` block in
`test/common.bats`. The helper scans an array (passed BY NAME, like the existing
`bats_linear_reverse_search` / `bats_binary_search` helpers) from the lowest index
upward, writes the zero-based index of the FIRST element equal to <search-value>
into the variable named by <output-variable> and returns 0; on a miss it returns
non-zero and leaves the output variable untouched.

Verification strategy (grounded in the ext3 requirement doc, NOT ext1):
  * L1: the two deliverable files exist, the new function definition is present in
        common.bash, the new `@test bats_array_index_of` block is present in
        common.bats, the helper is self-contained (no external programs), and it
        sources cleanly and is a real function.
  * L2: dynamic behavior. We drive the helper directly in isolated subshells for
        EVERY Expected-Functionality scenario from the doc -- found-in-the-middle,
        first-of-duplicates, not-found (with the output variable proven untouched),
        empty array, empty-string match, literal space-containing match, and
        no-substring matching -- capturing the exit code AND the value written to
        the output variable. These checks are written independently of the agent's
        own .bats test, so a solution that merely adds a passing-looking @test block
        without a correct implementation (or a stub that hardcodes an index / ignores
        an argument) WILL fail here. Finally we run the native acceptance command
        `bin/bats test/common.bats` so the agent's new @test passes alongside the
        whole pre-existing suite.
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

    def _call(self, search_value, array_setup, out_var="result"):
        """Source common.bash, set up an array, call bats_array_index_of, and report
        back the exit code and the post-call value of the output variable.

        Parameters
        ----------
        search_value : str
            The value to search for (passed literally, single-quoted).
        array_setup : str
            A snippet of bash that declares the array named ``arr`` (e.g.
            ``arr=(a b c)`` or ``arr=()``).
        out_var : str
            Name of the output variable to pass as the first argument.

        Returns (returncode, out_present, out_value):
          * returncode  -- the helper's exit status
          * out_present -- True iff the output variable was *set* after the call
                           (so we can prove a miss leaves it untouched/unset)
          * out_value   -- the string value of the output variable (or "" if unset)

        The helper is invoked WITHOUT a wrapping subshell so that the value it
        writes into the (caller-scoped) output variable is observable here.
        Quoting defends against empty / special-character inputs. We pre-unset the
        output variable so "untouched on miss" is detectable.
        """
        script = (
            "set +e\n"
            "source '%s'\n"
            "%s\n"
            "unset %s\n"
            "bats_array_index_of %s '%s' arr\n"
            "echo \"__RC__=$?\"\n"
            "if [[ -n \"${%s+x}\" ]]; then\n"
            "  echo \"__SET__=1\"\n"
            "  echo \"__VAL__=${%s}\"\n"
            "else\n"
            "  echo \"__SET__=0\"\n"
            "fi\n"
            % (self.COMMON_BASH, array_setup, out_var, out_var,
               search_value, out_var, out_var)
        )
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
        m_set = re.search(r"__SET__=(\d)", proc.stdout)
        out_present = bool(m_set and m_set.group(1) == "1")
        m_val = re.search(r"__VAL__=(.*)", proc.stdout)
        out_value = m_val.group(1) if m_val else ""
        return rc, out_present, out_value

    # --------------------------------------------------------------------- L1

    def test_repo_and_files_present(self):
        """L1: REPO_DIR, the two deliverable files, and the bats runner all exist."""
        assert os.path.isdir(self.REPO_DIR), "missing repo dir %s" % self.REPO_DIR
        assert os.path.isfile(self.COMMON_BASH), "missing %s" % self.COMMON_BASH
        assert os.path.isfile(self.COMMON_BATS), "missing %s" % self.COMMON_BATS
        assert os.path.isfile(self.BATS_BIN), "missing bats runner %s" % self.BATS_BIN

    def test_function_defined_in_common_bash(self):
        """L1: a `bats_array_index_of` function definition was added to common.bash."""
        with open(self.COMMON_BASH) as f:
            content = f.read()
        assert re.search(
            r"(?m)^\s*(function\s+)?bats_array_index_of\s*\(\s*\)",
            content,
        ), "no bats_array_index_of function definition found in common.bash"

    def test_new_test_block_present(self):
        """L1: a `@test bats_array_index_of` block was added to common.bats."""
        with open(self.COMMON_BATS) as f:
            content = f.read()
        assert re.search(
            r'@test\s+(bats_array_index_of\b|"bats_array_index_of"|'
            r"'bats_array_index_of')",
            content,
        ), "no `@test bats_array_index_of` block found in common.bats"

    def test_helper_is_self_contained(self):
        """L1: the helper body introduces no external program / filesystem / network
        dependency (it must be pure per the doc's Constraints)."""
        with open(self.COMMON_BASH) as f:
            content = f.read()
        m = re.search(
            r"(?ms)^\s*(?:function\s+)?bats_array_index_of\s*\(\s*\).*?\n\}",
            content,
        )
        assert m is not None, "could not isolate bats_array_index_of body"
        body = m.group(0)
        for forbidden in ("awk", "grep", "sed", "python", "perl", "curl", "wget",
                          " cat ", "mktemp"):
            assert forbidden not in body, (
                "helper must be self-contained: found external/forbidden token %r"
                % forbidden
            )

    def test_helper_is_sourceable_and_is_function(self):
        """L1/L2 bridge: common.bash sources cleanly and exposes the new function."""
        script = (
            "source '%s'\n"
            "type -t bats_array_index_of\n" % self.COMMON_BASH
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
            "bats_array_index_of is not a defined function after sourcing; got %r"
            % proc.stdout
        )

    # --------------------------------------------------------------------- L2

    def test_found_in_middle(self):
        """L2: array (a b c), search 'b' -> success, index 1 written to out var."""
        rc, present, val = self._call("b", "arr=(a b c)")
        assert rc == 0, "search 'b' in (a b c) must succeed, rc=%d" % rc
        assert present, "output variable must be set on a match"
        assert val == "1", "index of 'b' in (a b c) must be 1, got %r" % val

    def test_found_at_index_zero(self):
        """L2: array (a b c), search 'a' -> success, index 0 (boundary: lowest idx)."""
        rc, present, val = self._call("a", "arr=(a b c)")
        assert rc == 0, "search 'a' in (a b c) must succeed, rc=%d" % rc
        assert present and val == "0", (
            "index of 'a' must be 0 (the helper must report the literal 0, not "
            "treat 0 as a miss); rc=%d present=%s val=%r" % (rc, present, val)
        )

    def test_found_at_last_index(self):
        """L2: array (a b c), search 'c' -> success, index 2 (scans full array)."""
        rc, present, val = self._call("c", "arr=(a b c)")
        assert rc == 0, "search 'c' in (a b c) must succeed, rc=%d" % rc
        assert present and val == "2", "index of 'c' must be 2, got %r" % val

    def test_first_of_duplicates(self):
        """L2: array (x y x z), search 'x' -> index 0 (LOWEST index, not last).

        A reverse-scanning or last-match implementation would return 2 here and
        must fail."""
        rc, present, val = self._call("x", "arr=(x y x z)")
        assert rc == 0, "search 'x' in (x y x z) must succeed, rc=%d" % rc
        assert present and val == "0", (
            "first occurrence of 'x' is index 0, not the last; got %r" % val
        )

    def test_not_found_leaves_output_untouched(self):
        """L2: array (a b c), search 'd' -> non-zero rc AND the output variable is
        left unset/untouched (the doc requires the out var not be modified on miss).

        A stub that always writes an index (e.g. -1 or 0) is caught here."""
        rc, present, val = self._call("d", "arr=(a b c)")
        assert rc != 0, "search 'd' in (a b c) must miss (non-zero), rc=%d" % rc
        assert not present, (
            "on a miss the output variable must NOT be set; it was set to %r" % val
        )

    def test_empty_array_misses(self):
        """L2: an empty array yields a miss for any search value (non-zero rc, out
        var untouched)."""
        rc, present, val = self._call("a", "arr=()")
        assert rc != 0, "empty array must miss, rc=%d" % rc
        assert not present, "empty-array miss must not set the output variable"

    def test_empty_string_is_a_valid_match(self):
        """L2: array ("" b), search '' -> index 0 (the empty string is a valid,
        matchable element; a miss here would be wrong)."""
        rc, present, val = self._call("", 'arr=("" b)')
        assert rc == 0, "empty-string element must be matchable, rc=%d" % rc
        assert present and val == "0", (
            "empty string matches the element at index 0, got rc=%d val=%r"
            % (rc, val)
        )

    def test_empty_string_search_misses_when_absent(self):
        """L2: searching '' in (a b) (no empty element) is a miss -- the empty search
        value is not a wildcard."""
        rc, present, val = self._call("", "arr=(a b)")
        assert rc != 0, "empty-string search in (a b) must miss, rc=%d" % rc
        assert not present, "missing empty-string search must not set output var"

    def test_literal_space_containing_match(self):
        """L2: array ("a b" c), search 'a b' -> index 0. The element with a space is
        matched literally (no word-splitting). A naive implementation that expands
        the array at the call site or splits on whitespace would mis-index here."""
        rc, present, val = self._call("a b", 'arr=("a b" c)')
        assert rc == 0, "literal 'a b' must match the first element, rc=%d" % rc
        assert present and val == "0", (
            "index of literal 'a b' must be 0 (no word-splitting), got rc=%d val=%r"
            % (rc, val)
        )

    def test_no_substring_or_glob_matching(self):
        """L2: matching is EXACT string equality, not substring/glob.

        * (ab cd), search 'a'  -> miss   (not a substring match of 'ab')
        * (foo bar), search '*' -> miss  ('*' must be compared literally, not as a
                                          glob that would match everything)
        """
        rc1, present1, _ = self._call("a", "arr=(ab cd)")
        assert rc1 != 0, "'a' is not equal to 'ab'/'cd' -> must miss, rc=%d" % rc1
        assert not present1, "substring non-match must not set the output variable"

        rc2, present2, val2 = self._call("*", "arr=(foo bar)")
        assert rc2 != 0, (
            "'*' must be matched literally (no globbing); searching '*' in "
            "(foo bar) must miss, rc=%d val=%r" % (rc2, val2)
        )
        assert not present2, "glob-literal non-match must not set the output variable"

    def test_special_char_literal_match(self):
        """L2: a search value containing shell-special chars (']', '$') matches an
        equal element literally, with the correct index, and no globbing."""
        rc, present, val = self._call("a]b", 'arr=(x "a]b" y)')
        assert rc == 0, "literal 'a]b' element must be matchable, rc=%d" % rc
        assert present and val == "1", (
            "index of literal 'a]b' must be 1, got rc=%d val=%r" % (rc, val)
        )

    def test_by_name_not_call_site_expansion(self):
        """L2: the helper references the array BY NAME. We confirm it works on an
        array whose name differs from any value it contains, and that values
        containing what looks like an array reference are treated as data.

        Array (\\${arr} b): searching the literal text '${arr}' must hit index 0,
        proving the search value is compared literally rather than re-expanded."""
        rc, present, val = self._call("${arr}", "arr=('${arr}' b)")
        assert rc == 0, (
            "literal '${arr}' element must match without re-expansion, rc=%d" % rc
        )
        assert present and val == "0", (
            "index of literal '${arr}' must be 0, got rc=%d val=%r" % (rc, val)
        )

    def test_existing_search_helpers_unchanged(self):
        """L2: the pre-existing array helpers still behave correctly after the edit
        (a solution that mangles shared array-handling code is caught).

        bats_binary_search on a sorted (1 2 3): hit for each element, miss for 'a',
        and arg-count error returns 2."""
        script = (
            "set +e\n"
            "source '%s'\n"
            "arr=(1 2 3)\n"
            "( bats_binary_search 1 arr ); echo \"H1=$?\"\n"
            "( bats_binary_search 3 arr ); echo \"H3=$?\"\n"
            "( bats_binary_search a arr ); echo \"MISS=$?\"\n"
            "( bats_binary_search only_one_arg ); echo \"ARGC=$?\"\n"
            % self.COMMON_BASH
        )
        proc = subprocess.run(
            ["bash", "-c", script],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert "H1=0" in proc.stdout, "bats_binary_search 1 (1 2 3) must hit (0)"
        assert "H3=0" in proc.stdout, "bats_binary_search 3 (1 2 3) must hit (0)"
        assert "MISS=1" in proc.stdout, "bats_binary_search a (1 2 3) must miss (1)"
        assert "ARGC=2" in proc.stdout, (
            "bats_binary_search with wrong arg count must return 2; out=%r"
            % proc.stdout
        )

    def test_native_new_test_block_passes(self):
        """L2: the agent's new @test bats_array_index_of passes under the real bats
        runner (filtered to just that block, proving the block exists and runs)."""
        proc = subprocess.run(
            [self.BATS_BIN, "--filter", "bats_array_index_of", "test/common.bats"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=300,
        )
        out = proc.stdout + proc.stderr
        assert proc.returncode == 0, (
            "native run of `bats --filter bats_array_index_of test/common.bats` "
            "failed (rc=%d):\n%s" % (proc.returncode, out)
        )
        assert re.search(r"(?m)^ok \d+ bats_array_index_of\b", out), (
            "new @test bats_array_index_of did not run/pass under bats:\n%s" % out
        )

    def test_native_full_common_bats_suite_passes(self):
        """L2: the full `bin/bats test/common.bats` suite exits 0 with every test
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
            "`bin/bats test/common.bats` must exit 0; rc=%d\n%s"
            % (proc.returncode, out)
        )
        assert "bats_array_index_of" in out, (
            "the new test must appear in the suite output:\n%s" % out
        )
        assert "not ok" not in out, "no test in the suite may fail:\n%s" % out
        oks = re.findall(r"(?m)^ok \d+ ", out)
        assert len(oks) >= 5, (
            "expected several passing tests in common.bats, saw %d:\n%s"
            % (len(oks), out)
        )
