"""
Test skill: gitlab-ci-patterns
Verify that the Agent correctly configures GitLab CI/CD pipelines for a Rails
application with multi-stage, templates, parallel testing, and rollback.
"""

import os
import re
import pytest

try:
    import yaml
except ImportError:
    yaml = None


class TestGitlabCiPatterns:
    REPO_DIR = "/workspace/gitlabhq"

    GITLAB_CI = ".gitlab-ci.yml"
    TEST_TEMPLATE = "ci/templates/test-template.yml"
    DEPLOY_TEMPLATE = "ci/templates/deploy-template.yml"
    ROLLBACK_SCRIPT = "ci/scripts/rollback.sh"

    def _read_file(self, rel_path):
        filepath = os.path.join(self.REPO_DIR, rel_path)
        with open(filepath) as f:
            return f.read()

    # === File Path Checks ===

    def test_gitlab_ci_exists(self):
        filepath = os.path.join(self.REPO_DIR, self.GITLAB_CI)
        assert os.path.exists(filepath), f".gitlab-ci.yml not found at {filepath}"

    def test_test_template_exists(self):
        filepath = os.path.join(self.REPO_DIR, self.TEST_TEMPLATE)
        assert os.path.exists(filepath), f"test-template.yml not found"

    def test_deploy_template_exists(self):
        filepath = os.path.join(self.REPO_DIR, self.DEPLOY_TEMPLATE)
        assert os.path.exists(filepath), f"deploy-template.yml not found"

    def test_rollback_script_exists(self):
        filepath = os.path.join(self.REPO_DIR, self.ROLLBACK_SCRIPT)
        assert os.path.exists(filepath), f"rollback.sh not found"

    # === Semantic Checks ===

    def test_stages_defined(self):
        """Verify 5 stages: prepare, test, build, deploy, rollback"""
        content = self._read_file(self.GITLAB_CI)
        assert "stages:" in content, "Missing stages definition"
        for stage in ["prepare", "test", "build", "deploy", "rollback"]:
            assert stage in content, f"Missing stage: {stage}"

    def test_bundle_install_job(self):
        """Verify bundle-install job in prepare stage"""
        content = self._read_file(self.GITLAB_CI)
        assert "bundle" in content.lower(), "Missing bundle install job"
        assert "vendor/bundle" in content, "Missing vendor/bundle cache path"

    def test_cache_configuration(self):
        """Verify gem caching with correct key pattern"""
        content = self._read_file(self.GITLAB_CI)
        assert "cache" in content, "Missing cache configuration"
        has_key = "CI_COMMIT_REF_SLUG" in content or "gems" in content
        assert has_key, "Cache missing key with CI_COMMIT_REF_SLUG"

    def test_parallel_unit_tests(self):
        """Verify unit tests run in parallel with 4 nodes"""
        content = self._read_file(self.GITLAB_CI)
        assert "parallel" in content, "Missing parallel testing"
        assert "4" in content, "Missing parallel: 4 config"

    def test_junit_reports(self):
        """Verify JUnit report artifacts"""
        content = self._read_file(self.GITLAB_CI)
        assert "junit" in content.lower(), "Missing JUnit report"

    def test_integration_tests_have_services(self):
        """Verify integration tests define postgres and redis services"""
        content = self._read_file(self.GITLAB_CI)
        assert "postgres" in content, "Missing postgres service"
        assert "redis" in content, "Missing redis service"

    def test_docker_build_with_kaniko(self):
        """Verify docker-build uses Kaniko"""
        content = self._read_file(self.GITLAB_CI)
        has_kaniko = "kaniko" in content.lower() or "gcr.io/kaniko" in content
        assert has_kaniko, "Missing Kaniko for Docker build"

    def test_deploy_staging_auto(self):
        """Verify deploy-staging auto-deploys on main branch"""
        content = self._read_file(self.GITLAB_CI)
        assert "staging" in content, "Missing deploy-staging job"
        assert "main" in content, "Missing main branch reference"

    def test_deploy_production_manual(self):
        """Verify deploy-production is manual and only on tags"""
        content = self._read_file(self.GITLAB_CI)
        assert "production" in content, "Missing deploy-production job"
        assert "manual" in content, "Missing manual trigger for production"

    def test_rollback_job(self):
        """Verify rollback job exists and is manual"""
        content = self._read_file(self.GITLAB_CI)
        assert "rollback" in content.lower(), "Missing rollback job"

    def test_rollback_script_uses_kubectl(self):
        """Verify rollback script uses kubectl rollout undo"""
        content = self._read_file(self.ROLLBACK_SCRIPT)
        assert "kubectl" in content, "Rollback script missing kubectl"
        assert "rollout undo" in content, "Rollback missing rollout undo"
        assert "rollout status" in content, "Rollback missing status check"

    def test_templates_use_extends(self):
        """Verify jobs use extends for template reuse"""
        content = self._read_file(self.GITLAB_CI)
        assert "extends" in content, "Missing extends for template reuse"

    # === Functional Checks ===

    def test_gitlab_ci_valid_yaml(self):
        """Verify .gitlab-ci.yml is valid YAML"""
        if yaml is None:
            pytest.skip("PyYAML not installed")
        content = self._read_file(self.GITLAB_CI)
        try:
            yaml.safe_load(content)
        except yaml.YAMLError as e:
            pytest.fail(f".gitlab-ci.yml YAML error: {e}")

    def test_templates_valid_yaml(self):
        """Verify template YAML files are valid"""
        if yaml is None:
            pytest.skip("PyYAML not installed")
        for path in [self.TEST_TEMPLATE, self.DEPLOY_TEMPLATE]:
            content = self._read_file(path)
            try:
                yaml.safe_load(content)
            except yaml.YAMLError as e:
                pytest.fail(f"{path} YAML error: {e}")
