"""
Test skill: v3-performance-optimization
Verify that the Agent implements a Flash Attention Benchmark Suite —
benchmark_utils.py (BenchmarkResult, compute_attention_tflops, measure_peak_memory_mb,
benchmark_forward), benchmark_flash_attn_v2.py (configs, run_all_benchmarks,
print_comparison_table, speedup validation), and unit tests.
"""

import os
import re
import subprocess
import pytest


class TestV3PerformanceOptimization:
    REPO_DIR = "/workspace/flash-attention"

    # ────── helpers ──────

    def _read(self, rel_path):
        fpath = os.path.join(self.REPO_DIR, rel_path)
        with open(fpath, "r") as f:
            return f.read()

    def _exists(self, rel_path):
        return os.path.isfile(os.path.join(self.REPO_DIR, rel_path))

    # === File Path Checks ===

    def test_benchmark_utils_exists(self):
        """benchmark_utils.py must exist"""
        assert self._exists("benchmarks/benchmark_utils.py")

    def test_benchmark_script_exists(self):
        """benchmark_flash_attn_v2.py must exist"""
        assert self._exists("benchmarks/benchmark_flash_attn_v2.py")

    def test_correctness_test_exists(self):
        """test_benchmark_correctness.py must exist"""
        assert self._exists("tests/test_benchmark_correctness.py")

    # === Semantic Checks — benchmark_utils.py ===

    def test_benchmark_result_dataclass(self):
        """BenchmarkResult dataclass must be defined"""
        src = self._read("benchmarks/benchmark_utils.py")
        assert "BenchmarkResult" in src

    def test_benchmark_result_fields(self):
        """BenchmarkResult must have tflops, memory_mb, latency_ms, dtype"""
        src = self._read("benchmarks/benchmark_utils.py")
        for field in ["tflops", "memory_mb", "latency_ms", "dtype"]:
            assert field in src, f"Missing field: {field}"

    def test_compute_attention_tflops_func(self):
        """compute_attention_tflops function must be defined"""
        src = self._read("benchmarks/benchmark_utils.py")
        assert "compute_attention_tflops" in src

    def test_causal_tflops_factor(self):
        """Must differentiate causal vs non-causal FLOPs calculation"""
        src = self._read("benchmarks/benchmark_utils.py")
        assert "causal" in src.lower()

    def test_measure_peak_memory_func(self):
        """measure_peak_memory_mb function must be defined"""
        src = self._read("benchmarks/benchmark_utils.py")
        assert "measure_peak_memory_mb" in src

    def test_cuda_memory_stats(self):
        """Must use torch.cuda memory stats"""
        src = self._read("benchmarks/benchmark_utils.py")
        assert "reset_peak_memory_stats" in src or "max_memory_allocated" in src

    def test_benchmark_forward_func(self):
        """benchmark_forward function must be defined"""
        src = self._read("benchmarks/benchmark_utils.py")
        assert "benchmark_forward" in src

    def test_cuda_synchronize(self):
        """Must use torch.cuda.synchronize for timing"""
        src = self._read("benchmarks/benchmark_utils.py")
        assert "synchronize" in src

    def test_warmup_iters(self):
        """Must support warmup iterations"""
        src = self._read("benchmarks/benchmark_utils.py")
        assert "warmup" in src.lower()

    # === Semantic Checks — benchmark_flash_attn_v2.py ===

    def test_benchmark_configs(self):
        """BENCHMARK_CONFIGS must be defined with multiple configs"""
        src = self._read("benchmarks/benchmark_flash_attn_v2.py")
        assert "BENCHMARK_CONFIGS" in src

    def test_multiple_seq_lengths(self):
        """Must benchmark multiple sequence lengths"""
        src = self._read("benchmarks/benchmark_flash_attn_v2.py")
        for seq in ["512", "1024", "4096"]:
            assert seq in src, f"Missing seq length: {seq}"

    def test_dtype_options(self):
        """Must support float16 and bfloat16"""
        src = self._read("benchmarks/benchmark_flash_attn_v2.py")
        assert "float16" in src
        assert "bfloat16" in src

    def test_flash_attn_import(self):
        """Must import flash_attn"""
        src = self._read("benchmarks/benchmark_flash_attn_v2.py")
        assert "flash_attn" in src

    def test_run_all_benchmarks(self):
        """run_all_benchmarks function must exist"""
        src = self._read("benchmarks/benchmark_flash_attn_v2.py")
        assert "run_all_benchmarks" in src

    def test_print_comparison_table(self):
        """print_comparison_table function must exist"""
        src = self._read("benchmarks/benchmark_flash_attn_v2.py")
        assert "print_comparison_table" in src

    def test_speedup_validation(self):
        """Must validate speedup with assertions"""
        src = self._read("benchmarks/benchmark_flash_attn_v2.py")
        assert "speedup" in src.lower()
        assert "assert" in src

    def test_memory_savings_reporting(self):
        """Must report memory savings"""
        src = self._read("benchmarks/benchmark_flash_attn_v2.py")
        lower = src.lower()
        assert "memory" in lower and ("saving" in lower or "reduction" in lower)

    # === Semantic Checks — Unit Tests ===

    def test_tflops_test_cases(self):
        """Test file must verify TFLOP calculations"""
        src = self._read("tests/test_benchmark_correctness.py")
        assert "tflops" in src.lower() or "compute_attention" in src

    def test_causal_test(self):
        """Test file must verify causal vs non-causal difference"""
        src = self._read("tests/test_benchmark_correctness.py")
        assert "causal" in src.lower()

    # === Functional Checks ===

    def test_python_syntax_utils(self):
        """benchmark_utils.py must have valid syntax"""
        result = subprocess.run(
            ["python", "-c",
             "import py_compile; py_compile.compile('benchmarks/benchmark_utils.py', doraise=True)"],
            capture_output=True, text=True, cwd=self.REPO_DIR, timeout=30,
        )
        assert result.returncode == 0, f"Syntax error:\n{result.stderr}"

    def test_python_syntax_benchmark(self):
        """benchmark_flash_attn_v2.py must have valid syntax"""
        result = subprocess.run(
            ["python", "-c",
             "import py_compile; py_compile.compile('benchmarks/benchmark_flash_attn_v2.py', doraise=True)"],
            capture_output=True, text=True, cwd=self.REPO_DIR, timeout=30,
        )
        assert result.returncode == 0, f"Syntax error:\n{result.stderr}"

    def test_correctness_tests_pass(self):
        """Correctness tests must pass"""
        result = subprocess.run(
            ["python", "-m", "pytest",
             "tests/test_benchmark_correctness.py",
             "-v", "--tb=short"],
            capture_output=True, text=True, cwd=self.REPO_DIR, timeout=120,
        )
        assert result.returncode == 0, (
            f"Tests failed:\n{result.stdout}\n{result.stderr}"
        )
