"""
Tests for skill: python-performance-optimization
Repo: benfred/py-spy
Image: zhangyiiiiii/swe-skills-bench-rust
Task: Build a Python performance profiling and optimization toolkit with
      CPU profiler, memory tracker, benchmark suite, and optimization helpers.
"""

import ast
import os
import sys

import pytest

REPO_DIR = "/workspace/py-spy"
TOOLKIT_DIR = os.path.join(REPO_DIR, "examples", "profiling_toolkit")

INIT_FILE = os.path.join(TOOLKIT_DIR, "__init__.py")
PROFILER_FILE = os.path.join(TOOLKIT_DIR, "profiler.py")
MEMORY_FILE = os.path.join(TOOLKIT_DIR, "memory_tracker.py")
BENCHMARK_FILE = os.path.join(TOOLKIT_DIR, "benchmark.py")
OPTIMIZER_FILE = os.path.join(TOOLKIT_DIR, "optimizer.py")


# ---------------------------------------------------------------------------
# Layer 1 — file_path_check
# ---------------------------------------------------------------------------

class TestFilePathCheck:
    """Verify all required profiling toolkit files exist."""

    def test_init_exists(self):
        assert os.path.isfile(INIT_FILE), f"Missing {INIT_FILE}"

    def test_profiler_exists(self):
        assert os.path.isfile(PROFILER_FILE), f"Missing {PROFILER_FILE}"

    def test_memory_tracker_exists(self):
        assert os.path.isfile(MEMORY_FILE), f"Missing {MEMORY_FILE}"

    def test_benchmark_exists(self):
        assert os.path.isfile(BENCHMARK_FILE), f"Missing {BENCHMARK_FILE}"

    def test_optimizer_exists(self):
        assert os.path.isfile(OPTIMIZER_FILE), f"Missing {OPTIMIZER_FILE}"


# ---------------------------------------------------------------------------
# Layer 2 — semantic_check
# ---------------------------------------------------------------------------

