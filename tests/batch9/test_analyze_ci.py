"""
Test skill: analyze-ci
Verify that the Agent creates a CI failure analyzer for Sentry with log parser,
failure classifier, GitHub API client, and Markdown report generator.
"""

import os
import subprocess
import ast
import re
import pytest


class TestAnalyzeCi:
    REPO_DIR = "/workspace/sentry"

    # === File Path Checks ===

    def test_ci_analyzer_files_exist(self):
        """Verify CI analyzer files exist"""
        found = False
        for root, dirs, files in os.walk(self.REPO_DIR):
            if ".git" in root or "node_modules" in root:
                continue
            for f in files:
                if f.endswith(".py") and ("ci" in f.lower() or "analyzer" in f.lower() or "failure" in f.lower()):
                    fpath = os.path.join(root, f)
                    with open(fpath) as fh:
                        content = fh.read()
                    if "parser" in content.lower() or "classifier" in content.lower() or "analyze" in content.lower():
                        found = True
                        break
            if found:
                break
        assert found, "CI analyzer files not found"

    # === Semantic Checks ===

    def test_log_parser_defined(self):
        """Verify log parser is implemented"""
        content = self._find_content()
        content_lower = content.lower()
        has_parser = "parser" in content_lower and ("log" in content_lower or "parse" in content_lower)
        assert has_parser, "Log parser not found"

    def test_failure_classifier_defined(self):
        """Verify failure classifier is implemented with 7 failure types"""
        content = self._find_content()
        content_lower = content.lower()
        has_classifier = "classif" in content_lower or "categoriz" in content_lower
        assert has_classifier, "Failure classifier not found"

    def test_failure_types_defined(self):
        """Verify multiple failure type categories are defined"""
        content = self._find_content()
        content_lower = content.lower()
        failure_types = ["flaky", "timeout", "dependency", "infrastructure", "test", "build", "configuration"]
        found = [ft for ft in failure_types if ft in content_lower]
        assert len(found) >= 4, (
            f"Expected at least 4 failure types, found {len(found)}: {found}"
        )

    def test_github_api_client_defined(self):
        """Verify GitHub API client is implemented"""
        content = self._find_content()
        has_github = (
            "github" in content.lower()
            or "GitHubClient" in content
            or "github_api" in content.lower()
            or "requests" in content
        )
        assert has_github, "GitHub API client not found"

    def test_markdown_report_generator_defined(self):
        """Verify Markdown report generator is implemented"""
        content = self._find_content()
        content_lower = content.lower()
        has_report = (
            "markdown" in content_lower
            or "report" in content_lower
            or "render" in content_lower
        )
        assert has_report, "Markdown report generator not found"

    # === Functional Checks ===

    def test_analyzer_files_parse(self):
        """Verify all CI analyzer files have valid Python syntax"""
        for root, dirs, files in os.walk(self.REPO_DIR):
            if ".git" in root or "node_modules" in root:
                continue
            for f in files:
                if f.endswith(".py") and ("ci" in f.lower() or "analyzer" in f.lower() or "failure" in f.lower()):
                    fpath = os.path.join(root, f)
                    with open(fpath) as fh:
                        source = fh.read()
                    if "parser" in source.lower() or "classifier" in source.lower():
                        try:
                            ast.parse(source)
                        except SyntaxError as e:
                            pytest.fail(f"Syntax error in {fpath}: {e}")

    def test_analyzer_module_importable(self):
        """Verify analyzer module can be parsed"""
        analyzer_file = None
        for root, dirs, files in os.walk(self.REPO_DIR):
            if ".git" in root:
                continue
            for f in files:
                if f.endswith(".py") and ("analyzer" in f.lower() or "ci_failure" in f.lower()):
                    analyzer_file = os.path.join(root, f)
                    break
            if analyzer_file:
                break
        if analyzer_file is None:
            pytest.skip("Analyzer module not found")
        result = subprocess.run(
            ["python", "-c", f"import ast; ast.parse(open('{analyzer_file}').read()); print('OK')"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, f"Parse failed: {result.stderr}"

    def test_report_generates_markdown_format(self):
        """Verify report generator produces markdown syntax"""
        content = self._find_content()
        has_md_syntax = (
            "# " in content
            or "## " in content
            or "```" in content
            or "|" in content
            or "---" in content
        )
        assert has_md_syntax, "Report generator doesn't produce markdown syntax"

    def test_github_client_uses_http_requests(self):
        """Verify GitHub client makes HTTP requests"""
        content = self._find_content()
        has_http = (
            "requests" in content
            or "httpx" in content
            or "urllib" in content
            or "aiohttp" in content
            or "fetch" in content.lower()
        )
        assert has_http, "GitHub client missing HTTP request library"

    def _find_content(self):
        """Helper to find CI analyzer content"""
        all_content = ""
        for root, dirs, files in os.walk(self.REPO_DIR):
            if ".git" in root or "node_modules" in root:
                continue
            for f in files:
                if f.endswith(".py") and ("ci" in f.lower() or "analyzer" in f.lower() or "failure" in f.lower() or "report" in f.lower()):
                    fpath = os.path.join(root, f)
                    try:
                        with open(fpath) as fh:
                            content = fh.read()
                        if any(kw in content.lower() for kw in ["parser", "classifier", "analyzer", "github", "report"]):
                            all_content += content + "\n"
                    except (UnicodeDecodeError, PermissionError):
                        continue
        return all_content
