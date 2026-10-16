"""
Test skill: service-mesh-observability
Verify that the Agent correctly implements Golden Signal Metrics
and a Grafana Dashboard for Linkerd2 viz.
"""

import os
import re
import json
import pytest


class TestServiceMeshObservability:
    REPO_DIR = "/workspace/linkerd2"

    # === File Path Checks ===

    def test_prometheus_go_exists(self):
        """Verify prometheus.go was modified"""
        path = os.path.join(
            self.REPO_DIR, "viz/metrics-api/prometheus.go"
        )
        assert os.path.exists(path), "prometheus.go not found"

    def test_prometheus_configmap_yaml_exists(self):
        """Verify prometheus-configmap.yaml exists"""
        path = os.path.join(
            self.REPO_DIR,
            "viz/charts/prometheus/templates/prometheus-configmap.yaml",
        )
        assert os.path.exists(path), "prometheus-configmap.yaml not found"

    def test_grafana_dashboard_json_exists(self):
        """Verify linkerd-service-health.json was created"""
        path = os.path.join(
            self.REPO_DIR,
            "viz/charts/grafana/dashboards/linkerd-service-health.json",
        )
        assert os.path.exists(path), "linkerd-service-health.json not found"

    def test_prometheus_test_go_exists(self):
        """Verify prometheus_test.go was modified"""
        path = os.path.join(
            self.REPO_DIR, "viz/metrics-api/prometheus_test.go"
        )
        assert os.path.exists(path), "prometheus_test.go not found"

    # === Semantic Checks: Golden Signal Queries ===

    def _load_prometheus_go(self):
        path = os.path.join(
            self.REPO_DIR, "viz/metrics-api/prometheus.go"
        )
        return open(path).read()

    def test_golden_signal_queries_function(self):
        """Verify GoldenSignalQueries function is defined"""
        source = self._load_prometheus_go()
        assert "GoldenSignalQueries" in source, (
            "GoldenSignalQueries function not found"
        )

    def test_golden_signal_takes_service_namespace(self):
        """Verify GoldenSignalQueries accepts service and namespace params"""
        source = self._load_prometheus_go()
        match = re.search(r'func\s+GoldenSignalQueries\s*\((.*?)\)', source, re.DOTALL)
        assert match, "GoldenSignalQueries function signature not found"
        params = match.group(1)
        assert "service" in params.lower() and "namespace" in params.lower(), (
            "GoldenSignalQueries does not accept service and namespace params"
        )

    def test_golden_signal_returns_four_queries(self):
        """Verify GoldenSignalQueries returns 4 PromQL expressions"""
        source = self._load_prometheus_go()
        # Check for latency, error rate, request rate, saturation
        has_latency = "latency" in source.lower() or "histogram_quantile" in source
        has_error = "error" in source.lower()
        has_request_rate = "request" in source.lower() and "rate" in source.lower()
        has_saturation = "saturation" in source.lower() or "active" in source.lower()
        all_signals = [has_latency, has_error, has_request_rate, has_saturation]
        assert sum(all_signals) >= 3, (
            f"Expected at least 3 of 4 golden signals, found {sum(all_signals)}"
        )

    # === Semantic Checks: Recording Rules ===

    def _load_configmap_yaml(self):
        path = os.path.join(
            self.REPO_DIR,
            "viz/charts/prometheus/templates/prometheus-configmap.yaml",
        )
        return open(path).read()

    def test_recording_rules_group_name(self):
        """Verify recording rules group is named linkerd_golden_signals"""
        source = self._load_configmap_yaml()
        assert "linkerd_golden_signals" in source, (
            "Recording rules group 'linkerd_golden_signals' not found"
        )

    def test_recording_rules_latency_percentiles(self):
        """Verify P50/P95/P99 latency recording rules exist"""
        source = self._load_configmap_yaml()
        has_p50 = "0.5" in source or "p50" in source.lower() or "P50" in source
        has_p95 = "0.95" in source or "p95" in source.lower() or "P95" in source
        has_p99 = "0.99" in source or "p99" in source.lower() or "P99" in source
        assert has_p50 and has_p95 and has_p99, (
            "Missing P50/P95/P99 latency percentile recording rules"
        )

    def test_recording_rules_error_rate(self):
        """Verify error rate recording rule exists"""
        source = self._load_configmap_yaml()
        assert "error" in source.lower() and "rate" in source.lower(), (
            "Error rate recording rule not found"
        )

    # === Semantic Checks: Grafana Dashboard ===

    def _load_dashboard_json(self):
        path = os.path.join(
            self.REPO_DIR,
            "viz/charts/grafana/dashboards/linkerd-service-health.json",
        )
        return open(path).read()

    def _parse_dashboard(self):
        content = self._load_dashboard_json()
        return json.loads(content)

    def test_dashboard_valid_json(self):
        """Verify dashboard file is valid JSON"""
        try:
            self._parse_dashboard()
        except json.JSONDecodeError as e:
            pytest.fail(f"Dashboard JSON is invalid: {e}")

    def test_dashboard_schema_version(self):
        """Verify dashboard uses schema version 36"""
        dashboard = self._parse_dashboard()
        assert dashboard.get("schemaVersion") == 36, (
            f"Expected schemaVersion 36, got {dashboard.get('schemaVersion')}"
        )

    def test_dashboard_has_service_template_variable(self):
        """Verify dashboard has 'service' template variable"""
        dashboard = self._parse_dashboard()
        templating = dashboard.get("templating", {})
        var_list = templating.get("list", [])
        service_vars = [v for v in var_list if v.get("name") == "service"]
        assert len(service_vars) > 0, (
            "Dashboard missing 'service' template variable"
        )

    # === Functional Checks ===

    def test_dashboard_has_required_panels(self):
        """Verify dashboard contains key panels for golden signals"""
        dashboard = self._parse_dashboard()
        panels = dashboard.get("panels", [])
        panel_titles = [p.get("title", "") for p in panels]
        # Should have panels related to latency, error rate, request rate
        combined = " ".join(panel_titles).lower()
        assert "latency" in combined or "duration" in combined, (
            "No latency panel found in dashboard"
        )
        assert "error" in combined, "No error rate panel found in dashboard"
        assert "request" in combined or "rate" in combined, (
            "No request rate panel found in dashboard"
        )

    def test_dashboard_panels_use_datasource_variable(self):
        """Verify dashboard panels reference datasource variable"""
        content = self._load_dashboard_json()
        assert "${datasource}" in content or "datasource" in content, (
            "Panels do not reference the datasource variable"
        )

    def test_recording_rules_request_rate(self):
        """Verify request rate recording rule exists"""
        source = self._load_configmap_yaml()
        assert "request" in source.lower() and "rate" in source.lower(), (
            "Request rate recording rule not found"
        )

    def test_prometheus_go_has_promql(self):
        """Verify prometheus.go contains PromQL query expressions"""
        source = self._load_prometheus_go()
        has_promql = (
            "histogram_quantile" in source
            or "rate(" in source
            or "sum(" in source
        )
        assert has_promql, "No PromQL expressions found in prometheus.go"

    def test_dashboard_has_datasource_template_variable(self):
        """Verify dashboard has 'datasource' template variable"""
        dashboard = self._parse_dashboard()
        templating = dashboard.get("templating", {})
        var_list = templating.get("list", [])
        ds_vars = [v for v in var_list if v.get("name") == "datasource"]
        assert len(ds_vars) > 0, (
            "Dashboard missing 'datasource' template variable"
        )

    def test_recording_rules_saturation(self):
        """Verify saturation recording rule exists"""
        source = self._load_configmap_yaml()
        has_saturation = (
            "saturation" in source.lower()
            or "connections" in source.lower()
            or "active" in source.lower()
            or "concurrent" in source.lower()
        )
        assert has_saturation, "Saturation recording rule not found"
