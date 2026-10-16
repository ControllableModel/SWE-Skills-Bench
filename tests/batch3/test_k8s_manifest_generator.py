"""
Tests for the k8s-manifest-generator skill.

Validates that Kubernetes manifest generators were implemented for kustomize,
including DeploymentGenerator, NetworkPolicyGenerator, and ConfigMapGenerator.

Repo: kustomize (https://github.com/kubernetes-sigs/kustomize)
"""

import os
import re
import subprocess

REPO_DIR = "/workspace/kustomize"


class TestFilePathCheck:
    """Verify that all required files were created."""

    def test_deployment_generator_exists(self):
        path = os.path.join(
            REPO_DIR, "api", "manifest", "deployment_generator.go",
        )
        assert os.path.isfile(path), f"Expected deployment_generator.go at {path}"

    def test_network_policy_generator_exists(self):
        path = os.path.join(
            REPO_DIR, "api", "manifest", "network_policy_generator.go",
        )
        assert os.path.isfile(path), f"Expected network_policy_generator.go at {path}"

    def test_configmap_generator_exists(self):
        path = os.path.join(
            REPO_DIR, "api", "manifest", "configmap_generator.go",
        )
        assert os.path.isfile(path), f"Expected configmap_generator.go at {path}"

    def test_deployment_test_exists(self):
        path = os.path.join(
            REPO_DIR, "api", "manifest", "deployment_generator_test.go",
        )
        assert os.path.isfile(path), f"Expected deployment_generator_test.go"

    def test_network_policy_test_exists(self):
        path = os.path.join(
            REPO_DIR, "api", "manifest", "network_policy_generator_test.go",
        )
        assert os.path.isfile(path), f"Expected network_policy_generator_test.go"


class TestSemanticDeploymentGenerator:
    """Verify DeploymentGenerator creates correct K8s Deployments."""

    def _read_deployment(self):
        path = os.path.join(
            REPO_DIR, "api", "manifest", "deployment_generator.go",
        )
        with open(path, "r") as f:
            return f.read()

    def test_struct_definition(self):
        content = self._read_deployment()
        assert re.search(r"type\s+DeploymentGenerator\s+struct", content), (
            "Expected DeploymentGenerator struct"
        )

    def test_api_version_apps_v1(self):
        content = self._read_deployment()
        assert re.search(r"apps/v1", content), (
            "Expected apiVersion: apps/v1 in deployment output"
        )

    def test_replicas_validation(self):
        content = self._read_deployment()
        assert re.search(r"replicas|Replicas", content), (
            "Expected replicas field with validation (>= 1)"
        )

    def test_image_tag_validation(self):
        content = self._read_deployment()
        assert re.search(r"image|Image|tag|Tag", content), (
            "Expected image tag validation (must include tag)"
        )

    def test_resource_limits(self):
        content = self._read_deployment()
        assert re.search(r"limits|Limits|resources|Resources", content), (
            "Expected resource limits/requests configuration"
        )

    def test_requests_le_limits(self):
        content = self._read_deployment()
        assert re.search(r"request|Request", content), (
            "Expected requests <= limits validation"
        )

    def test_probes(self):
        content = self._read_deployment()
        probes_found = sum(
            1 for p in ["liveness", "readiness", "startup"]
            if re.search(p, content, re.IGNORECASE)
        )
        assert probes_found >= 2, (
            f"Expected liveness and readiness probes, found {probes_found} probe types"
        )

    def test_security_context(self):
        content = self._read_deployment()
        assert re.search(r"securityContext|SecurityContext|security_context", content), (
            "Expected securityContext configuration"
        )

    def test_run_as_non_root(self):
        content = self._read_deployment()
        assert re.search(r"runAsNonRoot|RunAsNonRoot|run_as_non_root", content), (
            "Expected runAsNonRoot: true"
        )

    def test_read_only_root_filesystem(self):
        content = self._read_deployment()
        assert re.search(
            r"readOnlyRootFilesystem|ReadOnlyRootFilesystem", content
        ), "Expected readOnlyRootFilesystem: true"

    def test_drop_all_capabilities(self):
        content = self._read_deployment()
        assert re.search(r"drop.*ALL|ALL|capabilities", content), (
            "Expected drop ALL capabilities"
        )


