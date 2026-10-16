"""
Tests for the bazel-build-optimization skill.

Validates that a multi-language Bazel build configuration was created
with WORKSPACE, BUILD files, .bazelrc, and a custom Starlark rule.

Repo: bazel (https://github.com/bazelbuild/bazel)
"""

import os
import re

REPO_DIR = "/workspace/bazel"
EXAMPLE_DIR = os.path.join(REPO_DIR, "examples", "python-bazel")


class TestFilePathCheck:
    """Verify all required files were created."""

    def test_workspace_exists(self):
        path = os.path.join(EXAMPLE_DIR, "WORKSPACE")
        assert os.path.isfile(path), f"Expected WORKSPACE at {path}"

    def test_root_build_exists(self):
        path = os.path.join(EXAMPLE_DIR, "BUILD")
        assert os.path.isfile(path), f"Expected root BUILD at {path}"

    def test_bazelrc_exists(self):
        path = os.path.join(EXAMPLE_DIR, ".bazelrc")
        assert os.path.isfile(path), f"Expected .bazelrc at {path}"

    def test_src_build_exists(self):
        path = os.path.join(EXAMPLE_DIR, "src", "BUILD")
        assert os.path.isfile(path), f"Expected src/BUILD at {path}"

    def test_src_app_py_exists(self):
        path = os.path.join(EXAMPLE_DIR, "src", "app.py")
        assert os.path.isfile(path), f"Expected src/app.py at {path}"

    def test_utils_build_exists(self):
        path = os.path.join(EXAMPLE_DIR, "src", "utils", "BUILD")
        assert os.path.isfile(path), f"Expected src/utils/BUILD at {path}"

    def test_utils_helpers_exists(self):
        path = os.path.join(EXAMPLE_DIR, "src", "utils", "helpers.py")
        assert os.path.isfile(path), f"Expected src/utils/helpers.py at {path}"

    def test_tests_build_exists(self):
        path = os.path.join(EXAMPLE_DIR, "tests", "BUILD")
        assert os.path.isfile(path), f"Expected tests/BUILD at {path}"

    def test_tests_test_app_exists(self):
        path = os.path.join(EXAMPLE_DIR, "tests", "test_app.py")
        assert os.path.isfile(path), f"Expected tests/test_app.py at {path}"

    def test_codegen_rule_exists(self):
        path = os.path.join(EXAMPLE_DIR, "rules", "codegen.bzl")
        assert os.path.isfile(path), f"Expected rules/codegen.bzl at {path}"


class TestSemanticWorkspace:
    """Verify WORKSPACE sets up Python toolchain and dependencies."""

    def _read_workspace(self):
        path = os.path.join(EXAMPLE_DIR, "WORKSPACE")
        with open(path, "r") as f:
            return f.read()

    def test_rules_python(self):
        content = self._read_workspace()
        assert "rules_python" in content, (
            "Expected rules_python in WORKSPACE"
        )

    def test_python_3_11_toolchain(self):
        content = self._read_workspace()
        assert re.search(r"python_register_toolchains|3\.11", content), (
            "Expected Python 3.11 toolchain registration"
        )

    def test_pip_dependencies(self):
        content = self._read_workspace()
        assert re.search(r"pip_parse|pip_install", content), (
            "Expected pip_parse or pip_install for external dependencies"
        )

    def test_requirements_lock(self):
        content = self._read_workspace()
        assert re.search(r"requirements.*lock|requirements_lock", content), (
            "Expected requirements_lock.txt reference"
        )


class TestSemanticBuildFiles:
    """Verify BUILD files define correct targets with dependencies."""

    def test_root_py_binary(self):
        path = os.path.join(EXAMPLE_DIR, "BUILD")
        with open(path, "r") as f:
            content = f.read()
        assert re.search(r"py_binary", content), (
            "Expected py_binary target in root BUILD"
        )
        assert re.search(r"//src:lib|//src", content), (
            "Expected dependency on //src:lib"
        )

    def test_src_py_library(self):
        path = os.path.join(EXAMPLE_DIR, "src", "BUILD")
        with open(path, "r") as f:
            content = f.read()
        assert re.search(r"py_library", content), (
            "Expected py_library target in src/BUILD"
        )

    def test_src_depends_on_utils(self):
        path = os.path.join(EXAMPLE_DIR, "src", "BUILD")
        with open(path, "r") as f:
            content = f.read()
        assert re.search(r"//src/utils:helpers|//src/utils", content), (
            "Expected dependency on //src/utils:helpers"
        )

    def test_src_depends_on_requests(self):
        path = os.path.join(EXAMPLE_DIR, "src", "BUILD")
        with open(path, "r") as f:
            content = f.read()
        assert re.search(r"requests", content), (
            "Expected dependency on external requests package"
        )

    def test_src_depends_on_pydantic(self):
        path = os.path.join(EXAMPLE_DIR, "src", "BUILD")
        with open(path, "r") as f:
            content = f.read()
        assert re.search(r"pydantic", content), (
            "Expected dependency on external pydantic package"
        )

    def test_utils_py_library(self):
        path = os.path.join(EXAMPLE_DIR, "src", "utils", "BUILD")
        with open(path, "r") as f:
            content = f.read()
        assert re.search(r"py_library", content), (
            "Expected py_library target in src/utils/BUILD"
        )

    def test_tests_py_test(self):
        path = os.path.join(EXAMPLE_DIR, "tests", "BUILD")
        with open(path, "r") as f:
            content = f.read()
        assert re.search(r"py_test", content), (
            "Expected py_test target in tests/BUILD"
        )

    def test_visibility_settings(self):
        all_builds = ""
        for sub in ["BUILD", "src/BUILD", "src/utils/BUILD", "tests/BUILD"]:
            path = os.path.join(EXAMPLE_DIR, sub)
            if os.path.isfile(path):
                with open(path, "r") as f:
                    all_builds += f.read()
        assert re.search(r"visibility", all_builds), (
            "Expected visibility settings on targets"
        )


