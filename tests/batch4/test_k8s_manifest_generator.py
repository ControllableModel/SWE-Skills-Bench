"""
Tests for skill: k8s-manifest-generator
Repo: kubernetes-sigs/kustomize
Image: zhangyiiiiii/swe-skills-bench-golang
Task: Build a Kubernetes manifest generator library that produces
      production-ready YAML with security defaults and Kustomize output.
"""

import ast
import importlib
import os
import sys

import pytest

REPO_DIR = "/workspace/kustomize"
GEN_DIR = os.path.join(REPO_DIR, "examples", "manifest-gen")

GENERATOR_FILE = os.path.join(GEN_DIR, "generator.py")
MODELS_FILE = os.path.join(GEN_DIR, "models.py")
SECURITY_FILE = os.path.join(GEN_DIR, "security.py")
KUSTOMIZE_WRITER_FILE = os.path.join(GEN_DIR, "kustomize_writer.py")


# ---------------------------------------------------------------------------
# Layer 1 — file_path_check
# ---------------------------------------------------------------------------

class TestFilePathCheck:
    """Verify all required manifest generator files exist."""

    def test_generator_exists(self):
        assert os.path.isfile(GENERATOR_FILE), f"Missing {GENERATOR_FILE}"

    def test_models_exists(self):
        assert os.path.isfile(MODELS_FILE), f"Missing {MODELS_FILE}"

    def test_security_exists(self):
        assert os.path.isfile(SECURITY_FILE), f"Missing {SECURITY_FILE}"

    def test_kustomize_writer_exists(self):
        assert os.path.isfile(KUSTOMIZE_WRITER_FILE), f"Missing {KUSTOMIZE_WRITER_FILE}"


# ---------------------------------------------------------------------------
# Layer 2 — semantic_check
# ---------------------------------------------------------------------------

class TestSemanticModels:
    """Verify application specification data models."""

    @pytest.fixture(autouse=True)
    def _load(self):
        with open(MODELS_FILE, "r", encoding="utf-8") as f:
            self.src = f.read()
        self.tree = ast.parse(self.src)

    def test_app_spec_class(self):
        classes = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.ClassDef)]
        assert "AppSpec" in classes, f"Expected AppSpec class; found {classes}"

    def test_resource_spec_class(self):
        classes = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.ClassDef)]
        assert "ResourceSpec" in classes, f"Expected ResourceSpec class; found {classes}"

    def test_storage_spec_class(self):
        classes = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.ClassDef)]
        assert "StorageSpec" in classes, f"Expected StorageSpec class; found {classes}"

    def test_ingress_spec_class(self):
        classes = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.ClassDef)]
        assert "IngressSpec" in classes, f"Expected IngressSpec class; found {classes}"

    def test_app_spec_fields(self):
        for field in ["name", "image", "port", "replicas"]:
            assert field in self.src, f"AppSpec should have field '{field}'"

    def test_storage_fields(self):
        for field in ["size", "mount_path", "access_mode"]:
            assert field in self.src, f"StorageSpec should have field '{field}'"


