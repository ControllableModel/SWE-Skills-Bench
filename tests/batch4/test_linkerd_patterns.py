"""
Tests for skill: linkerd-patterns
Repo: linkerd/linkerd2
Image: zhangyiiiiii/swe-skills-bench-golang
Task: Create Linkerd service mesh configuration with service profiles,
      traffic splits, and server authorization policies.
"""

import os
import re

import pytest
import yaml

REPO_DIR = "/workspace/linkerd2"
DEMO_DIR = os.path.join(REPO_DIR, "examples", "mesh-demo")

MANIFESTS_DIR = os.path.join(DEMO_DIR, "manifests")
PROFILES_DIR = os.path.join(DEMO_DIR, "profiles")
TRAFFIC_DIR = os.path.join(DEMO_DIR, "traffic")
POLICY_DIR = os.path.join(DEMO_DIR, "policy")

NAMESPACE_FILE = os.path.join(MANIFESTS_DIR, "namespace.yaml")
FRONTEND_FILE = os.path.join(MANIFESTS_DIR, "frontend.yaml")
API_FILE = os.path.join(MANIFESTS_DIR, "api.yaml")
DB_PROXY_FILE = os.path.join(MANIFESTS_DIR, "db-proxy.yaml")
API_PROFILE_FILE = os.path.join(PROFILES_DIR, "api-profile.yaml")
FRONTEND_PROFILE_FILE = os.path.join(PROFILES_DIR, "frontend-profile.yaml")
CANARY_SPLIT_FILE = os.path.join(TRAFFIC_DIR, "canary-split.yaml")
SERVER_POLICY_FILE = os.path.join(POLICY_DIR, "server.yaml")


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
    """Verify all required Linkerd manifest files exist."""

    def test_namespace_exists(self):
        assert os.path.isfile(NAMESPACE_FILE), f"Missing {NAMESPACE_FILE}"

    def test_frontend_exists(self):
        assert os.path.isfile(FRONTEND_FILE), f"Missing {FRONTEND_FILE}"

    def test_api_exists(self):
        assert os.path.isfile(API_FILE), f"Missing {API_FILE}"

    def test_db_proxy_exists(self):
        assert os.path.isfile(DB_PROXY_FILE), f"Missing {DB_PROXY_FILE}"

    def test_api_profile_exists(self):
        assert os.path.isfile(API_PROFILE_FILE), f"Missing {API_PROFILE_FILE}"

    def test_frontend_profile_exists(self):
        assert os.path.isfile(FRONTEND_PROFILE_FILE), f"Missing {FRONTEND_PROFILE_FILE}"

    def test_canary_split_exists(self):
        assert os.path.isfile(CANARY_SPLIT_FILE), f"Missing {CANARY_SPLIT_FILE}"

    def test_server_policy_exists(self):
        assert os.path.isfile(SERVER_POLICY_FILE), f"Missing {SERVER_POLICY_FILE}"


# ---------------------------------------------------------------------------
# Layer 2 — semantic_check
# ---------------------------------------------------------------------------

