"""
Tests for skill: bazel-build-optimization
Repo: bazelbuild/bazel
Image: zhangyiiiiii/swe-skills-bench-bazel
Task: Configure Bazel build infrastructure with remote caching, custom
      rules, and a Python monorepo with library/binary/test targets.
"""

import os
import re
import subprocess

import pytest

REPO_DIR = "/workspace/bazel"
DEMO_DIR = os.path.join(REPO_DIR, "examples", "python-bazel")

WORKSPACE_FILE = os.path.join(DEMO_DIR, "WORKSPACE.bazel")
BAZELRC_FILE = os.path.join(DEMO_DIR, ".bazelrc")
ROOT_BUILD = os.path.join(DEMO_DIR, "BUILD.bazel")
LIB_BUILD = os.path.join(DEMO_DIR, "src", "lib", "BUILD.bazel")
APP_BUILD = os.path.join(DEMO_DIR, "src", "app", "BUILD.bazel")
TESTS_BUILD = os.path.join(DEMO_DIR, "tests", "BUILD.bazel")
MACROS_FILE = os.path.join(DEMO_DIR, "tools", "macros.bzl")
CALC_FILE = os.path.join(DEMO_DIR, "src", "lib", "calculator.py")
FORMATTER_FILE = os.path.join(DEMO_DIR, "src", "lib", "formatter.py")
MAIN_FILE = os.path.join(DEMO_DIR, "src", "app", "main.py")
REQUIREMENTS_FILE = os.path.join(DEMO_DIR, "requirements.txt")
TEST_CALC_FILE = os.path.join(DEMO_DIR, "tests", "test_calculator.py")
TEST_FMT_FILE = os.path.join(DEMO_DIR, "tests", "test_formatter.py")


# ---------------------------------------------------------------------------
# Layer 1 — file_path_check
# ---------------------------------------------------------------------------

class TestFilePathCheck:
    """Verify all required Bazel project files exist."""

    def test_workspace_exists(self):
        assert os.path.isfile(WORKSPACE_FILE), f"Missing {WORKSPACE_FILE}"

    def test_bazelrc_exists(self):
        assert os.path.isfile(BAZELRC_FILE), f"Missing {BAZELRC_FILE}"

    def test_root_build_exists(self):
        assert os.path.isfile(ROOT_BUILD), f"Missing {ROOT_BUILD}"

    def test_lib_build_exists(self):
        assert os.path.isfile(LIB_BUILD), f"Missing {LIB_BUILD}"

    def test_app_build_exists(self):
        assert os.path.isfile(APP_BUILD), f"Missing {APP_BUILD}"

    def test_tests_build_exists(self):
        assert os.path.isfile(TESTS_BUILD), f"Missing {TESTS_BUILD}"

    def test_macros_exists(self):
        assert os.path.isfile(MACROS_FILE), f"Missing {MACROS_FILE}"

    def test_calculator_exists(self):
        assert os.path.isfile(CALC_FILE), f"Missing {CALC_FILE}"

    def test_formatter_exists(self):
        assert os.path.isfile(FORMATTER_FILE), f"Missing {FORMATTER_FILE}"

    def test_main_exists(self):
        assert os.path.isfile(MAIN_FILE), f"Missing {MAIN_FILE}"

    def test_requirements_exists(self):
        assert os.path.isfile(REQUIREMENTS_FILE), f"Missing {REQUIREMENTS_FILE}"


# ---------------------------------------------------------------------------
# Layer 2 — semantic_check
# ---------------------------------------------------------------------------

class TestSemanticWorkspace:
    """Verify WORKSPACE.bazel content."""

    @pytest.fixture(autouse=True)
    def _load(self):
        with open(WORKSPACE_FILE, "r", encoding="utf-8") as f:
            self.src = f.read()

    def test_workspace_name(self):
        assert "python_bazel_demo" in self.src, (
            "WORKSPACE should declare name 'python_bazel_demo'"
        )

    def test_rules_python(self):
        assert "rules_python" in self.src, "WORKSPACE must load rules_python"

    def test_http_archive(self):
        assert "http_archive" in self.src, "WORKSPACE must use http_archive"

    def test_pip_parse(self):
        assert "pip_parse" in self.src, "WORKSPACE must use pip_parse for pip deps"

    def test_python_toolchain(self):
        assert "3.11" in self.src or "python3" in self.src.lower(), (
            "WORKSPACE should configure Python 3.11 toolchain"
        )


class TestSemanticBazelrc:
    """Verify .bazelrc profiles."""

    @pytest.fixture(autouse=True)
    def _load(self):
        with open(BAZELRC_FILE, "r", encoding="utf-8") as f:
            self.src = f.read()

    def test_disk_cache_profile(self):
        assert "config=cache" in self.src or "config cache" in self.src, (
            ".bazelrc should define a disk cache profile"
        )
        assert "disk_cache" in self.src, "Cache profile should set disk_cache"

    def test_remote_cache_profile(self):
        assert "remote-cache" in self.src or "remote_cache" in self.src, (
            ".bazelrc should define a remote cache profile"
        )
        assert "remote_cache" in self.src, "Remote cache profile should set remote_cache"

    def test_ci_profile(self):
        assert "config=ci" in self.src or "config ci" in self.src, (
            ".bazelrc should define a CI profile"
        )

    def test_test_output(self):
        assert "test_output" in self.src, ".bazelrc should set test_output"

    def test_jobs_auto(self):
        assert "jobs" in self.src, ".bazelrc should configure jobs setting"


