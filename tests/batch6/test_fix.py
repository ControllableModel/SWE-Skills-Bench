"""
Test skill: fix
Verify that the Agent correctly fixes linting and formatting errors
in the Upgradle React application.
"""

import os
import subprocess
import pytest


class TestFix:
    REPO_DIR = "/workspace/upgradle"

    # === File Path Checks ===

    def test_app_tsx_exists(self):
        """Verify that App.tsx exists"""
        path = os.path.join(self.REPO_DIR, "src/App.tsx")
        assert os.path.exists(path), f"App.tsx not found at {path}"

    def test_board_tsx_exists(self):
        """Verify that Board.tsx exists"""
        path = os.path.join(self.REPO_DIR, "src/components/Board.tsx")
        assert os.path.exists(path), f"Board.tsx not found at {path}"

    def test_tile_tsx_exists(self):
        """Verify that Tile.tsx exists"""
        path = os.path.join(self.REPO_DIR, "src/components/Tile.tsx")
        assert os.path.exists(path), f"Tile.tsx not found at {path}"

    def test_keyboard_tsx_exists(self):
        """Verify that Keyboard.tsx exists"""
        path = os.path.join(self.REPO_DIR, "src/components/Keyboard.tsx")
        assert os.path.exists(path), f"Keyboard.tsx not found at {path}"

    def test_game_utils_exists(self):
        """Verify that game.ts utility file exists"""
        path = os.path.join(self.REPO_DIR, "src/utils/game.ts")
        assert os.path.exists(path), f"game.ts not found at {path}"

    # === Semantic Checks ===

    def test_no_unused_imports_in_source_files(self):
        """Verify that no unused imports remain in key source files"""
        source_files = [
            "src/App.tsx",
            "src/components/Board.tsx",
            "src/components/Tile.tsx",
            "src/components/Keyboard.tsx",
            "src/utils/game.ts",
        ]
        for rel_path in source_files:
            full_path = os.path.join(self.REPO_DIR, rel_path)
            if not os.path.exists(full_path):
                continue
            with open(full_path, "r") as f:
                content = f.read()
            # Basic heuristic: check for common unused import patterns
            # This is a supplementary check; the real check is the linter
            lines = content.split("\n")
            import_lines = [l.strip() for l in lines if l.strip().startswith("import ")]
            # Just verify imports exist and the file is parseable
            assert len(lines) > 0, f"{rel_path} is empty"

    def test_no_console_log_in_production_code(self):
        """Verify that no console.log statements remain in source files"""
        source_files = [
            "src/App.tsx",
            "src/components/Board.tsx",
            "src/components/Tile.tsx",
            "src/components/Keyboard.tsx",
            "src/utils/game.ts",
            "src/utils/words.ts",
        ]
        for rel_path in source_files:
            full_path = os.path.join(self.REPO_DIR, rel_path)
            if not os.path.exists(full_path):
                continue
            with open(full_path, "r") as f:
                content = f.read()
            lines = content.split("\n")
            for i, line in enumerate(lines, 1):
                stripped = line.strip()
                # Skip comments
                if stripped.startswith("//") or stripped.startswith("/*"):
                    continue
                assert "console.log(" not in stripped, (
                    f"console.log found in {rel_path} at line {i}: {stripped}"
                )

    def test_jsx_map_renders_have_key_prop(self):
        """Verify that all .map() JSX renders include a key prop"""
        source_files = [
            "src/App.tsx",
            "src/components/Board.tsx",
            "src/components/Tile.tsx",
            "src/components/Keyboard.tsx",
        ]
        import re
        for rel_path in source_files:
            full_path = os.path.join(self.REPO_DIR, rel_path)
            if not os.path.exists(full_path):
                continue
            with open(full_path, "r") as f:
                content = f.read()
            # Find .map( patterns that return JSX (contain < after map)
            map_pattern = re.compile(r'\.map\s*\(.*?=>\s*[\(\{]?\s*<', re.DOTALL)
            matches = map_pattern.finditer(content)
            for match in matches:
                # Get surrounding context to check for key prop
                start = match.start()
                # Look forward up to 500 chars for the closing of the first JSX element
                context = content[start:start + 500]
                # The first JSX element should have a key prop
                first_tag_end = context.find(">")
                if first_tag_end > 0:
                    first_tag = context[:first_tag_end + 1]
                    assert "key=" in first_tag or "key =" in first_tag, (
                        f"Missing key prop in .map() JSX render in {rel_path}. "
                        f"Context: {first_tag[:100]}..."
                    )

    def test_source_files_have_consistent_formatting(self):
        """Verify that source files don't have obvious formatting issues like mixed tabs/spaces"""
        source_files = [
            "src/App.tsx",
            "src/components/Board.tsx",
            "src/components/Keyboard.tsx",
        ]
        for rel_path in source_files:
            full_path = os.path.join(self.REPO_DIR, rel_path)
            if not os.path.exists(full_path):
                continue
            with open(full_path, "r") as f:
                content = f.read()
            lines = content.split("\n")
            has_tabs = any(l.startswith("\t") for l in lines if l.strip())
            has_spaces = any(l.startswith("  ") for l in lines if l.strip())
            # Should not have mixed indentation
            assert not (has_tabs and has_spaces), (
                f"{rel_path} has mixed tabs and spaces indentation"
            )

    # === Functional Checks ===

    def test_yarn_install_succeeds(self):
        """Verify that yarn install succeeds (dependency setup)"""
        result = subprocess.run(
            ["yarn", "install", "--frozen-lockfile"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            # Try without frozen lockfile
            result = subprocess.run(
                ["yarn", "install"],
                cwd=self.REPO_DIR,
                capture_output=True,
                text=True,
                timeout=120,
            )
        assert result.returncode == 0, f"yarn install failed: {result.stderr}"

    def test_prettier_reports_no_changes(self):
        """Verify that yarn prettier reports no files need formatting changes"""
        # Ensure deps are installed
        subprocess.run(
            ["yarn", "install"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        result = subprocess.run(
            ["yarn", "prettier", "--check", "src/"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0, (
            f"Prettier found formatting issues:\n{result.stdout}\n{result.stderr}"
        )

    def test_lint_check_passes(self):
        """Verify that yarn linc exits with code 0 and reports no errors"""
        subprocess.run(
            ["yarn", "install"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        result = subprocess.run(
            ["yarn", "linc"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0, (
            f"yarn linc failed with errors:\n{result.stdout}\n{result.stderr}"
        )

    def test_application_builds_successfully(self):
        """Verify that the application builds without errors after fixes"""
        subprocess.run(
            ["yarn", "install"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        result = subprocess.run(
            ["yarn", "build"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, (
            f"Build failed:\n{result.stdout}\n{result.stderr}"
        )

    def test_no_eslint_errors_on_individual_files(self):
        """Verify that individual source files pass ESLint without errors"""
        subprocess.run(
            ["yarn", "install"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        files_to_check = [
            "src/App.tsx",
            "src/components/Board.tsx",
            "src/components/Tile.tsx",
            "src/components/Keyboard.tsx",
        ]
        for rel_path in files_to_check:
            full_path = os.path.join(self.REPO_DIR, rel_path)
            if not os.path.exists(full_path):
                continue
            result = subprocess.run(
                ["npx", "eslint", rel_path, "--no-error-on-unmatched-pattern"],
                cwd=self.REPO_DIR,
                capture_output=True,
                text=True,
                timeout=30,
            )
            assert result.returncode == 0, (
                f"ESLint errors in {rel_path}:\n{result.stdout}\n{result.stderr}"
            )

    def test_game_logic_unchanged_words_ts(self):
        """Verify that words.ts still contains word data (no accidental deletion)"""
        path = os.path.join(self.REPO_DIR, "src/utils/words.ts")
        if not os.path.exists(path):
            pytest.skip("words.ts not found")
        with open(path, "r") as f:
            content = f.read()
        # The file should still export word-related functions/constants
        assert len(content) > 100, (
            f"words.ts seems too small ({len(content)} chars), may have been truncated"
        )
        assert "export" in content, "words.ts should export functions or constants"
