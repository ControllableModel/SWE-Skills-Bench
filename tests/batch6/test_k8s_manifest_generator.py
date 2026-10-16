"""
Test skill: k8s-manifest-generator
Verify that the Agent generates production-ready Kubernetes manifests for
a three-tier e-commerce application (storefront, API, PostgreSQL) with
security contexts, HPA, NetworkPolicies, and Ingress.
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


class TestK8sManifestGenerator:
    REPO_DIR = "/workspace/kustomize"

    # === File Path Checks ===

    def test_namespace_exists(self):
        assert os.path.exists(os.path.join(self.REPO_DIR, "k8s/namespace.yaml"))

    def test_storefront_manifests_exist(self):
        for f in ("deployment.yaml", "service.yaml", "configmap.yaml"):
            path = os.path.join(self.REPO_DIR, f"k8s/storefront/{f}")
            assert os.path.exists(path), f"Missing storefront/{f}"

    def test_api_manifests_exist(self):
        for f in ("deployment.yaml", "service.yaml", "configmap.yaml", "secret.yaml", "hpa.yaml"):
            path = os.path.join(self.REPO_DIR, f"k8s/api/{f}")
            assert os.path.exists(path), f"Missing api/{f}"

    def test_db_manifests_exist(self):
        for f in ("statefulset.yaml", "service.yaml", "configmap.yaml", "secret.yaml"):
            path = os.path.join(self.REPO_DIR, f"k8s/db/{f}")
            assert os.path.exists(path), f"Missing db/{f}"

    def test_ingress_exists(self):
        assert os.path.exists(os.path.join(self.REPO_DIR, "k8s/ingress.yaml"))

    def test_networkpolicy_exists(self):
        assert os.path.exists(os.path.join(self.REPO_DIR, "k8s/networkpolicy.yaml"))

    # === Semantic Checks ===

    def test_storefront_uses_pinned_tag(self):
        """Storefront deployment should use pinned image tag, not :latest"""
        docs = load_yaml(os.path.join(self.REPO_DIR, "k8s/storefront/deployment.yaml"))
        doc = docs[0]
        containers = doc["spec"]["template"]["spec"]["containers"]
        image = containers[0].get("image", "")
        assert ":latest" not in image, "Image must not use :latest"
        assert ":" in image, "Image must have a pinned tag"

    def test_storefront_has_security_context(self):
        """Storefront should run as non-root with readOnlyRootFilesystem"""
        docs = load_yaml(os.path.join(self.REPO_DIR, "k8s/storefront/deployment.yaml"))
        spec = docs[0]["spec"]["template"]["spec"]
        pod_sec = spec.get("securityContext", {})
        assert pod_sec.get("runAsNonRoot") is True, "Must set runAsNonRoot: true"
        container_sec = spec["containers"][0].get("securityContext", {})
        assert container_sec.get("readOnlyRootFilesystem") is True, (
            "Must set readOnlyRootFilesystem: true"
        )
        assert container_sec.get("allowPrivilegeEscalation") is False, (
            "Must set allowPrivilegeEscalation: false"
        )

    def test_storefront_has_probes(self):
        """Storefront should have liveness and readiness probes"""
        docs = load_yaml(os.path.join(self.REPO_DIR, "k8s/storefront/deployment.yaml"))
        container = docs[0]["spec"]["template"]["spec"]["containers"][0]
        assert "livenessProbe" in container, "Missing livenessProbe"
        assert "readinessProbe" in container, "Missing readinessProbe"

    def test_storefront_has_resource_limits(self):
        """Storefront should have resource requests and limits"""
        docs = load_yaml(os.path.join(self.REPO_DIR, "k8s/storefront/deployment.yaml"))
        container = docs[0]["spec"]["template"]["spec"]["containers"][0]
        resources = container.get("resources", {})
        assert "requests" in resources, "Missing resource requests"
        assert "limits" in resources, "Missing resource limits"

    def test_api_hpa_config(self):
        """HPA should target API deployment with min 3 max 10"""
        docs = load_yaml(os.path.join(self.REPO_DIR, "k8s/api/hpa.yaml"))
        doc = docs[0]
        spec = doc.get("spec", {})
        assert spec.get("minReplicas") == 3, f"HPA min should be 3, got {spec.get('minReplicas')}"
        assert spec.get("maxReplicas") == 10, f"HPA max should be 10, got {spec.get('maxReplicas')}"

    def test_api_hpa_targets_cpu_and_memory(self):
        """HPA should target both CPU and memory utilization"""
        docs = load_yaml(os.path.join(self.REPO_DIR, "k8s/api/hpa.yaml"))
        metrics = docs[0].get("spec", {}).get("metrics", [])
        metric_types = [m.get("resource", {}).get("name", "") for m in metrics if m.get("type") == "Resource"]
        assert "cpu" in metric_types, "HPA should target CPU"
        assert "memory" in metric_types, "HPA should target memory"

    def test_db_statefulset_has_volume_claim(self):
        """PostgreSQL StatefulSet should have volumeClaimTemplates"""
        docs = load_yaml(os.path.join(self.REPO_DIR, "k8s/db/statefulset.yaml"))
        doc = docs[0]
        assert doc.get("kind") == "StatefulSet", "DB should be a StatefulSet"
        vcts = doc.get("spec", {}).get("volumeClaimTemplates", [])
        assert len(vcts) >= 1, "Missing volumeClaimTemplates"
        storage = vcts[0]["spec"]["resources"]["requests"]["storage"]
        assert "20Gi" in str(storage), f"VCT should request 20Gi, got {storage}"

    def test_db_uses_postgres_alpine(self):
        """DB should use postgres:16-alpine image"""
        docs = load_yaml(os.path.join(self.REPO_DIR, "k8s/db/statefulset.yaml"))
        containers = docs[0]["spec"]["template"]["spec"]["containers"]
        image = containers[0].get("image", "")
        assert "postgres" in image, f"DB image should be postgres, got {image}"
        assert "alpine" in image, "Should use alpine variant"

    def test_ingress_has_tls(self):
        """Ingress should have TLS configuration"""
        docs = load_yaml(os.path.join(self.REPO_DIR, "k8s/ingress.yaml"))
        doc = docs[0]
        assert doc.get("spec", {}).get("tls"), "Ingress must have TLS config"

    def test_ingress_has_path_routing(self):
        """Ingress should route /api to api and / to storefront"""
        path = os.path.join(self.REPO_DIR, "k8s/ingress.yaml")
        with open(path) as f:
            content = f.read()
        assert "/api" in content, "Ingress should route /api"
        assert "storefront" in content, "Ingress should route to storefront"

    def test_networkpolicy_has_default_deny(self):
        """NetworkPolicies should include default deny"""
        path = os.path.join(self.REPO_DIR, "k8s/networkpolicy.yaml")
        with open(path) as f:
            content = f.read()
        assert "default-deny" in content or "DefaultDeny" in content or "deny" in content.lower(), (
            "Should include a default-deny NetworkPolicy"
        )

    def test_api_has_startup_probe(self):
        """API deployment should have startupProbe"""
        docs = load_yaml(os.path.join(self.REPO_DIR, "k8s/api/deployment.yaml"))
        container = docs[0]["spec"]["template"]["spec"]["containers"][0]
        assert "startupProbe" in container, "API should have startupProbe"

    # === Functional Checks ===

    def test_all_yaml_files_parse(self):
        """All YAML files under k8s/ should parse without errors"""
        if yaml is None:
            pytest.skip("PyYAML not available")
        base = os.path.join(self.REPO_DIR, "k8s")
        for root, _dirs, files in os.walk(base):
            for fname in files:
                if fname.endswith((".yaml", ".yml")):
                    filepath = os.path.join(root, fname)
                    try:
                        with open(filepath) as f:
                            list(yaml.safe_load_all(f))
                    except yaml.YAMLError as e:
                        pytest.fail(f"{filepath} has YAML error: {e}")

    def test_all_manifests_have_namespace(self):
        """All manifests should reference the production namespace"""
        if yaml is None:
            pytest.skip("PyYAML not available")
        # Check a sampling of key files
        for filepath in (
            "k8s/storefront/deployment.yaml",
            "k8s/api/deployment.yaml",
            "k8s/db/statefulset.yaml",
        ):
            full = os.path.join(self.REPO_DIR, filepath)
            docs = load_yaml(full)
            ns = docs[0].get("metadata", {}).get("namespace", "")
            assert ns == "production", (
                f"{filepath} should be in production namespace, got '{ns}'"
            )

    def test_secrets_are_base64_or_stringdata(self):
        """Secrets should use data (base64) or stringData"""
        for filepath in ("k8s/api/secret.yaml", "k8s/db/secret.yaml"):
            full = os.path.join(self.REPO_DIR, filepath)
            if not os.path.exists(full):
                continue
            docs = load_yaml(full)
            doc = docs[0]
            assert doc.get("kind") == "Secret", f"{filepath} should be a Secret"
            assert "data" in doc or "stringData" in doc, (
                f"{filepath} should have data or stringData"
            )
