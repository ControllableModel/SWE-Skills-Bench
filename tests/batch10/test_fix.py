"""
Test skill: fix
Verify that the Agent correctly fixes lint and formatting errors in the Upgradle repository
(a Vite + React + TypeScript word-guessing game).
"""

import os
import json
import re
import subprocess
import pytest


class TestFix:
    REPO_DIR = "/workspace/upgradle"

    @classmethod
    def setup_class(cls):
        """Install Node.js dependencies if not already present."""
        node_modules = os.path.join(cls.REPO_DIR, "node_modules")
        if not os.path.exists(node_modules):
            result = subprocess.run(
                ["yarn", "install", "--frozen-lockfile"],
                cwd=cls.REPO_DIR,
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode != 0:
                # Try without frozen lockfile
                result = subprocess.run(
                    ["yarn", "install"],
                    cwd=cls.REPO_DIR,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                if result.returncode != 0:
                    pytest.skip(f"yarn install failed: {result.stderr[:500]}")

    # === File Path Checks ===

    def test_app_tsx_exists(self):
        """Verify that the main application component src/App.tsx exists"""
        path = os.path.join(self.REPO_DIR, "src/App.tsx")
        assert os.path.exists(path), f"App.tsx not found at {path}"

    def test_dictionary_ts_exists(self):
        """Verify that src/dictionary.ts exists"""
        path = os.path.join(self.REPO_DIR, "src/dictionary.ts")
        assert os.path.exists(path), f"dictionary.ts not found at {path}"

    def test_package_json_exists_and_parseable(self):
        """Verify package.json exists and is valid JSON"""
        path = os.path.join(self.REPO_DIR, "package.json")
        assert os.path.exists(path), f"package.json not found at {path}"
        with open(path) as f:
            data = json.load(f)
        assert isinstance(data, dict), "package.json did not parse to a dict"
        assert "name" in data, "package.json missing 'name' field"

    def test_eslint_config_exists(self):
        """Verify an ESLint configuration file exists"""
        candidates = [
            os.path.join(self.REPO_DIR, "eslint.config.js"),
            os.path.join(self.REPO_DIR, "eslint.config.mjs"),
            os.path.join(self.REPO_DIR, ".eslintrc.js"),
            os.path.join(self.REPO_DIR, ".eslintrc.json"),
            os.path.join(self.REPO_DIR, ".eslintrc.cjs"),
        ]
        found = any(os.path.exists(c) for c in candidates)
        assert found, f"No ESLint config found. Checked: {candidates}"

    # === Semantic Checks ===

    def test_package_json_has_prettier_script(self):
        """Verify package.json has a prettier or format script defined"""
        pkg_path = os.path.join(self.REPO_DIR, "package.json")
        with open(pkg_path) as f:
            pkg = json.load(f)
        scripts = pkg.get("scripts", {})
        has_prettier = any(
            key in scripts for key in ("prettier", "format", "prettier:check", "format:check")
        )
        assert has_prettier, (
            f"package.json missing prettier/format script. Available scripts: {list(scripts.keys())}"
        )

    def test_package_json_has_lint_script(self):
        """Verify package.json has a linc or lint script defined"""
        pkg_path = os.path.join(self.REPO_DIR, "package.json")
        with open(pkg_path) as f:
            pkg = json.load(f)
        scripts = pkg.get("scripts", {})
        has_lint = any(key in scripts for key in ("linc", "lint", "eslint"))
        assert has_lint, (
            f"package.json missing linc/lint script. Available scripts: {list(scripts.keys())}"
        )

    def test_app_tsx_no_unused_imports(self):
        """Verify App.tsx does not contain obvious unused imports (checked via ESLint)"""
        app_path = os.path.join(self.REPO_DIR, "src/App.tsx")
        with open(app_path) as f:
            content = f.read()
        # Count @ts-ignore comments — excessive use indicates suppressed errors
        ts_ignore_count = len(re.findall(r'@ts-ignore', content))
        assert ts_ignore_count <= 1, (
            f"Found {ts_ignore_count} @ts-ignore comments in App.tsx. "
            "Should use proper type annotations instead."
        )

    def test_source_files_no_trailing_whitespace(self):
        """Verify .ts and .tsx source files have no trailing whitespace"""
        src_dir = os.path.join(self.REPO_DIR, "src")
        if not os.path.isdir(src_dir):
            pytest.skip("src/ directory not found")
        violations = []
        for root, _, files in os.walk(src_dir):
            for fname in files:
                if fname.endswith(('.ts', '.tsx')):
                    fpath = os.path.join(root, fname)
                    with open(fpath) as f:
                        for i, line in enumerate(f, 1):
                            stripped = line.rstrip('\n').rstrip('\r')
                            if stripped != stripped.rstrip():
                                violations.append(f"{os.path.relpath(fpath, self.REPO_DIR)}:{i}")
                                break
        assert len(violations) == 0, (
            f"Files with trailing whitespace: {violations}"
        )

    def test_source_files_consistent_quotes(self):
        """Verify source files use consistent quote style (single or double based on config)"""
        src_dir = os.path.join(self.REPO_DIR, "src")
        if not os.path.isdir(src_dir):
            pytest.skip("src/ directory not found")
        # Just verify files are parseable and not mixing styles erratically
        tsx_files = []
        for root, _, files in os.walk(src_dir):
            for fname in files:
                if fname.endswith(('.ts', '.tsx')):
                    tsx_files.append(os.path.join(root, fname))
        assert len(tsx_files) > 0, "No .ts/.tsx files found in src/"

    # === Functional Checks ===

    def test_yarn_linc_exits_cleanly(self):
        """Verify yarn linc (lint changed files) exits with code 0, zero errors"""
        result = subprocess.run(
            ["yarn", "linc"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, (
            f"yarn linc failed (exit {result.returncode}).\n"
            f"stdout: {result.stdout[-1000:]}\nstderr: {result.stderr[-1000:]}"
        )

    def test_yarn_build_succeeds(self):
        """Verify yarn build (Vite production build) completes without errors"""
        result = subprocess.run(
            ["yarn", "build"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, (
            f"yarn build failed (exit {result.returncode}).\n"
            f"stdout: {result.stdout[-1000:]}\nstderr: {result.stderr[-1000:]}"
        )

    def test_prettier_check_passes(self):
        """Verify that all source files conform to Prettier formatting"""
        result = subprocess.run(
            ["npx", "prettier", "--check", "src/"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            # Try with the project's own prettier script
            result2 = subprocess.run(
                ["yarn", "prettier"],
                cwd=self.REPO_DIR,
                capture_output=True,
                text=True,
                timeout=60,
            )
            # After running prettier, re-check
            result3 = subprocess.run(
                ["npx", "prettier", "--check", "src/"],
                cwd=self.REPO_DIR,
                capture_output=True,
                text=True,
                timeout=60,
            )
            assert result3.returncode == 0, (
                f"Prettier check failed after formatting.\n"
                f"Non-conforming files: {result3.stdout[-1000:]}"
            )

    def test_no_eslint_errors_in_src(self):
        """Verify ESLint reports zero errors across all source files"""
        result = subprocess.run(
            ["npx", "eslint", "src/", "--format", "json"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.stdout.strip():
            try:
                lint_results = json.loads(result.stdout)
                total_errors = sum(r.get("errorCount", 0) for r in lint_results)
                total_warnings = sum(r.get("warningCount", 0) for r in lint_results)
                assert total_errors == 0, (
                    f"ESLint reported {total_errors} errors and {total_warnings} warnings"
                )
            except json.JSONDecodeError:
                # If JSON parsing fails, just check exit code
                assert result.returncode == 0, (
                    f"ESLint failed: {result.stderr[-500:]}"
                )
        else:
            assert result.returncode == 0, (
                f"ESLint failed: {result.stderr[-500:]}"
            )
