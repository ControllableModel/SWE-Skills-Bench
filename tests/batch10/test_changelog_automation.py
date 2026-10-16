"""
Test skill: changelog-automation
Verify that the Agent correctly implements a Conventional Commit parser,
changelog renderer, and version calculator for github-changelog-generator.
"""

import os
import re
import subprocess
import pytest


class TestChangelogAutomation:
    REPO_DIR = "/workspace/github-changelog-generator"

    # === File Path Checks ===

    def test_conventional_commit_rb_exists(self):
        """Verify conventional_commit.rb was created"""
        path = os.path.join(
            self.REPO_DIR,
            "lib/github_changelog_generator/conventional_commit.rb",
        )
        assert os.path.exists(path), f"conventional_commit.rb not found"

    def test_changelog_renderer_rb_exists(self):
        """Verify changelog_renderer.rb was created"""
        path = os.path.join(
            self.REPO_DIR,
            "lib/github_changelog_generator/changelog_renderer.rb",
        )
        assert os.path.exists(path), f"changelog_renderer.rb not found"

    def test_version_calculator_rb_exists(self):
        """Verify version_calculator.rb was created"""
        path = os.path.join(
            self.REPO_DIR,
            "lib/github_changelog_generator/version_calculator.rb",
        )
        assert os.path.exists(path), f"version_calculator.rb not found"

    def test_commit_spec_exists(self):
        """Verify conventional_commit_spec.rb was created"""
        path = os.path.join(
            self.REPO_DIR, "spec/unit/conventional_commit_spec.rb"
        )
        assert os.path.exists(path), f"conventional_commit_spec.rb not found"

    def test_renderer_spec_exists(self):
        """Verify changelog_renderer_spec.rb was created"""
        path = os.path.join(
            self.REPO_DIR, "spec/unit/changelog_renderer_spec.rb"
        )
        assert os.path.exists(path), f"changelog_renderer_spec.rb not found"

    def test_version_calculator_spec_exists(self):
        """Verify version_calculator_spec.rb was created"""
        path = os.path.join(
            self.REPO_DIR, "spec/unit/version_calculator_spec.rb"
        )
        assert os.path.exists(path), f"version_calculator_spec.rb not found"

    # === Semantic Checks: ConventionalCommit Parser ===

    def test_parse_method_defined(self):
        """Verify ConventionalCommit.parse method is defined"""
        path = os.path.join(
            self.REPO_DIR,
            "lib/github_changelog_generator/conventional_commit.rb",
        )
        with open(path) as f:
            content = f.read()
        assert "def" in content and "parse" in content, (
            "Should define parse method"
        )

    def test_parser_handles_type(self):
        """Verify parser extracts type field"""
        path = os.path.join(
            self.REPO_DIR,
            "lib/github_changelog_generator/conventional_commit.rb",
        )
        with open(path) as f:
            content = f.read()
        assert "type" in content, "Should extract type field"

    def test_parser_handles_scope(self):
        """Verify parser extracts scope from parentheses"""
        path = os.path.join(
            self.REPO_DIR,
            "lib/github_changelog_generator/conventional_commit.rb",
        )
        with open(path) as f:
            content = f.read()
        assert "scope" in content, "Should extract scope field"

    def test_parser_detects_breaking_via_bang(self):
        """Verify breaking detection via ! after type"""
        path = os.path.join(
            self.REPO_DIR,
            "lib/github_changelog_generator/conventional_commit.rb",
        )
        with open(path) as f:
            content = f.read()
        assert "!" in content, "Should detect ! for breaking changes"

    def test_parser_detects_breaking_footer(self):
        """Verify BREAKING CHANGE footer detection"""
        path = os.path.join(
            self.REPO_DIR,
            "lib/github_changelog_generator/conventional_commit.rb",
        )
        with open(path) as f:
            content = f.read()
        assert "BREAKING CHANGE" in content, (
            "Should detect BREAKING CHANGE footer"
        )

    def test_parser_returns_nil_for_invalid(self):
        """Verify nil return for non-conventional messages"""
        path = os.path.join(
            self.REPO_DIR,
            "lib/github_changelog_generator/conventional_commit.rb",
        )
        with open(path) as f:
            content = f.read()
        assert "nil" in content, "Should return nil for non-conventional messages"

    def test_supported_types_listed(self):
        """Verify all supported commit types"""
        path = os.path.join(
            self.REPO_DIR,
            "lib/github_changelog_generator/conventional_commit.rb",
        )
        with open(path) as f:
            content = f.read()
        for commit_type in ["feat", "fix", "docs", "refactor", "perf", "chore"]:
            assert commit_type in content, (
                f"Should support '{commit_type}' commit type"
            )

    # === Semantic Checks: ChangelogRenderer ===

    def test_renderer_class_defined(self):
        """Verify ChangelogRenderer class is defined"""
        path = os.path.join(
            self.REPO_DIR,
            "lib/github_changelog_generator/changelog_renderer.rb",
        )
        with open(path) as f:
            content = f.read()
        assert "ChangelogRenderer" in content, (
            "ChangelogRenderer class should be defined"
        )

    def test_renderer_has_render_method(self):
        """Verify render method is defined"""
        path = os.path.join(
            self.REPO_DIR,
            "lib/github_changelog_generator/changelog_renderer.rb",
        )
        with open(path) as f:
            content = f.read()
        assert "def render" in content, "Should have render method"

    def test_renderer_section_headers(self):
        """Verify Keep a Changelog section headers"""
        path = os.path.join(
            self.REPO_DIR,
            "lib/github_changelog_generator/changelog_renderer.rb",
        )
        with open(path) as f:
            content = f.read()
        for section in ["Added", "Changed", "Fixed", "Deprecated", "Removed", "Security"]:
            assert section in content, f"Should have '{section}' section"

    def test_renderer_comparison_link(self):
        """Verify comparison link at bottom of output"""
        path = os.path.join(
            self.REPO_DIR,
            "lib/github_changelog_generator/changelog_renderer.rb",
        )
        with open(path) as f:
            content = f.read()
        assert "compare" in content, "Should include comparison link"

    def test_renderer_scoped_entries(self):
        """Verify scoped entries formatted with bold scope"""
        path = os.path.join(
            self.REPO_DIR,
            "lib/github_changelog_generator/changelog_renderer.rb",
        )
        with open(path) as f:
            content = f.read()
        assert "**" in content, "Should format scope in bold"

    # === Semantic Checks: VersionCalculator ===

    def test_version_calculator_class(self):
        """Verify VersionCalculator class is defined"""
        path = os.path.join(
            self.REPO_DIR,
            "lib/github_changelog_generator/version_calculator.rb",
        )
        with open(path) as f:
            content = f.read()
        assert "VersionCalculator" in content, (
            "VersionCalculator class should be defined"
        )

    def test_next_version_method(self):
        """Verify next_version method is defined"""
        path = os.path.join(
            self.REPO_DIR,
            "lib/github_changelog_generator/version_calculator.rb",
        )
        with open(path) as f:
            content = f.read()
        assert "next_version" in content, "Should have next_version method"

    def test_version_bumps_major(self):
        """Verify major version bump for breaking changes"""
        path = os.path.join(
            self.REPO_DIR,
            "lib/github_changelog_generator/version_calculator.rb",
        )
        with open(path) as f:
            content = f.read()
        assert "breaking" in content.lower(), (
            "Should handle breaking changes for major bump"
        )

    def test_version_zero_major_special(self):
        """Verify major-0 special case (minor bump instead of major)"""
        path = os.path.join(
            self.REPO_DIR,
            "lib/github_changelog_generator/version_calculator.rb",
        )
        with open(path) as f:
            content = f.read()
        # Either checks major == 0 or has specific 0.x handling
        assert "0" in content, "Should handle major-0 special case"

    def test_prerelease_handling(self):
        """Verify pre-release version handling"""
        path = os.path.join(
            self.REPO_DIR,
            "lib/github_changelog_generator/version_calculator.rb",
        )
        with open(path) as f:
            content = f.read()
        assert "pre" in content.lower() or "beta" in content.lower() or "graduate" in content.lower(), (
            "Should handle pre-release versions"
        )

    # === Functional Checks ===

    def test_ruby_syntax_conventional_commit(self):
        """Verify conventional_commit.rb has valid Ruby syntax"""
        path = os.path.join(
            self.REPO_DIR,
            "lib/github_changelog_generator/conventional_commit.rb",
        )
        result = subprocess.run(
            ["ruby", "-c", path],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, (
            f"Ruby syntax error:\n{result.stderr}"
        )

    def test_ruby_syntax_renderer(self):
        """Verify changelog_renderer.rb has valid Ruby syntax"""
        path = os.path.join(
            self.REPO_DIR,
            "lib/github_changelog_generator/changelog_renderer.rb",
        )
        result = subprocess.run(
            ["ruby", "-c", path],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, (
            f"Ruby syntax error:\n{result.stderr}"
        )

    def test_ruby_syntax_version_calculator(self):
        """Verify version_calculator.rb has valid Ruby syntax"""
        path = os.path.join(
            self.REPO_DIR,
            "lib/github_changelog_generator/version_calculator.rb",
        )
        result = subprocess.run(
            ["ruby", "-c", path],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, (
            f"Ruby syntax error:\n{result.stderr}"
        )

    def test_commit_specs_pass(self):
        """Verify conventional commit specs pass"""
        result = subprocess.run(
            ["bundle", "exec", "rspec", "spec/unit/conventional_commit_spec.rb"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, (
            f"RSpec failed:\n{result.stdout}\n{result.stderr}"
        )

    def test_renderer_specs_pass(self):
        """Verify renderer specs pass"""
        result = subprocess.run(
            ["bundle", "exec", "rspec", "spec/unit/changelog_renderer_spec.rb"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, (
            f"RSpec failed:\n{result.stdout}\n{result.stderr}"
        )

    def test_version_calculator_specs_pass(self):
        """Verify version calculator specs pass"""
        result = subprocess.run(
            ["bundle", "exec", "rspec", "spec/unit/version_calculator_spec.rb"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, (
            f"RSpec failed:\n{result.stdout}\n{result.stderr}"
        )
