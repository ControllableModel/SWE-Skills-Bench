"""
Tests for skill: istio-traffic-management
Repo: istio/istio
Image: zhangyiiiiii/swe-skills-bench-python
Task: Implement Istio traffic management manifests for a bookinfo-style
      application with VirtualService routing, circuit breaking, fault
      injection, and traffic mirroring.
"""

import os
import re

import pytest
import yaml

REPO_DIR = "/workspace/istio"
DEMO_DIR = os.path.join(REPO_DIR, "samples", "traffic-demo")

BASE_DIR = os.path.join(DEMO_DIR, "base")
NET_DIR = os.path.join(DEMO_DIR, "networking")

DEPLOYMENTS_FILE = os.path.join(BASE_DIR, "deployments.yaml")
SERVICES_FILE = os.path.join(BASE_DIR, "services.yaml")
GATEWAY_FILE = os.path.join(NET_DIR, "gateway.yaml")
VIRTUALSERVICES_FILE = os.path.join(NET_DIR, "virtualservices.yaml")
DESTINATION_RULES_FILE = os.path.join(NET_DIR, "destination-rules.yaml")
TRAFFIC_MIRROR_FILE = os.path.join(NET_DIR, "traffic-mirror.yaml")


def _load_yaml(path):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _load_yaml_all(path):
    with open(path, "r", encoding="utf-8") as f:
        return [d for d in yaml.safe_load_all(f) if d]


# ---------------------------------------------------------------------------
# Layer 1 — file_path_check
# ---------------------------------------------------------------------------

class TestFilePathCheck:
    """Verify all required Istio manifest files exist."""

    def test_deployments_exists(self):
        assert os.path.isfile(DEPLOYMENTS_FILE), f"Missing {DEPLOYMENTS_FILE}"

    def test_services_exists(self):
        assert os.path.isfile(SERVICES_FILE), f"Missing {SERVICES_FILE}"

    def test_gateway_exists(self):
        assert os.path.isfile(GATEWAY_FILE), f"Missing {GATEWAY_FILE}"

    def test_virtualservices_exists(self):
        assert os.path.isfile(VIRTUALSERVICES_FILE), f"Missing {VIRTUALSERVICES_FILE}"

    def test_destination_rules_exists(self):
        assert os.path.isfile(DESTINATION_RULES_FILE), f"Missing {DESTINATION_RULES_FILE}"

    def test_traffic_mirror_exists(self):
        assert os.path.isfile(TRAFFIC_MIRROR_FILE), f"Missing {TRAFFIC_MIRROR_FILE}"


# ---------------------------------------------------------------------------
# Layer 2 — semantic_check
# ---------------------------------------------------------------------------

class TestSemanticDeployments:
    """Verify deployment manifests for all services."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.docs = _load_yaml_all(DEPLOYMENTS_FILE)
        self.deployments = [d for d in self.docs if d.get("kind") == "Deployment"]

    def test_at_least_four_deployments(self):
        assert len(self.deployments) >= 4, (
            f"Expected at least 4 Deployments (frontend, reviews-v1, reviews-v2, ratings); "
            f"found {len(self.deployments)}"
        )

    def test_frontend_deployment(self):
        for dep in self.deployments:
            labels = dep["spec"]["template"]["metadata"].get("labels", {})
            if labels.get("app") == "frontend":
                return
        pytest.fail("Missing frontend deployment")

    def test_reviews_v1_deployment(self):
        for dep in self.deployments:
            labels = dep["spec"]["template"]["metadata"].get("labels", {})
            if labels.get("app") == "reviews" and labels.get("version") == "v1":
                return
        pytest.fail("Missing reviews v1 deployment")

    def test_reviews_v2_deployment(self):
        for dep in self.deployments:
            labels = dep["spec"]["template"]["metadata"].get("labels", {})
            if labels.get("app") == "reviews" and labels.get("version") == "v2":
                return
        pytest.fail("Missing reviews v2 deployment")

    def test_istio_injection_annotation(self):
        for dep in self.deployments:
            annots = dep["spec"]["template"]["metadata"].get("annotations", {})
            inject = annots.get("sidecar.istio.io/inject", "")
            if inject != "true":
                name = dep["metadata"].get("name", "unknown")
                pytest.fail(
                    f"Deployment '{name}' missing sidecar.istio.io/inject: 'true'"
                )


class TestSemanticGateway:
    """Verify Istio Gateway resource."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.doc = _load_yaml(GATEWAY_FILE)

    def test_kind_gateway(self):
        assert self.doc["kind"] == "Gateway"

    def test_api_version(self):
        api = self.doc.get("apiVersion", "")
        assert "istio" in api or "networking" in api, (
            f"Expected Istio networking API version; got '{api}'"
        )

    def test_selector_ingressgateway(self):
        selector = self.doc["spec"].get("selector", {})
        assert selector.get("istio") == "ingressgateway", (
            f"Gateway selector should be istio: ingressgateway; got {selector}"
        )

    def test_host_configured(self):
        servers = self.doc["spec"].get("servers", [])
        for s in servers:
            hosts = s.get("hosts", [])
            if any("traffic-demo" in h for h in hosts):
                return
        pytest.fail("Gateway should have traffic-demo.example.com host")

    def test_port_80(self):
        servers = self.doc["spec"].get("servers", [])
        for s in servers:
            port = s.get("port", {})
            if port.get("number") == 80:
                return
        pytest.fail("Gateway should have port 80")


