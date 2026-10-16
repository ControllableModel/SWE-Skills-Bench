"""
Tests for the k8s-manifest-generator skill.
Validates a Kubernetes manifest generator with Kustomize overlay support,
security policies, and best-practice validation.
"""

import os
import re
import ast

REPO_DIR = "/workspace/kustomize"
PYTHON_DIR = os.path.join(REPO_DIR, "tests", "python")


class TestK8sManifestGenerator:
    """Tests for the Kubernetes manifest generator."""

    # ── file_path_check ──────────────────────────────────────────────

    def test_manifest_generator_exists(self):
        """ManifestGenerator module must exist."""
        path = os.path.join(PYTHON_DIR, "manifest_generator.py")
        assert os.path.isfile(path), f"Missing {path}"

    def test_kustomize_builder_exists(self):
        """KustomizeBuilder module must exist."""
        path = os.path.join(PYTHON_DIR, "kustomize_builder.py")
        assert os.path.isfile(path), f"Missing {path}"

    def test_security_policies_exists(self):
        """SecurityPolicyGenerator module must exist."""
        path = os.path.join(PYTHON_DIR, "security_policies.py")
        assert os.path.isfile(path), f"Missing {path}"

    def test_manifest_validator_exists(self):
        """ManifestValidator module must exist."""
        path = os.path.join(PYTHON_DIR, "manifest_validator.py")
        assert os.path.isfile(path), f"Missing {path}"

    # ── semantic_check ───────────────────────────────────────────────

    def _read(self, filename):
        path = os.path.join(PYTHON_DIR, filename)
        if not os.path.isfile(path):
            return ""
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def test_generator_deployment(self):
        """ManifestGenerator must produce Deployment resources."""
        content = self._read("manifest_generator.py")
        assert re.search(r"class\s+ManifestGenerator", content), (
            "ManifestGenerator class not defined"
        )
        assert re.search(r"def\s+generate_deployment\b", content), (
            "generate_deployment not defined"
        )

    def test_generator_service_and_others(self):
        """ManifestGenerator must produce Service, ConfigMap, Ingress, HPA."""
        content = self._read("manifest_generator.py")
        for method in ["generate_service", "generate_configmap",
                        "generate_ingress", "generate_hpa"]:
            assert re.search(rf"def\s+{method}\b", content), f"{method} not defined"

    def test_health_probes_in_deployment(self):
        """Deployment must include liveness and readiness probes."""
        content = self._read("manifest_generator.py")
        assert re.search(r"liveness|livenessProbe", content, re.IGNORECASE), (
            "Liveness probe not found"
        )
        assert re.search(r"readiness|readinessProbe", content, re.IGNORECASE), (
            "Readiness probe not found"
        )

    def test_resource_limits_defaults(self):
        """Deployment must include default resource requests and limits."""
        content = self._read("manifest_generator.py")
        assert re.search(r"requests|limits|cpu|memory", content, re.IGNORECASE), (
            "Resource limits not found"
        )

    def test_kustomize_builder_class(self):
        """KustomizeBuilder must define create_base and create_overlay."""
        content = self._read("kustomize_builder.py")
        assert re.search(r"class\s+KustomizeBuilder", content), (
            "KustomizeBuilder class not defined"
        )
        assert re.search(r"def\s+create_base\b", content), "create_base not defined"
        assert re.search(r"def\s+create_overlay\b", content), "create_overlay not defined"

    def test_security_context(self):
        """SecurityPolicyGenerator must add non-root, read-only filesystem."""
        content = self._read("security_policies.py")
        assert re.search(r"runAsNonRoot|run_as_non_root", content), (
            "runAsNonRoot not found"
        )
        assert re.search(r"readOnlyRootFilesystem|read_only", content), (
            "readOnlyRootFilesystem not found"
        )

    def test_network_policy(self):
        """SecurityPolicyGenerator must generate NetworkPolicy."""
        content = self._read("security_policies.py")
        assert re.search(r"NetworkPolicy|network_policy", content), (
            "NetworkPolicy generation not found"
        )

    def test_validator_violations(self):
        """ManifestValidator must check for common violations."""
        content = self._read("manifest_validator.py")
        assert re.search(r"class\s+ManifestValidator", content), (
            "ManifestValidator class not defined"
        )
        assert re.search(r"def\s+validate\b", content), "validate method not defined"
        assert re.search(r"latest|Missing.*label|resource.*limit|privileged", content, re.IGNORECASE), (
            "Validation rules not found"
        )

    # ── functional_check ─────────────────────────────────────────────

    def test_all_files_valid_python(self):
        """All manifest generator Python files must have valid syntax."""
        errors = []
        for fname in ["manifest_generator.py", "kustomize_builder.py",
                       "security_policies.py", "manifest_validator.py"]:
            content = self._read(fname)
            if not content:
                continue
            try:
                ast.parse(content)
            except SyntaxError as e:
                errors.append(f"{fname}: {e}")
        assert not errors, "Syntax errors:\n" + "\n".join(errors)

    def test_api_versions_correct(self):
        """Generator must use correct Kubernetes API versions."""
        content = self._read("manifest_generator.py")
        assert re.search(r"apps/v1|networking\.k8s\.io/v1|autoscaling/v2", content), (
            "Correct Kubernetes API versions not found"
        )

    def test_rolling_update_strategy(self):
        """Deployment must use RollingUpdate strategy."""
        content = self._read("manifest_generator.py")
        assert re.search(r"RollingUpdate|rolling.update|maxSurge", content, re.IGNORECASE), (
            "RollingUpdate strategy not found"
        )

    def test_anti_affinity(self):
        """Deployment must include pod anti-affinity for spread."""
        content = self._read("manifest_generator.py")
        assert re.search(r"anti.affinity|antiAffinity|podAntiAffinity", content, re.IGNORECASE), (
            "Pod anti-affinity not found"
        )

    def test_pdb_generation(self):
        """SecurityPolicyGenerator must generate PodDisruptionBudget."""
        content = self._read("security_policies.py")
        assert re.search(r"PodDisruptionBudget|pdb|min_available", content, re.IGNORECASE), (
            "PodDisruptionBudget generation not found"
        )
