"""Benchmark test for the `pytest-plugin-development` skill task (variant ext7).

Task: add a self-contained glob-style test-file pattern matcher module at
`src/_pytest/_globmatch.py` (pure stdlib, no other `_pytest` imports) exporting
`matches(name, pattern) -> bool`, `matches_any(name, patterns) -> bool`, and
`split_segments(path) -> list[str]`, plus an exhaustive test module
`testing/test_globmatch_util.py`.

Verification strategy: this file independently exercises the agent's
implementation by loading the delivered module directly (via importlib by file
path, avoiding `_pytest` package side effects) and asserting its real runtime
behavior across every enumerated edge case in the requirement doc:

  * `*` matches empty / non-empty runs but NEVER crosses `/`;
  * `?` matches exactly one non-`/` char;
  * positive / negated / ranged character classes;
  * case-sensitivity;
  * the empty-pattern-matches-only-empty-string rule;
  * an unterminated character class raising ValueError that names the pattern;
  * `matches_any` true / false / empty-list-is-False;
  * `split_segments` duplicate-separator collapse, preserved `.` segment,
    leading-`/` not creating an empty first segment, empty-string -> [].

These checks do NOT rely on the agent's own test file, so a partial / hardcoded
implementation (e.g. `*` crossing `/`, ignoring negation/ranges, swallowing the
`.` segment, or never raising on an unterminated class) must fail here. A final
L2 method also runs the doc's exact native acceptance command against the
agent's own test module.
"""

import importlib.util
import os
import subprocess
import sys

import pytest


