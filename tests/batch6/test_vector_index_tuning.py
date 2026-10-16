"""
Test skill: vector-index-tuning
Verify that the Agent builds a vector index benchmarking and tuning
framework with HNSW parameter sweep, quantization strategies,
evaluation metrics, and Pareto frontier recommendation.
"""

import os
import re
import ast
import subprocess
import pytest


class TestVectorIndexTuning:
    REPO_DIR = "/workspace/faiss"

    # === File Path Checks ===

    def test_index_builder_exists(self):
        path = os.path.join(self.REPO_DIR, "benchmark/index_builder.py")
        assert os.path.exists(path), f"index_builder.py not found at {path}"

    def test_quantization_exists(self):
        path = os.path.join(self.REPO_DIR, "benchmark/quantization.py")
        assert os.path.exists(path), f"quantization.py not found at {path}"

    def test_evaluator_exists(self):
        path = os.path.join(self.REPO_DIR, "benchmark/evaluator.py")
        assert os.path.exists(path), f"evaluator.py not found at {path}"

    def test_parameter_sweep_exists(self):
        path = os.path.join(self.REPO_DIR, "benchmark/parameter_sweep.py")
        assert os.path.exists(path), f"parameter_sweep.py not found at {path}"

    def test_recommender_exists(self):
        path = os.path.join(self.REPO_DIR, "benchmark/recommender.py")
        assert os.path.exists(path), f"recommender.py not found at {path}"

    def test_benchmark_tests_exist(self):
        path = os.path.join(self.REPO_DIR, "tests/test_benchmark.py")
        assert os.path.exists(path), f"tests/test_benchmark.py not found"

    # === Semantic Checks ===

    def test_index_builder_supports_hnswlib(self):
        """Verify HNSWIndexBuilder builds hnswlib indexes"""
        path = os.path.join(self.REPO_DIR, "benchmark/index_builder.py")
        with open(path, "r") as f:
            content = f.read()

        assert "HNSWIndexBuilder" in content or "IndexBuilder" in content, (
            "Must define HNSWIndexBuilder class"
        )
        assert "hnswlib" in content or "hnsw" in content.lower(), (
            "Index builder should support hnswlib"
        )

    def test_index_builder_supports_faiss(self):
        """Verify index builder supports FAISS HNSW and IVF"""
        path = os.path.join(self.REPO_DIR, "benchmark/index_builder.py")
        with open(path, "r") as f:
            content = f.read()

        assert "faiss" in content, "Index builder should support FAISS"
        assert "IVF" in content or "ivf" in content, "Should support IVF index"

    def test_index_config_dataclass(self):
        """Verify IndexConfig dataclass is defined"""
        path = os.path.join(self.REPO_DIR, "benchmark/index_builder.py")
        with open(path, "r") as f:
            content = f.read()

        assert "IndexConfig" in content, "Must define IndexConfig"
        assert "ef_construction" in content or "efConstruction" in content, (
            "IndexConfig should have ef_construction"
        )

    def test_quantization_has_scalar_and_pq(self):
        """Verify quantization module has scalar INT8 and PQ"""
        path = os.path.join(self.REPO_DIR, "benchmark/quantization.py")
        with open(path, "r") as f:
            content = f.read()

        assert "QuantizationBenchmark" in content, "Must define QuantizationBenchmark"
        assert re.search(r"def\s+quantize_scalar_int8", content), (
            "Missing quantize_scalar_int8"
        )
        assert re.search(r"def\s+build_pq_index", content), "Missing build_pq_index"

    def test_quantization_has_memory_estimation(self):
        """Verify quantization has estimate_memory function"""
        path = os.path.join(self.REPO_DIR, "benchmark/quantization.py")
        with open(path, "r") as f:
            content = f.read()

        assert re.search(r"def\s+estimate_memory", content), "Missing estimate_memory"

    def test_evaluator_measures_recall_latency_throughput(self):
        """Verify evaluator measures recall@k, latency, and throughput"""
        path = os.path.join(self.REPO_DIR, "benchmark/evaluator.py")
        with open(path, "r") as f:
            content = f.read()

        assert "IndexEvaluator" in content, "Must define IndexEvaluator class"
        assert re.search(r"def\s+recall_at_k", content), "Missing recall_at_k"
        assert re.search(r"def\s+measure_latency", content), "Missing measure_latency"
        assert re.search(r"def\s+measure_throughput", content), "Missing measure_throughput"

    def test_evaluator_returns_percentiles(self):
        """Verify latency measurement includes p50, p95, p99"""
        path = os.path.join(self.REPO_DIR, "benchmark/evaluator.py")
        with open(path, "r") as f:
            content = f.read()

        assert "p50" in content or "p95" in content or "p99" in content, (
            "Latency should report p50/p95/p99 percentiles"
        )

    def test_parameter_sweep_covers_m_values(self):
        """Verify parameter sweep tests M ∈ {8,16,32,48,64}"""
        path = os.path.join(self.REPO_DIR, "benchmark/parameter_sweep.py")
        with open(path, "r") as f:
            content = f.read()

        assert "ParameterSweep" in content, "Must define ParameterSweep class"
        # Check M values
        m_values = ["8", "16", "32", "48", "64"]
        found = sum(1 for v in m_values if v in content)
        assert found >= 3, (
            f"Parameter sweep should test multiple M values, found {found} of {m_values}"
        )

    def test_recommender_has_pareto_frontier(self):
        """Verify recommender computes Pareto frontier"""
        path = os.path.join(self.REPO_DIR, "benchmark/recommender.py")
        with open(path, "r") as f:
            content = f.read()

        assert "ConfigRecommender" in content, "Must define ConfigRecommender"
        assert re.search(r"def\s+pareto_frontier", content), "Missing pareto_frontier"

    def test_recommender_has_profiles(self):
        """Verify recommender has predefined profiles"""
        path = os.path.join(self.REPO_DIR, "benchmark/recommender.py")
        with open(path, "r") as f:
            content = f.read()

        profiles = ["low_latency", "high_recall", "balanced", "memory_efficient"]
        found = [p for p in profiles if p in content]
        assert len(found) >= 3, (
            f"Recommender should have profiles. Found: {found}"
        )

    # === Functional Checks ===

    def test_all_python_files_parse(self):
        """Verify all benchmark Python files parse"""
        files = [
            "benchmark/index_builder.py", "benchmark/quantization.py",
            "benchmark/evaluator.py", "benchmark/parameter_sweep.py",
            "benchmark/recommender.py",
        ]
        for filename in files:
            path = os.path.join(self.REPO_DIR, filename)
            with open(path, "r") as f:
                source = f.read()
            try:
                ast.parse(source)
            except SyntaxError as e:
                pytest.fail(f"{filename} has syntax error: {e}")

    def test_evaluator_imports(self):
        """Verify evaluator can be imported"""
        result = subprocess.run(
            ["python", "-c",
             "import sys; sys.path.insert(0, '.'); "
             "from benchmark.evaluator import IndexEvaluator; print('OK')"],
            capture_output=True, text=True, timeout=30,
            cwd=self.REPO_DIR,
        )
        assert result.returncode == 0, (
            f"Failed to import IndexEvaluator:\n{result.stderr[:500]}"
        )

    def test_unit_tests_pass(self):
        """Verify benchmark unit tests pass"""
        result = subprocess.run(
            ["python", "-m", "pytest", "tests/test_benchmark.py",
             "-v", "--tb=short"],
            capture_output=True, text=True, timeout=120,
            cwd=self.REPO_DIR,
        )
        assert result.returncode == 0, (
            f"Unit tests failed:\n{result.stdout[-1000:]}\n{result.stderr[-500:]}"
        )
