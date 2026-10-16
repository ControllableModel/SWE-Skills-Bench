"""
Tests for the istio-traffic-management skill.
Validates an Istio traffic management configuration generator with
VirtualService, DestinationRule, Gateway, canary management, and validation.
"""

import os
import re
import ast

REPO_DIR = "/workspace/istio"
PYTHON_DIR = os.path.join(REPO_DIR, "tests", "python")


class TestIstioTrafficManagement:
    """Tests for the Istio traffic management generator."""

    # ── file_path_check ──────────────────────────────────────────────

    def test_istio_generator_exists(self):
        """IstioTrafficGenerator module must exist."""
        path = os.path.join(PYTHON_DIR, "istio_generator.py")
        assert os.path.isfile(path), f"Missing {path}"

    def test_canary_manager_exists(self):
        """CanaryManager module must exist."""
        path = os.path.join(PYTHON_DIR, "canary_manager.py")
        assert os.path.isfile(path), f"Missing {path}"

    def test_resilience_config_exists(self):
        """ResilienceConfig module must exist."""
        path = os.path.join(PYTHON_DIR, "resilience_config.py")
        assert os.path.isfile(path), f"Missing {path}"

    def test_istio_validator_exists(self):
        """IstioValidator module must exist."""
        path = os.path.join(PYTHON_DIR, "istio_validator.py")
        assert os.path.isfile(path), f"Missing {path}"

    # ── semantic_check ───────────────────────────────────────────────

    def _read(self, filename):
        path = os.path.join(PYTHON_DIR, filename)
        if not os.path.isfile(path):
            return ""
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def test_generator_resources(self):
        """IstioTrafficGenerator must generate VirtualService, DestinationRule, Gateway."""
        content = self._read("istio_generator.py")
        assert re.search(r"class\s+IstioTrafficGenerator", content), (
            "IstioTrafficGenerator class not defined"
        )
        for method in ["generate_destination_rule", "generate_virtual_service",
                        "generate_gateway", "generate_service_entry"]:
            assert re.search(rf"def\s+{method}\b", content), f"{method} not defined"

    def test_istio_api_version(self):
        """Generator must use networking.istio.io/v1beta1 API version."""
        content = self._read("istio_generator.py")
        assert "networking.istio.io" in content, "Istio API version not found"

    def test_weight_sum_validation(self):
        """VirtualService weights must sum to 100."""
        content = self._read("istio_generator.py")
        assert re.search(r"sum.*100|100.*sum|ValueError.*weight", content, re.IGNORECASE), (
            "Weight sum validation (100) not found"
        )

    def test_canary_manager_class(self):
        """CanaryManager must define generate_steps, generate_rollback, generate_with_analysis."""
        content = self._read("canary_manager.py")
        assert re.search(r"class\s+CanaryManager", content), "CanaryManager class not defined"
        for method in ["generate_steps", "generate_rollback", "generate_with_analysis"]:
            assert re.search(rf"def\s+{method}\b", content), f"{method} not defined"

    def test_resilience_methods(self):
        """ResilienceConfig must define circuit_breaker, retry_policy, timeout, fault_injection."""
        content = self._read("resilience_config.py")
        for method in ["circuit_breaker", "retry_policy", "timeout", "fault_injection"]:
            assert re.search(rf"def\s+{method}\b", content), f"{method} not defined"

    def test_fault_injection_validation(self):
        """fault_injection must raise ValueError if neither delay nor abort specified."""
        content = self._read("resilience_config.py")
        assert re.search(r"ValueError|At least one|delay.*abort", content, re.IGNORECASE), (
            "Fault injection validation not found"
        )

    def test_validator_methods(self):
        """IstioValidator must validate VirtualService, DestinationRule, Gateway."""
        content = self._read("istio_validator.py")
        assert re.search(r"class\s+IstioValidator", content), "IstioValidator class not defined"
        for method in ["validate_virtual_service", "validate_destination_rule",
                        "validate_gateway", "validate_all"]:
            assert re.search(rf"def\s+{method}\b", content), f"{method} not defined"

    def test_subset_validation(self):
        """Validator must check subset references exist in DestinationRules."""
        content = self._read("istio_validator.py")
        assert re.search(r"[Ss]ubset.*not found|not found.*subset", content), (
            "Subset existence validation not found"
        )

    # ── functional_check ─────────────────────────────────────────────

    def test_all_files_valid_python(self):
        """All Istio Python files must have valid syntax."""
        errors = []
        for fname in ["istio_generator.py", "canary_manager.py",
                       "resilience_config.py", "istio_validator.py"]:
            content = self._read(fname)
            if not content:
                continue
            try:
                ast.parse(content)
            except SyntaxError as e:
                errors.append(f"{fname}: {e}")
        assert not errors, "Syntax errors:\n" + "\n".join(errors)

    def test_lb_policy_validation(self):
        """Generator must raise ValueError for invalid lb_policy."""
        content = self._read("istio_generator.py")
        assert "ROUND_ROBIN" in content, "ROUND_ROBIN policy not found"
        assert "LEAST_CONN" in content, "LEAST_CONN policy not found"
        assert re.search(r"ValueError|invalid.*policy", content, re.IGNORECASE), (
            "lb_policy validation not found"
        )

    def test_tls_mode_support(self):
        """Gateway must support SIMPLE, MUTUAL, PASSTHROUGH TLS modes."""
        content = self._read("istio_generator.py")
        for mode in ["SIMPLE", "MUTUAL", "PASSTHROUGH"]:
            assert mode in content, f"TLS mode '{mode}' not found"

    def test_rate_limit(self):
        """ResilienceConfig must define rate_limit method."""
        content = self._read("resilience_config.py")
        assert re.search(r"def\s+rate_limit\b", content), "rate_limit method not defined"

    def test_test_file_exists(self):
        """Test file must exist."""
        path = os.path.join(REPO_DIR, "tests", "test_istio_traffic_management.py")
        assert os.path.isfile(path), f"Missing {path}"
