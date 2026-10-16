"""
Tests for skill: vector-index-tuning
Repo: facebookresearch/faiss
Image: zhangyiiiiii/swe-skills-bench-python
Task: Implement an adaptive HNSW index tuner and quantization advisor for FAISS.
"""

import ast
import os
import re
import subprocess

import pytest

REPO_DIR = "/workspace/faiss"

TUNER_FILE = os.path.join(REPO_DIR, "contrib", "hnsw_tuner.py")
QUANT_FILE = os.path.join(REPO_DIR, "contrib", "quantization_advisor.py")
TEST_FILE = os.path.join(REPO_DIR, "tests", "test_hnsw_tuner.py")


# ---------------------------------------------------------------------------
# Layer 1 — file_path_check
# ---------------------------------------------------------------------------

class TestFilePathCheck:
    """Verify all required files were created."""

    def test_hnsw_tuner_file_exists(self):
        assert os.path.isfile(TUNER_FILE), f"Expected {TUNER_FILE}"

    def test_quantization_advisor_file_exists(self):
        assert os.path.isfile(QUANT_FILE), f"Expected {QUANT_FILE}"

    def test_test_file_exists(self):
        assert os.path.isfile(TEST_FILE), f"Expected {TEST_FILE}"


# ---------------------------------------------------------------------------
# Layer 2 — semantic_check
# ---------------------------------------------------------------------------

class TestSemanticHNSWTuner:
    """Verify HNSWTuner class structure."""

    @pytest.fixture(autouse=True)
    def _load_source(self):
        with open(TUNER_FILE, "r", encoding="utf-8") as f:
            self.src = f.read()
        self.tree = ast.parse(self.src)

    def test_hnsw_tuner_class_defined(self):
        classes = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.ClassDef)]
        assert "HNSWTuner" in classes, (
            f"Expected HNSWTuner class; found: {classes}"
        )

    def test_benchmark_method(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "benchmark" in funcs, "Expected benchmark() method"

    def test_recommend_method(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "recommend" in funcs, "Expected recommend() method"

    def test_benchmark_params(self):
        """Benchmark must accept M, efConstruction, efSearch parameter lists."""
        for param in ["m_values", "ef_construction", "ef_search"]:
            assert param in self.src.lower() or param.replace("_", "") in self.src.lower(), (
                f"Expected parameter '{param}' in benchmark method"
            )

    def test_recall_at_k_computation(self):
        """Must compute recall@k for benchmark evaluation."""
        assert "recall" in self.src.lower(), "Expected recall@k computation"

    def test_constraints_met_flag(self):
        """recommend() must return a constraints_met flag."""
        assert "constraints_met" in self.src, (
            "Expected constraints_met flag in recommend results"
        )

    def test_metric_support(self):
        """Must support L2 and IP metrics."""
        assert "L2" in self.src and "IP" in self.src, (
            "Expected L2 and IP metric support"
        )

    def test_perf_counter_timing(self):
        """Build/search time must use perf_counter."""
        assert "perf_counter" in self.src or "time" in self.src, (
            "Expected time.perf_counter for timing measurements"
        )


class TestSemanticQuantizationAdvisor:
    """Verify QuantizationAdvisor class."""

    @pytest.fixture(autouse=True)
    def _load_source(self):
        with open(QUANT_FILE, "r", encoding="utf-8") as f:
            self.src = f.read()
        self.tree = ast.parse(self.src)

    def test_class_defined(self):
        classes = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.ClassDef)]
        assert "QuantizationAdvisor" in classes, (
            f"Expected QuantizationAdvisor class; found: {classes}"
        )

    def test_estimate_memory_method(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "estimate_memory" in funcs, "Expected estimate_memory() method"

    def test_recommend_quantization_method(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "recommend_quantization" in funcs, "Expected recommend_quantization() method"

    def test_apply_quantization_method(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "apply_quantization" in funcs, "Expected apply_quantization() method"

    def test_index_types_supported(self):
        """Must support flat, hnsw, and ivfpq index types."""
        for idx_type in ["flat", "hnsw", "ivfpq"]:
            assert idx_type in self.src.lower(), (
                f"Expected index type '{idx_type}' support"
            )

    def test_quantization_types(self):
        """Must support none, scalar_int8, product_quantization."""
        for qtype in ["none", "scalar", "product_quantization"]:
            assert qtype in self.src.lower(), (
                f"Expected quantization type '{qtype}'"
            )

    def test_recall_impact_returned(self):
        """recommend_quantization must return expected_recall_impact."""
        assert "recall_impact" in self.src or "expected_recall" in self.src, (
            "Expected expected_recall_impact in quantization recommendation"
        )


# ---------------------------------------------------------------------------
# Layer 3 — functional_check
# ---------------------------------------------------------------------------

class TestFunctionalVectorIndexTuning:
    """Functional checks — syntax, imports, and basic validation."""

    def _run(self, cmd, cwd=REPO_DIR, timeout=60):
        return subprocess.run(
            cmd, shell=True, cwd=cwd,
            capture_output=True, text=True, timeout=timeout,
        )

    def test_tuner_valid_python(self):
        with open(TUNER_FILE, "r", encoding="utf-8") as f:
            src = f.read()
        try:
            ast.parse(src)
        except SyntaxError as e:
            pytest.fail(f"hnsw_tuner.py syntax error: {e}")

    def test_quant_valid_python(self):
        with open(QUANT_FILE, "r", encoding="utf-8") as f:
            src = f.read()
        try:
            ast.parse(src)
        except SyntaxError as e:
            pytest.fail(f"quantization_advisor.py syntax error: {e}")

    def test_test_file_valid_python(self):
        with open(TEST_FILE, "r", encoding="utf-8") as f:
            src = f.read()
        try:
            ast.parse(src)
        except SyntaxError as e:
            pytest.fail(f"test_hnsw_tuner.py syntax error: {e}")

    def test_faiss_importable(self):
        """faiss must be importable in the environment."""
        result = self._run("python -c \"import faiss; print('OK')\"", timeout=30)
        if "OK" not in result.stdout:
            pytest.skip("faiss not importable in this environment")

    def test_tuner_importable(self):
        """HNSWTuner must be importable."""
        result = self._run(
            f"python -c \"import sys; sys.path.insert(0, '{REPO_DIR}'); "
            f"from contrib.hnsw_tuner import HNSWTuner; print('OK')\"",
            timeout=30,
        )
        if result.returncode != 0:
            result2 = self._run(
                f"python -c \"import sys; sys.path.insert(0, '{os.path.join(REPO_DIR, 'contrib')}'); "
                f"from hnsw_tuner import HNSWTuner; print('OK')\"",
                timeout=30,
            )
            assert "OK" in result.stdout or "OK" in result2.stdout, (
                f"Could not import HNSWTuner:\n{result.stderr[:300]}\n{result2.stderr[:300]}"
            )

    def test_ground_truth_shape_validation(self):
        """HNSWTuner must validate ground_truth shape."""
        with open(TUNER_FILE, "r", encoding="utf-8") as f:
            src = f.read()
        has_validation = (
            "shape" in src
            and "ValueError" in src
        )
        assert has_validation, (
            "Expected ground_truth shape validation raising ValueError"
        )

    def test_memory_estimation_formula(self):
        """QuantizationAdvisor must compute memory based on known formulas."""
        with open(QUANT_FILE, "r", encoding="utf-8") as f:
            src = f.read()
        has_formula = (
            "float32" in src.lower() or "* 4" in src
            or "bytes" in src.lower()
        )
        assert has_formula, (
            "Expected memory estimation formula (n*d*4 bytes for float32)"
        )
