"""
Test skill: gitops-workflow
Verify that the Agent implements a Multi-Tenant GitOps Reconciliation Controller
in Flux2 — TenantConfig CRD, TenantReconciler, namespace/GitRepository/Kustomization
management, and finalizer-based cleanup.
"""

import os
import re
import subprocess
import pytest


class TestGitopsWorkflow:
    REPO_DIR = "/workspace/flux2"

    # ────────────────── helpers ──────────────────

    def _read(self, rel_path):
        fpath = os.path.join(self.REPO_DIR, rel_path)
        with open(fpath, "r") as f:
            return f.read()

    def _exists(self, rel_path):
        return os.path.isfile(os.path.join(self.REPO_DIR, rel_path))

    # === File Path Checks ===

    def test_tenant_controller_exists(self):
        """tenant_controller.go must exist"""
        assert self._exists("internal/controller/tenant_controller.go")

    def test_tenantconfig_types_exists(self):
        """tenantconfig_types.go must exist"""
        assert self._exists("api/v1alpha1/tenantconfig_types.go")

    def test_tenant_controller_test_exists(self):
        """tenant_controller_test.go must exist"""
        assert self._exists("internal/controller/tenant_controller_test.go")

    def test_tenantconfig_types_test_exists(self):
        """tenantconfig_types_test.go must exist"""
        assert self._exists("api/v1alpha1/tenantconfig_types_test.go")

    # === Semantic Checks — CRD Types ===

    def test_tenantconfig_spec_struct(self):
        """TenantConfigSpec struct must be defined"""
        src = self._read("api/v1alpha1/tenantconfig_types.go")
        assert re.search(r'type\s+TenantConfigSpec\s+struct', src), (
            "TenantConfigSpec struct not found"
        )

    def test_tenantconfig_status_struct(self):
        """TenantConfigStatus struct must be defined"""
        src = self._read("api/v1alpha1/tenantconfig_types.go")
        assert re.search(r'type\s+TenantConfigStatus\s+struct', src), (
            "TenantConfigStatus struct not found"
        )

    def test_spec_fields(self):
        """TenantConfigSpec must have key fields"""
        src = self._read("api/v1alpha1/tenantconfig_types.go")
        for field in ["TenantName", "GitSource", "TargetNamespace",
                       "Path", "Interval", "Suspend"]:
            assert field in src, f"TenantConfigSpec missing field: {field}"

    def test_git_source_spec_struct(self):
        """GitSourceSpec must be defined with URL and Branch"""
        src = self._read("api/v1alpha1/tenantconfig_types.go")
        assert re.search(r'type\s+GitSourceSpec\s+struct', src), (
            "GitSourceSpec struct not found"
        )
        assert "URL" in src and "Branch" in src, (
            "GitSourceSpec missing URL or Branch"
        )

    def test_resource_quota_spec(self):
        """ResourceQuotaSpec must be defined"""
        src = self._read("api/v1alpha1/tenantconfig_types.go")
        assert "ResourceQuotaSpec" in src or "ResourceQuota" in src, (
            "ResourceQuotaSpec not found"
        )

    def test_status_ready_fields(self):
        """Status must have NamespaceReady, GitRepositoryReady, KustomizationReady"""
        src = self._read("api/v1alpha1/tenantconfig_types.go")
        for field in ["NamespaceReady", "GitRepositoryReady", "KustomizationReady"]:
            assert field in src, f"Status missing field: {field}"

    def test_status_conditions(self):
        """Status must include Conditions field"""
        src = self._read("api/v1alpha1/tenantconfig_types.go")
        assert "Conditions" in src, "Status missing Conditions field"

    # === Semantic Checks — Controller ===

    def test_reconciler_struct(self):
        """TenantReconciler struct must be defined"""
        src = self._read("internal/controller/tenant_controller.go")
        assert re.search(r'type\s+TenantReconciler\s+struct', src), (
            "TenantReconciler struct not found"
        )

    def test_reconcile_method(self):
        """Reconcile method must be defined"""
        src = self._read("internal/controller/tenant_controller.go")
        assert re.search(r'func\s+\(.*TenantReconciler\)\s+Reconcile\b', src), (
            "Reconcile method not found"
        )

    def test_namespace_creation_logic(self):
        """Controller must create target namespace"""
        src = self._read("internal/controller/tenant_controller.go")
        assert "Namespace" in src, "Namespace creation logic not found"

    def test_git_repository_creation(self):
        """Controller must create GitRepository resources"""
        src = self._read("internal/controller/tenant_controller.go")
        assert "GitRepository" in src, "GitRepository creation not found"

    def test_kustomization_creation(self):
        """Controller must create Kustomization resources"""
        src = self._read("internal/controller/tenant_controller.go")
        assert "Kustomization" in src, "Kustomization creation not found"

    def test_finalizer_usage(self):
        """Controller must use a finalizer for cleanup"""
        src = self._read("internal/controller/tenant_controller.go")
        assert "finalizer" in src.lower(), "Finalizer logic not found"

    def test_owner_reference(self):
        """Controller must set owner references on created resources"""
        src = self._read("internal/controller/tenant_controller.go")
        assert "OwnerReference" in src or "SetControllerReference" in src, (
            "Owner reference setting not found"
        )

    def test_suspend_handling(self):
        """Controller must handle spec.suspend"""
        src = self._read("internal/controller/tenant_controller.go")
        assert "Suspend" in src or "suspend" in src, (
            "Suspend handling not found"
        )

    # === Functional Checks ===

    def test_go_build(self):
        """Project must build without errors"""
        result = subprocess.run(
            ["go", "build", "./..."],
            capture_output=True, text=True, cwd=self.REPO_DIR, timeout=300,
        )
        assert result.returncode == 0, (
            f"go build failed:\n{result.stdout}\n{result.stderr}"
        )

    def test_controller_tests_pass(self):
        """Controller tests must pass"""
        result = subprocess.run(
            ["go", "test", "-v", "./internal/controller/...",
             "-run", "TestTenant"],
            capture_output=True, text=True, cwd=self.REPO_DIR, timeout=300,
        )
        assert result.returncode == 0, (
            f"Tests failed:\n{result.stdout}\n{result.stderr}"
        )

    def test_types_tests_pass(self):
        """CRD type tests must pass"""
        result = subprocess.run(
            ["go", "test", "-v", "./api/v1alpha1/...",
             "-run", "TestTenant"],
            capture_output=True, text=True, cwd=self.REPO_DIR, timeout=120,
        )
        assert result.returncode == 0, (
            f"Tests failed:\n{result.stdout}\n{result.stderr}"
        )
