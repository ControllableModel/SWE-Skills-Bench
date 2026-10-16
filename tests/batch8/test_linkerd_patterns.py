"""
Tests for the linkerd-patterns skill.
Validates a Linkerd service mesh configuration generator with
ServiceProfiles, TrafficSplits, authorization policies, and validation.
"""

import os
import re
import ast

REPO_DIR = "/workspace/linkerd2"
PYTHON_DIR = os.path.join(REPO_DIR, "test", "python")


class TestLinkerdPatterns:
    """Tests for the Linkerd configuration generator."""

    # ── file_path_check ──────────────────────────────────────────────

    def test_linkerd_generator_exists(self):
        """LinkerdConfigGenerator module must exist."""
        path = os.path.join(PYTHON_DIR, "linkerd_generator.py")
        assert os.path.isfile(path), f"Missing {path}"

    def test_traffic_split_exists(self):
        """TrafficSplitManager module must exist."""
        path = os.path.join(PYTHON_DIR, "traffic_split.py")
        assert os.path.isfile(path), f"Missing {path}"

    def test_auth_policy_exists(self):
        """AuthorizationPolicyBuilder module must exist."""
        path = os.path.join(PYTHON_DIR, "auth_policy.py")
        assert os.path.isfile(path), f"Missing {path}"

    def test_validator_exists(self):
        """LinkerdValidator module must exist."""
        path = os.path.join(PYTHON_DIR, "linkerd_validator.py")
        assert os.path.isfile(path), f"Missing {path}"

    # ── semantic_check ───────────────────────────────────────────────

    def _read(self, filename):
        path = os.path.join(PYTHON_DIR, filename)
        if not os.path.isfile(path):
            return ""
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def test_generator_service_profile(self):
        """Generator must produce ServiceProfile resources."""
        content = self._read("linkerd_generator.py")
        assert re.search(r"class\s+LinkerdConfigGenerator", content), (
            "LinkerdConfigGenerator class not defined"
        )
        assert re.search(r"def\s+generate_service_profile\b", content), (
            "generate_service_profile method not defined"
        )
        assert "ServiceProfile" in content, "ServiceProfile kind not referenced"

    def test_generator_server_resource(self):
        """Generator must produce Server and ServerAuthorization resources."""
        content = self._read("linkerd_generator.py")
        assert re.search(r"def\s+generate_server\b", content), (
            "generate_server method not defined"
        )
        assert re.search(r"def\s+generate_server_authorization\b", content), (
            "generate_server_authorization method not defined"
        )

    def test_traffic_split_manager(self):
        """TrafficSplitManager must define generate_traffic_split and shift_traffic."""
        content = self._read("traffic_split.py")
        assert re.search(r"class\s+TrafficSplitManager", content), (
            "TrafficSplitManager class not defined"
        )
        assert re.search(r"def\s+generate_traffic_split\b", content), (
            "generate_traffic_split not defined"
        )
        assert re.search(r"def\s+shift_traffic\b", content), "shift_traffic not defined"

    def test_canary_steps(self):
        """TrafficSplitManager must support generate_canary_steps."""
        content = self._read("traffic_split.py")
        assert re.search(r"def\s+generate_canary_steps\b", content), (
            "generate_canary_steps not defined"
        )

    def test_weight_sum_validation(self):
        """TrafficSplit weights must sum to 1000."""
        content = self._read("traffic_split.py")
        assert "1000" in content, "Weight sum of 1000 not referenced"
        assert re.search(r"ValueError|sum.*1000|weights.*sum", content, re.IGNORECASE), (
            "Weight sum validation not found"
        )

    def test_auth_policy_builder(self):
        """AuthorizationPolicyBuilder must define default_deny and zero_trust_policy."""
        content = self._read("auth_policy.py")
        assert re.search(r"class\s+AuthorizationPolicyBuilder", content), (
            "AuthorizationPolicyBuilder class not defined"
        )
        assert re.search(r"def\s+default_deny\b", content), "default_deny not defined"
        assert re.search(r"def\s+generate_zero_trust_policy\b", content), (
            "generate_zero_trust_policy not defined"
        )

    def test_validator_methods(self):
        """Validator must check ServiceProfile, TrafficSplit, and Authorization."""
        content = self._read("linkerd_validator.py")
        assert re.search(r"class\s+LinkerdValidator", content), (
            "LinkerdValidator class not defined"
        )
        for method in ["validate_service_profile", "validate_traffic_split", "validate_authorization"]:
            assert re.search(rf"def\s+{method}\b", content), (
                f"{method} method not defined"
            )

    # ── functional_check ─────────────────────────────────────────────

    def test_all_files_valid_python(self):
        """All Linkerd Python files must have valid syntax."""
        errors = []
        for fname in ["linkerd_generator.py", "traffic_split.py",
                       "auth_policy.py", "linkerd_validator.py"]:
            content = self._read(fname)
            if not content:
                continue
            try:
                ast.parse(content)
            except SyntaxError as e:
                errors.append(f"{fname}: {e}")
        assert not errors, "Syntax errors:\n" + "\n".join(errors)

    def test_smi_api_version(self):
        """TrafficSplit must use SMI spec API version."""
        content = self._read("traffic_split.py")
        assert re.search(r"split\.smi-spec\.io|smi.*spec", content), (
            "SMI spec API version not found"
        )

    def test_linkerd_api_versions(self):
        """Generator must use correct Linkerd API versions."""
        content = self._read("linkerd_generator.py")
        assert re.search(r"linkerd\.io|policy\.linkerd\.io", content), (
            "Linkerd API versions not found"
        )

    def test_rollback_method(self):
        """TrafficSplitManager must support rollback."""
        content = self._read("traffic_split.py")
        assert re.search(r"def\s+rollback\b", content), "rollback method not defined"

    def test_regex_validation(self):
        """Validator must check route regex validity."""
        content = self._read("linkerd_validator.py")
        assert re.search(r"regex|re\.compile|pattern", content, re.IGNORECASE), (
            "Regex validation not found in validator"
        )
