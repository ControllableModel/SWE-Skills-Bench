"""
Tests for skill: v3-performance-optimization
Repo: Dao-AILab/flash-attention
Image: zhangyiiiiii/swe-skills-bench-python
Task: Implement a performance benchmark suite with Flash Attention and HNSW
      search optimization targets, memory profiling, and report generation.
"""

import ast
import os
import sys

import pytest

REPO_DIR = "/workspace/flash-attention"
BENCH_DIR = os.path.join(REPO_DIR, "benchmarks")

INIT_FILE = os.path.join(BENCH_DIR, "__init__.py")
ATTENTION_FILE = os.path.join(BENCH_DIR, "attention_benchmark.py")
SEARCH_FILE = os.path.join(BENCH_DIR, "search_benchmark.py")
MEMORY_FILE = os.path.join(BENCH_DIR, "memory_benchmark.py")
REPORT_FILE = os.path.join(BENCH_DIR, "report_generator.py")


# ---------------------------------------------------------------------------
# Layer 1 — file_path_check
# ---------------------------------------------------------------------------

class TestFilePathCheck:
    """Verify all benchmark suite files exist."""

    def test_init_exists(self):
        assert os.path.isfile(INIT_FILE), f"Missing {INIT_FILE}"

    def test_attention_benchmark_exists(self):
        assert os.path.isfile(ATTENTION_FILE), f"Missing {ATTENTION_FILE}"

    def test_search_benchmark_exists(self):
        assert os.path.isfile(SEARCH_FILE), f"Missing {SEARCH_FILE}"

    def test_memory_benchmark_exists(self):
        assert os.path.isfile(MEMORY_FILE), f"Missing {MEMORY_FILE}"

    def test_report_generator_exists(self):
        assert os.path.isfile(REPORT_FILE), f"Missing {REPORT_FILE}"


# ---------------------------------------------------------------------------
# Layer 2 — semantic_check
# ---------------------------------------------------------------------------

