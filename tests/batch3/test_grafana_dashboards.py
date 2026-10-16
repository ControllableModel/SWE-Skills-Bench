"""
Tests for the grafana-dashboards skill.

Validates that Grafana dashboard provisioning was implemented for a
microservice monitoring stack with RED/USE panels, alerting, and
dashboard-as-code provisioning.

Repo: grafana (https://github.com/grafana/grafana)
"""

import json
import os
import re

REPO_DIR = "/workspace/grafana"


class TestFilePathCheck:
    """Verify all required files were created."""

    def test_dashboard_json_exists(self):
        path = os.path.join(
            REPO_DIR, "devenv", "dashboards",
            "microservice-monitoring.json",
        )
        assert os.path.isfile(path), f"Expected microservice-monitoring.json"

    def test_provisioning_yaml_exists(self):
        path = os.path.join(
            REPO_DIR, "devenv", "dashboards", "provisioning.yaml",
        )
        assert os.path.isfile(path), f"Expected provisioning.yaml"

    def test_alert_rules_exists(self):
        path = os.path.join(REPO_DIR, "devenv", "alerting", "alert-rules.yaml")
        assert os.path.isfile(path), f"Expected alerting/alert-rules.yaml"

    def test_red_panels_exists(self):
        path = os.path.join(
            REPO_DIR, "devenv", "dashboards", "panels", "red-panels.json",
        )
        assert os.path.isfile(path), f"Expected panels/red-panels.json"

    def test_use_panels_exists(self):
        path = os.path.join(
            REPO_DIR, "devenv", "dashboards", "panels", "use-panels.json",
        )
        assert os.path.isfile(path), f"Expected panels/use-panels.json"


class TestSemanticDashboardJson:
    """Verify dashboard JSON structure."""

    def _load(self):
        path = os.path.join(
            REPO_DIR, "devenv", "dashboards",
            "microservice-monitoring.json",
        )
        with open(path, "r") as f:
            return json.load(f)

    def test_valid_json(self):
        data = self._load()
        assert isinstance(data, dict), "Dashboard should be valid JSON object"

    def test_title(self):
        data = self._load()
        assert data.get("title") == "Microservice Monitoring", (
            "Expected title 'Microservice Monitoring'"
        )

    def test_uid(self):
        data = self._load()
        assert data.get("uid") == "microservice-monitoring-v1", (
            "Expected uid 'microservice-monitoring-v1'"
        )

    def test_tags(self):
        data = self._load()
        tags = data.get("tags", [])
        for tag in ["monitoring", "microservices", "sre"]:
            assert tag in tags, f"Expected tag '{tag}'"

    def test_template_variables(self):
        data = self._load()
        templating = data.get("templating", {})
        var_list = templating.get("list", [])
        var_names = [v.get("name") for v in var_list]
        for var in ["namespace", "service", "interval"]:
            assert var in var_names, f"Expected template variable '${var}'"

    def test_panels_exist(self):
        data = self._load()
        panels = data.get("panels", [])
        assert len(panels) >= 6, (
            f"Expected >= 6 panels, found {len(panels)}"
        )

    def test_grid_pos(self):
        data = self._load()
        panels = data.get("panels", [])
        has_grid = any("gridPos" in p for p in panels)
        assert has_grid, "Expected gridPos on panels for layout"


class TestSemanticRedPanels:
    """Verify RED method panels and PromQL queries."""

    def _read_dashboard(self):
        path = os.path.join(
            REPO_DIR, "devenv", "dashboards",
            "microservice-monitoring.json",
        )
        with open(path, "r") as f:
            return f.read()

    def test_request_rate_query(self):
        content = self._read_dashboard()
        assert re.search(r"rate\(http_requests_total", content), (
            "Expected rate(http_requests_total...) for request rate"
        )

    def test_error_rate_query(self):
        content = self._read_dashboard()
        assert re.search(r'status.*5\.\.|5xx|"5\.\."', content), (
            "Expected 5xx error rate PromQL query"
        )

    def test_latency_histogram(self):
        content = self._read_dashboard()
        assert re.search(r"histogram_quantile", content), (
            "Expected histogram_quantile for latency percentiles"
        )

    def test_multiple_quantiles(self):
        content = self._read_dashboard()
        for q in ["0.5", "0.9", "0.99"]:
            assert q in content, f"Expected quantile {q} for latency"


