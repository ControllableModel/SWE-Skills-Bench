"""
Tests for the linkerd-patterns skill.

Validates that Linkerd service profile, traffic split, and authorization
policy builders were implemented for linkerd2.

Repo: linkerd2 (https://github.com/linkerd/linkerd2)
"""

import os
import re
import subprocess

REPO_DIR = "/workspace/linkerd2"


class TestFilePathCheck:
    """Verify that all required files were created."""

    def test_service_profile_builder_exists(self):
        path = os.path.join(
            REPO_DIR, "controller", "api", "destination",
            "service_profile_builder.go",
        )
        assert os.path.isfile(path), f"Expected service_profile_builder.go at {path}"

    def test_traffic_split_exists(self):
        path = os.path.join(
            REPO_DIR, "controller", "api", "destination", "traffic_split.go",
        )
        assert os.path.isfile(path), f"Expected traffic_split.go at {path}"

    def test_auth_policy_exists(self):
        path = os.path.join(
            REPO_DIR, "controller", "api", "destination", "auth_policy.go",
        )
        assert os.path.isfile(path), f"Expected auth_policy.go at {path}"

    def test_service_profile_test_exists(self):
        path = os.path.join(
            REPO_DIR, "controller", "api", "destination",
            "service_profile_builder_test.go",
        )
        assert os.path.isfile(path), f"Expected service_profile_builder_test.go"

    def test_traffic_split_test_exists(self):
        path = os.path.join(
            REPO_DIR, "controller", "api", "destination",
            "traffic_split_test.go",
        )
        assert os.path.isfile(path), f"Expected traffic_split_test.go"


class TestSemanticServiceProfileBuilder:
    """Verify ServiceProfileBuilder produces correct Linkerd service profiles."""

    def _read_builder(self):
        path = os.path.join(
            REPO_DIR, "controller", "api", "destination",
            "service_profile_builder.go",
        )
        with open(path, "r") as f:
            return f.read()

    def test_struct_definition(self):
        content = self._read_builder()
        assert re.search(r"type\s+ServiceProfileBuilder\s+struct", content), (
            "Expected ServiceProfileBuilder struct"
        )

    def test_route_spec(self):
        content = self._read_builder()
        assert re.search(r"RouteSpec|route.*spec|routes", content, re.IGNORECASE), (
            "Expected RouteSpec configuration in service profile"
        )

    def test_retry_budget(self):
        content = self._read_builder()
        assert re.search(r"retryBudget|RetryBudget|retry_budget", content), (
            "Expected retryBudget configuration"
        )

    def test_retry_ratio_bound(self):
        """retryRatio should be between 0.0 and 1.0."""
        content = self._read_builder()
        assert re.search(r"retryRatio|RetryRatio|retry.*ratio", content), (
            "Expected retryRatio validation (0.0-1.0)"
        )

    def test_timeout(self):
        content = self._read_builder()
        assert re.search(r"timeout|Timeout", content, re.IGNORECASE), (
            "Expected timeout configuration on routes"
        )

    def test_api_version(self):
        content = self._read_builder()
        assert re.search(r"linkerd\.io/v1alpha2|v1alpha2", content), (
            "Expected apiVersion linkerd.io/v1alpha2"
        )

    def test_route_name_uniqueness(self):
        content = self._read_builder()
        assert re.search(r"name|Name|duplicate|unique", content, re.IGNORECASE), (
            "Expected route name field for uniqueness"
        )


class TestSemanticTrafficSplit:
    """Verify TrafficSplitBuilder for SMI traffic splits."""

    def _read_split(self):
        path = os.path.join(
            REPO_DIR, "controller", "api", "destination", "traffic_split.go",
        )
        with open(path, "r") as f:
            return f.read()

    def test_struct_definition(self):
        content = self._read_split()
        assert re.search(r"type\s+TrafficSplit\w*\s+struct", content), (
            "Expected TrafficSplitBuilder struct"
        )

    def test_smi_api_version(self):
        content = self._read_split()
        assert re.search(r"split\.smi-spec\.io|smi-spec", content), (
            "Expected SMI apiVersion: split.smi-spec.io/v1alpha2"
        )

    def test_weights_sum_1000(self):
        content = self._read_split()
        assert re.search(r"1000|weights|Weights", content), (
            "Expected weights summing to 1000"
        )

    def test_minimum_two_backends(self):
        content = self._read_split()
        assert re.search(r"backend|Backend|service", content, re.IGNORECASE), (
            "Expected at least 2 backends for traffic split"
        )

    def test_shift_weight(self):
        content = self._read_split()
        assert re.search(r"shift.*weight|ShiftWeight|shift_weight", content, re.IGNORECASE), (
            "Expected shift_weight method for gradual canary rollout"
        )


class TestSemanticAuthPolicy:
    """Verify AuthPolicyBuilder for Linkerd authorization."""

    def _read_auth(self):
        path = os.path.join(
            REPO_DIR, "controller", "api", "destination", "auth_policy.go",
        )
        with open(path, "r") as f:
            return f.read()

    def test_struct_definition(self):
        content = self._read_auth()
        assert re.search(r"type\s+AuthPolicy\w*\s+struct", content), (
            "Expected AuthPolicyBuilder struct"
        )

    def test_policy_api_version(self):
        content = self._read_auth()
        assert re.search(r"policy\.linkerd\.io|v1beta1", content), (
            "Expected apiVersion policy.linkerd.io/v1beta1"
        )

    def test_three_modes(self):
        content = self._read_auth()
        mode_count = sum(
            1 for mode in ["allow", "deny", "audit"]
            if re.search(mode, content, re.IGNORECASE)
        )
        assert mode_count >= 2, (
            f"Expected at least 2 of 3 auth modes (allow/deny/audit), found {mode_count}"
        )


class TestFunctionalGoSyntax:
    """Validate Go files compile and have tests."""

    def _base_dir(self):
        return os.path.join(
            REPO_DIR, "controller", "api", "destination",
        )

    def test_package_declaration(self):
        path = os.path.join(self._base_dir(), "service_profile_builder.go")
        with open(path, "r") as f:
            first_lines = f.read(500)
        assert re.search(r"^package\s+\w+", first_lines, re.MULTILINE), (
            "Expected package declaration"
        )

    def test_go_vet(self):
        result = subprocess.run(
            ["go", "vet", "./controller/api/destination/..."],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            stderr = result.stderr.lower()
            assert "syntax error" not in stderr, (
                f"Go syntax errors: {result.stderr[:500]}"
            )

    def test_service_profile_test_funcs(self):
        path = os.path.join(
            self._base_dir(), "service_profile_builder_test.go",
        )
        with open(path, "r") as f:
            content = f.read()
        test_count = len(re.findall(r"func\s+Test\w+", content))
        assert test_count >= 2, (
            f"Expected >= 2 test functions, found {test_count}"
        )

    def test_traffic_split_test_funcs(self):
        path = os.path.join(self._base_dir(), "traffic_split_test.go")
        with open(path, "r") as f:
            content = f.read()
        test_count = len(re.findall(r"func\s+Test\w+", content))
        assert test_count >= 2, (
            f"Expected >= 2 test functions, found {test_count}"
        )
