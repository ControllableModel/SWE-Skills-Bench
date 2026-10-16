"""
Test skill: github-actions-templates
Verify that the Agent correctly creates GitHub Actions reusable workflow
templates for a CI/CD pipeline in the starter-workflows repository.
"""

import os
import subprocess
import pytest


class TestGithubActionsTemplates:
    REPO_DIR = "/workspace/starter-workflows"

    CI_WORKFLOW = "ci/python-webapp-ci.yml"
    CD_WORKFLOW = "deployments/python-webapp-deploy.yml"
    SECURITY_WORKFLOW = "code-scanning/python-security-scan.yml"
    REUSABLE_WORKFLOW = "ci/docker-build-reusable.yml"

    def _read_file(self, rel_path):
        filepath = os.path.join(self.REPO_DIR, rel_path)
        with open(filepath) as f:
            return f.read()

    def _load_yaml(self, rel_path):
        import yaml
        filepath = os.path.join(self.REPO_DIR, rel_path)
        with open(filepath) as f:
            return yaml.safe_load(f)

    # === File Path Checks ===

    def test_ci_workflow_exists(self):
        """Verify CI workflow YAML file exists"""
        filepath = os.path.join(self.REPO_DIR, self.CI_WORKFLOW)
        assert os.path.exists(filepath), f"CI workflow not found at {filepath}"

    def test_cd_workflow_exists(self):
        """Verify CD deployment workflow YAML file exists"""
        filepath = os.path.join(self.REPO_DIR, self.CD_WORKFLOW)
        assert os.path.exists(filepath), f"CD workflow not found at {filepath}"

    def test_security_workflow_exists(self):
        """Verify security scan workflow YAML file exists"""
        filepath = os.path.join(self.REPO_DIR, self.SECURITY_WORKFLOW)
        assert os.path.exists(filepath), f"Security workflow not found at {filepath}"

    def test_reusable_workflow_exists(self):
        """Verify reusable Docker build workflow YAML file exists"""
        filepath = os.path.join(self.REPO_DIR, self.REUSABLE_WORKFLOW)
        assert os.path.exists(filepath), f"Reusable workflow not found at {filepath}"

    # === Semantic Checks ===

    def test_ci_workflow_valid_yaml_with_triggers(self):
        """Verify CI workflow is valid YAML with push and pull_request triggers"""
        config = self._load_yaml(self.CI_WORKFLOW)
        assert config is not None, "CI workflow is empty or invalid YAML"
        triggers = config.get("on", {})
        if isinstance(triggers, str):
            triggers = {triggers: None}
        assert "push" in triggers or "pull_request" in triggers, \
            f"CI workflow missing push/pull_request triggers, found: {list(triggers.keys())}"

    def test_ci_workflow_has_lint_test_build_jobs(self):
        """Verify CI workflow defines lint, test, and build jobs"""
        config = self._load_yaml(self.CI_WORKFLOW)
        jobs = config.get("jobs", {})
        job_names = [k.lower() for k in jobs.keys()]
        assert any("lint" in j for j in job_names), \
            f"CI workflow missing lint job. Jobs: {list(jobs.keys())}"
        assert any("test" in j for j in job_names), \
            f"CI workflow missing test job. Jobs: {list(jobs.keys())}"
        assert any("build" in j for j in job_names), \
            f"CI workflow missing build job. Jobs: {list(jobs.keys())}"

    def test_ci_workflow_test_job_has_matrix_strategy(self):
        """Verify test job uses matrix strategy for Python versions"""
        config = self._load_yaml(self.CI_WORKFLOW)
        jobs = config.get("jobs", {})
        test_job = None
        for name, job in jobs.items():
            if "test" in name.lower():
                test_job = job
                break
        assert test_job is not None, "Test job not found"
        strategy = test_job.get("strategy", {})
        matrix = strategy.get("matrix", {})
        assert len(matrix) > 0, "Test job missing matrix strategy"
        # Check for Python version in matrix
        matrix_values = str(matrix)
        assert "3.11" in matrix_values or "3.12" in matrix_values, \
            f"Matrix should include Python 3.11/3.12, got: {matrix}"

    def test_cd_workflow_has_workflow_dispatch(self):
        """Verify CD workflow uses workflow_dispatch with environment input"""
        config = self._load_yaml(self.CD_WORKFLOW)
        triggers = config.get("on", {})
        assert "workflow_dispatch" in triggers, \
            "CD workflow missing workflow_dispatch trigger"
        inputs = triggers.get("workflow_dispatch", {}).get("inputs", {})
        has_env_input = any(
            "environment" in k.lower() or "env" in k.lower()
            for k in inputs.keys()
        )
        assert has_env_input, \
            f"CD workflow missing environment input. Inputs: {list(inputs.keys())}"

    def test_reusable_workflow_uses_workflow_call(self):
        """Verify reusable Docker workflow uses workflow_call trigger"""
        config = self._load_yaml(self.REUSABLE_WORKFLOW)
        triggers = config.get("on", {})
        assert "workflow_call" in triggers, \
            "Reusable workflow missing workflow_call trigger"
        call_config = triggers.get("workflow_call", {})
        inputs = call_config.get("inputs", {})
        assert "image_name" in inputs or any("image" in k for k in inputs), \
            f"Reusable workflow missing image_name input. Inputs: {list(inputs.keys())}"

    def test_security_workflow_has_schedule_trigger(self):
        """Verify security workflow has schedule trigger"""
        config = self._load_yaml(self.SECURITY_WORKFLOW)
        triggers = config.get("on", {})
        assert "schedule" in triggers, \
            "Security workflow missing schedule trigger"

    def test_security_workflow_has_four_scan_jobs(self):
        """Verify security workflow defines 4 independent scan jobs"""
        config = self._load_yaml(self.SECURITY_WORKFLOW)
        jobs = config.get("jobs", {})
        job_names_lower = [k.lower() for k in jobs.keys()]
        scan_keywords = ["audit", "sast", "bandit", "secret", "gitleaks", "sbom", "syft"]
        found_scans = [
            j for j in job_names_lower
            if any(kw in j for kw in scan_keywords)
        ]
        assert len(found_scans) >= 4, \
            f"Expected 4+ scan jobs, found {len(found_scans)}: {found_scans}"

    def test_no_hardcoded_secrets(self):
        """Verify no hardcoded secrets or tokens in workflow files"""
        import re
        for wf in [self.CI_WORKFLOW, self.CD_WORKFLOW,
                    self.SECURITY_WORKFLOW, self.REUSABLE_WORKFLOW]:
            content = self._read_file(wf)
            # Check for hardcoded secrets patterns
            assert not re.search(r'ghp_[A-Za-z0-9]{36}', content), \
                f"Hardcoded GitHub token found in {wf}"
            assert not re.search(r'(password|token|secret)\s*:\s*["\'][^$]', content, re.IGNORECASE), \
                f"Possible hardcoded credential in {wf}"

    # === Functional Checks ===

    def test_ci_workflow_build_depends_on_lint_and_test(self):
        """Verify build job depends on lint and test jobs"""
        config = self._load_yaml(self.CI_WORKFLOW)
        jobs = config.get("jobs", {})
        build_job = None
        for name, job in jobs.items():
            if "build" in name.lower():
                build_job = job
                break
        assert build_job is not None, "Build job not found"
        needs = build_job.get("needs", [])
        if isinstance(needs, str):
            needs = [needs]
        needs_lower = [n.lower() for n in needs]
        assert any("lint" in n for n in needs_lower), \
            f"Build job should need lint job, got needs: {needs}"
        assert any("test" in n for n in needs_lower), \
            f"Build job should need test job, got needs: {needs}"

    def test_reusable_workflow_has_docker_buildx(self):
        """Verify reusable workflow uses Docker Buildx for building"""
        content = self._read_file(self.REUSABLE_WORKFLOW)
        assert "buildx" in content.lower() or "build-push-action" in content, \
            "Reusable workflow missing Docker Buildx setup or build-push-action"

    def test_ci_workflow_has_concurrency(self):
        """Verify CI workflow defines concurrency groups to cancel stale runs"""
        content = self._read_file(self.CI_WORKFLOW)
        assert "concurrency" in content, \
            "CI workflow missing concurrency configuration"

    def test_all_workflows_valid_yaml(self):
        """Verify all workflow files parse as valid YAML without errors"""
        for wf in [self.CI_WORKFLOW, self.CD_WORKFLOW,
                    self.SECURITY_WORKFLOW, self.REUSABLE_WORKFLOW]:
            try:
                data = self._load_yaml(wf)
                assert data is not None, f"{wf} parsed as empty document"
                assert "jobs" in data or "on" in data, \
                    f"{wf} missing 'jobs' or 'on' top-level key"
            except Exception as e:
                pytest.fail(f"{wf} is not valid YAML: {e}")
