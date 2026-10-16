"""
Tests for the gitops-workflow skill.

Validates that a GitOps application deployment configuration generator
was implemented for Flux, including Kustomization/GitRepository CRDs,
multi-environment promotion, health checks, and drift detection.

Repo: flux2 (https://github.com/fluxcd/flux2)
"""

import os
import re
import subprocess

REPO_DIR = "/workspace/flux2"


class TestFilePathCheck:
    """Verify that all required files were created."""

    def test_app_generator_exists(self):
        path = os.path.join(REPO_DIR, "internal", "gitops", "app_generator.go")
        assert os.path.isfile(path), f"Expected app_generator.go at {path}"

    def test_environment_exists(self):
        path = os.path.join(REPO_DIR, "internal", "gitops", "environment.go")
        assert os.path.isfile(path), f"Expected environment.go at {path}"

    def test_health_check_exists(self):
        path = os.path.join(REPO_DIR, "internal", "gitops", "health_check.go")
        assert os.path.isfile(path), f"Expected health_check.go at {path}"

    def test_app_generator_test_exists(self):
        path = os.path.join(REPO_DIR, "internal", "gitops", "app_generator_test.go")
        assert os.path.isfile(path), f"Expected app_generator_test.go at {path}"

    def test_environment_test_exists(self):
        path = os.path.join(REPO_DIR, "internal", "gitops", "environment_test.go")
        assert os.path.isfile(path), f"Expected environment_test.go at {path}"


class TestSemanticAppGenerator:
    """Verify AppGenerator produces Flux CRDs."""

    def _read_generator(self):
        path = os.path.join(REPO_DIR, "internal", "gitops", "app_generator.go")
        with open(path, "r") as f:
            return f.read()

    def test_app_generator_struct(self):
        content = self._read_generator()
        assert re.search(r"type\s+AppGenerator\s+struct", content), (
            "Expected AppGenerator struct"
        )

    def test_kustomization_api_version(self):
        content = self._read_generator()
        assert re.search(r"kustomize\.toolkit\.fluxcd\.io/v1", content), (
            "Expected Kustomization apiVersion: kustomize.toolkit.fluxcd.io/v1"
        )

    def test_git_repository_api_version(self):
        content = self._read_generator()
        assert re.search(r"source\.toolkit\.fluxcd\.io/v1", content), (
            "Expected GitRepository apiVersion: source.toolkit.fluxcd.io/v1"
        )

    def test_prune_enabled(self):
        content = self._read_generator()
        assert re.search(r"prune.*true|Prune.*true", content, re.IGNORECASE), (
            "Expected prune: true in Kustomization"
        )

    def test_source_ref(self):
        content = self._read_generator()
        assert re.search(r"sourceRef|SourceRef|source_ref", content), (
            "Expected sourceRef in Kustomization pointing to GitRepository"
        )

    def test_target_namespace(self):
        content = self._read_generator()
        assert re.search(r"targetNamespace|TargetNamespace", content), (
            "Expected targetNamespace field in Kustomization"
        )


class TestSemanticEnvironmentManager:
    """Verify multi-environment promotion logic."""

    def _read_env(self):
        path = os.path.join(REPO_DIR, "internal", "gitops", "environment.go")
        with open(path, "r") as f:
            return f.read()

    def test_environment_manager_struct(self):
        content = self._read_env()
        assert re.search(r"EnvironmentManager|type\s+\w*Manager\s+struct", content), (
            "Expected EnvironmentManager struct"
        )

    def test_three_environments(self):
        content = self._read_env()
        for env in ["development", "staging", "production"]:
            assert env in content, f"Expected environment '{env}'"

    def test_promote_method(self):
        content = self._read_env()
        assert re.search(r"func.*promote|func.*Promote", content), (
            "Expected promote method"
        )

    def test_production_suspended(self):
        content = self._read_env()
        assert re.search(r"suspend.*true|Suspend|suspend", content, re.IGNORECASE), (
            "Expected production Kustomization to be suspended by default"
        )

    def test_depends_on_staging(self):
        content = self._read_env()
        assert re.search(r"dependsOn|depends_on|DependsOn", content), (
            "Expected dependency relationships between environments"
        )

    def test_environment_intervals(self):
        """dev=1m, staging=5m, production=10m."""
        content = self._read_env()
        assert "1m" in content and "5m" in content and "10m" in content, (
            "Expected environment-specific sync intervals (1m, 5m, 10m)"
        )


class TestSemanticHealthCheck:
    """Verify health check configuration."""

    def _read_health(self):
        path = os.path.join(REPO_DIR, "internal", "gitops", "health_check.go")
        with open(path, "r") as f:
            return f.read()

    def test_health_check_config(self):
        content = self._read_health()
        assert re.search(r"HealthCheck|healthCheck|health_check", content), (
            "Expected HealthCheckConfig struct/type"
        )

    def test_deployment_health(self):
        content = self._read_health()
        assert re.search(r"Deployment|apps/v1", content), (
            "Expected Deployment health check (apps/v1)"
        )

    def test_timeout_configuration(self):
        content = self._read_health()
        assert re.search(r"timeout|Timeout|5m", content, re.IGNORECASE), (
            "Expected health check timeout configuration"
        )


class TestSemanticDriftDetection:
    """Verify drift detection configuration."""

    def _read_all(self):
        content = ""
        for fname in ["app_generator.go", "environment.go"]:
            path = os.path.join(REPO_DIR, "internal", "gitops", fname)
            if os.path.isfile(path):
                with open(path, "r") as f:
                    content += f.read()
        return content

    def test_force_field(self):
        content = self._read_all()
        assert re.search(r"force.*true|Force", content, re.IGNORECASE), (
            "Expected force: true for drift correction"
        )

    def test_alert_resource(self):
        """Should generate a Flux Alert for drift detection."""
        content = self._read_all()
        health = os.path.join(REPO_DIR, "internal", "gitops", "health_check.go")
        if os.path.isfile(health):
            with open(health, "r") as f:
                content += f.read()
        assert re.search(r"Alert|alert|drift|reconcile", content, re.IGNORECASE), (
            "Expected drift detection Alert resource configuration"
        )


class TestFunctionalGoSyntax:
    """Validate Go files are syntactically correct."""

    def test_package_declaration(self):
        path = os.path.join(REPO_DIR, "internal", "gitops", "app_generator.go")
        with open(path, "r") as f:
            content = f.read()
        assert re.search(r"^package\s+gitops", content, re.MULTILINE), (
            "Expected 'package gitops' declaration"
        )

    def test_go_vet(self):
        result = subprocess.run(
            ["go", "vet", "./internal/gitops/..."],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            stderr = result.stderr.lower()
            assert "syntax error" not in stderr, (
                f"Go syntax errors: {result.stderr[:500]}"
            )

    def test_app_generator_test_has_funcs(self):
        path = os.path.join(REPO_DIR, "internal", "gitops", "app_generator_test.go")
        with open(path, "r") as f:
            content = f.read()
        test_count = len(re.findall(r"func\s+Test\w+", content))
        assert test_count >= 2, (
            f"Expected at least 2 test functions, found {test_count}"
        )

    def test_environment_test_has_funcs(self):
        path = os.path.join(REPO_DIR, "internal", "gitops", "environment_test.go")
        with open(path, "r") as f:
            content = f.read()
        test_count = len(re.findall(r"func\s+Test\w+", content))
        assert test_count >= 2, (
            f"Expected at least 2 test functions, found {test_count}"
        )
