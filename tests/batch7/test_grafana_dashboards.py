"""
Test skill: grafana-dashboards
Verify that the Agent implements a Dashboard Provisioning API Handler in Grafana —
DashboardProvisionService (Provision method, validation, overwrite logic, error types),
HTTP handler (status code mapping), and route registration with auth middleware.
"""

import os
import re
import subprocess
import pytest


class TestGrafanaDashboards:
    REPO_DIR = "/workspace/grafana"

    # ────── helpers ──────

    def _read(self, rel_path):
        fpath = os.path.join(self.REPO_DIR, rel_path)
        with open(fpath, "r") as f:
            return f.read()

    def _exists(self, rel_path):
        return os.path.isfile(os.path.join(self.REPO_DIR, rel_path))

    # === File Path Checks ===

    def test_dashboard_provision_handler_exists(self):
        """dashboard_provision.go must exist"""
        assert self._exists("pkg/api/dashboard_provision.go")

    def test_provision_service_exists(self):
        """provision_service.go must exist"""
        assert self._exists("pkg/services/dashboards/provision_service.go")

    def test_provision_service_test_exists(self):
        """provision_service_test.go must exist"""
        assert self._exists("pkg/services/dashboards/provision_service_test.go")

    # === Semantic Checks — provision_service.go ===

    def test_provision_request_struct(self):
        """ProvisionRequest struct must be defined"""
        src = self._read("pkg/services/dashboards/provision_service.go")
        assert re.search(r'type\s+ProvisionRequest\s+struct', src)

    def test_provision_result_struct(self):
        """ProvisionResult struct must be defined"""
        src = self._read("pkg/services/dashboards/provision_service.go")
        assert re.search(r'type\s+ProvisionResult\s+struct', src)

    def test_service_struct(self):
        """DashboardProvisionService struct must be defined"""
        src = self._read("pkg/services/dashboards/provision_service.go")
        assert "DashboardProvisionService" in src

    def test_provision_method(self):
        """Provision method must exist"""
        src = self._read("pkg/services/dashboards/provision_service.go")
        assert "Provision" in src

    def test_title_validation(self):
        """Must validate title field"""
        src = self._read("pkg/services/dashboards/provision_service.go")
        assert "title" in src.lower()

    def test_schema_version_validation(self):
        """Must validate schemaVersion"""
        src = self._read("pkg/services/dashboards/provision_service.go")
        lower = src.lower()
        assert "schemaversion" in lower or "schema_version" in lower

    def test_overwrite_logic(self):
        """Must handle overwrite flag"""
        src = self._read("pkg/services/dashboards/provision_service.go")
        assert "Overwrite" in src or "overwrite" in src

    def test_uid_generation(self):
        """Must generate UID when not provided"""
        src = self._read("pkg/services/dashboards/provision_service.go")
        lower = src.lower()
        assert "uid" in lower and ("generate" in lower or "shortuid" in lower)

    def test_err_invalid_dashboard(self):
        """ErrInvalidDashboard error type must be defined"""
        src = self._read("pkg/services/dashboards/provision_service.go")
        assert "ErrInvalidDashboard" in src

    def test_err_dashboard_exists(self):
        """ErrDashboardExists error type must be defined"""
        src = self._read("pkg/services/dashboards/provision_service.go")
        assert "ErrDashboardExists" in src

    def test_folder_resolution(self):
        """Must resolve folder by UID"""
        src = self._read("pkg/services/dashboards/provision_service.go")
        lower = src.lower()
        assert "folder" in lower

    def test_version_increment(self):
        """Must increment version on overwrite"""
        src = self._read("pkg/services/dashboards/provision_service.go")
        lower = src.lower()
        assert "version" in lower

    # === Semantic Checks — dashboard_provision.go ===

    def test_handler_function(self):
        """ProvisionDashboardHandler must be defined"""
        src = self._read("pkg/api/dashboard_provision.go")
        assert "ProvisionDashboardHandler" in src

    def test_http_status_codes(self):
        """Must return 400, 409, 500 for different error types"""
        src = self._read("pkg/api/dashboard_provision.go")
        assert "BadRequest" in src or "400" in src
        assert "Conflict" in src or "409" in src

    def test_json_decode(self):
        """Must decode request body"""
        src = self._read("pkg/api/dashboard_provision.go")
        assert "Decode" in src or "Bind" in src or "json" in src.lower()

    # === Semantic Checks — Route Registration ===

    def test_route_registration(self):
        """Route must be registered in dashboard_routes.go"""
        src = self._read("pkg/api/routing/dashboard_routes.go")
        assert "provision" in src.lower() or "ProvisionDashboard" in src

    def test_auth_middleware(self):
        """Route must use auth middleware"""
        src = self._read("pkg/api/routing/dashboard_routes.go")
        lower = src.lower()
        assert "signedin" in lower or "reqsignedin" in lower or "auth" in lower

    def test_role_check(self):
        """Route must require Editor role"""
        src = self._read("pkg/api/routing/dashboard_routes.go")
        assert "Editor" in src or "RoleEditor" in src or "editor" in src.lower()

    # === Functional Checks ===

    def test_go_build(self):
        """Project must build"""
        result = subprocess.run(
            ["go", "build", "./pkg/..."],
            capture_output=True, text=True, cwd=self.REPO_DIR, timeout=600,
        )
        assert result.returncode == 0, (
            f"go build failed:\n{result.stdout}\n{result.stderr}"
        )

    def test_provision_service_tests(self):
        """Provision service tests must pass"""
        result = subprocess.run(
            ["go", "test", "-v",
             "./pkg/services/dashboards/...",
             "-run", "TestProvision"],
            capture_output=True, text=True, cwd=self.REPO_DIR, timeout=300,
        )
        assert result.returncode == 0, (
            f"Tests failed:\n{result.stdout}\n{result.stderr}"
        )
