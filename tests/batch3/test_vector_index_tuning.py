"""
Tests for the vector-index-tuning skill.

Validates that HNSW parameter tuning benchmarks, quantization strategy
evaluation, index recommendation engine, and benchmark report generation
were implemented for FAISS.

Repo: faiss (https://github.com/facebookresearch/faiss)
"""

import ast
import os
import re

REPO_DIR = "/workspace/faiss"


class TestFilePathCheck:
    """Verify that all required files were created."""

    def test_hnsw_tuning_file_exists(self):
        path = os.path.join(REPO_DIR, "benchs", "hnsw_tuning.py")
        assert os.path.isfile(path), f"Expected hnsw_tuning.py at {path}"

    def test_quantization_benchmark_file_exists(self):
        path = os.path.join(REPO_DIR, "benchs", "quantization_benchmark.py")
        assert os.path.isfile(path), f"Expected quantization_benchmark.py at {path}"

    def test_index_selector_file_exists(self):
        path = os.path.join(REPO_DIR, "benchs", "index_selector.py")
        assert os.path.isfile(path), f"Expected index_selector.py at {path}"

    def test_benchmark_report_file_exists(self):
        path = os.path.join(REPO_DIR, "benchs", "benchmark_report.py")
        assert os.path.isfile(path), f"Expected benchmark_report.py at {path}"

    def test_test_file_exists(self):
        path = os.path.join(REPO_DIR, "tests", "test_hnsw_tuning.py")
        assert os.path.isfile(path), f"Expected test_hnsw_tuning.py at {path}"


class TestSemanticHNSWTuner:
    """Verify HNSWTuner class and parameter sweep."""

    def _read_hnsw(self):
        path = os.path.join(REPO_DIR, "benchs", "hnsw_tuning.py")
        with open(path, "r") as f:
            return f.read()

    def test_hnsw_tuner_class(self):
        content = self._read_hnsw()
        assert re.search(r"class\s+HNSWTuner", content), (
            "Expected HNSWTuner class"
        )

    def test_m_parameter_values(self):
        content = self._read_hnsw()
        for m in ["8", "16", "32", "64"]:
            assert m in content, f"Expected M value {m} in HNSW tuning parameters"

    def test_ef_construction_values(self):
        content = self._read_hnsw()
        for ef in ["40", "100", "200", "400"]:
            assert ef in content, f"Expected efConstruction value {ef}"

    def test_ef_search_values(self):
        content = self._read_hnsw()
        for ef in ["16", "128", "256"]:
            assert ef in content, f"Expected efSearch value {ef}"

    def test_recall_computation(self):
        """Recall should be computed against IndexFlatL2 ground truth."""
        content = self._read_hnsw()
        assert re.search(r"recall|IndexFlatL2|ground.truth|brute.force", content, re.IGNORECASE), (
            "Expected recall computation against IndexFlatL2 ground truth"
        )

    def test_metrics_measured(self):
        """Should measure build time, index size, query latency, recall."""
        content = self._read_hnsw()
        metrics = ["build_time", "index_size", "latency", "recall"]
        found = sum(1 for m in metrics if re.search(m, content, re.IGNORECASE))
        assert found >= 3, (
            f"Expected at least 3 of 4 metrics measured, found {found}"
        )

    def test_random_seed_reproducibility(self):
        content = self._read_hnsw()
        assert re.search(r"seed|random_state|np\.random\.seed|RandomState", content), (
            "Expected random seed for reproducibility"
        )


class TestSemanticQuantizationBenchmark:
    """Verify quantization strategy benchmarks."""

    def _read_quant(self):
        path = os.path.join(REPO_DIR, "benchs", "quantization_benchmark.py")
        with open(path, "r") as f:
            return f.read()

    def test_pq_quantization(self):
        content = self._read_quant()
        assert re.search(r"PQ|ProductQuantiz|IndexHNSWPQ", content, re.IGNORECASE), (
            "Expected PQ (Product Quantization) benchmark"
        )

    def test_sq_quantization(self):
        content = self._read_quant()
        assert re.search(r"SQ|ScalarQuantiz|IndexHNSWSQ|QT_8bit|QT_4bit", content, re.IGNORECASE), (
            "Expected SQ (Scalar Quantization) benchmark"
        )

    def test_opq_quantization(self):
        content = self._read_quant()
        assert re.search(r"OPQ|OPQMatrix|Optimized.*Product", content, re.IGNORECASE), (
            "Expected OPQ (Optimized Product Quantization) benchmark"
        )

    def test_compression_ratio(self):
        content = self._read_quant()
        assert re.search(r"compression.ratio|original.*index.*size", content, re.IGNORECASE), (
            "Expected compression ratio computation"
        )


