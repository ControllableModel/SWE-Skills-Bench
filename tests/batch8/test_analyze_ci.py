"""
Tests for the analyze-ci skill.
Validates a CI Failure Analyzer for GitHub Actions workflows in Sentry
that fetches logs, parses failures, and classifies them into categories.
"""

import os
import re
import ast

REPO_DIR = "/workspace/sentry"
CI_DIR = os.path.join(REPO_DIR, "src", "sentry", "utils", "ci_analyzer")


class TestAnalyzeCi:
    """Tests for the CI Failure Analyzer."""

    # ── file_path_check ──────────────────────────────────────────────

    def test_init_file_exists(self):
        """Package __init__.py must exist."""
        path = os.path.join(CI_DIR, "__init__.py")
        assert os.path.isfile(path), f"Missing {path}"

    def test_fetcher_file_exists(self):
        """Fetcher module must exist."""
        path = os.path.join(CI_DIR, "fetcher.py")
        assert os.path.isfile(path), f"Missing {path}"

    def test_parser_file_exists(self):
        """Log parser module must exist."""
        path = os.path.join(CI_DIR, "parser.py")
        assert os.path.isfile(path), f"Missing {path}"

    def test_classifier_file_exists(self):
        """Failure classifier module must exist."""
        path = os.path.join(CI_DIR, "classifier.py")
        assert os.path.isfile(path), f"Missing {path}"

    def test_models_file_exists(self):
        """Data models module must exist."""
        path = os.path.join(CI_DIR, "models.py")
        assert os.path.isfile(path), f"Missing {path}"

    def test_cli_file_exists(self):
        """CLI entry point must exist."""
        path = os.path.join(CI_DIR, "cli.py")
        assert os.path.isfile(path), f"Missing {path}"

    # ── semantic_check ───────────────────────────────────────────────

    def _read(self, filename):
        path = os.path.join(CI_DIR, filename)
        if not os.path.isfile(path):
            return ""
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def test_pr_url_parsing(self):
        """Fetcher must parse GitHub PR URLs extracting owner, repo, PR number."""
        content = self._read("fetcher.py")
        assert re.search(r"owner|repo|pull|pr_number|PR.*URL", content, re.IGNORECASE), (
            "PR URL parsing not found in fetcher"
        )

    def test_invalid_url_raises_valueerror(self):
        """Invalid PR URL must raise ValueError."""
        content = self._read("fetcher.py")
        assert re.search(r"ValueError|Invalid PR URL", content), (
            "ValueError for invalid PR URL not found"
        )

    def test_classification_categories(self):
        """Classifier must support test_failure, lint_error, build_error, timeout, infra_flake, unknown."""
        content = self._read("classifier.py")
        for cat in ["test_failure", "lint_error", "build_error", "timeout", "infra_flake", "unknown"]:
            assert cat in content, f"Category '{cat}' not found in classifier"

    def test_confidence_scores(self):
        """Classifications must include confidence scores (1.0, 0.8, 0.5)."""
        content = self._read("classifier.py")
        assert re.search(r"confidence|1\.0|0\.8|0\.5", content), (
            "Confidence scores not found in classifier"
        )

    def test_log_parsing_error_patterns(self):
        """Parser must detect common error patterns (FAILED, Error:, AssertionError)."""
        content = self._read("parser.py")
        assert re.search(r"FAILED|Error:|AssertionError|TIMEOUT|exit code", content), (
            "Common error patterns not found in parser"
        )

    def test_report_json_structure(self):
        """CLI must output JSON report with pr_url, head_sha, failures, summary."""
        content = self._read("cli.py") + self._read("models.py")
        for field in ["pr_url", "head_sha", "failures", "summary"]:
            assert field in content, f"Report field '{field}' not found"

    # ── functional_check ─────────────────────────────────────────────

    def test_all_files_valid_python(self):
        """All analyzer Python files must have valid syntax."""
        errors = []
        for fname in ["__init__.py", "fetcher.py", "parser.py",
                       "classifier.py", "models.py", "cli.py"]:
            content = self._read(fname)
            if not content:
                continue
            try:
                ast.parse(content)
            except SyntaxError as e:
                errors.append(f"{fname}: {e}")
        assert not errors, "Syntax errors:\n" + "\n".join(errors)

    def test_text_format_output(self):
        """CLI must support --format text for human-readable output."""
        content = self._read("cli.py")
        assert re.search(r"text|format|table|human.readable", content, re.IGNORECASE), (
            "Text format output not found in CLI"
        )

    def test_github_api_usage(self):
        """Fetcher must use GitHub API for workflow runs and jobs."""
        content = self._read("fetcher.py")
        assert re.search(r"api\.github|actions/runs|repos/.*actions|workflow", content, re.IGNORECASE), (
            "GitHub API usage not found in fetcher"
        )

    def test_stack_trace_capture(self):
        """Parser must capture stack traces from logs."""
        content = self._read("parser.py")
        assert re.search(r"stack.trace|traceback|indent|consecutive", content, re.IGNORECASE), (
            "Stack trace capture not found in parser"
        )

    def test_unavailable_log_handling(self):
        """Parser must handle unavailable logs gracefully."""
        content = self._read("parser.py") + self._read("classifier.py")
        assert re.search(r"unavailable|empty|cannot.*download|Log unavailable", content, re.IGNORECASE), (
            "Unavailable log handling not found"
        )

    def test_iso_timestamp_in_report(self):
        """Report must include ISO 8601 timestamp."""
        content = self._read("cli.py") + self._read("models.py")
        assert re.search(r"isoformat|ISO.*8601|analyzed_at|datetime", content, re.IGNORECASE), (
            "ISO 8601 timestamp not found in report"
        )
