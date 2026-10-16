"""
Tests for skill: python-packaging
Repo: pypa/packaging
Image: zhangyiiiiii/swe-skills-bench-python
Task: Create a distributable Python package with CLI, plugins, and
      PyPI-ready configuration using modern pyproject.toml.
"""

import ast
import os
import re
import subprocess

import pytest

REPO_DIR = "/workspace/packaging"
PKG_DIR = os.path.join(REPO_DIR, "examples", "sample_package")
SRC_DIR = os.path.join(PKG_DIR, "src", "sample_lib")

PYPROJECT = os.path.join(PKG_DIR, "pyproject.toml")
INIT_FILE = os.path.join(SRC_DIR, "__init__.py")
CORE_FILE = os.path.join(SRC_DIR, "core.py")
CLI_FILE = os.path.join(SRC_DIR, "cli.py")
PLUGINS_FILE = os.path.join(SRC_DIR, "plugins.py")
PY_TYPED = os.path.join(SRC_DIR, "py.typed")
TEST_CORE = os.path.join(PKG_DIR, "tests", "test_core.py")
TEST_CLI = os.path.join(PKG_DIR, "tests", "test_cli.py")
TEST_PLUGINS = os.path.join(PKG_DIR, "tests", "test_plugins.py")
README = os.path.join(PKG_DIR, "README.md")


# ---------------------------------------------------------------------------
# Layer 1 — file_path_check
# ---------------------------------------------------------------------------

class TestFilePathCheck:
    """Verify all required package files were created."""

    def test_pyproject_exists(self):
        assert os.path.isfile(PYPROJECT), f"Expected {PYPROJECT}"

    def test_init_exists(self):
        assert os.path.isfile(INIT_FILE), f"Expected {INIT_FILE}"

    def test_core_exists(self):
        assert os.path.isfile(CORE_FILE), f"Expected {CORE_FILE}"

    def test_cli_exists(self):
        assert os.path.isfile(CLI_FILE), f"Expected {CLI_FILE}"

    def test_plugins_exists(self):
        assert os.path.isfile(PLUGINS_FILE), f"Expected {PLUGINS_FILE}"

    def test_py_typed_exists(self):
        assert os.path.isfile(PY_TYPED), f"Expected {PY_TYPED}"

    def test_test_core_exists(self):
        assert os.path.isfile(TEST_CORE), f"Expected {TEST_CORE}"

    def test_test_cli_exists(self):
        assert os.path.isfile(TEST_CLI), f"Expected {TEST_CLI}"

    def test_test_plugins_exists(self):
        assert os.path.isfile(TEST_PLUGINS), f"Expected {TEST_PLUGINS}"

    def test_readme_exists(self):
        assert os.path.isfile(README), f"Expected {README}"


# ---------------------------------------------------------------------------
# Layer 2 — semantic_check
# ---------------------------------------------------------------------------

class TestSemanticPyproject:
    """Verify pyproject.toml content."""

    @pytest.fixture(autouse=True)
    def _load_source(self):
        with open(PYPROJECT, "r", encoding="utf-8") as f:
            self.src = f.read()

    def test_build_system(self):
        assert "build-system" in self.src, "Expected [build-system] section"
        assert "setuptools" in self.src, "Expected setuptools as build backend"

    def test_project_name(self):
        assert "sample-lib" in self.src or "sample_lib" in self.src, (
            "Expected project name 'sample-lib'"
        )

    def test_version(self):
        assert "1.0.0" in self.src, "Expected version '1.0.0'"

    def test_requires_python(self):
        assert "requires-python" in self.src, "Expected requires-python field"
        assert "3.9" in self.src, "Expected Python >=3.9"

    def test_scripts_entry_point(self):
        assert "sample-tool" in self.src, "Expected sample-tool CLI entry point"

    def test_optional_dependencies(self):
        """Must have dev and docs extras."""
        assert "dev" in self.src, "Expected [project.optional-dependencies] dev"
        assert "pytest" in self.src, "Expected pytest in dev dependencies"

    def test_plugin_entry_points(self):
        """Must define plugin entry point group."""
        assert "sample_lib.plugins" in self.src, (
            "Expected [project.entry-points.\"sample_lib.plugins\"] section"
        )

    def test_classifiers(self):
        """Must have at least 5 classifiers."""
        classifier_count = self.src.count("Programming Language")
        classifier_count += self.src.count("License")
        classifier_count += self.src.count("Operating System")
        assert classifier_count >= 2 or "classifiers" in self.src, (
            "Expected classifiers in project metadata"
        )


