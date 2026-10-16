"""
Test skill: python-performance-optimization
Verify that the Agent builds a profile aggregator, flame graph filter,
and summary report tool that processes py-spy speedscope JSON output.
"""

import os
import re
import ast
import json
import subprocess
import pytest


class TestPythonPerformanceOptimization:
    REPO_DIR = "/workspace/py-spy"

    # === File Path Checks ===

    def test_profile_aggregator_exists(self):
        assert os.path.exists(
            os.path.join(self.REPO_DIR, "scripts/profile_aggregator.py")
        )

    def test_flamegraph_filter_exists(self):
        assert os.path.exists(
            os.path.join(self.REPO_DIR, "scripts/flamegraph_filter.py")
        )

    def test_profile_report_exists(self):
        assert os.path.exists(
            os.path.join(self.REPO_DIR, "scripts/profile_report.py")
        )

    def test_aggregator_tests_exist(self):
        assert os.path.exists(
            os.path.join(self.REPO_DIR, "tests/test_profile_aggregator.py")
        )

    def test_filter_tests_exist(self):
        assert os.path.exists(
            os.path.join(self.REPO_DIR, "tests/test_flamegraph_filter.py")
        )

    # === Semantic Checks ===

    def test_aggregator_reads_speedscope_json(self):
        """Aggregator should read speedscope JSON format"""
        path = os.path.join(self.REPO_DIR, "scripts/profile_aggregator.py")
        with open(path) as f:
            content = f.read()
        assert "speedscope" in content.lower() or "json" in content.lower(), (
            "Should read speedscope JSON format"
        )

    def test_aggregator_merges_samples(self):
        """Aggregator should merge/sum sample counts"""
        path = os.path.join(self.REPO_DIR, "scripts/profile_aggregator.py")
        with open(path) as f:
            content = f.read()
        content_lower = content.lower()
        assert "merge" in content_lower or "sum" in content_lower or "aggregate" in content_lower, (
            "Should merge sample counts across files"
        )

    def test_filter_supports_module_flag(self):
        """Filter should support --module flag"""
        path = os.path.join(self.REPO_DIR, "scripts/flamegraph_filter.py")
        with open(path) as f:
            content = f.read()
        assert "--module" in content or "module" in content, (
            "Should support --module filter flag"
        )

    def test_filter_supports_function_regex(self):
        """Filter should support --function regex flag"""
        path = os.path.join(self.REPO_DIR, "scripts/flamegraph_filter.py")
        with open(path) as f:
            content = f.read()
        assert "--function" in content or "function" in content, (
            "Should support --function filter"
        )
        assert "re" in content or "regex" in content.lower() or "pattern" in content, (
            "Should support regex matching"
        )

    def test_filter_supports_min_samples(self):
        """Filter should support --min-samples flag"""
        path = os.path.join(self.REPO_DIR, "scripts/flamegraph_filter.py")
        with open(path) as f:
            content = f.read()
        assert "min" in content.lower() and "sample" in content.lower(), (
            "Should support --min-samples filter"
        )

    def test_filter_supports_exclude_module(self):
        """Filter should support --exclude-module flag"""
        path = os.path.join(self.REPO_DIR, "scripts/flamegraph_filter.py")
        with open(path) as f:
            content = f.read()
        assert "exclude" in content.lower(), "Should support --exclude-module"

    def test_report_has_top_functions(self):
        """Report should show top N hottest functions"""
        path = os.path.join(self.REPO_DIR, "scripts/profile_report.py")
        with open(path) as f:
            content = f.read()
        assert "top" in content.lower() or "hottest" in content.lower(), (
            "Should show top hottest functions"
        )

    def test_report_has_module_breakdown(self):
        """Report should include per-module breakdown"""
        path = os.path.join(self.REPO_DIR, "scripts/profile_report.py")
        with open(path) as f:
            content = f.read()
        assert "module" in content.lower(), "Should have per-module breakdown"

    def test_report_supports_json_format(self):
        """Report should support --format json output"""
        path = os.path.join(self.REPO_DIR, "scripts/profile_report.py")
        with open(path) as f:
            content = f.read()
        assert "json" in content.lower(), "Should support JSON output format"
        assert "--format" in content or "format" in content, "Should support --format flag"

    def test_report_has_deepest_call_chain(self):
        """Report should include deepest call chain"""
        path = os.path.join(self.REPO_DIR, "scripts/profile_report.py")
        with open(path) as f:
            content = f.read()
        content_lower = content.lower()
        assert "deep" in content_lower or "chain" in content_lower or "longest" in content_lower, (
            "Should show deepest call chain"
        )

    def test_error_handling_for_missing_files(self):
        """Scripts should handle missing input files"""
        path = os.path.join(self.REPO_DIR, "scripts/profile_aggregator.py")
        with open(path) as f:
            content = f.read()
        assert "FileNotFoundError" in content or "exist" in content or "os.path" in content, (
            "Should handle missing input files"
        )

    # === Functional Checks ===

    def test_all_python_files_parse(self):
        """All Python scripts should parse without syntax errors"""
        scripts = [
            "scripts/profile_aggregator.py",
            "scripts/flamegraph_filter.py",
            "scripts/profile_report.py",
            "tests/test_profile_aggregator.py",
            "tests/test_flamegraph_filter.py",
        ]
        for s in scripts:
            path = os.path.join(self.REPO_DIR, s)
            with open(path) as f:
                source = f.read()
            try:
                ast.parse(source)
            except SyntaxError as e:
                pytest.fail(f"{s} syntax error: {e}")

    def test_aggregator_help(self):
        """Aggregator should support --help"""
        path = os.path.join(self.REPO_DIR, "scripts/profile_aggregator.py")
        result = subprocess.run(
            ["python", path, "--help"],
            capture_output=True, text=True, timeout=15
        )
        assert result.returncode == 0, f"--help failed: {result.stderr}"

    def test_filter_help(self):
        """Filter should support --help"""
        path = os.path.join(self.REPO_DIR, "scripts/flamegraph_filter.py")
        result = subprocess.run(
            ["python", path, "--help"],
            capture_output=True, text=True, timeout=15
        )
        assert result.returncode == 0, f"--help failed: {result.stderr}"

    def test_report_help(self):
        """Report should support --help"""
        path = os.path.join(self.REPO_DIR, "scripts/profile_report.py")
        result = subprocess.run(
            ["python", path, "--help"],
            capture_output=True, text=True, timeout=15
        )
        assert result.returncode == 0, f"--help failed: {result.stderr}"