class TestSemanticUsePanels:
    """Verify USE method panels."""

    def _read_dashboard(self):
        path = os.path.join(
            REPO_DIR, "devenv", "dashboards",
            "microservice-monitoring.json",
        )
        with open(path, "r") as f:
            return f.read()

    def test_cpu_utilization(self):
        content = self._read_dashboard()
        assert re.search(r"container_cpu_usage_seconds_total|cpu.*usage", content), (
            "Expected CPU utilization metric"
        )

    def test_memory_utilization(self):
        content = self._read_dashboard()
        assert re.search(r"container_memory_working_set_bytes|memory.*working", content), (
            "Expected memory utilization metric"
        )

    def test_cpu_saturation(self):
        content = self._read_dashboard()
        assert re.search(r"cpu_cfs_throttled|throttle", content, re.IGNORECASE), (
            "Expected CPU saturation (throttled) metric"
        )

    def test_pod_restarts(self):
        content = self._read_dashboard()
        assert re.search(r"restarts_total|restart", content, re.IGNORECASE), (
            "Expected pod restarts metric"
        )


class TestSemanticAlertRules:
    """Verify alerting rules."""

    def _read(self):
        path = os.path.join(REPO_DIR, "devenv", "alerting", "alert-rules.yaml")
        with open(path, "r") as f:
            return f.read()

    def test_high_error_rate_alert(self):
        content = self._read()
        assert re.search(r"HighErrorRate|high.*error.*rate", content, re.IGNORECASE), (
            "Expected HighErrorRate alert rule"
        )

    def test_high_latency_alert(self):
        content = self._read()
        assert re.search(r"HighLatency|high.*latency", content, re.IGNORECASE), (
            "Expected HighLatency alert rule"
        )

    def test_high_pod_restarts_alert(self):
        content = self._read()
        assert re.search(r"HighPodRestarts|pod.*restart", content, re.IGNORECASE), (
            "Expected HighPodRestarts alert rule"
        )

    def test_severity_labels(self):
        content = self._read()
        assert re.search(r"severity.*critical|severity.*warning", content), (
            "Expected severity labels (critical/warning)"
        )


class TestSemanticProvisioning:
    """Verify provisioning YAML configuration."""

    def _read(self):
        path = os.path.join(
            REPO_DIR, "devenv", "dashboards", "provisioning.yaml",
        )
        with open(path, "r") as f:
            return f.read()

    def test_update_interval(self):
        content = self._read()
        assert re.search(r"updateIntervalSeconds.*30|updateInterval", content), (
            "Expected updateIntervalSeconds: 30"
        )

    def test_allow_ui_updates_false(self):
        content = self._read()
        assert re.search(r"allowUiUpdates.*false", content), (
            "Expected allowUiUpdates: false"
        )

    def test_folder_microservices(self):
        content = self._read()
        assert re.search(r"Microservices|folder.*Microservices", content), (
            "Expected folder: Microservices"
        )


class TestFunctionalJsonValidity:
    """Validate JSON files are well-formed."""

    def test_red_panels_valid_json(self):
        path = os.path.join(
            REPO_DIR, "devenv", "dashboards", "panels", "red-panels.json",
        )
        with open(path, "r") as f:
            data = json.load(f)
        assert isinstance(data, (dict, list)), "red-panels.json should be valid JSON"

    def test_use_panels_valid_json(self):
        path = os.path.join(
            REPO_DIR, "devenv", "dashboards", "panels", "use-panels.json",
        )
        with open(path, "r") as f:
            data = json.load(f)
        assert isinstance(data, (dict, list)), "use-panels.json should be valid JSON"

    def test_alert_rules_valid_yaml(self):
        import yaml
        path = os.path.join(REPO_DIR, "devenv", "alerting", "alert-rules.yaml")
        with open(path, "r") as f:
            data = yaml.safe_load(f)
        assert isinstance(data, (dict, list)), "alert-rules.yaml should be valid YAML"

    def test_provisioning_valid_yaml(self):
        import yaml
        path = os.path.join(
            REPO_DIR, "devenv", "dashboards", "provisioning.yaml",
        )
        with open(path, "r") as f:
            data = yaml.safe_load(f)
        assert isinstance(data, (dict, list)), "provisioning.yaml should be valid YAML"