class TestSemanticGenerator:
    """Verify ManifestGenerator structure."""

    @pytest.fixture(autouse=True)
    def _load(self):
        with open(GENERATOR_FILE, "r", encoding="utf-8") as f:
            self.src = f.read()
        self.tree = ast.parse(self.src)

    def test_manifest_generator_class(self):
        classes = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.ClassDef)]
        assert "ManifestGenerator" in classes, f"Expected ManifestGenerator; found {classes}"

    def test_generate_deployment_method(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "generate_deployment" in funcs, f"Expected generate_deployment; found {funcs}"

    def test_generate_service_method(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "generate_service" in funcs, f"Expected generate_service; found {funcs}"

    def test_generate_configmap_method(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "generate_configmap" in funcs, f"Expected generate_configmap; found {funcs}"

    def test_generate_secret_method(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "generate_secret" in funcs, f"Expected generate_secret; found {funcs}"

    def test_generate_all_method(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "generate_all" in funcs, f"Expected generate_all; found {funcs}"

    def test_health_probes(self):
        assert "healthz" in self.src and "readyz" in self.src, (
            "Generator must include liveness (/healthz) and readiness (/readyz) probes"
        )


class TestSemanticSecurity:
    """Verify security module structure."""

    @pytest.fixture(autouse=True)
    def _load(self):
        with open(SECURITY_FILE, "r", encoding="utf-8") as f:
            self.src = f.read()
        self.tree = ast.parse(self.src)

    def test_apply_security_context_function(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "apply_security_context" in funcs, (
            f"Expected apply_security_context; found {funcs}"
        )

    def test_validate_image_function(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "validate_image" in funcs, f"Expected validate_image; found {funcs}"

    def test_run_as_non_root(self):
        assert "runAsNonRoot" in self.src, "Security context must set runAsNonRoot"

    def test_read_only_root(self):
        assert "readOnlyRootFilesystem" in self.src, (
            "Security context must set readOnlyRootFilesystem"
        )

    def test_drop_all_capabilities(self):
        assert "ALL" in self.src and "drop" in self.src.lower(), (
            "Security context must drop ALL capabilities"
        )

    def test_no_privilege_escalation(self):
        assert "allowPrivilegeEscalation" in self.src, (
            "Security context must set allowPrivilegeEscalation"
        )


class TestSemanticKustomizeWriter:
    """Verify KustomizeWriter structure."""

    @pytest.fixture(autouse=True)
    def _load(self):
        with open(KUSTOMIZE_WRITER_FILE, "r", encoding="utf-8") as f:
            self.src = f.read()
        self.tree = ast.parse(self.src)

    def test_class_defined(self):
        classes = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.ClassDef)]
        assert "KustomizeWriter" in classes, f"Expected KustomizeWriter; found {classes}"

    def test_write_method(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "write" in funcs, f"Expected write method; found {funcs}"

    def test_kustomization_yaml_reference(self):
        assert "kustomization.yaml" in self.src or "kustomization" in self.src.lower(), (
            "KustomizeWriter must generate a kustomization.yaml"
        )


# ---------------------------------------------------------------------------
# Layer 3 — functional_check
# ---------------------------------------------------------------------------

class TestFunctionalManifestGenerator:
    """Run ManifestGenerator and verify output objects."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        sys.path.insert(0, GEN_DIR)
        sys.path.insert(0, REPO_DIR)
        try:
            from models import AppSpec
            from generator import ManifestGenerator
            self.AppSpec = AppSpec
            self.ManifestGenerator = ManifestGenerator
        except ImportError:
            try:
                from manifest_gen.models import AppSpec
                from manifest_gen.generator import ManifestGenerator
                self.AppSpec = AppSpec
                self.ManifestGenerator = ManifestGenerator
            except ImportError:
                pytest.skip("Cannot import ManifestGenerator")

    def test_basic_deployment(self):
        spec = self.AppSpec(name="myapp", image="nginx:1.25", port=80)
        gen = self.ManifestGenerator(spec)
        dep = gen.generate_deployment()
        assert dep["kind"] == "Deployment"
        assert dep["metadata"]["labels"]["app"] == "myapp"

    def test_default_replicas(self):
        spec = self.AppSpec(name="myapp", image="nginx:1.25", port=80)
        gen = self.ManifestGenerator(spec)
        dep = gen.generate_deployment()
        assert dep["spec"]["replicas"] == 3, "Default replicas should be 3"

    def test_service_cluster_ip(self):
        spec = self.AppSpec(name="myapp", image="nginx:1.25", port=80)
        gen = self.ManifestGenerator(spec)
        svc = gen.generate_service()
        assert svc["kind"] == "Service"
        svc_type = svc["spec"].get("type", "ClusterIP")
        assert svc_type == "ClusterIP"

    def test_security_context_applied(self):
        spec = self.AppSpec(name="myapp", image="nginx:1.25", port=80)
        gen = self.ManifestGenerator(spec)
        dep = gen.generate_deployment()
        containers = dep["spec"]["template"]["spec"]["containers"]
        ctx = containers[0].get("securityContext", {})
        assert ctx.get("runAsNonRoot") is True, "runAsNonRoot should be True"
        assert ctx.get("readOnlyRootFilesystem") is True, "readOnlyRootFilesystem should be True"
        assert ctx.get("allowPrivilegeEscalation") is False, "allowPrivilegeEscalation should be False"

    def test_drop_all_capabilities(self):
        spec = self.AppSpec(name="myapp", image="nginx:1.25", port=80)
        gen = self.ManifestGenerator(spec)
        dep = gen.generate_deployment()
        containers = dep["spec"]["template"]["spec"]["containers"]
        caps = containers[0].get("securityContext", {}).get("capabilities", {})
        assert "ALL" in caps.get("drop", []), "Should drop ALL capabilities"


class TestFunctionalImageValidation:
    """Verify image tag validation rejects :latest and untagged images."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        sys.path.insert(0, GEN_DIR)
        sys.path.insert(0, REPO_DIR)
        try:
            from security import validate_image
            self.validate_image = validate_image
        except ImportError:
            try:
                from manifest_gen.security import validate_image
                self.validate_image = validate_image
            except ImportError:
                pytest.skip("Cannot import validate_image")

    def test_valid_image(self):
        assert self.validate_image("nginx:1.25") is True

    def test_latest_rejected(self):
        with pytest.raises(ValueError):
            self.validate_image("nginx:latest")

    def test_no_tag_rejected(self):
        with pytest.raises(ValueError):
            self.validate_image("nginx")


class TestFunctionalConditionalGeneration:
    """Verify conditional manifest generation based on spec."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        sys.path.insert(0, GEN_DIR)
        sys.path.insert(0, REPO_DIR)
        try:
            from models import AppSpec, StorageSpec
            from generator import ManifestGenerator
            self.AppSpec = AppSpec
            self.StorageSpec = StorageSpec
            self.ManifestGenerator = ManifestGenerator
        except ImportError:
            try:
                from manifest_gen.models import AppSpec, StorageSpec
                from manifest_gen.generator import ManifestGenerator
                self.AppSpec = AppSpec
                self.StorageSpec = StorageSpec
                self.ManifestGenerator = ManifestGenerator
            except ImportError:
                pytest.skip("Cannot import models/generator")

    def test_secret_generated_when_secrets_provided(self):
        spec = self.AppSpec(
            name="myapp", image="nginx:1.25", port=80,
            secrets={"DB_PASSWORD": "s3cret"},
        )
        gen = self.ManifestGenerator(spec)
        secret = gen.generate_secret()
        assert secret is not None, "Secret should be generated when secrets are provided"
        assert secret["kind"] == "Secret"

    def test_pvc_generated_with_storage(self):
        storage = self.StorageSpec(size="10Gi", mount_path="/data")
        spec = self.AppSpec(
            name="myapp", image="nginx:1.25", port=80,
            storage=storage,
        )
        gen = self.ManifestGenerator(spec)
        pvc = gen.generate_pvc()
        assert pvc is not None, "PVC should be generated when storage is specified"
        assert pvc["kind"] == "PersistentVolumeClaim"

    def test_generate_all_includes_deployment_and_service(self):
        spec = self.AppSpec(name="myapp", image="nginx:1.25", port=80)
        gen = self.ManifestGenerator(spec)
        manifests = gen.generate_all()
        kinds = [m["kind"] for m in manifests]
        assert "Deployment" in kinds, f"generate_all must include Deployment; got {kinds}"
        assert "Service" in kinds, f"generate_all must include Service; got {kinds}"

    def test_resource_limits_in_deployment(self):
        spec = self.AppSpec(name="myapp", image="nginx:1.25", port=80)
        gen = self.ManifestGenerator(spec)
        dep = gen.generate_deployment()
        containers = dep["spec"]["template"]["spec"]["containers"]
        res = containers[0].get("resources", {})
        assert "limits" in res, "Container must have resource limits"
        assert "requests" in res, "Container must have resource requests"

    def test_managed_by_label(self):
        spec = self.AppSpec(name="myapp", image="nginx:1.25", port=80)
        gen = self.ManifestGenerator(spec)
        dep = gen.generate_deployment()
        labels = dep["metadata"].get("labels", {})
        assert labels.get("app.kubernetes.io/managed-by") == "manifest-gen", (
            f"Expected managed-by=manifest-gen label; got {labels}"
        )
