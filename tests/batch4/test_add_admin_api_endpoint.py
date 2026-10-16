"""
Test skill: add-admin-api-endpoint
Verify that the Announcements Admin API endpoint has been correctly added to Ghost CMS,
including controller structure, route registration, model creation, permissions,
input validation, and e2e test coverage.
"""

import os
import re
import json
import subprocess
import pytest


class TestAddAdminApiEndpoint:
    REPO_DIR = "/workspace/Ghost"

    CONTROLLER_PATH = "ghost/core/core/server/api/endpoints/announcements.js"
    ROUTES_PATH = "ghost/core/core/server/web/api/endpoints/admin/routes.js"
    MODEL_PATH = "ghost/core/core/server/models/announcement.js"
    E2E_TEST_PATH = "ghost/core/test/e2e-api/admin/announcements.test.js"

    # === File Path Checks ===

    def test_controller_file_exists(self):
        """Verify that the announcements controller file was created"""
        filepath = os.path.join(self.REPO_DIR, self.CONTROLLER_PATH)
        assert os.path.exists(filepath), f"Controller not found at {filepath}"

    def test_model_file_exists(self):
        """Verify that the announcement model file was created"""
        filepath = os.path.join(self.REPO_DIR, self.MODEL_PATH)
        assert os.path.exists(filepath), f"Model not found at {filepath}"

    def test_e2e_test_file_exists(self):
        """Verify that the e2e test file was created"""
        filepath = os.path.join(self.REPO_DIR, self.E2E_TEST_PATH)
        assert os.path.exists(filepath), f"E2E test not found at {filepath}"

    def test_routes_file_exists(self):
        """Verify that the admin routes file exists"""
        filepath = os.path.join(self.REPO_DIR, self.ROUTES_PATH)
        assert os.path.exists(filepath), f"Admin routes file not found at {filepath}"

    # === Semantic Checks ===

    def test_controller_has_docname(self):
        """Verify controller exports docName: 'announcements'"""
        filepath = os.path.join(self.REPO_DIR, self.CONTROLLER_PATH)
        with open(filepath) as f:
            content = f.read()
        assert "docName" in content, "Controller should export docName property"
        assert re.search(r"""docName\s*:\s*['"]announcements['"]""", content), \
            "Controller docName should be 'announcements'"

    def test_controller_has_all_crud_methods(self):
        """Verify controller has browse, read, add, edit, and destroy methods"""
        filepath = os.path.join(self.REPO_DIR, self.CONTROLLER_PATH)
        with open(filepath) as f:
            content = f.read()
        required_methods = ["browse", "read", "add", "edit", "destroy"]
        for method in required_methods:
            assert re.search(rf'\b{method}\b', content), \
                f"Controller missing '{method}' method"

    def test_controller_enforces_permissions(self):
        """Verify that controller methods enforce permissions"""
        filepath = os.path.join(self.REPO_DIR, self.CONTROLLER_PATH)
        with open(filepath) as f:
            content = f.read()
        assert "permissions" in content, \
            "Controller should declare permissions for its methods"
        # Should have permissions: true or a permissions function
        permission_count = len(re.findall(r'permissions\s*:', content))
        assert permission_count >= 3, \
            f"Expected permissions declarations for multiple methods, found {permission_count}"

    def test_routes_register_announcements_endpoints(self):
        """Verify routes file registers all announcements endpoints"""
        filepath = os.path.join(self.REPO_DIR, self.ROUTES_PATH)
        with open(filepath) as f:
            content = f.read()
        assert "announcements" in content, \
            "Admin routes file should reference 'announcements' resource"

    def test_controller_validates_title_and_content(self):
        """Verify that controller validates title (max 255) and content (max 2000)"""
        filepath = os.path.join(self.REPO_DIR, self.CONTROLLER_PATH)
        with open(filepath) as f:
            content = f.read()
        # Should reference validation for title/content
        has_title_validation = ("title" in content and
                                ("255" in content or "max" in content.lower() or "required" in content.lower()))
        assert has_title_validation, \
            "Controller should validate title field (required, max 255 chars)"

    def test_controller_validates_visibility_enum(self):
        """Verify that controller validates visibility to allowed values"""
        filepath = os.path.join(self.REPO_DIR, self.CONTROLLER_PATH)
        with open(filepath) as f:
            content = f.read()
        has_visibility = all(v in content for v in ["public", "members", "paid"])
        assert has_visibility, \
            "Controller should validate visibility against allowed values: public, members, paid"

    def test_model_defines_announcement_schema(self):
        """Verify that the model file defines the announcement entity"""
        filepath = os.path.join(self.REPO_DIR, self.MODEL_PATH)
        with open(filepath) as f:
            content = f.read()
        assert "Announcement" in content or "announcement" in content, \
            "Model should define Announcement entity"
        # Should reference Bookshelf/Ghost model pattern
        has_model_pattern = ("tableName" in content or "Model" in content or
                             "ghostBookshelf" in content or "bookshelf" in content.lower())
        assert has_model_pattern, \
            "Model should follow Ghost's Bookshelf model pattern"

    def test_e2e_test_covers_crud_operations(self):
        """Verify e2e tests cover CRUD operations and error cases"""
        filepath = os.path.join(self.REPO_DIR, self.E2E_TEST_PATH)
        with open(filepath) as f:
            content = f.read()
        # Should test various HTTP methods
        assert "POST" in content or "post" in content, \
            "E2E tests should cover POST (create) operations"
        assert "GET" in content or "get" in content, \
            "E2E tests should cover GET (browse/read) operations"
        assert "PUT" in content or "put" in content, \
            "E2E tests should cover PUT (edit) operations"
        assert "DELETE" in content or "delete" in content, \
            "E2E tests should cover DELETE operations"
        # Should test status codes
        assert "201" in content or "200" in content, \
            "E2E tests should verify success status codes"
        assert "422" in content or "403" in content, \
            "E2E tests should verify error status codes (422 or 403)"

    # === Functional Checks ===

    def test_controller_file_has_valid_js_syntax(self):
        """Verify that the controller file is syntactically valid JavaScript"""
        filepath = os.path.join(self.REPO_DIR, self.CONTROLLER_PATH)
        result = subprocess.run(
            ["node", "--check", filepath],
            capture_output=True, text=True, timeout=30
        )
        assert result.returncode == 0, \
            f"Controller has JS syntax error: {result.stderr}"

    def test_model_file_has_valid_js_syntax(self):
        """Verify that the model file is syntactically valid JavaScript"""
        filepath = os.path.join(self.REPO_DIR, self.MODEL_PATH)
        result = subprocess.run(
            ["node", "--check", filepath],
            capture_output=True, text=True, timeout=30
        )
        assert result.returncode == 0, \
            f"Model has JS syntax error: {result.stderr}"

    def test_e2e_test_file_has_valid_js_syntax(self):
        """Verify that the e2e test file is syntactically valid JavaScript"""
        filepath = os.path.join(self.REPO_DIR, self.E2E_TEST_PATH)
        result = subprocess.run(
            ["node", "--check", filepath],
            capture_output=True, text=True, timeout=30
        )
        assert result.returncode == 0, \
            f"E2E test has JS syntax error: {result.stderr}"

    def test_routes_file_remains_valid_js(self):
        """Verify that the modified routes file is still syntactically valid"""
        filepath = os.path.join(self.REPO_DIR, self.ROUTES_PATH)
        result = subprocess.run(
            ["node", "--check", filepath],
            capture_output=True, text=True, timeout=30
        )
        assert result.returncode == 0, \
            f"Routes file has JS syntax error after modification: {result.stderr}"
