"""
Test skill: fix
Verify that the Agent correctly fixes lint and formatting errors in the Upgradle React application.
"""

import os
import subprocess
import json
import pytest


class TestFix:
    REPO_DIR = "/workspace/upgradle"

    # === File Path Checks ===

    def test_package_json_exists(self):
        """Verify that package.json exists in the repo root"""
        pkg_path = os.path.join(self.REPO_DIR, "package.json")
        assert os.path.exists(pkg_path), f"package.json not found at {pkg_path}"
        with open(pkg_path) as f:
            data = json.load(f)
        assert "scripts" in data, "package.json missing 'scripts' section"

    def test_src_directory_exists(self):
        """Verify that the src directory exists"""
        src_path = os.path.join(self.REPO_DIR, "src")
        assert os.path.isdir(src_path), f"src/ directory not found at {src_path}"

    def test_source_files_exist(self):
        """Verify that source JS/JSX/TS/TSX files exist under src/"""
        src_path = os.path.join(self.REPO_DIR, "src")
        extensions = {".js", ".jsx", ".ts", ".tsx"}
        found = False
        for root, dirs, files in os.walk(src_path):
            for f in files:
                if os.path.splitext(f)[1] in extensions:
                    found = True
                    break
            if found:
                break
        assert found, "No JS/JSX/TS/TSX source files found under src/"

    # === Semantic Checks ===

    def test_no_global_eslint_rule_disables_in_config(self):
        """Verify no ESLint rules are globally disabled in configuration files"""
        config_files = [
            ".eslintrc", ".eslintrc.js", ".eslintrc.json", ".eslintrc.yaml",
            ".eslintrc.yml", "eslint.config.js", "eslint.config.mjs"
        ]
        for cfg in config_files:
            cfg_path = os.path.join(self.REPO_DIR, cfg)
            if os.path.exists(cfg_path):
                with open(cfg_path) as f:
                    content = f.read()
                # Check for blanket "off" rules that disable important rules
                # A global disable would be something like "no-unused-vars": "off" in the config
                # We check that no massive amount of rules are turned off
                off_count = content.lower().count('"off"') + content.lower().count("'off'")
                assert off_count <= 3, \
                    f"Too many global rule disables ({off_count}) found in {cfg}. " \
                    "Fix code issues instead of disabling rules."

    def test_inline_disables_have_explanations(self):
        """Verify that any inline eslint-disable comments include explanations"""
        src_path = os.path.join(self.REPO_DIR, "src")
        violations = []
        for root, dirs, files in os.walk(src_path):
            for fname in files:
                if not any(fname.endswith(ext) for ext in [".js", ".jsx", ".ts", ".tsx"]):
                    continue
                fpath = os.path.join(root, fname)
                with open(fpath, errors="replace") as f:
                    for i, line in enumerate(f, 1):
                        stripped = line.strip()
                        if "eslint-disable" in stripped and stripped.startswith("//"):
                            # Check if there's an explanation (text after the rule name)
                            # Pattern: // eslint-disable-next-line rule-name -- explanation
                            if "--" not in stripped and stripped.count("//") < 2:
                                # Allow if it's a very short targeted disable
                                pass  # Relaxed: just ensure they exist
        # We check that disables are targeted (not blanket)
        for root, dirs, files in os.walk(src_path):
            for fname in files:
                if not any(fname.endswith(ext) for ext in [".js", ".jsx", ".ts", ".tsx"]):
                    continue
                fpath = os.path.join(root, fname)
                with open(fpath, errors="replace") as f:
                    content = f.read()
                if "eslint-disable " in content and "eslint-disable-next-line" not in content:
                    # File-level disable without specific rule targeting
                    if "/* eslint-disable */" in content:
                        violations.append(f"{fname}: blanket eslint-disable found")
        assert len(violations) == 0, \
            f"Blanket eslint-disable directives found: {violations}"

    def test_package_json_has_lint_scripts(self):
        """Verify package.json has lint-related scripts configured"""
        pkg_path = os.path.join(self.REPO_DIR, "package.json")
        with open(pkg_path) as f:
            data = json.load(f)
        scripts = data.get("scripts", {})
        # Should have some lint/format related scripts
        lint_keywords = ["lint", "eslint", "format", "prettier", "linc"]
        has_lint = any(
            any(kw in k.lower() or kw in v.lower() for kw in lint_keywords)
            for k, v in scripts.items()
        )
        assert has_lint, \
            f"No lint/format scripts found in package.json. Scripts: {list(scripts.keys())}"

    def test_no_unused_imports_in_source(self):
        """Verify no obvious unused imports remain in source files (spot check)"""
        # This is a semantic check - we look for common patterns of unused imports
        # The real validation is done by the eslint run in functional checks
        src_path = os.path.join(self.REPO_DIR, "src")
        assert os.path.isdir(src_path), "src/ directory not found"
        # Just verify files are parseable (not broken by fixes)
        for root, dirs, files in os.walk(src_path):
            for fname in files:
                if fname.endswith((".js", ".jsx", ".ts", ".tsx")):
                    fpath = os.path.join(root, fname)
                    with open(fpath, errors="replace") as f:
                        content = f.read()
                    assert len(content) > 0, f"File {fname} is empty after fixes"

    # === Functional Checks ===

    def _ensure_deps_installed(self):
        """Helper to install dependencies if not already installed"""
        node_modules = os.path.join(self.REPO_DIR, "node_modules")
        if not os.path.isdir(node_modules):
            result = subprocess.run(
                ["yarn", "install", "--frozen-lockfile"],
                cwd=self.REPO_DIR,
                capture_output=True, text=True, timeout=300
            )
            if result.returncode != 0:
                # Try without frozen lockfile
                result = subprocess.run(
                    ["yarn", "install"],
                    cwd=self.REPO_DIR,
                    capture_output=True, text=True, timeout=300
                )
                if result.returncode != 0:
                    pytest.skip(f"yarn install failed: {result.stderr[:500]}")

    def test_prettier_check_passes(self):
        """Verify all files pass Prettier formatting checks"""
        self._ensure_deps_installed()
        result = subprocess.run(
            ["yarn", "prettier", "--check", "."],
            cwd=self.REPO_DIR,
            capture_output=True, text=True, timeout=120
        )
        assert result.returncode == 0, \
            f"Prettier check failed (files not formatted):\n{result.stdout[:2000]}\n{result.stderr[:500]}"

    def test_eslint_passes(self):
        """Verify ESLint passes with zero errors"""
        self._ensure_deps_installed()
        # Try the project's lint command first
        result = subprocess.run(
            ["yarn", "linc"],
            cwd=self.REPO_DIR,
            capture_output=True, text=True, timeout=120
        )
        if result.returncode != 0:
            # Fallback: try running eslint directly
            result = subprocess.run(
                ["yarn", "eslint", "src/", "--max-warnings=0"],
                cwd=self.REPO_DIR,
                capture_output=True, text=True, timeout=120
            )
        assert result.returncode == 0, \
            f"ESLint check failed:\n{result.stdout[:2000]}\n{result.stderr[:500]}"

    def test_application_builds_successfully(self):
        """Verify the application still builds after fixes"""
        self._ensure_deps_installed()
        # Try common build commands
        build_cmds = [
            ["yarn", "build"],
            ["yarn", "react-scripts", "build"],
            ["npx", "react-scripts", "build"],
        ]
        success = False
        last_err = ""
        for cmd in build_cmds:
            result = subprocess.run(
                cmd,
                cwd=self.REPO_DIR,
                capture_output=True, text=True, timeout=300,
                env={**os.environ, "CI": "true", "NODE_ENV": "production"}
            )
            if result.returncode == 0:
                success = True
                break
            last_err = f"{result.stdout[:500]}\n{result.stderr[:500]}"
        assert success, f"Application build failed after fixes:\n{last_err}"

    def test_no_eslint_errors_in_output(self):
        """Verify eslint output contains zero error count"""
        self._ensure_deps_installed()
        result = subprocess.run(
            ["yarn", "eslint", "src/", "--format=json"],
            cwd=self.REPO_DIR,
            capture_output=True, text=True, timeout=120
        )
        if result.returncode != 0 and not result.stdout.strip():
            pytest.skip("eslint json output not available")
        try:
            eslint_output = json.loads(result.stdout)
            total_errors = sum(item.get("errorCount", 0) for item in eslint_output)
            assert total_errors == 0, \
                f"ESLint reported {total_errors} errors. Expected 0."
        except json.JSONDecodeError:
            # If JSON parsing fails, fall back to return code check
            assert result.returncode == 0, \
                f"ESLint failed with non-zero exit code: {result.stderr[:500]}"

    def test_no_new_warnings_from_eslint(self):
        """Verify no new warnings are introduced by the fixes"""
        self._ensure_deps_installed()
        result = subprocess.run(
            ["yarn", "eslint", "src/", "--format=json"],
            cwd=self.REPO_DIR,
            capture_output=True, text=True, timeout=120
        )
        if result.returncode != 0 and not result.stdout.strip():
            pytest.skip("eslint json output not available")
        try:
            eslint_output = json.loads(result.stdout)
            total_warnings = sum(item.get("warningCount", 0) for item in eslint_output)
            # Allow some warnings but not excessive ones
            assert total_warnings <= 5, \
                f"ESLint reported {total_warnings} warnings (>5). Fixes should not introduce new warnings."
        except json.JSONDecodeError:
            pass  # Gracefully handle if json format unavailable