class TestSemanticBazelrc:
    """Verify .bazelrc performance and caching configuration."""

    def _read_bazelrc(self):
        path = os.path.join(EXAMPLE_DIR, ".bazelrc")
        with open(path, "r") as f:
            return f.read()

    def test_remote_cache(self):
        content = self._read_bazelrc()
        assert re.search(r"remote_cache", content), (
            "Expected remote_cache configuration"
        )

    def test_remote_download_minimal(self):
        content = self._read_bazelrc()
        assert re.search(r"remote_download_outputs.*minimal|remote_download_minimal", content), (
            "Expected remote_download_outputs=minimal (build without the bytes)"
        )

    def test_sandbox_no_network(self):
        content = self._read_bazelrc()
        assert re.search(r"sandbox.*network.*false|sandbox_default_allow_network.*false", content), (
            "Expected sandbox_default_allow_network=false"
        )

    def test_jobs_auto(self):
        content = self._read_bazelrc()
        assert re.search(r"jobs.*auto|--jobs=auto", content), (
            "Expected --jobs=auto"
        )

    def test_ci_config(self):
        content = self._read_bazelrc()
        assert re.search(r"build:ci", content), (
            "Expected CI-specific configuration (build:ci)"
        )

    def test_test_output_errors(self):
        content = self._read_bazelrc()
        assert re.search(r"test_output.*errors|--test_output=errors", content), (
            "Expected test --test_output=errors"
        )

    def test_jvm_memory_startup(self):
        content = self._read_bazelrc()
        assert re.search(r"host_jvm_args.*Xmx|Xmx4g", content), (
            "Expected startup --host_jvm_args=-Xmx4g"
        )


class TestSemanticCodegenRule:
    """Verify custom Starlark codegen rule."""

    def _read_codegen(self):
        path = os.path.join(EXAMPLE_DIR, "rules", "codegen.bzl")
        with open(path, "r") as f:
            return f.read()

    def test_rule_implementation(self):
        content = self._read_codegen()
        assert re.search(r"rule\(|codegen_rule", content), (
            "Expected Starlark rule() definition"
        )

    def test_template_attr(self):
        content = self._read_codegen()
        assert re.search(r"template|\.py\.tmpl", content), (
            "Expected template file attribute"
        )

    def test_config_attr(self):
        content = self._read_codegen()
        assert re.search(r"config|json", content, re.IGNORECASE), (
            "Expected config (JSON) attribute"
        )

    def test_ctx_actions(self):
        content = self._read_codegen()
        assert re.search(r"ctx\.actions\.run|ctx\.actions", content), (
            "Expected ctx.actions.run for generating output"
        )

    def test_variable_substitution(self):
        content = self._read_codegen()
        assert re.search(r"\{\{|replace|substitut", content, re.IGNORECASE), (
            "Expected {{variable}} placeholder substitution logic"
        )


class TestFunctionalAppCode:
    """Verify application code is valid Python."""

    def test_app_py_syntax(self):
        path = os.path.join(EXAMPLE_DIR, "src", "app.py")
        with open(path, "r") as f:
            content = f.read()
        compile(content, path, "exec")

    def test_helpers_py_syntax(self):
        path = os.path.join(EXAMPLE_DIR, "src", "utils", "helpers.py")
        with open(path, "r") as f:
            content = f.read()
        compile(content, path, "exec")

    def test_test_app_syntax(self):
        path = os.path.join(EXAMPLE_DIR, "tests", "test_app.py")
        with open(path, "r") as f:
            content = f.read()
        compile(content, path, "exec")

    def test_app_uses_requests(self):
        path = os.path.join(EXAMPLE_DIR, "src", "app.py")
        with open(path, "r") as f:
            content = f.read()
        assert "requests" in content, "Expected requests import in app.py"

    def test_app_uses_pydantic(self):
        path = os.path.join(EXAMPLE_DIR, "src", "app.py")
        with open(path, "r") as f:
            content = f.read()
        assert "pydantic" in content, "Expected pydantic import in app.py"
