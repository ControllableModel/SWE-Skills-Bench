"""
Test skill: bazel-build-optimization
Verify that the Agent correctly implements a Bazel build configuration
generator with remote cache validation and dependency analysis.
"""

import os
import re
import ast
import subprocess
import pytest


class TestBazelBuildOptimization:
    REPO_DIR = "/workspace/bazel"

    # === File Path Checks ===

    def test_workspace_bazel_exists(self):
        """Verify WORKSPACE.bazel was created"""
        path = os.path.join(self.REPO_DIR, "examples/python-bazel/WORKSPACE.bazel")
        assert os.path.exists(path), "WORKSPACE.bazel not found"

    def test_bazelrc_exists(self):
        """Verify .bazelrc was created"""
        path = os.path.join(self.REPO_DIR, "examples/python-bazel/.bazelrc")
        assert os.path.exists(path), ".bazelrc not found"

    def test_root_build_exists(self):
        """Verify root BUILD.bazel was created"""
        path = os.path.join(self.REPO_DIR, "examples/python-bazel/BUILD.bazel")
        assert os.path.exists(path), "Root BUILD.bazel not found"

    def test_lib_build_exists(self):
        """Verify src/lib/BUILD.bazel was created"""
        path = os.path.join(self.REPO_DIR, "examples/python-bazel/src/lib/BUILD.bazel")
        assert os.path.exists(path), "src/lib/BUILD.bazel not found"

    def test_graph_py_exists(self):
        """Verify graph.py was created"""
        path = os.path.join(self.REPO_DIR, "examples/python-bazel/src/lib/graph.py")
        assert os.path.exists(path), "graph.py not found"

    def test_config_validator_py_exists(self):
        """Verify config_validator.py was created"""
        path = os.path.join(
            self.REPO_DIR, "examples/python-bazel/src/lib/config_validator.py"
        )
        assert os.path.exists(path), "config_validator.py not found"

    def test_bin_build_exists(self):
        """Verify src/bin/BUILD.bazel was created"""
        path = os.path.join(self.REPO_DIR, "examples/python-bazel/src/bin/BUILD.bazel")
        assert os.path.exists(path), "src/bin/BUILD.bazel not found"

    def test_analyzer_py_exists(self):
        """Verify analyzer.py was created"""
        path = os.path.join(self.REPO_DIR, "examples/python-bazel/src/bin/analyzer.py")
        assert os.path.exists(path), "analyzer.py not found"

    def test_tests_build_exists(self):
        """Verify tests/BUILD.bazel was created"""
        path = os.path.join(self.REPO_DIR, "examples/python-bazel/tests/BUILD.bazel")
        assert os.path.exists(path), "tests/BUILD.bazel not found"

    def test_test_graph_py_exists(self):
        """Verify tests/test_graph.py was created"""
        path = os.path.join(
            self.REPO_DIR, "examples/python-bazel/tests/test_graph.py"
        )
        assert os.path.exists(path), "tests/test_graph.py not found"

    def test_test_config_validator_py_exists(self):
        """Verify tests/test_config_validator.py was created"""
        path = os.path.join(
            self.REPO_DIR, "examples/python-bazel/tests/test_config_validator.py"
        )
        assert os.path.exists(path), "tests/test_config_validator.py not found"

    # === Semantic Checks: WORKSPACE ===

    def test_workspace_has_name(self):
        """Verify workspace declaration with name"""
        path = os.path.join(self.REPO_DIR, "examples/python-bazel/WORKSPACE.bazel")
        with open(path) as f:
            content = f.read()
        assert "python_bazel_example" in content, (
            "Workspace should be named python_bazel_example"
        )

    def test_workspace_has_rules_python(self):
        """Verify rules_python http_archive"""
        path = os.path.join(self.REPO_DIR, "examples/python-bazel/WORKSPACE.bazel")
        with open(path) as f:
            content = f.read()
        assert "rules_python" in content, "Should load rules_python"
        assert "http_archive" in content, "Should use http_archive"

    def test_workspace_has_sha256(self):
        """Verify http_archive has sha256"""
        path = os.path.join(self.REPO_DIR, "examples/python-bazel/WORKSPACE.bazel")
        with open(path) as f:
            content = f.read()
        assert "sha256" in content, "http_archive should have sha256"

    def test_workspace_has_toolchain(self):
        """Verify python_register_toolchains call"""
        path = os.path.join(self.REPO_DIR, "examples/python-bazel/WORKSPACE.bazel")
        with open(path) as f:
            content = f.read()
        assert "python_register_toolchains" in content, (
            "Should call python_register_toolchains"
        )

    # === Semantic Checks: .bazelrc ===

    def test_bazelrc_jobs_auto(self):
        """Verify build --jobs=auto"""
        path = os.path.join(self.REPO_DIR, "examples/python-bazel/.bazelrc")
        with open(path) as f:
            content = f.read()
        assert "--jobs=auto" in content, "Should set --jobs=auto"

    def test_bazelrc_disk_cache(self):
        """Verify disk cache setting"""
        path = os.path.join(self.REPO_DIR, "examples/python-bazel/.bazelrc")
        with open(path) as f:
            content = f.read()
        assert "--disk_cache" in content, "Should set --disk_cache"

    def test_bazelrc_remote_cache_grpcs(self):
        """Verify remote cache uses grpcs://"""
        path = os.path.join(self.REPO_DIR, "examples/python-bazel/.bazelrc")
        with open(path) as f:
            content = f.read()
        assert "grpcs://" in content, "Remote cache should use grpcs://"

    def test_bazelrc_ci_config(self):
        """Verify CI config profile"""
        path = os.path.join(self.REPO_DIR, "examples/python-bazel/.bazelrc")
        with open(path) as f:
            content = f.read()
        assert "build:ci" in content, "Should define CI config"

    def test_bazelrc_try_import(self):
        """Verify try-import for user.bazelrc"""
        path = os.path.join(self.REPO_DIR, "examples/python-bazel/.bazelrc")
        with open(path) as f:
            content = f.read()
        assert "try-import" in content, "Should have try-import"
        assert "user.bazelrc" in content, "Should import user.bazelrc"

    # === Semantic Checks: graph.py ===

    def test_dependency_graph_class(self):
        """Verify DependencyGraph class is defined"""
        path = os.path.join(self.REPO_DIR, "examples/python-bazel/src/lib/graph.py")
        with open(path) as f:
            content = f.read()
        assert "class DependencyGraph" in content, (
            "DependencyGraph class should be defined"
        )

    def test_add_target_method(self):
        """Verify add_target method"""
        path = os.path.join(self.REPO_DIR, "examples/python-bazel/src/lib/graph.py")
        with open(path) as f:
            content = f.read()
        assert "def add_target(" in content, "Should have add_target method"

    def test_resolve_order_method(self):
        """Verify resolve_order method with topological sort"""
        path = os.path.join(self.REPO_DIR, "examples/python-bazel/src/lib/graph.py")
        with open(path) as f:
            content = f.read()
        assert "def resolve_order(" in content, "Should have resolve_order method"

    def test_cyclic_dependency_error(self):
        """Verify CyclicDependencyError is defined"""
        path = os.path.join(self.REPO_DIR, "examples/python-bazel/src/lib/graph.py")
        with open(path) as f:
            content = f.read()
        assert "CyclicDependencyError" in content, (
            "CyclicDependencyError should be defined"
        )

    def test_invalid_label_error(self):
        """Verify InvalidLabelError is defined"""
        path = os.path.join(self.REPO_DIR, "examples/python-bazel/src/lib/graph.py")
        with open(path) as f:
            content = f.read()
        assert "InvalidLabelError" in content, (
            "InvalidLabelError should be defined"
        )

    def test_query_deps_method(self):
        """Verify query_deps method for transitive deps"""
        path = os.path.join(self.REPO_DIR, "examples/python-bazel/src/lib/graph.py")
        with open(path) as f:
            content = f.read()
        assert "query_deps" in content, "Should have query_deps method"

    def test_query_rdeps_method(self):
        """Verify query_rdeps method for reverse deps"""
        path = os.path.join(self.REPO_DIR, "examples/python-bazel/src/lib/graph.py")
        with open(path) as f:
            content = f.read()
        assert "query_rdeps" in content, "Should have query_rdeps method"

    # === Semantic Checks: config_validator.py ===

    def test_validate_bazelrc_function(self):
        """Verify validate_bazelrc function"""
        path = os.path.join(
            self.REPO_DIR, "examples/python-bazel/src/lib/config_validator.py"
        )
        with open(path) as f:
            content = f.read()
        assert "def validate_bazelrc(" in content, (
            "Should have validate_bazelrc function"
        )

    def test_validate_workspace_function(self):
        """Verify validate_workspace function"""
        path = os.path.join(
            self.REPO_DIR, "examples/python-bazel/src/lib/config_validator.py"
        )
        with open(path) as f:
            content = f.read()
        assert "def validate_workspace(" in content, (
            "Should have validate_workspace function"
        )

    def test_config_issue_class(self):
        """Verify ConfigIssue class with line, severity, message"""
        path = os.path.join(
            self.REPO_DIR, "examples/python-bazel/src/lib/config_validator.py"
        )
        with open(path) as f:
            content = f.read()
        assert "ConfigIssue" in content, "ConfigIssue should be defined"

    # === Semantic Checks: BUILD files ===

    def test_lib_build_has_py_library(self):
        """Verify src/lib/BUILD.bazel has py_library rule"""
        path = os.path.join(
            self.REPO_DIR, "examples/python-bazel/src/lib/BUILD.bazel"
        )
        with open(path) as f:
            content = f.read()
        assert "py_library" in content, "Should define py_library rule"

    def test_bin_build_has_py_binary(self):
        """Verify src/bin/BUILD.bazel has py_binary rule"""
        path = os.path.join(
            self.REPO_DIR, "examples/python-bazel/src/bin/BUILD.bazel"
        )
        with open(path) as f:
            content = f.read()
        assert "py_binary" in content, "Should define py_binary rule"

    def test_tests_build_has_py_test(self):
        """Verify tests/BUILD.bazel has py_test rules"""
        path = os.path.join(
            self.REPO_DIR, "examples/python-bazel/tests/BUILD.bazel"
        )
        with open(path) as f:
            content = f.read()
        assert "py_test" in content, "Should define py_test rules"

    # === Functional Checks ===

    def test_graph_py_parses(self):
        """Verify graph.py has valid Python syntax"""
        path = os.path.join(self.REPO_DIR, "examples/python-bazel/src/lib/graph.py")
        with open(path) as f:
            source = f.read()
        try:
            ast.parse(source)
        except SyntaxError as e:
            pytest.fail(f"graph.py has syntax error: {e}")

    def test_config_validator_parses(self):
        """Verify config_validator.py has valid Python syntax"""
        path = os.path.join(
            self.REPO_DIR, "examples/python-bazel/src/lib/config_validator.py"
        )
        with open(path) as f:
            source = f.read()
        try:
            ast.parse(source)
        except SyntaxError as e:
            pytest.fail(f"config_validator.py has syntax error: {e}")

    def test_bazel_build(self):
        """Verify bazel build //... succeeds"""
        result = subprocess.run(
            ["bazel", "build", "//..."],
            cwd=os.path.join(self.REPO_DIR, "examples/python-bazel"),
            capture_output=True,
            text=True,
            timeout=600,
        )
        assert result.returncode == 0, (
            f"bazel build failed:\n{result.stderr[-2000:]}"
        )
