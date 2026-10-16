"""
Test skill: k8s-manifest-generator
Verify that the Agent creates Deployment, Service, HPA, PDB, and NetworkPolicy
generators with security best practices (Go / Kustomize).
"""

import os
import re
import subprocess
import pytest


class TestK8sManifestGenerator:
    REPO_DIR = "/workspace/kustomize"

    # === File Path Checks ===

    def test_generator_files_exist(self):
        """Verify Kubernetes manifest generator files exist"""
        found = False
        for root, dirs, files in os.walk(self.REPO_DIR):
            if ".git" in root or "vendor" in root:
                continue
            for f in files:
                if f.endswith(".go") and ("deploy" in f.lower() or "service" in f.lower() or "hpa" in f.lower() or "pdb" in f.lower() or "network" in f.lower() or "generator" in f.lower() or "manifest" in f.lower()):
                    found = True
                    break
            if found:
                break
        assert found, "K8s manifest generator files not found"

    # === Semantic Checks ===

    def test_deployment_generator_defined(self):
        """Verify Deployment generator is implemented"""
        content = self._collect_content()
        assert "Deployment" in content, "Deployment generator not found"

    def test_service_generator_defined(self):
        """Verify Service generator is implemented"""
        content = self._collect_content()
        has_svc = "Service" in content and ("ClusterIP" in content or "NodePort" in content or "LoadBalancer" in content or "Port" in content)
        assert has_svc, "Service generator not found"

    def test_hpa_generator_defined(self):
        """Verify HorizontalPodAutoscaler generator is implemented"""
        content = self._collect_content()
        has_hpa = "HorizontalPodAutoscaler" in content or "autoscaling" in content or "HPA" in content
        assert has_hpa, "HPA generator not found"

    def test_pdb_generator_defined(self):
        """Verify PodDisruptionBudget generator is implemented"""
        content = self._collect_content()
        has_pdb = "PodDisruptionBudget" in content or "pdb" in content.lower()
        assert has_pdb, "PDB generator not found"

    def test_network_policy_generator_defined(self):
        """Verify NetworkPolicy generator is implemented"""
        content = self._collect_content()
        has_np = "NetworkPolicy" in content or "networkpolicy" in content.lower()
        assert has_np, "NetworkPolicy generator not found"

    def test_security_context_applied(self):
        """Verify security best practices like SecurityContext are applied"""
        content = self._collect_content()
        content_lower = content.lower()
        has_security = (
            "securitycontext" in content_lower
            or "readonly" in content_lower
            or "runasnonroot" in content_lower
            or "allowprivilegeescalation" in content_lower
            or "readonlyrootfilesystem" in content_lower
        )
        assert has_security, "Security context not applied"

    # === Functional Checks ===

    def test_go_files_have_package(self):
        """Verify Go files have proper package declarations"""
        go_files = self._find_go_files()
        assert len(go_files) > 0, "No relevant Go files found"
        for gf in go_files:
            with open(gf) as fh:
                content = fh.read()
            assert "package " in content[:200], f"{gf} missing package declaration"

    def test_go_files_balanced_braces(self):
        """Verify Go files have balanced braces"""
        go_files = self._find_go_files()
        for gf in go_files:
            with open(gf) as fh:
                content = fh.read()
            cleaned = re.sub(r'"[^"]*"', '', content)
            cleaned = re.sub(r'`[^`]*`', '', cleaned)
            cleaned = re.sub(r'//[^\n]*', '', cleaned)
            cleaned = re.sub(r'/\*.*?\*/', '', cleaned, flags=re.DOTALL)
            opens = cleaned.count('{')
            closes = cleaned.count('}')
            assert opens == closes, f"Unbalanced braces in {gf}: {opens} vs {closes}"

    def test_go_build(self):
        """Verify the project builds"""
        result = subprocess.run(
            ["go", "build", "./..."],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode != 0:
            related = [
                line for line in result.stderr.splitlines()
                if any(kw in line.lower() for kw in ["deploy", "service", "hpa", "pdb", "network", "generator", "manifest"])
            ]
            assert len(related) == 0, f"Build errors in generators: {related[:5]}"

    def test_resource_limits_enforced(self):
        """Verify resource limits are generated for Deployments"""
        content = self._collect_content()
        content_lower = content.lower()
        has_resources = "resources" in content_lower or "limits" in content_lower or "requests" in content_lower
        assert has_resources, "Resource limits not enforced in generated manifests"

    def _collect_content(self):
        all_content = ""
        for root, dirs, files in os.walk(self.REPO_DIR):
            if ".git" in root or "vendor" in root:
                continue
            for f in files:
                if f.endswith(".go"):
                    fpath = os.path.join(root, f)
                    try:
                        with open(fpath) as fh:
                            c = fh.read()
                        if any(kw in c for kw in ["Deployment", "Service", "HorizontalPodAutoscaler", "PodDisruptionBudget", "NetworkPolicy"]):
                            all_content += c + "\n"
                    except (UnicodeDecodeError, PermissionError):
                        continue
        return all_content

    def _find_go_files(self):
        go_files = []
        for root, dirs, files in os.walk(self.REPO_DIR):
            if ".git" in root or "vendor" in root:
                continue
            for f in files:
                if f.endswith(".go") and ("deploy" in f.lower() or "service" in f.lower() or "hpa" in f.lower() or "pdb" in f.lower() or "network" in f.lower() or "generator" in f.lower() or "manifest" in f.lower()):
                    go_files.append(os.path.join(root, f))
        return go_files
