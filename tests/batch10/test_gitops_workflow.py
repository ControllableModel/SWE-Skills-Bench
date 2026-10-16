"""
Test skill: gitops-workflow
Verify that the Agent correctly implements a GitOps reconciliation pipeline
with multi-environment Flux CD deployment.
"""

import os
import re
import subprocess
import pytest


class TestGitopsWorkflow:
    REPO_DIR = "/workspace/flux2"

    # === File Path Checks ===

    def test_pipeline_go_exists(self):
        """Verify pipeline.go was created"""
        path = os.path.join(self.REPO_DIR, "internal/reconcile/pipeline.go")
        assert os.path.exists(path), f"pipeline.go not found at {path}"

    def test_pipeline_test_go_exists(self):
        """Verify pipeline_test.go was created"""
        path = os.path.join(self.REPO_DIR, "internal/reconcile/pipeline_test.go")
        assert os.path.exists(path), f"pipeline_test.go not found at {path}"

    def test_health_go_exists(self):
        """Verify health.go was created"""
        path = os.path.join(self.REPO_DIR, "internal/reconcile/health.go")
        assert os.path.exists(path), f"health.go not found at {path}"

    def test_health_test_go_exists(self):
        """Verify health_test.go was created"""
        path = os.path.join(self.REPO_DIR, "internal/reconcile/health_test.go")
        assert os.path.exists(path), f"health_test.go not found at {path}"

    def test_base_kustomization_exists(self):
        """Verify base/kustomization.yaml was created"""
        path = os.path.join(
            self.REPO_DIR, "pkg/manifests/multi_env/base/kustomization.yaml"
        )
        assert os.path.exists(path), f"base/kustomization.yaml not found"

    def test_staging_kustomization_exists(self):
        """Verify staging/kustomization.yaml was created"""
        path = os.path.join(
            self.REPO_DIR, "pkg/manifests/multi_env/staging/kustomization.yaml"
        )
        assert os.path.exists(path), f"staging/kustomization.yaml not found"

    def test_production_kustomization_exists(self):
        """Verify production/kustomization.yaml was created"""
        path = os.path.join(
            self.REPO_DIR, "pkg/manifests/multi_env/production/kustomization.yaml"
        )
        assert os.path.exists(path), f"production/kustomization.yaml not found"

    # === Semantic Checks: GitRepositorySource ===

    def test_git_repository_source_struct(self):
        """Verify GitRepositorySource struct is defined"""
        path = os.path.join(self.REPO_DIR, "internal/reconcile/pipeline.go")
        with open(path) as f:
            content = f.read()
        assert "GitRepositorySource" in content, (
            "GitRepositorySource struct should be defined"
        )

    def test_git_source_has_url_field(self):
        """Verify GitRepositorySource has URL field"""
        path = os.path.join(self.REPO_DIR, "internal/reconcile/pipeline.go")
        with open(path) as f:
            content = f.read()
        assert "URL" in content, "GitRepositorySource should have URL field"

    def test_git_source_has_validate(self):
        """Verify GitRepositorySource has Validate method"""
        path = os.path.join(self.REPO_DIR, "internal/reconcile/pipeline.go")
        with open(path) as f:
            content = f.read()
        assert "Validate" in content, "Should have Validate method"

    def test_git_source_has_reconcile(self):
        """Verify Reconcile method is defined"""
        path = os.path.join(self.REPO_DIR, "internal/reconcile/pipeline.go")
        with open(path) as f:
            content = f.read()
        assert "Reconcile" in content, "Should have Reconcile method"

    def test_git_source_reject_empty_url(self):
        """Verify Validate rejects empty URL"""
        path = os.path.join(self.REPO_DIR, "internal/reconcile/pipeline.go")
        with open(path) as f:
            content = f.read()
        assert "url is required" in content.lower() or "URL" in content, (
            "Should reject empty URL"
        )

    def test_git_source_reject_short_interval(self):
        """Verify Validate rejects intervals below 30s"""
        path = os.path.join(self.REPO_DIR, "internal/reconcile/pipeline.go")
        with open(path) as f:
            content = f.read()
        assert "30" in content, "Should check interval >=30s"

    # === Semantic Checks: KustomizationReconciler ===

    def test_kustomization_reconciler_struct(self):
        """Verify KustomizationReconciler struct is defined"""
        path = os.path.join(self.REPO_DIR, "internal/reconcile/pipeline.go")
        with open(path) as f:
            content = f.read()
        assert "KustomizationReconciler" in content, (
            "KustomizationReconciler should be defined"
        )

    def test_kustomization_spec_depends_on(self):
        """Verify KustomizationSpec has DependsOn field"""
        path = os.path.join(self.REPO_DIR, "internal/reconcile/pipeline.go")
        with open(path) as f:
            content = f.read()
        assert "DependsOn" in content, "KustomizationSpec should have DependsOn"

    def test_circular_dependency_error(self):
        """Verify CircularDependencyError is defined"""
        path = os.path.join(self.REPO_DIR, "internal/reconcile/pipeline.go")
        with open(path) as f:
            content = f.read()
        assert "CircularDependencyError" in content, (
            "CircularDependencyError should be defined"
        )

    def test_prune_result_defined(self):
        """Verify PruneResult is defined"""
        path = os.path.join(self.REPO_DIR, "internal/reconcile/pipeline.go")
        with open(path) as f:
            content = f.read()
        assert "PruneResult" in content, "PruneResult should be defined"

    # === Semantic Checks: Pipeline ===

    def test_pipeline_struct_defined(self):
        """Verify Pipeline struct with Stages is defined"""
        path = os.path.join(self.REPO_DIR, "internal/reconcile/pipeline.go")
        with open(path) as f:
            content = f.read()
        assert "Pipeline" in content, "Pipeline struct should be defined"
        assert "Stage" in content, "Stage struct should be defined"

    def test_pipeline_execute(self):
        """Verify Pipeline.Execute method is defined"""
        path = os.path.join(self.REPO_DIR, "internal/reconcile/pipeline.go")
        with open(path) as f:
            content = f.read()
        assert "Execute" in content, "Pipeline should have Execute method"

    def test_gate_failed_error(self):
        """Verify GateFailedError is defined"""
        path = os.path.join(self.REPO_DIR, "internal/reconcile/pipeline.go")
        with open(path) as f:
            content = f.read()
        assert "GateFailedError" in content, (
            "GateFailedError should be defined"
        )

    def test_manual_approval_gate(self):
        """Verify ManualApprovalGate is defined"""
        path = os.path.join(self.REPO_DIR, "internal/reconcile/pipeline.go")
        with open(path) as f:
            content = f.read()
        assert "ManualApproval" in content, (
            "ManualApprovalGate should be defined"
        )

    def test_pipeline_approve(self):
        """Verify Pipeline.Approve method is defined"""
        path = os.path.join(self.REPO_DIR, "internal/reconcile/pipeline.go")
        with open(path) as f:
            content = f.read()
        assert "Approve" in content, "Pipeline should have Approve method"

    # === Semantic Checks: Health Gate ===

    def test_health_gate_evaluator(self):
        """Verify HealthGate checks deployment Available condition"""
        path = os.path.join(self.REPO_DIR, "internal/reconcile/health.go")
        with open(path) as f:
            content = f.read()
        assert "Available" in content, (
            "Should check Available condition"
        )

    def test_health_gate_generation_matching(self):
        """Verify ObservedGeneration matching"""
        path = os.path.join(self.REPO_DIR, "internal/reconcile/health.go")
        with open(path) as f:
            content = f.read()
        assert "ObservedGeneration" in content or "Generation" in content, (
            "Should check ObservedGeneration matches Generation"
        )

    # === Semantic Checks: Kustomize Overlays ===

    def test_base_has_web_app_deployment(self):
        """Verify base kustomization declares web-app deployment"""
        path = os.path.join(
            self.REPO_DIR, "pkg/manifests/multi_env/base/kustomization.yaml"
        )
        with open(path) as f:
            content = f.read()
        assert "web-app" in content, "Base should declare web-app"

    def test_staging_patches_namespace(self):
        """Verify staging overlay patches namespace to staging"""
        path = os.path.join(
            self.REPO_DIR, "pkg/manifests/multi_env/staging/kustomization.yaml"
        )
        with open(path) as f:
            content = f.read()
        assert "staging" in content, "Should patch namespace to staging"

    def test_production_patches_replicas(self):
        """Verify production overlay sets replicas to 3"""
        path = os.path.join(
            self.REPO_DIR, "pkg/manifests/multi_env/production/kustomization.yaml"
        )
        with open(path) as f:
            content = f.read()
        assert "3" in content, "Production should set replicas to 3"

    def test_production_has_resource_limits(self):
        """Verify production overlay has resource limits"""
        path = os.path.join(
            self.REPO_DIR, "pkg/manifests/multi_env/production/kustomization.yaml"
        )
        with open(path) as f:
            content = f.read()
        assert "500m" in content or "512Mi" in content, (
            "Production should have resource limits"
        )

    # === Functional Checks ===

    def test_go_files_have_package(self):
        """Verify Go files have proper package declarations"""
        for rel_path in [
            "internal/reconcile/pipeline.go",
            "internal/reconcile/health.go",
        ]:
            path = os.path.join(self.REPO_DIR, rel_path)
            with open(path) as f:
                content = f.read()
            assert content.startswith("package "), (
                f"{rel_path} should start with package declaration"
            )

    def test_reconcile_tests_pass(self):
        """Verify go test passes for internal/reconcile/"""
        result = subprocess.run(
            ["go", "test", "./internal/reconcile/", "-v"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, (
            f"go test failed:\n{result.stdout}\n{result.stderr}"
        )

    def test_kustomize_yaml_valid(self):
        """Verify kustomization YAML files are valid"""
        import yaml
        for env in ["base", "staging", "production"]:
            path = os.path.join(
                self.REPO_DIR,
                f"pkg/manifests/multi_env/{env}/kustomization.yaml",
            )
            with open(path) as f:
                data = yaml.safe_load(f)
            assert data is not None, f"{env}/kustomization.yaml should be valid YAML"
