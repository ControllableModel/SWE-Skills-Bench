"""Benchmark test for the `pytest-plugin-development` skill task (variant ext2).

Task: add a self-contained, dependency-free duration utility module at
`src/_pytest/_duration.py` (pure stdlib + `from __future__ import annotations`
only, no other `_pytest` imports) exporting exactly two public callables:

    parse_duration(text: str) -> float      # "1h 30m" -> 5400.0
    format_duration(seconds: float) -> str  # 3661 -> "1h1m1s"

plus an exhaustive test module `testing/test_duration_util.py`.

Verification strategy: this file independently exercises the agent's
implementation by loading the delivered module DIRECTLY from its file path (via
importlib, avoiding `_pytest` package side effects) and asserting its real
runtime behavior across every enumerated edge case in the requirement doc:
every unit, multi-term expressions, case-insensitivity, whitespace handling,
ms rounding, the round-trip property, the "never emit a zero unit" rule, and
each distinct ValueError failure mode (negative, empty, unknown unit, missing
number) — each ValueError message must contain the offending input. A partial,
stubbed or hardcoded implementation (fixed return, ignored input, no rounding,
missing failure modes) MUST fail at least one assertion here. We do NOT trust
the agent's own test file for the behavioral checks; finally we also run the
task's native acceptance command to confirm the agent's suite collects & passes.
"""

