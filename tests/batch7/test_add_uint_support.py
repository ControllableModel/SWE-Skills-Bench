"""
Test skill: add-uint-support
Verify that the Agent correctly adds uint16/uint32/uint64 dispatch support
to PyTorch CUDA reduction, sorting, cumsum, and comparison kernels.
"""

import os
import re
import subprocess
import pytest


class TestAddUintSupport:
    REPO_DIR = "/workspace/pytorch"

    # === File Path Checks ===

    def test_reduce_min_max_kernel_exists(self):
        """Verify ReduceMinMaxKernel.cu exists at the expected path"""
        fpath = os.path.join(self.REPO_DIR, "aten/src/ATen/native/cuda/ReduceMinMaxKernel.cu")
        assert os.path.isfile(fpath), f"ReduceMinMaxKernel.cu not found at {fpath}"

    def test_sorting_kernel_exists(self):
        """Verify SortingKernel.cu exists at the expected path"""
        fpath = os.path.join(self.REPO_DIR, "aten/src/ATen/native/cuda/SortingKernel.cu")
        assert os.path.isfile(fpath), f"SortingKernel.cu not found at {fpath}"

    def test_cumsum_kernel_exists(self):
        """Verify CumsumKernel.cu exists at the expected path"""
        fpath = os.path.join(self.REPO_DIR, "aten/src/ATen/native/cuda/CumsumKernel.cu")
        assert os.path.isfile(fpath), f"CumsumKernel.cu not found at {fpath}"

    def test_compare_kernels_exists(self):
        """Verify CompareKernels.cu exists at the expected path"""
        fpath = os.path.join(self.REPO_DIR, "aten/src/ATen/native/cuda/CompareKernels.cu")
        assert os.path.isfile(fpath), f"CompareKernels.cu not found at {fpath}"

    # === Semantic Checks ===

    def test_reduce_min_max_kernel_has_uint_dispatch(self):
        """Verify ReduceMinMaxKernel.cu includes uint32 and uint64 in dispatch macros"""
        fpath = os.path.join(self.REPO_DIR, "aten/src/ATen/native/cuda/ReduceMinMaxKernel.cu")
        with open(fpath, "r") as f:
            content = f.read()
        # Check for uint32 / kUInt32 references
        has_uint32 = bool(re.search(r'(kUInt32|uint32|ScalarType::UInt32)', content))
        has_uint64 = bool(re.search(r'(kUInt64|uint64|ScalarType::UInt64)', content))
        assert has_uint32, "ReduceMinMaxKernel.cu missing uint32 dispatch support"
        assert has_uint64, "ReduceMinMaxKernel.cu missing uint64 dispatch support"

    def test_reduce_min_max_kernel_has_uint16_dispatch(self):
        """Verify ReduceMinMaxKernel.cu includes uint16 in dispatch macros"""
        fpath = os.path.join(self.REPO_DIR, "aten/src/ATen/native/cuda/ReduceMinMaxKernel.cu")
        with open(fpath, "r") as f:
            content = f.read()
        has_uint16 = bool(re.search(r'(kUInt16|uint16|ScalarType::UInt16)', content))
        assert has_uint16, "ReduceMinMaxKernel.cu missing uint16 dispatch support"

    def test_sorting_kernel_has_uint_dispatch(self):
        """Verify SortingKernel.cu includes uint32 and uint64 in type dispatch"""
        fpath = os.path.join(self.REPO_DIR, "aten/src/ATen/native/cuda/SortingKernel.cu")
        with open(fpath, "r") as f:
            content = f.read()
        has_uint32 = bool(re.search(r'(kUInt32|uint32|ScalarType::UInt32)', content))
        has_uint64 = bool(re.search(r'(kUInt64|uint64|ScalarType::UInt64)', content))
        assert has_uint32, "SortingKernel.cu missing uint32 dispatch support"
        assert has_uint64, "SortingKernel.cu missing uint64 dispatch support"

    def test_cumsum_kernel_has_uint_dispatch(self):
        """Verify CumsumKernel.cu includes uint16, uint32, and uint64 in type dispatch"""
        fpath = os.path.join(self.REPO_DIR, "aten/src/ATen/native/cuda/CumsumKernel.cu")
        with open(fpath, "r") as f:
            content = f.read()
        has_uint16 = bool(re.search(r'(kUInt16|uint16|ScalarType::UInt16)', content))
        has_uint32 = bool(re.search(r'(kUInt32|uint32|ScalarType::UInt32)', content))
        has_uint64 = bool(re.search(r'(kUInt64|uint64|ScalarType::UInt64)', content))
        assert has_uint16, "CumsumKernel.cu missing uint16 dispatch support"
        assert has_uint32, "CumsumKernel.cu missing uint32 dispatch support"
        assert has_uint64, "CumsumKernel.cu missing uint64 dispatch support"

    def test_compare_kernels_has_uint_dispatch(self):
        """Verify CompareKernels.cu includes uint16, uint32, and uint64 in type dispatch"""
        fpath = os.path.join(self.REPO_DIR, "aten/src/ATen/native/cuda/CompareKernels.cu")
        with open(fpath, "r") as f:
            content = f.read()
        has_uint16 = bool(re.search(r'(kUInt16|uint16|ScalarType::UInt16)', content))
        has_uint32 = bool(re.search(r'(kUInt32|uint32|ScalarType::UInt32)', content))
        has_uint64 = bool(re.search(r'(kUInt64|uint64|ScalarType::UInt64)', content))
        assert has_uint16, "CompareKernels.cu missing uint16 dispatch support"
        assert has_uint32, "CompareKernels.cu missing uint32 dispatch support"
        assert has_uint64, "CompareKernels.cu missing uint64 dispatch support"

    def test_all_dispatch_sites_updated_in_reduce_min_max(self):
        """Verify every AT_DISPATCH site in ReduceMinMaxKernel.cu includes unsigned types"""
        fpath = os.path.join(self.REPO_DIR, "aten/src/ATen/native/cuda/ReduceMinMaxKernel.cu")
        with open(fpath, "r") as f:
            content = f.read()
        # Find all AT_DISPATCH macro blocks
        dispatch_calls = re.findall(r'AT_DISPATCH_\w+\([^;]+?\{', content, re.DOTALL)
        assert len(dispatch_calls) > 0, "No AT_DISPATCH calls found in ReduceMinMaxKernel.cu"
        # For each dispatch call that includes integral types, check for unsigned coverage
        integral_dispatches = [d for d in dispatch_calls if re.search(r'(ALL_TYPES|INTEGRAL|all_types)', d, re.IGNORECASE)]
        if integral_dispatches:
            # At least one dispatch should mention unsigned types or use a macro that covers them
            has_unsigned_macro = any(
                re.search(r'(AT_DISPATCH_ALL_TYPES_AND.*kUInt|uint32|uint64|UNSIGNED)', d)
                for d in integral_dispatches
            )
            # Or alternatively all dispatch sites use a macro that already includes uint
            has_broad_macro = any(
                re.search(r'AT_DISPATCH_ALL_TYPES_AND', d) for d in integral_dispatches
            )
            assert has_unsigned_macro or has_broad_macro, (
                "Not all dispatch sites in ReduceMinMaxKernel.cu appear to include unsigned integer types"
            )

    def test_existing_types_preserved_in_sorting_kernel(self):
        """Verify SortingKernel.cu still supports existing signed integer and float types"""
        fpath = os.path.join(self.REPO_DIR, "aten/src/ATen/native/cuda/SortingKernel.cu")
        with open(fpath, "r") as f:
            content = f.read()
        # Check that dispatch macros still exist (not accidentally removed)
        assert re.search(r'AT_DISPATCH_', content), (
            "SortingKernel.cu missing AT_DISPATCH macros - existing type support may have been removed"
        )
        # Verify file still references sorting-related functions
        has_sort_ref = bool(re.search(r'(sort|Sort)', content))
        assert has_sort_ref, "SortingKernel.cu missing sorting function references"

    # === Functional Checks ===

    def test_pytorch_build_succeeds(self):
        """Verify PyTorch builds successfully with the modifications"""
        result = subprocess.run(
            ["python", "setup.py", "develop"],
            cwd=os.path.join(self.REPO_DIR, "pytorch") if os.path.isdir(os.path.join(self.REPO_DIR, "pytorch")) else self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=600,
            env={**os.environ, "MAX_JOBS": "4", "USE_CUDA": "0"}
        )
        assert result.returncode == 0, f"PyTorch build failed: {result.stderr[-2000:]}"

    def test_torch_uint32_tensor_creation(self):
        """Verify torch.uint32 tensors can be created successfully"""
        try:
            import torch
        except ImportError:
            pytest.skip("torch not importable - build may not be complete")
        t = torch.tensor([1, 2, 3], dtype=torch.uint32)
        assert t.dtype == torch.uint32, f"Expected dtype torch.uint32, got {t.dtype}"
        assert t.tolist() == [1, 2, 3], f"Tensor values incorrect: {t.tolist()}"

    def test_torch_min_with_uint32(self):
        """Verify torch.min works with uint32 tensors and returns correct value"""
        try:
            import torch
        except ImportError:
            pytest.skip("torch not importable")
        t = torch.tensor([3, 1, 2], dtype=torch.uint32)
        try:
            result = torch.min(t)
            assert result.item() == 1, f"Expected min=1, got {result.item()}"
            assert result.dtype == torch.uint32, f"Expected uint32 result, got {result.dtype}"
        except RuntimeError as e:
            pytest.fail(f"torch.min failed for uint32: {e}")

    def test_torch_max_with_uint64(self):
        """Verify torch.max works with uint64 tensors and returns correct value"""
        try:
            import torch
        except ImportError:
            pytest.skip("torch not importable")
        t = torch.tensor([100, 500, 200], dtype=torch.uint64)
        try:
            result = torch.max(t)
            assert result.item() == 500, f"Expected max=500, got {result.item()}"
        except RuntimeError as e:
            pytest.fail(f"torch.max failed for uint64: {e}")

    def test_torch_sort_with_uint32(self):
        """Verify torch.sort works with uint32 tensors in ascending order"""
        try:
            import torch
        except ImportError:
            pytest.skip("torch not importable")
        t = torch.tensor([300, 100, 200], dtype=torch.uint32)
        try:
            values, indices = torch.sort(t)
            assert values.tolist() == [100, 200, 300], f"Sort values wrong: {values.tolist()}"
            assert indices.tolist() == [1, 2, 0], f"Sort indices wrong: {indices.tolist()}"
        except RuntimeError as e:
            pytest.fail(f"torch.sort failed for uint32: {e}")

    def test_torch_cumsum_with_uint32(self):
        """Verify torch.cumsum works with uint32 tensors and returns correct prefix sums"""
        try:
            import torch
        except ImportError:
            pytest.skip("torch not importable")
        t = torch.tensor([1, 2, 3], dtype=torch.uint32)
        try:
            result = torch.cumsum(t, dim=0)
            assert result.tolist() == [1, 3, 6], f"cumsum values wrong: {result.tolist()}"
            assert result.dtype == torch.uint32, f"Expected uint32 result, got {result.dtype}"
        except RuntimeError as e:
            pytest.fail(f"torch.cumsum failed for uint32: {e}")

    def test_torch_eq_with_uint16(self):
        """Verify torch.eq works with uint16 tensors and returns correct boolean results"""
        try:
            import torch
        except ImportError:
            pytest.skip("torch not importable")
        a = torch.tensor([1, 2], dtype=torch.uint16)
        b = torch.tensor([1, 3], dtype=torch.uint16)
        try:
            result = torch.eq(a, b)
            assert result.tolist() == [True, False], f"eq result wrong: {result.tolist()}"
        except RuntimeError as e:
            pytest.fail(f"torch.eq failed for uint16: {e}")

    def test_torch_sort_descending_uint64(self):
        """Verify torch.sort descending mode works with uint64 tensors"""
        try:
            import torch
        except ImportError:
            pytest.skip("torch not importable")
        t = torch.tensor([10, 50, 30], dtype=torch.uint64)
        try:
            values, indices = torch.sort(t, descending=True)
            assert values.tolist() == [50, 30, 10], f"Descending sort values wrong: {values.tolist()}"
            assert indices.tolist() == [1, 2, 0], f"Descending sort indices wrong: {indices.tolist()}"
        except RuntimeError as e:
            pytest.fail(f"torch.sort descending failed for uint64: {e}")

    def test_torch_comparison_operators_uint32(self):
        """Verify all six comparison operators (eq, ne, lt, le, gt, ge) work with uint32"""
        try:
            import torch
        except ImportError:
            pytest.skip("torch not importable")
        a = torch.tensor([1, 5, 3], dtype=torch.uint32)
        b = torch.tensor([2, 5, 1], dtype=torch.uint32)
        try:
            assert torch.lt(a, b).tolist() == [True, False, False], "lt failed for uint32"
            assert torch.le(a, b).tolist() == [True, True, False], "le failed for uint32"
            assert torch.gt(a, b).tolist() == [False, False, True], "gt failed for uint32"
            assert torch.ge(a, b).tolist() == [False, True, True], "ge failed for uint32"
            assert torch.eq(a, b).tolist() == [False, True, False], "eq failed for uint32"
            assert torch.ne(a, b).tolist() == [True, False, True], "ne failed for uint32"
        except RuntimeError as e:
            pytest.fail(f"Comparison operators failed for uint32: {e}")
