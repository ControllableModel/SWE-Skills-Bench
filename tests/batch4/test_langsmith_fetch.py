"""
Tests for skill: langsmith-fetch
Repo: langchain-ai/langchain
Image: zhangyiiiiii/swe-skills-bench-python
Task: Build a LangSmith trace fetcher and analyzer library with API client,
      trace parser, analyzer, and reporter.
"""

import ast
import json
import os
import sys

import pytest

REPO_DIR = "/workspace/langchain"
DEBUG_DIR = os.path.join(REPO_DIR, "libs", "langchain", "langchain", "debug")

FETCHER_FILE = os.path.join(DEBUG_DIR, "trace_fetcher.py")
PARSER_FILE = os.path.join(DEBUG_DIR, "trace_parser.py")
ANALYZER_FILE = os.path.join(DEBUG_DIR, "analyzer.py")
REPORTER_FILE = os.path.join(DEBUG_DIR, "reporter.py")


# ---------------------------------------------------------------------------
# Layer 1 — file_path_check
# ---------------------------------------------------------------------------

class TestFilePathCheck:
    """Verify all debug module files exist."""

    def test_trace_fetcher_exists(self):
        assert os.path.isfile(FETCHER_FILE), f"Missing {FETCHER_FILE}"

    def test_trace_parser_exists(self):
        assert os.path.isfile(PARSER_FILE), f"Missing {PARSER_FILE}"

    def test_analyzer_exists(self):
        assert os.path.isfile(ANALYZER_FILE), f"Missing {ANALYZER_FILE}"

    def test_reporter_exists(self):
        assert os.path.isfile(REPORTER_FILE), f"Missing {REPORTER_FILE}"


# ---------------------------------------------------------------------------
# Layer 2 — semantic_check
# ---------------------------------------------------------------------------

