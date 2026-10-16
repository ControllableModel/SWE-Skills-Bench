"""
Test skill: changelog-automation
Verify that the Agent creates changelog generation configuration for
github-changelog-generator including section config class, Keep a
Changelog formatter, and configuration file.
"""

import os
import re
import subprocess
import pytest


class TestChangelogAutomation:
    REPO_DIR = "/workspace/github-changelog-generator"

    # === File Path Checks ===

    def test_section_config_exists(self):
        """Verify section_config.rb exists"""
        path = os.path.join(
            self.REPO_DIR,
            "lib/github_changelog_generator/section_config.rb",
        )
        assert os.path.exists(path), f"section_config.rb not found at {path}"

    def test_keep_a_changelog_formatter_exists(self):
        """Verify keep_a_changelog.rb formatter exists"""
        path = os.path.join(
            self.REPO_DIR,
            "lib/github_changelog_generator/formatter/keep_a_changelog.rb",
        )
        assert os.path.exists(path), f"keep_a_changelog.rb not found"

    def test_config_file_exists(self):
        """Verify .github_changelog_generator config exists"""
        path = os.path.join(
            self.REPO_DIR, ".github_changelog_generator"
        )
        assert os.path.exists(path), f".github_changelog_generator not found"

    # === Semantic Checks ===

    def test_label_to_section_mapping(self):
        """Verify label-to-section mapping (enhancement->Features, bug->Bug Fixes)"""
        combined = ""
        for fname in [
            "lib/github_changelog_generator/section_config.rb",
            ".github_changelog_generator",
        ]:
            path = os.path.join(self.REPO_DIR, fname)
            if os.path.exists(path):
                with open(path) as f:
                    combined += f.read()

        section_indicators = [
            "enhancement", "bug", "breaking", "feature",
            "Features", "Bug Fixes", "Breaking",
        ]
        found = [ind for ind in section_indicators if ind in combined]
        assert len(found) >= 3, (
            f"Should map labels to sections. Found: {found}"
        )

    def test_at_least_four_sections(self):
        """Verify at least four distinct changelog sections"""
        combined = ""
        for fname in [
            "lib/github_changelog_generator/section_config.rb",
            ".github_changelog_generator",
        ]:
            path = os.path.join(self.REPO_DIR, fname)
            if os.path.exists(path):
                with open(path) as f:
                    combined += f.read()

        section_headings = [
            "Feature", "Bug", "Breaking", "Deprecat",
            "Security", "Documentation", "Performance",
            "Maintenance", "Refactor",
        ]
        found = [s for s in section_headings if s.lower() in combined.lower()]
        assert len(found) >= 4, (
            f"Should define at least 4 sections. Found: {found}"
        )

    def test_unlabeled_fallback(self):
        """Verify unlabeled items have a default section"""
        combined = ""
        for fname in [
            "lib/github_changelog_generator/section_config.rb",
            ".github_changelog_generator",
        ]:
            path = os.path.join(self.REPO_DIR, fname)
            if os.path.exists(path):
                with open(path) as f:
                    combined += f.read()

        fallback_indicators = [
            "unlabeled", "default", "other", "misc",
            "uncategorized", "Other",
        ]
        found = [ind for ind in fallback_indicators if ind in combined.lower()]
        assert len(found) >= 1, (
            f"Should handle unlabeled items. Found: {found}"
        )

    def test_keep_a_changelog_format(self):
        """Verify Keep a Changelog format is implemented"""
        path = os.path.join(
            self.REPO_DIR,
            "lib/github_changelog_generator/formatter/keep_a_changelog.rb",
        )
        with open(path) as f:
            content = f.read()

        format_indicators = [
            "Keep a Changelog", "keepachangelog",
            "##", "###", "Added", "Changed", "Fixed",
            "format", "render", "generate",
        ]
        found = [ind for ind in format_indicators if ind in content]
        assert len(found) >= 2, (
            f"Should implement Keep a Changelog format. Found: {found}"
        )

    def test_pr_links_and_attribution(self):
        """Verify PR/issue links and contributor attribution"""
        path = os.path.join(
            self.REPO_DIR,
            "lib/github_changelog_generator/formatter/keep_a_changelog.rb",
        )
        with open(path) as f:
            content = f.read().lower()

        link_indicators = [
            "url", "link", "pr", "pull", "issue",
            "contributor", "author", "attribution",
        ]
        found = [ind for ind in link_indicators if ind in content]
        assert len(found) >= 2, (
            f"Should include PR links and attribution. Found: {found}"
        )

    def test_inclusion_exclusion_rules(self):
        """Verify inclusion/exclusion rules in config"""
        path = os.path.join(
            self.REPO_DIR, ".github_changelog_generator"
        )
        with open(path) as f:
            content = f.read().lower()

        rule_indicators = [
            "exclude", "include", "filter", "ignore",
            "skip", "label",
        ]
        found = [ind for ind in rule_indicators if ind in content]
        assert len(found) >= 1, (
            f"Config should have inclusion/exclusion rules. Found: {found}"
        )

    # === Functional Checks ===

    def test_section_config_valid_ruby(self):
        """Verify section_config.rb passes Ruby syntax check"""
        path = os.path.join(
            self.REPO_DIR,
            "lib/github_changelog_generator/section_config.rb",
        )
        result = subprocess.run(
            ["ruby", "-c", path],
            capture_output=True, text=True, timeout=15,
        )
        assert result.returncode == 0, (
            f"section_config.rb has syntax errors: {result.stderr}"
        )

    def test_formatter_valid_ruby(self):
        """Verify keep_a_changelog.rb passes Ruby syntax check"""
        path = os.path.join(
            self.REPO_DIR,
            "lib/github_changelog_generator/formatter/keep_a_changelog.rb",
        )
        result = subprocess.run(
            ["ruby", "-c", path],
            capture_output=True, text=True, timeout=15,
        )
        assert result.returncode == 0, (
            f"keep_a_changelog.rb has syntax errors: {result.stderr}"
        )

    def test_section_config_defines_class(self):
        """Verify section_config.rb defines a class"""
        path = os.path.join(
            self.REPO_DIR,
            "lib/github_changelog_generator/section_config.rb",
        )
        with open(path) as f:
            content = f.read()

        assert re.search(r"class\s+\w+", content), (
            "section_config.rb should define a class"
        )
