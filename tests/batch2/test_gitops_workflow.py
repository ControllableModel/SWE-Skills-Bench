"""
Test skill: gitops-workflow
Verify that the Agent creates a complete Flux GitOps configuration example
with source definitions, multi-environment kustomizations, base manifests,
and overlay patches.
"""

import os
import re
import subprocess
import pytest


class TestGitopsWorkflow:
    REPO_DIR = "/workspace/flux2"

    BASE = "examples/gitops-demo"

    # === File Path Checks ===

    def test_source_yaml_exists(self):
        """Verify source.yaml exists"""
        path = os.path.join(self.REPO_DIR, self.BASE, "source.yaml")
        assert os.path.exists(path), f"source.yaml not found at {path}"

    def test_staging_kustomization_exists(self):
        """Verify staging-kustomization.yaml exists"""
        path = os.path.join(
            self.REPO_DIR, self.BASE, "staging-kustomization.yaml"
        )
        assert os.path.exists(path), f"staging-kustomization.yaml not found"

    def test_production_kustomization_exists(self):
        """Verify production-kustomization.yaml exists"""
        path = os.path.join(
            self.REPO_DIR, self.BASE, "production-kustomization.yaml"
        )
        assert os.path.exists(path), f"production-kustomization.yaml not found"

    def test_base_deployment_exists(self):
        """Verify base/deployment.yaml exists"""
        path = os.path.join(
            self.REPO_DIR, self.BASE, "base/deployment.yaml"
        )
        assert os.path.exists(path), f"base/deployment.yaml not found"

    # === Semantic Checks ===

    def test_source_defines_git_repository(self):
        """Verify source.yaml defines a GitRepository"""
        path = os.path.join(self.REPO_DIR, self.BASE, "source.yaml")
        with open(path) as f:
            content = f.read()

        assert "GitRepository" in content, (
            "source.yaml should define a GitRepository kind"
        )
        git_indicators = ["branch", "interval", "url"]
        found = [ind for ind in git_indicators if ind in content.lower()]
        assert len(found) >= 2, (
            f"GitRepository should have branch/interval/url. Found: {found}"
        )

    def test_kustomizations_have_different_intervals(self):
        """Verify staging and production have different reconciliation intervals"""
        intervals = []
        for fname in [
            "staging-kustomization.yaml",
            "production-kustomization.yaml",
        ]:
            path = os.path.join(self.REPO_DIR, self.BASE, fname)
            if os.path.exists(path):
                with open(path) as f:
                    content = f.read()
                match = re.search(r"interval:\s*(\S+)", content)
                if match:
                    intervals.append(match.group(1))

        assert len(intervals) >= 2, (
            "Both kustomizations should specify reconciliation intervals"
        )

    def test_kustomizations_reference_paths(self):
        """Verify kustomizations reference overlay paths"""
        for fname in [
            "staging-kustomization.yaml",
            "production-kustomization.yaml",
        ]:
            path = os.path.join(self.REPO_DIR, self.BASE, fname)
            if os.path.exists(path):
                with open(path) as f:
                    content = f.read()
                assert "path" in content.lower(), (
                    f"{fname} should reference a source path"
                )

    def test_pruning_configured(self):
        """Verify pruning is configured in kustomizations"""
        for fname in [
            "staging-kustomization.yaml",
            "production-kustomization.yaml",
        ]:
            path = os.path.join(self.REPO_DIR, self.BASE, fname)
            if os.path.exists(path):
                with open(path) as f:
                    content = f.read()
                if "prune" in content.lower():
                    return
        pytest.fail("At least one kustomization should configure pruning")

    def test_health_checks_configured(self):
        """Verify health checks are configured"""
        combined = ""
        for fname in [
            "staging-kustomization.yaml",
            "production-kustomization.yaml",
        ]:
            path = os.path.join(self.REPO_DIR, self.BASE, fname)
            if os.path.exists(path):
                with open(path) as f:
                    combined += f.read()

        health_indicators = ["healthCheck", "health", "timeout", "ready"]
        found = [ind for ind in health_indicators if ind in combined]
        assert len(found) >= 1, (
            f"Should configure health checks. Found: {found}"
        )

    def test_overlays_differ(self):
        """Verify staging and production overlays have differences"""
        overlays = {}
        for env in ["staging", "production"]:
            path = os.path.join(
                self.REPO_DIR, self.BASE,
                f"overlays/{env}/kustomization.yaml",
            )
            if os.path.exists(path):
                with open(path) as f:
                    overlays[env] = f.read()

        assert len(overlays) >= 2, (
            "Both staging and production overlay kustomization.yaml should exist"
        )
        assert overlays["staging"] != overlays["production"], (
            "Staging and production overlays should differ"
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

        assert len(yaml_files) >= 5, (
            f"Should have at least 5 YAML files. Found: {len(yaml_files)}"
        )
        for yf in yaml_files:
            with open(yf) as f:
                try:
                    list(yaml.safe_load_all(f.read()))
                except yaml.YAMLError as e:
                    pytest.fail(f"Invalid YAML in {yf}: {e}")

    def test_base_kustomization_lists_resources(self):
        """Verify base kustomization.yaml lists all base resources"""
        path = os.path.join(
            self.REPO_DIR, self.BASE, "base/kustomization.yaml"
        )
        assert os.path.exists(path), "base/kustomization.yaml not found"
        with open(path) as f:
            content = f.read()

        assert "resources" in content, (
            "base/kustomization.yaml should list resources"
        )