class TestSemanticNamespace:
    """Verify namespace with Linkerd injection annotation."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.doc = _load_yaml(NAMESPACE_FILE)

    def test_kind_namespace(self):
        assert self.doc["kind"] == "Namespace"

    def test_name_mesh_demo(self):
        assert self.doc["metadata"]["name"] == "mesh-demo"

    def test_injection_annotation(self):
        annotations = self.doc["metadata"].get("annotations", {})
        assert annotations.get("linkerd.io/inject") == "enabled", (
            f"Expected linkerd.io/inject=enabled; got {annotations}"
        )


class TestSemanticServiceDeployments:
    """Verify frontend, API, and db-proxy deployment structures."""

    def _find_deployment(self, docs):
        for d in docs:
            if d.get("kind") == "Deployment":
                return d
        return None

    def _find_service(self, docs):
        for d in docs:
            if d.get("kind") == "Service":
                return d
        return None

    def test_frontend_replicas(self):
        docs = _load_yaml_all(FRONTEND_FILE)
        dep = self._find_deployment(docs)
        assert dep, "Frontend deployment not found"
        assert dep["spec"].get("replicas", 1) == 2, "Frontend should have 2 replicas"

    def test_frontend_port(self):
        docs = _load_yaml_all(FRONTEND_FILE)
        dep = self._find_deployment(docs)
        containers = dep["spec"]["template"]["spec"]["containers"]
        ports = [p["containerPort"] for c in containers for p in c.get("ports", [])]
        assert 8080 in ports, f"Frontend container port should be 8080; got {ports}"

    def test_frontend_injection_annotation(self):
        docs = _load_yaml_all(FRONTEND_FILE)
        dep = self._find_deployment(docs)
        annots = dep["spec"]["template"]["metadata"].get("annotations", {})
        assert annots.get("linkerd.io/inject") == "enabled", (
            "Frontend pod template needs linkerd.io/inject: enabled"
        )

    def test_api_stable_version_label(self):
        docs = _load_yaml_all(API_FILE)
        for d in docs:
            if d.get("kind") == "Deployment":
                labels = d["spec"]["template"]["metadata"].get("labels", {})
                if labels.get("version") == "v1":
                    return
        pytest.fail("Expected API stable deployment with version=v1 label")

    def test_api_canary_version_label(self):
        docs = _load_yaml_all(API_FILE)
        found_canary = False
        for d in docs:
            if d.get("kind") == "Deployment":
                labels = d["spec"]["template"]["metadata"].get("labels", {})
                if labels.get("version") == "v2":
                    found_canary = True
        if not found_canary:
            # Canary may be in a separate file; check traffic dir
            canary_path = os.path.join(MANIFESTS_DIR, "api-canary.yaml")
            if os.path.isfile(canary_path):
                docs2 = _load_yaml_all(canary_path)
                for d in docs2:
                    if d.get("kind") == "Deployment":
                        labels = d["spec"]["template"]["metadata"].get("labels", {})
                        if labels.get("version") == "v2":
                            found_canary = True
        assert found_canary, "Expected API canary deployment with version=v2 label"

    def test_db_proxy_port(self):
        docs = _load_yaml_all(DB_PROXY_FILE)
        dep = self._find_deployment(docs)
        assert dep, "DB proxy deployment not found"
        containers = dep["spec"]["template"]["spec"]["containers"]
        ports = [p["containerPort"] for c in containers for p in c.get("ports", [])]
        assert 5432 in ports, f"DB proxy container port should be 5432; got {ports}"

    def test_db_proxy_tcp_probe(self):
        docs = _load_yaml_all(DB_PROXY_FILE)
        dep = self._find_deployment(docs)
        containers = dep["spec"]["template"]["spec"]["containers"]
        for c in containers:
            probe = c.get("livenessProbe", {})
            tcp = probe.get("tcpSocket", {})
            if tcp.get("port") == 5432:
                return
        pytest.fail("DB proxy should have TCP liveness probe on port 5432")


class TestSemanticAPIProfile:
    """Verify API ServiceProfile routes, retries, and timeouts."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.doc = _load_yaml(API_PROFILE_FILE)

    def test_kind_service_profile(self):
        assert self.doc["kind"] == "ServiceProfile"

    def test_api_version(self):
        api = self.doc.get("apiVersion", "")
        assert "linkerd.io" in api, f"Expected linkerd.io API version; got '{api}'"

    def test_routes_defined(self):
        routes = self.doc.get("spec", {}).get("routes", [])
        assert len(routes) >= 4, f"Expected at least 4 API routes; found {len(routes)}"

    def test_get_users_retryable(self):
        routes = self.doc["spec"]["routes"]
        for r in routes:
            name = r.get("name", "")
            cond = r.get("condition", {})
            method = cond.get("method", "")
            path = cond.get("pathRegex", "")
            if "GET" in (method or name) and "/api/users" in (path or name):
                if path == "/api/users" or (not re.search(r'\{|\\[', path)):
                    retryable = r.get("isRetryable", False)
                    assert retryable, f"GET /api/users should be retryable"
                    return
        pytest.fail("GET /api/users route not found in API profile")

    def test_post_users_not_retryable(self):
        routes = self.doc["spec"]["routes"]
        for r in routes:
            name = r.get("name", "")
            cond = r.get("condition", {})
            method = cond.get("method", "")
            path = cond.get("pathRegex", "")
            if "POST" in (method or name) and "/api/users" in (path or name):
                retryable = r.get("isRetryable", True)
                assert not retryable, "POST /api/users should NOT be retryable"
                return
        pytest.fail("POST /api/users route not found in API profile")

    def test_retry_budget(self):
        budget = self.doc["spec"].get("retryBudget", {})
        assert budget, "API profile must have a retryBudget"
        assert "retryRatio" in budget, "retryBudget must include retryRatio"

    def test_route_timeouts(self):
        routes = self.doc["spec"]["routes"]
        for r in routes:
            timeout = r.get("timeout", "")
            if timeout:
                return
        pytest.fail("At least one route should have a timeout defined")


