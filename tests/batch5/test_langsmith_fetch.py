"""
Test skill: langsmith-fetch
Verify that the Agent builds a LangSmith run trace fetcher with
analyzer, quality report generator, and CLI.
"""

import os
import re
import ast
import pytest


class TestLangsmithFetch:
    REPO_DIR = "/workspace/langchain"

    BASE = "libs/community/langchain_community/callbacks"
    FETCHER = f"{BASE}/langsmith_fetcher.py"
    ANALYZER = f"{BASE}/trace_analyzer.py"
    REPORT = f"{BASE}/quality_report.py"
    CLI = f"{BASE}/cli.py"
    TESTS = "libs/community/tests/unit_tests/callbacks/test_langsmith_fetcher.py"

    def _read_file(self, rel_path):
        filepath = os.path.join(self.REPO_DIR, rel_path)
        with open(filepath) as f:
            return f.read()

    # === File Path Checks ===

    def test_fetcher_exists(self):
        filepath = os.path.join(self.REPO_DIR, self.FETCHER)
        assert os.path.exists(filepath), "langsmith_fetcher.py not found"

    def test_analyzer_exists(self):
        filepath = os.path.join(self.REPO_DIR, self.ANALYZER)
        assert os.path.exists(filepath), "trace_analyzer.py not found"

    def test_report_exists(self):
        filepath = os.path.join(self.REPO_DIR, self.REPORT)
        assert os.path.exists(filepath), "quality_report.py not found"

    def test_cli_exists(self):
        filepath = os.path.join(self.REPO_DIR, self.CLI)
        assert os.path.exists(filepath), "cli.py not found"

    def test_tests_exist(self):
        filepath = os.path.join(self.REPO_DIR, self.TESTS)
        assert os.path.exists(filepath), "test_langsmith_fetcher.py not found"

    # === Semantic Checks ===

    def test_fetcher_class_defined(self):
        """Verify LangSmithFetcher class with api_key parameter"""
        content = self._read_file(self.FETCHER)
        assert "LangSmithFetcher" in content, "Missing LangSmithFetcher class"
        assert "api_key" in content, "Fetcher missing api_key parameter"

    def test_fetcher_fetch_runs_method(self):
        """Verify fetch_runs with project_name, date range, pagination"""
        content = self._read_file(self.FETCHER)
        assert "fetch_runs" in content, "Missing fetch_runs method"
        assert "project_name" in content, "fetch_runs missing project_name"
        assert "pagination" in content.lower() or "cursor" in content.lower() \
            or "offset" in content.lower() or "limit" in content, \
            "fetch_runs missing pagination support"

    def test_fetcher_run_trace_dataclass(self):
        """Verify RunTrace dataclass with required fields"""
        content = self._read_file(self.FETCHER)
        assert "RunTrace" in content, "Missing RunTrace dataclass"
        for field in ["latency_ms", "total_tokens", "status", "model_name"]:
            assert field in content, f"RunTrace missing field: {field}"

    def test_fetcher_authentication_error(self):
        """Verify 401 raises AuthenticationError"""
        content = self._read_file(self.FETCHER)
        assert "AuthenticationError" in content, "Missing AuthenticationError"
        assert "401" in content, "Missing 401 handling"

    def test_analyzer_latency_stats(self):
        """Verify compute_latency_stats with p50/p95/p99"""
        content = self._read_file(self.ANALYZER)
        assert "TraceAnalyzer" in content, "Missing TraceAnalyzer class"
        assert "compute_latency_stats" in content, "Missing compute_latency_stats"
        for pct in ["p50", "p95", "p99"]:
            assert pct in content, f"Analyzer missing {pct} percentile"

    def test_analyzer_token_stats(self):
        """Verify compute_token_stats method"""
        content = self._read_file(self.ANALYZER)
        assert "compute_token_stats" in content, "Missing compute_token_stats"
        assert "total_tokens" in content, "Analyzer missing total_tokens"

    def test_analyzer_error_stats(self):
        """Verify compute_error_stats with error_rate"""
        content = self._read_file(self.ANALYZER)
        assert "compute_error_stats" in content, "Missing compute_error_stats"
        assert "error_rate" in content, "Analyzer missing error_rate"

    def test_analyzer_model_distribution(self):
        """Verify compute_model_distribution method"""
        content = self._read_file(self.ANALYZER)
        assert "compute_model_distribution" in content, \
            "Missing compute_model_distribution"

    def test_report_generate_markdown(self):
        """Verify generate_markdown with summary table and slowest runs"""
        content = self._read_file(self.REPORT)
        assert "generate_markdown" in content, "Missing generate_markdown"
        assert "slowest" in content.lower() or "top" in content.lower(), \
            "Report missing top slowest runs"

    def test_report_latency_distribution(self):
        """Verify latency distribution buckets"""
        content = self._read_file(self.REPORT)
        has_buckets = bool(re.search(r'(100ms|500ms|1s|5s|bucket)', content))
        assert has_buckets, "Report missing latency distribution buckets"

    def test_cli_argparse(self):
        """Verify CLI accepts --project, --start-date, --output, --format"""
        content = self._read_file(self.CLI)
        assert "argparse" in content, "CLI missing argparse"
        for arg in ["--project", "--start-date", "--output", "--format"]:
            assert arg in content, f"CLI missing {arg} argument"

    # === Functional Checks ===

    def test_all_files_valid_python(self):
        """Verify all Python files have valid syntax"""
        for path in [self.FETCHER, self.ANALYZER, self.REPORT,
                     self.CLI, self.TESTS]:
            filepath = os.path.join(self.REPO_DIR, path)
            with open(filepath) as f:
                try:
                    ast.parse(f.read())
                except SyntaxError as e:
                    pytest.fail(f"{path} syntax error: {e}")

    def test_tests_mock_api(self):
        """Verify tests use mocked API responses"""
        content = self._read_file(self.TESTS)
        has_mock = bool(re.search(r'(mock|Mock|patch|MagicMock)', content))
        assert has_mock, "Tests missing mocked API responses"
        tree = ast.parse(content)
        test_funcs = [
            n.name for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")
        ]
        assert len(test_funcs) >= 3, \
            f"Expected >=3 tests, found {len(test_funcs)}"
