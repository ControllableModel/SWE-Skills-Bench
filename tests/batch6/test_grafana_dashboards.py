"""
Tests for grafana-dashboards skill.
Verifies creation of Grafana dashboard JSON files and provisioning YAML configs
for executive overview, service RED metrics, and infrastructure USE metrics.
"""

import json
import os
import re

import pytest
import yaml


class TestGrafanaDashboards:
    """Tests for grafana-dashboards skill."""

    REPO_DIR = "/workspace/grafana"

    # ------------------------------------------------------------------ #
    #  file_path_check – verify expected files exist
    # ------------------------------------------------------------------ #

    def test_executive_overview_json_exists(self):
        path = os.path.join(self.REPO_DIR, "grafana", "dashboards", "executive-overview.json")
        assert os.path.isfile(path), f"Missing {path}"

    def test_service_red_json_exists(self):
        path = os.path.join(self.REPO_DIR, "grafana", "dashboards", "service-red.json")
        assert os.path.isfile(path), f"Missing {path}"

    def test_infrastructure_use_json_exists(self):
        path = os.path.join(self.REPO_DIR, "grafana", "dashboards", "infrastructure-use.json")
        assert os.path.isfile(path), f"Missing {path}"

    def test_provisioning_dashboards_yaml_exists(self):
        path = os.path.join(self.REPO_DIR, "grafana", "provisioning", "dashboards.yaml")
        assert os.path.isfile(path), f"Missing {path}"

    def test_provisioning_datasources_yaml_exists(self):
        path = os.path.join(self.REPO_DIR, "grafana", "provisioning", "datasources.yaml")
        assert os.path.isfile(path), f"Missing {path}"

    # ------------------------------------------------------------------ #
    #  semantic_check – structural / content validation
    # ------------------------------------------------------------------ #

    def _load_dashboard(self, name):
        path = os.path.join(self.REPO_DIR, "grafana", "dashboards", name)
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def test_executive_overview_valid_json_structure(self):
        """Executive overview has correct title, uid, tags and templating."""
        dash = self._load_dashboard("executive-overview.json")
        assert dash.get("title") == "Platform Executive Overview"
        assert dash.get("uid") == "exec-overview"
        tags = dash.get("tags", [])
        assert "executive" in tags and "platform" in tags
        # Template variables
        var_names = [v.get("name") for v in dash.get("templating", {}).get("list", [])]
        assert "environment" in var_names or "env" in var_names

    def test_service_red_valid_json_structure(self):
        """Service RED dashboard has correct title, uid, tags and template vars."""
        dash = self._load_dashboard("service-red.json")
        assert dash.get("title") == "Service RED Metrics"
        assert dash.get("uid") == "service-red"
        tags = dash.get("tags", [])
        assert "service" in tags and "red" in tags
        var_names = [v.get("name") for v in dash.get("templating", {}).get("list", [])]
        assert "namespace" in var_names
        assert "service" in var_names

    def test_infrastructure_use_valid_json_structure(self):
        """Infrastructure USE dashboard has correct title, uid, tags."""
        dash = self._load_dashboard("infrastructure-use.json")
        assert dash.get("title") == "Infrastructure USE Metrics"
        assert dash.get("uid") == "infra-use"
        tags = dash.get("tags", [])
        assert "infrastructure" in tags and "use" in tags

    def test_provisioning_dashboards_yaml_valid(self):
        """Dashboard provisioning YAML is valid and has required structure."""
        path = os.path.join(self.REPO_DIR, "grafana", "provisioning", "dashboards.yaml")
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        assert data is not None
        assert "apiVersion" in data
        providers = data.get("providers", [])
        assert len(providers) >= 1
        provider = providers[0]
        assert "options" in provider
        assert "path" in provider["options"]

    def test_provisioning_datasources_yaml_valid(self):
        """Datasources YAML includes Prometheus and PostgreSQL."""
        path = os.path.join(self.REPO_DIR, "grafana", "provisioning", "datasources.yaml")
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        assert data is not None
        ds_names = [ds.get("name", "").lower() for ds in data.get("datasources", [])]
        assert any("prometheus" in n for n in ds_names), "Prometheus datasource missing"
        assert any("postgres" in n for n in ds_names), "PostgreSQL datasource missing"

    def test_executive_dashboard_has_panels(self):
        """Executive dashboard contains multiple panels or rows."""
        dash = self._load_dashboard("executive-overview.json")
        panels = dash.get("panels", [])
        # May have rows with nested panels
        total = len(panels)
        for p in panels:
            total += len(p.get("panels", []))
        assert total >= 4, f"Expected ≥4 panels, got {total}"

    # ------------------------------------------------------------------ #
    #  functional_check – deeper content validation
    # ------------------------------------------------------------------ #

    def test_executive_overview_stat_panels_promql(self):
        """Executive overview stat panels contain PromQL-like expressions."""
        dash = self._load_dashboard("executive-overview.json")
        text = json.dumps(dash)
        assert "http_requests_total" in text, "Missing http_requests_total metric"
        assert "rate(" in text, "Missing rate() function in PromQL queries"

    def test_service_red_latency_heatmap_or_histogram(self):
        """Service RED dashboard includes latency histogram/heatmap queries."""
        dash = self._load_dashboard("service-red.json")
        text = json.dumps(dash)
        assert "histogram_quantile" in text or "heatmap" in text.lower(), \
            "Missing histogram_quantile or heatmap panel in service RED dashboard"

    def test_infrastructure_use_node_metrics(self):
        """Infrastructure USE dashboard references node-level metrics."""
        dash = self._load_dashboard("infrastructure-use.json")
        text = json.dumps(dash)
        assert "node_cpu" in text or "kube_node" in text, \
            "Missing node CPU or kube_node metrics in infrastructure dashboard"
        assert "node_memory" in text or "container_memory" in text, \
            "Missing memory metrics in infrastructure dashboard"

    def test_executive_overview_threshold_configuration(self):
        """Executive dashboard panels include threshold configurations."""
        dash = self._load_dashboard("executive-overview.json")
        text = json.dumps(dash)
        # Thresholds may appear as "thresholds" key or "steps"
        assert "threshold" in text.lower(), "No threshold configuration found"

    def test_service_red_status_code_color_overrides(self):
        """Service RED dashboard differentiates HTTP status codes (2xx/4xx/5xx)."""
        dash = self._load_dashboard("service-red.json")
        text = json.dumps(dash)
        assert "status" in text, "No status reference in service RED dashboard"
        # Should reference 5xx error filtering
        assert re.search(r'5[x.]{2}|5\d{2}|status=~"5', text), \
            "No 5xx error filtering in service RED dashboard"

    def test_infrastructure_use_pod_resources(self):
        """Infrastructure dashboard monitors pod CPU/memory vs requests/limits."""
        dash = self._load_dashboard("infrastructure-use.json")
        text = json.dumps(dash)
        has_pod = "container_cpu" in text or "kube_pod" in text
        assert has_pod, "Missing pod-level resource metrics"

    def test_datasource_prometheus_is_default(self):
        """Prometheus datasource is marked as default."""
        path = os.path.join(self.REPO_DIR, "grafana", "provisioning", "datasources.yaml")
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        prometheus_ds = [
            ds for ds in data.get("datasources", [])
            if "prometheus" in ds.get("name", "").lower() or ds.get("type") == "prometheus"
        ]
        assert len(prometheus_ds) >= 1
        assert prometheus_ds[0].get("isDefault") is True, "Prometheus should be the default datasource"
