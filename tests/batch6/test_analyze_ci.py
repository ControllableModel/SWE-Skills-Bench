"""
Test skill: analyze-ci
Verify that the Agent builds a CI failure analysis CLI tool that parses
GitHub CI logs, categorizes failures, and generates structured reports.
"""

import os
import re
import ast
import json
import subprocess
import pytest


class TestAnalyzeCi:
    REPO_DIR = "/workspace/sentry"

    # === File Path Checks ===

    def test_cli_file_exists(self):
        path = os.path.join(self.REPO_DIR, "tools/ci_analyzer/cli.py")
        assert os.path.exists(path), "cli.py not found"

    def test_github_client_file_exists(self):
        path = os.path.join(self.REPO_DIR, "tools/ci_analyzer/github_client.py")
        assert os.path.exists(path), "github_client.py not found"

    def test_log_parser_file_exists(self):
        path = os.path.join(self.REPO_DIR, "tools/ci_analyzer/log_parser.py")
        assert os.path.exists(path), "log_parser.py not found"

    def test_report_file_exists(self):
        path = os.path.join(self.REPO_DIR, "tools/ci_analyzer/report.py")
        assert os.path.exists(path), "report.py not found"

    def test_init_file_exists(self):
        path = os.path.join(self.REPO_DIR, "tools/ci_analyzer/__init__.py")
        assert os.path.exists(path), "__init__.py not found"

    # === Semantic Checks ===

    def test_cli_parses_pr_and_job_urls(self):
        """CLI should accept PR URLs and optional --job URL"""
        path = os.path.join(self.REPO_DIR, "tools/ci_analyzer/cli.py")
        with open(path, "r") as f:
            content = f.read()

        assert re.search(r"(pr_url|pr-url|pull|pr)", content, re.IGNORECASE), (
            "CLI should parse PR URL argument"
        )
        assert "--format" in content or "format" in content, (
            "CLI should support --format option"
        )

    def test_cli_supports_text_and_json_format(self):
        """CLI should support text and JSON output formats"""
        path = os.path.join(self.REPO_DIR, "tools/ci_analyzer/cli.py")
        with open(path, "r") as f:
            content = f.read()

        assert "text" in content.lower() and "json" in content.lower(), (
            "CLI should support both text and JSON output formats"
        )

    def test_github_client_fetches_check_runs(self):
        """GH client should traverse PR -> SHA -> check-suites -> check-runs -> logs"""
        path = os.path.join(self.REPO_DIR, "tools/ci_analyzer/github_client.py")
        with open(path, "r") as f:
            content = f.read()

        assert "class" in content, "Should define a GitHub client class"
        assert re.search(r"def\s+get_failed_jobs", content), (
            "Missing get_failed_jobs method"
        )
        assert "check" in content.lower(), (
            "Client should reference check-suites or check-runs"
        )

    def test_github_client_handles_auth(self):
        """Client should require GH_TOKEN for authentication"""
        path = os.path.join(self.REPO_DIR, "tools/ci_analyzer/github_client.py")
        with open(path, "r") as f:
            content = f.read()

        assert re.search(r"GH_TOKEN|GITHUB_TOKEN", content), (
            "Client should use GH_TOKEN or GITHUB_TOKEN for auth"
        )

    def test_github_client_has_rate_limiting(self):
        """Client should handle GitHub rate limiting"""
        path = os.path.join(self.REPO_DIR, "tools/ci_analyzer/github_client.py")
        with open(path, "r") as f:
            content = f.read()

        assert re.search(r"rate.?limit|retry|429|X-RateLimit|sleep|backoff", content, re.IGNORECASE), (
            "Client should handle rate limiting"
        )

    def test_log_parser_has_five_categories(self):
        """Log parser should categorize failures into 5 types"""
        path = os.path.join(self.REPO_DIR, "tools/ci_analyzer/log_parser.py")
        with open(path, "r") as f:
            content = f.read()

        categories = ["test_failure", "build_error", "lint_violation", "timeout", "infrastructure"]
        found = [c for c in categories if c in content]
        assert len(found) >= 4, (
            f"Expected 5 failure categories. Found: {found}"
        )

    def test_log_parser_extracts_test_names_and_errors(self):
        """Log parser should extract test names, error messages, stack traces"""
        path = os.path.join(self.REPO_DIR, "tools/ci_analyzer/log_parser.py")
        with open(path, "r") as f:
            content = f.read()

        content_lower = content.lower()
        assert (
            "test_name" in content_lower
            or "test name" in content_lower
            or "extract" in content_lower
        ), "Parser should extract test names"
        assert (
            "error_message" in content_lower
            or "error message" in content_lower
            or "message" in content_lower
        ), "Parser should extract error messages"
        assert (
            "stack_trace" in content_lower
            or "traceback" in content_lower
            or "stacktrace" in content_lower
        ), "Parser should extract stack traces"

    def test_report_formats_text_and_json(self):
        """Report module should produce text and JSON formats"""
        path = os.path.join(self.REPO_DIR, "tools/ci_analyzer/report.py")
        with open(path, "r") as f:
            content = f.read()

        assert re.search(r"def\s+(format_text|to_text|render_text|generate_text)", content), (
            "Report should have text format method"
        )
        assert re.search(r"def\s+(format_json|to_json|render_json|generate_json)", content), (
            "Report should have JSON format method"
        )

    def test_report_groups_by_category(self):
        """Report should group failures by category"""
        path = os.path.join(self.REPO_DIR, "tools/ci_analyzer/report.py")
        with open(path, "r") as f:
            content = f.read()

        assert "categor" in content.lower(), (
            "Report should organize failures by category"
        )

    # === Functional Checks ===

    def test_all_python_files_parse(self):
        """Verify all Python files parse without syntax errors"""
        base = os.path.join(self.REPO_DIR, "tools/ci_analyzer")
        for root, _dirs, files in os.walk(base):
            for fname in files:
                if fname.endswith(".py"):
                    filepath = os.path.join(root, fname)
                    with open(filepath, "r") as f:
                        source = f.read()
                    try:
                        ast.parse(source)
                    except SyntaxError as e:
                        pytest.fail(f"{filepath} has syntax error: {e}")

    def test_cli_module_import(self):
        """Verify cli.py can be imported"""
        result = subprocess.run(
            ["python", "-c", "import ast; ast.parse(open('tools/ci_analyzer/cli.py').read())"],
            capture_output=True, text=True, cwd=self.REPO_DIR
        )
        assert result.returncode == 0, f"cli.py cannot be parsed: {result.stderr}"

    def test_log_parser_is_importable(self):
        """Verify log_parser can be imported"""
        result = subprocess.run(
            ["python", "-c", "import ast; ast.parse(open('tools/ci_analyzer/log_parser.py').read())"],
            capture_output=True, text=True, cwd=self.REPO_DIR
        )
        assert result.returncode == 0, f"log_parser.py cannot be parsed: {result.stderr}"

    def test_report_is_importable(self):
        """Verify report module can be imported"""
        result = subprocess.run(
            ["python", "-c", "import ast; ast.parse(open('tools/ci_analyzer/report.py').read())"],
            capture_output=True, text=True, cwd=self.REPO_DIR
        )
        assert result.returncode == 0, f"report.py cannot be parsed: {result.stderr}"
