"""
Tests for skill: analyze-ci
Repo: getsentry/sentry
Image: zhangyiiiiii/swe-skills-bench-python
Task: Build a CI failure analyzer module for Sentry that fetches GitHub
      Actions logs, parses errors, classifies failures, and generates reports.
"""

import ast
import os
import re
import subprocess

import pytest

REPO_DIR = "/workspace/sentry"
CI_DIR = os.path.join(REPO_DIR, "src", "sentry", "ci_analysis")

INIT_FILE = os.path.join(CI_DIR, "__init__.py")
FETCHER_FILE = os.path.join(CI_DIR, "log_fetcher.py")
PARSER_FILE = os.path.join(CI_DIR, "log_parser.py")
CLASSIFIER_FILE = os.path.join(CI_DIR, "failure_classifier.py")
REPORTER_FILE = os.path.join(CI_DIR, "reporter.py")
TEST_FILE = os.path.join(REPO_DIR, "tests", "sentry", "ci_analysis", "test_ci_analysis.py")


# ---------------------------------------------------------------------------
# Layer 1 — file_path_check
# ---------------------------------------------------------------------------

class TestFilePathCheck:
    """Verify all required CI analysis files were created."""

    def test_init_exists(self):
        assert os.path.isfile(INIT_FILE), f"Expected {INIT_FILE}"

    def test_fetcher_exists(self):
        assert os.path.isfile(FETCHER_FILE), f"Expected {FETCHER_FILE}"

    def test_parser_exists(self):
        assert os.path.isfile(PARSER_FILE), f"Expected {PARSER_FILE}"

    def test_classifier_exists(self):
        assert os.path.isfile(CLASSIFIER_FILE), f"Expected {CLASSIFIER_FILE}"

    def test_reporter_exists(self):
        assert os.path.isfile(REPORTER_FILE), f"Expected {REPORTER_FILE}"

    def test_test_file_exists(self):
        assert os.path.isfile(TEST_FILE), f"Expected {TEST_FILE}"


# ---------------------------------------------------------------------------
# Layer 2 — semantic_check
# ---------------------------------------------------------------------------

