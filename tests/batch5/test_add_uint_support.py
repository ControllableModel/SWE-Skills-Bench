"""
Test skill: add-uint-support
Verify that the Agent correctly adds uint32/uint64 operator support
to six CUDA kernel files in the PyTorch codebase.
"""

import os
import re
import subprocess
import pytest


class TestAddUintSupport:
    REPO_DIR = "/workspace/pytorch"

    BITWISE_OPS_FILE = "aten/src/ATen/native/cuda/BinaryBitwiseOpsKernels.cu"
    SHIFT_OPS_FILE = "aten/src/ATen/native/cuda/BinaryShiftOpsKernels.cu"
    MAXMIN_FILE = "aten/src/ATen/native/cuda/MaxMinElementwiseKernel.cu"

    def _read_file(self, rel_path):
        """Helper to read a file from the repo."""
        filepath = os.path.join(self.REPO_DIR, rel_path)
        with open(filepath) as f:
            return f.read()

    def _strip_comments(self, content):
        """Remove C/C++ single-line and multi-line comments."""
        content = re.sub(r'//.*?$', '', content, flags=re.MULTILINE)
        content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)
        return content

    def _extract_kernel_function(self, content, func_name):
        """Extract a kernel function body by matching function name and braces."""
        pattern = rf'{func_name}\s*\('
        match = re.search(pattern, content)
        if not match:
            return None
        brace_start = content.find('{', match.end())
        if brace_start == -1:
            return None
        depth = 0
        for i in range(brace_start, len(content)):
            if content[i] == '{':
                depth += 1
            elif content[i] == '}':
                depth -= 1
                if depth == 0:
                    return content[match.start():i + 1]
        return content[match.start():]

    # === File Path Checks ===

    def test_bitwise_ops_kernel_file_exists(self):
        """Verify BinaryBitwiseOpsKernels.cu exists at the expected path"""
        filepath = os.path.join(self.REPO_DIR, self.BITWISE_OPS_FILE)
        assert os.path.exists(filepath), f"File not found: {filepath}"

    def test_shift_ops_kernel_file_exists(self):
        """Verify BinaryShiftOpsKernels.cu exists at the expected path"""
        filepath = os.path.join(self.REPO_DIR, self.SHIFT_OPS_FILE)
        assert os.path.exists(filepath), f"File not found: {filepath}"

    def test_maxmin_kernel_file_exists(self):
        """Verify MaxMinElementwiseKernel.cu exists at the expected path"""
        filepath = os.path.join(self.REPO_DIR, self.MAXMIN_FILE)
        assert os.path.exists(filepath), f"File not found: {filepath}"

    # === Semantic Checks ===

    def test_bitwise_and_dispatches_uint32(self):
        """Verify bitwise_and_kernel_cuda dispatch includes uint32 type"""
        content = self._read_file(self.BITWISE_OPS_FILE)
        func = self._extract_kernel_function(content, "bitwise_and_kernel_cuda")
        assert func is not None, "Could not find bitwise_and_kernel_cuda function"
        clean = self._strip_comments(func)
        assert re.search(r'(kUInt32|uint32_t|at::kUInt32|ScalarType::UInt32)', clean), \
            "bitwise_and_kernel_cuda does not dispatch uint32 type"

    def test_bitwise_and_dispatches_uint64(self):
        """Verify bitwise_and_kernel_cuda dispatch includes uint64 type"""
        content = self._read_file(self.BITWISE_OPS_FILE)
        func = self._extract_kernel_function(content, "bitwise_and_kernel_cuda")
        assert func is not None, "Could not find bitwise_and_kernel_cuda function"
        clean = self._strip_comments(func)
        assert re.search(r'(kUInt64|uint64_t|at::kUInt64|ScalarType::UInt64)', clean), \
            "bitwise_and_kernel_cuda does not dispatch uint64 type"

    def test_bitwise_or_dispatches_uint_types(self):
        """Verify bitwise_or_kernel_cuda dispatch includes both uint32 and uint64"""
        content = self._read_file(self.BITWISE_OPS_FILE)
        func = self._extract_kernel_function(content, "bitwise_or_kernel_cuda")
        assert func is not None, "Could not find bitwise_or_kernel_cuda function"
        clean = self._strip_comments(func)
        has_uint32 = bool(re.search(r'(kUInt32|uint32_t|at::kUInt32|ScalarType::UInt32)', clean))
        has_uint64 = bool(re.search(r'(kUInt64|uint64_t|at::kUInt64|ScalarType::UInt64)', clean))
        assert has_uint32 and has_uint64, \
            f"bitwise_or_kernel_cuda missing uint dispatch: uint32={has_uint32}, uint64={has_uint64}"

    def test_bitwise_xor_dispatches_uint_types(self):
        """Verify bitwise_xor_kernel_cuda dispatch includes both uint32 and uint64"""
        content = self._read_file(self.BITWISE_OPS_FILE)
        func = self._extract_kernel_function(content, "bitwise_xor_kernel_cuda")
        assert func is not None, "Could not find bitwise_xor_kernel_cuda function"
        clean = self._strip_comments(func)
        has_uint32 = bool(re.search(r'(kUInt32|uint32_t|at::kUInt32|ScalarType::UInt32)', clean))
        has_uint64 = bool(re.search(r'(kUInt64|uint64_t|at::kUInt64|ScalarType::UInt64)', clean))
        assert has_uint32 and has_uint64, \
            f"bitwise_xor_kernel_cuda missing uint dispatch: uint32={has_uint32}, uint64={has_uint64}"

    def test_lshift_dispatches_uint_types(self):
        """Verify lshift_kernel_cuda dispatch includes uint32 and uint64"""
        content = self._read_file(self.SHIFT_OPS_FILE)
        func = self._extract_kernel_function(content, "lshift_kernel_cuda")
        assert func is not None, "Could not find lshift_kernel_cuda function"
        clean = self._strip_comments(func)
        has_uint32 = bool(re.search(r'(kUInt32|uint32_t|at::kUInt32|ScalarType::UInt32)', clean))
        has_uint64 = bool(re.search(r'(kUInt64|uint64_t|at::kUInt64|ScalarType::UInt64)', clean))
        assert has_uint32 and has_uint64, \
            f"lshift_kernel_cuda missing uint dispatch: uint32={has_uint32}, uint64={has_uint64}"

    def test_rshift_dispatches_uint_types(self):
        """Verify rshift_kernel_cuda dispatch includes uint32 and uint64"""
        content = self._read_file(self.SHIFT_OPS_FILE)
        func = self._extract_kernel_function(content, "rshift_kernel_cuda")
        assert func is not None, "Could not find rshift_kernel_cuda function"
        clean = self._strip_comments(func)
        has_uint32 = bool(re.search(r'(kUInt32|uint32_t|at::kUInt32|ScalarType::UInt32)', clean))
        has_uint64 = bool(re.search(r'(kUInt64|uint64_t|at::kUInt64|ScalarType::UInt64)', clean))
        assert has_uint32 and has_uint64, \
            f"rshift_kernel_cuda missing uint dispatch: uint32={has_uint32}, uint64={has_uint64}"

    def test_maximum_dispatches_uint_types(self):
        """Verify maximum_kernel_cuda dispatch includes uint32 and uint64"""
        content = self._read_file(self.MAXMIN_FILE)
        func = self._extract_kernel_function(content, "maximum_kernel_cuda")
        assert func is not None, "Could not find maximum_kernel_cuda function"
        clean = self._strip_comments(func)
        has_uint32 = bool(re.search(r'(kUInt32|uint32_t|at::kUInt32|ScalarType::UInt32)', clean))
        has_uint64 = bool(re.search(r'(kUInt64|uint64_t|at::kUInt64|ScalarType::UInt64)', clean))
        assert has_uint32 and has_uint64, \
            f"maximum_kernel_cuda missing uint dispatch: uint32={has_uint32}, uint64={has_uint64}"

    def test_minimum_dispatches_uint_types(self):
        """Verify minimum_kernel_cuda dispatch includes uint32 and uint64"""
        content = self._read_file(self.MAXMIN_FILE)
        func = self._extract_kernel_function(content, "minimum_kernel_cuda")
        assert func is not None, "Could not find minimum_kernel_cuda function"
        clean = self._strip_comments(func)
        has_uint32 = bool(re.search(r'(kUInt32|uint32_t|at::kUInt32|ScalarType::UInt32)', clean))
        has_uint64 = bool(re.search(r'(kUInt64|uint64_t|at::kUInt64|ScalarType::UInt64)', clean))
        assert has_uint32 and has_uint64, \
            f"minimum_kernel_cuda missing uint dispatch: uint32={has_uint32}, uint64={has_uint64}"

    # === Functional Checks ===

    def test_bitwise_ops_preserves_bool_dispatch(self):
        """Verify bitwise ops still dispatch for bool type (existing behavior preserved)"""
        content = self._read_file(self.BITWISE_OPS_FILE)
        clean = self._strip_comments(content)
        assert re.search(r'kBool|ScalarType::Bool', clean), \
            "Bitwise ops file lost bool type dispatch - existing behavior broken"

    def test_bitwise_ops_preserves_signed_int_dispatch(self):
        """Verify bitwise ops still dispatch for signed integer types"""
        content = self._read_file(self.BITWISE_OPS_FILE)
        clean = self._strip_comments(content)
        has_integral = bool(re.search(r'AT_DISPATCH.*INTEGRAL|AT_DISPATCH_ALL_TYPES', clean))
        assert has_integral, \
            "Bitwise ops lost integral type dispatch macro - signed types no longer supported"

    def test_shift_ops_preserves_signed_int_dispatch(self):
        """Verify shift ops still dispatch for signed integer types"""
        content = self._read_file(self.SHIFT_OPS_FILE)
        clean = self._strip_comments(content)
        has_integral = bool(re.search(r'AT_DISPATCH.*INTEGRAL|AT_DISPATCH_ALL_TYPES', clean))
        assert has_integral, \
            "Shift ops lost integral type dispatch macro - signed types no longer supported"

    def test_maxmin_preserves_signed_int_dispatch(self):
        """Verify max/min ops still dispatch for signed integer types"""
        content = self._read_file(self.MAXMIN_FILE)
        clean = self._strip_comments(content)
        has_integral = bool(re.search(r'AT_DISPATCH.*INTEGRAL|AT_DISPATCH_ALL_TYPES', clean))
        assert has_integral, \
            "Max/min ops lost integral type dispatch macro - signed types no longer supported"

    def test_bitwise_uint_references_in_code_not_comments(self):
        """Verify uint type references in bitwise ops are in actual code, not just comments"""
        content = self._read_file(self.BITWISE_OPS_FILE)
        clean = self._strip_comments(content)
        uint_refs = re.findall(r'(kUInt32|kUInt64|uint32_t|uint64_t)', clean)
        assert len(uint_refs) >= 6, \
            f"Expected at least 6 uint type references in bitwise ops code " \
            f"(3 kernels x 2 types), found {len(uint_refs)}"

    def test_shift_uint_references_in_code_not_comments(self):
        """Verify uint type references in shift ops are in actual code, not just comments"""
        content = self._read_file(self.SHIFT_OPS_FILE)
        clean = self._strip_comments(content)
        uint_refs = re.findall(r'(kUInt32|kUInt64|uint32_t|uint64_t)', clean)
        assert len(uint_refs) >= 4, \
            f"Expected at least 4 uint type references in shift ops code " \
            f"(2 kernels x 2 types), found {len(uint_refs)}"

    def test_maxmin_uint_references_in_code_not_comments(self):
        """Verify uint type references in max/min ops are in actual code, not just comments"""
        content = self._read_file(self.MAXMIN_FILE)
        clean = self._strip_comments(content)
        uint_refs = re.findall(r'(kUInt32|kUInt64|uint32_t|uint64_t)', clean)
        assert len(uint_refs) >= 4, \
            f"Expected at least 4 uint type references in max/min ops code " \
            f"(2 kernels x 2 types), found {len(uint_refs)}"

    def test_all_seven_kernels_have_uint_dispatch(self):
        """Verify all 7 kernel functions have been modified to include uint types"""
        kernels_and_files = [
            (self.BITWISE_OPS_FILE, "bitwise_and_kernel_cuda"),
            (self.BITWISE_OPS_FILE, "bitwise_or_kernel_cuda"),
            (self.BITWISE_OPS_FILE, "bitwise_xor_kernel_cuda"),
            (self.SHIFT_OPS_FILE, "lshift_kernel_cuda"),
            (self.SHIFT_OPS_FILE, "rshift_kernel_cuda"),
            (self.MAXMIN_FILE, "maximum_kernel_cuda"),
            (self.MAXMIN_FILE, "minimum_kernel_cuda"),
        ]

        missing = []
        for rel_path, kernel_name in kernels_and_files:
            content = self._read_file(rel_path)
            func = self._extract_kernel_function(content, kernel_name)
            if func is None:
                missing.append(f"{kernel_name} (function not found)")
                continue
            clean = self._strip_comments(func)
            has_uint = bool(re.search(
                r'(kUInt32|kUInt64|uint32_t|uint64_t|UInt32|UInt64)', clean
            ))
            if not has_uint:
                missing.append(f"{kernel_name} (no uint dispatch)")

        assert len(missing) == 0, \
            f"Kernels not updated with uint types: {', '.join(missing)}"
