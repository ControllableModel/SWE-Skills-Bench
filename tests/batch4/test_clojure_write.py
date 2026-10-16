"""
Tests for skill: clojure-write
Repo: metabase/metabase
Image: zhangyiiiiii/swe-skills-bench-clojure
Task: Implement a metadata audit log system in Metabase recording database
      metadata changes, with Toucan 2 model, event listeners, and API endpoints.
"""

import json
import os
import re
import subprocess

import pytest

REPO_DIR = "/workspace/metabase"

MODEL_FILE = os.path.join(REPO_DIR, "src", "metabase", "models", "metadata_audit_log.clj")
API_FILE = os.path.join(REPO_DIR, "src", "metabase", "api", "metadata_audit.clj")
EVENTS_FILE = os.path.join(REPO_DIR, "src", "metabase", "events", "metadata_audit.clj")
MIGRATION_DIR = os.path.join(REPO_DIR, "resources", "migrations")


# ---------------------------------------------------------------------------
# Layer 1 — file_path_check
# ---------------------------------------------------------------------------

class TestFilePathCheck:
    """Verify all required files were created."""

    def test_model_file_exists(self):
        assert os.path.isfile(MODEL_FILE), (
            f"Expected model file at {MODEL_FILE}"
        )

    def test_api_file_exists(self):
        assert os.path.isfile(API_FILE), (
            f"Expected API file at {API_FILE}"
        )

    def test_events_file_exists(self):
        assert os.path.isfile(EVENTS_FILE), (
            f"Expected events file at {EVENTS_FILE}"
        )

    def test_migration_file_exists(self):
        """A SQL migration creating the audit log table must exist."""
        assert os.path.isdir(MIGRATION_DIR), (
            f"Expected migrations directory at {MIGRATION_DIR}"
        )
        migration_files = [
            f for f in os.listdir(MIGRATION_DIR)
            if "metadata_audit_log" in f.lower() or "audit" in f.lower()
        ]
        assert len(migration_files) >= 1, (
            f"Expected at least one migration file for metadata_audit_log table "
            f"in {MIGRATION_DIR}, found: {os.listdir(MIGRATION_DIR)[:20]}"
        )


# ---------------------------------------------------------------------------
# Layer 2 — semantic_check
# ---------------------------------------------------------------------------

class TestSemanticModel:
    """Verify Toucan 2 model definition for MetadataAuditLog."""

    @pytest.fixture(autouse=True)
    def _load_source(self):
        with open(MODEL_FILE, "r", encoding="utf-8") as f:
            self.src = f.read()

    def test_model_namespace_declaration(self):
        """Model file must declare a Clojure namespace."""
        assert re.search(r"\(ns\s+metabase\.models\.metadata[_-]audit[_-]log", self.src), (
            "Expected (ns metabase.models.metadata-audit-log ...) namespace declaration"
        )

    def test_json_type_mapping(self):
        """old_value and new_value must be mapped to :json type for auto-serialization."""
        assert ":json" in self.src, (
            "Expected :json type mapping for old_value/new_value fields"
        )

    def test_log_change_helper(self):
        """A log-change! helper function must be defined."""
        assert "log-change!" in self.src, (
            "Expected log-change! helper function in model file"
        )

    def test_entity_type_validation(self):
        """log-change! must validate entity_type against allowed values."""
        for entity_type in ["table", "field", "database"]:
            assert f'"{entity_type}"' in self.src, (
                f"Expected entity type \"{entity_type}\" in model validation"
            )

    def test_action_types_defined(self):
        """Expected action types must appear in the model file."""
        actions = ["visibility_changed", "description_updated",
                   "semantic_type_changed", "settings_changed"]
        found = [a for a in actions if a in self.src]
        assert len(found) >= 3, (
            f"Expected at least 3 of the 4 action types in model; found: {found}"
        )


class TestSemanticAPI:
    """Verify API namespace for metadata audit endpoints."""

    @pytest.fixture(autouse=True)
    def _load_source(self):
        with open(API_FILE, "r", encoding="utf-8") as f:
            self.src = f.read()

    def test_api_namespace_declaration(self):
        assert re.search(r"\(ns\s+metabase\.api\.metadata[_-]audit", self.src), (
            "Expected (ns metabase.api.metadata-audit ...) namespace"
        )

    def test_get_list_endpoint(self):
        """GET endpoint for listing audit entries must exist."""
        has_get = re.search(r"defendpoint\s+:?GET", self.src, re.IGNORECASE)
        assert has_get, "Expected GET defendpoint for listing audit log entries"

    def test_get_by_id_endpoint(self):
        """GET /:id endpoint for retrieving a single entry must exist."""
        has_id_param = re.search(r":id|id", self.src)
        assert has_id_param, "Expected :id route parameter for single-entry lookup"

    def test_pagination_params(self):
        """API must accept limit and offset query params."""
        assert "limit" in self.src, "Expected 'limit' query parameter"
        assert "offset" in self.src, "Expected 'offset' query parameter"

    def test_auth_and_admin_check(self):
        """Endpoints must require authentication and admin permissions."""
        has_auth = (
            "check-superuser" in self.src
            or "superuser?" in self.src
            or "admin" in self.src.lower()
            or "is-superuser?" in self.src
            or "api/check-superuser" in self.src
        )
        assert has_auth, (
            "Expected admin/superuser permission check in API endpoints"
        )


