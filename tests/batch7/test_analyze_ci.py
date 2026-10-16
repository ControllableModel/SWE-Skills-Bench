"""
Test skill: analyze-ci
Verify that the Agent implements a CI Build Failure Analyzer Service in
Sentry — Django models, CIFailureAnalyzer classification/extraction, and
DRF API endpoints.
"""

import os
import re
import ast
import subprocess
import pytest


class TestAnalyzeCi:
    REPO_DIR = "/workspace/sentry"

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

    def test_models_file_exists(self):
        """src/sentry/ci_analysis/models.py must exist"""
        assert self._exists("src/sentry/ci_analysis/models.py")

    def test_analyzer_file_exists(self):
        """src/sentry/ci_analysis/analyzer.py must exist"""
        assert self._exists("src/sentry/ci_analysis/analyzer.py")

    def test_api_file_exists(self):
        """src/sentry/ci_analysis/api.py must exist"""
        assert self._exists("src/sentry/ci_analysis/api.py")

    def test_init_file_exists(self):
        """src/sentry/ci_analysis/__init__.py must exist"""
        assert self._exists("src/sentry/ci_analysis/__init__.py")

    def test_analyzer_test_exists(self):
        """tests/sentry/ci_analysis/test_analyzer.py must exist"""
        assert self._exists("tests/sentry/ci_analysis/test_analyzer.py")

    def test_api_test_exists(self):
        """tests/sentry/ci_analysis/test_api.py must exist"""
        assert self._exists("tests/sentry/ci_analysis/test_api.py")

    # === Semantic Checks — Models ===

    def test_ci_build_failure_model(self):
        """CIBuildFailure model class must be defined"""
        src = self._read("src/sentry/ci_analysis/models.py")
        assert re.search(r'class\s+CIBuildFailure\b', src), (
            "CIBuildFailure model not found"
        )

    def test_model_fields(self):
        """CIBuildFailure must have key fields"""
        src = self._read("src/sentry/ci_analysis/models.py")
        for field in ["repository", "workflow_name", "job_name",
                       "run_id", "failure_type", "raw_log", "analysis_result"]:
            assert field in src, f"CIBuildFailure missing field: {field}"

    def test_failure_type_choices(self):
        """failure_type must support all six classification types"""
        src = self._read("src/sentry/ci_analysis/models.py")
        for ft in ["test_failure", "build_error", "timeout",
                    "infrastructure", "dependency", "unknown"]:
            assert ft in src, f"failure_type missing choice: {ft}"

    def test_model_indexes(self):
        """CIBuildFailure must have indexes defined"""
        src = self._read("src/sentry/ci_analysis/models.py")
        assert "index" in src.lower(), "Model indexes not found"

    # === Semantic Checks — Analyzer ===

    def test_ci_failure_analyzer_class(self):
        """CIFailureAnalyzer class must be defined"""
        src = self._read("src/sentry/ci_analysis/analyzer.py")
        assert re.search(r'class\s+CIFailureAnalyzer\b', src), (
            "CIFailureAnalyzer class not found"
        )

    def test_analyze_method(self):
        """CIFailureAnalyzer must have an analyze() method"""
        src = self._read("src/sentry/ci_analysis/analyzer.py")
        assert re.search(r'def\s+analyze\s*\(\s*self', src), (
            "analyze() method not found"
        )

    def test_analysis_result_dataclass(self):
        """AnalysisResult dataclass must be defined"""
        src = self._read("src/sentry/ci_analysis/analyzer.py")
        assert "AnalysisResult" in src, "AnalysisResult dataclass not found"

    def test_analysis_result_fields(self):
        """AnalysisResult must have required fields"""
        src = self._read("src/sentry/ci_analysis/analyzer.py")
        for field in ["failure_type", "summary", "root_cause",
                       "error_messages", "failed_tests", "stack_traces",
                       "suggestions"]:
            assert field in src, f"AnalysisResult missing field: {field}"

    def test_failed_test_dataclass(self):
        """FailedTest dataclass must be defined"""
        src = self._read("src/sentry/ci_analysis/analyzer.py")
        assert "FailedTest" in src, "FailedTest dataclass not found"

    def test_failed_test_fields(self):
        """FailedTest must have test_name, error_type, error_message"""
        src = self._read("src/sentry/ci_analysis/analyzer.py")
        for field in ["test_name", "error_type", "error_message"]:
            assert field in src, f"FailedTest missing field: {field}"

    # === Semantic Checks — Classification Patterns ===

    def test_test_failure_patterns(self):
        """Analyzer must detect test failure patterns"""
        src = self._read("src/sentry/ci_analysis/analyzer.py")
        assert "FAILED" in src or "AssertionError" in src or "pytest" in src, (
            "Test failure detection patterns not found"
        )

    def test_build_error_patterns(self):
        """Analyzer must detect build error patterns"""
        src = self._read("src/sentry/ci_analysis/analyzer.py")
        assert "SyntaxError" in src or "ModuleNotFoundError" in src or "error:" in src, (
            "Build error detection patterns not found"
        )

    def test_timeout_patterns(self):
        """Analyzer must detect timeout patterns"""
        src = self._read("src/sentry/ci_analysis/analyzer.py")
        assert "timeout" in src.lower() or "SIGKILL" in src, (
            "Timeout detection patterns not found"
        )

    def test_traceback_extraction(self):
        """Analyzer must extract Python tracebacks"""
        src = self._read("src/sentry/ci_analysis/analyzer.py")
        assert "Traceback" in src, (
            "Python traceback extraction logic not found"
        )

    # === Semantic Checks — API ===

    def test_api_post_endpoint(self):
        """POST endpoint for submitting CI logs must be defined"""
        src = self._read("src/sentry/ci_analysis/api.py")
        assert "post" in src.lower() or "POST" in src, (
            "POST endpoint not found in api.py"
        )

    def test_api_get_endpoint(self):
        """GET endpoint for retrieving analysis must be defined"""
        src = self._read("src/sentry/ci_analysis/api.py")
        assert "get" in src.lower() or "GET" in src, (
            "GET endpoint not found in api.py"
        )

    # === Functional Checks ===

    def test_analyzer_importable(self):
        """CIFailureAnalyzer must be importable"""
        result = subprocess.run(
            ["python", "-c",
             "from sentry.ci_analysis.analyzer import CIFailureAnalyzer, "
             "AnalysisResult, FailedTest; print('OK')"],
            capture_output=True, text=True, cwd=self.REPO_DIR, timeout=60,
        )
        assert "OK" in result.stdout, (
            f"Import failed:\n{result.stdout}\n{result.stderr}"
        )

    def test_analyzer_classifies_test_failure(self):
        """Analyzer should classify a pytest failure log as test_failure"""
        result = subprocess.run(
            ["python", "-c",
             "from sentry.ci_analysis.analyzer import CIFailureAnalyzer; "
             "a = CIFailureAnalyzer(); "
             "log = 'FAILED tests/test_auth.py::TestLogin::test_invalid - AssertionError'; "
             "r = a.analyze(log); "
             "assert r.failure_type == 'test_failure', f'Got {r.failure_type}'; "
             "print('OK')"],
            capture_output=True, text=True, cwd=self.REPO_DIR, timeout=60,
        )
        assert "OK" in result.stdout, (
            f"Classification test failed:\n{result.stdout}\n{result.stderr}"
        )

    def test_analyzer_classifies_timeout(self):
        """Analyzer should classify a timeout log correctly"""
        result = subprocess.run(
            ["python", "-c",
             "from sentry.ci_analysis.analyzer import CIFailureAnalyzer; "
             "a = CIFailureAnalyzer(); "
             "log = 'The job running on runner GitHub Actions 4 has exceeded the maximum time limit of 360 minutes'; "
             "r = a.analyze(log); "
             "assert r.failure_type == 'timeout', f'Got {r.failure_type}'; "
             "print('OK')"],
            capture_output=True, text=True, cwd=self.REPO_DIR, timeout=60,
        )
        assert "OK" in result.stdout, (
            f"Classification test failed:\n{result.stdout}\n{result.stderr}"
        )

    def test_analyzer_tests_pass(self):
        """Analyzer unit tests must pass"""
        result = subprocess.run(
            ["python", "-m", "pytest",
             "tests/sentry/ci_analysis/test_analyzer.py",
             "-v", "--tb=short"],
            capture_output=True, text=True, cwd=self.REPO_DIR, timeout=120,
        )
        assert result.returncode == 0, (
            f"Tests failed:\n{result.stdout}\n{result.stderr}"
        )
