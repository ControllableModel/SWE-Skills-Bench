"""
Test skill: add-uint-support
Verify that unsigned integer (uint16/uint32/uint64) support has been correctly
added to PyTorch reduction operators (min, max, sum, prod) on CPU and CUDA kernels,
including dispatch macro updates and correctness of results.
"""

import os
import re
import subprocess
import pytest


class TestAddUintSupport:
    REPO_DIR = "/workspace/pytorch"

    # === File Path Checks ===

    def test_reduce_min_max_kernel_cu_exists(self):
        """Verify that ReduceMinMaxKernel.cu exists at the expected path"""
        filepath = os.path.join(self.REPO_DIR, "aten/src/ATen/native/cuda/ReduceMinMaxKernel.cu")
        assert os.path.exists(filepath), f"ReduceMinMaxKernel.cu not found at {filepath}"

    def test_reduce_ops_kernel_cu_exists(self):
        """Verify that ReduceOpsKernel.cu exists at the expected path"""
        filepath = os.path.join(self.REPO_DIR, "aten/src/ATen/native/cuda/ReduceOpsKernel.cu")
        assert os.path.exists(filepath), f"ReduceOpsKernel.cu not found at {filepath}"

    def test_reduce_ops_kernel_cpp_exists(self):
        """Verify that CPU ReduceOpsKernel.cpp exists at the expected path"""
        filepath = os.path.join(self.REPO_DIR, "aten/src/ATen/native/cpu/ReduceOpsKernel.cpp")
        assert os.path.exists(filepath), f"ReduceOpsKernel.cpp not found at {filepath}"

    def test_reduce_ops_cpp_exists(self):
        """Verify that top-level ReduceOps.cpp exists at the expected path"""
        filepath = os.path.join(self.REPO_DIR, "aten/src/ATen/native/ReduceOps.cpp")
        assert os.path.exists(filepath), f"ReduceOps.cpp not found at {filepath}"

    # === Semantic Checks ===

    def test_cuda_min_max_kernel_uses_v2_dispatch(self):
        """Verify that ReduceMinMaxKernel.cu uses AT_DISPATCH_V2 macros instead of legacy dispatch"""
        filepath = os.path.join(self.REPO_DIR, "aten/src/ATen/native/cuda/ReduceMinMaxKernel.cu")
        with open(filepath) as f:
            content = f.read()
        assert "AT_DISPATCH_V2" in content, \
            "ReduceMinMaxKernel.cu should use AT_DISPATCH_V2 macro instead of legacy dispatch"

    def test_cuda_reduce_ops_kernel_uses_v2_dispatch(self):
        """Verify that ReduceOpsKernel.cu uses AT_DISPATCH_V2 macros"""
        filepath = os.path.join(self.REPO_DIR, "aten/src/ATen/native/cuda/ReduceOpsKernel.cu")
        with open(filepath) as f:
            content = f.read()
        assert "AT_DISPATCH_V2" in content, \
            "ReduceOpsKernel.cu should use AT_DISPATCH_V2 macro"

    def test_cpu_reduce_ops_kernel_uses_v2_dispatch(self):
        """Verify that CPU ReduceOpsKernel.cpp uses AT_DISPATCH_V2 macros"""
        filepath = os.path.join(self.REPO_DIR, "aten/src/ATen/native/cpu/ReduceOpsKernel.cpp")
        with open(filepath) as f:
            content = f.read()
        assert "AT_DISPATCH_V2" in content, \
            "CPU ReduceOpsKernel.cpp should use AT_DISPATCH_V2 macro"

    def test_dispatch_sites_include_unsigned_integer_types(self):
        """Verify dispatch macros in all kernel files reference uint16/uint32/uint64 types"""
        target_files = [
            "aten/src/ATen/native/cuda/ReduceMinMaxKernel.cu",
            "aten/src/ATen/native/cuda/ReduceOpsKernel.cu",
            "aten/src/ATen/native/cpu/ReduceOpsKernel.cpp",
        ]
        for rel_path in target_files:
            filepath = os.path.join(self.REPO_DIR, rel_path)
            with open(filepath) as f:
                content = f.read()
            has_uint = any(token in content for token in [
                "kUInt16", "kUInt32", "kUInt64",
                "ScalarType::UInt16", "ScalarType::UInt32", "ScalarType::UInt64",
            ])
            assert has_uint, \
                f"{rel_path} does not include unsigned integer type references (kUInt16/kUInt32/kUInt64) in dispatch"

    def test_at_expand_wrapping_in_v2_dispatch(self):
        """Verify that AT_EXPAND() wrapping is used alongside AT_DISPATCH_V2 macros"""
        target_files = [
            "aten/src/ATen/native/cuda/ReduceMinMaxKernel.cu",
            "aten/src/ATen/native/cuda/ReduceOpsKernel.cu",
            "aten/src/ATen/native/cpu/ReduceOpsKernel.cpp",
        ]
        for rel_path in target_files:
            filepath = os.path.join(self.REPO_DIR, rel_path)
            with open(filepath) as f:
                content = f.read()
            if "AT_DISPATCH_V2" in content:
                assert "AT_EXPAND" in content, \
                    f"{rel_path} uses AT_DISPATCH_V2 but missing AT_EXPAND() type group wrapping"

    def test_reduce_ops_cpp_updated_for_unsigned_types(self):
        """Verify that top-level ReduceOps.cpp dispatch wrappers include unsigned type support"""
        filepath = os.path.join(self.REPO_DIR, "aten/src/ATen/native/ReduceOps.cpp")
        with open(filepath) as f:
            content = f.read()
        has_uint_dispatch = (
            "AT_DISPATCH_V2" in content or
            "kUInt16" in content or "kUInt32" in content or "kUInt64" in content
        )
        assert has_uint_dispatch, \
            "ReduceOps.cpp should be updated to support unsigned integer dispatch"

    def test_cpu_and_cuda_consistency_for_min_max(self):
        """Verify that both CPU and CUDA min/max kernels have unsigned type coverage"""
        cuda_path = os.path.join(self.REPO_DIR, "aten/src/ATen/native/cuda/ReduceMinMaxKernel.cu")
        cpu_path = os.path.join(self.REPO_DIR, "aten/src/ATen/native/cpu/ReduceOpsKernel.cpp")

        with open(cuda_path) as f:
            cuda_content = f.read()
        with open(cpu_path) as f:
            cpu_content = f.read()

        cuda_has_uint = any(t in cuda_content for t in ["kUInt16", "kUInt32", "kUInt64"])
        cpu_has_uint = any(t in cpu_content for t in ["kUInt16", "kUInt32", "kUInt64"])

        assert cuda_has_uint, "CUDA ReduceMinMaxKernel.cu missing unsigned integer dispatch"
        assert cpu_has_uint, "CPU ReduceOpsKernel.cpp missing unsigned integer dispatch (inconsistent with CUDA)"

    # === Functional Checks ===

    def test_sum_uint32_returns_correct_value(self):
        """Verify torch.ones(4, dtype=torch.uint32).sum() returns 4"""
        result = subprocess.run(
            ["python", "-c",
             "import torch; t = torch.ones(4, dtype=torch.uint32); s = t.sum(); "
             "print(f'{s.item()}|{s.dtype}')"],
            cwd=self.REPO_DIR,
            capture_output=True, text=True, timeout=120
        )
        assert result.returncode == 0, f"Failed to compute uint32 sum: {result.stderr}"
        parts = result.stdout.strip().split("|")
        assert len(parts) == 2, f"Unexpected output format: {result.stdout}"
        value = int(float(parts[0]))
        assert value == 4, f"Expected sum=4 for torch.ones(4, dtype=uint32), got {value}"

    def test_min_uint64_returns_correct_value(self):
        """Verify torch.tensor([3,1,4,1,5], dtype=torch.uint64).min() returns 1"""
        result = subprocess.run(
            ["python", "-c",
             "import torch; t = torch.tensor([3,1,4,1,5], dtype=torch.uint64); "
             "print(t.min().item())"],
            cwd=self.REPO_DIR,
            capture_output=True, text=True, timeout=120
        )
        assert result.returncode == 0, f"Failed to compute uint64 min: {result.stderr}"
        value = int(float(result.stdout.strip()))
        assert value == 1, f"Expected min=1 for [3,1,4,1,5] uint64, got {value}"

    def test_max_uint16_returns_correct_value(self):
        """Verify torch.tensor([3,1,4,1,5], dtype=torch.uint16).max() returns 5"""
        result = subprocess.run(
            ["python", "-c",
             "import torch; t = torch.tensor([3,1,4,1,5], dtype=torch.uint16); "
             "print(t.max().item())"],
            cwd=self.REPO_DIR,
            capture_output=True, text=True, timeout=120
        )
        assert result.returncode == 0, f"Failed to compute uint16 max: {result.stderr}"
        value = int(float(result.stdout.strip()))
        assert value == 5, f"Expected max=5 for [3,1,4,1,5] uint16, got {value}"

    def test_sum_uint16_accumulates_correctly(self):
        """Verify that uint16 sum does not wrap to signed type and accumulates correctly"""
        result = subprocess.run(
            ["python", "-c",
             "import torch; t = torch.tensor([100, 200, 300], dtype=torch.uint16); "
             "s = t.sum(); print(f'{s.item()}|{s.dtype}')"],
            cwd=self.REPO_DIR,
            capture_output=True, text=True, timeout=120
        )
        assert result.returncode == 0, f"Failed to compute uint16 sum: {result.stderr}"
        parts = result.stdout.strip().split("|")
        value = int(float(parts[0]))
        assert value == 600, f"Expected sum=600 for [100,200,300] uint16, got {value}"

    def test_prod_uint32_returns_correct_value(self):
        """Verify torch.tensor([2,3,5], dtype=torch.uint32).prod() returns 30"""
        result = subprocess.run(
            ["python", "-c",
             "import torch; t = torch.tensor([2, 3, 5], dtype=torch.uint32); "
             "p = t.prod(); print(p.item())"],
            cwd=self.REPO_DIR,
            capture_output=True, text=True, timeout=120
        )
        assert result.returncode == 0, f"Failed to compute uint32 prod: {result.stderr}"
        value = int(float(result.stdout.strip()))
        assert value == 30, f"Expected prod=30 for [2,3,5] uint32, got {value}"

    def test_mean_rejects_uint32_tensor(self):
        """Verify that float-only operator (mean) still rejects unsigned integer tensors"""
        result = subprocess.run(
            ["python", "-c",
             "import torch; t = torch.ones(4, dtype=torch.uint32); t.mean()"],
            cwd=self.REPO_DIR,
            capture_output=True, text=True, timeout=120
        )
        assert result.returncode != 0, \
            "mean() on uint32 tensor should raise an error but succeeded"
        stderr_lower = result.stderr.lower()
        assert ("not implemented" in stderr_lower or
                "runtimeerror" in stderr_lower or
                "error" in stderr_lower), \
            f"Expected 'not implemented' error for mean(uint32), got: {result.stderr[:500]}"

    def test_existing_float_reductions_not_regressed(self):
        """Verify that existing float32 reduction operators are not regressed"""
        result = subprocess.run(
            ["python", "-c",
             "import torch; t = torch.tensor([1.5, 2.5, 3.5]); "
             "print(f'{t.sum().item():.4f}|{t.min().item():.4f}|{t.max().item():.4f}')"],
            cwd=self.REPO_DIR,
            capture_output=True, text=True, timeout=120
        )
        assert result.returncode == 0, f"Float reduction failed: {result.stderr}"
        parts = result.stdout.strip().split("|")
        assert len(parts) == 3, f"Unexpected output: {result.stdout}"
        assert abs(float(parts[0]) - 7.5) < 0.001, f"Expected float sum=7.5, got {parts[0]}"
        assert abs(float(parts[1]) - 1.5) < 0.001, f"Expected float min=1.5, got {parts[1]}"
        assert abs(float(parts[2]) - 3.5) < 0.001, f"Expected float max=3.5, got {parts[2]}"

    def test_existing_int32_reductions_not_regressed(self):
        """Verify that existing int32 reduction operators still work correctly"""
        result = subprocess.run(
            ["python", "-c",
             "import torch; t = torch.tensor([10, 20, 30], dtype=torch.int32); "
             "print(f'{t.sum().item()}|{t.min().item()}|{t.max().item()}')"],
            cwd=self.REPO_DIR,
            capture_output=True, text=True, timeout=120
        )
        assert result.returncode == 0, f"Int32 reduction failed: {result.stderr}"
        parts = result.stdout.strip().split("|")
        assert int(parts[0]) == 60, f"Expected int32 sum=60, got {parts[0]}"
        assert int(parts[1]) == 10, f"Expected int32 min=10, got {parts[1]}"
        assert int(parts[2]) == 30, f"Expected int32 max=30, got {parts[2]}"

    def test_max_uint64_large_values(self):
        """Verify max works correctly with large uint64 values without overflow"""
        result = subprocess.run(
            ["python", "-c",
             "import torch; t = torch.tensor([1, 2**32, 2**48], dtype=torch.uint64); "
             "m = t.max(); print(m.item())"],
            cwd=self.REPO_DIR,
            capture_output=True, text=True, timeout=120
        )
        assert result.returncode == 0, f"Failed uint64 large value max: {result.stderr}"
        value = int(float(result.stdout.strip()))
        expected = 2**48
        assert value == expected, f"Expected max=2^48={expected}, got {value}"
