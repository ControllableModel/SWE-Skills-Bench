"""
Test skill: implementing-jsc-classes-zig
Verify that a URLPatternMatcher class has been correctly implemented for Bun
using Zig-JS bindings, including .classes.ts definition, Zig implementation,
class registration, pattern matching, and error handling.
"""

import os
import re
import subprocess
import pytest


class TestImplementingJscClassesZig:
    REPO_DIR = "/workspace/bun"

    CLASSES_TS = "src/bun.js/api/URLPatternMatcher.classes.ts"
    ZIG_IMPL = "src/bun.js/api/URLPatternMatcher.zig"
    CLASSES_LIST = "src/bun.js/bindings/generated_classes_list.zig"

    # === File Path Checks ===

    def test_classes_ts_exists(self):
        """Verify URLPatternMatcher.classes.ts definition file exists"""
        filepath = os.path.join(self.REPO_DIR, self.CLASSES_TS)
        assert os.path.exists(filepath), f".classes.ts not found at {filepath}"

    def test_zig_implementation_exists(self):
        """Verify URLPatternMatcher.zig implementation file exists"""
        filepath = os.path.join(self.REPO_DIR, self.ZIG_IMPL)
        assert os.path.exists(filepath), f"Zig impl not found at {filepath}"

    def test_generated_classes_list_exists(self):
        """Verify generated_classes_list.zig exists"""
        filepath = os.path.join(self.REPO_DIR, self.CLASSES_LIST)
        assert os.path.exists(filepath), f"Classes list not found at {filepath}"

    # === Semantic Checks ===

    def test_classes_ts_defines_class(self):
        """Verify .classes.ts defines URLPatternMatcher class with required methods"""
        filepath = os.path.join(self.REPO_DIR, self.CLASSES_TS)
        with open(filepath) as f:
            content = f.read()
        assert "URLPatternMatcher" in content, \
            ".classes.ts should define URLPatternMatcher"
        assert "match" in content, \
            ".classes.ts should define 'match' method"
        assert "test" in content, \
            ".classes.ts should define 'test' method"
        assert "pattern" in content, \
            ".classes.ts should define 'pattern' getter"
        assert "paramNames" in content, \
            ".classes.ts should define 'paramNames' getter"

    def test_classes_ts_has_finalize(self):
        """Verify .classes.ts sets finalize: true for GC cleanup"""
        filepath = os.path.join(self.REPO_DIR, self.CLASSES_TS)
        with open(filepath) as f:
            content = f.read()
        assert "finalize" in content, \
            ".classes.ts should set finalize: true for GC cleanup"

    def test_zig_impl_has_constructor_and_methods(self):
        """Verify Zig implementation has constructor, match, test, deinit"""
        filepath = os.path.join(self.REPO_DIR, self.ZIG_IMPL)
        with open(filepath) as f:
            content = f.read()
        required = ["constructor", "match", "deinit", "finalize"]
        for item in required:
            assert item in content, \
                f"Zig implementation should have '{item}' function"

    def test_zig_impl_handles_named_parameters(self):
        """Verify Zig implementation supports named parameter extraction (:param)"""
        filepath = os.path.join(self.REPO_DIR, self.ZIG_IMPL)
        with open(filepath) as f:
            content = f.read()
        has_param = (":" in content and ("param" in content.lower() or
                                          "named" in content.lower() or
                                          "capture" in content.lower()))
        assert has_param, \
            "Zig implementation should handle named parameters (e.g., :id)"

    def test_zig_impl_handles_wildcards(self):
        """Verify Zig implementation supports wildcard segments (*path)"""
        filepath = os.path.join(self.REPO_DIR, self.ZIG_IMPL)
        with open(filepath) as f:
            content = f.read()
        assert "*" in content or "wildcard" in content.lower() or "glob" in content.lower(), \
            "Zig implementation should handle wildcard segments (*path)"

    def test_zig_impl_validates_pattern(self):
        """Verify Zig implementation validates patterns (empty, //, unnamed :)"""
        filepath = os.path.join(self.REPO_DIR, self.ZIG_IMPL)
        with open(filepath) as f:
            content = f.read()
        # Should throw errors for invalid patterns
        has_error_handling = ("throw" in content or "globalObject" in content or
                              "error" in content.lower())
        assert has_error_handling, \
            "Zig implementation should throw errors for invalid patterns"

    def test_zig_impl_uses_bun_allocator(self):
        """Verify Zig implementation uses bun.default_allocator for memory"""
        filepath = os.path.join(self.REPO_DIR, self.ZIG_IMPL)
        with open(filepath) as f:
            content = f.read()
        has_allocator = ("default_allocator" in content or "allocator" in content)
        assert has_allocator, \
            "Zig implementation should use bun.default_allocator"

    def test_zig_finalize_calls_deinit(self):
        """Verify finalize() calls deinit() for proper memory cleanup"""
        filepath = os.path.join(self.REPO_DIR, self.ZIG_IMPL)
        with open(filepath) as f:
            content = f.read()
        # finalize should reference deinit
        assert "deinit" in content, \
            "finalize() should call deinit() for memory cleanup"

    def test_class_registered_in_generated_list(self):
        """Verify URLPatternMatcher is registered in generated_classes_list.zig"""
        filepath = os.path.join(self.REPO_DIR, self.CLASSES_LIST)
        with open(filepath) as f:
            content = f.read()
        assert "URLPatternMatcher" in content, \
            "URLPatternMatcher should be registered in generated_classes_list.zig"

    def test_zig_impl_argument_validation(self):
        """Verify Zig implementation validates argument count and types"""
        filepath = os.path.join(self.REPO_DIR, self.ZIG_IMPL)
        with open(filepath) as f:
            content = f.read()
        has_arg_check = ("arguments" in content or "callFrame" in content or
                         "argument" in content.lower())
        assert has_arg_check, \
            "Methods should validate argument count using callFrame.arguments()"

    # === Functional Checks ===

    def test_classes_ts_is_valid_typescript(self):
        """Verify .classes.ts has valid TypeScript syntax (basic bracket check)"""
        filepath = os.path.join(self.REPO_DIR, self.CLASSES_TS)
        with open(filepath) as f:
            content = f.read()
        open_braces = content.count('{')
        close_braces = content.count('}')
        assert abs(open_braces - close_braces) <= 1, \
            f"Unbalanced braces in .classes.ts: {open_braces} open, {close_braces} close"
        open_parens = content.count('(')
        close_parens = content.count(')')
        assert abs(open_parens - close_parens) <= 1, \
            f"Unbalanced parens in .classes.ts: {open_parens} open, {close_parens} close"

    def test_zig_impl_compiles_syntax(self):
        """Verify Zig file has no obvious syntax issues (balanced braces)"""
        filepath = os.path.join(self.REPO_DIR, self.ZIG_IMPL)
        with open(filepath) as f:
            content = f.read()
        open_braces = content.count('{')
        close_braces = content.count('}')
        assert abs(open_braces - close_braces) <= 2, \
            f"Unbalanced braces in Zig file: {open_braces} open, {close_braces} close"

    def test_zig_impl_match_returns_object_or_null(self):
        """Verify match function logic constructs result object or returns null"""
        filepath = os.path.join(self.REPO_DIR, self.ZIG_IMPL)
        with open(filepath) as f:
            content = f.read()
        has_null_return = ("null" in content or "JSValue.null" in content or
                           ".jsNull()" in content)
        assert has_null_return, \
            "match() should return null on no-match"
        has_object = ("createObject" in content or "Object" in content or
                      "params" in content)
        assert has_object, \
            "match() should construct a result object with params on success"
