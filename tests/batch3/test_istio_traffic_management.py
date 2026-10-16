"""
Tests for the istio-traffic-management skill.

Validates that Istio VirtualService and DestinationRule traffic management
builders were implemented, including canary deployment configuration.

Repo: istio (https://github.com/istio/istio)
"""

import os
import re
import subprocess

REPO_DIR = "/workspace/istio"


class TestFilePathCheck:
    """Verify that all required files were created."""

    def test_virtualservice_builder_exists(self):
        path = os.path.join(
            REPO_DIR, "pilot", "pkg", "config", "traffic",
            "virtualservice_builder.go",
        )
        assert os.path.isfile(path), f"Expected virtualservice_builder.go at {path}"

    def test_destinationrule_builder_exists(self):
        path = os.path.join(
            REPO_DIR, "pilot", "pkg", "config", "traffic",
            "destinationrule_builder.go",
        )
        assert os.path.isfile(path), f"Expected destinationrule_builder.go"

    def test_canary_exists(self):
        path = os.path.join(
            REPO_DIR, "pilot", "pkg", "config", "traffic", "canary.go",
        )
        assert os.path.isfile(path), f"Expected canary.go at {path}"

    def test_virtualservice_test_exists(self):
        path = os.path.join(
            REPO_DIR, "pilot", "pkg", "config", "traffic",
            "virtualservice_builder_test.go",
        )
        assert os.path.isfile(path), f"Expected virtualservice_builder_test.go"

    def test_destinationrule_test_exists(self):
        path = os.path.join(
            REPO_DIR, "pilot", "pkg", "config", "traffic",
            "destinationrule_builder_test.go",
        )
        assert os.path.isfile(path), f"Expected destinationrule_builder_test.go"


class TestSemanticVirtualServiceBuilder:
    """Verify VirtualService builder with routing, faults, retries."""

    def _read(self):
        path = os.path.join(
            REPO_DIR, "pilot", "pkg", "config", "traffic",
            "virtualservice_builder.go",
        )
        with open(path, "r") as f:
            return f.read()

    def test_struct_definition(self):
        content = self._read()
        assert re.search(r"type\s+VirtualServiceBuilder\s+struct", content), (
            "Expected VirtualServiceBuilder struct"
        )

    def test_api_version(self):
        content = self._read()
        assert re.search(r"networking\.istio\.io/v1beta1", content), (
            "Expected apiVersion: networking.istio.io/v1beta1"
        )

    def test_hosts_field(self):
        content = self._read()
        assert re.search(r"hosts|Hosts", content), (
            "Expected hosts field (required, at least one)"
        )

    def test_route_weight(self):
        content = self._read()
        assert re.search(r"weight|Weight", content), (
            "Expected route weight configuration"
        )

    def test_weight_sum_validation(self):
        content = self._read()
        assert re.search(r"100|sum|Sum|weight.*100", content), (
            "Expected weights sum to 100 validation"
        )

    def test_fault_injection_delay(self):
        content = self._read()
        assert re.search(r"delay|Delay|fault.*delay", content, re.IGNORECASE), (
            "Expected fault injection delay support"
        )

    def test_fault_injection_abort(self):
        content = self._read()
        assert re.search(r"abort|Abort|fault.*abort", content, re.IGNORECASE), (
            "Expected fault injection abort support"
        )

    def test_retry_policy(self):
        content = self._read()
        assert re.search(r"retry|Retry|retryOn|perTryTimeout", content), (
            "Expected retry policy configuration"
        )

    def test_request_timeout(self):
        content = self._read()
        assert re.search(r"timeout|Timeout", content), (
            "Expected request timeout configuration"
        )


class TestSemanticDestinationRuleBuilder:
    """Verify DestinationRule builder with circuit breaker, LB, connection pool."""

    def _read(self):
        path = os.path.join(
            REPO_DIR, "pilot", "pkg", "config", "traffic",
            "destinationrule_builder.go",
        )
        with open(path, "r") as f:
            return f.read()

    def test_struct_definition(self):
        content = self._read()
        assert re.search(r"type\s+DestinationRuleBuilder\s+struct", content), (
            "Expected DestinationRuleBuilder struct"
        )

    def test_api_version(self):
        content = self._read()
        assert re.search(r"networking\.istio\.io/v1beta1", content), (
            "Expected apiVersion networking.istio.io/v1beta1"
        )

    def test_subsets(self):
        content = self._read()
        assert re.search(r"subset|Subset", content), (
            "Expected subsets with label selectors"
        )

    def test_connection_pool(self):
        content = self._read()
        assert re.search(
            r"connectionPool|ConnectionPool|maxConnections|MaxConnections", content
        ), "Expected connection pool configuration"

    def test_outlier_detection(self):
        content = self._read()
        assert re.search(
            r"outlierDetection|OutlierDetection|consecutive5xxErrors", content
        ), "Expected outlier detection (circuit breaker)"

    def test_load_balancing(self):
        content = self._read()
        assert re.search(
            r"ROUND_ROBIN|LEAST_REQUEST|RANDOM|loadBalanc", content
        ), "Expected load balancing mode configuration"

    def test_max_ejection_percent(self):
        content = self._read()
        assert re.search(r"maxEjectionPercent|MaxEjection", content), (
            "Expected maxEjectionPercent validation (0-100)"
        )


class TestSemanticCanaryDeployment:
    """Verify canary deployment configuration."""

    def _read(self):
        path = os.path.join(
            REPO_DIR, "pilot", "pkg", "config", "traffic", "canary.go",
        )
        with open(path, "r") as f:
            return f.read()

    def test_canary_config_struct(self):
        content = self._read()
        assert re.search(r"type\s+Canary\w*\s+struct", content), (
            "Expected CanaryConfig struct"
        )

    def test_stable_canary_subsets(self):
        content = self._read()
        assert "stable" in content.lower() and "canary" in content.lower(), (
            "Expected stable and canary subset references"
        )

    def test_progressive_rollout(self):
        content = self._read()
        assert re.search(r"progressive|rollout|ProgressiveRollout", content, re.IGNORECASE), (
            "Expected progressive_rollout method"
        )

    def test_monotonic_validation(self):
        content = self._read()
        assert re.search(r"monoton|increasing|previous|step", content, re.IGNORECASE), (
            "Expected monotonically increasing weight validation"
        )


class TestFunctionalGoSyntax:
    """Validate Go source files."""

    def _base_dir(self):
        return os.path.join(
            REPO_DIR, "pilot", "pkg", "config", "traffic",
        )

    def test_package_declaration(self):
        path = os.path.join(self._base_dir(), "virtualservice_builder.go")
        with open(path, "r") as f:
            content = f.read(500)
        assert re.search(r"^package\s+\w+", content, re.MULTILINE), (
            "Expected package declaration"
        )

    def test_go_vet(self):
        result = subprocess.run(
            ["go", "vet", "./pilot/pkg/config/traffic/..."],
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

    def test_virtualservice_test_funcs(self):
        path = os.path.join(
            self._base_dir(), "virtualservice_builder_test.go",
        )
        with open(path, "r") as f:
            content = f.read()
        count = len(re.findall(r"func\s+Test\w+", content))
        assert count >= 3, (
            f"Expected >= 3 test functions in VS test, found {count}"
        )

    def test_destinationrule_test_funcs(self):
        path = os.path.join(
            self._base_dir(), "destinationrule_builder_test.go",
        )
        with open(path, "r") as f:
            content = f.read()
        count = len(re.findall(r"func\s+Test\w+", content))
        assert count >= 3, (
            f"Expected >= 3 test functions in DR test, found {count}"
        )
