"""
Test skill: python-background-jobs
Verify that the Agent adds a ResultAggregator utility to Celery's contrib
module — collecting grouped task results, handling partial failures,
max-failures thresholds, timeouts, reduce/filter, and progress callbacks.
"""

import os
import re
import ast
import subprocess
import pytest


class TestPythonBackgroundJobs:
    REPO_DIR = "/workspace/celery"

    # ────────────────── helpers ──────────────────

    def _read(self, rel_path):
        fpath = os.path.join(self.REPO_DIR, rel_path)
        with open(fpath, "r") as f:
            return f.read()

    def _exists(self, rel_path):
        return os.path.isfile(os.path.join(self.REPO_DIR, rel_path))

    def _parse(self, rel_path):
        fpath = os.path.join(self.REPO_DIR, rel_path)
        with open(fpath, "r") as f:
            return ast.parse(f.read())

    # === File Path Checks ===

    def test_result_aggregator_module_exists(self):
        """celery/contrib/result_aggregator.py must exist"""
        assert self._exists("celery/contrib/result_aggregator.py")

    def test_contrib_init_exists(self):
        """celery/contrib/__init__.py must exist"""
        assert self._exists("celery/contrib/__init__.py")

    def test_unit_test_file_exists(self):
        """t/unit/contrib/test_result_aggregator.py must exist"""
        assert self._exists("t/unit/contrib/test_result_aggregator.py")

    # === Semantic Checks — Class Definitions ===

    def test_result_aggregator_class_defined(self):
        """ResultAggregator class must be defined"""
        tree = self._parse("celery/contrib/result_aggregator.py")
        classes = [n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
        assert "ResultAggregator" in classes, "ResultAggregator class not found"

    def test_aggregation_result_class_defined(self):
        """AggregationResult class must be defined"""
        tree = self._parse("celery/contrib/result_aggregator.py")
        classes = [n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
        assert "AggregationResult" in classes, "AggregationResult class not found"

    def test_failed_task_class_defined(self):
        """FailedTask class must be defined"""
        tree = self._parse("celery/contrib/result_aggregator.py")
        classes = [n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
        assert "FailedTask" in classes, "FailedTask class not found"

    def test_max_failures_exceeded_exception_defined(self):
        """MaxFailuresExceeded exception must be defined"""
        tree = self._parse("celery/contrib/result_aggregator.py")
        classes = [n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
        assert "MaxFailuresExceeded" in classes, "MaxFailuresExceeded exception not found"

    # === Semantic Checks — ResultAggregator Methods ===

    def test_collect_method(self):
        """ResultAggregator must have a collect() method"""
        src = self._read("celery/contrib/result_aggregator.py")
        assert re.search(r'def\s+collect\s*\(\s*self', src), (
            "collect() method not found"
        )

    def test_reduce_method(self):
        """ResultAggregator must have a reduce() method"""
        src = self._read("celery/contrib/result_aggregator.py")
        assert re.search(r'def\s+reduce\s*\(\s*self', src), (
            "reduce() method not found"
        )

    def test_filter_method(self):
        """ResultAggregator must have a filter() method"""
        src = self._read("celery/contrib/result_aggregator.py")
        assert re.search(r'def\s+filter\s*\(\s*self', src), (
            "filter() method not found"
        )

    # === Semantic Checks — Constructor Parameters ===

    def test_constructor_parameters(self):
        """__init__ must accept group_result, on_result, on_error, timeout, max_failures"""
        src = self._read("celery/contrib/result_aggregator.py")
        init_match = re.search(r'def\s+__init__\s*\(self.*?\)', src, re.DOTALL)
        assert init_match, "__init__ not found"
        init_sig = init_match.group(0)
        for param in ["group_result", "on_result", "on_error", "timeout", "max_failures"]:
            assert param in init_sig, f"Constructor missing parameter: {param}"

    # === Semantic Checks — AggregationResult Attributes ===

    def test_aggregation_result_fields(self):
        """AggregationResult must have succeeded, failed, total, success_count,
        failure_count, elapsed attributes"""
        src = self._read("celery/contrib/result_aggregator.py")
        for field in ["succeeded", "failed", "total", "success_count",
                       "failure_count", "elapsed"]:
            assert field in src, f"AggregationResult missing field: {field}"

    def test_success_rate_property(self):
        """AggregationResult must have a success_rate property"""
        src = self._read("celery/contrib/result_aggregator.py")
        assert "success_rate" in src, "success_rate property not found"

    def test_is_complete_property(self):
        """AggregationResult must have an is_complete property"""
        src = self._read("celery/contrib/result_aggregator.py")
        assert "is_complete" in src, "is_complete property not found"

    # === Semantic Checks — FailedTask Attributes ===

    def test_failed_task_fields(self):
        """FailedTask must have index, task_id, exception attributes"""
        src = self._read("celery/contrib/result_aggregator.py")
        for field in ["index", "task_id", "exception"]:
            assert field in src, f"FailedTask missing field: {field}"

    # === Semantic Checks — MaxFailuresExceeded ===

    def test_max_failures_has_partial_result(self):
        """MaxFailuresExceeded must expose partial_result attribute"""
        src = self._read("celery/contrib/result_aggregator.py")
        assert "partial_result" in src, (
            "MaxFailuresExceeded missing partial_result attribute"
        )

    # === Semantic Checks — Behavioural Requirements ===

    def test_uses_functools_reduce(self):
        """reduce() method should use functools.reduce"""
        src = self._read("celery/contrib/result_aggregator.py")
        assert "functools" in src, "functools not imported — needed for reduce()"

    def test_propagate_false(self):
        """collect() must call .get(propagate=False) to avoid exception propagation"""
        src = self._read("celery/contrib/result_aggregator.py")
        assert "propagate=False" in src or "propagate = False" in src, (
            "collect() should use propagate=False"
        )

    # === Semantic Checks — Export ===

    def test_contrib_init_exports_result_aggregator(self):
        """celery/contrib/__init__.py must export ResultAggregator"""
        src = self._read("celery/contrib/__init__.py")
        assert "ResultAggregator" in src, (
            "ResultAggregator not exported from celery.contrib"
        )

    # === Functional Checks ===

    def test_module_importable(self):
        """ResultAggregator must be importable"""
        result = subprocess.run(
            ["python", "-c",
             "from celery.contrib.result_aggregator import "
             "ResultAggregator, AggregationResult, FailedTask, MaxFailuresExceeded; "
             "print('OK')"],
            capture_output=True, text=True, cwd=self.REPO_DIR, timeout=60,
        )
        assert "OK" in result.stdout, (
            f"Import failed:\n{result.stdout}\n{result.stderr}"
        )

    def test_unit_tests_pass(self):
        """Unit tests for result_aggregator must pass"""
        result = subprocess.run(
            ["python", "-m", "pytest",
             "t/unit/contrib/test_result_aggregator.py",
             "-v", "--tb=short"],
            capture_output=True, text=True, cwd=self.REPO_DIR, timeout=120,
        )
        assert result.returncode == 0, (
            f"Unit tests failed:\n{result.stdout}\n{result.stderr}"
        )

    def test_aggregation_result_success_rate_zero_division(self):
        """AggregationResult.success_rate must handle total=0 without ZeroDivisionError"""
        result = subprocess.run(
            ["python", "-c",
             "from celery.contrib.result_aggregator import AggregationResult; "
             "r = AggregationResult(succeeded=[], failed=[], total=0, "
             "success_count=0, failure_count=0, elapsed=0.0); "
             "assert r.success_rate == 0.0; "
             "print('OK')"],
            capture_output=True, text=True, cwd=self.REPO_DIR, timeout=30,
        )
        assert "OK" in result.stdout, (
            f"success_rate zero-division check failed:\n{result.stdout}\n{result.stderr}"
        )

    def test_aggregation_result_is_complete_true(self):
        """is_complete should be True when all tasks are accounted for"""
        result = subprocess.run(
            ["python", "-c",
             "from celery.contrib.result_aggregator import AggregationResult; "
             "r = AggregationResult(succeeded=[1,2], failed=[], total=2, "
             "success_count=2, failure_count=0, elapsed=1.0); "
             "assert r.is_complete is True; "
             "print('OK')"],
            capture_output=True, text=True, cwd=self.REPO_DIR, timeout=30,
        )
        assert "OK" in result.stdout, (
            f"is_complete check failed:\n{result.stdout}\n{result.stderr}"
        )
