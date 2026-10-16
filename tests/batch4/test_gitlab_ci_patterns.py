"""
Tests for skill: gitlab-ci-patterns
Repo: gitlabhq/gitlabhq
Image: zhangyiiiiii/swe-skills-bench-ruby
Task: Create a multi-stage GitLab CI/CD pipeline with caching,
      multi-environment deployment, and reusable templates.
"""

import os
import re

import pytest
import yaml

REPO_DIR = "/workspace/gitlabhq"
DEMO_DIR = os.path.join(REPO_DIR, "examples", "ci-demo")

MAIN_CI = os.path.join(DEMO_DIR, ".gitlab-ci.yml")
TEMPLATES_FILE = os.path.join(DEMO_DIR, ".gitlab", "ci", "templates.yml")
DEPLOY_FILE = os.path.join(DEMO_DIR, ".gitlab", "ci", "deploy.yml")
SECURITY_FILE = os.path.join(DEMO_DIR, ".gitlab", "ci", "security.yml")
DOCKERFILE = os.path.join(DEMO_DIR, "Dockerfile")


def _load_yaml(path):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------
# Layer 1 — file_path_check
# ---------------------------------------------------------------------------

class TestFilePathCheck:
    """Verify all required GitLab CI files exist."""

    def test_main_ci_exists(self):
        assert os.path.isfile(MAIN_CI), f"Missing {MAIN_CI}"

    def test_templates_exists(self):
        assert os.path.isfile(TEMPLATES_FILE), f"Missing {TEMPLATES_FILE}"

    def test_deploy_exists(self):
        assert os.path.isfile(DEPLOY_FILE), f"Missing {DEPLOY_FILE}"

    def test_security_exists(self):
        assert os.path.isfile(SECURITY_FILE), f"Missing {SECURITY_FILE}"

    def test_dockerfile_exists(self):
        assert os.path.isfile(DOCKERFILE), f"Missing {DOCKERFILE}"


# ---------------------------------------------------------------------------
# Layer 2 — semantic_check
# ---------------------------------------------------------------------------

class TestSemanticMainPipeline:
    """Verify main .gitlab-ci.yml structure."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.cfg = _load_yaml(MAIN_CI)

    def test_stages_defined(self):
        stages = self.cfg.get("stages", [])
        assert len(stages) >= 5, f"Expected at least 5 stages; got {stages}"

    def test_stages_order(self):
        stages = self.cfg.get("stages", [])
        expected_order = ["build", "test", "security"]
        found = [s for s in stages if any(e in s for e in expected_order)]
        assert len(found) >= 3, f"Expected build, test, security stages; got {stages}"
        # build should come before test
        build_idx = next((i for i, s in enumerate(stages) if "build" in s), -1)
        test_idx = next((i for i, s in enumerate(stages) if "test" in s), -1)
        assert build_idx < test_idx, f"build should precede test; stages={stages}"

    def test_include_directive(self):
        includes = self.cfg.get("include", [])
        assert len(includes) >= 3 or "include" in str(self.cfg), (
            "Main CI should include partial CI files"
        )

    def test_global_cache(self):
        raw = yaml.dump(self.cfg)
        assert "cache" in raw, "Main CI should define a global cache"
        assert "node_modules" in raw, "Cache should include node_modules"

    def test_global_variables(self):
        variables = self.cfg.get("variables", {})
        assert "DOCKER_DRIVER" in variables or "DOCKER_TLS_CERTDIR" in variables, (
            f"Expected Docker-related global variables; got {list(variables.keys())}"
        )

    def test_default_image(self):
        raw = yaml.dump(self.cfg)
        assert "node:20" in raw or "node:" in raw, (
            "Default image should be node:20"
        )


class TestSemanticBuildJob:
    """Verify build job configuration."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.cfg = _load_yaml(MAIN_CI)

    def _find_build_job(self):
        for key, val in self.cfg.items():
            if isinstance(val, dict) and "build" in key.lower():
                stage = val.get("stage", "")
                if "build" in stage:
                    return val
        return None

    def test_build_artifacts(self):
        raw = yaml.dump(self.cfg)
        assert "artifacts" in raw, "Build job should produce artifacts"
        assert "dist" in raw, "Build artifacts should include dist/"

    def test_npm_ci_in_build(self):
        raw = yaml.dump(self.cfg)
        assert "npm ci" in raw, "Build should run npm ci"


class TestSemanticTestJobs:
    """Verify test stage jobs."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.cfg = _load_yaml(MAIN_CI)
        self.raw = yaml.dump(self.cfg)

    def test_unit_test_job(self):
        assert "unit" in self.raw, "Should have a unit test job"

    def test_lint_job(self):
        assert "lint" in self.raw, "Should have a lint job"

    def test_integration_test(self):
        assert "integration" in self.raw, "Should have an integration test job"

    def test_postgres_service(self):
        assert "postgres" in self.raw, (
            "Integration tests should use postgres service"
        )

    def test_coverage_regex(self):
        assert "coverage" in self.raw.lower(), "Unit tests should report coverage"


class TestSemanticSecurityJobs:
    """Verify security scanning jobs."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.cfg = _load_yaml(SECURITY_FILE)
        self.raw = yaml.dump(self.cfg)

    def test_sast_job(self):
        assert "sast" in self.raw.lower() or "semgrep" in self.raw.lower(), (
            "Security file should define SAST job"
        )

    def test_dependency_scan(self):
        assert "dependency" in self.raw.lower() or "npm audit" in self.raw, (
            "Security file should define dependency scanning"
        )

    def test_allow_failure(self):
        assert "allow_failure" in self.raw, (
            "Security jobs should have allow_failure: true"
        )