class TestSemanticTrafficSplit:
    """Verify canary traffic split configuration."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.doc = _load_yaml(CANARY_SPLIT_FILE)

    def test_kind_traffic_split(self):
        assert self.doc["kind"] == "TrafficSplit"

    def test_api_version(self):
        api = self.doc.get("apiVersion", "")
        assert "split.smi-spec.io" in api, f"Expected split.smi-spec.io; got '{api}'"

    def test_two_backends(self):
        backends = self.doc["spec"].get("backends", [])
        assert len(backends) == 2, f"Expected 2 backends; got {len(backends)}"

    def test_weights_900_100(self):
        backends = self.doc["spec"]["backends"]
        weights = sorted([b.get("weight", 0) for b in backends])
        assert weights == [100, 900], f"Expected weights [100, 900]; got {weights}"

    def test_service_reference(self):
        svc = self.doc["spec"].get("service", "")
        assert "api" in svc, f"TrafficSplit should reference the api service; got '{svc}'"


class TestSemanticServerPolicy:
    """Verify zero-trust Server and ServerAuthorization resources."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.docs = _load_yaml_all(SERVER_POLICY_FILE)

    def test_server_resource_present(self):
        kinds = [d["kind"] for d in self.docs]
        assert "Server" in kinds, f"Expected Server resource; found {kinds}"

    def test_server_authorization_present(self):
        kinds = [d["kind"] for d in self.docs]
        assert "ServerAuthorization" in kinds, f"Expected ServerAuthorization; found {kinds}"

    def test_server_port(self):
        for d in self.docs:
            if d["kind"] == "Server":
                port = d["spec"].get("port", 0)
                assert port == 8081, f"Server port should be 8081; got {port}"
                return
        pytest.fail("Server resource not found")

    def test_frontend_authorization(self):
        """Verify only frontend service account is authorized to access API."""
        for d in self.docs:
            if d["kind"] == "ServerAuthorization":
                raw = yaml.dump(d)
                if "frontend" in raw:
                    return
        pytest.fail("Expected ServerAuthorization allowing frontend service account")


# ---------------------------------------------------------------------------
# Layer 3 — functional_check
# ---------------------------------------------------------------------------

