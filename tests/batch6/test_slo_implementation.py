"""
Test skill: slo-implementation
Verify that the Agent implements SLO monitoring for a payment processing
API with SLI recording rules, multi-window burn-rate alerting, Grafana
SLO dashboard, and error budget policy.
"""

import os
import re
import json
import pytest

try:
    import yaml
except ImportError:
    yaml = None


class TestSloImplementation:
    REPO_DIR = "/workspace/slo-generator"

    # === File Path Checks ===

    def test_slo_definitions_exists(self):
        assert os.path.exists(os.path.join(self.REPO_DIR, "slo/slo-definitions.yaml"))

    def test_recording_rules_exists(self):
        assert os.path.exists(
            os.path.join(self.REPO_DIR, "slo/prometheus/recording-rules.yaml")
        )

    def test_alerting_rules_exists(self):
        assert os.path.exists(
            os.path.join(self.REPO_DIR, "slo/prometheus/alerting-rules.yaml")
        )

    def test_dashboard_exists(self):
        assert os.path.exists(
            os.path.join(self.REPO_DIR, "slo/grafana/slo-dashboard.json")
        )

    def test_error_budget_policy_exists(self):
        assert os.path.exists(
            os.path.join(self.REPO_DIR, "slo/error-budget-policy.md")
        )

    # === Semantic Checks ===

    def test_slo_definitions_cover_endpoints(self):
        """SLO definitions should cover all 3 endpoints"""
        if yaml is None:
            pytest.skip("PyYAML not available")
        path = os.path.join(self.REPO_DIR, "slo/slo-definitions.yaml")
        with open(path) as f:
            data = yaml.safe_load(f)
        slos = data.get("slos", [])
        names = [s.get("name", "") for s in slos]
        names_str = " ".join(names)
        assert "payments_create" in names_str, "Missing payments create SLO"
        assert "payments_get" in names_str, "Missing payments get SLO"
        assert "refund" in names_str, "Missing refund SLO"

    def test_slo_definitions_have_availability_and_latency(self):
        """SLOs should include both availability and latency types"""
        if yaml is None:
            pytest.skip("PyYAML not available")
        path = os.path.join(self.REPO_DIR, "slo/slo-definitions.yaml")
        with open(path) as f:
            data = yaml.safe_load(f)
        types = {s.get("sli", {}).get("type") for s in data.get("slos", [])}
        assert "availability" in types, "Missing availability SLI type"
        assert "latency" in types, "Missing latency SLI type"

    def test_recording_rules_have_multi_window(self):
        """Recording rules should compute SLIs across multiple time windows"""
        path = os.path.join(self.REPO_DIR, "slo/prometheus/recording-rules.yaml")
        with open(path) as f:
            content = f.read()
        for window in ("5m", "1h", "1d"):
            assert window in content, f"Missing {window} window in recording rules"

    def test_recording_rules_have_error_budget(self):
        """Recording rules should compute error budget remaining"""
        path = os.path.join(self.REPO_DIR, "slo/prometheus/recording-rules.yaml")
        with open(path) as f:
            content = f.read()
        assert "error_budget" in content, "Missing error budget recording rule"

    def test_alerting_has_burn_rate_alerts(self):
        """Alerting rules should use multi-window burn rate"""
        path = os.path.join(self.REPO_DIR, "slo/prometheus/alerting-rules.yaml")
        with open(path) as f:
            content = f.read()
        assert "BurnRate" in content or "burn_rate" in content or "burn" in content.lower(), (
            "Missing burn rate alerts"
        )

    def test_alerting_has_critical_and_warning(self):
        """Alerting rules should have both critical and warning severities"""
        path = os.path.join(self.REPO_DIR, "slo/prometheus/alerting-rules.yaml")
        with open(path) as f:
            content = f.read()
        assert "critical" in content, "Missing critical severity"
        assert "warning" in content, "Missing warning severity"

    def test_alerting_has_burn_rate_factors(self):
        """Alerting rules should use 14.4x, 6x, 3x, 1x burn rate factors"""
        path = os.path.join(self.REPO_DIR, "slo/prometheus/alerting-rules.yaml")
        with open(path) as f:
            content = f.read()
        assert "14.4" in content, "Missing 14.4x burn rate factor"
        assert "6" in content, "Should have 6x factor"

    def test_dashboard_has_error_budget_panel(self):
        """Dashboard should have error budget burn-down panel"""
        path = os.path.join(self.REPO_DIR, "slo/grafana/slo-dashboard.json")
        with open(path) as f:
            data = json.load(f)
        content_str = json.dumps(data).lower()
        assert "error" in content_str and "budget" in content_str, (
            "Dashboard should have error budget panel"
        )

    def test_dashboard_has_burn_rate_panel(self):
        """Dashboard should have burn rate panel"""
        path = os.path.join(self.REPO_DIR, "slo/grafana/slo-dashboard.json")
        with open(path) as f:
            data = json.load(f)
        content_str = json.dumps(data).lower()
        assert "burn" in content_str or "rate" in content_str, (
            "Dashboard should have burn rate panel"
        )

    def test_error_budget_policy_has_thresholds(self):
        """Error budget policy should define actions at budget thresholds"""
        path = os.path.join(self.REPO_DIR, "slo/error-budget-policy.md")
        with open(path) as f:
            content = f.read()
        assert "%" in content or "percent" in content.lower(), (
            "Policy should reference budget percentages"
        )
        content_lower = content.lower()
        assert "budget" in content_lower, "Should reference error budget"

    # === Functional Checks ===

    def test_all_yaml_files_valid(self):
        """All YAML files should parse without errors"""
        if yaml is None:
            pytest.skip("PyYAML not available")
        base = os.path.join(self.REPO_DIR, "slo")
        for root, _dirs, files in os.walk(base):
            for fname in files:
                if fname.endswith((".yaml", ".yml")):
                    filepath = os.path.join(root, fname)
                    try:
                        with open(filepath) as f:
                            list(yaml.safe_load_all(f))
                    except yaml.YAMLError as e:
                        pytest.fail(f"{filepath} YAML error: {e}")

    def test_dashboard_json_valid(self):
        """Dashboard JSON should be valid"""
        path = os.path.join(self.REPO_DIR, "slo/grafana/slo-dashboard.json")
        with open(path) as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError as e:
                pytest.fail(f"Dashboard JSON error: {e}")
        assert "panels" in data or "rows" in data, "Dashboard should have panels"

    def test_slo_targets_are_valid(self):
        """SLO targets should be between 90 and 100"""
        if yaml is None:
            pytest.skip("PyYAML not available")
        path = os.path.join(self.REPO_DIR, "slo/slo-definitions.yaml")
        with open(path) as f:
            data = yaml.safe_load(f)
        for slo in data.get("slos", []):
            target = slo.get("target", 0)
            assert 90 <= target <= 100, (
                f"SLO target {target} for {slo.get('name')} is out of range"
            )
