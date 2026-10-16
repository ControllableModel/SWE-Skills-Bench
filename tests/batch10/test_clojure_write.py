"""
Test skill: clojure-write
Verify that the Agent correctly implements a query result cache namespace
in Metabase's Clojure backend.
"""

import os
import re
import subprocess
import pytest


class TestClojureWrite:
    REPO_DIR = "/workspace/metabase"

    # === File Path Checks ===

    def test_cache_namespace_exists(self):
        """Verify src/metabase/query_result_cache.clj was created"""
        path = os.path.join(self.REPO_DIR, "src/metabase/query_result_cache.clj")
        assert os.path.exists(path), f"query_result_cache.clj not found at {path}"

    def test_cache_test_namespace_exists(self):
        """Verify test/metabase/query_result_cache_test.clj was created"""
        path = os.path.join(self.REPO_DIR, "test/metabase/query_result_cache_test.clj")
        assert os.path.exists(path), f"query_result_cache_test.clj not found at {path}"

    def test_dataset_api_exists(self):
        """Verify src/metabase/api/dataset.clj exists (to be modified)"""
        path = os.path.join(self.REPO_DIR, "src/metabase/api/dataset.clj")
        assert os.path.exists(path), f"dataset.clj not found at {path}"

    # === Semantic Checks: Namespace Declaration ===

    def test_cache_namespace_declaration(self):
        """Verify correct namespace declaration with requires"""
        path = os.path.join(self.REPO_DIR, "src/metabase/query_result_cache.clj")
        with open(path) as f:
            content = f.read()
        assert "ns metabase.query-result-cache" in content, (
            "Namespace should be declared as metabase.query-result-cache"
        )

    def test_cache_uses_atom(self):
        """Verify the cache store uses an atom"""
        path = os.path.join(self.REPO_DIR, "src/metabase/query_result_cache.clj")
        with open(path) as f:
            content = f.read()
        assert "atom" in content, "Cache store should use an atom"

    # === Semantic Checks: Cache Operations ===

    def test_cache_key_function_exists(self):
        """Verify cache-key function is defined"""
        path = os.path.join(self.REPO_DIR, "src/metabase/query_result_cache.clj")
        with open(path) as f:
            content = f.read()
        assert "cache-key" in content, "cache-key function should be defined"

    def test_cache_get_function_exists(self):
        """Verify cache-get function is defined"""
        path = os.path.join(self.REPO_DIR, "src/metabase/query_result_cache.clj")
        with open(path) as f:
            content = f.read()
        assert "cache-get" in content, "cache-get function should be defined"

    def test_cache_put_function_exists(self):
        """Verify cache-put! function is defined"""
        path = os.path.join(self.REPO_DIR, "src/metabase/query_result_cache.clj")
        with open(path) as f:
            content = f.read()
        assert "cache-put!" in content, "cache-put! function should be defined"

    def test_cache_invalidate_function_exists(self):
        """Verify cache-invalidate! function is defined"""
        path = os.path.join(self.REPO_DIR, "src/metabase/query_result_cache.clj")
        with open(path) as f:
            content = f.read()
        assert "cache-invalidate!" in content, "cache-invalidate! function should be defined"

    def test_cache_clear_function_exists(self):
        """Verify cache-clear! function is defined"""
        path = os.path.join(self.REPO_DIR, "src/metabase/query_result_cache.clj")
        with open(path) as f:
            content = f.read()
        assert "cache-clear!" in content, "cache-clear! function should be defined"

    def test_cache_stats_function_exists(self):
        """Verify cache-stats function is defined"""
        path = os.path.join(self.REPO_DIR, "src/metabase/query_result_cache.clj")
        with open(path) as f:
            content = f.read()
        assert "cache-stats" in content, "cache-stats function should be defined"

    # === Semantic Checks: TTL and Eviction ===

    def test_ttl_check_in_cache_get(self):
        """Verify cache-get checks TTL expiration"""
        path = os.path.join(self.REPO_DIR, "src/metabase/query_result_cache.clj")
        with open(path) as f:
            content = f.read()
        assert "created-at" in content, "Cache entries should track :created-at"
        assert "System/currentTimeMillis" in content or "currentTimeMillis" in content, (
            "TTL check should use System/currentTimeMillis"
        )

    def test_lru_eviction_by_last_accessed(self):
        """Verify eviction uses :last-accessed timestamp"""
        path = os.path.join(self.REPO_DIR, "src/metabase/query_result_cache.clj")
        with open(path) as f:
            content = f.read()
        assert "last-accessed" in content, (
            "Cache entries should track :last-accessed for LRU eviction"
        )

    def test_size_tracking(self):
        """Verify cache tracks entry size in bytes"""
        path = os.path.join(self.REPO_DIR, "src/metabase/query_result_cache.clj")
        with open(path) as f:
            content = f.read()
        assert "size-bytes" in content or "size" in content, (
            "Cache entries should track :size-bytes"
        )

    def test_eviction_uses_swap(self):
        """Verify eviction is performed atomically with swap!"""
        path = os.path.join(self.REPO_DIR, "src/metabase/query_result_cache.clj")
        with open(path) as f:
            content = f.read()
        assert "swap!" in content, "Eviction must be done inside swap! for atomicity"

    # === Semantic Checks: Normalization and Hashing ===

    def test_cache_key_strips_middleware(self):
        """Verify cache-key strips :middleware key before hashing"""
        path = os.path.join(self.REPO_DIR, "src/metabase/query_result_cache.clj")
        with open(path) as f:
            content = f.read()
        assert "middleware" in content, (
            "cache-key should reference :middleware for stripping"
        )

    def test_cache_key_strips_info(self):
        """Verify cache-key strips :info key before hashing"""
        path = os.path.join(self.REPO_DIR, "src/metabase/query_result_cache.clj")
        with open(path) as f:
            content = f.read()
        assert "info" in content, "cache-key should reference :info for stripping"

    def test_cache_key_uses_sha256(self):
        """Verify cache-key produces SHA-256 hex hash"""
        path = os.path.join(self.REPO_DIR, "src/metabase/query_result_cache.clj")
        with open(path) as f:
            content = f.read()
        assert "SHA-256" in content or "sha-256" in content.lower() or "sha256" in content.lower(), (
            "cache-key should use SHA-256 hashing"
        )

    # === Semantic Checks: Hit/Miss Counters ===

    def test_hit_miss_counters(self):
        """Verify hit-count and miss-count are tracked"""
        path = os.path.join(self.REPO_DIR, "src/metabase/query_result_cache.clj")
        with open(path) as f:
            content = f.read()
        assert "hit-count" in content, "Cache should track :hit-count"
        assert "miss-count" in content, "Cache should track :miss-count"

    # === Semantic Checks: Integration in dataset.clj ===

    def test_dataset_api_integration(self):
        """Verify dataset.clj integrates cache lookup around query execution"""
        path = os.path.join(self.REPO_DIR, "src/metabase/api/dataset.clj")
        with open(path) as f:
            content = f.read()
        assert "cache" in content.lower(), (
            "dataset.clj should integrate query result cache"
        )

    # === Semantic Checks: Test File ===

    def test_test_file_has_cache_key_tests(self):
        """Verify test file covers cache-key normalization"""
        path = os.path.join(self.REPO_DIR, "test/metabase/query_result_cache_test.clj")
        with open(path) as f:
            content = f.read()
        assert "cache-key" in content, "Tests should cover cache-key function"

    def test_test_file_has_ttl_tests(self):
        """Verify test file covers TTL expiration"""
        path = os.path.join(self.REPO_DIR, "test/metabase/query_result_cache_test.clj")
        with open(path) as f:
            content = f.read()
        assert "expir" in content.lower() or "ttl" in content.lower(), (
            "Tests should cover TTL expiration behavior"
        )

    def test_test_file_has_eviction_tests(self):
        """Verify test file covers LRU eviction"""
        path = os.path.join(self.REPO_DIR, "test/metabase/query_result_cache_test.clj")
        with open(path) as f:
            content = f.read()
        assert "evict" in content.lower() or "max-entries" in content, (
            "Tests should cover eviction behavior"
        )

    # === Functional Checks ===

    def test_balanced_parentheses(self):
        """Verify query_result_cache.clj has balanced parentheses"""
        path = os.path.join(self.REPO_DIR, "src/metabase/query_result_cache.clj")
        with open(path) as f:
            content = f.read()
        open_count = content.count("(") + content.count("[") + content.count("{")
        close_count = content.count(")") + content.count("]") + content.count("}")
        assert open_count == close_count, (
            f"Parentheses mismatch: {open_count} open vs {close_count} close"
        )

    def test_file_ends_with_newline(self):
        """Verify source files end with newline"""
        path = os.path.join(self.REPO_DIR, "src/metabase/query_result_cache.clj")
        with open(path) as f:
            content = f.read()
        assert content.endswith("\n"), "Source file should end with a newline character"

    def test_test_file_balanced_parentheses(self):
        """Verify test file has balanced parentheses"""
        path = os.path.join(self.REPO_DIR, "test/metabase/query_result_cache_test.clj")
        with open(path) as f:
            content = f.read()
        open_count = content.count("(") + content.count("[") + content.count("{")
        close_count = content.count(")") + content.count("]") + content.count("}")
        assert open_count == close_count, (
            f"Test file parentheses mismatch: {open_count} open vs {close_count} close"
        )

    def test_cache_max_entries_parameter(self):
        """Verify cache-put! accepts max-entries parameter"""
        path = os.path.join(self.REPO_DIR, "src/metabase/query_result_cache.clj")
        with open(path) as f:
            content = f.read()
        assert "max-entries" in content, "cache-put! should accept max-entries parameter"

    def test_cache_max_total_bytes_parameter(self):
        """Verify cache-put! accepts max-total-bytes parameter"""
        path = os.path.join(self.REPO_DIR, "src/metabase/query_result_cache.clj")
        with open(path) as f:
            content = f.read()
        assert "max-total-bytes" in content, (
            "cache-put! should accept max-total-bytes parameter"
        )
