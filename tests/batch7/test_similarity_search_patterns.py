"""
Test skill: similarity-search-patterns
Verify that the Agent implements a Filtered Vector Search Operator with Dynamic
Pruning in Milvus — SelectivityEstimator, FilteredSearchOperator, and
CosineDistance metric.
"""

import os
import re
import subprocess
import pytest


class TestSimilaritySearchPatterns:
    REPO_DIR = "/workspace/milvus"
    SEGMENTS = "internal/querynodev2/segments"

    # ────────────────── helpers ──────────────────

    def _read(self, rel_path):
        fpath = os.path.join(self.REPO_DIR, rel_path)
        with open(fpath, "r") as f:
            return f.read()

    def _exists(self, rel_path):
        return os.path.isfile(os.path.join(self.REPO_DIR, rel_path))

    # === File Path Checks ===

    def test_filtered_search_exists(self):
        """filtered_search.go must exist"""
        assert self._exists(f"{self.SEGMENTS}/filtered_search.go")

    def test_selectivity_estimator_exists(self):
        """selectivity_estimator.go must exist"""
        assert self._exists(f"{self.SEGMENTS}/selectivity_estimator.go")

    def test_filtered_search_test_exists(self):
        """filtered_search_test.go must exist"""
        assert self._exists(f"{self.SEGMENTS}/filtered_search_test.go")

    def test_selectivity_estimator_test_exists(self):
        """selectivity_estimator_test.go must exist"""
        assert self._exists(f"{self.SEGMENTS}/selectivity_estimator_test.go")

    def test_metrics_go_exists(self):
        """pkg/util/similarity/metrics.go must exist"""
        assert self._exists("pkg/util/similarity/metrics.go")

    # === Semantic Checks — SelectivityEstimator ===

    def test_selectivity_estimator_struct(self):
        """SelectivityEstimator struct must be defined"""
        src = self._read(f"{self.SEGMENTS}/selectivity_estimator.go")
        assert re.search(r'type\s+SelectivityEstimator\s+struct', src), (
            "SelectivityEstimator struct not found"
        )

    def test_segment_stats_struct(self):
        """SegmentStats struct must be defined"""
        src = self._read(f"{self.SEGMENTS}/selectivity_estimator.go")
        assert re.search(r'type\s+SegmentStats\s+struct', src), (
            "SegmentStats struct not found"
        )

    def test_field_stats_struct(self):
        """FieldStats struct must be defined"""
        src = self._read(f"{self.SEGMENTS}/selectivity_estimator.go")
        assert re.search(r'type\s+FieldStats\s+struct', src), (
            "FieldStats struct not found"
        )

    def test_estimate_selectivity_method(self):
        """EstimateSelectivity method must be defined"""
        src = self._read(f"{self.SEGMENTS}/selectivity_estimator.go")
        assert "EstimateSelectivity" in src, (
            "EstimateSelectivity method not found"
        )

    # === Semantic Checks — FilteredSearchOperator ===

    def test_filtered_search_operator_struct(self):
        """FilteredSearchOperator struct must be defined"""
        src = self._read(f"{self.SEGMENTS}/filtered_search.go")
        assert re.search(r'type\s+FilteredSearchOperator\s+struct', src), (
            "FilteredSearchOperator struct not found"
        )

    def test_search_request_struct(self):
        """SearchRequest struct must be defined"""
        src = self._read(f"{self.SEGMENTS}/filtered_search.go")
        assert re.search(r'type\s+SearchRequest\s+struct', src), (
            "SearchRequest struct not found"
        )

    def test_search_result_struct(self):
        """SearchResult struct must be defined with Strategy field"""
        src = self._read(f"{self.SEGMENTS}/filtered_search.go")
        assert re.search(r'type\s+SearchResult\s+struct', src), (
            "SearchResult struct not found"
        )
        assert "Strategy" in src, "SearchResult missing Strategy field"

    def test_search_method(self):
        """Search method must be defined"""
        src = self._read(f"{self.SEGMENTS}/filtered_search.go")
        assert re.search(r'func\s+\(.*FilteredSearchOperator\)\s+Search\b', src), (
            "Search method not found on FilteredSearchOperator"
        )

    def test_pre_filter_strategy(self):
        """Must implement pre_filter strategy"""
        src = self._read(f"{self.SEGMENTS}/filtered_search.go")
        assert "pre_filter" in src, "pre_filter strategy not found"

    def test_post_filter_strategy(self):
        """Must implement post_filter strategy"""
        src = self._read(f"{self.SEGMENTS}/filtered_search.go")
        assert "post_filter" in src, "post_filter strategy not found"

    def test_pre_filter_threshold(self):
        """preFilterThreshold must be configurable"""
        src = self._read(f"{self.SEGMENTS}/filtered_search.go")
        assert "preFilterThreshold" in src or "PreFilterThreshold" in src, (
            "preFilterThreshold not found"
        )

    def test_post_filter_multiplier(self):
        """postFilterMultiplier must be configurable"""
        src = self._read(f"{self.SEGMENTS}/filtered_search.go")
        assert "postFilterMultiplier" in src or "PostFilterMultiplier" in src, (
            "postFilterMultiplier not found"
        )

    # === Semantic Checks — Filter Expressions ===

    def test_filter_expression_interface(self):
        """FilterExpression interface must be defined"""
        src = self._read(f"{self.SEGMENTS}/filtered_search.go")
        assert "FilterExpression" in src, "FilterExpression interface not found"

    def test_compare_expr(self):
        """CompareExpr type must be defined"""
        src = self._read(f"{self.SEGMENTS}/filtered_search.go")
        assert "CompareExpr" in src, "CompareExpr type not found"

    def test_and_or_not_exprs(self):
        """AndExpr, OrExpr, NotExpr must be defined"""
        src = self._read(f"{self.SEGMENTS}/filtered_search.go")
        for expr_type in ["AndExpr", "OrExpr", "NotExpr"]:
            assert expr_type in src, f"{expr_type} type not found"

    # === Semantic Checks — CosineDistance ===

    def test_cosine_distance_function(self):
        """CosineDistance function must be defined in metrics.go"""
        src = self._read("pkg/util/similarity/metrics.go")
        assert re.search(r'func\s+CosineDistance\b', src), (
            "CosineDistance function not found in metrics.go"
        )

    # === Functional Checks ===

    def test_go_build(self):
        """Go packages must build without errors"""
        result = subprocess.run(
            ["go", "build", f"./{self.SEGMENTS}/..."],
            capture_output=True, text=True, cwd=self.REPO_DIR, timeout=120,
        )
        assert result.returncode == 0, (
            f"go build failed:\n{result.stdout}\n{result.stderr}"
        )

    def test_metrics_build(self):
        """metrics package must build without errors"""
        result = subprocess.run(
            ["go", "build", "./pkg/util/similarity/..."],
            capture_output=True, text=True, cwd=self.REPO_DIR, timeout=120,
        )
        assert result.returncode == 0, (
            f"go build failed:\n{result.stdout}\n{result.stderr}"
        )

    def test_filtered_search_tests_pass(self):
        """filtered_search_test.go must pass"""
        result = subprocess.run(
            ["go", "test", "-v", "-run", "TestFiltered",
             f"./{self.SEGMENTS}/..."],
            capture_output=True, text=True, cwd=self.REPO_DIR, timeout=120,
        )
        assert result.returncode == 0, (
            f"Tests failed:\n{result.stdout}\n{result.stderr}"
        )

    def test_selectivity_estimator_tests_pass(self):
        """selectivity_estimator_test.go must pass"""
        result = subprocess.run(
            ["go", "test", "-v", "-run", "TestSelectivity",
             f"./{self.SEGMENTS}/..."],
            capture_output=True, text=True, cwd=self.REPO_DIR, timeout=120,
        )
        assert result.returncode == 0, (
            f"Tests failed:\n{result.stdout}\n{result.stderr}"
        )
