"""
Test skill: similarity-search-patterns
Verify that the Agent builds a hybrid similarity search service with
multiple index types (Flat, HNSW, IVF+PQ), Pinecone/FAISS stores,
BM25 sparse search, RRF fusion, and a REST API.
"""

import os
import re
import ast
import json
import subprocess
import pytest


class TestSimilaritySearchPatterns:
    REPO_DIR = "/workspace/milvus"

    # === File Path Checks ===

    def test_pinecone_store_exists(self):
        path = os.path.join(self.REPO_DIR, "src/similarity/pinecone_store.py")
        assert os.path.exists(path), f"pinecone_store.py not found"

    def test_faiss_store_exists(self):
        path = os.path.join(self.REPO_DIR, "src/similarity/faiss_store.py")
        assert os.path.exists(path), f"faiss_store.py not found"

    def test_hybrid_exists(self):
        path = os.path.join(self.REPO_DIR, "src/similarity/hybrid.py")
        assert os.path.exists(path), f"hybrid.py not found"

    def test_reranker_exists(self):
        path = os.path.join(self.REPO_DIR, "src/similarity/reranker.py")
        assert os.path.exists(path), f"reranker.py not found"

    def test_api_exists(self):
        path = os.path.join(self.REPO_DIR, "src/similarity/api.py")
        assert os.path.exists(path), f"api.py not found"

    def test_models_exists(self):
        path = os.path.join(self.REPO_DIR, "src/similarity/models.py")
        assert os.path.exists(path), f"models.py not found"

    # === Semantic Checks ===

    def test_faiss_store_supports_three_index_types(self):
        """Verify FAISSStore supports flat, HNSW, and IVF+PQ"""
        path = os.path.join(self.REPO_DIR, "src/similarity/faiss_store.py")
        with open(path, "r") as f:
            content = f.read()

        assert "FAISSStore" in content, "Must define FAISSStore class"
        assert "flat" in content, "Must support flat index"
        assert "hnsw" in content.lower(), "Must support HNSW index"
        assert "ivf" in content.lower() or "IVF" in content, "Must support IVF index"
        assert "pq" in content.lower() or "PQ" in content, "Must support PQ quantization"

    def test_faiss_store_enforces_training(self):
        """Verify IVF+PQ requires training before adding vectors"""
        path = os.path.join(self.REPO_DIR, "src/similarity/faiss_store.py")
        with open(path, "r") as f:
            content = f.read()

        assert "train" in content, "IVF+PQ should require training"
        assert "ValueError" in content or "requires training" in content.lower(), (
            "Should raise ValueError if add() called before train()"
        )

    def test_faiss_store_has_save_load(self):
        """Verify FAISSStore supports save/load"""
        path = os.path.join(self.REPO_DIR, "src/similarity/faiss_store.py")
        with open(path, "r") as f:
            content = f.read()

        assert re.search(r"def\s+save", content), "Missing save method"
        assert re.search(r"def\s+load", content), "Missing load method"

    def test_pinecone_store_has_required_methods(self):
        """Verify PineconeStore has upsert, search, delete, describe"""
        path = os.path.join(self.REPO_DIR, "src/similarity/pinecone_store.py")
        with open(path, "r") as f:
            content = f.read()

        assert "PineconeStore" in content, "Must define PineconeStore class"
        for method in ["upsert", "search", "delete", "describe"]:
            assert re.search(rf"def\s+{method}", content), f"Missing {method} method"

    def test_pinecone_supports_metadata_filter(self):
        """Verify PineconeStore supports metadata filtering"""
        path = os.path.join(self.REPO_DIR, "src/similarity/pinecone_store.py")
        with open(path, "r") as f:
            content = f.read()

        assert "filter" in content, "PineconeStore should support metadata filtering"

    def test_hybrid_searcher_uses_rrf(self):
        """Verify HybridSearcher uses Reciprocal Rank Fusion"""
        path = os.path.join(self.REPO_DIR, "src/similarity/hybrid.py")
        with open(path, "r") as f:
            content = f.read()

        assert "HybridSearcher" in content, "Must define HybridSearcher class"
        assert "rrf" in content.lower() or "reciprocal" in content.lower(), (
            "Should use RRF for score fusion"
        )
        assert "BM25" in content or "bm25" in content, "Should use BM25 for sparse search"

    def test_api_has_all_endpoints(self):
        """Verify REST API defines all required endpoints"""
        path = os.path.join(self.REPO_DIR, "src/similarity/api.py")
        with open(path, "r") as f:
            content = f.read()

        assert "search" in content, "API must have /search endpoint"
        assert "hybrid" in content, "API must have /hybrid-search endpoint"
        assert "upsert" in content, "API must have /upsert endpoint"
        assert "health" in content, "API must have /health endpoint"

    def test_models_use_pydantic(self):
        """Verify request/response models use Pydantic"""
        path = os.path.join(self.REPO_DIR, "src/similarity/models.py")
        with open(path, "r") as f:
            content = f.read()

        assert "BaseModel" in content or "pydantic" in content, (
            "Models should use Pydantic BaseModel"
        )

    # === Functional Checks ===

    def test_all_python_files_parse(self):
        """Verify all Python files parse without syntax errors"""
        files = [
            "src/similarity/__init__.py",
            "src/similarity/pinecone_store.py",
            "src/similarity/faiss_store.py",
            "src/similarity/hybrid.py",
            "src/similarity/reranker.py",
            "src/similarity/api.py",
            "src/similarity/models.py",
        ]
        for filename in files:
            path = os.path.join(self.REPO_DIR, filename)
            with open(path, "r") as f:
                source = f.read()
            try:
                ast.parse(source)
            except SyntaxError as e:
                pytest.fail(f"{filename} has syntax error: {e}")

    def test_init_exports_main_classes(self):
        """Verify __init__.py exports main classes"""
        path = os.path.join(self.REPO_DIR, "src/similarity/__init__.py")
        with open(path, "r") as f:
            content = f.read()

        assert "SimilarityService" in content or "FAISSStore" in content, (
            "__init__.py should export main classes"
        )

    def test_test_files_exist(self):
        """Verify test files exist"""
        test_files = [
            "tests/test_faiss_store.py",
            "tests/test_hybrid.py",
            "tests/test_api.py",
        ]
        for filename in test_files:
            path = os.path.join(self.REPO_DIR, filename)
            assert os.path.exists(path), f"Test file {filename} not found"
