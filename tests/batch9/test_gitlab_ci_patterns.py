"""
Test skill: gitlab-ci-patterns
Verify that the Agent creates a multi-stage .gitlab-ci.yml configuration
with proper stage definitions, caching, and artifact management (Ruby).
"""

import os
import re
import subprocess
import pytest


class TestGitlabCiPatterns:
    REPO_DIR = "/workspace/gitlabhq"

    # === File Path Checks ===

    def test_gitlab_ci_yml_exists(self):
        """Verify .gitlab-ci.yml exists"""
        assert os.path.isfile(os.path.join(self.REPO_DIR, ".gitlab-ci.yml")), ".gitlab-ci.yml not found"

    # === Semantic Checks ===

    def test_gitlab_ci_has_stages(self):
        """Verify .gitlab-ci.yml defines stages"""
        content = self._read_ci_file()
        assert "stages:" in content, ".gitlab-ci.yml missing stages definition"

    def test_gitlab_ci_has_multiple_stages(self):
        """Verify at least 3 stages are defined"""
        content = self._read_ci_file()
        stages_match = re.search(r'stages:\s*\n((?:\s+-\s+\S+\n)+)', content)
        if stages_match:
            stage_lines = [l.strip().lstrip("- ") for l in stages_match.group(1).strip().splitlines() if l.strip().startswith("-")]
            assert len(stage_lines) >= 3, f"Expected at least 3 stages, found {len(stage_lines)}"
        else:
            lines_with_stage = [l for l in content.splitlines() if "stage:" in l]
            unique_stages = set()
            for l in lines_with_stage:
                m = re.search(r'stage:\s*(\S+)', l)
                if m:
                    unique_stages.add(m.group(1))
            assert len(unique_stages) >= 3, f"Expected at least 3 unique stages, found {len(unique_stages)}"

    def test_gitlab_ci_has_cache(self):
        """Verify caching is configured"""
        content = self._read_ci_file()
        assert "cache:" in content, ".gitlab-ci.yml missing cache configuration"

    def test_gitlab_ci_has_artifacts(self):
        """Verify artifacts are defined"""
        content = self._read_ci_file()
        assert "artifacts:" in content, ".gitlab-ci.yml missing artifacts configuration"

    def test_gitlab_ci_has_rules_or_only(self):
        """Verify conditional execution rules are defined"""
        content = self._read_ci_file()
        has_rules = "rules:" in content or "only:" in content or "except:" in content
        assert has_rules, ".gitlab-ci.yml missing conditional execution rules"

    def test_gitlab_ci_has_variables(self):
        """Verify variables are defined"""
        content = self._read_ci_file()
        assert "variables:" in content, ".gitlab-ci.yml missing variables"

    # === Functional Checks ===

    def test_gitlab_ci_valid_yaml(self):
        """Verify .gitlab-ci.yml is valid YAML"""
        import yaml
        content = self._read_ci_file()
        data = yaml.safe_load(content)
        assert isinstance(data, dict), ".gitlab-ci.yml is not a YAML mapping"

    def test_gitlab_ci_jobs_have_script(self):
        """Verify jobs have script sections"""
        import yaml
        content = self._read_ci_file()
        data = yaml.safe_load(content)
        reserved_keys = {"stages", "variables", "default", "include", "workflow", "cache", "image", "services", "before_script", "after_script"}
        jobs = {k: v for k, v in data.items() if k not in reserved_keys and isinstance(v, dict)}
        jobs_with_script = sum(1 for j in jobs.values() if "script" in j)
        assert jobs_with_script >= 3, f"Only {jobs_with_script} jobs have 'script' section"

    def test_gitlab_ci_includes_or_extends(self):
        """Verify template reuse via include or extends"""
        content = self._read_ci_file()
        has_reuse = "include:" in content or "extends:" in content or "!reference" in content
        assert has_reuse, ".gitlab-ci.yml missing include/extends/reference for template reuse"

    def test_gitlab_ci_no_duplicate_stages(self):
        """Verify no duplicate stages in stages list"""
        import yaml
        content = self._read_ci_file()
        data = yaml.safe_load(content)
        stages = data.get("stages", [])
        if stages:
            assert len(stages) == len(set(stages)), f"Duplicate stages found: {stages}"

    def _read_ci_file(self):
        ci_path = os.path.join(self.REPO_DIR, ".gitlab-ci.yml")
        with open(ci_path) as fh:
            return fh.read()
