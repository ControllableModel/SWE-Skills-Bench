"""
Test skill: implementing-jsc-classes-zig
Verify that the Agent correctly implements a URLPattern class binding
in Bun's Zig-JSC bridge.
"""

import os
import re
import subprocess
import pytest


class TestImplementingJscClassesZig:
    REPO_DIR = "/workspace/bun"

    # === File Path Checks ===

    def test_classes_ts_definition_exists(self):
        """Verify url_pattern.classes.ts was created"""
        path = os.path.join(self.REPO_DIR, "src/bun.js/url_pattern.classes.ts")
        assert os.path.exists(path), f"url_pattern.classes.ts not found at {path}"

    def test_zig_implementation_exists(self):
        """Verify URLPattern.zig was created"""
        path = os.path.join(self.REPO_DIR, "src/bun.js/bindings/URLPattern.zig")
        assert os.path.exists(path), f"URLPattern.zig not found at {path}"

    def test_test_file_exists(self):
        """Verify test/js/bun/url_pattern.test.ts was created"""
        path = os.path.join(self.REPO_DIR, "test/js/bun/url_pattern.test.ts")
        assert os.path.exists(path), f"url_pattern.test.ts not found at {path}"

    # === Semantic Checks: Classes TS Definition ===

    def test_classes_ts_has_urlpattern_class(self):
        """Verify classes.ts defines URLPattern class"""
        path = os.path.join(self.REPO_DIR, "src/bun.js/url_pattern.classes.ts")
        with open(path) as f:
            content = f.read()
        assert "URLPattern" in content, "url_pattern.classes.ts should define URLPattern"

    def test_classes_ts_has_constructor(self):
        """Verify classes.ts specifies constructor: true"""
        path = os.path.join(self.REPO_DIR, "src/bun.js/url_pattern.classes.ts")
        with open(path) as f:
            content = f.read()
        assert "constructor" in content, "Class definition should have constructor"

    def test_classes_ts_has_finalize(self):
        """Verify classes.ts specifies finalize: true for GC cleanup"""
        path = os.path.join(self.REPO_DIR, "src/bun.js/url_pattern.classes.ts")
        with open(path) as f:
            content = f.read()
        assert "finalize" in content, "Class definition should have finalize: true"

    def test_classes_ts_has_test_and_exec_methods(self):
        """Verify classes.ts defines test and exec prototype methods"""
        path = os.path.join(self.REPO_DIR, "src/bun.js/url_pattern.classes.ts")
        with open(path) as f:
            content = f.read()
        assert "test" in content, "Class definition should have 'test' method"
        assert "exec" in content, "Class definition should have 'exec' method"

    def test_classes_ts_has_getters(self):
        """Verify classes.ts defines protocol, hostname, pathname, search, hash getters"""
        path = os.path.join(self.REPO_DIR, "src/bun.js/url_pattern.classes.ts")
        with open(path) as f:
            content = f.read()
        for getter in ["protocol", "hostname", "pathname", "search", "hash"]:
            assert getter in content, f"Class definition missing getter: {getter}"

    # === Semantic Checks: Zig Implementation ===

    def test_zig_has_urlpattern_struct(self):
        """Verify URLPattern.zig defines the URLPattern struct"""
        path = os.path.join(self.REPO_DIR, "src/bun.js/bindings/URLPattern.zig")
        with open(path) as f:
            content = f.read()
        assert "URLPattern" in content, "URLPattern.zig should define URLPattern struct"
        assert "struct" in content.lower() or "pub const" in content, (
            "URLPattern.zig should contain a struct definition"
        )

    def test_zig_has_constructor(self):
        """Verify URLPattern.zig implements constructor function"""
        path = os.path.join(self.REPO_DIR, "src/bun.js/bindings/URLPattern.zig")
        with open(path) as f:
            content = f.read()
        assert "constructor" in content, "URLPattern.zig should implement constructor"

    def test_zig_has_test_method(self):
        """Verify URLPattern.zig implements test method"""
        path = os.path.join(self.REPO_DIR, "src/bun.js/bindings/URLPattern.zig")
        with open(path) as f:
            content = f.read()
        # Look for a test function (avoiding matching the word 'test' in comments)
        assert re.search(r'pub\s+fn\s+test\b', content) or "fn test(" in content, (
            "URLPattern.zig should implement 'test' method"
        )

    def test_zig_has_exec_method(self):
        """Verify URLPattern.zig implements exec method"""
        path = os.path.join(self.REPO_DIR, "src/bun.js/bindings/URLPattern.zig")
        with open(path) as f:
            content = f.read()
        assert "exec" in content, "URLPattern.zig should implement 'exec' method"

    def test_zig_has_finalize_deinit(self):
        """Verify URLPattern.zig implements finalize and deinit for memory management"""
        path = os.path.join(self.REPO_DIR, "src/bun.js/bindings/URLPattern.zig")
        with open(path) as f:
            content = f.read()
        assert "finalize" in content, "URLPattern.zig should implement finalize"
        assert "deinit" in content, "URLPattern.zig should implement deinit"

    def test_zig_has_getter_functions(self):
        """Verify URLPattern.zig implements getter functions for all component patterns"""
        path = os.path.join(self.REPO_DIR, "src/bun.js/bindings/URLPattern.zig")
        with open(path) as f:
            content = f.read()
        for getter in ["getProtocol", "getHostname", "getPathname", "getSearch", "getHash"]:
            assert getter in content, f"URLPattern.zig missing getter: {getter}"

    def test_zig_handles_no_arguments_error(self):
        """Verify constructor throws error when called with zero arguments"""
        path = os.path.join(self.REPO_DIR, "src/bun.js/bindings/URLPattern.zig")
        with open(path) as f:
            content = f.read()
        # Should have argument count check
        assert "argument" in content.lower(), (
            "Constructor should check for minimum argument count"
        )

    # === Semantic Checks: Registration ===

    def test_registered_in_generated_classes_list(self):
        """Verify URLPattern is registered in generated_classes_list.zig"""
        path = os.path.join(
            self.REPO_DIR,
            "src/bun.js/bindings/generated_classes_list.zig",
        )
        assert os.path.exists(path), f"generated_classes_list.zig not found"
        with open(path) as f:
            content = f.read()
        assert "URLPattern" in content, (
            "URLPattern should be registered in generated_classes_list.zig"
        )

    # === Semantic Checks: Test File ===

    def test_test_file_covers_construction(self):
        """Verify test file tests URLPattern construction"""
        path = os.path.join(self.REPO_DIR, "test/js/bun/url_pattern.test.ts")
        with open(path) as f:
            content = f.read()
        assert "new URLPattern" in content, "Tests should construct URLPattern instances"

    def test_test_file_covers_matching(self):
        """Verify test file tests URL matching"""
        path = os.path.join(self.REPO_DIR, "test/js/bun/url_pattern.test.ts")
        with open(path) as f:
            content = f.read()
        assert ".test(" in content, "Tests should call .test() method"

    def test_test_file_covers_exec(self):
        """Verify test file tests exec with named groups"""
        path = os.path.join(self.REPO_DIR, "test/js/bun/url_pattern.test.ts")
        with open(path) as f:
            content = f.read()
        assert ".exec(" in content, "Tests should call .exec() method"

    def test_test_file_covers_error_handling(self):
        """Verify test file tests error cases"""
        path = os.path.join(self.REPO_DIR, "test/js/bun/url_pattern.test.ts")
        with open(path) as f:
            content = f.read()
        assert "throw" in content.lower() or "error" in content.lower() or "toThrow" in content, (
            "Tests should cover error handling cases"
        )
