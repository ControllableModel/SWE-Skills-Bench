"""
Test skill: implementing-jsc-classes-zig
Verify that the Agent correctly implements a URLPattern JavaScript class
in Bun using Zig bindings with pattern parsing, matching, and group extraction.
"""

import os
import subprocess
import re
import pytest


class TestImplementingJscClassesZig:
    REPO_DIR = "/workspace/bun"

    # === File Path Checks ===

    def test_classes_ts_exists(self):
        """Verify that the URLPattern class definition file exists"""
        filepath = os.path.join(self.REPO_DIR, "src/bun.js/api/URLPattern.classes.ts")
        assert os.path.exists(filepath), f"URLPattern.classes.ts not found at {filepath}"

    def test_zig_implementation_exists(self):
        """Verify that the Zig implementation file exists"""
        filepath = os.path.join(self.REPO_DIR, "src/bun.js/api/URLPattern.zig")
        assert os.path.exists(filepath), f"URLPattern.zig not found at {filepath}"

    def test_test_file_exists(self):
        """Verify that the test file exists"""
        filepath = os.path.join(self.REPO_DIR, "src/bun.js/api/URLPattern.test.ts")
        assert os.path.exists(filepath), f"URLPattern.test.ts not found at {filepath}"

    # === Semantic Checks ===

    def test_classes_ts_defines_urlpattern(self):
        """Verify the class definition declares URLPattern with required config"""
        filepath = os.path.join(self.REPO_DIR, "src/bun.js/api/URLPattern.classes.ts")
        with open(filepath) as f:
            content = f.read()

        assert "URLPattern" in content, (
            "URLPattern.classes.ts does not define URLPattern class"
        )
        assert "constructor" in content.lower(), (
            "URLPattern.classes.ts missing constructor definition"
        )
        assert "finalize" in content.lower(), (
            "URLPattern.classes.ts missing finalize for cleanup"
        )

    def test_classes_ts_defines_methods_and_getters(self):
        """Verify the class definition includes test, exec methods and getters"""
        filepath = os.path.join(self.REPO_DIR, "src/bun.js/api/URLPattern.classes.ts")
        with open(filepath) as f:
            content = f.read()

        required_elements = {
            "test method": "test" in content,
            "exec method": "exec" in content,
            "protocol getter": "protocol" in content,
            "hostname getter": "hostname" in content,
            "pathname getter": "pathname" in content,
        }
        missing = [e for e, found in required_elements.items() if not found]
        assert len(missing) == 0, (
            f"URLPattern.classes.ts missing: {missing}"
        )

    def test_zig_implementation_has_pattern_parsing(self):
        """Verify Zig implementation includes pattern parsing logic"""
        filepath = os.path.join(self.REPO_DIR, "src/bun.js/api/URLPattern.zig")
        with open(filepath) as f:
            content = f.read()

        has_parsing = (
            "parse" in content.lower()
            or "pattern" in content.lower()
            or "segment" in content.lower()
        )
        assert has_parsing, (
            "URLPattern.zig does not appear to implement pattern parsing"
        )

    def test_zig_implementation_has_matching_logic(self):
        """Verify Zig implementation includes URL matching logic"""
        filepath = os.path.join(self.REPO_DIR, "src/bun.js/api/URLPattern.zig")
        with open(filepath) as f:
            content = f.read()

        has_matching = (
            "match" in content.lower()
            or "test" in content.lower()
            or "exec" in content.lower()
        )
        assert has_matching, (
            "URLPattern.zig does not appear to implement URL matching logic"
        )

    def test_zig_implementation_has_named_parameters(self):
        """Verify Zig implementation handles named parameters (:paramName)"""
        filepath = os.path.join(self.REPO_DIR, "src/bun.js/api/URLPattern.zig")
        with open(filepath) as f:
            content = f.read()

        has_params = (
            "param" in content.lower()
            or ":" in content
            or "named" in content.lower()
            or "capture" in content.lower()
            or "group" in content.lower()
        )
        assert has_params, (
            "URLPattern.zig does not appear to handle named parameters"
        )

    def test_zig_implementation_uses_jsc_api(self):
        """Verify Zig implementation uses JSC API for JS interop"""
        filepath = os.path.join(self.REPO_DIR, "src/bun.js/api/URLPattern.zig")
        with open(filepath) as f:
            content = f.read()

        has_jsc = (
            "JSC" in content or "JSValue" in content
            or "jsString" in content or "createEmptyObject" in content
            or "JSGlobalObject" in content
        )
        assert has_jsc, (
            "URLPattern.zig does not use JSC API (JSValue, JSGlobalObject, etc.)"
        )

    # === Functional Checks ===

    def test_test_file_has_test_cases(self):
        """Verify the test file has meaningful test cases"""
        filepath = os.path.join(self.REPO_DIR, "src/bun.js/api/URLPattern.test.ts")
        with open(filepath) as f:
            content = f.read()

        # Count test cases
        test_blocks = (
            len(re.findall(r'\bit\s*\(', content))
            + len(re.findall(r'\btest\s*\(', content))
        )
        assert test_blocks >= 5, (
            f"Expected at least 5 test cases in URLPattern.test.ts, found {test_blocks}"
        )

    def test_test_file_covers_key_scenarios(self):
        """Verify test file covers matching, non-matching, and parameter extraction"""
        filepath = os.path.join(self.REPO_DIR, "src/bun.js/api/URLPattern.test.ts")
        with open(filepath) as f:
            content = f.read()

        scenarios = {
            "pattern matching (test)": ".test(" in content,
            "result extraction (exec)": ".exec(" in content,
            "named parameters": ":id" in content or ":param" in content or "param" in content.lower(),
            "error handling": "TypeError" in content or "invalid" in content.lower() or "throw" in content,
        }
        missing = [s for s, found in scenarios.items() if not found]
        assert len(missing) <= 1, (
            f"Test file missing coverage for: {missing}"
        )

    def test_zig_has_deinit(self):
        """Verify Zig implementation implements deinit for proper cleanup"""
        filepath = os.path.join(self.REPO_DIR, "src/bun.js/api/URLPattern.zig")
        with open(filepath) as f:
            content = f.read()

        assert "deinit" in content, (
            "URLPattern.zig missing 'deinit' function for cleanup/finalization"
        )

    def test_zig_handles_wildcard(self):
        """Verify Zig implementation handles wildcard * patterns"""
        filepath = os.path.join(self.REPO_DIR, "src/bun.js/api/URLPattern.zig")
        with open(filepath) as f:
            content = f.read()

        has_wildcard = (
            "wildcard" in content.lower()
            or "'*'" in content
            or '"*"' in content
            or "asterisk" in content.lower()
        )
        assert has_wildcard, (
            "URLPattern.zig does not appear to handle wildcard (*) patterns"
        )

    def test_classes_ts_has_cache_on_getters(self):
        """Verify getters use cache: true in class definition"""
        filepath = os.path.join(self.REPO_DIR, "src/bun.js/api/URLPattern.classes.ts")
        with open(filepath) as f:
            content = f.read()

        has_cache = "cache" in content.lower()
        assert has_cache, (
            "URLPattern.classes.ts getters should use cache: true"
        )
