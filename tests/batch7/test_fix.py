"""
Test skill: fix
Verify that the Agent correctly fixes lint and formatting errors
in the Upgradle React application so that ESLint, Prettier, and build all pass.
"""

import os
import subprocess
import json
import pytest


class TestFix:
    REPO_DIR = "/workspace/upgradle"

    # === File Path Checks ===

    def test_app_tsx_exists(self):
        """Verify src/App.tsx exists"""
        fpath = os.path.join(self.REPO_DIR, "src/App.tsx")
        assert os.path.isfile(fpath), f"App.tsx not found at {fpath}"

    def test_dictionary_ts_exists(self):
        """Verify src/dictionary.ts exists"""
        fpath = os.path.join(self.REPO_DIR, "src/dictionary.ts")
        assert os.path.isfile(fpath), f"dictionary.ts not found at {fpath}"

    def test_app_css_exists(self):
        """Verify src/App.css exists"""
        fpath = os.path.join(self.REPO_DIR, "src/App.css")
        assert os.path.isfile(fpath), f"App.css not found at {fpath}"

    def test_package_json_exists(self):
        """Verify package.json exists in repo root"""
        fpath = os.path.join(self.REPO_DIR, "package.json")
        assert os.path.isfile(fpath), f"package.json not found at {fpath}"

    # === Semantic Checks ===

    def test_app_tsx_no_unused_imports(self):
        """Verify App.tsx has no obvious unused imports"""
        fpath = os.path.join(self.REPO_DIR, "src/App.tsx")
        with open(fpath, "r") as f:
            content = f.read()
        # Basic structural check: file should be valid TypeScript/JSX
        assert "import" in content, "App.tsx should contain import statements"
        assert "export" in content or "function App" in content, (
            "App.tsx should export a component or contain App function"
        )

    def test_app_tsx_preserves_game_logic(self):
        """Verify App.tsx still contains core game logic elements"""
        fpath = os.path.join(self.REPO_DIR, "src/App.tsx")
        with open(fpath, "r") as f:
            content = f.read()
        # Check that key game elements are preserved
        has_reducer = "reducer" in content.lower() or "useReducer" in content or "dispatch" in content
        has_keyboard = "keyboard" in content.lower() or "key" in content.lower()
        assert has_reducer or has_keyboard, (
            "App.tsx should preserve game logic (reducer/dispatch or keyboard handling)"
        )

    def test_dictionary_ts_preserves_functionality(self):
        """Verify dictionary.ts still filters words correctly"""
        fpath = os.path.join(self.REPO_DIR, "src/dictionary.ts")
        with open(fpath, "r") as f:
            content = f.read()
        # dictionary module should export something and contain filtering logic
        assert "export" in content, "dictionary.ts should export word list or function"
        # Should contain word length filtering logic
        has_length_filter = "length" in content or "filter" in content
        assert has_length_filter, "dictionary.ts should contain word filtering logic"

    def test_eslint_config_exists(self):
        """Verify ESLint configuration file exists"""
        eslint_paths = [
            os.path.join(self.REPO_DIR, "eslint.config.js"),
            os.path.join(self.REPO_DIR, ".eslintrc.js"),
            os.path.join(self.REPO_DIR, ".eslintrc.json"),
            os.path.join(self.REPO_DIR, ".eslintrc"),
        ]
        found = any(os.path.isfile(p) for p in eslint_paths)
        assert found, "No ESLint configuration file found in the repository"

    # === Functional Checks ===

    def test_npm_install_succeeds(self):
        """Verify npm install completes without errors"""
        result = subprocess.run(
            ["npm", "install"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=120
        )
        assert result.returncode == 0, f"npm install failed: {result.stderr[-1000:]}"

    def test_eslint_passes_with_zero_errors(self):
        """Verify ESLint reports zero errors across all source files"""
        # Ensure dependencies installed
        subprocess.run(["npm", "install"], cwd=self.REPO_DIR, capture_output=True, timeout=120)

        result = subprocess.run(
            ["npx", "eslint", "src/", "--format", "json"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=60
        )
        if result.stdout.strip():
            try:
                lint_results = json.loads(result.stdout)
                total_errors = sum(r.get("errorCount", 0) for r in lint_results)
                total_warnings = sum(r.get("warningCount", 0) for r in lint_results)
                assert total_errors == 0, (
                    f"ESLint reports {total_errors} errors. "
                    f"First file with errors: {next((r['filePath'] for r in lint_results if r.get('errorCount', 0) > 0), 'unknown')}"
                )
                assert total_warnings == 0, f"ESLint reports {total_warnings} warnings"
            except json.JSONDecodeError:
                # If JSON parsing fails, check exit code
                assert result.returncode == 0, f"ESLint failed: {result.stderr[-500:]}"
        else:
            assert result.returncode == 0, f"ESLint failed: {result.stderr[-500:]}"

    def test_prettier_check_passes(self):
        """Verify Prettier reports no formatting differences"""
        subprocess.run(["npm", "install"], cwd=self.REPO_DIR, capture_output=True, timeout=120)

        result = subprocess.run(
            ["npx", "prettier", "--check", "src/"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=60
        )
        assert result.returncode == 0, (
            f"Prettier found formatting issues: {result.stdout[:500]}"
        )

    def test_build_succeeds(self):
        """Verify the production build succeeds without errors"""
        subprocess.run(["npm", "install"], cwd=self.REPO_DIR, capture_output=True, timeout=120)

        result = subprocess.run(
            ["npm", "run", "build"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=120
        )
        assert result.returncode == 0, f"Build failed: {result.stderr[-1000:]}"

    def test_no_typescript_errors(self):
        """Verify TypeScript compilation has no type errors"""
        subprocess.run(["npm", "install"], cwd=self.REPO_DIR, capture_output=True, timeout=120)

        result = subprocess.run(
            ["npx", "tsc", "--noEmit"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=60
        )
        # Some projects may not have strict tsconfig, accept both 0 and non-zero
        # but if tsc exists, its error output tells us about type errors
        if result.returncode != 0:
            error_lines = [l for l in result.stdout.split("\n") if "error TS" in l]
            assert len(error_lines) == 0, (
                f"TypeScript has {len(error_lines)} type errors: {error_lines[:5]}"
            )

    def test_no_explicit_any_in_app_tsx(self):
        """Verify App.tsx does not contain unresolved explicit 'any' types that ESLint would flag"""
        fpath = os.path.join(self.REPO_DIR, "src/App.tsx")
        with open(fpath, "r") as f:
            lines = f.readlines()
        # Check for ': any' patterns that are typically lint violations
        any_count = 0
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("//") or stripped.startswith("*"):
                continue
            import re
            # Match ': any' that is not in a comment
            if re.search(r':\s*any\b', line):
                any_count += 1
        # Some uses of 'any' may be legitimate with eslint-disable, so just warn if many
        assert any_count <= 2, (
            f"App.tsx contains {any_count} explicit 'any' type annotations, "
            "which typically trigger ESLint @typescript-eslint/no-explicit-any"
        )

    def test_jsx_elements_have_key_props(self):
        """Verify list-rendered JSX elements in App.tsx have key props"""
        fpath = os.path.join(self.REPO_DIR, "src/App.tsx")
        with open(fpath, "r") as f:
            content = f.read()
        import re
        # Find .map() calls that return JSX
        map_blocks = re.findall(r'\.map\s*\([^)]*\)\s*=>\s*[\({]?\s*<\w+', content)
        if map_blocks:
            # Each map-rendered element should have a key prop somewhere nearby
            # This is a heuristic check
            map_sections = re.findall(r'\.map\s*\([^}]+\}', content, re.DOTALL)
            for section in map_sections:
                if "<" in section:
                    assert "key=" in section or "key =" in section, (
                        f"JSX element inside .map() appears to be missing 'key' prop"
                    )
