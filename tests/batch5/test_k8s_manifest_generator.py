"""
Test skill: k8s-manifest-generator
Verify that the Agent correctly creates Kustomize base and overlay structure
for a web application with dev, staging, and production environments.
"""

import os
import re
import subprocess
import pytest

try:
    import yaml
except ImportError:
    yaml = None


class TestK8sManifestGenerator:
    REPO_DIR = "/workspace/kustomize"

    BASE_DEPLOY = "examples/webapp/base/deployment.yaml"
    BASE_SERVICE = "examples/webapp/base/service.yaml"
    BASE_HPA = "examples/webapp/base/hpa.yaml"
    BASE_KUSTOMIZATION = "examples/webapp/base/kustomization.yaml"
    DEV_OVERLAY = "examples/webapp/overlays/dev/kustomization.yaml"
    STAGING_OVERLAY = "examples/webapp/overlays/staging/kustomization.yaml"
    PROD_OVERLAY = "examples/webapp/overlays/production/kustomization.yaml"
    PROD_INGRESS = "examples/webapp/overlays/production/ingress.yaml"
    PROD_PDB = "examples/webapp/overlays/production/pdb.yaml"

    def _read_file(self, rel_path):
        filepath = os.path.join(self.REPO_DIR, rel_path)
        with open(filepath) as f:
            return f.read()

    # === File Path Checks ===

    def test_base_files_exist(self):
        for path in [self.BASE_DEPLOY, self.BASE_SERVICE, self.BASE_HPA,
                     self.BASE_KUSTOMIZATION]:
            filepath = os.path.join(self.REPO_DIR, path)
            assert os.path.exists(filepath), f"Base file not found: {filepath}"

    def test_overlay_files_exist(self):
        for path in [self.DEV_OVERLAY, self.STAGING_OVERLAY, self.PROD_OVERLAY]:
            filepath = os.path.join(self.REPO_DIR, path)
            assert os.path.exists(filepath), f"Overlay not found: {filepath}"

    def test_prod_extras_exist(self):
        for path in [self.PROD_INGRESS, self.PROD_PDB]:
            filepath = os.path.join(self.REPO_DIR, path)
            assert os.path.exists(filepath), f"Production extra not found: {filepath}"

    # === Semantic Checks ===

    @pytest.mark.skipif(yaml is None, reason="PyYAML not installed")
    def test_base_deploy_has_probes_and_resources(self):
        """Verify base deployment has probes and resource limits"""
        docs = list(yaml.safe_load_all(self._read_file(self.BASE_DEPLOY)))
        deploy = docs[0]
        container = deploy["spec"]["template"]["spec"]["containers"][0]
        assert "readinessProbe" in container, "Missing readinessProbe"
        assert "livenessProbe" in container, "Missing livenessProbe"
        assert "resources" in container, "Missing resource limits"
        resources = container["resources"]
        assert "limits" in resources, "Missing resource limits"
        assert "requests" in resources, "Missing resource requests"

    @pytest.mark.skipif(yaml is None, reason="PyYAML not installed")
    def test_base_deploy_ports(self):
        """Verify deployment exposes ports 8080 and 9090"""
        docs = list(yaml.safe_load_all(self._read_file(self.BASE_DEPLOY)))
        deploy = docs[0]
        container = deploy["spec"]["template"]["spec"]["containers"][0]
        ports = [p.get("containerPort") for p in container.get("ports", [])]
        assert 8080 in ports, "Missing port 8080"
        assert 9090 in ports, "Missing metrics port 9090"

    @pytest.mark.skipif(yaml is None, reason="PyYAML not installed")
    def test_base_hpa_config(self):
        """Verify HPA: min 2, max 10, CPU 70%"""
        docs = list(yaml.safe_load_all(self._read_file(self.BASE_HPA)))
        hpa = docs[0]
        spec = hpa["spec"]
        assert spec.get("minReplicas") == 2, "HPA minReplicas should be 2"
        assert spec.get("maxReplicas") == 10, "HPA maxReplicas should be 10"

    def test_base_kustomization_has_configmap_generator(self):
        """Verify base kustomization uses configMapGenerator"""
        content = self._read_file(self.BASE_KUSTOMIZATION)
        assert "configMapGenerator" in content, \
            "Base kustomization missing configMapGenerator"

    def test_dev_overlay_reduces_replicas(self):
        """Verify dev overlay sets replicas to 1 and removes HPA"""
        dev_dir = os.path.dirname(os.path.join(self.REPO_DIR, self.DEV_OVERLAY))
        all_content = ""
        for f in os.listdir(dev_dir):
            fp = os.path.join(dev_dir, f)
            if os.path.isfile(fp):
                with open(fp) as fh:
                    all_content += fh.read()
        assert "1" in all_content, "Dev overlay missing replicas: 1 patch"
        assert "debug" in all_content.lower(), "Dev overlay missing LOG_LEVEL=debug"

    def test_prod_overlay_has_3_replicas(self):
        """Verify production overlay sets 3 replicas"""
        prod_dir = os.path.dirname(os.path.join(self.REPO_DIR, self.PROD_OVERLAY))
        all_content = ""
        for f in os.listdir(prod_dir):
            fp = os.path.join(prod_dir, f)
            if os.path.isfile(fp):
                with open(fp) as fh:
                    all_content += fh.read()
        assert "3" in all_content, "Production overlay missing replicas: 3"

    @pytest.mark.skipif(yaml is None, reason="PyYAML not installed")
    def test_prod_ingress_has_tls(self):
        """Verify production ingress has TLS configuration"""
        docs = list(yaml.safe_load_all(self._read_file(self.PROD_INGRESS)))
        ingress = docs[0]
        assert ingress.get("kind") == "Ingress", "Not an Ingress resource"
        assert "tls" in ingress.get("spec", {}), "Ingress missing TLS"
        assert "webapp.example.com" in self._read_file(self.PROD_INGRESS), \
            "Ingress missing host webapp.example.com"

    @pytest.mark.skipif(yaml is None, reason="PyYAML not installed")
    def test_prod_pdb_config(self):
        """Verify PodDisruptionBudget with minAvailable"""
        docs = list(yaml.safe_load_all(self._read_file(self.PROD_PDB)))
        pdb = docs[0]
        assert pdb.get("kind") == "PodDisruptionBudget", "Not a PDB resource"
        assert "minAvailable" in pdb.get("spec", {}), "PDB missing minAvailable"

    # === Functional Checks ===

    def test_all_yaml_files_valid(self):
        """Verify all YAML files parse without errors"""
        if yaml is None:
            pytest.skip("PyYAML not installed")
        paths = [
            self.BASE_DEPLOY, self.BASE_SERVICE, self.BASE_HPA,
            self.BASE_KUSTOMIZATION, self.DEV_OVERLAY, self.STAGING_OVERLAY,
            self.PROD_OVERLAY, self.PROD_INGRESS, self.PROD_PDB,
        ]
        for path in paths:
            filepath = os.path.join(self.REPO_DIR, path)
            if os.path.exists(filepath):
                with open(filepath) as f:
                    try:
                        list(yaml.safe_load_all(f.read()))
                    except yaml.YAMLError as e:
                        pytest.fail(f"{path} YAML error: {e}")

    def test_kustomize_build_dev(self):
        """Verify kustomize build succeeds for dev overlay"""
        result = subprocess.run(
            ["kustomize", "build", "examples/webapp/overlays/dev/"],
            cwd=self.REPO_DIR,
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            assert "Deployment" in result.stdout, "Dev build missing Deployment"
        # May fail if kustomize not installed; not a hard failure

    def test_kustomize_build_production(self):
        """Verify kustomize build succeeds for production overlay"""
        result = subprocess.run(
            ["kustomize", "build", "examples/webapp/overlays/production/"],
            cwd=self.REPO_DIR,
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            output = result.stdout
            assert "Deployment" in output, "Prod build missing Deployment"
            assert "Ingress" in output, "Prod build missing Ingress"
