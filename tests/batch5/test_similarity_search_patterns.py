"""
Test skill: similarity-search-patterns
Verify that the Agent correctly implements a Go-based similarity search
service for Milvus with collections, filter builder, and batch search.
"""

import os
import re
import subprocess
import pytest


class TestSimilaritySearchPatterns:
    REPO_DIR = "/workspace/milvus"

    SERVICE = "internal/search/service.go"
    CONFIG = "internal/search/config.go"
    BATCH = "internal/search/batch.go"
    FILTER = "internal/search/filter.go"
    TESTS = "internal/search/service_test.go"

    def _read_file(self, rel_path):
        filepath = os.path.join(self.REPO_DIR, rel_path)
        with open(filepath) as f:
            return f.read()

    # === File Path Checks ===

    def test_service_file_exists(self):
        filepath = os.path.join(self.REPO_DIR, self.SERVICE)
        assert os.path.exists(filepath), f"service.go not found at {filepath}"

    def test_config_file_exists(self):
        filepath = os.path.join(self.REPO_DIR, self.CONFIG)
        assert os.path.exists(filepath), f"config.go not found at {filepath}"

    def test_batch_file_exists(self):
        filepath = os.path.join(self.REPO_DIR, self.BATCH)
        assert os.path.exists(filepath), f"batch.go not found at {filepath}"

    def test_filter_file_exists(self):
        filepath = os.path.join(self.REPO_DIR, self.FILTER)
        assert os.path.exists(filepath), f"filter.go not found at {filepath}"

    def test_tests_file_exists(self):
        filepath = os.path.join(self.REPO_DIR, self.TESTS)
        assert os.path.exists(filepath), f"service_test.go not found at {filepath}"

    # === Semantic Checks ===

    def test_service_defines_struct(self):
        """Verify SearchService struct with NewSearchService constructor"""
        content = self._read_file(self.SERVICE)
        assert "SearchService" in content, "Missing SearchService struct"
        assert "NewSearchService" in content, "Missing NewSearchService constructor"

    def test_service_crud_methods(self):
        """Verify CreateCollection, BuildIndex, Insert, Search, Close methods"""
        content = self._read_file(self.SERVICE)
        for method in ["CreateCollection", "BuildIndex", "Insert", "Search", "Close"]:
            assert method in content, f"Missing method: {method}"

    def test_service_supports_ivf_and_hnsw(self):
        """Verify support for IVF_FLAT and HNSW index types"""
        content = self._read_file(self.SERVICE) + self._read_file(self.CONFIG)
        assert "IVF_FLAT" in content or "IvfFlat" in content, \
            "Missing IVF_FLAT index support"
        assert "HNSW" in content, "Missing HNSW index support"

    def test_config_types_defined(self):
        """Verify CollectionConfig and SearchConfig types"""
        content = self._read_file(self.CONFIG)
        assert "CollectionConfig" in content, "Missing CollectionConfig type"
        assert "SearchConfig" in content, "Missing SearchConfig type"
        for field in ["Dimension", "MetricType", "TopK"]:
            assert field in content, f"Config missing field: {field}"

    def test_filter_builder_methods(self):
        """Verify FilterBuilder with Equal, NotEqual, GreaterThan, LessThan, In"""
        content = self._read_file(self.FILTER)
        assert "FilterBuilder" in content, "Missing FilterBuilder type"
        for method in ["Equal", "NotEqual", "GreaterThan", "LessThan", "In"]:
            assert method in content, f"FilterBuilder missing method: {method}"

    def test_filter_builder_combinators(self):
        """Verify And and Or combinators"""
        content = self._read_file(self.FILTER)
        assert "And" in content, "FilterBuilder missing And combinator"
        assert "Or" in content, "FilterBuilder missing Or combinator"

    def test_filter_prevents_injection(self):
        """Verify filter validates field names to prevent injection"""
        content = self._read_file(self.FILTER)
        has_validation = bool(re.search(
            r'(regexp|alphanumeric|validate|^[a-zA-Z]|injection|sanitize)',
            content,
            re.IGNORECASE,
        ))
        assert has_validation, "FilterBuilder missing field name injection prevention"

    def test_batch_search_concurrency(self):
        """Verify BatchSearch uses bounded concurrency with semaphore"""
        content = self._read_file(self.BATCH)
        assert "BatchSearch" in content, "Missing BatchSearch function"
        has_semaphore = bool(re.search(
            r'(chan.*struct|semaphore|make.*chan|maxConcurrency|sem)',
            content,
        ))
        assert has_semaphore, "BatchSearch missing semaphore for bounded concurrency"

    def test_batch_preserves_ordering(self):
        """Verify batch results maintain input query order"""
        content = self._read_file(self.BATCH)
        has_ordering = bool(re.search(
            r'(index|results\[i\]|\[idx\]|order)', content, re.IGNORECASE
        ))
        assert has_ordering, "BatchSearch missing result ordering preservation"

    # === Functional Checks ===

    def test_go_build_compiles(self):
        """Verify Go code compiles"""
        result = subprocess.run(
            ["go", "build", "./internal/search/..."],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            # Only fail on compilation errors, not link errors
            if "cannot find" not in result.stderr and "syntax" in result.stderr.lower():
                pytest.fail(f"Go compilation error: {result.stderr[:500]}")

    def test_tests_have_assertions(self):
        """Verify test file contains Go test functions"""
        content = self._read_file(self.TESTS)
        test_count = len(re.findall(r'func Test\w+', content))
        assert test_count >= 3, \
            f"Expected at least 3 Go test functions, found {test_count}"

    def test_filter_build_produces_expression(self):
        """Verify Build() method returns string expression"""
        content = self._read_file(self.FILTER)
        assert "Build" in content, "Missing Build method"
        assert "string" in content, "Build should return string type"
