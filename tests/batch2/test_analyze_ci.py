"""
Test skill: analyze-ci
Verify that the Agent creates a CI failure analysis script for Sentry
that parses pytest logs, categorizes failures, and produces structured
analysis reports in text and JSON formats.
"""

import os
import re
import ast
import subprocess
import pytest


class TestAnalyzeCi:
    REPO_DIR = "/workspace/sentry"

    # === File Path Checks ===

    def test_script_exists(self):
        """Verify scripts/analyze_ci_failures.py exists"""
        path = os.path.join(self.REPO_DIR, "scripts/analyze_ci_failures.py")
        assert os.path.exists(path), (
            f"analyze_ci_failures.py not found at {path}"
        )

    # === Semantic Checks ===

    def test_pytest_log_parsing(self):
        """Verify script parses pytest output logs"""
        path = os.path.join(self.REPO_DIR, "scripts/analyze_ci_failures.py")
        with open(path) as f:
            content = f.read().lower()

        pytest_indicators = [
            "pytest", "test", "failed", "passed", "error",
            "traceback", "assert",
        ]
        found = [ind for ind in pytest_indicators if ind in content]
        assert len(found) >= 3, (
            f"Should parse pytest output. Found: {found}"
        )

    def test_failure_record_extraction(self):
        """Verify individual failure records are extracted"""
        path = os.path.join(self.REPO_DIR, "scripts/analyze_ci_failures.py")
        with open(path) as f:
            content = f.read().lower()

        record_indicators = [
            "test_name", "test name", "file_path", "file path",
            "failure_type", "failure type", "error_message", "error message",
            "message", "name",
        ]
        found = [ind for ind in record_indicators if ind in content]
        assert len(found) >= 3, (
            f"Should extract failure records. Found: {found}"
        )

    def test_failure_categorization(self):
        """Verify failures are categorized into groups"""
        path = os.path.join(self.REPO_DIR, "scripts/analyze_ci_failures.py")
        with open(path) as f:
            content = f.read().lower()

        category_indicators = [
            "assertion", "import", "timeout", "flake",
            "infrastructure", "category", "categoriz",
            "uncategorized",
        ]
        found = [ind for ind in category_indicators if ind in content]
        assert len(found) >= 3, (
            f"Should categorize failures. Found: {found}"
        )

    def test_traceback_handling(self):
        """Verify multi-line traceback and exception chain handling"""
        path = os.path.join(self.REPO_DIR, "scripts/analyze_ci_failures.py")
        with open(path) as f:
            content = f.read().lower()

        traceback_indicators = [
            "traceback", "exception", "chain", "multiline",
            "multi-line", "nested", "cause",
        ]
        found = [ind for ind in traceback_indicators if ind in content]
        assert len(found) >= 1, (
            f"Should handle multi-line tracebacks. Found: {found}"
        )

    def test_summary_statistics(self):
        """Verify report includes total/passed/failed/skipped counts"""
        path = os.path.join(self.REPO_DIR, "scripts/analyze_ci_failures.py")
        with open(path) as f:
            content = f.read().lower()

        stat_indicators = [
            "total", "passed", "failed", "skipped",
            "count", "summary",
        ]
        found = [ind for ind in stat_indicators if ind in content]
        assert len(found) >= 3, (
            f"Should compute summary statistics. Found: {found}"
        )

    def test_top_failing_files(self):
        """Verify report identifies top N most-failing test files"""
        path = os.path.join(self.REPO_DIR, "scripts/analyze_ci_failures.py")
        with open(path) as f:
            content = f.read().lower()

        top_indicators = [
            "top", "most", "frequent", "common",
            "file", "counter", "sorted",
        ]
        found = [ind for ind in top_indicators if ind in content]
        assert len(found) >= 2, (
            f"Should identify top failing files. Found: {found}"
        )

    def test_json_output_support(self):
        """Verify JSON output format is supported"""
        path = os.path.join(self.REPO_DIR, "scripts/analyze_ci_failures.py")
        with open(path) as f:
            content = f.read()

        assert "json" in content.lower(), (
            "Should support JSON output format"
        )
        json_indicators = [
            "json.dump", "json.dumps", "import json",
        ]
        found = [ind for ind in json_indicators if ind in content]
        assert len(found) >= 1, (
            f"Should use json module for output. Found: {found}"
        )

    def test_cli_interface(self):
        """Verify command-line argument parsing"""
        path = os.path.join(self.REPO_DIR, "scripts/analyze_ci_failures.py")
        with open(path) as f:
            content = f.read()

        cli_indicators = [
            "argparse", "ArgumentParser", "add_argument",
            "sys.argv", "click", "typer",
        ]
        found = [ind for ind in cli_indicators if ind in content]
        assert len(found) >= 1, (
            f"Should have CLI argument parsing. Found: {found}"
        )

    # === Functional Checks ===

    def test_script_valid_python(self):
        """Verify analyze_ci_failures.py is valid Python"""
        path = os.path.join(self.REPO_DIR, "scripts/analyze_ci_failures.py")
        with open(path) as f:
            source = f.read()
        try:
            ast.parse(source)
        except SyntaxError as e:
            pytest.fail(f"analyze_ci_failures.py has syntax errors: {e}")

    def test_has_main_entry_point(self):
        """Verify script has __main__ entry point"""
        path = os.path.join(self.REPO_DIR, "scripts/analyze_ci_failures.py")
        with open(path) as f:
            content = f.read()

        assert '__name__' in content and '__main__' in content, (
            "Script should have a __main__ entry point"
        )

    def test_stdin_support(self):
        """Verify script supports reading from stdin or file"""
        path = os.path.join(self.REPO_DIR, "scripts/analyze_ci_failures.py")
        with open(path) as f:
            content = f.read()

        stdin_indicators = [
            "stdin", "sys.stdin", "open(", "file",
            "input", "read()",
        ]
        found = [ind for ind in stdin_indicators if ind in content]
        assert len(found) >= 2, (
            f"Should support reading from file/stdin. Found: {found}"
        )
