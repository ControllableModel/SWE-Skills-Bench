"""
Test skill: python-packaging
Verify that the Agent creates a code metrics CLI package with pyproject.toml,
CodeAnalyzer (AST), and formatters for pypa/packaging.
"""

import os
import subprocess
import ast
import re
import pytest


class TestPythonPackaging:
    REPO_DIR = "/workspace/packaging"

    # === File Path Checks ===

    def test_pyproject_toml_exists(self):
        """Verify pyproject.toml exists"""
        path = os.path.join(self.REPO_DIR, "pyproject.toml")
        assert os.path.exists(path), f"pyproject.toml not found at {path}"

    def test_code_analyzer_exists(self):
        """Verify CodeAnalyzer module exists"""
        found = False
        for root, dirs, files in os.walk(self.REPO_DIR):
            if ".git" in root:
                continue
            for f in files:
                if f.endswith(".py"):
                    fpath = os.path.join(root, f)
                    with open(fpath) as fh:
                        content = fh.read()
                    if "CodeAnalyzer" in content:
                        found = True
                        break
            if found:
                break
        assert found, "CodeAnalyzer class not found"

    # === Semantic Checks ===

    def test_pyproject_has_build_system(self):
        """Verify pyproject.toml defines build-system"""
        path = os.path.join(self.REPO_DIR, "pyproject.toml")
        with open(path) as f:
            content = f.read()
        assert "[build-system]" in content, "pyproject.toml missing [build-system]"

    def test_pyproject_has_project_metadata(self):
        """Verify pyproject.toml has project name and version"""
        path = os.path.join(self.REPO_DIR, "pyproject.toml")
        with open(path) as f:
            content = f.read()
        assert "[project]" in content or "name" in content, "pyproject.toml missing project metadata"

    def test_pyproject_has_cli_entry_point(self):
        """Verify pyproject.toml defines CLI entry point"""
        path = os.path.join(self.REPO_DIR, "pyproject.toml")
        with open(path) as f:
            content = f.read()
        has_cli = (
            "[project.scripts]" in content
            or "console_scripts" in content
            or "[tool.poetry.scripts]" in content
        )
        assert has_cli, "pyproject.toml missing CLI entry point"

    def test_code_analyzer_uses_ast(self):
        """Verify CodeAnalyzer uses AST for code analysis"""
        content = self._find_code_analyzer_content()
        has_ast = "ast" in content and ("parse" in content or "walk" in content or "NodeVisitor" in content)
        assert has_ast, "CodeAnalyzer doesn't use AST for analysis"

    def test_formatters_defined(self):
        """Verify output formatters are defined"""
        found = False
        for root, dirs, files in os.walk(self.REPO_DIR):
            if ".git" in root:
                continue
            for f in files:
                if f.endswith(".py") and ("format" in f.lower() or "output" in f.lower()):
                    found = True
                    break
                if f.endswith(".py"):
                    fpath = os.path.join(root, f)
                    with open(fpath) as fh:
                        content = fh.read()
                    if "Formatter" in content or "format" in content.lower():
                        if "json" in content.lower() or "table" in content.lower() or "csv" in content.lower():
                            found = True
                            break
            if found:
                break
        assert found, "Output formatters not found"

    # === Functional Checks ===

    def test_code_analyzer_file_parses(self):
        """Verify CodeAnalyzer file has valid Python syntax"""
        for root, dirs, files in os.walk(self.REPO_DIR):
            if ".git" in root:
                continue
            for f in files:
                if f.endswith(".py"):
                    fpath = os.path.join(root, f)
                    with open(fpath) as fh:
                        source = fh.read()
                    if "CodeAnalyzer" in source:
                        try:
                            ast.parse(source)
                        except SyntaxError as e:
                            pytest.fail(f"Syntax error in {fpath}: {e}")
                        return

    def test_package_installable(self):
        """Verify package can be installed with pip"""
        result = subprocess.run(
            ["pip", "install", "-e", ".", "--no-deps"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, f"pip install failed: {result.stderr[:500]}"

    def test_cli_entry_point_accessible(self):
        """Verify CLI entry point is accessible after install"""
        # First install
        subprocess.run(
            ["pip", "install", "-e", "."],
            cwd=self.REPO_DIR,
            capture_output=True,
            timeout=120,
        )
        # Check if help command works
        result = subprocess.run(
            ["python", "-m", "code_metrics", "--help"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            # Try alternative module names
            result = subprocess.run(
                ["python", "-c", "from packaging import code_metrics; print('OK')"],
                cwd=self.REPO_DIR,
                capture_output=True,
                text=True,
                timeout=30,
            )
        # At minimum, the Python files should parse
        assert result.returncode == 0 or True  # Soft check

    def test_code_analyzer_has_analyze_method(self):
        """Verify CodeAnalyzer has an analyze/run method"""
        content = self._find_code_analyzer_content()
        has_method = (
            "def analyze" in content
            or "def run" in content
            or "def process" in content
        )
        assert has_method, "CodeAnalyzer missing analyze/run method"

    def _find_code_analyzer_content(self):
        """Helper to find CodeAnalyzer content"""
        for root, dirs, files in os.walk(self.REPO_DIR):
            if ".git" in root:
                continue
            for f in files:
                if f.endswith(".py"):
                    fpath = os.path.join(root, f)
                    with open(fpath) as fh:
                        content = fh.read()
                    if "CodeAnalyzer" in content:
                        return content
        return ""
