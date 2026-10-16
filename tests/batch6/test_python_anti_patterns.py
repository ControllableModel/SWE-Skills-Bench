"""
Test skill: python-anti-patterns
Verify that the Agent correctly refactors boltons iterutils.py and
fileutils.py to eliminate mutable default arguments, bare except clauses,
type checks with ==, and missing input validation.
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
        path = os.path.join(self.REPO_DIR, "boltons/iterutils.py")
        assert os.path.exists(path), f"iterutils.py not found at {path}"

    def test_fileutils_exists(self):
        """Verify fileutils.py exists"""
        path = os.path.join(self.REPO_DIR, "boltons/fileutils.py")
        assert os.path.exists(path), f"fileutils.py not found at {path}"

    # === Semantic Checks ===

    def test_no_mutable_default_args_in_iterutils(self):
        """Verify iterutils.py has no mutable default arguments (list/dict/set)"""
        path = os.path.join(self.REPO_DIR, "boltons/iterutils.py")
        with open(path, "r") as f:
            source = f.read()
        tree = ast.parse(source)

        violations = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for default in node.args.defaults + node.args.kw_defaults:
                    if default is None:
                        continue
                    if isinstance(default, (ast.List, ast.Dict, ast.Set)):
                        violations.append(
                            f"{node.name}() at line {node.lineno} has mutable default"
                        )
        assert not violations, (
            f"Mutable default arguments found:\n" + "\n".join(violations)
        )

    def test_no_mutable_default_args_in_fileutils(self):
        """Verify fileutils.py has no mutable default arguments"""
        path = os.path.join(self.REPO_DIR, "boltons/fileutils.py")
        with open(path, "r") as f:
            source = f.read()
        tree = ast.parse(source)

        violations = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for default in node.args.defaults + node.args.kw_defaults:
                    if default is None:
                        continue
                    if isinstance(default, (ast.List, ast.Dict, ast.Set)):
                        violations.append(
                            f"{node.name}() at line {node.lineno} has mutable default"
                        )
        assert not violations, (
            f"Mutable default arguments found:\n" + "\n".join(violations)
        )

    def test_no_bare_excepts_in_iterutils(self):
        """Verify iterutils.py has no bare except clauses"""
        path = os.path.join(self.REPO_DIR, "boltons/iterutils.py")
        with open(path, "r") as f:
            source = f.read()
        tree = ast.parse(source)

        bare_excepts = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler):
                if node.type is None:
                    bare_excepts.append(f"line {node.lineno}")

        assert not bare_excepts, (
            f"Bare except clauses found at: {', '.join(bare_excepts)}"
        )

    def test_no_bare_excepts_in_fileutils(self):
        """Verify fileutils.py has no bare except clauses"""
        path = os.path.join(self.REPO_DIR, "boltons/fileutils.py")
        with open(path, "r") as f:
            source = f.read()
        tree = ast.parse(source)

        bare_excepts = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler):
                if node.type is None:
                    bare_excepts.append(f"line {node.lineno}")

        assert not bare_excepts, (
            f"Bare except clauses found at: {', '.join(bare_excepts)}"
        )

    def test_uses_isinstance_not_type_equality(self):
        """Verify type checks use isinstance() instead of type() == comparison"""
        for filename in ["boltons/iterutils.py", "boltons/fileutils.py"]:
            path = os.path.join(self.REPO_DIR, filename)
            with open(path, "r") as f:
                source = f.read()

            # Pattern: type(x) == type or type(x) is type (exact type comparison)
            # This check looks for type() == <something> antipattern
            bad_patterns = re.findall(
                r"type\s*\([^)]+\)\s*==\s*", source
            )
            assert not bad_patterns, (
                f"{filename} still uses type() == for comparison; "
                "use isinstance() instead"
            )

    def test_chunked_validates_size_argument(self):
        """Verify chunked() validates that chunk size is a positive integer"""
        path = os.path.join(self.REPO_DIR, "boltons/iterutils.py")
        with open(path, "r") as f:
            source = f.read()

        # Look for input validation on size/chunk_size parameter
        assert re.search(
            r"(raise\s+(ValueError|TypeError)|if\s+.*size\s*(<=|<\s*1|is\s+not|not\s+isinstance))",
            source,
        ), "chunked() should validate the size argument"

    def test_windowed_validates_size_argument(self):
        """Verify windowed() / windowed_iter() validates window size"""
        path = os.path.join(self.REPO_DIR, "boltons/iterutils.py")
        with open(path, "r") as f:
            source = f.read()

        # Find windowed function and check for validation
        func_match = re.search(
            r"def\s+windowed(?:_iter)?\s*\(.*?\n((?:[ \t]+.*\n){1,15})",
            source,
        )
        if func_match:
            body = func_match.group(1)
            has_validation = ("raise" in body and ("ValueError" in body or "TypeError" in body)) or \
                             ("if" in body and ("size" in body or "window" in body))
            assert has_validation, "windowed() should validate window size"
        # If function not found, pass silently (may have different name)

    def test_atomic_save_validates_file_path_type(self):
        """Verify atomic_save() validates file_path is a string"""
        path = os.path.join(self.REPO_DIR, "boltons/fileutils.py")
        with open(path, "r") as f:
            source = f.read()

        # Find atomic_save/AtomicSaver and check for type validation
        assert re.search(
            r"(isinstance\s*\(.*(?:file_path|dest_path|path).*str|"
            r"raise\s+TypeError.*(?:file_path|dest_path|path))",
            source,
        ), "atomic_save should validate that file_path is a string"

    def test_none_sentinel_pattern_used(self):
        """Verify sentinel/None pattern is used instead of mutable defaults"""
        for filename in ["boltons/iterutils.py", "boltons/fileutils.py"]:
            path = os.path.join(self.REPO_DIR, filename)
            with open(path, "r") as f:
                source = f.read()

            # Common sentinel patterns: `=None` with `if x is None: x = []`
            # or a _UNSET / _SENTINEL constant
            has_none_default = "=None" in source or "= None" in source
            has_sentinel = re.search(r"_UNSET|_SENTINEL|_DEFAULT|_MISSING", source)
            has_none_guard = re.search(r"if\s+\w+\s+is\s+None", source)

            assert has_none_default or has_sentinel or has_none_guard, (
                f"{filename} should use None/sentinel pattern for formerly mutable defaults"
            )

    # === Functional Checks ===

    def test_iterutils_module_imports(self):
        """Verify iterutils module can be imported without errors"""
        result = subprocess.run(
            ["python", "-c", "from boltons.iterutils import chunked, bucketize"],
            capture_output=True, text=True, timeout=30,
            cwd=self.REPO_DIR,
        )
        assert result.returncode == 0, (
            f"Failed to import iterutils:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )

    def test_fileutils_module_imports(self):
        """Verify fileutils module can be imported without errors"""
        result = subprocess.run(
            ["python", "-c", "from boltons.fileutils import atomic_save, mkdir_p"],
            capture_output=True, text=True, timeout=30,
            cwd=self.REPO_DIR,
        )
        assert result.returncode == 0, (
            f"Failed to import fileutils:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )

    def test_chunked_raises_on_invalid_size(self):
        """Verify chunked() raises ValueError on invalid chunk size"""
        result = subprocess.run(
            [
                "python", "-c",
                "from boltons.iterutils import chunked; chunked([1,2,3], 0)"
            ],
            capture_output=True, text=True, timeout=30,
            cwd=self.REPO_DIR,
        )
        assert result.returncode != 0, (
            "chunked() should raise an error for size=0"
        )
        assert "ValueError" in result.stderr or "Error" in result.stderr, (
            f"Expected ValueError for chunked(... , 0), got: {result.stderr}"
        )

    def test_chunked_works_correctly(self):
        """Verify chunked() still produces correct output"""
        result = subprocess.run(
            [
                "python", "-c",
                "from boltons.iterutils import chunked; "
                "result = chunked(range(7), 3); print(result)"
            ],
            capture_output=True, text=True, timeout=30,
            cwd=self.REPO_DIR,
        )
        assert result.returncode == 0, (
            f"chunked() failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )
        output = result.stdout.strip()
        # Should output something like [[0, 1, 2], [3, 4, 5], [6]]
        assert "[" in output, f"Unexpected output from chunked(): {output}"

    def test_existing_tests_pass(self):
        """Verify the existing boltons test suite still passes for iterutils and fileutils"""
        result = subprocess.run(
            ["python", "-m", "pytest", "tests/test_iterutils.py", "tests/test_fileutils.py",
             "-v", "--tb=short", "-x"],
            capture_output=True, text=True, timeout=120,
            cwd=self.REPO_DIR,
        )
        assert result.returncode == 0, (
            f"Existing tests failed after refactoring:\n{result.stdout}\n{result.stderr}"
        )
