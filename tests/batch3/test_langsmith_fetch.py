"""
Tests for the langsmith-fetch skill.

Validates that a LangSmith trace analysis and export module was implemented
for LangChain, including trace models, latency analysis, bottleneck detection,
error analysis, and session export.

Repo: langchain (https://github.com/langchain-ai/langchain)
"""

import os
import re
import subprocess
import sys

REPO_DIR = "/workspace/langchain"


class TestFilePathCheck:
    """Verify all required files were created."""

    def test_trace_analyzer_exists(self):
        path = os.path.join(
            REPO_DIR, "libs", "core", "langchain_core", "tracers",
            "trace_analyzer.py",
        )
        assert os.path.isfile(path), f"Expected trace_analyzer.py at {path}"

    def test_trace_models_exists(self):
        path = os.path.join(
            REPO_DIR, "libs", "core", "langchain_core", "tracers",
            "trace_models.py",
        )
        assert os.path.isfile(path), f"Expected trace_models.py at {path}"

    def test_trace_analyzer_test_exists(self):
        path = os.path.join(
            REPO_DIR, "libs", "core", "tests", "unit_tests", "tracers",
            "test_trace_analyzer.py",
        )
        assert os.path.isfile(path), f"Expected test_trace_analyzer.py"


class TestSemanticTraceModels:
    """Verify trace data models."""

    def _read(self):
        path = os.path.join(
            REPO_DIR, "libs", "core", "langchain_core", "tracers",
            "trace_models.py",
        )
        with open(path, "r") as f:
            return f.read()

    def test_run_class(self):
        content = self._read()
        assert re.search(r"class\s+Run", content), (
            "Expected Run dataclass"
        )

    def test_run_fields(self):
        content = self._read()
        for field in ["id", "name", "run_type", "start_time", "end_time", "status"]:
            assert field in content, f"Expected Run field '{field}'"

    def test_run_types(self):
        content = self._read()
        for run_type in ["chain", "llm", "tool", "retriever"]:
            assert run_type in content, f"Expected run_type '{run_type}'"

    def test_status_values(self):
        content = self._read()
        for status in ["success", "error", "pending"]:
            assert status in content, f"Expected status '{status}'"

    def test_child_runs(self):
        content = self._read()
        assert re.search(r"child_runs", content), (
            "Expected child_runs field for nested run tree"
        )

    def test_trace_session_class(self):
        content = self._read()
        assert re.search(r"class\s+TraceSession", content), (
            "Expected TraceSession dataclass"
        )

    def test_validation_end_time(self):
        content = self._read()
        assert re.search(r"end_time.*start_time|ValueError|validate", content), (
            "Expected end_time >= start_time validation"
        )


class TestSemanticLatencyAnalysis:
    """Verify latency analysis functionality."""

    def _read(self):
        path = os.path.join(
            REPO_DIR, "libs", "core", "langchain_core", "tracers",
            "trace_analyzer.py",
        )
        with open(path, "r") as f:
            return f.read()

    def test_analyze_latency_function(self):
        content = self._read()
        assert re.search(r"def\s+analyze_latency", content), (
            "Expected analyze_latency function"
        )

    def test_total_duration(self):
        content = self._read()
        assert re.search(r"total_duration", content), (
            "Expected total_duration computation"
        )

    def test_self_time(self):
        content = self._read()
        assert re.search(r"self_time", content), (
            "Expected self_time computation (total minus children)"
        )

    def test_child_breakdown(self):
        content = self._read()
        assert re.search(r"child_breakdown", content), (
            "Expected child_breakdown mapping"
        )

    def test_critical_path(self):
        content = self._read()
        assert re.search(r"critical_path", content), (
            "Expected critical_path (longest execution path)"
        )

    def test_latency_breakdown_class(self):
        content = self._read()
        assert re.search(r"LatencyBreakdown|latency_breakdown", content), (
            "Expected LatencyBreakdown return type"
        )


