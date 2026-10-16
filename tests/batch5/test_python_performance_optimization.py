"""
Test skill: python-performance-optimization
Verify that the Agent optimizes hot paths in py-spy's profile processing
scripts with benchmarking, deduplication, and streaming I/O.
"""

import os
import re
import ast
import pytest


class TestPythonPerformanceOptimization:
    REPO_DIR = "/workspace/py-spy"

    BENCHMARK = "scripts/benchmark_processing.py"
    PROCESS_PROFILE = "scripts/process_profile.py"
    FLAMEGRAPH = "scripts/flamegraph.py"
    TESTS = "scripts/tests/test_process_profile.py"

    def _read_file(self, rel_path):
        filepath = os.path.join(self.REPO_DIR, rel_path)
        with open(filepath) as f:
            return f.read()

    # === File Path Checks ===

    def test_benchmark_script_exists(self):
        filepath = os.path.join(self.REPO_DIR, self.BENCHMARK)
        assert os.path.exists(filepath), f"benchmark_processing.py not found"

    def test_process_profile_exists(self):
        filepath = os.path.join(self.REPO_DIR, self.PROCESS_PROFILE)
        assert os.path.exists(filepath), f"process_profile.py not found"

    def test_flamegraph_exists(self):
        filepath = os.path.join(self.REPO_DIR, self.FLAMEGRAPH)
        assert os.path.exists(filepath), f"flamegraph.py not found"

    def test_tests_file_exists(self):
        filepath = os.path.join(self.REPO_DIR, self.TESTS)
        assert os.path.exists(filepath), f"test_process_profile.py not found"

    # === Semantic Checks ===

    def test_benchmark_generates_synthetic_data(self):
        """Verify benchmark generates configurable synthetic profile data"""
        content = self._read_file(self.BENCHMARK)
        has_samples = bool(re.search(r'(100[_,]?000|samples|sample_count)', content))
        assert has_samples, "Benchmark missing sample count configuration"

    def test_benchmark_reports_json(self):
        """Verify benchmark outputs JSON with time, memory, throughput"""
        content = self._read_file(self.BENCHMARK)
        assert "json" in content.lower(), "Benchmark missing JSON output"
        for field in ["time_seconds", "peak_memory", "throughput"]:
            assert field in content, f"Benchmark missing report field: {field}"

    def test_benchmark_measures_memory(self):
        """Verify benchmark measures peak memory usage"""
        content = self._read_file(self.BENCHMARK)
        has_mem = bool(re.search(r'(tracemalloc|resource|memory_profiler|psutil)', content))
        assert has_mem, "Benchmark missing memory measurement"

    def test_process_profile_integer_dedup(self):
        """Verify deduplication uses integer IDs instead of strings"""
        content = self._read_file(self.PROCESS_PROFILE)
        has_dedup = bool(re.search(
            r'(intern|id_map|frame_id|string_table|lookup)', content
        ))
        assert has_dedup, "process_profile missing integer-based deduplication"

    def test_process_profile_counter_aggregation(self):
        """Verify aggregation uses Counter or similar O(1) approach"""
        content = self._read_file(self.PROCESS_PROFILE)
        has_counter = bool(re.search(
            r'(Counter|defaultdict|counter)', content
        ))
        assert has_counter, "process_profile missing Counter-based aggregation"

    def test_flamegraph_join_instead_of_concat(self):
        """Verify flamegraph uses str.join instead of += concatenation"""
        content = self._read_file(self.FLAMEGRAPH)
        assert ".join(" in content, "flamegraph missing str.join optimization"

    def test_flamegraph_streaming_io(self):
        """Verify flamegraph uses buffered/streaming I/O"""
        content = self._read_file(self.FLAMEGRAPH)
        has_streaming = bool(re.search(
            r'(BufferedWriter|buffered|chunk|io\.open|write_lines)', content
        ))
        assert has_streaming, "flamegraph missing streaming I/O"

    def test_process_profile_buffered_read(self):
        """Verify profile reading uses buffered chunks"""
        content = self._read_file(self.PROCESS_PROFILE)
        has_buffered = bool(re.search(
            r'(chunk|buffer|readline|iter|mmap)', content
        ))
        assert has_buffered, "process_profile missing buffered read"

    # === Functional Checks ===

    def test_all_files_valid_python(self):
        """Verify all Python files have valid syntax"""
        for path in [self.BENCHMARK, self.PROCESS_PROFILE,
                     self.FLAMEGRAPH, self.TESTS]:
            filepath = os.path.join(self.REPO_DIR, path)
            with open(filepath) as f:
                try:
                    ast.parse(f.read())
                except SyntaxError as e:
                    pytest.fail(f"{path} syntax error: {e}")

    def test_tests_have_correctness_checks(self):
        """Verify test file has correctness and performance tests"""
        content = self._read_file(self.TESTS)
        tree = ast.parse(content)
        test_funcs = [
            n.name for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")
        ]
        assert len(test_funcs) >= 3, \
            f"Expected >=3 tests, found {len(test_funcs)}"

    def test_benchmark_has_argparse(self):
        """Verify benchmark script accepts --samples argument"""
        content = self._read_file(self.BENCHMARK)
        has_args = bool(re.search(r'(argparse|--samples|sys\.argv)', content))
        assert has_args, "Benchmark missing --samples argument parsing"
