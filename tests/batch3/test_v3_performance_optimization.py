"""
Tests for the v3-performance-optimization skill.

Validates that a Flash Attention benchmark suite with memory optimization
analysis was implemented, including attention benchmarks, memory analysis,
benchmark report generation, and correctness tests.

Repo: flash-attention (https://github.com/Dao-AILab/flash-attention)
"""

import os
import re
import subprocess
import sys

REPO_DIR = "/workspace/flash-attention"


class TestFilePathCheck:
    """Verify all required files were created."""

    def test_benchmark_attention_exists(self):
        path = os.path.join(REPO_DIR, "benchmarks", "benchmark_attention.py")
        assert os.path.isfile(path), f"Expected benchmarks/benchmark_attention.py"

    def test_memory_analysis_exists(self):
        path = os.path.join(REPO_DIR, "benchmarks", "memory_analysis.py")
        assert os.path.isfile(path), f"Expected benchmarks/memory_analysis.py"

    def test_benchmark_report_exists(self):
        path = os.path.join(REPO_DIR, "benchmarks", "benchmark_report.py")
        assert os.path.isfile(path), f"Expected benchmarks/benchmark_report.py"

    def test_test_benchmark_suite_exists(self):
        path = os.path.join(REPO_DIR, "tests", "test_benchmark_suite.py")
        assert os.path.isfile(path), f"Expected tests/test_benchmark_suite.py"


class TestSemanticBenchmarkAttention:
    """Verify attention benchmark suite."""

    def _read(self):
        path = os.path.join(REPO_DIR, "benchmarks", "benchmark_attention.py")
        with open(path, "r") as f:
            return f.read()

    def test_class_definition(self):
        content = self._read()
        assert re.search(r"class\s+AttentionBenchmark", content), (
            "Expected AttentionBenchmark class"
        )

    def test_batch_sizes(self):
        content = self._read()
        for bs in ["1", "4", "8", "16"]:
            assert bs in content, f"Expected batch size {bs}"

    def test_sequence_lengths(self):
        content = self._read()
        for sl in ["512", "1024", "2048", "4096"]:
            assert sl in content, f"Expected sequence length {sl}"

    def test_flash_attention_import(self):
        content = self._read()
        assert re.search(r"flash_attn|flash_attention", content, re.IGNORECASE), (
            "Expected Flash Attention implementation reference"
        )

    def test_standard_attention(self):
        content = self._read()
        assert re.search(r"scaled_dot_product_attention|standard.*attention", content, re.IGNORECASE), (
            "Expected PyTorch standard attention comparison"
        )

    def test_cuda_events_timing(self):
        content = self._read()
        assert re.search(r"cuda.*event|Event\(|start\.record|elapsed_time", content, re.IGNORECASE), (
            "Expected CUDA event timing (not wall-clock)"
        )

    def test_flops_calculation(self):
        content = self._read()
        assert re.search(r"4\s*\*|flops|FLOPS|tflops|TFLOPS", content, re.IGNORECASE), (
            "Expected FLOPS calculation (4 * batch * heads * seq_len^2 * head_dim)"
        )

    def test_warmup_runs(self):
        content = self._read()
        assert re.search(r"warmup|warm_up|warm.*up", content, re.IGNORECASE), (
            "Expected warmup runs before measurement"
        )

    def test_memory_estimation_skip(self):
        content = self._read()
        assert re.search(r"skip|exceed|memory.*limit|OOM", content, re.IGNORECASE), (
            "Expected skipping configurations that exceed GPU memory"
        )


class TestSemanticMemoryAnalysis:
    """Verify memory analysis module."""

    def _read(self):
        path = os.path.join(REPO_DIR, "benchmarks", "memory_analysis.py")
        with open(path, "r") as f:
            return f.read()

    def test_class_definition(self):
        content = self._read()
        assert re.search(r"class\s+MemoryAnalyzer", content), (
            "Expected MemoryAnalyzer class"
        )

    def test_peak_memory(self):
        content = self._read()
        assert re.search(r"max_memory_allocated|peak.*memory", content, re.IGNORECASE), (
            "Expected peak memory measurement via torch.cuda.max_memory_allocated"
        )

    def test_memory_savings_ratio(self):
        content = self._read()
        assert re.search(r"savings.*ratio|memory.*ratio|savings", content, re.IGNORECASE), (
            "Expected memory savings ratio computation"
        )

    def test_linear_growth_check(self):
        content = self._read()
        assert re.search(r"linear|O\(N\)|regression", content, re.IGNORECASE), (
            "Expected verification of Flash Attention O(N) memory"
        )

    def test_quadratic_growth_check(self):
        content = self._read()
        assert re.search(r"quadratic|O\(N.?2\)|N\^2|N\*\*2", content, re.IGNORECASE), (
            "Expected verification of standard attention O(N^2) memory"
        )


