"""
Test skill: prometheus-configuration
Verify that the Agent correctly adds multi-tier scrape configuration,
recording rules, alert rules, and file-based service discovery for Prometheus.
"""

import os
import json
import subprocess
import pytest


class TestPrometheusConfiguration:
    REPO_DIR = "/workspace/prometheus"

    def _load_yaml(self, rel_path):
        """Helper to load and parse a YAML file."""
        import yaml
        path = os.path.join(self.REPO_DIR, rel_path)
        assert os.path.exists(path), f"File not found: {path}"
        with open(path) as f:
            data = yaml.safe_load(f)
        assert data is not None, f"{rel_path} is empty or invalid"
        return data

    # === File Path Checks ===

    def test_multi_tier_scrape_config_exists(self):
        """Verify multi_tier_scrape.yml was created"""
        path = os.path.join(self.REPO_DIR, "config/testdata/multi_tier_scrape.yml")
        assert os.path.exists(path), f"Config not found at {path}"

    def test_recording_rules_exists(self):
        """Verify recording_rules.yml was created"""
        path = os.path.join(self.REPO_DIR, "config/testdata/recording_rules.yml")
        assert os.path.exists(path), f"Recording rules not found at {path}"

    def test_alert_rules_exists(self):
        """Verify alert_rules.yml was created"""
        path = os.path.join(self.REPO_DIR, "config/testdata/alert_rules.yml")
        assert os.path.exists(path), f"Alert rules not found at {path}"

    def test_file_sd_targets_exists(self):
        """Verify file_sd_targets.json was created"""
        path = os.path.join(self.REPO_DIR, "config/testdata/file_sd_targets.json")
        assert os.path.exists(path), f"SD targets not found at {path}"

    # === Semantic Checks: Scrape Config ===

    def test_global_scrape_interval(self):
        """Verify global scrape_interval is 15s"""
        data = self._load_yaml("config/testdata/multi_tier_scrape.yml")
        global_cfg = data.get("global", {})
        scrape_interval = str(global_cfg.get("scrape_interval", ""))
        assert "15" in scrape_interval, (
            f"Expected scrape_interval 15s, got {scrape_interval}"
        )

    def test_external_labels(self):
        """Verify external_labels include cluster and region"""
        data = self._load_yaml("config/testdata/multi_tier_scrape.yml")
        global_cfg = data.get("global", {})
        ext_labels = global_cfg.get("external_labels", {})
        assert "cluster" in ext_labels, "Missing external_label 'cluster'"
        assert "region" in ext_labels, "Missing external_label 'region'"
        assert ext_labels["cluster"] == "production", (
            f"Expected cluster=production, got {ext_labels['cluster']}"
        )

    def test_four_scrape_configs(self):
        """Verify exactly 4 scrape configs are defined"""
        data = self._load_yaml("config/testdata/multi_tier_scrape.yml")
        scrape_configs = data.get("scrape_configs", [])
        assert len(scrape_configs) == 4, (
            f"Expected 4 scrape configs, got {len(scrape_configs)}"
        )

    def test_scrape_job_names(self):
        """Verify scrape configs have correct job names"""
        data = self._load_yaml("config/testdata/multi_tier_scrape.yml")
        scrape_configs = data.get("scrape_configs", [])
        job_names = [sc.get("job_name") for sc in scrape_configs]
        for expected in ["prometheus", "node-exporter", "application-api", "kubernetes-pods"]:
            assert expected in job_names, (
                f"Missing scrape job: {expected}. Found: {job_names}"
            )

    def test_node_exporter_has_relabel_config(self):
        """Verify node-exporter scrape config has relabel_configs"""
        data = self._load_yaml("config/testdata/multi_tier_scrape.yml")
        scrape_configs = data.get("scrape_configs", [])
        node_job = next((sc for sc in scrape_configs if sc.get("job_name") == "node-exporter"), None)
        assert node_job is not None, "node-exporter job not found"
        relabel = node_job.get("relabel_configs", [])
        assert len(relabel) >= 1, "node-exporter should have relabel_configs"

    def test_application_api_has_file_sd(self):
        """Verify application-api uses file_sd_configs with correct metrics_path"""
        data = self._load_yaml("config/testdata/multi_tier_scrape.yml")
        scrape_configs = data.get("scrape_configs", [])
        api_job = next((sc for sc in scrape_configs if sc.get("job_name") == "application-api"), None)
        assert api_job is not None, "application-api job not found"
        assert "file_sd_configs" in api_job, "application-api should use file_sd_configs"
        metrics_path = api_job.get("metrics_path", "")
        assert metrics_path == "/internal/metrics", (
            f"Expected metrics_path '/internal/metrics', got '{metrics_path}'"
        )

    def test_kubernetes_pods_has_relabel_rules(self):
        """Verify kubernetes-pods scrape config has proper relabel chain"""
        data = self._load_yaml("config/testdata/multi_tier_scrape.yml")
        scrape_configs = data.get("scrape_configs", [])
        k8s_job = next((sc for sc in scrape_configs if sc.get("job_name") == "kubernetes-pods"), None)
        assert k8s_job is not None, "kubernetes-pods job not found"
        relabel = k8s_job.get("relabel_configs", [])
        assert len(relabel) >= 4, (
            f"kubernetes-pods should have at least 4 relabel rules, got {len(relabel)}"
        )

    # === Semantic Checks: Recording Rules ===

    def test_recording_rules_has_two_groups(self):
        """Verify recording rules define 2 rule groups"""
        data = self._load_yaml("config/testdata/recording_rules.yml")
        groups = data.get("groups", [])
        assert len(groups) == 2, f"Expected 2 rule groups, got {len(groups)}"

    def test_http_metrics_group_has_four_rules(self):
        """Verify http_metrics group has 4 recording rules"""
        data = self._load_yaml("config/testdata/recording_rules.yml")
        groups = data.get("groups", [])
        http_group = next((g for g in groups if g.get("name") == "http_metrics"), None)
        assert http_group is not None, "http_metrics rule group not found"
        rules = http_group.get("rules", [])
        assert len(rules) == 4, f"http_metrics should have 4 rules, got {len(rules)}"

    def test_recording_rule_names(self):
        """Verify recording rules have correct metric names"""
        data = self._load_yaml("config/testdata/recording_rules.yml")
        groups = data.get("groups", [])
        all_rules = []
        for g in groups:
            all_rules.extend(g.get("rules", []))
        rule_names = [r.get("record") for r in all_rules if "record" in r]
        expected = [
            "job:http_requests:rate5m",
            "job:http_requests_errors:rate5m",
            "job:http_requests_error_rate:percentage",
            "job:http_request_duration:p95",
        ]
        for name in expected:
            assert name in rule_names, f"Missing recording rule: {name}. Found: {rule_names}"

    # === Semantic Checks: Alert Rules ===

    def test_alert_rules_has_three_alerts(self):
        """Verify alert rules define 3 alerting rules"""
        data = self._load_yaml("config/testdata/alert_rules.yml")
        groups = data.get("groups", [])
        total_alerts = sum(len(g.get("rules", [])) for g in groups)
        assert total_alerts == 3, f"Expected 3 alert rules, got {total_alerts}"

    def test_service_down_alert_properties(self):
        """Verify ServiceDown alert has correct severity and duration"""
        data = self._load_yaml("config/testdata/alert_rules.yml")
        groups = data.get("groups", [])
        all_rules = []
        for g in groups:
            all_rules.extend(g.get("rules", []))
        svc_down = next((r for r in all_rules if r.get("alert") == "ServiceDown"), None)
        assert svc_down is not None, "ServiceDown alert not found"
        labels = svc_down.get("labels", {})
        assert labels.get("severity") == "critical", (
            f"ServiceDown severity should be 'critical', got '{labels.get('severity')}'"
        )
        annotations = svc_down.get("annotations", {})
        assert "summary" in annotations, "ServiceDown missing 'summary' annotation"
        assert "description" in annotations, "ServiceDown missing 'description' annotation"

    # === Semantic Checks: File SD Targets ===

    def test_file_sd_targets_structure(self):
        """Verify file_sd_targets.json has 2 target groups with correct counts"""
        path = os.path.join(self.REPO_DIR, "config/testdata/file_sd_targets.json")
        with open(path) as f:
            data = json.load(f)
        assert isinstance(data, list), "file_sd_targets.json should be a JSON array"
        assert len(data) == 2, f"Expected 2 target groups, got {len(data)}"
        group1_targets = data[0].get("targets", [])
        group2_targets = data[1].get("targets", [])
        assert len(group1_targets) == 2, (
            f"First target group should have 2 targets, got {len(group1_targets)}"
        )
        assert len(group2_targets) == 3, (
            f"Second target group should have 3 targets, got {len(group2_targets)}"
        )

    # === Functional Checks ===

    def test_go_test_config_passes(self):
        """Verify Go config tests pass (if applicable)"""
        result = subprocess.run(
            ["go", "test", "./config/", "-run", "TestMultiTierScrape", "-v", "-count=1"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=300,
        )
        # If the test function exists, it should pass
        if "no test to run" in result.stdout.lower() or "no test to run" in result.stderr.lower():
            pytest.skip("TestMultiTierScrape test not found in config_test.go")
        if result.returncode != 0:
            assert False, (
                f"Go config test failed:\n{result.stdout[-1000:]}\n{result.stderr[-500:]}"
            )

    def test_yaml_files_parseable_by_python(self):
        """Verify all YAML config files are parseable without errors"""
        import yaml
        files = [
            "config/testdata/multi_tier_scrape.yml",
            "config/testdata/recording_rules.yml",
            "config/testdata/alert_rules.yml",
        ]
        for f in files:
            path = os.path.join(self.REPO_DIR, f)
            if os.path.exists(path):
                with open(path) as fh:
                    data = yaml.safe_load(fh)
                assert data is not None, f"{f} parsed as empty/None"
