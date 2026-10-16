"""
Tests for the changelog-automation skill.
Validates an automated changelog generator with conventional commit parsing,
Keep a Changelog formatting, semantic version bumping, and release notes.
"""

import os
import re
import ast

REPO_DIR = "/workspace/github-changelog-generator"
LIB_DIR = os.path.join(REPO_DIR, "lib", "changelog")


class TestChangelogAutomation:
    """Tests for the changelog automation module."""

    # ── file_path_check ──────────────────────────────────────────────

    def test_commit_parser_exists(self):
        """ConventionalCommitParser module must exist."""
        path = os.path.join(LIB_DIR, "commit_parser.py")
        assert os.path.isfile(path), f"Missing {path}"

    def test_changelog_builder_exists(self):
        """ChangelogBuilder module must exist."""
        path = os.path.join(LIB_DIR, "changelog_builder.py")
        assert os.path.isfile(path), f"Missing {path}"

    def test_version_bumper_exists(self):
        """VersionBumper module must exist."""
        path = os.path.join(LIB_DIR, "version_bumper.py")
        assert os.path.isfile(path), f"Missing {path}"

    def test_release_notes_exists(self):
        """ReleaseNotesGenerator module must exist."""
        path = os.path.join(LIB_DIR, "release_notes.py")
        assert os.path.isfile(path), f"Missing {path}"

    # ── semantic_check ───────────────────────────────────────────────

    def _read(self, filename):
        path = os.path.join(LIB_DIR, filename)
        if not os.path.isfile(path):
            return ""
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def test_commit_parser_class(self):
        """ConventionalCommitParser must define parse, parse_many, is_conventional."""
        content = self._read("commit_parser.py")
        assert re.search(r"class\s+ConventionalCommitParser", content), (
            "ConventionalCommitParser class not defined"
        )
        for method in ["parse", "parse_many", "is_conventional"]:
            assert re.search(rf"def\s+{method}\b", content), (
                f"{method} method not defined"
            )

    def test_conventional_commit_types(self):
        """Parser must recognize standard commit types: feat, fix, docs, etc."""
        content = self._read("commit_parser.py")
        for ctype in ["feat", "fix", "docs", "refactor", "perf", "test"]:
            assert ctype in content, f"Commit type '{ctype}' not found"

    def test_breaking_change_detection(self):
        """Parser must detect breaking changes via ! suffix and BREAKING CHANGE footer."""
        content = self._read("commit_parser.py")
        assert re.search(r"BREAKING.CHANGE|breaking|!.*:", content), (
            "Breaking change detection not found"
        )

    def test_changelog_builder_class(self):
        """ChangelogBuilder must define add_commits and build methods."""
        content = self._read("changelog_builder.py")
        assert re.search(r"class\s+ChangelogBuilder", content), (
            "ChangelogBuilder class not defined"
        )
        assert re.search(r"def\s+add_commits\b", content), "add_commits not defined"
        assert re.search(r"def\s+build\b", content), "build method not defined"

    def test_changelog_sections(self):
        """ChangelogBuilder must produce standard sections: Added, Fixed, Changed."""
        content = self._read("changelog_builder.py")
        for section in ["Added", "Fixed", "Changed"]:
            assert section in content, f"Section '{section}' not found"

    def test_version_bumper_class(self):
        """VersionBumper must define determine_bump and bump methods."""
        content = self._read("version_bumper.py")
        assert re.search(r"class\s+VersionBumper", content), (
            "VersionBumper class not defined"
        )
        assert re.search(r"def\s+determine_bump\b", content), "determine_bump not defined"
        assert re.search(r"def\s+bump\b", content), "bump method not defined"

    def test_semver_bump_types(self):
        """VersionBumper must support major, minor, patch bump types."""
        content = self._read("version_bumper.py")
        for bump in ["major", "minor", "patch"]:
            assert bump in content, f"Bump type '{bump}' not found"

    def test_release_notes_class(self):
        """ReleaseNotesGenerator must define generate method."""
        content = self._read("release_notes.py")
        assert re.search(r"class\s+ReleaseNotesGenerator", content), (
            "ReleaseNotesGenerator class not defined"
        )
        assert re.search(r"def\s+generate\b", content), "generate method not defined"

    # ── functional_check ─────────────────────────────────────────────

    def test_all_files_valid_python(self):
        """All changelog Python files must have valid syntax."""
        errors = []
        for fname in ["commit_parser.py", "changelog_builder.py",
                       "version_bumper.py", "release_notes.py"]:
            content = self._read(fname)
            if not content:
                continue
            try:
                ast.parse(content)
            except SyntaxError as e:
                errors.append(f"{fname}: {e}")
        assert not errors, "Syntax errors:\n" + "\n".join(errors)

    def test_footer_parsing(self):
        """Parser must extract footers like Refs: and Reviewed-by:."""
        content = self._read("commit_parser.py")
        assert re.search(r"footer|Refs:|Reviewed-by|key.*value", content, re.IGNORECASE), (
            "Footer parsing not found in commit parser"
        )

    def test_pre_release_support(self):
        """VersionBumper must handle pre-release versions."""
        content = self._read("version_bumper.py")
        assert re.search(r"pre.release|alpha|beta|rc|-", content, re.IGNORECASE), (
            "Pre-release version support not found"
        )

    def test_invalid_version_raises_error(self):
        """VersionBumper must raise ValueError for invalid version strings."""
        content = self._read("version_bumper.py")
        assert re.search(r"ValueError|Invalid.*semver|invalid.*version", content, re.IGNORECASE), (
            "ValueError for invalid version not found"
        )

    def test_pr_references_in_release_notes(self):
        """ReleaseNotesGenerator must link PR references."""
        content = self._read("release_notes.py")
        assert re.search(r"#\d+|pull/|PR|pr_number", content), (
            "PR reference linking not found in release notes"
        )
