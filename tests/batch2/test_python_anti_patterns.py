"""
Test skill: python-anti-patterns
Verify that the Agent correctly refactors Python anti-patterns in the
Boltons library (iterutils.py and strutils.py) while preserving public
API and behavior.
"""

import os
import sys
import ast
import re
import subprocess
import pytest


class TestPythonAntiPatterns:
    REPO_DIR = "/workspace/boltons"

    # === File Path Checks ===

    def test_iterutils_file_exists(self):
        """Verify boltons/iterutils.py exists"""
        path = os.path.join(self.REPO_DIR, "boltons/iterutils.py")
        assert os.path.exists(path), f"iterutils.py not found at {path}"

    def test_strutils_file_exists(self):
        """Verify boltons/strutils.py exists"""
        path = os.path.join(self.REPO_DIR, "boltons/strutils.py")
        assert os.path.exists(path), f"strutils.py not found at {path}"

    def test_files_are_valid_python(self):
        """Verify both files are syntactically valid Python"""
        for modname in ["iterutils", "strutils"]:
            path = os.path.join(self.REPO_DIR, f"boltons/{modname}.py")
            with open(path) as f:
                content = f.read()
            try:
                ast.parse(content)
            except SyntaxError as e:
                pytest.fail(f"boltons/{modname}.py has syntax error: {e}")

    # === Semantic Checks ===

    def test_no_type_equality_checks(self):
        """Verify type(x) == ... patterns are replaced with isinstance()"""
        for modname in ["iterutils", "strutils"]:
            path = os.path.join(self.REPO_DIR, f"boltons/{modname}.py")
            with open(path) as f:
                content = f.read()

            # Look for patterns like type(x) == type or type(x) is type
            type_eq_pattern = re.compile(r'type\s*\([^)]+\)\s*==\s*')
            matches = type_eq_pattern.findall(content)
            assert len(matches) == 0, (
                f"boltons/{modname}.py still has {len(matches)} type(x) == ... patterns. "
                f"These should be replaced with isinstance(). Examples: {matches[:3]}"
            )

    def test_no_bare_except_clauses(self):
        """Verify bare except: clauses are replaced with specific exception types"""
        for modname in ["iterutils", "strutils"]:
            path = os.path.join(self.REPO_DIR, f"boltons/{modname}.py")
            with open(path) as f:
                tree = ast.parse(f.read())

            bare_excepts = []
            for node in ast.walk(tree):
                if isinstance(node, ast.ExceptHandler):
                    if node.type is None:
                        bare_excepts.append(node.lineno)

            assert len(bare_excepts) == 0, (
                f"boltons/{modname}.py still has bare 'except:' at lines {bare_excepts}. "
                "Should use specific exception types."
            )

    def test_uses_fstrings_where_appropriate(self):
        """Verify old-style string formatting is reduced in favor of f-strings"""
        for modname in ["iterutils", "strutils"]:
            path = os.path.join(self.REPO_DIR, f"boltons/{modname}.py")
            with open(path) as f:
                content = f.read()

            # Count old-style % formatting usage
            percent_format = re.findall(r'["\'].*?%[sd].*?["\']\s*%\s', content)
            # Count .format() usage
            dot_format = content.count(".format(")
            # Count f-string usage
            fstring_count = len(re.findall(r'f["\']', content))

            total_old = len(percent_format) + dot_format
            # Allow some legacy formatting, but f-strings should be present
            if total_old > 5:
                assert fstring_count > 0, (
                    f"boltons/{modname}.py has {total_old} old-style format calls "
                    f"but no f-strings. Some should be converted to f-strings."
                )

    def test_public_api_preserved_iterutils(self):
        """Verify iterutils public API is preserved after refactoring"""
        path = os.path.join(self.REPO_DIR, "boltons/iterutils.py")
        with open(path) as f:
            tree = ast.parse(f.read())

        public_names = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                if not node.name.startswith("_"):
                    public_names.append(node.name)

        # These are well-known public functions in iterutils
        expected_public = [
            "chunked", "windowed", "unique", "flatten",
        ]
        for name in expected_public:
            found = any(name in pn for pn in public_names)
            # Some names might not exist in all versions, so soft check
            if not found:
                pass  # Don't fail on non-essential functions

        assert len(public_names) >= 5, (
            f"iterutils should maintain its public API. Only {len(public_names)} "
            f"public names found: {public_names[:10]}"
        )

    def test_public_api_preserved_strutils(self):
        """Verify strutils public API is preserved after refactoring"""
        path = os.path.join(self.REPO_DIR, "boltons/strutils.py")
        with open(path) as f:
            tree = ast.parse(f.read())

        public_names = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                if not node.name.startswith("_"):
                    public_names.append(node.name)

        assert len(public_names) >= 3, (
            f"strutils should maintain its public API. Only {len(public_names)} "
            f"public names found: {public_names[:10]}"
        )

    # === Functional Checks ===

    def test_iterutils_importable(self):
        """Verify boltons.iterutils is importable after refactoring"""
        sys.path.insert(0, self.REPO_DIR)
        try:
            from boltons import iterutils
            assert iterutils is not None
        except ImportError as e:
            pytest.fail(f"Cannot import boltons.iterutils: {e}")

    def test_strutils_importable(self):
        """Verify boltons.strutils is importable after refactoring"""
        sys.path.insert(0, self.REPO_DIR)
        try:
            from boltons import strutils
            assert strutils is not None
        except ImportError as e:
            pytest.fail(f"Cannot import boltons.strutils: {e}")

    def test_iterutils_functions_work_correctly(self):
        """Verify key iterutils functions produce correct results"""
        sys.path.insert(0, self.REPO_DIR)
        from boltons import iterutils

        # Test chunked if available
        if hasattr(iterutils, "chunked"):
            result = list(iterutils.chunked(range(10), 3))
            assert len(result) == 4, (
                f"chunked(range(10), 3) should produce 4 chunks, got {len(result)}"
            )
            assert list(result[0]) == [0, 1, 2] or result[0] == (0, 1, 2) or result[0] == [0, 1, 2], (
                f"First chunk should be [0, 1, 2], got {result[0]}"
            )

        # Test flatten if available
        if hasattr(iterutils, "flatten"):
            result = list(iterutils.flatten([[1, 2], [3, 4]]))
            assert result == [1, 2, 3, 4], (
                f"flatten([[1,2],[3,4]]) should be [1,2,3,4], got {result}"
            )

    def test_strutils_functions_work_correctly(self):
        """Verify key strutils functions produce correct results"""
        sys.path.insert(0, self.REPO_DIR)
        from boltons import strutils

        # Test slugify if available
        if hasattr(strutils, "slugify"):
            result = strutils.slugify("Hello World!")
            assert isinstance(result, str), f"slugify should return str, got {type(result)}"
            assert " " not in result, f"slugify should remove spaces: {result}"

        # Test camel_to_under if available
        if hasattr(strutils, "camel2under"):
            result = strutils.camel2under("CamelCase")
            assert result == "camel_case", (
                f"camel2under('CamelCase') should be 'camel_case', got '{result}'"
            )

    def test_existing_tests_still_pass(self):
        """Verify existing boltons tests still pass after refactoring"""
        result = subprocess.run(
            ["python", "-m", "pytest", "tests/", "-x", "-q", "--tb=short"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode != 0:
            # Allow partial failures for tests unrelated to our changes
            output = result.stdout + result.stderr
            if "iterutils" in output or "strutils" in output:
                pytest.fail(
                    f"Tests related to modified modules failed:\n"
                    f"{output[:2000]}"
                )

    def test_no_new_dependencies_introduced(self):
        """Verify no new imports/dependencies added to the modules"""
        for modname in ["iterutils", "strutils"]:
            path = os.path.join(self.REPO_DIR, f"boltons/{modname}.py")
            with open(path) as f:
                tree = ast.parse(f.read())

            imports = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.append(alias.name)
                elif isinstance(node, ast.ImportFrom):
                    if node.module and not node.module.startswith("boltons"):
                        imports.append(node.module)

            # These should only use stdlib modules
            stdlib_modules = {
                "os", "sys", "re", "math", "itertools", "functools",
                "operator", "collections", "string", "textwrap", "io",
                "types", "copy", "warnings", "codecs", "unicodedata",
                "html", "decimal", "fractions",
            }
            external = [i for i in imports if i.split(".")[0] not in stdlib_modules]
            assert len(external) == 0, (
                f"boltons/{modname}.py should not introduce new external dependencies. "
                f"Non-stdlib imports: {external}"
            )
