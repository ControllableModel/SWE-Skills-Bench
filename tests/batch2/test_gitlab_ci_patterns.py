"""
Test skill: gitlab-ci-patterns
Verify that the Agent fixes GitLab security CI templates (SAST, DAST,
Dependency-Scanning) with complete job configurations, execution rules,
artifact collection, and valid YAML.
"""

import os
import re
import subprocess
import pytest


class TestGitlabCiPatterns:
    REPO_DIR = "/workspace/gitlabhq"

    TEMPLATE_DIR = "lib/gitlab/ci/templates/Security"

    # === File Path Checks ===

    def test_sast_template_exists(self):
        """Verify SAST.gitlab-ci.yml exists"""
        path = os.path.join(
            self.REPO_DIR, self.TEMPLATE_DIR, "SAST.gitlab-ci.yml"
        )
        assert os.path.exists(path), f"SAST template not found at {path}"

    def test_dast_template_exists(self):
        """Verify DAST.gitlab-ci.yml exists"""
        path = os.path.join(
            self.REPO_DIR, self.TEMPLATE_DIR, "DAST.gitlab-ci.yml"
        )
        assert os.path.exists(path), f"DAST template not found at {path}"

    def test_dependency_scanning_template_exists(self):
        """Verify Dependency-Scanning.gitlab-ci.yml exists"""
        path = os.path.join(
            self.REPO_DIR, self.TEMPLATE_DIR,
            "Dependency-Scanning.gitlab-ci.yml",
        )
        assert os.path.exists(path), (
            f"Dependency-Scanning template not found"
        )

    # === Semantic Checks ===

    def test_sast_has_scanner_image(self):
        """Verify SAST template references a scanner image"""
        path = os.path.join(
            self.REPO_DIR, self.TEMPLATE_DIR, "SAST.gitlab-ci.yml"
        )
        with open(path) as f:
            content = f.read()

        image_indicators = ["image:", "IMAGE", "scanner", "sast"]
        found = [ind for ind in image_indicators if ind in content]
        assert len(found) >= 2, (
            f"SAST should reference scanner image. Found: {found}"
        )

    def test_sast_has_variables(self):
        """Verify SAST template defines configurable variables"""
        path = os.path.join(
            self.REPO_DIR, self.TEMPLATE_DIR, "SAST.gitlab-ci.yml"
        )
        with open(path) as f:
            content = f.read()

        assert "variables" in content.lower(), (
            "SAST template should define variables"
        )

    def test_dast_has_stage(self):
        """Verify DAST template defines stage assignments"""
        path = os.path.join(
            self.REPO_DIR, self.TEMPLATE_DIR, "DAST.gitlab-ci.yml"
        )
        with open(path) as f:
            content = f.read()

        assert "stage" in content.lower(), (
            "DAST template should define stage assignments"
        )

    def test_dast_has_variables(self):
        """Verify DAST template includes runtime variables"""
        path = os.path.join(
            self.REPO_DIR, self.TEMPLATE_DIR, "DAST.gitlab-ci.yml"
        )
        with open(path) as f:
            content = f.read()

        assert "variables" in content.lower(), (
            "DAST template should define variables"
        )

    def test_dependency_scanning_has_artifacts(self):
        """Verify Dependency Scanning configures artifact collection"""
        path = os.path.join(
            self.REPO_DIR, self.TEMPLATE_DIR,
            "Dependency-Scanning.gitlab-ci.yml",
        )
        with open(path) as f:
            content = f.read()

        artifact_indicators = ["artifacts", "reports", "paths"]
        found = [ind for ind in artifact_indicators if ind in content.lower()]
        assert len(found) >= 1, (
            f"Should configure artifact collection. Found: {found}"
        )

    def test_templates_have_execution_rules(self):
        """Verify templates have execution control (rules/only/when)"""
        for template in [
            "SAST.gitlab-ci.yml",
            "DAST.gitlab-ci.yml",
            "Dependency-Scanning.gitlab-ci.yml",
        ]:
            path = os.path.join(
                self.REPO_DIR, self.TEMPLATE_DIR, template
            )
            with open(path) as f:
                content = f.read()

            rule_indicators = [
                "rules:", "only:", "when:", "allow_failure",
                "except:", "if:",
            ]
            found = [ind for ind in rule_indicators if ind in content]
            assert len(found) >= 1, (
                f"{template} should have execution rules. Found: {found}"
            )

    def test_templates_have_script_or_extends(self):
        """Verify templates define runnable behavior"""
        for template in [
            "SAST.gitlab-ci.yml",
            "DAST.gitlab-ci.yml",
            "Dependency-Scanning.gitlab-ci.yml",
        ]:
            path = os.path.join(
                self.REPO_DIR, self.TEMPLATE_DIR, template
            )
            with open(path) as f:
                content = f.read()

            action_indicators = [
                "script:", "extends:", "include:",
            ]
            found = [ind for ind in action_indicators if ind in content]
            assert len(found) >= 1, (
                f"{template} should have script/extends/include. Found: {found}"
            )

    # === Functional Checks ===

    def test_sast_valid_yaml(self):
        """Verify SAST template is valid YAML"""
        import yaml
        path = os.path.join(
            self.REPO_DIR, self.TEMPLATE_DIR, "SAST.gitlab-ci.yml"
        )
        with open(path) as f:
            try:
                yaml.safe_load(f.read())
            except yaml.YAMLError as e:
                pytest.fail(f"SAST template invalid YAML: {e}")

    def test_dast_valid_yaml(self):
        """Verify DAST template is valid YAML"""
        import yaml
        path = os.path.join(
            self.REPO_DIR, self.TEMPLATE_DIR, "DAST.gitlab-ci.yml"
        )
        with open(path) as f:
            try:
                yaml.safe_load(f.read())
            except yaml.YAMLError as e:
                pytest.fail(f"DAST template invalid YAML: {e}")

    def test_dependency_scanning_valid_yaml(self):
        """Verify Dependency-Scanning template is valid YAML"""
        import yaml
        path = os.path.join(
            self.REPO_DIR, self.TEMPLATE_DIR,
            "Dependency-Scanning.gitlab-ci.yml",
        )
        with open(path) as f:
            try:
                yaml.safe_load(f.read())
            except yaml.YAMLError as e:
                pytest.fail(
                    f"Dependency-Scanning template invalid YAML: {e}"
                )

    def test_templates_separate_concerns(self):
        """Verify templates separate three scanning concerns"""
        templates = {}
        for template in [
            "SAST.gitlab-ci.yml",
            "DAST.gitlab-ci.yml",
            "Dependency-Scanning.gitlab-ci.yml",
        ]:
            path = os.path.join(
                self.REPO_DIR, self.TEMPLATE_DIR, template
            )
            with open(path) as f:
                templates[template] = f.read()

        # Each should focus on its own concern
        assert "sast" in templates["SAST.gitlab-ci.yml"].lower()
        assert "dast" in templates["DAST.gitlab-ci.yml"].lower()
        dep_content = templates["Dependency-Scanning.gitlab-ci.yml"].lower()
        assert "dependency" in dep_content or "scanning" in dep_content
