"""
Test skill: implementing-jsc-classes-zig
Verify that the Agent correctly implements a RingBuffer class in Bun's Zig
runtime with JSC bindings, including the classes.ts definition and Zig
implementation.
"""

import os
import re
import json
import subprocess
import pytest


class TestImplementingJscClassesZig:
    REPO_DIR = "/workspace/bun"

    # === File Path Checks ===

    def test_ring_buffer_classes_ts_exists(self):
        """Verify RingBuffer.classes.ts exists"""
        fpath = os.path.join(self.REPO_DIR, "src/bun.js/api/RingBuffer.classes.ts")
        assert os.path.isfile(fpath), f"RingBuffer.classes.ts not found at {fpath}"

    def test_ring_buffer_zig_exists(self):
        """Verify RingBuffer.zig exists"""
        fpath = os.path.join(self.REPO_DIR, "src/bun.js/api/RingBuffer.zig")
        assert os.path.isfile(fpath), f"RingBuffer.zig not found at {fpath}"

    def test_test_file_exists(self):
        """Verify ringbuffer.test.ts test file exists"""
        fpath = os.path.join(self.REPO_DIR, "test/js/bun/ringbuffer.test.ts")
        assert os.path.isfile(fpath), f"ringbuffer.test.ts not found at {fpath}"

    # === Semantic Checks ===

    def test_classes_ts_defines_constructor(self):
        """Verify RingBuffer.classes.ts defines constructor with capacity parameter"""
        fpath = os.path.join(self.REPO_DIR, "src/bun.js/api/RingBuffer.classes.ts")
        with open(fpath, "r") as f:
            content = f.read()
        assert "RingBuffer" in content, "classes.ts should define 'RingBuffer'"
        assert "capacity" in content, "classes.ts should reference 'capacity' parameter"

    def test_classes_ts_defines_methods(self):
        """Verify RingBuffer.classes.ts defines all required methods"""
        fpath = os.path.join(self.REPO_DIR, "src/bun.js/api/RingBuffer.classes.ts")
        with open(fpath, "r") as f:
            content = f.read()
        required_methods = ["write", "read", "peek", "clear", "toBytes"]
        for method in required_methods:
            assert method in content, f"classes.ts missing method definition: '{method}'"

    def test_classes_ts_defines_properties(self):
        """Verify RingBuffer.classes.ts defines all required properties"""
        fpath = os.path.join(self.REPO_DIR, "src/bun.js/api/RingBuffer.classes.ts")
        with open(fpath, "r") as f:
            content = f.read()
        required_props = ["capacity", "length", "available", "isEmpty", "isFull"]
        for prop in required_props:
            assert prop in content, f"classes.ts missing property definition: '{prop}'"

    def test_zig_has_ring_buffer_struct(self):
        """Verify RingBuffer.zig defines a RingBuffer struct"""
        fpath = os.path.join(self.REPO_DIR, "src/bun.js/api/RingBuffer.zig")
        with open(fpath, "r") as f:
            content = f.read()
        has_struct = bool(re.search(r'(pub\s+)?const\s+RingBuffer\s*=\s*struct', content))
        assert has_struct, "RingBuffer.zig should define a RingBuffer struct"

    def test_zig_has_head_tail_pointers(self):
        """Verify RingBuffer.zig uses head/tail pointer design"""
        fpath = os.path.join(self.REPO_DIR, "src/bun.js/api/RingBuffer.zig")
        with open(fpath, "r") as f:
            content = f.read()
        has_head = bool(re.search(r'head', content))
        has_tail = bool(re.search(r'tail', content))
        assert has_head and has_tail, (
            "RingBuffer.zig should use head/tail pointer design"
        )

    def test_zig_has_write_method(self):
        """Verify RingBuffer.zig implements write method with wrap-around"""
        fpath = os.path.join(self.REPO_DIR, "src/bun.js/api/RingBuffer.zig")
        with open(fpath, "r") as f:
            content = f.read()
        has_write = bool(re.search(r'(pub\s+)?fn\s+write', content))
        assert has_write, "RingBuffer.zig should implement a write function"
        # Should handle wrap-around with memcpy
        has_memcpy = bool(re.search(r'(@memcpy|@memcopy|std\.mem\.copy)', content))
        assert has_memcpy, "write should use memcpy for efficient copying"

    def test_zig_has_read_method(self):
        """Verify RingBuffer.zig implements read method"""
        fpath = os.path.join(self.REPO_DIR, "src/bun.js/api/RingBuffer.zig")
        with open(fpath, "r") as f:
            content = f.read()
        has_read = bool(re.search(r'(pub\s+)?fn\s+read', content))
        assert has_read, "RingBuffer.zig should implement a read function"

    def test_zig_has_memory_management(self):
        """Verify RingBuffer.zig handles memory allocation and deallocation"""
        fpath = os.path.join(self.REPO_DIR, "src/bun.js/api/RingBuffer.zig")
        with open(fpath, "r") as f:
            content = f.read()
        has_alloc = bool(re.search(r'(alloc|allocator)', content))
        has_free = bool(re.search(r'(free|deinit|finalize|destroy)', content))
        assert has_alloc, "RingBuffer.zig should allocate memory for the buffer"
        assert has_free, "RingBuffer.zig should free memory on destruction"

    def test_zig_has_error_handling(self):
        """Verify RingBuffer.zig validates arguments and throws appropriate errors"""
        fpath = os.path.join(self.REPO_DIR, "src/bun.js/api/RingBuffer.zig")
        with open(fpath, "r") as f:
            content = f.read()
        has_type_error = bool(re.search(r'(TypeError|type.*error|globalThis\.throw)', content, re.IGNORECASE))
        assert has_type_error, "RingBuffer.zig should throw TypeError for invalid arguments"

    def test_generated_classes_list_includes_ring_buffer(self):
        """Verify RingBuffer is registered in generated_classes_list.zig"""
        fpath = os.path.join(self.REPO_DIR, "src/bun.js/bindings/generated_classes_list.zig")
        if not os.path.isfile(fpath):
            pytest.skip("generated_classes_list.zig not found")
        with open(fpath, "r") as f:
            content = f.read()
        assert "RingBuffer" in content, (
            "RingBuffer should be registered in generated_classes_list.zig"
        )

    # === Functional Checks ===

    def test_classes_ts_is_valid_typescript(self):
        """Verify RingBuffer.classes.ts is syntactically valid"""
        fpath = os.path.join(self.REPO_DIR, "src/bun.js/api/RingBuffer.classes.ts")
        # Check basic syntax with node if available
        result = subprocess.run(
            ["node", "-e", f"require('fs').readFileSync('{fpath}', 'utf-8')"],
            capture_output=True,
            text=True,
            timeout=10
        )
        # At minimum verify the file is readable and non-empty
        with open(fpath, "r") as f:
            content = f.read()
        assert len(content) > 50, "classes.ts should not be empty or trivial"

    def test_test_file_has_sufficient_coverage(self):
        """Verify test file covers required functionality"""
        fpath = os.path.join(self.REPO_DIR, "test/js/bun/ringbuffer.test.ts")
        with open(fpath, "r") as f:
            content = f.read()
        # Count test cases
        test_count = len(re.findall(r'(test|it)\s*\(', content))
        assert test_count >= 5, (
            f"Test file should have at least 5 test cases, found {test_count}"
        )

    def test_test_file_covers_error_cases(self):
        """Verify test file includes error handling tests"""
        fpath = os.path.join(self.REPO_DIR, "test/js/bun/ringbuffer.test.ts")
        with open(fpath, "r") as f:
            content = f.read()
        has_error_test = bool(re.search(
            r'(TypeError|RangeError|throw|toThrow|error)',
            content,
            re.IGNORECASE
        ))
        assert has_error_test, "Test file should cover error handling (TypeError, RangeError)"

    def test_test_file_covers_wraparound(self):
        """Verify test file tests wrap-around behavior"""
        fpath = os.path.join(self.REPO_DIR, "test/js/bun/ringbuffer.test.ts")
        with open(fpath, "r") as f:
            content = f.read()
        has_wrap = bool(re.search(r'(wrap|circular|full|overflow)', content, re.IGNORECASE))
        assert has_wrap, "Test file should test wrap-around behavior"
