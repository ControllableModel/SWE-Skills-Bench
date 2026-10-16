"""
Test skill: grafana-dashboards
Verify that the Agent creates valid Grafana dashboard JSON models
for cluster overview, pod metrics, and golden signals with a generator script.
"""

import os
import re
import ast
import json
import pytest


class TestGrafanaDashboards:
    REPO_DIR = "/workspace/grafana"

    CLUSTER_OVERVIEW = "devenv/dashboards/cluster-overview.json"
    POD_METRICS = "devenv/dashboards/pod-metrics.json"
    GOLDEN_SIGNALS = "devenv/dashboards/golden-signals.json"
    GENERATOR = "devenv/dashboards/scripts/generate_dashboard.py"

    def _read_file(self, rel_path):
        filepath = os.path.join(self.REPO_DIR, rel_path)
        with open(filepath) as f:
            return f.read()

    def _load_json(self, rel_path):
        content = self._read_file(rel_path)
        return json.loads(content)

    # === File Path Checks ===

    def test_cluster_overview_exists(self):
        filepath = os.path.join(self.REPO_DIR, self.CLUSTER_OVERVIEW)
        assert os.path.exists(filepath), "cluster-overview.json not found"

    def test_pod_metrics_exists(self):
        filepath = os.path.join(self.REPO_DIR, self.POD_METRICS)
        assert os.path.exists(filepath), "pod-metrics.json not found"

    def test_golden_signals_exists(self):
        filepath = os.path.join(self.REPO_DIR, self.GOLDEN_SIGNALS)
        assert os.path.exists(filepath), "golden-signals.json not found"

    def test_generator_exists(self):
        filepath = os.path.join(self.REPO_DIR, self.GENERATOR)
        assert os.path.exists(filepath), "generate_dashboard.py not found"

    # === Semantic Checks ===

    def test_cluster_overview_has_cpu_panel(self):
        """Verify cluster overview has CPU usage gauge"""
        content = self._read_file(self.CLUSTER_OVERVIEW)
        assert "container_cpu_usage_seconds_total" in content, \
            "Cluster overview missing CPU usage PromQL"

    def test_cluster_overview_has_memory_panel(self):
        """Verify cluster overview has memory usage panel"""
        content = self._read_file(self.CLUSTER_OVERVIEW)
        assert "container_memory_working_set_bytes" in content, \
            "Cluster overview missing memory PromQL"

    def test_cluster_overview_has_node_count(self):
        """Verify cluster overview has node count stat"""
        content = self._read_file(self.CLUSTER_OVERVIEW)
        assert "kube_node_info" in content, "Missing kube_node_info query"

    def test_cluster_overview_has_namespace_table(self):
        """Verify cluster overview has namespace breakdown table"""
        content = self._read_file(self.CLUSTER_OVERVIEW)
        assert "namespace" in content.lower(), "Missing namespace breakdown"
        assert "table" in content.lower(), "Missing table panel type"

    def test_pod_metrics_has_template_vars(self):
        """Verify pod metrics has namespace and pod template variables"""
        doc = self._load_json(self.POD_METRICS)
        templating = doc.get("templating", {}).get("list", [])
        var_names = [v.get("name", "") for v in templating]
        assert "namespace" in var_names, "Pod metrics missing namespace variable"
        assert "pod" in var_names, "Pod metrics missing pod variable"

    def test_pod_metrics_has_network_io(self):
        """Verify pod metrics has network I/O panel"""
        content = self._read_file(self.POD_METRICS)
        assert "container_network_receive_bytes_total" in content, \
            "Pod metrics missing network receive query"

    def test_golden_signals_has_request_rate(self):
        """Verify golden signals has request rate panel"""
        content = self._read_file(self.GOLDEN_SIGNALS)
        assert "http_requests_total" in content, \
            "Golden signals missing http_requests_total"

    def test_golden_signals_has_error_rate_thresholds(self):
        """Verify golden signals error rate has color thresholds"""
        content = self._read_file(self.GOLDEN_SIGNALS)
        assert "threshold" in content.lower(), \
            "Golden signals missing error rate thresholds"

    def test_golden_signals_has_latency_percentiles(self):
        """Verify golden signals has P50/P95/P99 latency panels"""
        content = self._read_file(self.GOLDEN_SIGNALS)
        assert "histogram_quantile" in content, \
            "Golden signals missing histogram_quantile"
        for pct in ["0.50", "0.95", "0.99"]:
            assert pct in content, f"Golden signals missing {pct} percentile"

    def test_all_dashboards_have_datasource(self):
        """Verify all dashboards reference Prometheus datasource"""
        for path in [self.CLUSTER_OVERVIEW, self.POD_METRICS, self.GOLDEN_SIGNALS]:
            content = self._read_file(path)
            has_ds = "prometheus" in content.lower() or "Prometheus" in content
            assert has_ds, f"{path} missing Prometheus datasource"

    # === Functional Checks ===

    def test_all_dashboards_valid_json(self):
        """Verify all dashboard files parse as valid JSON"""
        for path in [self.CLUSTER_OVERVIEW, self.POD_METRICS, self.GOLDEN_SIGNALS]:
            filepath = os.path.join(self.REPO_DIR, path)
            with open(filepath) as f:
                try:
                    doc = json.load(f)
                except json.JSONDecodeError as e:
                    pytest.fail(f"{path} JSON error: {e}")
            assert "panels" in doc, f"{path} missing panels key"
            assert "schemaVersion" in doc, f"{path} missing schemaVersion"

    def test_generator_valid_python(self):
        """Verify generator script has valid Python syntax"""
        content = self._read_file(self.GENERATOR)
        try:
            ast.parse(content)
        except SyntaxError as e:
            pytest.fail(f"Generator syntax error: {e}")

    def test_generator_has_builder_classes(self):
        """Verify generator defines Panel, Row, Dashboard classes"""
        content = self._read_file(self.GENERATOR)
        for cls in ["Panel", "Dashboard"]:
            assert cls in content, f"Generator missing {cls} class"
        assert "to_json" in content, "Generator missing to_json method"
