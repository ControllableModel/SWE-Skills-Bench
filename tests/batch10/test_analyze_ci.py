"""
Test skill: analyze-ci
Verify that the Agent correctly implements a GitHub Actions CI failure
analyzer CLI for the Sentry project.
"""

import os
import re
import ast
import subprocess
import pytest


class TestAnalyzeCi:
    REPO_DIR = "/workspace/sentry"

    # === File Path Checks ===

    def test_analyzer_exists(self):
        """Verify analyzer.py was created"""
        path = os.path.join(self.REPO_DIR, "src/sentry/utils/ci/analyzer.py")
        assert os.path.exists(path), f"analyzer.py not found at {path}"

    def test_github_client_exists(self):
        """Verify github_client.py was created"""
        path = os.path.join(self.REPO_DIR, "src/sentry/utils/ci/github_client.py")
        assert os.path.exists(path), f"github_client.py not found at {path}"

    def test_log_parser_exists(self):
        """Verify log_parser.py was created"""
        path = os.path.join(self.REPO_DIR, "src/sentry/utils/ci/log_parser.py")
        assert os.path.exists(path), f"log_parser.py not found at {path}"

    def test_formatter_exists(self):
        """Verify formatter.py was created"""
        path = os.path.join(self.REPO_DIR, "src/sentry/utils/ci/formatter.py")
        assert os.path.exists(path), f"formatter.py not found at {path}"

    def test_cli_exists(self):
        """Verify cli.py was created"""
        path = os.path.join(self.REPO_DIR, "src/sentry/utils/ci/cli.py")
        assert os.path.exists(path), f"cli.py not found at {path}"

    def test_log_parser_test_exists(self):
        """Verify test_log_parser.py was created"""
        path = os.path.join(self.REPO_DIR, "tests/sentry/utils/ci/test_log_parser.py")
        assert os.path.exists(path), f"test_log_parser.py not found at {path}"

    def test_analyzer_test_exists(self):
        """Verify test_analyzer.py was created"""
        path = os.path.join(self.REPO_DIR, "tests/sentry/utils/ci/test_analyzer.py")
        assert os.path.exists(path), f"test_analyzer.py not found at {path}"

    def test_formatter_test_exists(self):
        """Verify test_formatter.py was created"""
        path = os.path.join(self.REPO_DIR, "tests/sentry/utils/ci/test_formatter.py")
        assert os.path.exists(path), f"test_formatter.py not found at {path}"

    # === Semantic Checks: GitHub Client ===

    def test_github_client_class(self):
        """Verify GitHubActionsClient class is defined"""
        path = os.path.join(self.REPO_DIR, "src/sentry/utils/ci/github_client.py")
        with open(path) as f:
            content = f.read()
        assert "class GitHubActionsClient" in content, (
            "GitHubActionsClient class should be defined"
        )

    def test_github_client_token_from_env(self):
        """Verify token is read from GH_TOKEN env var"""
        path = os.path.join(self.REPO_DIR, "src/sentry/utils/ci/github_client.py")
        with open(path) as f:
            content = f.read()
        assert "GH_TOKEN" in content, "Should read GH_TOKEN from environment"

    def test_github_client_parse_url(self):
        """Verify parse_url method is defined"""
        path = os.path.join(self.REPO_DIR, "src/sentry/utils/ci/github_client.py")
        with open(path) as f:
            content = f.read()
        assert "def parse_url(" in content, "Should have parse_url method"

    def test_github_client_get_failed_jobs(self):
        """Verify get_failed_jobs method is defined"""
        path = os.path.join(self.REPO_DIR, "src/sentry/utils/ci/github_client.py")
        with open(path) as f:
            content = f.read()
        assert "get_failed_jobs" in content, "Should have get_failed_jobs method"

    def test_github_client_download_job_log(self):
        """Verify download_job_log method is defined"""
        path = os.path.join(self.REPO_DIR, "src/sentry/utils/ci/github_client.py")
        with open(path) as f:
            content = f.read()
        assert "download_job_log" in content, (
            "Should have download_job_log method"
        )

    def test_github_client_uses_auth_header(self):
        """Verify Authorization header is set"""
        path = os.path.join(self.REPO_DIR, "src/sentry/utils/ci/github_client.py")
        with open(path) as f:
            content = f.read()
        assert "Authorization" in content or "Bearer" in content, (
            "Should set Authorization: Bearer header"
        )

    # === Semantic Checks: Log Parser ===

    def test_log_parser_parse_log(self):
        """Verify parse_log function is defined"""
        path = os.path.join(self.REPO_DIR, "src/sentry/utils/ci/log_parser.py")
        with open(path) as f:
            content = f.read()
        assert "def parse_log(" in content, "Should have parse_log function"

    def test_log_parser_extracts_errors(self):
        """Verify error extraction patterns"""
        path = os.path.join(self.REPO_DIR, "src/sentry/utils/ci/log_parser.py")
        with open(path) as f:
            content = f.read()
        assert "errors" in content, "Should extract error lines"

    def test_log_parser_extracts_stack_traces(self):
        """Verify stack trace extraction"""
        path = os.path.join(self.REPO_DIR, "src/sentry/utils/ci/log_parser.py")
        with open(path) as f:
            content = f.read()
        assert "stack_traces" in content or "Traceback" in content, (
            "Should extract Python/JS stack traces"
        )

    def test_log_parser_extracts_failed_tests(self):
        """Verify test failure extraction for pytest and Jest"""
        path = os.path.join(self.REPO_DIR, "src/sentry/utils/ci/log_parser.py")
        with open(path) as f:
            content = f.read()
        assert "failed_tests" in content, "Should extract failed tests"
        assert "FAILED" in content, "Should detect pytest FAILED patterns"

    def test_log_parser_strips_ansi(self):
        """Verify ANSI escape code stripping"""
        path = os.path.join(self.REPO_DIR, "src/sentry/utils/ci/log_parser.py")
        with open(path) as f:
            content = f.read()
        assert "\\x1b" in content or "ansi" in content.lower() or "\\033" in content, (
            "Should strip ANSI escape codes"
        )

    def test_log_parser_extracts_annotations(self):
        """Verify GitHub Actions annotation extraction"""
        path = os.path.join(self.REPO_DIR, "src/sentry/utils/ci/log_parser.py")
        with open(path) as f:
            content = f.read()
        assert "::error::" in content or "annotations" in content, (
            "Should extract ::error:: annotations"
        )

    def test_log_parser_extract_context(self):
        """Verify extract_relevant_context function is defined"""
        path = os.path.join(self.REPO_DIR, "src/sentry/utils/ci/log_parser.py")
        with open(path) as f:
            content = f.read()
        assert "extract_relevant_context" in content, (
            "Should have extract_relevant_context function"
        )

    # === Semantic Checks: Formatter ===

    def test_formatter_format_summary(self):
        """Verify format_summary function is defined"""
        path = os.path.join(self.REPO_DIR, "src/sentry/utils/ci/formatter.py")
        with open(path) as f:
            content = f.read()
        assert "def format_summary(" in content, (
            "Should have format_summary function"
        )

    def test_formatter_supports_text_and_json(self):
        """Verify both text and json formats are supported"""
        path = os.path.join(self.REPO_DIR, "src/sentry/utils/ci/formatter.py")
        with open(path) as f:
            content = f.read()
        assert "text" in content, "Should support text format"
        assert "json" in content, "Should support json format"

    def test_formatter_has_markdown_headers(self):
        """Verify text format includes markdown headers"""
        path = os.path.join(self.REPO_DIR, "src/sentry/utils/ci/formatter.py")
        with open(path) as f:
            content = f.read()
        assert "CI Failure Summary" in content, (
            "Should include CI Failure Summary header"
        )

    # === Semantic Checks: CLI ===

    def test_cli_uses_argparse(self):
        """Verify CLI uses argparse"""
        path = os.path.join(self.REPO_DIR, "src/sentry/utils/ci/cli.py")
        with open(path) as f:
            content = f.read()
        assert "argparse" in content, "CLI should use argparse"

    def test_cli_has_debug_flag(self):
        """Verify --debug flag"""
        path = os.path.join(self.REPO_DIR, "src/sentry/utils/ci/cli.py")
        with open(path) as f:
            content = f.read()
        assert "debug" in content, "CLI should have --debug flag"

    def test_cli_has_format_flag(self):
        """Verify --format flag"""
        path = os.path.join(self.REPO_DIR, "src/sentry/utils/ci/cli.py")
        with open(path) as f:
            content = f.read()
        assert "format" in content, "CLI should have --format flag"

    # === Functional Checks ===

    def test_log_parser_parses(self):
        """Verify log_parser.py has valid Python syntax"""
        path = os.path.join(self.REPO_DIR, "src/sentry/utils/ci/log_parser.py")
        with open(path) as f:
            source = f.read()
        try:
            ast.parse(source)
        except SyntaxError as e:
            pytest.fail(f"log_parser.py has syntax error: {e}")

    def test_formatter_parses(self):
        """Verify formatter.py has valid Python syntax"""
        path = os.path.join(self.REPO_DIR, "src/sentry/utils/ci/formatter.py")
        with open(path) as f:
            source = f.read()
        try:
            ast.parse(source)
        except SyntaxError as e:
            pytest.fail(f"formatter.py has syntax error: {e}")

    def test_log_parser_tests_pass(self):
        """Verify log parser tests pass"""
        result = subprocess.run(
            [
                "python", "-m", "pytest",
                "tests/sentry/utils/ci/test_log_parser.py",
                "-v", "--tb=short",
            ],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, (
            f"Log parser tests failed:\n{result.stdout}\n{result.stderr}"
        )

    def test_formatter_tests_pass(self):
        """Verify formatter tests pass"""
        result = subprocess.run(
            [
                "python", "-m", "pytest",
                "tests/sentry/utils/ci/test_formatter.py",
                "-v", "--tb=short",
            ],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, (
            f"Formatter tests failed:\n{result.stdout}\n{result.stderr}"
        )
