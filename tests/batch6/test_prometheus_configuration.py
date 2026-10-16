"""
Test skill: prometheus-configuration
Verify that the Agent correctly configures Prometheus monitoring for a
multi-service e-commerce platform with recording rules, alerting rules,
alertmanager, and redis exporter.
"""

import os
import re
import subprocess
import pytest

try:
    import yaml
except ImportError:
    yaml = None


class TestPrometheusConfiguration:
    REPO_DIR = "/workspace/prometheus"

    @staticmethod
    def _load_yaml(path):
        if yaml is None:
            subprocess.run(["pip", "install", "pyyaml"], capture_output=True, text=True, timeout=30)
            import yaml as _yaml
            with open(path, "r") as f:
                return _yaml.safe_load(f)
        with open(path, "r") as f:
            return yaml.safe_load(f)

    # === File Path Checks ===

    def test_prometheus_yml_exists(self):
        """Verify that the main Prometheus config file exists"""
        path = os.path.join(self.REPO_DIR, "monitoring/prometheus/prometheus.yml")
        assert os.path.exists(path), f"prometheus.yml not found at {path}"

    def test_recording_rules_file_exists(self):
        """Verify that recording rules file exists"""
        path = os.path.join(self.REPO_DIR, "monitoring/prometheus/rules/recording-rules.yml")
        assert os.path.exists(path), f"recording-rules.yml not found at {path}"

    def test_alerting_rules_file_exists(self):
        """Verify that alerting rules file exists"""
        path = os.path.join(self.REPO_DIR, "monitoring/prometheus/rules/alerting-rules.yml")
        assert os.path.exists(path), f"alerting-rules.yml not found at {path}"

    def test_node_alerts_file_exists(self):
        """Verify that node-level alerts file exists"""
        path = os.path.join(self.REPO_DIR, "monitoring/prometheus/rules/node-alerts.yml")
        assert os.path.exists(path), f"node-alerts.yml not found at {path}"

    def test_alertmanager_config_exists(self):
        """Verify that Alertmanager configuration exists"""
        path = os.path.join(self.REPO_DIR, "monitoring/alertmanager/alertmanager.yml")
        assert os.path.exists(path), f"alertmanager.yml not found at {path}"

    def test_redis_exporter_yaml_exists(self):
        """Verify that Redis exporter Kubernetes manifest exists"""
        path = os.path.join(self.REPO_DIR, "monitoring/exporters/redis-exporter.yaml")
        assert os.path.exists(path), f"redis-exporter.yaml not found at {path}"

    # === Semantic Checks ===

    def test_prometheus_yml_global_settings(self):
        """Verify Prometheus global settings (scrape_interval, evaluation_interval)"""
        path = os.path.join(self.REPO_DIR, "monitoring/prometheus/prometheus.yml")
        data = self._load_yaml(path)
        assert data is not None, "prometheus.yml is empty or invalid"

        g = data.get("global", {})
        assert "scrape_interval" in g, "Missing global scrape_interval"
        assert "evaluation_interval" in g, "Missing global evaluation_interval"

    def test_prometheus_has_kubernetes_sd(self):
        """Verify that scrape configs use kubernetes_sd_configs"""
        path = os.path.join(self.REPO_DIR, "monitoring/prometheus/prometheus.yml")
        with open(path, "r") as f:
            content = f.read()

        assert "kubernetes_sd_configs" in content, (
            "Prometheus should use kubernetes_sd_configs for service discovery"
        )

    def test_prometheus_has_required_scrape_jobs(self):
        """Verify that Prometheus defines required scrape jobs"""
        path = os.path.join(self.REPO_DIR, "monitoring/prometheus/prometheus.yml")
        data = self._load_yaml(path)
        scrape_configs = data.get("scrape_configs", [])
        job_names = [sc.get("job_name", "") for sc in scrape_configs]

        expected_jobs = ["kubernetes-pods", "node-exporter", "redis-exporter"]
        for job in expected_jobs:
            found = any(job in jn for jn in job_names)
            assert found, f"Missing scrape job: {job}. Found jobs: {job_names}"

    def test_prometheus_drops_high_cardinality_metrics(self):
        """Verify metric relabeling drops go_* and promhttp_* metrics"""
        path = os.path.join(self.REPO_DIR, "monitoring/prometheus/prometheus.yml")
        with open(path, "r") as f:
            content = f.read()

        assert "go_" in content or "go_.*" in content, (
            "Should have metric relabeling to drop go_* metrics"
        )

    def test_recording_rules_has_red_metrics(self):
        """Verify recording rules define RED metrics (rate, errors, duration)"""
        path = os.path.join(self.REPO_DIR, "monitoring/prometheus/rules/recording-rules.yml")
        data = self._load_yaml(path)
        assert data is not None

        groups = data.get("groups", [])
        assert len(groups) >= 1, "Recording rules should have at least 1 group"

        all_records = []
        for group in groups:
            for rule in group.get("rules", []):
                if "record" in rule:
                    all_records.append(rule["record"])

        # Check RED metrics
        has_rate = any("request" in r and "rate" in r for r in all_records)
        has_error = any("error" in r for r in all_records)
        has_duration = any("duration" in r or "latency" in r for r in all_records)

        assert has_rate, f"Recording rules missing request rate metric. Records: {all_records}"
        assert has_error, f"Recording rules missing error rate metric. Records: {all_records}"
        assert has_duration, f"Recording rules missing latency/duration metric. Records: {all_records}"

    def test_recording_rules_has_percentile_metrics(self):
        """Verify recording rules include P50, P95, P99 latency percentiles"""
        path = os.path.join(self.REPO_DIR, "monitoring/prometheus/rules/recording-rules.yml")
        with open(path, "r") as f:
            content = f.read()

        assert "histogram_quantile" in content, (
            "Recording rules should use histogram_quantile for latency percentiles"
        )
        assert "0.95" in content, "Missing P95 latency recording rule"
        assert "0.99" in content, "Missing P99 latency recording rule"

    def test_alerting_rules_has_service_alerts(self):
        """Verify alerting rules include service-level alerts"""
        path = os.path.join(self.REPO_DIR, "monitoring/prometheus/rules/alerting-rules.yml")
        data = self._load_yaml(path)
        assert data is not None

        groups = data.get("groups", [])
        all_alerts = []
        for group in groups:
            for rule in group.get("rules", []):
                if "alert" in rule:
                    all_alerts.append(rule["alert"])

        assert any("ErrorRate" in a or "Error" in a for a in all_alerts), (
            f"Missing error rate alert. Alerts: {all_alerts}"
        )
        assert any("Latency" in a or "Slow" in a for a in all_alerts), (
            f"Missing latency alert. Alerts: {all_alerts}"
        )

    def test_alerting_rules_checkout_stricter_threshold(self):
        """Verify that checkout service has stricter latency threshold (500ms vs 1s)"""
        path = os.path.join(self.REPO_DIR, "monitoring/prometheus/rules/alerting-rules.yml")
        with open(path, "r") as f:
            content = f.read()

        assert "checkout" in content.lower(), (
            "Alerting rules should have checkout-specific alert with stricter threshold"
        )
        assert "0.5" in content, (
            "Checkout latency threshold should be 0.5s (500ms)"
        )

    def test_alertmanager_has_routing_and_receivers(self):
        """Verify Alertmanager has route tree and receivers"""
        path = os.path.join(self.REPO_DIR, "monitoring/alertmanager/alertmanager.yml")
        data = self._load_yaml(path)
        assert data is not None

        assert "route" in data, "Alertmanager missing route configuration"
        assert "receivers" in data, "Alertmanager missing receivers"

        receivers = data.get("receivers", [])
        receiver_names = [r.get("name", "") for r in receivers]
        assert len(receiver_names) >= 2, (
            f"Alertmanager should have at least 2 receivers, got: {receiver_names}"
        )

    def test_alertmanager_has_pagerduty_and_slack(self):
        """Verify Alertmanager has PagerDuty and Slack receivers"""
        path = os.path.join(self.REPO_DIR, "monitoring/alertmanager/alertmanager.yml")
        with open(path, "r") as f:
            content = f.read()

        assert "pagerduty" in content.lower(), "Alertmanager missing PagerDuty receiver"
        assert "slack" in content.lower(), "Alertmanager missing Slack receiver"

    def test_alertmanager_has_inhibition_rules(self):
        """Verify Alertmanager has inhibition rules"""
        path = os.path.join(self.REPO_DIR, "monitoring/alertmanager/alertmanager.yml")
        data = self._load_yaml(path)
        assert data is not None

        inhibit_rules = data.get("inhibit_rules", [])
        assert len(inhibit_rules) >= 1, (
            "Alertmanager should have inhibition rules"
        )

    def test_redis_exporter_is_valid_k8s_manifest(self):
        """Verify Redis exporter YAML is a valid Kubernetes manifest"""
        path = os.path.join(self.REPO_DIR, "monitoring/exporters/redis-exporter.yaml")
        data = self._load_yaml(path)
        assert data is not None

        # Could be a single doc or multi-doc
        if isinstance(data, dict):
            assert "kind" in data, "Redis exporter YAML missing 'kind' field"
        # Verify it's a Deployment or has Deployment
        with open(path, "r") as f:
            content = f.read()
        assert "Deployment" in content or "deployment" in content, (
            "Redis exporter should have a Deployment resource"
        )
        assert "9121" in content, (
            "Redis exporter should expose port 9121"
        )

    # === Functional Checks ===

    def test_all_yaml_files_are_valid(self):
        """Verify that all monitoring YAML files parse without errors"""
        monitoring_dir = os.path.join(self.REPO_DIR, "monitoring")
        if not os.path.exists(monitoring_dir):
            pytest.fail("monitoring/ directory not found")

        yaml_files = []
        for root, dirs, files in os.walk(monitoring_dir):
            for f in files:
                if f.endswith((".yml", ".yaml")):
                    yaml_files.append(os.path.join(root, f))

        assert len(yaml_files) >= 5, (
            f"Expected at least 5 YAML files in monitoring/, found {len(yaml_files)}"
        )

        for yf in yaml_files:
            try:
                self._load_yaml(yf)
            except Exception as e:
                pytest.fail(f"Invalid YAML in {yf}: {e}")

    def test_node_alerts_cover_cpu_memory_disk(self):
        """Verify node alerts cover CPU, memory, and disk"""
        path = os.path.join(self.REPO_DIR, "monitoring/prometheus/rules/node-alerts.yml")
        data = self._load_yaml(path)
        groups = data.get("groups", [])

        all_alerts = []
        for group in groups:
            for rule in group.get("rules", []):
                if "alert" in rule:
                    all_alerts.append(rule["alert"])

        alerts_str = " ".join(all_alerts).lower()
        assert "cpu" in alerts_str, f"Node alerts missing CPU alert. Alerts: {all_alerts}"
        assert "memory" in alerts_str or "mem" in alerts_str, (
            f"Node alerts missing memory alert. Alerts: {all_alerts}"
        )
        assert "disk" in alerts_str, f"Node alerts missing disk alert. Alerts: {all_alerts}"
