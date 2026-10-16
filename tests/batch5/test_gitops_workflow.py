"""
Test skill: gitops-workflow
Verify that the Agent correctly configures a Flux CD GitOps deployment
pipeline with Kustomization, HelmRelease, and multi-environment overlays.
"""

import os
import re
import pytest

try:
    import yaml
except ImportError:
    yaml = None


class TestGitopsWorkflow:
    REPO_DIR = "/workspace/flux2"

    GOTK_SYNC = "config/clusters/staging/flux-system/gotk-sync.yaml"
    STAGING_KUSTOMIZATION = "config/clusters/staging/apps/kustomization.yaml"
    FRONTEND_DEPLOY = "config/apps/base/frontend/deployment.yaml"
    BACKEND_DEPLOY = "config/apps/base/backend/deployment.yaml"
    STAGING_OVERLAY = "config/apps/overlays/staging/kustomization.yaml"
    PROD_OVERLAY = "config/apps/overlays/production/kustomization.yaml"
    HELM_RELEASE = "config/infrastructure/db/helmrelease.yaml"
    HELM_REPO = "config/infrastructure/db/helmrepository.yaml"

    def _read_file(self, rel_path):
        filepath = os.path.join(self.REPO_DIR, rel_path)
        with open(filepath) as f:
            return f.read()

    def _load_yaml(self, rel_path):
        content = self._read_file(rel_path)
        return list(yaml.safe_load_all(content))

    # === File Path Checks ===

    def test_gotk_sync_exists(self):
        filepath = os.path.join(self.REPO_DIR, self.GOTK_SYNC)
        assert os.path.exists(filepath), f"gotk-sync.yaml not found at {filepath}"

    def test_base_deployments_exist(self):
        for path in [self.FRONTEND_DEPLOY, self.BACKEND_DEPLOY]:
            filepath = os.path.join(self.REPO_DIR, path)
            assert os.path.exists(filepath), f"Deployment not found: {filepath}"

    def test_overlays_exist(self):
        for path in [self.STAGING_OVERLAY, self.PROD_OVERLAY]:
            filepath = os.path.join(self.REPO_DIR, path)
            assert os.path.exists(filepath), f"Overlay not found: {filepath}"

    def test_helm_release_exists(self):
        filepath = os.path.join(self.REPO_DIR, self.HELM_RELEASE)
        assert os.path.exists(filepath), f"HelmRelease not found at {filepath}"

    # === Semantic Checks ===

    @pytest.mark.skipif(yaml is None, reason="PyYAML not installed")
    def test_gotk_sync_has_gitrepository_and_kustomization(self):
        """Verify gotk-sync.yaml contains GitRepository and Kustomization"""
        docs = self._load_yaml(self.GOTK_SYNC)
        kinds = [d.get("kind") for d in docs if d]
        assert "GitRepository" in kinds, "Missing GitRepository resource"
        assert "Kustomization" in kinds, "Missing Kustomization resource"

    @pytest.mark.skipif(yaml is None, reason="PyYAML not installed")
    def test_frontend_deploy_has_probes_and_resources(self):
        """Verify frontend deployment has readiness probe and resource limits"""
        docs = self._load_yaml(self.FRONTEND_DEPLOY)
        deploy = docs[0]
        containers = deploy["spec"]["template"]["spec"]["containers"]
        container = containers[0]
        assert "readinessProbe" in container, "Frontend missing readinessProbe"
        assert "resources" in container, "Frontend missing resource limits"

    @pytest.mark.skipif(yaml is None, reason="PyYAML not installed")
    def test_backend_deploy_has_env_from_configmap_and_secret(self):
        """Verify backend deployment gets env vars from ConfigMap and Secret"""
        content = self._read_file(self.BACKEND_DEPLOY)
        assert "configMapKeyRef" in content or "configMapRef" in content or "backend-config" in content, \
            "Backend missing ConfigMap env vars"
        assert "secretKeyRef" in content or "secretRef" in content or "backend-secrets" in content, \
            "Backend missing Secret env vars"

    @pytest.mark.skipif(yaml is None, reason="PyYAML not installed")
    def test_helm_release_postgresql(self):
        """Verify HelmRelease references Bitnami PostgreSQL chart"""
        docs = self._load_yaml(self.HELM_RELEASE)
        hr = docs[0]
        assert hr.get("kind") == "HelmRelease", "Not a HelmRelease resource"
        chart = hr["spec"]["chart"]["spec"]
        assert chart.get("chart") == "postgresql", "HelmRelease missing postgresql chart"
        assert "bitnami" in chart.get("sourceRef", {}).get("name", "").lower() or \
               "bitnami" in self._read_file(self.HELM_REPO).lower(), \
            "HelmRelease missing Bitnami source"

    @pytest.mark.skipif(yaml is None, reason="PyYAML not installed")
    def test_helm_release_remediation(self):
        """Verify HelmRelease has install/upgrade remediation retries"""
        content = self._read_file(self.HELM_RELEASE)
        assert "remediation" in content, "HelmRelease missing remediation config"
        assert "retries" in content, "HelmRelease missing retry count"

    def test_prod_overlay_has_pdb(self):
        """Verify production overlay includes PodDisruptionBudget"""
        prod_dir = os.path.dirname(os.path.join(self.REPO_DIR, self.PROD_OVERLAY))
        files = os.listdir(prod_dir) if os.path.isdir(prod_dir) else []
        all_content = ""
        for f in files:
            fp = os.path.join(prod_dir, f)
            if os.path.isfile(fp):
                with open(fp) as fh:
                    all_content += fh.read()
        assert "PodDisruptionBudget" in all_content, \
            "Production overlay missing PodDisruptionBudget"

    def test_staging_overlay_reduces_replicas(self):
        """Verify staging overlay sets replicas to 1"""
        content = self._read_file(self.STAGING_OVERLAY)
        staging_dir = os.path.dirname(os.path.join(self.REPO_DIR, self.STAGING_OVERLAY))
        all_content = content
        for f in os.listdir(staging_dir):
            fp = os.path.join(staging_dir, f)
            if os.path.isfile(fp) and f != "kustomization.yaml":
                with open(fp) as fh:
                    all_content += fh.read()
        assert "1" in all_content, "Staging overlay missing replicas: 1"

    # === Functional Checks ===

    def test_all_yaml_files_valid(self):
        """Verify all YAML files parse without errors"""
        if yaml is None:
            pytest.skip("PyYAML not installed")
        paths = [
            self.GOTK_SYNC, self.FRONTEND_DEPLOY, self.BACKEND_DEPLOY,
            self.HELM_RELEASE, self.HELM_REPO,
            self.STAGING_OVERLAY, self.PROD_OVERLAY,
        ]
        for path in paths:
            filepath = os.path.join(self.REPO_DIR, path)
            if os.path.exists(filepath):
                with open(filepath) as f:
                    try:
                        list(yaml.safe_load_all(f.read()))
                    except yaml.YAMLError as e:
                        pytest.fail(f"{path} has YAML error: {e}")

    def test_dependency_ordering(self):
        """Verify dependency ordering: database → backend → frontend"""
        content = self._read_file(self.STAGING_KUSTOMIZATION) if os.path.exists(
            os.path.join(self.REPO_DIR, self.STAGING_KUSTOMIZATION)
        ) else ""
        # Also check gotk-sync for dependency refs
        gotk = self._read_file(self.GOTK_SYNC)
        combined = content + gotk
        assert "dependsOn" in combined or "depends" in combined.lower(), \
            "Missing dependency ordering in Flux resources"

    def test_rolling_update_strategy(self):
        """Verify deployments use rolling update strategy"""
        for path in [self.FRONTEND_DEPLOY, self.BACKEND_DEPLOY]:
            content = self._read_file(path)
            assert "RollingUpdate" in content or "maxSurge" in content, \
                f"{path} missing rolling update strategy"
