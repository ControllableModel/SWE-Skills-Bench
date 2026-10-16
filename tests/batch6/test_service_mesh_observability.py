"""
Test skill: service-mesh-observability
Verify that the Agent builds a service mesh observability stack with
Prometheus scrape configs, recording/alerting rules, Grafana dashboards,
Kiali CR, and OTel Collector config.
"""

import os
import re
import json
import pytest

try:
    import yaml
except ImportError:
    yaml = None


class TestServiceMeshObservability:
    REPO_DIR = "/workspace/linkerd2"

    # === File Path Checks ===

    def test_prometheus_config_exists(self):
        assert os.path.exists(
            os.path.join(self.REPO_DIR, "observability/prometheus/config.yaml")
        )

    def test_prometheus_alerts_exists(self):
        assert os.path.exists(
            os.path.join(self.REPO_DIR, "observability/prometheus/alerts.yaml")
        )

    def test_mesh_overview_dashboard_exists(self):
        assert os.path.exists(
            os.path.join(self.REPO_DIR, "observability/grafana/dashboards/mesh-overview.json")
        )

    def test_service_detail_dashboard_exists(self):
        assert os.path.exists(
            os.path.join(self.REPO_DIR, "observability/grafana/dashboards/service-detail.json")
        )

    def test_datasources_exists(self):
        assert os.path.exists(
            os.path.join(self.REPO_DIR, "observability/grafana/datasources.yaml")
        )

    def test_kiali_cr_exists(self):
        assert os.path.exists(
            os.path.join(self.REPO_DIR, "observability/kiali/kiali-cr.yaml")
        )

    def test_otel_collector_config_exists(self):
        assert os.path.exists(
            os.path.join(self.REPO_DIR, "observability/otel-collector/config.yaml")
        )

    # === Semantic Checks ===

    def test_prometheus_has_scrape_configs(self):
        """Prometheus config should have scrape configs for Istio metrics"""
        path = os.path.join(self.REPO_DIR, "observability/prometheus/config.yaml")
        with open(path) as f:
            content = f.read()
        assert "scrape_configs" in content, "Missing scrape_configs"
        assert "envoy" in content.lower() or "istio" in content.lower(), (
            "Should scrape Istio/Envoy metrics"
        )

    def test_prometheus_has_recording_rules(self):
        """Prometheus should have recording rules for golden signals"""
        path = os.path.join(self.REPO_DIR, "observability/prometheus/config.yaml")
        with open(path) as f:
            content = f.read()
        assert "record:" in content or "recording" in content, "Missing recording rules"
        assert "error_rate" in content or "istio_error" in content, "Missing error rate rule"
        assert "latency" in content, "Missing latency rule"

    def test_alerts_has_high_error_rate(self):
        """Alerts should include HighErrorRate alert"""
        path = os.path.join(self.REPO_DIR, "observability/prometheus/alerts.yaml")
        with open(path) as f:
            content = f.read()
        assert "HighErrorRate" in content, "Missing HighErrorRate alert"
        assert "critical" in content, "Should have critical severity"

    def test_alerts_has_latency_alerts(self):
        """Alerts should include latency threshold alerts"""
        path = os.path.join(self.REPO_DIR, "observability/prometheus/alerts.yaml")
        with open(path) as f:
            content = f.read()
        assert "Latency" in content or "latency" in content, "Missing latency alerts"

    def test_alerts_has_circuit_breaker(self):
        """Alerts should detect circuit breaker trips"""
        path = os.path.join(self.REPO_DIR, "observability/prometheus/alerts.yaml")
        with open(path) as f:
            content = f.read()
        assert "CircuitBreaker" in content or "UO" in content, (
            "Missing CircuitBreaker alert"
        )

    def test_mesh_overview_has_golden_signals(self):
        """Mesh overview dashboard should have golden signal panels"""
        path = os.path.join(self.REPO_DIR, "observability/grafana/dashboards/mesh-overview.json")
        with open(path) as f:
            data = json.load(f)
        content_str = json.dumps(data)
        assert "mesh-overview" in data.get("uid", "") or "mesh" in data.get("title", "").lower(), (
            "Dashboard UID should be mesh-overview"
        )
        assert "request" in content_str.lower() or "rate" in content_str.lower(), (
            "Should have request rate panel"
        )
        assert "error" in content_str.lower(), "Should have error rate panel"
        assert "latency" in content_str.lower() or "p99" in content_str.lower(), (
            "Should have latency panel"
        )

    def test_service_detail_has_variables(self):
        """Service detail dashboard should have namespace and service variables"""
        path = os.path.join(self.REPO_DIR, "observability/grafana/dashboards/service-detail.json")
        with open(path) as f:
            data = json.load(f)
        templating = data.get("templating", {}).get("list", [])
        names = [t.get("name", "") for t in templating]
        assert "namespace" in names, "Missing namespace variable"
        assert "service" in names, "Missing service variable"

    def test_datasources_has_prometheus_and_jaeger(self):
        """Datasources should include Prometheus and Jaeger"""
        if yaml is None:
            pytest.skip("PyYAML not available")
        path = os.path.join(self.REPO_DIR, "observability/grafana/datasources.yaml")
        with open(path) as f:
            data = yaml.safe_load(f)
        ds_names = [d.get("name", "").lower() for d in data.get("datasources", [])]
        assert any("prometheus" in n for n in ds_names), "Missing Prometheus datasource"
        assert any("jaeger" in n for n in ds_names), "Missing Jaeger datasource"

    def test_kiali_has_external_services(self):
        """Kiali CR should reference Prometheus, Grafana, Jaeger"""
        path = os.path.join(self.REPO_DIR, "observability/kiali/kiali-cr.yaml")
        with open(path) as f:
            content = f.read()
        assert "prometheus" in content.lower(), "Kiali should reference Prometheus"
        assert "grafana" in content.lower(), "Kiali should reference Grafana"
        assert "jaeger" in content.lower() or "tracing" in content.lower(), (
            "Kiali should reference Jaeger"
        )

    def test_otel_collector_has_otlp_receiver(self):
        """OTel Collector should have OTLP receiver"""
        path = os.path.join(self.REPO_DIR, "observability/otel-collector/config.yaml")
        with open(path) as f:
            content = f.read()
        assert "otlp" in content, "Missing OTLP receiver"
        assert "4317" in content, "Should listen on gRPC port 4317"

    # === Functional Checks ===

    def test_all_yaml_files_valid(self):
        """All YAML files should parse without errors"""
        if yaml is None:
            pytest.skip("PyYAML not available")
        base = os.path.join(self.REPO_DIR, "observability")
        for root, _dirs, files in os.walk(base):
            for fname in files:
                if fname.endswith((".yaml", ".yml")):
                    filepath = os.path.join(root, fname)
                    try:
                        with open(filepath) as f:
                            list(yaml.safe_load_all(f))
                    except yaml.YAMLError as e:
                        pytest.fail(f"{filepath} YAML error: {e}")

    def test_dashboard_jsons_valid(self):
        """All Grafana dashboard JSON files should be valid"""
        for fname in ("mesh-overview.json", "service-detail.json"):
            path = os.path.join(
                self.REPO_DIR, f"observability/grafana/dashboards/{fname}"
            )
            with open(path) as f:
                try:
                    json.load(f)
                except json.JSONDecodeError as e:
                    pytest.fail(f"{fname} JSON error: {e}")

    def test_alerts_yaml_valid(self):
        """Alerts YAML should be valid"""
        if yaml is None:
            pytest.skip("PyYAML not available")
        path = os.path.join(self.REPO_DIR, "observability/prometheus/alerts.yaml")
        with open(path) as f:
            data = yaml.safe_load(f)
        assert data is not None, "Alerts file is empty"
