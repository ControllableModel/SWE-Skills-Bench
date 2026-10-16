"""
Tests for the similarity-search-patterns skill.

Validates that a hybrid search engine with HNSW/IVF index selection,
Reciprocal Rank Fusion reranking, and score normalization was
implemented for Milvus.

Repo: milvus (https://github.com/milvus-io/milvus)
"""

import os
import re
import subprocess

REPO_DIR = "/workspace/milvus"


class TestFilePathCheck:
    """Verify that all required files were created."""

    def test_hybrid_searcher_exists(self):
        path = os.path.join(REPO_DIR, "internal", "search", "hybrid_searcher.go")
        assert os.path.isfile(path), f"Expected hybrid_searcher.go at {path}"

    def test_index_selector_exists(self):
        path = os.path.join(REPO_DIR, "internal", "search", "index_selector.go")
        assert os.path.isfile(path), f"Expected index_selector.go at {path}"

    def test_reranker_exists(self):
        path = os.path.join(REPO_DIR, "internal", "search", "reranker.go")
        assert os.path.isfile(path), f"Expected reranker.go at {path}"

    def test_hybrid_searcher_test_exists(self):
        path = os.path.join(REPO_DIR, "internal", "search", "hybrid_searcher_test.go")
        assert os.path.isfile(path), f"Expected hybrid_searcher_test.go at {path}"

    def test_reranker_test_exists(self):
        path = os.path.join(REPO_DIR, "internal", "search", "reranker_test.go")
        assert os.path.isfile(path), f"Expected reranker_test.go at {path}"


class TestSemanticHybridSearcher:
    """Verify HybridSearcher structure and behavior."""

    def _read_hybrid(self):
        path = os.path.join(REPO_DIR, "internal", "search", "hybrid_searcher.go")
        with open(path, "r") as f:
            return f.read()

    def test_hybrid_searcher_struct(self):
        content = self._read_hybrid()
        assert re.search(r"type\s+HybridSearcher\s+struct", content), (
            "Expected HybridSearcher struct definition"
        )

    def test_dense_searcher_interface(self):
        content = self._read_hybrid()
        assert re.search(r"DenseSearcher|dense.*interface|Search.*vector", content, re.IGNORECASE), (
            "Expected DenseSearcher interface"
        )

    def test_sparse_searcher_interface(self):
        content = self._read_hybrid()
        assert re.search(r"SparseSearcher|sparse.*interface|Search.*query.*string", content, re.IGNORECASE), (
            "Expected SparseSearcher interface"
        )

    def test_alpha_weight_parameter(self):
        content = self._read_hybrid()
        assert re.search(r"alpha", content), (
            "Expected alpha weight parameter for dense/sparse balance"
        )

    def test_alpha_range_validation(self):
        """Alpha must be 0.0-1.0; error if out of range."""
        content = self._read_hybrid()
        assert re.search(r"0\.0|1\.0|range|invalid.*alpha|alpha.*error", content, re.IGNORECASE), (
            "Expected alpha range validation (0.0-1.0)"
        )

    def test_deduplication_by_id(self):
        content = self._read_hybrid()
        assert re.search(r"dedup|seen|unique|map\[|exist", content, re.IGNORECASE), (
            "Expected deduplication by ID when same result appears in both searchers"
        )

    def test_search_result_struct(self):
        content = self._read_hybrid()
        assert re.search(r"type\s+SearchResult\s+struct|SearchResult", content), (
            "Expected SearchResult struct definition"
        )


