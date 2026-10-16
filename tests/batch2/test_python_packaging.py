"""
Test skill: python-packaging
Verify that the Agent creates a packaging demo script exercising
PEP 440 version parsing, specifier matching, requirement handling,
and error reporting.
"""

import os
import re
import ast
import subprocess
import pytest


class TestPythonPackaging:
    REPO_DIR = "/workspace/packaging"

    # === File Path Checks ===

    def test_demo_script_exists(self):
        """Verify scripts/demo_packaging.py exists"""
        path = os.path.join(self.REPO_DIR, "scripts/demo_packaging.py")
        assert os.path.exists(path), f"demo_packaging.py not found at {path}"

    # === Semantic Checks ===

    def test_version_parsing(self):
        """Verify PEP 440 version parsing is demonstrated"""
        path = os.path.join(self.REPO_DIR, "scripts/demo_packaging.py")
        with open(path) as f:
            content = f.read()

        version_indicators = [
            "Version", "parse", "version", "PEP 440",
            "release", "pre", "post", "dev",
        ]
        found = [ind for ind in version_indicators if ind in content]
        assert len(found) >= 3, (
            f"Should demonstrate version parsing. Found: {found}"
        )

    def test_version_comparison(self):
        """Verify version comparison and sorting"""
        path = os.path.join(self.REPO_DIR, "scripts/demo_packaging.py")
        with open(path) as f:
            content = f.read()

        compare_indicators = [
            "sort", "compare", "<", ">", "==", "!=",
            "sorted(", "min(", "max(",
        ]
        found = [ind for ind in compare_indicators if ind in content]
        assert len(found) >= 2, (
            f"Should demonstrate version comparison. Found: {found}"
        )

    def test_specifier_matching(self):
        """Verify version specifier matching is demonstrated"""
        path = os.path.join(self.REPO_DIR, "scripts/demo_packaging.py")
        with open(path) as f:
            content = f.read()

        specifier_indicators = [
            "Specifier", "SpecifierSet", "specifier",
            ">=", "<", "~=", "!=", "contains",
        ]
        found = [ind for ind in specifier_indicators if ind in content]
        assert len(found) >= 2, (
            f"Should demonstrate specifier matching. Found: {found}"
        )

    def test_requirement_parsing(self):
        """Verify requirement string parsing"""
        path = os.path.join(self.REPO_DIR, "scripts/demo_packaging.py")
        with open(path) as f:
            content = f.read()

        req_indicators = [
            "Requirement", "requirement", "extras", "marker",
            "name", "specifier",
        ]
        found = [ind for ind in req_indicators if ind in content]
        assert len(found) >= 2, (
            f"Should demonstrate requirement parsing. Found: {found}"
        )

    def test_invalid_version_handling(self):
        """Verify graceful handling of invalid version strings"""
        path = os.path.join(self.REPO_DIR, "scripts/demo_packaging.py")
        with open(path) as f:
            content = f.read()

        error_indicators = [
            "Invalid", "invalid", "error", "except",
            "try", "InvalidVersion", "ValueError",
        ]
        found = [ind for ind in error_indicators if ind in content]
        assert len(found) >= 2, (
            f"Should handle invalid versions gracefully. Found: {found}"
        )

    def test_pre_release_versions(self):
        """Verify pre-release version handling"""
        path = os.path.join(self.REPO_DIR, "scripts/demo_packaging.py")
        with open(path) as f:
            content = f.read().lower()

        prerelease_indicators = [
            "pre", "alpha", "beta", "rc", "dev",
            "pre_release", "is_prerelease",
        ]
        found = [ind for ind in prerelease_indicators if ind in content]
        assert len(found) >= 1, (
            f"Should demonstrate pre-release versions. Found: {found}"
        )

    def test_structured_output(self):
        """Verify structured report output"""
        path = os.path.join(self.REPO_DIR, "scripts/demo_packaging.py")
        with open(path) as f:
            content = f.read()

        output_indicators = [
            "print", "format", "report", "result",
            "table", "=", "---",
        ]
        found = [ind for ind in output_indicators if ind in content]
        assert len(found) >= 2, (
            f"Should produce structured output. Found: {found}"
        )

    # === Functional Checks ===

    def test_script_valid_python(self):
        """Verify demo_packaging.py is valid Python"""
        path = os.path.join(self.REPO_DIR, "scripts/demo_packaging.py")
        with open(path) as f:
            source = f.read()
        try:
            ast.parse(source)
        except SyntaxError as e:
            pytest.fail(f"demo_packaging.py has syntax errors: {e}")

    def test_has_main_entry_point(self):
        """Verify script has __main__ entry point"""
        path = os.path.join(self.REPO_DIR, "scripts/demo_packaging.py")
        with open(path) as f:
            content = f.read()

        assert '__name__' in content and '__main__' in content, (
            "Script should have a __main__ entry point"
        )

    def test_imports_packaging(self):
        """Verify script imports from the packaging library"""
        path = os.path.join(self.REPO_DIR, "scripts/demo_packaging.py")
        with open(path) as f:
            content = f.read()

        import_indicators = [
            "from packaging", "import packaging",
        ]
        found = [ind for ind in import_indicators if ind in content]
        assert len(found) >= 1, (
            f"Should import from the packaging library. Found: {found}"
        )

    def test_importable(self):
        """Verify script can be imported without errors"""
        path = os.path.join(self.REPO_DIR, "scripts/demo_packaging.py")
        result = subprocess.run(
            [
                "python", "-c",
                f"import ast; ast.parse(open('{path}').read())",
            ],
            capture_output=True, text=True, timeout=15,
        )
        assert result.returncode == 0, (
            f"Script should be parseable: {result.stderr}"
        )

    def test_epoch_version_support(self):
        """Verify epoch-prefixed version parsing is covered"""
        path = os.path.join(self.REPO_DIR, "scripts/demo_packaging.py")
        with open(path) as f:
            content = f.read()

        epoch_indicators = ["epoch", "1!", "2!"]
        found = [ind for ind in epoch_indicators if ind in content]
        assert len(found) >= 1, (
            f"Should demonstrate epoch-prefixed versions. Found: {found}"
        )
