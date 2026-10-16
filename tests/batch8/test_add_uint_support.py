"""
Test skill: add-uint-support
Verify that the Agent correctly restores uint32/uint64 operator support in PyTorch,
including reduction, comparison, clamping, conditional, and bitwise operators.
"""

import os
import subprocess
import sys
import ast
import pytest


class TestAddUintSupport:
    REPO_DIR = "/workspace/pytorch"

    # === File Path Checks ===

    def test_reduce_ops_file_exists(self):
        """Verify that ReduceOps.cpp exists at the expected path"""
        filepath = os.path.join(self.REPO_DIR, "aten/src/ATen/native/ReduceOps.cpp")
        assert os.path.exists(filepath), f"ReduceOps.cpp not found at {filepath}"

    def test_tensor_compare_file_exists(self):
        """Verify that TensorCompare.cpp exists at the expected path"""
        filepath = os.path.join(self.REPO_DIR, "aten/src/ATen/native/TensorCompare.cpp")
        assert os.path.exists(filepath), f"TensorCompare.cpp not found at {filepath}"

    def test_binary_ops_kernel_file_exists(self):
        """Verify that BinaryOpsKernel.cpp exists at the expected path"""
        filepath = os.path.join(self.REPO_DIR, "aten/src/ATen/native/cpu/BinaryOpsKernel.cpp")
        assert os.path.exists(filepath), f"BinaryOpsKernel.cpp not found at {filepath}"

    # === Semantic Checks ===

    def test_reduce_ops_uses_unsigned_dispatch(self):
        """Verify ReduceOps.cpp contains dispatch macros for unsigned integer types"""
        filepath = os.path.join(self.REPO_DIR, "aten/src/ATen/native/ReduceOps.cpp")
        with open(filepath) as f:
            content = f.read()
        # Should use AT_DISPATCH_V2 or AT_BAREBONES_UNSIGNED_TYPES or AT_INTEGRAL_TYPES_V2
        has_unsigned = (
            "AT_BAREBONES_UNSIGNED_TYPES" in content
            or "AT_INTEGRAL_TYPES_V2" in content
            or ("AT_DISPATCH_V2" in content and ("kUInt32" in content or "kUInt16" in content or "Unsigned" in content.replace(" ", "")))
        )
        assert has_unsigned, (
            "ReduceOps.cpp does not contain unsigned integer dispatch macros. "
            "Expected AT_BAREBONES_UNSIGNED_TYPES, AT_INTEGRAL_TYPES_V2, or AT_DISPATCH_V2 with unsigned types."
        )

    def test_tensor_compare_uses_unsigned_dispatch(self):
        """Verify TensorCompare.cpp contains dispatch macros for unsigned integer types"""
        filepath = os.path.join(self.REPO_DIR, "aten/src/ATen/native/TensorCompare.cpp")
        with open(filepath) as f:
            content = f.read()
        has_unsigned = (
            "AT_BAREBONES_UNSIGNED_TYPES" in content
            or "AT_INTEGRAL_TYPES_V2" in content
            or ("AT_DISPATCH_V2" in content and ("kUInt32" in content or "kUInt16" in content or "Unsigned" in content.replace(" ", "")))
        )
        assert has_unsigned, (
            "TensorCompare.cpp does not contain unsigned integer dispatch macros."
        )

    def test_binary_ops_kernel_uses_unsigned_dispatch(self):
        """Verify BinaryOpsKernel.cpp contains dispatch macros for unsigned integer types"""
        filepath = os.path.join(self.REPO_DIR, "aten/src/ATen/native/cpu/BinaryOpsKernel.cpp")
        with open(filepath) as f:
            content = f.read()
        has_unsigned = (
            "AT_BAREBONES_UNSIGNED_TYPES" in content
            or "AT_INTEGRAL_TYPES_V2" in content
            or ("AT_DISPATCH_V2" in content and ("kUInt32" in content or "kUInt16" in content or "Unsigned" in content.replace(" ", "")))
        )
        assert has_unsigned, (
            "BinaryOpsKernel.cpp does not contain unsigned integer dispatch macros."
        )

    def test_dispatch_v2_macro_format(self):
        """Verify that modified files use AT_DISPATCH_V2 macro format, not legacy AT_DISPATCH_ALL_TYPES"""
        files_to_check = [
            "aten/src/ATen/native/ReduceOps.cpp",
            "aten/src/ATen/native/TensorCompare.cpp",
            "aten/src/ATen/native/cpu/BinaryOpsKernel.cpp",
        ]
        for relpath in files_to_check:
            filepath = os.path.join(self.REPO_DIR, relpath)
            if not os.path.exists(filepath):
                continue
            with open(filepath) as f:
                content = f.read()
            # Files should have AT_DISPATCH_V2 or the unsigned type group macros
            assert "AT_DISPATCH_V2" in content or "AT_BAREBONES_UNSIGNED_TYPES" in content or "AT_INTEGRAL_TYPES_V2" in content, (
                f"{relpath} does not use AT_DISPATCH_V2 or V2-compatible unsigned type macros. "
                "Legacy AT_DISPATCH_ALL_TYPES should have been migrated."
            )

    # === Functional Checks ===

    def test_min_uint32_basic(self):
        """Verify torch.min works on uint32 tensors with correct result"""
        try:
            import torch
        except ImportError:
            pytest.skip("PyTorch not installed")

        t = torch.tensor([3, 1, 2], dtype=torch.uint32)
        result = torch.min(t)
        assert result.item() == 1, f"Expected min=1, got {result.item()}"
        assert result.dtype == torch.uint32, f"Expected dtype uint32, got {result.dtype}"

    def test_max_uint32_large_value(self):
        """Verify torch.max handles large uint32 values (2^32 - 1) without wrap"""
        try:
            import torch
        except ImportError:
            pytest.skip("PyTorch not installed")

        t = torch.tensor([0, 4294967295], dtype=torch.uint32)
        result = torch.max(t)
        assert result.item() == 4294967295, (
            f"Expected max=4294967295 (2^32-1), got {result.item()}. "
            "Large unsigned values may be misinterpreted as negative."
        )

    def test_min_dim_reduction_uint32(self):
        """Verify torch.min with dim argument returns correct values and indices for uint32"""
        try:
            import torch
        except ImportError:
            pytest.skip("PyTorch not installed")

        t = torch.tensor([[3, 1], [5, 2]], dtype=torch.uint32)
        values, indices = torch.min(t, dim=1)
        assert values.tolist() == [1, 2], f"Expected values [1, 2], got {values.tolist()}"
        assert indices.tolist() == [1, 1], f"Expected indices [1, 1], got {indices.tolist()}"
        assert values.dtype == torch.uint32, f"Expected dtype uint32, got {values.dtype}"

    def test_clamp_uint16(self):
        """Verify torch.clamp works on uint16 tensors"""
        try:
            import torch
        except ImportError:
            pytest.skip("PyTorch not installed")

        t = torch.tensor([0, 500, 1000], dtype=torch.uint16)
        result = torch.clamp(t, min=100, max=800)
        assert result.tolist() == [100, 500, 800], (
            f"Expected [100, 500, 800], got {result.tolist()}"
        )
        assert result.dtype == torch.uint16, f"Expected dtype uint16, got {result.dtype}"

    def test_clamp_min_uint32_noop(self):
        """Verify torch.clamp_min(t, 0) on uint32 is a no-op since unsigned values are non-negative"""
        try:
            import torch
        except ImportError:
            pytest.skip("PyTorch not installed")

        t = torch.tensor([5, 10, 0], dtype=torch.uint32)
        result = torch.clamp_min(t, 0)
        assert result.tolist() == [5, 10, 0], (
            f"Expected [5, 10, 0], got {result.tolist()}"
        )

    def test_clamp_max_uint16(self):
        """Verify torch.clamp_max on uint16 correctly clamps values exceeding limit"""
        try:
            import torch
        except ImportError:
            pytest.skip("PyTorch not installed")

        t = torch.tensor([100, 255, 300, 0], dtype=torch.uint16)
        result = torch.clamp_max(t, 255)
        assert result.tolist() == [100, 255, 255, 0], (
            f"Expected [100, 255, 255, 0], got {result.tolist()}"
        )

    def test_where_uint64(self):
        """Verify torch.where works with uint64 tensors and preserves dtype"""
        try:
            import torch
        except ImportError:
            pytest.skip("PyTorch not installed")

        cond = torch.tensor([True, False, True])
        x = torch.tensor([10, 20, 30], dtype=torch.uint64)
        y = torch.tensor([40, 50, 60], dtype=torch.uint64)
        result = torch.where(cond, x, y)
        assert result.tolist() == [10, 50, 30], f"Expected [10, 50, 30], got {result.tolist()}"
        assert result.dtype == torch.uint64, f"Expected dtype uint64, got {result.dtype}"

    def test_bitwise_and_uint16(self):
        """Verify torch.bitwise_and on uint16 tensors produces correct bit-level result"""
        try:
            import torch
        except ImportError:
            pytest.skip("PyTorch not installed")

        a = torch.tensor([0xFF00], dtype=torch.uint16)
        b = torch.tensor([0x0F0F], dtype=torch.uint16)
        result = torch.bitwise_and(a, b)
        assert result.item() == 0x0F00, (
            f"Expected 0x0F00 (3840), got {result.item()} (0x{result.item():04X})"
        )

    def test_bitwise_or_uint32(self):
        """Verify torch.bitwise_or on uint32 tensors"""
        try:
            import torch
        except ImportError:
            pytest.skip("PyTorch not installed")

        a = torch.tensor([0xF0F0F0F0], dtype=torch.uint32)
        b = torch.tensor([0x0F0F0F0F], dtype=torch.uint32)
        result = torch.bitwise_or(a, b)
        assert result.item() == 0xFFFFFFFF, (
            f"Expected 0xFFFFFFFF, got 0x{result.item():08X}"
        )

    def test_bitwise_xor_uint64(self):
        """Verify torch.bitwise_xor on uint64 tensors"""
        try:
            import torch
        except ImportError:
            pytest.skip("PyTorch not installed")

        a = torch.tensor([0xFF], dtype=torch.uint64)
        b = torch.tensor([0x0F], dtype=torch.uint64)
        result = torch.bitwise_xor(a, b)
        assert result.item() == 0xF0, (
            f"Expected 0xF0 (240), got {result.item()} (0x{result.item():02X})"
        )

    def test_bitwise_and_scalar_tensor_uint32(self):
        """Verify scalar-tensor bitwise_and on uint32 tensors"""
        try:
            import torch
        except ImportError:
            pytest.skip("PyTorch not installed")

        t = torch.tensor([0xABCD1234], dtype=torch.uint32)
        result = torch.bitwise_and(t, 0xFF)
        assert result.item() == 0x34, (
            f"Expected 0x34 (52), got {result.item()} (0x{result.item():02X})"
        )

    def test_max_uint64_boundary(self):
        """Verify torch.max handles uint64 maximum value (2^64-1) correctly"""
        try:
            import torch
        except ImportError:
            pytest.skip("PyTorch not installed")

        max_val = 2**64 - 1
        t = torch.tensor([0, max_val], dtype=torch.uint64)
        result = torch.max(t)
        assert result.item() == max_val, (
            f"Expected max={max_val}, got {result.item()}. "
            "Large uint64 value may have been misinterpreted."
        )
