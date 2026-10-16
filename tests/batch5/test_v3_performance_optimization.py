"""
Test skill: v3-performance-optimization
Verify that the Agent benchmarks and optimizes Flash Attention forward pass
for long sequences with correct CSV output and kernel modifications.
"""

import os
import re
import ast
import csv
import pytest


class TestV3PerformanceOptimization:
    REPO_DIR = "/workspace/flash-attention"

    BENCHMARK = "benchmarks/benchmark_flash_attn_long_seq.py"
    INTERFACE = "hopper/flash_attn_interface.py"
    KERNEL = "hopper/flash_fwd_kernel.h"
    BASELINE_CSV = "benchmarks/results/long_seq_baseline.csv"
    OPTIMIZED_CSV = "benchmarks/results/long_seq_optimized.csv"

    def _read_file(self, rel_path):
        filepath = os.path.join(self.REPO_DIR, rel_path)
        with open(filepath) as f:
            return f.read()

    # === File Path Checks ===

    def test_benchmark_script_exists(self):
        filepath = os.path.join(self.REPO_DIR, self.BENCHMARK)
        assert os.path.exists(filepath), "benchmark script not found"

    def test_interface_exists(self):
        filepath = os.path.join(self.REPO_DIR, self.INTERFACE)
        assert os.path.exists(filepath), "flash_attn_interface.py not found"

    def test_kernel_exists(self):
        filepath = os.path.join(self.REPO_DIR, self.KERNEL)
        assert os.path.exists(filepath), "flash_fwd_kernel.h not found"

    def test_baseline_csv_exists(self):
        filepath = os.path.join(self.REPO_DIR, self.BASELINE_CSV)
        assert os.path.exists(filepath), "long_seq_baseline.csv not found"

    def test_optimized_csv_exists(self):
        filepath = os.path.join(self.REPO_DIR, self.OPTIMIZED_CSV)
        assert os.path.exists(filepath), "long_seq_optimized.csv not found"

    # === Semantic Checks ===

    def test_benchmark_measures_configs(self):
        """Verify benchmark tests seq_len 4096, 8192, 16384"""
        content = self._read_file(self.BENCHMARK)
        for seq_len in ["4096", "8192", "16384"]:
            assert seq_len in content, f"Benchmark missing seq_len={seq_len}"

    def test_benchmark_measures_batch_sizes(self):
        """Verify benchmark tests batch_size 1, 4, 8"""
        content = self._read_file(self.BENCHMARK)
        for bs in ["1", "4", "8"]:
            assert bs in content, f"Benchmark missing batch_size={bs}"

    def test_benchmark_measures_causal(self):
        """Verify benchmark tests both causal and non-causal"""
        content = self._read_file(self.BENCHMARK)
        assert "causal" in content.lower(), "Benchmark missing causal testing"

    def test_benchmark_warmup_and_median(self):
        """Verify benchmark uses warmup runs and median timing"""
        content = self._read_file(self.BENCHMARK)
        has_warmup = bool(re.search(r'(warmup|warm_up|warm)', content))
        has_median = bool(re.search(r'(median|np\.median)', content))
        assert has_warmup, "Benchmark missing warmup runs"
        assert has_median, "Benchmark missing median timing"

    def test_benchmark_correctness_check(self):
        """Verify benchmark validates against reference attention"""
        content = self._read_file(self.BENCHMARK)
        has_ref = bool(re.search(
            r'(scaled_dot_product_attention|atol|allclose|reference)', content
        ))
        assert has_ref, "Benchmark missing correctness validation"

    def test_benchmark_csv_output(self):
        """Verify benchmark outputs CSV with required columns"""
        content = self._read_file(self.BENCHMARK)
        for col in ["seq_len", "batch_size", "time_ms", "peak_memory"]:
            assert col in content, f"Benchmark missing CSV column: {col}"

    def test_interface_tile_size_logic(self):
        """Verify interface has tile-size selection for long sequences"""
        content = self._read_file(self.INTERFACE)
        has_tile = bool(re.search(
            r'(tile|block_size|BLOCK|seqlen.*4096|long_seq)', content, re.I
        ))
        assert has_tile, "Interface missing tile-size selection for long sequences"

    def test_csv_files_have_headers(self):
        """Verify CSV files have correct column headers"""
        for path in [self.BASELINE_CSV, self.OPTIMIZED_CSV]:
            filepath = os.path.join(self.REPO_DIR, path)
            with open(filepath) as f:
                reader = csv.reader(f)
                header = next(reader)
                header_str = ",".join(header).lower()
                assert "seq_len" in header_str, f"{path} CSV missing seq_len column"
                assert "time" in header_str, f"{path} CSV missing time column"

    # === Functional Checks ===

    def test_benchmark_valid_python(self):
        """Verify benchmark script has valid Python syntax"""
        content = self._read_file(self.BENCHMARK)
        try:
            ast.parse(content)
        except SyntaxError as e:
            pytest.fail(f"Benchmark syntax error: {e}")

    def test_csv_has_data_rows(self):
        """Verify CSV files have data (not just headers)"""
        for path in [self.BASELINE_CSV, self.OPTIMIZED_CSV]:
            filepath = os.path.join(self.REPO_DIR, path)
            with open(filepath) as f:
                lines = f.readlines()
                assert len(lines) >= 2, \
                    f"{path} CSV has no data rows (only {len(lines)} lines)"
