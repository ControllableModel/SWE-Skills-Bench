"""
Test skill: vector-index-tuning
Verify that the Agent creates HNSW benchmark, adaptive tuner,
quantization comparison, and Pareto frontier analysis for FAISS.
"""

import os
import subprocess
import ast
import re
import pytest


class TestVectorIndexTuning:
    REPO_DIR = "/workspace/faiss"

    # === File Path Checks ===

    def test_benchmark_file_exists(self):
        """Verify HNSW benchmark file exists"""
        found = False
        for root, dirs, files in os.walk(self.REPO_DIR):
            if ".git" in root:
                continue
            for f in files:
                if f.endswith(".py") and ("benchmark" in f.lower() or "hnsw" in f.lower()):
                    found = True
                    break
            if found:
                break
        assert found, "HNSW benchmark file not found"

    # === Semantic Checks ===

    def test_hnsw_benchmark_defined(self):
        """Verify HNSW benchmark logic is implemented"""
        content = self._find_content(["benchmark", "hnsw"])
        content_lower = content.lower()
        has_hnsw = "hnsw" in content_lower or "IndexHNSW" in content
        assert has_hnsw, "HNSW benchmark not found"

    def test_adaptive_tuner_defined(self):
        """Verify adaptive tuner is implemented"""
        content = self._find_content(["tuner", "adaptive", "benchmark"])
        content_lower = content.lower()
        has_tuner = (
            "tuner" in content_lower
            or "adaptive" in content_lower
            or "auto_tune" in content_lower
            or "optimize" in content_lower
        )
        assert has_tuner, "Adaptive tuner not found"

    def test_quantization_comparison_defined(self):
        """Verify quantization comparison is implemented"""
        content = self._find_content(["quantization", "comparison", "benchmark"])
        content_lower = content.lower()
        has_quant = (
            "quantiz" in content_lower
            or "pq" in content_lower
            or "opq" in content_lower
            or "scalar_quantizer" in content_lower
        )
        assert has_quant, "Quantization comparison not found"

    def test_pareto_frontier_defined(self):
        """Verify Pareto frontier analysis is implemented"""
        content = self._find_content(["pareto", "frontier", "benchmark", "tuner"])
        content_lower = content.lower()
        has_pareto = "pareto" in content_lower or "frontier" in content_lower or "tradeoff" in content_lower
        assert has_pareto, "Pareto frontier analysis not found"

    def test_benchmark_measures_recall_and_latency(self):
        """Verify benchmark measures both recall and latency"""
        content = self._find_content(["benchmark", "hnsw"])
        content_lower = content.lower()
        has_recall = "recall" in content_lower
        has_latency = "latency" in content_lower or "time" in content_lower or "qps" in content_lower
        assert has_recall and has_latency, (
            f"Benchmark should measure recall and latency. recall={has_recall}, latency={has_latency}"
        )

    # === Functional Checks ===

    def test_benchmark_files_parse(self):
        """Verify all benchmark Python files have valid syntax"""
        for root, dirs, files in os.walk(self.REPO_DIR):
            if ".git" in root:
                continue
            for f in files:
                if f.endswith(".py") and ("benchmark" in f.lower() or "tuner" in f.lower() or "pareto" in f.lower()):
                    fpath = os.path.join(root, f)
                    with open(fpath) as fh:
                        source = fh.read()
                    try:
                        ast.parse(source)
                    except SyntaxError as e:
                        pytest.fail(f"Syntax error in {fpath}: {e}")

    def test_uses_faiss_library(self):
        """Verify benchmark imports faiss library"""
        content = self._find_content(["benchmark", "hnsw", "tuner"])
        assert "faiss" in content or "import faiss" in content, (
            "Benchmark files do not import faiss"
        )

    def test_benchmark_module_importable(self):
        """Verify benchmark module syntax is valid"""
        bench_file = None
        for root, dirs, files in os.walk(self.REPO_DIR):
            if ".git" in root:
                continue
            for f in files:
                if f.endswith(".py") and "benchmark" in f.lower():
                    bench_file = os.path.join(root, f)
                    break
            if bench_file:
                break
        if bench_file is None:
            pytest.skip("Benchmark file not found")
        result = subprocess.run(
            ["python", "-c", f"import ast; ast.parse(open('{bench_file}').read()); print('OK')"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, f"Benchmark parse failed: {result.stderr}"

    def test_tuner_has_parameter_search(self):
        """Verify tuner implements parameter search (grid/random/bayesian)"""
        content = self._find_content(["tuner", "adaptive"])
        content_lower = content.lower()
        has_search = (
            "search" in content_lower
            or "grid" in content_lower
            or "parameter" in content_lower
            or "config" in content_lower
        )
        assert has_search, "Tuner missing parameter search logic"

    def _find_content(self, keywords):
        """Helper to find content in files matching keywords"""
        all_content = ""
        for root, dirs, files in os.walk(self.REPO_DIR):
            if ".git" in root:
                continue
            for f in files:
                if f.endswith(".py"):
                    fname_lower = f.lower()
                    if any(kw in fname_lower for kw in keywords):
                        fpath = os.path.join(root, f)
                        try:
                            with open(fpath) as fh:
                                all_content += fh.read() + "\n"
                        except (UnicodeDecodeError, PermissionError):
                            continue
        return all_content
