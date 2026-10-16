"""
Test skill: gitops-workflow
Verify that the Agent creates GitOps generator with Kustomization, HelmRelease,
ImageUpdate, and promotion controller for Flux CD (Go).
"""

import os
import re
import subprocess
import pytest


class TestGitopsWorkflow:
    REPO_DIR = "/workspace/flux2"

    # === File Path Checks ===

    def test_gitops_generator_files_exist(self):
        """Verify GitOps generator Go files exist"""
        found = False
        for root, dirs, files in os.walk(self.REPO_DIR):
            if ".git" in root or "vendor" in root:
                continue
            for f in files:
                if f.endswith(".go") and ("generator" in f.lower() or "gitops" in f.lower() or "kustomiz" in f.lower()):
                    found = True
                    break
            if found:
                break
        assert found, "GitOps generator files not found"

    # === Semantic Checks ===

    def test_kustomization_generator_defined(self):
        """Verify Kustomization generator is implemented"""
        content = self._find_content()
        has_kust = "Kustomization" in content or "kustomization" in content.lower()
        assert has_kust, "Kustomization generator not found"

    def test_helm_release_generator_defined(self):
        """Verify HelmRelease generator is implemented"""
        content = self._find_content()
        has_helm = "HelmRelease" in content or "helmrelease" in content.lower()
        assert has_helm, "HelmRelease generator not found"

    def test_image_update_generator_defined(self):
        """Verify ImageUpdate automation generator is implemented"""
        content = self._find_content()
        has_image = "ImageUpdate" in content or "imageupdate" in content.lower() or "ImagePolicy" in content
        assert has_image, "ImageUpdate generator not found"

    def test_promotion_controller_defined(self):
        """Verify promotion controller is implemented"""
        content = self._find_content()
        content_lower = content.lower()
        has_promotion = "promotion" in content_lower or "promote" in content_lower
        assert has_promotion, "Promotion controller not found"

    def test_flux_api_types_used(self):
        """Verify Flux API types are used"""
        content = self._find_content()
        has_flux_api = (
            "fluxcd" in content.lower()
            or "source.toolkit" in content
            or "kustomize.toolkit" in content
            or "notification.toolkit" in content
        )
        assert has_flux_api, "Flux API types not found"

    # === Functional Checks ===

    def test_go_files_have_package(self):
        """Verify Go files have proper package declarations"""
        go_files = self._find_go_files()
        assert len(go_files) > 0, "No generator Go files found"
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
            cleaned = re.sub(r'//[^\n]*', '', cleaned)
            cleaned = re.sub(r'/\*.*?\*/', '', cleaned, flags=re.DOTALL)
            opens = cleaned.count('{')
            closes = cleaned.count('}')
            assert opens == closes, f"Unbalanced braces in {gf}: {opens} vs {closes}"

    def test_go_build(self):
        """Verify Go project builds"""
        result = subprocess.run(
            ["go", "build", "./..."],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode != 0:
            generator_errors = [
                line for line in result.stderr.splitlines()
                if "generator" in line.lower() or "gitops" in line.lower()
            ]
            assert len(generator_errors) == 0, (
                f"Build errors in generator files: {generator_errors[:5]}"
            )

    def test_generator_produces_yaml_output(self):
        """Verify generators produce YAML output"""
        content = self._find_content()
        has_yaml = (
            "yaml" in content.lower()
            or "Marshal" in content
            or "apiVersion" in content
            or "kind:" in content
        )
        assert has_yaml, "Generators don't produce YAML output"

    def _find_content(self):
        all_content = ""
        for root, dirs, files in os.walk(self.REPO_DIR):
            if ".git" in root or "vendor" in root:
                continue
            for f in files:
                if f.endswith(".go"):
                    fpath = os.path.join(root, f)
                    try:
                        with open(fpath) as fh:
                            content = fh.read()
                        if any(kw in content for kw in ["Kustomization", "HelmRelease", "ImageUpdate", "promotion", "generator"]):
                            all_content += content + "\n"
                    except (UnicodeDecodeError, PermissionError):
                        continue
        return all_content

    def _find_go_files(self):
        go_files = []
        for root, dirs, files in os.walk(self.REPO_DIR):
            if ".git" in root or "vendor" in root:
                continue
            for f in files:
                if f.endswith(".go") and ("generator" in f.lower() or "gitops" in f.lower() or "promot" in f.lower()):
                    go_files.append(os.path.join(root, f))
        return go_files
