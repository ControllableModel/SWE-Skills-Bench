"""
Test skill: slo-implementation
Verify that the Agent configures SLOs with error budget tracking for
slo-generator including YAML configs, report generator, and burn-rate alerting.
"""

import os
import re
import ast
import json
import pytest

try:
    import yaml
except ImportError:
    yaml = None


class TestSloImplementation:
    REPO_DIR = "/workspace/slo-generator"

    SLO_CONFIG = "samples/payments-api/slo_config.yaml"
    BUDGET_POLICY = "samples/payments-api/error_budget_policy.yaml"
    EXPORTERS = "samples/payments-api/exporters.yaml"
    REPORT_GEN = "samples/payments-api/slo_report_generator.py"
    TESTS = "tests/test_slo_payments_api.py"

    def _read_file(self, rel_path):
        filepath = os.path.join(self.REPO_DIR, rel_path)
        with open(filepath) as f:
            return f.read()

    # === File Path Checks ===

    def test_slo_config_exists(self):
        filepath = os.path.join(self.REPO_DIR, self.SLO_CONFIG)
        assert os.path.exists(filepath), f"slo_config.yaml not found"

    def test_error_budget_policy_exists(self):
        filepath = os.path.join(self.REPO_DIR, self.BUDGET_POLICY)
        assert os.path.exists(filepath), f"error_budget_policy.yaml not found"

    def test_exporters_exists(self):
        filepath = os.path.join(self.REPO_DIR, self.EXPORTERS)
        assert os.path.exists(filepath), f"exporters.yaml not found"

    def test_report_generator_exists(self):
        filepath = os.path.join(self.REPO_DIR, self.REPORT_GEN)
        assert os.path.exists(filepath), f"slo_report_generator.py not found"

    def test_tests_file_exists(self):
        filepath = os.path.join(self.REPO_DIR, self.TESTS)
        assert os.path.exists(filepath), f"test_slo_payments_api.py not found"

    # === Semantic Checks ===

    @pytest.mark.skipif(yaml is None, reason="PyYAML not installed")
    def test_slo_config_availability_target(self):
        """Verify availability SLO with 99.9% target"""
        content = self._read_file(self.SLO_CONFIG)
        doc = yaml.safe_load(content)
        content_str = str(doc)
        assert "99.9" in content or "0.999" in content, \
            "SLO config missing 99.9% availability target"

    @pytest.mark.skipif(yaml is None, reason="PyYAML not installed")
    def test_slo_config_latency_target(self):
        """Verify latency SLO with 95% target and 500ms threshold"""
        content = self._read_file(self.SLO_CONFIG)
        assert "95" in content or "0.95" in content, \
            "SLO config missing 95% latency target"
        assert "500" in content, "SLO config missing 500ms latency threshold"

    def test_slo_config_service_name(self):
        """Verify service_name is payments-api"""
        content = self._read_file(self.SLO_CONFIG)
        assert "payments-api" in content, "SLO config missing payments-api"

    def test_slo_config_prometheus_backend(self):
        """Verify prometheus backend type"""
        content = self._read_file(self.SLO_CONFIG)
        assert "prometheus" in content.lower(), "SLO config missing prometheus backend"

    def test_slo_config_30d_window(self):
        """Verify 30-day rolling window"""
        content = self._read_file(self.SLO_CONFIG)
        has_30d = "30" in content or "2592000" in content  # 30d in seconds
        assert has_30d, "SLO config missing 30-day window"

    @pytest.mark.skipif(yaml is None, reason="PyYAML not installed")
    def test_error_budget_burn_rate_windows(self):
        """Verify 4 burn-rate windows per SLO"""
        content = self._read_file(self.BUDGET_POLICY)
        assert "14.4" in content, "Budget policy missing 14.4x fast burn rate"
        assert "6" in content, "Budget policy missing 6x burn rate"
        assert "3" in content, "Budget policy missing 3x slow burn rate"

    def test_error_budget_alert_severities(self):
        """Verify critical, warning, info alert severities"""
        content = self._read_file(self.BUDGET_POLICY)
        assert "critical" in content.lower(), "Budget policy missing critical severity"
        assert "warning" in content.lower(), "Budget policy missing warning severity"
        assert "info" in content.lower(), "Budget policy missing info severity"

    def test_report_generator_computes_sli(self):
        """Verify report generator computes SLI value"""
        content = self._read_file(self.REPORT_GEN)
        assert "sli" in content.lower(), "Report generator missing SLI computation"

    def test_report_generator_computes_budget(self):
        """Verify report generator computes error budget remaining"""
        content = self._read_file(self.REPORT_GEN)
        has_budget = bool(re.search(r'(budget|remaining|burn_rate)', content, re.I))
        assert has_budget, "Report generator missing error budget computation"

    def test_report_generator_outputs_markdown(self):
        """Verify report generator outputs Markdown table"""
        content = self._read_file(self.REPORT_GEN)
        has_md = bool(re.search(r'(\|.*\|.*\||markdown|\.md)', content, re.I))
        assert has_md, "Report generator missing Markdown output"

    def test_report_generator_health_status(self):
        """Verify report includes healthy/warning/breached status"""
        content = self._read_file(self.REPORT_GEN)
        assert "healthy" in content.lower(), "Report missing healthy status"
        assert "breached" in content.lower(), "Report missing breached status"

    # === Functional Checks ===

    @pytest.mark.skipif(yaml is None, reason="PyYAML not installed")
    def test_all_yaml_files_valid(self):
        """Verify all YAML files parse without errors"""
        for path in [self.SLO_CONFIG, self.BUDGET_POLICY, self.EXPORTERS]:
            content = self._read_file(path)
            try:
                yaml.safe_load(content)
            except yaml.YAMLError as e:
                pytest.fail(f"{path} YAML error: {e}")

    def test_report_generator_valid_python(self):
        """Verify report generator has valid Python syntax"""
        content = self._read_file(self.REPORT_GEN)
        try:
            ast.parse(content)
        except SyntaxError as e:
            pytest.fail(f"Report generator syntax error: {e}")

    def test_tests_valid_python(self):
        """Verify test file has valid syntax and tests"""
        content = self._read_file(self.TESTS)
        tree = ast.parse(content)
        test_funcs = [
            n.name for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")
        ]
        assert len(test_funcs) >= 3, \
            f"Expected >=3 tests, found {len(test_funcs)}"