class TestSemanticTraceFetcher:
    """Verify trace fetcher module structure."""

    @pytest.fixture(autouse=True)
    def _load(self):
        with open(FETCHER_FILE, "r", encoding="utf-8") as f:
            self.src = f.read()
        self.tree = ast.parse(self.src)

    def test_trace_fetcher_class(self):
        classes = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.ClassDef)]
        assert "TraceFetcher" in classes, f"Expected TraceFetcher; found {classes}"

    def test_fetch_recent(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "fetch_recent" in funcs, f"Expected fetch_recent; found {funcs}"

    def test_fetch_trace(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "fetch_trace" in funcs, f"Expected fetch_trace; found {funcs}"

    def test_fetch_runs(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "fetch_runs" in funcs, f"Expected fetch_runs; found {funcs}"

    def test_api_key_header(self):
        assert "X-API-Key" in self.src or "x-api-key" in self.src, (
            "Should use X-API-Key header for authentication"
        )

    def test_timeout(self):
        assert "timeout" in self.src and "30" in self.src, (
            "Should use a 30-second timeout"
        )

    def test_base_url_default(self):
        assert "api.smith.langchain.com" in self.src, (
            "Default base_url should be https://api.smith.langchain.com"
        )


class TestSemanticExceptionHierarchy:
    """Verify custom exception hierarchy."""

    @pytest.fixture(autouse=True)
    def _load(self):
        with open(FETCHER_FILE, "r", encoding="utf-8") as f:
            self.src = f.read()

    def test_langsmith_error_base(self):
        assert "LangSmithError" in self.src, "Should define LangSmithError base class"

    def test_authentication_error(self):
        assert "AuthenticationError" in self.src, (
            "Should define AuthenticationError for 401"
        )

    def test_trace_not_found_error(self):
        assert "TraceNotFoundError" in self.src, (
            "Should define TraceNotFoundError for 404"
        )

    def test_rate_limit_error(self):
        assert "RateLimitError" in self.src, (
            "Should define RateLimitError for 429"
        )

    def test_api_error(self):
        assert "LangSmithAPIError" in self.src, (
            "Should define LangSmithAPIError for other HTTP errors"
        )


class TestSemanticTraceParser:
    """Verify trace parser module structure."""

    @pytest.fixture(autouse=True)
    def _load(self):
        with open(PARSER_FILE, "r", encoding="utf-8") as f:
            self.src = f.read()
        self.tree = ast.parse(self.src)

    def test_parsed_trace_class(self):
        classes = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.ClassDef)]
        assert "ParsedTrace" in classes, f"Expected ParsedTrace; found {classes}"

    def test_parsed_run_class(self):
        classes = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.ClassDef)]
        assert "ParsedRun" in classes, f"Expected ParsedRun; found {classes}"

    def test_parse_trace_function(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "parse_trace" in funcs, f"Expected parse_trace; found {funcs}"

    def test_dataclass_usage(self):
        assert "dataclass" in self.src, "ParsedTrace should be a dataclass"

    def test_trace_id_field(self):
        assert "trace_id" in self.src, "ParsedTrace should have trace_id field"

    def test_total_tokens_field(self):
        assert "total_tokens" in self.src, "ParsedTrace should have total_tokens field"

    def test_tool_calls_field(self):
        assert "tool_calls" in self.src, "ParsedTrace should have tool_calls field"

    def test_errors_field(self):
        assert "errors" in self.src, "ParsedTrace should have errors list"


class TestSemanticAnalyzer:
    """Verify analyzer module structure."""

    @pytest.fixture(autouse=True)
    def _load(self):
        with open(ANALYZER_FILE, "r", encoding="utf-8") as f:
            self.src = f.read()
        self.tree = ast.parse(self.src)

    def test_trace_analyzer_class(self):
        classes = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.ClassDef)]
        assert "TraceAnalyzer" in classes, f"Expected TraceAnalyzer; found {classes}"

    def test_analysis_result(self):
        assert "AnalysisResult" in self.src, "Should define AnalysisResult"

    def test_analyze_method(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "analyze" in funcs, f"Expected analyze(); found {funcs}"

    def test_success_rate_field(self):
        assert "success_rate" in self.src, "AnalysisResult should have success_rate"

    def test_p95_field(self):
        assert "p95" in self.src, "AnalysisResult should have p95_duration_ms"

    def test_slowest_tools_field(self):
        assert "slowest_tools" in self.src, "AnalysisResult should have slowest_tools"

    def test_error_patterns_field(self):
        assert "error_patterns" in self.src, "AnalysisResult should have error_patterns"

    def test_recommendations_field(self):
        assert "recommendations" in self.src, "AnalysisResult should have recommendations"


class TestSemanticReporter:
    """Verify reporter module structure."""

    @pytest.fixture(autouse=True)
    def _load(self):
        with open(REPORTER_FILE, "r", encoding="utf-8") as f:
            self.src = f.read()
        self.tree = ast.parse(self.src)

    def test_debug_reporter_class(self):
        classes = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.ClassDef)]
        assert "DebugReporter" in classes, f"Expected DebugReporter; found {classes}"

    def test_report_text(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "report_text" in funcs, f"Expected report_text; found {funcs}"

    def test_report_json(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "report_json" in funcs, f"Expected report_json; found {funcs}"

    def test_report_markdown(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "report_markdown" in funcs, f"Expected report_markdown; found {funcs}"

    def test_report_trace_detail(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "report_trace_detail" in funcs, (
            f"Expected report_trace_detail; found {funcs}"
        )


# ---------------------------------------------------------------------------
# Layer 3 — functional_check
# ---------------------------------------------------------------------------

class TestFunctionalExceptions:
    """Run and verify custom exception hierarchy."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        sys.path.insert(0, os.path.join(REPO_DIR, "libs", "langchain"))
        sys.path.insert(0, DEBUG_DIR)
        try:
            from langchain.debug.trace_fetcher import (
                LangSmithError,
                AuthenticationError,
                TraceNotFoundError,
                RateLimitError,
                LangSmithAPIError,
            )
            self.LangSmithError = LangSmithError
            self.AuthenticationError = AuthenticationError
            self.TraceNotFoundError = TraceNotFoundError
            self.RateLimitError = RateLimitError
            self.LangSmithAPIError = LangSmithAPIError
        except ImportError:
            try:
                from trace_fetcher import (
                    LangSmithError,
                    AuthenticationError,
                    TraceNotFoundError,
                    RateLimitError,
                    LangSmithAPIError,
                )
                self.LangSmithError = LangSmithError
                self.AuthenticationError = AuthenticationError
                self.TraceNotFoundError = TraceNotFoundError
                self.RateLimitError = RateLimitError
                self.LangSmithAPIError = LangSmithAPIError
            except ImportError:
                pytest.skip("Cannot import exception classes")

    def test_auth_error_is_langsmith_error(self):
        assert issubclass(self.AuthenticationError, self.LangSmithError), (
            "AuthenticationError should inherit from LangSmithError"
        )

    def test_not_found_is_langsmith_error(self):
        assert issubclass(self.TraceNotFoundError, self.LangSmithError), (
            "TraceNotFoundError should inherit from LangSmithError"
        )

    def test_rate_limit_is_langsmith_error(self):
        assert issubclass(self.RateLimitError, self.LangSmithError), (
            "RateLimitError should inherit from LangSmithError"
        )

    def test_api_error_is_langsmith_error(self):
        assert issubclass(self.LangSmithAPIError, self.LangSmithError), (
            "LangSmithAPIError should inherit from LangSmithError"
        )


class TestFunctionalTraceParser:
    """Parse a synthetic trace and verify output."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        sys.path.insert(0, os.path.join(REPO_DIR, "libs", "langchain"))
        sys.path.insert(0, DEBUG_DIR)
        try:
            from langchain.debug.trace_parser import parse_trace
            self.parse_trace = parse_trace
        except ImportError:
            try:
                from trace_parser import parse_trace
                self.parse_trace = parse_trace
            except ImportError:
                pytest.skip("Cannot import parse_trace")

    def _make_raw_trace(self):
        return {
            "id": "trace-001",
            "name": "agent-run",
            "status": "success",
            "start_time": "2024-01-01T00:00:00Z",
            "end_time": "2024-01-01T00:00:05Z",
        }

    def _make_raw_runs(self):
        return [
            {
                "id": "run-001",
                "name": "llm-call",
                "run_type": "llm",
                "status": "success",
                "start_time": "2024-01-01T00:00:00Z",
                "end_time": "2024-01-01T00:00:02Z",
                "inputs": {"prompt": "Hello world"},
                "outputs": {"text": "Hi there!"},
                "extra": {"tokens": {"total_tokens": 50, "prompt_tokens": 20, "completion_tokens": 30}},
            },
            {
                "id": "run-002",
                "name": "search-tool",
                "run_type": "tool",
                "status": "success",
                "start_time": "2024-01-01T00:00:02Z",
                "end_time": "2024-01-01T00:00:04Z",
                "inputs": {"query": "test"},
                "outputs": {"result": "found"},
            },
            {
                "id": "run-003",
                "name": "llm-final",
                "run_type": "llm",
                "status": "error",
                "start_time": "2024-01-01T00:00:04Z",
                "end_time": "2024-01-01T00:00:05Z",
                "error": "timeout",
                "extra": {"tokens": {"total_tokens": 30, "prompt_tokens": 15, "completion_tokens": 15}},
            },
        ]

    def test_trace_id_parsed(self):
        parsed = self.parse_trace(self._make_raw_trace(), self._make_raw_runs())
        assert parsed.trace_id == "trace-001"

    def test_runs_parsed(self):
        parsed = self.parse_trace(self._make_raw_trace(), self._make_raw_runs())
        assert len(parsed.runs) == 3

    def test_token_aggregation(self):
        parsed = self.parse_trace(self._make_raw_trace(), self._make_raw_runs())
        assert parsed.total_tokens >= 80, (
            f"Expected total_tokens >= 80; got {parsed.total_tokens}"
        )

    def test_errors_extracted(self):
        parsed = self.parse_trace(self._make_raw_trace(), self._make_raw_runs())
        assert len(parsed.errors) >= 1, "Should extract at least one error"

    def test_missing_fields_handled(self):
        parsed = self.parse_trace({}, [])
        assert parsed is not None, "parse_trace should handle empty data gracefully"


class TestFunctionalAnalyzer:
    """Run analyzer on synthetic parsed traces."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        sys.path.insert(0, os.path.join(REPO_DIR, "libs", "langchain"))
        sys.path.insert(0, DEBUG_DIR)
        try:
            from langchain.debug.trace_parser import ParsedTrace, ParsedRun
            from langchain.debug.analyzer import TraceAnalyzer
            self.ParsedTrace = ParsedTrace
            self.ParsedRun = ParsedRun
            self.TraceAnalyzer = TraceAnalyzer
        except ImportError:
            try:
                from trace_parser import ParsedTrace, ParsedRun
                from analyzer import TraceAnalyzer
                self.ParsedTrace = ParsedTrace
                self.ParsedRun = ParsedRun
                self.TraceAnalyzer = TraceAnalyzer
            except ImportError:
                pytest.skip("Cannot import analyzer")

    def _make_traces(self):
        traces = []
        for i in range(10):
            status = "success" if i < 8 else "error"
            t = self.ParsedTrace(
                trace_id=f"t-{i}",
                name=f"run-{i}",
                status=status,
                start_time="2024-01-01T00:00:00Z",
                end_time="2024-01-01T00:00:01Z",
                duration_ms=1000 + i * 100,
                total_tokens=100,
                prompt_tokens=60,
                completion_tokens=40,
                tool_calls=["search-tool"],
                errors=["timeout"] if status == "error" else [],
                runs=[],
            )
            traces.append(t)
        return traces

    def test_success_rate_80(self):
        analyzer = self.TraceAnalyzer()
        result = analyzer.analyze(self._make_traces())
        assert abs(result.success_rate - 0.8) < 1e-6, (
            f"Expected success_rate 0.8; got {result.success_rate}"
        )

    def test_total_traces(self):
        analyzer = self.TraceAnalyzer()
        result = analyzer.analyze(self._make_traces())
        assert result.total_traces == 10

    def test_error_patterns(self):
        analyzer = self.TraceAnalyzer()
        result = analyzer.analyze(self._make_traces())
        assert len(result.error_patterns) >= 1, "Should identify error patterns"


class TestFunctionalReporter:
    """Run reporter and verify output formats."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        sys.path.insert(0, os.path.join(REPO_DIR, "libs", "langchain"))
        sys.path.insert(0, DEBUG_DIR)
        try:
            from langchain.debug.analyzer import AnalysisResult
            from langchain.debug.reporter import DebugReporter
            self.AnalysisResult = AnalysisResult
            self.DebugReporter = DebugReporter
        except ImportError:
            try:
                from analyzer import AnalysisResult
                from reporter import DebugReporter
                self.AnalysisResult = AnalysisResult
                self.DebugReporter = DebugReporter
            except ImportError:
                pytest.skip("Cannot import reporter")

    def _make_result(self):
        return self.AnalysisResult(
            total_traces=10,
            success_count=8,
            error_count=2,
            success_rate=0.8,
            avg_duration_ms=1500.0,
            p95_duration_ms=1900.0,
            total_tokens_used=1000,
            avg_tokens_per_trace=100.0,
            slowest_tools=[("search", 5000.0)],
            error_patterns=[("timeout", 2)],
            recommendations=["Tool 'search' averages 5s — consider caching"],
        )

    def test_report_json_valid(self):
        reporter = self.DebugReporter()
        output = reporter.report_json(self._make_result())
        parsed = json.loads(output)
        assert isinstance(parsed, dict), "JSON report should be a dict"

    def test_report_text_nonempty(self):
        reporter = self.DebugReporter()
        output = reporter.report_text(self._make_result())
        assert isinstance(output, str) and len(output) > 0

    def test_report_markdown_has_table(self):
        reporter = self.DebugReporter()
        output = reporter.report_markdown(self._make_result())
        assert "|" in output, "Markdown report should contain a table"
