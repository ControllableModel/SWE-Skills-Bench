"""
Test skill: istio-traffic-management
Verify that the Agent correctly implements traffic management policies
for the Bookinfo application in Istio.
"""

import os
import re
import subprocess
import pytest
import yaml


class TestIstioTrafficManagement:
    REPO_DIR = "/workspace/istio"

    # === File Path Checks ===

    def test_reviews_canary_exists(self):
        """Verify reviews-canary.yaml was created"""
        path = os.path.join(
            self.REPO_DIR, "samples/bookinfo/networking/reviews-canary.yaml"
        )
        assert os.path.exists(path), "reviews-canary.yaml not found"

    def test_ratings_circuit_breaker_exists(self):
        """Verify ratings-circuit-breaker.yaml was created"""
        path = os.path.join(
            self.REPO_DIR, "samples/bookinfo/networking/ratings-circuit-breaker.yaml"
        )
        assert os.path.exists(path), "ratings-circuit-breaker.yaml not found"

    def test_details_fault_injection_exists(self):
        """Verify details-fault-injection.yaml was created"""
        path = os.path.join(
            self.REPO_DIR, "samples/bookinfo/networking/details-fault-injection.yaml"
        )
        assert os.path.exists(path), "details-fault-injection.yaml not found"

    def test_bookinfo_gateway_exists(self):
        """Verify bookinfo-gateway.yaml was created"""
        path = os.path.join(
            self.REPO_DIR, "samples/bookinfo/networking/bookinfo-gateway.yaml"
        )
        assert os.path.exists(path), "bookinfo-gateway.yaml not found"

    # === Semantic Checks: Reviews Canary ===

    def test_reviews_canary_vs_name(self):
        """Verify VirtualService named reviews-canary"""
        path = os.path.join(
            self.REPO_DIR, "samples/bookinfo/networking/reviews-canary.yaml"
        )
        docs = list(yaml.safe_load_all(open(path)))
        vs_docs = [d for d in docs if d and d.get("kind") == "VirtualService"]
        names = [d["metadata"]["name"] for d in vs_docs]
        assert "reviews-canary" in names, "Should have VirtualService reviews-canary"

    def test_reviews_canary_weighted_80_20(self):
        """Verify 80/20 traffic split"""
        path = os.path.join(
            self.REPO_DIR, "samples/bookinfo/networking/reviews-canary.yaml"
        )
        with open(path) as f:
            content = f.read()
        assert "80" in content, "Should have 80% weight"
        assert "20" in content, "Should have 20% weight"

    def test_reviews_canary_header_match(self):
        """Verify x-canary header match rule"""
        path = os.path.join(
            self.REPO_DIR, "samples/bookinfo/networking/reviews-canary.yaml"
        )
        with open(path) as f:
            content = f.read()
        assert "x-canary" in content, "Should match x-canary header"

    def test_reviews_dr_three_subsets(self):
        """Verify DestinationRule has v1, stable, canary subsets"""
        path = os.path.join(
            self.REPO_DIR, "samples/bookinfo/networking/reviews-canary.yaml"
        )
        docs = list(yaml.safe_load_all(open(path)))
        dr_docs = [d for d in docs if d and d.get("kind") == "DestinationRule"]
        assert len(dr_docs) >= 1, "Should have DestinationRule"
        dr = dr_docs[0]
        subset_names = [s["name"] for s in dr["spec"]["subsets"]]
        for name in ["v1", "stable", "canary"]:
            assert name in subset_names, f"Should have subset '{name}'"

    def test_reviews_dr_connection_pool(self):
        """Verify DestinationRule has connectionPool settings"""
        path = os.path.join(
            self.REPO_DIR, "samples/bookinfo/networking/reviews-canary.yaml"
        )
        with open(path) as f:
            content = f.read()
        assert "connectionPool" in content, "Should have connectionPool"
        assert "100" in content, "Should have maxConnections: 100"

    # === Semantic Checks: Ratings Circuit Breaker ===

    def test_ratings_cb_name(self):
        """Verify DestinationRule named ratings-cb"""
        path = os.path.join(
            self.REPO_DIR, "samples/bookinfo/networking/ratings-circuit-breaker.yaml"
        )
        docs = list(yaml.safe_load_all(open(path)))
        dr = [d for d in docs if d and d.get("kind") == "DestinationRule"]
        assert any(d["metadata"]["name"] == "ratings-cb" for d in dr), (
            "Should have DestinationRule ratings-cb"
        )

    def test_ratings_cb_outlier_detection(self):
        """Verify outlier detection settings"""
        path = os.path.join(
            self.REPO_DIR, "samples/bookinfo/networking/ratings-circuit-breaker.yaml"
        )
        with open(path) as f:
            content = f.read()
        assert "outlierDetection" in content, "Should have outlierDetection"
        assert "consecutive5xxErrors" in content, (
            "Should have consecutive5xxErrors"
        )

    def test_ratings_cb_max_connections(self):
        """Verify tcp maxConnections: 50"""
        path = os.path.join(
            self.REPO_DIR, "samples/bookinfo/networking/ratings-circuit-breaker.yaml"
        )
        with open(path) as f:
            content = f.read()
        assert "50" in content, "Should have maxConnections: 50"

    # === Semantic Checks: Details Fault Injection ===

    def test_details_fault_delay(self):
        """Verify fixed delay of 3s on 15% of requests"""
        path = os.path.join(
            self.REPO_DIR, "samples/bookinfo/networking/details-fault-injection.yaml"
        )
        with open(path) as f:
            content = f.read()
        assert "3s" in content, "Should inject 3s delay"
        assert "15" in content, "Should apply to 15% of requests"

    def test_details_fault_abort(self):
        """Verify HTTP 503 abort on 5% of requests"""
        path = os.path.join(
            self.REPO_DIR, "samples/bookinfo/networking/details-fault-injection.yaml"
        )
        with open(path) as f:
            content = f.read()
        assert "503" in content, "Should inject 503 abort"

    def test_details_timeout_and_retries(self):
        """Verify timeout and retries configuration"""
        path = os.path.join(
            self.REPO_DIR, "samples/bookinfo/networking/details-fault-injection.yaml"
        )
        with open(path) as f:
            content = f.read()
        assert "timeout" in content, "Should have timeout"
        assert "retries" in content, "Should have retries block"
        assert "attempts" in content, "Should specify retry attempts"

    # === Semantic Checks: Gateway ===

    def test_gateway_name(self):
        """Verify Gateway named bookinfo-gateway"""
        path = os.path.join(
            self.REPO_DIR, "samples/bookinfo/networking/bookinfo-gateway.yaml"
        )
        docs = list(yaml.safe_load_all(open(path)))
        gw = [d for d in docs if d and d.get("kind") == "Gateway"]
        assert any(d["metadata"]["name"] == "bookinfo-gateway" for d in gw), (
            "Should have Gateway bookinfo-gateway"
        )

    def test_gateway_https_tls(self):
        """Verify HTTPS server with TLS mode SIMPLE"""
        path = os.path.join(
            self.REPO_DIR, "samples/bookinfo/networking/bookinfo-gateway.yaml"
        )
        with open(path) as f:
            content = f.read()
        assert "SIMPLE" in content, "Should have TLS mode SIMPLE"
        assert "443" in content, "Should have port 443"

    def test_gateway_http_redirect(self):
        """Verify HTTP redirect to HTTPS"""
        path = os.path.join(
            self.REPO_DIR, "samples/bookinfo/networking/bookinfo-gateway.yaml"
        )
        with open(path) as f:
            content = f.read()
        assert "httpsRedirect" in content, "Should have httpsRedirect"
        assert "80" in content, "Should have port 80"

    def test_gateway_routing_rules(self):
        """Verify VirtualService with URI prefix routes"""
        path = os.path.join(
            self.REPO_DIR, "samples/bookinfo/networking/bookinfo-gateway.yaml"
        )
        with open(path) as f:
            content = f.read()
        assert "/api/v1/reviews" in content, "Should route /api/v1/reviews"
        assert "/api/v1/ratings" in content, "Should route /api/v1/ratings"
        assert "productpage" in content, "Should route / to productpage"

    # === Semantic Checks: Shared ===

    def test_all_resources_use_v1beta1(self):
        """Verify all resources use networking.istio.io/v1beta1"""
        files = [
            "samples/bookinfo/networking/reviews-canary.yaml",
            "samples/bookinfo/networking/ratings-circuit-breaker.yaml",
            "samples/bookinfo/networking/details-fault-injection.yaml",
            "samples/bookinfo/networking/bookinfo-gateway.yaml",
        ]
        for rel_path in files:
            path = os.path.join(self.REPO_DIR, rel_path)
            with open(path) as f:
                content = f.read()
            assert "networking.istio.io/v1beta1" in content, (
                f"{rel_path} should use apiVersion networking.istio.io/v1beta1"
            )

    def test_all_resources_have_namespace(self):
        """Verify all resources set namespace: bookinfo"""
        files = [
            "samples/bookinfo/networking/reviews-canary.yaml",
            "samples/bookinfo/networking/ratings-circuit-breaker.yaml",
            "samples/bookinfo/networking/details-fault-injection.yaml",
            "samples/bookinfo/networking/bookinfo-gateway.yaml",
        ]
        for rel_path in files:
            path = os.path.join(self.REPO_DIR, rel_path)
            docs = list(yaml.safe_load_all(open(path)))
            for doc in docs:
                if doc and "metadata" in doc:
                    assert doc["metadata"].get("namespace") == "bookinfo", (
                        f"{doc['metadata']['name']} should have namespace bookinfo"
                    )

    # === Functional Checks ===

    def test_all_yaml_valid(self):
        """Verify all YAML files parse without errors"""
        files = [
            "samples/bookinfo/networking/reviews-canary.yaml",
            "samples/bookinfo/networking/ratings-circuit-breaker.yaml",
            "samples/bookinfo/networking/details-fault-injection.yaml",
            "samples/bookinfo/networking/bookinfo-gateway.yaml",
        ]
        for rel_path in files:
            path = os.path.join(self.REPO_DIR, rel_path)
            docs = list(yaml.safe_load_all(open(path)))
            assert len(docs) > 0, f"{rel_path} should have at least one document"

    def test_no_duplicate_names_in_file(self):
        """Verify no duplicate metadata.name within same file"""
        files = [
            "samples/bookinfo/networking/reviews-canary.yaml",
            "samples/bookinfo/networking/ratings-circuit-breaker.yaml",
            "samples/bookinfo/networking/details-fault-injection.yaml",
            "samples/bookinfo/networking/bookinfo-gateway.yaml",
        ]
        for rel_path in files:
            path = os.path.join(self.REPO_DIR, rel_path)
            docs = list(yaml.safe_load_all(open(path)))
            names = [
                d["metadata"]["name"] for d in docs
                if d and "metadata" in d and "name" in d["metadata"]
            ]
            assert len(names) == len(set(names)), (
                f"{rel_path} has duplicate metadata.name values"
            )
