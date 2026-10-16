"""
Test skill: prometheus-configuration
Verify that the Agent creates prometheus.yml, recording_rules.yml, alerting_rules.yml,
slo_rules.yml, and docker-compose.yml for monitoring 4 microservices.
"""

import os
import subprocess
import re
import pytest

try:
    import yaml
except ImportError:
    yaml = None


class TestPrometheusConfiguration:
    REPO_DIR = "/workspace/prometheus"

    # === File Path Checks ===

    def test_prometheus_yml_exists(self):
        """Verify prometheus.yml exists"""
        path = os.path.join(self.REPO_DIR, "prometheus.yml")
        assert os.path.exists(path), f"prometheus.yml not found at {path}"

    def test_recording_rules_exists(self):
        """Verify recording_rules.yml exists"""
        path = os.path.join(self.REPO_DIR, "recording_rules.yml")
        assert os.path.exists(path), f"recording_rules.yml not found at {path}"

    def test_alerting_rules_exists(self):
        """Verify alerting_rules.yml exists"""
        path = os.path.join(self.REPO_DIR, "alerting_rules.yml")
        assert os.path.exists(path), f"alerting_rules.yml not found at {path}"

    def test_slo_rules_exists(self):
        """Verify slo_rules.yml exists"""
        path = os.path.join(self.REPO_DIR, "slo_rules.yml")
        assert os.path.exists(path), f"slo_rules.yml not found at {path}"

    def test_docker_compose_exists(self):
        """Verify docker-compose.yml exists"""
        candidates = [
            os.path.join(self.REPO_DIR, "docker-compose.yml"),
            os.path.join(self.REPO_DIR, "docker-compose.yaml"),
        ]
        found = any(os.path.exists(c) for c in candidates)
        assert found, "docker-compose.yml not found"

    # === Semantic Checks ===

    def test_prometheus_yml_has_scrape_configs(self):
        """Verify prometheus.yml defines scrape_configs"""
        if yaml is None:
            path = os.path.join(self.REPO_DIR, "prometheus.yml")
            with open(path) as f:
                content = f.read()
            assert "scrape_configs" in content
            return
        path = os.path.join(self.REPO_DIR, "prometheus.yml")
        with open(path) as f:
            config = yaml.safe_load(f)
        assert "scrape_configs" in config, "prometheus.yml missing scrape_configs section"
        assert len(config["scrape_configs"]) >= 4, (
            f"Expected at least 4 scrape configs (one per microservice), found {len(config['scrape_configs'])}"
        )

    def test_prometheus_yml_has_rule_files(self):
        """Verify prometheus.yml references rule files"""
        path = os.path.join(self.REPO_DIR, "prometheus.yml")
        with open(path) as f:
            content = f.read()
        assert "rule_files" in content, "prometheus.yml missing rule_files section"
        assert "recording_rules" in content, "prometheus.yml doesn't reference recording_rules"
        assert "alerting_rules" in content, "prometheus.yml doesn't reference alerting_rules"

    def test_alerting_rules_have_severity(self):
        """Verify alerting rules include severity labels"""
        path = os.path.join(self.REPO_DIR, "alerting_rules.yml")
        with open(path) as f:
            content = f.read()
        assert "severity" in content, "Alerting rules missing severity labels"

    def test_alerting_rules_cover_key_metrics(self):
        """Verify alerting rules cover latency, error rate, saturation"""
        path = os.path.join(self.REPO_DIR, "alerting_rules.yml")
        with open(path) as f:
            content = f.read()
        content_lower = content.lower()
        metrics = {
            "latency": "latency" in content_lower or "duration" in content_lower,
            "error": "error" in content_lower,
            "saturation": "saturation" in content_lower or "memory" in content_lower or "cpu" in content_lower,
        }
        found = [k for k, v in metrics.items() if v]
        assert len(found) >= 2, (
            f"Alerting rules should cover latency, error, saturation. Found: {found}"
        )

    def test_docker_compose_has_prometheus_service(self):
        """Verify docker-compose.yml includes prometheus service"""
        candidates = [
            os.path.join(self.REPO_DIR, "docker-compose.yml"),
            os.path.join(self.REPO_DIR, "docker-compose.yaml"),
        ]
        content = ""
        for c in candidates:
            if os.path.exists(c):
                with open(c) as f:
                    content = f.read()
                break
        assert "prometheus" in content.lower(), "docker-compose missing prometheus service"
        assert "services:" in content, "docker-compose missing services section"

    def test_slo_rules_define_error_budget(self):
        """Verify SLO rules include error budget calculations"""
        path = os.path.join(self.REPO_DIR, "slo_rules.yml")
        with open(path) as f:
            content = f.read()
        content_lower = content.lower()
        has_slo = (
            "slo" in content_lower
            or "error_budget" in content_lower
            or "availability" in content_lower
            or "burn_rate" in content_lower
        )
        assert has_slo, "SLO rules don't define error budget or availability targets"

    # === Functional Checks ===

    def test_prometheus_yml_valid_yaml(self):
        """Verify prometheus.yml is valid YAML"""
        if yaml is None:
            pytest.skip("PyYAML not installed")
        path = os.path.join(self.REPO_DIR, "prometheus.yml")
        with open(path) as f:
            try:
                config = yaml.safe_load(f)
            except yaml.YAMLError as e:
                pytest.fail(f"Invalid YAML in prometheus.yml: {e}")
        assert isinstance(config, dict), "prometheus.yml should be a YAML mapping"

    def test_all_rule_files_valid_yaml(self):
        """Verify all rule files are valid YAML"""
        if yaml is None:
            pytest.skip("PyYAML not installed")
        rule_files = ["recording_rules.yml", "alerting_rules.yml", "slo_rules.yml"]
        for rf in rule_files:
            path = os.path.join(self.REPO_DIR, rf)
            with open(path) as f:
                try:
                    yaml.safe_load(f)
                except yaml.YAMLError as e:
                    pytest.fail(f"Invalid YAML in {rf}: {e}")

    def test_docker_compose_valid(self):
        """Verify docker-compose.yml is valid"""
        candidates = [
            os.path.join(self.REPO_DIR, "docker-compose.yml"),
            os.path.join(self.REPO_DIR, "docker-compose.yaml"),
        ]
        compose_file = None
        for c in candidates:
            if os.path.exists(c):
                compose_file = c
                break
        assert compose_file is not None
        result = subprocess.run(
            ["docker", "compose", "-f", compose_file, "config", "--quiet"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            # Try docker-compose (v1)
            result = subprocess.run(
                ["docker-compose", "-f", compose_file, "config", "--quiet"],
                cwd=self.REPO_DIR,
                capture_output=True,
                text=True,
                timeout=30,
            )
        assert result.returncode == 0, (
            f"docker-compose config validation failed: {result.stderr[:500]}"
        )
