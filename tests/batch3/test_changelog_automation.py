"""
Tests for the changelog-automation skill.

Validates that a changelog automation system was implemented for
github-changelog-generator, including Conventional Commit parsing,
semantic versioning calculation, and Keep-a-Changelog formatting.

Repo: github-changelog-generator (Ruby)
"""

import os
import re

REPO_DIR = "/workspace/github-changelog-generator"


class TestFilePathCheck:
    """Verify that all required files were created."""

    def test_conventional_parser_exists(self):
        path = os.path.join(
            REPO_DIR, "lib", "github_changelog_generator", "conventional.rb",
        )
        assert os.path.isfile(path), f"Expected conventional.rb at {path}"

    def test_semver_calculator_exists(self):
        path = os.path.join(
            REPO_DIR, "lib", "github_changelog_generator",
            "semver_calculator.rb",
        )
        assert os.path.isfile(path), f"Expected semver_calculator.rb at {path}"

    def test_changelog_formatter_exists(self):
        path = os.path.join(
            REPO_DIR, "lib", "github_changelog_generator",
            "changelog_formatter.rb",
        )
        assert os.path.isfile(path), f"Expected changelog_formatter.rb at {path}"

    def test_conventional_spec_exists(self):
        spec_path = os.path.join(REPO_DIR, "spec")
        assert os.path.isdir(spec_path), "Expected spec directory for tests"
        spec_files = []
        for root, dirs, files in os.walk(spec_path):
            for f in files:
                if "conventional" in f.lower():
                    spec_files.append(f)
        assert len(spec_files) >= 1, (
            "Expected at least one spec file for conventional commits"
        )


class TestSemanticConventionalParser:
    """Verify ConventionalCommit parser."""

    def _read_parser(self):
        path = os.path.join(
            REPO_DIR, "lib", "github_changelog_generator", "conventional.rb",
        )
        with open(path, "r") as f:
            return f.read()

    def test_conventional_commit_class(self):
        content = self._read_parser()
        assert re.search(r"class\s+ConventionalCommit", content), (
            "Expected ConventionalCommit class"
        )

    def test_type_extraction(self):
        content = self._read_parser()
        assert re.search(r"type|@type|:type", content), (
            "Expected type field extraction from commit message"
        )

    def test_scope_extraction(self):
        content = self._read_parser()
        assert re.search(r"scope|@scope|:scope", content), (
            "Expected scope field extraction"
        )

    def test_description_extraction(self):
        content = self._read_parser()
        assert re.search(r"description|@description|:description|subject", content), (
            "Expected description/subject field extraction"
        )

    def test_breaking_change_detection(self):
        content = self._read_parser()
        assert re.search(r"breaking|BREAKING", content), (
            "Expected breaking change detection (! or BREAKING CHANGE footer)"
        )

    def test_supported_types(self):
        content = self._read_parser()
        for commit_type in ["feat", "fix"]:
            assert commit_type in content, (
                f"Expected commit type '{commit_type}' handling"
            )

    def test_nil_for_non_conforming(self):
        content = self._read_parser()
        assert re.search(r"nil|return nil|parse.*nil", content), (
            "Expected nil return for non-conforming messages"
        )


class TestSemanticCategorization:
    """Verify commit type to changelog category mapping."""

    def _read_all_sources(self):
        content = ""
        for fname in ["conventional.rb", "changelog_formatter.rb"]:
            path = os.path.join(
                REPO_DIR, "lib", "github_changelog_generator", fname,
            )
            if os.path.isfile(path):
                with open(path, "r") as f:
                    content += f.read()
        return content

    def test_feat_maps_to_added(self):
        content = self._read_all_sources()
        assert re.search(r"Added|added", content), (
            "Expected 'feat' mapped to 'Added' category"
        )

    def test_fix_maps_to_fixed(self):
        content = self._read_all_sources()
        assert re.search(r"Fixed|fixed", content), (
            "Expected 'fix' mapped to 'Fixed' category"
        )

    def test_breaking_category(self):
        content = self._read_all_sources()
        assert re.search(r"BREAKING", content), (
            "Expected 'BREAKING CHANGES' category"
        )


