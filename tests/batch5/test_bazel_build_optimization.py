"""
Test skill: bazel-build-optimization
Verify that the Agent correctly creates an optimized Bazel build configuration
for a Python monorepo with test sharding, remote caching, and build profiles.
"""

import os
import re
import pytest


class TestBazelBuildOptimization:
    REPO_DIR = "/workspace/bazel"

    WORKSPACE = "examples/python-bazel/WORKSPACE"
    ROOT_BUILD = "examples/python-bazel/BUILD.bazel"
    LIB_BUILD = "examples/python-bazel/lib/BUILD.bazel"
    UTILS_BUILD = "examples/python-bazel/lib/utils/BUILD.bazel"
    SERVICE_BUILD = "examples/python-bazel/service/BUILD.bazel"
    PIPELINE_BUILD = "examples/python-bazel/pipeline/BUILD.bazel"
    CLI_BUILD = "examples/python-bazel/cli/BUILD.bazel"
    BAZELRC = "examples/python-bazel/.bazelrc"
    REQUIREMENTS = "examples/python-bazel/requirements_lock.txt"

    def _read_file(self, rel_path):
        filepath = os.path.join(self.REPO_DIR, rel_path)
        with open(filepath) as f:
            return f.read()

    # === File Path Checks ===

    def test_workspace_exists(self):
        filepath = os.path.join(self.REPO_DIR, self.WORKSPACE)
        assert os.path.exists(filepath), f"WORKSPACE not found at {filepath}"

    def test_build_files_exist(self):
        for path in [self.ROOT_BUILD, self.LIB_BUILD, self.UTILS_BUILD,
                     self.SERVICE_BUILD, self.PIPELINE_BUILD, self.CLI_BUILD]:
            filepath = os.path.join(self.REPO_DIR, path)
            assert os.path.exists(filepath), f"BUILD file not found: {filepath}"

    def test_bazelrc_exists(self):
        filepath = os.path.join(self.REPO_DIR, self.BAZELRC)
        assert os.path.exists(filepath), f".bazelrc not found at {filepath}"

    def test_requirements_lock_exists(self):
        filepath = os.path.join(self.REPO_DIR, self.REQUIREMENTS)
        assert os.path.exists(filepath), f"requirements_lock.txt not found"

    # === Semantic Checks ===

    def test_workspace_loads_rules_python(self):
        """Verify WORKSPACE loads rules_python"""
        content = self._read_file(self.WORKSPACE)
        assert "rules_python" in content, "WORKSPACE missing rules_python"

    def test_workspace_configures_python_toolchain(self):
        """Verify Python 3.11 toolchain registration"""
        content = self._read_file(self.WORKSPACE)
        assert "python_register_toolchains" in content or "python3_11" in content, \
            "WORKSPACE missing Python toolchain registration"

    def test_workspace_configures_pip_parse(self):
        """Verify pip_parse for requirements resolution"""
        content = self._read_file(self.WORKSPACE)
        assert "pip_parse" in content, "WORKSPACE missing pip_parse"
        assert "requirements_lock" in content, \
            "WORKSPACE missing requirements_lock reference"

    def test_lib_build_has_granular_targets(self):
        """Verify lib BUILD has models, database, cache py_library targets"""
        content = self._read_file(self.LIB_BUILD)
        for target in ["models", "database", "cache"]:
            assert target in content, f"lib BUILD missing target: {target}"
        assert "py_library" in content, "lib BUILD missing py_library rules"

    def test_lib_build_has_test_sharding(self):
        """Verify database_test has shard_count = 4"""
        content = self._read_file(self.LIB_BUILD)
        assert "shard_count" in content, "lib BUILD missing test sharding"
        assert "4" in content, "lib BUILD missing shard_count = 4"

    def test_utils_build_has_per_module_targets(self):
        """Verify utils BUILD has one py_library per module"""
        content = self._read_file(self.UTILS_BUILD)
        for module in ["string_utils", "date_utils", "retry"]:
            assert module in content, f"utils BUILD missing module: {module}"

    def test_service_build_has_binary_and_dependencies(self):
        """Verify service BUILD has py_binary with correct deps"""
        content = self._read_file(self.SERVICE_BUILD)
        assert "py_binary" in content, "service BUILD missing py_binary"
        assert "//lib:models" in content or "lib:models" in content, \
            "service BUILD missing lib:models dependency"

    def test_pipeline_build_has_test_data(self):
        """Verify pipeline BUILD has filegroup for test data"""
        content = self._read_file(self.PIPELINE_BUILD)
        assert "filegroup" in content, "pipeline BUILD missing filegroup"
        assert "test_data" in content, "pipeline BUILD missing test_data filegroup"
        assert "large" in content.lower() or "timeout" in content.lower(), \
            "pipeline test missing size=large or timeout=long"

    def test_bazelrc_three_profiles(self):
        """Verify .bazelrc defines dev, ci, release profiles"""
        content = self._read_file(self.BAZELRC)
        for profile in ["config=dev", "config=ci", "config=release"]:
            assert profile in content, f".bazelrc missing profile: {profile}"

    def test_bazelrc_remote_cache_in_ci(self):
        """Verify CI profile has remote_cache configured"""
        content = self._read_file(self.BAZELRC)
        assert "remote_cache" in content, ".bazelrc missing remote_cache in CI"

    def test_bazelrc_release_stamp(self):
        """Verify release profile has stamp enabled"""
        content = self._read_file(self.BAZELRC)
        assert "stamp" in content, ".bazelrc missing stamp in release profile"

    # === Functional Checks ===

    def test_workspace_has_valid_starlark_syntax(self):
        """Verify WORKSPACE file uses valid Starlark patterns"""
        content = self._read_file(self.WORKSPACE)
        assert "load(" in content, "WORKSPACE missing load statements"
        assert "http_archive" in content or "rules_python" in content, \
            "WORKSPACE missing repository rules"

    def test_strict_mode_in_bazelrc(self):
        """Verify .bazelrc enables strict action env"""
        content = self._read_file(self.BAZELRC)
        assert "strict_action_env" in content, \
            ".bazelrc missing --incompatible_strict_action_env"
