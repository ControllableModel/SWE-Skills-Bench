"""
Test skill: similarity-search-patterns
Verify that the Agent correctly implements multi-metric similarity search
with reranking for Milvus.
"""

import os
import re
import subprocess
import pytest


class TestSimilaritySearchPatterns:
    REPO_DIR = "/workspace/milvus"

    # === File Path Checks ===

    def test_multi_metric_search_exists(self):
        """Verify multi_metric_search.go was created"""
        path = os.path.join(
            self.REPO_DIR,
            "internal/querynodev2/services/multi_metric_search.go",
        )
        assert os.path.exists(path), f"multi_metric_search.go not found at {path}"

    def test_reranker_exists(self):
        """Verify reranker.go was created"""
        path = os.path.join(
            self.REPO_DIR,
            "internal/querynodev2/services/reranker.go",
        )
        assert os.path.exists(path), f"reranker.go not found at {path}"

    def test_distance_metrics_exists(self):
        """Verify distance_metrics.go was created"""
        path = os.path.join(
            self.REPO_DIR,
            "pkg/util/distance/distance_metrics.go",
        )
        assert os.path.exists(path), f"distance_metrics.go not found at {path}"

    def test_distance_metrics_test_exists(self):
        """Verify distance_metrics_test.go was created"""
        path = os.path.join(
            self.REPO_DIR,
            "pkg/util/distance/distance_metrics_test.go",
        )
        assert os.path.exists(path), f"distance_metrics_test.go not found at {path}"

    def test_multi_metric_test_exists(self):
        """Verify multi_metric_search_test.go was created"""
        path = os.path.join(
            self.REPO_DIR,
            "internal/querynodev2/services/multi_metric_search_test.go",
        )
        assert os.path.exists(path), f"multi_metric_search_test.go not found"

    def test_reranker_test_exists(self):
        """Verify reranker_test.go was created"""
        path = os.path.join(
            self.REPO_DIR,
            "internal/querynodev2/services/reranker_test.go",
        )
        assert os.path.exists(path), f"reranker_test.go not found"

    # === Semantic Checks: Distance Metrics ===

    def test_cosine_similarity_defined(self):
        """Verify CosineSimilarity function is defined"""
        path = os.path.join(
            self.REPO_DIR, "pkg/util/distance/distance_metrics.go"
        )
        with open(path) as f:
            content = f.read()
        assert "CosineSimilarity" in content, (
            "CosineSimilarity function should be defined"
        )

    def test_l2_distance_defined(self):
        """Verify L2Distance function is defined"""
        path = os.path.join(
            self.REPO_DIR, "pkg/util/distance/distance_metrics.go"
        )
        with open(path) as f:
            content = f.read()
        assert "L2Distance" in content, "L2Distance function should be defined"

    def test_inner_product_defined(self):
        """Verify InnerProduct function is defined"""
        path = os.path.join(
            self.REPO_DIR, "pkg/util/distance/distance_metrics.go"
        )
        with open(path) as f:
            content = f.read()
        assert "InnerProduct" in content, (
            "InnerProduct function should be defined"
        )

    def test_manhattan_distance_defined(self):
        """Verify ManhattanDistance function is defined"""
        path = os.path.join(
            self.REPO_DIR, "pkg/util/distance/distance_metrics.go"
        )
        with open(path) as f:
            content = f.read()
        assert "ManhattanDistance" in content, (
            "ManhattanDistance function should be defined"
        )

    def test_normalize_scores_defined(self):
        """Verify NormalizeScores function is defined"""
        path = os.path.join(
            self.REPO_DIR, "pkg/util/distance/distance_metrics.go"
        )
        with open(path) as f:
            content = f.read()
        assert "NormalizeScores" in content, (
            "NormalizeScores function should be defined"
        )

    def test_distance_functions_return_errors(self):
        """Verify distance functions return error for invalid inputs"""
        path = os.path.join(
            self.REPO_DIR, "pkg/util/distance/distance_metrics.go"
        )
        with open(path) as f:
            content = f.read()
        assert "error" in content, "Functions should return error type"

    # === Semantic Checks: Multi-Metric Search ===

    def test_multi_metric_search_request_struct(self):
        """Verify MultiMetricSearchRequest struct is defined"""
        path = os.path.join(
            self.REPO_DIR,
            "internal/querynodev2/services/multi_metric_search.go",
        )
        with open(path) as f:
            content = f.read()
        assert "MultiMetricSearchRequest" in content, (
            "MultiMetricSearchRequest struct should be defined"
        )

    def test_search_result_struct(self):
        """Verify SearchResult struct is defined"""
        path = os.path.join(
            self.REPO_DIR,
            "internal/querynodev2/services/multi_metric_search.go",
        )
        with open(path) as f:
            content = f.read()
        assert "SearchResult" in content, (
            "SearchResult struct should be defined"
        )

    def test_execute_multi_metric_search_function(self):
        """Verify ExecuteMultiMetricSearch function is defined"""
        path = os.path.join(
            self.REPO_DIR,
            "internal/querynodev2/services/multi_metric_search.go",
        )
        with open(path) as f:
            content = f.read()
        assert "ExecuteMultiMetricSearch" in content, (
            "ExecuteMultiMetricSearch function should be defined"
        )

    def test_rrf_fusion_implemented(self):
        """Verify RRF fusion is implemented"""
        path = os.path.join(
            self.REPO_DIR,
            "internal/querynodev2/services/multi_metric_search.go",
        )
        with open(path) as f:
            content = f.read()
        assert "rrf" in content.lower() or "rank" in content.lower(), (
            "Should implement RRF fusion"
        )

    # === Semantic Checks: Reranker ===

    def test_rerank_by_score_defined(self):
        """Verify RerankByScore function is defined"""
        path = os.path.join(
            self.REPO_DIR,
            "internal/querynodev2/services/reranker.go",
        )
        with open(path) as f:
            content = f.read()
        assert "RerankByScore" in content, (
            "RerankByScore function should be defined"
        )

    def test_rerank_by_mmr_defined(self):
        """Verify RerankByMMR function is defined"""
        path = os.path.join(
            self.REPO_DIR,
            "internal/querynodev2/services/reranker.go",
        )
        with open(path) as f:
            content = f.read()
        assert "RerankByMMR" in content, (
            "RerankByMMR function should be defined"
        )

    def test_deduplicate_defined(self):
        """Verify Deduplicate function is defined"""
        path = os.path.join(
            self.REPO_DIR,
            "internal/querynodev2/services/reranker.go",
        )
        with open(path) as f:
            content = f.read()
        assert "Deduplicate" in content, (
            "Deduplicate function should be defined"
        )

    def test_mmr_uses_lambda(self):
        """Verify MMR uses lambda parameter"""
        path = os.path.join(
            self.REPO_DIR,
            "internal/querynodev2/services/reranker.go",
        )
        with open(path) as f:
            content = f.read()
        assert "lambda" in content.lower(), (
            "RerankByMMR should use lambda parameter"
        )

    # === Functional Checks ===

    def test_go_files_have_package(self):
        """Verify Go files have proper package declarations"""
        files = [
            "pkg/util/distance/distance_metrics.go",
            "internal/querynodev2/services/multi_metric_search.go",
            "internal/querynodev2/services/reranker.go",
        ]
        for rel_path in files:
            path = os.path.join(self.REPO_DIR, rel_path)
            with open(path) as f:
                content = f.read()
            assert content.startswith("package "), (
                f"{rel_path} should start with package declaration"
            )

    def test_go_vet_distance(self):
        """Verify distance_metrics.go passes go vet"""
        result = subprocess.run(
            ["go", "vet", "./pkg/util/distance/..."],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, (
            f"go vet failed:\n{result.stderr}"
        )

    def test_distance_tests_pass(self):
        """Verify distance metric tests pass"""
        result = subprocess.run(
            ["go", "test", "./pkg/util/distance/", "-v", "-run", "TestDistance"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, (
            f"Distance tests failed:\n{result.stdout}\n{result.stderr}"
        )
