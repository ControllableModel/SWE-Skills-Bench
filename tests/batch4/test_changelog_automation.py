"""
Tests for skill: changelog-automation
Repo: github-changelog-generator/github-changelog-generator
Image: zhangyiiiiii/swe-skills-bench-ruby
Task: Build an automated changelog generator from Conventional Commits
      with commit parsing, version calculation, and Keep a Changelog output.
"""

import ast
import importlib
import os
import re
import sys
import textwrap

import pytest

REPO_DIR = "/workspace/github-changelog-generator"
PKG_DIR = os.path.join(REPO_DIR, "lib", "changelog")

INIT_FILE = os.path.join(PKG_DIR, "__init__.py")
PARSER_FILE = os.path.join(PKG_DIR, "commit_parser.py")
VERSION_FILE = os.path.join(PKG_DIR, "version_calculator.py")
GENERATOR_FILE = os.path.join(PKG_DIR, "generator.py")
GIT_LOG_FILE = os.path.join(PKG_DIR, "git_log.py")


# ---------------------------------------------------------------------------
# Layer 1 — file_path_check
# ---------------------------------------------------------------------------

class TestFilePathCheck:
    """Verify all required changelog library files exist."""

    def test_init_exists(self):
        assert os.path.isfile(INIT_FILE), f"Missing {INIT_FILE}"

    def test_commit_parser_exists(self):
        assert os.path.isfile(PARSER_FILE), f"Missing {PARSER_FILE}"

    def test_version_calculator_exists(self):
        assert os.path.isfile(VERSION_FILE), f"Missing {VERSION_FILE}"

    def test_generator_exists(self):
        assert os.path.isfile(GENERATOR_FILE), f"Missing {GENERATOR_FILE}"

    def test_git_log_exists(self):
        assert os.path.isfile(GIT_LOG_FILE), f"Missing {GIT_LOG_FILE}"


# ---------------------------------------------------------------------------
# Layer 2 — semantic_check
# ---------------------------------------------------------------------------

class TestSemanticCommitParser:
    """Verify commit parser module structure."""

    @pytest.fixture(autouse=True)
    def _load(self):
        with open(PARSER_FILE, "r", encoding="utf-8") as f:
            self.src = f.read()
        self.tree = ast.parse(self.src)

    def test_parse_commit_function(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "parse_commit" in funcs, f"Expected parse_commit function; found {funcs}"

    def test_conventional_commit_class(self):
        names = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.ClassDef)]
        # Could be ConventionalCommit or dataclass
        assert any("Commit" in n or "commit" in n.lower() for n in names) or \
               "ConventionalCommit" in self.src, (
            "Expected a ConventionalCommit class or similar data structure"
        )

    def test_breaking_detection(self):
        assert "breaking" in self.src.lower(), (
            "Parser must detect breaking changes (BREAKING CHANGE footer or !)"
        )

    def test_scope_handling(self):
        assert "scope" in self.src.lower(), "Parser must handle optional scope"

    def test_footer_parsing(self):
        assert "footer" in self.src.lower(), "Parser must parse footers"

    def test_supported_types(self):
        """Verify common commit types are recognized."""
        for ctype in ["feat", "fix", "docs", "refactor", "perf"]:
            assert ctype in self.src, f"Expected commit type '{ctype}' in parser"


