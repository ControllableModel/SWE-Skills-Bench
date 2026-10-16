"""
Test skill: v3-performance-optimization
Verify that the Agent creates a benchmark suite and correctness tests
for Flash Attention performance optimization.
"""

import os
import re
import ast
import subprocess
import pytest


class TestV3PerformanceOptimization:
    REPO_DIR = "/workspace/flash-attention"

    # === File Path Checks ===

    def test_benchmark_files_exist(self):
        """Verify benchmark suite files exist"""
        found = False
        for root, dirs, files in os.walk(self.REPO_DIR):
            if ".git" in root or "node_modules" in root:
                continue
            for f in files:
                if ("benchmark" in f.lower() or "perf" in f.lower() or "test" in f.lower()) and (f.endswith(".py") or f.endswith(".cu") or f.endswith(".cuh")):
                    found = True
                    break
            if found:
                break
        assert found, "Benchmark suite files not found"

    # === Semantic Checks ===

    def test_flash_attention_referenced(self):
        """Verify flash attention is referenced"""
        content = self._collect_content()
        content_lower = content.lower()
        has_flash = "flash" in content_lower or "attention" in content_lower
        assert has_flash, "Flash attention not referenced"

    def test_benchmark_functions_defined(self):
        """Verify benchmark functions are defined"""
        content = self._collect_content()
        content_lower = content.lower()
        has_bench = (
            "benchmark" in content_lower
            or "perf_test" in content_lower
            or "time_" in content_lower
            or "measure" in content_lower
        )
        assert has_bench, "Benchmark functions not found"

    def test_correctness_tests_defined(self):
        """Verify correctness tests are implemented"""
        content = self._collect_content()
        content_lower = content.lower()
        has_correct = (
            "correct" in content_lower
            or "assert" in content_lower
            or "allclose" in content_lower
            or "reference" in content_lower
            or "expected" in content_lower
        )
        assert has_correct, "Correctness tests not found"

    def test_sequence_length_variation(self):
        """Verify tests cover different sequence lengths"""
        content = self._collect_content()
        content_lower = content.lower()
        has_seq = (
            "seq_len" in content_lower
            or "sequence_length" in content_lower
            or "seqlen" in content_lower
            or "128" in content
            or "512" in content
            or "1024" in content
            or "2048" in content
        )
        assert has_seq, "Sequence length variation not tested"

    # === Functional Checks ===

    def test_python_files_valid_syntax(self):
        """Verify Python files have valid AST"""
        py_files = self._find_py_files()
        for pf in py_files:
            with open(pf) as fh:
                source = fh.read()
            try:
                ast.parse(source)
            except SyntaxError as e:
                pytest.fail(f"Syntax error in {pf}: {e}")

    def test_torch_used(self):
        """Verify PyTorch is used for benchmarking"""
        content = self._collect_content()
        has_torch = "torch" in content or "import torch" in content
        assert has_torch, "PyTorch not used"

    def test_gpu_configuration(self):
        """Verify GPU/CUDA configuration is present"""
        content = self._collect_content()
        content_lower = content.lower()
        has_gpu = (
            "cuda" in content_lower
            or "gpu" in content_lower
            or "device" in content_lower
            or ".to(" in content
        )
        assert has_gpu, "GPU/CUDA configuration not found"

    def test_timing_measurement(self):
        """Verify timing/performance measurement is implemented"""
        content = self._collect_content()
        content_lower = content.lower()
        has_timing = (
            "time" in content_lower
            or "elapsed" in content_lower
            or "latency" in content_lower
            or "throughput" in content_lower
            or "flops" in content_lower
            or "tflops" in content_lower
        )
        assert has_timing, "Timing measurement not found"

    def test_memory_measurement(self):
        """Verify memory usage measurement"""
        content = self._collect_content()
        content_lower = content.lower()
        has_memory = (
            "memory" in content_lower
            or "mem_" in content_lower
            or "max_memory" in content_lower
            or "allocated" in content_lower
        )
        assert has_memory, "Memory measurement not found"

    def test_head_dim_variation(self):
        """Verify tests cover different head dimensions"""
        content = self._collect_content()
        content_lower = content.lower()
        has_head = (
            "head_dim" in content_lower
            or "headdim" in content_lower
            or "d_model" in content_lower
            or "num_heads" in content_lower
        )
        assert has_head, "Head dimension variation not tested"

    def _collect_content(self):
        all_content = ""
        for root, dirs, files in os.walk(self.REPO_DIR):
            if ".git" in root or "node_modules" in root:
                continue
            for f in files:
                if f.endswith(".py") or f.endswith(".cu") or f.endswith(".cuh"):
                    fpath = os.path.join(root, f)
                    try:
                        with open(fpath) as fh:
                            c = fh.read()
                        if any(kw in c.lower() for kw in ["flash", "attention", "benchmark", "test", "perf"]):
                            all_content += c + "\n"
                    except (UnicodeDecodeError, PermissionError):
                        continue
        return all_content

    def _find_py_files(self):
        result = []
        for root, dirs, files in os.walk(self.REPO_DIR):
            if ".git" in root or "node_modules" in root:
                continue
            for f in files:
                if f.endswith(".py") and ("benchmark" in f.lower() or "test" in f.lower() or "perf" in f.lower()):
                    result.append(os.path.join(root, f))
        return result
