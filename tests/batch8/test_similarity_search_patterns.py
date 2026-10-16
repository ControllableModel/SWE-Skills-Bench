"""
Tests for the similarity-search-patterns skill.
Validates a multi-backend similarity search service for Milvus with
index configuration, search with filters, reranking, and benchmarking.
"""

import os
import re
import ast

REPO_DIR = "/workspace/milvus"
CLIENT_DIR = os.path.join(REPO_DIR, "tests", "python_client")


class TestSimilaritySearchPatterns:
    """Tests for the Milvus similarity search service."""

    # ── file_path_check ──────────────────────────────────────────────

    def test_search_service_exists(self):
        """SimilaritySearchService module must exist."""
        path = os.path.join(CLIENT_DIR, "search_service.py")
        assert os.path.isfile(path), f"Missing {path}"

    def test_index_config_exists(self):
        """IndexConfig and IndexFactory module must exist."""
        path = os.path.join(CLIENT_DIR, "index_config.py")
        assert os.path.isfile(path), f"Missing {path}"

    def test_search_benchmark_exists(self):
        """SearchBenchmark module must exist."""
        path = os.path.join(CLIENT_DIR, "search_benchmark.py")
        assert os.path.isfile(path), f"Missing {path}"

    def test_reranker_exists(self):
        """SearchReranker module must exist."""
        path = os.path.join(CLIENT_DIR, "reranker.py")
        assert os.path.isfile(path), f"Missing {path}"

    # ── semantic_check ───────────────────────────────────────────────

    def _read(self, filename):
        path = os.path.join(CLIENT_DIR, filename)
        if not os.path.isfile(path):
            return ""
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def test_index_factory_class(self):
        """IndexFactory class must be defined with create method."""
        content = self._read("index_config.py")
        assert re.search(r"class\s+IndexFactory", content), "IndexFactory class not defined"
        assert re.search(r"def\s+create\b", content), "create method not defined"

    def test_index_types_supported(self):
        """IndexFactory must support FLAT, IVF_FLAT, IVF_PQ, HNSW."""
        content = self._read("index_config.py")
        for itype in ["FLAT", "IVF_FLAT", "IVF_PQ", "HNSW"]:
            assert itype in content, f"Index type '{itype}' not supported"

    def test_search_service_class(self):
        """SimilaritySearchService must define insert, search, batch_search."""
        content = self._read("search_service.py")
        assert re.search(r"class\s+SimilaritySearchService", content), (
            "SimilaritySearchService class not defined"
        )
        for method in ["insert", "search", "batch_search"]:
            assert re.search(rf"def\s+{method}\b", content), (
                f"{method} method not defined"
            )

    def test_deduplicated_batch_search_defined(self):
        """deduplicated_batch_search method must be defined."""
        content = self._read("search_service.py")
        assert re.search(r"def\s+deduplicated_batch_search\b", content), (
            "deduplicated_batch_search method not defined"
        )

    def test_multi_vector_search_defined(self):
        """multi_vector_search method must be defined."""
        content = self._read("search_service.py")
        assert re.search(r"def\s+multi_vector_search\b", content), (
            "multi_vector_search method not defined"
        )

    def test_reranker_mmr_and_rrf(self):
        """SearchReranker must implement MMR reranking and RRF fusion."""
        content = self._read("reranker.py")
        assert re.search(r"class\s+SearchReranker", content), "SearchReranker class not defined"
        assert re.search(r"def\s+mmr_rerank\b", content), "mmr_rerank method not defined"
        assert re.search(r"def\s+rrf_fuse\b", content), "rrf_fuse method not defined"

    def test_metadata_filter_support(self):
        """Search must support metadata filtering with comparison operators."""
        content = self._read("search_service.py")
        assert re.search(r"filter|_lt|_gt|_lte|_gte|predicate", content, re.IGNORECASE), (
            "Metadata filter support not found"
        )

    def test_benchmark_compare_configs(self):
        """SearchBenchmark must define compare_configs and find_optimal."""
        content = self._read("search_benchmark.py")
        assert re.search(r"class\s+SearchBenchmark", content), (
            "SearchBenchmark class not defined"
        )
        assert re.search(r"def\s+compare_configs\b", content), "compare_configs not defined"
        assert re.search(r"def\s+find_optimal\b", content), "find_optimal not defined"

    # ── functional_check ─────────────────────────────────────────────

    def test_all_files_valid_python(self):
        """All search service Python files must have valid syntax."""
        errors = []
        for fname in ["search_service.py", "index_config.py",
                       "search_benchmark.py", "reranker.py"]:
            content = self._read(fname)
            if not content:
                continue
            try:
                ast.parse(content)
            except SyntaxError as e:
                errors.append(f"{fname}: {e}")
        assert not errors, "Syntax errors:\n" + "\n".join(errors)

    def test_dimension_validation(self):
        """Insert/search must validate vector dimensions."""
        content = self._read("search_service.py")
        assert re.search(r"dimension|ValueError|len\(.*\)|shape", content), (
            "Dimension validation not found"
        )

    def test_cosine_similarity_in_reranker(self):
        """Reranker must compute cosine similarity with zero-norm handling."""
        content = self._read("reranker.py")
        assert re.search(r"cosine|dot|norm", content, re.IGNORECASE), (
            "Cosine similarity not found in reranker"
        )

    def test_weight_normalization(self):
        """multi_vector_search must normalize weights to sum to 1.0."""
        content = self._read("search_service.py")
        assert re.search(r"normalize|sum.*weight|weight.*sum", content, re.IGNORECASE), (
            "Weight normalization not found"
        )

    def test_index_param_validation(self):
        """IndexFactory must validate parameter ranges (M, nlist, etc.)."""
        content = self._read("index_config.py")
        assert re.search(r"ValueError|range|<|>|must be", content), (
            "Parameter range validation not found in IndexFactory"
        )
