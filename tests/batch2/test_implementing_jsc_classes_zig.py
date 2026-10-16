"""
Test skill: implementing-jsc-classes-zig
Verify that the Agent correctly implements a JavaScript hash class using
Bun's Zig-JSC bindings including the .classes.ts definition, the .zig
implementation, and the JavaScript test file.
"""

import os
import re
import subprocess
import pytest


class TestImplementingJscClassesZig:
    REPO_DIR = "/workspace/bun"

    # === File Path Checks ===

    def test_classes_ts_file_exists(self):
        """Verify BunHasher.classes.ts definition file exists"""
        path = os.path.join(
            self.REPO_DIR, "src/bun.js/api/BunHasher.classes.ts"
        )
        assert os.path.exists(path), f"BunHasher.classes.ts not found at {path}"

    def test_zig_implementation_file_exists(self):
        """Verify BunHasher.zig implementation file exists"""
        path = os.path.join(
            self.REPO_DIR, "src/bun.js/api/BunHasher.zig"
        )
        assert os.path.exists(path), f"BunHasher.zig not found at {path}"

    def test_test_file_exists(self):
        """Verify hasher.test.ts test file exists"""
        path = os.path.join(self.REPO_DIR, "test/js/bun/hasher.test.ts")
        assert os.path.exists(path), f"hasher.test.ts not found at {path}"

    # === Semantic Checks ===

    def test_classes_ts_uses_define_pattern(self):
        """Verify BunHasher.classes.ts uses Bun's define() code generator pattern"""
        path = os.path.join(
            self.REPO_DIR, "src/bun.js/api/BunHasher.classes.ts"
        )
        with open(path) as f:
            content = f.read()

        assert "define" in content, (
            "BunHasher.classes.ts should use Bun's define() pattern"
        )

    def test_classes_ts_declares_constructor_and_methods(self):
        """Verify class definition declares constructor, methods, and property"""
        path = os.path.join(
            self.REPO_DIR, "src/bun.js/api/BunHasher.classes.ts"
        )
        with open(path) as f:
            content = f.read().lower()

        required = {
            "constructor": "construct" in content or "constructor" in content,
            "hash_method": "hash" in content or "update" in content or "digest" in content,
            "property_getter": "get" in content or "property" in content or "algorithm" in content,
            "finalize": "finalize" in content or "deinit" in content or "destroy" in content,
        }
        found = [k for k, v in required.items() if v]
        assert len(found) >= 3, (
            f"Class definition should declare constructor, methods, getter, and finalize. "
            f"Found: {found}"
        )

    def test_zig_implements_struct(self):
        """Verify BunHasher.zig implements a Zig struct with required functions"""
        path = os.path.join(
            self.REPO_DIR, "src/bun.js/api/BunHasher.zig"
        )
        with open(path) as f:
            content = f.read()

        # Should define a struct
        assert "struct" in content, "BunHasher.zig should define a struct"

        # Should have public functions
        pub_fn_count = content.count("pub fn")
        assert pub_fn_count >= 3, (
            f"BunHasher.zig should expose at least 3 public functions. "
            f"Found {pub_fn_count}"
        )

    def test_zig_supports_multiple_algorithms(self):
        """Verify Zig implementation supports multiple hash algorithm variants"""
        path = os.path.join(
            self.REPO_DIR, "src/bun.js/api/BunHasher.zig"
        )
        with open(path) as f:
            content = f.read().lower()

        algorithms = ["sha256", "sha1", "md5", "sha512", "sha384", "blake"]
        found = [algo for algo in algorithms if algo in content]
        assert len(found) >= 2, (
            f"Zig implementation should support multiple hash algorithms. "
            f"Found: {found}. Expected at least 2."
        )

    def test_zig_handles_string_and_binary_input(self):
        """Verify Zig implementation accepts both string and binary inputs"""
        path = os.path.join(
            self.REPO_DIR, "src/bun.js/api/BunHasher.zig"
        )
        with open(path) as f:
            content = f.read()

        # Should reference string or slice types
        input_handling = [
            "JSValue", "String", "string", "slice", "Uint8Array",
            "ArrayBuffer", "bytes", "toSlice",
        ]
        found = [ind for ind in input_handling if ind in content]
        assert len(found) >= 2, (
            f"Zig implementation should handle string and binary inputs. "
            f"Found: {found}. Expected at least 2 of: {input_handling}"
        )

    def test_zig_has_finalizer(self):
        """Verify Zig implementation has a finalizer for memory cleanup"""
        path = os.path.join(
            self.REPO_DIR, "src/bun.js/api/BunHasher.zig"
        )
        with open(path) as f:
            content = f.read()

        finalize_indicators = [
            "finalize", "deinit", "destroy", "dealloc", "free",
        ]
        found = [ind for ind in finalize_indicators if ind in content]
        assert len(found) >= 1, (
            f"Zig implementation should have a finalizer for cleanup. "
            f"None of {finalize_indicators} found."
        )

    def test_zig_uses_jsc_interface_methods(self):
        """Verify Zig implementation integrates with JSC interface methods"""
        path = os.path.join(
            self.REPO_DIR, "src/bun.js/api/BunHasher.zig"
        )
        with open(path) as f:
            content = f.read()

        jsc_indicators = [
            "JSC", "JSValue", "JSGlobalObject", "callFrame",
            "globalObject", "toJS", "fromJS",
        ]
        found = [ind for ind in jsc_indicators if ind in content]
        assert len(found) >= 3, (
            f"Zig should integrate with JSC interface. "
            f"Found: {found}. Expected at least 3 of: {jsc_indicators}"
        )

    # === Functional Checks ===

    def test_classes_ts_has_valid_syntax(self):
        """Verify BunHasher.classes.ts has valid JavaScript/TypeScript syntax"""
        path = os.path.join(
            self.REPO_DIR, "src/bun.js/api/BunHasher.classes.ts"
        )
        result = subprocess.run(
            ["node", "--check", path],
            capture_output=True,
            text=True,
            timeout=30,
        )
        # .ts file may not parse with node directly, check for basic structure instead
        if result.returncode != 0:
            with open(path) as f:
                content = f.read()
            assert "export" in content or "define" in content, (
                "BunHasher.classes.ts should have valid structure"
            )

    def test_test_file_covers_algorithms(self):
        """Verify test file tests multiple hash algorithms"""
        path = os.path.join(self.REPO_DIR, "test/js/bun/hasher.test.ts")
        with open(path) as f:
            content = f.read().lower()

        algorithms = ["sha256", "sha1", "md5", "sha512"]
        found = [algo for algo in algorithms if algo in content]
        assert len(found) >= 2, (
            f"Test file should test multiple algorithms. Found: {found}"
        )

    def test_test_file_covers_input_types(self):
        """Verify test file tests various input types"""
        path = os.path.join(self.REPO_DIR, "test/js/bun/hasher.test.ts")
        with open(path) as f:
            content = f.read()

        input_types = {
            "empty_string": '""' in content or "empty" in content.lower(),
            "string_input": "string" in content.lower() or '"hello' in content.lower() or "'hello" in content.lower(),
            "binary_input": "Uint8Array" in content or "Buffer" in content or "binary" in content.lower(),
        }
        found = [k for k, v in input_types.items() if v]
        assert len(found) >= 2, (
            f"Test file should cover various input types. Found: {found}"
        )

    def test_test_file_verifies_determinism(self):
        """Verify test file checks deterministic output (same input = same hash)"""
        path = os.path.join(self.REPO_DIR, "test/js/bun/hasher.test.ts")
        with open(path) as f:
            content = f.read().lower()

        determinism_indicators = [
            "equal", "same", "deterministic", "consistent",
            "expect(", "tobe(", "toequal(",
        ]
        found = [ind for ind in determinism_indicators if ind in content]
        assert len(found) >= 2, (
            f"Test file should verify deterministic hash output. "
            f"Found: {found}"
        )
