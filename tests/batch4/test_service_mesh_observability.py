"""
Tests for skill: service-mesh-observability
Repo: linkerd/linkerd2
Image: zhangyiiiiii/swe-skills-bench-golang
Task: Build a service mesh observability dashboard configuration with Prometheus
      scraping, recording rules, alerting rules, and Grafana dashboards.
"""

import json
import os
import re

import pytest
import yaml

REPO_DIR = "/workspace/linkerd2"
OBS_DIR = os.path.join(REPO_DIR, "viz", "observability")

PROM_DIR = os.path.join(OBS_DIR, "prometheus")
GRAFANA_DIR = os.path.join(OBS_DIR, "grafana")

SCRAPE_CONFIG = os.path.join(PROM_DIR, "scrape-config.yaml")
RECORDING_RULES = os.path.join(PROM_DIR, "recording-rules.yaml")
ALERTING_RULES = os.path.join(PROM_DIR, "alerting-rules.yaml")
MESH_OVERVIEW = os.path.join(GRAFANA_DIR, "mesh-overview.json")
SERVICE_DETAIL = os.path.join(GRAFANA_DIR, "service-detail.json")


def _load_yaml(path):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Layer 1 — file_path_check
# ---------------------------------------------------------------------------

class TestFilePathCheck:
    """Verify all required observability files exist."""

    def test_scrape_config_exists(self):
        assert os.path.isfile(SCRAPE_CONFIG), f"Missing {SCRAPE_CONFIG}"

    def test_recording_rules_exists(self):
        assert os.path.isfile(RECORDING_RULES), f"Missing {RECORDING_RULES}"

    def test_alerting_rules_exists(self):
        assert os.path.isfile(ALERTING_RULES), f"Missing {ALERTING_RULES}"

    def test_mesh_overview_exists(self):
        assert os.path.isfile(MESH_OVERVIEW), f"Missing {MESH_OVERVIEW}"

    def test_service_detail_exists(self):
        assert os.path.isfile(SERVICE_DETAIL), f"Missing {SERVICE_DETAIL}"


# ---------------------------------------------------------------------------
# Layer 2 — semantic_check
# ---------------------------------------------------------------------------

class TestSemanticScrapeConfig:
    """Verify Prometheus scrape configuration."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.cfg = _load_yaml(SCRAPE_CONFIG)
        self.raw = yaml.dump(self.cfg)

    def test_linkerd_proxy_job(self):
        assert "linkerd-proxy" in self.raw or "linkerd" in self.raw, (
            "Should have a linkerd-proxy scrape job"
        )

    def test_scrape_interval(self):
        assert "15s" in self.raw, "Scrape interval should be 15s"

    def test_metrics_path(self):
        assert "/metrics" in self.raw, "Metrics path should be /metrics"

    def test_port_4191(self):
        assert "4191" in self.raw, "Should scrape Linkerd admin port 4191"

    def test_kubernetes_sd(self):
        assert "kubernetes_sd" in self.raw or "kubernetes" in self.raw, (
            "Should use Kubernetes service discovery"
        )


class TestSemanticRecordingRules:
    """Verify recording rules for golden signals."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.cfg = _load_yaml(RECORDING_RULES)
        self.raw = yaml.dump(self.cfg)

    def test_groups_defined(self):
        groups = self.cfg.get("groups", [])
        assert len(groups) >= 1, "Should have at least one rule group"

    def test_request_rate_rule(self):
        assert "request_rate" in self.raw, "Should have request_rate recording rule"

    def test_success_rate_rule(self):
        assert "success_rate" in self.raw, "Should have success_rate recording rule"

    def test_latency_p50_rule(self):
        assert "p50" in self.raw or "0.5" in self.raw, "Should have P50 latency rule"

    def test_latency_p99_rule(self):
        assert "p99" in self.raw or "0.99" in self.raw, "Should have P99 latency rule"

    def test_tcp_connections_rule(self):
        assert "tcp" in self.raw.lower(), "Should have TCP connection recording rule"

    def test_rate_function(self):
        assert "rate(" in self.raw, "Recording rules should use rate() function"

    def test_histogram_quantile(self):
        assert "histogram_quantile" in self.raw, (
            "Latency rules should use histogram_quantile"
        )