class TestSemanticVirtualServices:
    """Verify VirtualService routing rules."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.docs = _load_yaml_all(VIRTUALSERVICES_FILE)
        self.vs_map = {}
        for d in self.docs:
            if d.get("kind") == "VirtualService":
                name = d["metadata"].get("name", "")
                self.vs_map[name] = d

    def test_at_least_three_virtualservices(self):
        vs_list = [d for d in self.docs if d.get("kind") == "VirtualService"]
        assert len(vs_list) >= 3, (
            f"Expected at least 3 VirtualServices; found {len(vs_list)}"
        )

    def test_reviews_canary_weights(self):
        """Reviews VS should have 90/10 canary split."""
        for name, vs in self.vs_map.items():
            hosts = vs["spec"].get("hosts", [])
            if any("reviews" in h for h in hosts) or "reviews" in name:
                routes = vs["spec"].get("http", [])
                for r in routes:
                    destinations = r.get("route", [])
                    weights = [d.get("weight", 0) for d in destinations if "weight" in d]
                    if 90 in weights and 10 in weights:
                        return
                    if sorted(weights) == [10, 90]:
                        return
        pytest.fail("Reviews VirtualService should have 90/10 canary weights")

    def test_reviews_header_routing(self):
        """Reviews VS should route based on end-user header."""
        for name, vs in self.vs_map.items():
            hosts = vs["spec"].get("hosts", [])
            if any("reviews" in h for h in hosts) or "reviews" in name:
                raw = yaml.dump(vs)
                if "end-user" in raw or "tester" in raw:
                    return
        pytest.fail("Reviews VS should have header-based routing for end-user: tester")

    def test_reviews_timeout(self):
        for name, vs in self.vs_map.items():
            hosts = vs["spec"].get("hosts", [])
            if any("reviews" in h for h in hosts) or "reviews" in name:
                raw = yaml.dump(vs)
                if "timeout" in raw:
                    return
        pytest.fail("Reviews VS should have a timeout configured")

    def test_reviews_retries(self):
        for name, vs in self.vs_map.items():
            hosts = vs["spec"].get("hosts", [])
            if any("reviews" in h for h in hosts) or "reviews" in name:
                raw = yaml.dump(vs)
                if "retries" in raw:
                    return
        pytest.fail("Reviews VS should have retries configured")


class TestSemanticRatingsFaultInjection:
    """Verify fault injection on ratings VirtualService."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.docs = _load_yaml_all(VIRTUALSERVICES_FILE)

    def test_abort_fault(self):
        for d in self.docs:
            if d.get("kind") == "VirtualService":
                raw = yaml.dump(d)
                if "ratings" in raw and "abort" in raw:
                    return
        pytest.fail("Ratings VS should have abort fault injection")

    def test_delay_fault(self):
        for d in self.docs:
            if d.get("kind") == "VirtualService":
                raw = yaml.dump(d)
                if "ratings" in raw and ("fixedDelay" in raw or "delay" in raw):
                    return
        pytest.fail("Ratings VS should have delay fault injection")


class TestSemanticDestinationRules:
    """Verify DestinationRule resources."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.docs = _load_yaml_all(DESTINATION_RULES_FILE)

    def test_reviews_destination_rule(self):
        for d in self.docs:
            if d.get("kind") == "DestinationRule":
                host = d["spec"].get("host", "")
                if "reviews" in host:
                    return
        pytest.fail("Missing reviews DestinationRule")

    def test_reviews_subsets(self):
        for d in self.docs:
            if d.get("kind") == "DestinationRule":
                host = d["spec"].get("host", "")
                if "reviews" in host:
                    subsets = d["spec"].get("subsets", [])
                    names = [s.get("name", "") for s in subsets]
                    assert "v1" in names, f"Reviews DR should have v1 subset; got {names}"
                    assert "v2" in names, f"Reviews DR should have v2 subset; got {names}"
                    return
        pytest.fail("Missing reviews DestinationRule")

    def test_outlier_detection(self):
        for d in self.docs:
            if d.get("kind") == "DestinationRule":
                raw = yaml.dump(d)
                if "outlierDetection" in raw:
                    return
        pytest.fail("At least one DestinationRule should have outlierDetection")

    def test_connection_pool(self):
        for d in self.docs:
            if d.get("kind") == "DestinationRule":
                raw = yaml.dump(d)
                if "connectionPool" in raw:
                    return
        pytest.fail("Reviews DestinationRule should have connectionPool settings")


class TestSemanticTrafficMirror:
    """Verify traffic mirroring configuration."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.doc = _load_yaml(TRAFFIC_MIRROR_FILE)

    def test_kind_virtualservice(self):
        assert self.doc["kind"] == "VirtualService"

    def test_mirror_configured(self):
        raw = yaml.dump(self.doc)
        assert "mirror" in raw.lower(), "Traffic mirror VS must have mirror configuration"

    def test_mirror_percentage(self):
        raw = yaml.dump(self.doc)
        assert "mirrorPercent" in raw or "mirror_percentage" in raw or "100" in raw, (
            "Mirror should specify percentage"
        )