class TestSemanticProfiler:
    """Verify CPU profiler module structure."""

    @pytest.fixture(autouse=True)
    def _load(self):
        with open(PROFILER_FILE, "r", encoding="utf-8") as f:
            self.src = f.read()
        self.tree = ast.parse(self.src)

    def test_profile_decorator(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "profile" in funcs, f"Expected profile decorator; found {funcs}"

    def test_profile_context_manager(self):
        classes = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.ClassDef)]
        assert "ProfileContext" in classes, f"Expected ProfileContext; found {classes}"

    def test_profile_to_file(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "profile_to_file" in funcs, f"Expected profile_to_file; found {funcs}"

    def test_compare_profiles(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "compare_profiles" in funcs, f"Expected compare_profiles; found {funcs}"

    def test_cprofile_usage(self):
        assert "cProfile" in self.src or "cprofile" in self.src.lower(), (
            "Profiler should use cProfile"
        )

    def test_perf_counter(self):
        assert "perf_counter" in self.src, (
            "Should use perf_counter for timing"
        )


class TestSemanticMemoryTracker:
    """Verify memory tracker module structure."""

    @pytest.fixture(autouse=True)
    def _load(self):
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            self.src = f.read()
        self.tree = ast.parse(self.src)

    def test_track_memory_decorator(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "track_memory" in funcs, f"Expected track_memory; found {funcs}"

    def test_memory_snapshot_class(self):
        classes = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.ClassDef)]
        assert "MemorySnapshot" in classes, f"Expected MemorySnapshot; found {classes}"

    def test_track_allocations(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "track_allocations" in funcs, f"Expected track_allocations; found {funcs}"

    def test_tracemalloc_usage(self):
        assert "tracemalloc" in self.src, "Should use tracemalloc for allocation tracking"

    def test_psutil_or_fallback(self):
        assert "psutil" in self.src or "tracemalloc" in self.src, (
            "Should use psutil (with tracemalloc fallback) for RSS"
        )


class TestSemanticBenchmark:
    """Verify benchmark suite module structure."""

    @pytest.fixture(autouse=True)
    def _load(self):
        with open(BENCHMARK_FILE, "r", encoding="utf-8") as f:
            self.src = f.read()
        self.tree = ast.parse(self.src)

    def test_benchmark_class(self):
        classes = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.ClassDef)]
        assert "Benchmark" in classes, f"Expected Benchmark; found {classes}"

    def test_add_method(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "add" in funcs, f"Expected add(); found {funcs}"

    def test_run_method(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "run" in funcs, f"Expected run(); found {funcs}"

    def test_benchmark_result(self):
        assert "BenchmarkResult" in self.src, "Should define BenchmarkResult"

    def test_comparison_table(self):
        assert "comparison_table" in self.src, (
            "BenchmarkResult should have comparison_table method"
        )

    def test_warmup(self):
        assert "warmup" in self.src, "Benchmark should support warmup iterations"

    def test_outlier_removal(self):
        assert "std" in self.src or "standard_deviation" in self.src or "outlier" in self.src.lower(), (
            "Benchmark should remove statistical outliers"
        )


class TestSemanticOptimizer:
    """Verify optimization utilities module structure."""

    @pytest.fixture(autouse=True)
    def _load(self):
        with open(OPTIMIZER_FILE, "r", encoding="utf-8") as f:
            self.src = f.read()
        self.tree = ast.parse(self.src)

    def test_memoize_decorator(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "memoize" in funcs, f"Expected memoize; found {funcs}"

    def test_lazy_property(self):
        assert "lazy_property" in self.src, "Should define lazy_property"

    def test_batch_processor(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "batch_processor" in funcs, f"Expected batch_processor; found {funcs}"

    def test_chunk_iterator(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "chunk_iterator" in funcs, f"Expected chunk_iterator; found {funcs}"

    def test_timed_decorator(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "timed" in funcs, f"Expected timed; found {funcs}"

    def test_lru_cache(self):
        assert "lru_cache" in self.src, "memoize should wrap functools.lru_cache"


# ---------------------------------------------------------------------------
# Layer 3 — functional_check
# ---------------------------------------------------------------------------

class TestFunctionalMemoize:
    """Run memoize and verify caching behavior."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        sys.path.insert(0, TOOLKIT_DIR)
        sys.path.insert(0, REPO_DIR)
        try:
            from optimizer import memoize
            self.memoize = memoize
        except ImportError:
            try:
                from profiling_toolkit.optimizer import memoize
                self.memoize = memoize
            except ImportError:
                pytest.skip("Cannot import memoize")

    def test_caches_results(self):
        call_count = 0

        @self.memoize(maxsize=128)
        def expensive(n):
            nonlocal call_count
            call_count += 1
            return n * 2

        expensive(5)
        expensive(5)
        assert call_count == 1, "memoize should cache repeated calls"

    def test_fibonacci_performance(self):
        @self.memoize(maxsize=128)
        def fib(n):
            if n < 2:
                return n
            return fib(n - 1) + fib(n - 2)

        result = fib(30)
        assert result == 832040, f"fib(30) should be 832040; got {result}"


class TestFunctionalBatchProcessor:
    """Run batch_processor and chunk_iterator."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        sys.path.insert(0, TOOLKIT_DIR)
        sys.path.insert(0, REPO_DIR)
        try:
            from optimizer import batch_processor, chunk_iterator
            self.batch_processor = batch_processor
            self.chunk_iterator = chunk_iterator
        except ImportError:
            try:
                from profiling_toolkit.optimizer import batch_processor, chunk_iterator
                self.batch_processor = batch_processor
                self.chunk_iterator = chunk_iterator
            except ImportError:
                pytest.skip("Cannot import batch_processor / chunk_iterator")

    def test_batch_processor_basic(self):
        results = self.batch_processor(
            items=list(range(10)),
            batch_size=3,
            process_fn=lambda batch: [x * 2 for x in batch],
        )
        assert results == [0, 2, 4, 6, 8, 10, 12, 14, 16, 18], (
            f"Expected doubled values; got {results}"
        )

    def test_chunk_iterator(self):
        chunks = list(self.chunk_iterator(range(10), 3))
        assert len(chunks) == 4, f"Expected 4 chunks; got {len(chunks)}"
        assert list(chunks[0]) == [0, 1, 2]
        assert list(chunks[-1]) == [9]


class TestFunctionalBenchmarkSuite:
    """Run Benchmark suite on sample functions."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        sys.path.insert(0, TOOLKIT_DIR)
        sys.path.insert(0, REPO_DIR)
        try:
            from benchmark import Benchmark
            self.Benchmark = Benchmark
        except ImportError:
            try:
                from profiling_toolkit.benchmark import Benchmark
                self.Benchmark = Benchmark
            except ImportError:
                pytest.skip("Cannot import Benchmark")

    def test_basic_benchmark(self):
        bm = self.Benchmark(name="test")
        bm.add("sum_range", lambda: sum(range(100)))
        bm.add("list_comp", lambda: [i for i in range(100)])
        result = bm.run(iterations=100, warmup=10)
        assert hasattr(result, "results"), "BenchmarkResult should have results"
        assert hasattr(result, "fastest"), "BenchmarkResult should have fastest"
        assert result.fastest in ("sum_range", "list_comp")

    def test_comparison_table(self):
        bm = self.Benchmark(name="test")
        bm.add("sum_range", lambda: sum(range(100)))
        bm.add("list_comp", lambda: [i for i in range(100)])
        result = bm.run(iterations=50, warmup=5)
        table = result.comparison_table()
        assert isinstance(table, str), "comparison_table should return a string"
        assert "sum_range" in table and "list_comp" in table


class TestFunctionalLazyProperty:
    """Run lazy_property and verify single-computation behavior."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        sys.path.insert(0, TOOLKIT_DIR)
        sys.path.insert(0, REPO_DIR)
        try:
            from optimizer import lazy_property
            self.lazy_property = lazy_property
        except ImportError:
            try:
                from profiling_toolkit.optimizer import lazy_property
                self.lazy_property = lazy_property
            except ImportError:
                pytest.skip("Cannot import lazy_property")

    def test_computed_once(self):
        call_count = 0
        lazy_prop = self.lazy_property

        class Foo:
            @lazy_prop
            def value(self):
                nonlocal call_count
                call_count += 1
                return 42

        foo = Foo()
        assert foo.value == 42
        assert foo.value == 42
        assert call_count == 1, "lazy_property should compute only once"