class TestSemanticSemverCalculator:
    """Verify semantic version calculation."""

    def _read_semver(self):
        path = os.path.join(
            REPO_DIR, "lib", "github_changelog_generator",
            "semver_calculator.rb",
        )
        with open(path, "r") as f:
            return f.read()

    def test_class_definition(self):
        content = self._read_semver()
        assert re.search(r"class\s+SemverCalculator", content), (
            "Expected SemverCalculator class"
        )

    def test_major_version_bump(self):
        content = self._read_semver()
        assert re.search(r"major", content, re.IGNORECASE), (
            "Expected major version bump logic"
        )

    def test_minor_version_bump(self):
        content = self._read_semver()
        assert re.search(r"minor", content, re.IGNORECASE), (
            "Expected minor version bump logic"
        )

    def test_patch_version_bump(self):
        content = self._read_semver()
        assert re.search(r"patch", content, re.IGNORECASE), (
            "Expected patch version bump logic"
        )

    def test_invalid_version_error(self):
        content = self._read_semver()
        assert re.search(r"InvalidVersion|Error|raise|ArgumentError", content), (
            "Expected error handling for invalid versions"
        )

    def test_prerelease_handling(self):
        content = self._read_semver()
        assert re.search(r"pre|alpha|beta|rc|-", content, re.IGNORECASE), (
            "Expected pre-release version handling"
        )


class TestSemanticChangelogFormatter:
    """Verify Keep a Changelog formatting."""

    def _read_formatter(self):
        path = os.path.join(
            REPO_DIR, "lib", "github_changelog_generator",
            "changelog_formatter.rb",
        )
        with open(path, "r") as f:
            return f.read()

    def test_class_definition(self):
        content = self._read_formatter()
        assert re.search(r"class\s+ChangelogFormatter", content), (
            "Expected ChangelogFormatter class"
        )

    def test_keepachangelog_header(self):
        content = self._read_formatter()
        assert re.search(r"Changelog|CHANGELOG|changelog|# Changelog", content), (
            "Expected Keep a Changelog format header"
        )

    def test_comparison_links(self):
        content = self._read_formatter()
        assert re.search(r"compare|http|url|link|diff", content, re.IGNORECASE), (
            "Expected comparison links between versions"
        )


class TestFunctionalRubySyntax:
    """Validate Ruby files have correct syntax structure."""

    def test_balanced_def_end(self):
        path = os.path.join(
            REPO_DIR, "lib", "github_changelog_generator", "conventional.rb",
        )
        with open(path, "r") as f:
            content = f.read()
        opens = len(re.findall(r"\b(class|module|def|do|if|unless|case|begin)\b", content))
        ends = len(re.findall(r"\bend\b", content))
        # One-liner if/unless on a single line might not need end
        # but opens should approximate ends
        assert abs(opens - ends) <= 5, (
            f"Unbalanced Ruby blocks: {opens} opens vs {ends} ends"
        )

    def test_rspec_specs_exist(self):
        spec_dir = os.path.join(REPO_DIR, "spec")
        spec_files = []
        for root, dirs, files in os.walk(spec_dir):
            for f in files:
                if f.endswith("_spec.rb"):
                    spec_files.append(os.path.join(root, f))
        conventional_specs = [
            s for s in spec_files if "conventional" in s or "semver" in s or "changelog" in s
        ]
        assert len(conventional_specs) >= 1, (
            "Expected at least one RSpec file for the new modules"
        )

    def test_rspec_describe_blocks(self):
        spec_dir = os.path.join(REPO_DIR, "spec")
        found_describe = False
        for root, dirs, files in os.walk(spec_dir):
            for f in files:
                if f.endswith("_spec.rb") and any(
                    kw in f for kw in ["conventional", "semver", "changelog"]
                ):
                    with open(os.path.join(root, f), "r") as fh:
                        content = fh.read()
                    if re.search(r"describe\s+", content):
                        found_describe = True
                        break
            if found_describe:
                break
        assert found_describe, "Expected RSpec describe blocks in spec files"

    def test_module_namespace(self):
        path = os.path.join(
            REPO_DIR, "lib", "github_changelog_generator", "conventional.rb",
        )
        with open(path, "r") as f:
            content = f.read()
        assert re.search(r"module\s+GitHubChangelogGenerator|module\s+Github", content, re.IGNORECASE), (
            "Expected GitHubChangelogGenerator module namespace"
        )
