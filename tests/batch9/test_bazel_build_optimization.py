"""
Test skill: bazel-build-optimization
Verify that the Agent creates BUILD files, WORKSPACE.bazel, .bazelrc,
and custom macros for Bazel build optimization.
"""

import os
import re
import subprocess
import pytest


class TestBazelBuildOptimization:
    REPO_DIR = "/workspace/bazel"

    # === File Path Checks ===

    def test_workspace_bazel_exists(self):
        """Verify WORKSPACE or WORKSPACE.bazel exists"""
        ws = os.path.isfile(os.path.join(self.REPO_DIR, "WORKSPACE.bazel")) or \
             os.path.isfile(os.path.join(self.REPO_DIR, "WORKSPACE"))
        assert ws, "WORKSPACE.bazel or WORKSPACE not found"

    def test_bazelrc_exists(self):
        """Verify .bazelrc exists"""
        assert os.path.isfile(os.path.join(self.REPO_DIR, ".bazelrc")), ".bazelrc not found"

    # === Semantic Checks ===

    def test_build_files_exist(self):
        """Verify BUILD or BUILD.bazel files exist"""
        found = 0
        for root, dirs, files in os.walk(self.REPO_DIR):
            if ".git" in root:
                continue
            for f in files:
                if f in ("BUILD", "BUILD.bazel"):
                    found += 1
        assert found >= 1, "No BUILD files found"

    def test_bazelrc_has_optimization_flags(self):
        """Verify .bazelrc contains optimization flags"""
        bazelrc_path = os.path.join(self.REPO_DIR, ".bazelrc")
        with open(bazelrc_path) as fh:
            content = fh.read()
        content_lower = content.lower()
        has_opt = (
            "--remote_cache" in content
            or "--disk_cache" in content
            or "--jobs" in content
            or "--compilation_mode" in content
            or "build:" in content
            or "--config" in content
        )
        assert has_opt, ".bazelrc missing optimization flags"

    def test_build_rules_defined(self):
        """Verify BUILD files define rules"""
        build_content = self._collect_build_content()
        has_rules = (
            "cc_library" in build_content
            or "cc_binary" in build_content
            or "java_library" in build_content
            or "java_binary" in build_content
            or "py_library" in build_content
            or "py_binary" in build_content
            or "genrule" in build_content
            or "filegroup" in build_content
        )
        assert has_rules, "BUILD files missing build rules"

    def test_custom_macros_or_rules_defined(self):
        """Verify custom Bazel macros or rules are defined"""
        found = False
        for root, dirs, files in os.walk(self.REPO_DIR):
            if ".git" in root:
                continue
            for f in files:
                if f.endswith(".bzl"):
                    found = True
                    break
            if found:
                break
        assert found, "No .bzl custom macro/rule files found"

    def test_bzl_files_use_rule_or_macro(self):
        """Verify .bzl files define rules or macros"""
        bzl_content = ""
        for root, dirs, files in os.walk(self.REPO_DIR):
            if ".git" in root:
                continue
            for f in files:
                if f.endswith(".bzl"):
                    fpath = os.path.join(root, f)
                    try:
                        with open(fpath) as fh:
                            bzl_content += fh.read() + "\n"
                    except (UnicodeDecodeError, PermissionError):
                        continue
        assert "def " in bzl_content or "rule(" in bzl_content, ".bzl files missing macro/rule definitions"

    # === Functional Checks ===

    def test_build_files_valid_starlark(self):
        """Verify BUILD files use valid Starlark syntax"""
        build_content = self._collect_build_content()
        assert len(build_content) > 0, "Empty BUILD files"
        parens = build_content.count('(') - build_content.count(')')
        assert parens == 0, f"Unbalanced parentheses in BUILD files: diff={parens}"

    def test_workspace_has_external_deps(self):
        """Verify WORKSPACE defines external dependencies"""
        ws_path = os.path.join(self.REPO_DIR, "WORKSPACE.bazel")
        if not os.path.isfile(ws_path):
            ws_path = os.path.join(self.REPO_DIR, "WORKSPACE")
        with open(ws_path) as fh:
            content = fh.read()
        has_deps = (
            "http_archive" in content
            or "git_repository" in content
            or "maven_jar" in content
            or "load(" in content
        )
        assert has_deps, "WORKSPACE missing external dependency declarations"

    def test_bazelrc_remote_or_local_cache(self):
        """Verify .bazelrc configures caching (remote or disk)"""
        bazelrc_path = os.path.join(self.REPO_DIR, ".bazelrc")
        with open(bazelrc_path) as fh:
            content = fh.read()
        has_cache = "cache" in content.lower()
        assert has_cache, ".bazelrc missing cache configuration"

    def test_visibility_specified(self):
        """Verify BUILD files specify visibility"""
        build_content = self._collect_build_content()
        has_vis = "visibility" in build_content
        assert has_vis, "BUILD files missing visibility declarations"

    def _collect_build_content(self):
        all_content = ""
        for root, dirs, files in os.walk(self.REPO_DIR):
            if ".git" in root:
                continue
            for f in files:
                if f in ("BUILD", "BUILD.bazel"):
                    fpath = os.path.join(root, f)
                    try:
                        with open(fpath) as fh:
                            all_content += fh.read() + "\n"
                    except (UnicodeDecodeError, PermissionError):
                        continue
        return all_content
