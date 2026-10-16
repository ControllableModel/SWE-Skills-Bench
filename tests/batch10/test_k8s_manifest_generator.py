"""
Test skill: k8s-manifest-generator
Verify that the Agent correctly implements a Kubernetes manifest generator
with validation and security context enforcement for Kustomize.
"""

import os
import re
import subprocess
import pytest


class TestK8sManifestGenerator:
    REPO_DIR = "/workspace/kustomize"

    # === File Path Checks ===

    def test_generator_go_exists(self):
        """Verify generator.go was created"""
        path = os.path.join(self.REPO_DIR, "api/manifest/generator.go")
        assert os.path.exists(path), f"generator.go not found at {path}"

    def test_generator_test_go_exists(self):
        """Verify generator_test.go was created"""
        path = os.path.join(self.REPO_DIR, "api/manifest/generator_test.go")
        assert os.path.exists(path), f"generator_test.go not found at {path}"

    def test_security_go_exists(self):
        """Verify security.go was created"""
        path = os.path.join(self.REPO_DIR, "api/manifest/security.go")
        assert os.path.exists(path), f"security.go not found at {path}"

    def test_security_test_go_exists(self):
        """Verify security_test.go was created"""
        path = os.path.join(self.REPO_DIR, "api/manifest/security_test.go")
        assert os.path.exists(path), f"security_test.go not found at {path}"

    def test_labels_go_exists(self):
        """Verify labels.go was created"""
        path = os.path.join(self.REPO_DIR, "api/manifest/labels.go")
        assert os.path.exists(path), f"labels.go not found at {path}"

    def test_labels_test_go_exists(self):
        """Verify labels_test.go was created"""
        path = os.path.join(self.REPO_DIR, "api/manifest/labels_test.go")
        assert os.path.exists(path), f"labels_test.go not found at {path}"

    # === Semantic Checks: DeploymentBuilder ===

    def test_new_deployment_function(self):
        """Verify NewDeployment function is defined"""
        path = os.path.join(self.REPO_DIR, "api/manifest/generator.go")
        with open(path) as f:
            content = f.read()
        assert "NewDeployment" in content, "NewDeployment function should be defined"

    def test_deployment_with_replicas(self):
        """Verify WithReplicas method is defined"""
        path = os.path.join(self.REPO_DIR, "api/manifest/generator.go")
        with open(path) as f:
            content = f.read()
        assert "WithReplicas" in content, "Should have WithReplicas method"

    def test_deployment_with_port(self):
        """Verify WithPort method validates port range 1-65535"""
        path = os.path.join(self.REPO_DIR, "api/manifest/generator.go")
        with open(path) as f:
            content = f.read()
        assert "WithPort" in content, "Should have WithPort method"
        assert "65535" in content, "Should validate port range up to 65535"

    def test_deployment_with_resources(self):
        """Verify WithResources method with ResourceSpec"""
        path = os.path.join(self.REPO_DIR, "api/manifest/generator.go")
        with open(path) as f:
            content = f.read()
        assert "WithResources" in content, "Should have WithResources method"
        assert "ResourceSpec" in content, "Should have ResourceSpec struct"

    def test_deployment_with_probe(self):
        """Verify WithProbe method for liveness/readiness"""
        path = os.path.join(self.REPO_DIR, "api/manifest/generator.go")
        with open(path) as f:
            content = f.read()
        assert "WithProbe" in content, "Should have WithProbe method"
        assert "liveness" in content or "readiness" in content, (
            "Should support liveness and readiness probes"
        )

    def test_deployment_rejects_latest_tag(self):
        """Verify Build rejects :latest image tag"""
        path = os.path.join(self.REPO_DIR, "api/manifest/generator.go")
        with open(path) as f:
            content = f.read()
        assert "latest" in content, "Should reject :latest image tag"

    def test_deployment_build_returns_rnode(self):
        """Verify Build returns *yaml.RNode"""
        path = os.path.join(self.REPO_DIR, "api/manifest/generator.go")
        with open(path) as f:
            content = f.read()
        assert "Build" in content, "Should have Build method"

    # === Semantic Checks: ServiceBuilder ===

    def test_new_service_function(self):
        """Verify NewService function is defined"""
        path = os.path.join(self.REPO_DIR, "api/manifest/generator.go")
        with open(path) as f:
            content = f.read()
        assert "NewService" in content, "NewService function should be defined"

    def test_service_type_validation(self):
        """Verify only ClusterIP, NodePort, LoadBalancer allowed"""
        path = os.path.join(self.REPO_DIR, "api/manifest/generator.go")
        with open(path) as f:
            content = f.read()
        for svc_type in ["ClusterIP", "NodePort", "LoadBalancer"]:
            assert svc_type in content, (
                f"Should support {svc_type} service type"
            )

    # === Semantic Checks: ConfigMapBuilder ===

    def test_new_config_map_function(self):
        """Verify NewConfigMap function is defined"""
        path = os.path.join(self.REPO_DIR, "api/manifest/generator.go")
        with open(path) as f:
            content = f.read()
        assert "NewConfigMap" in content, "NewConfigMap function should be defined"

    def test_config_map_rejects_path_traversal(self):
        """Verify ConfigMap rejects keys with .. or /"""
        path = os.path.join(self.REPO_DIR, "api/manifest/generator.go")
        with open(path) as f:
            content = f.read()
        assert ".." in content, "Should reject keys containing .."

    # === Semantic Checks: SecretBuilder ===

    def test_new_secret_function(self):
        """Verify NewSecret function is defined"""
        path = os.path.join(self.REPO_DIR, "api/manifest/generator.go")
        with open(path) as f:
            content = f.read()
        assert "NewSecret" in content, "NewSecret function should be defined"

    def test_secret_tls_key_requirement(self):
        """Verify TLS secrets require tls.crt and tls.key"""
        path = os.path.join(self.REPO_DIR, "api/manifest/generator.go")
        with open(path) as f:
            content = f.read()
        assert "tls.crt" in content, "Should require tls.crt for TLS secrets"
        assert "tls.key" in content, "Should require tls.key for TLS secrets"

    # === Semantic Checks: Security Context ===

    def test_security_context_struct(self):
        """Verify SecurityContext struct is defined"""
        path = os.path.join(self.REPO_DIR, "api/manifest/security.go")
        with open(path) as f:
            content = f.read()
        assert "SecurityContext" in content, (
            "SecurityContext struct should be defined"
        )

    def test_enforce_security_policy(self):
        """Verify EnforceSecurityPolicy function is defined"""
        path = os.path.join(self.REPO_DIR, "api/manifest/security.go")
        with open(path) as f:
            content = f.read()
        assert "EnforceSecurityPolicy" in content, (
            "EnforceSecurityPolicy function should be defined"
        )

    def test_security_violation_struct(self):
        """Verify SecurityViolation struct is defined"""
        path = os.path.join(self.REPO_DIR, "api/manifest/security.go")
        with open(path) as f:
            content = f.read()
        assert "SecurityViolation" in content, (
            "SecurityViolation struct should be defined"
        )

    def test_apply_security_defaults(self):
        """Verify ApplySecurityDefaults function is defined"""
        path = os.path.join(self.REPO_DIR, "api/manifest/security.go")
        with open(path) as f:
            content = f.read()
        assert "ApplySecurityDefaults" in content, (
            "ApplySecurityDefaults function should be defined"
        )

    def test_security_checks_run_as_non_root(self):
        """Verify RunAsNonRoot check"""
        path = os.path.join(self.REPO_DIR, "api/manifest/security.go")
        with open(path) as f:
            content = f.read()
        assert "RunAsNonRoot" in content, "Should check RunAsNonRoot"

    def test_security_checks_privilege_escalation(self):
        """Verify AllowPrivilegeEscalation check"""
        path = os.path.join(self.REPO_DIR, "api/manifest/security.go")
        with open(path) as f:
            content = f.read()
        assert "AllowPrivilegeEscalation" in content, (
            "Should check AllowPrivilegeEscalation"
        )

    def test_security_drop_all_caps(self):
        """Verify DROP ALL capability check"""
        path = os.path.join(self.REPO_DIR, "api/manifest/security.go")
        with open(path) as f:
            content = f.read()
        assert "ALL" in content, "Should check for DROP ALL capabilities"

    # === Semantic Checks: Labels ===

    def test_standard_labels_function(self):
        """Verify StandardLabels function is defined"""
        path = os.path.join(self.REPO_DIR, "api/manifest/labels.go")
        with open(path) as f:
            content = f.read()
        assert "StandardLabels" in content, (
            "StandardLabels function should be defined"
        )

    def test_k8s_label_keys(self):
        """Verify Kubernetes standard label keys"""
        path = os.path.join(self.REPO_DIR, "api/manifest/labels.go")
        with open(path) as f:
            content = f.read()
        assert "app.kubernetes.io/name" in content, "Should use standard label keys"
        assert "app.kubernetes.io/managed-by" in content, (
            "Should set managed-by label"
        )

    def test_validate_labels_function(self):
        """Verify ValidateLabels function is defined"""
        path = os.path.join(self.REPO_DIR, "api/manifest/labels.go")
        with open(path) as f:
            content = f.read()
        assert "ValidateLabels" in content, (
            "ValidateLabels function should be defined"
        )

    # === Functional Checks ===

    def test_go_files_have_package(self):
        """Verify Go files have proper package declarations"""
        for rel_path in [
            "api/manifest/generator.go",
            "api/manifest/security.go",
            "api/manifest/labels.go",
        ]:
            path = os.path.join(self.REPO_DIR, rel_path)
            with open(path) as f:
                content = f.read()
            assert content.startswith("package "), (
                f"{rel_path} should start with package declaration"
            )

    def test_deployment_tests_pass(self):
        """Verify deployment tests pass"""
        result = subprocess.run(
            ["go", "test", "./api/manifest/", "-run", "TestDeployment", "-v"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, (
            f"Deployment tests failed:\n{result.stdout}\n{result.stderr}"
        )

    def test_security_tests_pass(self):
        """Verify security tests pass"""
        result = subprocess.run(
            ["go", "test", "./api/manifest/", "-run", "TestSecurity", "-v"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, (
            f"Security tests failed:\n{result.stdout}\n{result.stderr}"
        )

    def test_labels_tests_pass(self):
        """Verify labels tests pass"""
        result = subprocess.run(
            ["go", "test", "./api/manifest/", "-run", "TestLabels", "-v"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, (
            f"Labels tests failed:\n{result.stdout}\n{result.stderr}"
        )
