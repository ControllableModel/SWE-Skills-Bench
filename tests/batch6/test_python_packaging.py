"""
Test skill: python-packaging
Verify that the Agent builds a "version-inspector" CLI tool using Click
with PEP 440 version parsing, comparison, and specifier range checking,
packaged with pyproject.toml, src layout, and console script entry point.
"""

import os
import re
import ast
import json
import subprocess
import pytest

try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None


class TestPythonPackaging:
    REPO_DIR = "/workspace/packaging"

    # === File Path Checks ===

    def test_pyproject_toml_exists(self):
        path = os.path.join(self.REPO_DIR, "pyproject.toml")
        assert os.path.exists(path), "pyproject.toml not found"

    def test_src_layout_exists(self):
        base = os.path.join(self.REPO_DIR, "src")
        assert os.path.isdir(base), "src/ directory not found"
        # Should have a package directory inside src/
        entries = os.listdir(base)
        pkg_dirs = [e for e in entries if os.path.isdir(os.path.join(base, e))]
        assert len(pkg_dirs) >= 1, "No package directory found inside src/"

    def test_cli_module_exists(self):
        """Verify that a CLI module exists (cli.py or __main__.py)"""
        found = False
        for root, _dirs, files in os.walk(os.path.join(self.REPO_DIR, "src")):
            for f in files:
                if f in ("cli.py", "__main__.py", "main.py"):
                    found = True
                    break
        assert found, "No CLI module (cli.py or __main__.py) found under src/"

    # === Semantic Checks ===

    def test_pyproject_has_build_system(self):
        """pyproject.toml should have a build-system section"""
        path = os.path.join(self.REPO_DIR, "pyproject.toml")
        with open(path) as f:
            content = f.read()
        assert "[build-system]" in content, "Missing [build-system] section"
        assert re.search(r"build-backend", content), "Missing build-backend"

    def test_pyproject_has_console_script(self):
        """pyproject.toml should define a console_scripts entry point"""
        path = os.path.join(self.REPO_DIR, "pyproject.toml")
        with open(path) as f:
            content = f.read()
        assert re.search(
            r"console.scripts|console_scripts|entry.points", content, re.IGNORECASE
        ), "Missing console_scripts entry point"
        assert "version-inspector" in content or "version_inspector" in content, (
            "Console script should be named version-inspector"
        )

    def test_pyproject_depends_on_click(self):
        """pyproject.toml should declare Click as a dependency"""
        path = os.path.join(self.REPO_DIR, "pyproject.toml")
        with open(path) as f:
            content = f.read()
        assert "click" in content.lower(), "Missing click dependency"

    def test_cli_has_parse_subcommand(self):
        """CLI should have a 'parse' subcommand"""
        cli_path = self._find_cli_file()
        assert cli_path, "CLI file not found"
        with open(cli_path) as f:
            content = f.read()
        assert re.search(r"def\s+parse", content), "Missing 'parse' subcommand"

    def test_cli_has_compare_subcommand(self):
        """CLI should have a 'compare' subcommand"""
        cli_path = self._find_cli_file()
        assert cli_path, "CLI file not found"
        with open(cli_path) as f:
            content = f.read()
        assert re.search(r"def\s+compare", content), "Missing 'compare' subcommand"

    def test_cli_has_check_subcommand(self):
        """CLI should have a 'check' subcommand for specifier matching"""
        cli_path = self._find_cli_file()
        assert cli_path, "CLI file not found"
        with open(cli_path) as f:
            content = f.read()
        assert re.search(r"def\s+check", content), "Missing 'check' subcommand"

    def test_cli_has_range_subcommand(self):
        """CLI should have a 'range' subcommand"""
        cli_path = self._find_cli_file()
        assert cli_path, "CLI file not found"
        with open(cli_path) as f:
            content = f.read()
        assert re.search(r"def\s+range", content), "Missing 'range' subcommand"

    def test_cli_uses_click(self):
        """CLI should use Click for command parsing"""
        cli_path = self._find_cli_file()
        assert cli_path, "CLI file not found"
        with open(cli_path) as f:
            content = f.read()
        assert "import click" in content or "from click" in content, (
            "CLI should use Click"
        )
        assert "@click" in content, "CLI should use Click decorators"

    def test_cli_has_json_format_option(self):
        """CLI should support --format json|table option"""
        cli_path = self._find_cli_file()
        assert cli_path, "CLI file not found"
        with open(cli_path) as f:
            content = f.read()
        assert "format" in content.lower(), "CLI should support --format option"
        assert "json" in content.lower(), "CLI should support JSON output format"

    def test_cli_handles_invalid_versions(self):
        """CLI should have error handling for invalid versions"""
        cli_path = self._find_cli_file()
        assert cli_path, "CLI file not found"
        with open(cli_path) as f:
            content = f.read()
        content_lower = content.lower()
        assert (
            "invalidversion" in content_lower
            or "invalid" in content_lower
            or "error" in content_lower
            or "exception" in content_lower
        ), "CLI should handle invalid versions gracefully"

    def test_uses_pep440_parsing(self):
        """Code should use PEP 440 version parsing (packaging.version)"""
        cli_path = self._find_cli_file()
        assert cli_path, "CLI file not found"
        with open(cli_path) as f:
            content = f.read()
        assert re.search(r"from packaging|import packaging", content), (
            "Should use packaging library for PEP 440 version parsing"
        )

    # === Functional Checks ===

    def test_all_python_files_parse(self):
        """Verify all Python files in src/ parse without syntax errors"""
        src_dir = os.path.join(self.REPO_DIR, "src")
        if not os.path.isdir(src_dir):
            pytest.skip("src/ directory not found")
        for root, _dirs, files in os.walk(src_dir):
            for fname in files:
                if fname.endswith(".py"):
                    filepath = os.path.join(root, fname)
                    with open(filepath) as f:
                        source = f.read()
                    try:
                        ast.parse(source)
                    except SyntaxError as e:
                        pytest.fail(f"{filepath} has syntax error: {e}")

    def test_pyproject_toml_is_valid(self):
        """Verify pyproject.toml is valid TOML"""
        if tomllib is None:
            pytest.skip("No TOML parser available")
        path = os.path.join(self.REPO_DIR, "pyproject.toml")
        with open(path, "rb") as f:
            data = tomllib.load(f)
        assert "build-system" in data, "Missing build-system in pyproject.toml"
        assert "project" in data, "Missing project table in pyproject.toml"

    def test_package_is_installable(self):
        """Verify the package can be installed with pip"""
        result = subprocess.run(
            ["pip", "install", "-e", "."],
            capture_output=True, text=True, cwd=self.REPO_DIR, timeout=120
        )
        assert result.returncode == 0, (
            f"pip install -e . failed:\n{result.stderr}"
        )

    def test_version_inspector_cli_help(self):
        """Verify the CLI entry point works and shows help"""
        result = subprocess.run(
            ["version-inspector", "--help"],
            capture_output=True, text=True, cwd=self.REPO_DIR, timeout=30
        )
        assert result.returncode == 0, (
            f"version-inspector --help failed:\n{result.stderr}"
        )
        assert "parse" in result.stdout.lower() or "Usage" in result.stdout, (
            "Help output should list subcommands"
        )

    # --- Helpers ---

    def _find_cli_file(self):
        """Find the CLI module file under src/"""
        for root, _dirs, files in os.walk(os.path.join(self.REPO_DIR, "src")):
            for f in files:
                if f in ("cli.py", "__main__.py", "main.py"):
                    return os.path.join(root, f)
        return None
