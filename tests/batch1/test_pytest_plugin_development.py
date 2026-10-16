"""Benchmark test for the `pytest-plugin-development` skill task.

Task: add a self-contained node-id segment parser utility module at
`src/_pytest/_nodeid.py` (pure stdlib, no other `_pytest` imports) exporting
`split_nodeid`, `parametrize_id`, `base_name`, `normalize_nodeid`, plus an
exhaustive test module `testing/test_nodeid_util.py`.

This test file independently exercises the agent's implementation by loading
the delivered module directly (via importlib, avoiding package side effects)
and asserting its real runtime behavior across every enumerated edge case. It
does NOT rely on the agent's own test file for the behavioral checks, so a
partial / hardcoded implementation must fail here.
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
        return os.path.join(cls.REPO_DIR, "src", "_pytest", "_nodeid.py")

    @classmethod
    def _load_module(cls):
        """Load the delivered _nodeid.py directly from its file path.

        Loading by file path (not `import _pytest._nodeid`) avoids importing the
        whole `_pytest` package and guarantees we exercise the agent's file.
        """
        path = cls._module_path()
        assert os.path.isfile(path), f"missing deliverable: {path}"
        spec = importlib.util.spec_from_file_location("_nodeid_under_test", path)
        assert spec is not None and spec.loader is not None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    # ------------------------------------------------------------------ #
    # L1 — deliverables exist & are minimally well-formed                #
    # ------------------------------------------------------------------ #
    def test_l1_module_file_exists(self):
        """L1: src/_pytest/_nodeid.py deliverable exists."""
        assert os.path.isfile(self._module_path()), self._module_path()

    def test_l1_test_module_exists(self):
        """L1: testing/test_nodeid_util.py deliverable exists."""
        p = os.path.join(self.REPO_DIR, "testing", "test_nodeid_util.py")
        assert os.path.isfile(p), p

    def test_l1_exports_four_public_callables(self):
        """L1: module exports the four required callables."""
        mod = self._load_module()
        for name in ("split_nodeid", "parametrize_id", "base_name", "normalize_nodeid"):
            assert hasattr(mod, name), f"missing export: {name}"
            assert callable(getattr(mod, name)), f"{name} is not callable"

    def test_l1_module_is_dependency_free(self):
        """L1: module imports no other _pytest submodules (pure stdlib)."""
        path = self._module_path()
        with open(path, "r", encoding="utf-8") as fh:
            src = fh.read()
        # No imports pulling in sibling _pytest modules. Allow the bare
        # `from __future__ import annotations` and stdlib imports only.
        import ast

        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                base = (node.module or "").split(".")[0]
                assert base not in ("_pytest",), (
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
    # L2 — split_nodeid                                                  #
    # ------------------------------------------------------------------ #
    def test_l2_split_nodeid_basic(self):
        """L2: split_nodeid splits path from :: name segments."""
        mod = self._load_module()
        path, segs = mod.split_nodeid("tests/test_app.py::TestClass::test_method")
        assert path == "tests/test_app.py"
        assert segs == ["TestClass", "test_method"]

    def test_l2_split_nodeid_no_segments(self):
        """L2: a node id with no :: yields an empty segment list."""
        mod = self._load_module()
        path, segs = mod.split_nodeid("tests/test_app.py")
        assert path == "tests/test_app.py"
        assert segs == []

    def test_l2_split_nodeid_preserves_whitespace(self):
        """L2: whitespace inside a segment is preserved (no stripping)."""
        mod = self._load_module()
        path, segs = mod.split_nodeid("a.py::test[ x ]::  spaced  ")
        assert path == "a.py"
        assert segs == ["test[ x ]", "  spaced  "]

    def test_l2_split_nodeid_empty_segment_raises(self):
        """L2: trailing/interior empty segments raise ValueError mentioning input."""
        mod = self._load_module()
        for bad in ("a.py::", "a.py::::b", "a.py::b::"):
            with pytest.raises(ValueError) as exc:
                mod.split_nodeid(bad)
            assert bad in str(exc.value), (
                f"ValueError message for {bad!r} must contain the offending input; "
                f"got: {exc.value}"
            )

    def test_l2_split_nodeid_empty_string_raises(self):
        """L2: an empty node id raises ValueError."""
        mod = self._load_module()
        with pytest.raises(ValueError):
            mod.split_nodeid("")

    # ------------------------------------------------------------------ #
    # L2 — parametrize_id                                                #
    # ------------------------------------------------------------------ #
    def test_l2_parametrize_id_present_and_absent(self):
        """L2: returns inner id when parametrized, else None."""
        mod = self._load_module()
        assert mod.parametrize_id("test_method[param-1]") == "param-1"
        assert mod.parametrize_id("test_method") is None

    def test_l2_parametrize_id_empty_brackets_distinct_from_none(self):
        """L2: empty brackets yield "" which is distinct from None."""
        mod = self._load_module()
        result = mod.parametrize_id("test_method[]")
        assert result == ""
        assert result is not None

    def test_l2_parametrize_id_unmatched_and_nested(self):
        """L2: unmatched trailing [ -> None; nested keeps the outermost pair."""
        mod = self._load_module()
        assert mod.parametrize_id("test_method[oops") is None
        assert mod.parametrize_id("t[a[b]c]") == "a[b]c"
        # A ] not at the very end does not count as the closing bracket.
        assert mod.parametrize_id("t[a]b") is None

    # ------------------------------------------------------------------ #
    # L2 — base_name                                                     #
    # ------------------------------------------------------------------ #
    def test_l2_base_name_variants(self):
        """L2: base_name strips trailing [...]; handles bare-parametrization."""
        mod = self._load_module()
        assert mod.base_name("test_method[param-1]") == "test_method"
        assert mod.base_name("test_method") == "test_method"
        assert mod.base_name("test_method[]") == "test_method"
        assert mod.base_name("[x]") == ""
        # Nested: only the trailing parametrization is removed.
        assert mod.base_name("t[a[b]c]") == "t"

    # ------------------------------------------------------------------ #
    # L2 — normalize_nodeid                                              #
    # ------------------------------------------------------------------ #
    def test_l2_normalize_backslash_to_sep(self):
        """L2: backslashes in path become sep (default "/")."""
        mod = self._load_module()
        assert mod.normalize_nodeid("a\\b.py::t") == "a/b.py::t"

    def test_l2_normalize_collapse_dot_and_dupsep(self):
        """L2: redundant "." components and duplicate separators collapse."""
        mod = self._load_module()
        assert mod.normalize_nodeid("a/./b//c.py::t") == "a/b/c.py::t"

    def test_l2_normalize_dotdot_preserved(self):
        """L2: a ".." component is kept verbatim (not resolved)."""
        mod = self._load_module()
        out = mod.normalize_nodeid("a/../b.py::t")
        assert ".." in out, f"'..' must be preserved, got {out!r}"
        assert out == "a/../b.py::t"

    def test_l2_normalize_custom_sep_replaces_both_slashes(self):
        """L2: with a custom sep, both / and \\ are replaced by sep."""
        mod = self._load_module()
        out = mod.normalize_nodeid("a/b\\c.py::t", sep="|")
        assert out == "a|b|c.py::t", out

    def test_l2_normalize_leaves_name_segments_untouched(self):
        """L2: name segments are never normalized, even with /, \\, . in them."""
        mod = self._load_module()
        nid = "a/./b.py::weird/seg\\name::dot.in.name"
        out = mod.normalize_nodeid(nid)
        # path collapsed, segments verbatim
        assert out == "a/b.py::weird/seg\\name::dot.in.name", out
        # Verify with a custom sep too: still must not touch segments.
        out2 = mod.normalize_nodeid(nid, sep="#")
        assert out2 == "a#b.py::weird/seg\\name::dot.in.name", out2

    # ------------------------------------------------------------------ #
    # L2 — cross-function invariants                                     #
    # ------------------------------------------------------------------ #
    def test_l2_normalize_is_idempotent_on_clean_ids(self):
        """L2: normalizing an already-clean node id returns it unchanged."""
        mod = self._load_module()
        for clean in (
            "tests/test_app.py::TestClass::test_method[param-1]",
            "a/b/c.py::t",
            "single.py",
        ):
            assert mod.normalize_nodeid(clean) == clean, clean

    def test_l2_base_name_parametrize_id_reconstruct_segment(self):
        """L2: for parametrized segs, seg == base_name + "[" + parametrize_id + "]"."""
        mod = self._load_module()
        for seg in ("test_method[param-1]", "test_method[]", "t[a[b]c]", "[x]"):
            pid = mod.parametrize_id(seg)
            assert pid is not None, f"{seg!r} should be detected as parametrized"
            reconstructed = mod.base_name(seg) + "[" + pid + "]"
            assert reconstructed == seg, (
                f"reconstruction failed for {seg!r}: got {reconstructed!r}"
            )

    def test_l2_split_then_normalize_roundtrip_consistency(self):
        """L2: path from split of a clean id matches normalize's path component."""
        mod = self._load_module()
        nid = "tests/test_app.py::TestClass::test_method"
        path, segs = mod.split_nodeid(nid)
        normalized = mod.normalize_nodeid(nid)
        # Already clean -> normalize is identity, and the path prefix matches.
        assert normalized == nid
        assert normalized.startswith(path + "::")
        assert normalized == path + "::" + "::".join(segs)

    # ------------------------------------------------------------------ #
    # L2 — the task's own acceptance command must pass                   #
    # ------------------------------------------------------------------ #
    def test_l2_native_pytest_suite_passes(self):
        """L2: the agent's testing/test_nodeid_util.py passes via native pytest.

        Runs the exact acceptance command. Requires at least one test collected
        and zero failures.
        """
        env = dict(os.environ)
        # Ensure the repo's src tree is importable for the native suite.
        env["PYTHONPATH"] = os.path.join(self.REPO_DIR, "src")
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "testing/test_nodeid_util.py",
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
        assert ("passed" in combined.lower()), combined
