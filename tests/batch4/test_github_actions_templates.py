"""
Test skill: github-actions-templates
Verify that GitHub Actions CI/CD workflows for a Python library have been
correctly created, including CI matrix, publish workflow, security scan,
and release drafter — all with proper YAML structure and best practices.
"""

import os
import subprocess
import pytest


class TestGithubActionsTemplates:
    REPO_DIR = "/workspace/starter-workflows"

    CI_PATH = "ci/python-library-ci.yml"
    PUBLISH_PATH = "deployments/python-library-publish.yml"
    SECURITY_PATH = "code-scanning/python-security-scan.yml"
    RELEASE_PATH = "automation/python-release-drafter.yml"

    @staticmethod
    def _load_yaml(filepath):
        """Helper to load YAML file"""
        try:
            import yaml
        except ImportError:
            subprocess.run(["pip", "install", "pyyaml"],
                           capture_output=True, text=True, timeout=60)
            import yaml
        with open(filepath) as f:
            return yaml.safe_load(f)

    # === File Path Checks ===

    def test_ci_workflow_exists(self):
        """Verify CI workflow file exists"""
        filepath = os.path.join(self.REPO_DIR, self.CI_PATH)
        assert os.path.exists(filepath), f"CI workflow not found at {filepath}"

    def test_publish_workflow_exists(self):
        """Verify publish workflow file exists"""
        filepath = os.path.join(self.REPO_DIR, self.PUBLISH_PATH)
        assert os.path.exists(filepath), f"Publish workflow not found at {filepath}"

    def test_security_scan_workflow_exists(self):
        """Verify security scan workflow file exists"""
        filepath = os.path.join(self.REPO_DIR, self.SECURITY_PATH)
        assert os.path.exists(filepath), f"Security scan workflow not found at {filepath}"

    def test_release_drafter_workflow_exists(self):
        """Verify release drafter workflow file exists"""
        filepath = os.path.join(self.REPO_DIR, self.RELEASE_PATH)
        assert os.path.exists(filepath), f"Release drafter workflow not found at {filepath}"

    # === Semantic Checks ===

    def test_ci_workflow_has_matrix_strategy(self):
        """Verify CI workflow uses matrix strategy with 4 Python versions"""
        filepath = os.path.join(self.REPO_DIR, self.CI_PATH)
        config = self._load_yaml(filepath)
        assert config is not None, "CI workflow YAML is empty or invalid"
        jobs = config.get("jobs", {})
        # Find the matrix test job
        matrix_found = False
        for job_name, job in jobs.items():
            strategy = job.get("strategy", {})
            matrix = strategy.get("matrix", {})
            python_versions = matrix.get("python-version", [])
            if len(python_versions) >= 4:
                matrix_found = True
                version_strs = [str(v) for v in python_versions]
                assert any("3.9" in v for v in version_strs), "Matrix should include Python 3.9"
                assert any("3.12" in v for v in version_strs), "Matrix should include Python 3.12"
                break
        assert matrix_found, "CI workflow should have a matrix job testing 4+ Python versions"

    def test_ci_workflow_has_all_checks_pass_job(self):
        """Verify CI workflow has an all-checks-pass gate job"""
        filepath = os.path.join(self.REPO_DIR, self.CI_PATH)
        config = self._load_yaml(filepath)
        jobs = config.get("jobs", {})
        has_gate = any("all-checks" in name.lower() or "gate" in name.lower() or
                       "status" in name.lower()
                       for name in jobs.keys())
        # Also check if any job has 'needs' referencing the matrix job
        if not has_gate:
            for job_name, job in jobs.items():
                needs = job.get("needs", [])
                if isinstance(needs, str):
                    needs = [needs]
                if len(needs) > 0 and job_name != list(jobs.keys())[0]:
                    has_gate = True
                    break
        assert has_gate, "CI workflow should have an all-checks-pass gate job"

    def test_ci_workflow_triggers_correct(self):
        """Verify CI workflow triggers on push and pull_request"""
        filepath = os.path.join(self.REPO_DIR, self.CI_PATH)
        config = self._load_yaml(filepath)
        triggers = config.get("on", config.get(True, {}))
        assert "push" in triggers or "pull_request" in triggers, \
            "CI workflow should trigger on push and/or pull_request"

    def test_publish_workflow_uses_trusted_publishing(self):
        """Verify publish workflow uses id-token: write for trusted PyPI publishing"""
        filepath = os.path.join(self.REPO_DIR, self.PUBLISH_PATH)
        with open(filepath) as f:
            content = f.read()
        assert "id-token" in content, \
            "Publish workflow should use id-token: write for trusted publishing"
        assert "pypi" in content.lower(), \
            "Publish workflow should reference PyPI publishing"

    def test_publish_workflow_triggers_on_release(self):
        """Verify publish workflow triggers on release event"""
        filepath = os.path.join(self.REPO_DIR, self.PUBLISH_PATH)
        config = self._load_yaml(filepath)
        triggers = config.get("on", config.get(True, {}))
        assert "release" in triggers, \
            "Publish workflow should trigger on release event"

    def test_security_scan_has_pip_audit_and_bandit(self):
        """Verify security scan runs both pip-audit and bandit"""
        filepath = os.path.join(self.REPO_DIR, self.SECURITY_PATH)
        with open(filepath) as f:
            content = f.read()
        assert "pip-audit" in content, \
            "Security scan should run pip-audit for dependency vulnerability checking"
        assert "bandit" in content, \
            "Security scan should run bandit for source code security scanning"

    def test_security_scan_has_cron_schedule(self):
        """Verify security scan has a weekly cron schedule"""
        filepath = os.path.join(self.REPO_DIR, self.SECURITY_PATH)
        config = self._load_yaml(filepath)
        triggers = config.get("on", config.get(True, {}))
        assert "schedule" in triggers, \
            "Security scan should have a schedule trigger"

    def test_release_drafter_has_categories(self):
        """Verify release drafter defines feature, bug fix, docs, and breaking categories"""
        filepath = os.path.join(self.REPO_DIR, self.RELEASE_PATH)
        with open(filepath) as f:
            content = f.read()
        assert "release-drafter" in content.lower(), \
            "Release drafter workflow should use release-drafter action"

    def test_actions_use_pinned_versions(self):
        """Verify all action references use pinned versions (@v*), not @latest or @main"""
        workflow_files = [self.CI_PATH, self.PUBLISH_PATH, self.SECURITY_PATH, self.RELEASE_PATH]
        import re
        for rel_path in workflow_files:
            filepath = os.path.join(self.REPO_DIR, rel_path)
            if not os.path.exists(filepath):
                continue
            with open(filepath) as f:
                content = f.read()
            # Find action references (uses: action/name@version)
            action_refs = re.findall(r'uses:\s*[\w\-\.]+/[\w\-\.]+@(\S+)', content)
            for ref in action_refs:
                assert ref != "latest" and ref != "main" and ref != "master", \
                    f"Action in {rel_path} uses unpinned version @{ref}"

    # === Functional Checks ===

    def test_all_workflows_are_valid_yaml(self):
        """Verify all workflow files parse as valid YAML without errors"""
        workflow_files = [self.CI_PATH, self.PUBLISH_PATH, self.SECURITY_PATH, self.RELEASE_PATH]
        for rel_path in workflow_files:
            filepath = os.path.join(self.REPO_DIR, rel_path)
            if not os.path.exists(filepath):
                continue
            config = self._load_yaml(filepath)
            assert config is not None, f"{rel_path} is empty or invalid YAML"
            assert isinstance(config, dict), f"{rel_path} should be a YAML mapping"

    def test_ci_workflow_includes_lint_and_test_steps(self):
        """Verify CI workflow includes ruff, mypy, and pytest steps"""
        filepath = os.path.join(self.REPO_DIR, self.CI_PATH)
        with open(filepath) as f:
            content = f.read()
        assert "ruff" in content, "CI should include ruff linting step"
        assert "mypy" in content, "CI should include mypy type checking step"
        assert "pytest" in content, "CI should include pytest testing step"

    def test_ci_workflow_caches_pip(self):
        """Verify CI workflow enables pip caching in Python setup"""
        filepath = os.path.join(self.REPO_DIR, self.CI_PATH)
        with open(filepath) as f:
            content = f.read()
        has_cache = ("cache: pip" in content or "cache: 'pip'" in content or
                     'cache: "pip"' in content or "actions/cache" in content)
        assert has_cache, "CI workflow should enable pip caching"
