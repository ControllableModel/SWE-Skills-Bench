"""
Tests for the python-packaging skill.

Validates that a Python package with CLI, src layout, and publish workflow
was created for pypa/packaging, including parse-version, check-requirement,
inspect-metadata commands, pyproject.toml configuration, and GitHub Actions.

Repo: packaging (https://github.com/pypa/packaging)
"""

import ast
import os
import re
import subprocess
import sys

REPO_DIR = "/workspace/packaging"


class TestFilePathCheck:
    """Verify that all required files were created."""

    def test_init_file_exists(self):
        path = os.path.join(REPO_DIR, "src", "packaging_cli", "__init__.py")
        assert os.path.isfile(path), f"Expected __init__.py at {path}"

    def test_main_file_exists(self):
        path = os.path.join(REPO_DIR, "src", "packaging_cli", "__main__.py")
        assert os.path.isfile(path), f"Expected __main__.py at {path}"

    def test_cli_file_exists(self):
        path = os.path.join(REPO_DIR, "src", "packaging_cli", "cli.py")
        assert os.path.isfile(path), f"Expected cli.py at {path}"

    def test_py_typed_marker_exists(self):
        path = os.path.join(REPO_DIR, "src", "packaging_cli", "py.typed")
        assert os.path.isfile(path), f"Expected py.typed PEP 561 marker at {path}"

    def test_test_file_exists(self):
        path = os.path.join(REPO_DIR, "tests", "test_cli.py")
        assert os.path.isfile(path), f"Expected test_cli.py at {path}"

    def test_publish_workflow_exists(self):
        path = os.path.join(REPO_DIR, ".github", "workflows", "publish.yml")
        assert os.path.isfile(path), f"Expected publish.yml workflow at {path}"


class TestSemanticPackageMetadata:
    """Verify pyproject.toml configuration."""

    def _read_pyproject(self):
        path = os.path.join(REPO_DIR, "pyproject.toml")
        with open(path, "r") as f:
            return f.read()

    def test_project_table_exists(self):
        content = self._read_pyproject()
        assert re.search(r"\[project\]", content), (
            "Expected [project] table in pyproject.toml"
        )

    def test_package_name(self):
        content = self._read_pyproject()
        assert re.search(r'name\s*=\s*"packaging-cli"', content), (
            "Expected package name 'packaging-cli' in pyproject.toml"
        )

    def test_requires_python(self):
        content = self._read_pyproject()
        assert re.search(r"requires-python.*3\.9|requires.python.*>=.*3\.9", content), (
            "Expected requires-python >= 3.9"
        )

    def test_packaging_dependency(self):
        content = self._read_pyproject()
        assert re.search(r'packaging\s*>=\s*24\.0|"packaging>=24\.0"', content), (
            "Expected packaging >= 24.0 dependency"
        )

    def test_build_system(self):
        content = self._read_pyproject()
        assert re.search(r"\[build-system\]", content), (
            "Expected [build-system] table in pyproject.toml"
        )

    def test_console_script_entry_point(self):
        content = self._read_pyproject()
        assert re.search(r"packaging-cli\s*=\s*.*packaging_cli.*cli.*main", content), (
            "Expected console script entry point: packaging-cli = packaging_cli.cli:main"
        )


class TestSemanticCLICommands:
    """Verify CLI command implementations."""

    def _read_cli(self):
        path = os.path.join(REPO_DIR, "src", "packaging_cli", "cli.py")
        with open(path, "r") as f:
            return f.read()

    def test_parse_version_command(self):
        content = self._read_cli()
        assert re.search(r"parse.version|parse_version", content, re.IGNORECASE), (
            "Expected parse-version CLI command"
        )

    def test_check_requirement_command(self):
        content = self._read_cli()
        assert re.search(r"check.requirement|check_requirement", content, re.IGNORECASE), (
            "Expected check-requirement CLI command"
        )

    def test_inspect_metadata_command(self):
        content = self._read_cli()
        assert re.search(r"inspect.metadata|inspect_metadata", content, re.IGNORECASE), (
            "Expected inspect-metadata CLI command"
        )

    def test_json_output_format(self):
        content = self._read_cli()
        assert re.search(r"json|JSON|format", content), (
            "Expected JSON output format support"
        )

    def test_text_output_format(self):
        content = self._read_cli()
        assert re.search(r"text|TEXT|--format", content), (
            "Expected text output format option"
        )

    def test_main_function(self):
        content = self._read_cli()
        assert re.search(r"def\s+main", content), (
            "Expected main() function as CLI entry point"
        )

    def test_argparse_or_click_usage(self):
        content = self._read_cli()
        assert re.search(r"argparse|click|typer|ArgumentParser", content), (
            "Expected argument parser (argparse, click, or typer)"
        )


