"""Benchmark test for the `pytest-plugin-development` skill task (variant ext10).

Task: add a self-contained unified-diff line-renderer utility module at
`src/_pytest/_linediff.py` (pure stdlib; `difflib` permitted; no other `_pytest`
imports) exporting:

  * ``diff_lines(expected, actual) -> list[str]`` — prefixed diff lines
    ("  " unchanged, "- " removed, "+ " added), exact text preservation,
    ValueError for embedded "\\n", "[]" for two empty inputs.
  * ``count_changes(diff) -> tuple[int, int]`` — (removed, added) counts.
  * ``is_equal(expected, actual) -> bool`` — True iff diff has no +/- lines.

plus an exhaustive test module `testing/test_linediff_util.py`.

Verification strategy: load the delivered ``_linediff.py`` directly by file
path (via importlib, avoiding ``_pytest`` package side effects) and assert its
real runtime behavior across every enumerated edge case from the requirement
doc. The behavioral checks do NOT trust the agent's own test file, so a partial
/ hardcoded / stub implementation must fail here. A final L2 case also drives
the task's native acceptance command on the agent-authored suite.
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
        return os.path.join(cls.REPO_DIR, "src", "_pytest", "_linediff.py")

    @classmethod
    def _load_module(cls):
        """Load the delivered _linediff.py directly from its file path.

        Loading by file path (not ``import _pytest._linediff``) avoids importing
        the whole ``_pytest`` package and guarantees we exercise the agent's
        actual file.
        """
        path = cls._module_path()
        assert os.path.isfile(path), f"missing deliverable: {path}"
        spec = importlib.util.spec_from_file_location("_linediff_under_test", path)
        assert spec is not None and spec.loader is not None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    # ------------------------------------------------------------------ #
    # L1 — deliverables exist & are minimally well-formed                #
    # ------------------------------------------------------------------ #
    def test_l1_module_file_exists(self):
        """L1: src/_pytest/_linediff.py deliverable exists."""
        assert os.path.isfile(self._module_path()), self._module_path()

    def test_l1_test_module_exists(self):
        """L1: testing/test_linediff_util.py deliverable exists."""
        p = os.path.join(self.REPO_DIR, "testing", "test_linediff_util.py")
        assert os.path.isfile(p), p

    def test_l1_exports_three_public_callables(self):
        """L1: module exports the three required callables."""
        mod = self._load_module()
        for name in ("diff_lines", "count_changes", "is_equal"):
            assert hasattr(mod, name), f"missing export: {name}"
            assert callable(getattr(mod, name)), f"{name} is not callable"

    def test_l1_module_is_dependency_free(self):
        """L1: module imports no other _pytest submodules (pure stdlib only).

        ``difflib`` is explicitly permitted; ``from __future__ import
        annotations`` is allowed. Any import that pulls in a sibling ``_pytest``
        module — or any relative import — is forbidden.
        """
        path = self._module_path()
        with open(path, "r", encoding="utf-8") as fh:
            src = fh.read()
        import ast

        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                base = (node.module or "").split(".")[0]
                assert base != "_pytest", (
                    f"module must not import from _pytest, found: {node.module}"
                )
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
    # L2 — diff_lines: prefixes, text preservation, edge cases           #
    # ------------------------------------------------------------------ #
    def test_l2_diff_lines_substitution_example(self):
        """L2: the canonical substitution example yields exactly the spec output.

        expected=["a","b","c"], actual=["a","x","c"] -> two unchanged lines,
        one removed ("- b") and one added ("+ x"). A naive implementation that
        ignores the inputs / hardcodes output cannot produce this.
        """
        mod = self._load_module()
        out = mod.diff_lines(["a", "b", "c"], ["a", "x", "c"])
        # Exactly one removed and one added.
        removed = [ln for ln in out if ln.startswith("- ")]
        added = [ln for ln in out if ln.startswith("+ ")]
        unchanged = [ln for ln in out if ln.startswith("  ")]
        assert removed == ["- b"], out
        assert added == ["+ x"], out
        assert unchanged == ["  a", "  c"], out
        # Every line must carry one of the three 2-char prefixes.
        for ln in out:
            assert ln[:2] in ("  ", "- ", "+ "), f"bad prefix: {ln!r}"

    def test_l2_diff_lines_all_unchanged_when_equal(self):
        """L2: identical inputs -> every line is an unchanged ("  ") line.

        The number of output lines equals the number of input lines, and the
        stripped text is recoverable verbatim.
        """
        mod = self._load_module()
        inp = ["alpha", "beta", "gamma"]
        out = mod.diff_lines(inp, list(inp))
        assert len(out) == len(inp), out
        for ln in out:
            assert ln.startswith("  "), f"expected unchanged prefix, got {ln!r}"
        assert [ln[2:] for ln in out] == inp, out

    def test_l2_diff_lines_both_empty_returns_empty(self):
        """L2: two empty inputs return an empty list (not [""] or None)."""
        mod = self._load_module()
        out = mod.diff_lines([], [])
        assert out == [], out

    def test_l2_diff_lines_pure_append(self):
        """L2: a pure-append case yields exactly one added, zero removed lines."""
        mod = self._load_module()
        out = mod.diff_lines(["a"], ["a", "b"])
        removed = [ln for ln in out if ln.startswith("- ")]
        added = [ln for ln in out if ln.startswith("+ ")]
        assert removed == [], out
        assert added == ["+ b"], out
        # The original "a" survives as an unchanged line.
        assert "  a" in out, out

    def test_l2_diff_lines_pure_removal(self):
        """L2: removing a line yields exactly one removed, zero added lines."""
        mod = self._load_module()
        out = mod.diff_lines(["a", "b"], ["a"])
        removed = [ln for ln in out if ln.startswith("- ")]
        added = [ln for ln in out if ln.startswith("+ ")]
        assert removed == ["- b"], out
        assert added == [], out
        assert "  a" in out, out

    def test_l2_diff_lines_preserves_exact_text(self):
        """L2: prefixes preserve original line text exactly, including internal
        and trailing whitespace inside a line.

        A stub that strips or normalizes whitespace must fail this.
        """
        mod = self._load_module()
        out = mod.diff_lines(["  leading", "trailing  "], ["  leading", "trailing  "])
        # Both unchanged; the 2-char prefix plus the *exact* original text.
        assert out == ["    leading", "  trailing  "], repr(out)
        # And in a change context, the added text is preserved verbatim.
        out2 = mod.diff_lines(["x"], ["y\ty "])
        added = [ln for ln in out2 if ln.startswith("+ ")]
        assert added == ["+ y\ty "], repr(out2)

    def test_l2_diff_lines_embedded_newline_raises(self):
        """L2: any input line containing "\\n" raises ValueError naming the line.

        Both the expected and actual sides must be validated.
        """
        mod = self._load_module()
        offending = "bad\nline"
        with pytest.raises(ValueError) as exc:
            mod.diff_lines([offending], ["ok"])
        assert offending in str(exc.value), (
            f"ValueError must mention the offending line; got: {exc.value}"
        )
        with pytest.raises(ValueError) as exc2:
            mod.diff_lines(["ok"], ["also\nbad"])
        assert "also\nbad" in str(exc2.value), exc2.value

    # ------------------------------------------------------------------ #
    # L2 — count_changes                                                #
    # ------------------------------------------------------------------ #
    def test_l2_count_changes_substitution(self):
        """L2: count_changes on the substitution diff returns (1, 1)."""
        mod = self._load_module()
        diff = mod.diff_lines(["a", "b", "c"], ["a", "x", "c"])
        assert mod.count_changes(diff) == (1, 1), diff

    def test_l2_count_changes_identical_is_zero(self):
        """L2: count_changes on an all-unchanged diff returns (0, 0)."""
        mod = self._load_module()
        diff = mod.diff_lines(["a", "b"], ["a", "b"])
        assert mod.count_changes(diff) == (0, 0), diff

    def test_l2_count_changes_append_and_removal_asymmetry(self):
        """L2: count_changes distinguishes removed from added (order matters)."""
        mod = self._load_module()
        appended = mod.diff_lines(["a"], ["a", "b"])
        assert mod.count_changes(appended) == (0, 1), appended
        removed = mod.diff_lines(["a", "b"], ["a"])
        assert mod.count_changes(removed) == (1, 0), removed

    def test_l2_count_changes_ignores_unchanged_lines(self):
        """L2: count_changes counts only +/- lines; unchanged lines are ignored.

        Built directly from prefixed lines so this exercises count_changes in
        isolation from diff_lines.
        """
        mod = self._load_module()
        synthetic = ["  keep", "- gone", "+ new", "  keep2", "- gone2"]
        assert mod.count_changes(synthetic) == (2, 1), synthetic

    # ------------------------------------------------------------------ #
    # L2 — is_equal                                                     #
    # ------------------------------------------------------------------ #
    def test_l2_is_equal_true_when_identical(self):
        """L2: is_equal is True for identical inputs and for two empty lists."""
        mod = self._load_module()
        assert mod.is_equal(["a", "b", "c"], ["a", "b", "c"]) is True
        assert mod.is_equal([], []) is True

    def test_l2_is_equal_false_on_any_change(self):
        """L2: is_equal is False on substitution, append, and removal."""
        mod = self._load_module()
        assert mod.is_equal(["a", "b", "c"], ["a", "x", "c"]) is False
        assert mod.is_equal(["a"], ["a", "b"]) is False
        assert mod.is_equal(["a", "b"], ["a"]) is False

    def test_l2_is_equal_returns_real_bool(self):
        """L2: is_equal returns an actual bool, not a truthy/falsy proxy."""
        mod = self._load_module()
        for res in (
            mod.is_equal(["a"], ["a"]),
            mod.is_equal(["a"], ["b"]),
        ):
            assert isinstance(res, bool), f"expected bool, got {type(res)}"

    # ------------------------------------------------------------------ #
    # L2 — cross-function invariants                                     #
    # ------------------------------------------------------------------ #
    def test_l2_is_equal_consistent_with_count_changes(self):
        """L2: is_equal(e,a) is True iff count_changes(diff_lines(e,a)) == (0,0)."""
        mod = self._load_module()
        cases = [
            (["a", "b", "c"], ["a", "x", "c"]),
            (["a"], ["a"]),
            (["a"], ["a", "b"]),
            (["a", "b"], ["a"]),
            ([], []),
            (["x", "y", "z"], ["x", "y", "z"]),
        ]
        for exp, act in cases:
            diff = mod.diff_lines(exp, act)
            removed, added = mod.count_changes(diff)
            equal = mod.is_equal(exp, act)
            assert equal == (removed == 0 and added == 0), (
                f"is_equal/count_changes disagree for {exp!r} vs {act!r}: "
                f"is_equal={equal}, counts=({removed},{added})"
            )

    def test_l2_unchanged_count_plus_changes_accounts_for_all_lines(self):
        """L2: unchanged + removed lines == len(expected); unchanged + added ==
        len(actual). Verifies diff_lines is a faithful edit script, not a stub."""
        mod = self._load_module()
        for exp, act in [
            (["a", "b", "c"], ["a", "x", "c"]),
            (["a"], ["a", "b", "c"]),
            (["a", "b", "c", "d"], ["b", "d"]),
        ]:
            diff = mod.diff_lines(exp, act)
            removed, added = mod.count_changes(diff)
            unchanged = sum(1 for ln in diff if ln.startswith("  "))
            assert unchanged + removed == len(exp), (exp, act, diff)
            assert unchanged + added == len(act), (exp, act, diff)

    # ------------------------------------------------------------------ #
    # L2 — the task's own acceptance command must pass                   #
    # ------------------------------------------------------------------ #
    def test_l2_native_pytest_suite_passes(self):
        """L2: the agent's testing/test_linediff_util.py passes via native pytest.

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
                "testing/test_linediff_util.py",
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
