"""
Tests for langsmith-fetch skill.
Verifies creation of debug/analysis scripts and diagnostic report for
debugging a LangGraph agent using LangSmith traces.
"""

import ast
import os
import re
import subprocess

import pytest


class TestLangsmithFetch:
    """Tests for langsmith-fetch skill."""

    REPO_DIR = "/workspace/langchain"

    # ------------------------------------------------------------------ #
    #  file_path_check – verify expected files exist
    # ------------------------------------------------------------------ #

    def test_debug_agent_sh_exists(self):
        assert os.path.isfile(os.path.join(self.REPO_DIR, "scripts", "debug_agent.sh"))

    def test_analyze_traces_py_exists(self):
        assert os.path.isfile(os.path.join(self.REPO_DIR, "scripts", "analyze_traces.py"))

    def test_agent_diagnostic_md_exists(self):
        assert os.path.isfile(os.path.join(self.REPO_DIR, "reports", "agent_diagnostic.md"))

    # ------------------------------------------------------------------ #
    #  semantic_check – structural / content validation
    # ------------------------------------------------------------------ #

    def _read(self, relpath):
        path = os.path.join(self.REPO_DIR, relpath)
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def test_debug_script_checks_env_vars(self):
        """debug_agent.sh validates LANGSMITH_API_KEY and LANGSMITH_PROJECT."""
        content = self._read("scripts/debug_agent.sh")
        assert "LANGSMITH_API_KEY" in content, "Should check LANGSMITH_API_KEY"
        assert "LANGSMITH_PROJECT" in content, "Should check LANGSMITH_PROJECT"

    def test_debug_script_uses_langsmith_fetch(self):
        """debug_agent.sh calls langsmith-fetch commands."""
        content = self._read("scripts/debug_agent.sh")
        assert "langsmith-fetch" in content or "langsmith_fetch" in content, \
            "Should invoke langsmith-fetch CLI"

    def test_debug_script_creates_output_dirs(self):
        """debug_agent.sh creates output directories."""
        content = self._read("scripts/debug_agent.sh")
        assert "mkdir" in content, "Should create output directories with mkdir"

    def test_debug_script_exits_on_missing_env(self):
        """debug_agent.sh exits with code 1 when env vars are missing."""
        content = self._read("scripts/debug_agent.sh")
        assert "exit 1" in content or "exit1" in content.replace(" ", ""), \
            "Should exit with code 1 on missing env vars"

    def test_analyze_traces_valid_python(self):
        """analyze_traces.py is valid Python."""
        content = self._read("scripts/analyze_traces.py")
        try:
            ast.parse(content)
        except SyntaxError as e:
            pytest.fail(f"analyze_traces.py has syntax error: {e}")

    def test_analyze_traces_detects_failure_patterns(self):
        """analyze_traces.py detects the 5 required failure patterns."""
        content = self._read("scripts/analyze_traces.py").lower()
        patterns = ["empty_response", "tool_loop", "context_ignored", "timeout", "tool_error"]
        for pattern in patterns:
            assert pattern in content, f"Missing failure pattern detection: {pattern}"

    def test_analyze_traces_generates_json_report(self):
        """analyze_traces.py writes a JSON report to reports/agent_diagnostic.json."""
        content = self._read("scripts/analyze_traces.py")
        assert "agent_diagnostic.json" in content or "diagnostic" in content.lower(), \
            "Should output agent_diagnostic.json"
        assert "json" in content.lower(), "Should use json module for output"

    def test_diagnostic_report_has_required_sections(self):
        """agent_diagnostic.md contains all required report sections."""
        content = self._read("reports/agent_diagnostic.md")
        content_lower = content.lower()
        assert "executive summary" in content_lower or "summary" in content_lower, \
            "Report should have Executive Summary section"
        assert "failure" in content_lower and ("pattern" in content_lower or "breakdown" in content_lower), \
            "Report should have Failure Pattern Breakdown section"
        assert "recommendation" in content_lower, \
            "Report should have Recommendations section"

    # ------------------------------------------------------------------ #
    #  functional_check – deeper content validation
    # ------------------------------------------------------------------ #

    def test_debug_script_is_executable_bash(self):
        """debug_agent.sh starts with a bash shebang."""
        content = self._read("scripts/debug_agent.sh")
        first_line = content.strip().split("\n")[0]
        assert first_line.startswith("#!") and ("bash" in first_line or "sh" in first_line), \
            "Should have a bash/sh shebang line"

    def test_debug_script_fetches_traces_and_threads(self):
        """debug_agent.sh fetches both traces and threads from LangSmith."""
        content = self._read("scripts/debug_agent.sh")
        assert "traces" in content.lower(), "Should fetch traces"
        assert "thread" in content.lower(), "Should fetch threads"

    def test_debug_script_deep_fetches_failing_traces(self):
        """debug_agent.sh deep-fetches individual failing traces."""
        content = self._read("scripts/debug_agent.sh")
        # Should iterate over failing trace IDs
        assert "failing_trace_ids" in content or "trace_id" in content.lower() or "trace-id" in content, \
            "Should reference failing trace IDs for deep fetch"

    def test_analyze_traces_tool_loop_detection(self):
        """analyze_traces.py checks for consecutive repeated tool calls."""
        content = self._read("scripts/analyze_traces.py").lower()
        assert "consecutive" in content or "repeat" in content or "loop" in content, \
            "Should detect consecutive/repeated tool calls"

    def test_analyze_traces_context_ignored_keyword_overlap(self):
        """analyze_traces.py checks keyword overlap for context-ignored detection."""
        content = self._read("scripts/analyze_traces.py").lower()
        assert "keyword" in content or "overlap" in content or "context" in content, \
            "Should check keyword overlap for context_ignored pattern"

    def test_analyze_traces_recommendations(self):
        """analyze_traces.py generates pattern-specific recommendations."""
        content = self._read("scripts/analyze_traces.py").lower()
        assert "recommendation" in content, "Should generate recommendations"
        # Should have conditional recommendation logic
        assert "max_iteration" in content or "retry" in content or "timeout" in content, \
            "Should include specific remediation advice"

    def test_analyze_traces_summary_statistics(self):
        """analyze_traces.py computes aggregate statistics (failure rate, p95, etc.)."""
        content = self._read("scripts/analyze_traces.py").lower()
        assert "failure_rate" in content or "failure rate" in content, \
            "Should compute failure rate"
        assert "p95" in content or "percentile" in content or "quantile" in content, \
            "Should compute p95 execution time"

    def test_debug_script_prints_summary(self):
        """debug_agent.sh prints a summary of fetched traces and failures."""
        content = self._read("scripts/debug_agent.sh").lower()
        assert "fetched" in content or "summary" in content or "total" in content, \
            "Should print a summary of fetched data"
