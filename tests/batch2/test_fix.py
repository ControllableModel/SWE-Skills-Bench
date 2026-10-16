"""
Test skill: fix
Verify that the Agent correctly fixes lint and formatting violations
in the Upgradle React TypeScript project without introducing functional
changes or suppressing lint rules.
"""

import os
import json
import subprocess
import pytest


class TestFix:
    REPO_DIR = "/workspace/upgradle"

    @classmethod
    def _ensure_deps(cls):
        """Install npm dependencies if not already present."""
        if not os.path.exists(os.path.join(cls.REPO_DIR, "node_modules")):
            result = subprocess.run(
                ["npm", "install"],
                cwd=cls.REPO_DIR,
                capture_output=True,
                text=True,
                timeout=300,
            )
            if result.returncode != 0:
                pytest.skip(f"npm install failed: {result.stderr[:500]}")

    # === File Path Checks ===

    def test_app_tsx_exists(self):
        """Verify src/App.tsx exists"""
        path = os.path.join(self.REPO_DIR, "src/App.tsx")
        assert os.path.exists(path), f"App.tsx not found at {path}"

    def test_index_tsx_exists(self):
        """Verify src/index.tsx exists"""
        path = os.path.join(self.REPO_DIR, "src/index.tsx")
        assert os.path.exists(path), f"index.tsx not found at {path}"

    def test_package_json_exists_and_parseable(self):
        """Verify package.json exists and is valid JSON"""
        path = os.path.join(self.REPO_DIR, "package.json")
        assert os.path.exists(path), f"package.json not found at {path}"
        with open(path) as f:
            pkg = json.load(f)
        assert "scripts" in pkg, "package.json must have a 'scripts' section"

    # === Semantic Checks ===

    def test_no_blanket_eslint_disable_in_src(self):
        """Verify no blanket eslint-disable comments were added to any src file"""
        src_dir = os.path.join(self.REPO_DIR, "src")
        blanket_disable_files = []
        for root, _dirs, files in os.walk(src_dir):
            for fname in files:
                if fname.endswith((".ts", ".tsx", ".js", ".jsx")):
                    fpath = os.path.join(root, fname)
                    with open(fpath) as f:
                        content = f.read()
                    if "/* eslint-disable */" in content:
                        blanket_disable_files.append(
                            os.path.relpath(fpath, self.REPO_DIR)
                        )
        assert blanket_disable_files == [], (
            f"Blanket eslint-disable found in: {blanket_disable_files}. "
            "Lint rules should be fixed, not suppressed."
        )

    def test_no_excessive_eslint_disable_next_line(self):
        """Verify eslint-disable-next-line is not overused to bypass fixes"""
        src_dir = os.path.join(self.REPO_DIR, "src")
        total_disable_count = 0
        for root, _dirs, files in os.walk(src_dir):
            for fname in files:
                if fname.endswith((".ts", ".tsx", ".js", ".jsx")):
                    fpath = os.path.join(root, fname)
                    with open(fpath) as f:
                        content = f.read()
                    total_disable_count += content.count("eslint-disable-next-line")
        assert total_disable_count <= 3, (
            f"Found {total_disable_count} eslint-disable-next-line comments. "
            "Expected at most 3 — issues should be fixed, not suppressed."
        )

    def test_eslint_config_not_weakened(self):
        """Verify ESLint config was not weakened by turning rules off"""
        # Check .eslintrc or eslintConfig in package.json
        pkg_path = os.path.join(self.REPO_DIR, "package.json")
        with open(pkg_path) as f:
            pkg = json.load(f)

        eslint_config = pkg.get("eslintConfig", {})
        rules = eslint_config.get("rules", {})

        disabled_rules = [
            rule for rule, val in rules.items()
            if val == "off" or val == 0 or (isinstance(val, list) and val[0] in ("off", 0))
        ]
        assert len(disabled_rules) <= 2, (
            f"ESLint config has too many disabled rules: {disabled_rules}. "
            "Rules should not be turned off to fix lint violations."
        )

    def test_source_files_are_not_empty(self):
        """Verify that key source files are not empty after fixes"""
        critical_files = ["src/App.tsx", "src/index.tsx"]
        for rel_path in critical_files:
            fpath = os.path.join(self.REPO_DIR, rel_path)
            if os.path.exists(fpath):
                size = os.path.getsize(fpath)
                assert size > 50, (
                    f"{rel_path} is suspiciously small ({size} bytes). "
                    "Files should be fixed, not gutted."
                )

    # === Functional Checks ===

    def test_npm_install_succeeds(self):
        """Verify npm install completes successfully"""
        result = subprocess.run(
            ["npm", "install"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=300,
        )
        assert result.returncode == 0 or os.path.exists(
            os.path.join(self.REPO_DIR, "node_modules")
        ), f"npm install failed: {result.stderr[:1000]}"

    def test_lint_command_exits_zero(self):
        """Verify npm run lint exits with code 0 (no errors)"""
        self._ensure_deps()
        result = subprocess.run(
            ["npm", "run", "lint"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, (
            f"Lint still reports errors (exit code {result.returncode}).\n"
            f"stdout: {result.stdout[:2000]}\n"
            f"stderr: {result.stderr[:2000]}"
        )

    def test_lint_output_has_no_error_lines(self):
        """Verify lint output does not contain error-level messages"""
        self._ensure_deps()
        result = subprocess.run(
            ["npm", "run", "lint"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        combined = result.stdout + result.stderr
        # ESLint typically reports "X problems (Y errors, Z warnings)"
        import re
        error_match = re.search(r"(\d+)\s+error", combined.lower())
        if error_match:
            error_count = int(error_match.group(1))
            assert error_count == 0, (
                f"Lint reports {error_count} error(s). Output:\n{combined[:2000]}"
            )

    def test_typescript_compilation_no_new_syntax_errors(self):
        """Verify TypeScript files do not have syntax-level errors"""
        self._ensure_deps()
        result = subprocess.run(
            ["npx", "tsc", "--noEmit", "--pretty", "false"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        # We check for *syntax* errors specifically introduced by the fix
        if result.returncode != 0:
            output = result.stdout + result.stderr
            syntax_errors = [
                line for line in output.splitlines()
                if "error TS1" in line  # TS1xxx = syntax errors
            ]
            assert len(syntax_errors) == 0, (
                f"TypeScript syntax errors detected:\n" +
                "\n".join(syntax_errors[:10])
            )

    def test_app_tsx_contains_valid_component(self):
        """Verify App.tsx still contains a valid React component export"""
        path = os.path.join(self.REPO_DIR, "src/App.tsx")
        with open(path) as f:
            content = f.read()
        assert "import" in content, "App.tsx should retain import statements"
        has_component = (
            "function App" in content
            or "const App" in content
            or "class App" in content
            or "export default" in content
        )
        assert has_component, (
            "App.tsx should still export a React component (function/const/class App or default export)"
        )

    def test_project_builds_successfully(self):
        """Verify the project can build without errors after lint fixes"""
        self._ensure_deps()
        # Check if build script exists
        pkg_path = os.path.join(self.REPO_DIR, "package.json")
        with open(pkg_path) as f:
            pkg = json.load(f)
        if "build" not in pkg.get("scripts", {}):
            pytest.skip("No build script defined in package.json")

        result = subprocess.run(
            ["npm", "run", "build"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=300,
        )
        assert result.returncode == 0, (
            f"Build failed after lint fixes (exit code {result.returncode}).\n"
            f"stderr: {result.stderr[:2000]}"
        )
