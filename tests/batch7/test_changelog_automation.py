"""
Test skill: changelog-automation
Verify that the Agent implements Conventional Commits Parsing and Scoped
Changelog generation in github-changelog-generator — ConventionalCommitParser
(regex-based type/scope/description/breaking/footers), ScopedChangelog (Markdown
grouped by type and scope with breaking changes first).
"""

import os
import re
import subprocess
import pytest


class TestChangelogAutomation:
    REPO_DIR = "/workspace/github-changelog-generator"

    # ────── helpers ──────

    def _read(self, rel_path):
        fpath = os.path.join(self.REPO_DIR, rel_path)
        with open(fpath, "r") as f:
            return f.read()

    def _exists(self, rel_path):
        return os.path.isfile(os.path.join(self.REPO_DIR, rel_path))

    # === File Path Checks ===

    def test_conventional_commit_parser_exists(self):
        """ConventionalCommitParser file must exist"""
        assert self._exists(
            "lib/github_changelog_generator/parser/conventional_commit_parser.rb"
        )

    def test_scoped_changelog_exists(self):
        """ScopedChangelog file must exist"""
        assert self._exists(
            "lib/github_changelog_generator/generator/scoped_changelog.rb"
        )

    def test_conventional_commit_parser_spec_exists(self):
        """Parser spec must exist"""
        found = False
        for candidate in [
            "spec/unit/parser/conventional_commit_parser_spec.rb",
            "spec/parser/conventional_commit_parser_spec.rb",
            "spec/conventional_commit_parser_spec.rb",
        ]:
            if self._exists(candidate):
                found = True
                break
        assert found, "No spec file for ConventionalCommitParser found"

    def test_scoped_changelog_spec_exists(self):
        """Scoped changelog spec must exist"""
        found = False
        for candidate in [
            "spec/unit/generator/scoped_changelog_spec.rb",
            "spec/generator/scoped_changelog_spec.rb",
            "spec/scoped_changelog_spec.rb",
        ]:
            if self._exists(candidate):
                found = True
                break
        assert found, "No spec file for ScopedChangelog found"

    # === Semantic Checks — ConventionalCommitParser ===

    def test_parser_class_definition(self):
        """ConventionalCommitParser class must be defined"""
        src = self._read(
            "lib/github_changelog_generator/parser/conventional_commit_parser.rb"
        )
        assert re.search(r'class\s+ConventionalCommitParser', src), (
            "ConventionalCommitParser class not found"
        )

    def test_parser_parse_method(self):
        """parse method must exist"""
        src = self._read(
            "lib/github_changelog_generator/parser/conventional_commit_parser.rb"
        )
        assert re.search(r'def\s+parse\b', src), "parse method not found"

    def test_parser_parse_all_method(self):
        """parse_all method that handles a collection of commits"""
        src = self._read(
            "lib/github_changelog_generator/parser/conventional_commit_parser.rb"
        )
        assert re.search(r'def\s+parse_all\b', src), "parse_all method not found"

    def test_parser_regex_pattern(self):
        """Must use a regex for conventional commit format (type(scope): desc)"""
        src = self._read(
            "lib/github_changelog_generator/parser/conventional_commit_parser.rb"
        )
        # Should have a regex literal or Regexp.new
        assert "Regexp" in src or re.search(r'/.*\\(/', src) or "PATTERN" in src.upper() or "regex" in src.lower(), (
            "No regex pattern found for conventional commit parsing"
        )

    def test_parser_type_scope_extraction(self):
        """Must extract type, scope, description"""
        src = self._read(
            "lib/github_changelog_generator/parser/conventional_commit_parser.rb"
        )
        lower = src.lower()
        assert "type" in lower, "No 'type' extraction"
        assert "scope" in lower, "No 'scope' extraction"
        assert "description" in lower or "desc" in lower or "subject" in lower, (
            "No description extraction"
        )

    def test_parser_breaking_change_detection(self):
        """Must detect breaking changes (! or BREAKING CHANGE footer)"""
        src = self._read(
            "lib/github_changelog_generator/parser/conventional_commit_parser.rb"
        )
        lower = src.lower()
        assert "breaking" in lower, "Breaking change detection not found"

    def test_parser_footer_parsing(self):
        """Must parse commit footers"""
        src = self._read(
            "lib/github_changelog_generator/parser/conventional_commit_parser.rb"
        )
        lower = src.lower()
        assert "footer" in lower or "trailer" in lower, (
            "Footer/trailer parsing not found"
        )

    # === Semantic Checks — ScopedChangelog ===

    def test_scoped_changelog_class(self):
        """ScopedChangelog class must be defined"""
        src = self._read(
            "lib/github_changelog_generator/generator/scoped_changelog.rb"
        )
        assert re.search(r'class\s+ScopedChangelog', src), (
            "ScopedChangelog class not found"
        )

    def test_scoped_changelog_generate(self):
        """generate method must produce Markdown"""
        src = self._read(
            "lib/github_changelog_generator/generator/scoped_changelog.rb"
        )
        assert re.search(r'def\s+generate\b', src), "generate method not found"

    def test_scoped_changelog_grouping(self):
        """Must group entries by type or scope"""
        src = self._read(
            "lib/github_changelog_generator/generator/scoped_changelog.rb"
        )
        lower = src.lower()
        assert "group" in lower or "section" in lower or "type" in lower, (
            "Grouping logic not found"
        )

    def test_scoped_changelog_breaking_section(self):
        """Breaking changes section rendered first"""
        src = self._read(
            "lib/github_changelog_generator/generator/scoped_changelog.rb"
        )
        lower = src.lower()
        assert "breaking" in lower, "Breaking changes section not found"

    def test_scoped_changelog_type_headings(self):
        """Must produce type headings (Features, Bug Fixes, etc.)"""
        src = self._read(
            "lib/github_changelog_generator/generator/scoped_changelog.rb"
        )
        # Markdown headings or heading constants
        assert "###" in src or "heading" in src.lower() or "Features" in src or "Bug Fixes" in src, (
            "Type headings not found"
        )

    def test_scoped_changelog_sha_links(self):
        """Must include SHA links in output"""
        src = self._read(
            "lib/github_changelog_generator/generator/scoped_changelog.rb"
        )
        lower = src.lower()
        assert "sha" in lower or "commit" in lower or "link" in lower or "url" in lower, (
            "SHA link generation not found"
        )

    # === Functional Checks ===

    def test_ruby_syntax_parser(self):
        """Parser file must have valid Ruby syntax"""
        result = subprocess.run(
            ["ruby", "-c",
             "lib/github_changelog_generator/parser/conventional_commit_parser.rb"],
            capture_output=True, text=True, cwd=self.REPO_DIR, timeout=30,
        )
        assert result.returncode == 0, (
            f"Syntax check failed:\n{result.stderr}"
        )

    def test_ruby_syntax_scoped_changelog(self):
        """ScopedChangelog file must have valid Ruby syntax"""
        result = subprocess.run(
            ["ruby", "-c",
             "lib/github_changelog_generator/generator/scoped_changelog.rb"],
            capture_output=True, text=True, cwd=self.REPO_DIR, timeout=30,
        )
        assert result.returncode == 0, (
            f"Syntax check failed:\n{result.stderr}"
        )

    def test_rspec_conventional_parser(self):
        """ConventionalCommitParser specs must pass"""
        # Find the spec file
        spec = None
        for candidate in [
            "spec/unit/parser/conventional_commit_parser_spec.rb",
            "spec/parser/conventional_commit_parser_spec.rb",
            "spec/conventional_commit_parser_spec.rb",
        ]:
            if self._exists(candidate):
                spec = candidate
                break
        assert spec, "Spec file not found"
        result = subprocess.run(
            ["bundle", "exec", "rspec", spec, "--format", "documentation"],
            capture_output=True, text=True, cwd=self.REPO_DIR, timeout=120,
        )
        assert result.returncode == 0, (
            f"RSpec failed:\n{result.stdout}\n{result.stderr}"
        )

    def test_rspec_scoped_changelog(self):
        """ScopedChangelog specs must pass"""
        spec = None
        for candidate in [
            "spec/unit/generator/scoped_changelog_spec.rb",
            "spec/generator/scoped_changelog_spec.rb",
            "spec/scoped_changelog_spec.rb",
        ]:
            if self._exists(candidate):
                spec = candidate
                break
        assert spec, "Spec file not found"
        result = subprocess.run(
            ["bundle", "exec", "rspec", spec, "--format", "documentation"],
            capture_output=True, text=True, cwd=self.REPO_DIR, timeout=120,
        )
        assert result.returncode == 0, (
            f"RSpec failed:\n{result.stdout}\n{result.stderr}"
        )