import ast
import importlib.util
import math
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
        return os.path.join(cls.REPO_DIR, "src", "_pytest", "_duration.py")

    @classmethod
    def _load_module(cls):
        """Load the delivered _duration.py directly from its file path.

        Loading by file path (not `import _pytest._duration`) avoids importing
        the whole `_pytest` package and guarantees we exercise the agent's file.
        """
        path = cls._module_path()
        assert os.path.isfile(path), f"missing deliverable: {path}"
        spec = importlib.util.spec_from_file_location("_duration_under_test", path)
        assert spec is not None and spec.loader is not None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    # ------------------------------------------------------------------ #
    # L1 — deliverables exist & are minimally well-formed                #
    # ------------------------------------------------------------------ #
    def test_l1_module_file_exists(self):
        """L1: src/_pytest/_duration.py deliverable exists."""
        assert os.path.isfile(self._module_path()), self._module_path()

    def test_l1_test_module_exists(self):
        """L1: testing/test_duration_util.py deliverable exists."""
        p = os.path.join(self.REPO_DIR, "testing", "test_duration_util.py")
        assert os.path.isfile(p), p

    def test_l1_exports_two_public_callables(self):
        """L1: module exports parse_duration and format_duration, both callable."""
        mod = self._load_module()
        for name in ("parse_duration", "format_duration"):
            assert hasattr(mod, name), f"missing export: {name}"
            assert callable(getattr(mod, name)), f"{name} is not callable"

    def test_l1_module_is_dependency_free(self):
        """L1: module imports no other _pytest submodules and no third-party pkgs."""
        path = self._module_path()
        with open(path, "r", encoding="utf-8") as fh:
            src = fh.read()
        tree = ast.parse(src)
        # Standard-library top-level module names allowed by the doc ("pure,
        # dependency-free; only the Python standard library").
        stdlib_ok = {
            "re", "math", "typing", "decimal", "fractions", "numbers",
            "functools", "itertools", "collections", "string", "__future__",
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                base = (node.module or "").split(".")[0]
                assert base != "_pytest", (
                    f"module must not import from _pytest, found: {node.module}"
                )
                assert not (node.level and node.level > 0), (
                    "relative import found; module must be dependency-free"
                )
                assert base in stdlib_ok, (
                    f"unexpected non-stdlib import: {node.module}"
                )
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    assert not alias.name.startswith("_pytest"), (
                        f"module must not import _pytest, found: {alias.name}"
                    )
                    assert top in stdlib_ok, (
                        f"unexpected non-stdlib import: {alias.name}"
                    )

    # ------------------------------------------------------------------ #
    # L2 — parse_duration: bare numbers & every unit                     #
    # ------------------------------------------------------------------ #
    def test_l2_parse_bare_numbers_are_seconds(self):
        """L2: a bare number parses as seconds, including fractional."""
        mod = self._load_module()
        assert mod.parse_duration("5") == 5.0
        assert mod.parse_duration("0.25") == 0.25
        # A naive impl returning a constant cannot satisfy both of these.
        assert mod.parse_duration("0") == 0.0

    def test_l2_parse_each_unit(self):
        """L2: ms, s, m, h units each convert to the correct number of seconds."""
        mod = self._load_module()
        assert mod.parse_duration("500ms") == pytest.approx(0.5)
        assert mod.parse_duration("2s") == pytest.approx(2.0)
        assert mod.parse_duration("3m") == pytest.approx(180.0)
        assert mod.parse_duration("1h") == pytest.approx(3600.0)

    def test_l2_parse_multi_term_expressions(self):
        """L2: whitespace-separated multi-term expressions sum their seconds."""
        mod = self._load_module()
        assert mod.parse_duration("1h 30m") == pytest.approx(5400.0)
        assert mod.parse_duration("1m 30s") == pytest.approx(90.0)
        # Three terms across all the larger units.
        assert mod.parse_duration("1h 1m 1s") == pytest.approx(3661.0)

    def test_l2_parse_whitespace_handling(self):
        """L2: leading/trailing trimmed; internal whitespace runs collapse."""
        mod = self._load_module()
        assert mod.parse_duration("   2s   ") == pytest.approx(2.0)
        assert mod.parse_duration("1h\t30m") == pytest.approx(5400.0)
        assert mod.parse_duration("1h    30m") == pytest.approx(5400.0)

    def test_l2_parse_unit_case_insensitive(self):
        """L2: the unit suffix is case-insensitive (2S == 2s)."""
        mod = self._load_module()
        assert mod.parse_duration("2S") == mod.parse_duration("2s")
        assert mod.parse_duration("1H 30M") == pytest.approx(5400.0)
        assert mod.parse_duration("500MS") == pytest.approx(0.5)

    # ------------------------------------------------------------------ #
    # L2 — parse_duration: every distinct ValueError failure mode        #
    # ------------------------------------------------------------------ #
    def test_l2_parse_negative_raises_with_input(self):
        """L2: a negative value raises ValueError whose message contains input."""
        mod = self._load_module()
        for bad in ("-5", "-2s", "-0.5"):
            with pytest.raises(ValueError) as exc:
                mod.parse_duration(bad)
            assert bad in str(exc.value), (
                f"ValueError for {bad!r} must mention the input; got {exc.value!r}"
            )

    def test_l2_parse_empty_or_whitespace_raises(self):
        """L2: empty or whitespace-only input raises ValueError."""
        mod = self._load_module()
        for bad in ("", "   ", "\t\n"):
            with pytest.raises(ValueError):
                mod.parse_duration(bad)

    def test_l2_parse_unknown_unit_raises_with_unit_and_input(self):
        """L2: an unknown unit raises ValueError mentioning the unit and the input."""
        mod = self._load_module()
        bad = "5d"
        with pytest.raises(ValueError) as exc:
            mod.parse_duration(bad)
        msg = str(exc.value)
        assert bad in msg, f"message must contain input {bad!r}; got {msg!r}"
        assert "d" in msg, f"message must mention the offending unit; got {msg!r}"

    def test_l2_parse_missing_number_raises_with_input(self):
        """L2: a term with no numeric part (e.g. 'ms') raises ValueError."""
        mod = self._load_module()
        for bad in ("ms", "s", "1h m"):
            with pytest.raises(ValueError) as exc:
                mod.parse_duration(bad)
            assert bad in str(exc.value), (
                f"ValueError for {bad!r} must mention the input; got {exc.value!r}"
            )

    # ------------------------------------------------------------------ #
    # L2 — format_duration                                               #
    # ------------------------------------------------------------------ #
    def test_l2_format_zero_and_compound(self):
        """L2: exact compact formatting for 0, 90, 3600, 3661."""
        mod = self._load_module()
        assert mod.format_duration(0) == "0s"
        assert mod.format_duration(90) == "1m30s"
        assert mod.format_duration(3600) == "1h"
        assert mod.format_duration(3661) == "1h1m1s"

    def test_l2_format_subsecond_milliseconds(self):
        """L2: sub-second values render in ms; 0.5 -> '500ms'."""
        mod = self._load_module()
        assert mod.format_duration(0.5) == "500ms"
        # Rounded to the nearest whole millisecond.
        assert mod.format_duration(0.001) == "1ms"
        assert mod.format_duration(0.0004) == "0s"  # rounds below 1ms -> zero
        assert mod.format_duration(0.123) == "123ms"

    def test_l2_format_ms_rounding_to_nearest(self):
        """L2: milliseconds round to the nearest whole millisecond, not truncate."""
        mod = self._load_module()
        # 0.0015s == 1.5ms -> rounds to 2ms (truncation would give 1ms).
        assert mod.format_duration(0.0015) == "2ms"
        # 0.0024s == 2.4ms -> 2ms.
        assert mod.format_duration(0.0024) == "2ms"

    def test_l2_format_never_emits_zero_units(self):
        """L2: no unit with value zero is emitted except the lone '0s'."""
        mod = self._load_module()
        # 3601 has zero minutes -> minutes must be omitted, not "1h0m1s".
        out = mod.format_duration(3601)
        assert out == "1h1s", out
        assert "0m" not in out
        # 7200 -> exactly two hours, no trailing zero units.
        assert mod.format_duration(7200) == "2h"
        # 60 -> one minute, no seconds.
        assert mod.format_duration(60) == "1m"

    def test_l2_format_negative_raises(self):
        """L2: a negative number of seconds raises ValueError."""
        mod = self._load_module()
        for bad in (-1, -0.5, -3600):
            with pytest.raises(ValueError):
                mod.format_duration(bad)

    # ------------------------------------------------------------------ #
    # L2 — cross-function invariants                                     #
    # ------------------------------------------------------------------ #
    def test_l2_roundtrip_whole_seconds(self):
        """L2: parse_duration(format_duration(n)) == float(n) for whole seconds."""
        mod = self._load_module()
        for n in (0, 1, 30, 59, 60, 61, 90, 3599, 3600, 3661, 7322, 86399):
            formatted = mod.format_duration(n)
            recovered = mod.parse_duration(formatted)
            assert recovered == pytest.approx(float(n)), (
                f"round-trip failed for {n}: format -> {formatted!r} -> {recovered}"
            )

    def test_l2_format_output_is_parseable_general(self):
        """L2: format output is always re-parseable and numerically consistent."""
        mod = self._load_module()
        # Includes a sub-second value whose ms form must re-parse to the same value.
        for seconds in (0.5, 2.0, 180.0, 5400.0, 0.123):
            out = mod.format_duration(seconds)
            assert isinstance(out, str) and out, out
            back = mod.parse_duration(out)
            assert back == pytest.approx(seconds), (
                f"{seconds} -> {out!r} -> {back}"
            )

    def test_l2_return_types(self):
        """L2: parse_duration returns float, format_duration returns str."""
        mod = self._load_module()
        v = mod.parse_duration("1h 30m")
        assert isinstance(v, float) and not isinstance(v, bool)
        assert not math.isnan(v)
        s = mod.format_duration(3661)
        assert isinstance(s, str)

    # ------------------------------------------------------------------ #
    # L2 — the task's own acceptance command must pass                   #
    # ------------------------------------------------------------------ #
    def test_l2_native_pytest_suite_passes(self):
        """L2: the agent's testing/test_duration_util.py passes via native pytest.

        Runs the exact acceptance command from the doc. Requires at least one
        test collected and zero failures.
        """
        env = dict(os.environ)
        # Ensure the repo's src tree is importable for the native suite.
        env["PYTHONPATH"] = os.path.join(self.REPO_DIR, "src")
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "testing/test_duration_util.py",
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
