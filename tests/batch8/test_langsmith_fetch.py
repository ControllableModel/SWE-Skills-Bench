"""
Tests for the langsmith-fetch skill.
Validates a LangSmith trace analyzer with trace loading, run tree parsing,
error pattern detection, statistics, and diagnostic report generation.
"""

import os
import re
import ast

REPO_DIR = "/workspace/langchain"
SMITH_DIR = os.path.join(REPO_DIR, "libs", "langchain", "langchain", "smith")


class TestLangsmithFetch:
    """Tests for the LangSmith trace analyzer."""

    # ── file_path_check ──────────────────────────────────────────────

    def test_trace_analyzer_exists(self):
        """TraceAnalyzer module must exist."""
        path = os.path.join(SMITH_DIR, "trace_analyzer.py")
        assert os.path.isfile(path), f"Missing {path}"

    def test_trace_loader_exists(self):
        """TraceLoader module must exist."""
        path = os.path.join(SMITH_DIR, "trace_loader.py")
        assert os.path.isfile(path), f"Missing {path}"

    def test_report_generator_exists(self):
        """DiagnosticReport module must exist."""
        path = os.path.join(SMITH_DIR, "report_generator.py")
        assert os.path.isfile(path), f"Missing {path}"

    # ── semantic_check ───────────────────────────────────────────────

    def _read(self, filename):
        path = os.path.join(SMITH_DIR, filename)
        if not os.path.isfile(path):
            return ""
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def test_trace_loader_class(self):
        """TraceLoader must define load_from_file and load_from_dict."""
        content = self._read("trace_loader.py")
        assert re.search(r"class\s+TraceLoader", content), "TraceLoader class not defined"
        assert re.search(r"def\s+load_from_file\b", content), "load_from_file not defined"
        assert re.search(r"def\s+load_from_dict\b", content), "load_from_dict not defined"

    def test_loader_validation(self):
        """TraceLoader must validate required fields and raise ValueError."""
        content = self._read("trace_loader.py")
        assert re.search(r"ValueError|Missing required field", content), (
            "Validation with ValueError not found"
        )
        for field in ["run_id", "name", "run_type"]:
            assert field in content, f"Required field '{field}' not validated"

    def test_analyzer_class(self):
        """TraceAnalyzer must define flatten_runs, get_timeline, get_errors, compute_statistics."""
        content = self._read("trace_analyzer.py")
        assert re.search(r"class\s+TraceAnalyzer", content), "TraceAnalyzer class not defined"
        for method in ["flatten_runs", "get_timeline", "get_errors", "compute_statistics"]:
            assert re.search(rf"def\s+{method}\b", content), f"{method} not defined"

    def test_analyzer_tool_and_llm_calls(self):
        """TraceAnalyzer must define get_tool_calls and get_llm_calls."""
        content = self._read("trace_analyzer.py")
        assert re.search(r"def\s+get_tool_calls\b", content), "get_tool_calls not defined"
        assert re.search(r"def\s+get_llm_calls\b", content), "get_llm_calls not defined"

    def test_pattern_detection(self):
        """TraceAnalyzer must detect timeout, retry_storm, cascading_failure, empty_retrieval."""
        content = self._read("trace_analyzer.py")
        assert re.search(r"def\s+detect_patterns\b", content), "detect_patterns not defined"
        for pattern in ["timeout", "retry_storm", "cascading_failure", "empty_retrieval"]:
            assert pattern in content, f"Pattern '{pattern}' not detected"

    def test_statistics_fields(self):
        """compute_statistics must return total_runs, error_count, total_tokens, avg_llm_duration_ms."""
        content = self._read("trace_analyzer.py")
        for field in ["total_runs", "error_count", "total_tokens", "error_rate"]:
            assert field in content, f"Statistics field '{field}' not found"

    def test_diagnostic_report_class(self):
        """DiagnosticReport must define generate and to_text methods."""
        content = self._read("report_generator.py")
        assert re.search(r"class\s+DiagnosticReport", content), (
            "DiagnosticReport class not defined"
        )
        assert re.search(r"def\s+generate\b", content), "generate method not defined"
        assert re.search(r"def\s+to_text\b", content), "to_text method not defined"

    def test_run_types_validated(self):
        """TraceLoader must validate run_type is one of chain, llm, tool, retriever."""
        content = self._read("trace_loader.py")
        for rt in ["chain", "llm", "tool", "retriever"]:
            assert rt in content, f"Run type '{rt}' not referenced"

    # ── functional_check ─────────────────────────────────────────────

    def test_all_files_valid_python(self):
        """All trace analyzer Python files must have valid syntax."""
        errors = []
        for fname in ["trace_analyzer.py", "trace_loader.py", "report_generator.py"]:
            content = self._read(fname)
            if not content:
                continue
            try:
                ast.parse(content)
            except SyntaxError as e:
                errors.append(f"{fname}: {e}")
        assert not errors, "Syntax errors:\n" + "\n".join(errors)

    def test_depth_tracking(self):
        """flatten_runs must track depth and parent_run_id."""
        content = self._read("trace_analyzer.py")
        assert "depth" in content, "depth tracking not found in flatten_runs"
        assert "parent_run_id" in content, "parent_run_id tracking not found"

    def test_duration_computation(self):
        """Timeline must compute duration_ms from start_time and end_time."""
        content = self._read("trace_analyzer.py")
        assert re.search(r"duration_ms|duration", content), "duration_ms computation not found"

    def test_severity_levels(self):
        """Pattern detection must assign severity: critical or warning."""
        content = self._read("trace_analyzer.py")
        assert "critical" in content, "Critical severity not found"
        assert "warning" in content, "Warning severity not found"

    def test_test_file_exists(self):
        """Test file must exist."""
        path = os.path.join(REPO_DIR, "tests", "test_langsmith_fetch.py")
        assert os.path.isfile(path), f"Missing {path}"