class TestSemanticAlertingRules:
    """Verify alerting rules for SLO violations."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.cfg = _load_yaml(ALERTING_RULES)
        self.raw = yaml.dump(self.cfg)

    def test_high_error_rate_alert(self):
        assert "HighErrorRate" in self.raw or "high_error" in self.raw.lower(), (
            "Should have a high error rate alert"
        )

    def test_high_latency_alert(self):
        assert "HighLatency" in self.raw or "high_latency" in self.raw.lower(), (
            "Should have a high latency alert"
        )

    def test_proxy_down_alert(self):
        assert "ProxyDown" in self.raw or "proxy_down" in self.raw.lower(), (
            "Should have a proxy down alert"
        )

    def test_severity_labels(self):
        assert "critical" in self.raw or "warning" in self.raw, (
            "Alerts should have severity labels"
        )

    def test_for_duration(self):
        assert re.search(r"for:\s*\d+m", self.raw), (
            "Alerts should have a 'for' duration"
        )


class TestSemanticMeshOverview:
    """Verify mesh overview Grafana dashboard."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.dashboard = _load_json(MESH_OVERVIEW)

    def test_title(self):
        title = self.dashboard.get("title", "")
        assert "mesh" in title.lower() or "overview" in title.lower(), (
            f"Dashboard title should mention mesh overview; got '{title}'"
        )

    def test_templating_namespace(self):
        raw = json.dumps(self.dashboard)
        assert "namespace" in raw, "Should have namespace templating variable"

    def test_panels_exist(self):
        panels = self.dashboard.get("panels", [])
        rows = self.dashboard.get("rows", [])
        assert len(panels) > 0 or len(rows) > 0, (
            "Dashboard should have panels or rows"
        )

    def test_promql_queries(self):
        raw = json.dumps(self.dashboard)
        assert "request_rate" in raw or "request_total" in raw, (
            "Dashboard should have request rate PromQL queries"
        )

    def test_stat_panels(self):
        raw = json.dumps(self.dashboard)
        assert "stat" in raw.lower() or "singlestat" in raw.lower(), (
            "Dashboard should have stat panels for summary"
        )


class TestSemanticServiceDetail:
    """Verify service detail Grafana dashboard."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.dashboard = _load_json(SERVICE_DETAIL)

    def test_title(self):
        title = self.dashboard.get("title", "")
        assert "service" in title.lower() or "detail" in title.lower(), (
            f"Dashboard title should mention service detail; got '{title}'"
        )

    def test_deployment_variable(self):
        raw = json.dumps(self.dashboard)
        assert "deployment" in raw, "Should have deployment templating variable"

    def test_heatmap_panel(self):
        raw = json.dumps(self.dashboard).lower()
        assert "heatmap" in raw or "histogram" in raw, (
            "Service detail should have a latency heatmap or histogram panel"
        )


# ---------------------------------------------------------------------------
# Layer 3 — functional_check
# ---------------------------------------------------------------------------

class TestFunctionalRecordingRulePromQL:
    """Verify PromQL syntax in recording rules."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.cfg = _load_yaml(RECORDING_RULES)

    def test_success_rate_formula(self):
        raw = yaml.dump(self.cfg)
        # success_rate should be a ratio
        assert "classification" in raw or "success" in raw, (
            "Success rate rule should filter on classification=success"
        )

    def test_latency_by_deployment(self):
        raw = yaml.dump(self.cfg)
        assert "deployment" in raw, (
            "Recording rules should aggregate by deployment"
        )

    def test_inbound_direction(self):
        raw = yaml.dump(self.cfg)
        assert "inbound" in raw, (
            "Recording rules should filter on direction=inbound"
        )

    def test_rule_interval(self):
        groups = self.cfg.get("groups", [])
        for g in groups:
            interval = g.get("interval", "")
            if "30s" in str(interval):
                return
        pytest.fail("Rule group should have 30s evaluation interval")


class TestFunctionalAlertThresholds:
    """Verify alert threshold values."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.cfg = _load_yaml(ALERTING_RULES)
        self.raw = yaml.dump(self.cfg)

    def test_error_rate_threshold_99(self):
        assert "0.99" in self.raw, (
            "Error rate alert should fire below 0.99 success rate"
        )

    def test_latency_threshold_500(self):
        assert "500" in self.raw, (
            "Latency alert should fire above 500ms P99"
        )

    def test_proxy_down_check(self):
        assert "up" in self.raw and "0" in self.raw, (
            "Proxy down alert should check up == 0"
        )


class TestFunctionalDashboardJSON:
    """Verify dashboard JSON validity and structure."""

    def test_mesh_overview_valid_json(self):
        with open(MESH_OVERVIEW, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert "title" in data, "Dashboard must have a title"

    def test_service_detail_valid_json(self):
        with open(SERVICE_DETAIL, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert "title" in data, "Dashboard must have a title"

    def test_all_yaml_valid(self):
        for dirpath, _, filenames in os.walk(OBS_DIR):
            for fn in filenames:
                if fn.endswith(".yaml") or fn.endswith(".yml"):
                    fpath = os.path.join(dirpath, fn)
                    with open(fpath, "r", encoding="utf-8") as f:
                        doc = yaml.safe_load(f)
                    assert doc is not None, f"Failed to parse {fpath}"
