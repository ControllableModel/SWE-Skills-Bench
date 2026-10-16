"""
Tests for the python-packaging skill.
Validates creation of a distributable Python package for the Packaging library's
test utilities with PEP 621 metadata, src layout, and utility classes.
"""

import os
import re
import ast

REPO_DIR = "/workspace/packaging"
PKG_DIR = os.path.join(REPO_DIR, "packaging_test_utils")
SRC_DIR = os.path.join(PKG_DIR, "src", "packaging_test_utils")


class TestPythonPackaging:
    """Tests for the packaging-test-utils package."""

    # ── file_path_check ──────────────────────────────────────────────

    def test_pyproject_toml_exists(self):
        """pyproject.toml must exist."""
        path = os.path.join(PKG_DIR, "pyproject.toml")
        assert os.path.isfile(path), f"Missing {path}"

    def test_init_file_exists(self):
        """Package __init__.py must exist in src layout."""
        path = os.path.join(SRC_DIR, "__init__.py")
        assert os.path.isfile(path), f"Missing {path}"

    def test_versions_module_exists(self):
        """VersionFactory module must exist."""
        path = os.path.join(SRC_DIR, "versions.py")
        assert os.path.isfile(path), f"Missing {path}"

    def test_specifiers_module_exists(self):
        """SpecifierFactory module must exist."""
        path = os.path.join(SRC_DIR, "specifiers.py")
        assert os.path.isfile(path), f"Missing {path}"

    def test_markers_module_exists(self):
        """MarkerEvaluator module must exist."""
        path = os.path.join(SRC_DIR, "markers.py")
        assert os.path.isfile(path), f"Missing {path}"

    def test_readme_exists(self):
        """README.md must exist."""
        path = os.path.join(PKG_DIR, "README.md")
        assert os.path.isfile(path), f"Missing {path}"

    # ── semantic_check ───────────────────────────────────────────────

    def _read_src(self, filename):
        path = os.path.join(SRC_DIR, filename)
        if not os.path.isfile(path):
            return ""
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def _read_pkg(self, filename):
        path = os.path.join(PKG_DIR, filename)
        if not os.path.isfile(path):
            return ""
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def test_pyproject_pep621_metadata(self):
        """pyproject.toml must include PEP 621 project metadata."""
        content = self._read_pkg("pyproject.toml")
        assert "[project]" in content, "[project] table missing"
        assert "packaging-test-utils" in content, "Package name not found"
        assert "requires-python" in content, "requires-python not specified"

    def test_pyproject_hatchling_backend(self):
        """pyproject.toml must use hatchling as build backend."""
        content = self._read_pkg("pyproject.toml")
        assert "hatchling" in content, "hatchling build backend not specified"

    def test_pyproject_packaging_dependency(self):
        """pyproject.toml must depend on packaging>=24.0."""
        content = self._read_pkg("pyproject.toml")
        assert re.search(r"packaging.*>=.*24", content), (
            "packaging>=24.0 dependency not found"
        )

    def test_test_optional_dependency(self):
        """pyproject.toml must have test optional dependency with pytest."""
        content = self._read_pkg("pyproject.toml")
        assert re.search(r"test.*=|optional-dependencies", content, re.IGNORECASE), (
            "Test optional dependency not found"
        )
        assert "pytest" in content, "pytest not in test dependencies"

    def test_version_factory_class(self):
        """VersionFactory must define create, sequence, and pre_release_set."""
        content = self._read_src("versions.py")
        assert re.search(r"class\s+VersionFactory", content), "VersionFactory class not defined"
        for method in ["create", "sequence", "pre_release_set"]:
            assert re.search(rf"def\s+{method}\b", content), (
                f"VersionFactory.{method} method not defined"
            )

    def test_specifier_factory_class(self):
        """SpecifierFactory must define from_spec, range, compatible, matches."""
        content = self._read_src("specifiers.py")
        assert re.search(r"class\s+SpecifierFactory", content), (
            "SpecifierFactory class not defined"
        )
        for method in ["from_spec", "range", "compatible", "matches"]:
            assert re.search(rf"def\s+{method}\b", content), (
                f"SpecifierFactory.{method} method not defined"
            )

    def test_marker_evaluator_class(self):
        """MarkerEvaluator must define evaluate and required_on."""
        content = self._read_src("markers.py")
        assert re.search(r"class\s+MarkerEvaluator", content), (
            "MarkerEvaluator class not defined"
        )
        assert re.search(r"def\s+evaluate\b", content), "evaluate method not defined"
        assert re.search(r"def\s+required_on\b", content), "required_on method not defined"

    # ── functional_check ─────────────────────────────────────────────

    def test_all_files_valid_python(self):
        """All source Python files must have valid syntax."""
        errors = []
        for fname in ["__init__.py", "versions.py", "specifiers.py", "markers.py"]:
            content = self._read_src(fname)
            if not content:
                continue
            try:
                ast.parse(content)
            except SyntaxError as e:
                errors.append(f"{fname}: {e}")
        assert not errors, "Syntax errors:\n" + "\n".join(errors)

    def test_init_exports_public_api(self):
        """__init__.py must export VersionFactory, SpecifierFactory, MarkerEvaluator."""
        content = self._read_src("__init__.py")
        for cls in ["VersionFactory", "SpecifierFactory", "MarkerEvaluator"]:
            assert cls in content, f"{cls} not exported from __init__.py"

    def test_invalid_version_raises_error(self):
        """VersionFactory must raise InvalidVersion for invalid strings."""
        content = self._read_src("versions.py")
        assert re.search(r"InvalidVersion|invalid.*version", content, re.IGNORECASE), (
            "InvalidVersion error handling not found"
        )

    def test_src_layout_wheel_config(self):
        """pyproject.toml must specify src layout for hatch wheel build."""
        content = self._read_pkg("pyproject.toml")
        assert re.search(r"packages|src", content), (
            "src layout configuration not found in pyproject.toml"
        )

    def test_test_files_exist(self):
        """Test files for versions, specifiers, markers must exist."""
        tests_dir = os.path.join(PKG_DIR, "tests")
        for fname in ["test_versions.py", "test_specifiers.py", "test_markers.py"]:
            path = os.path.join(tests_dir, fname)
            assert os.path.isfile(path), f"Missing {path}"
