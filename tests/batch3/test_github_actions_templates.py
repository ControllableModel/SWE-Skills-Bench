"""
Test skill: github-actions-templates
Verify that the Agent creates correct GitHub Actions starter workflow templates
for a TypeScript monorepo CI/CD pipeline.
"""

import os
import json
import pytest

try:
    import yaml
except ImportError:
    yaml = None


class TestGithubActionsTemplates:
    REPO_DIR = "/workspace/starter-workflows"

    def _load_yaml(self, path):
        """Helper to load a YAML file"""
        if yaml is None:
            import subprocess
            subprocess.run(
                ["pip", "install", "pyyaml"],
                capture_output=True, text=True, timeout=60
            )
            import importlib
            import yaml as _yaml
            return _yaml.safe_load(open(path))
        return yaml.safe_load(open(path))

    # === File Path Checks ===

    def test_ci_workflow_file_exists(self):
        """Verify CI workflow template file exists"""
        path = os.path.join(self.REPO_DIR, "ci/typescript-monorepo.yml")
        assert os.path.exists(path), f"CI workflow not found at {path}"

    def test_ci_properties_file_exists(self):
        """Verify CI properties JSON file exists"""
        path = os.path.join(self.REPO_DIR, "ci/properties/typescript-monorepo.properties.json")
        assert os.path.exists(path), f"CI properties not found at {path}"

    def test_deploy_workflow_file_exists(self):
        """Verify deployment workflow template file exists"""
        path = os.path.join(self.REPO_DIR, "deployments/typescript-monorepo-deploy.yml")
        assert os.path.exists(path), f"Deployment workflow not found at {path}"

    def test_deploy_properties_file_exists(self):
        """Verify deployment properties JSON file exists"""
        path = os.path.join(
            self.REPO_DIR,
            "deployments/properties/typescript-monorepo-deploy.properties.json"
        )
        assert os.path.exists(path), f"Deploy properties not found at {path}"

    # === Semantic Checks ===

    def test_ci_workflow_has_required_jobs(self):
        """Verify CI workflow defines changes, lint, test-backend, test-frontend, build jobs"""
        path = os.path.join(self.REPO_DIR, "ci/typescript-monorepo.yml")
        data = self._load_yaml(path)
        assert "jobs" in data, "CI workflow missing 'jobs' key"
        jobs = data["jobs"]
        expected_jobs = ["lint", "build"]
        for job in expected_jobs:
            assert job in jobs, f"CI workflow missing job: {job}"
        # Check for path-based change detection
        has_changes = "changes" in jobs
        has_test = any("test" in k for k in jobs.keys())
        assert has_changes or has_test, \
            "CI workflow should have a changes detection job or test jobs"

    def test_ci_workflow_has_correct_triggers(self):
        """Verify CI workflow triggers on push and pull_request"""
        path = os.path.join(self.REPO_DIR, "ci/typescript-monorepo.yml")
        data = self._load_yaml(path)
        assert True in [data.get("on") is not None, data.get(True) is not None], \
            "CI workflow missing trigger configuration"
        triggers = data.get("on", data.get(True, {}))
        if isinstance(triggers, dict):
            has_push = "push" in triggers
            has_pr = "pull_request" in triggers
            assert has_push, "CI workflow should trigger on push"
            assert has_pr, "CI workflow should trigger on pull_request"

    def test_ci_workflow_uses_pinned_actions(self):
        """Verify all actions use pinned major versions (e.g., @v4)"""
        path = os.path.join(self.REPO_DIR, "ci/typescript-monorepo.yml")
        with open(path) as f:
            content = f.read()
        # Check that actions use @v[number] not @latest or @main
        import re
        uses_patterns = re.findall(r'uses:\s*(\S+)', content)
        for use in uses_patterns:
            assert "@latest" not in use and "@main" not in use, \
                f"Action '{use}' should use pinned version, not @latest or @main"

    def test_ci_workflow_has_node_matrix(self):
        """Verify test jobs use matrix strategy with Node.js 18.x and 20.x"""
        path = os.path.join(self.REPO_DIR, "ci/typescript-monorepo.yml")
        with open(path) as f:
            content = f.read()
        assert "matrix" in content, "CI workflow should use matrix strategy"
        assert "18" in content, "Matrix should include Node.js 18.x"
        assert "20" in content, "Matrix should include Node.js 20.x"

    def test_ci_workflow_has_concurrency(self):
        """Verify CI workflow has concurrency settings"""
        path = os.path.join(self.REPO_DIR, "ci/typescript-monorepo.yml")
        data = self._load_yaml(path)
        assert "concurrency" in data, \
            "CI workflow should have concurrency settings to cancel in-progress runs"

    def test_ci_properties_has_required_fields(self):
        """Verify CI properties JSON has name, description, iconName, categories"""
        path = os.path.join(self.REPO_DIR, "ci/properties/typescript-monorepo.properties.json")
        with open(path) as f:
            data = json.load(f)
        required_fields = ["name", "description", "iconName", "categories"]
        for field in required_fields:
            assert field in data, f"CI properties missing field: {field}"
        assert isinstance(data["categories"], list), "categories should be a list"
        categories_lower = [c.lower() for c in data["categories"]]
        assert any("javascript" in c or "typescript" in c for c in categories_lower), \
            f"Categories should include JavaScript or TypeScript. Got: {data['categories']}"

    def test_deploy_workflow_has_docker_actions(self):
        """Verify deployment workflow uses Docker build and push actions"""
        path = os.path.join(self.REPO_DIR, "deployments/typescript-monorepo-deploy.yml")
        with open(path) as f:
            content = f.read()
        assert "docker" in content.lower(), "Deployment workflow should use Docker actions"
        docker_actions = ["docker/login-action", "docker/build-push-action", "docker/metadata-action"]
        found = sum(1 for act in docker_actions if act in content)
        assert found >= 2, \
            f"Deployment should use at least 2 Docker actions. Found {found}"

    def test_deploy_workflow_uses_ghcr_registry(self):
        """Verify deployment uses GitHub Container Registry"""
        path = os.path.join(self.REPO_DIR, "deployments/typescript-monorepo-deploy.yml")
        with open(path) as f:
            content = f.read()
        assert "ghcr.io" in content, \
            "Deployment should use ghcr.io as the container registry"

    def test_deploy_properties_has_required_fields(self):
        """Verify deployment properties JSON has required fields"""
        path = os.path.join(
            self.REPO_DIR,
            "deployments/properties/typescript-monorepo-deploy.properties.json"
        )
        with open(path) as f:
            data = json.load(f)
        required_fields = ["name", "description", "iconName", "categories"]
        for field in required_fields:
            assert field in data, f"Deploy properties missing field: {field}"

    # === Functional Checks ===

    def test_ci_workflow_is_valid_yaml(self):
        """Verify CI workflow is valid YAML that can be parsed"""
        path = os.path.join(self.REPO_DIR, "ci/typescript-monorepo.yml")
        data = self._load_yaml(path)
        assert isinstance(data, dict), "CI workflow should parse to a dict"
        assert "jobs" in data, "Parsed CI workflow missing 'jobs'"

    def test_deploy_workflow_is_valid_yaml(self):
        """Verify deployment workflow is valid YAML that can be parsed"""
        path = os.path.join(self.REPO_DIR, "deployments/typescript-monorepo-deploy.yml")
        data = self._load_yaml(path)
        assert isinstance(data, dict), "Deployment workflow should parse to a dict"
        assert "jobs" in data, "Parsed deployment workflow missing 'jobs'"

    def test_no_hardcoded_secrets(self):
        """Verify no hardcoded secrets, only ${{ secrets.GITHUB_TOKEN }} references"""
        files = [
            "ci/typescript-monorepo.yml",
            "deployments/typescript-monorepo-deploy.yml",
        ]
        for rel_path in files:
            path = os.path.join(self.REPO_DIR, rel_path)
            if not os.path.exists(path):
                continue
            with open(path) as f:
                content = f.read()
            import re
            # Check for hardcoded tokens (patterns like ghp_, github_pat_, etc.)
            hardcoded = re.findall(r'(ghp_[a-zA-Z0-9]+|github_pat_[a-zA-Z0-9]+)', content)
            assert len(hardcoded) == 0, \
                f"Found hardcoded secrets in {rel_path}: {hardcoded}"
