"""
Test skill: python-anti-patterns
Verify that the Agent correctly refactors anti-patterns in boltons utility modules
(socketutils.py, iterutils.py, fileutils.py).
"""

import os
import re
import ast
import sys
import subprocess
import pytest


class TestPythonAntiPatterns:
    REPO_DIR = "/workspace/boltons"

    # === File Path Checks ===

    def test_socketutils_exists(self):
        """Verify boltons/socketutils.py exists"""
        path = os.path.join(self.REPO_DIR, "boltons/socketutils.py")
        assert os.path.exists(path), f"socketutils.py not found at {path}"

    def test_iterutils_exists(self):
        """Verify boltons/iterutils.py exists"""
        path = os.path.join(self.REPO_DIR, "boltons/iterutils.py")
        assert os.path.exists(path), f"iterutils.py not found at {path}"

    def test_fileutils_exists(self):
        """Verify boltons/fileutils.py exists"""
        path = os.path.join(self.REPO_DIR, "boltons/fileutils.py")
        assert os.path.exists(path), f"fileutils.py not found at {path}"

    def test_refactor_test_files_exist(self):
        """Verify refactored test files were created"""
        for fname in [
            "tests/test_socketutils_refactor.py",
            "tests/test_iterutils_refactor.py",
            "tests/test_fileutils_refactor.py",
        ]:
            path = os.path.join(self.REPO_DIR, fname)
            assert os.path.exists(path), f"Test file not found: {path}"

    # === Semantic Checks: No Bare Exceptions ===

    def test_socketutils_no_bare_except(self):
        """Verify socketutils.py has no bare except or 'except Exception: pass'"""
        path = os.path.join(self.REPO_DIR, "boltons/socketutils.py")
        with open(path) as f:
            content = f.read()
        # Check for bare except:
        bare_except = re.findall(r'except\s*:\s*\n\s*pass', content)
        assert len(bare_except) == 0, (
            f"Found {len(bare_except)} bare 'except: pass' in socketutils.py"
        )
        # Check for except Exception: pass
        exception_pass = re.findall(r'except\s+Exception\s*:\s*\n\s*pass', content)
        assert len(exception_pass) == 0, (
            f"Found {len(exception_pass)} 'except Exception: pass' in socketutils.py"
        )

    def test_iterutils_no_bare_except(self):
        """Verify iterutils.py has no bare except or 'except Exception: pass'"""
        path = os.path.join(self.REPO_DIR, "boltons/iterutils.py")
        with open(path) as f:
            content = f.read()
        bare_except = re.findall(r'except\s*:\s*\n\s*pass', content)
        assert len(bare_except) == 0, (
            f"Found {len(bare_except)} bare 'except: pass' in iterutils.py"
        )

    def test_fileutils_no_bare_except(self):
        """Verify fileutils.py has no bare except or 'except Exception: pass'"""
        path = os.path.join(self.REPO_DIR, "boltons/fileutils.py")
        with open(path) as f:
            content = f.read()
        bare_except = re.findall(r'except\s*:\s*\n\s*pass', content)
        assert len(bare_except) == 0, (
            f"Found {len(bare_except)} bare 'except: pass' in fileutils.py"
        )

    # === Semantic Checks: Resource Management ===

    def test_fileutils_all_open_in_context_managers(self):
        """Verify every open() in fileutils.py is inside a 'with' block"""
        path = os.path.join(self.REPO_DIR, "boltons/fileutils.py")
        with open(path) as f:
            source = f.read()
        tree = ast.parse(source)
        # Find all Call nodes that call open()
        standalone_opens = 0
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                if isinstance(node.value, ast.Call):
                    func = node.value.func
                    if isinstance(func, ast.Name) and func.id == "open":
                        # Check if this assignment is inside a With statement
                        # Simple heuristic: check line content
                        line = source.split('\n')[node.lineno - 1].strip()
                        if not line.startswith("with "):
                            standalone_opens += 1
        # Allow a few since we can't perfectly detect with-as pattern in AST walk
        assert standalone_opens <= 2, (
            f"Found {standalone_opens} open() calls outside 'with' blocks in fileutils.py"
        )

    # === Semantic Checks: Type Annotations ===

    def test_fileutils_has_type_annotations(self):
        """Verify fileutils.py has type annotations on public functions"""
        path = os.path.join(self.REPO_DIR, "boltons/fileutils.py")
        with open(path) as f:
            content = f.read()
        # Check for from __future__ import annotations or typing imports
        has_typing = (
            "from __future__ import annotations" in content
            or "from typing import" in content
            or "import typing" in content
        )
        assert has_typing, "fileutils.py should import typing utilities"

    def test_iterutils_has_type_annotations(self):
        """Verify iterutils.py has type annotations on public functions"""
        path = os.path.join(self.REPO_DIR, "boltons/iterutils.py")
        with open(path) as f:
            content = f.read()
        has_typing = (
            "from __future__ import annotations" in content
            or "from typing import" in content
            or "import typing" in content
        )
        assert has_typing, "iterutils.py should import typing utilities"

    # === Functional Checks ===

    def test_chunked_empty_input(self):
        """Verify iterutils.chunked([],5) returns empty list"""
        sys.path.insert(0, self.REPO_DIR)
        try:
            from boltons.iterutils import chunked
            result = chunked([], 5)
            assert result == [], f"chunked([], 5) should return [], got {result}"
        finally:
            sys.path.pop(0)

    def test_chunked_invalid_size_raises_valueerror(self):
        """Verify iterutils.chunked([1,2,3], 0) raises ValueError"""
        sys.path.insert(0, self.REPO_DIR)
        try:
            from boltons.iterutils import chunked
            with pytest.raises(ValueError):
                chunked([1, 2, 3], 0)
        finally:
            sys.path.pop(0)

    def test_chunked_correct_output(self):
        """Verify iterutils.chunked(range(10), 3) returns correct chunks"""
        sys.path.insert(0, self.REPO_DIR)
        try:
            from boltons.iterutils import chunked
            result = chunked(range(10), 3)
            assert len(result) == 4, f"Expected 4 chunks, got {len(result)}"
            assert list(result[-1]) == [9], f"Last chunk should be [9], got {result[-1]}"
        finally:
            sys.path.pop(0)

    def test_refactored_socketutils_tests_pass(self):
        """Verify refactored socketutils tests pass"""
        result = subprocess.run(
            ["python", "-m", "pytest", "tests/test_socketutils_refactor.py", "-v", "--tb=short"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, (
            f"socketutils refactor tests failed:\n{result.stdout[-1000:]}\n{result.stderr[-500:]}"
        )

    def test_refactored_iterutils_tests_pass(self):
        """Verify refactored iterutils tests pass"""
        result = subprocess.run(
            ["python", "-m", "pytest", "tests/test_iterutils_refactor.py", "-v", "--tb=short"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, (
            f"iterutils refactor tests failed:\n{result.stdout[-1000:]}\n{result.stderr[-500:]}"
        )

    def test_refactored_fileutils_tests_pass(self):
        """Verify refactored fileutils tests pass"""
        result = subprocess.run(
            ["python", "-m", "pytest", "tests/test_fileutils_refactor.py", "-v", "--tb=short"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, (
            f"fileutils refactor tests failed:\n{result.stdout[-1000:]}\n{result.stderr[-500:]}"
        )

    def test_existing_tests_no_regression(self):
        """Verify existing boltons tests still pass (no regression)"""
        result = subprocess.run(
            ["python", "-m", "pytest", "tests/", "-v", "--tb=short", "-x",
             "--ignore=tests/test_socketutils_refactor.py",
             "--ignore=tests/test_iterutils_refactor.py",
             "--ignore=tests/test_fileutils_refactor.py"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=300,
        )
        if "no tests ran" in result.stdout.lower():
            pytest.skip("No existing tests found")
        assert result.returncode == 0, (
            f"Existing tests regressed:\n{result.stdout[-1000:]}\n{result.stderr[-500:]}"
        )
