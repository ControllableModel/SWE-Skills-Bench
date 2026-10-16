"""
Test skill: github-actions-templates
Verify that the Agent correctly creates a Python CI workflow template
for GitHub Actions with pytest, multi-version matrix, linting, caching,
and coverage handling.
"""

import os
import subprocess
import pytest


class TestGithubActionsTemplates:
    REPO_DIR = "/workspace/starter-workflows"

    # === File Path Checks ===

    def test_workflow_file_exists(self):
        """Verify ci/python-pytest.yml workflow file exists"""
        path = os.path.join(self.REPO_DIR, "ci/python-pytest.yml")
        assert os.path.exists(path), f"python-pytest.yml not found at {path}"

    def test_workflow_is_valid_yaml(self):
        """Verify the workflow file is syntactically valid YAML"""
        try:
            import yaml
        except ImportError:
            subprocess.run(["pip", "install", "pyyaml"], capture_output=True, timeout=60)
            import yaml

        path = os.path.join(self.REPO_DIR, "ci/python-pytest.yml")
        with open(path) as f:
            config = yaml.safe_load(f)
        assert config is not None, "Workflow YAML is empty or invalid"
        assert isinstance(config, dict), "Workflow YAML root should be a mapping"

    # === Semantic Checks ===

    def test_workflow_triggers_on_push_and_pr(self):
        """Verify workflow triggers on push to main and pull requests to main"""
        import yaml
        path = os.path.join(self.REPO_DIR, "ci/python-pytest.yml")
        with open(path) as f:
            config = yaml.safe_load(f)

        # Check for 'on' key (trigger configuration)
        triggers = config.get("on", config.get(True, {}))
        assert triggers is not None, "Workflow should define trigger events under 'on'"

        if isinstance(triggers, dict):
            has_push = "push" in triggers
            has_pr = "pull_request" in triggers or "pull_request_target" in triggers
            assert has_push, "Workflow should trigger on push events"
            assert has_pr, "Workflow should trigger on pull_request events"

            # Verify main branch targeting
            push_config = triggers.get("push", {})
            if isinstance(push_config, dict):
                branches = push_config.get("branches", [])
                branch_str = str(branches).lower()
                assert "main" in branch_str or "master" in branch_str or "$default-branch" in str(branches), (
                    f"Push trigger should target main branch. Branches: {branches}"
                )

    def test_workflow_has_matrix_strategy(self):
        """Verify workflow uses matrix strategy for multiple Python versions"""
        import yaml
        path = os.path.join(self.REPO_DIR, "ci/python-pytest.yml")
        with open(path) as f:
            config = yaml.safe_load(f)

        jobs = config.get("jobs", {})
        assert len(jobs) >= 1, "Workflow should define at least one job"

        matrix_found = False
        python_versions = []
        for job_name, job in jobs.items():
            strategy = job.get("strategy", {})
            matrix = strategy.get("matrix", {})
            if "python-version" in matrix or "python_version" in matrix:
                versions = matrix.get("python-version", matrix.get("python_version", []))
                python_versions = versions
                if len(versions) >= 2:
                    matrix_found = True
                    break

        assert matrix_found, (
            f"Workflow should test across at least 2 Python versions via matrix. "
            f"Python versions found: {python_versions}"
        )

    def test_workflow_has_required_steps(self):
        """Verify workflow includes checkout, setup, install, lint, and test steps"""
        import yaml
        path = os.path.join(self.REPO_DIR, "ci/python-pytest.yml")
        with open(path) as f:
            config = yaml.safe_load(f)

        jobs = config.get("jobs", {})
        all_steps_text = ""
        for job_name, job in jobs.items():
            steps = job.get("steps", [])
            for step in steps:
                uses = str(step.get("uses", "")).lower()
                run_cmd = str(step.get("run", "")).lower()
                name = str(step.get("name", "")).lower()
                all_steps_text += f" {uses} {run_cmd} {name}"

        required = {
            "checkout": "checkout" in all_steps_text,
            "python_setup": "setup-python" in all_steps_text or "python" in all_steps_text,
            "install": "install" in all_steps_text or "pip" in all_steps_text,
            "lint": "lint" in all_steps_text or "flake8" in all_steps_text or "ruff" in all_steps_text or "pylint" in all_steps_text,
            "test": "pytest" in all_steps_text or "test" in all_steps_text,
        }
        found = [k for k, v in required.items() if v]
        assert len(found) >= 4, (
            f"Workflow should include checkout, python setup, install, lint, and test. "
            f"Found: {found}"
        )

    def test_workflow_pins_action_versions(self):
        """Verify workflow pins action versions to specific tags"""
        import yaml
        path = os.path.join(self.REPO_DIR, "ci/python-pytest.yml")
        with open(path) as f:
            config = yaml.safe_load(f)

        jobs = config.get("jobs", {})
        floating_tags = []
        for job_name, job in jobs.items():
            for step in job.get("steps", []):
                uses = step.get("uses", "")
                if uses and "@" in uses:
                    tag = uses.split("@")[-1]
                    if tag in ("latest", "main", "master"):
                        floating_tags.append(uses)

        assert len(floating_tags) == 0, (
            f"Action versions should be pinned, not floating. "
            f"Floating tags found: {floating_tags}"
        )

    def test_workflow_configures_caching(self):
        """Verify workflow caches pip dependencies"""
        import yaml
        path = os.path.join(self.REPO_DIR, "ci/python-pytest.yml")
        with open(path) as f:
            content = f.read()

        cache_indicators = [
            "cache", "actions/cache", "setup-python",
            "pip cache", "cache: pip",
        ]
        config = yaml.safe_load(content)
        found = [ind for ind in cache_indicators if ind.lower() in content.lower()]
        assert len(found) >= 1, (
            f"Workflow should configure dependency caching. "
            f"None of {cache_indicators} found."
        )

    def test_workflow_handles_coverage(self):
        """Verify workflow handles test coverage (artifact or report)"""
        path = os.path.join(self.REPO_DIR, "ci/python-pytest.yml")
        with open(path) as f:
            content = f.read().lower()

        coverage_indicators = [
            "coverage", "cov", "--cov", "upload-artifact",
            "codecov", "coveralls",
        ]
        found = [ind for ind in coverage_indicators if ind in content]
        assert len(found) >= 1, (
            f"Workflow should handle coverage reporting. "
            f"None of {coverage_indicators} found."
        )

    # === Functional Checks ===

    def test_workflow_yaml_validates_structure(self):
        """Verify workflow has valid GitHub Actions structure"""
        import yaml
        path = os.path.join(self.REPO_DIR, "ci/python-pytest.yml")
        with open(path) as f:
            config = yaml.safe_load(f)

        # Must have 'on' and 'jobs' at minimum
        assert "on" in config or True in config, (
            f"Workflow must have 'on' trigger section. Keys: {list(config.keys())}"
        )
        assert "jobs" in config, (
            f"Workflow must have 'jobs' section. Keys: {list(config.keys())}"
        )

        jobs = config["jobs"]
        for job_name, job in jobs.items():
            assert "runs-on" in job, (
                f"Job '{job_name}' must specify 'runs-on'"
            )
            assert "steps" in job, (
                f"Job '{job_name}' must have 'steps'"
            )
            assert isinstance(job["steps"], list), (
                f"Job '{job_name}' steps should be a list"
            )
            assert len(job["steps"]) >= 3, (
                f"Job '{job_name}' should have at least 3 steps, "
                f"found {len(job['steps'])}"
            )

    def test_workflow_runs_on_ubuntu(self):
        """Verify job runs on ubuntu-latest"""
        import yaml
        path = os.path.join(self.REPO_DIR, "ci/python-pytest.yml")
        with open(path) as f:
            config = yaml.safe_load(f)

        jobs = config.get("jobs", {})
        for job_name, job in jobs.items():
            runs_on = str(job.get("runs-on", "")).lower()
            assert "ubuntu" in runs_on, (
                f"Job '{job_name}' should run on ubuntu. runs-on: {job.get('runs-on')}"
            )

    def test_yaml_no_syntax_issues_with_actionlint(self):
        """Verify YAML file has no obvious structural issues"""
        import yaml
        path = os.path.join(self.REPO_DIR, "ci/python-pytest.yml")
        with open(path) as f:
            config = yaml.safe_load(f)

        # Verify no empty jobs
        jobs = config.get("jobs", {})
        for job_name, job in jobs.items():
            steps = job.get("steps", [])
            for i, step in enumerate(steps):
                assert isinstance(step, dict), (
                    f"Step {i} in job '{job_name}' should be a mapping, got {type(step)}"
                )
                # Each step should have either 'uses' or 'run'
                has_action = "uses" in step or "run" in step
                assert has_action, (
                    f"Step {i} in job '{job_name}' should have 'uses' or 'run': {step}"
                )