# ---------------------------------------------------------------------------
# Layer 3 — functional_check
# ---------------------------------------------------------------------------

class TestFunctionalCanaryWeights:
    """Functionally verify canary split is exactly 90/10."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.docs = _load_yaml_all(VIRTUALSERVICES_FILE)

    def test_canary_weights_sum_100(self):
        for d in self.docs:
            if d.get("kind") == "VirtualService":
                hosts = d["spec"].get("hosts", [])
                if any("reviews" in h for h in hosts) or "reviews" in d["metadata"].get("name", ""):
                    for http_route in d["spec"].get("http", []):
                        route = http_route.get("route", [])
                        weights = [r.get("weight", 0) for r in route if "weight" in r]
                        if weights:
                            total = sum(weights)
                            assert total == 100, (
                                f"Canary weights should sum to 100; got {total} ({weights})"
                            )
                            return
        pytest.fail("Could not find reviews canary route with weights")


class TestFunctionalFaultPercentages:
    """Verify fault injection percentages on ratings."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.docs = _load_yaml_all(VIRTUALSERVICES_FILE)

    def test_abort_percentage_10(self):
        for d in self.docs:
            if d.get("kind") != "VirtualService":
                continue
            raw = yaml.dump(d)
            if "ratings" not in raw:
                continue
            for http_route in d["spec"].get("http", []):
                fault = http_route.get("fault", {})
                abort = fault.get("abort", {})
                pct = abort.get("percentage", abort.get("percent", {}))
                if isinstance(pct, dict):
                    val = pct.get("value", 0)
                else:
                    val = pct
                if val == 10:
                    return
        pytest.fail("Ratings abort fault should be 10%")

    def test_delay_percentage_5(self):
        for d in self.docs:
            if d.get("kind") != "VirtualService":
                continue
            raw = yaml.dump(d)
            if "ratings" not in raw:
                continue
            for http_route in d["spec"].get("http", []):
                fault = http_route.get("fault", {})
                delay = fault.get("delay", {})
                pct = delay.get("percentage", delay.get("percent", {}))
                if isinstance(pct, dict):
                    val = pct.get("value", 0)
                else:
                    val = pct
                if val == 5:
                    return
        pytest.fail("Ratings delay fault should be 5%")

    def test_delay_is_3_seconds(self):
        for d in self.docs:
            if d.get("kind") != "VirtualService":
                continue
            raw = yaml.dump(d)
            if "ratings" not in raw:
                continue
            for http_route in d["spec"].get("http", []):
                fault = http_route.get("fault", {})
                delay = fault.get("delay", {})
                fixed = delay.get("fixedDelay", "")
                if "3s" in str(fixed) or "3000" in str(fixed):
                    return
        pytest.fail("Ratings delay should be 3s")


class TestFunctionalCircuitBreaker:
    """Verify circuit breaker / outlier detection values."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.docs = _load_yaml_all(DESTINATION_RULES_FILE)

    def test_reviews_consecutive_errors(self):
        for d in self.docs:
            if d.get("kind") == "DestinationRule":
                host = d["spec"].get("host", "")
                if "reviews" in host:
                    od = d["spec"].get("trafficPolicy", {}).get("outlierDetection", {})
                    errors = od.get("consecutive5xxErrors", od.get("consecutiveErrors", 0))
                    assert errors == 5, (
                        f"Reviews outlier consecutive5xxErrors should be 5; got {errors}"
                    )
                    return
        pytest.fail("Reviews DestinationRule not found")

    def test_reviews_max_connections(self):
        for d in self.docs:
            if d.get("kind") == "DestinationRule":
                host = d["spec"].get("host", "")
                if "reviews" in host:
                    cp = d["spec"].get("trafficPolicy", {}).get("connectionPool", {})
                    tcp = cp.get("tcp", {})
                    max_conn = tcp.get("maxConnections", 0)
                    assert max_conn == 100, (
                        f"Reviews TCP maxConnections should be 100; got {max_conn}"
                    )
                    return
        pytest.fail("Reviews DestinationRule not found")

    def test_all_yaml_valid(self):
        """All YAML files in the demo directory must be parseable."""
        for dirpath, _, filenames in os.walk(DEMO_DIR):
            for fn in filenames:
                if fn.endswith(".yaml") or fn.endswith(".yml"):
                    fpath = os.path.join(dirpath, fn)
                    with open(fpath, "r", encoding="utf-8") as f:
                        docs = list(yaml.safe_load_all(f))
                    assert docs, f"Failed to parse {fpath}"
