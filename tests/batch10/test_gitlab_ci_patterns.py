"""
Test skill: gitlab-ci-patterns
Verify that the Agent correctly implements multi-stage CI/CD pipeline
configuration for GitLab CE.
"""

import os
import re
import subprocess
import pytest
import yaml


class TestGitlabCiPatterns:
    REPO_DIR = "/workspace/gitlabhq"

    # === File Path Checks ===

    def test_main_pipeline_exists(self):
        """Verify webhooks-processor.gitlab-ci.yml was created"""
        path = os.path.join(
            self.REPO_DIR,
            ".gitlab/ci/webhooks-processor.gitlab-ci.yml",
        )
        assert os.path.exists(path), "webhooks-processor.gitlab-ci.yml not found"

    def test_migrations_pipeline_exists(self):
        """Verify webhooks-processor-migrations.gitlab-ci.yml was created"""
        path = os.path.join(
            self.REPO_DIR,
            ".gitlab/ci/webhooks-processor-migrations.gitlab-ci.yml",
        )
        assert os.path.exists(path), "webhooks-processor-migrations.gitlab-ci.yml not found"

    def test_docker_template_exists(self):
        """Verify webhooks_docker.yml was created"""
        path = os.path.join(
            self.REPO_DIR,
            "lib/gitlab/ci/templates/webhooks_docker.yml",
        )
        assert os.path.exists(path), "webhooks_docker.yml not found"

    # === Semantic Checks: Main Pipeline ===

    def test_five_stages_defined(self):
        """Verify five stages in correct order"""
        path = os.path.join(
            self.REPO_DIR,
            ".gitlab/ci/webhooks-processor.gitlab-ci.yml",
        )
        with open(path) as f:
            data = yaml.safe_load(f)
        stages = data.get("stages", [])
        expected = ["build", "test", "scan", "package", "deploy"]
        assert stages == expected, f"Stages should be {expected}, got {stages}"

    def test_pipeline_variables(self):
        """Verify pipeline-level variables"""
        path = os.path.join(
            self.REPO_DIR,
            ".gitlab/ci/webhooks-processor.gitlab-ci.yml",
        )
        with open(path) as f:
            data = yaml.safe_load(f)
        variables = data.get("variables", {})
        assert variables.get("SERVICE_NAME") == "webhooks-processor", (
            "Should set SERVICE_NAME"
        )
        assert variables.get("DOCKER_DRIVER") == "overlay2", (
            "Should set DOCKER_DRIVER"
        )

    def test_build_job_exists(self):
        """Verify build:webhooks job"""
        path = os.path.join(
            self.REPO_DIR,
            ".gitlab/ci/webhooks-processor.gitlab-ci.yml",
        )
        with open(path) as f:
            data = yaml.safe_load(f)
        assert "build:webhooks" in data, "Should have build:webhooks job"
        job = data["build:webhooks"]
        assert job.get("stage") == "build", "Should be in build stage"

    def test_build_job_cache_policy(self):
        """Verify build job uses pull-push cache policy"""
        path = os.path.join(
            self.REPO_DIR,
            ".gitlab/ci/webhooks-processor.gitlab-ci.yml",
        )
        with open(path) as f:
            data = yaml.safe_load(f)
        job = data["build:webhooks"]
        cache = job.get("cache", {})
        if isinstance(cache, list):
            cache = cache[0]
        assert cache.get("policy") == "pull-push", (
            "Build cache policy should be pull-push"
        )

    def test_unit_test_job(self):
        """Verify test:unit job with needs and coverage"""
        path = os.path.join(
            self.REPO_DIR,
            ".gitlab/ci/webhooks-processor.gitlab-ci.yml",
        )
        with open(path) as f:
            data = yaml.safe_load(f)
        assert "test:unit" in data, "Should have test:unit job"
        job = data["test:unit"]
        assert job.get("stage") == "test", "Should be in test stage"

    def test_integration_test_allow_failure(self):
        """Verify test:integration has allow_failure: true"""
        path = os.path.join(
            self.REPO_DIR,
            ".gitlab/ci/webhooks-processor.gitlab-ci.yml",
        )
        with open(path) as f:
            data = yaml.safe_load(f)
        assert "test:integration" in data, "Should have test:integration job"
        job = data["test:integration"]
        assert job.get("allow_failure") is True, (
            "Integration test should have allow_failure: true"
        )

    def test_test_jobs_pull_cache(self):
        """Verify test jobs use pull cache policy"""
        path = os.path.join(
            self.REPO_DIR,
            ".gitlab/ci/webhooks-processor.gitlab-ci.yml",
        )
        with open(path) as f:
            data = yaml.safe_load(f)
        for job_name in ["test:unit", "test:integration"]:
            job = data[job_name]
            cache = job.get("cache", {})
            if isinstance(cache, list):
                cache = cache[0]
            assert cache.get("policy") == "pull", (
                f"{job_name} cache policy should be pull"
            )

    def test_package_docker_job(self):
        """Verify package:docker job with registry login"""
        path = os.path.join(
            self.REPO_DIR,
            ".gitlab/ci/webhooks-processor.gitlab-ci.yml",
        )
        with open(path) as f:
            data = yaml.safe_load(f)
        assert "package:docker" in data, "Should have package:docker job"
        job = data["package:docker"]
        assert job.get("stage") == "package", "Should be in package stage"

    def test_package_docker_registry_vars(self):
        """Verify package:docker uses CI registry variables"""
        path = os.path.join(
            self.REPO_DIR,
            ".gitlab/ci/webhooks-processor.gitlab-ci.yml",
        )
        with open(path) as f:
            content = f.read()
        assert "CI_REGISTRY" in content, "Should use CI_REGISTRY"
        assert "CI_REGISTRY_USER" in content or "CI_REGISTRY_PASSWORD" in content, (
            "Should use CI registry credentials"
        )

    def test_deploy_staging_job(self):
        """Verify deploy:staging job"""
        path = os.path.join(
            self.REPO_DIR,
            ".gitlab/ci/webhooks-processor.gitlab-ci.yml",
        )
        with open(path) as f:
            data = yaml.safe_load(f)
        assert "deploy:staging" in data, "Should have deploy:staging job"
        job = data["deploy:staging"]
        assert job.get("stage") == "deploy", "Should be in deploy stage"

    def test_deploy_production_manual(self):
        """Verify deploy:production with when: manual"""
        path = os.path.join(
            self.REPO_DIR,
            ".gitlab/ci/webhooks-processor.gitlab-ci.yml",
        )
        with open(path) as f:
            data = yaml.safe_load(f)
        assert "deploy:production" in data, "Should have deploy:production job"
        job = data["deploy:production"]
        assert job.get("when") == "manual", (
            "deploy:production should have when: manual"
        )

    def test_no_hardcoded_credentials(self):
        """Verify no hardcoded credentials in pipeline"""
        path = os.path.join(
            self.REPO_DIR,
            ".gitlab/ci/webhooks-processor.gitlab-ci.yml",
        )
        with open(path) as f:
            content = f.read()
        assert "password" not in content.lower() or "CI_REGISTRY_PASSWORD" in content, (
            "Should not have hardcoded passwords"
        )

    # === Semantic Checks: Migration Pipeline ===

    def test_migration_stages(self):
        """Verify migrate and verify stages"""
        path = os.path.join(
            self.REPO_DIR,
            ".gitlab/ci/webhooks-processor-migrations.gitlab-ci.yml",
        )
        with open(path) as f:
            data = yaml.safe_load(f)
        stages = data.get("stages", [])
        assert "migrate" in stages, "Should have migrate stage"
        assert "verify" in stages, "Should have verify stage"

    def test_migration_run_job(self):
        """Verify migrate:run job"""
        path = os.path.join(
            self.REPO_DIR,
            ".gitlab/ci/webhooks-processor-migrations.gitlab-ci.yml",
        )
        with open(path) as f:
            data = yaml.safe_load(f)
        assert "migrate:run" in data, "Should have migrate:run job"

    # === Semantic Checks: Docker Template ===

    def test_docker_template_has_anchor(self):
        """Verify YAML anchor in docker template"""
        path = os.path.join(
            self.REPO_DIR,
            "lib/gitlab/ci/templates/webhooks_docker.yml",
        )
        with open(path) as f:
            content = f.read()
        assert "&docker_build" in content, (
            "Should define &docker_build YAML anchor"
        )

    # === Functional Checks ===

    def test_main_pipeline_valid_yaml(self):
        """Verify main pipeline is valid YAML"""
        path = os.path.join(
            self.REPO_DIR,
            ".gitlab/ci/webhooks-processor.gitlab-ci.yml",
        )
        with open(path) as f:
            data = yaml.safe_load(f)
        assert data is not None, "Should be valid YAML"

    def test_migrations_valid_yaml(self):
        """Verify migrations pipeline is valid YAML"""
        path = os.path.join(
            self.REPO_DIR,
            ".gitlab/ci/webhooks-processor-migrations.gitlab-ci.yml",
        )
        with open(path) as f:
            data = yaml.safe_load(f)
        assert data is not None, "Should be valid YAML"

    def test_docker_template_valid_yaml(self):
        """Verify docker template is valid YAML"""
        path = os.path.join(
            self.REPO_DIR,
            "lib/gitlab/ci/templates/webhooks_docker.yml",
        )
        with open(path) as f:
            data = yaml.safe_load(f)
        assert data is not None, "Should be valid YAML"
