"""
Test skill: vector-index-tuning
Verify that the Agent creates a FAISS index tuning benchmark example
comparing recall vs latency across different index configurations
with configurable search effort parameters.
"""

import os
import re
import ast
import subprocess
import pytest


class TestVectorIndexTuning:
    REPO_DIR = "/workspace/faiss"

    # === File Path Checks ===

    def test_benchmark_script_exists(self):
        """Verify tutorial/python/index_tuning_benchmark.py exists"""
        path = os.path.join(
            self.REPO_DIR, "tutorial/python/index_tuning_benchmark.py"
        )
        assert os.path.exists(path), (
            f"index_tuning_benchmark.py not found at {path}"
        )

    # === Semantic Checks ===

    def test_multiple_index_types(self):
        """Verify at least two different index types are built"""
        path = os.path.join(
            self.REPO_DIR, "tutorial/python/index_tuning_benchmark.py"
        )
        with open(path) as f:
            content = f.read()

        index_types = [
            "IndexFlat", "IndexIVF", "IndexHNSW", "IndexPQ",
            "IndexScalarQuantizer", "index_factory",
            "Flat", "IVF", "HNSW", "PQ", "OPQ", "SQ",
        ]
        found = [idx for idx in index_types if idx in content]
        assert len(found) >= 2, (
            f"Should build at least two index types. Found: {found}"
        )

    def test_tuning_parameters(self):
        """Verify key tuning knobs are varied"""
        path = os.path.join(
            self.REPO_DIR, "tutorial/python/index_tuning_benchmark.py"
        )
        with open(path) as f:
            content = f.read()

        param_indicators = [
            "nprobe", "efSearch", "ef_search", "nlist",
            "nbits", "m", "k",
        ]
        found = [ind for ind in param_indicators if ind in content]
        assert len(found) >= 1, (
            f"Should vary tuning parameters. Found: {found}"
        )

    def test_recall_measurement(self):
        """Verify recall@k is computed"""
        path = os.path.join(
            self.REPO_DIR, "tutorial/python/index_tuning_benchmark.py"
        )
        with open(path) as f:
            content = f.read().lower()

        recall_indicators = [
            "recall", "ground_truth", "groundtruth", "intersection",
            "accuracy", "correct",
        ]
        found = [ind for ind in recall_indicators if ind in content]
        assert len(found) >= 2, (
            f"Should compute recall. Found: {found}"
        )

    def test_latency_measurement(self):
        """Verify query latency is measured"""
        path = os.path.join(
            self.REPO_DIR, "tutorial/python/index_tuning_benchmark.py"
        )
        with open(path) as f:
            content = f.read().lower()

        latency_indicators = [
            "time", "latency", "elapsed", "duration",
            "timeit", "perf_counter", "clock",
        ]
        found = [ind for ind in latency_indicators if ind in content]
        assert len(found) >= 2, (
            f"Should measure query latency. Found: {found}"
        )

    def test_ground_truth_computation(self):
        """Verify ground truth nearest neighbors are computed"""
        path = os.path.join(
            self.REPO_DIR, "tutorial/python/index_tuning_benchmark.py"
        )
        with open(path) as f:
            content = f.read()

        gt_indicators = [
            "ground_truth", "groundtruth", "IndexFlat", "exact",
            "brute_force", "brute force", "true_neighbors",
        ]
        found = [ind for ind in gt_indicators if ind in content]
        assert len(found) >= 1, (
            f"Should compute ground truth nearest neighbors. Found: {found}"
        )

    def test_dataset_generation(self):
        """Verify synthetic or sample dataset is used"""
        path = os.path.join(
            self.REPO_DIR, "tutorial/python/index_tuning_benchmark.py"
        )
        with open(path) as f:
            content = f.read()

        dataset_indicators = [
            "np.random", "random", "randn", "rand",
            "dataset", "vectors", "dimension", "d =",
        ]
        found = [ind for ind in dataset_indicators if ind in content]
        assert len(found) >= 2, (
            f"Should generate or load a dataset. Found: {found}"
        )

    def test_comparison_output(self):
        """Verify comparison table output"""
        path = os.path.join(
            self.REPO_DIR, "tutorial/python/index_tuning_benchmark.py"
        )
        with open(path) as f:
            content = f.read()

        output_indicators = [
            "print", "table", "format", "report",
            "recall", "latency", "time",
        ]
        found = [ind for ind in output_indicators if ind in content.lower()]
        assert len(found) >= 3, (
            f"Should produce comparison output. Found: {found}"
        )

    # === Functional Checks ===

    def test_script_valid_python(self):
        """Verify index_tuning_benchmark.py is valid Python"""
        path = os.path.join(
            self.REPO_DIR, "tutorial/python/index_tuning_benchmark.py"
        )
        with open(path) as f:
            source = f.read()
        try:
            ast.parse(source)
        except SyntaxError as e:
            pytest.fail(f"index_tuning_benchmark.py has syntax errors: {e}")

    def test_imports_faiss(self):
        """Verify script imports faiss"""
        path = os.path.join(
            self.REPO_DIR, "tutorial/python/index_tuning_benchmark.py"
        )
        with open(path) as f:
            content = f.read()

        assert "import faiss" in content, "Script should import faiss"

    def test_imports_numpy(self):
        """Verify script imports numpy"""
        path = os.path.join(
            self.REPO_DIR, "tutorial/python/index_tuning_benchmark.py"
        )
        with open(path) as f:
            content = f.read()

        assert "numpy" in content, "Script should import numpy"

    def test_documents_dataset_shape(self):
        """Verify dataset dimensions and size are documented"""
        path = os.path.join(
            self.REPO_DIR, "tutorial/python/index_tuning_benchmark.py"
        )
        with open(path) as f:
            content = f.read()

        shape_indicators = [
            "dimension", "dim", "n_vectors", "nb", "nq",
            "shape", "d =", "# ", "\"\"\"",
        ]
        found = [ind for ind in shape_indicators if ind in content]
        assert len(found) >= 2, (
            f"Should document dataset shape. Found: {found}"
        )
