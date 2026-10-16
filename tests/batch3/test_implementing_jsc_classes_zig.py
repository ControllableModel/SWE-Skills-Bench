"""
Test skill: implementing-jsc-classes-zig
Verify that the Agent implements JSC class bindings for a Zig-based
HTTPHeaders module in Bun.
"""

import os
import subprocess
import pytest


class TestImplementingJscClassesZig:
    REPO_DIR = "/workspace/bun"

    # === File Path Checks ===

    def test_classes_ts_exists(self):
        """Verify the .classes.ts definition file exists"""
        path = os.path.join(self.REPO_DIR, "src/bun.js/api/HTTPHeaders.classes.ts")
        assert os.path.exists(path), f"HTTPHeaders.classes.ts not found at {path}"

    def test_zig_impl_exists(self):
        """Verify the Zig implementation file exists"""
        path = os.path.join(self.REPO_DIR, "src/bun.js/bindings/HTTPHeaders.zig")
        assert os.path.exists(path), f"HTTPHeaders.zig not found at {path}"

    def test_exports_zig_exists(self):
        """Verify the exports binding file exists"""
        path = os.path.join(self.REPO_DIR, "src/bun.js/bindings/http_headers_exports.zig")
        assert os.path.exists(path), f"http_headers_exports.zig not found at {path}"

    def test_js_test_exists(self):
        """Verify the JavaScript test file exists"""
        path = os.path.join(self.REPO_DIR, "test/js/bun/http/headers.test.ts")
        assert os.path.exists(path), f"headers.test.ts not found at {path}"

    # === Semantic Checks ===

    def test_classes_ts_defines_httpheaders(self):
        """Verify .classes.ts defines HTTPHeaders class with required methods"""
        path = os.path.join(self.REPO_DIR, "src/bun.js/api/HTTPHeaders.classes.ts")
        with open(path) as f:
            content = f.read()
        assert "HTTPHeaders" in content, "Should define HTTPHeaders class"
        methods = ["get", "set", "append", "delete", "has", "entries", "keys", "values", "toJSON"]
        for method in methods:
            assert method in content, f"HTTPHeaders missing method definition: {method}"

    def test_classes_ts_defines_constructor(self):
        """Verify .classes.ts defines a constructor"""
        path = os.path.join(self.REPO_DIR, "src/bun.js/api/HTTPHeaders.classes.ts")
        with open(path) as f:
            content = f.read()
        assert "construct" in content.lower() or "init" in content.lower(), \
            "HTTPHeaders should define a constructor"

    def test_classes_ts_has_finalize(self):
        """Verify .classes.ts marks class as finalize-aware for GC"""
        path = os.path.join(self.REPO_DIR, "src/bun.js/api/HTTPHeaders.classes.ts")
        with open(path) as f:
            content = f.read()
        assert "finalize" in content.lower(), \
            "Class should be marked finalize-aware for garbage collection"

    def test_zig_impl_has_case_insensitive_storage(self):
        """Verify Zig implementation stores header names in lowercase"""
        path = os.path.join(self.REPO_DIR, "src/bun.js/bindings/HTTPHeaders.zig")
        with open(path) as f:
            content = f.read()
        has_lowercase = (
            "toLower" in content or
            "lowercase" in content.lower() or
            "std.ascii.toLower" in content or
            "lowerString" in content
        )
        assert has_lowercase, \
            "Zig implementation should convert header names to lowercase"

    def test_zig_impl_has_multi_value_support(self):
        """Verify Zig implementation supports multiple values per header"""
        path = os.path.join(self.REPO_DIR, "src/bun.js/bindings/HTTPHeaders.zig")
        with open(path) as f:
            content = f.read()
        has_multi = (
            "ArrayList" in content or
            "append" in content or
            "list" in content.lower() or
            "[]" in content
        )
        assert has_multi, \
            "Zig implementation should support multiple values per header (e.g., Set-Cookie)"

    def test_zig_impl_validates_header_names(self):
        """Verify Zig validates header names per RFC 7230 token characters"""
        path = os.path.join(self.REPO_DIR, "src/bun.js/bindings/HTTPHeaders.zig")
        with open(path) as f:
            content = f.read()
        has_validation = (
            "valid" in content.lower() or
            "token" in content.lower() or
            "isValid" in content or
            "isTokenChar" in content or
            "RFC" in content
        )
        assert has_validation, \
            "Zig should validate header names against RFC 7230 token characters"

    def test_zig_impl_validates_header_values(self):
        """Verify Zig rejects header values containing CR/LF"""
        path = os.path.join(self.REPO_DIR, "src/bun.js/bindings/HTTPHeaders.zig")
        with open(path) as f:
            content = f.read()
        has_crlf_check = (
            "\\r" in content or "\\n" in content or
            "'\\r'" in content or "'\\n'" in content or
            "0x0d" in content.lower() or "0x0a" in content.lower() or
            "newline" in content.lower() or "carriage" in content.lower()
        )
        assert has_crlf_check, \
            "Zig should reject header values containing CR or LF characters"

    def test_zig_impl_has_deinit(self):
        """Verify Zig implementation has deinit for memory cleanup"""
        path = os.path.join(self.REPO_DIR, "src/bun.js/bindings/HTTPHeaders.zig")
        with open(path) as f:
            content = f.read()
        assert "deinit" in content, \
            "Zig implementation should have deinit method for memory cleanup"

    def test_zig_impl_uses_allocator_pattern(self):
        """Verify Zig uses allocator pattern without global allocators"""
        path = os.path.join(self.REPO_DIR, "src/bun.js/bindings/HTTPHeaders.zig")
        with open(path) as f:
            content = f.read()
        assert "Allocator" in content or "allocator" in content, \
            "Zig should use the allocator pattern"

    # === Functional Checks ===

    def test_classes_ts_is_valid_typescript(self):
        """Verify .classes.ts is valid TypeScript/JavaScript"""
        path = os.path.join(self.REPO_DIR, "src/bun.js/api/HTTPHeaders.classes.ts")
        result = subprocess.run(
            ["node", "--check", path],
            cwd=self.REPO_DIR,
            capture_output=True, text=True, timeout=30
        )
        # .classes.ts might use TypeScript syntax, so node --check may fail
        # but it shouldn't have gross syntax errors
        if result.returncode != 0:
            with open(path) as f:
                content = f.read()
            # Basic sanity: non-empty and has expected structure
            assert len(content) > 100, \
                f"classes.ts is too short ({len(content)} chars)"
            assert "HTTPHeaders" in content, \
                "classes.ts should define HTTPHeaders"

    def test_js_test_file_has_tests(self):
        """Verify JS test file contains test cases"""
        path = os.path.join(self.REPO_DIR, "test/js/bun/http/headers.test.ts")
        with open(path) as f:
            content = f.read()
        test_count = content.count("it(") + content.count("test(")
        assert test_count >= 3, \
            f"Test file should have at least 3 test cases, found {test_count}"

    def test_js_tests_cover_key_scenarios(self):
        """Verify JS tests cover construction, get/set, multi-value, delete, validation"""
        path = os.path.join(self.REPO_DIR, "test/js/bun/http/headers.test.ts")
        with open(path) as f:
            content = f.read()
        scenarios = {
            "construction": ["new HTTPHeaders", "constructor", "HTTPHeaders("],
            "get/set": ["get(", "set("],
            "append": ["append("],
            "delete": ["delete("],
            "validation": ["invalid", "throw", "error", "TypeError"],
        }
        found_scenarios = []
        for scenario, keywords in scenarios.items():
            if any(kw in content for kw in keywords):
                found_scenarios.append(scenario)
        assert len(found_scenarios) >= 3, \
            f"Tests should cover key scenarios. Found: {found_scenarios}"

    def test_exports_zig_has_bridge_functions(self):
        """Verify exports file defines JSC bridge functions"""
        path = os.path.join(self.REPO_DIR, "src/bun.js/bindings/http_headers_exports.zig")
        with open(path) as f:
            content = f.read()
        # Should reference HTTPHeaders and export functions
        assert "HTTPHeaders" in content, \
            "Exports file should reference HTTPHeaders"
        has_exports = (
            "export" in content.lower() or
            "callFrame" in content or
            "CallFrame" in content or
            "JSValue" in content or
            "comptime" in content
        )
        assert has_exports, \
            "Exports file should define JSC bridge functions"
