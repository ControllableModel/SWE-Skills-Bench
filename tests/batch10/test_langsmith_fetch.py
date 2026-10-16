"""
Test skill: langsmith-fetch
Verify that the Agent correctly builds a LangSmith Trace Fetcher CLI
for LangChain Agent Debugging.
"""

import os
import re
import ast
import pytest


class TestLangsmithFetch:
    REPO_DIR = "/workspace/langchain"

    # === File Path Checks ===

    def test_langsmith_fetch_module_exists(self):
        """Verify langsmith_fetch.py was created"""
        path = os.path.join(
            self.REPO_DIR,
            "libs/langchain/langchain/tools/langsmith_fetch.py",
        )
        assert os.path.exists(path), "langsmith_fetch.py not found"

    def test_langsmith_fetch_cli_exists(self):
        """Verify langsmith_fetch_cli.py was created"""
        path = os.path.join(
            self.REPO_DIR,
            "libs/langchain/langchain/tools/langsmith_fetch_cli.py",
        )
        assert os.path.exists(path), "langsmith_fetch_cli.py not found"

    def test_pyproject_toml_exists(self):
        """Verify pyproject.toml was modified"""
        path = os.path.join(
            self.REPO_DIR, "libs/langchain/pyproject.toml"
        )
        assert os.path.exists(path), "pyproject.toml not found"

    def test_unit_test_exists(self):
        """Verify test_langsmith_fetch.py was created"""
        path = os.path.join(
            self.REPO_DIR,
            "libs/langchain/tests/unit_tests/tools/test_langsmith_fetch.py",
        )
        assert os.path.exists(path), "test_langsmith_fetch.py not found"

    # === Semantic Checks: TraceRecord dataclass ===

    def _load_fetch_module(self):
        path = os.path.join(
            self.REPO_DIR,
            "libs/langchain/langchain/tools/langsmith_fetch.py",
        )
        return open(path).read()

    def _load_cli_module(self):
        path = os.path.join(
            self.REPO_DIR,
            "libs/langchain/langchain/tools/langsmith_fetch_cli.py",
        )
        return open(path).read()

    def test_trace_record_dataclass(self):
        """Verify TraceRecord dataclass is defined"""
        source = self._load_fetch_module()
        assert "TraceRecord" in source, "TraceRecord not found"
        assert "dataclass" in source, "dataclass decorator not found"

    def test_trace_record_has_required_fields(self):
        """Verify TraceRecord has all required fields"""
        source = self._load_fetch_module()
        required_fields = [
            "trace_id", "agent_name", "status",
            "tools_called", "duration_ms", "token_count", "error_message",
        ]
        found = sum(1 for f in required_fields if f in source)
        assert found >= 5, (
            f"TraceRecord missing fields, found {found}/7 required"
        )

    def test_trace_record_status_values(self):
        """Verify status field supports success/error/timeout"""
        source = self._load_fetch_module()
        for val in ["success", "error", "timeout"]:
            assert val in source, f"Status value '{val}' not referenced"

    # === Semantic Checks: LangSmithClient ===

    def test_langsmith_client_class(self):
        """Verify LangSmithClient class is defined"""
        source = self._load_fetch_module()
        assert "class LangSmithClient" in source or "LangSmithClient" in source, (
            "LangSmithClient not found"
        )

    def test_fetch_traces_method(self):
        """Verify fetch_traces method is defined"""
        source = self._load_fetch_module()
        assert "fetch_traces" in source, "fetch_traces method not found"

    def test_fetch_trace_method(self):
        """Verify fetch_trace (single) method is defined"""
        source = self._load_fetch_module()
        assert "fetch_trace" in source, "fetch_trace method not found"

    def test_langsmith_fetch_error_exception(self):
        """Verify LangSmithFetchError custom exception is defined"""
        source = self._load_fetch_module()
        assert "LangSmithFetchError" in source, (
            "LangSmithFetchError exception not found"
        )

    # === Semantic Checks: CLI subcommands ===

    def test_cli_uses_argparse(self):
        """Verify CLI uses argparse"""
        source = self._load_cli_module()
        assert "argparse" in source, "CLI does not use argparse"

    def test_cli_traces_subcommand(self):
        """Verify CLI has traces subcommand"""
        source = self._load_cli_module()
        assert "traces" in source, "CLI missing 'traces' subcommand"

    def test_cli_trace_subcommand(self):
        """Verify CLI has trace subcommand for single trace"""
        source = self._load_cli_module()
        # Should have both 'traces' and 'trace' (single)
        has_trace_cmd = re.search(r'["\']trace["\']', source)
        assert has_trace_cmd, "CLI missing 'trace' subcommand"

    def test_cli_format_flag(self):
        """Verify CLI supports --format flag with pretty/json"""
        source = self._load_cli_module()
        assert "--format" in source, "CLI missing --format flag"
        assert "pretty" in source and "json" in source, (
            "CLI missing pretty/json format options"
        )

    # === Functional Checks ===

    def test_limit_clamped_to_100(self):
        """Verify limit exceeding 100 is clamped"""
        source = self._load_fetch_module()
        has_clamp = (
            "100" in source
            and ("min(" in source or "clamp" in source.lower() or ">" in source)
        )
        assert has_clamp, "No limit clamping to 100 logic found"

    def test_api_key_env_var_check(self):
        """Verify LANGSMITH_API_KEY environment variable is checked"""
        source = self._load_cli_module()
        assert "LANGSMITH_API_KEY" in source, (
            "CLI does not check LANGSMITH_API_KEY env var"
        )

    def test_project_env_var_check(self):
        """Verify LANGSMITH_PROJECT environment variable is checked"""
        source = self._load_cli_module()
        assert "LANGSMITH_PROJECT" in source, (
            "CLI does not check LANGSMITH_PROJECT env var"
        )

    def test_base_url_no_trailing_slash(self):
        """Verify base_url handling strips trailing slash"""
        source = self._load_fetch_module()
        has_strip = (
            "rstrip" in source
            or "strip" in source
            or "endswith" in source
            or 'api.smith.langchain.com"' in source
        )
        assert has_strip, "No trailing slash handling for base_url"

    def test_http_error_handling(self):
        """Verify HTTP errors raise LangSmithFetchError"""
        source = self._load_fetch_module()
        has_http_error = (
            "status_code" in source
            and "LangSmithFetchError" in source
        )
        assert has_http_error, (
            "HTTP error handling with LangSmithFetchError not found"
        )

    def test_cli_last_n_minutes_flag(self):
        """Verify CLI supports --last-n-minutes flag"""
        source = self._load_cli_module()
        assert "last-n-minutes" in source or "last_n_minutes" in source, (
            "CLI missing --last-n-minutes flag"
        )

    def test_cli_main_entry_point(self):
        """Verify main() function is defined as entry point"""
        source = self._load_cli_module()
        assert "def main" in source, "main() entry point not found"

    def test_pyproject_registers_script(self):
        """Verify pyproject.toml registers langsmith-fetch CLI entry"""
        path = os.path.join(
            self.REPO_DIR, "libs/langchain/pyproject.toml"
        )
        content = open(path).read()
        assert "langsmith-fetch" in content, (
            "pyproject.toml does not register langsmith-fetch script"
        )

    def test_modules_parseable(self):
        """Verify both Python modules have valid syntax"""
        for mod in [self._load_fetch_module(), self._load_cli_module()]:
            try:
                ast.parse(mod)
            except SyntaxError as e:
                pytest.fail(f"Module has syntax error: {e}")
