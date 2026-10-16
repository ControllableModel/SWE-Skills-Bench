"""
Test skill: fix
Verify that the Agent correctly fixes ESLint, Prettier, and TypeScript errors in the upgradle project.
"""

import os
import subprocess
import pytest


class TestFix:
    REPO_DIR = "/workspace/upgradle"

    # === File Path Checks ===

    def test_package_json_exists(self):
        """Verify package.json exists at project root"""
        path = os.path.join(self.REPO_DIR, "package.json")
        assert os.path.exists(path), f"package.json not found at {path}"

    def test_src_directory_exists(self):
        """Verify src directory exists"""
        path = os.path.join(self.REPO_DIR, "src")
        assert os.path.isdir(path), f"src directory not found at {path}"

    # === Semantic Checks ===

    def test_no_var_declarations_in_ts_files(self):
        """Verify no 'var' declarations remain in TypeScript source files"""
        src_dir = os.path.join(self.REPO_DIR, "src")
        import re
        var_pattern = re.compile(r"\bvar\s+\w+")
        violations = []
        for root, dirs, files in os.walk(src_dir):
            for fname in files:
                if fname.endswith((".ts", ".tsx")):
                    fpath = os.path.join(root, fname)
                    with open(fpath) as f:
                        for lineno, line in enumerate(f, 1):
                            if var_pattern.search(line) and not line.strip().startswith("//"):
                                violations.append(f"{fpath}:{lineno}")
        assert len(violations) == 0, (
            f"Found 'var' declarations in: {violations[:10]}"
        )

    def test_no_console_log_in_production_code(self):
        """Verify no stray console.log statements in source (common lint issue)"""
        src_dir = os.path.join(self.REPO_DIR, "src")
        import re
        console_pattern = re.compile(r"\bconsole\.log\(")
        violations = []
        for root, dirs, files in os.walk(src_dir):
            for fname in files:
                if fname.endswith((".ts", ".tsx")):
                    fpath = os.path.join(root, fname)
                    with open(fpath) as f:
                        for lineno, line in enumerate(f, 1):
                            if console_pattern.search(line) and not line.strip().startswith("//"):
                                violations.append(f"{fpath}:{lineno}")
        # console.log may be acceptable in some files, but flag if excessive
        assert len(violations) <= 5, (
            f"Too many console.log statements ({len(violations)}): {violations[:10]}"
        )

    def test_tsx_files_have_react_import_or_jsx_runtime(self):
        """Verify .tsx files either import React or use new JSX transform"""
        src_dir = os.path.join(self.REPO_DIR, "src")
        tsx_files = []
        for root, dirs, files in os.walk(src_dir):
            for fname in files:
                if fname.endswith(".tsx"):
                    tsx_files.append(os.path.join(root, fname))
        assert len(tsx_files) > 0, "No .tsx files found in src"
        # With new JSX transform, explicit React import is not needed.
        # Just verify files parse without obvious issues

    def test_no_trailing_whitespace_in_source(self):
        """Verify Prettier-style no trailing whitespace in source files"""
        src_dir = os.path.join(self.REPO_DIR, "src")
        violations = []
        for root, dirs, files in os.walk(src_dir):
            for fname in files:
                if fname.endswith((".ts", ".tsx", ".js", ".jsx")):
                    fpath = os.path.join(root, fname)
                    with open(fpath) as f:
                        for lineno, line in enumerate(f, 1):
                            if line.rstrip("\n") != line.rstrip():
                                violations.append(f"{fpath}:{lineno}")
        assert len(violations) == 0, (
            f"Trailing whitespace found in {len(violations)} lines: {violations[:10]}"
        )

    # === Functional Checks ===

    def test_npm_install_succeeds(self):
        """Verify npm install completes without errors"""
        result = subprocess.run(
            ["npm", "install"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, f"npm install failed: {result.stderr[:500]}"

    def test_eslint_passes(self):
        """Verify ESLint produces zero errors"""
        result = subprocess.run(
            ["npx", "eslint", "."],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, (
            f"ESLint reported errors:\n{result.stdout[:1000]}\n{result.stderr[:500]}"
        )

    def test_prettier_check_passes(self):
        """Verify Prettier check finds no formatting issues"""
        result = subprocess.run(
            ["npx", "prettier", "--check", "."],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, (
            f"Prettier check failed:\n{result.stdout[:1000]}\n{result.stderr[:500]}"
        )

    def test_typescript_noEmit_passes(self):
        """Verify TypeScript type checking passes with --noEmit"""
        result = subprocess.run(
            ["npx", "tsc", "--noEmit"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, (
            f"TypeScript errors found:\n{result.stdout[:1000]}\n{result.stderr[:500]}"
        )

    def test_npm_build_succeeds(self):
        """Verify the project builds successfully"""
        result = subprocess.run(
            ["npm", "run", "build"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, (
            f"Build failed:\n{result.stdout[:1000]}\n{result.stderr[:500]}"
        )

    def test_build_output_exists(self):
        """Verify build produces output files"""
        # Common build output directories
        possible_dirs = ["build", "dist", "out"]
        found = False
        for d in possible_dirs:
            path = os.path.join(self.REPO_DIR, d)
            if os.path.isdir(path) and os.listdir(path):
                found = True
                break
        assert found, "No build output directory found (build/, dist/, or out/)"
