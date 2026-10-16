"""
Test skill: python-anti-patterns
Verify that the Agent correctly adds a ResourcePool utility module to boltons
with thread-safe resource pooling, health checks, idle eviction, and statistics.
"""

import os
import subprocess
import sys
import ast
import inspect
import threading
import time
import pytest


class TestPythonAntiPatterns:
    REPO_DIR = "/workspace/boltons"

    # === File Path Checks ===

    def test_poolutils_module_exists(self):
        """Verify that poolutils.py exists in the boltons package"""
        filepath = os.path.join(self.REPO_DIR, "boltons/poolutils.py")
        assert os.path.exists(filepath), f"poolutils.py not found at {filepath}"

    def test_poolutils_test_exists(self):
        """Verify that test_poolutils.py exists"""
        filepath = os.path.join(self.REPO_DIR, "tests/test_poolutils.py")
        assert os.path.exists(filepath), f"test_poolutils.py not found at {filepath}"

    def test_poolutils_valid_python(self):
        """Verify that poolutils.py is valid Python syntax"""
        filepath = os.path.join(self.REPO_DIR, "boltons/poolutils.py")
        with open(filepath) as f:
            content = f.read()
        try:
            ast.parse(content)
        except SyntaxError as e:
            pytest.fail(f"poolutils.py has syntax errors: {e}")

    # === Semantic Checks ===

    def test_resource_pool_class_exists(self):
        """Verify ResourcePool class is defined in poolutils"""
        sys.path.insert(0, self.REPO_DIR)
        try:
            from boltons.poolutils import ResourcePool
            assert inspect.isclass(ResourcePool), "ResourcePool must be a class"
        except ImportError as e:
            pytest.fail(f"Cannot import ResourcePool: {e}")
        finally:
            sys.path.pop(0)

    def test_pool_exhausted_error_exists(self):
        """Verify PoolExhaustedError is defined"""
        sys.path.insert(0, self.REPO_DIR)
        try:
            from boltons.poolutils import PoolExhaustedError
            assert issubclass(PoolExhaustedError, Exception), (
                "PoolExhaustedError must be an Exception subclass"
            )
        except ImportError as e:
            pytest.fail(f"Cannot import PoolExhaustedError: {e}")
        finally:
            sys.path.pop(0)

    def test_pool_closed_error_exists(self):
        """Verify PoolClosedError is defined"""
        sys.path.insert(0, self.REPO_DIR)
        try:
            from boltons.poolutils import PoolClosedError
            assert issubclass(PoolClosedError, Exception), (
                "PoolClosedError must be an Exception subclass"
            )
        except ImportError as e:
            pytest.fail(f"Cannot import PoolClosedError: {e}")
        finally:
            sys.path.pop(0)

    def test_resource_pool_uses_threading(self):
        """Verify ResourcePool uses threading primitives for thread safety"""
        filepath = os.path.join(self.REPO_DIR, "boltons/poolutils.py")
        with open(filepath) as f:
            content = f.read()

        has_threading = (
            "threading.Lock" in content
            or "threading.Condition" in content
            or "threading.RLock" in content
            or "from threading import" in content
        )
        assert has_threading, (
            "poolutils.py does not use threading primitives (Lock/Condition). "
            "ResourcePool must be thread-safe."
        )

    def test_no_external_dependencies(self):
        """Verify poolutils uses only standard library (no external dependencies)"""
        filepath = os.path.join(self.REPO_DIR, "boltons/poolutils.py")
        with open(filepath) as f:
            content = f.read()

        tree = ast.parse(content)
        stdlib_modules = {
            "threading", "time", "queue", "collections", "functools",
            "contextlib", "weakref", "logging", "dataclasses", "typing",
            "abc", "os", "sys", "enum", "warnings", "heapq",
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    mod = alias.name.split('.')[0]
                    assert mod in stdlib_modules or mod == "boltons", (
                        f"poolutils.py imports external dependency '{mod}'. "
                        "Only standard library modules are allowed."
                    )
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    mod = node.module.split('.')[0]
                    assert mod in stdlib_modules or mod == "boltons", (
                        f"poolutils.py imports from external dependency '{mod}'"
                    )

    # === Functional Checks ===

    def test_pool_acquire_and_release(self):
        """Verify basic acquire/release semantics"""
        sys.path.insert(0, self.REPO_DIR)
        try:
            from boltons.poolutils import ResourcePool
            counter = [0]

            def factory():
                counter[0] += 1
                return f"resource-{counter[0]}"

            pool = ResourcePool(factory, max_size=3)
            r1 = pool.acquire()
            assert r1 is not None, "acquire() should return a resource"
            assert isinstance(r1, str), f"Expected string resource, got {type(r1)}"
            pool.release(r1)
            pool.close()
        except ImportError as e:
            pytest.skip(f"Cannot import ResourcePool: {e}")
        finally:
            sys.path.pop(0)

    def test_pool_context_manager(self):
        """Verify acquire works as context manager"""
        sys.path.insert(0, self.REPO_DIR)
        try:
            from boltons.poolutils import ResourcePool
            pool = ResourcePool(lambda: "resource", max_size=3)
            with pool.acquire() as r:
                assert r is not None, "Context manager should yield a resource"
            pool.close()
        except (ImportError, TypeError) as e:
            pytest.skip(f"Cannot test context manager: {e}")
        finally:
            sys.path.pop(0)

    def test_pool_exhausted_raises_error(self):
        """Verify PoolExhaustedError is raised when pool is exhausted and timeout elapses"""
        sys.path.insert(0, self.REPO_DIR)
        try:
            from boltons.poolutils import ResourcePool, PoolExhaustedError
            pool = ResourcePool(lambda: "resource", max_size=1)
            r1 = pool.acquire()

            with pytest.raises(PoolExhaustedError):
                pool.acquire(timeout=0.5)

            pool.release(r1)
            pool.close()
        except ImportError as e:
            pytest.skip(f"Cannot import: {e}")
        finally:
            sys.path.pop(0)

    def test_pool_closed_raises_error(self):
        """Verify PoolClosedError is raised after pool.close()"""
        sys.path.insert(0, self.REPO_DIR)
        try:
            from boltons.poolutils import ResourcePool, PoolClosedError
            pool = ResourcePool(lambda: "resource", max_size=3)
            pool.close()

            with pytest.raises(PoolClosedError):
                pool.acquire()
        except ImportError as e:
            pytest.skip(f"Cannot import: {e}")
        finally:
            sys.path.pop(0)

    def test_pool_health_check(self):
        """Verify health check discards unhealthy resources"""
        sys.path.insert(0, self.REPO_DIR)
        try:
            from boltons.poolutils import ResourcePool
            call_count = [0]

            def factory():
                call_count[0] += 1
                return {"id": call_count[0], "healthy": call_count[0] > 1}

            def health_check(resource):
                return resource["healthy"]

            pool = ResourcePool(factory, max_size=3, health_check=health_check)
            r = pool.acquire()
            # First resource (id=1) is unhealthy, should be discarded
            # Second resource (id=2) is healthy
            assert r["healthy"] is True, (
                f"Expected healthy resource, got unhealthy one: {r}"
            )
            assert call_count[0] >= 2, (
                f"Expected factory to be called at least twice (first unhealthy, then healthy), "
                f"called {call_count[0]} times"
            )
            pool.release(r)
            pool.close()
        except ImportError as e:
            pytest.skip(f"Cannot import: {e}")
        finally:
            sys.path.pop(0)

    def test_pool_stats(self):
        """Verify pool.stats() returns correct statistics"""
        sys.path.insert(0, self.REPO_DIR)
        try:
            from boltons.poolutils import ResourcePool
            pool = ResourcePool(lambda: "resource", max_size=5)

            r1 = pool.acquire()
            r2 = pool.acquire()
            pool.release(r1)

            stats = pool.stats()
            assert isinstance(stats, dict), f"Expected dict, got {type(stats)}"
            assert "total" in stats, "stats missing 'total' key"
            assert "idle" in stats, "stats missing 'idle' key"
            assert "in_use" in stats, "stats missing 'in_use' key"
            assert stats["in_use"] >= 1, f"Expected at least 1 in_use, got {stats['in_use']}"

            pool.release(r2)
            pool.close()
        except ImportError as e:
            pytest.skip(f"Cannot import: {e}")
        finally:
            sys.path.pop(0)

    def test_pool_tests_pass(self):
        """Verify that the test suite in test_poolutils.py passes"""
        result = subprocess.run(
            ["python", "-m", "pytest", "tests/test_poolutils.py", "-v", "--tb=short"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=120
        )
        assert result.returncode == 0, (
            f"test_poolutils.py failed:\n{result.stdout[:3000]}\n{result.stderr[:1000]}"
        )
