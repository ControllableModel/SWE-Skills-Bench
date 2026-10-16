"""
Test skill: linkerd-patterns
Verify that the Agent correctly implements Linkerd service profiles,
traffic splits, and authorization policies for a microservices app.
"""

import os
import re
import pytest

try:
    import yaml
except ImportError:
    yaml = None


class TestLinkerdPatterns:
    REPO_DIR = "/workspace/linkerd2"

    API_PROFILE = "policy/profiles/api-gateway-profile.yaml"
    ORDER_PROFILE = "policy/profiles/order-service-profile.yaml"
    PAYMENT_PROFILE = "policy/profiles/payment-service-profile.yaml"
    TRAFFIC_SPLIT = "policy/traffic-split/order-canary.yaml"
    SERVER_AUTHZ = "policy/authorization/server.yaml"
    AUTHZ_POLICY = "policy/authorization/authz-policy.yaml"
    TESTS = "tests/test_linkerd_patterns.py"

    def _read_file(self, rel_path):
        filepath = os.path.join(self.REPO_DIR, rel_path)
        with open(filepath) as f:
            return f.read()

    # === File Path Checks ===

    def test_api_gateway_profile_exists(self):
        filepath = os.path.join(self.REPO_DIR, self.API_PROFILE)
        assert os.path.exists(filepath), f"api-gateway-profile.yaml not found"

    def test_order_service_profile_exists(self):
        filepath = os.path.join(self.REPO_DIR, self.ORDER_PROFILE)
        assert os.path.exists(filepath), f"order-service-profile.yaml not found"

    def test_payment_service_profile_exists(self):
        filepath = os.path.join(self.REPO_DIR, self.PAYMENT_PROFILE)
        assert os.path.exists(filepath), f"payment-service-profile.yaml not found"

    def test_traffic_split_exists(self):
        filepath = os.path.join(self.REPO_DIR, self.TRAFFIC_SPLIT)
        assert os.path.exists(filepath), f"order-canary.yaml not found"

    def test_authorization_files_exist(self):
        for path in [self.SERVER_AUTHZ, self.AUTHZ_POLICY]:
            filepath = os.path.join(self.REPO_DIR, path)
            assert os.path.exists(filepath), f"Authorization file not found: {filepath}"

    def test_tests_file_exists(self):
        filepath = os.path.join(self.REPO_DIR, self.TESTS)
        assert os.path.exists(filepath), f"Tests file not found"

    # === Semantic Checks ===

    @pytest.mark.skipif(yaml is None, reason="PyYAML not installed")
    def test_api_gateway_profile_routes(self):
        """Verify API gateway profile defines required routes"""
        content = self._read_file(self.API_PROFILE)
        assert "ServiceProfile" in content, "Missing ServiceProfile kind"
        for route in ["/api/orders", "/api/health"]:
            assert route in content, f"API profile missing route: {route}"

    def test_api_gateway_retry_budget(self):
        """Verify API gateway has retryBudget configured"""
        content = self._read_file(self.API_PROFILE)
        assert "retryBudget" in content, "API profile missing retryBudget"
        assert "retryRatio" in content, "retryBudget missing retryRatio"

    def test_api_gateway_post_not_retryable(self):
        """Verify POST /api/orders is NOT retryable"""
        content = self._read_file(self.API_PROFILE)
        assert "POST" in content, "API profile missing POST method"
        # POST + isRetryable: false should be near each other
        assert "isRetryable" in content, "Missing isRetryable field"

    def test_payment_charge_not_retryable(self):
        """Verify POST /charge is not retryable (financial transaction)"""
        content = self._read_file(self.PAYMENT_PROFILE)
        assert "/charge" in content, "Payment profile missing /charge route"
        assert "15" in content, "Payment /charge missing 15s timeout"

    def test_traffic_split_90_10(self):
        """Verify traffic split: 90% stable, 10% canary"""
        content = self._read_file(self.TRAFFIC_SPLIT)
        assert "TrafficSplit" in content, "Missing TrafficSplit kind"
        assert "900" in content, "TrafficSplit missing weight 900 (90%)"
        assert "100" in content, "TrafficSplit missing weight 100 (10%)"
        assert "stable" in content, "TrafficSplit missing stable backend"
        assert "canary" in content, "TrafficSplit missing canary backend"

    def test_server_authorization_restricts_payment(self):
        """Verify ServerAuthorization restricts payment-service to order-service"""
        content = self._read_file(self.SERVER_AUTHZ)
        assert "ServerAuthorization" in content or "Server" in content, \
            "Missing Server/ServerAuthorization resource"
        assert "payment" in content.lower(), "Missing payment-service reference"
        assert "order-service" in content, "Missing order-service reference"

    def test_authz_policy_uses_mtls(self):
        """Verify AuthorizationPolicy with MeshTLSAuthentication"""
        content = self._read_file(self.AUTHZ_POLICY)
        assert "AuthorizationPolicy" in content, "Missing AuthorizationPolicy"
        has_mtls = "MeshTLSAuthentication" in content or "meshTLS" in content.lower()
        assert has_mtls, "Missing MeshTLSAuthentication"

    def test_order_service_profile_routes(self):
        """Verify order-service profile defines order routes"""
        content = self._read_file(self.ORDER_PROFILE)
        assert "/orders" in content, "Order profile missing /orders route"

    # === Functional Checks ===

    def test_all_yaml_files_valid(self):
        """Verify all YAML files parse without errors"""
        if yaml is None:
            pytest.skip("PyYAML not installed")
        paths = [
            self.API_PROFILE, self.ORDER_PROFILE, self.PAYMENT_PROFILE,
            self.TRAFFIC_SPLIT, self.SERVER_AUTHZ, self.AUTHZ_POLICY,
        ]
        for path in paths:
            filepath = os.path.join(self.REPO_DIR, path)
            with open(filepath) as f:
                try:
                    list(yaml.safe_load_all(f.read()))
                except yaml.YAMLError as e:
                    pytest.fail(f"{path} YAML error: {e}")

    def test_traffic_split_weights_sum_to_1000(self):
        """Verify TrafficSplit weights sum to 1000"""
        if yaml is None:
            pytest.skip("PyYAML not installed")
        docs = list(yaml.safe_load_all(self._read_file(self.TRAFFIC_SPLIT)))
        for doc in docs:
            if doc and doc.get("kind") == "TrafficSplit":
                backends = doc.get("spec", {}).get("backends", [])
                total = sum(b.get("weight", 0) for b in backends)
                assert total == 1000, f"TrafficSplit weights sum to {total}, expected 1000"

    def test_service_profiles_have_timeout(self):
        """Verify all service profiles define route timeouts"""
        for path in [self.API_PROFILE, self.ORDER_PROFILE, self.PAYMENT_PROFILE]:
            content = self._read_file(path)
            assert "timeout" in content.lower(), \
                f"{path} missing timeout configuration"
