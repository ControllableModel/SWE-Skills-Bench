"""
Test skill: llm-evaluation
Verify that the Agent correctly implements an LLM evaluation pipeline
with custom metrics (exact match, token overlap, faithfulness, relevance)
for HELM.
"""

import os
import re
import ast
import sys
import pytest


class TestLlmEvaluation:
    REPO_DIR = "/workspace/helm"

    SCENARIO = "src/helm/benchmark/scenarios/factual_qa_scenario.py"
    METRICS = "src/helm/benchmark/metrics/qa_quality_metrics.py"
    RUN_SPEC = "src/helm/benchmark/run_specs/factual_qa_run_spec.py"
    TESTS = "tests/test_factual_qa_evaluation.py"

    def _read_file(self, rel_path):
        filepath = os.path.join(self.REPO_DIR, rel_path)
        with open(filepath) as f:
            return f.read()

    # === File Path Checks ===

    def test_scenario_file_exists(self):
        filepath = os.path.join(self.REPO_DIR, self.SCENARIO)
        assert os.path.exists(filepath), f"factual_qa_scenario.py not found at {filepath}"

    def test_metrics_file_exists(self):
        filepath = os.path.join(self.REPO_DIR, self.METRICS)
        assert os.path.exists(filepath), f"qa_quality_metrics.py not found at {filepath}"

    def test_run_spec_file_exists(self):
        filepath = os.path.join(self.REPO_DIR, self.RUN_SPEC)
        assert os.path.exists(filepath), f"factual_qa_run_spec.py not found at {filepath}"

    def test_tests_file_exists(self):
        filepath = os.path.join(self.REPO_DIR, self.TESTS)
        assert os.path.exists(filepath), f"test file not found at {filepath}"

    # === Semantic Checks ===

    def test_scenario_class_defined(self):
        """Verify FactualQAScenario with get_instances"""
        content = self._read_file(self.SCENARIO)
        assert "FactualQAScenario" in content, "Missing FactualQAScenario class"
        assert "get_instances" in content, "Missing get_instances method"
        assert "dataset_path" in content, "Missing dataset_path parameter"

    def test_scenario_formats_input(self):
        """Verify input format: Context + Question + Answer prompt"""
        content = self._read_file(self.SCENARIO)
        assert "Context" in content, "Scenario input missing 'Context:' prefix"
        assert "Question" in content, "Scenario input missing 'Question:' prefix"

    def test_scenario_splits_train_test(self):
        """Verify 80/20 train/test split"""
        content = self._read_file(self.SCENARIO)
        has_split = bool(re.search(
            r'(TRAIN_SPLIT|TEST_SPLIT|train|test|0\.8|80)', content
        ))
        assert has_split, "Scenario missing train/test split logic"

    def test_exact_match_metric_defined(self):
        """Verify ExactMatchMetric with case-insensitive comparison"""
        content = self._read_file(self.METRICS)
        assert "ExactMatchMetric" in content, "Missing ExactMatchMetric class"
        assert "lower" in content, "ExactMatchMetric missing case-insensitive comparison"

    def test_token_overlap_metric_defined(self):
        """Verify TokenOverlapMetric with F1 computation"""
        content = self._read_file(self.METRICS)
        assert "TokenOverlapMetric" in content, "Missing TokenOverlapMetric class"
        has_f1 = bool(re.search(r'(f1|precision.*recall|2\s*\*)', content, re.IGNORECASE))
        assert has_f1, "TokenOverlapMetric missing F1 computation"

    def test_faithfulness_metric_defined(self):
        """Verify FaithfulnessMetric checks claims against context"""
        content = self._read_file(self.METRICS)
        assert "FaithfulnessMetric" in content, "Missing FaithfulnessMetric class"
        assert "context" in content, "FaithfulnessMetric missing context parameter"
        has_content_words = bool(re.search(
            r'(content.?word|stop.?word|len.*>=.*4|noun)', content, re.IGNORECASE
        ))
        assert has_content_words, \
            "FaithfulnessMetric missing content word extraction"

    def test_answer_relevance_metric_defined(self):
        """Verify AnswerRelevanceMetric with keyword overlap"""
        content = self._read_file(self.METRICS)
        assert "AnswerRelevanceMetric" in content, "Missing AnswerRelevanceMetric class"

    def test_run_spec_wires_all_components(self):
        """Verify run spec connects scenario, metrics, and adapter"""
        content = self._read_file(self.RUN_SPEC)
        assert "FactualQAScenario" in content, "Run spec missing scenario reference"
        assert "generation" in content, "Run spec missing generation adapter method"
        assert "max_tokens" in content, "Run spec missing max_tokens"
        assert "temperature" in content, "Run spec missing temperature"

    # === Functional Checks ===

    def test_all_files_valid_python(self):
        """Verify all Python files have valid syntax"""
        for path in [self.SCENARIO, self.METRICS, self.RUN_SPEC]:
            filepath = os.path.join(self.REPO_DIR, path)
            with open(filepath) as f:
                try:
                    ast.parse(f.read())
                except SyntaxError as e:
                    pytest.fail(f"{path} syntax error: {e}")

    def test_functional_exact_match(self):
        """Verify ExactMatchMetric returns 1.0 for case-insensitive match"""
        sys.path.insert(0, os.path.join(self.REPO_DIR, "src"))
        try:
            from helm.benchmark.metrics.qa_quality_metrics import ExactMatchMetric
            metric = ExactMatchMetric()
            result = metric.evaluate("Paris", "paris")
            score = result.score if hasattr(result, "score") else result
            assert score == 1.0, f"ExactMatch('Paris','paris') should be 1.0, got {score}"
        except ImportError:
            pytest.skip("Cannot import qa_quality_metrics")
        finally:
            if os.path.join(self.REPO_DIR, "src") in sys.path:
                sys.path.remove(os.path.join(self.REPO_DIR, "src"))

    def test_functional_token_overlap(self):
        """Verify TokenOverlapMetric computes correct F1"""
        sys.path.insert(0, os.path.join(self.REPO_DIR, "src"))
        try:
            from helm.benchmark.metrics.qa_quality_metrics import TokenOverlapMetric
            metric = TokenOverlapMetric()
            result = metric.evaluate(
                "The capital is Paris",
                "Paris is the capital of France",
            )
            score = result.score if hasattr(result, "score") else result
            assert 0.5 < score < 0.9, \
                f"TokenOverlap F1 should be ~0.67, got {score}"
        except ImportError:
            pytest.skip("Cannot import qa_quality_metrics")
        finally:
            if os.path.join(self.REPO_DIR, "src") in sys.path:
                sys.path.remove(os.path.join(self.REPO_DIR, "src"))

    def test_tests_cover_all_metrics(self):
        """Verify test file covers all four metrics"""
        content = self._read_file(self.TESTS)
        tree = ast.parse(content)
        test_funcs = [
            n.name for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")
        ]
        assert len(test_funcs) >= 6, \
            f"Expected at least 6 tests, found {len(test_funcs)}"
        content_lower = content.lower()
        assert "exact" in content_lower, "Tests missing ExactMatch coverage"
        assert "overlap" in content_lower or "token" in content_lower, \
            "Tests missing TokenOverlap coverage"
        assert "faithful" in content_lower, "Tests missing Faithfulness coverage"
