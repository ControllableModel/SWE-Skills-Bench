"""
Test skill: grafana-dashboards
Verify that the Agent correctly creates a Service Health Grafana Dashboard
with RED Method Panels and a Validator in Go for the grafana/grafana repo.
"""

import os
import re
import json
import subprocess
import pytest


class TestGrafanaDashboards:
    REPO_DIR = "/workspace/grafana"

    # === File Path Checks ===

    def test_dashboard_json_exists(self):
        """Verify service-health-dashboard.json was created"""
        path = os.path.join(
            self.REPO_DIR,
            "public/app/features/dashboard/state/service-health-dashboard.json",
        )
        assert os.path.exists(path), "service-health-dashboard.json not found"

    def test_validator_go_exists(self):
        """Verify service_health_validator.go was created"""
        path = os.path.join(
            self.REPO_DIR,
            "pkg/services/dashboards/service_health_validator.go",
        )
        assert os.path.exists(path), "service_health_validator.go not found"

    def test_validator_test_go_exists(self):
        """Verify service_health_validator_test.go was created"""
        path = os.path.join(
            self.REPO_DIR,
            "pkg/services/dashboards/service_health_validator_test.go",
        )
        assert os.path.exists(path), "service_health_validator_test.go not found"

    # === Semantic Checks: Dashboard JSON structure ===

    def _load_dashboard(self):
        path = os.path.join(
            self.REPO_DIR,
            "public/app/features/dashboard/state/service-health-dashboard.json",
        )
        return open(path).read()

    def _parse_dashboard(self):
        return json.loads(self._load_dashboard())

    def test_dashboard_valid_json(self):
        """Verify dashboard file is valid JSON"""
        try:
            self._parse_dashboard()
        except json.JSONDecodeError as e:
            pytest.fail(f"Dashboard JSON is invalid: {e}")

    def test_dashboard_title(self):
        """Verify dashboard title is Service Health (RED)"""
        d = self._parse_dashboard()
        assert d.get("title") == "Service Health (RED)", (
            f"Expected title 'Service Health (RED)', got '{d.get('title')}'"
        )

    def test_dashboard_tags(self):
        """Verify dashboard tags include red-method, api, service"""
        d = self._parse_dashboard()
        tags = d.get("tags", [])
        for tag in ["red-method", "api", "service"]:
            assert tag in tags, f"Missing tag '{tag}'"

    def test_dashboard_refresh(self):
        """Verify dashboard refresh is set to 30s"""
        d = self._parse_dashboard()
        assert d.get("refresh") == "30s", (
            f"Expected refresh '30s', got '{d.get('refresh')}'"
        )

    def test_dashboard_datasource_template_variable(self):
        """Verify datasource template variable exists with type=datasource"""
        d = self._parse_dashboard()
        var_list = d.get("templating", {}).get("list", [])
        ds_vars = [v for v in var_list if v.get("name") == "datasource"]
        assert len(ds_vars) > 0, "Missing 'datasource' template variable"
        assert ds_vars[0].get("type") == "datasource", (
            "datasource variable type should be 'datasource'"
        )

    def test_dashboard_service_template_variable(self):
        """Verify service template variable exists with type=query"""
        d = self._parse_dashboard()
        var_list = d.get("templating", {}).get("list", [])
        svc_vars = [v for v in var_list if v.get("name") == "service"]
        assert len(svc_vars) > 0, "Missing 'service' template variable"
        assert svc_vars[0].get("type") == "query", (
            "service variable type should be 'query'"
        )

    # === Semantic Checks: Required Panels ===

    def _get_panel_titles(self):
        d = self._parse_dashboard()
        panels = d.get("panels", [])
        return [p.get("title", "") for p in panels]

    def test_request_rate_panel(self):
        """Verify Request Rate panel exists"""
        titles = self._get_panel_titles()
        assert "Request Rate" in titles, "Missing 'Request Rate' panel"

    def test_error_rate_panel(self):
        """Verify Error Rate % panel exists"""
        titles = self._get_panel_titles()
        assert "Error Rate %" in titles, "Missing 'Error Rate %' panel"

    def test_p95_latency_panel(self):
        """Verify P95 Latency panel exists"""
        titles = self._get_panel_titles()
        assert "P95 Latency" in titles, "Missing 'P95 Latency' panel"

    def test_p99_latency_panel(self):
        """Verify P99 Latency panel exists"""
        titles = self._get_panel_titles()
        assert "P99 Latency" in titles, "Missing 'P99 Latency' panel"

    def test_active_connections_panel(self):
        """Verify Active Connections panel exists"""
        titles = self._get_panel_titles()
        assert "Active Connections" in titles, "Missing 'Active Connections' panel"

    # === Semantic Checks: Validator ===

    def _load_validator_source(self):
        path = os.path.join(
            self.REPO_DIR,
            "pkg/services/dashboards/service_health_validator.go",
        )
        return open(path).read()

    def test_validate_function_defined(self):
        """Verify ValidateServiceHealthDashboard function is defined"""
        source = self._load_validator_source()
        assert "ValidateServiceHealthDashboard" in source, (
            "ValidateServiceHealthDashboard not found"
        )

    def test_validator_checks_panel_titles(self):
        """Verify validator checks for required panel titles"""
        source = self._load_validator_source()
        required = ["Request Rate", "Error Rate %", "P95 Latency", "P99 Latency", "Active Connections"]
        found_count = sum(1 for t in required if t in source)
        assert found_count >= 3, (
            f"Validator only references {found_count}/5 required panel titles"
        )

    def test_validator_checks_template_variables(self):
        """Verify validator checks for template variables"""
        source = self._load_validator_source()
        assert "datasource" in source and "service" in source, (
            "Validator does not check for template variables"
        )

    # === Functional Checks ===

    def test_panels_reference_datasource_uid(self):
        """Verify panels reference ${datasource} as datasource uid"""
        content = self._load_dashboard()
        assert "${datasource}" in content, (
            "Panels do not reference ${datasource}"
        )

    def test_error_rate_panel_has_alert(self):
        """Verify Error Rate % panel has an alert rule"""
        d = self._parse_dashboard()
        panels = d.get("panels", [])
        err_panel = next((p for p in panels if p.get("title") == "Error Rate %"), None)
        assert err_panel is not None, "Error Rate % panel not found"
        has_alert = (
            "alert" in json.dumps(err_panel).lower()
            or "thresholds" in json.dumps(err_panel).lower()
        )
        assert has_alert, "Error Rate % panel missing alert configuration"

    def test_panel_ordering_by_grid_pos(self):
        """Verify panels are ordered by gridPos.y"""
        d = self._parse_dashboard()
        panels = d.get("panels", [])
        expected_order = ["Request Rate", "Error Rate %", "P95 Latency", "P99 Latency", "Active Connections"]
        panel_positions = []
        for title in expected_order:
            for p in panels:
                if p.get("title") == title:
                    y = p.get("gridPos", {}).get("y", -1)
                    panel_positions.append((title, y))
                    break
        # Verify y values are in ascending order
        y_values = [y for _, y in panel_positions if y >= 0]
        assert y_values == sorted(y_values), (
            f"Panels not in correct order by gridPos.y: {panel_positions}"
        )

    def test_validator_handles_malformed_json(self):
        """Verify validator references json error handling"""
        source = self._load_validator_source()
        has_json_error = (
            "json.SyntaxError" in source
            or "SyntaxError" in source
            or "Unmarshal" in source
            or "json.Unmarshal" in source
        )
        assert has_json_error, "Validator does not handle malformed JSON"

    def test_request_rate_panel_uses_reqps_unit(self):
        """Verify Request Rate panel uses reqps unit"""
        d = self._parse_dashboard()
        panels = d.get("panels", [])
        rr_panel = next((p for p in panels if p.get("title") == "Request Rate"), None)
        assert rr_panel is not None, "Request Rate panel not found"
        panel_str = json.dumps(rr_panel)
        assert "reqps" in panel_str, "Request Rate panel missing reqps unit"

    def test_active_connections_panel_type_stat(self):
        """Verify Active Connections panel type is stat"""
        d = self._parse_dashboard()
        panels = d.get("panels", [])
        ac_panel = next((p for p in panels if p.get("title") == "Active Connections"), None)
        assert ac_panel is not None, "Active Connections panel not found"
        assert ac_panel.get("type") == "stat", (
            f"Expected type 'stat', got '{ac_panel.get('type')}'"
        )