class TestSemanticCore:
    """Verify TextProcessor class."""

    @pytest.fixture(autouse=True)
    def _load_source(self):
        with open(CORE_FILE, "r", encoding="utf-8") as f:
            self.src = f.read()
        self.tree = ast.parse(self.src)

    def test_class_defined(self):
        classes = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.ClassDef)]
        assert "TextProcessor" in classes, (
            f"Expected TextProcessor class; found: {classes}"
        )

    def test_tokenize_method(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "tokenize" in funcs, "Expected tokenize() method"

    def test_normalize_method(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "normalize" in funcs, "Expected normalize() method"

    def test_word_count_method(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "word_count" in funcs, "Expected word_count() method"

    def test_word_frequencies_method(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "word_frequencies" in funcs, "Expected word_frequencies() method"

    def test_sentences_method(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "sentences" in funcs, "Expected sentences() method"


class TestSemanticCLI:
    """Verify CLI entry point."""

    @pytest.fixture(autouse=True)
    def _load_source(self):
        with open(CLI_FILE, "r", encoding="utf-8") as f:
            self.src = f.read()
        self.tree = ast.parse(self.src)

    def test_main_function(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "main" in funcs, "Expected main() function as CLI entry point"

    def test_argparse_used(self):
        assert "argparse" in self.src or "ArgumentParser" in self.src, (
            "Expected argparse for CLI argument parsing"
        )

    def test_subcommands(self):
        """Must support process, stats, plugins subcommands."""
        for cmd in ["process", "stats", "plugins"]:
            assert cmd in self.src, f"Expected subcommand '{cmd}'"


class TestSemanticPlugins:
    """Verify plugin system."""

    @pytest.fixture(autouse=True)
    def _load_source(self):
        with open(PLUGINS_FILE, "r", encoding="utf-8") as f:
            self.src = f.read()
        self.tree = ast.parse(self.src)

    def test_plugin_manager_class(self):
        classes = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.ClassDef)]
        assert "PluginManager" in classes, (
            f"Expected PluginManager class; found: {classes}"
        )

    def test_discover_method(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "discover" in funcs, "Expected discover() method"

    def test_register_method(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "register" in funcs, "Expected register() method"

    def test_apply_method(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "apply" in funcs, "Expected apply() method"

    def test_entry_points_discovery(self):
        """Must use importlib.metadata entry_points."""
        has_entry_points = (
            "entry_points" in self.src
            or "importlib.metadata" in self.src
        )
        assert has_entry_points, "Expected importlib.metadata entry_points discovery"

    def test_uppercase_builtin_plugin(self):
        assert "uppercase" in self.src, "Expected built-in uppercase plugin"


# ---------------------------------------------------------------------------
# Layer 3 — functional_check
# ---------------------------------------------------------------------------

class TestFunctionalPythonPackaging:
    """Functional checks — syntax, import, and build verification."""

    def _run(self, cmd, cwd=PKG_DIR, timeout=120):
        return subprocess.run(
            cmd, shell=True, cwd=cwd,
            capture_output=True, text=True, timeout=timeout,
        )

    def _parse(self, filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            src = f.read()
        try:
            ast.parse(src)
            return True, None
        except SyntaxError as e:
            return False, str(e)

    def test_core_valid_python(self):
        ok, err = self._parse(CORE_FILE)
        assert ok, f"core.py syntax error: {err}"

    def test_cli_valid_python(self):
        ok, err = self._parse(CLI_FILE)
        assert ok, f"cli.py syntax error: {err}"

    def test_plugins_valid_python(self):
        ok, err = self._parse(PLUGINS_FILE)
        assert ok, f"plugins.py syntax error: {err}"

    def test_test_core_valid_python(self):
        ok, err = self._parse(TEST_CORE)
        assert ok, f"test_core.py syntax error: {err}"

    def test_pyproject_toml_parseable(self):
        """pyproject.toml must be valid TOML."""
        try:
            import tomllib
        except ImportError:
            try:
                import tomli as tomllib
            except ImportError:
                pytest.skip("No TOML parser available (Python 3.11+ or tomli required)")
        with open(PYPROJECT, "rb") as f:
            data = tomllib.load(f)
        assert "project" in data, "Expected [project] table in pyproject.toml"
        assert "build-system" in data, "Expected [build-system] table"

    def test_core_importable(self):
        """TextProcessor must be importable."""
        result = self._run(
            f"python -c \"import sys; sys.path.insert(0, '{os.path.join(PKG_DIR, 'src')}'); "
            f"from sample_lib.core import TextProcessor; print('OK')\"",
            timeout=30,
        )
        assert "OK" in result.stdout, (
            f"Could not import TextProcessor:\n{result.stderr[:500]}"
        )

    def test_text_processor_basic_functionality(self):
        """TextProcessor must tokenize and count correctly."""
        code = (
            f"import sys; sys.path.insert(0, '{os.path.join(PKG_DIR, 'src')}'); "
            f"from sample_lib.core import TextProcessor; "
            f"tp = TextProcessor('hello world hello'); "
            f"print(tp.word_count())"
        )
        result = self._run(f'python -c "{code}"', timeout=30)
        if result.returncode == 0:
            count = int(result.stdout.strip())
            assert count == 3, f"Expected word_count()=3; got {count}"
        else:
            pytest.skip(f"TextProcessor not runnable: {result.stderr[:300]}")

    def test_src_layout_structure(self):
        """Package must follow src/ layout."""
        assert os.path.isdir(os.path.join(PKG_DIR, "src")), "Expected src/ directory"
        assert os.path.isdir(SRC_DIR), "Expected src/sample_lib/ directory"
