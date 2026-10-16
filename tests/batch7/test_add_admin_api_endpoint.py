"""
Test skill: add-admin-api-endpoint
Verify that the Agent correctly creates a bulk newsletter management
Admin API endpoint in the Ghost CMS application.
"""

import os
import re
import json
import subprocess
import pytest


class TestAddAdminApiEndpoint:
    REPO_DIR = "/workspace/Ghost"

    # === File Path Checks ===

    def test_newsletters_bulk_endpoint_file_exists(self):
        """Verify newsletters-bulk.js endpoint handler exists"""
        fpath = os.path.join(
            self.REPO_DIR,
            "ghost/core/core/server/api/endpoints/newsletters-bulk.js"
        )
        assert os.path.isfile(fpath), f"newsletters-bulk.js not found at {fpath}"

    def test_newsletter_bulk_service_exists(self):
        """Verify NewsletterBulkService.js service file exists"""
        fpath = os.path.join(
            self.REPO_DIR,
            "ghost/core/core/server/services/newsletters/NewsletterBulkService.js"
        )
        assert os.path.isfile(fpath), f"NewsletterBulkService.js not found at {fpath}"

    def test_e2e_test_file_exists(self):
        """Verify e2e test file for newsletters-bulk exists"""
        fpath = os.path.join(
            self.REPO_DIR,
            "ghost/core/test/e2e-api/admin/newsletters-bulk.test.js"
        )
        assert os.path.isfile(fpath), f"newsletters-bulk.test.js not found at {fpath}"

    # === Semantic Checks ===

    def test_endpoint_exports_bulk_handler(self):
        """Verify newsletters-bulk.js exports a handler for bulk operations"""
        fpath = os.path.join(
            self.REPO_DIR,
            "ghost/core/core/server/api/endpoints/newsletters-bulk.js"
        )
        with open(fpath, "r") as f:
            content = f.read()
        has_export = bool(re.search(r'(module\.exports|export)', content))
        assert has_export, "newsletters-bulk.js should export a handler"
        # Should reference bulk operations
        has_bulk = bool(re.search(r'bulk', content, re.IGNORECASE))
        assert has_bulk, "newsletters-bulk.js should reference bulk operations"

    def test_endpoint_handles_archive_action(self):
        """Verify the endpoint handler supports the 'archive' action"""
        fpath = os.path.join(
            self.REPO_DIR,
            "ghost/core/core/server/api/endpoints/newsletters-bulk.js"
        )
        with open(fpath, "r") as f:
            content = f.read()
        has_archive = bool(re.search(r'archive', content, re.IGNORECASE))
        assert has_archive, "Endpoint should handle 'archive' action"

    def test_endpoint_handles_unarchive_action(self):
        """Verify the endpoint handler supports the 'unarchive' action"""
        fpath = os.path.join(
            self.REPO_DIR,
            "ghost/core/core/server/api/endpoints/newsletters-bulk.js"
        )
        with open(fpath, "r") as f:
            content = f.read()
        has_unarchive = bool(re.search(r'unarchive', content, re.IGNORECASE))
        assert has_unarchive, "Endpoint should handle 'unarchive' action"

    def test_endpoint_handles_reorder_action(self):
        """Verify the endpoint handler supports the 'reorder' action"""
        fpath = os.path.join(
            self.REPO_DIR,
            "ghost/core/core/server/api/endpoints/newsletters-bulk.js"
        )
        with open(fpath, "r") as f:
            content = f.read()
        has_reorder = bool(re.search(r'reorder', content, re.IGNORECASE))
        assert has_reorder, "Endpoint should handle 'reorder' action"

    def test_service_has_validation_logic(self):
        """Verify NewsletterBulkService has validation for actions and IDs"""
        fpath = os.path.join(
            self.REPO_DIR,
            "ghost/core/core/server/services/newsletters/NewsletterBulkService.js"
        )
        with open(fpath, "r") as f:
            content = f.read()
        has_validation = bool(re.search(r'(valid|ValidationError|422|reject|invalid)', content, re.IGNORECASE))
        assert has_validation, "Service should include input validation logic"
        has_not_found = bool(re.search(r'(not.?found|404|NotFound)', content, re.IGNORECASE))
        assert has_not_found, "Service should handle not-found newsletter IDs"

    def test_service_prevents_archiving_last_active(self):
        """Verify service prevents archiving the only active newsletter"""
        fpath = os.path.join(
            self.REPO_DIR,
            "ghost/core/core/server/services/newsletters/NewsletterBulkService.js"
        )
        with open(fpath, "r") as f:
            content = f.read()
        has_last_active_check = bool(re.search(
            r'(last.*active|only.*active|at.least.one|cannot.*archive.*only)',
            content,
            re.IGNORECASE
        ))
        assert has_last_active_check, (
            "Service should prevent archiving the only remaining active newsletter"
        )

    def test_service_handles_atomicity(self):
        """Verify service applies operations atomically (transaction or rollback pattern)"""
        fpath = os.path.join(
            self.REPO_DIR,
            "ghost/core/core/server/services/newsletters/NewsletterBulkService.js"
        )
        with open(fpath, "r") as f:
            content = f.read()
        has_transaction = bool(re.search(
            r'(transaction|atomic|rollback|knex\.transaction|beginTransaction)',
            content,
            re.IGNORECASE
        ))
        assert has_transaction, "Service should apply operations atomically (transaction pattern)"

    def test_middleware_registers_bulk_route(self):
        """Verify the admin middleware registers the newsletters/bulk route"""
        fpath = os.path.join(
            self.REPO_DIR,
            "ghost/core/core/server/web/api/endpoints/admin/middleware.js"
        )
        if not os.path.isfile(fpath):
            # Try alternative router file locations
            alt_paths = [
                os.path.join(self.REPO_DIR, "ghost/core/core/server/web/api/endpoints/admin/index.js"),
                os.path.join(self.REPO_DIR, "ghost/core/core/server/web/api/endpoints/admin/routes.js"),
            ]
            found = False
            for alt in alt_paths:
                if os.path.isfile(alt):
                    fpath = alt
                    found = True
                    break
            if not found:
                pytest.skip("Admin middleware/router file not found in expected locations")

        with open(fpath, "r") as f:
            content = f.read()
        has_route = bool(re.search(r'newsletters.*bulk|bulk.*newsletters', content, re.IGNORECASE))
        assert has_route, "Admin router should register the newsletters/bulk route"

    def test_e2e_tests_cover_success_and_errors(self):
        """Verify e2e tests cover success, 404, 422, and 403 scenarios"""
        fpath = os.path.join(
            self.REPO_DIR,
            "ghost/core/test/e2e-api/admin/newsletters-bulk.test.js"
        )
        with open(fpath, "r") as f:
            content = f.read()
        has_success = bool(re.search(r'(200|success)', content, re.IGNORECASE))
        has_422 = bool(re.search(r'422', content))
        has_404 = bool(re.search(r'404', content))
        assert has_success, "E2E tests should cover success (200) scenario"
        assert has_422, "E2E tests should cover validation error (422) scenario"
        assert has_404, "E2E tests should cover not-found (404) scenario"

    # === Functional Checks ===

    def test_endpoint_file_is_valid_javascript(self):
        """Verify newsletters-bulk.js is valid JavaScript by running node syntax check"""
        fpath = os.path.join(
            self.REPO_DIR,
            "ghost/core/core/server/api/endpoints/newsletters-bulk.js"
        )
        result = subprocess.run(
            ["node", "--check", fpath],
            capture_output=True,
            text=True,
            timeout=30
        )
        assert result.returncode == 0, f"JavaScript syntax error: {result.stderr}"

    def test_service_file_is_valid_javascript(self):
        """Verify NewsletterBulkService.js is valid JavaScript"""
        fpath = os.path.join(
            self.REPO_DIR,
            "ghost/core/core/server/services/newsletters/NewsletterBulkService.js"
        )
        result = subprocess.run(
            ["node", "--check", fpath],
            capture_output=True,
            text=True,
            timeout=30
        )
        assert result.returncode == 0, f"JavaScript syntax error: {result.stderr}"

    def test_e2e_test_file_is_valid_javascript(self):
        """Verify e2e test file is valid JavaScript"""
        fpath = os.path.join(
            self.REPO_DIR,
            "ghost/core/test/e2e-api/admin/newsletters-bulk.test.js"
        )
        result = subprocess.run(
            ["node", "--check", fpath],
            capture_output=True,
            text=True,
            timeout=30
        )
        assert result.returncode == 0, f"JavaScript syntax error: {result.stderr}"

    def test_endpoint_defines_put_method(self):
        """Verify the endpoint is configured as a PUT method"""
        fpath = os.path.join(
            self.REPO_DIR,
            "ghost/core/core/server/api/endpoints/newsletters-bulk.js"
        )
        with open(fpath, "r") as f:
            content = f.read()
        has_put = bool(re.search(r'(PUT|put|\.put\()', content))
        assert has_put, "Endpoint should be a PUT method"

    def test_service_sets_archived_status(self):
        """Verify service sets status to 'archived' and visibility to 'none' for archive action"""
        fpath = os.path.join(
            self.REPO_DIR,
            "ghost/core/core/server/services/newsletters/NewsletterBulkService.js"
        )
        with open(fpath, "r") as f:
            content = f.read()
        has_archived_status = bool(re.search(r'["\']archived["\']', content))
        has_visibility_none = bool(re.search(r'["\']none["\']', content))
        assert has_archived_status, "Service should set status to 'archived'"
        assert has_visibility_none, "Service should set visibility to 'none' on archive"
