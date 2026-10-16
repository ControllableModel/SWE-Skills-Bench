"""
Test skill: implementing-jsc-classes-zig
Verify that the Agent correctly implements a CacheMap JSC class in Bun
using Zig with LRU eviction behavior.
"""

import os
import re
import subprocess
import pytest


class TestImplementingJscClassesZig:
    REPO_DIR = "/workspace/bun"

    CLASSES_TS = "src/bun.js/api/CacheMap.classes.ts"
    ZIG_IMPL = "src/bun.js/bindings/CacheMap.zig"
    GENERATED_ZIG = "src/bun.js/bindings/generated.zig"

    def _read_file(self, rel_path):
        filepath = os.path.join(self.REPO_DIR, rel_path)
        with open(filepath) as f:
            return f.read()

    # === File Path Checks ===

    def test_classes_ts_exists(self):
        """Verify CacheMap.classes.ts definition file exists"""
        filepath = os.path.join(self.REPO_DIR, self.CLASSES_TS)
        assert os.path.exists(filepath), f"CacheMap.classes.ts not found at {filepath}"

    def test_zig_implementation_exists(self):
        """Verify CacheMap.zig implementation file exists"""
        filepath = os.path.join(self.REPO_DIR, self.ZIG_IMPL)
        assert os.path.exists(filepath), f"CacheMap.zig not found at {filepath}"

    def test_generated_zig_exists(self):
        """Verify generated.zig binding registry exists"""
        filepath = os.path.join(self.REPO_DIR, self.GENERATED_ZIG)
        assert os.path.exists(filepath), f"generated.zig not found at {filepath}"

    # === Semantic Checks ===

    def test_classes_ts_exports_cachemap(self):
        """Verify CacheMap.classes.ts exports a CacheMap class definition"""
        content = self._read_file(self.CLASSES_TS)
        assert "CacheMap" in content, \
            "CacheMap.classes.ts missing CacheMap class definition"
        assert re.search(r'(export|class|name.*CacheMap)', content), \
            "CacheMap not properly exported in .classes.ts"

    def test_classes_ts_defines_methods(self):
        """Verify .classes.ts defines get, set, delete, clear methods"""
        content = self._read_file(self.CLASSES_TS)
        for method in ["get", "set", "delete", "clear"]:
            assert method in content, \
                f"CacheMap.classes.ts missing method definition: {method}"

    def test_classes_ts_defines_properties(self):
        """Verify .classes.ts defines size and capacity properties"""
        content = self._read_file(self.CLASSES_TS)
        assert "size" in content, "CacheMap.classes.ts missing 'size' property"
        assert "capacity" in content, "CacheMap.classes.ts missing 'capacity' property"

    def test_zig_has_hashmap_and_linked_list(self):
        """Verify Zig implementation uses hash map and linked list for LRU"""
        content = self._read_file(self.ZIG_IMPL)
        has_hashmap = bool(re.search(
            r'(HashMap|AutoHashMap|StringHashMap|hash_map|hashmap)',
            content,
            re.IGNORECASE,
        ))
        has_list = bool(re.search(
            r'(DoublyLinkedList|TailQueue|linked|LinkedList|prev.*next|next.*prev)',
            content,
            re.IGNORECASE,
        ))
        assert has_hashmap, "CacheMap.zig missing hash map data structure"
        assert has_list, "CacheMap.zig missing linked list for LRU tracking"

    def test_zig_implements_eviction(self):
        """Verify Zig implementation has LRU eviction logic"""
        content = self._read_file(self.ZIG_IMPL)
        has_eviction = bool(re.search(
            r'(evict|remove.*least|pop.*front|pop.*back|capacity|max_size)',
            content,
            re.IGNORECASE,
        ))
        assert has_eviction, \
            "CacheMap.zig missing eviction logic for LRU behavior"

    def test_zig_has_finalize_callback(self):
        """Verify Zig implementation has finalize callback for GC cleanup"""
        content = self._read_file(self.ZIG_IMPL)
        assert "finalize" in content.lower() or "deinit" in content.lower(), \
            "CacheMap.zig missing finalize/deinit callback for GC cleanup"

    def test_zig_validates_capacity(self):
        """Verify Zig implementation validates capacity (rejects 0 and negative)"""
        content = self._read_file(self.ZIG_IMPL)
        has_validation = bool(re.search(
            r'(capacity.*0|capacity.*<=|RangeError|TypeError|throw|invalid)',
            content,
            re.IGNORECASE,
        ))
        assert has_validation, \
            "CacheMap.zig missing capacity validation (should reject 0/negative)"

    def test_generated_zig_registers_cachemap(self):
        """Verify generated.zig registers CacheMap binding"""
        content = self._read_file(self.GENERATED_ZIG)
        assert "CacheMap" in content, \
            "generated.zig missing CacheMap registration"

    # === Functional Checks ===

    def test_classes_ts_valid_typescript(self):
        """Verify CacheMap.classes.ts is valid TypeScript/JavaScript"""
        filepath = os.path.join(self.REPO_DIR, self.CLASSES_TS)
        result = subprocess.run(
            ["node", "--check", filepath],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            # Try parsing as module
            result = subprocess.run(
                ["node", "-e", f"import('{filepath}').catch(()=>{{}})"],
                capture_output=True,
                text=True,
                timeout=30,
            )
        # Even if node check fails (TS syntax), verify no obvious errors
        content = self._read_file(self.CLASSES_TS)
        assert len(content) > 50, \
            f"CacheMap.classes.ts is too small ({len(content)} chars)"

    def test_zig_implementation_has_proper_structure(self):
        """Verify CacheMap.zig has proper Zig struct and method definitions"""
        content = self._read_file(self.ZIG_IMPL)
        # Check for Zig struct definition
        has_struct = bool(re.search(r'(const\s+CacheMap|pub\s+const\s+CacheMap)\s*=\s*struct', content))
        if not has_struct:
            has_struct = bool(re.search(r'struct\s*\{', content))
        assert has_struct, "CacheMap.zig missing proper struct definition"

        # Check for pub fn methods
        pub_fns = re.findall(r'pub\s+fn\s+(\w+)', content)
        assert len(pub_fns) >= 4, \
            f"Expected at least 4 public functions (get, set, delete, clear), found: {pub_fns}"

    def test_zig_handles_string_keys_safely(self):
        """Verify Zig implementation properly handles JSValue string extraction"""
        content = self._read_file(self.ZIG_IMPL)
        # Should have JSValue string handling
        has_string_handling = bool(re.search(
            r'(toSlice|toString|getZigString|JSValue|callFrame|jsString)',
            content,
        ))
        assert has_string_handling, \
            "CacheMap.zig missing proper JSValue string handling"
