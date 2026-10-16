"""
Test skill: clojure-write
Verify that the Agent correctly implements an audit log query namespace
for Metabase with query functions, aggregation, API endpoints, and
validation.
"""

import os
import re
import subprocess
import pytest


class TestClojureWrite:
    REPO_DIR = "/workspace/metabase"

    # === File Path Checks ===

    def test_query_namespace_exists(self):
        """Verify audit_log/query.clj exists"""
        path = os.path.join(self.REPO_DIR, "src/metabase/audit_log/query.clj")
        assert os.path.exists(path), f"query.clj not found at {path}"

    def test_models_namespace_exists(self):
        """Verify audit_log/models.clj exists"""
        path = os.path.join(self.REPO_DIR, "src/metabase/audit_log/models.clj")
        assert os.path.exists(path), f"models.clj not found at {path}"

    def test_api_namespace_exists(self):
        """Verify api/audit_log.clj exists"""
        path = os.path.join(self.REPO_DIR, "src/metabase/api/audit_log.clj")
        assert os.path.exists(path), f"api/audit_log.clj not found at {path}"

    def test_test_file_exists(self):
        """Verify audit_log/query_test.clj exists"""
        path = os.path.join(self.REPO_DIR, "test/metabase/audit_log/query_test.clj")
        assert os.path.exists(path), f"query_test.clj not found at {path}"

    # === Semantic Checks ===

    def test_query_audit_log_function_defined(self):
        """Verify query-audit-log function is defined"""
        path = os.path.join(self.REPO_DIR, "src/metabase/audit_log/query.clj")
        with open(path, "r") as f:
            content = f.read()

        assert re.search(r"defn\s+query-audit-log", content), (
            "query.clj must define query-audit-log function"
        )

    def test_count_by_action_function_defined(self):
        """Verify count-by-action function is defined"""
        path = os.path.join(self.REPO_DIR, "src/metabase/audit_log/query.clj")
        with open(path, "r") as f:
            content = f.read()

        assert re.search(r"defn\s+count-by-action", content), (
            "query.clj must define count-by-action function"
        )

    def test_count_by_user_function_defined(self):
        """Verify count-by-user function is defined"""
        path = os.path.join(self.REPO_DIR, "src/metabase/audit_log/query.clj")
        with open(path, "r") as f:
            content = f.read()

        assert re.search(r"defn\s+count-by-user", content), (
            "query.clj must define count-by-user function"
        )

    def test_entity_history_function_defined(self):
        """Verify entity-history function is defined"""
        path = os.path.join(self.REPO_DIR, "src/metabase/audit_log/query.clj")
        with open(path, "r") as f:
            content = f.read()

        assert re.search(r"defn\s+entity-history", content), (
            "query.clj must define entity-history function"
        )

    def test_query_supports_filter_options(self):
        """Verify query-audit-log handles user-id, action, entity-type, dates, pagination"""
        path = os.path.join(self.REPO_DIR, "src/metabase/audit_log/query.clj")
        with open(path, "r") as f:
            content = f.read()

        expected_keys = [":user-id", ":action", ":entity-type", ":start-date", ":end-date",
                         ":limit", ":offset"]
        found_keys = [k for k in expected_keys if k in content]
        assert len(found_keys) >= 5, (
            f"query-audit-log should support filter keys. Found: {found_keys}, "
            f"expected at least 5 of: {expected_keys}"
        )

    def test_returns_results_and_total_count(self):
        """Verify query-audit-log returns :results and :total_count"""
        path = os.path.join(self.REPO_DIR, "src/metabase/audit_log/query.clj")
        with open(path, "r") as f:
            content = f.read()

        assert ":results" in content, "query-audit-log should return :results key"
        assert ":total_count" in content or ":total-count" in content, (
            "query-audit-log should return :total_count key"
        )

    def test_validation_entity_id_requires_entity_type(self):
        """Verify entity-id without entity-type raises validation error"""
        path = os.path.join(self.REPO_DIR, "src/metabase/audit_log/query.clj")
        with open(path, "r") as f:
            content = f.read()

        assert "entity-id requires entity-type" in content or \
               re.search(r"entity.id.*entity.type", content), (
            "Must validate that :entity-id requires :entity-type"
        )

    def test_validation_date_range(self):
        """Verify start-date must be before end-date"""
        path = os.path.join(self.REPO_DIR, "src/metabase/audit_log/query.clj")
        with open(path, "r") as f:
            content = f.read()

        assert "start-date must be before end-date" in content or \
               re.search(r"start.*before.*end", content), (
            "Must validate that start-date is before end-date"
        )

    def test_validation_limit_range(self):
        """Verify limit must be between 1 and 10000"""
        path = os.path.join(self.REPO_DIR, "src/metabase/audit_log/query.clj")
        with open(path, "r") as f:
            content = f.read()

        assert "10000" in content, (
            "Must validate that limit is between 1 and 10000"
        )

    def test_api_endpoints_defined(self):
        """Verify API endpoints are defined with admin permissions"""
        path = os.path.join(self.REPO_DIR, "src/metabase/api/audit_log.clj")
        with open(path, "r") as f:
            content = f.read()

        assert "audit-log" in content, "API should reference audit-log routes"
        assert "admin" in content.lower() or "superuser" in content.lower(), (
            "API endpoints should require admin permissions"
        )

    def test_api_has_summary_endpoint(self):
        """Verify GET /api/audit-log/summary endpoint exists"""
        path = os.path.join(self.REPO_DIR, "src/metabase/api/audit_log.clj")
        with open(path, "r") as f:
            content = f.read()

        assert "summary" in content, "API should define /summary endpoint"
        assert "count-by-action" in content, (
            "Summary endpoint should call count-by-action"
        )

    def test_api_has_top_users_endpoint(self):
        """Verify GET /api/audit-log/top-users endpoint exists"""
        path = os.path.join(self.REPO_DIR, "src/metabase/api/audit_log.clj")
        with open(path, "r") as f:
            content = f.read()

        assert "top-users" in content, "API should define /top-users endpoint"

    def test_models_define_action_keywords(self):
        """Verify models.clj defines the valid action keywords"""
        path = os.path.join(self.REPO_DIR, "src/metabase/audit_log/models.clj")
        with open(path, "r") as f:
            content = f.read()

        expected_actions = [":create", ":update", ":delete", ":login", ":logout"]
        found = [a for a in expected_actions if a in content]
        assert len(found) >= 4, (
            f"models.clj should define action keywords. Found: {found}"
        )

    # === Functional Checks ===

    def test_all_clj_files_have_balanced_parens(self):
        """Verify all Clojure files have balanced parentheses"""
        files = [
            "src/metabase/audit_log/query.clj",
            "src/metabase/audit_log/models.clj",
            "src/metabase/api/audit_log.clj",
            "test/metabase/audit_log/query_test.clj",
        ]
        for filename in files:
            path = os.path.join(self.REPO_DIR, filename)
            if not os.path.exists(path):
                continue
            with open(path, "r") as f:
                content = f.read()
            opens = content.count("(")
            closes = content.count(")")
            assert abs(opens - closes) <= 2, (
                f"{filename}: Unbalanced parens ({opens} open, {closes} close)"
            )

    def test_query_test_has_adequate_coverage(self):
        """Verify query_test.clj has tests for major functions"""
        path = os.path.join(self.REPO_DIR, "test/metabase/audit_log/query_test.clj")
        with open(path, "r") as f:
            content = f.read()

        assert "deftest" in content, "Test file must use deftest"
        test_count = len(re.findall(r"deftest", content))
        assert test_count >= 3, (
            f"query_test.clj should have at least 3 tests, found {test_count}"
        )

        # Should test main functions
        assert "query-audit-log" in content, "Tests should cover query-audit-log"
        assert "count-by" in content, "Tests should cover count-by-action or count-by-user"

    def test_namespaces_have_correct_ns_declaration(self):
        """Verify each file has proper (ns ...) declaration"""
        expected = {
            "src/metabase/audit_log/query.clj": "metabase.audit-log.query",
            "src/metabase/audit_log/models.clj": "metabase.audit-log.models",
            "src/metabase/api/audit_log.clj": "metabase.api.audit-log",
        }
        for filepath, ns_name in expected.items():
            path = os.path.join(self.REPO_DIR, filepath)
            if not os.path.exists(path):
                continue
            with open(path, "r") as f:
                content = f.read()
            # ns name may use underscores in filesystem but hyphens in Clojure
            ns_pattern = ns_name.replace(".", r"\.")
            assert re.search(rf"\(ns\s+{ns_pattern}", content) or ns_name in content, (
                f"{filepath} should declare namespace {ns_name}"
            )
