"""
Test skill: add-uint-support
Verify that the Agent correctly adds uint16/uint32/uint64 support
to PyTorch reduction operators (min, max, sum, prod, aminmax).
"""

import os
import re
import subprocess
import pytest


class TestAddUintSupport:
    REPO_DIR = "/workspace/pytorch"

    # === File Path Checks ===

    def test_reduce_min_values_kernel_exists(self):
        """Verify that ReduceMinValuesKernel.cu exists at the expected location"""
        path = os.path.join(self.REPO_DIR, "aten/src/ATen/native/cuda/ReduceMinValuesKernel.cu")
        assert os.path.exists(path), f"ReduceMinValuesKernel.cu not found at {path}"

    def test_reduce_max_values_kernel_exists(self):
        """Verify that ReduceMaxValuesKernel.cu exists at the expected location"""
        path = os.path.join(self.REPO_DIR, "aten/src/ATen/native/cuda/ReduceMaxValuesKernel.cu")
        assert os.path.exists(path), f"ReduceMaxValuesKernel.cu not found at {path}"

    def test_reduce_ops_cpp_exists(self):
        """Verify that ReduceOps.cpp exists at the expected location"""
        path = os.path.join(self.REPO_DIR, "aten/src/ATen/native/ReduceOps.cpp")
        assert os.path.exists(path), f"ReduceOps.cpp not found at {path}"

    def test_shared_reduce_ops_header_exists(self):
        """Verify that SharedReduceOps.h exists and contains numeric_limits usage"""
        path = os.path.join(self.REPO_DIR, "aten/src/ATen/native/SharedReduceOps.h")
        assert os.path.exists(path), f"SharedReduceOps.h not found at {path}"
        with open(path) as f:
            content = f.read()
        assert "numeric_limits" in content, (
            "SharedReduceOps.h should reference numeric_limits for reduction identity values"
        )

    # === Semantic Checks ===

    def test_min_kernel_uses_dispatch_v2_no_legacy(self):
        """Verify ReduceMinValuesKernel.cu uses AT_DISPATCH_V2 and has no legacy dispatch macros"""
        path = os.path.join(self.REPO_DIR, "aten/src/ATen/native/cuda/ReduceMinValuesKernel.cu")
        with open(path) as f:
            content = f.read()
        legacy = re.findall(r'\bAT_DISPATCH_ALL_TYPES\b(?!_V2)', content)
        legacy += re.findall(r'\bAT_DISPATCH_ALL_TYPES_AND\b', content)
        legacy += re.findall(r'\bAT_DISPATCH_ALL_TYPES_AND2\b', content)
        assert len(legacy) == 0, (
            f"Legacy dispatch macros found in ReduceMinValuesKernel.cu: {legacy}. "
            "All dispatch sites should use AT_DISPATCH_V2."
        )

    def test_max_kernel_uses_dispatch_v2_no_legacy(self):
        """Verify ReduceMaxValuesKernel.cu uses AT_DISPATCH_V2 and has no legacy dispatch macros"""
        path = os.path.join(self.REPO_DIR, "aten/src/ATen/native/cuda/ReduceMaxValuesKernel.cu")
        with open(path) as f:
            content = f.read()
        legacy = re.findall(r'\bAT_DISPATCH_ALL_TYPES\b(?!_V2)', content)
        legacy += re.findall(r'\bAT_DISPATCH_ALL_TYPES_AND\b', content)
        legacy += re.findall(r'\bAT_DISPATCH_ALL_TYPES_AND2\b', content)
        assert len(legacy) == 0, (
            f"Legacy dispatch macros found in ReduceMaxValuesKernel.cu: {legacy}. "
            "All dispatch sites should use AT_DISPATCH_V2."
        )

    def test_min_kernel_includes_unsigned_type_coverage(self):
        """Verify ReduceMinValuesKernel.cu dispatch includes unsigned integer types"""
        path = os.path.join(self.REPO_DIR, "aten/src/ATen/native/cuda/ReduceMinValuesKernel.cu")
        with open(path) as f:
            content = f.read()
        has_unsigned = (
            "AT_BAREBONES_UNSIGNED_TYPES" in content
            or "kUInt16" in content
            or "kUInt32" in content
            or "kUInt64" in content
            or "AT_INTEGRAL_TYPES_V2" in content
        )
        assert has_unsigned, (
            "ReduceMinValuesKernel.cu does not include unsigned type dispatch coverage. "
            "Expected AT_BAREBONES_UNSIGNED_TYPES, AT_INTEGRAL_TYPES_V2, or explicit kUInt types."
        )

    def test_max_kernel_includes_unsigned_type_coverage(self):
        """Verify ReduceMaxValuesKernel.cu dispatch includes unsigned integer types"""
        path = os.path.join(self.REPO_DIR, "aten/src/ATen/native/cuda/ReduceMaxValuesKernel.cu")
        with open(path) as f:
            content = f.read()
        has_unsigned = (
            "AT_BAREBONES_UNSIGNED_TYPES" in content
            or "kUInt16" in content
            or "kUInt32" in content
            or "kUInt64" in content
            or "AT_INTEGRAL_TYPES_V2" in content
        )
        assert has_unsigned, (
            "ReduceMaxValuesKernel.cu does not include unsigned type dispatch coverage."
        )

    def test_aminmax_kernel_includes_unsigned_type_coverage(self):
        """Verify ReduceAMinMaxKernel.cu dispatch includes unsigned integer types"""
        path = os.path.join(self.REPO_DIR, "aten/src/ATen/native/cuda/ReduceAMinMaxKernel.cu")
        with open(path) as f:
            content = f.read()
        has_unsigned = (
            "AT_BAREBONES_UNSIGNED_TYPES" in content
            or "kUInt16" in content
            or "kUInt32" in content
            or "kUInt64" in content
            or "AT_INTEGRAL_TYPES_V2" in content
        )
        assert has_unsigned, (
            "ReduceAMinMaxKernel.cu does not include unsigned type dispatch coverage."
        )

    def test_reduce_ops_cpp_includes_unsigned_type_coverage(self):
        """Verify ReduceOps.cpp CPU dispatch includes unsigned integer types"""
        path = os.path.join(self.REPO_DIR, "aten/src/ATen/native/ReduceOps.cpp")
        with open(path) as f:
            content = f.read()
        has_unsigned = (
            "AT_BAREBONES_UNSIGNED_TYPES" in content
            or "kUInt16" in content
            or "kUInt32" in content
            or "kUInt64" in content
            or "AT_INTEGRAL_TYPES_V2" in content
        )
        assert has_unsigned, (
            "ReduceOps.cpp does not include unsigned type dispatch coverage for CPU reductions."
        )

    def test_reduce_ops_cpp_no_legacy_macros(self):
        """Verify ReduceOps.cpp does not have legacy dispatch macros in modified dispatch sites"""
        path = os.path.join(self.REPO_DIR, "aten/src/ATen/native/ReduceOps.cpp")
        with open(path) as f:
            content = f.read()
        # Check that AT_DISPATCH_V2 is used at least once
        assert "AT_DISPATCH_V2" in content, (
            "ReduceOps.cpp should use AT_DISPATCH_V2 for modified dispatch sites"
        )

    def test_dispatch_sites_use_at_wrap_in_v2(self):
        """Verify converted AT_DISPATCH_V2 sites use AT_WRAP for lambda bodies"""
        files_to_check = [
            "aten/src/ATen/native/cuda/ReduceMinValuesKernel.cu",
            "aten/src/ATen/native/cuda/ReduceMaxValuesKernel.cu",
            "aten/src/ATen/native/cuda/ReduceAMinMaxKernel.cu",
        ]
        for rel_path in files_to_check:
            path = os.path.join(self.REPO_DIR, rel_path)
            if not os.path.exists(path):
                continue
            with open(path) as f:
                content = f.read()
            if "AT_DISPATCH_V2" in content:
                assert "AT_WRAP" in content, (
                    f"{rel_path} uses AT_DISPATCH_V2 but missing AT_WRAP for lambda body"
                )

    # === Functional Checks ===

    def test_uint16_min_reduction_cpu(self):
        """Verify torch.uint16 min reduction returns correct value on CPU"""
        torch = pytest.importorskip("torch")
        t = torch.tensor([3, 1, 2], dtype=torch.uint16)
        result = t.min()
        assert result.item() == 1, f"Expected min=1 for uint16 tensor [3,1,2], got {result.item()}"
        assert result.dtype == torch.uint16, f"Expected dtype uint16, got {result.dtype}"

    def test_uint32_max_reduction_cpu(self):
        """Verify torch.uint32 max reduction returns correct value on CPU"""
        torch = pytest.importorskip("torch")
        t = torch.tensor([3, 1, 2], dtype=torch.uint32)
        result = t.max()
        assert result.item() == 3, f"Expected max=3 for uint32 tensor [3,1,2], got {result.item()}"
        assert result.dtype == torch.uint32, f"Expected dtype uint32, got {result.dtype}"

    def test_uint64_sum_reduction_cpu(self):
        """Verify torch.uint64 sum reduction returns correct value on CPU"""
        torch = pytest.importorskip("torch")
        t = torch.tensor([10, 20, 30], dtype=torch.uint64)
        result = t.sum()
        assert result.item() == 60, f"Expected sum=60 for uint64 tensor [10,20,30], got {result.item()}"
        assert result.dtype == torch.uint64, f"Expected dtype uint64, got {result.dtype}"

    def test_uint32_aminmax_cpu(self):
        """Verify torch.aminmax works with uint32 tensors on CPU"""
        torch = pytest.importorskip("torch")
        t = torch.tensor([5, 2, 8], dtype=torch.uint32)
        min_val, max_val = torch.aminmax(t)
        assert min_val.item() == 2, f"Expected aminmax min=2, got {min_val.item()}"
        assert max_val.item() == 8, f"Expected aminmax max=8, got {max_val.item()}"
        assert min_val.dtype == torch.uint32, f"Expected dtype uint32 for min, got {min_val.dtype}"
        assert max_val.dtype == torch.uint32, f"Expected dtype uint32 for max, got {max_val.dtype}"

    def test_float32_reduction_no_regression(self):
        """Verify float32 reductions still work after changes (no regression)"""
        torch = pytest.importorskip("torch")
        t = torch.tensor([1.5, 2.5, 3.5], dtype=torch.float32)
        assert t.min().item() == pytest.approx(1.5), "float32 min regression"
        assert t.max().item() == pytest.approx(3.5), "float32 max regression"
        assert t.sum().item() == pytest.approx(7.5), "float32 sum regression"

    def test_int32_reduction_no_regression(self):
        """Verify signed int32 reductions still work (no regression)"""
        torch = pytest.importorskip("torch")
        t = torch.tensor([-5, 3, 0, 7, -2], dtype=torch.int32)
        assert t.min().item() == -5, "int32 min regression"
        assert t.max().item() == 7, "int32 max regression"
        assert t.sum().item() == 3, "int32 sum regression"

    def test_uint16_prod_reduction_cpu(self):
        """Verify torch.uint16 prod reduction works on CPU"""
        torch = pytest.importorskip("torch")
        t = torch.tensor([2, 3, 4], dtype=torch.uint16)
        result = t.prod()
        assert result.item() == 24, f"Expected prod=24 for uint16 tensor [2,3,4], got {result.item()}"

    def test_test_reductions_file_includes_uint_dtypes(self):
        """Verify test/test_reductions.py includes uint16/uint32/uint64 in parametrization"""
        path = os.path.join(self.REPO_DIR, "test/test_reductions.py")
        assert os.path.exists(path), f"test_reductions.py not found at {path}"
        with open(path) as f:
            content = f.read()
        assert "uint16" in content, (
            "test_reductions.py should reference uint16 in dtype parametrization"
        )
        assert "uint32" in content, (
            "test_reductions.py should reference uint32 in dtype parametrization"
        )
        assert "uint64" in content, (
            "test_reductions.py should reference uint64 in dtype parametrization"
        )
