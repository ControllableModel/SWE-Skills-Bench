"""
Test skill: gitops-workflow
Verify that the Agent sets up a GitOps workflow with ArgoCD for
multi-environment Kubernetes deployments using App of Apps pattern,
Kustomize overlays, and Slack notifications.
"""

import os
import re
import json
import subprocess
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


class TestGitopsWorkflow:
    REPO_DIR = "/workspace/flux2"

    # === File Path Checks ===

    def test_appproject_exists(self):
        assert os.path.exists(
            os.path.join(self.REPO_DIR, "argocd/projects/platform.yaml")
        )

    def test_root_app_exists(self):
        assert os.path.exists(
            os.path.join(self.REPO_DIR, "argocd/applications/root-app.yaml")
        )

    def test_staging_apps_exist(self):
        for svc in ("frontend", "backend", "worker"):
            path = os.path.join(
                self.REPO_DIR, f"argocd/applications/staging/{svc}.yaml"
            )
            assert os.path.exists(path), f"Staging {svc} app not found"

    def test_production_apps_exist(self):
        for svc in ("frontend", "backend", "worker"):
            path = os.path.join(
                self.REPO_DIR, f"argocd/applications/production/{svc}.yaml"
            )
            assert os.path.exists(path), f"Production {svc} app not found"

    def test_base_manifests_exist(self):
        for svc in ("frontend", "backend"):
            for res in ("deployment.yaml", "service.yaml", "kustomization.yaml"):
                path = os.path.join(self.REPO_DIR, f"apps/base/{svc}/{res}")
                assert os.path.exists(path), f"Base {svc}/{res} not found"

    def test_overlay_dirs_exist(self):
        for env in ("staging", "production"):
            for svc in ("frontend", "backend"):
                path = os.path.join(
                    self.REPO_DIR,
                    f"apps/overlays/{env}/{svc}/kustomization.yaml",
                )
                assert os.path.exists(path), f"Overlay {env}/{svc} not found"

    def test_notifications_config_exists(self):
        assert os.path.exists(
            os.path.join(self.REPO_DIR, "argocd/notifications/config.yaml")
        )

    # === Semantic Checks ===

    def test_appproject_restricts_destinations(self):
        """AppProject restricts destinations to staging and production namespaces"""
        docs = load_yaml(
            os.path.join(self.REPO_DIR, "argocd/projects/platform.yaml")
        )
        doc = docs[0]
        spec = doc.get("spec", {})
        destinations = spec.get("destinations", [])
        namespaces = {d.get("namespace") for d in destinations}
        assert "staging" in namespaces, "Missing staging destination"
        assert "production" in namespaces, "Missing production destination"

    def test_root_app_is_app_of_apps(self):
        """Root app uses App of Apps pattern pointing to argocd/applications/"""
        docs = load_yaml(
            os.path.join(self.REPO_DIR, "argocd/applications/root-app.yaml")
        )
        doc = docs[0]
        src_path = doc.get("spec", {}).get("source", {}).get("path", "")
        assert "argocd/applications" in src_path, (
            f"Root app should point to argocd/applications, got: {src_path}"
        )

    def test_staging_apps_have_automated_sync(self):
        """Staging apps should have automated sync with prune and selfHeal"""
        for svc in ("frontend", "backend", "worker"):
            path = os.path.join(
                self.REPO_DIR, f"argocd/applications/staging/{svc}.yaml"
            )
            docs = load_yaml(path)
            sync = docs[0].get("spec", {}).get("syncPolicy", {})
            automated = sync.get("automated", {})
            assert automated, f"Staging {svc} should have automated sync"
            assert automated.get("prune") is True, f"Staging {svc} needs prune"
            assert automated.get("selfHeal") is True, f"Staging {svc} needs selfHeal"

    def test_production_apps_no_automated_sync(self):
        """Production apps should NOT have automated sync"""
        for svc in ("frontend", "backend", "worker"):
            path = os.path.join(
                self.REPO_DIR, f"argocd/applications/production/{svc}.yaml"
            )
            docs = load_yaml(path)
            sync = docs[0].get("spec", {}).get("syncPolicy", {})
            automated = sync.get("automated")
            assert not automated, (
                f"Production {svc} should not have automated sync"
            )

    def test_production_has_sync_windows(self):
        """Production apps should restrict syncs to business hours"""
        path = os.path.join(
            self.REPO_DIR, "argocd/applications/production/frontend.yaml"
        )
        with open(path) as f:
            content = f.read()
        assert re.search(r"syncWindows|sync.?window", content, re.IGNORECASE), (
            "Production app should have sync windows"
        )

    def test_staging_overlays_have_two_replicas(self):
        """Staging overlays set 2 replicas"""
        path = os.path.join(
            self.REPO_DIR,
            "apps/overlays/staging/frontend/kustomization.yaml",
        )
        with open(path) as f:
            content = f.read()
        assert "2" in content, "Staging should specify 2 replicas"

    def test_production_overlays_have_five_replicas(self):
        """Production overlays set 5 replicas"""
        path = os.path.join(
            self.REPO_DIR,
            "apps/overlays/production/frontend/kustomization.yaml",
        )
        with open(path) as f:
            content = f.read()
        assert "5" in content, "Production should specify 5 replicas"

    def test_production_overlays_have_pdb(self):
        """Production overlays should include PodDisruptionBudget"""
        path = os.path.join(
            self.REPO_DIR,
            "apps/overlays/production/frontend/kustomization.yaml",
        )
        with open(path) as f:
            content = f.read()
        content_lower = content.lower()
        assert "poddisruptionbudget" in content_lower or "pdb" in content_lower or "minavailable" in content_lower, (
            "Production overlay should include PodDisruptionBudget"
        )

    def test_notifications_has_slack_templates(self):
        """Notifications config has Slack templates for sync succeeded/failed"""
        path = os.path.join(
            self.REPO_DIR, "argocd/notifications/config.yaml"
        )
        with open(path) as f:
            content = f.read()
        assert "sync-succeeded" in content or "sync_succeeded" in content, (
            "Missing sync succeeded template"
        )
        assert "sync-failed" in content or "sync_failed" in content, (
            "Missing sync failed template"
        )
        assert "health-degraded" in content or "health_degraded" in content, (
            "Missing health degraded template"
        )

    def test_base_frontend_deployment_has_probes(self):
        """Base frontend deployment should have liveness and readiness probes"""
        path = os.path.join(
            self.REPO_DIR, "apps/base/frontend/deployment.yaml"
        )
        with open(path) as f:
            content = f.read()
        assert "livenessProbe" in content, "Missing livenessProbe"
        assert "readinessProbe" in content, "Missing readinessProbe"
        assert "/healthz" in content or "/health" in content, "Missing health path"

    # === Functional Checks ===

    def test_all_yaml_files_parse(self):
        """Verify all YAML files parse without errors"""
        if yaml is None:
            pytest.skip("PyYAML not available")
        dirs_to_scan = ["argocd", "apps"]
        for d in dirs_to_scan:
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
                            pytest.fail(f"{filepath} has YAML error: {e}")

    def test_all_apps_reference_platform_project(self):
        """All ArgoCD apps should reference the 'platform' project"""
        for env in ("staging", "production"):
            for svc in ("frontend", "backend", "worker"):
                path = os.path.join(
                    self.REPO_DIR, f"argocd/applications/{env}/{svc}.yaml"
                )
                docs = load_yaml(path)
                proj = docs[0].get("spec", {}).get("project", "")
                assert proj == "platform", (
                    f"{env}/{svc} should use project 'platform', got '{proj}'"
                )

    def test_staging_apps_target_staging_namespace(self):
        """All staging apps should target the staging namespace"""
        for svc in ("frontend", "backend", "worker"):
            path = os.path.join(
                self.REPO_DIR, f"argocd/applications/staging/{svc}.yaml"
            )
            docs = load_yaml(path)
            ns = docs[0].get("spec", {}).get("destination", {}).get("namespace", "")
            assert ns == "staging", f"Staging {svc} targets '{ns}' instead of 'staging'"
