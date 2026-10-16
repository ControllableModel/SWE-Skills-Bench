"""
Test skill: gitlab-ci-patterns
Verify that the Agent builds a GitLab CI/CD pipeline for a Python
microservice with 5 stages, Cobertura coverage, Docker layer caching,
YAML templates, and Terraform integration.
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

    # === File Path Checks ===

    def test_gitlab_ci_yml_exists(self):
        assert os.path.exists(os.path.join(self.REPO_DIR, ".gitlab-ci.yml"))

    def test_python_template_exists(self):
        assert os.path.exists(os.path.join(self.REPO_DIR, "ci/templates/python.yml"))

    def test_deploy_template_exists(self):
        assert os.path.exists(os.path.join(self.REPO_DIR, "ci/templates/deploy.yml"))

    def test_terraform_template_exists(self):
        assert os.path.exists(os.path.join(self.REPO_DIR, "ci/templates/terraform.yml"))

    def test_dockerfile_exists(self):
        assert os.path.exists(os.path.join(self.REPO_DIR, "Dockerfile"))

    # === Semantic Checks ===

    def test_pipeline_has_five_stages(self):
        """Pipeline should define 5 stages: validate, test, build, deploy-staging, deploy-production"""
        if yaml is None:
            pytest.skip("PyYAML not available")
        path = os.path.join(self.REPO_DIR, ".gitlab-ci.yml")
        with open(path) as f:
            data = yaml.safe_load(f)
        stages = data.get("stages", [])
        expected = {"validate", "test", "build", "deploy-staging", "deploy-production"}
        # Allow variations like deploy_staging
        stage_set = {s.replace("_", "-") for s in stages}
        missing = expected - stage_set
        assert not missing, f"Missing stages: {missing}. Found: {stages}"

    def test_pipeline_includes_templates(self):
        """Pipeline should include template files"""
        path = os.path.join(self.REPO_DIR, ".gitlab-ci.yml")
        with open(path) as f:
            content = f.read()
        assert "include" in content, "Pipeline should include templates"
        assert "python.yml" in content, "Should include python template"

    def test_python_template_has_base_job(self):
        """Python template should define .python-base hidden job"""
        path = os.path.join(self.REPO_DIR, "ci/templates/python.yml")
        with open(path) as f:
            content = f.read()
        assert ".python-base" in content, "Missing .python-base hidden job"

    def test_python_template_has_caching(self):
        """Python template should configure pip caching"""
        path = os.path.join(self.REPO_DIR, "ci/templates/python.yml")
        with open(path) as f:
            content = f.read()
        assert "cache" in content, "Missing cache configuration"
        assert "pip" in content.lower(), "Cache should reference pip"

    def test_unit_test_has_cobertura(self):
        """Unit test job should produce Cobertura coverage report"""
        path = os.path.join(self.REPO_DIR, ".gitlab-ci.yml")
        with open(path) as f:
            content = f.read()
        assert "cobertura" in content.lower(), "Missing Cobertura coverage"
        assert "coverage" in content, "Missing coverage configuration"

    def test_integration_test_has_services(self):
        """Integration test should use PostgreSQL and Redis services"""
        path = os.path.join(self.REPO_DIR, ".gitlab-ci.yml")
        with open(path) as f:
            content = f.read()
        assert "postgres" in content.lower(), "Missing PostgreSQL service"
        assert "redis" in content.lower(), "Missing Redis service"

    def test_build_docker_uses_dind(self):
        """Docker build should use docker-in-docker service"""
        path = os.path.join(self.REPO_DIR, ".gitlab-ci.yml")
        with open(path) as f:
            content = f.read()
        assert "dind" in content.lower() or "docker" in content, (
            "Build should use docker-in-docker"
        )

    def test_deploy_template_has_kubectl(self):
        """Deploy template should configure kubectl"""
        path = os.path.join(self.REPO_DIR, "ci/templates/deploy.yml")
        with open(path) as f:
            content = f.read()
        assert ".deploy-base" in content, "Missing .deploy-base hidden job"
        assert "kubectl" in content, "Should configure kubectl"

    def test_production_deploy_is_manual(self):
        """Production deploy should be manual with blocking approval"""
        path = os.path.join(self.REPO_DIR, ".gitlab-ci.yml")
        with open(path) as f:
            content = f.read()
        assert "manual" in content, "Production deploy should be manual"

    def test_terraform_has_plan_and_apply(self):
        """Terraform template should have plan and apply jobs"""
        path = os.path.join(self.REPO_DIR, "ci/templates/terraform.yml")
        with open(path) as f:
            content = f.read()
        assert "terraform" in content.lower(), "Should reference terraform"
        assert "plan" in content, "Missing terraform plan"
        assert "apply" in content, "Missing terraform apply"

    def test_dockerfile_is_multistage(self):
        """Dockerfile should use multi-stage build"""
        path = os.path.join(self.REPO_DIR, "Dockerfile")
        with open(path) as f:
            content = f.read()
        from_count = len(re.findall(r"^FROM\s", content, re.MULTILINE))
        assert from_count >= 2, "Dockerfile should use multi-stage build"

    def test_dockerfile_runs_as_nonroot(self):
        """Dockerfile should create a non-root user"""
        path = os.path.join(self.REPO_DIR, "Dockerfile")
        with open(path) as f:
            content = f.read()
        assert "USER" in content, "Dockerfile should switch to non-root user"

    def test_dockerfile_uses_uvicorn(self):
        """Dockerfile should run with uvicorn"""
        path = os.path.join(self.REPO_DIR, "Dockerfile")
        with open(path) as f:
            content = f.read()
        assert "uvicorn" in content, "Should run FastAPI with uvicorn"

    # === Functional Checks ===

    def test_all_yaml_files_valid(self):
        """All YAML files should parse without errors"""
        if yaml is None:
            pytest.skip("PyYAML not available")
        files = [
            ".gitlab-ci.yml",
            "ci/templates/python.yml",
            "ci/templates/deploy.yml",
            "ci/templates/terraform.yml",
        ]
        for f in files:
            path = os.path.join(self.REPO_DIR, f)
            try:
                with open(path) as fh:
                    yaml.safe_load(fh)
            except yaml.YAMLError as e:
                pytest.fail(f"{f} YAML error: {e}")

    def test_pipeline_uses_extends(self):
        """Pipeline should use extends for DRY configuration"""
        path = os.path.join(self.REPO_DIR, ".gitlab-ci.yml")
        with open(path) as f:
            content = f.read()
        assert "extends:" in content, "Pipeline should use extends for templates"
