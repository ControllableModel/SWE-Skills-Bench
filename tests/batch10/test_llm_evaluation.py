"""
Test skill: llm-evaluation
Verify that the Agent correctly implements an automated evaluation suite
with LLM-as-Judge for HELM.
"""

import os
import re
import ast
import subprocess
import pytest


class TestLlmEvaluation:
    REPO_DIR = "/workspace/helm"

    # === File Path Checks ===

    def test_text_generation_metrics_exists(self):
        """Verify text_generation_metrics.py was created"""
        path = os.path.join(
            self.REPO_DIR,
            "src/helm/benchmark/metrics/text_generation_metrics.py",
        )
        assert os.path.exists(path), f"text_generation_metrics.py not found"

    def test_llm_judge_exists(self):
        """Verify llm_judge.py was created"""
        path = os.path.join(
            self.REPO_DIR,
            "src/helm/benchmark/metrics/llm_judge.py",
        )
        assert os.path.exists(path), f"llm_judge.py not found"

    def test_custom_metrics_exists(self):
        """Verify custom_metrics.py was created"""
        path = os.path.join(
            self.REPO_DIR,
            "src/helm/benchmark/metrics/custom_metrics.py",
        )
        assert os.path.exists(path), f"custom_metrics.py not found"

    def test_evaluation_suite_exists(self):
        """Verify evaluation_suite.py was created"""
        path = os.path.join(
            self.REPO_DIR,
            "src/helm/benchmark/runner/evaluation_suite.py",
        )
        assert os.path.exists(path), f"evaluation_suite.py not found"

    def test_regression_detector_exists(self):
        """Verify regression_detector.py was created"""
        path = os.path.join(
            self.REPO_DIR,
            "src/helm/benchmark/runner/regression_detector.py",
        )
        assert os.path.exists(path), f"regression_detector.py not found"

    def test_ab_test_exists(self):
        """Verify ab_test.py was created"""
        path = os.path.join(
            self.REPO_DIR,
            "src/helm/benchmark/runner/ab_test.py",
        )
        assert os.path.exists(path), f"ab_test.py not found"

    def test_text_metrics_test_exists(self):
        """Verify text generation metrics test was created"""
        path = os.path.join(
            self.REPO_DIR,
            "src/helm/benchmark/tests/test_text_generation_metrics.py",
        )
        assert os.path.exists(path), f"test_text_generation_metrics.py not found"

    # === Semantic Checks: Text Generation Metrics ===

    def test_bleu_function_defined(self):
        """Verify calculate_bleu function is defined"""
        path = os.path.join(
            self.REPO_DIR,
            "src/helm/benchmark/metrics/text_generation_metrics.py",
        )
        with open(path) as f:
            content = f.read()
        assert "calculate_bleu" in content, (
            "calculate_bleu function should be defined"
        )

    def test_rouge_function_defined(self):
        """Verify calculate_rouge function is defined"""
        path = os.path.join(
            self.REPO_DIR,
            "src/helm/benchmark/metrics/text_generation_metrics.py",
        )
        with open(path) as f:
            content = f.read()
        assert "calculate_rouge" in content, (
            "calculate_rouge function should be defined"
        )

    def test_bertscore_function_defined(self):
        """Verify calculate_bertscore function is defined"""
        path = os.path.join(
            self.REPO_DIR,
            "src/helm/benchmark/metrics/text_generation_metrics.py",
        )
        with open(path) as f:
            content = f.read()
        assert "calculate_bertscore" in content, (
            "calculate_bertscore function should be defined"
        )

    def test_rouge_returns_dict_keys(self):
        """Verify ROUGE returns rouge1, rouge2, rougeL"""
        path = os.path.join(
            self.REPO_DIR,
            "src/helm/benchmark/metrics/text_generation_metrics.py",
        )
        with open(path) as f:
            content = f.read()
        for key in ["rouge1", "rouge2", "rougeL"]:
            assert key in content, f"calculate_rouge should return '{key}' key"

    # === Semantic Checks: LLM Judge ===

    def test_llm_judge_class_defined(self):
        """Verify LLMJudge class is defined"""
        path = os.path.join(
            self.REPO_DIR,
            "src/helm/benchmark/metrics/llm_judge.py",
        )
        with open(path) as f:
            content = f.read()
        assert "class LLMJudge" in content, "LLMJudge class should be defined"

    def test_llm_judge_pointwise_evaluate(self):
        """Verify pointwise_evaluate method exists"""
        path = os.path.join(
            self.REPO_DIR,
            "src/helm/benchmark/metrics/llm_judge.py",
        )
        with open(path) as f:
            content = f.read()
        assert "pointwise_evaluate" in content, (
            "Should have pointwise_evaluate method"
        )

    def test_llm_judge_pairwise_compare(self):
        """Verify pairwise_compare method exists"""
        path = os.path.join(
            self.REPO_DIR,
            "src/helm/benchmark/metrics/llm_judge.py",
        )
        with open(path) as f:
            content = f.read()
        assert "pairwise_compare" in content, (
            "Should have pairwise_compare method"
        )

    def test_llm_judge_reference_evaluate(self):
        """Verify reference_evaluate method exists"""
        path = os.path.join(
            self.REPO_DIR,
            "src/helm/benchmark/metrics/llm_judge.py",
        )
        with open(path) as f:
            content = f.read()
        assert "reference_evaluate" in content, (
            "Should have reference_evaluate method"
        )

    # === Semantic Checks: Evaluation Suite ===

    def test_evaluation_suite_class_defined(self):
        """Verify EvaluationSuite class is defined"""
        path = os.path.join(
            self.REPO_DIR,
            "src/helm/benchmark/runner/evaluation_suite.py",
        )
        with open(path) as f:
            content = f.read()
        assert "class EvaluationSuite" in content, (
            "EvaluationSuite class should be defined"
        )

    def test_suite_has_evaluate_method(self):
        """Verify evaluate method exists"""
        path = os.path.join(
            self.REPO_DIR,
            "src/helm/benchmark/runner/evaluation_suite.py",
        )
        with open(path) as f:
            content = f.read()
        assert "def evaluate(" in content, "Should have evaluate method"

    def test_suite_has_generate_report(self):
        """Verify generate_report method exists"""
        path = os.path.join(
            self.REPO_DIR,
            "src/helm/benchmark/runner/evaluation_suite.py",
        )
        with open(path) as f:
            content = f.read()
        assert "generate_report" in content, (
            "Should have generate_report method"
        )

    # === Semantic Checks: Regression Detector ===

    def test_regression_detector_class(self):
        """Verify regression detection with threshold"""
        path = os.path.join(
            self.REPO_DIR,
            "src/helm/benchmark/runner/regression_detector.py",
        )
        with open(path) as f:
            content = f.read()
        assert "threshold" in content, "Should use configurable threshold"
        assert "has_regression" in content, (
            "Should return has_regression flag"
        )

    def test_regression_detects_missing_metrics(self):
        """Verify detection of metrics missing in current but present in baseline"""
        path = os.path.join(
            self.REPO_DIR,
            "src/helm/benchmark/runner/regression_detector.py",
        )
        with open(path) as f:
            content = f.read()
        assert "-100" in content, (
            "Missing metrics should be flagged with -100.0 change"
        )

    # === Semantic Checks: A/B Test ===

    def test_ab_test_class_defined(self):
        """Verify A/B test harness class is defined"""
        path = os.path.join(
            self.REPO_DIR,
            "src/helm/benchmark/runner/ab_test.py",
        )
        with open(path) as f:
            content = f.read()
        assert "class" in content, "Should define an A/B test class"

    def test_ab_test_has_analyze_method(self):
        """Verify analyze method exists"""
        path = os.path.join(
            self.REPO_DIR,
            "src/helm/benchmark/runner/ab_test.py",
        )
        with open(path) as f:
            content = f.read()
        assert "def analyze(" in content, "Should have analyze method"

    def test_ab_test_uses_t_test(self):
        """Verify t-test is used for statistical significance"""
        path = os.path.join(
            self.REPO_DIR,
            "src/helm/benchmark/runner/ab_test.py",
        )
        with open(path) as f:
            content = f.read()
        assert "ttest" in content.lower() or "t_test" in content or "t-test" in content.lower() or "scipy" in content, (
            "Should use t-test for significance testing"
        )

    def test_ab_test_computes_cohens_d(self):
        """Verify Cohen's d effect size is computed"""
        path = os.path.join(
            self.REPO_DIR,
            "src/helm/benchmark/runner/ab_test.py",
        )
        with open(path) as f:
            content = f.read()
        assert "cohen" in content.lower(), (
            "Should compute Cohen's d effect size"
        )

    # === Functional Checks ===

    def test_text_metrics_parses(self):
        """Verify text_generation_metrics.py has valid Python syntax"""
        path = os.path.join(
            self.REPO_DIR,
            "src/helm/benchmark/metrics/text_generation_metrics.py",
        )
        with open(path) as f:
            source = f.read()
        try:
            ast.parse(source)
        except SyntaxError as e:
            pytest.fail(f"text_generation_metrics.py has syntax error: {e}")

    def test_llm_judge_parses(self):
        """Verify llm_judge.py has valid Python syntax"""
        path = os.path.join(
            self.REPO_DIR,
            "src/helm/benchmark/metrics/llm_judge.py",
        )
        with open(path) as f:
            source = f.read()
        try:
            ast.parse(source)
        except SyntaxError as e:
            pytest.fail(f"llm_judge.py has syntax error: {e}")

    def test_ab_test_parses(self):
        """Verify ab_test.py has valid Python syntax"""
        path = os.path.join(
            self.REPO_DIR,
            "src/helm/benchmark/runner/ab_test.py",
        )
        with open(path) as f:
            source = f.read()
        try:
            ast.parse(source)
        except SyntaxError as e:
            pytest.fail(f"ab_test.py has syntax error: {e}")

    def test_text_metrics_tests_pass(self):
        """Verify text generation metrics tests pass"""
        result = subprocess.run(
            [
                "python", "-m", "pytest",
                "src/helm/benchmark/tests/test_text_generation_metrics.py",
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
