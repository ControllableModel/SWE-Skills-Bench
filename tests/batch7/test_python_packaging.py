"""
Test skill: python-packaging
Verify that the Agent adds PEP 735 Dependency Group parsing to the packaging
library — DependencyGroup, DependencyGroupResolver, circular detection,
validation, and Requirement integration.
"""

import os
import re
import ast
import subprocess
import pytest


class TestPythonPackaging:
    REPO_DIR = "/workspace/packaging"

    # ────────────────── helpers ──────────────────

    def _read(self, rel_path):
        fpath = os.path.join(self.REPO_DIR, rel_path)
        with open(fpath, "r") as f:
            return f.read()

    def _exists(self, rel_path):
        return os.path.isfile(os.path.join(self.REPO_DIR, rel_path))

    def _parse(self, rel_path):
        fpath = os.path.join(self.REPO_DIR, rel_path)
        with open(fpath, "r") as f:
            return ast.parse(f.read())

    # === File Path Checks ===

    def test_dependency_groups_module_exists(self):
        """packaging/dependency_groups.py must exist"""
        assert self._exists("packaging/dependency_groups.py")

    def test_test_file_exists(self):
        """tests/test_dependency_groups.py must exist"""
        assert self._exists("tests/test_dependency_groups.py")

    def test_requirements_module_exists(self):
        """packaging/requirements.py must exist"""
        assert self._exists("packaging/requirements.py")

    # === Semantic Checks — DependencyGroup Class ===

    def test_dependency_group_class(self):
        """DependencyGroup class must be defined"""
        tree = self._parse("packaging/dependency_groups.py")
        classes = [n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
        assert "DependencyGroup" in classes, "DependencyGroup class not found"

    def test_dependency_group_name_property(self):
        """DependencyGroup must have name attribute"""
        src = self._read("packaging/dependency_groups.py")
        assert "name" in src, "DependencyGroup missing name attribute"

    def test_dependency_group_requirements_property(self):
        """DependencyGroup must have requirements attribute"""
        src = self._read("packaging/dependency_groups.py")
        assert "requirements" in src, "DependencyGroup missing requirements attribute"

    def test_dependency_group_include_groups_property(self):
        """DependencyGroup must have include_groups attribute"""
        src = self._read("packaging/dependency_groups.py")
        assert "include_groups" in src or "include-group" in src, (
            "DependencyGroup missing include_groups attribute"
        )

    # === Semantic Checks — DependencyGroupResolver Class ===

    def test_resolver_class(self):
        """DependencyGroupResolver class must be defined"""
        tree = self._parse("packaging/dependency_groups.py")
        classes = [n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
        assert "DependencyGroupResolver" in classes, (
            "DependencyGroupResolver class not found"
        )

    def test_resolver_resolve_method(self):
        """DependencyGroupResolver must have resolve() method"""
        src = self._read("packaging/dependency_groups.py")
        assert re.search(r'def\s+resolve\s*\(\s*self', src), (
            "resolve() method not found"
        )

    def test_resolver_resolve_all_method(self):
        """DependencyGroupResolver must have resolve_all() method"""
        src = self._read("packaging/dependency_groups.py")
        assert re.search(r'def\s+resolve_all\s*\(\s*self', src), (
            "resolve_all() method not found"
        )

    def test_resolver_validate_method(self):
        """DependencyGroupResolver must have validate() method"""
        src = self._read("packaging/dependency_groups.py")
        assert re.search(r'def\s+validate\s*\(\s*self', src), (
            "validate() method not found"
        )

    # === Semantic Checks — Exception Classes ===

    def test_invalid_dependency_group_exception(self):
        """InvalidDependencyGroup exception must be defined"""
        src = self._read("packaging/dependency_groups.py")
        assert re.search(r'class\s+InvalidDependencyGroup\b', src), (
            "InvalidDependencyGroup exception not found"
        )

    def test_undefined_dependency_group_exception(self):
        """UndefinedDependencyGroup exception must be defined"""
        src = self._read("packaging/dependency_groups.py")
        assert re.search(r'class\s+UndefinedDependencyGroup\b', src), (
            "UndefinedDependencyGroup exception not found"
        )

    def test_circular_dependency_group_exception(self):
        """CircularDependencyGroup exception must be defined"""
        src = self._read("packaging/dependency_groups.py")
        assert re.search(r'class\s+CircularDependencyGroup\b', src), (
            "CircularDependencyGroup exception not found"
        )

    def test_circular_has_cycle_attribute(self):
        """CircularDependencyGroup must have cycle attribute"""
        src = self._read("packaging/dependency_groups.py")
        assert "cycle" in src, (
            "CircularDependencyGroup missing cycle attribute"
        )

    # === Semantic Checks — Group Name Validation ===

    def test_group_name_regex_validation(self):
        """Group name must be validated with regex"""
        src = self._read("packaging/dependency_groups.py")
        # Should have a regex for group name validation
        assert re.search(r'\[a-z0-9\]', src) or "group_name" in src.lower(), (
            "Group name regex validation not found"
        )

    # === Semantic Checks — Requirement Integration ===

    def test_from_dependency_group_item_classmethod(self):
        """Requirement must have from_dependency_group_item class method"""
        src = self._read("packaging/requirements.py")
        assert "from_dependency_group_item" in src, (
            "from_dependency_group_item not found in requirements.py"
        )

    # === Semantic Checks — include-group handling ===

    def test_include_group_key(self):
        """Must handle include-group dict entries"""
        src = self._read("packaging/dependency_groups.py")
        assert "include-group" in src, (
            "include-group key handling not found"
        )

    # === Functional Checks ===

    def test_module_importable(self):
        """All classes must be importable"""
        result = subprocess.run(
            ["python", "-c",
             "from packaging.dependency_groups import ("
             "DependencyGroup, DependencyGroupResolver, "
             "InvalidDependencyGroup, UndefinedDependencyGroup, "
             "CircularDependencyGroup); print('OK')"],
            capture_output=True, text=True, cwd=self.REPO_DIR, timeout=30,
        )
        assert "OK" in result.stdout, (
            f"Import failed:\n{result.stdout}\n{result.stderr}"
        )

    def test_resolve_simple_group(self):
        """Resolver must resolve a simple group correctly"""
        result = subprocess.run(
            ["python", "-c",
             "from packaging.dependency_groups import DependencyGroupResolver; "
             "groups = {'test': ['pytest>=7.0', 'coverage[toml]']}; "
             "r = DependencyGroupResolver(groups); "
             "reqs = r.resolve('test'); "
             "assert len(reqs) == 2, f'Expected 2 requirements, got {len(reqs)}'; "
             "assert str(reqs[0]).startswith('pytest'), f'Got {reqs[0]}'; "
             "print('OK')"],
            capture_output=True, text=True, cwd=self.REPO_DIR, timeout=30,
        )
        assert "OK" in result.stdout, (
            f"Resolve test failed:\n{result.stdout}\n{result.stderr}"
        )

    def test_resolve_with_include_group(self):
        """Resolver must flatten include-group references"""
        result = subprocess.run(
            ["python", "-c",
             "from packaging.dependency_groups import DependencyGroupResolver; "
             "groups = {"
             "  'test': ['pytest>=7.0'], "
             "  'dev': [{'include-group': 'test'}, 'pre-commit']"
             "}; "
             "r = DependencyGroupResolver(groups); "
             "reqs = r.resolve('dev'); "
             "names = [str(rq).split('>')[0].split('[')[0] for rq in reqs]; "
             "assert 'pytest' in names, f'pytest not in {names}'; "
             "assert 'pre-commit' in names, f'pre-commit not in {names}'; "
             "print('OK')"],
            capture_output=True, text=True, cwd=self.REPO_DIR, timeout=30,
        )
        assert "OK" in result.stdout, (
            f"Include-group test failed:\n{result.stdout}\n{result.stderr}"
        )

    def test_circular_detection(self):
        """Resolver must detect circular include-group references"""
        result = subprocess.run(
            ["python", "-c",
             "from packaging.dependency_groups import ("
             "DependencyGroupResolver, CircularDependencyGroup); "
             "groups = {"
             "  'a': [{'include-group': 'b'}], "
             "  'b': [{'include-group': 'a'}]"
             "}; "
             "r = DependencyGroupResolver(groups); "
             "try:\n"
             "    r.resolve('a')\n"
             "    print('NO_ERROR')\n"
             "except CircularDependencyGroup:\n"
             "    print('OK')"],
            capture_output=True, text=True, cwd=self.REPO_DIR, timeout=30,
        )
        assert "OK" in result.stdout, (
            f"Circular detection failed:\n{result.stdout}\n{result.stderr}"
        )

    def test_unit_tests_pass(self):
        """tests/test_dependency_groups.py must pass"""
        result = subprocess.run(
            ["python", "-m", "pytest",
             "tests/test_dependency_groups.py",
             "-v", "--tb=short"],
            capture_output=True, text=True, cwd=self.REPO_DIR, timeout=120,
        )
        assert result.returncode == 0, (
            f"Tests failed:\n{result.stdout}\n{result.stderr}"
        )
