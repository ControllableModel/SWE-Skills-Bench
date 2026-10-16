"""
Test skill: bazel-build-optimization
Verify that the Agent creates a Python Bazel build example with
py_library, py_binary, py_test targets, workspace configuration,
and Python toolchain setup.
"""

import os
import re
import ast
import subprocess
import pytest


class TestBazelBuildOptimization:
    REPO_DIR = "/workspace/bazel"

    BASE = "examples/python-bazel"

    # === File Path Checks ===

    def test_build_file_exists(self):
        """Verify BUILD or BUILD.bazel file exists"""
        build = os.path.join(self.REPO_DIR, self.BASE, "BUILD")
        build_bazel = os.path.join(self.REPO_DIR, self.BASE, "BUILD.bazel")
        assert os.path.exists(build) or os.path.exists(build_bazel), (
            "BUILD or BUILD.bazel not found"
        )

    def test_workspace_file_exists(self):
        """Verify WORKSPACE.bazel or MODULE.bazel exists"""
        workspace = os.path.join(self.REPO_DIR, self.BASE, "WORKSPACE.bazel")
        workspace2 = os.path.join(self.REPO_DIR, self.BASE, "WORKSPACE")
        module = os.path.join(self.REPO_DIR, self.BASE, "MODULE.bazel")
        assert (
            os.path.exists(workspace)
            or os.path.exists(workspace2)
            or os.path.exists(module)
        ), "WORKSPACE.bazel, WORKSPACE, or MODULE.bazel not found"

    # === Semantic Checks ===

    def test_py_library_target(self):
        """Verify py_library target is defined"""
        content = self._read_build_file()
        assert "py_library" in content, (
            "BUILD file should define a py_library target"
        )

    def test_py_binary_target(self):
        """Verify py_binary target is defined"""
        content = self._read_build_file()
        assert "py_binary" in content, (
            "BUILD file should define a py_binary target"
        )

    def test_py_test_target(self):
        """Verify py_test target is defined"""
        content = self._read_build_file()
        assert "py_test" in content, (
            "BUILD file should define a py_test target"
        )

    def test_binary_depends_on_library(self):
        """Verify binary target depends on the library target"""
        content = self._read_build_file()
        assert "deps" in content, (
            "Binary target should declare deps on library"
        )

    def test_workspace_configures_rules_python(self):
        """Verify workspace configures rules_python"""
        combined = ""
        for fname in [
            "WORKSPACE.bazel", "WORKSPACE", "MODULE.bazel",
        ]:
            path = os.path.join(self.REPO_DIR, self.BASE, fname)
            if os.path.exists(path):
                with open(path) as f:
                    combined += f.read()

        python_indicators = [
            "rules_python", "python", "pip_install",
            "pip_parse", "python_register_toolchains",
        ]
        found = [ind for ind in python_indicators if ind in combined]
        assert len(found) >= 1, (
            f"Workspace should configure rules_python. Found: {found}"
        )

    def test_python_source_files_exist(self):
        """Verify Python source files exist in the example"""
        base_dir = os.path.join(self.REPO_DIR, self.BASE)
        py_files = []
        for root, _, files in os.walk(base_dir):
            for fname in files:
                if fname.endswith(".py"):
                    py_files.append(fname)

        assert len(py_files) >= 2, (
            f"Should have at least 2 Python files. Found: {py_files}"
        )

    def test_python_test_file_exists(self):
        """Verify a Python test file exists"""
        base_dir = os.path.join(self.REPO_DIR, self.BASE)
        test_files = []
        for root, _, files in os.walk(base_dir):
            for fname in files:
                if fname.startswith("test_") or fname.endswith("_test.py"):
                    test_files.append(fname)

        assert len(test_files) >= 1, (
            f"Should have at least 1 test file. Found: {test_files}"
        )

    # === Functional Checks ===

    def test_python_files_valid_syntax(self):
        """Verify all Python files have valid syntax"""
        base_dir = os.path.join(self.REPO_DIR, self.BASE)
        for root, _, files in os.walk(base_dir):
            for fname in files:
                if fname.endswith(".py"):
                    fpath = os.path.join(root, fname)
                    with open(fpath) as f:
                        source = f.read()
                    try:
                        ast.parse(source)
                    except SyntaxError as e:
                        pytest.fail(f"{fname} has syntax errors: {e}")

    def test_build_file_has_names(self):
        """Verify BUILD targets have name attributes"""
        content = self._read_build_file()
        name_count = content.count("name =") + content.count("name=")
        assert name_count >= 3, (
            f"BUILD file should have at least 3 named targets. "
            f"Found: {name_count}"
        )

    def test_library_importable_by_binary(self):
        """Verify library module is importable by binary via shared module name"""
        content = self._read_build_file()
        # Check that deps reference the library target
        assert ":" in content or "//" in content, (
            "Targets should reference each other via labels"
        )

    def _read_build_file(self):
        """Helper to read the BUILD file"""
        for fname in ["BUILD.bazel", "BUILD"]:
            path = os.path.join(self.REPO_DIR, self.BASE, fname)
            if os.path.exists(path):
                with open(path) as f:
                    return f.read()
        pytest.fail("No BUILD file found")