class TestSemanticIndexSelector:
    """Verify index recommendation engine."""

    def _read_selector(self):
        path = os.path.join(REPO_DIR, "benchs", "index_selector.py")
        with open(path, "r") as f:
            return f.read()

    def test_recommend_index_function(self):
        content = self._read_selector()
        assert re.search(r"def\s+recommend_index", content), (
            "Expected recommend_index function"
        )

    def test_recommendation_class(self):
        content = self._read_selector()
        assert re.search(r"class\s+Recommendation|Recommendation", content), (
            "Expected Recommendation class or namedtuple"
        )

    def test_flat_index_for_small_datasets(self):
        """Should recommend IndexFlatL2 for < 100K vectors."""
        content = self._read_selector()
        assert re.search(r"100.?000|100_000|IndexFlatL2|Flat", content), (
            "Expected IndexFlatL2 recommendation threshold at 100K vectors"
        )

    def test_ivfpq_for_large_datasets(self):
        """Should recommend IVF-PQ for >= 1M vectors."""
        content = self._read_selector()
        assert re.search(r"1.?000.?000|1_000_000|IndexIVFPQ|IVFPQ", content), (
            "Expected IndexIVFPQ recommendation for large datasets"
        )

    def test_memory_estimation(self):
        content = self._read_selector()
        assert re.search(r"estimated_memory|memory_mb|memory_budget", content), (
            "Expected memory estimation in recommendations"
        )

    def test_reasoning_field(self):
        content = self._read_selector()
        assert re.search(r"reasoning", content), (
            "Expected reasoning field in Recommendation"
        )


class TestSemanticBenchmarkReport:
    """Verify benchmark report generation."""

    def _read_report(self):
        path = os.path.join(REPO_DIR, "benchs", "benchmark_report.py")
        with open(path, "r") as f:
            return f.read()

    def test_benchmark_report_class(self):
        content = self._read_report()
        assert re.search(r"class\s+BenchmarkReport", content), (
            "Expected BenchmarkReport class"
        )

    def test_add_result_method(self):
        content = self._read_report()
        assert re.search(r"def\s+add_result", content), (
            "Expected add_result method"
        )

    def test_generate_table_method(self):
        content = self._read_report()
        assert re.search(r"def\s+generate_table", content), (
            "Expected generate_table method"
        )

    def test_pareto_frontier_method(self):
        content = self._read_report()
        assert re.search(r"def\s+pareto_frontier|def\s+pareto", content), (
            "Expected pareto_frontier method"
        )

    def test_csv_export(self):
        content = self._read_report()
        assert re.search(r"def\s+to_csv", content), (
            "Expected to_csv method for CSV export"
        )

    def test_json_export(self):
        content = self._read_report()
        assert re.search(r"def\s+to_json", content), (
            "Expected to_json method for JSON export"
        )


class TestFunctionalPythonSyntax:
    """Validate Python syntax of all created files."""

    def _check_syntax(self, filepath):
        with open(filepath, "r") as f:
            source = f.read()
        ast.parse(source)

    def test_hnsw_tuning_syntax(self):
        self._check_syntax(os.path.join(REPO_DIR, "benchs", "hnsw_tuning.py"))

    def test_quantization_benchmark_syntax(self):
        self._check_syntax(os.path.join(REPO_DIR, "benchs", "quantization_benchmark.py"))

    def test_index_selector_syntax(self):
        self._check_syntax(os.path.join(REPO_DIR, "benchs", "index_selector.py"))

    def test_benchmark_report_syntax(self):
        self._check_syntax(os.path.join(REPO_DIR, "benchs", "benchmark_report.py"))

    def test_test_file_syntax(self):
        self._check_syntax(os.path.join(REPO_DIR, "tests", "test_hnsw_tuning.py"))


class TestFunctionalTestCoverage:
    """Verify the agent's test file has adequate coverage."""

    def _read_test(self):
        path = os.path.join(REPO_DIR, "tests", "test_hnsw_tuning.py")
        with open(path, "r") as f:
            return f.read()

    def test_sufficient_test_count(self):
        content = self._read_test()
        test_count = len(re.findall(r"def\s+test_", content))
        assert test_count >= 5, (
            f"Expected at least 5 test functions, found {test_count}"
        )

    def test_covers_recall_computation(self):
        content = self._read_test()
        assert re.search(r"recall", content, re.IGNORECASE), (
            "Expected test coverage for recall computation"
        )

    def test_covers_recommendation(self):
        content = self._read_test()
        assert re.search(r"recommend|selector", content, re.IGNORECASE), (
            "Expected test coverage for index recommendation"
        )

    def test_covers_pareto(self):
        content = self._read_test()
        assert re.search(r"pareto", content, re.IGNORECASE), (
            "Expected test coverage for Pareto frontier"
        )
