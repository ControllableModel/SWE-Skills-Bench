"""
Test skill: bazel-build-optimization
Verify that the Agent configures a Bazel build system for a polyglot
monorepo with WORKSPACE, BUILD files, .bazelrc presets, custom Starlark
rules, and CI workflow with remote caching.
"""

import os
import re
import pytest

try:
    import yaml
except ImportError:
    yaml = None


class TestBazelBuildOptimization:
    REPO_DIR = "/workspace/bazel"

    # === File Path Checks ===

    def test_workspace_bazel_exists(self):
        assert os.path.exists(os.path.join(self.REPO_DIR, "WORKSPACE.bazel"))

    def test_bazelrc_exists(self):
        assert os.path.exists(os.path.join(self.REPO_DIR, ".bazelrc"))

    def test_bazelversion_exists(self):
        assert os.path.exists(os.path.join(self.REPO_DIR, ".bazelversion"))

    def test_web_build_exists(self):
        assert os.path.exists(os.path.join(self.REPO_DIR, "apps/web/BUILD.bazel"))

    def test_ml_build_exists(self):
        assert os.path.exists(os.path.join(self.REPO_DIR, "services/ml/BUILD.bazel"))

    def test_gateway_build_exists(self):
        assert os.path.exists(os.path.join(self.REPO_DIR, "services/gateway/BUILD.bazel"))

    def test_proto_build_exists(self):
        assert os.path.exists(os.path.join(self.REPO_DIR, "proto/BUILD.bazel"))

    def test_custom_starlark_rules_exist(self):
        assert os.path.exists(os.path.join(self.REPO_DIR, "tools/rules/proto_gen.bzl"))
        assert os.path.exists(os.path.join(self.REPO_DIR, "tools/rules/docker.bzl"))

    def test_ci_workflow_exists(self):
        assert os.path.exists(
            os.path.join(self.REPO_DIR, ".github/workflows/bazel-ci.yml")
        )

    # === Semantic Checks ===

    def test_workspace_has_name(self):
        """WORKSPACE should define workspace name 'monorepo'"""
        path = os.path.join(self.REPO_DIR, "WORKSPACE.bazel")
        with open(path) as f:
            content = f.read()
        assert re.search(r'workspace\s*\(\s*name\s*=\s*"monorepo"', content), (
            "WORKSPACE should be named 'monorepo'"
        )

    def test_workspace_registers_toolchains(self):
        """WORKSPACE should register TS, Python, Go, and Protobuf toolchains"""
        path = os.path.join(self.REPO_DIR, "WORKSPACE.bazel")
        with open(path) as f:
            content = f.read()
        assert "rules_js" in content or "aspect_rules_js" in content, "Missing JS/TS toolchain"
        assert "rules_python" in content, "Missing Python toolchain"
        assert "rules_go" in content, "Missing Go toolchain"
        assert "rules_proto" in content or "proto" in content, "Missing Protobuf toolchain"

    def test_workspace_has_container_rules(self):
        """WORKSPACE should have container/OCI rules"""
        path = os.path.join(self.REPO_DIR, "WORKSPACE.bazel")
        with open(path) as f:
            content = f.read()
        assert "rules_oci" in content or "container" in content or "rules_docker" in content, (
            "Missing container rules"
        )

    def test_bazelrc_has_remote_cache(self):
        """.bazelrc should configure remote caching"""
        path = os.path.join(self.REPO_DIR, ".bazelrc")
        with open(path) as f:
            content = f.read()
        assert "remote-cache" in content or "remote_cache" in content, (
            "Missing remote cache configuration"
        )

    def test_bazelrc_has_ci_preset(self):
        """.bazelrc should have CI preset"""
        path = os.path.join(self.REPO_DIR, ".bazelrc")
        with open(path) as f:
            content = f.read()
        assert "build:ci" in content, "Missing CI preset"

    def test_bazelrc_has_disk_cache(self):
        """.bazelrc should configure disk cache"""
        path = os.path.join(self.REPO_DIR, ".bazelrc")
        with open(path) as f:
            content = f.read()
        assert "disk_cache" in content, "Missing disk cache configuration"

    def test_bazelrc_has_sandboxing(self):
        """.bazelrc should disable sandbox networking"""
        path = os.path.join(self.REPO_DIR, ".bazelrc")
        with open(path) as f:
            content = f.read()
        assert "sandbox" in content, "Missing sandboxing config"

    def test_web_build_has_targets(self):
        """Web BUILD should have library, test, and binary targets"""
        path = os.path.join(self.REPO_DIR, "apps/web/BUILD.bazel")
        with open(path) as f:
            content = f.read()
        assert "js_library" in content or "ts_library" in content, "Missing library target"
        assert "js_test" in content or "ts_test" in content or "test" in content, "Missing test target"

    def test_ml_build_has_py_targets(self):
        """ML BUILD should have py_binary and py_test targets"""
        path = os.path.join(self.REPO_DIR, "services/ml/BUILD.bazel")
        with open(path) as f:
            content = f.read()
        assert "py_binary" in content, "Missing py_binary target"
        assert "py_test" in content, "Missing py_test target"

    def test_gateway_build_has_go_targets(self):
        """Gateway BUILD should have go_binary and go_test targets"""
        path = os.path.join(self.REPO_DIR, "services/gateway/BUILD.bazel")
        with open(path) as f:
            content = f.read()
        assert "go_binary" in content, "Missing go_binary target"
        assert "go_test" in content, "Missing go_test target"

    def test_proto_build_has_proto_library(self):
        """Proto BUILD should have proto_library definitions"""
        path = os.path.join(self.REPO_DIR, "proto/BUILD.bazel")
        with open(path) as f:
            content = f.read()
        assert "proto_library" in content, "Missing proto_library"

    def test_platforms_build_exists(self):
        """Platform definitions should exist"""
        path = os.path.join(self.REPO_DIR, "platforms/BUILD.bazel")
        assert os.path.exists(path), "Missing platforms/BUILD.bazel"
        with open(path) as f:
            content = f.read()
        assert "linux" in content.lower() or "platform" in content, (
            "Platform definitions should include linux"
        )

    # === Functional Checks ===

    def test_bazelversion_contains_valid_version(self):
        """.bazelversion should contain a valid semver string"""
        path = os.path.join(self.REPO_DIR, ".bazelversion")
        with open(path) as f:
            version = f.read().strip()
        assert re.match(r"\d+\.\d+\.\d+", version), (
            f"Invalid Bazel version: {version}"
        )

    def test_proto_gen_bzl_defines_rule(self):
        """proto_gen.bzl should define a custom rule or macro"""
        path = os.path.join(self.REPO_DIR, "tools/rules/proto_gen.bzl")
        with open(path) as f:
            content = f.read()
        assert "def " in content, "Should define functions/macros"
        assert "rule(" in content or "def " in content, "Should define a rule or macro"

    def test_docker_bzl_defines_macro(self):
        """docker.bzl should define a container image macro"""
        path = os.path.join(self.REPO_DIR, "tools/rules/docker.bzl")
        with open(path) as f:
            content = f.read()
        assert "def " in content, "Should define a macro"
        assert "container" in content.lower() or "image" in content.lower() or "oci" in content.lower(), (
            "Should reference container/image/OCI"
        )

    def test_ci_workflow_valid_yaml(self):
        """CI workflow should be valid YAML"""
        if yaml is None:
            pytest.skip("PyYAML not available")
        path = os.path.join(self.REPO_DIR, ".github/workflows/bazel-ci.yml")
        with open(path) as f:
            data = yaml.safe_load(f)
        assert "jobs" in data, "Workflow must have jobs"
