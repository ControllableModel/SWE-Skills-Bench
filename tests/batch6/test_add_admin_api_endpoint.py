"""
Test skill: add-admin-api-endpoint
Verify that the Agent correctly adds a Webhooks CRUD Admin API endpoint to Ghost CMS.
"""

import os
import re
import json
import subprocess
import pytest


class TestAddAdminApiEndpoint:
    REPO_DIR = "/workspace/Ghost"

    # === File Path Checks ===

    def test_webhooks_endpoint_file_exists(self):
        """Verify that the webhooks API controller file exists"""
        path = os.path.join(self.REPO_DIR, "ghost/core/core/server/api/endpoints/webhooks.js")
        assert os.path.exists(path), f"webhooks.js endpoint not found at {path}"

    def test_admin_routes_file_exists(self):
        """Verify that the admin routes file exists"""
        path = os.path.join(self.REPO_DIR, "ghost/core/core/server/web/api/endpoints/admin/routes.js")
        assert os.path.exists(path), f"admin routes.js not found at {path}"

    def test_e2e_test_file_exists(self):
        """Verify that the E2E test file for webhooks exists"""
        path = os.path.join(self.REPO_DIR, "ghost/core/test/e2e-api/admin/webhooks.test.js")
        assert os.path.exists(path), f"webhooks.test.js not found at {path}"

    # === Semantic Checks ===

    def test_webhooks_controller_has_docname(self):
        """Verify that webhooks controller exports docName as 'webhooks'"""
        path = os.path.join(self.REPO_DIR, "ghost/core/core/server/api/endpoints/webhooks.js")
        with open(path, "r") as f:
            content = f.read()

        assert "docName" in content, "Webhooks controller missing docName property"
        # Verify docName value is 'webhooks'
        docname_pattern = re.compile(r"""docName\s*[:=]\s*['"]webhooks['"]""")
        assert docname_pattern.search(content), (
            "docName should be 'webhooks', but pattern not found"
        )

    def test_webhooks_controller_has_all_crud_methods(self):
        """Verify that webhooks controller defines browse, read, add, edit, destroy"""
        path = os.path.join(self.REPO_DIR, "ghost/core/core/server/api/endpoints/webhooks.js")
        with open(path, "r") as f:
            content = f.read()

        required_methods = ["browse", "read", "add", "edit", "destroy"]
        for method in required_methods:
            assert method in content, (
                f"Webhooks controller missing '{method}' method"
            )

    def test_webhooks_controller_validates_target_url_https(self):
        """Verify that add/edit methods validate that target_url uses HTTPS"""
        path = os.path.join(self.REPO_DIR, "ghost/core/core/server/api/endpoints/webhooks.js")
        with open(path, "r") as f:
            content = f.read()

        has_https_validation = any(kw in content for kw in [
            "https", "HTTPS", "target_url must use HTTPS",
            "target_url", "protocol",
        ])
        assert has_https_validation, (
            "Webhooks controller should validate that target_url uses HTTPS scheme"
        )

    def test_webhooks_controller_validates_event_types(self):
        """Verify that controller validates event types against allowed list"""
        path = os.path.join(self.REPO_DIR, "ghost/core/core/server/api/endpoints/webhooks.js")
        with open(path, "r") as f:
            content = f.read()

        allowed_events = [
            "post.published", "post.unpublished", "post.deleted",
            "page.published", "page.unpublished", "page.deleted",
            "member.added", "member.deleted",
        ]
        found_events = sum(1 for event in allowed_events if event in content)
        assert found_events >= 4, (
            f"Webhooks controller should define allowed event types. "
            f"Found {found_events} of {len(allowed_events)} expected events"
        )

    def test_admin_routes_has_webhook_routes(self):
        """Verify that admin routes file registers all webhook HTTP routes"""
        path = os.path.join(self.REPO_DIR, "ghost/core/core/server/web/api/endpoints/admin/routes.js")
        with open(path, "r") as f:
            content = f.read()

        assert "webhooks" in content, (
            "Admin routes file should register webhook routes"
        )

        # Check for HTTP methods
        has_get = re.search(r"(get|GET).*webhooks", content)
        has_post = re.search(r"(post|POST).*webhooks", content)
        has_put = re.search(r"(put|PUT).*webhooks", content)
        has_delete = re.search(r"(delete|DELETE|del).*webhooks", content)

        assert has_get, "Admin routes missing GET /webhooks/ route"
        assert has_post, "Admin routes missing POST /webhooks/ route"
        assert has_put, "Admin routes missing PUT /webhooks/:id/ route"
        assert has_delete, "Admin routes missing DELETE /webhooks/:id/ route"

    def test_webhooks_controller_requires_admin_permission(self):
        """Verify that webhook operations require admin permissions"""
        path = os.path.join(self.REPO_DIR, "ghost/core/core/server/api/endpoints/webhooks.js")
        with open(path, "r") as f:
            content = f.read()

        has_permission = any(kw in content for kw in [
            "permissions", "permission", "admin", "isAdmin",
        ])
        assert has_permission, (
            "Webhooks controller should require admin permissions for all operations"
        )

    def test_webhooks_controller_cache_invalidation(self):
        """Verify that add/edit/destroy invalidate cache"""
        path = os.path.join(self.REPO_DIR, "ghost/core/core/server/api/endpoints/webhooks.js")
        with open(path, "r") as f:
            content = f.read()

        has_cache_handling = any(kw in content for kw in [
            "cache", "invalidate", "Cache",
        ])
        assert has_cache_handling, (
            "Webhooks controller should handle cache invalidation on mutations"
        )

    # === Functional Checks ===

    def test_e2e_tests_cover_crud_operations(self):
        """Verify that E2E tests cover all CRUD operations"""
        path = os.path.join(self.REPO_DIR, "ghost/core/test/e2e-api/admin/webhooks.test.js")
        with open(path, "r") as f:
            content = f.read()

        # Check for creation test
        assert "POST" in content or "add" in content or "create" in content.lower(), (
            "E2E tests should include webhook creation test"
        )
        # Check for read/browse test
        assert "GET" in content or "browse" in content or "read" in content, (
            "E2E tests should include webhook read/browse test"
        )
        # Check for update test
        assert "PUT" in content or "edit" in content or "update" in content.lower(), (
            "E2E tests should include webhook update test"
        )
        # Check for delete test
        assert "DELETE" in content or "destroy" in content or "delete" in content.lower(), (
            "E2E tests should include webhook delete test"
        )

    def test_e2e_tests_cover_validation_failures(self):
        """Verify that E2E tests include validation error scenarios"""
        path = os.path.join(self.REPO_DIR, "ghost/core/test/e2e-api/admin/webhooks.test.js")
        with open(path, "r") as f:
            content = f.read()

        has_validation_test = any(kw in content for kw in [
            "422", "validation", "invalid", "http://", "Invalid event",
        ])
        assert has_validation_test, (
            "E2E tests should include validation failure scenarios "
            "(e.g., HTTP URL, invalid event type)"
        )

    def test_e2e_tests_cover_404_handling(self):
        """Verify that E2E tests include 404 not-found scenarios"""
        path = os.path.join(self.REPO_DIR, "ghost/core/test/e2e-api/admin/webhooks.test.js")
        with open(path, "r") as f:
            content = f.read()

        assert "404" in content or "not found" in content.lower() or "NotFound" in content, (
            "E2E tests should include 404 not-found scenarios"
        )

    def test_webhooks_js_is_valid_javascript(self):
        """Verify that the webhooks.js file is valid JavaScript syntax"""
        path = os.path.join(self.REPO_DIR, "ghost/core/core/server/api/endpoints/webhooks.js")
        result = subprocess.run(
            ["node", "-c", path],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=30,
        )
        # node -c checks syntax
        if result.returncode != 0:
            # Try alternative: node --check
            result = subprocess.run(
                ["node", "--check", path],
                cwd=self.REPO_DIR,
                capture_output=True,
                text=True,
                timeout=30,
            )
        assert result.returncode == 0, (
            f"webhooks.js has JavaScript syntax errors: {result.stderr}"
        )

    def test_webhooks_controller_module_exports(self):
        """Verify that webhooks.js properly exports the controller module"""
        path = os.path.join(self.REPO_DIR, "ghost/core/core/server/api/endpoints/webhooks.js")
        with open(path, "r") as f:
            content = f.read()

        has_export = "module.exports" in content or "export" in content
        assert has_export, (
            "webhooks.js should export the controller (module.exports or export)"
        )