class TestSemanticBuildTargets:
    """Verify BUILD file targets."""

    def _read(self, path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def test_lib_calculator_target(self):
        src = self._read(LIB_BUILD)
        assert "calculator" in src, "lib BUILD should have calculator target"
        assert "py_library" in src, "lib BUILD should use py_library"

    def test_lib_formatter_target(self):
        src = self._read(LIB_BUILD)
        assert "formatter" in src, "lib BUILD should have formatter target"

    def test_app_binary_target(self):
        src = self._read(APP_BUILD)
        assert "py_binary" in src, "app BUILD should use py_binary"
        assert "main" in src, "app BUILD should reference main.py"

    def test_app_deps_on_lib(self):
        src = self._read(APP_BUILD)
        assert "//src/lib" in src, "app should depend on //src/lib"

    def test_test_targets(self):
        src = self._read(TESTS_BUILD)
        assert "py_test" in src, "tests BUILD should use py_test"
        assert "test_calculator" in src, "tests BUILD should have test_calculator target"

    def test_test_size_small(self):
        src = self._read(TESTS_BUILD)
        assert 'size = "small"' in src or "size='small'" in src, (
            "Test targets should have size 'small'"
        )


class TestSemanticMacro:
    """Verify custom Starlark macro."""

    @pytest.fixture(autouse=True)
    def _load(self):
        with open(MACROS_FILE, "r", encoding="utf-8") as f:
            self.src = f.read()

    def test_function_defined(self):
        assert "def py_library_with_tests" in self.src, (
            "Macro file should define py_library_with_tests"
        )

    def test_generates_py_library(self):
        assert "py_library" in self.src, "Macro should generate py_library target"

    def test_generates_py_test(self):
        assert "py_test" in self.src, "Macro should generate py_test target"

    def test_test_srcs_conditional(self):
        assert "test_srcs" in self.src, "Macro should accept test_srcs parameter"


class TestSemanticCalculator:
    """Verify calculator module source."""

    @pytest.fixture(autouse=True)
    def _load(self):
        with open(CALC_FILE, "r", encoding="utf-8") as f:
            self.src = f.read()

    def test_add_function(self):
        assert "def add" in self.src, "Calculator should have add function"

    def test_subtract_function(self):
        assert "def subtract" in self.src, "Calculator should have subtract function"

    def test_multiply_function(self):
        assert "def multiply" in self.src, "Calculator should have multiply function"

    def test_divide_function(self):
        assert "def divide" in self.src, "Calculator should have divide function"

    def test_division_by_zero_value_error(self):
        assert "ValueError" in self.src, "divide should raise ValueError on zero division"


# ---------------------------------------------------------------------------
# Layer 3 — functional_check
# ---------------------------------------------------------------------------

class TestFunctionalCalculator:
    """Import and run calculator functions."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        import sys
        sys.path.insert(0, os.path.join(DEMO_DIR, "src", "lib"))
        try:
            import calculator
            self.calc = calculator
        except ImportError:
            pytest.skip("Cannot import calculator module")

    def test_add(self):
        result = self.calc.add(3, 4)
        assert result == 7.0 or result == 7

    def test_subtract(self):
        result = self.calc.subtract(10, 4)
        assert result == 6.0 or result == 6

    def test_multiply(self):
        result = self.calc.multiply(3, 5)
        assert result == 15.0 or result == 15

    def test_divide(self):
        result = self.calc.divide(10, 2)
        assert result == 5.0 or result == 5

    def test_divide_by_zero_raises_value_error(self):
        with pytest.raises(ValueError, match="[Cc]annot divide by zero"):
            self.calc.divide(10, 0)


class TestFunctionalFormatter:
    """Import and run formatter functions."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        import sys
        sys.path.insert(0, os.path.join(DEMO_DIR, "src", "lib"))
        try:
            import formatter as fmt_mod
            self.fmt = fmt_mod
        except ImportError:
            pytest.skip("Cannot import formatter module")

    def test_format_result(self):
        result = self.fmt.format_result("+", 3, 4, 7.0)
        assert "3" in result and "4" in result and "7" in result
        assert "+" in result

    def test_format_table(self):
        data = [("+", 1, 2, 3), ("-", 5, 3, 2)]
        result = self.fmt.format_table(data)
        assert "1" in result and "2" in result
        # Table should have multiple lines
        assert result.count("\n") >= 2, "Table should have at least header + 2 rows"


class TestFunctionalBazelBuild:
    """Run bazel build if available."""

    def test_bazel_build_all(self):
        result = subprocess.run(
            ["bazel", "build", "//..."],
            cwd=DEMO_DIR,
            capture_output=True,
            text=True,
            timeout=600,
        )
        assert result.returncode == 0, (
            f"bazel build //... failed:\nSTDOUT: {result.stdout[-500:]}\n"
            f"STDERR: {result.stderr[-500:]}"
        )