class TestSemanticBenchmarkReport:
    """Verify benchmark report generation."""

    def _read(self):
        path = os.path.join(REPO_DIR, "benchmarks", "benchmark_report.py")
        with open(path, "r") as f:
            return f.read()

    def test_class_definition(self):
        content = self._read()
        assert re.search(r"class\s+BenchmarkReport", content), (
            "Expected BenchmarkReport class"
        )

    def test_speedup_table(self):
        content = self._read()
        assert re.search(r"speedup|Speedup", content), (
            "Expected speedup table generation"
        )

    def test_memory_savings_table(self):
        content = self._read()
        assert re.search(r"memory.*saving|savings|Memory", content, re.IGNORECASE), (
            "Expected memory savings table"
        )

    def test_scaling_analysis(self):
        content = self._read()
        assert re.search(r"scaling|scale|seq.*len", content, re.IGNORECASE), (
            "Expected scaling analysis (how speedup changes with seq_len)"
        )

    def test_peak_performance(self):
        content = self._read()
        assert re.search(r"peak.*performance|highest.*tflops|max.*tflops", content, re.IGNORECASE), (
            "Expected peak performance identification"
        )

    def test_csv_export(self):
        content = self._read()
        assert re.search(r"csv|CSV|to_csv", content), (
            "Expected CSV export format"
        )

    def test_json_export(self):
        content = self._read()
        assert re.search(r"json|JSON|to_json", content), (
            "Expected JSON export format"
        )


class TestSemanticCorrectnessAndReproducibility:
    """Verify correctness verification and reproducibility."""

    def _read_benchmark(self):
        path = os.path.join(REPO_DIR, "benchmarks", "benchmark_attention.py")
        with open(path, "r") as f:
            return f.read()

    def test_torch_allclose(self):
        content = self._read_benchmark()
        assert re.search(r"allclose|torch\.allclose", content), (
            "Expected torch.allclose correctness verification"
        )

    def test_random_seed(self):
        content = self._read_benchmark()
        assert re.search(r"manual_seed|seed.*42|torch\.manual_seed", content), (
            "Expected random seed for reproducibility (42)"
        )

    def test_fp16_support(self):
        content = self._read_benchmark()
        assert re.search(r"float16|fp16|half", content, re.IGNORECASE), (
            "Expected FP16 data type support"
        )

    def test_bf16_support(self):
        content = self._read_benchmark()
        assert re.search(r"bfloat16|bf16", content, re.IGNORECASE), (
            "Expected BF16 data type support"
        )


class TestFunctionalPythonSyntax:
    """Validate Python files compile and tests pass."""

    def test_benchmark_attention_syntax(self):
        path = os.path.join(REPO_DIR, "benchmarks", "benchmark_attention.py")
        with open(path, "r") as f:
            content = f.read()
        compile(content, path, "exec")

    def test_memory_analysis_syntax(self):
        path = os.path.join(REPO_DIR, "benchmarks", "memory_analysis.py")
        with open(path, "r") as f:
            content = f.read()
        compile(content, path, "exec")

    def test_benchmark_report_syntax(self):
        path = os.path.join(REPO_DIR, "benchmarks", "benchmark_report.py")
        with open(path, "r") as f:
            content = f.read()
        compile(content, path, "exec")

    def test_agent_tests_pass(self):
        test_path = os.path.join(REPO_DIR, "tests", "test_benchmark_suite.py")
        if os.path.isfile(test_path):
            result = subprocess.run(
                [sys.executable, "-m", "pytest", test_path, "-v", "--tb=short"],
                cwd=REPO_DIR,
                capture_output=True,
                text=True,
                timeout=120,
            )
            assert result.returncode == 0, (
                f"Agent tests failed:\n{result.stdout[-1000:]}\n{result.stderr[-500:]}"
            )
