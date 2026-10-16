"""
Test skill: python-performance-optimization
Verify that the Agent correctly implements a Profile Summary
subcommand for py-spy (Rust).
"""

import os
import re
import pytest


class TestPythonPerformanceOptimization:
    REPO_DIR = "/workspace/py-spy"

    # === File Path Checks ===

    def test_summary_rs_exists(self):
        """Verify summary.rs was created"""
        path = os.path.join(self.REPO_DIR, "src/summary.rs")
        assert os.path.exists(path), "src/summary.rs not found"

    def test_main_rs_exists(self):
        """Verify main.rs was modified"""
        path = os.path.join(self.REPO_DIR, "src/main.rs")
        assert os.path.exists(path), "src/main.rs not found"

    def test_config_rs_exists(self):
        """Verify config.rs was modified"""
        path = os.path.join(self.REPO_DIR, "src/config.rs")
        assert os.path.exists(path), "src/config.rs not found"

    def test_test_summary_rs_exists(self):
        """Verify test_summary.rs was created"""
        found = False
        for root, dirs, files in os.walk(self.REPO_DIR):
            for f in files:
                if f == "test_summary.rs" or (f.endswith(".rs") and "test_summary" in f):
                    found = True
                    break
            if found:
                break
        if not found:
            # Also check tests/ directory
            path = os.path.join(self.REPO_DIR, "tests/test_summary.rs")
            found = os.path.exists(path)
        assert found, "test_summary.rs not found"

    # === Semantic Checks: SummaryConfig structure ===

    def _load_summary_rs(self):
        path = os.path.join(self.REPO_DIR, "src/summary.rs")
        return open(path).read()

    def _load_config_rs(self):
        path = os.path.join(self.REPO_DIR, "src/config.rs")
        return open(path).read()

    def _load_main_rs(self):
        path = os.path.join(self.REPO_DIR, "src/main.rs")
        return open(path).read()

    def test_summary_config_struct(self):
        """Verify SummaryConfig struct is defined"""
        source = self._load_summary_rs()
        config_src = self._load_config_rs()
        combined = source + config_src
        assert "SummaryConfig" in combined or "summary" in combined.lower(), (
            "SummaryConfig struct not found"
        )

    def test_summary_config_has_filename(self):
        """Verify SummaryConfig has filename field"""
        source = self._load_summary_rs()
        config_src = self._load_config_rs()
        combined = source + config_src
        assert "filename" in combined or "file" in combined.lower(), (
            "filename field not found in SummaryConfig"
        )

    def test_summary_config_has_top_n(self):
        """Verify SummaryConfig has top_n field"""
        source = self._load_summary_rs()
        config_src = self._load_config_rs()
        combined = source + config_src
        assert "top_n" in combined or "top" in combined.lower(), (
            "top_n field not found"
        )

    def test_summary_config_has_min_pct(self):
        """Verify SummaryConfig has min_pct field"""
        source = self._load_summary_rs()
        config_src = self._load_config_rs()
        combined = source + config_src
        assert "min_pct" in combined or "min" in combined.lower(), (
            "min_pct field not found"
        )

    def test_summary_config_has_output_format(self):
        """Verify SummaryConfig has output_format field (Table/Json)"""
        source = self._load_summary_rs()
        config_src = self._load_config_rs()
        combined = source + config_src
        has_format = (
            "output_format" in combined
            or "OutputFormat" in combined
            or ("Table" in combined and "Json" in combined)
        )
        assert has_format, "output_format field not found"

    # === Semantic Checks: Aggregation ===

    def test_aggregation_by_function(self):
        """Verify aggregation by function name"""
        source = self._load_summary_rs()
        assert "function" in source.lower() or "func_name" in source, (
            "No aggregation by function name"
        )

    def test_aggregation_by_file_line(self):
        """Verify aggregation by file and line"""
        source = self._load_summary_rs()
        has_file = "file" in source.lower()
        has_line = "line" in source.lower()
        assert has_file and has_line, "No aggregation by file and line"

    # === Functional Checks ===

    def test_cumulative_vs_self_time(self):
        """Verify both cumulative and self time are computed"""
        source = self._load_summary_rs()
        has_cumulative = (
            "cumulative" in source.lower()
            or "total_time" in source
            or "total" in source.lower()
        )
        has_self = (
            "self_time" in source
            or "self" in source.lower()
            or "own_time" in source
        )
        assert has_cumulative and has_self, (
            "Missing cumulative or self time computation"
        )

    def test_json_output_format(self):
        """Verify JSON output format is supported"""
        source = self._load_summary_rs()
        assert "json" in source.lower() or "Json" in source, (
            "JSON output format not supported"
        )

    def test_table_output_format(self):
        """Verify Table output format is supported"""
        source = self._load_summary_rs()
        assert "table" in source.lower() or "Table" in source, (
            "Table output format not supported"
        )

    def test_main_rs_registers_summary_subcommand(self):
        """Verify main.rs routes to the summary subcommand"""
        source = self._load_main_rs()
        assert "summary" in source.lower(), (
            "main.rs does not reference summary subcommand"
        )

    def test_top_n_validation(self):
        """Verify top_n is validated (1-1000 range)"""
        source = self._load_summary_rs()
        config_src = self._load_config_rs()
        combined = source + config_src
        has_validation = (
            "1000" in combined
            or re.search(r'top_n.*[<>]', combined)
            or "range" in combined.lower()
            or "valid" in combined.lower()
        )
        assert has_validation, "No top_n range validation (1-1000)"

    def test_min_pct_validation(self):
        """Verify min_pct is validated (0-100 range)"""
        source = self._load_summary_rs()
        config_src = self._load_config_rs()
        combined = source + config_src
        has_validation = (
            "100" in combined
            or re.search(r'min_pct.*[<>]', combined)
            or "percent" in combined.lower()
        )
        assert has_validation, "No min_pct range validation (0-100)"

    def test_sorted_output(self):
        """Verify output is sorted (by time or percentage)"""
        source = self._load_summary_rs()
        has_sort = (
            "sort" in source.lower()
            or "order" in source.lower()
            or "reverse" in source.lower()
        )
        assert has_sort, "No sorting logic found for output"
