"""
Test skill: changelog-automation
Verify that the Agent correctly implements automated changelog generation
using Conventional Commits in Ruby for github-changelog-generator.
"""

import os
import re
import pytest


class TestChangelogAutomation:
    REPO_DIR = "/workspace/github-changelog-generator"

    PARSER = "lib/github_changelog_generator/conventional_parser.rb"
    CATEGORIZER = "lib/github_changelog_generator/categorizer.rb"
    VERSION_INFERRER = "lib/github_changelog_generator/version_inferrer.rb"
    FORMATTER = "lib/github_changelog_generator/markdown_formatter.rb"
    PARSER_SPEC = "spec/conventional_parser_spec.rb"
    CATEGORIZER_SPEC = "spec/categorizer_spec.rb"
    VERSION_SPEC = "spec/version_inferrer_spec.rb"
    FORMATTER_SPEC = "spec/markdown_formatter_spec.rb"

    def _read_file(self, rel_path):
        filepath = os.path.join(self.REPO_DIR, rel_path)
        with open(filepath) as f:
            return f.read()

    # === File Path Checks ===

    def test_parser_file_exists(self):
        filepath = os.path.join(self.REPO_DIR, self.PARSER)
        assert os.path.exists(filepath), f"conventional_parser.rb not found"

    def test_categorizer_file_exists(self):
        filepath = os.path.join(self.REPO_DIR, self.CATEGORIZER)
        assert os.path.exists(filepath), f"categorizer.rb not found"

    def test_version_inferrer_file_exists(self):
        filepath = os.path.join(self.REPO_DIR, self.VERSION_INFERRER)
        assert os.path.exists(filepath), f"version_inferrer.rb not found"

    def test_formatter_file_exists(self):
        filepath = os.path.join(self.REPO_DIR, self.FORMATTER)
        assert os.path.exists(filepath), f"markdown_formatter.rb not found"

    def test_spec_files_exist(self):
        for path in [self.PARSER_SPEC, self.CATEGORIZER_SPEC,
                      self.VERSION_SPEC, self.FORMATTER_SPEC]:
            filepath = os.path.join(self.REPO_DIR, path)
            assert os.path.exists(filepath), f"Spec file not found: {filepath}"

    # === Semantic Checks ===

    def test_parser_extracts_conventional_commit(self):
        """Verify parser recognizes type(scope)!: description pattern"""
        content = self._read_file(self.PARSER)
        assert "ConventionalParser" in content, "Missing ConventionalParser class"
        # Should parse type, scope, breaking, description
        for field in ["type", "scope", "breaking", "description"]:
            assert field in content, f"Parser missing field extraction: {field}"

    def test_parser_recognizes_all_types(self):
        """Verify parser recognizes feat, fix, docs, perf, etc."""
        content = self._read_file(self.PARSER)
        types = ["feat", "fix", "docs", "perf", "refactor", "test"]
        found = sum(1 for t in types if t in content)
        assert found >= 4, f"Parser missing commit types, found {found}/6"

    def test_parser_handles_breaking_change(self):
        """Verify parser detects ! and BREAKING CHANGE footer"""
        content = self._read_file(self.PARSER)
        assert "BREAKING CHANGE" in content or "breaking" in content, \
            "Parser missing BREAKING CHANGE detection"

    def test_categorizer_groups_into_sections(self):
        """Verify categorizer maps types to changelog sections"""
        content = self._read_file(self.CATEGORIZER)
        assert "Categorizer" in content, "Missing Categorizer class"
        for section in ["Features", "Bug Fixes", "Breaking Changes"]:
            assert section in content, f"Categorizer missing section: {section}"

    def test_version_inferrer_semver_rules(self):
        """Verify version inferrer follows SemVer bump rules"""
        content = self._read_file(self.VERSION_INFERRER)
        assert "VersionInferrer" in content, "Missing VersionInferrer class"
        assert "major" in content.lower(), "Version inferrer missing major bump"
        assert "minor" in content.lower(), "Version inferrer missing minor bump"
        assert "patch" in content.lower(), "Version inferrer missing patch bump"

    def test_version_inferrer_zero_x_convention(self):
        """Verify 0.x SemVer convention (breaking → minor, feat → patch)"""
        content = self._read_file(self.VERSION_INFERRER)
        has_zero_x = bool(re.search(r'(0\.|zero|pre.*1\.0)', content, re.IGNORECASE))
        assert has_zero_x, "Version inferrer missing 0.x SemVer convention"

    def test_version_inferrer_prerelease(self):
        """Verify pre-release label support"""
        content = self._read_file(self.VERSION_INFERRER)
        has_pre = "pre_release" in content or "prerelease" in content or "pre-release" in content
        assert has_pre, "Version inferrer missing pre-release support"

    def test_formatter_produces_markdown(self):
        """Verify Markdown formatter produces structured output"""
        content = self._read_file(self.FORMATTER)
        assert "MarkdownFormatter" in content, "Missing MarkdownFormatter class"
        assert "##" in content or "format" in content, \
            "Formatter missing Markdown heading generation"

    def test_formatter_includes_scope_and_pr_links(self):
        """Verify formatter includes scope prefix and PR links"""
        content = self._read_file(self.FORMATTER)
        assert "scope" in content, "Formatter missing scope in entries"
        has_links = bool(re.search(r'(pr_number|pull|issue|link|#)', content))
        assert has_links, "Formatter missing PR/issue links"

    # === Functional Checks ===

    def test_parser_ruby_syntax(self):
        """Verify parser.rb has valid Ruby syntax markers"""
        content = self._read_file(self.PARSER)
        assert "class " in content or "module " in content, \
            "Parser missing Ruby class/module definition"
        assert "def " in content, "Parser missing method definitions"
        assert "end" in content, "Parser missing end keyword"

    def test_categorizer_handles_empty_sections(self):
        """Verify categorizer omits empty categories"""
        content = self._read_file(self.CATEGORIZER)
        has_empty_check = bool(re.search(
            r'(empty\?|reject|compact|length.*0|size.*0|blank)',
            content,
        ))
        assert has_empty_check, "Categorizer missing empty section removal"

    def test_specs_have_describe_blocks(self):
        """Verify spec files have RSpec describe/it blocks"""
        for path in [self.PARSER_SPEC, self.CATEGORIZER_SPEC,
                      self.VERSION_SPEC, self.FORMATTER_SPEC]:
            content = self._read_file(path)
            assert "describe" in content, f"{path} missing describe block"
            assert "it " in content, f"{path} missing it block"
