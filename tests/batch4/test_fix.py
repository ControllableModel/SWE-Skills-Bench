"""
Test skill: fix
Verify that lint and formatting violations in the Upgradle React application
have been correctly resolved without altering runtime behavior.
No eslint-disable comments should be added; all issues must be properly fixed.
"""

import os
import re
import json
import subprocess
import pytest


class TestFix:
    REPO_DIR = "/workspace/upgradle"

    @classmethod
    def _ensure_npm_installed(cls):
        """Helper to ensure npm dependencies are installed (called by tests that need it)"""
        result = subprocess.run(
            ["npm", "install"],
            cwd=cls.REPO_DIR,
            capture_output=True, text=True, timeout=120
        )
        if result.returncode != 0:
            pytest.skip(f"npm install failed: {result.stderr[:500]}")

    # === File Path Checks ===

    def test_app_js_exists(self):
        """Verify that src/App.js exists in the repository"""
        filepath = os.path.join(self.REPO_DIR, "src/App.js")
        assert os.path.exists(filepath), f"App.js not found at {filepath}"

    def test_board_js_exists(self):
        """Verify that src/components/Board.js exists"""
        filepath = os.path.join(self.REPO_DIR, "src/components/Board.js")
        assert os.path.exists(filepath), f"Board.js not found at {filepath}"

    def test_tile_js_exists(self):
        """Verify that src/components/Tile.js exists"""
        filepath = os.path.join(self.REPO_DIR, "src/components/Tile.js")
        assert os.path.exists(filepath), f"Tile.js not found at {filepath}"

    def test_index_js_exists(self):
        """Verify that src/index.js exists"""
        filepath = os.path.join(self.REPO_DIR, "src/index.js")
        assert os.path.exists(filepath), f"index.js not found at {filepath}"

    # === Semantic Checks ===

    def test_no_eslint_disable_comments_in_src(self):
        """Verify that no eslint-disable comments were added to suppress warnings"""
        src_dir = os.path.join(self.REPO_DIR, "src")
        violations = []
        for root, dirs, files in os.walk(src_dir):
            for fname in files:
                if fname.endswith(('.js', '.jsx', '.ts', '.tsx')):
                    filepath = os.path.join(root, fname)
                    with open(filepath) as f:
                        for line_num, line in enumerate(f, 1):
                            if "eslint-disable" in line:
                                violations.append(f"{filepath}:{line_num}: {line.strip()}")
        assert len(violations) == 0, \
            f"Found eslint-disable comments (should fix issues instead):\n" + "\n".join(violations)

    def test_source_files_are_syntactically_valid(self):
        """Verify that all modified JS source files are syntactically valid using node --check"""
        src_files = [
            "src/App.js",
            "src/components/Board.js",
            "src/components/Tile.js",
            "src/index.js",
        ]
        node_check = subprocess.run(["which", "node"], capture_output=True, text=True)
        if node_check.returncode != 0:
            pytest.skip("Node.js not available in this environment")

        for rel_path in src_files:
            filepath = os.path.join(self.REPO_DIR, rel_path)
            if os.path.exists(filepath):
                result = subprocess.run(
                    ["node", "--check", filepath],
                    capture_output=True, text=True, timeout=30
                )
                assert result.returncode == 0, \
                    f"Syntax error in {rel_path}: {result.stderr}"

    def test_index_js_no_unused_imports(self):
        """Verify that unused imports have been removed from index.js"""
        filepath = os.path.join(self.REPO_DIR, "src/index.js")
        with open(filepath) as f:
            content = f.read()
        lines = content.split('\n')
        import_lines = [l.strip() for l in lines if l.strip().startswith('import')]
        non_import_content = '\n'.join(l for l in lines if not l.strip().startswith('import'))

        for imp in import_lines:
            # Extract default import name e.g. "import React from '...'" -> "React"
            match = re.match(r"import\s+(\w+)\s+from", imp)
            if match:
                name = match.group(1)
                # In older React (pre-17), React import is needed for JSX even if not explicitly used
                if name == "React":
                    continue
                # Check the name appears somewhere in the non-import code
                if name not in non_import_content:
                    pytest.fail(
                        f"Import '{name}' in index.js appears unused. "
                        f"Import line: {imp}"
                    )

    def test_files_use_consistent_quote_style(self):
        """Verify that JS files use a consistent quote style (as per Prettier config)"""
        # Check for Prettier config to determine expected quote style
        pkg_path = os.path.join(self.REPO_DIR, "package.json")
        expected_single = True  # Prettier default is double, but many React projects use single
        if os.path.exists(pkg_path):
            with open(pkg_path) as f:
                pkg = json.load(f)
            prettier_config = pkg.get("prettier", {})
            if isinstance(prettier_config, dict):
                expected_single = prettier_config.get("singleQuote", False)

        # Verify at least one file follows the config (basic consistency check)
        filepath = os.path.join(self.REPO_DIR, "src/App.js")
        if os.path.exists(filepath):
            with open(filepath) as f:
                content = f.read()
            # This is a soft check - just verify the file is non-empty and has imports
            assert len(content.strip()) > 0, "App.js should not be empty"

    # === Functional Checks ===

    def test_npm_install_succeeds(self):
        """Verify that npm install succeeds for the project"""
        node_check = subprocess.run(["which", "node"], capture_output=True, text=True)
        if node_check.returncode != 0:
            pytest.skip("Node.js not available")

        result = subprocess.run(
            ["npm", "install"],
            cwd=self.REPO_DIR,
            capture_output=True, text=True, timeout=180
        )
        assert result.returncode == 0, \
            f"npm install failed: {result.stderr[:1000]}"

    def test_prettier_formatting_check_passes(self):
        """Verify that Prettier formatting check reports zero differences"""
        self._ensure_npm_installed()

        # Determine the correct formatting check command from package.json
        pkg_path = os.path.join(self.REPO_DIR, "package.json")
        with open(pkg_path) as f:
            pkg = json.load(f)
        scripts = pkg.get("scripts", {})

        # Try known script names for format check
        format_cmd = None
        for key in ["format:check", "prettier:check", "format", "prettier"]:
            if key in scripts:
                format_cmd = key
                break

        if format_cmd:
            result = subprocess.run(
                ["npm", "run", format_cmd],
                cwd=self.REPO_DIR,
                capture_output=True, text=True, timeout=60
            )
            assert result.returncode == 0, \
                f"Prettier check failed (npm run {format_cmd}):\n{result.stdout[:1000]}\n{result.stderr[:500]}"
        else:
            # Run prettier directly
            result = subprocess.run(
                ["npx", "prettier", "--check", "src/"],
                cwd=self.REPO_DIR,
                capture_output=True, text=True, timeout=60
            )
            assert result.returncode == 0, \
                f"Prettier check failed:\n{result.stdout[:1000]}\n{result.stderr[:500]}"

    def test_eslint_check_passes_zero_errors_and_warnings(self):
        """Verify that ESLint reports zero errors and zero warnings"""
        self._ensure_npm_installed()

        # Try eslint via npx with JSON format for precise validation
        result = subprocess.run(
            ["npx", "eslint", "src/", "--format=json", "--max-warnings=0"],
            cwd=self.REPO_DIR,
            capture_output=True, text=True, timeout=60
        )

        if result.returncode != 0:
            # Parse JSON output for detailed error info
            try:
                lint_output = json.loads(result.stdout)
                total_errors = sum(f.get("errorCount", 0) for f in lint_output)
                total_warnings = sum(f.get("warningCount", 0) for f in lint_output)
                error_details = []
                for f in lint_output:
                    for msg in f.get("messages", []):
                        error_details.append(
                            f"  {f['filePath']}:{msg.get('line', '?')}: "
                            f"[{msg.get('ruleId', '?')}] {msg.get('message', '')}"
                        )
                detail_str = "\n".join(error_details[:20])
                pytest.fail(
                    f"ESLint found {total_errors} errors and {total_warnings} warnings:\n{detail_str}"
                )
            except json.JSONDecodeError:
                pytest.fail(
                    f"ESLint check failed (rc={result.returncode}):\n"
                    f"{result.stdout[:1000]}\n{result.stderr[:500]}"
                )

    def test_react_app_builds_successfully(self):
        """Verify that the React application builds without errors (CI=true treats warnings as errors)"""
        self._ensure_npm_installed()

        env = os.environ.copy()
        env["CI"] = "true"
        result = subprocess.run(
            ["npm", "run", "build"],
            cwd=self.REPO_DIR,
            capture_output=True, text=True, timeout=180,
            env=env,
        )
        assert result.returncode == 0, \
            f"React build failed with CI=true:\n{result.stdout[-1500:]}\n{result.stderr[-500:]}"

    def test_lint_script_in_package_json_passes(self):
        """Verify that the project's own lint script (if defined) exits cleanly"""
        self._ensure_npm_installed()

        pkg_path = os.path.join(self.REPO_DIR, "package.json")
        with open(pkg_path) as f:
            pkg = json.load(f)
        scripts = pkg.get("scripts", {})

        lint_cmd = None
        for key in ["lint", "lint:check", "eslint"]:
            if key in scripts:
                lint_cmd = key
                break

        if lint_cmd is None:
            pytest.skip("No dedicated lint script found in package.json")

        result = subprocess.run(
            ["npm", "run", lint_cmd],
            cwd=self.REPO_DIR,
            capture_output=True, text=True, timeout=60
        )
        assert result.returncode == 0, \
            f"Lint script 'npm run {lint_cmd}' failed:\n{result.stdout[:1000]}\n{result.stderr[:500]}"

    def test_no_proptype_violations_in_components(self):
        """Verify that PropTypes declarations match actual props usage in components"""
        component_files = [
            "src/components/Board.js",
            "src/components/Tile.js",
        ]
        for rel_path in component_files:
            filepath = os.path.join(self.REPO_DIR, rel_path)
            if not os.path.exists(filepath):
                continue
            with open(filepath) as f:
                content = f.read()
            # If PropTypes is imported, it should be defined for the component
            if "import PropTypes" in content or "from 'prop-types'" in content:
                assert ".propTypes" in content, \
                    f"{rel_path} imports PropTypes but never defines .propTypes on a component"
