"""
Test skill: gitlab-ci-patterns
Verify that the Agent implements a PipelineTemplateGenerator for GitLab CI —
StageDefinitions (StageConfig, JobDefinition), PipelineTemplateGenerator
(generate method producing full .gitlab-ci.yml Hash with build, test, security,
deploy stages for rails/node/python/golang project types).
"""

import os
import re
import subprocess
import pytest


class TestGitlabCiPatterns:
    REPO_DIR = "/workspace/gitlabhq"

    # ────── helpers ──────

    def _read(self, rel_path):
        fpath = os.path.join(self.REPO_DIR, rel_path)
        with open(fpath, "r") as f:
            return f.read()

    def _exists(self, rel_path):
        return os.path.isfile(os.path.join(self.REPO_DIR, rel_path))

    # === File Path Checks ===

    def test_pipeline_template_generator_exists(self):
        """pipeline_template_generator.rb must exist"""
        assert self._exists("lib/gitlab/ci/pipeline_template_generator.rb")

    def test_stage_definitions_exists(self):
        """stage_definitions.rb must exist"""
        assert self._exists("lib/gitlab/ci/stage_definitions.rb")

    def test_spec_file_exists(self):
        """RSpec file must exist"""
        assert self._exists("spec/lib/gitlab/ci/pipeline_template_generator_spec.rb")

    # === Semantic Checks — StageDefinitions ===

    def test_stage_config_struct(self):
        """StageConfig must be defined"""
        src = self._read("lib/gitlab/ci/stage_definitions.rb")
        assert "StageConfig" in src

    def test_job_definition_struct(self):
        """JobDefinition must be defined"""
        src = self._read("lib/gitlab/ci/stage_definitions.rb")
        assert "JobDefinition" in src

    def test_module_namespace(self):
        """Must be in Gitlab::CI module"""
        src = self._read("lib/gitlab/ci/stage_definitions.rb")
        assert "module Gitlab" in src or "module CI" in src

    # === Semantic Checks — PipelineTemplateGenerator ===

    def test_generator_class(self):
        """PipelineTemplateGenerator class must be defined"""
        src = self._read("lib/gitlab/ci/pipeline_template_generator.rb")
        assert re.search(r'class\s+PipelineTemplateGenerator', src)

    def test_supported_types(self):
        """Must support rails, node, python, golang"""
        src = self._read("lib/gitlab/ci/pipeline_template_generator.rb")
        for t in ["rails", "node", "python", "golang"]:
            assert t in src, f"Missing project type: {t}"

    def test_generate_method(self):
        """generate method must exist"""
        src = self._read("lib/gitlab/ci/pipeline_template_generator.rb")
        assert re.search(r'def\s+generate\b', src)

    def test_stages_definition(self):
        """Must define stages: build, test, security, deploy"""
        src = self._read("lib/gitlab/ci/pipeline_template_generator.rb")
        for stage in ["build", "test", "security", "deploy"]:
            assert stage in src, f"Missing stage: {stage}"

    def test_docker_build_job(self):
        """Must define build-image job"""
        src = self._read("lib/gitlab/ci/pipeline_template_generator.rb")
        assert "build" in src.lower() and "docker" in src.lower()

    def test_test_job_parallel(self):
        """Test job must support parallel configuration"""
        src = self._read("lib/gitlab/ci/pipeline_template_generator.rb")
        assert "parallel" in src.lower()

    def test_security_scan_job(self):
        """security-scan job must exist with allow_failure"""
        src = self._read("lib/gitlab/ci/pipeline_template_generator.rb")
        assert "security" in src.lower()
        assert "allow_failure" in src

    def test_deploy_jobs(self):
        """Deploy jobs for staging and production"""
        src = self._read("lib/gitlab/ci/pipeline_template_generator.rb")
        assert "staging" in src and "production" in src

    def test_manual_production_deploy(self):
        """Production deploy must be manual"""
        src = self._read("lib/gitlab/ci/pipeline_template_generator.rb")
        assert "manual" in src

    def test_initialize_validation(self):
        """Constructor must validate project_type"""
        src = self._read("lib/gitlab/ci/pipeline_template_generator.rb")
        assert "ArgumentError" in src or "raise" in src

    def test_test_images_per_type(self):
        """Must return correct test image per project type"""
        src = self._read("lib/gitlab/ci/pipeline_template_generator.rb")
        lower = src.lower()
        assert "ruby" in lower  # rails image
        assert "node" in lower  # node image
        assert "python" in lower  # python image
        assert "golang" in lower  # golang image

    def test_coverage_regex(self):
        """Must define coverage regex patterns"""
        src = self._read("lib/gitlab/ci/pipeline_template_generator.rb")
        # Coverage regex for at least one type
        assert "coverage" in src.lower()

    def test_retry_default(self):
        """Must include retry default for runner failures"""
        src = self._read("lib/gitlab/ci/pipeline_template_generator.rb")
        assert "retry" in src.lower()

    def test_kubectl_deploy_script(self):
        """Deploy script must use kubectl"""
        src = self._read("lib/gitlab/ci/pipeline_template_generator.rb")
        assert "kubectl" in src

    # === Functional Checks ===

    def test_ruby_syntax_generator(self):
        """Generator file must have valid Ruby syntax"""
        result = subprocess.run(
            ["ruby", "-c", "lib/gitlab/ci/pipeline_template_generator.rb"],
            capture_output=True, text=True, cwd=self.REPO_DIR, timeout=30,
        )
        assert result.returncode == 0, (
            f"Syntax check failed:\n{result.stderr}"
        )

    def test_ruby_syntax_stage_definitions(self):
        """Stage definitions file must have valid Ruby syntax"""
        result = subprocess.run(
            ["ruby", "-c", "lib/gitlab/ci/stage_definitions.rb"],
            capture_output=True, text=True, cwd=self.REPO_DIR, timeout=30,
        )
        assert result.returncode == 0, (
            f"Syntax check failed:\n{result.stderr}"
        )

    def test_rspec_tests_pass(self):
        """RSpec tests must pass"""
        result = subprocess.run(
            ["bundle", "exec", "rspec",
             "spec/lib/gitlab/ci/pipeline_template_generator_spec.rb",
             "--format", "documentation"],
            capture_output=True, text=True, cwd=self.REPO_DIR, timeout=180,
        )
        assert result.returncode == 0, (
            f"RSpec failed:\n{result.stdout}\n{result.stderr}"
        )
