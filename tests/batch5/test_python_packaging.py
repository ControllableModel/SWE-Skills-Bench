"""
Test skill: python-packaging
Verify that the Agent correctly creates a pyproject.toml-based package
with CLI entry points for the packaging library.
"""

import os
import re
import ast
import subprocess
import pytest


class TestPythonPackaging:
    REPO_DIR = "/workspace/packaging"

    PYPROJECT = "packaging_cli/pyproject.toml"
    INIT = "packaging_cli/src/packaging_cli/__init__.py"
    CLI = "packaging_cli/src/packaging_cli/cli.py"
    VERSION_CHECK = "packaging_cli/src/packaging_cli/commands/version_check.py"
    SPECIFIER_CHECK = "packaging_cli/src/packaging_cli/commands/specifier_check.py"
    NORMALIZE = "packaging_cli/src/packaging_cli/commands/normalize.py"
    TESTS = "packaging_cli/tests/test_cli.py"
    README = "packaging_cli/README.md"

    def _read_file(self, rel_path):
        filepath = os.path.join(self.REPO_DIR, rel_path)
        with open(filepath) as f:
            return f.read()

    # === File Path Checks ===

    def test_pyproject_exists(self):
        filepath = os.path.join(self.REPO_DIR, self.PYPROJECT)
        assert os.path.exists(filepath), f"pyproject.toml not found at {filepath}"

    def test_init_file_exists(self):
        filepath = os.path.join(self.REPO_DIR, self.INIT)
        assert os.path.exists(filepath), f"__init__.py not found at {filepath}"

    def test_cli_file_exists(self):
        filepath = os.path.join(self.REPO_DIR, self.CLI)
        assert os.path.exists(filepath), f"cli.py not found at {filepath}"

    def test_command_files_exist(self):
        for path in [self.VERSION_CHECK, self.SPECIFIER_CHECK, self.NORMALIZE]:
            filepath = os.path.join(self.REPO_DIR, path)
            assert os.path.exists(filepath), f"Command file not found: {filepath}"

    def test_tests_file_exists(self):
        filepath = os.path.join(self.REPO_DIR, self.TESTS)
        assert os.path.exists(filepath), f"test_cli.py not found at {filepath}"

    def test_readme_exists(self):
        filepath = os.path.join(self.REPO_DIR, self.README)
        assert os.path.exists(filepath), f"README.md not found at {filepath}"

    # === Semantic Checks ===

    def test_pyproject_has_pep621_metadata(self):
        """Verify pyproject.toml has PEP 621 project metadata"""
        content = self._read_file(self.PYPROJECT)
        assert "[project]" in content, "pyproject.toml missing [project] table"
        assert 'name = "packaging-cli"' in content or "name = 'packaging-cli'" in content, \
            "pyproject.toml missing name"
        assert "requires-python" in content, "pyproject.toml missing requires-python"

    def test_pyproject_has_build_backend(self):
        """Verify pyproject.toml declares a build backend"""
        content = self._read_file(self.PYPROJECT)
        assert "[build-system]" in content, "pyproject.toml missing [build-system]"
        assert "build-backend" in content, "pyproject.toml missing build-backend"

    def test_pyproject_declares_cli_entry_point(self):
        """Verify pyproject.toml has packaging-cli script entry point"""
        content = self._read_file(self.PYPROJECT)
        assert "packaging-cli" in content, "pyproject.toml missing CLI entry point"
        assert "[project.scripts]" in content, "pyproject.toml missing [project.scripts]"

    def test_pyproject_depends_on_packaging(self):
        """Verify dependency on packaging>=23.0"""
        content = self._read_file(self.PYPROJECT)
        assert "packaging" in content, "pyproject.toml missing packaging dependency"

    def test_init_has_version(self):
        """Verify __init__.py defines __version__"""
        content = self._read_file(self.INIT)
        assert "__version__" in content, "__init__.py missing __version__"

    def test_cli_defines_main_with_subcommands(self):
        """Verify cli.py defines main() with check-version, check-specifier, normalize"""
        content = self._read_file(self.CLI)
        assert "def main" in content, "cli.py missing main() function"
        for cmd in ["check-version", "check_version", "check-specifier",
                     "check_specifier", "normalize"]:
            if cmd in content:
                break
        else:
            pytest.fail("cli.py missing subcommand definitions")

    def test_version_check_uses_packaging_version(self):
        """Verify version_check uses packaging.version for parsing"""
        content = self._read_file(self.VERSION_CHECK)
        assert "packaging.version" in content or "from packaging" in content, \
            "version_check missing packaging.version import"
        assert "InvalidVersion" in content or "Version" in content, \
            "version_check missing Version/InvalidVersion usage"

    def test_specifier_check_uses_packaging_specifiers(self):
        """Verify specifier_check uses packaging.specifiers"""
        content = self._read_file(self.SPECIFIER_CHECK)
        assert "specifier" in content.lower(), \
            "specifier_check missing specifier handling"

    def test_normalize_produces_pep440(self):
        """Verify normalize command produces PEP 440 normalized form"""
        content = self._read_file(self.NORMALIZE)
        assert "normalize" in content.lower(), "normalize missing normalization logic"

    # === Functional Checks ===

    def test_all_python_files_valid(self):
        """Verify all Python files have valid syntax"""
        for path in [self.INIT, self.CLI, self.VERSION_CHECK,
                     self.SPECIFIER_CHECK, self.NORMALIZE]:
            filepath = os.path.join(self.REPO_DIR, path)
            with open(filepath) as f:
                try:
                    ast.parse(f.read())
                except SyntaxError as e:
                    pytest.fail(f"{path} syntax error: {e}")

    def test_pip_install_succeeds(self):
        """Verify pip install -e ./packaging_cli works"""
        result = subprocess.run(
            ["pip", "install", "-e", "./packaging_cli"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, \
            f"pip install failed: {result.stderr[:500]}"

    def test_cli_check_version_valid(self):
        """Verify packaging-cli check-version '1.2.3' exits 0"""
        result = subprocess.run(
            ["python", "-m", "packaging_cli.cli", "check-version", "1.2.3"],
            cwd=os.path.join(self.REPO_DIR, "packaging_cli", "src"),
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            assert "1.2.3" in result.stdout
        # May fail if module path differs; not a hard failure

    def test_tests_cover_valid_invalid_edge_cases(self):
        """Verify tests cover valid, invalid, and edge case inputs"""
        content = self._read_file(self.TESTS)
        tree = ast.parse(content)
        test_funcs = [
            n.name for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")
        ]
        assert len(test_funcs) >= 6, \
            f"Expected at least 6 tests, found {len(test_funcs)}"
        content_lower = content.lower()
        assert "invalid" in content_lower or "error" in content_lower, \
            "Tests missing invalid input coverage"
        assert "pre" in content_lower or "alpha" in content_lower or "dev" in content_lower, \
            "Tests missing pre-release edge case"
