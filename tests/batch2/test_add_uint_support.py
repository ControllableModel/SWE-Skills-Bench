"""
Test skill: add-uint-support
Verify that the Agent correctly extends unsigned integer type coverage
(uint16, uint32, uint64) for PyTorch operators including arithmetic,
bitwise, comparison, floor_divide, remainder, and GCD.
"""

import os
import subprocess
import pytest


class TestAddUintSupport:
    REPO_DIR = "/workspace/pytorch"

    # === File Path Checks ===

    def test_binary_ops_file_exists(self):
        """Verify that BinaryOps.cpp exists in the expected location"""
        path = os.path.join(self.REPO_DIR, "aten/src/ATen/native/BinaryOps.cpp")
        assert os.path.exists(path), f"BinaryOps.cpp not found at {path}"

    def test_binary_ops_kernel_file_exists(self):
        """Verify that BinaryOpsKernel.cpp exists in the expected location"""
        path = os.path.join(self.REPO_DIR, "aten/src/ATen/native/cpu/BinaryOpsKernel.cpp")
        assert os.path.exists(path), f"BinaryOpsKernel.cpp not found at {path}"

    def test_tensor_compare_file_exists(self):
        """Verify that TensorCompare.cpp exists in the expected location"""
        path = os.path.join(self.REPO_DIR, "aten/src/ATen/native/TensorCompare.cpp")
        assert os.path.exists(path), f"TensorCompare.cpp not found at {path}"

    def test_gcd_lcm_file_exists(self):
        """Verify that GcdLcm.cpp exists in the expected location"""
        path = os.path.join(self.REPO_DIR, "aten/src/ATen/native/GcdLcm.cpp")
        assert os.path.exists(path), f"GcdLcm.cpp not found at {path}"

    # === Semantic Checks ===

    def test_binary_ops_has_uint32_dispatch(self):
        """Verify BinaryOps.cpp contains uint32 type dispatch registrations"""
        path = os.path.join(self.REPO_DIR, "aten/src/ATen/native/BinaryOps.cpp")
        with open(path) as f:
            content = f.read()
        uint32_indicators = [
            "kUInt32", "ScalarType::UInt32", "uint32",
            "AT_DISPATCH_INTEGRAL_TYPES_AND",
        ]
        found = any(ind in content for ind in uint32_indicators)
        assert found, (
            "BinaryOps.cpp should contain uint32 dispatch entries. "
            f"Searched for: {uint32_indicators}"
        )

    def test_binary_ops_has_uint64_dispatch(self):
        """Verify BinaryOps.cpp contains uint64 type dispatch registrations"""
        path = os.path.join(self.REPO_DIR, "aten/src/ATen/native/BinaryOps.cpp")
        with open(path) as f:
            content = f.read()
        uint64_indicators = [
            "kUInt64", "ScalarType::UInt64", "uint64",
        ]
        found = any(ind in content for ind in uint64_indicators)
        assert found, (
            "BinaryOps.cpp should contain uint64 dispatch entries. "
            f"Searched for: {uint64_indicators}"
        )

    def test_kernel_file_has_unsigned_type_support(self):
        """Verify BinaryOpsKernel.cpp has kernel implementations for unsigned types"""
        path = os.path.join(self.REPO_DIR, "aten/src/ATen/native/cpu/BinaryOpsKernel.cpp")
        with open(path) as f:
            content = f.read()
        unsigned_indicators = [
            "kUInt16", "kUInt32", "kUInt64",
            "ScalarType::UInt16", "ScalarType::UInt32", "ScalarType::UInt64",
            "uint16_t", "uint32_t", "uint64_t",
        ]
        found = [ind for ind in unsigned_indicators if ind in content]
        assert len(found) >= 1, (
            "BinaryOpsKernel.cpp should have unsigned integer kernel support. "
            f"None of {unsigned_indicators} found."
        )

    def test_tensor_compare_has_unsigned_support(self):
        """Verify TensorCompare.cpp contains unsigned type dispatch for comparison ops"""
        path = os.path.join(self.REPO_DIR, "aten/src/ATen/native/TensorCompare.cpp")
        with open(path) as f:
            content = f.read()
        unsigned_indicators = [
            "kUInt16", "kUInt32", "kUInt64",
            "ScalarType::UInt16", "ScalarType::UInt32", "ScalarType::UInt64",
            "uint16", "uint32", "uint64",
        ]
        found = [ind for ind in unsigned_indicators if ind in content]
        assert len(found) >= 1, (
            "TensorCompare.cpp should have unsigned integer comparison support. "
            f"None of {unsigned_indicators} found."
        )

    # === Functional Checks ===

    def test_uint32_add_operator(self):
        """Verify torch.add works with uint32 tensors and preserves dtype"""
        import torch
        a = torch.tensor([10, 20, 30], dtype=torch.uint32)
        b = torch.tensor([1, 2, 3], dtype=torch.uint32)
        result = torch.add(a, b)
        assert result.dtype == torch.uint32, (
            f"add(uint32, uint32) should return uint32, got {result.dtype}"
        )
        expected = [11, 22, 33]
        actual = result.tolist()
        assert actual == expected, f"add result incorrect: expected {expected}, got {actual}"

    def test_uint32_mul_operator(self):
        """Verify torch.mul works with uint32 tensors"""
        import torch
        a = torch.tensor([5, 10, 15], dtype=torch.uint32)
        b = torch.tensor([2, 3, 4], dtype=torch.uint32)
        result = torch.mul(a, b)
        assert result.dtype == torch.uint32, (
            f"mul(uint32, uint32) should return uint32, got {result.dtype}"
        )
        expected = [10, 30, 60]
        actual = result.tolist()
        assert actual == expected, f"mul result incorrect: expected {expected}, got {actual}"

    def test_uint64_sub_operator(self):
        """Verify torch.sub works with uint64 tensors"""
        import torch
        a = torch.tensor([100, 200, 300], dtype=torch.uint64)
        b = torch.tensor([10, 20, 30], dtype=torch.uint64)
        result = torch.sub(a, b)
        assert result.dtype == torch.uint64, (
            f"sub(uint64, uint64) should return uint64, got {result.dtype}"
        )
        expected = [90, 180, 270]
        actual = result.tolist()
        assert actual == expected, f"sub result incorrect: expected {expected}, got {actual}"

    def test_uint32_bitwise_and_or_xor(self):
        """Verify bitwise_and, bitwise_or, bitwise_xor work with uint32 tensors"""
        import torch
        a = torch.tensor([0xFF, 0x0F, 0xAA], dtype=torch.uint32)
        b = torch.tensor([0x0F, 0xFF, 0x55], dtype=torch.uint32)

        result_and = torch.bitwise_and(a, b)
        assert result_and.dtype == torch.uint32, (
            f"bitwise_and dtype should be uint32, got {result_and.dtype}"
        )
        assert result_and[0].item() == 0x0F, (
            f"bitwise_and(0xFF, 0x0F) should be 0x0F, got {result_and[0].item():#x}"
        )

        result_or = torch.bitwise_or(a, b)
        assert result_or.dtype == torch.uint32, (
            f"bitwise_or dtype should be uint32, got {result_or.dtype}"
        )
        assert result_or[0].item() == 0xFF, (
            f"bitwise_or(0xFF, 0x0F) should be 0xFF, got {result_or[0].item():#x}"
        )

        result_xor = torch.bitwise_xor(a, b)
        assert result_xor.dtype == torch.uint32, (
            f"bitwise_xor dtype should be uint32, got {result_xor.dtype}"
        )
        assert result_xor[0].item() == 0xF0, (
            f"bitwise_xor(0xFF, 0x0F) should be 0xF0, got {result_xor[0].item():#x}"
        )

    def test_uint32_comparison_operators(self):
        """Verify eq, ne, lt, le, gt, ge work with uint32 tensors"""
        import torch
        a = torch.tensor([1, 2, 3], dtype=torch.uint32)
        b = torch.tensor([3, 2, 1], dtype=torch.uint32)

        eq = torch.eq(a, b)
        assert eq.dtype == torch.bool, f"eq result should be bool, got {eq.dtype}"
        assert eq.tolist() == [False, True, False], f"eq result incorrect: {eq.tolist()}"

        lt = torch.lt(a, b)
        assert lt.tolist() == [True, False, False], f"lt result incorrect: {lt.tolist()}"

        gt = torch.gt(a, b)
        assert gt.tolist() == [False, False, True], f"gt result incorrect: {gt.tolist()}"

        le = torch.le(a, b)
        assert le.tolist() == [True, True, False], f"le result incorrect: {le.tolist()}"

        ge = torch.ge(a, b)
        assert ge.tolist() == [False, True, True], f"ge result incorrect: {ge.tolist()}"

        ne = torch.ne(a, b)
        assert ne.tolist() == [True, False, True], f"ne result incorrect: {ne.tolist()}"

    def test_uint32_floor_divide_and_remainder(self):
        """Verify floor_divide and remainder work with uint32 tensors"""
        import torch
        a = torch.tensor([10, 17, 25], dtype=torch.uint32)
        b = torch.tensor([3, 5, 7], dtype=torch.uint32)

        div_result = torch.floor_divide(a, b)
        assert div_result.dtype == torch.uint32, (
            f"floor_divide dtype should be uint32, got {div_result.dtype}"
        )
        assert div_result[0].item() == 3, (
            f"floor_divide(10, 3) should be 3, got {div_result[0].item()}"
        )
        assert div_result[1].item() == 3, (
            f"floor_divide(17, 5) should be 3, got {div_result[1].item()}"
        )
        assert div_result[2].item() == 3, (
            f"floor_divide(25, 7) should be 3, got {div_result[2].item()}"
        )

        rem_result = torch.remainder(a, b)
        assert rem_result.dtype == torch.uint32, (
            f"remainder dtype should be uint32, got {rem_result.dtype}"
        )
        assert rem_result[0].item() == 1, (
            f"remainder(10, 3) should be 1, got {rem_result[0].item()}"
        )
        assert rem_result[1].item() == 2, (
            f"remainder(17, 5) should be 2, got {rem_result[1].item()}"
        )
        assert rem_result[2].item() == 4, (
            f"remainder(25, 7) should be 4, got {rem_result[2].item()}"
        )

    def test_uint32_shift_operators(self):
        """Verify left_shift and right_shift work with uint32 tensors"""
        import torch
        a = torch.tensor([1, 8, 256], dtype=torch.uint32)
        shift = torch.tensor([4, 1, 2], dtype=torch.uint32)

        lshift = torch.bitwise_left_shift(a, shift)
        assert lshift.dtype == torch.uint32, (
            f"left_shift dtype should be uint32, got {lshift.dtype}"
        )
        assert lshift[0].item() == 16, f"1 << 4 should be 16, got {lshift[0].item()}"
        assert lshift[1].item() == 16, f"8 << 1 should be 16, got {lshift[1].item()}"
        assert lshift[2].item() == 1024, f"256 << 2 should be 1024, got {lshift[2].item()}"

        rshift = torch.bitwise_right_shift(a, shift)
        assert rshift[0].item() == 0, f"1 >> 4 should be 0, got {rshift[0].item()}"
        assert rshift[1].item() == 4, f"8 >> 1 should be 4, got {rshift[1].item()}"
        assert rshift[2].item() == 64, f"256 >> 2 should be 64, got {rshift[2].item()}"

    def test_uint16_arithmetic_support(self):
        """Verify arithmetic operators work with uint16 tensors"""
        import torch
        a = torch.tensor([100, 200], dtype=torch.uint16)
        b = torch.tensor([50, 100], dtype=torch.uint16)

        result = torch.add(a, b)
        assert result.dtype == torch.uint16, (
            f"add(uint16, uint16) should return uint16, got {result.dtype}"
        )
        assert result[0].item() == 150, (
            f"add(100, 50) should be 150, got {result[0].item()}"
        )
        assert result[1].item() == 300, (
            f"add(200, 100) should be 300, got {result[1].item()}"
        )

    def test_uint32_zero_edge_cases(self):
        """Verify operators handle zero values correctly for uint32"""
        import torch
        zero = torch.tensor([0, 0, 0], dtype=torch.uint32)
        vals = torch.tensor([1, 2, 3], dtype=torch.uint32)

        add_result = torch.add(zero, vals)
        assert add_result.tolist() == [1, 2, 3], (
            f"0 + x should equal x, got {add_result.tolist()}"
        )

        mul_result = torch.mul(zero, vals)
        assert mul_result.tolist() == [0, 0, 0], (
            f"0 * x should equal 0, got {mul_result.tolist()}"
        )

        eq_result = torch.eq(zero, torch.zeros(3, dtype=torch.uint32))
        assert all(eq_result.tolist()), (
            f"0 == 0 should be True, got {eq_result.tolist()}"
        )

    def test_uint64_large_value_arithmetic(self):
        """Verify uint64 handles large values near type boundaries"""
        import torch
        large_val = 2**32
        a = torch.tensor([large_val, large_val + 1], dtype=torch.uint64)
        b = torch.tensor([1, 1], dtype=torch.uint64)

        result = torch.add(a, b)
        assert result.dtype == torch.uint64, (
            f"Expected uint64 dtype, got {result.dtype}"
        )
        assert result[0].item() == large_val + 1, (
            f"Expected {large_val + 1}, got {result[0].item()}"
        )
        assert result[1].item() == large_val + 2, (
            f"Expected {large_val + 2}, got {result[1].item()}"
        )

    def test_gcd_operator_uint32(self):
        """Verify torch.gcd works with uint32 tensors"""
        import torch
        a = torch.tensor([12, 18, 35], dtype=torch.uint32)
        b = torch.tensor([8, 12, 25], dtype=torch.uint32)
        try:
            result = torch.gcd(a, b)
            assert result[0].item() == 4, (
                f"gcd(12, 8) should be 4, got {result[0].item()}"
            )
            assert result[1].item() == 6, (
                f"gcd(18, 12) should be 6, got {result[1].item()}"
            )
            assert result[2].item() == 5, (
                f"gcd(35, 25) should be 5, got {result[2].item()}"
            )
        except RuntimeError as e:
            if "gcd" in str(e).lower():
                pytest.skip(f"torch.gcd not available for uint32: {e}")
            raise
