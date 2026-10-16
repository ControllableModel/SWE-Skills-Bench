"""
Test skill: python-packaging
Verify that the Agent correctly implements a PEP 621 metadata validator,
build backend shim, and dependency resolver for the packaging library.
"""

import os
import re
import ast
import subprocess
import pytest


class TestPythonPackaging:
    REPO_DIR = "/workspace/packaging"

    # === File Path Checks ===

    def test_metadata_init_exists(self):
        """Verify packaging/metadata/__init__.py was created"""
        path = os.path.join(self.REPO_DIR, "packaging/metadata/__init__.py")
        assert os.path.exists(path), f"__init__.py not found at {path}"

    def test_validator_exists(self):
        """Verify packaging/metadata/validator.py was created"""
        path = os.path.join(self.REPO_DIR, "packaging/metadata/validator.py")
        assert os.path.exists(path), f"validator.py not found at {path}"

    def test_build_system_exists(self):
        """Verify packaging/metadata/build_system.py was created"""
        path = os.path.join(self.REPO_DIR, "packaging/metadata/build_system.py")
        assert os.path.exists(path), f"build_system.py not found at {path}"

    def test_dependency_resolver_exists(self):
        """Verify packaging/metadata/dependency_resolver.py was created"""
        path = os.path.join(
            self.REPO_DIR, "packaging/metadata/dependency_resolver.py"
        )
        assert os.path.exists(path), f"dependency_resolver.py not found at {path}"

    def test_validator_test_exists(self):
        """Verify tests/test_pyproject_validator.py was created"""
        path = os.path.join(self.REPO_DIR, "tests/test_pyproject_validator.py")
        assert os.path.exists(path), f"test_pyproject_validator.py not found"

    def test_build_system_test_exists(self):
        """Verify tests/test_build_system.py was created"""
        path = os.path.join(self.REPO_DIR, "tests/test_build_system.py")
        assert os.path.exists(path), f"test_build_system.py not found"

    def test_dependency_resolver_test_exists(self):
        """Verify tests/test_dependency_resolver.py was created"""
        path = os.path.join(self.REPO_DIR, "tests/test_dependency_resolver.py")
        assert os.path.exists(path), f"test_dependency_resolver.py not found"

    # === Semantic Checks: PyProjectValidator ===

    def test_validator_class_defined(self):
        """Verify PyProjectValidator class is defined"""
        path = os.path.join(self.REPO_DIR, "packaging/metadata/validator.py")
        with open(path) as f:
            content = f.read()
        assert "class PyProjectValidator" in content, (
            "PyProjectValidator class should be defined"
        )

    def test_validator_has_validate_method(self):
        """Verify validate method exists"""
        path = os.path.join(self.REPO_DIR, "packaging/metadata/validator.py")
        with open(path) as f:
            content = f.read()
        assert "def validate(" in content, "Should have validate method"

    def test_validator_checks_name(self):
        """Verify name field validation"""
        path = os.path.join(self.REPO_DIR, "packaging/metadata/validator.py")
        with open(path) as f:
            content = f.read()
        assert "name" in content, "Should validate project name field"

    def test_validator_checks_version_pep440(self):
        """Verify version validation against PEP 440"""
        path = os.path.join(self.REPO_DIR, "packaging/metadata/validator.py")
        with open(path) as f:
            content = f.read()
        assert "Version" in content or "version" in content, (
            "Should validate version against PEP 440"
        )

    def test_validator_checks_dependencies_pep508(self):
        """Verify dependency validation against PEP 508"""
        path = os.path.join(self.REPO_DIR, "packaging/metadata/validator.py")
        with open(path) as f:
            content = f.read()
        assert "Requirement" in content or "requirement" in content, (
            "Should validate dependencies against PEP 508"
        )

    def test_validator_checks_requires_python(self):
        """Verify requires-python validation"""
        path = os.path.join(self.REPO_DIR, "packaging/metadata/validator.py")
        with open(path) as f:
            content = f.read()
        assert "requires-python" in content or "requires_python" in content, (
            "Should validate requires-python specifier"
        )

    def test_validator_checks_urls(self):
        """Verify URL validation (http/https)"""
        path = os.path.join(self.REPO_DIR, "packaging/metadata/validator.py")
        with open(path) as f:
            content = f.read()
        assert "http" in content, "Should validate URLs start with http/https"

    def test_validator_has_validation_result(self):
        """Verify ValidationResult with is_valid, errors, warnings"""
        path = os.path.join(self.REPO_DIR, "packaging/metadata/validator.py")
        with open(path) as f:
            content = f.read()
        assert "ValidationResult" in content or "is_valid" in content, (
            "Should return ValidationResult with is_valid"
        )

    # === Semantic Checks: BuildSystemInfo ===

    def test_build_system_class_defined(self):
        """Verify BuildSystemInfo class is defined"""
        path = os.path.join(self.REPO_DIR, "packaging/metadata/build_system.py")
        with open(path) as f:
            content = f.read()
        assert "class BuildSystemInfo" in content, (
            "BuildSystemInfo class should be defined"
        )

    def test_build_system_detects_backend_type(self):
        """Verify backend_type detection (setuptools, hatchling, flit, etc.)"""
        path = os.path.join(self.REPO_DIR, "packaging/metadata/build_system.py")
        with open(path) as f:
            content = f.read()
        for backend in ["setuptools", "hatchling", "flit", "poetry"]:
            assert backend in content, f"Should detect {backend} backend type"

    def test_build_system_pep517_compliance(self):
        """Verify is_pep517_compliant method"""
        path = os.path.join(self.REPO_DIR, "packaging/metadata/build_system.py")
        with open(path) as f:
            content = f.read()
        assert "pep517" in content.lower() or "is_pep517" in content, (
            "Should have PEP 517 compliance check"
        )

    # === Semantic Checks: DependencyResolver ===

    def test_dependency_resolver_class_defined(self):
        """Verify DependencyResolver class is defined"""
        path = os.path.join(
            self.REPO_DIR, "packaging/metadata/dependency_resolver.py"
        )
        with open(path) as f:
            content = f.read()
        assert "class DependencyResolver" in content, (
            "DependencyResolver class should be defined"
        )

    def test_resolver_detects_self_references(self):
        """Verify detect_self_references method"""
        path = os.path.join(
            self.REPO_DIR, "packaging/metadata/dependency_resolver.py"
        )
        with open(path) as f:
            content = f.read()
        assert "detect_self_references" in content, (
            "Should have detect_self_references method"
        )

    def test_resolver_detects_circular_extras(self):
        """Verify detect_circular_extras method"""
        path = os.path.join(
            self.REPO_DIR, "packaging/metadata/dependency_resolver.py"
        )
        with open(path) as f:
            content = f.read()
        assert "detect_circular_extras" in content or "circular" in content, (
            "Should have detect_circular_extras method"
        )

    def test_resolver_normalizes_names_pep503(self):
        """Verify normalize_name follows PEP 503"""
        path = os.path.join(
            self.REPO_DIR, "packaging/metadata/dependency_resolver.py"
        )
        with open(path) as f:
            content = f.read()
        assert "normalize_name" in content, (
            "Should have normalize_name method"
        )

    def test_resolver_resolve_extras(self):
        """Verify resolve_extras method for transitive expansion"""
        path = os.path.join(
            self.REPO_DIR, "packaging/metadata/dependency_resolver.py"
        )
        with open(path) as f:
            content = f.read()
        assert "resolve_extras" in content, (
            "Should have resolve_extras method"
        )

    # === Semantic Checks: __init__.py exports ===

    def test_init_exports_classes(self):
        """Verify __init__.py re-exports main classes"""
        path = os.path.join(self.REPO_DIR, "packaging/metadata/__init__.py")
        with open(path) as f:
            content = f.read()
        assert "PyProjectValidator" in content, (
            "__init__.py should export PyProjectValidator"
        )
        assert "BuildSystemInfo" in content, (
            "__init__.py should export BuildSystemInfo"
        )
        assert "DependencyResolver" in content, (
            "__init__.py should export DependencyResolver"
        )

    # === Functional Checks ===

    def test_validator_parses(self):
        """Verify validator.py has valid Python syntax"""
        path = os.path.join(self.REPO_DIR, "packaging/metadata/validator.py")
        with open(path) as f:
            source = f.read()
        try:
            ast.parse(source)
        except SyntaxError as e:
            pytest.fail(f"validator.py has syntax error: {e}")

    def test_build_system_parses(self):
        """Verify build_system.py has valid Python syntax"""
        path = os.path.join(self.REPO_DIR, "packaging/metadata/build_system.py")
        with open(path) as f:
            source = f.read()
        try:
            ast.parse(source)
        except SyntaxError as e:
            pytest.fail(f"build_system.py has syntax error: {e}")

    def test_dependency_resolver_parses(self):
        """Verify dependency_resolver.py has valid Python syntax"""
        path = os.path.join(
            self.REPO_DIR, "packaging/metadata/dependency_resolver.py"
        )
        with open(path) as f:
            source = f.read()
        try:
            ast.parse(source)
        except SyntaxError as e:
            pytest.fail(f"dependency_resolver.py has syntax error: {e}")

    def test_validator_tests_pass(self):
        """Verify validator tests pass"""
        result = subprocess.run(
            [
                "python", "-m", "pytest",
                "tests/test_pyproject_validator.py",
                "-v", "--tb=short",
            ],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, (
            f"Validator tests failed:\n{result.stdout}\n{result.stderr}"
        )

    def test_build_system_tests_pass(self):
        """Verify build system tests pass"""
        result = subprocess.run(
            [
                "python", "-m", "pytest",
                "tests/test_build_system.py",
                "-v", "--tb=short",
            ],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, (
            f"Build system tests failed:\n{result.stdout}\n{result.stderr}"
        )

    def test_dependency_resolver_tests_pass(self):
        """Verify dependency resolver tests pass"""
        result = subprocess.run(
            [
                "python", "-m", "pytest",
                "tests/test_dependency_resolver.py",
                "-v", "--tb=short",
            ],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, (
            f"Dependency resolver tests failed:\n{result.stdout}\n{result.stderr}"
        )
