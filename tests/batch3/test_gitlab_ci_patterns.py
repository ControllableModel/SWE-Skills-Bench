"""
Tests for the gitlab-ci-patterns skill.

Validates that a multi-stage GitLab CI pipeline was implemented with
build, test, security scanning, and deployment stages.

Repo: gitlabhq (https://github.com/gitlabhq/gitlabhq)
"""

import os
import re

REPO_DIR = "/workspace/gitlabhq"


class TestFilePathCheck:
    """Verify all required CI files were created."""

    def test_gitlab_ci_yml_exists(self):
        path = os.path.join(REPO_DIR, ".gitlab-ci.yml")
        assert os.path.isfile(path), f"Expected .gitlab-ci.yml at {path}"

    def test_build_template_exists(self):
        path = os.path.join(REPO_DIR, "ci", "templates", "build.yml")
        assert os.path.isfile(path), f"Expected ci/templates/build.yml"

    def test_test_template_exists(self):
        path = os.path.join(REPO_DIR, "ci", "templates", "test.yml")
        assert os.path.isfile(path), f"Expected ci/templates/test.yml"

    def test_security_template_exists(self):
        path = os.path.join(REPO_DIR, "ci", "templates", "security.yml")
        assert os.path.isfile(path), f"Expected ci/templates/security.yml"

    def test_deploy_template_exists(self):
        path = os.path.join(REPO_DIR, "ci", "templates", "deploy.yml")
        assert os.path.isfile(path), f"Expected ci/templates/deploy.yml"

    def test_dynamic_generator_exists(self):
        path = os.path.join(REPO_DIR, "ci", "dynamic", "generate-pipeline.rb")
        assert os.path.isfile(path), f"Expected ci/dynamic/generate-pipeline.rb"


class TestSemanticRootPipeline:
    """Verify root .gitlab-ci.yml structure."""

    def _read(self):
        path = os.path.join(REPO_DIR, ".gitlab-ci.yml")
        with open(path, "r") as f:
            return f.read()

    def test_stages_defined(self):
        content = self._read()
        assert re.search(r"stages:", content), "Expected stages: definition"

    def test_five_stages(self):
        content = self._read()
        for stage in ["build", "test", "security", "deploy-staging", "deploy-production"]:
            assert stage in content, f"Expected stage '{stage}'"

    def test_global_variables(self):
        content = self._read()
        assert re.search(r"variables:", content), "Expected global variables section"
        assert re.search(r"DOCKER_REGISTRY", content), "Expected DOCKER_REGISTRY variable"
        assert re.search(r"IMAGE_TAG", content), "Expected IMAGE_TAG variable"

    def test_include_local(self):
        content = self._read()
        assert re.search(r"include:", content), "Expected include: directive"
        assert re.search(r"local:", content), "Expected include: local references"

    def test_cache_configuration(self):
        content = self._read()
        assert re.search(r"cache:", content), "Expected global cache configuration"


class TestSemanticBuildStage:
    """Verify build stage templates."""

    def _read(self):
        path = os.path.join(REPO_DIR, "ci", "templates", "build.yml")
        with open(path, "r") as f:
            return f.read()

    def test_docker_build_job(self):
        content = self._read()
        assert re.search(r"build:docker|build_docker", content), (
            "Expected build:docker job"
        )

    def test_dind_service(self):
        content = self._read()
        assert re.search(r"docker.*dind|dind", content), (
            "Expected Docker-in-Docker service"
        )

    def test_build_args(self):
        content = self._read()
        assert re.search(r"build-arg|RUBY_VERSION", content), (
            "Expected --build-arg RUBY_VERSION"
        )

    def test_rules_changes(self):
        content = self._read()
        assert re.search(r"rules:|changes:", content), (
            "Expected rules: changes: for conditional builds"
        )

    def test_assets_job(self):
        content = self._read()
        assert re.search(r"build:assets|assets", content), (
            "Expected build:assets job"
        )

    def test_yarn_install(self):
        content = self._read()
        assert re.search(r"yarn install.*frozen-lockfile|yarn install", content), (
            "Expected yarn install --frozen-lockfile"
        )


