"""
Test skill: linkerd-patterns
Verify that the Agent configures Linkerd service mesh with ServiceProfiles,
TrafficSplit for canary deployments, and ServerAuthorization for zero-trust.
"""

import os
import re
import pytest

try:
    import yaml
except ImportError:
    yaml = None


def load_yaml(path):
    if yaml is None:
        pytest.skip("PyYAML not available")
    with open(path) as f:
        return list(yaml.safe_load_all(f))


class TestLinkerdPatterns:
    REPO_DIR = "/workspace/linkerd2"

    # === File Path Checks ===

    def test_namespace_exists(self):
        assert os.path.exists(
            os.path.join(self.REPO_DIR, "linkerd/namespace.yaml")
        )

    def test_gateway_service_profile_exists(self):
        assert os.path.exists(
            os.path.join(self.REPO_DIR, "linkerd/service-profiles/gateway-sp.yaml")
        )

    def test_orders_service_profile_exists(self):
        assert os.path.exists(
            os.path.join(self.REPO_DIR, "linkerd/service-profiles/orders-sp.yaml")
        )

    def test_payments_service_profile_exists(self):
        assert os.path.exists(
            os.path.join(self.REPO_DIR, "linkerd/service-profiles/payments-sp.yaml")
        )

    def test_traffic_split_exists(self):
        assert os.path.exists(
            os.path.join(self.REPO_DIR, "linkerd/traffic-split/orders-canary.yaml")
        )

    def test_authorization_files_exist(self):
        for fname in (
            "server-orders.yaml",
            "authz-orders.yaml",
            "authz-payments.yaml",
            "authz-notifications.yaml",
            "default-deny.yaml",
        ):
            path = os.path.join(self.REPO_DIR, f"linkerd/authorization/{fname}")
            assert os.path.exists(path), f"Missing {fname}"

    # === Semantic Checks ===

    def test_namespace_has_linkerd_inject(self):
        """Namespace should have linkerd.io/inject: enabled annotation"""
        docs = load_yaml(
            os.path.join(self.REPO_DIR, "linkerd/namespace.yaml")
        )
        doc = docs[0]
        annotations = doc.get("metadata", {}).get("annotations", {})
        assert annotations.get("linkerd.io/inject") == "enabled", (
            "Namespace must have linkerd.io/inject: enabled"
        )

    def test_gateway_sp_has_routes(self):
        """Gateway ServiceProfile should define routes with timeouts"""
        docs = load_yaml(
            os.path.join(self.REPO_DIR, "linkerd/service-profiles/gateway-sp.yaml")
        )
        spec = docs[0].get("spec", {})
        routes = spec.get("routes", [])
        assert len(routes) >= 4, f"Gateway SP should have at least 4 routes, found {len(routes)}"

    def test_gateway_sp_has_retry_budget(self):
        """Gateway ServiceProfile should have retryBudget"""
        path = os.path.join(
            self.REPO_DIR, "linkerd/service-profiles/gateway-sp.yaml"
        )
        with open(path) as f:
            content = f.read()
        assert "retryBudget" in content, "Missing retryBudget"
        assert "retryRatio" in content, "Missing retryRatio"

    def test_payments_post_not_retryable(self):
        """POST /payments should NOT be retryable"""
        docs = load_yaml(
            os.path.join(self.REPO_DIR, "linkerd/service-profiles/payments-sp.yaml")
        )
        spec = docs[0].get("spec", {})
        for route in spec.get("routes", []):
            name = route.get("name", "")
            if "POST" in name and "payment" in name.lower():
                assert route.get("isRetryable") is False or route.get("isRetryable") is None, (
                    "POST /payments must not be retryable"
                )

    def test_traffic_split_90_10(self):
        """TrafficSplit should be 90/10 between stable and canary"""
        docs = load_yaml(
            os.path.join(self.REPO_DIR, "linkerd/traffic-split/orders-canary.yaml")
        )
        doc = docs[0]
        assert doc.get("kind") == "TrafficSplit", "Must be kind TrafficSplit"
        backends = doc.get("spec", {}).get("backends", [])
        weights = {b.get("service"): b.get("weight") for b in backends}
        assert "orders-stable" in weights, "Missing orders-stable backend"
        assert "orders-canary" in weights, "Missing orders-canary backend"
        total = sum(weights.values())
        stable_pct = weights["orders-stable"] / total * 100
        assert 88 <= stable_pct <= 92, f"Stable should be ~90%, got {stable_pct:.1f}%"

    def test_authz_orders_allows_only_gateway(self):
        """Only gateway service account should access orders"""
        path = os.path.join(
            self.REPO_DIR, "linkerd/authorization/authz-orders.yaml"
        )
        with open(path) as f:
            content = f.read()
        assert "gateway" in content, "Orders authz should reference gateway SA"

    def test_authz_payments_allows_only_orders(self):
        """Only orders service account should access payments"""
        path = os.path.join(
            self.REPO_DIR, "linkerd/authorization/authz-payments.yaml"
        )
        with open(path) as f:
            content = f.read()
        assert "orders" in content, "Payments authz should reference orders SA"

    def test_authz_notifications_allows_orders_and_payments(self):
        """Both orders and payments should access notifications"""
        path = os.path.join(
            self.REPO_DIR, "linkerd/authorization/authz-notifications.yaml"
        )
        with open(path) as f:
            content = f.read()
        assert "orders" in content, "Notifications authz should allow orders"
        assert "payments" in content, "Notifications authz should allow payments"

    def test_default_deny_policy(self):
        """Default deny should select all pods in namespace"""
        docs = load_yaml(
            os.path.join(self.REPO_DIR, "linkerd/authorization/default-deny.yaml")
        )
        doc = docs[0]
        with open(os.path.join(self.REPO_DIR, "linkerd/authorization/default-deny.yaml")) as f:
            content = f.read()
        assert "deny" in content.lower() or "accessPolicy" in content, (
            "Default deny must enforce deny policy"
        )

    def test_mutation_routes_not_retryable(self):
        """POST/PUT/DELETE routes in orders SP should not be retryable"""
        docs = load_yaml(
            os.path.join(self.REPO_DIR, "linkerd/service-profiles/orders-sp.yaml")
        )
        spec = docs[0].get("spec", {})
        for route in spec.get("routes", []):
            name = route.get("name", "")
            if any(m in name for m in ("POST", "PUT", "DELETE")):
                assert route.get("isRetryable") is False, (
                    f"Mutation route '{name}' must have isRetryable: false"
                )

    # === Functional Checks ===

    def test_all_yaml_files_parse(self):
        """All YAML files under linkerd/ should parse without errors"""
        if yaml is None:
            pytest.skip("PyYAML not available")
        base = os.path.join(self.REPO_DIR, "linkerd")
        for root, _dirs, files in os.walk(base):
            for fname in files:
                if fname.endswith((".yaml", ".yml")):
                    filepath = os.path.join(root, fname)
                    try:
                        with open(filepath) as f:
                            list(yaml.safe_load_all(f))
                    except yaml.YAMLError as e:
                        pytest.fail(f"{filepath} has YAML error: {e}")

    def test_traffic_split_api_version(self):
        """TrafficSplit should use split.smi-spec.io/v1alpha1"""
        docs = load_yaml(
            os.path.join(self.REPO_DIR, "linkerd/traffic-split/orders-canary.yaml")
        )
        api = docs[0].get("apiVersion", "")
        assert "split.smi-spec.io" in api, (
            f"Expected split.smi-spec.io API version, got: {api}"
        )

    def test_server_uses_policy_api(self):
        """Server resources should use policy.linkerd.io API"""
        path = os.path.join(
            self.REPO_DIR, "linkerd/authorization/server-orders.yaml"
        )
        with open(path) as f:
            content = f.read()
        assert "policy.linkerd.io" in content, (
            "Server resource should use policy.linkerd.io API"
        )
