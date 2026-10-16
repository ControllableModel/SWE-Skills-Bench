"""
Test skill: slo-implementation
Verify that the Agent correctly implements SLI/SLO Recording Rules
and Error Budget computation for slo-generator.
"""

import os
import re
import ast
import pytest


class TestSloImplementation:
    REPO_DIR = "/workspace/slo-generator"

    # === File Path Checks ===

    def test_availability_slo_yaml_exists(self):
        """Verify slo_prometheus_api_availability.yaml was created"""
        path = os.path.join(
            self.REPO_DIR,
            "samples/prometheus/slo_prometheus_api_availability.yaml",
        )
        assert os.path.exists(path), "slo_prometheus_api_availability.yaml not found"

    def test_latency_slo_yaml_exists(self):
        """Verify slo_prometheus_api_latency.yaml was created"""
        path = os.path.join(
            self.REPO_DIR,
            "samples/prometheus/slo_prometheus_api_latency.yaml",
        )
        assert os.path.exists(path), "slo_prometheus_api_latency.yaml not found"

    def test_prometheus_rules_yaml_exists(self):
        """Verify prometheus_rules.yaml was created"""
        path = os.path.join(
            self.REPO_DIR,
            "samples/prometheus/prometheus_rules.yaml",
        )
        assert os.path.exists(path), "prometheus_rules.yaml not found"

    def test_prometheus_backend_exists(self):
        """Verify prometheus.py backend was modified"""
        path = os.path.join(
            self.REPO_DIR,
            "slo_generator/backends/prometheus.py",
        )
        assert os.path.exists(path), "prometheus.py backend not found"

    def test_prometheus_backend_test_exists(self):
        """Verify test_prometheus_backend.py was modified"""
        found = False
        for root, dirs, files in os.walk(self.REPO_DIR):
            if "test_prometheus_backend.py" in files:
                found = True
                break
        assert found, "test_prometheus_backend.py not found"

    # === Semantic Checks: Error Budget Function ===

    def _load_prometheus_backend(self):
        path = os.path.join(
            self.REPO_DIR,
            "slo_generator/backends/prometheus.py",
        )
        return open(path).read()

    def test_compute_error_budget_function(self):
        """Verify compute_error_budget_remaining is defined"""
        source = self._load_prometheus_backend()
        assert "compute_error_budget_remaining" in source, (
            "compute_error_budget_remaining function not found"
        )

    def test_error_budget_takes_slo_config_and_sli(self):
        """Verify compute_error_budget_remaining takes slo_config and current_sli_value"""
        source = self._load_prometheus_backend()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "compute_error_budget_remaining":
                args = [a.arg for a in node.args.args if a.arg != "self"]
                assert "slo_config" in args or "config" in " ".join(args).lower(), (
                    "Missing slo_config parameter"
                )
                assert any("sli" in a.lower() for a in args), (
                    "Missing current_sli_value parameter"
                )
                return
        pytest.fail("compute_error_budget_remaining function not found in AST")

    def test_error_budget_clamps_output(self):
        """Verify error budget result is clamped to [0.0, 1.0]"""
        source = self._load_prometheus_backend()
        has_clamp = (
            "max(0" in source
            or "min(1" in source
            or "clamp" in source.lower()
            or ("max(" in source and "min(" in source)
            or re.search(r'if.*<\s*0', source)
            or re.search(r'if.*>\s*1', source)
        )
        assert has_clamp, "No clamping logic for error budget result"

    def test_error_budget_raises_value_error(self):
        """Verify ValueError is raised for invalid goal"""
        source = self._load_prometheus_backend()
        assert "ValueError" in source, (
            "No ValueError raised for invalid goal"
        )

    # === Semantic Checks: Recording Rules ===

    def _load_prometheus_rules(self):
        path = os.path.join(
            self.REPO_DIR,
            "samples/prometheus/prometheus_rules.yaml",
        )
        return open(path).read()

    def test_rules_have_multi_window_burn_rate(self):
        """Verify multi-window burn rate alert rules exist"""
        source = self._load_prometheus_rules()
        has_burn_rate = (
            "burn_rate" in source.lower()
            or "burn" in source.lower()
            or "14.4" in source
            or "multiwindow" in source.lower()
        )
        assert has_burn_rate, "No multi-window burn rate alert rules found"

    def test_rules_fast_burn_rate_14_4(self):
        """Verify fast burn rate factor of 14.4"""
        source = self._load_prometheus_rules()
        assert "14.4" in source, "Fast burn rate factor 14.4 not found"

    def test_rules_slow_burn_rate_6(self):
        """Verify slow burn rate factor of 6"""
        source = self._load_prometheus_rules()
        # Look for the number 6 in burn rate context
        has_slow = (
            re.search(r'(?:burn|factor|rate).*\b6\b', source, re.IGNORECASE)
            or re.search(r'\b6\b.*(?:burn|factor|rate)', source, re.IGNORECASE)
            or re.search(r'\*\s*6\b', source)
            or re.search(r'\b6\s*\*', source)
        )
        assert has_slow, "Slow burn rate factor 6 not found in rules"

    # === Functional Checks ===

    def test_availability_slo_has_goal(self):
        """Verify availability SLO config contains a goal/target"""
        path = os.path.join(
            self.REPO_DIR,
            "samples/prometheus/slo_prometheus_api_availability.yaml",
        )
        content = open(path).read()
        has_goal = (
            "goal" in content.lower()
            or "target" in content.lower()
            or "objective" in content.lower()
        )
        assert has_goal, "Availability SLO missing goal/target"

    def test_latency_slo_has_threshold(self):
        """Verify latency SLO config has latency threshold"""
        path = os.path.join(
            self.REPO_DIR,
            "samples/prometheus/slo_prometheus_api_latency.yaml",
        )
        content = open(path).read()
        has_threshold = (
            "threshold" in content.lower()
            or "latency" in content.lower()
            or "duration" in content.lower()
        )
        assert has_threshold, "Latency SLO missing threshold"

    def test_rules_yaml_valid_structure(self):
        """Verify prometheus_rules.yaml has valid YAML structure"""
        import yaml
        path = os.path.join(
            self.REPO_DIR,
            "samples/prometheus/prometheus_rules.yaml",
        )
        with open(path) as f:
            try:
                data = yaml.safe_load(f)
            except yaml.YAMLError as e:
                pytest.fail(f"Invalid YAML in prometheus_rules.yaml: {e}")
        assert data is not None, "Empty YAML file"

    def test_rules_have_recording_rules(self):
        """Verify prometheus_rules.yaml contains recording rules"""
        source = self._load_prometheus_rules()
        has_recording = (
            "record:" in source
            or "recording" in source.lower()
            or "rules:" in source
        )
        assert has_recording, "No recording rules found in prometheus_rules.yaml"

    def test_rules_have_alert_rules(self):
        """Verify prometheus_rules.yaml contains alert rules"""
        source = self._load_prometheus_rules()
        has_alert = (
            "alert:" in source
            or "alerting" in source.lower()
        )
        assert has_alert, "No alert rules found in prometheus_rules.yaml"

    def test_prometheus_backend_parseable(self):
        """Verify prometheus.py has valid Python syntax"""
        source = self._load_prometheus_backend()
        try:
            ast.parse(source)
        except SyntaxError as e:
            pytest.fail(f"prometheus.py has syntax error: {e}")
