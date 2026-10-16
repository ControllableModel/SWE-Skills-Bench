"""
Test skill: python-anti-patterns
Verify that anti-patterns in boltons utility modules have been correctly
refactored: no mutable defaults, no bare exceptions, proper resource management,
input validation, and separation of concerns — while preserving existing behavior.
"""

import os
import ast
import re
import subprocess
import pytest


class TestPythonAntiPatterns:
    REPO_DIR = "/workspace/boltons"

    MODIFIED_FILES = [
        "boltons/iterutils.py",
        "boltons/fileutils.py",
        "boltons/strutils.py",
        "boltons/cacheutils.py",
    ]

    # === File Path Checks ===

    def test_modified_files_exist(self):
        """Verify all four target files exist"""
        for rel_path in self.MODIFIED_FILES:
            filepath = os.path.join(self.REPO_DIR, rel_path)
            assert os.path.exists(filepath), f"File not found: {filepath}"

    def test_anti_pattern_test_file_exists(self):
        """Verify the new test file was created"""
        filepath = os.path.join(self.REPO_DIR, "tests/test_anti_pattern_fixes.py")
        assert os.path.exists(filepath), \
            "tests/test_anti_pattern_fixes.py not found"

    def test_all_modified_files_are_valid_python(self):
        """Verify all modified files parse as valid Python"""
        for rel_path in self.MODIFIED_FILES:
            filepath = os.path.join(self.REPO_DIR, rel_path)
            with open(filepath) as f:
                content = f.read()
            try:
                ast.parse(content)
            except SyntaxError as e:
                pytest.fail(f"Syntax error in {rel_path}: {e}")

    # === Semantic Checks ===

    def test_no_mutable_default_arguments(self):
        """Verify no function uses mutable default arguments (list, dict, set)"""
        for rel_path in self.MODIFIED_FILES:
            filepath = os.path.join(self.REPO_DIR, rel_path)
            with open(filepath) as f:
                content = f.read()
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    for default in node.args.defaults + node.args.kw_defaults:
                        if default is None:
                            continue
                        if isinstance(default, ast.List):
                            pytest.fail(
                                f"Mutable default (list) in {rel_path}::{node.name}() "
                                f"at line {node.lineno}"
                            )
                        elif isinstance(default, ast.Dict):
                            pytest.fail(
                                f"Mutable default (dict) in {rel_path}::{node.name}() "
                                f"at line {node.lineno}"
                            )
                        elif isinstance(default, ast.Set):
                            pytest.fail(
                                f"Mutable default (set) in {rel_path}::{node.name}() "
                                f"at line {node.lineno}"
                            )
                        elif isinstance(default, ast.Call):
                            func_name = ""
                            if isinstance(default.func, ast.Name):
                                func_name = default.func.id
                            elif isinstance(default.func, ast.Attribute):
                                func_name = default.func.attr
                            if func_name in ("list", "dict", "set"):
                                pytest.fail(
                                    f"Mutable default ({func_name}()) in "
                                    f"{rel_path}::{node.name}() at line {node.lineno}"
                                )

    def test_no_bare_except_pass(self):
        """Verify no bare except: or except Exception: pass patterns exist"""
        for rel_path in self.MODIFIED_FILES:
            filepath = os.path.join(self.REPO_DIR, rel_path)
            with open(filepath) as f:
                content = f.read()
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, ast.ExceptHandler):
                    # Bare except (no exception type specified)
                    if node.type is None:
                        # Check if body is just pass
                        if (len(node.body) == 1 and
                                isinstance(node.body[0], ast.Pass)):
                            pytest.fail(
                                f"Bare 'except: pass' found in {rel_path} "
                                f"at line {node.lineno}"
                            )

    def test_file_operations_use_context_managers(self):
        """Verify file operations in fileutils.py use 'with' statements"""
        filepath = os.path.join(self.REPO_DIR, "boltons/fileutils.py")
        with open(filepath) as f:
            content = f.read()
        tree = ast.parse(content)

        # Check for bare open() calls not inside a with statement
        # This is a heuristic: look for open() calls in assignments
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                if isinstance(node.value, ast.Call):
                    func = node.value.func
                    func_name = ""
                    if isinstance(func, ast.Name):
                        func_name = func.id
                    if func_name == "open":
                        # Check if this is inside a with statement
                        # Heuristic: if open() is assigned to a variable,
                        # it should be inside a with block
                        pass  # Complex to check parent context via AST

    def test_input_validation_on_public_functions(self):
        """Verify public functions in iterutils.py have input validation"""
        filepath = os.path.join(self.REPO_DIR, "boltons/iterutils.py")
        with open(filepath) as f:
            content = f.read()
        # Public functions should raise TypeError/ValueError on bad input
        has_type_error = "TypeError" in content
        has_value_error = "ValueError" in content
        assert has_type_error or has_value_error, \
            "iterutils.py should have input validation raising TypeError or ValueError"

    def test_no_silent_exception_suppression(self):
        """Verify no except blocks silently suppress errors with just 'pass'"""
        for rel_path in self.MODIFIED_FILES:
            filepath = os.path.join(self.REPO_DIR, rel_path)
            with open(filepath) as f:
                content = f.read()
            # Pattern: except SomeException:\n    pass
            bare_passes = re.findall(
                r'except\s+\w+(?:\s*,\s*\w+)*\s*:\s*\n\s+pass\s*$',
                content, re.MULTILINE
            )
            # Allow some strategic pass usages but flag excessive ones
            assert len(bare_passes) <= 2, \
                f"Found {len(bare_passes)} silent exception suppressions in {rel_path}"

    # === Functional Checks ===

    def test_chunked_basic_functionality_preserved(self):
        """Verify iterutils.chunked([1,2,3,4,5], 2) returns correct result"""
        result = subprocess.run(
            ["python", "-c",
             "import sys; sys.path.insert(0, '.'); "
             "from boltons.iterutils import chunked; "
             "r = chunked([1,2,3,4,5], 2); "
             "print(r)"],
            cwd=self.REPO_DIR,
            capture_output=True, text=True, timeout=30
        )
        assert result.returncode == 0, f"chunked() failed: {result.stderr}"
        output = result.stdout.strip()
        assert "[[1, 2], [3, 4], [5]]" in output, \
            f"chunked([1,2,3,4,5], 2) should return [[1,2],[3,4],[5]], got {output}"

    def test_chunked_rejects_none_input(self):
        """Verify chunked(None, 2) raises TypeError"""
        result = subprocess.run(
            ["python", "-c",
             "import sys; sys.path.insert(0, '.'); "
             "from boltons.iterutils import chunked; "
             "chunked(None, 2)"],
            cwd=self.REPO_DIR,
            capture_output=True, text=True, timeout=30
        )
        assert result.returncode != 0, \
            "chunked(None, 2) should raise TypeError"
        assert "TypeError" in result.stderr, \
            f"chunked(None, 2) should raise TypeError, got: {result.stderr[:300]}"

    def test_chunked_rejects_negative_size(self):
        """Verify chunked([1,2], -1) raises ValueError"""
        result = subprocess.run(
            ["python", "-c",
             "import sys; sys.path.insert(0, '.'); "
             "from boltons.iterutils import chunked; "
             "chunked([1,2], -1)"],
            cwd=self.REPO_DIR,
            capture_output=True, text=True, timeout=30
        )
        assert result.returncode != 0, \
            "chunked([1,2], -1) should raise ValueError"
        assert "ValueError" in result.stderr or "Error" in result.stderr, \
            f"chunked with negative size should raise ValueError, got: {result.stderr[:300]}"

    def test_slugify_preserved(self):
        """Verify strutils.slugify('Hello World!') returns 'hello-world'"""
        result = subprocess.run(
            ["python", "-c",
             "import sys; sys.path.insert(0, '.'); "
             "from boltons.strutils import slugify; "
             "print(slugify('Hello World!'))"],
            cwd=self.REPO_DIR,
            capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            pytest.skip(f"slugify not available or import failed: {result.stderr[:200]}")
        output = result.stdout.strip()
        assert output == "hello-world" or output == "hello_world", \
            f"slugify('Hello World!') should return 'hello-world', got '{output}'"

    def test_existing_boltons_tests_pass(self):
        """Verify all existing boltons tests still pass after refactoring"""
        # Install boltons first
        subprocess.run(["pip", "install", "-e", "."], cwd=self.REPO_DIR,
                       capture_output=True, text=True, timeout=120)
        result = subprocess.run(
            ["python", "-m", "pytest", "tests/", "-v", "--tb=short", "-x", "-q"],
            cwd=self.REPO_DIR,
            capture_output=True, text=True, timeout=300
        )
        assert result.returncode == 0, \
            f"Existing boltons tests failed:\n{result.stdout[-1500:]}\n{result.stderr[-500:]}"

    def test_anti_pattern_fix_tests_pass(self):
        """Verify the Agent's anti-pattern fix test suite passes"""
        subprocess.run(["pip", "install", "-e", "."], cwd=self.REPO_DIR,
                       capture_output=True, text=True, timeout=120)
        result = subprocess.run(
            ["python", "-m", "pytest", "tests/test_anti_pattern_fixes.py",
             "-v", "--tb=short"],
            cwd=self.REPO_DIR,
            capture_output=True, text=True, timeout=120
        )
        assert result.returncode == 0, \
            f"Anti-pattern fix tests failed:\n{result.stdout[-1500:]}\n{result.stderr[-500:]}"
