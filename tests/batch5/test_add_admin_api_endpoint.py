"""
Test skill: add-admin-api-endpoint
Verify that the Agent correctly adds a Bookmarks Admin API endpoint
to the Ghost publishing platform.
"""

import os
import re
import json
import subprocess
import pytest


class TestAddAdminApiEndpoint:
    REPO_DIR = "/workspace/Ghost"

    BOOKMARKS_CTRL = "ghost/core/core/server/api/endpoints/bookmarks.js"
    ENDPOINTS_INDEX = "ghost/core/core/server/api/endpoints/index.js"
    BOOKMARK_MODEL = "ghost/core/core/server/models/bookmark.js"
    SCHEMA_FILE = "ghost/core/core/server/data/schema/schema.js"
    E2E_TEST = "ghost/core/test/e2e-api/admin/bookmarks.test.js"

    def _read_file(self, rel_path):
        filepath = os.path.join(self.REPO_DIR, rel_path)
        with open(filepath) as f:
            return f.read()

    # === File Path Checks ===

    def test_bookmarks_controller_exists(self):
        """Verify bookmarks.js controller file exists"""
        filepath = os.path.join(self.REPO_DIR, self.BOOKMARKS_CTRL)
        assert os.path.exists(filepath), f"bookmarks.js not found at {filepath}"

    def test_bookmark_model_exists(self):
        """Verify bookmark.js model file exists"""
        filepath = os.path.join(self.REPO_DIR, self.BOOKMARK_MODEL)
        assert os.path.exists(filepath), f"bookmark.js model not found at {filepath}"

    def test_e2e_test_file_exists(self):
        """Verify e2e test file for bookmarks exists"""
        filepath = os.path.join(self.REPO_DIR, self.E2E_TEST)
        assert os.path.exists(filepath), f"E2E test file not found at {filepath}"

    # === Semantic Checks ===

    def test_controller_has_all_crud_actions(self):
        """Verify bookmarks controller implements browse, read, add, edit, destroy"""
        content = self._read_file(self.BOOKMARKS_CTRL)
        for action in ["browse", "read", "add", "edit", "destroy"]:
            assert action in content, \
                f"Bookmarks controller missing '{action}' action"

    def test_controller_registered_in_index(self):
        """Verify bookmarks controller is registered in the endpoints index"""
        content = self._read_file(self.ENDPOINTS_INDEX)
        assert "bookmark" in content.lower(), \
            "Bookmarks controller not registered in endpoints/index.js"

    def test_schema_defines_bookmarks_table(self):
        """Verify schema.js defines the bookmarks table with required columns"""
        content = self._read_file(self.SCHEMA_FILE)
        assert "bookmarks" in content, \
            "Schema file missing 'bookmarks' table definition"
        required_columns = ["title", "url"]
        for col in required_columns:
            assert col in content, \
                f"Schema missing required column '{col}' in bookmarks table"

    def test_bookmark_model_defines_table_name(self):
        """Verify bookmark model references the bookmarks table"""
        content = self._read_file(self.BOOKMARK_MODEL)
        assert "bookmarks" in content or "Bookmark" in content, \
            "Bookmark model missing table name reference"

    def test_controller_validates_required_fields(self):
        """Verify controller or model validates title and url as required"""
        ctrl_content = self._read_file(self.BOOKMARKS_CTRL)
        model_content = self._read_file(self.BOOKMARK_MODEL)
        combined = ctrl_content + model_content
        has_title_required = bool(re.search(
            r'(required|notNull|validate.*title|title.*required)', combined, re.IGNORECASE
        ))
        has_url_required = bool(re.search(
            r'(required|notNull|validate.*url|url.*required)', combined, re.IGNORECASE
        ))
        assert has_title_required, \
            "No validation found requiring 'title' field for bookmarks"
        assert has_url_required, \
            "No validation found requiring 'url' field for bookmarks"

    def test_schema_has_bookmarks_tags_join_table(self):
        """Verify schema defines bookmarks_tags join table for many-to-many"""
        content = self._read_file(self.SCHEMA_FILE)
        assert "bookmarks_tags" in content, \
            "Schema missing bookmarks_tags join table for tag associations"

    def test_e2e_test_covers_crud_and_validation(self):
        """Verify e2e tests cover all CRUD actions and validation errors"""
        content = self._read_file(self.E2E_TEST)
        for action_keyword in ["POST", "GET", "PUT", "DELETE"]:
            assert action_keyword in content, \
                f"E2E tests missing {action_keyword} request coverage"
        has_validation_test = bool(re.search(
            r'(422|validation|required|error)', content, re.IGNORECASE
        ))
        assert has_validation_test, \
            "E2E tests missing validation error scenario"

    # === Functional Checks ===

    def test_bookmarks_controller_is_valid_javascript(self):
        """Verify bookmarks.js is parseable JavaScript using Node.js"""
        filepath = os.path.join(self.REPO_DIR, self.BOOKMARKS_CTRL)
        result = subprocess.run(
            ["node", "-e", f"require('{filepath}')"],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=self.REPO_DIR,
        )
        if result.returncode != 0:
            # Try syntax check only
            result = subprocess.run(
                ["node", "--check", filepath],
                capture_output=True,
                text=True,
                timeout=30,
            )
        assert result.returncode == 0, \
            f"bookmarks.js has JavaScript errors: {result.stderr[:500]}"

    def test_bookmark_model_is_valid_javascript(self):
        """Verify bookmark.js model is parseable JavaScript"""
        filepath = os.path.join(self.REPO_DIR, self.BOOKMARK_MODEL)
        result = subprocess.run(
            ["node", "--check", filepath],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, \
            f"bookmark.js model has JavaScript errors: {result.stderr[:500]}"

    def test_controller_exports_standard_api_shape(self):
        """Verify controller module exports object with expected action keys"""
        filepath = os.path.join(self.REPO_DIR, self.BOOKMARKS_CTRL)
        content = self._read_file(self.BOOKMARKS_CTRL)
        # Ghost controllers export an object with action names as keys
        has_module_export = bool(re.search(
            r'module\.exports\s*=', content
        ))
        assert has_module_export, \
            "bookmarks.js controller does not export via module.exports"
        exported_actions = re.findall(
            r'(browse|read|add|edit|destroy)\s*[:\(]', content
        )
        assert len(set(exported_actions)) >= 5, \
            f"Expected 5 CRUD actions exported, found: {set(exported_actions)}"
