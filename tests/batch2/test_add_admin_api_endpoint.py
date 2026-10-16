"""
Test skill: add-admin-api-endpoint
Verify that the Agent correctly creates an audit logs endpoint in the
Ghost Admin API with browse support, filtering, pagination, and access control.
"""

import os
import re
import json
import subprocess
import pytest


class TestAddAdminApiEndpoint:
    REPO_DIR = "/workspace/Ghost"

    # === File Path Checks ===

    def test_audit_logs_endpoint_file_exists(self):
        """Verify audit-logs.js endpoint controller file exists"""
        path = os.path.join(
            self.REPO_DIR,
            "ghost/core/core/server/api/endpoints/audit-logs.js",
        )
        assert os.path.exists(path), f"audit-logs.js not found at {path}"

    def test_audit_log_service_file_exists(self):
        """Verify audit-log service index.js file exists"""
        path = os.path.join(
            self.REPO_DIR,
            "ghost/core/core/server/services/audit-log/index.js",
        )
        assert os.path.exists(path), f"audit-log service not found at {path}"

    def test_endpoints_router_file_exists(self):
        """Verify the endpoints router file exists"""
        path = os.path.join(
            self.REPO_DIR,
            "ghost/core/core/server/web/api/endpoints.js",
        )
        assert os.path.exists(path), f"endpoints.js not found at {path}"

    # === Semantic Checks ===

    def test_audit_logs_endpoint_exports_browse(self):
        """Verify audit-logs.js exports a browse handler"""
        path = os.path.join(
            self.REPO_DIR,
            "ghost/core/core/server/api/endpoints/audit-logs.js",
        )
        with open(path) as f:
            content = f.read()

        assert "browse" in content.lower(), (
            "audit-logs.js should export a 'browse' handler for GET requests"
        )

    def test_audit_logs_endpoint_has_permission_check(self):
        """Verify audit-logs.js enforces admin-level permissions"""
        path = os.path.join(
            self.REPO_DIR,
            "ghost/core/core/server/api/endpoints/audit-logs.js",
        )
        with open(path) as f:
            content = f.read()

        permission_indicators = [
            "permissions", "permission", "admin", "role",
            "isOwner", "isAdmin", "authenticated",
        ]
        found = [ind for ind in permission_indicators if ind.lower() in content.lower()]
        assert len(found) >= 1, (
            "audit-logs.js should enforce admin permissions. "
            f"Found: {found}. Expected at least 1 of: {permission_indicators}"
        )

    def test_audit_log_service_supports_filtering(self):
        """Verify audit-log service supports filtering by action, actor, date"""
        path = os.path.join(
            self.REPO_DIR,
            "ghost/core/core/server/services/audit-log/index.js",
        )
        with open(path) as f:
            content = f.read()

        filter_keywords = ["action", "actor", "date", "filter", "query"]
        found = [kw for kw in filter_keywords if kw.lower() in content.lower()]
        assert len(found) >= 2, (
            "Audit log service should support filtering. "
            f"Found references to: {found}. Expected at least 2 of: {filter_keywords}"
        )

    def test_audit_log_service_supports_pagination(self):
        """Verify audit-log service implements pagination"""
        path = os.path.join(
            self.REPO_DIR,
            "ghost/core/core/server/services/audit-log/index.js",
        )
        with open(path) as f:
            content = f.read()

        pagination_keywords = [
            "page", "limit", "offset", "pagination",
            "total", "pages", "next", "prev",
        ]
        found = [kw for kw in pagination_keywords if kw.lower() in content.lower()]
        assert len(found) >= 2, (
            "Audit log service should implement pagination. "
            f"Found: {found}. Expected at least 2 of: {pagination_keywords}"
        )

    def test_endpoints_router_registers_audit_logs(self):
        """Verify endpoints.js registers the audit_logs route"""
        path = os.path.join(
            self.REPO_DIR,
            "ghost/core/core/server/web/api/endpoints.js",
        )
        with open(path) as f:
            content = f.read()

        route_indicators = [
            "audit_logs", "audit-logs", "auditLogs", "audit",
        ]
        found = [ind for ind in route_indicators if ind in content]
        assert len(found) >= 1, (
            "endpoints.js should register the audit_logs route. "
            f"None of {route_indicators} found in endpoints router."
        )

    def test_audit_log_data_model_has_required_fields(self):
        """Verify audit log entries include required fields in service or endpoint"""
        # Check both service and endpoint files for data model definition
        files_to_check = [
            os.path.join(
                self.REPO_DIR,
                "ghost/core/core/server/api/endpoints/audit-logs.js",
            ),
            os.path.join(
                self.REPO_DIR,
                "ghost/core/core/server/services/audit-log/index.js",
            ),
        ]
        combined_content = ""
        for fpath in files_to_check:
            if os.path.exists(fpath):
                with open(fpath) as f:
                    combined_content += f.read() + "\n"

        required_fields = ["action", "actor", "resource", "timestamp"]
        found = [f for f in required_fields if f.lower() in combined_content.lower()]
        assert len(found) >= 3, (
            "Audit log entries should include action, actor, resource, and timestamp. "
            f"Found references to: {found}"
        )

    # === Functional Checks ===

    def test_audit_logs_endpoint_has_valid_js_syntax(self):
        """Verify audit-logs.js has valid JavaScript syntax"""
        path = os.path.join(
            self.REPO_DIR,
            "ghost/core/core/server/api/endpoints/audit-logs.js",
        )
        result = subprocess.run(
            ["node", "--check", path],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, (
            f"audit-logs.js has JS syntax errors: {result.stderr[:1000]}"
        )

    def test_audit_log_service_has_valid_js_syntax(self):
        """Verify audit-log service index.js has valid JavaScript syntax"""
        path = os.path.join(
            self.REPO_DIR,
            "ghost/core/core/server/services/audit-log/index.js",
        )
        result = subprocess.run(
            ["node", "--check", path],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, (
            f"audit-log service has JS syntax errors: {result.stderr[:1000]}"
        )

    def test_audit_logs_module_is_requireable(self):
        """Verify audit-logs.js can be required by Node.js"""
        path = os.path.join(
            self.REPO_DIR,
            "ghost/core/core/server/api/endpoints/audit-logs.js",
        )
        # Try to require the file - may fail due to missing deps, but should
        # not fail due to syntax
        result = subprocess.run(
            ["node", "-e", f"try {{ require('{path}') }} catch(e) {{ "
             "if (e instanceof SyntaxError) {{ process.exit(1) }} }}"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, (
            f"audit-logs.js cannot be loaded: {result.stderr[:1000]}"
        )

    def test_audit_log_response_follows_ghost_envelope(self):
        """Verify the endpoint response structure follows Ghost API conventions"""
        path = os.path.join(
            self.REPO_DIR,
            "ghost/core/core/server/api/endpoints/audit-logs.js",
        )
        with open(path) as f:
            content = f.read()

        # Ghost API returns objects in an envelope like { audit_logs: [...], meta: {} }
        envelope_indicators = [
            "audit_logs", "meta", "pagination",
        ]
        found = [ind for ind in envelope_indicators if ind in content]
        assert len(found) >= 1, (
            "Endpoint response should use Ghost's envelope format "
            f"(e.g., audit_logs, meta). Found: {found}"
        )
