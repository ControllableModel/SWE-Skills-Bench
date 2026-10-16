"""
Tests for the v3-performance-optimization skill.
Validates a Flash Attention benchmarking suite with attention benchmarks,
memory profiling, performance analysis, and report generation.
"""

import os
import re
import ast

REPO_DIR = "/workspace/flash-attention"
BENCH_DIR = os.path.join(REPO_DIR, "benchmarks")


class TestV3PerformanceOptimization:
    """Tests for the Flash Attention benchmark suite."""

    # ── file_path_check ──────────────────────────────────────────────

    def test_attention_benchmark_exists(self):
        """AttentionBenchmark module must exist."""
        path = os.path.join(BENCH_DIR, "attention_benchmark.py")
        assert os.path.isfile(path), f"Missing {path}"

    def test_memory_profiler_exists(self):
        """MemoryProfiler module must exist."""
        path = os.path.join(BENCH_DIR, "memory_profiler.py")
        assert os.path.isfile(path), f"Missing {path}"

    def test_performance_analyzer_exists(self):
        """PerformanceAnalyzer module must exist."""
        path = os.path.join(BENCH_DIR, "performance_analyzer.py")
        assert os.path.isfile(path), f"Missing {path}"

    def test_benchmark_report_exists(self):
        """BenchmarkReport module must exist."""
        path = os.path.join(BENCH_DIR, "benchmark_report.py")
        assert os.path.isfile(path), f"Missing {path}"

    # ── semantic_check ───────────────────────────────────────────────

    def _read(self, filename):
        path = os.path.join(BENCH_DIR, filename)
        if not os.path.isfile(path):
            return ""
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def test_benchmark_class_methods(self):
        """AttentionBenchmark must define benchmark_standard_attention, benchmark_flash_attention, sweep."""
        content = self._read("attention_benchmark.py")
        assert re.search(r"class\s+AttentionBenchmark", content), (
            "AttentionBenchmark class not defined"
        )
        for method in ["benchmark_standard_attention", "benchmark_flash_attention", "sweep"]:
            assert re.search(rf"def\s+{method}\b", content), f"{method} not defined"

    def test_memory_profiler_class(self):
        """MemoryProfiler must define profile_operation, compare_memory, estimate_memory."""
        content = self._read("memory_profiler.py")
        assert re.search(r"class\s+MemoryProfiler", content), (
            "MemoryProfiler class not defined"
        )
        for method in ["profile_operation", "compare_memory", "estimate_memory"]:
            assert re.search(rf"def\s+{method}\b", content), f"{method} not defined"

    def test_analyzer_class(self):
        """PerformanceAnalyzer must define compute_speedup_summary, pareto_frontier, find_crossover_point, optimal_config."""
        content = self._read("performance_analyzer.py")
        assert re.search(r"class\s+PerformanceAnalyzer", content), (
            "PerformanceAnalyzer class not defined"
        )
        for method in ["compute_speedup_summary", "pareto_frontier",
                        "find_crossover_point", "optimal_config"]:
            assert re.search(rf"def\s+{method}\b", content), f"{method} not defined"

    def test_report_class(self):
        """BenchmarkReport must define generate and to_markdown."""
        content = self._read("benchmark_report.py")
        assert re.search(r"class\s+BenchmarkReport", content), (
            "BenchmarkReport class not defined"
        )
        assert re.search(r"def\s+generate\b", content), "generate method not defined"
        assert re.search(r"def\s+to_markdown\b", content), "to_markdown method not defined"

    def test_flops_calculation(self):
        """Benchmark must compute FLOPs for attention operations."""
        content = self._read("attention_benchmark.py")
        assert re.search(r"flops|FLOPS|FLOPs", content, re.IGNORECASE), (
            "FLOPs calculation not found"
        )

    def test_oom_handling(self):
        """Sweep must handle OOM errors gracefully."""
        content = self._read("attention_benchmark.py")
        assert re.search(r"OOM|OutOfMemory|oom|RuntimeError|CUDA.*memory", content, re.IGNORECASE), (
            "OOM error handling not found"
        )

    def test_speedup_computation(self):
        """Benchmark must compute speedup ratios (standard/flash)."""
        content = self._read("attention_benchmark.py") + self._read("performance_analyzer.py")
        assert re.search(r"speedup|speed_up", content, re.IGNORECASE), (
            "Speedup computation not found"
        )

    def test_memory_savings_formula(self):
        """MemoryProfiler must compute savings_pct."""
        content = self._read("memory_profiler.py")
        assert re.search(r"savings_pct|savings.*percent", content, re.IGNORECASE), (
            "Memory savings percentage not computed"
        )

    # ── functional_check ─────────────────────────────────────────────

    def test_all_files_valid_python(self):
        """All benchmark Python files must have valid syntax."""
        errors = []
        for fname in ["attention_benchmark.py", "memory_profiler.py",
                       "performance_analyzer.py", "benchmark_report.py"]:
            content = self._read(fname)
            if not content:
                continue
            try:
                ast.parse(content)
            except SyntaxError as e:
                errors.append(f"{fname}: {e}")
        assert not errors, "Syntax errors:\n" + "\n".join(errors)

    def test_cuda_requirement(self):
        """Benchmark must check CUDA availability."""
        content = self._read("attention_benchmark.py")
        assert re.search(r"cuda|CUDA|is_available", content), (
            "CUDA availability check not found"
        )

    def test_recommendations_in_report(self):
        """Report must generate recommendations based on results."""
        content = self._read("benchmark_report.py")
        assert re.search(r"recommendation|Recommended|recommend", content, re.IGNORECASE), (
            "Recommendations not found in report"
        )

    def test_crossover_binary_search(self):
        """find_crossover_point must use binary search approach."""
        content = self._read("performance_analyzer.py")
        assert re.search(r"binary.*search|low.*high|mid|crossover", content, re.IGNORECASE), (
            "Binary search for crossover point not found"
        )

    def test_test_file_exists(self):
        """Test file must exist."""
        path = os.path.join(REPO_DIR, "tests", "test_v3_performance_optimization.py")
        assert os.path.isfile(path), f"Missing {path}"
