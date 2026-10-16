"""
Tests for v3-performance-optimization skill.
Verifies creation of a Triton-based causal flash attention kernel,
benchmark suite, memory profiler, benchmark utilities, and correctness tests.
"""

import ast
import os
import re

import pytest


class TestV3PerformanceOptimization:
    """Tests for v3-performance-optimization skill."""

    REPO_DIR = "/workspace/flash-attention"

    # ------------------------------------------------------------------ #
    #  file_path_check – verify expected files exist
    # ------------------------------------------------------------------ #

    def test_flash_attn_triton_exists(self):
        assert os.path.isfile(os.path.join(self.REPO_DIR, "flash_attn", "flash_attn_triton.py"))

    def test_benchmark_causal_exists(self):
        assert os.path.isfile(os.path.join(self.REPO_DIR, "benchmarks", "benchmark_causal.py"))

    def test_benchmark_memory_exists(self):
        assert os.path.isfile(os.path.join(self.REPO_DIR, "benchmarks", "benchmark_memory.py"))

    def test_benchmark_utils_exists(self):
        assert os.path.isfile(os.path.join(self.REPO_DIR, "flash_attn", "utils", "benchmark_utils.py"))

    def test_test_causal_correctness_exists(self):
        assert os.path.isfile(os.path.join(self.REPO_DIR, "tests", "test_causal_correctness.py"))

    # ------------------------------------------------------------------ #
    #  semantic_check – structural / content validation
    # ------------------------------------------------------------------ #

    def _read(self, relpath):
        path = os.path.join(self.REPO_DIR, relpath)
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def test_triton_kernel_valid_python(self):
        """flash_attn_triton.py is syntactically valid Python."""
        content = self._read("flash_attn/flash_attn_triton.py")
        try:
            ast.parse(content)
        except SyntaxError as e:
            pytest.fail(f"flash_attn_triton.py has syntax error: {e}")

    def test_triton_kernel_uses_triton(self):
        """flash_attn_triton.py imports and uses Triton."""
        content = self._read("flash_attn/flash_attn_triton.py")
        assert "import triton" in content or "from triton" in content, \
            "Should import triton"
        assert "triton.jit" in content or "@triton.jit" in content or "tl." in content, \
            "Should use triton.jit decorator or triton language primitives"

    def test_triton_kernel_implements_causal_masking(self):
        """Kernel implements causal masking logic."""
        content = self._read("flash_attn/flash_attn_triton.py").lower()
        assert "causal" in content, "Should reference causal masking"
        assert "mask" in content, "Should implement masking logic"

    def test_triton_kernel_tiled_blocks(self):
        """Kernel uses tiling with configurable block sizes."""
        content = self._read("flash_attn/flash_attn_triton.py")
        assert "BLOCK" in content or "block_size" in content.lower() or "BLOCK_M" in content, \
            "Should define block/tile sizes"
        # Should support block sizes 64 and 128
        assert "64" in content and "128" in content, \
            "Should support block sizes of 64 and 128"

    def test_triton_kernel_skips_masked_blocks(self):
        """Kernel skips fully-masked blocks for efficiency."""
        content = self._read("flash_attn/flash_attn_triton.py").lower()
        # Should have logic to skip blocks where all elements are masked
        has_skip = "skip" in content or "continue" in content or "if " in content
        has_causal_check = "causal" in content and ("block" in content or "tile" in content)
        assert has_skip or has_causal_check, \
            "Should skip fully-masked blocks in causal attention"

    def test_benchmark_causal_valid_python(self):
        """benchmark_causal.py is syntactically valid."""
        content = self._read("benchmarks/benchmark_causal.py")
        try:
            ast.parse(content)
        except SyntaxError as e:
            pytest.fail(f"benchmark_causal.py has syntax error: {e}")

    def test_benchmark_causal_configurations(self):
        """benchmark_causal.py tests multiple sequence lengths and head dims."""
        content = self._read("benchmarks/benchmark_causal.py")
        assert "512" in content, "Should test seqlen 512"
        assert "1024" in content, "Should test seqlen 1024"
        assert "2048" in content, "Should test seqlen 2048"
        assert "4096" in content, "Should test seqlen 4096"
        assert "64" in content and "128" in content, "Should test head dims 64 and 128"

    def test_benchmark_causal_outputs_json(self):
        """benchmark_causal.py outputs results in JSON format."""
        content = self._read("benchmarks/benchmark_causal.py").lower()
        assert "json" in content, "Should output JSON results"

    # ------------------------------------------------------------------ #
    #  functional_check – deeper content validation
    # ------------------------------------------------------------------ #

    def test_benchmark_memory_measures_peak(self):
        """benchmark_memory.py uses torch.cuda.max_memory_allocated."""
        content = self._read("benchmarks/benchmark_memory.py")
        assert "max_memory_allocated" in content, \
            "Should use torch.cuda.max_memory_allocated for peak memory"

    def test_benchmark_memory_configurations(self):
        """benchmark_memory.py covers required batch/seqlen configurations."""
        content = self._read("benchmarks/benchmark_memory.py")
        assert "1024" in content and "2048" in content and "4096" in content, \
            "Should test sequence lengths 1024, 2048, 4096"

    def test_benchmark_utils_timing(self):
        """benchmark_utils.py provides GPU timing utilities."""
        content = self._read("flash_attn/utils/benchmark_utils.py").lower()
        assert "cuda" in content or "event" in content or "synchronize" in content, \
            "Should provide CUDA timing utilities"
        assert "warmup" in content, "Should support warmup iterations"

    def test_correctness_tests_valid_python(self):
        """test_causal_correctness.py is syntactically valid."""
        content = self._read("tests/test_causal_correctness.py")
        try:
            ast.parse(content)
        except SyntaxError as e:
            pytest.fail(f"test_causal_correctness.py has syntax error: {e}")

    def test_correctness_tests_tolerance(self):
        """test_causal_correctness.py uses atol=1e-3 tolerance."""
        content = self._read("tests/test_causal_correctness.py")
        assert "atol" in content, "Should specify absolute tolerance"
        assert "1e-3" in content or "0.001" in content, "Should use atol=1e-3"

    def test_correctness_tests_multiple_shapes(self):
        """test_causal_correctness.py tests at least 5 input shape combinations."""
        content = self._read("tests/test_causal_correctness.py")
        # Count parametrize decorators or distinct shape tuples
        shape_tuples = re.findall(r'\(\d+,\s*\d+,\s*\d+,\s*\d+\)', content)
        param_match = re.search(r'parametrize', content)
        assert len(shape_tuples) >= 5 or param_match, \
            "Should test at least 5 different (batch, nheads, seqlen, headdim) combinations"

    def test_correctness_tests_fp16(self):
        """test_causal_correctness.py tests with fp16 dtype."""
        content = self._read("tests/test_causal_correctness.py").lower()
        assert "float16" in content or "fp16" in content or "half" in content, \
            "Should test with fp16 dtype"

    def test_triton_kernel_supports_bf16(self):
        """Kernel supports both fp16 and bf16 dtypes."""
        content = self._read("flash_attn/flash_attn_triton.py").lower()
        assert "bfloat16" in content or "bf16" in content, \
            "Kernel should support bf16 dtype"

    def test_benchmark_causal_reports_tflops(self):
        """benchmark_causal.py computes and reports TFLOPS."""
        content = self._read("benchmarks/benchmark_causal.py").lower()
        assert "tflops" in content or "flops" in content, \
            "Should compute and report TFLOPS"
