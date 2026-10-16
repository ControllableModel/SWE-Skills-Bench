"""
Test skill: python-anti-patterns
Verify that the Agent refactors boltons modules to fix mutable defaults,
bare exceptions, builtin shadowing, and inefficient patterns.
"""

import os
import subprocess
import ast
import re
import pytest


class TestPythonAntiPatterns:
    REPO_DIR = "/workspace/boltons"

    # === File Path Checks ===

    def test_cacheutils_exists(self):
        """Verify cacheutils.py exists"""
        path = os.path.join(self.REPO_DIR, "boltons/cacheutils.py")
        assert os.path.exists(path), f"cacheutils.py not found at {path}"

    def test_iterutils_exists(self):
        """Verify iterutils.py exists"""
        path = os.path.join(self.REPO_DIR, "boltons/iterutils.py")
        assert os.path.exists(path), f"iterutils.py not found at {path}"

    def test_strutils_exists(self):
        """Verify strutils.py exists"""
        path = os.path.join(self.REPO_DIR, "boltons/strutils.py")
        assert os.path.exists(path), f"strutils.py not found at {path}"

    def test_dictutils_exists(self):
        """Verify dictutils.py exists"""
        path = os.path.join(self.REPO_DIR, "boltons/dictutils.py")
        assert os.path.exists(path), f"dictutils.py not found at {path}"

    # === Semantic Checks ===

    def test_no_mutable_default_arguments(self):
        """Verify no functions use mutable default arguments (list, dict, set)"""
        modules = ["cacheutils.py", "iterutils.py", "strutils.py", "dictutils.py"]
        violations = []
        for mod in modules:
            path = os.path.join(self.REPO_DIR, "boltons", mod)
            with open(path) as f:
                source = f.read()
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    for default in node.args.defaults + node.args.kw_defaults:
                        if default is None:
                            continue
                        if isinstance(default, (ast.List, ast.Dict, ast.Set)):
                            violations.append(f"{mod}:{node.name}:{node.lineno}")
        assert len(violations) == 0, (
            f"Mutable default arguments found: {violations}"
        )

    def test_no_bare_except_clauses(self):
        """Verify no bare except clauses (except: without specifying exception type)"""
        modules = ["cacheutils.py", "iterutils.py", "strutils.py", "dictutils.py"]
        violations = []
        for mod in modules:
            path = os.path.join(self.REPO_DIR, "boltons", mod)
            with open(path) as f:
                source = f.read()
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, ast.ExceptHandler):
                    if node.type is None:
                        violations.append(f"{mod}:{node.lineno}")
        assert len(violations) == 0, (
            f"Bare except clauses found: {violations}"
        )

    def test_no_builtin_shadowing(self):
        """Verify no builtin names are shadowed as function parameters or local variables"""
        import builtins
        builtin_names = set(dir(builtins))
        # Common ones that are typically shadowed
        common_shadows = {"id", "type", "list", "dict", "set", "map", "filter", "input", "format", "hash", "range", "len", "sum", "max", "min", "next", "iter", "open", "all", "any"}
        modules = ["cacheutils.py", "iterutils.py", "strutils.py", "dictutils.py"]
        violations = []
        for mod in modules:
            path = os.path.join(self.REPO_DIR, "boltons", mod)
            with open(path) as f:
                source = f.read()
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    # Check parameter names
                    for arg in node.args.args:
                        if arg.arg in common_shadows:
                            violations.append(f"{mod}:{node.name}:param={arg.arg}:{node.lineno}")
        # Allow a few violations since some may be intentional in utility libraries
        assert len(violations) <= 3, (
            f"Builtin shadowing found ({len(violations)} instances): {violations[:5]}"
        )

    # === Functional Checks ===

    def test_cacheutils_imports(self):
        """Verify cacheutils can be imported"""
        result = subprocess.run(
            ["python", "-c", "from boltons import cacheutils; print('OK')"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, f"Import failed: {result.stderr}"
        assert "OK" in result.stdout

    def test_iterutils_imports(self):
        """Verify iterutils can be imported"""
        result = subprocess.run(
            ["python", "-c", "from boltons import iterutils; print('OK')"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, f"Import failed: {result.stderr}"
        assert "OK" in result.stdout

    def test_strutils_imports(self):
        """Verify strutils can be imported"""
        result = subprocess.run(
            ["python", "-c", "from boltons import strutils; print('OK')"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, f"Import failed: {result.stderr}"
        assert "OK" in result.stdout

    def test_dictutils_imports(self):
        """Verify dictutils can be imported"""
        result = subprocess.run(
            ["python", "-c", "from boltons import dictutils; print('OK')"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, f"Import failed: {result.stderr}"
        assert "OK" in result.stdout

    def test_existing_tests_pass(self):
        """Verify existing boltons tests pass after refactoring"""
        result = subprocess.run(
            ["python", "-m", "pytest", "tests/", "-x", "-q", "--timeout=60"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, (
            f"Tests failed after refactoring:\n{result.stdout[-1000:]}\n{result.stderr[:500]}"
        )

    def test_all_modules_parse_cleanly(self):
        """Verify all modified modules have valid Python syntax"""
        modules = ["cacheutils.py", "iterutils.py", "strutils.py", "dictutils.py"]
        for mod in modules:
            path = os.path.join(self.REPO_DIR, "boltons", mod)
            with open(path) as f:
                source = f.read()
            try:
                ast.parse(source)
            except SyntaxError as e:
                pytest.fail(f"Syntax error in {mod}: {e}")
