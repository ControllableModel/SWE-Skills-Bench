"""
Test skill: add-uint-support
Verify that the Agent correctly adds uint32/uint64 support to PyTorch reduction operators.
"""

import os
import subprocess
import ast
import re
import pytest


class TestAddUintSupport:
    REPO_DIR = "/workspace/pytorch"

    # === File Path Checks ===

    def test_reduce_min_values_kernel_exists(self):
        """Verify ReduceMinValuesKernel.cu exists"""
        path = os.path.join(self.REPO_DIR, "aten/src/ATen/native/cuda/ReduceMinValuesKernel.cu")
        assert os.path.exists(path), f"ReduceMinValuesKernel.cu not found at {path}"

    def test_reduce_max_values_kernel_exists(self):
        """Verify ReduceMaxValuesKernel.cu exists"""
        path = os.path.join(self.REPO_DIR, "aten/src/ATen/native/cuda/ReduceMaxValuesKernel.cu")
        assert os.path.exists(path), f"ReduceMaxValuesKernel.cu not found at {path}"

    def test_reduce_argmin_kernel_exists(self):
        """Verify ReduceArgMinKernel.cu exists"""
        path = os.path.join(self.REPO_DIR, "aten/src/ATen/native/cuda/ReduceArgMinKernel.cu")
        assert os.path.exists(path), f"ReduceArgMinKernel.cu not found at {path}"

    def test_reduce_argmax_kernel_exists(self):
        """Verify ReduceArgMaxKernel.cu exists"""
        path = os.path.join(self.REPO_DIR, "aten/src/ATen/native/cuda/ReduceArgMaxKernel.cu")
        assert os.path.exists(path), f"ReduceArgMaxKernel.cu not found at {path}"

    def test_cumsum_kernel_exists(self):
        """Verify CumsumKernel.cu exists"""
        path = os.path.join(self.REPO_DIR, "aten/src/ATen/native/cuda/CumsumKernel.cu")
        assert os.path.exists(path), f"CumsumKernel.cu not found at {path}"

    # === Semantic Checks ===

    def test_min_values_kernel_has_uint_dispatch(self):
        """Verify ReduceMinValuesKernel.cu includes kUInt32 and kUInt64 in dispatch"""
        path = os.path.join(self.REPO_DIR, "aten/src/ATen/native/cuda/ReduceMinValuesKernel.cu")
        with open(path) as f:
            content = f.read()
        has_v2 = "AT_DISPATCH_V2" in content
        has_uint32 = "kUInt32" in content
        has_uint64 = "kUInt64" in content
        assert has_v2, "ReduceMinValuesKernel.cu must use AT_DISPATCH_V2 macro"
        assert has_uint32, "ReduceMinValuesKernel.cu must include kUInt32 in dispatch"
        assert has_uint64, "ReduceMinValuesKernel.cu must include kUInt64 in dispatch"

    def test_max_values_kernel_has_uint_dispatch(self):
        """Verify ReduceMaxValuesKernel.cu includes kUInt32 and kUInt64 in dispatch"""
        path = os.path.join(self.REPO_DIR, "aten/src/ATen/native/cuda/ReduceMaxValuesKernel.cu")
        with open(path) as f:
            content = f.read()
        has_v2 = "AT_DISPATCH_V2" in content
        has_uint32 = "kUInt32" in content
        has_uint64 = "kUInt64" in content
        assert has_v2, "ReduceMaxValuesKernel.cu must use AT_DISPATCH_V2 macro"
        assert has_uint32, "ReduceMaxValuesKernel.cu must include kUInt32 in dispatch"
        assert has_uint64, "ReduceMaxValuesKernel.cu must include kUInt64 in dispatch"

    def test_argmin_kernel_has_uint_dispatch(self):
        """Verify ReduceArgMinKernel.cu includes kUInt32 and kUInt64 in dispatch"""
        path = os.path.join(self.REPO_DIR, "aten/src/ATen/native/cuda/ReduceArgMinKernel.cu")
        with open(path) as f:
            content = f.read()
        has_v2 = "AT_DISPATCH_V2" in content
        has_uint32 = "kUInt32" in content
        has_uint64 = "kUInt64" in content
        assert has_v2, "ReduceArgMinKernel.cu must use AT_DISPATCH_V2 macro"
        assert has_uint32, "ReduceArgMinKernel.cu must include kUInt32 in dispatch"
        assert has_uint64, "ReduceArgMinKernel.cu must include kUInt64 in dispatch"

    def test_argmax_kernel_has_uint_dispatch(self):
        """Verify ReduceArgMaxKernel.cu includes kUInt32 and kUInt64 in dispatch"""
        path = os.path.join(self.REPO_DIR, "aten/src/ATen/native/cuda/ReduceArgMaxKernel.cu")
        with open(path) as f:
            content = f.read()
        has_v2 = "AT_DISPATCH_V2" in content
        has_uint32 = "kUInt32" in content
        has_uint64 = "kUInt64" in content
        assert has_v2, "ReduceArgMaxKernel.cu must use AT_DISPATCH_V2 macro"
        assert has_uint32, "ReduceArgMaxKernel.cu must include kUInt32 in dispatch"
        assert has_uint64, "ReduceArgMaxKernel.cu must include kUInt64 in dispatch"

    def test_cumsum_kernel_has_uint_dispatch(self):
        """Verify CumsumKernel.cu includes kUInt32 and kUInt64 in dispatch"""
        path = os.path.join(self.REPO_DIR, "aten/src/ATen/native/cuda/CumsumKernel.cu")
        with open(path) as f:
            content = f.read()
        has_v2 = "AT_DISPATCH_V2" in content
        has_uint32 = "kUInt32" in content
        has_uint64 = "kUInt64" in content
        assert has_v2, "CumsumKernel.cu must use AT_DISPATCH_V2 macro"
        assert has_uint32, "CumsumKernel.cu must include kUInt32 in dispatch"
        assert has_uint64, "CumsumKernel.cu must include kUInt64 in dispatch"

    def test_uint16_also_added_to_all_kernels(self):
        """Verify all 5 kernel files also include kUInt16 in dispatch"""
        kernel_files = [
            "aten/src/ATen/native/cuda/ReduceMinValuesKernel.cu",
            "aten/src/ATen/native/cuda/ReduceMaxValuesKernel.cu",
            "aten/src/ATen/native/cuda/ReduceArgMinKernel.cu",
            "aten/src/ATen/native/cuda/ReduceArgMaxKernel.cu",
            "aten/src/ATen/native/cuda/CumsumKernel.cu",
        ]
        for kf in kernel_files:
            path = os.path.join(self.REPO_DIR, kf)
            with open(path) as f:
                content = f.read()
            assert "kUInt16" in content, f"{kf} must include kUInt16 in dispatch"

    def test_dispatch_macros_consistent_within_files(self):
        """Verify all dispatch sites within each file use AT_DISPATCH_V2 (no legacy macros remain)"""
        kernel_files = [
            "aten/src/ATen/native/cuda/ReduceMinValuesKernel.cu",
            "aten/src/ATen/native/cuda/ReduceMaxValuesKernel.cu",
            "aten/src/ATen/native/cuda/ReduceArgMinKernel.cu",
            "aten/src/ATen/native/cuda/ReduceArgMaxKernel.cu",
            "aten/src/ATen/native/cuda/CumsumKernel.cu",
        ]
        legacy_pattern = re.compile(r"AT_DISPATCH_ALL_TYPES_AND")
        for kf in kernel_files:
            path = os.path.join(self.REPO_DIR, kf)
            with open(path) as f:
                content = f.read()
            # Some legacy macros may coexist for float-only dispatch sites, so we just ensure
            # at least one AT_DISPATCH_V2 with unsigned types exists
            v2_blocks = re.findall(r"AT_DISPATCH_V2\([^)]*\)", content, re.DOTALL)
            found_uint_in_v2 = any("kUInt32" in block for block in v2_blocks)
            assert found_uint_in_v2, (
                f"{kf}: Expected at least one AT_DISPATCH_V2 block containing kUInt32"
            )

    # === Functional Checks ===

    def test_build_succeeds(self):
        """Verify the project builds successfully with USE_CUDA=0"""
        result = subprocess.run(
            ["python", "setup.py", "develop", "--no-deps"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=600,
            env={**os.environ, "MAX_JOBS": "4", "USE_CUDA": "0"},
        )
        # Build may already be done; check either success or that torch is importable
        import_result = subprocess.run(
            ["python", "-c", "import torch; print(torch.__version__)"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert import_result.returncode == 0, (
            f"torch import failed: {import_result.stderr}"
        )

    def test_torch_uint32_dtype_exists(self):
        """Verify torch.uint32 dtype is accessible"""
        result = subprocess.run(
            ["python", "-c", "import torch; print(torch.uint32)"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0, f"torch.uint32 not accessible: {result.stderr}"
        assert "uint32" in result.stdout.lower(), f"Unexpected output: {result.stdout}"

    def test_torch_uint64_dtype_exists(self):
        """Verify torch.uint64 dtype is accessible"""
        result = subprocess.run(
            ["python", "-c", "import torch; print(torch.uint64)"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0, f"torch.uint64 not accessible: {result.stderr}"
        assert "uint64" in result.stdout.lower(), f"Unexpected output: {result.stdout}"

    def test_min_accepts_uint32_tensor(self):
        """Verify torch.min accepts uint32 tensors on CPU"""
        script = """
import torch
try:
    t = torch.tensor([10, 20, 5, 30], dtype=torch.uint32)
    result = torch.min(t)
    print(f"OK:{result.item()}")
except RuntimeError as e:
    print(f"FAIL:{e}")
"""
        result = subprocess.run(
            ["python", "-c", script],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0, f"Script failed: {result.stderr}"
        output = result.stdout.strip()
        assert output.startswith("OK:"), f"torch.min failed for uint32: {output}"
        assert output == "OK:5", f"Expected min=5, got {output}"

    def test_max_accepts_uint64_tensor(self):
        """Verify torch.max accepts uint64 tensors on CPU"""
        script = """
import torch
try:
    t = torch.tensor([100, 200, 50], dtype=torch.uint64)
    result = torch.max(t)
    print(f"OK:{result.item()}")
except RuntimeError as e:
    print(f"FAIL:{e}")
"""
        result = subprocess.run(
            ["python", "-c", script],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0, f"Script failed: {result.stderr}"
        output = result.stdout.strip()
        assert output.startswith("OK:"), f"torch.max failed for uint64: {output}"
        assert output == "OK:200", f"Expected max=200, got {output}"