class TestSemanticBottleneckDetection:
    """Verify bottleneck detection functionality."""

    def _read(self):
        path = os.path.join(
            REPO_DIR, "libs", "core", "langchain_core", "tracers",
            "trace_analyzer.py",
        )
        with open(path, "r") as f:
            return f.read()

    def test_detect_bottlenecks_function(self):
        content = self._read()
        assert re.search(r"def\s+detect_bottlenecks", content), (
            "Expected detect_bottlenecks function"
        )

    def test_threshold_param(self):
        content = self._read()
        assert re.search(r"threshold_ms|threshold", content), (
            "Expected threshold_ms parameter (default 1000)"
        )

    def test_bottleneck_class(self):
        content = self._read()
        assert re.search(r"Bottleneck|bottleneck", content), (
            "Expected Bottleneck result class"
        )

    def test_percentage_of_total(self):
        content = self._read()
        assert re.search(r"percentage_of_total|percent", content), (
            "Expected percentage_of_total in Bottleneck"
        )


class TestSemanticErrorAnalysis:
    """Verify error analysis functionality."""

    def _read(self):
        path = os.path.join(
            REPO_DIR, "libs", "core", "langchain_core", "tracers",
            "trace_analyzer.py",
        )
        with open(path, "r") as f:
            return f.read()

    def test_analyze_errors_function(self):
        content = self._read()
        assert re.search(r"def\s+analyze_errors", content), (
            "Expected analyze_errors function"
        )

    def test_error_summary(self):
        content = self._read()
        assert re.search(r"ErrorSummary|error_summary", content), (
            "Expected ErrorSummary return type"
        )

    def test_error_rate(self):
        content = self._read()
        assert re.search(r"error_rate", content), (
            "Expected error_rate computation"
        )

    def test_errors_by_type(self):
        content = self._read()
        assert re.search(r"errors_by_type|by_type", content), (
            "Expected errors_by_type grouping"
        )


class TestSemanticExport:
    """Verify session export functionality."""

    def _read(self):
        path = os.path.join(
            REPO_DIR, "libs", "core", "langchain_core", "tracers",
            "trace_analyzer.py",
        )
        with open(path, "r") as f:
            return f.read()

    def test_export_session_function(self):
        content = self._read()
        assert re.search(r"def\s+export_session", content), (
            "Expected export_session function"
        )

    def test_json_format(self):
        content = self._read()
        assert re.search(r"json|JSON", content), (
            "Expected JSON export format support"
        )

    def test_csv_format(self):
        content = self._read()
        assert re.search(r"csv|CSV", content), (
            "Expected CSV export format support"
        )

    def test_unsupported_format_error(self):
        content = self._read()
        assert re.search(r"ValueError|unsupported|format", content, re.IGNORECASE), (
            "Expected ValueError for unsupported formats"
        )


class TestFunctionalPythonSyntax:
    """Validate Python files compile and tests pass."""

    def test_trace_analyzer_syntax(self):
        path = os.path.join(
            REPO_DIR, "libs", "core", "langchain_core", "tracers",
            "trace_analyzer.py",
        )
        with open(path, "r") as f:
            content = f.read()
        compile(content, path, "exec")

    def test_trace_models_syntax(self):
        path = os.path.join(
            REPO_DIR, "libs", "core", "langchain_core", "tracers",
            "trace_models.py",
        )
        with open(path, "r") as f:
            content = f.read()
        compile(content, path, "exec")

    def test_agent_tests_pass(self):
        test_path = os.path.join(
            REPO_DIR, "libs", "core", "tests", "unit_tests", "tracers",
            "test_trace_analyzer.py",
        )
        if os.path.isfile(test_path):
            result = subprocess.run(
                [sys.executable, "-m", "pytest", test_path, "-v", "--tb=short"],
                cwd=REPO_DIR,
                capture_output=True,
                text=True,
                timeout=120,
            )
            assert result.returncode == 0, (
                f"Agent tests failed:\n{result.stdout[-1000:]}\n{result.stderr[-500:]}"
            )