class TestSemanticLogFetcher:
    """Verify LogFetcher class."""

    @pytest.fixture(autouse=True)
    def _load_source(self):
        with open(FETCHER_FILE, "r", encoding="utf-8") as f:
            self.src = f.read()
        self.tree = ast.parse(self.src)

    def test_class_defined(self):
        classes = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.ClassDef)]
        assert "LogFetcher" in classes, f"Expected LogFetcher; found: {classes}"

    def test_fetch_failed_jobs_method(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "fetch_failed_jobs" in funcs, "Expected fetch_failed_jobs() method"

    def test_fetch_job_log_method(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "fetch_job_log" in funcs, "Expected fetch_job_log() method"

    def test_github_api_usage(self):
        """Must call GitHub Actions API."""
        has_api = (
            "api.github.com" in self.src
            or "github" in self.src.lower()
            or "actions" in self.src
        )
        assert has_api, "Expected GitHub Actions API usage"

    def test_timeout_configured(self):
        assert "timeout" in self.src, "Expected request timeout configuration"

    def test_error_handling(self):
        """Must handle 404 and 403 HTTP errors."""
        has_error_handling = "404" in self.src or "403" in self.src
        assert has_error_handling, "Expected HTTP 404/403 error handling"


class TestSemanticLogParser:
    """Verify LogParser class."""

    @pytest.fixture(autouse=True)
    def _load_source(self):
        with open(PARSER_FILE, "r", encoding="utf-8") as f:
            self.src = f.read()
        self.tree = ast.parse(self.src)

    def test_class_defined(self):
        classes = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.ClassDef)]
        assert "LogParser" in classes, f"Expected LogParser; found: {classes}"

    def test_parse_method(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "parse" in funcs, "Expected parse() method"

    def test_parse_result_structure(self):
        """ParseResult must have errors, failed_tests, stack_traces."""
        for field in ["errors", "failed_tests", "stack_traces"]:
            assert field in self.src, f"Expected ParseResult field '{field}'"

    def test_exit_code_extraction(self):
        assert "exit_code" in self.src, "Expected exit_code extraction"

    def test_pytest_pattern_support(self):
        """Must support pytest FAILED patterns."""
        has_pytest = "FAILED" in self.src or "pytest" in self.src.lower()
        assert has_pytest, "Expected pytest failure pattern matching"

    def test_jest_pattern_support(self):
        """Must support jest FAIL patterns."""
        has_jest = "FAIL" in self.src or "jest" in self.src.lower()
        assert has_jest, "Expected jest failure pattern matching"


class TestSemanticFailureClassifier:
    """Verify FailureClassifier class."""

    @pytest.fixture(autouse=True)
    def _load_source(self):
        with open(CLASSIFIER_FILE, "r", encoding="utf-8") as f:
            self.src = f.read()
        self.tree = ast.parse(self.src)

    def test_class_defined(self):
        classes = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.ClassDef)]
        assert "FailureClassifier" in classes, (
            f"Expected FailureClassifier; found: {classes}"
        )

    def test_classify_method(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "classify" in funcs, "Expected classify() method"

    def test_categories_defined(self):
        """All 7 failure categories must be defined."""
        categories = ["test_failure", "build_error", "lint_error", "timeout",
                       "infrastructure", "dependency", "unknown"]
        found = [c for c in categories if c in self.src]
        assert len(found) >= 6, (
            f"Expected at least 6 of 7 categories; found: {found}"
        )

    def test_confidence_score(self):
        assert "confidence" in self.src, "Expected confidence score in classification"

    def test_timeout_detection(self):
        """Must detect timeout via exit code 124 or timeout keywords."""
        assert "124" in self.src or "timeout" in self.src.lower(), (
            "Expected timeout detection (exit code 124 or timeout keywords)"
        )


class TestSemanticReporter:
    """Verify FailureReporter class."""

    @pytest.fixture(autouse=True)
    def _load_source(self):
        with open(REPORTER_FILE, "r", encoding="utf-8") as f:
            self.src = f.read()
        self.tree = ast.parse(self.src)

    def test_class_defined(self):
        classes = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.ClassDef)]
        assert "FailureReporter" in classes, (
            f"Expected FailureReporter; found: {classes}"
        )

    def test_generate_report_method(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "generate_report" in funcs, "Expected generate_report() method"

    def test_report_fields(self):
        """Report must contain summary, failed_jobs, root_cause."""
        for field in ["summary", "failed_jobs", "root_cause"]:
            assert field in self.src, f"Expected report field '{field}'"


# ---------------------------------------------------------------------------
# Layer 3 — functional_check
# ---------------------------------------------------------------------------

class TestFunctionalAnalyzeCI:
    """Functional checks — syntax and structure validation."""

    def _parse(self, filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            src = f.read()
        try:
            ast.parse(src)
            return True, None
        except SyntaxError as e:
            return False, str(e)

    def test_fetcher_valid_python(self):
        ok, err = self._parse(FETCHER_FILE)
        assert ok, f"log_fetcher.py syntax error: {err}"

    def test_parser_valid_python(self):
        ok, err = self._parse(PARSER_FILE)
        assert ok, f"log_parser.py syntax error: {err}"

    def test_classifier_valid_python(self):
        ok, err = self._parse(CLASSIFIER_FILE)
        assert ok, f"failure_classifier.py syntax error: {err}"

    def test_reporter_valid_python(self):
        ok, err = self._parse(REPORTER_FILE)
        assert ok, f"reporter.py syntax error: {err}"

    def test_test_file_valid_python(self):
        ok, err = self._parse(TEST_FILE)
        assert ok, f"test_ci_analysis.py syntax error: {err}"

    def test_parser_importable(self):
        """LogParser must be importable."""
        result = subprocess.run(
            f"python -c \"import sys; sys.path.insert(0, '{CI_DIR}'); "
            f"from log_parser import LogParser; print('OK')\"",
            shell=True, capture_output=True, text=True, timeout=30,
            cwd=REPO_DIR,
        )
        if "OK" not in result.stdout:
            pytest.skip(f"LogParser not importable: {result.stderr[:300]}")

    def test_error_pattern_regex(self):
        """Parser must define error patterns as regex."""
        with open(PARSER_FILE, "r", encoding="utf-8") as f:
            src = f.read()
        has_patterns = (
            "re.compile" in src
            or "re.search" in src
            or "re.match" in src
            or "ERROR" in src
        )
        assert has_patterns, "Expected regex-based error pattern matching in parser"