class TestSemanticTestStage:
    """Verify test stage templates."""

    def _read(self):
        path = os.path.join(REPO_DIR, "ci", "templates", "test.yml")
        with open(path, "r") as f:
            return f.read()

    def test_rspec_job(self):
        content = self._read()
        assert re.search(r"test:rspec|rspec", content), (
            "Expected test:rspec job"
        )

    def test_parallel_execution(self):
        content = self._read()
        assert re.search(r"parallel:\s*4|parallel:", content), (
            "Expected parallel: 4 for rspec"
        )

    def test_junit_artifacts(self):
        content = self._read()
        assert re.search(r"junit|JUnit|reports:", content), (
            "Expected JUnit XML artifact for test reports"
        )

    def test_coverage_regex(self):
        content = self._read()
        assert re.search(r"coverage:", content), (
            "Expected coverage regex configuration"
        )

    def test_jest_job(self):
        content = self._read()
        assert re.search(r"test:jest|jest", content), (
            "Expected test:jest job"
        )

    def test_needs_build(self):
        content = self._read()
        assert re.search(r"needs:", content), (
            "Expected needs: dependency on build stage"
        )


class TestSemanticSecurityStage:
    """Verify security scanning templates."""

    def _read(self):
        path = os.path.join(REPO_DIR, "ci", "templates", "security.yml")
        with open(path, "r") as f:
            return f.read()

    def test_sast_job(self):
        content = self._read()
        assert re.search(r"sast|SAST", content), "Expected SAST job"

    def test_sast_excluded_paths(self):
        content = self._read()
        assert re.search(r"SAST_EXCLUDED_PATHS", content), (
            "Expected SAST_EXCLUDED_PATHS configuration"
        )

    def test_dependency_scanning(self):
        content = self._read()
        assert re.search(r"dependency.*scanning|Dependency.*Scanning", content, re.IGNORECASE), (
            "Expected dependency scanning job"
        )

    def test_container_scanning(self):
        content = self._read()
        assert re.search(r"container.*scanning|Container.*Scanning", content, re.IGNORECASE), (
            "Expected container scanning job"
        )


class TestSemanticDeployStage:
    """Verify deployment templates."""

    def _read(self):
        path = os.path.join(REPO_DIR, "ci", "templates", "deploy.yml")
        with open(path, "r") as f:
            return f.read()

    def test_staging_job(self):
        content = self._read()
        assert re.search(r"deploy:staging|staging", content), (
            "Expected deploy:staging job"
        )

    def test_staging_environment(self):
        content = self._read()
        assert re.search(r"environment:", content), "Expected environment config"
        assert re.search(r"staging", content), "Expected staging environment"

    def test_production_job(self):
        content = self._read()
        assert re.search(r"deploy:production|production", content), (
            "Expected deploy:production job"
        )

    def test_production_manual(self):
        content = self._read()
        assert re.search(r"when:\s*manual", content), (
            "Expected when: manual for production deployment"
        )

    def test_production_needs_staging(self):
        content = self._read()
        assert re.search(r"needs:.*staging|needs:", content), (
            "Expected production needs staging dependency"
        )

    def test_tag_rule(self):
        content = self._read()
        assert re.search(r"v\*|tag|refs/tags", content, re.IGNORECASE), (
            "Expected version tag rule (v*) for production"
        )


class TestSemanticDynamicPipeline:
    """Verify dynamic child pipeline generator."""

    def _read(self):
        path = os.path.join(REPO_DIR, "ci", "dynamic", "generate-pipeline.rb")
        with open(path, "r") as f:
            return f.read()

    def test_ruby_file(self):
        content = self._read()
        assert re.search(r"require|def |class |puts|YAML|yaml", content), (
            "Expected Ruby code in generate-pipeline.rb"
        )

    def test_changed_files(self):
        content = self._read()
        assert re.search(r"changed|diff|CI_MERGE_REQUEST_DIFF_BASE_SHA", content), (
            "Expected changed file detection logic"
        )

    def test_docs_only_check(self):
        content = self._read()
        assert re.search(r"docs|doc/", content), (
            "Expected docs-only change detection"
        )

    def test_yaml_output(self):
        content = self._read()
        assert re.search(r"YAML|yaml|\.yml", content, re.IGNORECASE), (
            "Expected YAML output generation"
        )


class TestFunctionalYamlValidity:
    """Validate YAML files are well-formed."""

    def test_root_pipeline_yaml(self):
        import yaml
        path = os.path.join(REPO_DIR, ".gitlab-ci.yml")
        with open(path, "r") as f:
            data = yaml.safe_load(f)
        assert isinstance(data, dict), ".gitlab-ci.yml should be valid YAML dict"

    def test_build_template_yaml(self):
        import yaml
        path = os.path.join(REPO_DIR, "ci", "templates", "build.yml")
        with open(path, "r") as f:
            data = yaml.safe_load(f)
        assert isinstance(data, dict), "build.yml should be valid YAML dict"

    def test_security_template_yaml(self):
        import yaml
        path = os.path.join(REPO_DIR, "ci", "templates", "security.yml")
        with open(path, "r") as f:
            data = yaml.safe_load(f)
        assert isinstance(data, dict), "security.yml should be valid YAML dict"
