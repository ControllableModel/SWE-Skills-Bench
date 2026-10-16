"""
Tests for skill: grafana-dashboards
Repo: grafana/grafana
Image: zhangyiiiiii/swe-skills-bench-golang
Task: Create Grafana dashboard JSON models for API monitoring (RED method),
      infrastructure monitoring (USE method), SLO compliance, and provisioning config.
"""

import json
import os
import re

import pytest
import yaml

REPO_DIR = "/workspace/grafana"
DASH_DIR = os.path.join(REPO_DIR, "public", "dashboards")

API_DASHBOARD = os.path.join(DASH_DIR, "api-monitoring.json")
INFRA_DASHBOARD = os.path.join(DASH_DIR, "infrastructure.json")
SLO_DASHBOARD = os.path.join(DASH_DIR, "slo-compliance.json")
PROVISIONING = os.path.join(DASH_DIR, "provisioning.yaml")


def _load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _all_panel_exprs(dashboard):
    """Recursively extract all PromQL expressions from a dashboard JSON."""
    raw = json.dumps(dashboard)
    exprs = re.findall(r'"expr"\s*:\s*"([^"]+)"', raw)
    return exprs


# ---------------------------------------------------------------------------
# Layer 1 — file_path_check
# ---------------------------------------------------------------------------

class TestFilePathCheck:
    """Verify all dashboard files exist."""

    def test_api_monitoring_exists(self):
        assert os.path.isfile(API_DASHBOARD), f"Missing {API_DASHBOARD}"

    def test_infrastructure_exists(self):
        assert os.path.isfile(INFRA_DASHBOARD), f"Missing {INFRA_DASHBOARD}"

    def test_slo_compliance_exists(self):
        assert os.path.isfile(SLO_DASHBOARD), f"Missing {SLO_DASHBOARD}"

    def test_provisioning_exists(self):
        assert os.path.isfile(PROVISIONING), f"Missing {PROVISIONING}"


# ---------------------------------------------------------------------------
# Layer 2 — semantic_check
# ---------------------------------------------------------------------------

class TestSemanticAPIDashboard:
    """Verify API monitoring dashboard structure."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.dashboard = _load_json(API_DASHBOARD)
        self.raw = json.dumps(self.dashboard)

    def test_title(self):
        title = self.dashboard.get("title", "")
        assert "API" in title, f"Expected 'API' in title; got '{title}'"

    def test_uid(self):
        uid = self.dashboard.get("uid", "")
        assert "api-monitoring" in uid, f"Expected uid 'api-monitoring'; got '{uid}'"

    def test_tags_contain_api(self):
        tags = self.dashboard.get("tags", [])
        assert "api" in tags, f"Expected 'api' tag; got {tags}"

    def test_templating_datasource(self):
        templating = self.dashboard.get("templating", {}).get("list", [])
        names = [t.get("name", "") for t in templating]
        assert "datasource" in names, f"Expected datasource variable; found {names}"

    def test_templating_namespace(self):
        templating = self.dashboard.get("templating", {}).get("list", [])
        names = [t.get("name", "") for t in templating]
        assert "namespace" in names, f"Expected namespace variable; found {names}"

    def test_templating_service(self):
        templating = self.dashboard.get("templating", {}).get("list", [])
        names = [t.get("name", "") for t in templating]
        assert "service" in names, f"Expected service variable; found {names}"

    def test_request_rate_promql(self):
        assert "http_requests_total" in self.raw, (
            "Dashboard should query http_requests_total"
        )

    def test_error_rate_promql(self):
        assert "5.." in self.raw or "5xx" in self.raw.lower() or 'status=~"5' in self.raw, (
            "Dashboard should filter 5xx errors"
        )

    def test_latency_histogram_quantile(self):
        assert "histogram_quantile" in self.raw, (
            "Dashboard should use histogram_quantile for latency"
        )

    def test_stat_panel_type(self):
        assert '"stat"' in self.raw or '"singlestat"' in self.raw, (
            "Dashboard should have stat panels for summary"
        )

    def test_heatmap_panel(self):
        assert "heatmap" in self.raw.lower(), (
            "Dashboard should have a heatmap panel for request duration"
        )

    def test_table_panel(self):
        assert "table" in self.raw.lower(), (
            "Dashboard should have a table panel for top endpoints"
        )


class TestSemanticInfraDashboard:
    """Verify infrastructure dashboard structure."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.dashboard = _load_json(INFRA_DASHBOARD)
        self.raw = json.dumps(self.dashboard)

    def test_title(self):
        title = self.dashboard.get("title", "")
        assert "Infrastructure" in title or "infrastructure" in title.lower(), (
            f"Expected 'Infrastructure' in title; got '{title}'"
        )

    def test_uid(self):
        uid = self.dashboard.get("uid", "")
        assert "infrastructure" in uid, f"Expected uid 'infrastructure'; got '{uid}'"

    def test_cpu_metric(self):
        assert "node_cpu_seconds_total" in self.raw, (
            "Should query node_cpu_seconds_total"
        )

    def test_memory_metric(self):
        assert "node_memory" in self.raw, "Should query node_memory metrics"

    def test_disk_metric(self):
        assert "node_disk" in self.raw or "node_filesystem" in self.raw, (
            "Should query disk metrics"
        )

    def test_network_metric(self):
        assert "node_network" in self.raw, "Should query node_network metrics"

    def test_gauge_panel(self):
        assert "gauge" in self.raw.lower(), "Should have gauge panels"

    def test_instance_variable(self):
        templating = self.dashboard.get("templating", {}).get("list", [])
        names = [t.get("name", "") for t in templating]
        assert "instance" in names, f"Expected instance variable; found {names}"


