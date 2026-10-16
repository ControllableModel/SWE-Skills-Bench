"""
Test skill: github-actions-templates
Verify that the Agent correctly creates CI/CD starter workflow templates
for a full-stack Node.js application in the starter-workflows repository.
"""

import os
import pytest


class TestGithubActionsTemplates:
    REPO_DIR = "/workspace/starter-workflows"

    def _load_yaml(self, rel_path):
        """Helper to load and parse a YAML workflow file."""
        import yaml
        path = os.path.join(self.REPO_DIR, rel_path)
        assert os.path.exists(path), f"Workflow file not found: {path}"
        with open(path) as f:
            data = yaml.safe_load(f)
        assert data is not None, f"{rel_path} is empty or invalid YAML"
        return data

    # === File Path Checks ===

    def test_ci_workflow_exists(self):
        """Verify ci/node-fullstack-ci.yml was created"""
        path = os.path.join(self.REPO_DIR, "ci/node-fullstack-ci.yml")
        assert os.path.exists(path), f"CI workflow not found at {path}"

    def test_deploy_workflow_exists(self):
        """Verify deployments/docker-ghcr-deploy.yml was created"""
        path = os.path.join(self.REPO_DIR, "deployments/docker-ghcr-deploy.yml")
        assert os.path.exists(path), f"Deploy workflow not found at {path}"

    def test_release_workflow_exists(self):
        """Verify automation/release-please.yml was created"""
        path = os.path.join(self.REPO_DIR, "automation/release-please.yml")
        assert os.path.exists(path), f"Release workflow not found at {path}"

    def test_all_workflows_are_valid_yaml(self):
        """Verify all three workflow files parse as valid YAML"""
        import yaml
        files = [
            "ci/node-fullstack-ci.yml",
            "deployments/docker-ghcr-deploy.yml",
            "automation/release-please.yml",
        ]
        for f in files:
            path = os.path.join(self.REPO_DIR, f)
            if os.path.exists(path):
                with open(path) as fh:
                    data = yaml.safe_load(fh)
                assert data is not None, f"{f} is empty or invalid YAML"

    # === Semantic Checks: CI Workflow ===

    def test_ci_has_matrix_strategy(self):
        """Verify CI workflow defines a matrix with node-version and os"""
        data = self._load_yaml("ci/node-fullstack-ci.yml")
        jobs = data.get("jobs", {})
        test_job = jobs.get("test", {})
        strategy = test_job.get("strategy", {})
        matrix = strategy.get("matrix", {})
        node_versions = matrix.get("node-version", [])
        os_list = matrix.get("os", [])
        assert len(node_versions) >= 3, (
            f"Expected at least 3 Node.js versions, got {node_versions}"
        )
        assert len(os_list) >= 2, (
            f"Expected at least 2 OS targets, got {os_list}"
        )

    def test_ci_has_fail_fast_false(self):
        """Verify CI matrix strategy has fail-fast: false"""
        data = self._load_yaml("ci/node-fullstack-ci.yml")
        jobs = data.get("jobs", {})
        test_job = jobs.get("test", {})
        strategy = test_job.get("strategy", {})
        assert strategy.get("fail-fast") is False, (
            "CI matrix strategy should have fail-fast: false"
        )

    def test_ci_test_job_has_required_steps(self):
        """Verify CI test job includes checkout, setup-node, npm ci, lint, test steps"""
        data = self._load_yaml("ci/node-fullstack-ci.yml")
        jobs = data.get("jobs", {})
        test_job = jobs.get("test", {})
        steps = test_job.get("steps", [])
        step_uses = [s.get("uses", "") for s in steps]
        step_runs = [s.get("run", "") for s in steps]
        all_text = " ".join(step_uses + step_runs)
        assert "actions/checkout" in all_text, "Missing actions/checkout step"
        assert "actions/setup-node" in all_text, "Missing actions/setup-node step"
        assert "npm ci" in all_text, "Missing npm ci step"
        assert "lint" in all_text, "Missing lint step"
        assert "test" in all_text, "Missing test step"

    def test_ci_build_job_depends_on_test(self):
        """Verify CI build job has needs: [test]"""
        data = self._load_yaml("ci/node-fullstack-ci.yml")
        jobs = data.get("jobs", {})
        build_job = jobs.get("build", {})
        needs = build_job.get("needs", [])
        if isinstance(needs, str):
            needs = [needs]
        assert "test" in needs, (
            f"build job should need 'test', got needs: {needs}"
        )

    def test_ci_uses_pinned_action_versions(self):
        """Verify all action references use pinned versions (e.g., @v4)"""
        import re
        data = self._load_yaml("ci/node-fullstack-ci.yml")
        jobs = data.get("jobs", {})
        for job_name, job in jobs.items():
            for step in job.get("steps", []):
                uses = step.get("uses", "")
                if uses and "@" in uses:
                    version = uses.split("@")[-1]
                    assert version not in ("latest", "main", "master"), (
                        f"Job '{job_name}' uses unpinned action: {uses}"
                    )

    # === Semantic Checks: Deploy Workflow ===

    def test_deploy_has_ghcr_registry(self):
        """Verify deploy workflow sets REGISTRY env to ghcr.io"""
        data = self._load_yaml("deployments/docker-ghcr-deploy.yml")
        env = data.get("env", {})
        assert env.get("REGISTRY") == "ghcr.io", (
            f"Expected REGISTRY: ghcr.io, got {env.get('REGISTRY')}"
        )

    def test_deploy_has_build_and_push_job(self):
        """Verify deploy workflow has build-and-push job with correct permissions"""
        data = self._load_yaml("deployments/docker-ghcr-deploy.yml")
        jobs = data.get("jobs", {})
        bp_job = jobs.get("build-and-push", {})
        assert bp_job, "Missing 'build-and-push' job"
        permissions = bp_job.get("permissions", {})
        assert permissions.get("packages") == "write", (
            "build-and-push job needs packages: write permission"
        )

    def test_deploy_uses_docker_actions(self):
        """Verify deploy workflow uses docker/login-action, metadata-action, build-push-action"""
        data = self._load_yaml("deployments/docker-ghcr-deploy.yml")
        jobs = data.get("jobs", {})
        bp_job = jobs.get("build-and-push", {})
        steps = bp_job.get("steps", [])
        step_uses = [s.get("uses", "") for s in steps]
        all_uses = " ".join(step_uses)
        assert "docker/login-action" in all_uses, "Missing docker/login-action"
        assert "docker/metadata-action" in all_uses, "Missing docker/metadata-action"
        assert "docker/build-push-action" in all_uses, "Missing docker/build-push-action"

    def test_deploy_staging_needs_build(self):
        """Verify deploy-staging job depends on build-and-push"""
        data = self._load_yaml("deployments/docker-ghcr-deploy.yml")
        jobs = data.get("jobs", {})
        staging = jobs.get("deploy-staging", {})
        if staging:
            needs = staging.get("needs", [])
            if isinstance(needs, str):
                needs = [needs]
            assert "build-and-push" in needs, (
                f"deploy-staging should need build-and-push, got {needs}"
            )

    # === Semantic Checks: Release Workflow ===

    def test_release_triggers_on_version_tags(self):
        """Verify release workflow triggers on version tags"""
        data = self._load_yaml("automation/release-please.yml")
        on_trigger = data.get("on", data.get(True, {}))
        push = on_trigger.get("push", {}) if isinstance(on_trigger, dict) else {}
        tags = push.get("tags", [])
        tag_str = str(tags)
        assert "v" in tag_str, (
            f"Release workflow should trigger on version tags (v*), got {tags}"
        )

    def test_release_creates_github_release(self):
        """Verify release workflow uses softprops/action-gh-release or similar"""
        data = self._load_yaml("automation/release-please.yml")
        jobs = data.get("jobs", {})
        release_job = jobs.get("release", {})
        steps = release_job.get("steps", [])
        step_uses = [s.get("uses", "") for s in steps]
        all_uses = " ".join(step_uses)
        assert "gh-release" in all_uses or "release" in all_uses.lower(), (
            "Release workflow should use an action to create GitHub releases"
        )

    def test_release_no_hardcoded_secrets(self):
        """Verify no workflow file contains hardcoded credentials"""
        import re
        files = [
            "ci/node-fullstack-ci.yml",
            "deployments/docker-ghcr-deploy.yml",
            "automation/release-please.yml",
        ]
        for f in files:
            path = os.path.join(self.REPO_DIR, f)
            if not os.path.exists(path):
                continue
            with open(path) as fh:
                content = fh.read()
            # Check for hardcoded tokens/passwords
            assert not re.search(r'ghp_[a-zA-Z0-9]{36}', content), (
                f"{f} contains a hardcoded GitHub token"
            )
            assert not re.search(r'password:\s*["\'][^$]', content), (
                f"{f} may contain a hardcoded password"
            )
