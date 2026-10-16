"""
Test skill: prometheus-configuration
Verify that the Agent correctly creates a production-grade Prometheus
configuration with Kubernetes SD, recording rules, alerting rules, and
Alertmanager config.
"""

import os
import re
import subprocess
import pytest


class TestPrometheusConfiguration:
    REPO_DIR = "/workspace/prometheus"
    CONFIG_DIR = "/workspace/prometheus/documentation/examples/k8s-monitoring"

    # === File Path Checks ===

    def test_prometheus_yml_exists(self):
        """Verify prometheus.yml exists in k8s-monitoring directory"""
        fpath = os.path.join(self.CONFIG_DIR, "prometheus.yml")
        assert os.path.isfile(fpath), f"prometheus.yml not found at {fpath}"

    def test_recording_rules_yml_exists(self):
        """Verify recording_rules.yml exists"""
        fpath = os.path.join(self.CONFIG_DIR, "recording_rules.yml")
        assert os.path.isfile(fpath), f"recording_rules.yml not found at {fpath}"

    def test_alerting_rules_yml_exists(self):
        """Verify alerting_rules.yml exists"""
        fpath = os.path.join(self.CONFIG_DIR, "alerting_rules.yml")
        assert os.path.isfile(fpath), f"alerting_rules.yml not found at {fpath}"

    def test_alertmanager_yml_exists(self):
        """Verify alertmanager.yml exists"""
        fpath = os.path.join(self.CONFIG_DIR, "alertmanager.yml")
        assert os.path.isfile(fpath), f"alertmanager.yml not found at {fpath}"

    # === Semantic Checks ===

    def test_prometheus_yml_has_global_config(self):
        """Verify prometheus.yml has correct global scrape and evaluation intervals"""
        import yaml
        fpath = os.path.join(self.CONFIG_DIR, "prometheus.yml")
        with open(fpath, "r") as f:
            config = yaml.safe_load(f)
        assert "global" in config, "prometheus.yml missing 'global' section"
        global_cfg = config["global"]
        assert "scrape_interval" in global_cfg, "Global config missing 'scrape_interval'"
        assert "evaluation_interval" in global_cfg, "Global config missing 'evaluation_interval'"

    def test_prometheus_yml_has_four_scrape_jobs(self):
        """Verify prometheus.yml defines at least 4 scrape jobs"""
        import yaml
        fpath = os.path.join(self.CONFIG_DIR, "prometheus.yml")
        with open(fpath, "r") as f:
            config = yaml.safe_load(f)
        scrape_configs = config.get("scrape_configs", [])
        assert len(scrape_configs) >= 4, (
            f"Expected at least 4 scrape jobs, found {len(scrape_configs)}: "
            f"{[j.get('job_name', 'unnamed') for j in scrape_configs]}"
        )

    def test_prometheus_yml_has_kubernetes_sd(self):
        """Verify prometheus.yml uses kubernetes_sd_configs"""
        fpath = os.path.join(self.CONFIG_DIR, "prometheus.yml")
        with open(fpath, "r") as f:
            content = f.read()
        assert "kubernetes_sd_configs" in content, "prometheus.yml should use kubernetes_sd_configs"

    def test_prometheus_yml_scrapes_pods_by_annotation(self):
        """Verify pod scraping filters by prometheus.io/scrape annotation"""
        fpath = os.path.join(self.CONFIG_DIR, "prometheus.yml")
        with open(fpath, "r") as f:
            content = f.read()
        has_annotation = bool(re.search(r'prometheus\.io/scrape', content))
        assert has_annotation, "Pod scraping should filter by prometheus.io/scrape annotation"

    def test_prometheus_yml_references_rule_files(self):
        """Verify prometheus.yml references recording and alerting rule files"""
        import yaml
        fpath = os.path.join(self.CONFIG_DIR, "prometheus.yml")
        with open(fpath, "r") as f:
            config = yaml.safe_load(f)
        rule_files = config.get("rule_files", [])
        assert len(rule_files) >= 2, f"Should reference at least 2 rule files, found: {rule_files}"

    def test_recording_rules_has_required_metrics(self):
        """Verify recording_rules.yml defines required computed metrics"""
        fpath = os.path.join(self.CONFIG_DIR, "recording_rules.yml")
        with open(fpath, "r") as f:
            content = f.read()
        required_rules = [
            "request_rate", "error_rate", "latency_p99", "cpu_utilization"
        ]
        for rule in required_rules:
            has_rule = bool(re.search(rule.replace("_", ".*"), content, re.IGNORECASE))
            assert has_rule, f"recording_rules.yml should define metric matching: '{rule}'"

    def test_alerting_rules_has_required_alerts(self):
        """Verify alerting_rules.yml defines all six required alerts"""
        fpath = os.path.join(self.CONFIG_DIR, "alerting_rules.yml")
        with open(fpath, "r") as f:
            content = f.read()
        required_alerts = [
            "HighErrorRate", "HighLatency", "PodCrashLooping",
            "NodeHighCPU", "NodeDiskPressure", "ReplicasMismatch"
        ]
        for alert in required_alerts:
            has_alert = bool(re.search(alert.replace("_", ".*"), content, re.IGNORECASE))
            assert has_alert, f"alerting_rules.yml missing alert: '{alert}'"

    def test_alerting_rules_have_severity_labels(self):
        """Verify alerting rules include severity labels (critical/warning)"""
        fpath = os.path.join(self.CONFIG_DIR, "alerting_rules.yml")
        with open(fpath, "r") as f:
            content = f.read()
        assert "critical" in content, "Alerting rules should have 'critical' severity"
        assert "warning" in content, "Alerting rules should have 'warning' severity"

    def test_alerting_rules_have_annotations(self):
        """Verify alerting rules include summary and description annotations"""
        fpath = os.path.join(self.CONFIG_DIR, "alerting_rules.yml")
        with open(fpath, "r") as f:
            content = f.read()
        assert "summary" in content, "Alerting rules should have 'summary' annotation"
        assert "description" in content, "Alerting rules should have 'description' annotation"

    def test_alertmanager_has_routing_config(self):
        """Verify alertmanager.yml has route configuration with grouping"""
        import yaml
        fpath = os.path.join(self.CONFIG_DIR, "alertmanager.yml")
        with open(fpath, "r") as f:
            config = yaml.safe_load(f)
        assert "route" in config, "alertmanager.yml missing 'route' section"
        route = config["route"]
        assert "group_by" in route, "Route should have group_by configuration"
        group_by = route["group_by"]
        assert "namespace" in group_by or "alertname" in group_by, (
            f"Route should group by namespace or alertname. Got: {group_by}"
        )

    def test_alertmanager_has_inhibition_rules(self):
        """Verify alertmanager.yml has inhibition rules"""
        import yaml
        fpath = os.path.join(self.CONFIG_DIR, "alertmanager.yml")
        with open(fpath, "r") as f:
            config = yaml.safe_load(f)
        inhibit = config.get("inhibit_rules", [])
        assert len(inhibit) >= 1, "alertmanager.yml should have at least 1 inhibition rule"

    def test_alertmanager_has_webhook_receiver(self):
        """Verify alertmanager.yml defines a webhook receiver"""
        fpath = os.path.join(self.CONFIG_DIR, "alertmanager.yml")
        with open(fpath, "r") as f:
            content = f.read()
        assert "webhook" in content.lower(), "alertmanager.yml should define a webhook receiver"

    # === Functional Checks ===

    def test_prometheus_yml_is_valid_yaml(self):
        """Verify prometheus.yml is valid YAML"""
        import yaml
        fpath = os.path.join(self.CONFIG_DIR, "prometheus.yml")
        with open(fpath, "r") as f:
            try:
                data = yaml.safe_load(f)
            except yaml.YAMLError as e:
                pytest.fail(f"prometheus.yml is not valid YAML: {e}")
        assert isinstance(data, dict), "prometheus.yml should parse to a dict"

    def test_recording_rules_is_valid_yaml(self):
        """Verify recording_rules.yml is valid YAML with groups"""
        import yaml
        fpath = os.path.join(self.CONFIG_DIR, "recording_rules.yml")
        with open(fpath, "r") as f:
            try:
                data = yaml.safe_load(f)
            except yaml.YAMLError as e:
                pytest.fail(f"recording_rules.yml is not valid YAML: {e}")
        assert "groups" in data, "recording_rules.yml should have 'groups' key"
        groups = data["groups"]
        assert len(groups) >= 1, "recording_rules.yml should have at least 1 group"
        for group in groups:
            assert "rules" in group, f"Group '{group.get('name', 'unnamed')}' missing 'rules'"
            assert len(group["rules"]) >= 1, f"Group should have at least 1 rule"

    def test_alerting_rules_is_valid_yaml(self):
        """Verify alerting_rules.yml is valid YAML with groups"""
        import yaml
        fpath = os.path.join(self.CONFIG_DIR, "alerting_rules.yml")
        with open(fpath, "r") as f:
            try:
                data = yaml.safe_load(f)
            except yaml.YAMLError as e:
                pytest.fail(f"alerting_rules.yml is not valid YAML: {e}")
        assert "groups" in data, "alerting_rules.yml should have 'groups' key"
        groups = data["groups"]
        for group in groups:
            rules = group.get("rules", [])
            for rule in rules:
                assert "alert" in rule, f"Alert rule missing 'alert' name: {rule}"
                assert "expr" in rule, f"Alert rule '{rule.get('alert')}' missing 'expr'"

    def test_promtool_check_config(self):
        """Verify configuration passes promtool validation if available"""
        # Check if promtool is available
        which_result = subprocess.run(
            ["which", "promtool"],
            capture_output=True, text=True, timeout=10
        )
        if which_result.returncode != 0:
            pytest.skip("promtool not available in the environment")

        result = subprocess.run(
            ["promtool", "check", "config", "prometheus.yml"],
            cwd=self.CONFIG_DIR,
            capture_output=True,
            text=True,
            timeout=30
        )
        assert result.returncode == 0, f"promtool check config failed: {result.stderr}"

    def test_promtool_check_rules(self):
        """Verify rule files pass promtool rules validation if available"""
        which_result = subprocess.run(
            ["which", "promtool"],
            capture_output=True, text=True, timeout=10
        )
        if which_result.returncode != 0:
            pytest.skip("promtool not available in the environment")

        for rule_file in ["recording_rules.yml", "alerting_rules.yml"]:
            result = subprocess.run(
                ["promtool", "check", "rules", rule_file],
                cwd=self.CONFIG_DIR,
                capture_output=True,
                text=True,
                timeout=30
            )
            assert result.returncode == 0, (
                f"promtool check rules failed for {rule_file}: {result.stderr}"
            )
