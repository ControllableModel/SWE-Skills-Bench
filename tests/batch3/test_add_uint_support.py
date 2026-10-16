"""
Test skill: add-uint-support
Verify that the Agent correctly restores uint32/uint64 operator dispatch support in PyTorch.
"""

import os
import subprocess
import pytest


class TestAddUintSupport:
    REPO_DIR = "/workspace/pytorch"

    # === File Path Checks ===

    def test_dispatch_header_exists(self):
        """Verify that the Dispatch.h header file exists"""
        dispatch_path = os.path.join(self.REPO_DIR, "aten/src/ATen/Dispatch.h")
        assert os.path.exists(dispatch_path), f"Dispatch.h not found at {dispatch_path}"

    def test_test_uint_ops_file_exists(self):
        """Verify that the uint ops test file was created"""
        test_path = os.path.join(self.REPO_DIR, "test/test_uint_ops.py")
        assert os.path.exists(test_path), f"test_uint_ops.py not found at {test_path}"
        # Verify it's valid Python
        import ast
        with open(test_path) as f:
            ast.parse(f.read())

    # === Semantic Checks ===

    def test_dispatch_macro_exists_in_header(self):
        """Verify that AT_DISPATCH_ALL_TYPES_AND_UINT macro is defined in Dispatch.h"""
        dispatch_path = os.path.join(self.REPO_DIR, "aten/src/ATen/Dispatch.h")
        with open(dispatch_path) as f:
            content = f.read()
        assert "AT_DISPATCH_ALL_TYPES_AND_UINT" in content, \
            "AT_DISPATCH_ALL_TYPES_AND_UINT macro not found in Dispatch.h"

    def test_dispatch_macro_includes_uint_types(self):
        """Verify that the new dispatch macro references kUInt32 and kUInt64"""
        dispatch_path = os.path.join(self.REPO_DIR, "aten/src/ATen/Dispatch.h")
        with open(dispatch_path) as f:
            content = f.read()
        assert "kUInt32" in content, "kUInt32 not referenced in Dispatch.h"
        assert "kUInt64" in content, "kUInt64 not referenced in Dispatch.h"

    def test_original_dispatch_macro_unchanged(self):
        """Verify AT_DISPATCH_ALL_TYPES macro still exists (backward compat)"""
        dispatch_path = os.path.join(self.REPO_DIR, "aten/src/ATen/Dispatch.h")
        with open(dispatch_path) as f:
            content = f.read()
        # The original macro must still be present
        assert "AT_DISPATCH_ALL_TYPES(" in content or "#define AT_DISPATCH_ALL_TYPES" in content, \
            "Original AT_DISPATCH_ALL_TYPES macro appears to be removed or renamed"

    def test_unary_ops_dispatch_uint(self):
        """Verify UnaryOps.cpp references uint dispatch"""
        unary_path = os.path.join(self.REPO_DIR, "aten/src/ATen/native/UnaryOps.cpp")
        assert os.path.exists(unary_path), f"UnaryOps.cpp not found at {unary_path}"
        with open(unary_path) as f:
            content = f.read()
        # Should reference the new dispatch macro or kUInt32/kUInt64 directly
        has_uint_dispatch = (
            "AT_DISPATCH_ALL_TYPES_AND_UINT" in content
            or ("kUInt32" in content and "kUInt64" in content)
            or "uint32" in content.lower()
        )
        assert has_uint_dispatch, \
            "UnaryOps.cpp does not appear to dispatch on uint32/uint64 types"

    def test_binary_ops_dispatch_uint(self):
        """Verify BinaryOps.cpp references uint dispatch"""
        binary_path = os.path.join(self.REPO_DIR, "aten/src/ATen/native/BinaryOps.cpp")
        assert os.path.exists(binary_path), f"BinaryOps.cpp not found at {binary_path}"
        with open(binary_path) as f:
            content = f.read()
        has_uint_dispatch = (
            "AT_DISPATCH_ALL_TYPES_AND_UINT" in content
            or ("kUInt32" in content and "kUInt64" in content)
            or "uint32" in content.lower()
        )
        assert has_uint_dispatch, \
            "BinaryOps.cpp does not appear to dispatch on uint32/uint64 types"

    def test_compare_ops_dispatch_uint(self):
        """Verify CompareOps.cpp references uint dispatch"""
        compare_path = os.path.join(self.REPO_DIR, "aten/src/ATen/native/CompareOps.cpp")
        assert os.path.exists(compare_path), f"CompareOps.cpp not found at {compare_path}"
        with open(compare_path) as f:
            content = f.read()
        has_uint_dispatch = (
            "AT_DISPATCH_ALL_TYPES_AND_UINT" in content
            or ("kUInt32" in content and "kUInt64" in content)
            or "uint32" in content.lower()
        )
        assert has_uint_dispatch, \
            "CompareOps.cpp does not appear to dispatch on uint32/uint64 types"

    # === Functional Checks ===

    def test_uint32_addition(self):
        """Verify uint32 tensor addition produces correct results"""
        result = subprocess.run(
            ["python", "-c",
             "import torch; "
             "a = torch.tensor([1, 2, 3], dtype=torch.uint32); "
             "b = torch.tensor([4, 5, 6], dtype=torch.uint32); "
             "c = a + b; "
             "assert c.dtype == torch.uint32, f'Expected uint32, got {c.dtype}'; "
             "assert list(c.numpy()) == [5, 7, 9], f'Expected [5,7,9], got {list(c.numpy())}'; "
             "print('PASS')"],
            cwd=self.REPO_DIR,
            capture_output=True, text=True, timeout=120
        )
        assert result.returncode == 0, f"uint32 addition failed: {result.stderr}"
        assert "PASS" in result.stdout, f"Unexpected output: {result.stdout}"

    def test_uint64_addition(self):
        """Verify uint64 tensor addition produces correct results"""
        result = subprocess.run(
            ["python", "-c",
             "import torch; "
             "a = torch.tensor([10, 20, 30], dtype=torch.uint64); "
             "b = torch.tensor([1, 2, 3], dtype=torch.uint64); "
             "c = a + b; "
             "assert c.dtype == torch.uint64, f'Expected uint64, got {c.dtype}'; "
             "assert list(c.numpy()) == [11, 22, 33], f'Expected [11,22,33], got {list(c.numpy())}'; "
             "print('PASS')"],
            cwd=self.REPO_DIR,
            capture_output=True, text=True, timeout=120
        )
        assert result.returncode == 0, f"uint64 addition failed: {result.stderr}"
        assert "PASS" in result.stdout, f"Unexpected output: {result.stdout}"

    def test_uint32_bitwise_not(self):
        """Verify bitwise_not works on uint32 tensors"""
        result = subprocess.run(
            ["python", "-c",
             "import torch; "
             "a = torch.tensor([0, 255], dtype=torch.uint32); "
             "b = a.bitwise_not(); "
             "assert b.dtype == torch.uint32, f'Expected uint32, got {b.dtype}'; "
             "vals = list(b.numpy()); "
             "assert vals[0] == 0xFFFFFFFF, f'bitwise_not(0) should be 0xFFFFFFFF, got {vals[0]}'; "
             "assert vals[1] == 0xFFFFFFFF - 255, f'bitwise_not(255) wrong, got {vals[1]}'; "
             "print('PASS')"],
            cwd=self.REPO_DIR,
            capture_output=True, text=True, timeout=120
        )
        assert result.returncode == 0, f"uint32 bitwise_not failed: {result.stderr}"
        assert "PASS" in result.stdout, f"Unexpected output: {result.stdout}"

    def test_uint32_abs_identity(self):
        """Verify abs is identity for unsigned types"""
        result = subprocess.run(
            ["python", "-c",
             "import torch; "
             "a = torch.tensor([0, 1, 100, 4294967295], dtype=torch.uint32); "
             "b = a.abs(); "
             "assert list(b.numpy()) == list(a.numpy()), 'abs should be identity for uint32'; "
             "print('PASS')"],
            cwd=self.REPO_DIR,
            capture_output=True, text=True, timeout=120
        )
        assert result.returncode == 0, f"uint32 abs failed: {result.stderr}"
        assert "PASS" in result.stdout, f"Unexpected output: {result.stdout}"

    def test_uint32_neg_raises_error(self):
        """Verify negation on uint32 raises RuntimeError"""
        result = subprocess.run(
            ["python", "-c",
             "import torch; "
             "a = torch.tensor([1], dtype=torch.uint32); "
             "try:\n"
             "    b = -a\n"
             "    print('FAIL: no error raised')\n"
             "except RuntimeError as e:\n"
             "    msg = str(e).lower()\n"
             "    if 'unsigned' in msg or 'negat' in msg or 'not supported' in msg:\n"
             "        print('PASS')\n"
             "    else:\n"
             "        print(f'FAIL: wrong error message: {e}')"],
            cwd=self.REPO_DIR,
            capture_output=True, text=True, timeout=120
        )
        assert "PASS" in result.stdout, \
            f"Negation on uint32 should raise RuntimeError about unsigned types. stdout={result.stdout}, stderr={result.stderr}"

    def test_uint32_comparison_returns_bool(self):
        """Verify comparison ops on uint32 return bool tensors"""
        result = subprocess.run(
            ["python", "-c",
             "import torch; "
             "a = torch.tensor([1, 2, 3], dtype=torch.uint64); "
             "b = torch.tensor([2, 2, 2], dtype=torch.uint64); "
             "c = a > b; "
             "assert c.dtype == torch.bool, f'Expected bool, got {c.dtype}'; "
             "assert list(c.numpy()) == [False, False, True], f'Expected [F,F,T], got {list(c.numpy())}'; "
             "print('PASS')"],
            cwd=self.REPO_DIR,
            capture_output=True, text=True, timeout=120
        )
        assert result.returncode == 0, f"uint64 comparison failed: {result.stderr}"
        assert "PASS" in result.stdout, f"Unexpected output: {result.stdout}"

    def test_uint32_subtraction_underflow_wraps(self):
        """Verify unsigned subtraction underflow wraps around"""
        result = subprocess.run(
            ["python", "-c",
             "import torch; "
             "a = torch.tensor([1], dtype=torch.uint32); "
             "b = torch.tensor([2], dtype=torch.uint32); "
             "c = a - b; "
             "val = int(c.numpy()[0]); "
             "# Should wrap around: 1 - 2 = 0xFFFFFFFF = 4294967295\n"
             "assert val == 4294967295, f'Expected 4294967295 (wrap), got {val}'; "
             "print('PASS')"],
            cwd=self.REPO_DIR,
            capture_output=True, text=True, timeout=120
        )
        assert result.returncode == 0, f"uint32 underflow wrap failed: {result.stderr}"
        assert "PASS" in result.stdout, f"Unexpected output: {result.stdout}"

    def test_uint32_div_by_zero_raises_error(self):
        """Verify division by zero on uint32 raises RuntimeError"""
        result = subprocess.run(
            ["python", "-c",
             "import torch; "
             "a = torch.tensor([10], dtype=torch.uint32); "
             "b = torch.tensor([0], dtype=torch.uint32); "
             "try:\n"
             "    c = torch.div(a, b)\n"
             "    print('FAIL: no error raised')\n"
             "except RuntimeError as e:\n"
             "    msg = str(e).lower()\n"
             "    if 'zero' in msg or 'division' in msg:\n"
             "        print('PASS')\n"
             "    else:\n"
             "        print(f'FAIL: wrong error message: {e}')"],
            cwd=self.REPO_DIR,
            capture_output=True, text=True, timeout=120
        )
        assert "PASS" in result.stdout, \
            f"Division by zero should raise RuntimeError. stdout={result.stdout}, stderr={result.stderr}"

    def test_uint_binary_bitwise_operations(self):
        """Verify bitwise_and, bitwise_or, bitwise_xor work on uint32"""
        result = subprocess.run(
            ["python", "-c",
             "import torch; "
             "a = torch.tensor([0xFF, 0xAA], dtype=torch.uint32); "
             "b = torch.tensor([0x0F, 0x55], dtype=torch.uint32); "
             "r_and = (a & b).numpy().tolist(); "
             "r_or = (a | b).numpy().tolist(); "
             "r_xor = (a ^ b).numpy().tolist(); "
             "assert r_and == [0x0F, 0x00], f'bitwise_and wrong: {r_and}'; "
             "assert r_or == [0xFF, 0xFF], f'bitwise_or wrong: {r_or}'; "
             "assert r_xor == [0xF0, 0xFF], f'bitwise_xor wrong: {r_xor}'; "
             "print('PASS')"],
            cwd=self.REPO_DIR,
            capture_output=True, text=True, timeout=120
        )
        assert result.returncode == 0, f"bitwise ops failed: {result.stderr}"
        assert "PASS" in result.stdout, f"Unexpected output: {result.stdout}"

    def test_uint_mul_and_div(self):
        """Verify multiplication and integer division on uint32"""
        result = subprocess.run(
            ["python", "-c",
             "import torch; "
             "a = torch.tensor([3, 10, 7], dtype=torch.uint32); "
             "b = torch.tensor([4, 3, 2], dtype=torch.uint32); "
             "m = (a * b).numpy().tolist(); "
             "d = torch.div(a, b).numpy().tolist(); "
             "assert m == [12, 30, 14], f'mul wrong: {m}'; "
             "assert d == [0, 3, 3], f'div wrong: {d}'; "
             "print('PASS')"],
            cwd=self.REPO_DIR,
            capture_output=True, text=True, timeout=120
        )
        assert result.returncode == 0, f"mul/div failed: {result.stderr}"
        assert "PASS" in result.stdout, f"Unexpected output: {result.stdout}"

    def test_run_uint_ops_test_file(self):
        """Verify that the test_uint_ops.py file runs and passes"""
        test_path = os.path.join(self.REPO_DIR, "test/test_uint_ops.py")
        if not os.path.exists(test_path):
            pytest.skip("test/test_uint_ops.py not found")
        result = subprocess.run(
            ["python", "-m", "pytest", test_path, "-v", "--tb=short"],
            cwd=self.REPO_DIR,
            capture_output=True, text=True, timeout=300
        )
        assert result.returncode == 0, \
            f"test_uint_ops.py failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
