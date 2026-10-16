"""
Test skill: similarity-search-patterns
Verify that the Agent creates a Milvus similarity search demo including
collection setup, vector insertion, multi-metric search, filtered search,
and result display.
"""

import os
import re
import ast
import subprocess
import pytest


class TestSimilaritySearchPatterns:
    REPO_DIR = "/workspace/milvus"

    # === File Path Checks ===

    def test_demo_script_exists(self):
        """Verify examples/similarity_search_demo.py exists"""
        path = os.path.join(self.REPO_DIR, "examples/similarity_search_demo.py")
        assert os.path.exists(path), (
            f"similarity_search_demo.py not found at {path}"
        )

    # === Semantic Checks ===

    def test_collection_creation(self):
        """Verify collection is created with a defined schema"""
        path = os.path.join(self.REPO_DIR, "examples/similarity_search_demo.py")
        with open(path) as f:
            content = f.read()

        schema_indicators = [
            "Collection", "schema", "FieldSchema", "CollectionSchema",
            "create_collection", "collection",
        ]
        found = [ind for ind in schema_indicators if ind in content]
        assert len(found) >= 2, (
            f"Should create a collection with schema. Found: {found}"
        )

    def test_vector_insertion(self):
        """Verify sample vectors with metadata are inserted"""
        path = os.path.join(self.REPO_DIR, "examples/similarity_search_demo.py")
        with open(path) as f:
            content = f.read()

        insert_indicators = [
            "insert", "add", "upsert", "data",
            "entities", "vectors",
        ]
        found = [ind for ind in insert_indicators if ind in content]
        assert len(found) >= 2, (
            f"Should insert vectors with metadata. Found: {found}"
        )

    def test_multiple_distance_metrics(self):
        """Verify at least two distance metrics are demonstrated"""
        path = os.path.join(self.REPO_DIR, "examples/similarity_search_demo.py")
        with open(path) as f:
            content = f.read()

        metric_indicators = [
            "L2", "IP", "COSINE", "l2", "inner_product",
            "cosine", "euclidean", "metric_type",
        ]
        found = [ind for ind in metric_indicators if ind in content]
        assert len(found) >= 2, (
            f"Should use at least two distance metrics. Found: {found}"
        )

    def test_configurable_top_k(self):
        """Verify configurable top-k search parameter"""
        path = os.path.join(self.REPO_DIR, "examples/similarity_search_demo.py")
        with open(path) as f:
            content = f.read()

        topk_indicators = [
            "top_k", "topk", "limit", "k=", "anns_field",
            "param", "search_params",
        ]
        found = [ind for ind in topk_indicators if ind in content]
        assert len(found) >= 1, (
            f"Should support configurable top-k. Found: {found}"
        )

    def test_filtered_search(self):
        """Verify filtered search combining similarity with metadata predicates"""
        path = os.path.join(self.REPO_DIR, "examples/similarity_search_demo.py")
        with open(path) as f:
            content = f.read()

        filter_indicators = [
            "filter", "expr", "expression", "boolean_expr",
            "predicate", "where", "metadata",
        ]
        found = [ind for ind in filter_indicators if ind in content]
        assert len(found) >= 1, (
            f"Should support filtered search. Found: {found}"
        )

    def test_result_display(self):
        """Verify search results display distances/scores and metadata"""
        path = os.path.join(self.REPO_DIR, "examples/similarity_search_demo.py")
        with open(path) as f:
            content = f.read().lower()

        display_indicators = [
            "print", "distance", "score", "result",
            "id", "metadata", "hit",
        ]
        found = [ind for ind in display_indicators if ind in content]
        assert len(found) >= 3, (
            f"Should display results with distances and metadata. Found: {found}"
        )

    def test_index_creation(self):
        """Verify a vector index is created on the collection"""
        path = os.path.join(self.REPO_DIR, "examples/similarity_search_demo.py")
        with open(path) as f:
            content = f.read()

        index_indicators = [
            "create_index", "index", "IVF_FLAT", "HNSW",
            "IVF_SQ8", "IndexType", "index_params",
        ]
        found = [ind for ind in index_indicators if ind in content]
        assert len(found) >= 1, (
            f"Should create a vector index. Found: {found}"
        )

    # === Functional Checks ===

    def test_script_valid_python(self):
        """Verify similarity_search_demo.py is valid Python"""
        path = os.path.join(self.REPO_DIR, "examples/similarity_search_demo.py")
        with open(path) as f:
            source = f.read()
        try:
            ast.parse(source)
        except SyntaxError as e:
            pytest.fail(f"similarity_search_demo.py has syntax errors: {e}")

    def test_imports_pymilvus(self):
        """Verify script imports pymilvus"""
        path = os.path.join(self.REPO_DIR, "examples/similarity_search_demo.py")
        with open(path) as f:
            content = f.read()

        assert "pymilvus" in content or "milvus" in content, (
            "Script should import pymilvus or milvus client"
        )

    def test_defines_functions(self):
        """Verify script defines reusable functions"""
        path = os.path.join(self.REPO_DIR, "examples/similarity_search_demo.py")
        with open(path) as f:
            source = f.read()

        tree = ast.parse(source)
        func_names = [
            node.name for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef)
        ]
        assert len(func_names) >= 2, (
            f"Script should define functions. Found: {func_names}"
        )

    def test_sample_data_with_metadata(self):
        """Verify sample data includes metadata fields beyond vectors"""
        path = os.path.join(self.REPO_DIR, "examples/similarity_search_demo.py")
        with open(path) as f:
            content = f.read().lower()

        metadata_indicators = [
            "metadata", "field", "name", "category",
            "label", "tag", "description", "varchar",
        ]
        found = [ind for ind in metadata_indicators if ind in content]
        assert len(found) >= 2, (
            f"Sample data should include metadata fields. Found: {found}"
        )
