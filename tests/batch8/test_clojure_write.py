"""
Tests for the clojure-write skill.
Validates implementation of a Data Catalog namespace for Metabase's
internal metadata registry with search, stats, and public API functions.
"""

import os
import re

REPO_DIR = "/workspace/metabase"


class TestClojureWrite:
    """Tests for the Metabase Data Catalog namespace implementation."""

    # ── file_path_check ──────────────────────────────────────────────

    def test_catalog_core_exists(self):
        """Core namespace file must exist."""
        path = os.path.join(REPO_DIR, "src", "metabase", "catalog", "core.clj")
        assert os.path.isfile(path), f"Missing {path}"

    def test_catalog_registry_exists(self):
        """Registry namespace file must exist."""
        path = os.path.join(REPO_DIR, "src", "metabase", "catalog", "registry.clj")
        assert os.path.isfile(path), f"Missing {path}"

    def test_catalog_search_exists(self):
        """Search namespace file must exist."""
        path = os.path.join(REPO_DIR, "src", "metabase", "catalog", "search.clj")
        assert os.path.isfile(path), f"Missing {path}"

    def test_catalog_stats_exists(self):
        """Stats namespace file must exist."""
        path = os.path.join(REPO_DIR, "src", "metabase", "catalog", "stats.clj")
        assert os.path.isfile(path), f"Missing {path}"

    # ── semantic_check ───────────────────────────────────────────────

    def _read_ns(self, rel_path):
        """Read a namespace file and return its content."""
        path = os.path.join(REPO_DIR, rel_path)
        if not os.path.isfile(path):
            return ""
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def test_registry_build_catalog_defined(self):
        """registry/build-catalog function must be defined."""
        content = self._read_ns("src/metabase/catalog/registry.clj")
        assert re.search(r"defn\s+build-catalog", content), (
            "build-catalog function not defined in registry.clj"
        )

    def test_registry_update_catalog_defined(self):
        """registry/update-catalog function must be defined for incremental updates."""
        content = self._read_ns("src/metabase/catalog/registry.clj")
        assert re.search(r"defn\s+update-catalog", content), (
            "update-catalog function not defined in registry.clj"
        )

    def test_search_find_tables_defined(self):
        """search/find-tables function must be defined."""
        content = self._read_ns("src/metabase/catalog/search.clj")
        assert re.search(r"defn\s+find-tables", content), (
            "find-tables function not defined in search.clj"
        )

    def test_search_find_fields_defined(self):
        """search/find-fields function must be defined."""
        content = self._read_ns("src/metabase/catalog/search.clj")
        assert re.search(r"defn\s+find-fields", content), (
            "find-fields function not defined in search.clj"
        )

    def test_stats_database_summary_defined(self):
        """stats/database-summary function must be defined."""
        content = self._read_ns("src/metabase/catalog/stats.clj")
        assert re.search(r"defn\s+database-summary", content), (
            "database-summary function not defined in stats.clj"
        )

    def test_stats_table_detail_defined(self):
        """stats/table-detail function must be defined."""
        content = self._read_ns("src/metabase/catalog/stats.clj")
        assert re.search(r"defn\s+table-detail", content), (
            "table-detail function not defined in stats.clj"
        )

    def test_core_public_api_functions(self):
        """core namespace must expose get-catalog, search, database-stats, refresh-database."""
        content = self._read_ns("src/metabase/catalog/core.clj")
        expected = ["get-catalog", "search", "database-stats", "refresh-database"]
        for fn_name in expected:
            assert re.search(rf"defn\s+{re.escape(fn_name)}", content), (
                f"Public function {fn_name} not defined in core.clj"
            )

    def test_search_result_limit(self):
        """Search functions must enforce a 50-result cap."""
        content = self._read_ns("src/metabase/catalog/search.clj")
        assert re.search(r"50|take\s+50|:limit\s+50", content), (
            "50-result cap not found in search.clj"
        )

    # ── functional_check ─────────────────────────────────────────────

    def test_registry_excludes_audit_databases(self):
        """Registry must filter out audit databases (is_audit check)."""
        content = self._read_ns("src/metabase/catalog/registry.clj")
        assert re.search(r"is[_-]audit|:is_audit|audit", content, re.IGNORECASE), (
            "No audit database filtering found in registry.clj"
        )

    def test_registry_excludes_hidden_tables(self):
        """Registry must filter out hidden/technical tables (visibility_type)."""
        content = self._read_ns("src/metabase/catalog/registry.clj")
        assert re.search(r"visibility[_-]type|hidden|technical", content, re.IGNORECASE), (
            "No hidden/technical table filtering found in registry.clj"
        )

    def test_search_handles_blank_input(self):
        """Search must handle nil/blank query string returning empty vector."""
        content = self._read_ns("src/metabase/catalog/search.clj")
        assert re.search(r"blank\?|nil\?|empty\?|str/blank", content), (
            "No nil/blank input handling found in search.clj"
        )

    def test_all_files_have_balanced_parens(self):
        """All Clojure files must have balanced parentheses/brackets."""
        for rel in [
            "src/metabase/catalog/core.clj",
            "src/metabase/catalog/registry.clj",
            "src/metabase/catalog/search.clj",
            "src/metabase/catalog/stats.clj",
        ]:
            content = self._read_ns(rel)
            if not content:
                continue
            opens = content.count("(") + content.count("[") + content.count("{")
            closes = content.count(")") + content.count("]") + content.count("}")
            assert opens == closes, (
                f"Unbalanced brackets in {rel}: {opens} opens vs {closes} closes"
            )

    def test_core_test_file_exists(self):
        """Test file for core namespace must exist."""
        path = os.path.join(REPO_DIR, "test", "metabase", "catalog", "core_test.clj")
        assert os.path.isfile(path), f"Missing {path}"

    def test_search_test_file_exists(self):
        """Test file for search namespace must exist."""
        path = os.path.join(REPO_DIR, "test", "metabase", "catalog", "search_test.clj")
        assert os.path.isfile(path), f"Missing {path}"

    def test_namespace_declarations_correct(self):
        """Each file must have a proper (ns ...) declaration matching its path."""
        ns_map = {
            "src/metabase/catalog/core.clj": "metabase.catalog.core",
            "src/metabase/catalog/registry.clj": "metabase.catalog.registry",
            "src/metabase/catalog/search.clj": "metabase.catalog.search",
            "src/metabase/catalog/stats.clj": "metabase.catalog.stats",
        }
        for rel, expected_ns in ns_map.items():
            content = self._read_ns(rel)
            if not content:
                assert False, f"{rel} not found"
            assert re.search(rf"\(ns\s+{re.escape(expected_ns)}", content), (
                f"{rel} lacks correct (ns {expected_ns} ...) declaration"
            )