class TestSemanticSLODashboard:
    """Verify SLO compliance dashboard structure."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.dashboard = _load_json(SLO_DASHBOARD)
        self.raw = json.dumps(self.dashboard)

    def test_title(self):
        title = self.dashboard.get("title", "")
        assert "SLO" in title.upper(), f"Expected 'SLO' in title; got '{title}'"

    def test_uid(self):
        uid = self.dashboard.get("uid", "")
        assert "slo" in uid, f"Expected 'slo' in uid; got '{uid}'"

    def test_error_budget(self):
        assert "error_budget" in self.raw.lower() or "budget" in self.raw.lower(), (
            "SLO dashboard should show error budget"
        )

    def test_burn_rate(self):
        assert "burn" in self.raw.lower(), (
            "SLO dashboard should show burn rate"
        )

    def test_achievement(self):
        assert "achievement" in self.raw.lower() or "compliance" in self.raw.lower() or "slo" in self.raw.lower(), (
            "SLO dashboard should show achievement/compliance"
        )


class TestSemanticProvisioning:
    """Verify provisioning configuration."""

    @pytest.fixture(autouse=True)
    def _load(self):
        with open(PROVISIONING, "r", encoding="utf-8") as f:
            self.cfg = yaml.safe_load(f)

    def test_api_version(self):
        assert self.cfg.get("apiVersion") == 1, (
            f"Expected apiVersion 1; got {self.cfg.get('apiVersion')}"
        )

    def test_provider_name(self):
        providers = self.cfg.get("providers", [])
        assert len(providers) >= 1, "Should have at least one provider"
        names = [p.get("name", "") for p in providers]
        assert "default" in names, f"Expected provider 'default'; found {names}"

    def test_disable_deletion(self):
        providers = self.cfg.get("providers", [])
        for p in providers:
            if p.get("name") == "default":
                assert p.get("disableDeletion") is True, (
                    "disableDeletion should be true"
                )

    def test_file_type(self):
        providers = self.cfg.get("providers", [])
        for p in providers:
            assert p.get("type") == "file", f"Expected type=file; got {p.get('type')}"


# ---------------------------------------------------------------------------
# Layer 3 — functional_check
# ---------------------------------------------------------------------------

class TestFunctionalJSONValidity:
    """Verify all dashboard JSON files are valid."""

    def test_api_monitoring_valid(self):
        data = _load_json(API_DASHBOARD)
        assert isinstance(data, dict), "api-monitoring.json should be a JSON object"
        assert "schemaVersion" in data, "Dashboard should have schemaVersion"

    def test_infrastructure_valid(self):
        data = _load_json(INFRA_DASHBOARD)
        assert isinstance(data, dict), "infrastructure.json should be a JSON object"
        assert "schemaVersion" in data, "Dashboard should have schemaVersion"

    def test_slo_compliance_valid(self):
        data = _load_json(SLO_DASHBOARD)
        assert isinstance(data, dict), "slo-compliance.json should be a JSON object"
        assert "schemaVersion" in data, "Dashboard should have schemaVersion"


class TestFunctionalPromQLVariables:
    """Verify PromQL queries use templating variables correctly."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.api = _load_json(API_DASHBOARD)
        self.infra = _load_json(INFRA_DASHBOARD)

    def test_api_uses_namespace_variable(self):
        raw = json.dumps(self.api)
        assert "$namespace" in raw, "API queries should use $namespace variable"

    def test_api_uses_service_variable(self):
        raw = json.dumps(self.api)
        assert "$service" in raw, "API queries should use $service variable"

    def test_infra_uses_instance_variable(self):
        raw = json.dumps(self.infra)
        assert "$instance" in raw, "Infrastructure queries should use $instance variable"


class TestFunctionalThresholds:
    """Verify threshold configurations on panels."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.api = _load_json(API_DASHBOARD)
        self.api_raw = json.dumps(self.api)

    def test_error_rate_thresholds(self):
        # The raw JSON should contain threshold values for error rate
        assert "threshold" in self.api_raw.lower() or "thresholds" in self.api_raw.lower(), (
            "API dashboard should have threshold configurations"
        )

    def test_refresh_interval(self):
        refresh = self.api.get("refresh", "")
        assert "30s" in str(refresh) or "10s" in str(refresh), (
            f"Dashboard refresh should be 30s; got '{refresh}'"
        )


class TestFunctionalProvisioningYAML:
    """Verify provisioning YAML loads correctly."""

    def test_provisioning_valid_yaml(self):
        with open(PROVISIONING, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        assert cfg is not None, "Provisioning YAML should be valid"
        assert "providers" in cfg or "apiVersion" in cfg, (
            "Provisioning should have providers or apiVersion"
        )

    def test_dashboard_path(self):
        with open(PROVISIONING, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        raw = yaml.dump(cfg)
        assert "/var/lib/grafana/dashboards" in raw, (
            "Provisioning should reference /var/lib/grafana/dashboards"
        )
