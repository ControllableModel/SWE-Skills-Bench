"""
Test skill: langsmith-fetch
Verify that the Agent creates a LangSmith trace fetching example
for LangChain with API connection, filtering, pagination, summary
display, JSON output, and a __main__ entry point.
"""

import os
import re
import ast
import subprocess
import pytest


class TestLangsmithFetch:
    REPO_DIR = "/workspace/langchain"

    # === File Path Checks ===

    def test_langsmith_fetch_py_exists(self):
        """Verify langsmith_fetch.py exists"""
        path = os.path.join(self.REPO_DIR, "examples", "langsmith_fetch.py")
        assert os.path.exists(path), (
            f"langsmith_fetch.py not found at {path}"
        )

    # === Semantic Checks ===

    def test_environment_config(self):
        """Verify LangSmith API key / endpoint env var usage"""
        path = os.path.join(self.REPO_DIR, "examples", "langsmith_fetch.py")
        with open(path) as f:
            content = f.read()

        env_indicators = [
            "LANGSMITH_API_KEY", "LANGSMITH_ENDPOINT",
            "os.environ", "os.getenv",
        ]
        found = [ind for ind in env_indicators if ind in content]
        assert len(found) >= 2, (
            f"Should use env-based config. Found: {found}"
        )

    def test_trace_fetching(self):
        """Verify trace / run fetching from LangSmith"""
        path = os.path.join(self.REPO_DIR, "examples", "langsmith_fetch.py")
        with open(path) as f:
            content = f.read()

        fetch_indicators = [
            "trace", "run", "fetch", "list_runs",
            "get_runs", "client", "Client",
        ]
        found = [ind for ind in fetch_indicators if ind in content]
        assert len(found) >= 3, (
            f"Should fetch traces/runs. Found: {found}"
        )

    def test_filter_by_run_type(self):
        """Verify filtering by run type (chain, llm, tool)"""
        path = os.path.join(self.REPO_DIR, "examples", "langsmith_fetch.py")
        with open(path) as f:
            content = f.read()

        type_indicators = [
            "run_type", "chain", "llm", "tool",
            "filter", "type",
        ]
        found = [ind for ind in type_indicators if ind in content]
        assert len(found) >= 3, (
            f"Should filter by run type. Found: {found}"
        )

    def test_filter_by_status(self):
        """Verify filtering by status (success, error)"""
        path = os.path.join(self.REPO_DIR, "examples", "langsmith_fetch.py")
        with open(path) as f:
            content = f.read()

        status_indicators = [
            "status", "success", "error", "is_error",
            "filter",
        ]
        found = [ind for ind in status_indicators if ind in content]
        assert len(found) >= 2, (
            f"Should filter by status. Found: {found}"
        )

    def test_summary_display(self):
        """Verify formatted summary display: ID, name, type, status, latency, tokens"""
        path = os.path.join(self.REPO_DIR, "examples", "langsmith_fetch.py")
        with open(path) as f:
            content = f.read()

        summary_indicators = [
            "latency", "token", "name", "status",
            "run_id", "print", "format", "table",
        ]
        found = [ind for ind in summary_indicators if ind in content]
        assert len(found) >= 4, (
            f"Should display trace summary. Found: {found}"
        )

    def test_pagination_support(self):
        """Verify pagination for large trace sets"""
        path = os.path.join(self.REPO_DIR, "examples", "langsmith_fetch.py")
        with open(path) as f:
            content = f.read()

        page_indicators = [
            "page", "limit", "offset", "cursor", "next",
            "paginate", "max", "total",
        ]
        found = [ind for ind in page_indicators if ind in content]
        assert len(found) >= 2, (
            f"Should support pagination. Found: {found}"
        )

    def test_json_output_mode(self):
        """Verify JSON output mode support"""
        path = os.path.join(self.REPO_DIR, "examples", "langsmith_fetch.py")
        with open(path) as f:
            content = f.read()

        json_indicators = [
            "json", "JSON", "json.dump", "json.dumps",
            "output", "format",
        ]
        found = [ind for ind in json_indicators if ind in content]
        assert len(found) >= 2, (
            f"Should support JSON output. Found: {found}"
        )

    def test_error_trace_display(self):
        """Verify error traces show diagnostic info"""
        path = os.path.join(self.REPO_DIR, "examples", "langsmith_fetch.py")
        with open(path) as f:
            content = f.read()

        error_indicators = [
            "error", "Error", "message", "traceback",
            "diagnostic", "stderr",
        ]
        found = [ind for ind in error_indicators if ind in content]
        assert len(found) >= 2, (
            f"Should display error trace info. Found: {found}"
        )

    # === Functional Checks ===

    def test_valid_python_syntax(self):
        """Verify langsmith_fetch.py is valid Python"""
        path = os.path.join(self.REPO_DIR, "examples", "langsmith_fetch.py")
        with open(path) as f:
            source = f.read()
        try:
            ast.parse(source)
        except SyntaxError as e:
            pytest.fail(f"langsmith_fetch.py has syntax error: {e}")

    def test_main_entry_point(self):
        """Verify __main__ entry point"""
        path = os.path.join(self.REPO_DIR, "examples", "langsmith_fetch.py")
        with open(path) as f:
            content = f.read()
        assert '__name__' in content and '__main__' in content, (
            "Should have __main__ entry point"
        )

    def test_callable_functions(self):
        """Verify script defines reusable functions"""
        path = os.path.join(self.REPO_DIR, "examples", "langsmith_fetch.py")
        with open(path) as f:
            content = f.read()

        defs = re.findall(r"^def \w+", content, re.MULTILINE)
        assert len(defs) >= 2, (
            f"Should define at least 2 functions. Found: {defs}"
        )
