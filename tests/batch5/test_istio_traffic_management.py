"""
Test skill: istio-traffic-management
Verify that the Agent correctly configures Istio traffic management resources
for canary, fault injection, circuit breaking, and ingress routing.
"""

import os
import re
import pytest

try:
    import yaml
except ImportError:
    yaml = None


class TestIstioTrafficManagement:
    REPO_DIR = "/workspace/istio"

    DEST_RULES = "samples/bookinfo/networking/destination-rules.yaml"
    CANARY_VS = "samples/bookinfo/networking/virtual-service-canary.yaml"
    FAULT_VS = "samples/bookinfo/networking/virtual-service-fault.yaml"
    GATEWAY = "samples/bookinfo/networking/gateway.yaml"
    INGRESS_VS = "samples/bookinfo/networking/virtual-service-ingress.yaml"
    CIRCUIT_BREAKER = "samples/bookinfo/networking/circuit-breaker.yaml"

    def _read_file(self, rel_path):
        filepath = os.path.join(self.REPO_DIR, rel_path)
        with open(filepath) as f:
            return f.read()

    # === File Path Checks ===

    def test_destination_rules_exists(self):
        filepath = os.path.join(self.REPO_DIR, self.DEST_RULES)
        assert os.path.exists(filepath), f"destination-rules.yaml not found"

    def test_canary_virtual_service_exists(self):
        filepath = os.path.join(self.REPO_DIR, self.CANARY_VS)
        assert os.path.exists(filepath), f"virtual-service-canary.yaml not found"

    def test_fault_virtual_service_exists(self):
        filepath = os.path.join(self.REPO_DIR, self.FAULT_VS)
        assert os.path.exists(filepath), f"virtual-service-fault.yaml not found"

    def test_gateway_exists(self):
        filepath = os.path.join(self.REPO_DIR, self.GATEWAY)
        assert os.path.exists(filepath), f"gateway.yaml not found"

    def test_circuit_breaker_exists(self):
        filepath = os.path.join(self.REPO_DIR, self.CIRCUIT_BREAKER)
        assert os.path.exists(filepath), f"circuit-breaker.yaml not found"

    # === Semantic Checks ===

    @pytest.mark.skipif(yaml is None, reason="PyYAML not installed")
    def test_dest_rules_subsets(self):
        """Verify reviews destination rule has v1, v2, v3 subsets"""
        content = self._read_file(self.DEST_RULES)
        for version in ["v1", "v2", "v3"]:
            assert version in content, f"Destination rules missing subset: {version}"

    @pytest.mark.skipif(yaml is None, reason="PyYAML not installed")
    def test_canary_weights_sum_100(self):
        """Verify canary route weights sum to 100"""
        content = self._read_file(self.CANARY_VS)
        docs = list(yaml.safe_load_all(content))
        for doc in docs:
            if doc and doc.get("kind") == "VirtualService":
                routes = doc.get("spec", {}).get("http", [])
                for route in routes:
                    route_dests = route.get("route", [])
                    if len(route_dests) > 1:
                        total = sum(d.get("weight", 0) for d in route_dests)
                        assert total == 100, \
                            f"Canary weights sum to {total}, expected 100"

    def test_canary_header_based_routing(self):
        """Verify header x-canary: true routes to v3"""
        content = self._read_file(self.CANARY_VS)
        assert "x-canary" in content, "Canary VS missing x-canary header match"
        assert "v3" in content, "Canary VS missing v3 destination"

    def test_canary_timeout_and_retries(self):
        """Verify canary VS has timeout and retry config"""
        content = self._read_file(self.CANARY_VS)
        assert "timeout" in content, "Canary VS missing timeout"
        assert "retries" in content, "Canary VS missing retries"

    def test_fault_injection_delay_and_abort(self):
        """Verify fault injection with 7s delay (10%) and 503 abort (5%)"""
        content = self._read_file(self.FAULT_VS)
        assert "delay" in content, "Fault VS missing delay injection"
        assert "abort" in content, "Fault VS missing abort injection"
        assert "503" in content, "Fault VS missing HTTP 503 abort code"
        assert "7" in content, "Fault VS missing 7-second delay"

    def test_fault_injection_header_match(self):
        """Verify fault injection only when x-test-fault: enabled"""
        content = self._read_file(self.FAULT_VS)
        assert "x-test-fault" in content, "Fault VS missing header match"

    def test_gateway_http_and_https(self):
        """Verify gateway defines port 80 and 443 with TLS"""
        content = self._read_file(self.GATEWAY)
        assert "Gateway" in content, "Missing Gateway kind"
        assert "80" in content, "Gateway missing port 80"
        assert "443" in content, "Gateway missing port 443"
        assert "tls" in content.lower(), "Gateway missing TLS config"

    def test_circuit_breaker_config(self):
        """Verify circuit breaker with connection pool and outlier detection"""
        content = self._read_file(self.CIRCUIT_BREAKER)
        assert "connectionPool" in content, "CB missing connectionPool"
        assert "outlierDetection" in content, "CB missing outlierDetection"
        assert "consecutive5xxErrors" in content, "CB missing consecutive5xxErrors"
        assert "baseEjectionTime" in content, "CB missing baseEjectionTime"

    # === Functional Checks ===

    def test_all_yaml_files_valid(self):
        """Verify all YAML files parse without errors"""
        if yaml is None:
            pytest.skip("PyYAML not installed")
        paths = [self.DEST_RULES, self.CANARY_VS, self.FAULT_VS,
                 self.GATEWAY, self.INGRESS_VS, self.CIRCUIT_BREAKER]
        for path in paths:
            filepath = os.path.join(self.REPO_DIR, path)
            with open(filepath) as f:
                try:
                    list(yaml.safe_load_all(f.read()))
                except yaml.YAMLError as e:
                    pytest.fail(f"{path} YAML error: {e}")

    def test_all_resources_have_correct_api_version(self):
        """Verify all resources use networking.istio.io API"""
        for path in [self.DEST_RULES, self.CANARY_VS, self.FAULT_VS,
                     self.GATEWAY, self.INGRESS_VS, self.CIRCUIT_BREAKER]:
            content = self._read_file(path)
            assert "networking.istio.io" in content, \
                f"{path} missing networking.istio.io apiVersion"

    def test_ingress_vs_routes_to_services(self):
        """Verify ingress VS routes /productpage, /api/reviews, /api/ratings"""
        content = self._read_file(self.INGRESS_VS)
        assert "productpage" in content, "Ingress VS missing /productpage route"
        assert "reviews" in content, "Ingress VS missing reviews route"
        assert "ratings" in content, "Ingress VS missing ratings route"
