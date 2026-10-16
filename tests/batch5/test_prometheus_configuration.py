"""
Test skill: prometheus-configuration
Verify that the Agent correctly configures Prometheus monitoring for a
microservices stack with scrape configs, recording rules, and alerting rules.
"""

import os
import subprocess
import pytest


class TestPrometheusConfiguration:
    REPO_DIR = "/workspace/prometheus"

    PROM_CONFIG = "documentation/examples/microservices/prometheus.yml"
    RECORDING_RULES = "documentation/examples/microservices/rules/recording_rules.yml"
    ALERTING_RULES = "documentation/examples/microservices/rules/alerting_rules.yml"
    API_GW_TARGETS = "documentation/examples/microservices/targets/api_gateway.json"
    SERVICES_TARGETS = "documentation/examples/microservices/targets/services.json"

    def _read_file(self, rel_path):
        filepath = os.path.join(self.REPO_DIR, rel_path)
        with open(filepath) as f:
            return f.read()

    def _load_yaml(self, rel_path):
        import yaml
        filepath = os.path.join(self.REPO_DIR, rel_path)
        with open(filepath) as f:
            return yaml.safe_load(f)

    def _load_json(self, rel_path):
        import json
        filepath = os.path.join(self.REPO_DIR, rel_path)
        with open(filepath) as f:
            return json.load(f)

    # === File Path Checks ===

    def test_prometheus_yml_exists(self):
        """Verify prometheus.yml main config file exists"""
        filepath = os.path.join(self.REPO_DIR, self.PROM_CONFIG)
        assert os.path.exists(filepath), f"prometheus.yml not found at {filepath}"

    def test_recording_rules_exists(self):
        """Verify recording_rules.yml exists"""
        filepath = os.path.join(self.REPO_DIR, self.RECORDING_RULES)
        assert os.path.exists(filepath), f"recording_rules.yml not found"

    def test_alerting_rules_exists(self):
        """Verify alerting_rules.yml exists"""
        filepath = os.path.join(self.REPO_DIR, self.ALERTING_RULES)
        assert os.path.exists(filepath), f"alerting_rules.yml not found"

    def test_target_files_exist(self):
        """Verify service discovery target JSON files exist"""
        for path in [self.API_GW_TARGETS, self.SERVICES_TARGETS]:
            filepath = os.path.join(self.REPO_DIR, path)
            assert os.path.exists(filepath), f"Target file not found: {filepath}"

    # === Semantic Checks ===

    def test_prometheus_global_config(self):
        """Verify global settings: scrape_interval=15s, evaluation_interval=15s"""
        config = self._load_yaml(self.PROM_CONFIG)
        global_cfg = config.get("global", {})
        assert global_cfg.get("scrape_interval") == "15s", \
            f"scrape_interval should be 15s, got {global_cfg.get('scrape_interval')}"
        assert global_cfg.get("evaluation_interval") == "15s", \
            f"evaluation_interval should be 15s, got {global_cfg.get('evaluation_interval')}"

    def test_prometheus_external_labels(self):
        """Verify external_labels include cluster and environment"""
        config = self._load_yaml(self.PROM_CONFIG)
        labels = config.get("global", {}).get("external_labels", {})
        assert "cluster" in labels, "Missing external_label: cluster"
        assert "environment" in labels or "env" in labels, \
            "Missing external_label: environment"

    def test_prometheus_scrape_configs_for_three_services(self):
        """Verify scrape configs define targets for api-gateway, user-service, order-service"""
        config = self._load_yaml(self.PROM_CONFIG)
        scrape_configs = config.get("scrape_configs", [])
        job_names = [sc.get("job_name", "") for sc in scrape_configs]
        job_names_str = str(job_names).lower()
        assert "api" in job_names_str or "gateway" in job_names_str, \
            f"Missing scrape config for api-gateway. Jobs: {job_names}"
        assert "user" in job_names_str, \
            f"Missing scrape config for user-service. Jobs: {job_names}"
        assert "order" in job_names_str, \
            f"Missing scrape config for order-service. Jobs: {job_names}"

    def test_scrape_configs_use_file_sd(self):
        """Verify scrape configs use file_sd_configs for service discovery"""
        config = self._load_yaml(self.PROM_CONFIG)
        scrape_configs = config.get("scrape_configs", [])
        has_file_sd = any(
            "file_sd_configs" in sc for sc in scrape_configs
        )
        assert has_file_sd, \
            "Scrape configs should use file_sd_configs for service discovery"

    def test_metric_relabel_drops_go_metrics(self):
        """Verify metric_relabel_configs drops go_ prefixed metrics"""
        content = self._read_file(self.PROM_CONFIG)
        assert "go_" in content, \
            "Config missing go_ metric drop rule in metric_relabel_configs"
        assert "drop" in content.lower(), \
            "Config missing 'drop' action for go_ metrics"

    def test_recording_rules_compute_sli_metrics(self):
        """Verify recording rules define 5 SLI metric computations"""
        config = self._load_yaml(self.RECORDING_RULES)
        groups = config.get("groups", [])
        assert len(groups) > 0, "No recording rule groups defined"
        all_rules = []
        for group in groups:
            all_rules.extend(group.get("rules", []))
        record_names = [r.get("record", "") for r in all_rules]
        expected_metrics = [
            "requests:rate", "errors:rate", "error_ratio",
            "latency", "availability"
        ]
        for metric in expected_metrics:
            found = any(metric in name for name in record_names)
            assert found, \
                f"Recording rules missing metric containing '{metric}'. Rules: {record_names}"

    def test_alerting_rules_define_key_alerts(self):
        """Verify alerting rules define HighErrorRate, HighLatency, ServiceDown"""
        config = self._load_yaml(self.ALERTING_RULES)
        groups = config.get("groups", [])
        all_rules = []
        for group in groups:
            all_rules.extend(group.get("rules", []))
        alert_names = [r.get("alert", "") for r in all_rules]
        alert_names_lower = [n.lower() for n in alert_names]
        for expected in ["error", "latency", "down"]:
            found = any(expected in name for name in alert_names_lower)
            assert found, \
                f"Alerting rules missing alert containing '{expected}'. Alerts: {alert_names}"

    def test_alerting_rules_have_severity_labels(self):
        """Verify alerting rules include severity labels (warning/critical)"""
        config = self._load_yaml(self.ALERTING_RULES)
        groups = config.get("groups", [])
        for group in groups:
            for rule in group.get("rules", []):
                if "alert" in rule:
                    labels = rule.get("labels", {})
                    assert "severity" in labels, \
                        f"Alert '{rule['alert']}' missing severity label"
                    assert labels["severity"] in ("warning", "critical", "info"), \
                        f"Alert '{rule['alert']}' has invalid severity: {labels['severity']}"

    # === Functional Checks ===

    def test_api_gateway_targets_json_valid(self):
        """Verify api_gateway.json has valid targets structure"""
        data = self._load_json(self.API_GW_TARGETS)
        assert isinstance(data, list), "Targets file should be a JSON array"
        assert len(data) > 0, "Targets file should not be empty"
        first = data[0]
        assert "targets" in first, "Target entry missing 'targets' key"
        assert len(first["targets"]) >= 3, \
            f"Expected 3+ api-gateway targets, found {len(first['targets'])}"

    def test_services_targets_json_valid(self):
        """Verify services.json has targets for user-service and order-service"""
        data = self._load_json(self.SERVICES_TARGETS)
        assert isinstance(data, list), "Targets file should be a JSON array"
        all_labels = str(data).lower()
        assert "user" in all_labels, "services.json missing user-service targets"
        assert "order" in all_labels, "services.json missing order-service targets"
        total_targets = sum(len(entry.get("targets", [])) for entry in data)
        assert total_targets >= 4, \
            f"Expected 4+ service targets (2 user + 2 order), found {total_targets}"

    def test_recording_rules_valid_promql_syntax(self):
        """Verify recording rules have syntactically valid PromQL expressions"""
        config = self._load_yaml(self.RECORDING_RULES)
        groups = config.get("groups", [])
        for group in groups:
            for rule in group.get("rules", []):
                expr = rule.get("expr", "")
                assert len(expr) > 0, \
                    f"Recording rule '{rule.get('record', '')}' has empty expression"
                # Basic PromQL syntax check - should have metric name and operation
                assert not expr.startswith("="), \
                    f"Invalid PromQL expression: {expr[:100]}"

    def test_promtool_check_config(self):
        """Verify prometheus.yml passes promtool validation if available"""
        promtool = None
        for candidate in [
            os.path.join(self.REPO_DIR, "promtool"),
            "promtool",
        ]:
            result = subprocess.run(
                ["which", candidate] if candidate == "promtool"
                else ["test", "-x", candidate],
                capture_output=True, text=True,
            )
            if result.returncode == 0:
                promtool = candidate
                break
        if promtool is None:
            # Try building promtool first
            build_result = subprocess.run(
                ["go", "build", "-o", "promtool", "./cmd/promtool"],
                cwd=self.REPO_DIR,
                capture_output=True, text=True,
                timeout=300,
            )
            if build_result.returncode == 0:
                promtool = os.path.join(self.REPO_DIR, "promtool")

        if promtool is None:
            pytest.skip("promtool not available")

        config_path = os.path.join(self.REPO_DIR, self.PROM_CONFIG)
        result = subprocess.run(
            [promtool, "check", "config", config_path],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, \
            f"promtool check config failed: {result.stderr[:500]}"