class TestPytestPluginDevelopment:
    REPO_DIR = "/workspace/pytest"

    # ------------------------------------------------------------------ #
    # helpers                                                            #
    # ------------------------------------------------------------------ #
    @classmethod
    def _module_path(cls):
        return os.path.join(cls.REPO_DIR, "src", "_pytest", "_globmatch.py")

    @classmethod
    def _load_module(cls):
        """Load the delivered _globmatch.py directly from its file path.

        Loading by file path (not `import _pytest._globmatch`) avoids importing
        the whole `_pytest` package and guarantees we exercise the agent's file.
        """
        path = cls._module_path()
        assert os.path.isfile(path), f"missing deliverable: {path}"
        spec = importlib.util.spec_from_file_location("_globmatch_under_test", path)
        assert spec is not None and spec.loader is not None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    # ------------------------------------------------------------------ #
    # L1 — deliverables exist & are minimally well-formed                #
    # ------------------------------------------------------------------ #
    def test_l1_module_file_exists(self):
        """L1: src/_pytest/_globmatch.py deliverable exists."""
        assert os.path.isfile(self._module_path()), self._module_path()

    def test_l1_test_module_exists(self):
        """L1: testing/test_globmatch_util.py deliverable exists."""
        p = os.path.join(self.REPO_DIR, "testing", "test_globmatch_util.py")
        assert os.path.isfile(p), p

    def test_l1_exports_three_public_callables(self):
        """L1: module exports the three required callables."""
        mod = self._load_module()
        for name in ("matches", "matches_any", "split_segments"):
            assert hasattr(mod, name), f"missing export: {name}"
            assert callable(getattr(mod, name)), f"{name} is not callable"

    def test_l1_module_is_dependency_free(self):
        """L1: module imports no other _pytest submodules (pure stdlib)."""
        path = self._module_path()
        with open(path, "r", encoding="utf-8") as fh:
            src = fh.read()
        import ast

        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                base = (node.module or "").split(".")[0]
                assert base not in ("_pytest",), (
                    f"module must not import from _pytest, found: {node.module}"
                )
                # The only allowed relative/future-style import is `__future__`.
                if node.level and node.level > 0:
                    raise AssertionError(
                        "relative import found; module must be dependency-free"
                    )
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith("_pytest"), (
                        f"module must not import _pytest, found: {alias.name}"
                    )

    # ------------------------------------------------------------------ #
    # L2 — matches: the `*` wildcard                                     #
    # ------------------------------------------------------------------ #
    def test_l2_star_matches_empty_and_nonempty_run(self):
        """L2: `*` matches both an empty run and a non-empty run of chars."""
        mod = self._load_module()
        # non-empty run
        assert mod.matches("test_app.py", "test_*.py") is True
        # empty run: nothing between the literals
        assert mod.matches("test_.py", "test_*.py") is True
        # whole string
        assert mod.matches("anything", "*") is True
        assert mod.matches("", "*") is True

    def test_l2_star_never_crosses_slash(self):
        """L2: `*` must NOT match a `/` (the load-bearing path rule)."""
        mod = self._load_module()
        # doc examples
        assert mod.matches("a/b", "a*b") is False
        assert mod.matches("a/b.py", "*.py") is False
        assert mod.matches("b.py", "*.py") is True
        # a multi-char star still refuses to swallow a separator
        assert mod.matches("dir/test_x.py", "test_*.py") is False

    # ------------------------------------------------------------------ #
    # L2 — matches: the `?` wildcard                                     #
    # ------------------------------------------------------------------ #
    def test_l2_question_matches_exactly_one_non_slash(self):
        """L2: `?` matches exactly one char and never a `/`."""
        mod = self._load_module()
        assert mod.matches("ab", "a?") is True
        # `?` requires exactly one char: empty fails, two fail.
        assert mod.matches("a", "a?") is False
        assert mod.matches("abc", "a?") is False
        # `?` does not match a separator
        assert mod.matches("a/", "a?") is False

    # ------------------------------------------------------------------ #
    # L2 — matches: character classes                                   #
    # ------------------------------------------------------------------ #
    def test_l2_positive_character_class(self):
        """L2: `[abc]` matches exactly one of the listed characters."""
        mod = self._load_module()
        assert mod.matches("a", "[abc]") is True
        assert mod.matches("c", "[abc]") is True
        assert mod.matches("d", "[abc]") is False
        # class consumes exactly one character
        assert mod.matches("ab", "[abc]") is False

    def test_l2_negated_character_class(self):
        """L2: `[!abc]` matches one character NOT in the set, and is distinct."""
        mod = self._load_module()
        assert mod.matches("d", "[!abc]") is True
        assert mod.matches("a", "[!abc]") is False
        assert mod.matches("b", "[!abc]") is False
        # negation must still consume exactly one char (not empty / not two)
        assert mod.matches("", "[!abc]") is False
        # negated class is genuinely distinct from the positive form
        assert mod.matches("z", "[abc]") is False
        assert mod.matches("z", "[!abc]") is True

    def test_l2_ranged_character_class(self):
        """L2: `[a-z]` matches a contiguous range; bounds and outside differ."""
        mod = self._load_module()
        assert mod.matches("a", "[a-z]") is True
        assert mod.matches("m", "[a-z]") is True
        assert mod.matches("z", "[a-z]") is True
        assert mod.matches("A", "[a-z]") is False
        assert mod.matches("0", "[a-z]") is False
        # digit range, as a second distinct range
        assert mod.matches("5", "[0-9]") is True
        assert mod.matches("a", "[0-9]") is False

    def test_l2_matching_is_case_sensitive(self):
        """L2: matching is case-sensitive (no implicit lowercasing)."""
        mod = self._load_module()
        assert mod.matches("Test_App.PY", "test_*.py") is False
        assert mod.matches("test_app.py", "test_*.py") is True
        assert mod.matches("A", "a") is False
        assert mod.matches("a", "a") is True

    def test_l2_empty_pattern_matches_only_empty_string(self):
        """L2: an empty pattern matches only the empty string."""
        mod = self._load_module()
        assert mod.matches("", "") is True
        assert mod.matches("x", "") is False

    def test_l2_unterminated_class_raises_valueerror_with_pattern(self):
        """L2: an unterminated character class raises ValueError naming the pattern."""
        mod = self._load_module()
        for bad in ("a[bc", "[abc", "x[a-z"):
            with pytest.raises(ValueError) as exc:
                mod.matches("a", bad)
            assert bad in str(exc.value), (
                f"ValueError for pattern {bad!r} must contain the offending "
                f"pattern; got: {exc.value}"
            )

    def test_l2_literal_match_and_mismatch(self):
        """L2: plain literal patterns match exact strings only."""
        mod = self._load_module()
        assert mod.matches("conftest.py", "conftest.py") is True
        assert mod.matches("conftest.pyc", "conftest.py") is False
        assert mod.matches("conftest", "conftest.py") is False

    # ------------------------------------------------------------------ #
    # L2 — matches_any                                                   #
    # ------------------------------------------------------------------ #
    def test_l2_matches_any_true_false_and_empty_list(self):
        """L2: matches_any ORs over patterns; empty list is always False."""
        mod = self._load_module()
        # doc example: matches the second pattern only
        assert mod.matches_any("foo_test.py", ["test_*.py", "*_test.py"]) is True
        # against only the first pattern it must be False
        assert mod.matches_any("foo_test.py", ["test_*.py"]) is False
        # empty list -> False (not an exception, not True)
        assert mod.matches_any("anything", []) is False
        # matches the first pattern
        assert mod.matches_any("test_x.py", ["test_*.py", "*_test.py"]) is True

    def test_l2_matches_any_consistent_with_matches(self):
        """L2: matches_any True iff at least one matches() is True."""
        mod = self._load_module()
        name = "widget_test.py"
        patterns = ["test_*.py", "*_test.py", "*.txt"]
        expected = any(mod.matches(name, p) for p in patterns)
        assert mod.matches_any(name, patterns) is expected is True
        # a set with no match
        none_match = ["*.txt", "*.md"]
        assert mod.matches_any(name, none_match) is False

    # ------------------------------------------------------------------ #
    # L2 — split_segments                                                #
    # ------------------------------------------------------------------ #
    def test_l2_split_segments_collapses_dupsep_keeps_dot(self):
        """L2: duplicate `/` collapse but a `.` component is preserved."""
        mod = self._load_module()
        assert mod.split_segments("a//b/./c") == ["a", "b", ".", "c"]

    def test_l2_split_segments_leading_slash_no_empty_first(self):
        """L2: a leading `/` does not create an empty first segment."""
        mod = self._load_module()
        assert mod.split_segments("/a/b") == ["a", "b"]
        # leading + duplicate separators
        assert mod.split_segments("//a//b") == ["a", "b"]

    def test_l2_split_segments_empty_string(self):
        """L2: the empty string splits to an empty list."""
        mod = self._load_module()
        assert mod.split_segments("") == []
        # a path of only separators also yields no segments
        assert mod.split_segments("///") == []

    def test_l2_split_segments_simple_and_trailing(self):
        """L2: ordinary and trailing-separator paths split correctly."""
        mod = self._load_module()
        assert mod.split_segments("a/b/c") == ["a", "b", "c"]
        assert mod.split_segments("a/b/") == ["a", "b"]
        assert mod.split_segments("single") == ["single"]

    # ------------------------------------------------------------------ #
    # L2 — cross-function / integration behaviour                        #
    # ------------------------------------------------------------------ #
    def test_l2_segments_then_match_per_component(self):
        """L2: split_segments + matches compose for per-component checks.

        The `*`-does-not-cross-`/` rule means matching a basename pattern
        against the final split segment succeeds while matching the whole path
        fails.
        """
        mod = self._load_module()
        path = "tests/sub/test_feature.py"
        segs = mod.split_segments(path)
        assert segs == ["tests", "sub", "test_feature.py"]
        # last segment matches the basename pattern
        assert mod.matches(segs[-1], "test_*.py") is True
        # but the full path does not, because `*` will not cross `/`
        assert mod.matches(path, "test_*.py") is False

    # ------------------------------------------------------------------ #
    # L2 — the task's own acceptance command must pass                   #
    # ------------------------------------------------------------------ #
    def test_l2_native_pytest_suite_passes(self):
        """L2: the agent's testing/test_globmatch_util.py passes via native pytest.

        Runs the exact acceptance command from the requirement doc. Requires at
        least one test collected and zero failures.
        """
        env = dict(os.environ)
        # Ensure the repo's src tree is importable for the native suite.
        env["PYTHONPATH"] = os.path.join(self.REPO_DIR, "src")
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "testing/test_globmatch_util.py",
                "-p",
                "no:cacheprovider",
                "-q",
            ],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=300,
            env=env,
        )
        combined = proc.stdout + "\n" + proc.stderr
        assert proc.returncode == 0, f"native suite failed:\n{combined}"
        # Guard against an empty / no-collection pass.
        assert "no tests ran" not in combined.lower(), combined
        assert "passed" in combined.lower(), combined