class TestSemanticIndexSelector:
    """Verify index recommendation logic."""

    def _read_selector(self):
        path = os.path.join(REPO_DIR, "internal", "search", "index_selector.go")
        with open(path, "r") as f:
            return f.read()

    def test_index_selector_struct_or_func(self):
        content = self._read_selector()
        assert re.search(r"IndexSelector|func.*recommend|func.*Select", content), (
            "Expected IndexSelector struct or recommend function"
        )

    def test_hnsw_recommendation(self):
        content = self._read_selector()
        assert re.search(r"HNSW", content), (
            "Expected HNSW index recommendation"
        )

    def test_ivf_flat_recommendation(self):
        content = self._read_selector()
        assert re.search(r"IVF_FLAT|IVFFlat", content), (
            "Expected IVF_FLAT index recommendation"
        )

    def test_ivf_pq_recommendation(self):
        content = self._read_selector()
        assert re.search(r"IVF_PQ|IVFPQ", content), (
            "Expected IVF_PQ index recommendation"
        )

    def test_flat_recommendation(self):
        content = self._read_selector()
        assert re.search(r"FLAT|FlatIndex|brute.force", content, re.IGNORECASE), (
            "Expected FLAT index recommendation for small datasets"
        )

    def test_dataset_profile_struct(self):
        content = self._read_selector()
        assert re.search(r"DatasetProfile|NumVectors|Dimension|RecallTarget", content), (
            "Expected DatasetProfile struct with dataset characteristics"
        )

    def test_index_recommendation_output(self):
        content = self._read_selector()
        assert re.search(r"IndexRecommendation|Recommendation|reasoning|Reasoning", content), (
            "Expected IndexRecommendation output struct"
        )

    def test_hnsw_default_parameters(self):
        """HNSW defaults: M=16, efConstruction=200."""
        content = self._read_selector()
        assert "16" in content and "200" in content, (
            "Expected HNSW default parameters M=16, efConstruction=200"
        )


class TestSemanticReranker:
    """Verify reranking logic."""

    def _read_reranker(self):
        path = os.path.join(REPO_DIR, "internal", "search", "reranker.go")
        with open(path, "r") as f:
            return f.read()

    def test_reranker_interface(self):
        content = self._read_reranker()
        assert re.search(r"type\s+Reranker\s+interface|Rerank", content), (
            "Expected Reranker interface with Rerank method"
        )

    def test_rrf_implementation(self):
        """Reciprocal Rank Fusion: score = sum(1/(k + rank))."""
        content = self._read_reranker()
        assert re.search(r"RRF|ReciprocalRankFusion|reciprocal", content, re.IGNORECASE), (
            "Expected RRF reranker implementation"
        )

    def test_rrf_k_constant(self):
        """RRF k defaults to 60."""
        content = self._read_reranker()
        assert "60" in content, "Expected RRF k constant default of 60"

    def test_weighted_score_reranker(self):
        content = self._read_reranker()
        assert re.search(r"WeightedScore|weighted.*score|WeightedReranker", content, re.IGNORECASE), (
            "Expected WeightedScoreReranker implementation"
        )

    def test_score_normalization(self):
        content = self._read_reranker()
        assert re.search(r"normalize|min.*max|normalization", content, re.IGNORECASE), (
            "Expected score normalization (min-max to [0,1])"
        )


class TestFunctionalGoSyntax:
    """Validate Go files compile correctly."""

    def test_go_vet_search_package(self):
        """Run go vet on the search package."""
        result = subprocess.run(
            ["go", "vet", "./internal/search/..."],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        # go vet may fail due to dependencies, but pure syntax issues are critical
        if result.returncode != 0:
            stderr = result.stderr.lower()
            assert "syntax error" not in stderr, (
                f"Go syntax errors found: {result.stderr[:500]}"
            )

    def test_package_declaration_hybrid(self):
        path = os.path.join(REPO_DIR, "internal", "search", "hybrid_searcher.go")
        with open(path, "r") as f:
            content = f.read()
        assert re.search(r"^package\s+search", content, re.MULTILINE), (
            "Expected 'package search' declaration in hybrid_searcher.go"
        )

    def test_package_declaration_reranker(self):
        path = os.path.join(REPO_DIR, "internal", "search", "reranker.go")
        with open(path, "r") as f:
            content = f.read()
        assert re.search(r"^package\s+search", content, re.MULTILINE), (
            "Expected 'package search' declaration in reranker.go"
        )

    def test_test_file_has_test_funcs(self):
        path = os.path.join(REPO_DIR, "internal", "search", "hybrid_searcher_test.go")
        with open(path, "r") as f:
            content = f.read()
        test_count = len(re.findall(r"func\s+Test\w+", content))
        assert test_count >= 3, (
            f"Expected at least 3 test functions in hybrid_searcher_test.go, found {test_count}"
        )

    def test_reranker_test_has_test_funcs(self):
        path = os.path.join(REPO_DIR, "internal", "search", "reranker_test.go")
        with open(path, "r") as f:
            content = f.read()
        test_count = len(re.findall(r"func\s+Test\w+", content))
        assert test_count >= 2, (
            f"Expected at least 2 test functions in reranker_test.go, found {test_count}"
        )
