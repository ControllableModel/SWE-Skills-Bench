"""
Test skill: fix
Verify that the Agent correctly fixes all ESLint and Prettier violations
in the Upgradle React/TypeScript project without changing runtime behavior.
"""

import os
import subprocess
import json
import pytest


class TestFix:
    REPO_DIR = "/workspace/upgradle"

    # === File Path Checks ===

    def test_app_tsx_exists(self):
        """Verify that the main App.tsx file exists"""
        filepath = os.path.join(self.REPO_DIR, "src/App.tsx")
        assert os.path.exists(filepath), f"App.tsx not found at {filepath}"

    def test_eslint_config_exists(self):
        """Verify that eslint config file exists"""
        filepath = os.path.join(self.REPO_DIR, "eslint.config.js")
        assert os.path.exists(filepath), f"eslint.config.js not found at {filepath}"

    def test_package_json_exists_and_valid(self):
        """Verify package.json exists and is valid JSON"""
        filepath = os.path.join(self.REPO_DIR, "package.json")
        assert os.path.exists(filepath), f"package.json not found at {filepath}"
        with open(filepath) as f:
            data = json.load(f)
        assert "name" in data, "package.json missing 'name' field"
        assert "scripts" in data, "package.json missing 'scripts' field"

    # === Semantic Checks ===

    def test_no_eslint_disable_comments_added(self):
        """Verify that no eslint-disable comments were added to suppress errors"""
        src_dir = os.path.join(self.REPO_DIR, "src")
        for root, _dirs, files in os.walk(src_dir):
            for fname in files:
                if fname.endswith((".ts", ".tsx", ".js", ".jsx")):
                    filepath = os.path.join(root, fname)
                    with open(filepath) as f:
                        content = f.read()
                    assert "eslint-disable" not in content, (
                        f"Found eslint-disable comment in {filepath}. "
                        "Fixes must be applied to source code, not suppressed with disable comments."
                    )

    def test_eslint_config_not_weakened(self):
        """Verify that ESLint rules have not been disabled or downgraded in config"""
        filepath = os.path.join(self.REPO_DIR, "eslint.config.js")
        with open(filepath) as f:
            content = f.read()
        # Check that no rules are set to "off" that weren't there before
        # We check that common rules are not turned off
        problematic_patterns = [
            '"no-unused-vars": "off"',
            '"no-unused-vars":"off"',
            "'no-unused-vars': 'off'",
            "no-unused-vars\": 0",
            "no-unused-vars': 0",
        ]
        for pattern in problematic_patterns:
            assert pattern not in content, (
                f"ESLint rule appears to be disabled in config: found '{pattern}' in eslint.config.js"
            )

    def test_no_explicit_any_in_app(self):
        """Verify that explicit 'any' type annotations have been resolved in App.tsx"""
        filepath = os.path.join(self.REPO_DIR, "src/App.tsx")
        with open(filepath) as f:
            content = f.read()
        # Count occurrences of ': any' or 'as any' which are common lint violations
        import re
        any_matches = re.findall(r'\b(?::\s*any\b|as\s+any\b)', content)
        # Allow zero; if some exist, it indicates the lint issue wasn't fully fixed
        # But some repos may use any legitimately, so we just flag significant counts
        assert len(any_matches) <= 2, (
            f"Found {len(any_matches)} explicit 'any' type usages in App.tsx. "
            "TypeScript lint errors related to @typescript-eslint/no-explicit-any should be resolved."
        )

    def test_no_loose_equality(self):
        """Verify that == comparisons have been replaced with === in source files"""
        src_dir = os.path.join(self.REPO_DIR, "src")
        import re
        for root, _dirs, files in os.walk(src_dir):
            for fname in files:
                if fname.endswith((".ts", ".tsx")):
                    filepath = os.path.join(root, fname)
                    with open(filepath) as f:
                        content = f.read()
                    # Find == that is not === or !==
                    loose_eq = re.findall(r'(?<!=)==(?!=)', content)
                    assert len(loose_eq) == 0, (
                        f"Found {len(loose_eq)} loose equality (==) comparisons in {filepath}. "
                        "These should be replaced with === (strict equality)."
                    )

    # === Functional Checks ===

    def test_yarn_install_succeeds(self):
        """Verify that project dependencies can be installed"""
        result = subprocess.run(
            ["yarn", "install", "--frozen-lockfile"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=120
        )
        if result.returncode != 0:
            # Try without frozen lockfile
            result = subprocess.run(
                ["yarn", "install"],
                cwd=self.REPO_DIR,
                capture_output=True,
                text=True,
                timeout=120
            )
        assert result.returncode == 0, f"yarn install failed: {result.stderr}"

    def test_eslint_passes(self):
        """Verify that yarn linc (ESLint) exits with code 0 and no errors"""
        # Ensure dependencies are installed first
        subprocess.run(["yarn", "install"], cwd=self.REPO_DIR, capture_output=True, timeout=120)

        result = subprocess.run(
            ["yarn", "linc"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=120
        )
        assert result.returncode == 0, (
            f"yarn linc failed with exit code {result.returncode}.\n"
            f"stdout: {result.stdout[:2000]}\n"
            f"stderr: {result.stderr[:2000]}"
        )

    def test_prettier_check_passes(self):
        """Verify that Prettier reports no formatting changes needed"""
        subprocess.run(["yarn", "install"], cwd=self.REPO_DIR, capture_output=True, timeout=120)

        result = subprocess.run(
            ["yarn", "prettier", "--check", "."],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=120
        )
        if result.returncode != 0:
            # Also try the project's specific prettier command
            result2 = subprocess.run(
                ["yarn", "prettier"],
                cwd=self.REPO_DIR,
                capture_output=True,
                text=True,
                timeout=120
            )
            assert result2.returncode == 0, (
                f"Prettier check failed.\nstdout: {result.stdout[:2000]}\nstderr: {result.stderr[:2000]}"
            )

    def test_project_builds_successfully(self):
        """Verify that the project builds with yarn build without TypeScript errors"""
        subprocess.run(["yarn", "install"], cwd=self.REPO_DIR, capture_output=True, timeout=120)

        result = subprocess.run(
            ["yarn", "build"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=120
        )
        assert result.returncode == 0, (
            f"yarn build failed with exit code {result.returncode}.\n"
            f"stderr: {result.stderr[:2000]}"
        )

    def test_typescript_compilation_no_errors(self):
        """Verify that TypeScript compiler reports no errors"""
        subprocess.run(["yarn", "install"], cwd=self.REPO_DIR, capture_output=True, timeout=120)

        result = subprocess.run(
            ["npx", "tsc", "--noEmit"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=120
        )
        # tsc --noEmit with exit code 0 means no type errors
        assert result.returncode == 0, (
            f"TypeScript compilation has errors:\n{result.stdout[:3000]}"
        )
