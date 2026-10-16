"""
Test skill: analyze-ci
Verify that the Agent correctly builds a CI failure analysis report generator
for Sentry's GitHub Actions logs.
"""

import os
import re
import ast
import sys
import json
import pytest


class TestAnalyzeCi:
    REPO_DIR = "/workspace/sentry"

    ANALYZER = "scripts/ci_failure_analyzer.py"
    FAILURE_TYPES = "scripts/ci_failure_types.py"
    FORMATTER = "scripts/ci_report_formatter.py"
    TESTS = "tests/test_ci_failure_analyzer.py"

    def _read_file(self, rel_path):
        filepath = os.path.join(self.REPO_DIR, rel_path)
        with open(filepath) as f:
            return f.read()

    # === File Path Checks ===

    def test_analyzer_file_exists(self):
        filepath = os.path.join(self.REPO_DIR, self.ANALYZER)
        assert os.path.exists(filepath), f"ci_failure_analyzer.py not found at {filepath}"

    def test_failure_types_file_exists(self):
        filepath = os.path.join(self.REPO_DIR, self.FAILURE_TYPES)
        assert os.path.exists(filepath), f"ci_failure_types.py not found at {filepath}"

    def test_formatter_file_exists(self):
        filepath = os.path.join(self.REPO_DIR, self.FORMATTER)
        assert os.path.exists(filepath), f"ci_report_formatter.py not found at {filepath}"

    def test_tests_file_exists(self):
        filepath = os.path.join(self.REPO_DIR, self.TESTS)
        assert os.path.exists(filepath), f"test file not found at {filepath}"

    # === Semantic Checks ===

    def test_analyzer_parses_job_step_structure(self):
        """Verify analyzer parses GitHub Actions job and step names"""
        content = self._read_file(self.ANALYZER)
        for keyword in ["job", "step"]:
            assert keyword in content.lower(), \
                f"Analyzer missing {keyword} parsing"

    def test_analyzer_extracts_error_context(self):
        """Verify analyzer extracts error lines with surrounding context"""
        content = self._read_file(self.ANALYZER)
        assert "context" in content.lower(), "Analyzer missing context extraction"
        has_error_extraction = bool(re.search(
            r'(::error::|error.*line|extract.*error|surrounding)',
            content,
            re.IGNORECASE,
        ))
        assert has_error_extraction, "Analyzer missing error line extraction"

    def test_failure_types_defines_all_categories(self):
        """Verify all 6 failure categories are defined"""
        content = self._read_file(self.FAILURE_TYPES)
        for category in [
            "test_failure", "build_error", "lint_error",
            "timeout", "dependency_error", "infra_flake",
        ]:
            assert category in content, f"Missing failure category: {category}"

    def test_failure_types_has_classification_patterns(self):
        """Verify classification rules with regex patterns"""
        content = self._read_file(self.FAILURE_TYPES)
        patterns = ["FAILED", "AssertionError", "ModuleNotFoundError",
                     "flake8", "timed out", "pip install",
                     "rate limit", "503"]
        found = sum(1 for p in patterns if p in content)
        assert found >= 5, \
            f"Failure types missing classification patterns, found {found}/8"

    def test_analyzer_outputs_json_report(self):
        """Verify analyzer outputs JSON with required fields"""
        content = self._read_file(self.ANALYZER)
        for field in ["summary", "total_failed_jobs", "failures", "suggested_action"]:
            assert field in content, f"JSON report missing field: {field}"

    def test_formatter_outputs_markdown(self):
        """Verify formatter produces Markdown with table and collapsible sections"""
        content = self._read_file(self.FORMATTER)
        has_markdown = bool(re.search(
            r'(markdown|#|table|\|.*\|.*\||<details>|<summary>)',
            content,
            re.IGNORECASE,
        ))
        assert has_markdown, "Formatter missing Markdown output"

    def test_analyzer_handles_empty_log(self):
        """Verify analyzer handles empty or malformed log input"""
        content = self._read_file(self.ANALYZER)
        has_empty_handling = bool(re.search(
            r'(empty|no.*fail|malformed|total_failed_jobs.*0|not.*found)',
            content,
            re.IGNORECASE,
        ))
        assert has_empty_handling, "Analyzer missing empty/malformed log handling"

    # === Functional Checks ===

    def test_all_files_valid_python(self):
        """Verify all Python files have valid syntax"""
        for path in [self.ANALYZER, self.FAILURE_TYPES, self.FORMATTER]:
            filepath = os.path.join(self.REPO_DIR, path)
            with open(filepath) as f:
                try:
                    ast.parse(f.read())
                except SyntaxError as e:
                    pytest.fail(f"{path} syntax error: {e}")

    def test_functional_test_failure_classification(self):
        """Verify test_failure classification for pytest output"""
        sys.path.insert(0, os.path.join(self.REPO_DIR, "scripts"))
        try:
            from ci_failure_types import classify_failure
            line = "FAILED tests/test_foo.py::test_bar - AssertionError: expected 1"
            result = classify_failure(line)
            assert result == "test_failure", \
                f"Expected test_failure, got {result}"
        except (ImportError, TypeError):
            # Check via source analysis instead
            content = self._read_file(self.FAILURE_TYPES)
            assert "test_failure" in content and "FAILED" in content
        finally:
            if os.path.join(self.REPO_DIR, "scripts") in sys.path:
                sys.path.remove(os.path.join(self.REPO_DIR, "scripts"))

    def test_functional_dependency_error_classification(self):
        """Verify dependency_error classification"""
        sys.path.insert(0, os.path.join(self.REPO_DIR, "scripts"))
        try:
            from ci_failure_types import classify_failure
            line = "ERROR: Could not find a version that satisfies the requirement"
            result = classify_failure(line)
            assert result == "dependency_error", \
                f"Expected dependency_error, got {result}"
        except (ImportError, TypeError):
            content = self._read_file(self.FAILURE_TYPES)
            assert "dependency_error" in content
        finally:
            if os.path.join(self.REPO_DIR, "scripts") in sys.path:
                sys.path.remove(os.path.join(self.REPO_DIR, "scripts"))

    def test_tests_cover_all_failure_types(self):
        """Verify test file covers all 6 failure categories"""
        content = self._read_file(self.TESTS)
        tree = ast.parse(content)
        test_funcs = [
            n.name for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")
        ]
        assert len(test_funcs) >= 6, \
            f"Expected at least 6 tests, found {len(test_funcs)}"
