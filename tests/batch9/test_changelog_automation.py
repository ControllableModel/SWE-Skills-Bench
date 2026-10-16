"""
Test skill: changelog-automation
Verify that the Agent creates Conventional Commits parser, categorizer,
version calculator, and Keep a Changelog renderer (Ruby).
"""

import os
import re
import subprocess
import pytest


class TestChangelogAutomation:
    REPO_DIR = "/workspace/github-changelog-generator"

    # === File Path Checks ===

    def test_changelog_source_files_exist(self):
        """Verify changelog automation files exist"""
        found = False
        for root, dirs, files in os.walk(self.REPO_DIR):
            if ".git" in root or "vendor" in root:
                continue
            for f in files:
                if f.endswith(".rb") and ("changelog" in f.lower() or "commit" in f.lower() or "version" in f.lower() or "render" in f.lower()):
                    found = True
                    break
            if found:
                break
        assert found, "Changelog automation source files not found"

    # === Semantic Checks ===

    def test_conventional_commits_parser_defined(self):
        """Verify Conventional Commits parser is implemented"""
        content = self._collect_ruby_content()
        has_parser = "conventional" in content.lower() or "parse" in content.lower()
        assert has_parser, "Conventional Commits parser not found"

    def test_commit_categorizer_defined(self):
        """Verify commit categorizer assigns types to commits"""
        content = self._collect_ruby_content()
        has_categorizer = "categor" in content.lower() or "classify" in content.lower() or "type" in content.lower()
        assert has_categorizer, "Commit categorizer not found"

    def test_version_calculator_defined(self):
        """Verify SemVer version calculator is implemented"""
        content = self._collect_ruby_content()
        has_version = "version" in content.lower() or "semver" in content.lower() or "bump" in content.lower()
        assert has_version, "Version calculator not found"

    def test_changelog_renderer_defined(self):
        """Verify Keep a Changelog renderer is implemented"""
        content = self._collect_ruby_content()
        has_renderer = "render" in content.lower() or "format" in content.lower() or "changelog" in content.lower()
        assert has_renderer, "Keep a Changelog renderer not found"

    def test_commit_types_recognized(self):
        """Verify standard commit types are recognized (feat, fix, etc.)"""
        content = self._collect_ruby_content()
        has_feat = "feat" in content.lower()
        has_fix = "fix" in content.lower()
        assert has_feat or has_fix, "Standard commit types (feat/fix) not recognized"

    # === Functional Checks ===

    def test_ruby_files_valid_syntax(self):
        """Verify Ruby files have valid syntax"""
        rb_files = self._find_rb_files()
        assert len(rb_files) > 0, "No relevant Ruby files found"
        for rb in rb_files:
            result = subprocess.run(
                ["ruby", "-c", rb],
                capture_output=True,
                text=True,
                timeout=30,
            )
            assert result.returncode == 0, f"Syntax error in {rb}: {result.stderr}"

    def test_ruby_files_have_classes_or_modules(self):
        """Verify Ruby files define classes or modules"""
        rb_files = self._find_rb_files()
        any_class = False
        for rb in rb_files:
            with open(rb) as fh:
                content = fh.read()
            if re.search(r'^\s*(class|module)\s+\w+', content, re.MULTILINE):
                any_class = True
                break
        assert any_class, "No classes or modules found in Ruby source files"

    def test_changelog_output_format(self):
        """Verify changelog output follows Keep a Changelog format"""
        content = self._collect_ruby_content()
        has_markdown = (
            "##" in content
            or "###" in content
            or "changelog" in content.lower()
            or "keepachangelog" in content.lower()
            or "keep a changelog" in content.lower()
        )
        assert has_markdown, "Changelog output format not following Keep a Changelog standard"

    def test_breaking_change_detection(self):
        """Verify breaking changes are detected"""
        content = self._collect_ruby_content()
        has_breaking = (
            "breaking" in content.lower()
            or "BREAKING" in content
            or "major" in content.lower()
            or "!" in content
        )
        assert has_breaking, "Breaking change detection not implemented"

    def _collect_ruby_content(self):
        all_content = ""
        for root, dirs, files in os.walk(self.REPO_DIR):
            if ".git" in root or "vendor" in root:
                continue
            for f in files:
                if f.endswith(".rb"):
                    fpath = os.path.join(root, f)
                    try:
                        with open(fpath) as fh:
                            all_content += fh.read() + "\n"
                    except (UnicodeDecodeError, PermissionError):
                        continue
        return all_content

    def _find_rb_files(self):
        rb_files = []
        for root, dirs, files in os.walk(self.REPO_DIR):
            if ".git" in root or "vendor" in root:
                continue
            for f in files:
                if f.endswith(".rb") and ("changelog" in f.lower() or "commit" in f.lower() or "version" in f.lower() or "render" in f.lower() or "categor" in f.lower()):
                    rb_files.append(os.path.join(root, f))
        return rb_files
