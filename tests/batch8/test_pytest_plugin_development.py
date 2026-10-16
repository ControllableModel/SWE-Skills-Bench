"""Benchmark test for the `pytest-plugin-development` skill task (variant ext8).

Task: add a self-contained test-outcome counts aggregator module at
`src/_pytest/_outcomestats.py` (pure stdlib, no other `_pytest` imports)
exporting the `OutcomeStats` class and the `summary_line` function, plus an
exhaustive test module `testing/test_outcomestats_util.py`.

`OutcomeStats` records counts of the six allowed outcomes
(passed/failed/skipped/xfailed/xpassed/error), exposes `record`, `count`,
`total`, `failed_total`, and a non-mutating `merge`, raising ValueError on any
unknown outcome name. `summary_line` renders a comma-joined, fixed-order,
zero-omitting summary, returning "no tests ran" when empty.

Verification strategy: this file loads the delivered module directly from its
file path (via importlib, avoiding `_pytest` package side effects) and asserts
its real runtime behavior across every enumerated edge case — it does NOT trust
the agent's own test file for the behavioral checks. A partial / hardcoded /
naive implementation (fixed return, ignored input, mutating merge, silent
acceptance of bad outcomes, wrong order) must fail here. Finally it runs the
task's native acceptance command:

    python -m pytest testing/test_outcomestats_util.py -p no:cacheprovider -q
"""

import importlib.util
import os
import subprocess
import sys

import pytest


