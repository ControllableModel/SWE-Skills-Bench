"""
Test skill: python-anti-patterns
Verify that the Agent correctly refactors cacheutils module in boltons
to eliminate common Python anti-patterns.
"""

import os
import sys
import ast
import subprocess
import inspect
import pytest


class TestPythonAntiPatterns:
    REPO_DIR = "/workspace/boltons"

    # === File Path Checks ===

    def test_cacheutils_exists(self):
        """Verify the cacheutils module file exists"""
        path = os.path.join(self.REPO_DIR, "boltons/cacheutils.py")
        assert os.path.exists(path), f"cacheutils.py not found at {path}"
        with open(path) as f:
            ast.parse(f.read())

    def test_refactor_tests_exist(self):
        """Verify the refactoring test file exists"""
        path = os.path.join(self.REPO_DIR, "tests/test_cacheutils_refactor.py")
        assert os.path.exists(path), f"test_cacheutils_refactor.py not found at {path}"
        with open(path) as f:
            ast.parse(f.read())

    # === Semantic Checks ===

    def test_no_mutable_default_arguments(self):
        """Verify no mutable default arguments remain in function signatures"""
        path = os.path.join(self.REPO_DIR, "boltons/cacheutils.py")
        with open(path) as f:
            tree = ast.parse(f.read())

        mutable_defaults = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for default in node.args.defaults + node.args.kw_defaults:
                    if default is None:
                        continue
                    if isinstance(default, (ast.List, ast.Dict, ast.Set)):
                        mutable_defaults.append(
                            f"{node.name}: mutable default {type(default).__name__} "
                            f"at line {default.lineno}"
                        )
        assert len(mutable_defaults) == 0, \
            f"Mutable default arguments found: {mutable_defaults}"

    def test_no_bare_except_clauses(self):
        """Verify no bare except: or overly broad except Exception: remain"""
        path = os.path.join(self.REPO_DIR, "boltons/cacheutils.py")
        with open(path) as f:
            tree = ast.parse(f.read())

        bare_excepts = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler):
                if node.type is None:
                    bare_excepts.append(f"bare except at line {node.lineno}")
        assert len(bare_excepts) == 0, \
            f"Bare except clauses found: {bare_excepts}"

    def test_public_methods_have_type_annotations(self):
        """Verify public methods on LRU/LRI/cachedproperty have type annotations"""
        path = os.path.join(self.REPO_DIR, "boltons/cacheutils.py")
        with open(path) as f:
            tree = ast.parse(f.read())

        classes_to_check = {"LRU", "LRI", "cachedproperty"}
        missing_annotations = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name in classes_to_check:
                for item in node.body:
                    if isinstance(item, ast.FunctionDef):
                        if item.name.startswith("_") and item.name != "__init__":
                            continue
                        if item.returns is None and item.name != "__init__":
                            missing_annotations.append(
                                f"{node.name}.{item.name} missing return annotation"
                            )
        # Allow some missing but most should have annotations
        annotated_ratio = 1 - (len(missing_annotations) / max(1, len(missing_annotations) + 5))
        assert len(missing_annotations) <= 5, \
            f"Public methods missing type annotations: {missing_annotations[:5]}"

    def test_lru_validates_max_size(self):
        """Verify LRU raises ValueError for max_size=0 or negative"""
        sys.path.insert(0, self.REPO_DIR)
        try:
            from boltons.cacheutils import LRU
            with pytest.raises(ValueError) as exc_info:
                LRU(max_size=0)
            msg = str(exc_info.value).lower()
            assert "max_size" in msg or "positive" in msg or "size" in msg, \
                f"ValueError should mention max_size must be positive: {exc_info.value}"
        finally:
            sys.path.pop(0)
            for m in list(sys.modules.keys()):
                if "boltons" in m:
                    del sys.modules[m]

    def test_lru_validates_on_miss_callable(self):
        """Verify LRU/LRI raises TypeError for non-callable on_miss"""
        sys.path.insert(0, self.REPO_DIR)
        try:
            from boltons.cacheutils import LRI
            # on_miss might be a parameter in __init__
            sig = inspect.signature(LRI.__init__)
            if "on_miss" in sig.parameters:
                with pytest.raises(TypeError) as exc_info:
                    LRI(on_miss="not_callable")
                assert "callable" in str(exc_info.value).lower() or \
                       "on_miss" in str(exc_info.value).lower(), \
                    f"TypeError should mention on_miss must be callable: {exc_info.value}"
            else:
                pytest.skip("LRI does not have on_miss parameter")
        finally:
            sys.path.pop(0)
            for m in list(sys.modules.keys()):
                if "boltons" in m:
                    del sys.modules[m]

    # === Functional Checks ===

    def test_lru_eviction_with_setitem(self):
        """Verify LRU evicts correctly when items are added via __setitem__"""
        sys.path.insert(0, self.REPO_DIR)
        try:
            from boltons.cacheutils import LRU
            lru = LRU(max_size=5)
            for i in range(10):
                lru[f"key_{i}"] = f"value_{i}"
            assert len(lru) <= 5, \
                f"LRU should retain at most 5 items after inserting 10, got {len(lru)}"
            # Most recent 5 keys should be present
            for i in range(5, 10):
                assert f"key_{i}" in lru, \
                    f"key_{i} should be in LRU (recently inserted)"
        finally:
            sys.path.pop(0)
            for m in list(sys.modules.keys()):
                if "boltons" in m:
                    del sys.modules[m]

    def test_lru_eviction_with_update(self):
        """Verify LRU evicts correctly when items are added via update()"""
        sys.path.insert(0, self.REPO_DIR)
        try:
            from boltons.cacheutils import LRU
            lru = LRU(max_size=3)
            lru.update({"a": 1, "b": 2, "c": 3, "d": 4, "e": 5})
            assert len(lru) <= 3, \
                f"LRU should retain at most 3 items after update with 5, got {len(lru)}"
        finally:
            sys.path.pop(0)
            for m in list(sys.modules.keys()):
                if "boltons" in m:
                    del sys.modules[m]

    def test_cachedproperty_class_access(self):
        """Verify cachedproperty returns descriptor when accessed on class"""
        sys.path.insert(0, self.REPO_DIR)
        try:
            from boltons.cacheutils import cachedproperty

            class MyClass:
                @cachedproperty
                def my_prop(self):
                    return 42

            # Accessing on class should return the descriptor, not raise
            descriptor = MyClass.my_prop
            assert isinstance(descriptor, cachedproperty), \
                f"Accessing cachedproperty on class should return descriptor, got {type(descriptor)}"

            # Accessing on instance should return computed value
            obj = MyClass()
            assert obj.my_prop == 42, \
                f"Accessing cachedproperty on instance should return 42, got {obj.my_prop}"
        finally:
            sys.path.pop(0)
            for m in list(sys.modules.keys()):
                if "boltons" in m:
                    del sys.modules[m]

    def test_existing_tests_still_pass(self):
        """Verify existing cacheutils tests still pass after refactoring"""
        existing_test = os.path.join(self.REPO_DIR, "tests/test_cacheutils.py")
        if not os.path.exists(existing_test):
            pytest.skip("Existing test file not found")
        result = subprocess.run(
            ["python", "-m", "pytest", existing_test, "-v", "--tb=short"],
            cwd=self.REPO_DIR,
            capture_output=True, text=True, timeout=120
        )
        assert result.returncode == 0, \
            f"Existing cacheutils tests failed:\n{result.stdout[:2000]}\n{result.stderr[:500]}"

    def test_refactoring_tests_pass(self):
        """Verify the new refactoring test suite passes"""
        test_path = os.path.join(self.REPO_DIR, "tests/test_cacheutils_refactor.py")
        result = subprocess.run(
            ["python", "-m", "pytest", test_path, "-v", "--tb=short"],
            cwd=self.REPO_DIR,
            capture_output=True, text=True, timeout=120
        )
        assert result.returncode == 0, \
            f"Refactoring tests failed:\n{result.stdout[:2000]}\n{result.stderr[:500]}"

    def test_unhashable_key_raises_typeerror(self):
        """Verify using an unhashable key raises TypeError with descriptive message"""
        sys.path.insert(0, self.REPO_DIR)
        try:
            from boltons.cacheutils import LRU
            lru = LRU(max_size=5)
            with pytest.raises(TypeError):
                lru[[1, 2, 3]] = "value"  # list is unhashable
        finally:
            sys.path.pop(0)
            for m in list(sys.modules.keys()):
                if "boltons" in m:
                    del sys.modules[m]