class TestFunctionalTrafficSplitRatio:
    """Verify 90/10 canary split ratio."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.doc = _load_yaml(CANARY_SPLIT_FILE)

    def test_stable_weight_90_percent(self):
        backends = self.doc["spec"]["backends"]
        total = sum(b.get("weight", 0) for b in backends)
        stable = None
        for b in backends:
            name = b.get("service", b.get("name", ""))
            if "canary" not in name:
                stable = b.get("weight", 0)
        assert stable is not None, "Could not identify stable backend"
        ratio = stable / total
        assert abs(ratio - 0.9) < 0.01, f"Stable backend should get ~90% traffic; got {ratio*100:.1f}%"

    def test_canary_weight_10_percent(self):
        backends = self.doc["spec"]["backends"]
        total = sum(b.get("weight", 0) for b in backends)
        canary = None
        for b in backends:
            name = b.get("service", b.get("name", ""))
            if "canary" in name:
                canary = b.get("weight", 0)
        assert canary is not None, "Could not identify canary backend"
        ratio = canary / total
        assert abs(ratio - 0.1) < 0.01, f"Canary backend should get ~10% traffic; got {ratio*100:.1f}%"

    def test_weights_sum_to_1000(self):
        backends = self.doc["spec"]["backends"]
        total = sum(b.get("weight", 0) for b in backends)
        assert total == 1000, f"Weights should sum to 1000; got {total}"


class TestFunctionalAPIRouteDetails:
    """Verify specific API route configurations."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.doc = _load_yaml(API_PROFILE_FILE)
        self.routes = self.doc["spec"]["routes"]

    def _find_route(self, method_part, path_part):
        for r in self.routes:
            name = r.get("name", "")
            cond = r.get("condition", {})
            method = cond.get("method", "")
            path = cond.get("pathRegex", "")
            if method_part in (method or name) and path_part in (path or name):
                return r
        return None

    def test_get_users_timeout_5s(self):
        r = self._find_route("GET", "/api/users")
        assert r, "GET /api/users route not found"
        # Check the route or its first matching route for timeout
        timeout = r.get("timeout", "")
        assert "5" in str(timeout), f"GET /api/users timeout should be 5s; got '{timeout}'"

    def test_post_users_timeout_10s(self):
        r = self._find_route("POST", "/api/users")
        assert r, "POST /api/users route not found"
        timeout = r.get("timeout", "")
        assert "10" in str(timeout), f"POST /api/users timeout should be 10s; got '{timeout}'"

    def test_delete_users_not_retryable(self):
        r = self._find_route("DELETE", "/api/users")
        assert r, "DELETE /api/users/{id} route not found"
        retryable = r.get("isRetryable", True)
        assert not retryable, "DELETE /api/users/{id} should NOT be retryable"

    def test_retry_budget_ratio(self):
        budget = self.doc["spec"].get("retryBudget", {})
        ratio = budget.get("retryRatio", -1)
        assert ratio == 0.2, f"retryRatio should be 0.2; got {ratio}"

    def test_retry_budget_min_retries(self):
        budget = self.doc["spec"].get("retryBudget", {})
        min_retries = budget.get("minRetriesPerSecond", -1)
        assert min_retries == 10, f"minRetriesPerSecond should be 10; got {min_retries}"


class TestFunctionalZeroTrust:
    """Verify zero-trust policy enforcement details."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.docs = _load_yaml_all(SERVER_POLICY_FILE)

    def test_api_server_selects_api_pods(self):
        for d in self.docs:
            if d["kind"] == "Server":
                selector = d["spec"].get("podSelector", d["spec"].get("selector", {}))
                ml = selector.get("matchLabels", {})
                assert ml.get("app") == "api", (
                    f"Server should select pods with app=api; got {ml}"
                )
                return
        pytest.fail("Server resource not found")

    def test_prometheus_authorization(self):
        for d in self.docs:
            if d["kind"] == "ServerAuthorization":
                raw = yaml.dump(d)
                if "prometheus" in raw:
                    assert "monitoring" in raw, (
                        "Prometheus authorization should reference monitoring namespace"
                    )
                    return
        pytest.fail("Expected ServerAuthorization for prometheus service account")

    def test_all_yaml_valid(self):
        """All YAML files in the demo directory must be parseable."""
        for dirpath, _, filenames in os.walk(DEMO_DIR):
            for fn in filenames:
                if fn.endswith(".yaml") or fn.endswith(".yml"):
                    fpath = os.path.join(dirpath, fn)
                    with open(fpath, "r", encoding="utf-8") as f:
                        docs = list(yaml.safe_load_all(f))
                    assert docs, f"Failed to parse {fpath}"
