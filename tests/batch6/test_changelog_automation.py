"""
Test skill: changelog-automation
Verify that the Agent sets up automated changelog generation from
Conventional Commits, semantic version bumping, and GitHub Actions
release workflow.
"""

import os
import re
import ast
import json
import subprocess
import pytest

try:
    import yaml
except ImportError:
    yaml = None


class TestChangelogAutomation:
    REPO_DIR = "/workspace/github-changelog-generator"

    # === File Path Checks ===

    def test_commitlint_config_exists(self):
        assert os.path.exists(
            os.path.join(self.REPO_DIR, "commitlint.config.js")
        )

    def test_husky_hook_exists(self):
        assert os.path.exists(
            os.path.join(self.REPO_DIR, ".husky/commit-msg")
        )

    def test_generate_changelog_script_exists(self):
        assert os.path.exists(
            os.path.join(self.REPO_DIR, "scripts/generate-changelog.js")
        )

    def test_bump_version_script_exists(self):
        assert os.path.exists(
            os.path.join(self.REPO_DIR, "scripts/bump-version.js")
        )

    def test_release_workflow_exists(self):
        assert os.path.exists(
            os.path.join(self.REPO_DIR, ".github/workflows/release.yml")
        )

    def test_changelog_md_exists(self):
        assert os.path.exists(
            os.path.join(self.REPO_DIR, "CHANGELOG.md")
        )

    # === Semantic Checks ===

    def test_commitlint_extends_conventional(self):
        """commitlint.config.js should extend @commitlint/config-conventional"""
        path = os.path.join(self.REPO_DIR, "commitlint.config.js")
        with open(path) as f:
            content = f.read()
        assert "@commitlint/config-conventional" in content, (
            "Must extend @commitlint/config-conventional"
        )

    def test_commitlint_type_enum(self):
        """commitlint should define type-enum with at least feat, fix, docs"""
        path = os.path.join(self.REPO_DIR, "commitlint.config.js")
        with open(path) as f:
            content = f.read()
        for t in ("feat", "fix", "docs", "chore", "refactor", "perf", "test"):
            assert f"'{t}'" in content or f'"{t}"' in content, (
                f"Missing type '{t}' in type-enum"
            )

    def test_commitlint_subject_max_length(self):
        """commitlint should enforce subject max length of 72"""
        path = os.path.join(self.REPO_DIR, "commitlint.config.js")
        with open(path) as f:
            content = f.read()
        assert "72" in content, "Subject max length should be 72"

    def test_changelog_generator_has_parse_commits(self):
        """generate-changelog.js should have parseCommits function"""
        path = os.path.join(self.REPO_DIR, "scripts/generate-changelog.js")
        with open(path) as f:
            content = f.read()
        assert re.search(r"(function\s+parseCommits|parseCommits\s*=|parseCommits\s*\()", content), (
            "Missing parseCommits function"
        )

    def test_changelog_generator_has_categorize(self):
        """generate-changelog.js should have categorizeCommits function"""
        path = os.path.join(self.REPO_DIR, "scripts/generate-changelog.js")
        with open(path) as f:
            content = f.read()
        assert re.search(r"categorize", content, re.IGNORECASE), (
            "Missing categorizeCommits function"
        )

    def test_changelog_generator_maps_types_to_sections(self):
        """Changelog maps commit types to Keep a Changelog sections"""
        path = os.path.join(self.REPO_DIR, "scripts/generate-changelog.js")
        with open(path) as f:
            content = f.read()
        assert "Added" in content, "Missing 'Added' section mapping"
        assert "Fixed" in content, "Missing 'Fixed' section mapping"
        assert "Changed" in content, "Missing 'Changed' section mapping"

    def test_changelog_generator_detects_breaking_changes(self):
        """Changelog should detect BREAKING CHANGE: footer or ! suffix"""
        path = os.path.join(self.REPO_DIR, "scripts/generate-changelog.js")
        with open(path) as f:
            content = f.read()
        assert "BREAKING" in content or "breaking" in content, (
            "Must detect breaking changes"
        )

    def test_bump_version_has_determine_next(self):
        """bump-version.js should have determineNextVersion logic"""
        path = os.path.join(self.REPO_DIR, "scripts/bump-version.js")
        with open(path) as f:
            content = f.read()
        assert re.search(r"determine|nextVersion|bump", content, re.IGNORECASE), (
            "Missing version determination logic"
        )

    def test_bump_version_handles_semver(self):
        """bump-version.js should handle major/minor/patch bumps"""
        path = os.path.join(self.REPO_DIR, "scripts/bump-version.js")
        with open(path) as f:
            content = f.read()
        assert "major" in content, "Missing major version bump"
        assert "minor" in content, "Missing minor version bump"
        assert "patch" in content, "Missing patch version bump"

    def test_release_workflow_has_dispatch_trigger(self):
        """Release workflow should have workflow_dispatch trigger"""
        path = os.path.join(self.REPO_DIR, ".github/workflows/release.yml")
        with open(path) as f:
            content = f.read()
        assert "workflow_dispatch" in content, "Missing workflow_dispatch trigger"

    def test_release_workflow_has_full_history(self):
        """Release workflow should checkout with full git history"""
        path = os.path.join(self.REPO_DIR, ".github/workflows/release.yml")
        with open(path) as f:
            content = f.read()
        assert "fetch-depth: 0" in content or "fetch-depth: '0'" in content, (
            "Checkout should use fetch-depth: 0"
        )

    def test_release_workflow_creates_github_release(self):
        """Release workflow should create a GitHub Release"""
        path = os.path.join(self.REPO_DIR, ".github/workflows/release.yml")
        with open(path) as f:
            content = f.read()
        assert "gh-release" in content or "create-release" in content or "softprops" in content, (
            "Should use GitHub release action"
        )

    def test_changelog_follows_keep_a_changelog(self):
        """CHANGELOG.md should follow Keep a Changelog format"""
        path = os.path.join(self.REPO_DIR, "CHANGELOG.md")
        with open(path) as f:
            content = f.read()
        assert "Keep a Changelog" in content or "keepachangelog" in content.lower(), (
            "Should reference Keep a Changelog format"
        )
        assert "Semantic Versioning" in content or "semver" in content.lower(), (
            "Should reference Semantic Versioning"
        )

    # === Functional Checks ===

    def test_changelog_generator_valid_js(self):
        """generate-changelog.js should be valid JavaScript"""
        path = os.path.join(self.REPO_DIR, "scripts/generate-changelog.js")
        result = subprocess.run(
            ["node", "--check", path],
            capture_output=True, text=True, timeout=30
        )
        assert result.returncode == 0, (
            f"generate-changelog.js syntax error: {result.stderr}"
        )

    def test_bump_version_valid_js(self):
        """bump-version.js should be valid JavaScript"""
        path = os.path.join(self.REPO_DIR, "scripts/bump-version.js")
        result = subprocess.run(
            ["node", "--check", path],
            capture_output=True, text=True, timeout=30
        )
        assert result.returncode == 0, (
            f"bump-version.js syntax error: {result.stderr}"
        )

    def test_release_workflow_valid_yaml(self):
        """Release workflow should be valid YAML"""
        if yaml is None:
            pytest.skip("PyYAML not available")
        path = os.path.join(self.REPO_DIR, ".github/workflows/release.yml")
        with open(path) as f:
            try:
                data = yaml.safe_load(f)
            except yaml.YAMLError as e:
                pytest.fail(f"release.yml YAML error: {e}")
        assert "jobs" in data, "Workflow must have jobs"
