"""
Test skill: add-admin-api-endpoint
Verify that the Agent correctly adds a Bookmarks Admin API endpoint to Ghost CMS.
"""

import os
import json
import re
import subprocess
import pytest


class TestAddAdminApiEndpoint:
    REPO_DIR = "/workspace/Ghost"

    # === File Path Checks ===

    def test_bookmarks_controller_exists(self):
        """Verify the bookmarks API controller file was created"""
        path = os.path.join(
            self.REPO_DIR,
            "ghost/core/core/server/api/endpoints/bookmarks.js"
        )
        assert os.path.exists(path), f"Bookmarks controller not found at {path}"

    def test_bookmark_model_exists(self):
        """Verify the bookmark model file was created"""
        path = os.path.join(
            self.REPO_DIR,
            "ghost/core/core/server/models/bookmark.js"
        )
        assert os.path.exists(path), f"Bookmark model not found at {path}"

    def test_bookmarks_e2e_tests_exist(self):
        """Verify e2e tests were created for the bookmarks API"""
        path = os.path.join(
            self.REPO_DIR,
            "ghost/core/test/e2e-api/admin/bookmarks.test.js"
        )
        assert os.path.exists(path), f"Bookmarks e2e tests not found at {path}"

    # === Semantic Checks ===

    def test_schema_has_bookmarks_table(self):
        """Verify the database schema includes a bookmarks table definition"""
        schema_path = os.path.join(
            self.REPO_DIR,
            "ghost/core/core/server/data/schema/schema.js"
        )
        assert os.path.exists(schema_path), f"Schema file not found at {schema_path}"
        with open(schema_path) as f:
            content = f.read()
        assert "bookmarks" in content, \
            "Schema.js does not contain a 'bookmarks' table definition"

    def test_schema_bookmarks_table_has_required_columns(self):
        """Verify bookmarks table schema has required columns: id, user_id, post_id, created_at, note"""
        schema_path = os.path.join(
            self.REPO_DIR,
            "ghost/core/core/server/data/schema/schema.js"
        )
        with open(schema_path) as f:
            content = f.read()
        required_columns = ["user_id", "post_id", "created_at", "note"]
        for col in required_columns:
            assert col in content, \
                f"bookmarks schema missing column: {col}"

    def test_controller_has_crud_actions(self):
        """Verify bookmarks controller implements browse, read, add, destroy"""
        path = os.path.join(
            self.REPO_DIR,
            "ghost/core/core/server/api/endpoints/bookmarks.js"
        )
        with open(path) as f:
            content = f.read()
        actions = ["browse", "read", "add", "destroy"]
        for action in actions:
            assert action in content, \
                f"Bookmarks controller missing action: {action}"

    def test_controller_has_jsdoc(self):
        """Verify controller methods have JSDoc documentation"""
        path = os.path.join(
            self.REPO_DIR,
            "ghost/core/core/server/api/endpoints/bookmarks.js"
        )
        with open(path) as f:
            content = f.read()
        # JSDoc should contain @param or @returns or @description
        jsdoc_patterns = ["@param", "@returns", "@description"]
        found = sum(1 for p in jsdoc_patterns if p in content)
        assert found >= 1, \
            "Controller should have JSDoc documentation with @param, @returns, or @description"

    def test_routes_register_bookmark_endpoints(self):
        """Verify routes.js registers bookmark endpoints"""
        routes_path = os.path.join(
            self.REPO_DIR,
            "ghost/core/core/server/web/api/endpoints/admin/routes.js"
        )
        assert os.path.exists(routes_path), f"Admin routes file not found at {routes_path}"
        with open(routes_path) as f:
            content = f.read()
        assert "bookmark" in content.lower(), \
            "Admin routes.js does not reference bookmarks endpoints"

    def test_model_has_correct_structure(self):
        """Verify bookmark model defines tableName, relationships, and permittedAttributes"""
        path = os.path.join(
            self.REPO_DIR,
            "ghost/core/core/server/models/bookmark.js"
        )
        with open(path) as f:
            content = f.read()
        assert "bookmarks" in content, \
            "Model should define tableName 'bookmarks'"
        # Check for relationship definitions
        has_relationships = (
            "belongsTo" in content or
            "Post" in content or
            "User" in content
        )
        assert has_relationships, \
            "Model should define relationships to Post and User"

    def test_model_permitted_attributes(self):
        """Verify model defines permittedAttributes with required fields"""
        path = os.path.join(
            self.REPO_DIR,
            "ghost/core/core/server/models/bookmark.js"
        )
        with open(path) as f:
            content = f.read()
        assert "permittedAttributes" in content, \
            "Model should define permittedAttributes"
        expected_attrs = ["user_id", "post_id", "note"]
        for attr in expected_attrs:
            assert attr in content, \
                f"permittedAttributes should include '{attr}'"

    # === Functional Checks ===

    def test_controller_file_is_valid_js(self):
        """Verify the controller file is valid JavaScript by parsing with node"""
        path = os.path.join(
            self.REPO_DIR,
            "ghost/core/core/server/api/endpoints/bookmarks.js"
        )
        result = subprocess.run(
            ["node", "-e", f"require('{path}')"],
            cwd=self.REPO_DIR,
            capture_output=True, text=True, timeout=30
        )
        # May fail due to missing deps, but shouldn't be a syntax error
        if result.returncode != 0:
            assert "SyntaxError" not in result.stderr, \
                f"Bookmarks controller has JavaScript syntax errors: {result.stderr[:500]}"

    def test_model_file_is_valid_js(self):
        """Verify the bookmark model file has valid JavaScript syntax"""
        path = os.path.join(
            self.REPO_DIR,
            "ghost/core/core/server/models/bookmark.js"
        )
        result = subprocess.run(
            ["node", "-e", f"require('{path}')"],
            cwd=self.REPO_DIR,
            capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            assert "SyntaxError" not in result.stderr, \
                f"Bookmark model has JavaScript syntax errors: {result.stderr[:500]}"

    def test_e2e_tests_file_is_valid_js(self):
        """Verify the e2e test file has valid JavaScript syntax"""
        path = os.path.join(
            self.REPO_DIR,
            "ghost/core/test/e2e-api/admin/bookmarks.test.js"
        )
        result = subprocess.run(
            ["node", "--check", path],
            cwd=self.REPO_DIR,
            capture_output=True, text=True, timeout=30
        )
        assert result.returncode == 0, \
            f"E2E test file has syntax errors: {result.stderr[:500]}"

    def test_e2e_tests_cover_crud_operations(self):
        """Verify e2e tests cover all CRUD operations"""
        path = os.path.join(
            self.REPO_DIR,
            "ghost/core/test/e2e-api/admin/bookmarks.test.js"
        )
        with open(path) as f:
            content = f.read()
        # Check for test coverage of key operations
        crud_indicators = {
            "GET": ["GET", "get", "browse", "list", "read"],
            "POST": ["POST", "post", "add", "create"],
            "DELETE": ["DELETE", "delete", "destroy", "remove"],
        }
        for method, indicators in crud_indicators.items():
            found = any(ind in content for ind in indicators)
            assert found, \
                f"E2E tests should cover {method} operations for bookmarks"

    def test_e2e_tests_cover_error_scenarios(self):
        """Verify e2e tests check error scenarios (404, 422)"""
        path = os.path.join(
            self.REPO_DIR,
            "ghost/core/test/e2e-api/admin/bookmarks.test.js"
        )
        with open(path) as f:
            content = f.read()
        error_indicators = ["404", "422", "not found", "already exists", "duplicate", "invalid"]
        found = sum(1 for ind in error_indicators if ind.lower() in content.lower())
        assert found >= 2, \
            f"E2E tests should cover error scenarios (404, 422). Only found {found} error indicators"
