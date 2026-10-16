"""
Tests for the llm-evaluation skill.
Validates an evaluation framework for LLM output quality in HELM with
automated metrics, LLM-as-judge, regression detection, and suite orchestration.
"""

import os
import re
import ast

REPO_DIR = "/workspace/helm"
METRICS_DIR = os.path.join(REPO_DIR, "src", "helm", "benchmark", "metrics")


class TestLlmEvaluation:
    """Tests for the HELM LLM evaluation framework."""

    # ── file_path_check ──────────────────────────────────────────────

    def test_quality_evaluator_exists(self):
        """QualityEvaluator module must exist."""
        path = os.path.join(METRICS_DIR, "quality_evaluator.py")
        assert os.path.isfile(path), f"Missing {path}"

    def test_llm_judge_exists(self):
        """LLMJudge module must exist."""
        path = os.path.join(METRICS_DIR, "llm_judge.py")
        assert os.path.isfile(path), f"Missing {path}"

    def test_regression_detector_exists(self):
        """RegressionDetector module must exist."""
        path = os.path.join(METRICS_DIR, "regression_detector.py")
        assert os.path.isfile(path), f"Missing {path}"

    def test_evaluation_suite_exists(self):
        """EvaluationSuite module must exist."""
        path = os.path.join(METRICS_DIR, "evaluation_suite.py")
        assert os.path.isfile(path), f"Missing {path}"

    # ── semantic_check ───────────────────────────────────────────────

    def _read(self, filename):
        path = os.path.join(METRICS_DIR, filename)
        if not os.path.isfile(path):
            return ""
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def test_quality_evaluator_class(self):
        """QualityEvaluator must define evaluate and evaluate_batch methods."""
        content = self._read("quality_evaluator.py")
        assert re.search(r"class\s+QualityEvaluator", content), (
            "QualityEvaluator class not defined"
        )
        assert re.search(r"def\s+evaluate\b", content), "evaluate method not defined"
        assert re.search(r"def\s+evaluate_batch\b", content), "evaluate_batch method not defined"

    def test_metric_implementations(self):
        """QualityEvaluator must implement exact_match, bleu, rouge_l, f1."""
        content = self._read("quality_evaluator.py")
        for metric in ["exact_match", "bleu", "rouge_l", "f1"]:
            assert metric in content, f"Metric '{metric}' implementation not found"

    def test_custom_metric_registration(self):
        """QualityEvaluator must support custom metric registration."""
        content = self._read("quality_evaluator.py")
        assert re.search(r"def\s+register_metric\b", content), (
            "register_metric method not defined"
        )

    def test_llm_judge_class(self):
        """LLMJudge must define score_pointwise and compare_pairwise methods."""
        content = self._read("llm_judge.py")
        assert re.search(r"class\s+LLMJudge", content), "LLMJudge class not defined"
        assert re.search(r"def\s+score_pointwise\b", content), "score_pointwise not defined"
        assert re.search(r"def\s+compare_pairwise\b", content), "compare_pairwise not defined"

    def test_judge_dimensions(self):
        """LLMJudge must use accuracy, coherence, relevance, helpfulness dimensions."""
        content = self._read("llm_judge.py")
        for dim in ["accuracy", "coherence", "relevance", "helpfulness"]:
            assert dim in content, f"Dimension '{dim}' not found in LLMJudge"

    def test_regression_detector_class(self):
        """RegressionDetector must define compare method with t-test."""
        content = self._read("regression_detector.py")
        assert re.search(r"class\s+RegressionDetector", content), (
            "RegressionDetector class not defined"
        )
        assert re.search(r"def\s+compare\b", content), "compare method not defined"
        assert re.search(r"t.test|ttest|scipy.*stats", content, re.IGNORECASE), (
            "Paired t-test not found in regression detector"
        )

    def test_evaluation_suite_class(self):
        """EvaluationSuite must define run method orchestrating evaluators."""
        content = self._read("evaluation_suite.py")
        assert re.search(r"class\s+EvaluationSuite", content), (
            "EvaluationSuite class not defined"
        )
        assert re.search(r"def\s+run\b", content), "run method not defined"

    # ── functional_check ─────────────────────────────────────────────

    def test_all_files_valid_python(self):
        """All evaluation Python files must have valid syntax."""
        errors = []
        for fname in ["quality_evaluator.py", "llm_judge.py",
                       "regression_detector.py", "evaluation_suite.py"]:
            content = self._read(fname)
            if not content:
                continue
            try:
                ast.parse(content)
            except SyntaxError as e:
                errors.append(f"{fname}: {e}")
        assert not errors, "Syntax errors:\n" + "\n".join(errors)

    def test_bleu_brevity_penalty(self):
        """BLEU implementation must include brevity penalty."""
        content = self._read("quality_evaluator.py")
        assert re.search(r"brevity|penalty|bp|exp\(|min\(", content, re.IGNORECASE), (
            "BLEU brevity penalty not found"
        )

    def test_rouge_l_lcs(self):
        """ROUGE-L must use longest common subsequence."""
        content = self._read("quality_evaluator.py")
        assert re.search(r"lcs|longest.common|subsequence", content, re.IGNORECASE), (
            "Longest common subsequence not found for ROUGE-L"
        )

    def test_json_parse_error_handling(self):
        """LLMJudge must handle malformed JSON from judge responses."""
        content = self._read("llm_judge.py")
        assert re.search(r"parse_error|JSONDecodeError|json\.loads|except", content), (
            "JSON parse error handling not found in LLMJudge"
        )

    def test_regression_significance_level(self):
        """RegressionDetector must use configurable significance level."""
        content = self._read("regression_detector.py")
        assert re.search(r"significance|p_value|alpha|0\.05", content), (
            "Significance level configuration not found"
        )

    def test_test_file_exists(self):
        """Test suite file must exist."""
        path = os.path.join(REPO_DIR, "tests", "test_llm_evaluation.py")
        assert os.path.isfile(path), f"Missing {path}"
