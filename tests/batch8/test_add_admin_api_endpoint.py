"""
Test skill: add-admin-api-endpoint
Verify that the Agent correctly adds a Webhooks Admin API endpoint to Ghost,
including CRUD operations, validation, authentication, and response format.
"""

import os
import subprocess
import re
import json
import pytest


class TestAddAdminApiEndpoint:
    REPO_DIR = "/workspace/Ghost"

    # === File Path Checks ===

    def test_webhooks_endpoint_file_exists(self):
        """Verify that the webhooks endpoint handler file exists"""
        filepath = os.path.join(
            self.REPO_DIR,
            "ghost/core/core/server/api/endpoints/webhooks.js"
        )
        assert os.path.exists(filepath), f"webhooks.js endpoint not found at {filepath}"

    def test_webhooks_test_file_exists(self):
        """Verify that the webhooks e2e test file exists"""
        filepath = os.path.join(
            self.REPO_DIR,
            "ghost/core/test/e2e-api/admin/webhooks.test.js"
        )
        assert os.path.exists(filepath), f"webhooks.test.js not found at {filepath}"

    def test_admin_routes_file_exists(self):
        """Verify that the admin routes file exists"""
        filepath = os.path.join(
            self.REPO_DIR,
            "ghost/core/core/server/web/api/endpoints/admin/routes.js"
        )
        assert os.path.exists(filepath), f"admin routes.js not found at {filepath}"

    # === Semantic Checks ===

    def test_webhooks_endpoint_has_crud_methods(self):
        """Verify webhooks.js defines browse, read, add, edit, destroy handlers"""
        filepath = os.path.join(
            self.REPO_DIR,
            "ghost/core/core/server/api/endpoints/webhooks.js"
        )
        with open(filepath) as f:
            content = f.read()

        required_methods = ["browse", "read", "add", "edit", "destroy"]
        for method in required_methods:
            assert method in content, (
                f"webhooks.js missing '{method}' handler. "
                "All CRUD operations must be defined."
            )

    def test_admin_routes_registers_webhooks(self):
        """Verify that webhook routes are registered in the admin API router"""
        filepath = os.path.join(
            self.REPO_DIR,
            "ghost/core/core/server/web/api/endpoints/admin/routes.js"
        )
        with open(filepath) as f:
            content = f.read()

        assert "webhook" in content.lower(), (
            "admin routes.js does not contain webhook route registration. "
            "Routes must be registered for /webhooks/ endpoints."
        )

    def test_webhooks_endpoint_validates_event_types(self):
        """Verify that webhooks.js validates event types against an allowed list"""
        filepath = os.path.join(
            self.REPO_DIR,
            "ghost/core/core/server/api/endpoints/webhooks.js"
        )
        with open(filepath) as f:
            content = f.read()

        # Check for event validation - should contain allowed event names
        event_patterns = [
            "post.published",
            "post.unpublished",
            "member.added",
        ]
        found_events = sum(1 for e in event_patterns if e in content)
        assert found_events >= 2, (
            f"webhooks.js should validate event types against an allowed list. "
            f"Found only {found_events} event type references. "
            "Expected at least post.published, post.unpublished, member.added, etc."
        )

    def test_webhooks_endpoint_validates_https_url(self):
        """Verify that webhooks.js validates target_url as HTTPS"""
        filepath = os.path.join(
            self.REPO_DIR,
            "ghost/core/core/server/api/endpoints/webhooks.js"
        )
        with open(filepath) as f:
            content = f.read()

        has_url_validation = (
            "https" in content.lower()
            and ("validat" in content.lower() or "url" in content.lower())
        )
        # Also check model for URL validation
        model_path = os.path.join(
            self.REPO_DIR,
            "ghost/core/core/server/models/webhook.js"
        )
        if os.path.exists(model_path):
            with open(model_path) as f:
                model_content = f.read()
            has_url_validation = has_url_validation or (
                "https" in model_content.lower()
                and ("validat" in model_content.lower() or "url" in model_content.lower())
            )

        assert has_url_validation, (
            "No HTTPS URL validation found in webhooks endpoint or model. "
            "target_url must be validated as HTTPS URL."
        )

    def test_webhooks_test_covers_crud_operations(self):
        """Verify that the e2e test file covers all CRUD operations"""
        filepath = os.path.join(
            self.REPO_DIR,
            "ghost/core/test/e2e-api/admin/webhooks.test.js"
        )
        with open(filepath) as f:
            content = f.read()

        # Check for test coverage of CRUD operations
        crud_patterns = {
            "GET/browse": re.search(r'(?:GET|browse|list)', content, re.IGNORECASE),
            "POST/create": re.search(r'(?:POST|create|add)', content, re.IGNORECASE),
            "PUT/update": re.search(r'(?:PUT|update|edit)', content, re.IGNORECASE),
            "DELETE/destroy": re.search(r'(?:DELETE|destroy|delete)', content, re.IGNORECASE),
        }
        missing = [op for op, match in crud_patterns.items() if not match]
        assert len(missing) == 0, (
            f"e2e test file missing test coverage for: {missing}"
        )

    def test_webhooks_test_covers_validation_errors(self):
        """Verify that the e2e test covers validation error cases"""
        filepath = os.path.join(
            self.REPO_DIR,
            "ghost/core/test/e2e-api/admin/webhooks.test.js"
        )
        with open(filepath) as f:
            content = f.read()

        has_validation_tests = (
            "422" in content or "ValidationError" in content or "invalid" in content.lower()
        )
        assert has_validation_tests, (
            "e2e test file does not cover validation error cases. "
            "Expected tests for invalid URLs, invalid events, duplicate webhooks."
        )

    # === Functional Checks ===

    def test_webhooks_endpoint_is_valid_javascript(self):
        """Verify that webhooks.js is valid JavaScript by parsing with Node"""
        filepath = os.path.join(
            self.REPO_DIR,
            "ghost/core/core/server/api/endpoints/webhooks.js"
        )
        result = subprocess.run(
            ["node", "-e", f"require('{filepath}')"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=30
        )
        # If require fails, it might be due to missing deps, which is acceptable
        # but syntax errors are not
        if result.returncode != 0:
            stderr = result.stderr.lower()
            # Syntax errors are failures; module-not-found is acceptable
            assert "syntaxerror" not in stderr, (
                f"webhooks.js has JavaScript syntax errors: {result.stderr[:1000]}"
            )

    def test_webhook_model_exists_and_has_fields(self):
        """Verify the webhook model has required field definitions"""
        filepath = os.path.join(
            self.REPO_DIR,
            "ghost/core/core/server/models/webhook.js"
        )
        assert os.path.exists(filepath), f"webhook.js model not found at {filepath}"
        with open(filepath) as f:
            content = f.read()

        required_fields = ["event", "target_url"]
        for field in required_fields:
            assert field in content, (
                f"webhook.js model missing required field '{field}'"
            )

    def test_webhooks_endpoint_exports_handlers(self):
        """Verify that webhooks.js exports handler functions in the expected format"""
        filepath = os.path.join(
            self.REPO_DIR,
            "ghost/core/core/server/api/endpoints/webhooks.js"
        )
        with open(filepath) as f:
            content = f.read()

        # Ghost endpoints typically use module.exports
        assert "module.exports" in content or "export" in content, (
            "webhooks.js does not export its handlers. "
            "Expected module.exports with browse, read, add, edit, destroy."
        )

    def test_webhooks_test_has_sufficient_test_methods(self):
        """Verify that the e2e test file has a sufficient number of test cases"""
        filepath = os.path.join(
            self.REPO_DIR,
            "ghost/core/test/e2e-api/admin/webhooks.test.js"
        )
        with open(filepath) as f:
            content = f.read()

        # Count it() or test() blocks
        test_count = len(re.findall(r'\bit\s*\(', content)) + len(re.findall(r'\btest\s*\(', content))
        assert test_count >= 6, (
            f"Expected at least 6 test cases in webhooks.test.js, found {test_count}. "
            "Tests should cover CRUD, validation, pagination, and permissions."
        )

    def test_admin_routes_has_webhooks_path(self):
        """Verify that admin routes explicitly define /webhooks/ path"""
        filepath = os.path.join(
            self.REPO_DIR,
            "ghost/core/core/server/web/api/endpoints/admin/routes.js"
        )
        with open(filepath) as f:
            content = f.read()

        # Check for explicit route path
        has_webhooks_route = (
            "/webhooks" in content or "webhooks" in content
        )
        assert has_webhooks_route, (
            "admin routes.js does not define /webhooks/ path"
        )
