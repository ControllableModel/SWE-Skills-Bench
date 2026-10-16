"""
Test skill: prometheus-configuration
Verify that Prometheus scrape configuration, recording rules, alert rules,
and service discovery targets have been correctly created for a multi-service
application, including proper YAML structure and promtool validation.
"""

import os
import json
import subprocess
import pytest


class TestPrometheusConfiguration:
    REPO_DIR = "/workspace/prometheus"
    CONFIG_BASE = "documentation/examples/custom-app"

    @staticmethod
    def _load_yaml(filepath):
        try:
            import yaml
        except ImportError:
            subprocess.run(["pip", "install", "pyyaml"],
                           capture_output=True, text=True, timeout=60)
            import yaml
        with open(filepath) as f:
            return yaml.safe_load(f)

    # === File Path Checks ===

    def test_prometheus_yml_exists(self):
        """Verify prometheus.yml config file exists"""
        filepath = os.path.join(self.REPO_DIR, self.CONFIG_BASE, "prometheus.yml")
        assert os.path.exists(filepath), f"prometheus.yml not found at {filepath}"

    def test_recording_rules_exist(self):
        """Verify recording rules file exists"""
        filepath = os.path.join(self.REPO_DIR, self.CONFIG_BASE, "rules/recording_rules.yml")
        assert os.path.exists(filepath), f"recording_rules.yml not found at {filepath}"

    def test_alert_rules_exist(self):
        """Verify alert rules file exists"""
        filepath = os.path.join(self.REPO_DIR, self.CONFIG_BASE, "rules/alert_rules.yml")
        assert os.path.exists(filepath), f"alert_rules.yml not found at {filepath}"

    def test_service_discovery_targets_exist(self):
        """Verify service discovery targets file exists"""
        filepath = os.path.join(self.REPO_DIR, self.CONFIG_BASE, "targets/services.json")
        assert os.path.exists(filepath), f"services.json not found at {filepath}"

    # === Semantic Checks ===

    def test_prometheus_yml_has_global_settings(self):
        """Verify global scrape_interval and evaluation_interval are set to 15s"""
        filepath = os.path.join(self.REPO_DIR, self.CONFIG_BASE, "prometheus.yml")
        config = self._load_yaml(filepath)
        global_config = config.get("global", {})
        scrape = global_config.get("scrape_interval", "")
        eval_int = global_config.get("evaluation_interval", "")
        assert "15s" in str(scrape), f"Global scrape_interval should be 15s, got {scrape}"
        assert "15s" in str(eval_int), f"Global evaluation_interval should be 15s, got {eval_int}"

    def test_prometheus_yml_has_external_labels(self):
        """Verify external labels include cluster and environment"""
        filepath = os.path.join(self.REPO_DIR, self.CONFIG_BASE, "prometheus.yml")
        config = self._load_yaml(filepath)
        external_labels = config.get("global", {}).get("external_labels", {})
        assert "cluster" in external_labels, "External labels should include 'cluster'"
        assert "environment" in external_labels or "env" in external_labels, \
            "External labels should include 'environment'"

    def test_prometheus_yml_has_six_scrape_jobs(self):
        """Verify scrape_configs defines all six required jobs"""
        filepath = os.path.join(self.REPO_DIR, self.CONFIG_BASE, "prometheus.yml")
        config = self._load_yaml(filepath)
        scrape_configs = config.get("scrape_configs", [])
        job_names = [sc.get("job_name", "") for sc in scrape_configs]
        required_jobs = ["prometheus", "api-gateway", "backend-services",
                         "postgres-exporter", "redis-exporter"]
        for job in required_jobs:
            assert any(job in jn for jn in job_names), \
                f"Scrape config missing job '{job}'. Found jobs: {job_names}"

    def test_prometheus_yml_has_kubernetes_pod_sd(self):
        """Verify scrape config includes Kubernetes pod service discovery"""
        filepath = os.path.join(self.REPO_DIR, self.CONFIG_BASE, "prometheus.yml")
        with open(filepath) as f:
            content = f.read()
        assert "kubernetes" in content.lower(), \
            "Scrape config should include Kubernetes pod SD"
        assert "prometheus.io/scrape" in content, \
            "K8s pod SD should filter on prometheus.io/scrape annotation"

    def test_service_discovery_has_three_services(self):
        """Verify services.json defines three backend services with proper labels"""
        filepath = os.path.join(self.REPO_DIR, self.CONFIG_BASE, "targets/services.json")
        with open(filepath) as f:
            data = json.load(f)
        assert isinstance(data, list), "services.json should be a JSON array"
        all_targets = []
        for group in data:
            targets = group.get("targets", [])
            all_targets.extend(targets)
            labels = group.get("labels", {})
            assert "env" in labels or "environment" in labels, \
                "Each target group should have env label"
        service_names = ["user-service", "order-service", "payment-service"]
        for svc in service_names:
            assert any(svc in t for t in all_targets), \
                f"services.json should include target for {svc}"

    def test_recording_rules_has_required_metrics(self):
        """Verify recording rules define all five required pre-computed metrics"""
        filepath = os.path.join(self.REPO_DIR, self.CONFIG_BASE, "rules/recording_rules.yml")
        config = self._load_yaml(filepath)
        groups = config.get("groups", [])
        assert len(groups) >= 1, "Recording rules should have at least one group"
        all_records = []
        for group in groups:
            for rule in group.get("rules", []):
                if "record" in rule:
                    all_records.append(rule["record"])
        expected = [
            "job:http_requests_total:rate5m",
            "job:http_request_duration_seconds:p99",
            "job:http_request_errors:rate5m",
            "instance:node_cpu_utilization:ratio",
            "instance:node_memory_utilization:ratio",
        ]
        for metric in expected:
            assert metric in all_records, \
                f"Recording rules missing metric '{metric}'. Found: {all_records}"

    def test_alert_rules_has_required_alerts(self):
        """Verify alert rules define all six required alerts with correct severity"""
        filepath = os.path.join(self.REPO_DIR, self.CONFIG_BASE, "rules/alert_rules.yml")
        config = self._load_yaml(filepath)
        groups = config.get("groups", [])
        all_alerts = {}
        for group in groups:
            for rule in group.get("rules", []):
                if "alert" in rule:
                    name = rule["alert"]
                    severity = rule.get("labels", {}).get("severity", "")
                    all_alerts[name] = severity

        expected_alerts = {
            "HighErrorRate": "critical",
            "HighLatency": "warning",
            "ServiceDown": "critical",
            "HighCPU": "warning",
            "HighMemory": "warning",
            "DiskSpaceRunningLow": "critical",
        }
        for alert_name, expected_sev in expected_alerts.items():
            assert alert_name in all_alerts, \
                f"Alert rules missing '{alert_name}'. Found: {list(all_alerts.keys())}"
            assert all_alerts[alert_name] == expected_sev, \
                f"Alert '{alert_name}' severity should be '{expected_sev}', got '{all_alerts[alert_name]}'"

    def test_alert_rules_have_annotations(self):
        """Verify alert rules include summary and description annotations with templates"""
        filepath = os.path.join(self.REPO_DIR, self.CONFIG_BASE, "rules/alert_rules.yml")
        with open(filepath) as f:
            content = f.read()
        assert "summary" in content, "Alert rules should have summary annotations"
        assert "description" in content, "Alert rules should have description annotations"
        assert "{{ $labels" in content or "{{$labels" in content, \
            "Alert annotations should use template variables like {{ $labels.instance }}"

    # === Functional Checks ===

    def test_prometheus_yml_is_valid_yaml(self):
        """Verify prometheus.yml parses as valid YAML"""
        filepath = os.path.join(self.REPO_DIR, self.CONFIG_BASE, "prometheus.yml")
        config = self._load_yaml(filepath)
        assert config is not None, "prometheus.yml is empty or invalid YAML"
        assert "scrape_configs" in config, "prometheus.yml should have scrape_configs"

    def test_recording_rules_is_valid_yaml(self):
        """Verify recording_rules.yml parses as valid YAML"""
        filepath = os.path.join(self.REPO_DIR, self.CONFIG_BASE, "rules/recording_rules.yml")
        config = self._load_yaml(filepath)
        assert config is not None, "recording_rules.yml is empty"
        assert "groups" in config, "Recording rules should have 'groups' key"

    def test_alert_rules_is_valid_yaml(self):
        """Verify alert_rules.yml parses as valid YAML"""
        filepath = os.path.join(self.REPO_DIR, self.CONFIG_BASE, "rules/alert_rules.yml")
        config = self._load_yaml(filepath)
        assert config is not None, "alert_rules.yml is empty"
        assert "groups" in config, "Alert rules should have 'groups' key"

    def test_promtool_check_rules(self):
        """Verify rules files pass promtool check rules validation"""
        promtool = os.path.join(self.REPO_DIR, "promtool")
        if not os.path.exists(promtool):
            # Try to find promtool in PATH
            which_result = subprocess.run(["which", "promtool"],
                                          capture_output=True, text=True)
            if which_result.returncode != 0:
                pytest.skip("promtool not available")
            promtool = "promtool"

        for rules_file in ["rules/recording_rules.yml", "rules/alert_rules.yml"]:
            filepath = os.path.join(self.REPO_DIR, self.CONFIG_BASE, rules_file)
            if not os.path.exists(filepath):
                continue
            result = subprocess.run(
                [promtool, "check", "rules", filepath],
                capture_output=True, text=True, timeout=30
            )
            assert result.returncode == 0, \
                f"promtool check rules failed for {rules_file}: {result.stderr}"

    def test_services_json_is_valid_json(self):
        """Verify services.json is valid JSON"""
        filepath = os.path.join(self.REPO_DIR, self.CONFIG_BASE, "targets/services.json")
        with open(filepath) as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError as e:
                pytest.fail(f"services.json is not valid JSON: {e}")
        assert isinstance(data, list), "services.json should be a JSON array"
