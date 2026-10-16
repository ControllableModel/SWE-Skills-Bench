"""
Test skill: k8s-manifest-generator
Verify that the Agent creates multi-environment Kustomize overlays
with base manifests, staging/production patches, common labels,
and environment-specific customization.
"""

import os
import re
import subprocess
import pytest


class TestK8sManifestGenerator:
    REPO_DIR = "/workspace/kustomize"

    BASE = "examples/multi-env"

    # === File Path Checks ===

    def test_base_deployment_exists(self):
        """Verify base/deployment.yaml exists"""
        path = os.path.join(self.REPO_DIR, self.BASE, "base/deployment.yaml")
        assert os.path.exists(path), f"base/deployment.yaml not found"

    def test_base_service_exists(self):
        """Verify base/service.yaml exists"""
        path = os.path.join(self.REPO_DIR, self.BASE, "base/service.yaml")
        assert os.path.exists(path), f"base/service.yaml not found"

    def test_base_configmap_exists(self):
        """Verify base/configmap.yaml exists"""
        path = os.path.join(self.REPO_DIR, self.BASE, "base/configmap.yaml")
        assert os.path.exists(path), f"base/configmap.yaml not found"

    def test_base_kustomization_exists(self):
        """Verify base/kustomization.yaml exists"""
        path = os.path.join(
            self.REPO_DIR, self.BASE, "base/kustomization.yaml"
        )
        assert os.path.exists(path), f"base/kustomization.yaml not found"

    def test_staging_overlay_exists(self):
        """Verify staging overlay kustomization.yaml exists"""
        path = os.path.join(
            self.REPO_DIR, self.BASE,
            "overlays/staging/kustomization.yaml",
        )
        assert os.path.exists(path), f"staging overlay not found"

    def test_production_overlay_exists(self):
        """Verify production overlay kustomization.yaml exists"""
        path = os.path.join(
            self.REPO_DIR, self.BASE,
            "overlays/production/kustomization.yaml",
        )
        assert os.path.exists(path), f"production overlay not found"

    # === Semantic Checks ===

    def test_base_kustomization_lists_resources(self):
        """Verify base kustomization.yaml lists all base resources"""
        path = os.path.join(
            self.REPO_DIR, self.BASE, "base/kustomization.yaml"
        )
        with open(path) as f:
            content = f.read()

        assert "resources" in content, (
            "base kustomization.yaml should list resources"
        )
        resource_indicators = ["deployment", "service", "configmap"]
        found = [r for r in resource_indicators if r in content.lower()]
        assert len(found) >= 2, (
            f"Should reference base resources. Found: {found}"
        )

    def test_overlays_reference_base(self):
        """Verify overlays reference the base"""
        for env in ["staging", "production"]:
            path = os.path.join(
                self.REPO_DIR, self.BASE,
                f"overlays/{env}/kustomization.yaml",
            )
            with open(path) as f:
                content = f.read()
            assert "base" in content.lower() or "resources" in content, (
                f"{env} overlay should reference the base"
            )

    def test_overlays_customize_replicas(self):
        """Verify overlays customize replica counts"""
        replicas = {}
        for env in ["staging", "production"]:
            path = os.path.join(
                self.REPO_DIR, self.BASE,
                f"overlays/{env}/kustomization.yaml",
            )
            with open(path) as f:
                content = f.read()
            match = re.search(r"replicas?\s*[:=]\s*(\d+)", content)
            if match:
                replicas[env] = int(match.group(1))

        # Also check for separate patch files
        if len(replicas) < 2:
            for env in ["staging", "production"]:
                overlay_dir = os.path.join(
                    self.REPO_DIR, self.BASE, f"overlays/{env}"
                )
                if os.path.isdir(overlay_dir):
                    for fname in os.listdir(overlay_dir):
                        if fname.endswith((".yaml", ".yml")) and \
                                fname != "kustomization.yaml":
                            fpath = os.path.join(overlay_dir, fname)
                            with open(fpath) as f:
                                fc = f.read()
                            match = re.search(r"replicas?\s*[:=]\s*(\d+)", fc)
                            if match:
                                replicas[env] = int(match.group(1))

        assert len(replicas) >= 1, (
            "At least one overlay should customize replica counts"
        )

    def test_overlays_set_namespace(self):
        """Verify overlays assign namespace"""
        for env in ["staging", "production"]:
            combined = ""
            overlay_dir = os.path.join(
                self.REPO_DIR, self.BASE, f"overlays/{env}"
            )
            if os.path.isdir(overlay_dir):
                for fname in os.listdir(overlay_dir):
                    if fname.endswith((".yaml", ".yml")):
                        with open(os.path.join(overlay_dir, fname)) as f:
                            combined += f.read()
            if "namespace" in combined.lower():
                return
        pytest.fail("At least one overlay should set a namespace")

    def test_common_labels(self):
        """Verify common labels are applied via Kustomize"""
        combined = ""
        for root, _, files in os.walk(
            os.path.join(self.REPO_DIR, self.BASE)
        ):
            for fname in files:
                if fname.endswith((".yaml", ".yml")):
                    with open(os.path.join(root, fname)) as f:
                        combined += f.read()

        label_indicators = [
            "commonLabels", "labels", "app", "version",
        ]
        found = [ind for ind in label_indicators if ind in combined]
        assert len(found) >= 2, (
            f"Should apply common labels. Found: {found}"
        )

    # === Functional Checks ===

    def test_yaml_files_valid(self):
        """Verify all YAML files are syntactically valid"""
        import yaml

        yaml_files = []
        base_dir = os.path.join(self.REPO_DIR, self.BASE)
        for root, dirs, files in os.walk(base_dir):
            for fname in files:
                if fname.endswith((".yaml", ".yml")):
                    yaml_files.append(os.path.join(root, fname))

        assert len(yaml_files) >= 6, (
            f"Should have at least 6 YAML files. Found: {len(yaml_files)}"
        )
        for yf in yaml_files:
            with open(yf) as f:
                try:
                    list(yaml.safe_load_all(f.read()))
                except yaml.YAMLError as e:
                    pytest.fail(f"Invalid YAML in {yf}: {e}")

    def test_base_deployment_has_container_spec(self):
        """Verify base deployment has a container specification"""
        path = os.path.join(self.REPO_DIR, self.BASE, "base/deployment.yaml")
        with open(path) as f:
            content = f.read()

        assert "containers" in content, (
            "Base deployment should have containers spec"
        )
        assert "image" in content, (
            "Base deployment should reference a container image"
        )

    def test_overlays_differ(self):
        """Verify staging and production overlays produce different configs"""
        staging_path = os.path.join(
            self.REPO_DIR, self.BASE,
            "overlays/staging/kustomization.yaml",
        )
        prod_path = os.path.join(
            self.REPO_DIR, self.BASE,
            "overlays/production/kustomization.yaml",
        )
        with open(staging_path) as f:
            staging = f.read()
        with open(prod_path) as f:
            production = f.read()

        assert staging != production, (
            "Staging and production overlays should differ"
        )
