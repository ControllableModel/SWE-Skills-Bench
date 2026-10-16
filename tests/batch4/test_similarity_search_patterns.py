"""
Tests for skill: similarity-search-patterns
Repo: milvus-io/milvus
Image: zhangyiiiiii/swe-skills-bench-golang
Task: Implement a similarity search engine with multi-index support,
      auto-index selection, and batch search for Milvus.
"""

import ast
import os
import re
import subprocess

import pytest

REPO_DIR = "/workspace/milvus"
ENGINE_DIR = os.path.join(REPO_DIR, "scripts", "similarity_engine")

ENGINE_FILE = os.path.join(ENGINE_DIR, "engine.py")
ADVISOR_FILE = os.path.join(ENGINE_DIR, "index_advisor.py")
BATCH_FILE = os.path.join(ENGINE_DIR, "batch_search.py")
INIT_FILE = os.path.join(ENGINE_DIR, "__init__.py")
TEST_FILE = os.path.join(REPO_DIR, "tests", "python", "test_similarity_engine.py")


# ---------------------------------------------------------------------------
# Layer 1 — file_path_check
# ---------------------------------------------------------------------------

class TestFilePathCheck:
    """Verify all required files were created."""

    def test_engine_file_exists(self):
        assert os.path.isfile(ENGINE_FILE), f"Expected {ENGINE_FILE}"

    def test_advisor_file_exists(self):
        assert os.path.isfile(ADVISOR_FILE), f"Expected {ADVISOR_FILE}"

    def test_batch_file_exists(self):
        assert os.path.isfile(BATCH_FILE), f"Expected {BATCH_FILE}"

    def test_init_file_exists(self):
        assert os.path.isfile(INIT_FILE), f"Expected {INIT_FILE}"

    def test_test_file_exists(self):
        assert os.path.isfile(TEST_FILE), f"Expected {TEST_FILE}"


# ---------------------------------------------------------------------------
# Layer 2 — semantic_check
# ---------------------------------------------------------------------------

class TestSemanticEngine:
    """Verify SimilarityEngine class."""

    @pytest.fixture(autouse=True)
    def _load_source(self):
        with open(ENGINE_FILE, "r", encoding="utf-8") as f:
            self.src = f.read()
        self.tree = ast.parse(self.src)

    def test_class_defined(self):
        classes = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.ClassDef)]
        assert "SimilarityEngine" in classes, (
            f"Expected SimilarityEngine class; found: {classes}"
        )

    def test_insert_method(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "insert" in funcs, "Expected insert() method"

    def test_search_method(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "search" in funcs, "Expected search() method"

    def test_hybrid_search_method(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "hybrid_search" in funcs, "Expected hybrid_search() method"

    def test_delete_method(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "delete" in funcs, "Expected delete() method"

    def test_count_method(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "count" in funcs, "Expected count() method"

    def test_metric_types(self):
        """Must support L2, IP, and COSINE metrics."""
        for metric in ["L2", "IP", "COSINE"]:
            assert metric in self.src, f"Expected metric type '{metric}'"

    def test_index_types(self):
        """Must support HNSW, FLAT, IVF_PQ index types."""
        for idx_type in ["HNSW", "FLAT", "IVF_PQ"]:
            assert idx_type in self.src, f"Expected index type '{idx_type}'"

    def test_dimension_validation(self):
        """Must validate vector dimensions."""
        assert "ValueError" in self.src, "Expected ValueError for dimension mismatch"


class TestSemanticIndexAdvisor:
    """Verify IndexAdvisor class."""

    @pytest.fixture(autouse=True)
    def _load_source(self):
        with open(ADVISOR_FILE, "r", encoding="utf-8") as f:
            self.src = f.read()
        self.tree = ast.parse(self.src)

    def test_class_defined(self):
        classes = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.ClassDef)]
        assert "IndexAdvisor" in classes, (
            f"Expected IndexAdvisor class; found: {classes}"
        )

    def test_recommend_method(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "recommend" in funcs, "Expected recommend() method"

    def test_threshold_based_selection(self):
        """Selection logic should reference thresholds (10000, 1000000)."""
        assert "10000" in self.src or "10_000" in self.src, (
            "Expected 10,000 vector threshold"
        )

    def test_memory_estimation(self):
        """Must estimate memory for index types."""
        assert "memory" in self.src.lower() or "estimated_memory" in self.src, (
            "Expected memory estimation in recommendations"
        )

    def test_memory_budget_fallback(self):
        """If memory_budget_mb is provided and HNSW exceeds it, fall back to IVF_PQ."""
        has_budget = "memory_budget" in self.src
        assert has_budget, "Expected memory_budget_mb parameter"


class TestSemanticBatchSearcher:
    """Verify BatchSearcher class."""

    @pytest.fixture(autouse=True)
    def _load_source(self):
        with open(BATCH_FILE, "r", encoding="utf-8") as f:
            self.src = f.read()
        self.tree = ast.parse(self.src)

    def test_class_defined(self):
        classes = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.ClassDef)]
        assert "BatchSearcher" in classes, (
            f"Expected BatchSearcher class; found: {classes}"
        )

    def test_search_batch_method(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "search_batch" in funcs, "Expected search_batch() method"

    def test_search_and_aggregate_method(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "search_and_aggregate" in funcs, "Expected search_and_aggregate() method"

    def test_aggregation_modes(self):
        """Must support union, intersection, and rrf aggregation."""
        for mode in ["union", "intersection", "rrf"]:
            assert mode in self.src, f"Expected aggregation mode '{mode}'"


# ---------------------------------------------------------------------------
# Layer 3 — functional_check
# ---------------------------------------------------------------------------

class TestFunctionalSimilaritySearch:
    """Functional checks — syntax and structure validation."""

    def _parse(self, filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            src = f.read()
        try:
            ast.parse(src)
            return True, None
        except SyntaxError as e:
            return False, str(e)

    def test_engine_valid_python(self):
        ok, err = self._parse(ENGINE_FILE)
        assert ok, f"engine.py syntax error: {err}"

    def test_advisor_valid_python(self):
        ok, err = self._parse(ADVISOR_FILE)
        assert ok, f"index_advisor.py syntax error: {err}"

    def test_batch_valid_python(self):
        ok, err = self._parse(BATCH_FILE)
        assert ok, f"batch_search.py syntax error: {err}"

    def test_test_file_valid_python(self):
        ok, err = self._parse(TEST_FILE)
        assert ok, f"test_similarity_engine.py syntax error: {err}"

    def test_numpy_used(self):
        """Engine should use numpy for vector operations."""
        with open(ENGINE_FILE, "r", encoding="utf-8") as f:
            src = f.read()
        assert "numpy" in src or "np." in src, "Expected numpy for vector operations"

    def test_filter_expression_parsing(self):
        """Engine must parse filter expressions."""
        with open(ENGINE_FILE, "r", encoding="utf-8") as f:
            src = f.read()
        has_filter = (
            "filter" in src
            and ("parse" in src or "eval" in src.lower() or "expression" in src)
        )
        assert has_filter, "Expected filter expression parsing in engine"
