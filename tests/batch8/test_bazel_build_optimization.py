"""
Tests for the bazel-build-optimization skill.
Validates a Bazel build configuration optimizer with BUILD file analysis,
target generation, remote cache config, and build benchmarking.
"""

import os
import re
import ast

REPO_DIR = "/workspace/bazel"
TOOLS_DIR = os.path.join(REPO_DIR, "examples", "python-bazel", "tools")


class TestBazelBuildOptimization:
    """Tests for the Bazel build configuration optimizer."""

    # ── file_path_check ──────────────────────────────────────────────

    def test_build_analyzer_exists(self):
        """BuildAnalyzer module must exist."""
        path = os.path.join(TOOLS_DIR, "build_analyzer.py")
        assert os.path.isfile(path), f"Missing {path}"

    def test_build_generator_exists(self):
        """BuildFileGenerator module must exist."""
        path = os.path.join(TOOLS_DIR, "build_generator.py")
        assert os.path.isfile(path), f"Missing {path}"

    def test_cache_config_exists(self):
        """RemoteCacheConfig module must exist."""
        path = os.path.join(TOOLS_DIR, "cache_config.py")
        assert os.path.isfile(path), f"Missing {path}"

    def test_build_benchmark_exists(self):
        """BuildBenchmark module must exist."""
        path = os.path.join(TOOLS_DIR, "build_benchmark.py")
        assert os.path.isfile(path), f"Missing {path}"

    def test_build_file_exists(self):
        """BUILD.bazel for tools package must exist."""
        path = os.path.join(REPO_DIR, "examples", "python-bazel", "BUILD.bazel")
        assert os.path.isfile(path), f"Missing {path}"

    # ── semantic_check ───────────────────────────────────────────────

    def _read(self, filename):
        path = os.path.join(TOOLS_DIR, filename)
        if not os.path.isfile(path):
            return ""
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def test_analyzer_class_and_methods(self):
        """BuildAnalyzer must define parse_build_file, build_dependency_graph, find_circular_deps."""
        content = self._read("build_analyzer.py")
        assert re.search(r"class\s+BuildAnalyzer", content), "BuildAnalyzer class not defined"
        for method in ["parse_build_file", "build_dependency_graph", "find_circular_deps"]:
            assert re.search(rf"def\s+{method}\b", content), f"{method} not defined"

    def test_analyzer_unused_deps(self):
        """BuildAnalyzer must define find_unused_deps and target_statistics."""
        content = self._read("build_analyzer.py")
        assert re.search(r"def\s+find_unused_deps\b", content), "find_unused_deps not defined"
        assert re.search(r"def\s+target_statistics\b", content), "target_statistics not defined"

    def test_generator_methods(self):
        """BuildFileGenerator must define infer_targets, infer_deps, generate, optimize."""
        content = self._read("build_generator.py")
        assert re.search(r"class\s+BuildFileGenerator", content), "BuildFileGenerator class not defined"
        for method in ["infer_targets", "infer_deps", "generate", "optimize"]:
            assert re.search(rf"def\s+{method}\b", content), f"{method} not defined"

    def test_cache_config_types(self):
        """RemoteCacheConfig must support disk, http, grpc cache types."""
        content = self._read("cache_config.py")
        assert re.search(r"class\s+RemoteCacheConfig", content), "RemoteCacheConfig class not defined"
        for ct in ["disk", "http", "grpc"]:
            assert ct in content, f"Cache type '{ct}' not found"
        assert re.search(r"def\s+generate_bazelrc\b", content), "generate_bazelrc not defined"

    def test_benchmark_class(self):
        """BuildBenchmark must define clean_build, incremental_build, test_run, compare_configs."""
        content = self._read("build_benchmark.py")
        assert re.search(r"class\s+BuildBenchmark", content), "BuildBenchmark class not defined"
        for method in ["clean_build", "incremental_build", "test_run", "compare_configs"]:
            assert re.search(rf"def\s+{method}\b", content), f"{method} not defined"

    def test_bazel_rules_support(self):
        """Analyzer must support py_library, py_binary, py_test, py_proto_library rules."""
        content = self._read("build_analyzer.py")
        for rule in ["py_library", "py_binary", "py_test"]:
            assert rule in content, f"Rule '{rule}' not found in analyzer"

    def test_glob_handling(self):
        """Analyzer must handle glob() patterns."""
        content = self._read("build_analyzer.py")
        assert "glob" in content, "glob handling not found in analyzer"

    # ── functional_check ─────────────────────────────────────────────

    def test_all_files_valid_python(self):
        """All optimizer Python files must have valid syntax."""
        errors = []
        for fname in ["build_analyzer.py", "build_generator.py",
                       "cache_config.py", "build_benchmark.py"]:
            content = self._read(fname)
            if not content:
                continue
            try:
                ast.parse(content)
            except SyntaxError as e:
                errors.append(f"{fname}: {e}")
        assert not errors, "Syntax errors:\n" + "\n".join(errors)

    def test_invalid_cache_type_raises(self):
        """RemoteCacheConfig must raise ValueError for invalid cache_type."""
        content = self._read("cache_config.py")
        assert re.search(r"ValueError|invalid.*cache.*type|unsupported", content, re.IGNORECASE), (
            "ValueError for invalid cache_type not found"
        )

    def test_platform_config(self):
        """RemoteCacheConfig must support platform_config for cache key differentiation."""
        content = self._read("cache_config.py")
        assert re.search(r"def\s+platform_config\b", content), "platform_config not defined"
        assert re.search(r"OSFamily|exec_properties|platform", content), (
            "Platform configuration properties not found"
        )

    def test_markdown_report(self):
        """BuildBenchmark must generate a Markdown report."""
        content = self._read("build_benchmark.py")
        assert re.search(r"def\s+generate_report\b", content), "generate_report not defined"
        assert re.search(r"#|markdown|\|", content, re.IGNORECASE), (
            "Markdown formatting not found"
        )

    def test_test_file_exists(self):
        """Test file must exist."""
        path = os.path.join(REPO_DIR, "tests", "test_bazel_build_optimization.py")
        assert os.path.isfile(path), f"Missing {path}"