class TestSemanticDeployJobs:
    """Verify deployment jobs."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.cfg = _load_yaml(DEPLOY_FILE)
        self.raw = yaml.dump(self.cfg)

    def test_staging_deploy(self):
        assert "staging" in self.raw, "Deploy file should define staging deployment"

    def test_production_deploy(self):
        assert "production" in self.raw, "Deploy file should define production deployment"

    def test_manual_gate(self):
        assert "manual" in self.raw, (
            "Production deploy should have manual approval gate"
        )

    def test_environment_urls(self):
        assert "environment" in self.raw, "Deploy jobs should define environment"

    def test_kubectl_usage(self):
        assert "kubectl" in self.raw, "Deploy jobs should use kubectl"


class TestSemanticDockerfile:
    """Verify multi-stage Dockerfile."""

    @pytest.fixture(autouse=True)
    def _load(self):
        with open(DOCKERFILE, "r", encoding="utf-8") as f:
            self.src = f.read()

    def test_multi_stage(self):
        from_count = len(re.findall(r"^FROM\s+", self.src, re.MULTILINE))
        assert from_count >= 2, f"Dockerfile should be multi-stage; found {from_count} FROM"

    def test_node_base(self):
        assert "node:" in self.src, "Dockerfile should use node base image"

    def test_expose(self):
        assert "EXPOSE" in self.src, "Dockerfile should EXPOSE a port"

    def test_healthcheck(self):
        assert "HEALTHCHECK" in self.src, "Dockerfile should have HEALTHCHECK instruction"

    def test_non_root_user(self):
        assert "USER" in self.src or "user" in self.src, (
            "Dockerfile should set a non-root USER"
        )


class TestSemanticTemplates:
    """Verify reusable template patterns."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.cfg = _load_yaml(TEMPLATES_FILE)
        self.raw = yaml.dump(self.cfg)

    def test_node_template(self):
        assert "node_template" in self.raw or "node" in self.raw.lower(), (
            "Templates should define a node_template"
        )

    def test_deploy_template(self):
        assert "deploy_template" in self.raw or "deploy" in self.raw.lower(), (
            "Templates should define a deploy_template"
        )


# ---------------------------------------------------------------------------
# Layer 3 — functional_check
# ---------------------------------------------------------------------------

class TestFunctionalPipelineStructure:
    """Functionally verify the complete pipeline structure."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.cfg = _load_yaml(MAIN_CI)

    def test_deploy_staging_before_production(self):
        stages = self.cfg.get("stages", [])
        stg_idx = None
        prd_idx = None
        for i, s in enumerate(stages):
            if "staging" in s:
                stg_idx = i
            if "production" in s:
                prd_idx = i
        if stg_idx is not None and prd_idx is not None:
            assert stg_idx < prd_idx, (
                f"Staging (idx={stg_idx}) should precede production (idx={prd_idx})"
            )

    def test_security_after_test(self):
        stages = self.cfg.get("stages", [])
        test_idx = next((i for i, s in enumerate(stages) if "test" in s), -1)
        sec_idx = next((i for i, s in enumerate(stages) if "security" in s or "sec" in s), -1)
        if sec_idx >= 0:
            assert test_idx < sec_idx, (
                f"Test (idx={test_idx}) should precede security (idx={sec_idx})"
            )


class TestFunctionalCachePolicy:
    """Verify cache push/pull policies."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.cfg = _load_yaml(MAIN_CI)
        self.raw = yaml.dump(self.cfg)

    def test_cache_key_branch_slug(self):
        assert "CI_COMMIT_REF_SLUG" in self.raw, (
            "Cache key should use CI_COMMIT_REF_SLUG for branch isolation"
        )

    def test_cache_push_policy(self):
        assert "push" in self.raw, (
            "Build job cache should use push policy"
        )


class TestFunctionalDockerBuild:
    """Verify Docker build job configuration."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.cfg = _load_yaml(MAIN_CI)
        self.raw = yaml.dump(self.cfg)

    def test_docker_in_docker_service(self):
        assert "docker" in self.raw and "dind" in self.raw, (
            "Docker build job should use docker:dind service"
        )

    def test_ci_registry_push(self):
        assert "CI_REGISTRY" in self.raw, (
            "Docker build should push to CI_REGISTRY_IMAGE"
        )


class TestFunctionalAllYamlValid:
    """Verify all YAML files in demo are parseable."""

    def test_all_yaml_valid(self):
        for dirpath, _, filenames in os.walk(DEMO_DIR):
            for fn in filenames:
                if fn.endswith(".yml") or fn.endswith(".yaml"):
                    fpath = os.path.join(dirpath, fn)
                    with open(fpath, "r", encoding="utf-8") as f:
                        doc = yaml.safe_load(f)
                    assert doc is not None, f"Failed to parse {fpath}"