class TestSemanticAttentionBenchmark:
    """Verify attention benchmark module structure."""

    @pytest.fixture(autouse=True)
    def _load(self):
        with open(ATTENTION_FILE, "r", encoding="utf-8") as f:
            self.src = f.read()
        self.tree = ast.parse(self.src)

    def test_attention_benchmark_class(self):
        classes = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.ClassDef)]
        assert "AttentionBenchmark" in classes, (
            f"Expected AttentionBenchmark; found {classes}"
        )

    def test_standard_attention(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "standard_attention" in funcs, (
            f"Expected standard_attention; found {funcs}"
        )

    def test_flash_attention(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "flash_attention" in funcs, f"Expected flash_attention; found {funcs}"

    def test_benchmark_attention(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "benchmark_attention" in funcs, (
            f"Expected benchmark_attention; found {funcs}"
        )

    def test_softmax_formula(self):
        assert "softmax" in self.src.lower(), (
            "standard_attention should compute softmax(QK^T/sqrt(d_k))V"
        )

    def test_cuda_sync(self):
        assert "synchronize" in self.src, "Should use cuda.synchronize() for timing"

    def test_seq_lengths(self):
        assert "4096" in self.src or "2048" in self.src, (
            "Should benchmark at large sequence lengths"
        )


class TestSemanticSearchBenchmark:
    """Verify search benchmark module structure."""

    @pytest.fixture(autouse=True)
    def _load(self):
        with open(SEARCH_FILE, "r", encoding="utf-8") as f:
            self.src = f.read()
        self.tree = ast.parse(self.src)

    def test_search_benchmark_class(self):
        classes = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.ClassDef)]
        assert "SearchBenchmark" in classes, (
            f"Expected SearchBenchmark; found {classes}"
        )

    def test_linear_search(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "linear_search" in funcs, f"Expected linear_search; found {funcs}"

    def test_hnsw_search(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "hnsw_search" in funcs, f"Expected hnsw_search; found {funcs}"

    def test_build_hnsw_index(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "build_hnsw_index" in funcs, f"Expected build_hnsw_index; found {funcs}"

    def test_benchmark_search(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "benchmark_search" in funcs, f"Expected benchmark_search; found {funcs}"

    def test_recall_validation(self):
        assert "recall" in self.src.lower(), (
            "Should validate recall@k for HNSW results"
        )

    def test_fixed_seed(self):
        assert "seed" in self.src, "Should use fixed seed for reproducibility"

    def test_hnsw_library(self):
        assert "hnswlib" in self.src or "faiss" in self.src, (
            "Should use hnswlib or faiss for HNSW index"
        )


class TestSemanticMemoryBenchmark:
    """Verify memory benchmark module structure."""

    @pytest.fixture(autouse=True)
    def _load(self):
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            self.src = f.read()
        self.tree = ast.parse(self.src)

    def test_memory_benchmark_class(self):
        classes = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.ClassDef)]
        assert "MemoryBenchmark" in classes, (
            f"Expected MemoryBenchmark; found {classes}"
        )

    def test_measure_attention_memory(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "measure_attention_memory" in funcs, (
            f"Expected measure_attention_memory; found {funcs}"
        )

    def test_measure_search_memory(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "measure_search_memory" in funcs, (
            f"Expected measure_search_memory; found {funcs}"
        )

    def test_tracemalloc_usage(self):
        assert "tracemalloc" in self.src, "Should use tracemalloc for memory tracking"


class TestSemanticReportGenerator:
    """Verify report generator module structure."""

    @pytest.fixture(autouse=True)
    def _load(self):
        with open(REPORT_FILE, "r", encoding="utf-8") as f:
            self.src = f.read()
        self.tree = ast.parse(self.src)

    def test_performance_report_class(self):
        classes = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.ClassDef)]
        assert "PerformanceReport" in classes, (
            f"Expected PerformanceReport; found {classes}"
        )

    def test_generate_method(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "generate" in funcs, f"Expected generate(); found {funcs}"

    def test_to_markdown(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "to_markdown" in funcs, f"Expected to_markdown(); found {funcs}"

    def test_to_json(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "to_json" in funcs, f"Expected to_json(); found {funcs}"

    def test_target_validation(self):
        assert "2.49" in self.src or "target" in self.src.lower(), (
            "Should validate against performance targets"
        )

    def test_recommendations(self):
        assert "recommendations" in self.src, (
            "Should generate recommendations for unmet targets"
        )


# ---------------------------------------------------------------------------
# Layer 3 — functional_check
# ---------------------------------------------------------------------------

class TestFunctionalReportGeneration:
    """Run PerformanceReport on synthetic data."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        sys.path.insert(0, BENCH_DIR)
        sys.path.insert(0, REPO_DIR)
        try:
            from report_generator import PerformanceReport
            self.PerformanceReport = PerformanceReport
        except ImportError:
            try:
                from benchmarks.report_generator import PerformanceReport
                self.PerformanceReport = PerformanceReport
            except ImportError:
                pytest.skip("Cannot import PerformanceReport")

    def _make_attention_results(self):
        return [
            {"seq_length": 512, "standard_ms": 10.0, "flash_ms": 3.0, "speedup": 3.33, "output_matches": True},
            {"seq_length": 1024, "standard_ms": 40.0, "flash_ms": 8.0, "speedup": 5.0, "output_matches": True},
            {"seq_length": 2048, "standard_ms": 160.0, "flash_ms": 25.0, "speedup": 6.4, "output_matches": True},
        ]

    def _make_search_results(self):
        return [
            {"dataset_size": 1000, "linear_ms": 5.0, "hnsw_ms": 0.03, "speedup": 166.7, "recall_at_k": 0.98},
            {"dataset_size": 100000, "linear_ms": 500.0, "hnsw_ms": 0.05, "speedup": 10000.0, "recall_at_k": 0.96},
        ]

    def _make_memory_results(self):
        return [
            {"standard_mb": 1024.0, "flash_mb": 256.0, "reduction_percent": 75.0},
        ]

    def test_generate_returns_dict(self):
        report = self.PerformanceReport()
        result = report.generate(
            self._make_attention_results(),
            self._make_search_results(),
            self._make_memory_results(),
        )
        assert isinstance(result, dict), "generate() should return a dict"

    def test_attention_summary_present(self):
        report = self.PerformanceReport()
        result = report.generate(
            self._make_attention_results(),
            self._make_search_results(),
            self._make_memory_results(),
        )
        assert "attention_summary" in result, "Report should have attention_summary"

    def test_search_summary_present(self):
        report = self.PerformanceReport()
        result = report.generate(
            self._make_attention_results(),
            self._make_search_results(),
            self._make_memory_results(),
        )
        assert "search_summary" in result, "Report should have search_summary"

    def test_overall_targets_met(self):
        report = self.PerformanceReport()
        result = report.generate(
            self._make_attention_results(),
            self._make_search_results(),
            self._make_memory_results(),
        )
        assert "overall_targets_met" in result, (
            "Report should have overall_targets_met field"
        )


class TestFunctionalReportFormats:
    """Verify report output formats."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        sys.path.insert(0, BENCH_DIR)
        sys.path.insert(0, REPO_DIR)
        try:
            from report_generator import PerformanceReport
            self.PerformanceReport = PerformanceReport
        except ImportError:
            try:
                from benchmarks.report_generator import PerformanceReport
                self.PerformanceReport = PerformanceReport
            except ImportError:
                pytest.skip("Cannot import PerformanceReport")

    def _generate_report(self):
        report = self.PerformanceReport()
        report.generate(
            [{"seq_length": 512, "standard_ms": 10.0, "flash_ms": 3.0, "speedup": 3.33, "output_matches": True}],
            [{"dataset_size": 1000, "linear_ms": 5.0, "hnsw_ms": 0.03, "speedup": 166.7, "recall_at_k": 0.98}],
            [{"standard_mb": 1024.0, "flash_mb": 256.0, "reduction_percent": 75.0}],
        )
        return report

    def test_to_json_valid(self):
        import json
        report = self._generate_report()
        output = report.to_json()
        parsed = json.loads(output)
        assert isinstance(parsed, dict), "to_json() should return valid JSON"

    def test_to_markdown_nonempty(self):
        report = self._generate_report()
        output = report.to_markdown()
        assert isinstance(output, str) and len(output) > 0, (
            "to_markdown() should return non-empty string"
        )
        assert "|" in output or "#" in output, (
            "Markdown report should contain table or headers"
        )


class TestFunctionalSearchBenchmarkInit:
    """Verify SearchBenchmark can be instantiated."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        sys.path.insert(0, BENCH_DIR)
        sys.path.insert(0, REPO_DIR)
        try:
            from search_benchmark import SearchBenchmark
            self.SearchBenchmark = SearchBenchmark
        except ImportError:
            try:
                from benchmarks.search_benchmark import SearchBenchmark
                self.SearchBenchmark = SearchBenchmark
            except ImportError:
                pytest.skip("Cannot import SearchBenchmark")

    def test_default_dimension(self):
        sb = self.SearchBenchmark()
        assert hasattr(sb, "dimension"), "SearchBenchmark should have dimension attr"
        assert sb.dimension == 128, f"Default dimension should be 128; got {sb.dimension}"

    def test_build_hnsw_index(self):
        import numpy as np
        sb = self.SearchBenchmark(dimension=32)
        data = np.random.rand(100, 32).astype(np.float32)
        index = sb.build_hnsw_index(data)
        assert index is not None, "build_hnsw_index should return an index object"

    def test_linear_search(self):
        import numpy as np
        sb = self.SearchBenchmark(dimension=32)
        dataset = np.random.rand(100, 32).astype(np.float32)
        query = np.random.rand(32).astype(np.float32)
        indices, time_ms = sb.linear_search(query, dataset, k=5)
        assert len(indices) == 5, f"Should return k=5 indices; got {len(indices)}"
        assert time_ms >= 0, "Time should be non-negative"
