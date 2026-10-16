"""Benchmark test for the `pytest-plugin-development` skill task (variant ext4).

Task: add a self-contained terminal-width text truncation utility module at
`src/_pytest/_io/_truncate.py` (pure stdlib, no other `_pytest` imports)
exporting exactly two public callables `ellipsize` and `pad`, plus an
exhaustive test module `testing/io/test_truncate_util.py`.

Verification strategy: this test file independently exercises the agent's
implementation by loading the delivered module directly (via importlib, by file
path, so no `_pytest` package side effects are triggered) and asserting its real
runtime behavior across every enumerated edge case and failure mode from the
requirement doc. The behavioral checks do NOT trust the agent's own test file,
so a partial / hardcoded / input-ignoring implementation must fail here. A final
L2 case drives the task's exact native acceptance command end-to-end.

Native acceptance command (from the doc):
    python -m pytest testing/io/test_truncate_util.py -p no:cacheprovider -q
"""

import ast
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
        return os.path.join(cls.REPO_DIR, "src", "_pytest", "_io", "_truncate.py")

    @classmethod
    def _test_module_path(cls):
        return os.path.join(cls.REPO_DIR, "testing", "io", "test_truncate_util.py")

    @classmethod
    def _load_module(cls):
        """Load the delivered _truncate.py directly from its file path.

        Loading by file path (not `import _pytest._io._truncate`) avoids
        importing the whole `_pytest` package and guarantees we exercise the
        agent's file exactly as written.
        """
        path = cls._module_path()
        assert os.path.isfile(path), f"missing deliverable: {path}"
        spec = importlib.util.spec_from_file_location("_truncate_under_test", path)
        assert spec is not None and spec.loader is not None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    # ------------------------------------------------------------------ #
    # L1 — deliverables exist & are minimally well-formed                #
    # ------------------------------------------------------------------ #
    def test_l1_module_file_exists(self):
        """L1: src/_pytest/_io/_truncate.py deliverable exists."""
        assert os.path.isfile(self._module_path()), self._module_path()

    def test_l1_test_module_exists(self):
        """L1: testing/io/test_truncate_util.py deliverable exists."""
        assert os.path.isfile(self._test_module_path()), self._test_module_path()

    def test_l1_exports_two_public_callables(self):
        """L1: module exports exactly the two required callables ellipsize & pad."""
        mod = self._load_module()
        for name in ("ellipsize", "pad"):
            assert hasattr(mod, name), f"missing export: {name}"
            assert callable(getattr(mod, name)), f"{name} is not callable"

    def test_l1_module_is_dependency_free(self):
        """L1: module imports no other _pytest submodules and no third-party deps."""
        path = self._module_path()
        with open(path, "r", encoding="utf-8") as fh:
            src = fh.read()
        tree = ast.parse(src)
        # Only stdlib + `from __future__ import annotations` are permitted.
        # A minimal stdlib allow-set is generous; the hard rule is: no _pytest
        # imports and no relative imports.
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
    # L2 — ellipsize: passthrough & basic truncation                     #
    # ------------------------------------------------------------------ #
    def test_l2_ellipsize_no_truncation_passthrough(self):
        """L2: when len(text) <= width, text is returned unchanged (no marker)."""
        mod = self._load_module()
        assert mod.ellipsize("abc", 3) == "abc"
        assert mod.ellipsize("abc", 10) == "abc"
        assert mod.ellipsize("", 5) == ""
        # A naive impl that always appends the marker would add "..." here.
        assert "..." not in mod.ellipsize("abc", 10)

    def test_l2_ellipsize_exact_width_truncation(self):
        """L2: truncated result has length == width and ends with the marker."""
        mod = self._load_module()
        out = mod.ellipsize("abcdef", 5)
        assert out == "ab...", out
        assert len(out) == 5
        assert out.endswith("...")

    def test_l2_ellipsize_custom_marker(self):
        """L2: a custom (single-char) marker is honored."""
        mod = self._load_module()
        out = mod.ellipsize("abcdef", 4, marker="…")
        assert out == "abc…", out
        assert len(out) == 4
        assert out.endswith("…")

    def test_l2_ellipsize_marker_wider_than_width(self):
        """L2: when width < len(marker), result is the marker truncated to width."""
        mod = self._load_module()
        out = mod.ellipsize("abcdef", 2)
        assert out == "..", out
        assert len(out) == 2
        out1 = mod.ellipsize("abcdef", 1)
        assert out1 == ".", out1

    def test_l2_ellipsize_zero_width(self):
        """L2: a width of 0 returns the empty string."""
        mod = self._load_module()
        assert mod.ellipsize("abcdef", 0) == ""
        assert mod.ellipsize("", 0) == ""

    def test_l2_ellipsize_negative_width_raises(self):
        """L2: a negative width raises ValueError whose message contains the value."""
        mod = self._load_module()
        with pytest.raises(ValueError) as exc:
            mod.ellipsize("abcdef", -3)
        assert "-3" in str(exc.value), (
            f"ValueError message must contain the offending width; got: {exc.value}"
        )

    def test_l2_ellipsize_length_invariant(self):
        """L2: for any text and width >= 0, len(ellipsize(text, width)) <= width."""
        mod = self._load_module()
        samples = ["", "a", "ab", "abc", "hello world", "x" * 40]
        for text in samples:
            for width in range(0, 12):
                out = mod.ellipsize(text, width)
                assert len(out) <= width, (
                    f"ellipsize({text!r}, {width}) -> {out!r} exceeds width"
                )

    # ------------------------------------------------------------------ #
    # L2 — pad: alignment behavior                                        #
    # ------------------------------------------------------------------ #
    def test_l2_pad_default_left(self):
        """L2: default alignment is left; fill goes on the right."""
        mod = self._load_module()
        out = mod.pad("ab", 5)
        assert out == "ab   ", repr(out)
        assert len(out) == 5

    def test_l2_pad_right_align(self):
        """L2: right alignment puts fill on the left."""
        mod = self._load_module()
        out = mod.pad("ab", 5, align="right")
        assert out == "   ab", repr(out)
        assert len(out) == 5

    def test_l2_pad_center_odd_remainder(self):
        """L2: center splits remainder so extra fill goes to the right."""
        mod = self._load_module()
        # 3 fill chars for "ab" -> width 5: left=1, right=2 (extra on right).
        out = mod.pad("ab", 5, align="center")
        assert out == " ab  ", repr(out)
        assert len(out) == 5
        # Even remainder splits evenly.
        out_even = mod.pad("ab", 6, align="center")
        assert out_even == "  ab  ", repr(out_even)

    def test_l2_pad_center_right_never_fewer_than_left(self):
        """L2: center rule — right side never has fewer fill chars than left."""
        mod = self._load_module()
        for width in range(2, 14):
            out = mod.pad("ab", width, align="center")
            assert len(out) == max(2, width)
            stripped_left = len(out) - len(out.lstrip(" "))
            stripped_right = len(out) - len(out.rstrip(" "))
            assert stripped_right >= stripped_left, (
                f"center pad width={width}: left={stripped_left} "
                f"right={stripped_right} violates remainder rule ({out!r})"
            )

    def test_l2_pad_no_truncation_when_text_longer(self):
        """L2: when len(text) >= width, text is returned unchanged (never truncates)."""
        mod = self._load_module()
        assert mod.pad("abcdef", 3) == "abcdef"
        assert mod.pad("abc", 3) == "abc"
        assert mod.pad("abcdef", 0) == "abcdef"

    def test_l2_pad_custom_fill(self):
        """L2: a custom single-char fill is honored across alignments."""
        mod = self._load_module()
        assert mod.pad("ab", 5, fill="*") == "ab***"
        assert mod.pad("ab", 5, align="right", fill="*") == "***ab"
        assert mod.pad("ab", 5, align="center", fill="*") == "*ab**"

    def test_l2_pad_length_invariant(self):
        """L2: for any text and width, len(pad(text, width)) == max(len(text), width)."""
        mod = self._load_module()
        samples = ["", "a", "ab", "hello", "x" * 9]
        for text in samples:
            for width in range(0, 13):
                for align in ("left", "right", "center"):
                    out = mod.pad(text, width, align=align)
                    assert len(out) == max(len(text), width), (
                        f"pad({text!r}, {width}, align={align!r}) -> {out!r}"
                    )

    def test_l2_pad_bad_align_raises(self):
        """L2: an unknown alignment value raises ValueError."""
        mod = self._load_module()
        with pytest.raises(ValueError):
            mod.pad("ab", 5, align="middle")
        with pytest.raises(ValueError):
            mod.pad("ab", 5, align="")

    def test_l2_pad_bad_fill_raises(self):
        """L2: a multi-character or empty fill raises ValueError."""
        mod = self._load_module()
        with pytest.raises(ValueError):
            mod.pad("ab", 5, fill="--")
        with pytest.raises(ValueError):
            mod.pad("ab", 5, fill="")

    def test_l2_pad_negative_width_raises(self):
        """L2: a negative width raises ValueError."""
        mod = self._load_module()
        with pytest.raises(ValueError):
            mod.pad("ab", -1)

    # ------------------------------------------------------------------ #
    # L2 — the task's own acceptance command must pass                   #
    # ------------------------------------------------------------------ #
    def test_l2_native_pytest_suite_passes(self):
        """L2: the agent's testing/io/test_truncate_util.py passes via native pytest.

        Runs the exact acceptance command from the doc. Requires at least one
        test collected and zero failures.
        """
        assert os.path.isfile(self._test_module_path()), self._test_module_path()
        env = dict(os.environ)
        # Ensure the repo's src tree is importable for the native suite.
        env["PYTHONPATH"] = os.path.join(self.REPO_DIR, "src")
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "testing/io/test_truncate_util.py",
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
