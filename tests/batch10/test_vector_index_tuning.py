"""
Test skill: vector-index-tuning
Verify that the Agent correctly implements HNSW benchmarking, quantization,
memory estimation, and parameter recommendation for FAISS.
"""

import os
import re
import ast
import subprocess
import pytest


class TestVectorIndexTuning:
    REPO_DIR = "/workspace/faiss"

    # === File Path Checks ===

    def test_hnsw_benchmark_exists(self):
        """Verify faiss/python/hnsw_benchmark.py was created"""
        path = os.path.join(self.REPO_DIR, "faiss/python/hnsw_benchmark.py")
        assert os.path.exists(path), f"hnsw_benchmark.py not found at {path}"

    def test_quantization_exists(self):
        """Verify faiss/python/quantization.py was created"""
        path = os.path.join(self.REPO_DIR, "faiss/python/quantization.py")
        assert os.path.exists(path), f"quantization.py not found at {path}"

    def test_memory_estimator_exists(self):
        """Verify faiss/python/memory_estimator.py was created"""
        path = os.path.join(self.REPO_DIR, "faiss/python/memory_estimator.py")
        assert os.path.exists(path), f"memory_estimator.py not found at {path}"

    def test_param_recommender_exists(self):
        """Verify faiss/python/param_recommender.py was created"""
        path = os.path.join(self.REPO_DIR, "faiss/python/param_recommender.py")
        assert os.path.exists(path), f"param_recommender.py not found at {path}"

    def test_test_file_exists(self):
        """Verify test file was created"""
        path = os.path.join(
            self.REPO_DIR, "faiss/python/tests/test_vector_index_tuning.py"
        )
        assert os.path.exists(path), f"test_vector_index_tuning.py not found at {path}"

    # === Semantic Checks: HNSW Benchmark ===

    def test_hnsw_benchmark_class_defined(self):
        """Verify HNSWBenchmark class is defined"""
        path = os.path.join(self.REPO_DIR, "faiss/python/hnsw_benchmark.py")
        with open(path) as f:
            content = f.read()
        assert "class HNSWBenchmark" in content, (
            "HNSWBenchmark class should be defined"
        )

    def test_hnsw_benchmark_has_run_method(self):
        """Verify HNSWBenchmark has run method"""
        path = os.path.join(self.REPO_DIR, "faiss/python/hnsw_benchmark.py")
        with open(path) as f:
            content = f.read()
        assert "def run(" in content, "HNSWBenchmark should have run method"

    def test_hnsw_has_pareto_optimal(self):
        """Verify find_pareto_optimal method"""
        path = os.path.join(self.REPO_DIR, "faiss/python/hnsw_benchmark.py")
        with open(path) as f:
            content = f.read()
        assert "pareto" in content.lower(), (
            "Should have find_pareto_optimal method"
        )

    def test_hnsw_measures_recall(self):
        """Verify recall@k is computed"""
        path = os.path.join(self.REPO_DIR, "faiss/python/hnsw_benchmark.py")
        with open(path) as f:
            content = f.read()
        assert "recall" in content.lower(), "Should compute recall@k metric"

    # === Semantic Checks: Quantization ===

    def test_scalar_quantizer_defined(self):
        """Verify ScalarQuantizerINT8 class is defined"""
        path = os.path.join(self.REPO_DIR, "faiss/python/quantization.py")
        with open(path) as f:
            content = f.read()
        assert "ScalarQuantizerINT8" in content, (
            "ScalarQuantizerINT8 class should be defined"
        )

    def test_product_quantizer_defined(self):
        """Verify ProductQuantizer class is defined"""
        path = os.path.join(self.REPO_DIR, "faiss/python/quantization.py")
        with open(path) as f:
            content = f.read()
        assert "class ProductQuantizer" in content, (
            "ProductQuantizer class should be defined"
        )

    def test_binary_quantizer_defined(self):
        """Verify BinaryQuantizer class is defined"""
        path = os.path.join(self.REPO_DIR, "faiss/python/quantization.py")
        with open(path) as f:
            content = f.read()
        assert "BinaryQuantizer" in content, (
            "BinaryQuantizer class should be defined"
        )

    def test_scalar_quantizer_has_fit_quantize_dequantize(self):
        """Verify ScalarQuantizerINT8 has fit, quantize, dequantize methods"""
        path = os.path.join(self.REPO_DIR, "faiss/python/quantization.py")
        with open(path) as f:
            content = f.read()
        for method in ["def fit(", "def quantize(", "def dequantize("]:
            assert method in content, f"ScalarQuantizerINT8 should have {method}"

    def test_product_quantizer_has_encode_decode(self):
        """Verify ProductQuantizer has encode and decode methods"""
        path = os.path.join(self.REPO_DIR, "faiss/python/quantization.py")
        with open(path) as f:
            content = f.read()
        assert "def encode(" in content, "ProductQuantizer should have encode method"
        assert "def decode(" in content, "ProductQuantizer should have decode method"

    def test_product_quantizer_validates_dimensions(self):
        """Verify ProductQuantizer raises ValueError for indivisible dims"""
        path = os.path.join(self.REPO_DIR, "faiss/python/quantization.py")
        with open(path) as f:
            content = f.read()
        assert "ValueError" in content, (
            "Should raise ValueError for indivisible dimension/n_subvectors"
        )

    def test_binary_quantizer_has_hamming_distance(self):
        """Verify BinaryQuantizer has hamming_distance method"""
        path = os.path.join(self.REPO_DIR, "faiss/python/quantization.py")
        with open(path) as f:
            content = f.read()
        assert "hamming_distance" in content, (
            "BinaryQuantizer should have hamming_distance method"
        )

    # === Semantic Checks: Memory Estimator ===

    def test_estimate_memory_function(self):
        """Verify estimate_memory function is defined"""
        path = os.path.join(self.REPO_DIR, "faiss/python/memory_estimator.py")
        with open(path) as f:
            content = f.read()
        assert "def estimate_memory(" in content, (
            "estimate_memory function should be defined"
        )

    def test_memory_estimator_supports_quantization_types(self):
        """Verify supported quantization types: fp32, fp16, int8, pq, binary"""
        path = os.path.join(self.REPO_DIR, "faiss/python/memory_estimator.py")
        with open(path) as f:
            content = f.read()
        for qtype in ["fp32", "fp16", "int8", "pq", "binary"]:
            assert qtype in content, (
                f"Memory estimator should support '{qtype}' quantization"
            )

    def test_memory_estimator_supports_index_types(self):
        """Verify supported index types: flat, hnsw, ivf"""
        path = os.path.join(self.REPO_DIR, "faiss/python/memory_estimator.py")
        with open(path) as f:
            content = f.read()
        for itype in ["flat", "hnsw", "ivf"]:
            assert itype in content, (
                f"Memory estimator should support '{itype}' index type"
            )

    # === Semantic Checks: Param Recommender ===

    def test_recommend_hnsw_params_function(self):
        """Verify recommend_hnsw_params function is defined"""
        path = os.path.join(self.REPO_DIR, "faiss/python/param_recommender.py")
        with open(path) as f:
            content = f.read()
        assert "def recommend_hnsw_params(" in content, (
            "recommend_hnsw_params function should be defined"
        )

    def test_recommend_quantization_function(self):
        """Verify recommend_quantization function is defined"""
        path = os.path.join(self.REPO_DIR, "faiss/python/param_recommender.py")
        with open(path) as f:
            content = f.read()
        assert "def recommend_quantization(" in content, (
            "recommend_quantization function should be defined"
        )

    def test_recommender_memory_warning(self):
        """Verify recommender emits warning when memory exceeds available"""
        path = os.path.join(self.REPO_DIR, "faiss/python/param_recommender.py")
        with open(path) as f:
            content = f.read()
        assert "warning" in content.lower(), (
            "Recommender should emit warning when memory exceeds available"
        )

    # === Functional Checks ===

    def test_hnsw_benchmark_parses(self):
        """Verify hnsw_benchmark.py has valid Python syntax"""
        path = os.path.join(self.REPO_DIR, "faiss/python/hnsw_benchmark.py")
        with open(path) as f:
            source = f.read()
        try:
            ast.parse(source)
        except SyntaxError as e:
            pytest.fail(f"hnsw_benchmark.py has syntax error: {e}")

    def test_quantization_parses(self):
        """Verify quantization.py has valid Python syntax"""
        path = os.path.join(self.REPO_DIR, "faiss/python/quantization.py")
        with open(path) as f:
            source = f.read()
        try:
            ast.parse(source)
        except SyntaxError as e:
            pytest.fail(f"quantization.py has syntax error: {e}")

    def test_memory_estimator_parses(self):
        """Verify memory_estimator.py has valid Python syntax"""
        path = os.path.join(self.REPO_DIR, "faiss/python/memory_estimator.py")
        with open(path) as f:
            source = f.read()
        try:
            ast.parse(source)
        except SyntaxError as e:
            pytest.fail(f"memory_estimator.py has syntax error: {e}")

    def test_param_recommender_parses(self):
        """Verify param_recommender.py has valid Python syntax"""
        path = os.path.join(self.REPO_DIR, "faiss/python/param_recommender.py")
        with open(path) as f:
            source = f.read()
        try:
            ast.parse(source)
        except SyntaxError as e:
            pytest.fail(f"param_recommender.py has syntax error: {e}")

    def test_vector_index_tuning_tests_pass(self):
        """Verify all vector index tuning tests pass"""
        result = subprocess.run(
            [
                "python", "-m", "pytest",
                "faiss/python/tests/test_vector_index_tuning.py",
                "-v", "--tb=short",
            ],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, (
            f"Tests failed:\n{result.stdout}\n{result.stderr}"
        )
