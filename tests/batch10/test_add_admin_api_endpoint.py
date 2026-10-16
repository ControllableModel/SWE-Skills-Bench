"""
Test skill: add-admin-api-endpoint
Verify that the Agent correctly creates an Announcements Admin API endpoint
in the Ghost CMS repository following Ghost's framework conventions.
"""

import os
import re
import json
import subprocess
import pytest


class TestAddAdminApiEndpoint:
    REPO_DIR = "/workspace/Ghost"

    # === File Path Checks ===

    def test_announcements_controller_exists(self):
        """Verify the announcements API controller file was created"""
        path = os.path.join(
            self.REPO_DIR,
            "ghost/core/core/server/api/endpoints/announcements.js",
        )
        assert os.path.exists(path), f"Announcements controller not found at {path}"

    def test_announcement_model_exists(self):
        """Verify the Announcement Bookshelf model file was created"""
        path = os.path.join(
            self.REPO_DIR,
            "ghost/core/core/server/models/announcement.js",
        )
        assert os.path.exists(path), f"Announcement model not found at {path}"

    def test_e2e_test_file_exists(self):
        """Verify the e2e test file was created"""
        path = os.path.join(
            self.REPO_DIR,
            "ghost/core/test/e2e-api/admin/announcements.test.js",
        )
        assert os.path.exists(path), f"E2E test file not found at {path}"

    # === Semantic Checks ===

    def test_controller_has_docname_announcements(self):
        """Verify controller exports docName: 'announcements'"""
        path = os.path.join(
            self.REPO_DIR,
            "ghost/core/core/server/api/endpoints/announcements.js",
        )
        with open(path) as f:
            content = f.read()
        assert re.search(r"""docName\s*:\s*['"]announcements['"]""", content), (
            "Controller must have docName: 'announcements'"
        )

    def test_controller_has_all_crud_methods(self):
        """Verify controller defines browse, read, add, edit, destroy methods"""
        path = os.path.join(
            self.REPO_DIR,
            "ghost/core/core/server/api/endpoints/announcements.js",
        )
        with open(path) as f:
            content = f.read()
        required_methods = ["browse", "read", "add", "edit", "destroy"]
        for method in required_methods:
            assert re.search(rf'\b{method}\b', content), (
                f"Controller missing '{method}' method"
            )

    def test_controller_methods_have_permissions(self):
        """Verify every controller method has explicit permissions property"""
        path = os.path.join(
            self.REPO_DIR,
            "ghost/core/core/server/api/endpoints/announcements.js",
        )
        with open(path) as f:
            content = f.read()
        assert content.count("permissions") >= 5, (
            "Each of the 5 CRUD methods should have a 'permissions' property"
        )

    def test_model_sets_table_name(self):
        """Verify model sets tableName to 'announcements'"""
        path = os.path.join(
            self.REPO_DIR,
            "ghost/core/core/server/models/announcement.js",
        )
        with open(path) as f:
            content = f.read()
        assert re.search(r"""tableName\s*:\s*['"]announcements['"]""", content), (
            "Model must have tableName: 'announcements'"
        )

    def test_model_registers_with_bookshelf(self):
        """Verify model registers via ghostBookshelf.model"""
        path = os.path.join(
            self.REPO_DIR,
            "ghost/core/core/server/models/announcement.js",
        )
        with open(path) as f:
            content = f.read()
        has_registration = (
            "ghostBookshelf.model" in content
            or "module.exports" in content
        )
        assert has_registration, (
            "Model should register itself via ghostBookshelf.model or module.exports"
        )

    def test_routes_registered_for_announcements(self):
        """Verify admin routes.js registers announcement routes"""
        path = os.path.join(
            self.REPO_DIR,
            "ghost/core/core/server/web/api/endpoints/admin/routes.js",
        )
        assert os.path.exists(path), f"Admin routes.js not found at {path}"
        with open(path) as f:
            content = f.read()
        assert "announcements" in content, (
            "Admin routes.js must register announcement routes"
        )
        # Check for key HTTP methods
        route_patterns = [
            r"""(get|router\.get)\s*\(\s*['"].*announcements""",
            r"""(post|router\.post)\s*\(\s*['"].*announcements""",
            r"""(put|router\.put)\s*\(\s*['"].*announcements""",
            r"""(delete|router\.del|router\.delete)\s*\(\s*['"].*announcements""",
        ]
        for pattern in route_patterns:
            assert re.search(pattern, content, re.IGNORECASE), (
                f"Routes missing pattern: {pattern}"
            )

    def test_schema_has_announcements_table(self):
        """Verify schema.js defines the announcements table"""
        path = os.path.join(
            self.REPO_DIR,
            "ghost/core/core/server/data/schema/schema.js",
        )
        assert os.path.exists(path), f"Schema file not found at {path}"
        with open(path) as f:
            content = f.read()
        assert "announcements" in content, (
            "Schema must define 'announcements' table"
        )
        # Check for required columns
        for col in ["title", "content", "visibility", "starts_at", "ends_at"]:
            assert col in content, f"Schema missing column: {col}"

    def test_controller_add_returns_201(self):
        """Verify the add method specifies status code 201"""
        path = os.path.join(
            self.REPO_DIR,
            "ghost/core/core/server/api/endpoints/announcements.js",
        )
        with open(path) as f:
            content = f.read()
        assert "201" in content, "add method should specify status code 201"

    def test_controller_destroy_returns_204(self):
        """Verify the destroy method specifies status code 204"""
        path = os.path.join(
            self.REPO_DIR,
            "ghost/core/core/server/api/endpoints/announcements.js",
        )
        with open(path) as f:
            content = f.read()
        assert "204" in content, "destroy method should specify status code 204"

    def test_controller_validates_visibility(self):
        """Verify the controller validates visibility values"""
        path = os.path.join(
            self.REPO_DIR,
            "ghost/core/core/server/api/endpoints/announcements.js",
        )
        with open(path) as f:
            content = f.read()
        for val in ["public", "members", "paid"]:
            assert val in content, (
                f"Controller should validate visibility value '{val}'"
            )

    # === Functional Checks ===

    def test_e2e_test_covers_browse(self):
        """Verify e2e test file tests the browse endpoint"""
        path = os.path.join(
            self.REPO_DIR,
            "ghost/core/test/e2e-api/admin/announcements.test.js",
        )
        with open(path) as f:
            content = f.read()
        assert "browse" in content.lower() or "GET" in content, (
            "E2E tests should cover the browse (GET list) endpoint"
        )

    def test_e2e_test_covers_add_and_validation(self):
        """Verify e2e tests cover add endpoint and validation errors"""
        path = os.path.join(
            self.REPO_DIR,
            "ghost/core/test/e2e-api/admin/announcements.test.js",
        )
        with open(path) as f:
            content = f.read()
        assert "POST" in content or "add" in content, (
            "E2E tests should cover the add (POST) endpoint"
        )
        assert "422" in content, (
            "E2E tests should verify 422 validation errors"
        )

    def test_e2e_test_covers_destroy(self):
        """Verify e2e tests cover the destroy endpoint returning 204"""
        path = os.path.join(
            self.REPO_DIR,
            "ghost/core/test/e2e-api/admin/announcements.test.js",
        )
        with open(path) as f:
            content = f.read()
        assert "DELETE" in content or "destroy" in content, (
            "E2E tests should cover the destroy (DELETE) endpoint"
        )
        assert "204" in content, (
            "E2E tests should verify 204 status code on destroy"
        )

    def test_schema_id_column_correct_type(self):
        """Verify schema defines id column as string with maxlength 24"""
        path = os.path.join(
            self.REPO_DIR,
            "ghost/core/core/server/data/schema/schema.js",
        )
        with open(path) as f:
            content = f.read()
        # Find the announcements section and verify id column spec
        assert "24" in content, (
            "Schema id column should have maxlength 24 for ObjectId format"
        )