class TestSemanticVersionParsing:
    """Verify version parsing outputs correct JSON structure."""

    def _read_cli(self):
        path = os.path.join(REPO_DIR, "src", "packaging_cli", "cli.py")
        with open(path, "r") as f:
            return f.read()

    def test_version_components(self):
        """Should output major, minor, micro, pre, post, dev."""
        content = self._read_cli()
        for field in ["major", "minor", "micro"]:
            assert field in content, f"Expected '{field}' in version parse output"

    def test_prerelease_flag(self):
        content = self._read_cli()
        assert re.search(r"is_prerelease|prerelease", content), (
            "Expected is_prerelease field in version output"
        )

    def test_invalid_version_exit_code(self):
        content = self._read_cli()
        assert re.search(r"exit\(1\)|sys\.exit\(1\)|exit.*1|InvalidVersion", content), (
            "Expected exit code 1 for invalid version strings"
        )


class TestSemanticMainModule:
    """Verify __main__.py allows python -m packaging_cli."""

    def _read_main(self):
        path = os.path.join(REPO_DIR, "src", "packaging_cli", "__main__.py")
        with open(path, "r") as f:
            return f.read()

    def test_calls_main(self):
        content = self._read_main()
        assert re.search(r"main\(\)|from.*cli.*import|from.*packaging_cli", content), (
            "Expected __main__.py to invoke cli.main()"
        )


class TestSemanticVersionInit:
    """Verify __init__.py has __version__."""

    def test_version_defined(self):
        path = os.path.join(REPO_DIR, "src", "packaging_cli", "__init__.py")
        with open(path, "r") as f:
            content = f.read()
        assert re.search(r"__version__\s*=", content), (
            "Expected __version__ in __init__.py"
        )


class TestSemanticPublishWorkflow:
    """Verify GitHub Actions publish workflow configuration."""

    def _read_workflow(self):
        path = os.path.join(REPO_DIR, ".github", "workflows", "publish.yml")
        with open(path, "r") as f:
            return f.read()

    def test_triggers_on_tag_push(self):
        content = self._read_workflow()
        assert re.search(r"tags.*v\*|push.*tags", content, re.DOTALL), (
            "Expected workflow trigger on v* tag push"
        )

    def test_uses_pypi_publish_action(self):
        content = self._read_workflow()
        assert re.search(r"pypa/gh-action-pypi-publish", content), (
            "Expected pypa/gh-action-pypi-publish action"
        )

    def test_oidc_trusted_publishing(self):
        content = self._read_workflow()
        assert re.search(r"id-token.*write|id.token", content, re.IGNORECASE), (
            "Expected OIDC trusted publishing (id-token: write)"
        )

    def test_pytest_before_publish(self):
        content = self._read_workflow()
        assert re.search(r"pytest|test", content), (
            "Expected pytest step before publishing"
        )

    def test_python_build(self):
        content = self._read_workflow()
        assert re.search(r"python.*build|pip.*build|python -m build", content), (
            "Expected python -m build in workflow"
        )


class TestFunctionalPythonSyntax:
    """Validate Python syntax of all created files."""

    def _check_syntax(self, filepath):
        with open(filepath, "r") as f:
            source = f.read()
        ast.parse(source)

    def test_init_syntax(self):
        self._check_syntax(os.path.join(REPO_DIR, "src", "packaging_cli", "__init__.py"))

    def test_main_syntax(self):
        self._check_syntax(os.path.join(REPO_DIR, "src", "packaging_cli", "__main__.py"))

    def test_cli_syntax(self):
        self._check_syntax(os.path.join(REPO_DIR, "src", "packaging_cli", "cli.py"))

    def test_test_syntax(self):
        self._check_syntax(os.path.join(REPO_DIR, "tests", "test_cli.py"))


class TestFunctionalAgentTests:
    """Verify the agent's own tests pass."""

    def test_sufficient_test_count(self):
        path = os.path.join(REPO_DIR, "tests", "test_cli.py")
        with open(path, "r") as f:
            content = f.read()
        test_count = len(re.findall(r"def\s+test_", content))
        assert test_count >= 5, (
            f"Expected at least 5 test functions in test_cli.py, found {test_count}"
        )

    def test_agent_tests_pass(self):
        result = subprocess.run(
            [sys.executable, "-m", "pytest",
             "tests/test_cli.py", "-v", "--tb=short"],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, (
            f"Agent's CLI tests failed:\n{result.stdout[-1000:]}\n{result.stderr[-500:]}"
        )
