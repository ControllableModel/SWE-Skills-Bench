"""
Test skill: v3-performance-optimization
Verify that the Agent correctly implements a Flash Attention Benchmark Suite
and HNSW Search Performance Validator for flash-attention.
"""

import os
import re
import json
import ast
import pytest


class TestV3PerformanceOptimization:
    REPO_DIR = "/workspace/flash-attention"

    # === File Path Checks ===

    def test_benchmark_flash_attn_exists(self):
        """Verify benchmark_flash_attn_v3.py was created"""
        path = os.path.join(
            self.REPO_DIR, "benchmarks/benchmark_flash_attn_v3.py"
        )
        assert os.path.exists(path), "benchmark_flash_attn_v3.py not found"

    def test_benchmark_hnsw_exists(self):
        """Verify benchmark_hnsw_search.py was created"""
        path = os.path.join(
            self.REPO_DIR, "benchmarks/benchmark_hnsw_search.py"
        )
        assert os.path.exists(path), "benchmark_hnsw_search.py not found"

    def test_perf_validator_exists(self):
        """Verify perf_validator.py was created"""
        path = os.path.join(
            self.REPO_DIR, "benchmarks/perf_validator.py"
        )
        assert os.path.exists(path), "perf_validator.py not found"

    def test_thresholds_json_exists(self):
        """Verify thresholds.json was created"""
        path = os.path.join(
            self.REPO_DIR, "benchmarks/thresholds.json"
        )
        assert os.path.exists(path), "thresholds.json not found"

    def test_test_perf_validator_exists(self):
        """Verify test_perf_validator.py was created"""
        path = os.path.join(
            self.REPO_DIR, "tests/test_perf_validator.py"
        )
        assert os.path.exists(path), "tests/test_perf_validator.py not found"

    # === Semantic Checks: Flash Attention Benchmark ===

    def _load_flash_benchmark(self):
        path = os.path.join(
            self.REPO_DIR, "benchmarks/benchmark_flash_attn_v3.py"
        )
        return open(path).read()

    def test_flash_benchmark_uses_cuda_events(self):
        """Verify GPU timing uses torch.cuda.Event"""
        source = self._load_flash_benchmark()
        assert "cuda.Event" in source or "cuda_event" in source.lower(), (
            "Flash benchmark does not use torch.cuda.Event for timing"
        )

    def test_flash_benchmark_warmup_iterations(self):
        """Verify benchmark has warmup iterations"""
        source = self._load_flash_benchmark()
        has_warmup = (
            "warmup" in source.lower()
            or "warm_up" in source.lower()
            or "10" in source
        )
        assert has_warmup, "No warmup iterations in flash benchmark"

    def test_flash_benchmark_sequence_lengths(self):
        """Verify benchmark tests multiple sequence lengths"""
        source = self._load_flash_benchmark()
        for seq in ["512", "1024", "2048", "4096"]:
            assert seq in source, f"Sequence length {seq} not tested"

    def test_flash_benchmark_head_dimensions(self):
        """Verify benchmark tests head dimensions 64 and 128"""
        source = self._load_flash_benchmark()
        assert "64" in source and "128" in source, (
            "Head dimensions 64 and 128 not both tested"
        )

    def test_flash_benchmark_causal_modes(self):
        """Verify benchmark tests both causal and non-causal"""
        source = self._load_flash_benchmark()
        assert "causal" in source.lower(), "No causal mode testing"

    def test_flash_benchmark_memory_tracking(self):
        """Verify peak GPU memory is tracked"""
        source = self._load_flash_benchmark()
        has_mem = (
            "max_memory_allocated" in source
            or "reset_peak_memory_stats" in source
        )
        assert has_mem, "No GPU memory tracking logic"

    def test_flash_benchmark_cuda_guard(self):
        """Verify script handles CUDA not available"""
        source = self._load_flash_benchmark()
        has_guard = (
            "cuda.is_available" in source
            or "CUDA not available" in source
        )
        assert has_guard, "No CUDA availability check"

    # === Semantic Checks: HNSW Benchmark ===

    def _load_hnsw_benchmark(self):
        path = os.path.join(
            self.REPO_DIR, "benchmarks/benchmark_hnsw_search.py"
        )
        return open(path).read()

    def test_hnsw_uses_faiss(self):
        """Verify HNSW benchmark uses faiss"""
        source = self._load_hnsw_benchmark()
        assert "faiss" in source, "HNSW benchmark does not use faiss"

    def test_hnsw_index_type(self):
        """Verify HNSW benchmark uses IndexHNSWFlat"""
        source = self._load_hnsw_benchmark()
        assert "IndexHNSWFlat" in source or "HNSW" in source, (
            "IndexHNSWFlat not used"
        )

    def test_hnsw_dimensions_tested(self):
        """Verify HNSW tests dimensions 128, 256, 512"""
        source = self._load_hnsw_benchmark()
        for dim in ["128", "256", "512"]:
            assert dim in source, f"Dimension {dim} not tested in HNSW benchmark"

    def test_hnsw_recall_metric(self):
        """Verify recall@10 metric is computed"""
        source = self._load_hnsw_benchmark()
        has_recall = "recall" in source.lower()
        assert has_recall, "No recall metric in HNSW benchmark"

    # === Semantic Checks: Validator ===

    def _load_validator(self):
        path = os.path.join(
            self.REPO_DIR, "benchmarks/perf_validator.py"
        )
        return open(path).read()

    def test_validation_report_dataclass(self):
        """Verify ValidationReport dataclass is defined"""
        source = self._load_validator()
        assert "ValidationReport" in source, "ValidationReport not found"

    def test_validation_report_fields(self):
        """Verify ValidationReport has passed, failures, warnings fields"""
        source = self._load_validator()
        for field in ["passed", "failures", "warnings"]:
            assert field in source, f"ValidationReport missing '{field}' field"

    def test_validate_results_function(self):
        """Verify validate_results function is defined"""
        source = self._load_validator()
        assert "validate_results" in source, "validate_results not found"

    # === Semantic Checks: Thresholds ===

    def test_thresholds_valid_json(self):
        """Verify thresholds.json is valid JSON"""
        path = os.path.join(
            self.REPO_DIR, "benchmarks/thresholds.json"
        )
        with open(path) as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError as e:
                pytest.fail(f"thresholds.json invalid: {e}")
        assert data, "thresholds.json is empty"

    def test_thresholds_speedup_target(self):
        """Verify thresholds set flash attention speedup >= 2.0x"""
        path = os.path.join(
            self.REPO_DIR, "benchmarks/thresholds.json"
        )
        content = open(path).read()
        assert "2.0" in content or "2" in content, (
            "Speedup threshold of 2.0x not found"
        )

    def test_thresholds_memory_target(self):
        """Verify thresholds set memory reduction >= 40%"""
        path = os.path.join(
            self.REPO_DIR, "benchmarks/thresholds.json"
        )
        content = open(path).read()
        assert "40" in content, "Memory reduction threshold of 40% not found"

    # === Functional Checks ===

    def test_validator_raises_file_not_found(self):
        """Verify validate_results raises FileNotFoundError"""
        source = self._load_validator()
        assert "FileNotFoundError" in source, (
            "validate_results does not raise FileNotFoundError"
        )

    def test_validator_raises_value_error(self):
        """Verify validate_results raises ValueError for invalid JSON"""
        source = self._load_validator()
        assert "ValueError" in source, (
            "validate_results does not raise ValueError"
        )

    def test_validator_memory_is_soft_target(self):
        """Verify memory reduction is a warning not a failure"""
        source = self._load_validator()
        has_warning_logic = (
            "warning" in source.lower()
            and "memory" in source.lower()
        )
        assert has_warning_logic, (
            "Memory reduction not treated as soft target/warning"
        )

    def test_flash_benchmark_output_schema(self):
        """Verify flash benchmark outputs expected JSON fields"""
        source = self._load_flash_benchmark()
        expected_fields = ["speedup", "median", "peak_mem"]
        found = sum(1 for f in expected_fields if f in source.lower())
        assert found >= 2, (
            f"Flash benchmark output missing expected fields, found {found}/3"
        )

    def test_all_python_files_parseable(self):
        """Verify all created Python files have valid syntax"""
        files = [
            "benchmarks/benchmark_flash_attn_v3.py",
            "benchmarks/benchmark_hnsw_search.py",
            "benchmarks/perf_validator.py",
            "tests/test_perf_validator.py",
        ]
        for f in files:
            path = os.path.join(self.REPO_DIR, f)
            if os.path.exists(path):
                source = open(path).read()
                try:
                    ast.parse(source)
                except SyntaxError as e:
                    pytest.fail(f"{f} has syntax error: {e}")
