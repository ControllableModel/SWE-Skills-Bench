"""
Test skill: github-actions-templates
Verify that the Agent correctly creates GitHub Actions CI/CD workflows
for a full-stack TypeScript application with matrix builds, Docker, and deployment.
"""

import os
import re
import subprocess
import pytest

try:
    import yaml
except ImportError:
    yaml = None


class TestGithubActionsTemplates:
    REPO_DIR = "/workspace/starter-workflows"

    @staticmethod
    def _load_yaml(path):
        """Helper to load YAML file safely"""
        if yaml is None:
            subprocess.run(
                ["pip", "install", "pyyaml"],
                capture_output=True, text=True, timeout=30,
            )
            import yaml as _yaml
            with open(path, "r") as f:
                return _yaml.safe_load(f)
        with open(path, "r") as f:
            return yaml.safe_load(f)

    # === File Path Checks ===

    def test_ci_workflow_exists(self):
        """Verify that CI workflow file exists"""
        path = os.path.join(self.REPO_DIR, ".github/workflows/ci.yml")
        alt = os.path.join(self.REPO_DIR, ".github/workflows/ci.yaml")
        assert os.path.exists(path) or os.path.exists(alt), (
            "CI workflow file not found at .github/workflows/ci.yml"
        )

    def test_build_push_workflow_exists(self):
        """Verify that build-push workflow file exists"""
        path = os.path.join(self.REPO_DIR, ".github/workflows/build-push.yml")
        alt = os.path.join(self.REPO_DIR, ".github/workflows/build-push.yaml")
        assert os.path.exists(path) or os.path.exists(alt), (
            "Build-push workflow file not found"
        )

    def test_deploy_workflow_exists(self):
        """Verify that deploy workflow file exists"""
        path = os.path.join(self.REPO_DIR, ".github/workflows/deploy.yml")
        alt = os.path.join(self.REPO_DIR, ".github/workflows/deploy.yaml")
        assert os.path.exists(path) or os.path.exists(alt), (
            "Deploy workflow file not found"
        )

    def test_security_workflow_exists(self):
        """Verify that security scan workflow file exists"""
        path = os.path.join(self.REPO_DIR, ".github/workflows/security.yml")
        alt = os.path.join(self.REPO_DIR, ".github/workflows/security.yaml")
        assert os.path.exists(path) or os.path.exists(alt), (
            "Security workflow file not found"
        )

    def test_composite_action_exists(self):
        """Verify that composite setup-node action exists"""
        path = os.path.join(self.REPO_DIR, ".github/actions/setup-node/action.yml")
        alt = os.path.join(self.REPO_DIR, ".github/actions/setup-node/action.yaml")
        assert os.path.exists(path) or os.path.exists(alt), (
            "Composite action not found at .github/actions/setup-node/action.yml"
        )

    # === Semantic Checks ===

    def test_ci_workflow_has_matrix_strategy(self):
        """Verify that CI workflow uses matrix strategy with Node 18.x and 20.x"""
        ci_path = None
        for ext in ["yml", "yaml"]:
            p = os.path.join(self.REPO_DIR, f".github/workflows/ci.{ext}")
            if os.path.exists(p):
                ci_path = p
                break
        assert ci_path is not None
        with open(ci_path, "r") as f:
            content = f.read()

        assert "matrix" in content, "CI workflow should use matrix strategy"
        assert "18" in content, "Matrix should include Node 18.x"
        assert "20" in content, "Matrix should include Node 20.x"

    def test_ci_workflow_has_lint_test_build_jobs(self):
        """Verify that CI workflow defines lint, test, and build jobs"""
        ci_path = None
        for ext in ["yml", "yaml"]:
            p = os.path.join(self.REPO_DIR, f".github/workflows/ci.{ext}")
            if os.path.exists(p):
                ci_path = p
                break
        assert ci_path is not None
        with open(ci_path, "r") as f:
            content = f.read()

        assert "lint" in content, "CI workflow missing lint job"
        assert "test" in content, "CI workflow missing test job"
        assert "build" in content, "CI workflow missing build job"

    def test_ci_workflow_has_concurrency(self):
        """Verify that CI workflow has concurrency settings to cancel in-progress runs"""
        ci_path = None
        for ext in ["yml", "yaml"]:
            p = os.path.join(self.REPO_DIR, f".github/workflows/ci.{ext}")
            if os.path.exists(p):
                ci_path = p
                break
        assert ci_path is not None
        with open(ci_path, "r") as f:
            content = f.read()

        assert "concurrency" in content, "CI workflow should have concurrency settings"
        assert "cancel-in-progress" in content, (
            "CI workflow should cancel in-progress runs"
        )

    def test_build_push_uses_ghcr(self):
        """Verify that build-push workflow pushes to GitHub Container Registry"""
        bp_path = None
        for ext in ["yml", "yaml"]:
            p = os.path.join(self.REPO_DIR, f".github/workflows/build-push.{ext}")
            if os.path.exists(p):
                bp_path = p
                break
        assert bp_path is not None
        with open(bp_path, "r") as f:
            content = f.read()

        assert "ghcr.io" in content, (
            "Build-push workflow should push to GHCR (ghcr.io)"
        )
        assert "docker" in content.lower(), (
            "Build-push workflow should use Docker build actions"
        )

    def test_build_push_has_docker_cache(self):
        """Verify that Docker build uses GitHub Actions cache"""
        bp_path = None
        for ext in ["yml", "yaml"]:
            p = os.path.join(self.REPO_DIR, f".github/workflows/build-push.{ext}")
            if os.path.exists(p):
                bp_path = p
                break
        assert bp_path is not None
        with open(bp_path, "r") as f:
            content = f.read()

        assert "cache" in content.lower(), (
            "Build-push should use Docker build cache (type=gha)"
        )

    def test_deploy_has_staging_and_production(self):
        """Verify that deploy workflow has both staging and production environments"""
        dp_path = None
        for ext in ["yml", "yaml"]:
            p = os.path.join(self.REPO_DIR, f".github/workflows/deploy.{ext}")
            if os.path.exists(p):
                dp_path = p
                break
        assert dp_path is not None
        with open(dp_path, "r") as f:
            content = f.read()

        assert "staging" in content, "Deploy workflow missing staging environment"
        assert "production" in content, "Deploy workflow missing production environment"

    def test_deploy_production_has_approval(self):
        """Verify that production deployment requires approval"""
        dp_path = None
        for ext in ["yml", "yaml"]:
            p = os.path.join(self.REPO_DIR, f".github/workflows/deploy.{ext}")
            if os.path.exists(p):
                dp_path = p
                break
        assert dp_path is not None
        with open(dp_path, "r") as f:
            content = f.read()

        has_approval = any(kw in content for kw in [
            "environment", "workflow_dispatch", "reviewers",
        ])
        assert has_approval, (
            "Production deploy should use environment protection or workflow_dispatch"
        )

    def test_security_workflow_has_schedule(self):
        """Verify that security workflow runs on weekly schedule"""
        sec_path = None
        for ext in ["yml", "yaml"]:
            p = os.path.join(self.REPO_DIR, f".github/workflows/security.{ext}")
            if os.path.exists(p):
                sec_path = p
                break
        assert sec_path is not None
        with open(sec_path, "r") as f:
            content = f.read()

        assert "schedule" in content, "Security workflow should run on schedule"
        assert "cron" in content, "Security workflow should have cron trigger"

    def test_security_workflow_has_trivy_and_codeql(self):
        """Verify that security workflow includes Trivy and CodeQL scans"""
        sec_path = None
        for ext in ["yml", "yaml"]:
            p = os.path.join(self.REPO_DIR, f".github/workflows/security.{ext}")
            if os.path.exists(p):
                sec_path = p
                break
        assert sec_path is not None
        with open(sec_path, "r") as f:
            content = f.read()

        assert "trivy" in content.lower(), "Security workflow should include Trivy scan"
        assert "codeql" in content.lower(), "Security workflow should include CodeQL analysis"

    # === Functional Checks ===

    def test_ci_workflow_is_valid_yaml(self):
        """Verify that CI workflow is valid YAML"""
        ci_path = None
        for ext in ["yml", "yaml"]:
            p = os.path.join(self.REPO_DIR, f".github/workflows/ci.{ext}")
            if os.path.exists(p):
                ci_path = p
                break
        assert ci_path is not None
        data = self._load_yaml(ci_path)
        assert data is not None, "CI workflow YAML is empty"
        assert "on" in data or True in data, "CI workflow missing trigger definition"
        assert "jobs" in data, "CI workflow missing jobs definition"

    def test_all_workflows_are_valid_yaml(self):
        """Verify that all workflow files are valid YAML"""
        workflow_dir = os.path.join(self.REPO_DIR, ".github/workflows")
        if not os.path.exists(workflow_dir):
            pytest.skip("Workflow directory not found")

        for filename in os.listdir(workflow_dir):
            if filename.endswith((".yml", ".yaml")):
                filepath = os.path.join(workflow_dir, filename)
                data = self._load_yaml(filepath)
                assert data is not None, f"{filename} is empty or invalid"

    def test_composite_action_is_valid(self):
        """Verify that composite action has required structure"""
        act_path = None
        for ext in ["yml", "yaml"]:
            p = os.path.join(self.REPO_DIR, f".github/actions/setup-node/action.{ext}")
            if os.path.exists(p):
                act_path = p
                break
        assert act_path is not None
        data = self._load_yaml(act_path)
        assert data is not None, "Composite action YAML is empty"
        assert "runs" in data, "Composite action missing 'runs' definition"
        runs = data["runs"]
        assert runs.get("using") == "composite", (
            "Action should have using: composite"
        )
        assert "steps" in runs, "Composite action missing steps"
