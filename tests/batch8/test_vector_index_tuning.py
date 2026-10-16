"""
Tests for the vector-index-tuning skill.
Validates an HNSW index benchmarking and tuning module for FAISS with
parameter sweeps, Pareto frontier extraction, and quantization comparison.
"""

import os
import re
import ast

REPO_DIR = "/workspace/faiss"
BENCHS_DIR = os.path.join(REPO_DIR, "benchs")


class TestVectorIndexTuning:
    """Tests for the FAISS HNSW benchmarking and tuning module."""

    # ── file_path_check ──────────────────────────────────────────────

    def test_hnsw_tuner_exists(self):
        """HNSWTuner module must exist."""
        path = os.path.join(BENCHS_DIR, "hnsw_tuner.py")
        assert os.path.isfile(path), f"Missing {path}"

    def test_quantization_evaluator_exists(self):
        """QuantizationEvaluator module must exist."""
        path = os.path.join(BENCHS_DIR, "quantization_evaluator.py")
        assert os.path.isfile(path), f"Missing {path}"

    def test_benchmark_runner_exists(self):
        """BenchmarkRunner module must exist."""
        path = os.path.join(BENCHS_DIR, "benchmark_runner.py")
        assert os.path.isfile(path), f"Missing {path}"

    def test_benchmark_utils_exists(self):
        """Benchmark utility functions must exist."""
        path = os.path.join(BENCHS_DIR, "benchmark_utils.py")
        assert os.path.isfile(path), f"Missing {path}"

    # ── semantic_check ───────────────────────────────────────────────

    def _read(self, filename):
        path = os.path.join(BENCHS_DIR, filename)
        if not os.path.isfile(path):
            return ""
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def test_hnsw_tuner_class(self):
        """HNSWTuner class must be defined with sweep and pareto_frontier methods."""
        content = self._read("hnsw_tuner.py")
        assert re.search(r"class\s+HNSWTuner", content), "HNSWTuner class not defined"
        assert re.search(r"def\s+sweep\b", content), "sweep method not defined"
        assert re.search(r"def\s+pareto_frontier\b", content), "pareto_frontier method not defined"

    def test_recommend_method(self):
        """HNSWTuner must have a recommend method for target recall."""
        content = self._read("hnsw_tuner.py")
        assert re.search(r"def\s+recommend\b", content), "recommend method not defined"

    def test_quantization_evaluator_class(self):
        """QuantizationEvaluator class must be defined with compare method."""
        content = self._read("quantization_evaluator.py")
        assert re.search(r"class\s+QuantizationEvaluator", content), (
            "QuantizationEvaluator class not defined"
        )
        assert re.search(r"def\s+compare\b", content), "compare method not defined"

    def test_three_quantization_types(self):
        """QuantizationEvaluator must compare FP32, SQ8, and PQ."""
        content = self._read("quantization_evaluator.py")
        for qtype in ["FP32", "SQ8", "PQ"]:
            assert qtype in content, f"Quantization type '{qtype}' not found"

    def test_utility_functions_defined(self):
        """Utility functions must be defined."""
        content = self._read("benchmark_utils.py")
        for fn in ["generate_synthetic_data", "compute_ground_truth",
                    "compute_recall_at_k", "estimate_memory_bytes"]:
            assert re.search(rf"def\s+{fn}\b", content), (
                f"Utility function {fn} not defined in benchmark_utils.py"
            )

    def test_benchmark_runner_class(self):
        """BenchmarkRunner class must be defined with run_full_sweep."""
        content = self._read("benchmark_runner.py")
        assert re.search(r"class\s+BenchmarkRunner", content), (
            "BenchmarkRunner class not defined"
        )
        assert re.search(r"def\s+run_full_sweep\b", content), (
            "run_full_sweep method not defined"
        )

    def test_faiss_index_types_used(self):
        """HNSWTuner must use faiss.IndexHNSWFlat indexes."""
        content = self._read("hnsw_tuner.py")
        assert re.search(r"faiss\.IndexHNSW|IndexHNSWFlat", content), (
            "faiss HNSW index types not used"
        )

    # ── functional_check ─────────────────────────────────────────────

    def test_all_files_valid_python(self):
        """All benchmark Python files must have valid syntax."""
        errors = []
        for fname in ["hnsw_tuner.py", "quantization_evaluator.py",
                       "benchmark_runner.py", "benchmark_utils.py"]:
            content = self._read(fname)
            if not content:
                continue
            try:
                ast.parse(content)
            except SyntaxError as e:
                errors.append(f"{fname}: {e}")
        assert not errors, "Syntax errors:\n" + "\n".join(errors)

    def test_recall_at_k_computation(self):
        """compute_recall_at_k must compute intersection-based recall."""
        content = self._read("benchmark_utils.py")
        assert re.search(r"intersect|isin|set\(|& |intersection", content), (
            "Recall computation using intersection not found"
        )

    def test_pareto_frontier_non_dominated(self):
        """Pareto frontier must identify non-dominated configurations."""
        content = self._read("hnsw_tuner.py")
        assert re.search(r"dominat|pareto|frontier|non.dominated", content, re.IGNORECASE), (
            "Pareto frontier / non-dominated logic not found"
        )

    def test_sweep_default_parameters(self):
        """Sweep must define default M, efConstruction, efSearch values."""
        content = self._read("hnsw_tuner.py")
        # Check for default M values
        for val in ["8", "16", "32", "64"]:
            assert val in content, f"Default M value {val} not found in sweep"

    def test_memory_estimation_formula(self):
        """estimate_memory_bytes must account for vectors and graph edges."""
        content = self._read("benchmark_utils.py")
        # Check for dimension * 4 (FP32 bytes) or similar pattern
        assert re.search(r"dimension.*4|n_vectors.*M|graph.*edge", content, re.IGNORECASE), (
            "Memory estimation formula not found"
        )

    def test_recommend_target_recall_handling(self):
        """recommend must handle case where no config meets target recall."""
        content = self._read("hnsw_tuner.py")
        assert re.search(r"target_met|target_recall|highest.*recall|no config", content, re.IGNORECASE), (
            "Target recall miss handling not found in recommend"
        )