class TestSemanticVersionCalculator:
    """Verify version calculator module structure."""

    @pytest.fixture(autouse=True)
    def _load(self):
        with open(VERSION_FILE, "r", encoding="utf-8") as f:
            self.src = f.read()
        self.tree = ast.parse(self.src)

    def test_calculate_function(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert any("calculate" in f or "next_version" in f for f in funcs), (
            f"Expected calculate_next_version or similar; found {funcs}"
        )

    def test_major_bump_logic(self):
        src_lower = self.src.lower()
        assert "major" in src_lower, "Version calculator must handle MAJOR bumps"

    def test_minor_bump_logic(self):
        src_lower = self.src.lower()
        assert "minor" in src_lower, "Version calculator must handle MINOR bumps"

    def test_patch_bump_logic(self):
        src_lower = self.src.lower()
        assert "patch" in src_lower, "Version calculator must handle PATCH bumps"

    def test_semver_validation(self):
        assert "ValueError" in self.src, "Should raise ValueError for invalid semver"


class TestSemanticGenerator:
    """Verify changelog generator module structure."""

    @pytest.fixture(autouse=True)
    def _load(self):
        with open(GENERATOR_FILE, "r", encoding="utf-8") as f:
            self.src = f.read()
        self.tree = ast.parse(self.src)

    def test_generate_changelog_function(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert any("generate" in f and "changelog" in f for f in funcs), (
            f"Expected generate_changelog function; found {funcs}"
        )

    def test_section_headings(self):
        """Must produce Keep a Changelog sections."""
        for section in ["Added", "Fixed", "Changed"]:
            assert section in self.src, f"Expected section heading '{section}' in generator"

    def test_breaking_changes_section(self):
        assert "BREAKING" in self.src, "Must have a BREAKING CHANGES section"

    def test_full_changelog_assembly(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert any("full" in f.lower() and "changelog" in f.lower() for f in funcs), (
            f"Expected generate_full_changelog or similar; found {funcs}"
        )

    def test_keep_a_changelog_header(self):
        assert "Keep a Changelog" in self.src, (
            "Full changelog should reference Keep a Changelog format"
        )


# ---------------------------------------------------------------------------
# Layer 3 — functional_check
# ---------------------------------------------------------------------------

class TestFunctionalCommitParser:
    """Run the commit parser and verify behavior."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        sys.path.insert(0, os.path.join(REPO_DIR, "lib"))
        try:
            from changelog.commit_parser import parse_commit
            self.parse_commit = parse_commit
        except ImportError:
            # Try alternative import paths
            try:
                from changelog.commit_parser import parse_commit as pc
                self.parse_commit = pc
            except ImportError:
                pytest.skip("Cannot import parse_commit")

    def test_parse_feat_with_scope(self):
        result = self.parse_commit("feat(auth): add OAuth2 login support")
        assert result is not None, "Should parse a valid feat commit"
        assert result.type == "feat"
        assert result.scope == "auth"
        assert "OAuth2" in result.description or "login" in result.description

    def test_parse_fix_breaking(self):
        result = self.parse_commit("fix!: resolve crash on empty input")
        assert result is not None, "Should parse a breaking fix commit"
        assert result.type == "fix"
        assert result.breaking is True

    def test_parse_breaking_footer(self):
        msg = "feat(api): change response format\n\nBREAKING CHANGE: response is now JSON array"
        result = self.parse_commit(msg)
        assert result is not None
        assert result.breaking is True

    def test_parse_invalid_returns_none(self):
        result = self.parse_commit("this is not a conventional commit")
        assert result is None, "Invalid commit message should return None"

    def test_parse_with_body(self):
        msg = "fix(core): handle null values\n\nThis fixes the null pointer issue."
        result = self.parse_commit(msg)
        assert result is not None
        assert result.body is not None and "null" in result.body.lower()


class TestFunctionalVersionCalculator:
    """Run version calculator with known inputs."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        sys.path.insert(0, os.path.join(REPO_DIR, "lib"))
        try:
            from changelog.commit_parser import parse_commit
            from changelog.version_calculator import calculate_next_version
            self.parse_commit = parse_commit
            self.calculate = calculate_next_version
        except ImportError:
            pytest.skip("Cannot import version_calculator")

    def test_feat_bumps_minor(self):
        commits = [self.parse_commit("feat: new feature")]
        commits = [c for c in commits if c]
        result = self.calculate("1.2.3", commits)
        assert result == "1.3.0", f"feat should bump minor: expected 1.3.0, got {result}"

    def test_fix_bumps_patch(self):
        commits = [self.parse_commit("fix: bug fix")]
        commits = [c for c in commits if c]
        result = self.calculate("1.2.3", commits)
        assert result == "1.2.4", f"fix should bump patch: expected 1.2.4, got {result}"

    def test_breaking_bumps_major(self):
        commits = [self.parse_commit("feat!: breaking change")]
        commits = [c for c in commits if c]
        result = self.calculate("1.2.3", commits)
        assert result == "2.0.0", f"breaking should bump major: expected 2.0.0, got {result}"

    def test_no_relevant_commits(self):
        commits = [self.parse_commit("docs: update readme")]
        commits = [c for c in commits if c]
        result = self.calculate("1.2.3", commits)
        assert result == "1.2.3", f"docs should not bump version: expected 1.2.3, got {result}"

    def test_invalid_version_raises(self):
        with pytest.raises(ValueError):
            self.calculate("not-a-version", [])

    def test_mixed_commits_highest_wins(self):
        msgs = ["fix: a fix", "feat: a feature", "fix: another fix"]
        commits = [self.parse_commit(m) for m in msgs]
        commits = [c for c in commits if c]
        result = self.calculate("1.2.3", commits)
        assert result == "1.3.0", f"feat should dominate: expected 1.3.0, got {result}"


class TestFunctionalGenerator:
    """Run changelog generator and verify output format."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        sys.path.insert(0, os.path.join(REPO_DIR, "lib"))
        try:
            from changelog.commit_parser import parse_commit
            from changelog.generator import generate_changelog
            self.parse_commit = parse_commit
            self.generate = generate_changelog
        except ImportError:
            pytest.skip("Cannot import generator")

    def test_feat_in_added_section(self):
        commits = [self.parse_commit("feat(ui): add dark mode")]
        commits = [c for c in commits if c]
        output = self.generate("1.1.0", "2024-01-15", commits)
        assert "### Added" in output, "feat commits should appear under ### Added"
        assert "dark mode" in output

    def test_fix_in_fixed_section(self):
        commits = [self.parse_commit("fix: resolve timeout issue")]
        commits = [c for c in commits if c]
        output = self.generate("1.0.1", "2024-01-15", commits)
        assert "### Fixed" in output, "fix commits should appear under ### Fixed"

    def test_breaking_in_separate_section(self):
        commits = [self.parse_commit("feat!: change API response format")]
        commits = [c for c in commits if c]
        output = self.generate("2.0.0", "2024-01-15", commits)
        assert "BREAKING" in output, "Breaking changes should have a dedicated section"

    def test_docs_excluded(self):
        commits = [self.parse_commit("docs: update readme")]
        commits = [c for c in commits if c]
        output = self.generate("1.0.1", "2024-01-15", commits)
        assert "readme" not in output.lower() or "### " not in output, (
            "docs commits should be excluded from the changelog"
        )

    def test_scope_in_entry(self):
        commits = [self.parse_commit("feat(auth): add SSO support")]
        commits = [c for c in commits if c]
        output = self.generate("1.1.0", "2024-01-15", commits)
        assert "auth" in output, "Scope should appear in changelog entry"

    def test_version_header(self):
        commits = [self.parse_commit("feat: something")]
        commits = [c for c in commits if c]
        output = self.generate("1.1.0", "2024-01-15", commits)
        assert "1.1.0" in output, "Version should appear in changelog output"
        assert "2024-01-15" in output, "Date should appear in changelog output"
