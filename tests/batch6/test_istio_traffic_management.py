"""
Test skill: istio-traffic-management
Verify that the Agent configures Istio for canary deployment with
circuit breaking, fault injection, traffic mirroring, and Gateway/
VirtualService/DestinationRule resources.
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


class TestIstioTrafficManagement:
    REPO_DIR = "/workspace/istio"

    # === File Path Checks ===

    def test_gateway_exists(self):
        assert os.path.exists(os.path.join(self.REPO_DIR, "istio/gateway.yaml"))

    def test_checkout_vs_exists(self):
        assert os.path.exists(os.path.join(self.REPO_DIR, "istio/checkout-vs.yaml"))

    def test_checkout_dr_exists(self):
        assert os.path.exists(os.path.join(self.REPO_DIR, "istio/checkout-dr.yaml"))

    def test_payment_files_exist(self):
        assert os.path.exists(os.path.join(self.REPO_DIR, "istio/payment-vs.yaml"))
        assert os.path.exists(os.path.join(self.REPO_DIR, "istio/payment-dr.yaml"))

    def test_inventory_files_exist(self):
        assert os.path.exists(os.path.join(self.REPO_DIR, "istio/inventory-vs.yaml"))
        assert os.path.exists(os.path.join(self.REPO_DIR, "istio/inventory-dr.yaml"))

    def test_fault_injection_exists(self):
        assert os.path.exists(os.path.join(self.REPO_DIR, "istio/fault-injection.yaml"))

    def test_traffic_mirror_exists(self):
        assert os.path.exists(os.path.join(self.REPO_DIR, "istio/traffic-mirror.yaml"))

    def test_k8s_deployments_exist(self):
        assert os.path.exists(os.path.join(self.REPO_DIR, "k8s/checkout-v1-deployment.yaml"))
        assert os.path.exists(os.path.join(self.REPO_DIR, "k8s/checkout-v2-deployment.yaml"))

    # === Semantic Checks ===

    def test_gateway_has_https(self):
        """Gateway should configure HTTPS on port 443"""
        path = os.path.join(self.REPO_DIR, "istio/gateway.yaml")
        with open(path) as f:
            content = f.read()
        assert "443" in content, "Gateway should have port 443"
        assert "SIMPLE" in content or "tls" in content.lower(), "Gateway should have TLS config"
        assert "shop.example.com" in content, "Gateway should serve shop.example.com"

    def test_gateway_has_http_redirect(self):
        """Gateway should redirect HTTP to HTTPS"""
        path = os.path.join(self.REPO_DIR, "istio/gateway.yaml")
        with open(path) as f:
            content = f.read()
        assert "httpsRedirect" in content or "redirect" in content.lower(), (
            "Gateway should redirect HTTP to HTTPS"
        )

    def test_checkout_vs_has_canary_header(self):
        """Checkout VS should route x-canary: true to v2"""
        path = os.path.join(self.REPO_DIR, "istio/checkout-vs.yaml")
        with open(path) as f:
            content = f.read()
        assert "x-canary" in content, "Should match x-canary header"

    def test_checkout_vs_has_weighted_split(self):
        """Checkout VS should have weighted routing between v1 and v2"""
        docs = load_yaml(os.path.join(self.REPO_DIR, "istio/checkout-vs.yaml"))
        doc = docs[0]
        content_str = str(doc)
        assert "v1" in content_str and "v2" in content_str, (
            "VS should reference both v1 and v2 subsets"
        )
        assert "weight" in content_str, "VS should have weighted routing"

    def test_checkout_dr_has_subsets(self):
        """Checkout DR should define v1 and v2 subsets"""
        docs = load_yaml(os.path.join(self.REPO_DIR, "istio/checkout-dr.yaml"))
        spec = docs[0].get("spec", {})
        subsets = spec.get("trafficPolicy", {}) or spec.get("subsets", [])
        # Check in content
        with open(os.path.join(self.REPO_DIR, "istio/checkout-dr.yaml")) as f:
            content = f.read()
        assert "v1" in content and "v2" in content, "DR should define v1 and v2 subsets"

    def test_checkout_dr_has_circuit_breaker(self):
        """Checkout DR should have outlier detection for circuit breaking"""
        path = os.path.join(self.REPO_DIR, "istio/checkout-dr.yaml")
        with open(path) as f:
            content = f.read()
        assert "outlierDetection" in content, "Missing outlier detection"
        assert "consecutive5xxErrors" in content or "consecutiveErrors" in content, (
            "Missing consecutive error threshold"
        )

    def test_checkout_vs_has_timeout_and_retries(self):
        """Checkout VS should have timeout of 10s and 3 retries"""
        path = os.path.join(self.REPO_DIR, "istio/checkout-vs.yaml")
        with open(path) as f:
            content = f.read()
        assert "timeout" in content, "Missing timeout"
        assert "retries" in content, "Missing retries"

    def test_payment_vs_has_timeout(self):
        """Payment VS should have timeout of 5s"""
        path = os.path.join(self.REPO_DIR, "istio/payment-vs.yaml")
        with open(path) as f:
            content = f.read()
        assert "timeout" in content, "Missing timeout"
        assert "5s" in content, "Payment timeout should be 5s"

    def test_fault_injection_has_safety_guard(self):
        """Fault injection should require x-test-chaos header"""
        path = os.path.join(self.REPO_DIR, "istio/fault-injection.yaml")
        with open(path) as f:
            content = f.read()
        assert "x-test-chaos" in content, "Fault injection must be guarded by x-test-chaos header"

    def test_fault_injection_has_abort_and_delay(self):
        """Fault injection should include 503 abort and delay"""
        path = os.path.join(self.REPO_DIR, "istio/fault-injection.yaml")
        with open(path) as f:
            content = f.read()
        assert "abort" in content, "Missing abort fault"
        assert "503" in content, "Abort should return 503"
        assert "delay" in content, "Missing delay fault"

    def test_traffic_mirror_targets_v2(self):
        """Traffic mirror should mirror to v2 subset"""
        path = os.path.join(self.REPO_DIR, "istio/traffic-mirror.yaml")
        with open(path) as f:
            content = f.read()
        assert "mirror" in content, "Missing mirror configuration"
        assert "v2" in content, "Mirror should target v2"

    def test_k8s_deployments_have_version_labels(self):
        """K8s deployments should have version labels matching subsets"""
        for ver, fname in [("v1", "checkout-v1-deployment.yaml"), ("v2", "checkout-v2-deployment.yaml")]:
            docs = load_yaml(os.path.join(self.REPO_DIR, f"k8s/{fname}"))
            labels = docs[0]["spec"]["template"]["metadata"]["labels"]
            assert labels.get("version") == ver, (
                f"{fname} should have label version: {ver}"
            )
            assert labels.get("app") == "checkout", (
                f"{fname} should have label app: checkout"
            )

    # === Functional Checks ===

    def test_all_yaml_files_parse(self):
        """All YAML files should parse without errors"""
        if yaml is None:
            pytest.skip("PyYAML not available")
        for d in ("istio", "k8s"):
            base = os.path.join(self.REPO_DIR, d)
            if not os.path.isdir(base):
                continue
            for root, _dirs, files in os.walk(base):
                for fname in files:
                    if fname.endswith((".yaml", ".yml")):
                        filepath = os.path.join(root, fname)
                        try:
                            with open(filepath) as f:
                                list(yaml.safe_load_all(f))
                        except yaml.YAMLError as e:
                            pytest.fail(f"{filepath} YAML error: {e}")

    def test_connection_pool_configured(self):
        """DestinationRules should have connectionPool settings"""
        for dr_file in ("checkout-dr.yaml", "payment-dr.yaml", "inventory-dr.yaml"):
            path = os.path.join(self.REPO_DIR, f"istio/{dr_file}")
            with open(path) as f:
                content = f.read()
            assert "connectionPool" in content or "maxConnections" in content, (
                f"{dr_file} should have connection pool config"
            )