class TestPytestPluginDevelopment:
    REPO_DIR = "/workspace/pytest"

    ALLOWED = ("passed", "failed", "skipped", "xfailed", "xpassed", "error")

    # ------------------------------------------------------------------ #
    # helpers                                                            #
    # ------------------------------------------------------------------ #
    @classmethod
    def _module_path(cls):
        return os.path.join(cls.REPO_DIR, "src", "_pytest", "_outcomestats.py")

    @classmethod
    def _load_module(cls):
        """Load the delivered _outcomestats.py directly from its file path.

        Loading by file path (not `import _pytest._outcomestats`) avoids
        importing the whole `_pytest` package and guarantees we exercise the
        agent's actual file.
        """
        path = cls._module_path()
        assert os.path.isfile(path), f"missing deliverable: {path}"
        spec = importlib.util.spec_from_file_location("_outcomestats_under_test", path)
        assert spec is not None and spec.loader is not None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    @classmethod
    def _new_stats(cls):
        mod = cls._load_module()
        assert hasattr(mod, "OutcomeStats"), "missing export: OutcomeStats"
        return mod, mod.OutcomeStats()

    # ------------------------------------------------------------------ #
    # L1 — deliverables exist & are minimally well-formed                #
    # ------------------------------------------------------------------ #
    def test_l1_module_file_exists(self):
        """L1: src/_pytest/_outcomestats.py deliverable exists."""
        assert os.path.isfile(self._module_path()), self._module_path()

    def test_l1_test_module_exists(self):
        """L1: testing/test_outcomestats_util.py deliverable exists."""
        p = os.path.join(self.REPO_DIR, "testing", "test_outcomestats_util.py")
        assert os.path.isfile(p), p

    def test_l1_exports_class_and_function(self):
        """L1: module exports OutcomeStats (class) and summary_line (callable)."""
        mod = self._load_module()
        assert hasattr(mod, "OutcomeStats"), "missing export: OutcomeStats"
        assert isinstance(mod.OutcomeStats, type), "OutcomeStats must be a class"
        assert hasattr(mod, "summary_line"), "missing export: summary_line"
        assert callable(mod.summary_line), "summary_line is not callable"

    def test_l1_module_is_dependency_free(self):
        """L1: module imports no other _pytest submodules (pure stdlib only)."""
        path = self._module_path()
        with open(path, "r", encoding="utf-8") as fh:
            src = fh.read()
        import ast

        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                base = (node.module or "").split(".")[0]
                # `from __future__ import annotations` is explicitly allowed.
                if node.module == "__future__":
                    continue
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
    # L2 — construction & zero-init                                      #
    # ------------------------------------------------------------------ #
    def test_l2_zero_init_all_counts_zero(self):
        """L2: a fresh OutcomeStats reports 0 for every allowed outcome and totals."""
        _mod, s = self._new_stats()
        for outcome in self.ALLOWED:
            assert s.count(outcome) == 0, outcome
        assert s.total == 0
        assert s.failed_total == 0

    # ------------------------------------------------------------------ #
    # L2 — record / count for each valid outcome                         #
    # ------------------------------------------------------------------ #
    def test_l2_record_and_count_each_valid_outcome(self):
        """L2: record increments only the named outcome; count reflects it.

        A naive impl that ignores its input (or buckets everything into one
        counter) fails: each outcome is recorded a distinct number of times.
        """
        _mod, s = self._new_stats()
        # Record outcome i (i+1) times so every bucket has a unique count.
        for i, outcome in enumerate(self.ALLOWED):
            for _ in range(i + 1):
                assert s.record(outcome) is None, "record must return None"
        for i, outcome in enumerate(self.ALLOWED):
            assert s.count(outcome) == i + 1, (
                f"{outcome}: expected {i + 1}, got {s.count(outcome)}"
            )
        # total == sum(1..6) == 21
        assert s.total == sum(range(1, len(self.ALLOWED) + 1)) == 21

    def test_l2_record_does_not_bleed_into_other_buckets(self):
        """L2: recording one outcome leaves all others at zero."""
        _mod, s = self._new_stats()
        s.record("skipped")
        s.record("skipped")
        assert s.count("skipped") == 2
        for outcome in self.ALLOWED:
            if outcome != "skipped":
                assert s.count(outcome) == 0, outcome

    # ------------------------------------------------------------------ #
    # L2 — unknown-outcome error paths (never silently accepted)         #
    # ------------------------------------------------------------------ #
    def test_l2_record_unknown_outcome_raises_with_value(self):
        """L2: record("bogus") raises ValueError whose message names the value."""
        _mod, s = self._new_stats()
        with pytest.raises(ValueError) as exc:
            s.record("bogus")
        assert "bogus" in str(exc.value), (
            f"ValueError must contain the offending value; got: {exc.value}"
        )
        # The failed record must not have mutated any counter.
        assert s.total == 0

    def test_l2_count_unknown_outcome_raises_with_value(self):
        """L2: count("nope") raises ValueError whose message names the value."""
        _mod, s = self._new_stats()
        with pytest.raises(ValueError) as exc:
            s.count("nope")
        assert "nope" in str(exc.value), (
            f"ValueError must contain the offending value; got: {exc.value}"
        )

    def test_l2_record_passed_is_not_a_substring_alias(self):
        """L2: near-miss / case-variant names are rejected, not silently bucketed."""
        _mod, s = self._new_stats()
        for bad in ("Passed", "PASSED", "pass", "passed ", " failed", "errored"):
            with pytest.raises(ValueError):
                s.record(bad)
        assert s.total == 0

    # ------------------------------------------------------------------ #
    # L2 — total & failed_total semantics                                #
    # ------------------------------------------------------------------ #
    def test_l2_total_is_sum_of_all(self):
        """L2: total equals the sum across every recorded outcome."""
        _mod, s = self._new_stats()
        s.record("passed")
        s.record("passed")
        s.record("failed")
        s.record("xpassed")
        assert s.total == 4

    def test_l2_failed_total_counts_failed_plus_error_only(self):
        """L2: failed_total == failed + error, independent of skipped/xfailed.

        A naive impl that aliases failed_total to `total` (or omits error) fails.
        """
        _mod, s = self._new_stats()
        s.record("failed")
        s.record("failed")
        s.record("error")
        # Non-failing outcomes that must NOT affect failed_total.
        s.record("skipped")
        s.record("skipped")
        s.record("xfailed")
        s.record("passed")
        assert s.failed_total == 3, s.failed_total
        # Sanity: total counts everything, distinct from failed_total.
        assert s.total == 7
        assert s.failed_total != s.total

    def test_l2_failed_total_green_run_is_zero(self):
        """L2: a run with only passed/skipped/xfailed/xpassed is green."""
        _mod, s = self._new_stats()
        for outcome in ("passed", "skipped", "xfailed", "xpassed"):
            s.record(outcome)
        assert s.failed_total == 0
        assert s.total == 4

    # ------------------------------------------------------------------ #
    # L2 — merge: non-mutating, element-wise sum, commutative            #
    # ------------------------------------------------------------------ #
    def test_l2_merge_returns_elementwise_sum(self):
        """L2: merge yields per-outcome sums of the two operands."""
        mod, a = self._new_stats()
        b = mod.OutcomeStats()
        a.record("passed")
        a.record("passed")
        a.record("failed")
        b.record("passed")
        b.record("error")
        b.record("error")
        c = a.merge(b)
        assert c.count("passed") == 3
        assert c.count("failed") == 1
        assert c.count("error") == 2
        assert c.total == a.total + b.total == 6

    def test_l2_merge_does_not_mutate_operands(self):
        """L2: merge returns a NEW object; neither operand changes.

        A stub that mutates `self` (or returns `self`) fails this.
        """
        mod, a = self._new_stats()
        b = mod.OutcomeStats()
        a.record("passed")
        a.record("skipped")
        b.record("failed")
        a_before = {o: a.count(o) for o in self.ALLOWED}
        b_before = {o: b.count(o) for o in self.ALLOWED}
        c = a.merge(b)
        assert c is not a and c is not b, "merge must return a new object"
        assert {o: a.count(o) for o in self.ALLOWED} == a_before, "a was mutated"
        assert {o: b.count(o) for o in self.ALLOWED} == b_before, "b was mutated"

    def test_l2_merge_is_commutative_for_counts(self):
        """L2: a.merge(b) and b.merge(a) produce equal count vectors and total."""
        mod, a = self._new_stats()
        b = mod.OutcomeStats()
        a.record("passed")
        a.record("failed")
        a.record("failed")
        b.record("passed")
        b.record("skipped")
        b.record("error")
        ab = a.merge(b)
        ba = b.merge(a)
        for outcome in self.ALLOWED:
            assert ab.count(outcome) == ba.count(outcome), outcome
        assert ab.total == ba.total == a.total + b.total

    # ------------------------------------------------------------------ #
    # L2 — summary_line rendering                                        #
    # ------------------------------------------------------------------ #
    def test_l2_summary_line_basic(self):
        """L2: 3 passed + 1 failed renders "3 passed, 1 failed"."""
        mod, s = self._new_stats()
        for _ in range(3):
            s.record("passed")
        s.record("failed")
        assert mod.summary_line(s) == "3 passed, 1 failed"

    def test_l2_summary_line_omits_zero_outcomes(self):
        """L2: outcomes with a zero count are omitted from the line."""
        mod, s = self._new_stats()
        s.record("skipped")
        s.record("skipped")
        # Only skipped present -> no passed/failed/etc. noise.
        assert mod.summary_line(s) == "2 skipped"

    def test_l2_summary_line_fixed_order(self):
        """L2: present outcomes appear in the fixed canonical order regardless
        of insertion order.

        Record in a deliberately scrambled order; output must still be
        passed, failed, skipped, xfailed, xpassed, error.
        """
        mod, s = self._new_stats()
        # Scrambled insertion order.
        for outcome in ("error", "xpassed", "passed", "xfailed", "skipped", "failed"):
            s.record(outcome)
        assert mod.summary_line(s) == (
            "1 passed, 1 failed, 1 skipped, 1 xfailed, 1 xpassed, 1 error"
        )

    def test_l2_summary_line_partial_subset_keeps_order(self):
        """L2: a subset (passed, xpassed, error) stays in canonical order."""
        mod, s = self._new_stats()
        s.record("error")
        s.record("passed")
        s.record("passed")
        s.record("xpassed")
        assert mod.summary_line(s) == "2 passed, 1 xpassed, 1 error"

    def test_l2_summary_line_empty_is_no_tests_ran(self):
        """L2: with total == 0, summary_line returns the literal "no tests ran"."""
        mod, s = self._new_stats()
        assert mod.summary_line(s) == "no tests ran"

    def test_l2_summary_line_reflects_merge(self):
        """L2: summary_line over a merged stats object reflects combined counts.

        Ties merge + render together so a stub that special-cases one path fails.
        """
        mod, a = self._new_stats()
        b = mod.OutcomeStats()
        a.record("passed")
        a.record("passed")
        b.record("passed")
        b.record("failed")
        merged = a.merge(b)
        assert mod.summary_line(merged) == "3 passed, 1 failed"

    # ------------------------------------------------------------------ #
    # L2 — the task's own acceptance command must pass                   #
    # ------------------------------------------------------------------ #
    def test_l2_native_pytest_suite_passes(self):
        """L2: the agent's testing/test_outcomestats_util.py passes via native pytest.

        Runs the exact acceptance command from the task doc. Requires at least
        one test collected and zero failures.
        """
        env = dict(os.environ)
        # Ensure the repo's src tree is importable for the native suite.
        env["PYTHONPATH"] = os.path.join(self.REPO_DIR, "src")
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "testing/test_outcomestats_util.py",
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