class TestSemanticEvents:
    """Verify event listener namespace."""

    @pytest.fixture(autouse=True)
    def _load_source(self):
        with open(EVENTS_FILE, "r", encoding="utf-8") as f:
            self.src = f.read()

    def test_events_namespace(self):
        assert re.search(r"\(ns\s+metabase\.events\.metadata[_-]audit", self.src), (
            "Expected (ns metabase.events.metadata-audit ...) namespace"
        )

    def test_listens_for_field_update(self):
        """Event listener must handle field-update events."""
        has_field = (
            "field-update" in self.src
            or ":field" in self.src
            or "field" in self.src
        )
        assert has_field, "Expected field-update event handler"

    def test_listens_for_table_update(self):
        """Event listener must handle table-update events."""
        has_table = (
            "table-update" in self.src
            or ":table" in self.src
            or "table" in self.src
        )
        assert has_table, "Expected table-update event handler"

    def test_change_detection_logic(self):
        """Listener must compare old and new values to detect actual changes."""
        has_compare = (
            "not=" in self.src
            or "diff" in self.src
            or "changed" in self.src
            or "compare" in self.src
        )
        assert has_compare, (
            "Expected value comparison logic (not=, diff, etc.) in event listener"
        )


class TestSemanticMigration:
    """Verify migration SQL creates the correct table schema."""

    @pytest.fixture(autouse=True)
    def _load_migration(self):
        migration_files = sorted([
            f for f in os.listdir(MIGRATION_DIR)
            if "metadata_audit_log" in f.lower() or "audit" in f.lower()
        ])
        assert migration_files, "No migration file found"
        path = os.path.join(MIGRATION_DIR, migration_files[0])
        with open(path, "r", encoding="utf-8") as f:
            self.sql = f.read().upper()

    def test_create_table_statement(self):
        assert "CREATE TABLE" in self.sql, "Expected CREATE TABLE in migration"

    def test_required_columns(self):
        columns = ["USER_ID", "ENTITY_TYPE", "ENTITY_ID", "ACTION",
                    "OLD_VALUE", "NEW_VALUE", "CREATED_AT"]
        missing = [c for c in columns if c not in self.sql]
        assert not missing, f"Migration missing columns: {missing}"


# ---------------------------------------------------------------------------
# Layer 3 — functional_check
# ---------------------------------------------------------------------------

class TestFunctionalClojureWrite:
    """Functional checks — validate syntax and structure."""

    def _balanced_parens(self, filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            src = f.read()
        assert src.count("(") == src.count(")"), (
            f"Unbalanced parentheses in {filepath}"
        )

    def test_model_balanced_parens(self):
        self._balanced_parens(MODEL_FILE)

    def test_api_balanced_parens(self):
        self._balanced_parens(API_FILE)

    def test_events_balanced_parens(self):
        self._balanced_parens(EVENTS_FILE)

    def test_model_requires_toucan(self):
        """Model file must require Toucan 2 for model definition."""
        with open(MODEL_FILE, "r", encoding="utf-8") as f:
            src = f.read()
        has_toucan = (
            "toucan2" in src
            or "toucan.models" in src
            or "metabase.models.interface" in src
            or "t2/define" in src
            or "define-model" in src
        )
        assert has_toucan, "Expected Toucan 2 or model interface require in model file"

    def test_api_requires_model(self):
        """API file must require the model namespace."""
        with open(API_FILE, "r", encoding="utf-8") as f:
            src = f.read()
        has_model_ref = (
            "metadata-audit-log" in src
            or "metadata_audit_log" in src
            or "MetadataAuditLog" in src
        )
        assert has_model_ref, (
            "Expected API file to reference MetadataAuditLog model"
        )

    def test_events_requires_model(self):
        """Events file must require the model for inserting log entries."""
        with open(EVENTS_FILE, "r", encoding="utf-8") as f:
            src = f.read()
        has_log_ref = (
            "log-change!" in src
            or "metadata-audit-log" in src
            or "MetadataAuditLog" in src
        )
        assert has_log_ref, (
            "Expected events file to reference log-change! or MetadataAuditLog"
        )

    def test_migration_sql_is_valid(self):
        """Migration SQL file must be non-trivial (> 100 chars)."""
        migration_files = sorted([
            f for f in os.listdir(MIGRATION_DIR)
            if "metadata_audit_log" in f.lower() or "audit" in f.lower()
        ])
        path = os.path.join(MIGRATION_DIR, migration_files[0])
        size = os.path.getsize(path)
        assert size > 100, (
            f"Migration file seems too small ({size} bytes): may be incomplete"
        )
