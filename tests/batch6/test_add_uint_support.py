"""
Test skill: add-uint-support
Verify that the Agent correctly adds unsigned integer (uint16, uint32, uint64)
support to PyTorch bitwise and comparison operators on CPU (and CUDA dispatch macros).
"""

import os
import re
import subprocess
import pytest


class TestAddUintSupport:
    REPO_DIR = "/workspace/pytorch"

    # === File Path Checks ===

    def test_binary_ops_kernel_cpp_exists(self):
        """Verify that the CPU BinaryOpsKernel.cpp file exists"""
        path = os.path.join(self.REPO_DIR, "aten/src/ATen/native/cpu/BinaryOpsKernel.cpp")
        assert os.path.exists(path), f"BinaryOpsKernel.cpp not found at {path}"

    def test_unary_ops_kernel_cpp_exists(self):
        """Verify that the CPU UnaryOpsKernel.cpp file exists"""
        path = os.path.join(self.REPO_DIR, "aten/src/ATen/native/cpu/UnaryOpsKernel.cpp")
        assert os.path.exists(path), f"UnaryOpsKernel.cpp not found at {path}"

    def test_compare_kernel_cpp_exists(self):
        """Verify that the CPU CompareKernel.cpp file exists"""
        path = os.path.join(self.REPO_DIR, "aten/src/ATen/native/cpu/CompareKernel.cpp")
        assert os.path.exists(path), f"CompareKernel.cpp not found at {path}"

    # === Semantic Checks ===

    def test_binary_ops_kernel_uses_at_dispatch_v2(self):
        """Verify that BinaryOpsKernel.cpp uses AT_DISPATCH_V2 macro format for bitwise ops"""
        path = os.path.join(self.REPO_DIR, "aten/src/ATen/native/cpu/BinaryOpsKernel.cpp")
        with open(path, "r") as f:
            content = f.read()
        # Find all dispatch macros related to bitwise operations
        # Should use AT_DISPATCH_V2 not legacy AT_DISPATCH_ALL_TYPES
        bitwise_sections = []
        lines = content.split("\n")
        for i, line in enumerate(lines):
            if "bitwise_and" in line.lower() or "bitwise_or" in line.lower() or "bitwise_xor" in line.lower():
                context = "\n".join(lines[max(0, i-5):min(len(lines), i+20)])
                bitwise_sections.append(context)

        # Check that AT_DISPATCH_V2 is used in the file for bitwise operations
        has_v2_dispatch = "AT_DISPATCH_V2" in content
        assert has_v2_dispatch, (
            "BinaryOpsKernel.cpp should use AT_DISPATCH_V2 macro format, "
            "but AT_DISPATCH_V2 was not found in the file"
        )

    def test_binary_ops_kernel_dispatches_uint_types(self):
        """Verify that BinaryOpsKernel.cpp dispatches over kUInt16, kUInt32, kUInt64"""
        path = os.path.join(self.REPO_DIR, "aten/src/ATen/native/cpu/BinaryOpsKernel.cpp")
        with open(path, "r") as f:
            content = f.read()

        for uint_type in ["kUInt16", "kUInt32", "kUInt64"]:
            assert uint_type in content, (
                f"BinaryOpsKernel.cpp missing dispatch for {uint_type}. "
                f"All three unsigned int types must be dispatched."
            )

    def test_unary_ops_kernel_dispatches_uint_types(self):
        """Verify that UnaryOpsKernel.cpp dispatches over kUInt16, kUInt32, kUInt64 for bitwise_not"""
        path = os.path.join(self.REPO_DIR, "aten/src/ATen/native/cpu/UnaryOpsKernel.cpp")
        with open(path, "r") as f:
            content = f.read()

        for uint_type in ["kUInt16", "kUInt32", "kUInt64"]:
            assert uint_type in content, (
                f"UnaryOpsKernel.cpp missing dispatch for {uint_type} in bitwise_not."
            )

    def test_compare_kernel_dispatches_uint_types(self):
        """Verify that CompareKernel.cpp dispatches over kUInt16, kUInt32, kUInt64"""
        path = os.path.join(self.REPO_DIR, "aten/src/ATen/native/cpu/CompareKernel.cpp")
        with open(path, "r") as f:
            content = f.read()

        for uint_type in ["kUInt16", "kUInt32", "kUInt64"]:
            assert uint_type in content, (
                f"CompareKernel.cpp missing dispatch for {uint_type}. "
                f"Comparison operators must support all three unsigned types."
            )

    def test_cuda_bitwise_kernels_dispatch_uint_types(self):
        """Verify that CUDA bitwise kernel files dispatch over unsigned int types"""
        cuda_binary_path = os.path.join(
            self.REPO_DIR, "aten/src/ATen/native/cuda/BinaryBitwiseOpsKernels.cu"
        )
        cuda_unary_path = os.path.join(
            self.REPO_DIR, "aten/src/ATen/native/cuda/UnaryBitwiseOpsKernels.cu"
        )

        for fpath, label in [
            (cuda_binary_path, "CUDA BinaryBitwiseOpsKernels"),
            (cuda_unary_path, "CUDA UnaryBitwiseOpsKernels"),
        ]:
            if not os.path.exists(fpath):
                pytest.skip(f"{fpath} not found (CUDA file may not exist in this build)")
            with open(fpath, "r") as f:
                content = f.read()
            for uint_type in ["kUInt32", "kUInt64"]:
                assert uint_type in content, (
                    f"{label} missing dispatch for {uint_type}"
                )

    def test_unary_ops_kernel_uses_at_dispatch_v2(self):
        """Verify that UnaryOpsKernel.cpp uses AT_DISPATCH_V2 for bitwise_not"""
        path = os.path.join(self.REPO_DIR, "aten/src/ATen/native/cpu/UnaryOpsKernel.cpp")
        with open(path, "r") as f:
            content = f.read()
        assert "AT_DISPATCH_V2" in content, (
            "UnaryOpsKernel.cpp should use AT_DISPATCH_V2 macro format"
        )

    # === Functional Checks ===

    def test_bitwise_and_uint32_cpu(self):
        """Verify torch.bitwise_and works on uint32 tensors and returns correct results"""
        result = subprocess.run(
            [
                "python", "-c",
                (
                    "import torch; "
                    "a = torch.tensor([0xFF00FF00], dtype=torch.uint32); "
                    "b = torch.tensor([0x0F0F0F0F], dtype=torch.uint32); "
                    "c = torch.bitwise_and(a, b); "
                    "print(c.item()); "
                    "print(c.dtype)"
                ),
            ],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, f"bitwise_and uint32 failed: {result.stderr}"
        lines = result.stdout.strip().split("\n")
        assert len(lines) >= 2, f"Expected 2 lines of output, got: {result.stdout}"
        value = int(lines[0])
        expected = 0xFF00FF00 & 0x0F0F0F0F  # 0x0F000F00 = 251662080
        assert value == expected, f"Expected {expected}, got {value}"
        assert "uint32" in lines[1], f"Result dtype should be uint32, got {lines[1]}"

    def test_bitwise_not_uint64_all_bits(self):
        """Verify torch.bitwise_not on uint64 tensor of 0 returns all bits set (2^64 - 1)"""
        result = subprocess.run(
            [
                "python", "-c",
                (
                    "import torch; "
                    "a = torch.tensor([0], dtype=torch.uint64); "
                    "c = torch.bitwise_not(a); "
                    "print(c.item()); "
                    "print(c.dtype)"
                ),
            ],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, f"bitwise_not uint64 failed: {result.stderr}"
        lines = result.stdout.strip().split("\n")
        value = int(lines[0])
        expected = 18446744073709551615  # 2^64 - 1
        assert value == expected, f"Expected {expected}, got {value}"

    def test_bitwise_or_uint16_cpu(self):
        """Verify torch.bitwise_or works on uint16 tensors"""
        result = subprocess.run(
            [
                "python", "-c",
                (
                    "import torch; "
                    "a = torch.tensor([0x00FF], dtype=torch.uint16); "
                    "b = torch.tensor([0xFF00], dtype=torch.uint16); "
                    "c = torch.bitwise_or(a, b); "
                    "print(c.item())"
                ),
            ],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, f"bitwise_or uint16 failed: {result.stderr}"
        value = int(result.stdout.strip())
        expected = 0x00FF | 0xFF00  # 0xFFFF = 65535
        assert value == expected, f"Expected {expected}, got {value}"

    def test_bitwise_xor_uint32_cpu(self):
        """Verify torch.bitwise_xor works on uint32 tensors"""
        result = subprocess.run(
            [
                "python", "-c",
                (
                    "import torch; "
                    "a = torch.tensor([0xAAAAAAAA], dtype=torch.uint32); "
                    "b = torch.tensor([0x55555555], dtype=torch.uint32); "
                    "c = torch.bitwise_xor(a, b); "
                    "print(c.item())"
                ),
            ],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, f"bitwise_xor uint32 failed: {result.stderr}"
        value = int(result.stdout.strip())
        expected = 0xAAAAAAAA ^ 0x55555555  # 0xFFFFFFFF = 4294967295
        assert value == expected, f"Expected {expected}, got {value}"

    def test_comparison_eq_uint16(self):
        """Verify torch.eq works on uint16 tensors with identical values"""
        result = subprocess.run(
            [
                "python", "-c",
                (
                    "import torch; "
                    "a = torch.tensor([10, 20, 30], dtype=torch.uint16); "
                    "b = torch.tensor([10, 20, 30], dtype=torch.uint16); "
                    "c = torch.eq(a, b); "
                    "print(c.tolist())"
                ),
            ],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, f"eq uint16 failed: {result.stderr}"
        assert "[True, True, True]" in result.stdout, (
            f"Expected all True for equal uint16 tensors, got: {result.stdout}"
        )

    def test_comparison_lt_uint32(self):
        """Verify torch.lt works on uint32 tensors and respects unsigned ordering"""
        result = subprocess.run(
            [
                "python", "-c",
                (
                    "import torch; "
                    "a = torch.tensor([0], dtype=torch.uint32); "
                    "b = torch.tensor([1], dtype=torch.uint32); "
                    "c = torch.lt(a, b); "
                    "print(c.item())"
                ),
            ],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, f"lt uint32 failed: {result.stderr}"
        assert "True" in result.stdout, f"Expected True for 0 < 1 uint32, got: {result.stdout}"

    def test_comparison_gt_uint32_max_value(self):
        """Verify torch.gt correctly handles uint32 max value comparison (unsigned semantics)"""
        result = subprocess.run(
            [
                "python", "-c",
                (
                    "import torch; "
                    "a = torch.tensor([0], dtype=torch.uint32); "
                    "b = torch.tensor([4294967295], dtype=torch.uint32); "
                    "c = torch.gt(a, b); "
                    "print(c.item())"
                ),
            ],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, f"gt uint32 failed: {result.stderr}"
        assert "False" in result.stdout, (
            f"Expected False for 0 > 4294967295 uint32, got: {result.stdout}"
        )

    def test_comparison_ne_uint64(self):
        """Verify torch.ne works on uint64 tensors"""
        result = subprocess.run(
            [
                "python", "-c",
                (
                    "import torch; "
                    "a = torch.tensor([100, 200], dtype=torch.uint64); "
                    "b = torch.tensor([100, 300], dtype=torch.uint64); "
                    "c = torch.ne(a, b); "
                    "print(c.tolist())"
                ),
            ],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, f"ne uint64 failed: {result.stderr}"
        assert "[False, True]" in result.stdout, (
            f"Expected [False, True] for ne on uint64, got: {result.stdout}"
        )

    def test_comparison_le_ge_uint32(self):
        """Verify torch.le and torch.ge work on uint32 tensors"""
        result = subprocess.run(
            [
                "python", "-c",
                (
                    "import torch; "
                    "a = torch.tensor([5, 5, 3], dtype=torch.uint32); "
                    "b = torch.tensor([5, 3, 5], dtype=torch.uint32); "
                    "le_result = torch.le(a, b).tolist(); "
                    "ge_result = torch.ge(a, b).tolist(); "
                    "print(le_result); "
                    "print(ge_result)"
                ),
            ],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, f"le/ge uint32 failed: {result.stderr}"
        lines = result.stdout.strip().split("\n")
        assert len(lines) >= 2, f"Expected 2 lines, got: {result.stdout}"
        assert "[True, False, True]" in lines[0], (
            f"Expected le=[True, False, True], got {lines[0]}"
        )
        assert "[True, True, False]" in lines[1], (
            f"Expected ge=[True, True, False], got {lines[1]}"
        )
