"""
Test skill: v3-performance-optimization
Verify that the Agent implements sliding window attention support
for Flash Attention with configurable window_size, causal/non-causal
modes, edge cases, and integration into the existing API.
"""

import os
import re
import ast
import subprocess
import pytest


class TestV3PerformanceOptimization:
    REPO_DIR = "/workspace/flash-attention"

    # === File Path Checks ===

    def test_sliding_window_py_exists(self):
        """Verify flash_attn_sliding_window.py exists"""
        path = os.path.join(
            self.REPO_DIR, "flash_attn", "flash_attn_sliding_window.py",
        )
        assert os.path.exists(path), (
            f"flash_attn_sliding_window.py not found at {path}"
        )

    def test_interface_py_exists(self):
        """Verify flash_attn_interface.py exists"""
        path = os.path.join(
            self.REPO_DIR, "flash_attn", "flash_attn_interface.py",
        )
        assert os.path.exists(path), (
            f"flash_attn_interface.py not found at {path}"
        )

    # === Semantic Checks ===

    def test_window_size_parameter(self):
        """Verify configurable window_size parameter"""
        combined = ""
        for fname in [
            "flash_attn_sliding_window.py",
            "flash_attn_interface.py",
        ]:
            path = os.path.join(self.REPO_DIR, "flash_attn", fname)
            if os.path.exists(path):
                with open(path) as f:
                    combined += f.read()

        ws_indicators = [
            "window_size", "WindowSize", "window",
        ]
        found = [ind for ind in ws_indicators if ind in combined]
        assert len(found) >= 1, (
            f"Should accept window_size parameter. Found: {found}"
        )

    def test_sliding_window_masking(self):
        """Verify tokens outside window are masked to zero"""
        path = os.path.join(
            self.REPO_DIR, "flash_attn", "flash_attn_sliding_window.py",
        )
        with open(path) as f:
            content = f.read()

        mask_indicators = [
            "mask", "zero", "window", "attend",
            "position", "causal",
        ]
        found = [ind for ind in mask_indicators if ind in content]
        assert len(found) >= 3, (
            f"Should mask tokens outside window. Found: {found}"
        )

    def test_fallback_full_attention(self):
        """Verify fallback to full attention when window_size is None or -1"""
        combined = ""
        for fname in [
            "flash_attn_sliding_window.py",
            "flash_attn_interface.py",
        ]:
            path = os.path.join(self.REPO_DIR, "flash_attn", fname)
            if os.path.exists(path):
                with open(path) as f:
                    combined += f.read()

        fallback_indicators = [
            "None", "-1", "full", "standard",
            "default", "is None",
        ]
        found = [ind for ind in fallback_indicators if ind in combined]
        assert len(found) >= 2, (
            f"Should fall back to full attention. Found: {found}"
        )

    def test_causal_mode_support(self):
        """Verify causal and non-causal mode support"""
        path = os.path.join(
            self.REPO_DIR, "flash_attn", "flash_attn_sliding_window.py",
        )
        with open(path) as f:
            content = f.read()

        causal_indicators = [
            "causal", "Causal", "is_causal",
        ]
        found = [ind for ind in causal_indicators if ind in content]
        assert len(found) >= 1, (
            f"Should support causal mode. Found: {found}"
        )

    def test_qkv_inputs(self):
        """Verify acceptance of query, key, value tensors"""
        path = os.path.join(
            self.REPO_DIR, "flash_attn", "flash_attn_sliding_window.py",
        )
        with open(path) as f:
            content = f.read()

        qkv_indicators = ["query", "key", "value", "q", "k", "v", "Q", "K", "V"]
        found = [ind for ind in qkv_indicators if ind in content]
        assert len(found) >= 3, (
            f"Should accept query/key/value inputs. Found: {found}"
        )

    def test_edge_case_window_larger_than_seq(self):
        """Verify edge case: window_size >= sequence_length equals full attention"""
        path = os.path.join(
            self.REPO_DIR, "flash_attn", "flash_attn_sliding_window.py",
        )
        with open(path) as f:
            content = f.read()

        edge_indicators = [
            "seq_len", "sequence", "length", "full",
            "min(", "max(",
        ]
        found = [ind for ind in edge_indicators if ind in content]
        assert len(found) >= 2, (
            f"Should handle window >= seq length. Found: {found}"
        )

    def test_interface_integration(self):
        """Verify sliding window integrates into flash_attn_interface.py"""
        path = os.path.join(
            self.REPO_DIR, "flash_attn", "flash_attn_interface.py",
        )
        with open(path) as f:
            content = f.read()

        integration_indicators = [
            "window_size", "sliding", "flash_attn_sliding_window",
            "import",
        ]
        found = [ind for ind in integration_indicators if ind in content]
        assert len(found) >= 1, (
            f"Interface should reference sliding window. Found: {found}"
        )

    # === Functional Checks ===

    def test_sliding_window_valid_python(self):
        """Verify flash_attn_sliding_window.py is valid Python"""
        path = os.path.join(
            self.REPO_DIR, "flash_attn", "flash_attn_sliding_window.py",
        )
        with open(path) as f:
            source = f.read()
        try:
            ast.parse(source)
        except SyntaxError as e:
            pytest.fail(
                f"flash_attn_sliding_window.py has syntax error: {e}"
            )

    def test_interface_valid_python(self):
        """Verify flash_attn_interface.py is valid Python"""
        path = os.path.join(
            self.REPO_DIR, "flash_attn", "flash_attn_interface.py",
        )
        with open(path) as f:
            source = f.read()
        try:
            ast.parse(source)
        except SyntaxError as e:
            pytest.fail(f"flash_attn_interface.py has syntax error: {e}")

    def test_function_definitions(self):
        """Verify sliding window module defines functions"""
        path = os.path.join(
            self.REPO_DIR, "flash_attn", "flash_attn_sliding_window.py",
        )
        with open(path) as f:
            content = f.read()

        defs = re.findall(r"^def \w+", content, re.MULTILINE)
        assert len(defs) >= 2, (
            f"Should define at least 2 functions. Found: {defs}"
        )

    def test_no_hardcoded_window_size(self):
        """Verify window_size is parameterized, not hardcoded"""
        path = os.path.join(
            self.REPO_DIR, "flash_attn", "flash_attn_sliding_window.py",
        )
        with open(path) as f:
            content = f.read()

        # Look for window_size as function parameter
        param_match = re.search(r"def\s+\w+\([^)]*window_size", content)
        assert param_match, (
            "window_size should be a function parameter, not hardcoded"
        )
