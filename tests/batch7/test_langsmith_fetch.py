"""
Test skill: langsmith-fetch
Verify that the Agent implements a LangSmith Trace Analyzer for LangChain —
TraceAnalyzer (fetch_recent, fetch_by_trace_id, _run_to_stats), TraceReport
(properties: error_runs, tool_calls, llm_runs, total_tokens, avg/p95 latency,
to_summary_text), and RunStats dataclass.
"""

import os
import re
import subprocess
import pytest


class TestLangsmithFetch:
    REPO_DIR = "/workspace/langchain"

    # ────── helpers ──────

    def _read(self, rel_path):
        fpath = os.path.join(self.REPO_DIR, rel_path)
        with open(fpath, "r") as f:
            return f.read()

    def _exists(self, rel_path):
        return os.path.isfile(os.path.join(self.REPO_DIR, rel_path))

    # === File Path Checks ===

    def test_trace_analyzer_exists(self):
        """trace_analyzer.py must exist"""
        assert self._exists("libs/langchain/langchain/smith/trace_analyzer.py")

    def test_trace_report_exists(self):
        """trace_report.py must exist"""
        assert self._exists("libs/langchain/langchain/smith/trace_report.py")

    def test_unit_test_exists(self):
        """test_trace_analyzer.py must exist"""
        assert self._exists(
            "libs/langchain/tests/unit_tests/smith/test_trace_analyzer.py"
        )

    # === Semantic Checks — trace_report.py ===

    def test_run_stats_dataclass(self):
        """RunStats dataclass must be defined"""
        src = self._read("libs/langchain/langchain/smith/trace_report.py")
        assert "RunStats" in src
        assert "dataclass" in src

    def test_run_stats_fields(self):
        """RunStats must have required fields"""
        src = self._read("libs/langchain/langchain/smith/trace_report.py")
        for field in ["run_id", "name", "run_type", "status", "latency_ms",
                       "prompt_tokens", "completion_tokens", "total_tokens"]:
            assert field in src, f"Missing field: {field}"

    def test_trace_report_class(self):
        """TraceReport dataclass must be defined"""
        src = self._read("libs/langchain/langchain/smith/trace_report.py")
        assert "TraceReport" in src

    def test_trace_report_error_runs(self):
        """error_runs property must exist"""
        src = self._read("libs/langchain/langchain/smith/trace_report.py")
        assert "error_runs" in src

    def test_trace_report_tool_calls(self):
        """tool_calls property must exist"""
        src = self._read("libs/langchain/langchain/smith/trace_report.py")
        assert "tool_calls" in src

    def test_trace_report_llm_runs(self):
        """llm_runs property must exist"""
        src = self._read("libs/langchain/langchain/smith/trace_report.py")
        assert "llm_runs" in src

    def test_trace_report_total_tokens(self):
        """total_tokens property must exist"""
        src = self._read("libs/langchain/langchain/smith/trace_report.py")
        assert "total_tokens" in src

    def test_trace_report_avg_latency(self):
        """avg_latency_ms property must exist"""
        src = self._read("libs/langchain/langchain/smith/trace_report.py")
        assert "avg_latency" in src

    def test_trace_report_p95_latency(self):
        """p95_latency_ms property must exist"""
        src = self._read("libs/langchain/langchain/smith/trace_report.py")
        assert "p95_latency" in src

    def test_trace_report_to_summary_text(self):
        """to_summary_text method must exist"""
        src = self._read("libs/langchain/langchain/smith/trace_report.py")
        assert "to_summary_text" in src

    # === Semantic Checks — trace_analyzer.py ===

    def test_trace_analyzer_class(self):
        """TraceAnalyzer class must be defined"""
        src = self._read("libs/langchain/langchain/smith/trace_analyzer.py")
        assert re.search(r'class\s+TraceAnalyzer', src)

    def test_fetch_recent_method(self):
        """fetch_recent method must exist"""
        src = self._read("libs/langchain/langchain/smith/trace_analyzer.py")
        assert "fetch_recent" in src

    def test_fetch_by_trace_id_method(self):
        """fetch_by_trace_id method must exist"""
        src = self._read("libs/langchain/langchain/smith/trace_analyzer.py")
        assert "fetch_by_trace_id" in src

    def test_run_to_stats_method(self):
        """_run_to_stats method must exist"""
        src = self._read("libs/langchain/langchain/smith/trace_analyzer.py")
        assert "_run_to_stats" in src

    def test_langsmith_client_usage(self):
        """Must use langsmith Client"""
        src = self._read("libs/langchain/langchain/smith/trace_analyzer.py")
        assert "langsmith" in src or "Client" in src

    def test_fetch_recent_params(self):
        """fetch_recent must accept last_n_minutes, limit, run_types, error_only"""
        src = self._read("libs/langchain/langchain/smith/trace_analyzer.py")
        for param in ["last_n_minutes", "limit"]:
            assert param in src, f"Missing param: {param}"

    def test_latency_calculation(self):
        """Must calculate latency from start_time and end_time"""
        src = self._read("libs/langchain/langchain/smith/trace_analyzer.py")
        assert "latency" in src.lower() or "total_seconds" in src

    def test_token_extraction(self):
        """Must extract token counts from LLM outputs"""
        src = self._read("libs/langchain/langchain/smith/trace_analyzer.py")
        assert "token" in src.lower()

    # === Functional Checks ===

    def test_python_syntax_analyzer(self):
        """trace_analyzer.py must have valid syntax"""
        result = subprocess.run(
            ["python", "-c",
             "import py_compile; py_compile.compile("
             "'libs/langchain/langchain/smith/trace_analyzer.py', doraise=True)"],
            capture_output=True, text=True, cwd=self.REPO_DIR, timeout=30,
        )
        assert result.returncode == 0, f"Syntax error:\n{result.stderr}"

    def test_python_syntax_report(self):
        """trace_report.py must have valid syntax"""
        result = subprocess.run(
            ["python", "-c",
             "import py_compile; py_compile.compile("
             "'libs/langchain/langchain/smith/trace_report.py', doraise=True)"],
            capture_output=True, text=True, cwd=self.REPO_DIR, timeout=30,
        )
        assert result.returncode == 0, f"Syntax error:\n{result.stderr}"

    def test_unit_tests_pass(self):
        """Unit tests must pass"""
        result = subprocess.run(
            ["python", "-m", "pytest",
             "libs/langchain/tests/unit_tests/smith/test_trace_analyzer.py",
             "-v", "--tb=short"],
            capture_output=True, text=True, cwd=self.REPO_DIR, timeout=120,
        )
        assert result.returncode == 0, (
            f"Tests failed:\n{result.stdout}\n{result.stderr}"
        )
