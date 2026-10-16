"""
Tests for the gitlab-ci-patterns skill.
Validates a GitLab CI pipeline generator with multi-stage pipelines,
job templates, cache strategies, and configuration validation.
"""

import os
import re
import ast

REPO_DIR = "/workspace/gitlabhq"
SCRIPTS_DIR = os.path.join(REPO_DIR, "scripts", "ci")


class TestGitlabCiPatterns:
    """Tests for the GitLab CI pipeline generator."""

    # ── file_path_check ──────────────────────────────────────────────

    def test_pipeline_generator_exists(self):
        """PipelineGenerator module must exist."""
        path = os.path.join(SCRIPTS_DIR, "pipeline_generator.py")
        assert os.path.isfile(path), f"Missing {path}"

    def test_job_templates_exists(self):
        """Job templates module must exist."""
        path = os.path.join(SCRIPTS_DIR, "job_templates.py")
        assert os.path.isfile(path), f"Missing {path}"

    def test_cache_config_exists(self):
        """CacheStrategy module must exist."""
        path = os.path.join(SCRIPTS_DIR, "cache_config.py")
        assert os.path.isfile(path), f"Missing {path}"

    def test_validator_exists(self):
        """PipelineValidator module must exist."""
        path = os.path.join(SCRIPTS_DIR, "validator.py")
        assert os.path.isfile(path), f"Missing {path}"

    # ── semantic_check ───────────────────────────────────────────────

    def _read(self, filename):
        path = os.path.join(SCRIPTS_DIR, filename)
        if not os.path.isfile(path):
            return ""
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def test_pipeline_generator_class(self):
        """PipelineGenerator must define generate, add_job, to_yaml, to_dict."""
        content = self._read("pipeline_generator.py")
        assert re.search(r"class\s+PipelineGenerator", content), (
            "PipelineGenerator class not defined"
        )
        for method in ["generate", "add_job", "to_yaml", "to_dict"]:
            assert re.search(rf"def\s+{method}\b", content), f"{method} not defined"

    def test_stage_ordering(self):
        """PipelineGenerator must define correct stage ordering."""
        content = self._read("pipeline_generator.py")
        for stage in ["build", "test", "security", "package", "deploy"]:
            assert stage in content, f"Stage '{stage}' not found"

    def test_language_support(self):
        """PipelineGenerator must support python, node, ruby, go."""
        content = self._read("pipeline_generator.py")
        for lang in ["python", "node", "ruby", "go"]:
            assert lang in content, f"Language '{lang}' not found"

    def test_job_template_classes(self):
        """Job templates must include BuildJob, TestJob, SecurityScanJob, DeployJob."""
        content = self._read("job_templates.py")
        for cls in ["BuildJob", "TestJob", "SecurityScanJob", "DeployJob"]:
            assert re.search(rf"class\s+{cls}", content), f"{cls} class not defined"

    def test_docker_build_job(self):
        """DockerBuildJob must use docker:24-dind service."""
        content = self._read("job_templates.py")
        assert re.search(r"class\s+DockerBuildJob", content), "DockerBuildJob class not defined"
        assert re.search(r"docker.*dind|dind", content), "Docker-in-Docker service not configured"

    def test_deploy_manual_production(self):
        """Production deploy must require manual approval."""
        content = self._read("job_templates.py")
        assert re.search(r"when.*manual|manual", content), "Manual deployment trigger not found"

    def test_cache_strategy_class(self):
        """CacheStrategy must define for_job with per-job-type policies."""
        content = self._read("cache_config.py")
        assert re.search(r"class\s+CacheStrategy", content), "CacheStrategy class not defined"
        assert re.search(r"def\s+for_job\b", content), "for_job method not defined"
        assert re.search(r"pull-push|pull|push", content), "Cache policies not found"

    def test_validator_class(self):
        """PipelineValidator must define validate and validate_yaml methods."""
        content = self._read("validator.py")
        assert re.search(r"class\s+PipelineValidator", content), (
            "PipelineValidator class not defined"
        )
        assert re.search(r"def\s+validate\b", content), "validate method not defined"
        assert re.search(r"def\s+validate_yaml\b", content), "validate_yaml method not defined"

    def test_validator_checks(self):
        """Validator must check undefined stages and missing dependencies."""
        content = self._read("validator.py")
        assert re.search(r"undefined.*stage|references.*stage", content, re.IGNORECASE), (
            "Undefined stage check not found"
        )
        assert re.search(r"needs.*non-existent|needs.*not.*found", content, re.IGNORECASE), (
            "Missing dependency check not found"
        )

    # ── functional_check ─────────────────────────────────────────────

    def test_all_files_valid_python(self):
        """All pipeline generator Python files must have valid syntax."""
        errors = []
        for fname in ["pipeline_generator.py", "job_templates.py",
                       "cache_config.py", "validator.py"]:
            content = self._read(fname)
            if not content:
                continue
            try:
                ast.parse(content)
            except SyntaxError as e:
                errors.append(f"{fname}: {e}")
        assert not errors, "Syntax errors:\n" + "\n".join(errors)

    def test_unsupported_language_raises(self):
        """PipelineGenerator must raise ValueError for unsupported language."""
        content = self._read("pipeline_generator.py")
        assert re.search(r"ValueError|Unsupported.*language|unsupported", content, re.IGNORECASE), (
            "ValueError for unsupported language not found"
        )

    def test_duplicate_job_raises(self):
        """PipelineGenerator must raise ValueError for duplicate job names."""
        content = self._read("pipeline_generator.py")
        assert re.search(r"ValueError|[Dd]uplicate.*job", content), (
            "Duplicate job check not found"
        )

    def test_security_scan_advisory(self):
        """SecurityScanJob must use allow_failure: true."""
        content = self._read("job_templates.py")
        assert re.search(r"allow_failure.*[Tt]rue|allow_failure.*true", content), (
            "allow_failure: true not found for security scan"
        )

    def test_test_file_exists(self):
        """Test file must exist."""
        path = os.path.join(REPO_DIR, "tests", "test_gitlab_ci_patterns.py")
        assert os.path.isfile(path), f"Missing {path}"
