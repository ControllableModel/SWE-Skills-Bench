"""
Test skill: langsmith-fetch
Verify that the Agent creates a LangSmith trace analyzer for
LangChain runs.
"""

import os
import re
import ast
import subprocess
import pytest


class TestLangsmithFetch:
    REPO_DIR = "/workspace/langchain"

    # === File Path Checks ===

    def test_langsmith_analyzer_files_exist(self):
        """Verify LangSmith trace analyzer files exist"""
        found = False
        for root, dirs, files in os.walk(self.REPO_DIR):
            if ".git" in root or "node_modules" in root:
                continue
            for f in files:
                if f.endswith(".py") and ("langsmith" in f.lower() or "trace" in f.lower() or "fetch" in f.lower() or "analyzer" in f.lower()):
                    found = True
                    break
            if found:
                break
        assert found, "LangSmith trace analyzer files not found"

    # === Semantic Checks ===

    def test_langsmith_client_used(self):
        """Verify LangSmith client is used"""
        content = self._collect_content()
        content_lower = content.lower()
        has_client = "langsmith" in content_lower or "Client" in content or "client" in content_lower
        assert has_client, "LangSmith client not found"

    def test_trace_fetching_defined(self):
        """Verify trace fetching functionality is defined"""
        content = self._collect_content()
        content_lower = content.lower()
        has_fetch = (
            "fetch" in content_lower
            or "list_runs" in content_lower
            or "get_run" in content_lower
            or "read_run" in content_lower
        )
        assert has_fetch, "Trace fetching not found"

    def test_trace_analysis_defined(self):
        """Verify trace analysis is implemented"""
        content = self._collect_content()
        content_lower = content.lower()
        has_analysis = (
            "analyz" in content_lower
            or "summary" in content_lower
            or "statistic" in content_lower
            or "metrics" in content_lower
            or "aggregate" in content_lower
        )
        assert has_analysis, "Trace analysis not found"

    def test_run_data_model(self):
        """Verify run data model is defined"""
        content = self._collect_content()
        has_model = (
            "Run" in content
            or "run_id" in content
            or "trace_id" in content
            or "run_type" in content
        )
        assert has_model, "Run data model not found"

    # === Functional Checks ===

    def test_python_files_valid_syntax(self):
        """Verify Python files have valid AST"""
        py_files = self._find_py_files()
        assert len(py_files) > 0, "No LangSmith Python files found"
        for pf in py_files:
            with open(pf) as fh:
                source = fh.read()
            try:
                ast.parse(source)
            except SyntaxError as e:
                pytest.fail(f"Syntax error in {pf}: {e}")

    def test_python_files_define_functions(self):
        """Verify Python files define functions or classes"""
        py_files = self._find_py_files()
        any_def = False
        for pf in py_files:
            with open(pf) as fh:
                source = fh.read()
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                    any_def = True
                    break
            if any_def:
                break
        assert any_def, "No functions or classes found"

    def test_error_handling(self):
        """Verify error handling for API calls"""
        content = self._collect_content()
        has_error_handling = (
            "try:" in content
            or "except" in content
            or "raise" in content
            or "error" in content.lower()
        )
        assert has_error_handling, "Error handling for API calls not found"

    def test_latency_or_token_analysis(self):
        """Verify latency or token usage analysis"""
        content = self._collect_content()
        content_lower = content.lower()
        has_perf = (
            "latency" in content_lower
            or "token" in content_lower
            or "duration" in content_lower
            or "cost" in content_lower
            or "total_tokens" in content_lower
        )
        assert has_perf, "Latency/token analysis not found"

    def test_filtering_capability(self):
        """Verify run filtering capabilities"""
        content = self._collect_content()
        content_lower = content.lower()
        has_filter = (
            "filter" in content_lower
            or "project" in content_lower
            or "session" in content_lower
            or "start_time" in content_lower
        )
        assert has_filter, "Run filtering capability not found"

    def _collect_content(self):
        all_content = ""
        for root, dirs, files in os.walk(self.REPO_DIR):
            if ".git" in root or "node_modules" in root:
                continue
            for f in files:
                if f.endswith(".py"):
                    fpath = os.path.join(root, f)
                    try:
                        with open(fpath) as fh:
                            c = fh.read()
                        if any(kw in c.lower() for kw in ["langsmith", "trace", "run", "fetch"]):
                            all_content += c + "\n"
                    except (UnicodeDecodeError, PermissionError):
                        continue
        return all_content

    def _find_py_files(self):
        result = []
        for root, dirs, files in os.walk(self.REPO_DIR):
            if ".git" in root or "node_modules" in root:
                continue
            for f in files:
                if f.endswith(".py") and ("langsmith" in f.lower() or "trace" in f.lower() or "fetch" in f.lower() or "analyzer" in f.lower()):
                    result.append(os.path.join(root, f))
        return result
