"""
Test skill: github-actions-templates
Verify that the Agent correctly creates reusable CI/CD workflow templates
for GitHub Actions, including test, Docker publish, deploy, and composite action.
"""

import os
import subprocess
import re
import pytest


class TestGithubActionsTemplates:
    REPO_DIR = "/workspace/starter-workflows"

    # === File Path Checks ===

    def test_reusable_test_workflow_exists(self):
        """Verify that the reusable test workflow file exists"""
        filepath = os.path.join(self.REPO_DIR, "ci/reusable-test.yml")
        assert os.path.exists(filepath), f"reusable-test.yml not found at {filepath}"

    def test_reusable_docker_publish_exists(self):
        """Verify that the reusable Docker publish workflow exists"""
        filepath = os.path.join(self.REPO_DIR, "ci/reusable-docker-publish.yml")
        assert os.path.exists(filepath), f"reusable-docker-publish.yml not found at {filepath}"

    def test_reusable_deploy_exists(self):
        """Verify that the reusable deploy workflow exists"""
        filepath = os.path.join(self.REPO_DIR, "ci/reusable-deploy.yml")
        assert os.path.exists(filepath), f"reusable-deploy.yml not found at {filepath}"

    def test_composite_setup_action_exists(self):
        """Verify that the composite setup action exists"""
        filepath = os.path.join(self.REPO_DIR, "ci/composite-setup/action.yml")
        assert os.path.exists(filepath), f"composite-setup/action.yml not found at {filepath}"

    # === Semantic Checks ===

    def test_reusable_test_is_valid_yaml(self):
        """Verify that reusable-test.yml is valid YAML with correct structure"""
        import yaml
        filepath = os.path.join(self.REPO_DIR, "ci/reusable-test.yml")
        with open(filepath) as f:
            data = yaml.safe_load(f)
        assert data is not None, "reusable-test.yml is empty or invalid YAML"

        # Check for workflow_call trigger
        on_section = data.get("on", data.get(True, {}))
        assert "workflow_call" in on_section or "workflow_call" in str(data.get("on", "")), (
            "reusable-test.yml must use workflow_call trigger"
        )

    def test_reusable_test_has_required_inputs(self):
        """Verify that reusable-test.yml defines required inputs"""
        import yaml
        filepath = os.path.join(self.REPO_DIR, "ci/reusable-test.yml")
        with open(filepath) as f:
            data = yaml.safe_load(f)

        on_section = data.get("on", data.get(True, {}))
        wf_call = on_section.get("workflow_call", {})
        inputs = wf_call.get("inputs", {})

        required_inputs = ["language", "language_versions", "test_command"]
        for inp in required_inputs:
            assert inp in inputs, (
                f"reusable-test.yml missing required input '{inp}'. Found: {list(inputs.keys())}"
            )

    def test_reusable_test_has_matrix_strategy(self):
        """Verify that reusable-test.yml uses matrix strategy"""
        filepath = os.path.join(self.REPO_DIR, "ci/reusable-test.yml")
        with open(filepath) as f:
            content = f.read()

        assert "matrix" in content, (
            "reusable-test.yml does not use matrix strategy. "
            "Expected os × language_version matrix."
        )

    def test_docker_publish_has_required_inputs(self):
        """Verify Docker publish workflow has required inputs"""
        import yaml
        filepath = os.path.join(self.REPO_DIR, "ci/reusable-docker-publish.yml")
        with open(filepath) as f:
            data = yaml.safe_load(f)

        on_section = data.get("on", data.get(True, {}))
        wf_call = on_section.get("workflow_call", {})
        inputs = wf_call.get("inputs", {})

        assert "image_name" in inputs, (
            "reusable-docker-publish.yml missing required input 'image_name'"
        )

    def test_docker_publish_uses_buildx(self):
        """Verify Docker publish workflow uses Docker Buildx for multi-platform builds"""
        filepath = os.path.join(self.REPO_DIR, "ci/reusable-docker-publish.yml")
        with open(filepath) as f:
            content = f.read()

        assert "buildx" in content.lower() or "build-push-action" in content, (
            "reusable-docker-publish.yml should use Docker Buildx or build-push-action"
        )

    def test_deploy_has_health_check_and_rollback(self):
        """Verify deploy workflow implements health check and rollback"""
        filepath = os.path.join(self.REPO_DIR, "ci/reusable-deploy.yml")
        with open(filepath) as f:
            content = f.read()

        has_health_check = "health" in content.lower() or "curl" in content or "wget" in content
        has_rollback = "rollback" in content.lower() or "undo" in content.lower()

        assert has_health_check, (
            "reusable-deploy.yml missing health check logic"
        )
        assert has_rollback, (
            "reusable-deploy.yml missing rollback mechanism"
        )

    def test_workflows_have_permissions(self):
        """Verify all workflows declare permissions at workflow level"""
        import yaml
        workflows = [
            "ci/reusable-test.yml",
            "ci/reusable-docker-publish.yml",
            "ci/reusable-deploy.yml",
        ]
        for wf_path in workflows:
            filepath = os.path.join(self.REPO_DIR, wf_path)
            if not os.path.exists(filepath):
                continue
            with open(filepath) as f:
                data = yaml.safe_load(f)
            assert "permissions" in data, (
                f"{wf_path} missing workflow-level 'permissions' declaration. "
                "All workflows must declare explicit permissions."
            )

    # === Functional Checks ===

    def test_all_workflow_files_are_valid_yaml(self):
        """Verify all workflow YAML files parse without errors"""
        import yaml
        files = [
            "ci/reusable-test.yml",
            "ci/reusable-docker-publish.yml",
            "ci/reusable-deploy.yml",
            "ci/composite-setup/action.yml",
        ]
        for rel_path in files:
            filepath = os.path.join(self.REPO_DIR, rel_path)
            assert os.path.exists(filepath), f"{rel_path} not found"
            with open(filepath) as f:
                try:
                    data = yaml.safe_load(f)
                    assert data is not None, f"{rel_path} parsed to None (empty file)"
                except yaml.YAMLError as e:
                    pytest.fail(f"{rel_path} is not valid YAML: {e}")

    def test_composite_action_supports_languages(self):
        """Verify composite action supports Node.js, Python, and Go"""
        filepath = os.path.join(self.REPO_DIR, "ci/composite-setup/action.yml")
        with open(filepath) as f:
            content = f.read()

        for lang in ["node", "python", "go"]:
            assert lang in content.lower(), (
                f"composite-setup/action.yml missing support for '{lang}'"
            )

    def test_composite_action_has_inputs(self):
        """Verify composite action defines required inputs"""
        import yaml
        filepath = os.path.join(self.REPO_DIR, "ci/composite-setup/action.yml")
        with open(filepath) as f:
            data = yaml.safe_load(f)

        inputs = data.get("inputs", {})
        assert "language" in inputs, "Composite action missing 'language' input"
        assert "language_version" in inputs or "language-version" in inputs, (
            "Composite action missing 'language_version' input"
        )

    def test_no_secret_logging(self):
        """Verify no secrets are echoed in workflow files"""
        files = [
            "ci/reusable-test.yml",
            "ci/reusable-docker-publish.yml",
            "ci/reusable-deploy.yml",
        ]
        for rel_path in files:
            filepath = os.path.join(self.REPO_DIR, rel_path)
            if not os.path.exists(filepath):
                continue
            with open(filepath) as f:
                content = f.read()
            # Check for echo ${{ secrets.* }} patterns
            secret_echo = re.findall(r'echo\s+.*\$\{\{\s*secrets\.', content)
            assert len(secret_echo) == 0, (
                f"Found potential secret logging in {rel_path}: {secret_echo}. "
                "Secrets must never be echoed to logs."
            )

    def test_deploy_has_concurrency(self):
        """Verify deploy workflow has concurrency group to prevent parallel deployments"""
        filepath = os.path.join(self.REPO_DIR, "ci/reusable-deploy.yml")
        with open(filepath) as f:
            content = f.read()

        assert "concurrency" in content, (
            "reusable-deploy.yml missing 'concurrency' configuration. "
            "Deploy workflows must prevent parallel deployments."
        )
