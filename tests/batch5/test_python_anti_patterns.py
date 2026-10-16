"""
Test skill: python-anti-patterns
Verify that the Agent correctly refactors boltons iterutils and cacheutils
to eliminate anti-patterns while preserving public API behavior.
"""

import os
import re
import ast
import sys
import subprocess
import pytest


class TestPythonAntiPatterns:
    REPO_DIR = "/workspace/boltons"

    ITERUTILS = "boltons/iterutils.py"
    CACHEUTILS = "boltons/cacheutils.py"
    TEST_ITERUTILS = "tests/test_iterutils.py"
    TEST_CACHEUTILS = "tests/test_cacheutils.py"

    def _read_file(self, rel_path):
        filepath = os.path.join(self.REPO_DIR, rel_path)
        with open(filepath) as f:
            return f.read()

    # === File Path Checks ===

    def test_iterutils_exists(self):
        """Verify boltons/iterutils.py exists"""
        filepath = os.path.join(self.REPO_DIR, self.ITERUTILS)
        assert os.path.exists(filepath), f"iterutils.py not found at {filepath}"

    def test_cacheutils_exists(self):
        """Verify boltons/cacheutils.py exists"""
        filepath = os.path.join(self.REPO_DIR, self.CACHEUTILS)
        assert os.path.exists(filepath), f"cacheutils.py not found at {filepath}"

    def test_test_files_exist(self):
        """Verify test files for both modules exist"""
        for path in [self.TEST_ITERUTILS, self.TEST_CACHEUTILS]:
            filepath = os.path.join(self.REPO_DIR, path)
            assert os.path.exists(filepath), f"Test file not found: {filepath}"

    # === Semantic Checks ===

    def test_no_bare_except_in_iterutils(self):
        """Verify iterutils.py has no bare except: clauses"""
        content = self._read_file(self.ITERUTILS)
        tree = ast.parse(content)
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler):
                # Bare except has type=None
                if node.type is None:
                    pytest.fail(
                        f"Bare 'except:' found in iterutils.py at line {node.lineno}"
                    )

    def test_no_bare_except_in_cacheutils(self):
        """Verify cacheutils.py has no bare except: clauses"""
        content = self._read_file(self.CACHEUTILS)
        tree = ast.parse(content)
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler):
                if node.type is None:
                    pytest.fail(
                        f"Bare 'except:' found in cacheutils.py at line {node.lineno}"
                    )

    def test_no_broad_exception_handler_in_iterutils(self):
        """Verify iterutils.py does not catch broad Exception class"""
        content = self._read_file(self.ITERUTILS)
        tree = ast.parse(content)
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler) and node.type is not None:
                if isinstance(node.type, ast.Name) and node.type.id == "Exception":
                    pytest.fail(
                        f"Broad 'except Exception' found in iterutils.py at line {node.lineno}"
                    )

    def test_no_mutable_default_arguments_in_iterutils(self):
        """Verify iterutils.py has no mutable default arguments in function signatures"""
        content = self._read_file(self.ITERUTILS)
        tree = ast.parse(content)
        mutable_types = (ast.List, ast.Dict, ast.Set)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for default in node.args.defaults + node.args.kw_defaults:
                    if default is not None and isinstance(default, mutable_types):
                        pytest.fail(
                            f"Mutable default argument in '{node.name}' at line {node.lineno}"
                        )

    def test_no_mutable_default_arguments_in_cacheutils(self):
        """Verify cacheutils.py has no mutable default arguments"""
        content = self._read_file(self.CACHEUTILS)
        tree = ast.parse(content)
        mutable_types = (ast.List, ast.Dict, ast.Set)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for default in node.args.defaults + node.args.kw_defaults:
                    if default is not None and isinstance(default, mutable_types):
                        pytest.fail(
                            f"Mutable default argument in '{node.name}' at line {node.lineno}"
                        )

    def test_cacheutils_except_handlers_are_specific(self):
        """Verify cacheutils.py exception handlers catch specific exception types"""
        content = self._read_file(self.CACHEUTILS)
        tree = ast.parse(content)
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler):
                if node.type is None:
                    pytest.fail(
                        f"Bare except in cacheutils.py at line {node.lineno}"
                    )
                if isinstance(node.type, ast.Name) and node.type.id == "Exception":
                    pytest.fail(
                        f"Broad 'except Exception' in cacheutils.py at line {node.lineno}"
                    )

    # === Functional Checks ===

    def test_chunked_works_with_sequences(self):
        """Verify chunked still works with standard sequences"""
        sys.path.insert(0, self.REPO_DIR)
        from boltons.iterutils import chunked
        result = chunked([1, 2, 3, 4, 5], 2)
        assert result == [[1, 2], [3, 4], [5]], \
            f"chunked([1,2,3,4,5], 2) returned {result}"

    def test_chunked_raises_on_non_iterable(self):
        """Verify chunked(42, 3) raises TypeError instead of returning empty"""
        sys.path.insert(0, self.REPO_DIR)
        from boltons.iterutils import chunked
        with pytest.raises(TypeError):
            chunked(42, 3)

    def test_bucketize_works_on_empty(self):
        """Verify bucketize([]) returns empty dict without error"""
        sys.path.insert(0, self.REPO_DIR)
        from boltons.iterutils import bucketize
        result = bucketize([], key=lambda x: x)
        assert result == {}, f"bucketize([]) should return {{}}, got {result}"

    def test_unique_handles_none_values(self):
        """Verify unique handles None values correctly"""
        sys.path.insert(0, self.REPO_DIR)
        from boltons.iterutils import unique
        result = unique([1, 2, None, 1, None])
        assert result == [1, 2, None], \
            f"unique([1, 2, None, 1, None]) should return [1, 2, None], got {result}"

    def test_lru_cache_eviction(self):
        """Verify LRU cache evicts correctly at capacity"""
        sys.path.insert(0, self.REPO_DIR)
        from boltons.cacheutils import LRU
        cache = LRU(max_size=2)
        cache["a"] = 1
        cache["b"] = 2
        cache["c"] = 3
        assert len(cache) == 2, \
            f"LRU(max_size=2) should have 2 items after 3 inserts, got {len(cache)}"
        assert "a" not in cache, "LRU should have evicted 'a' (least recently used)"
        assert "b" in cache and "c" in cache, "LRU should keep 'b' and 'c'"

    def test_existing_tests_pass(self):
        """Verify all existing tests pass after refactoring"""
        result = subprocess.run(
            ["python", "-m", "pytest",
             "tests/test_iterutils.py", "tests/test_cacheutils.py",
             "-v", "--tb=short"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, \
            f"Existing tests failed:\n{result.stdout[-500:]}\n{result.stderr[-500:]}"
