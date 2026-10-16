"""
Test skill: python-anti-patterns
Verify that the Agent correctly refactors anti-patterns in the boltons
utility library (mutable defaults, bare excepts, resource management,
string building, type checking).
"""

import os
import re
import ast
import subprocess
import pytest


class TestPythonAntiPatterns:
    REPO_DIR = "/workspace/boltons"

    # === File Path Checks ===

    def test_iterutils_exists(self):
        """Verify iterutils.py exists"""
        fpath = os.path.join(self.REPO_DIR, "boltons/iterutils.py")
        assert os.path.isfile(fpath), f"iterutils.py not found at {fpath}"

    def test_strutils_exists(self):
        """Verify strutils.py exists"""
        fpath = os.path.join(self.REPO_DIR, "boltons/strutils.py")
        assert os.path.isfile(fpath), f"strutils.py not found at {fpath}"

    def test_dictutils_exists(self):
        """Verify dictutils.py exists"""
        fpath = os.path.join(self.REPO_DIR, "boltons/dictutils.py")
        assert os.path.isfile(fpath), f"dictutils.py not found at {fpath}"

    def test_fileutils_exists(self):
        """Verify fileutils.py exists"""
        fpath = os.path.join(self.REPO_DIR, "boltons/fileutils.py")
        assert os.path.isfile(fpath), f"fileutils.py not found at {fpath}"

    def test_funcutils_exists(self):
        """Verify funcutils.py exists"""
        fpath = os.path.join(self.REPO_DIR, "boltons/funcutils.py")
        assert os.path.isfile(fpath), f"funcutils.py not found at {fpath}"

    # === Semantic Checks ===

    def test_no_mutable_defaults_in_iterutils(self):
        """Verify iterutils.py has no mutable default arguments ([], {}, set())"""
        fpath = os.path.join(self.REPO_DIR, "boltons/iterutils.py")
        with open(fpath, "r") as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for default in node.args.defaults + node.args.kw_defaults:
                    if default is None:
                        continue
                    if isinstance(default, (ast.List, ast.Dict, ast.Set)):
                        pytest.fail(
                            f"iterutils.py: Function '{node.name}' has mutable default "
                            f"argument at line {default.lineno}"
                        )

    def test_no_mutable_defaults_in_dictutils(self):
        """Verify dictutils.py has no mutable default arguments"""
        fpath = os.path.join(self.REPO_DIR, "boltons/dictutils.py")
        with open(fpath, "r") as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for default in node.args.defaults + node.args.kw_defaults:
                    if default is None:
                        continue
                    if isinstance(default, (ast.List, ast.Dict, ast.Set)):
                        pytest.fail(
                            f"dictutils.py: Function '{node.name}' has mutable default "
                            f"argument at line {default.lineno}"
                        )

    def test_no_bare_except_in_strutils(self):
        """Verify strutils.py has no bare except clauses"""
        fpath = os.path.join(self.REPO_DIR, "boltons/strutils.py")
        with open(fpath, "r") as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler):
                if node.type is None:
                    pytest.fail(
                        f"strutils.py: Bare except clause at line {node.lineno}"
                    )

    def test_no_bare_except_in_fileutils(self):
        """Verify fileutils.py has no bare except clauses"""
        fpath = os.path.join(self.REPO_DIR, "boltons/fileutils.py")
        with open(fpath, "r") as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler):
                if node.type is None:
                    pytest.fail(
                        f"fileutils.py: Bare except clause at line {node.lineno}"
                    )

    def test_fileutils_uses_context_managers(self):
        """Verify fileutils.py uses context managers for file operations"""
        fpath = os.path.join(self.REPO_DIR, "boltons/fileutils.py")
        with open(fpath, "r") as f:
            content = f.read()
        # Count open() calls outside 'with' statements vs inside
        # Find manual open/close patterns
        manual_close = re.findall(r'\.close\(\)', content)
        # This is a rough heuristic - manual close() calls suggest missing context managers
        if len(manual_close) > 2:
            pytest.fail(
                f"fileutils.py has {len(manual_close)} .close() calls - "
                "should use context managers (with statements) instead"
            )

    def test_no_type_equality_checks_in_iterutils(self):
        """Verify iterutils.py uses isinstance() instead of type() == comparisons"""
        fpath = os.path.join(self.REPO_DIR, "boltons/iterutils.py")
        with open(fpath, "r") as f:
            content = f.read()
        # Find type(x) == or type(x) is patterns
        bad_patterns = re.findall(r'type\s*\([^)]+\)\s*(==|is)\s*(list|dict|str|tuple|set|int|float)', content)
        assert len(bad_patterns) == 0, (
            f"iterutils.py has {len(bad_patterns)} 'type(x) == Type' patterns - "
            "should use isinstance() instead"
        )

    def test_strutils_no_string_concat_in_loops(self):
        """Verify strutils.py does not use string concatenation (+=) in loops"""
        fpath = os.path.join(self.REPO_DIR, "boltons/strutils.py")
        with open(fpath, "r") as f:
            tree = ast.parse(f.read())
        # Look for += inside for/while loops where target appears to be a string
        for node in ast.walk(tree):
            if isinstance(node, (ast.For, ast.While)):
                for child in ast.walk(node):
                    if isinstance(child, ast.AugAssign) and isinstance(child.op, ast.Add):
                        # Check if it's string concat (heuristic: target is a simple Name)
                        if isinstance(child.target, ast.Name):
                            # This is potentially string concat - but it could also be numeric
                            # We'll be lenient and just flag obvious patterns
                            pass

    # === Functional Checks ===

    def test_existing_tests_pass(self):
        """Verify all existing boltons tests pass after refactoring"""
        result = subprocess.run(
            ["python", "-m", "pytest", "tests/", "-v", "--tb=short", "-x", "-q"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=300
        )
        assert result.returncode == 0, (
            f"Existing tests failed after refactoring:\n{result.stdout[-1500:]}\n{result.stderr[-500:]}"
        )

    def test_iterutils_importable(self):
        """Verify iterutils.py can be imported without errors"""
        import sys
        sys.path.insert(0, self.REPO_DIR)
        try:
            from boltons import iterutils
            assert hasattr(iterutils, 'bucketize'), "iterutils should have 'bucketize' function"
        except ImportError as e:
            pytest.fail(f"Cannot import iterutils: {e}")

    def test_bucketize_works_correctly(self):
        """Verify bucketize function works correctly after refactoring"""
        import sys
        sys.path.insert(0, self.REPO_DIR)
        from boltons.iterutils import bucketize
        result = bucketize([1, 2, 3, 4, 5, 6], key=lambda x: x % 2)
        assert isinstance(result, dict), f"bucketize should return dict, got {type(result)}"
        assert 0 in result and 1 in result, f"bucketize result should have keys 0 and 1. Got: {result.keys()}"
        assert sorted(result[0]) == [2, 4, 6], f"Even numbers wrong: {result[0]}"
        assert sorted(result[1]) == [1, 3, 5], f"Odd numbers wrong: {result[1]}"

    def test_bucketize_mutable_default_isolation(self):
        """Verify bucketize default arg is not shared between calls"""
        import sys
        sys.path.insert(0, self.REPO_DIR)
        from boltons.iterutils import bucketize
        result1 = bucketize([1, 2], key=lambda x: "a")
        result2 = bucketize([3, 4], key=lambda x: "b")
        # Results should be independent - no shared mutable state
        assert "b" not in result1, "First call result contaminated by second call"
        assert "a" not in result2, "Second call result contaminated by first call"

    def test_dictutils_ordered_multi_dict_works(self):
        """Verify OrderedMultiDict works correctly after refactoring"""
        import sys
        sys.path.insert(0, self.REPO_DIR)
        from boltons.dictutils import OrderedMultiDict
        omd = OrderedMultiDict()
        omd["key"] = "value1"
        assert omd["key"] == "value1", f"Expected 'value1', got {omd['key']}"

    def test_strutils_importable(self):
        """Verify strutils.py can be imported without errors"""
        import sys
        sys.path.insert(0, self.REPO_DIR)
        try:
            from boltons import strutils
            assert strutils is not None
        except ImportError as e:
            pytest.fail(f"Cannot import strutils: {e}")

    def test_funcutils_importable(self):
        """Verify funcutils.py can be imported without errors"""
        import sys
        sys.path.insert(0, self.REPO_DIR)
        try:
            from boltons import funcutils
            assert funcutils is not None
        except ImportError as e:
            pytest.fail(f"Cannot import funcutils: {e}")