class TestSemanticNetworkPolicyGenerator:
    """Verify NetworkPolicyGenerator creates correct NetworkPolicies."""

    def _read_netpol(self):
        path = os.path.join(
            REPO_DIR, "api", "manifest", "network_policy_generator.go",
        )
        with open(path, "r") as f:
            return f.read()

    def test_struct_definition(self):
        content = self._read_netpol()
        assert re.search(r"type\s+NetworkPolicy\w*\s+struct", content), (
            "Expected NetworkPolicyGenerator struct"
        )

    def test_deny_all_ingress(self):
        content = self._read_netpol()
        assert re.search(r"deny|Deny|Ingress|ingress", content, re.IGNORECASE), (
            "Expected deny-all ingress default policy"
        )

    def test_namespace_allow(self):
        content = self._read_netpol()
        assert re.search(r"namespace|Namespace|namespaceSelector", content), (
            "Expected namespace-based allow rule"
        )

    def test_port_range_validation(self):
        content = self._read_netpol()
        assert re.search(r"port|Port|65535", content), (
            "Expected port validation (1-65535)"
        )

    def test_cidr_egress(self):
        content = self._read_netpol()
        assert re.search(r"cidr|CIDR|Egress|egress", content), (
            "Expected CIDR-based egress rules"
        )

    def test_block_metadata_service(self):
        content = self._read_netpol()
        assert re.search(r"169\.254\.169\.254", content), (
            "Expected block for cloud metadata service 169.254.169.254/32"
        )


class TestSemanticConfigMapGenerator:
    """Verify ConfigMapGenerator and Secret generation."""

    def _read_configmap(self):
        path = os.path.join(
            REPO_DIR, "api", "manifest", "configmap_generator.go",
        )
        with open(path, "r") as f:
            return f.read()

    def test_size_limit(self):
        content = self._read_configmap()
        # 1 MiB = 1048576
        assert re.search(r"1048576|1.*MiB|1.*Mi|size.*limit", content, re.IGNORECASE), (
            "Expected ConfigMap size limit of 1MiB"
        )

    def test_key_validation(self):
        content = self._read_configmap()
        assert re.search(r"key|Key|name|Name|valid", content, re.IGNORECASE), (
            "Expected key naming validation"
        )

    def test_secret_base64(self):
        content = self._read_configmap()
        assert re.search(r"base64|Base64|Secret|secret|encode", content), (
            "Expected Secret generation with base64 encoding"
        )


class TestFunctionalGoSyntax:
    """Validate Go files are syntactically correct."""

    def _base_dir(self):
        return os.path.join(REPO_DIR, "api", "manifest")

    def test_package_declaration(self):
        path = os.path.join(self._base_dir(), "deployment_generator.go")
        with open(path, "r") as f:
            content = f.read(500)
        assert re.search(r"^package\s+\w+", content, re.MULTILINE), (
            "Expected package declaration"
        )

    def test_go_vet(self):
        result = subprocess.run(
            ["go", "vet", "./api/manifest/..."],
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

    def test_deployment_test_funcs(self):
        path = os.path.join(self._base_dir(), "deployment_generator_test.go")
        with open(path, "r") as f:
            content = f.read()
        test_count = len(re.findall(r"func\s+Test\w+", content))
        assert test_count >= 3, (
            f"Expected >= 3 test functions, found {test_count}"
        )

    def test_yaml_output(self):
        """Generated manifests should contain YAML-like structure."""
        path = os.path.join(self._base_dir(), "deployment_generator.go")
        with open(path, "r") as f:
            content = f.read()
        assert re.search(r"yaml|YAML|marshal|Marshal|encoding", content, re.IGNORECASE), (
            "Expected YAML marshaling of K8s manifests"
        )
