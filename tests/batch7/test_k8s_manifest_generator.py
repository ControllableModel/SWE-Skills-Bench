"""
Test skill: k8s-manifest-generator
Verify that the Agent implements an ApplicationGenerator plugin for Kustomize —
ApplicationSpec types, Deployment/Service/ConfigMap/HPA generation, autoscaling
logic, health probes, and ConfigMap volume mounting.
"""

import os
import re
import subprocess
import pytest


class TestK8sManifestGenerator:
    REPO_DIR = "/workspace/kustomize"

    # ────── helpers ──────

    def _read(self, rel_path):
        fpath = os.path.join(self.REPO_DIR, rel_path)
        with open(fpath, "r") as f:
            return f.read()

    def _exists(self, rel_path):
        return os.path.isfile(os.path.join(self.REPO_DIR, rel_path))

    # === File Path Checks ===

    def test_applicationspec_types_exists(self):
        """ApplicationSpec type definitions must exist"""
        assert self._exists("api/types/applicationspec.go")

    def test_applicationgenerator_exists(self):
        """ApplicationGenerator plugin implementation must exist"""
        found = False
        for candidate in [
            "plugin/builtin/applicationgenerator/ApplicationGenerator.go",
            "plugin/builtin/applicationgenerator/applicationgenerator.go",
        ]:
            if self._exists(candidate):
                found = True
                break
        assert found, "ApplicationGenerator plugin file not found"

    def test_applicationgenerator_test_exists(self):
        """ApplicationGenerator test file must exist"""
        found = False
        for candidate in [
            "plugin/builtin/applicationgenerator/ApplicationGenerator_test.go",
            "plugin/builtin/applicationgenerator/applicationgenerator_test.go",
        ]:
            if self._exists(candidate):
                found = True
                break
        assert found, "ApplicationGenerator test file not found"

    # === Semantic Checks — ApplicationSpec Types ===

    def test_applicationspec_struct(self):
        """ApplicationSpec struct must be defined"""
        src = self._read("api/types/applicationspec.go")
        assert re.search(r'type\s+ApplicationSpec\s+struct', src), (
            "ApplicationSpec struct not found"
        )

    def test_applicationspec_core_fields(self):
        """ApplicationSpec must have key fields"""
        src = self._read("api/types/applicationspec.go")
        for field in ["Name", "Image", "Port", "Replicas"]:
            assert field in src, f"ApplicationSpec missing field: {field}"

    def test_applicationspec_autoscaling_fields(self):
        """Must have autoscaling spec"""
        src = self._read("api/types/applicationspec.go")
        lower = src.lower()
        assert "autoscal" in lower or "hpa" in lower or "minreplicas" in lower, (
            "Autoscaling fields not found"
        )

    def test_applicationspec_health_probe_fields(self):
        """Must have health/readiness probe configuration"""
        src = self._read("api/types/applicationspec.go")
        lower = src.lower()
        assert "health" in lower or "probe" in lower or "liveness" in lower or "readiness" in lower, (
            "Health probe fields not found"
        )

    def test_applicationspec_configmap_fields(self):
        """Must have ConfigMap / environment configuration"""
        src = self._read("api/types/applicationspec.go")
        lower = src.lower()
        assert "config" in lower or "env" in lower or "configmap" in lower, (
            "ConfigMap / environment fields not found"
        )

    # === Semantic Checks — ApplicationGenerator Plugin ===

    def _read_generator(self):
        for candidate in [
            "plugin/builtin/applicationgenerator/ApplicationGenerator.go",
            "plugin/builtin/applicationgenerator/applicationgenerator.go",
        ]:
            if self._exists(candidate):
                return self._read(candidate)
        pytest.fail("ApplicationGenerator file not found")

    def test_generate_method(self):
        """Generate method must exist"""
        src = self._read_generator()
        assert re.search(r'func\s+\(.*\)\s+Generate\b', src), (
            "Generate method not found"
        )

    def test_deployment_generation(self):
        """Must generate a Deployment resource"""
        src = self._read_generator()
        assert "Deployment" in src, "Deployment generation not found"

    def test_service_generation(self):
        """Must generate a Service resource"""
        src = self._read_generator()
        assert "Service" in src, "Service generation not found"

    def test_configmap_generation(self):
        """Must generate a ConfigMap resource"""
        src = self._read_generator()
        assert "ConfigMap" in src, "ConfigMap generation not found"

    def test_hpa_generation(self):
        """Must generate HorizontalPodAutoscaler when autoscaling enabled"""
        src = self._read_generator()
        assert "HorizontalPodAutoscaler" in src or "HPA" in src or "Autoscal" in src, (
            "HPA generation not found"
        )

    def test_replicas_omitted_when_autoscaling(self):
        """Replicas should be omitted from Deployment when autoscaling is enabled"""
        src = self._read_generator()
        lower = src.lower()
        # Must have conditional replicas logic
        assert ("autoscal" in lower and "replica" in lower), (
            "No conditional replica/autoscaling logic found"
        )

    def test_health_probes_in_deployment(self):
        """Health probes must be set on Deployment containers"""
        src = self._read_generator()
        lower = src.lower()
        assert "probe" in lower or "liveness" in lower or "readiness" in lower or "healthcheck" in lower, (
            "Health probes not applied in Deployment"
        )

    def test_configmap_volume_mount(self):
        """ConfigMap must be mounted as a volume in Deployment"""
        src = self._read_generator()
        lower = src.lower()
        assert "volume" in lower or "mount" in lower or "volumemount" in lower, (
            "ConfigMap volume mount not found"
        )

    # === Functional Checks ===

    def test_go_build_types(self):
        """Types package must build"""
        result = subprocess.run(
            ["go", "build", "./api/types/..."],
            capture_output=True, text=True, cwd=self.REPO_DIR, timeout=300,
        )
        assert result.returncode == 0, (
            f"go build failed:\n{result.stdout}\n{result.stderr}"
        )

    def test_go_build_plugin(self):
        """Plugin package must build"""
        result = subprocess.run(
            ["go", "build", "./plugin/builtin/applicationgenerator/..."],
            capture_output=True, text=True, cwd=self.REPO_DIR, timeout=300,
        )
        assert result.returncode == 0, (
            f"go build failed:\n{result.stdout}\n{result.stderr}"
        )

    def test_plugin_tests_pass(self):
        """ApplicationGenerator tests must pass"""
        result = subprocess.run(
            ["go", "test", "-v",
             "./plugin/builtin/applicationgenerator/...",
             "-run", "TestApplication"],
            capture_output=True, text=True, cwd=self.REPO_DIR, timeout=300,
        )
        assert result.returncode == 0, (
            f"Tests failed:\n{result.stdout}\n{result.stderr}"
        )
