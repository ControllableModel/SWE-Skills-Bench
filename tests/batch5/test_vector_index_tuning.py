"""
Test skill: vector-index-tuning
Verify that the Agent correctly implements a FAISS index benchmarking suite
with multiple index configurations, metrics, and report generation.
"""

import os
import re
import ast
import pytest


class TestVectorIndexTuning:
    REPO_DIR = "/workspace/faiss"

    BENCHMARK = "benchs/index_benchmark.py"
    CONFIGS = "benchs/index_configs.py"
    REPORT = "benchs/report_generator.py"
    TESTS = "tests/test_index_benchmark.py"

    def _read_file(self, rel_path):
        filepath = os.path.join(self.REPO_DIR, rel_path)
        with open(filepath) as f:
            return f.read()

    # === File Path Checks ===

    def test_benchmark_file_exists(self):
        filepath = os.path.join(self.REPO_DIR, self.BENCHMARK)
        assert os.path.exists(filepath), f"index_benchmark.py not found at {filepath}"

    def test_configs_file_exists(self):
        filepath = os.path.join(self.REPO_DIR, self.CONFIGS)
        assert os.path.exists(filepath), f"index_configs.py not found at {filepath}"

    def test_report_file_exists(self):
        filepath = os.path.join(self.REPO_DIR, self.REPORT)
        assert os.path.exists(filepath), f"report_generator.py not found at {filepath}"

    def test_tests_file_exists(self):
        filepath = os.path.join(self.REPO_DIR, self.TESTS)
        assert os.path.exists(filepath), f"test_index_benchmark.py not found at {filepath}"

    # === Semantic Checks ===

    def test_configs_define_all_index_types(self):
        """Verify configs define Flat, IVF4096, HNSW32, PQ32, IVF4096_PQ32"""
        content = self._read_file(self.CONFIGS)
        for idx_name in ["Flat", "IVF4096", "HNSW32", "PQ32"]:
            assert idx_name in content, f"Configs missing index type: {idx_name}"

    def test_configs_use_factory_strings(self):
        """Verify configs use FAISS index factory strings"""
        content = self._read_file(self.CONFIGS)
        factory_patterns = ["IVF4096,Flat", "HNSW32", "PQ32", "IVF4096,PQ32"]
        found = sum(1 for p in factory_patterns if p in content)
        assert found >= 3, \
            f"Configs should include at least 3 factory strings, found {found}"

    def test_configs_define_search_parameters(self):
        """Verify configs include nprobe and efSearch parameters"""
        content = self._read_file(self.CONFIGS)
        assert "nprobe" in content, "Configs missing nprobe parameter"
        assert "efSearch" in content, "Configs missing efSearch parameter"

    def test_benchmark_generates_synthetic_data(self):
        """Verify benchmark generates 1M vectors of dim 128 with seed 42"""
        content = self._read_file(self.BENCHMARK)
        assert "128" in content, "Benchmark missing dimension D=128"
        assert "42" in content, "Benchmark missing seed=42"
        has_million = bool(re.search(r'(1_?000_?000|1e6|10\*\*6)', content))
        assert has_million, "Benchmark missing N=1,000,000 vector count"

    def test_benchmark_computes_ground_truth(self):
        """Verify benchmark computes ground truth with IndexFlatL2"""
        content = self._read_file(self.BENCHMARK)
        assert "IndexFlatL2" in content, "Benchmark missing IndexFlatL2 for ground truth"
        assert "100" in content, "Benchmark missing k=100 for ground truth"

    def test_benchmark_measures_all_metrics(self):
        """Verify benchmark measures build time, latency, recall, memory"""
        content = self._read_file(self.BENCHMARK)
        for metric in ["build_time", "latency", "recall", "memory"]:
            assert metric in content.lower(), f"Benchmark missing metric: {metric}"

    def test_benchmark_measures_p99_latency(self):
        """Verify benchmark computes P99 latency"""
        content = self._read_file(self.BENCHMARK)
        has_p99 = bool(re.search(r'(p99|percentile.*99|99th)', content, re.IGNORECASE))
        assert has_p99, "Benchmark missing P99 latency measurement"

    def test_report_generates_markdown(self):
        """Verify report generator produces Markdown table"""
        content = self._read_file(self.REPORT)
        assert "generate_report" in content, "Missing generate_report function"
        has_md = bool(re.search(r'(\|.*\|.*\||markdown|table)', content, re.IGNORECASE))
        assert has_md, "Report missing Markdown table generation"

    def test_report_has_recommend_function(self):
        """Verify recommend function with recall and latency thresholds"""
        content = self._read_file(self.REPORT)
        assert "recommend" in content, "Missing recommend function"
        assert "min_recall" in content, "recommend missing min_recall parameter"
        assert "max_latency" in content, "recommend missing max_latency parameter"

    # === Functional Checks ===

    def test_all_files_valid_python(self):
        """Verify all files have valid Python syntax"""
        for path in [self.BENCHMARK, self.CONFIGS, self.REPORT]:
            filepath = os.path.join(self.REPO_DIR, path)
            with open(filepath) as f:
                try:
                    ast.parse(f.read())
                except SyntaxError as e:
                    pytest.fail(f"{path} syntax error: {e}")

    def test_recall_computation_logic(self):
        """Verify benchmark includes recall@10 and recall@100 calculation"""
        content = self._read_file(self.BENCHMARK)
        has_recall10 = bool(re.search(r'recall.*10|@10|k=10|k\s*=\s*10', content))
        has_recall100 = bool(re.search(r'recall.*100|@100|k=100|k\s*=\s*100', content))
        assert has_recall10, "Benchmark missing recall@10 computation"
        assert has_recall100, "Benchmark missing recall@100 computation"

    def test_tests_use_small_scale_data(self):
        """Verify tests use 10K vectors for validation"""
        content = self._read_file(self.TESTS)
        has_10k = bool(re.search(r'(10_?000|10000|1e4)', content))
        assert has_10k, "Tests should use 10K vectors for small-scale validation"
        tree = ast.parse(content)
        test_funcs = [
            n.name for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")
        ]
        assert len(test_funcs) >= 3, \
            f"Expected at least 3 tests, found {len(test_funcs)}"
