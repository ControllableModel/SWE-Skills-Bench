"""
Tests for the llm-evaluation skill.

Validates that an LLM evaluation framework with multi-metric scoring,
faithfulness metric, LLM-as-judge, and structured evaluation reports
was implemented for HELM.

Repo: helm (https://github.com/stanford-crfm/helm)
"""

import ast
import os
import re
import subprocess
import sys

REPO_DIR = "/workspace/helm"


class TestFilePathCheck:
    """Verify that all required files were created."""

    def test_multi_metric_scorer_exists(self):
        path = os.path.join(
            REPO_DIR, "src", "helm", "benchmark", "metrics", "multi_metric_scorer.py"
        )
        assert os.path.isfile(path), f"Expected multi_metric_scorer.py at {path}"

    def test_faithfulness_metric_exists(self):
        path = os.path.join(
            REPO_DIR, "src", "helm", "benchmark", "metrics", "faithfulness_metric.py"
        )
        assert os.path.isfile(path), f"Expected faithfulness_metric.py at {path}"

    def test_evaluation_report_exists(self):
        path = os.path.join(
            REPO_DIR, "src", "helm", "benchmark", "metrics", "evaluation_report.py"
        )
        assert os.path.isfile(path), f"Expected evaluation_report.py at {path}"

    def test_test_file_exists(self):
        path = os.path.join(
            REPO_DIR, "src", "helm", "benchmark", "metrics", "test_multi_metric_scorer.py"
        )
        assert os.path.isfile(path), f"Expected test_multi_metric_scorer.py at {path}"


class TestSemanticMultiMetricScorer:
    """Verify the MultiMetricScorer class structure."""

    def _read_scorer(self):
        path = os.path.join(
            REPO_DIR, "src", "helm", "benchmark", "metrics", "multi_metric_scorer.py"
        )
        with open(path, "r") as f:
            return f.read()

    def test_multi_metric_scorer_class(self):
        content = self._read_scorer()
        assert re.search(r"class\s+MultiMetricScorer", content), (
            "Expected MultiMetricScorer class"
        )

    def test_metric_result_class(self):
        content = self._read_scorer()
        assert re.search(r"class\s+MetricResult|MetricResult", content), (
            "Expected MetricResult class with score/explanation/metadata"
        )

    def test_sample_result_class(self):
        content = self._read_scorer()
        assert re.search(r"class\s+SampleResult|SampleResult", content), (
            "Expected SampleResult class"
        )

    def test_aggregate_modes(self):
        """Should support mean, weighted mean, and minimum aggregation."""
        content = self._read_scorer()
        assert re.search(r"mean|weighted|minimum|min", content, re.IGNORECASE), (
            "Expected aggregate score modes (mean, weighted mean, minimum)"
        )

    def test_weight_support(self):
        content = self._read_scorer()
        assert re.search(r"weight", content), (
            "Expected weight parameter for metrics"
        )


class TestSemanticBuiltInMetrics:
    """Verify built-in metric implementations."""

    def _read_scorer(self):
        path = os.path.join(
            REPO_DIR, "src", "helm", "benchmark", "metrics", "multi_metric_scorer.py"
        )
        with open(path, "r") as f:
            return f.read()

    def test_exact_match_metric(self):
        content = self._read_scorer()
        assert re.search(r"class\s+ExactMatchMetric|ExactMatch", content), (
            "Expected ExactMatchMetric class"
        )

    def test_contains_metric(self):
        content = self._read_scorer()
        assert re.search(r"class\s+ContainsMetric|Contains", content), (
            "Expected ContainsMetric class"
        )

    def test_rouge_metric(self):
        content = self._read_scorer()
        assert re.search(r"class\s+RougeMetric|Rouge|ROUGE|rouge_l", content, re.IGNORECASE), (
            "Expected RougeMetric class (ROUGE-L)"
        )

    def test_length_penalty_metric(self):
        content = self._read_scorer()
        assert re.search(r"class\s+LengthPenaltyMetric|LengthPenalty", content), (
            "Expected LengthPenaltyMetric class"
        )

    def test_case_sensitive_parameter(self):
        content = self._read_scorer()
        assert re.search(r"case_sensitive|case.insensitive", content, re.IGNORECASE), (
            "Expected case_sensitive parameter in ContainsMetric"
        )


class TestSemanticFaithfulnessMetric:
    """Verify faithfulness metric implementation."""

    def _read_faithfulness(self):
        path = os.path.join(
            REPO_DIR, "src", "helm", "benchmark", "metrics", "faithfulness_metric.py"
        )
        with open(path, "r") as f:
            return f.read()

    def test_faithfulness_class(self):
        content = self._read_faithfulness()
        assert re.search(r"class\s+\w*Faithfulness\w*", content), (
            "Expected FaithfulnessMetric class"
        )

    def test_sentence_splitting(self):
        content = self._read_faithfulness()
        assert re.search(r"split|sentence|\.|\?|!", content), (
            "Expected sentence splitting logic"
        )

    def test_word_overlap_ratio(self):
        """Support ratio >= 0.5 threshold for sentence support."""
        content = self._read_faithfulness()
        assert re.search(r"overlap|intersection|0\.5|ratio", content, re.IGNORECASE), (
            "Expected word overlap ratio computation (>= 0.5 threshold)"
        )

    def test_per_sentence_details(self):
        content = self._read_faithfulness()
        assert re.search(r"supported|per.sentence|metadata|details", content, re.IGNORECASE), (
            "Expected per-sentence support details in metadata"
        )


class TestSemanticLLMJudge:
    """Verify LLM-as-judge metric."""

    def _read_scorer(self):
        path = os.path.join(
            REPO_DIR, "src", "helm", "benchmark", "metrics", "multi_metric_scorer.py"
        )
        with open(path, "r") as f:
            return f.read()

    def test_llm_judge_class(self):
        content = self._read_scorer()
        assert re.search(r"class\s+LLMJudgeMetric|LLMJudge", content), (
            "Expected LLMJudgeMetric class"
        )

    def test_judge_function_injection(self):
        content = self._read_scorer()
        assert re.search(r"judge_function|judge_fn|scorer", content), (
            "Expected injectable judge_function parameter"
        )

    def test_exception_handling(self):
        content = self._read_scorer()
        assert re.search(r"except|Exception|0\.0.*error|error.*0\.0", content), (
            "Expected exception handling returning score 0.0"
        )


class TestSemanticEvaluationReport:
    """Verify evaluation report generation."""

    def _read_report(self):
        path = os.path.join(
            REPO_DIR, "src", "helm", "benchmark", "metrics", "evaluation_report.py"
        )
        with open(path, "r") as f:
            return f.read()

    def test_evaluation_report_class(self):
        content = self._read_report()
        assert re.search(r"class\s+EvaluationReport", content), (
            "Expected EvaluationReport class"
        )

    def test_add_sample_method(self):
        content = self._read_report()
        assert re.search(r"def\s+add_sample", content), (
            "Expected add_sample method"
        )

    def test_summary_method(self):
        content = self._read_report()
        assert re.search(r"def\s+summary", content), (
            "Expected summary method"
        )

    def test_report_summary_class(self):
        content = self._read_report()
        assert re.search(r"ReportSummary|class\s+\w*Summary", content), (
            "Expected ReportSummary class"
        )

    def test_to_json_method(self):
        content = self._read_report()
        assert re.search(r"def\s+to_json", content), (
            "Expected to_json export method"
        )

    def test_to_csv_method(self):
        content = self._read_report()
        assert re.search(r"def\s+to_csv", content), (
            "Expected to_csv export method"
        )

    def test_percentile_statistics(self):
        content = self._read_report()
        assert re.search(r"p25|p50|p75|percentile|median|std", content, re.IGNORECASE), (
            "Expected percentile statistics in report summary"
        )


class TestFunctionalPythonSyntax:
    """Validate Python syntax of all created files."""

    def _check_syntax(self, filepath):
        with open(filepath, "r") as f:
            source = f.read()
        ast.parse(source)

    def test_scorer_syntax(self):
        self._check_syntax(
            os.path.join(REPO_DIR, "src", "helm", "benchmark", "metrics", "multi_metric_scorer.py")
        )

    def test_faithfulness_syntax(self):
        self._check_syntax(
            os.path.join(REPO_DIR, "src", "helm", "benchmark", "metrics", "faithfulness_metric.py")
        )

    def test_report_syntax(self):
        self._check_syntax(
            os.path.join(REPO_DIR, "src", "helm", "benchmark", "metrics", "evaluation_report.py")
        )

    def test_test_file_syntax(self):
        self._check_syntax(
            os.path.join(
                REPO_DIR, "src", "helm", "benchmark", "metrics", "test_multi_metric_scorer.py"
            )
        )


class TestFunctionalAgentTests:
    """Verify the agent's own tests."""

    def test_sufficient_test_count(self):
        path = os.path.join(
            REPO_DIR, "src", "helm", "benchmark", "metrics", "test_multi_metric_scorer.py"
        )
        with open(path, "r") as f:
            content = f.read()
        test_count = len(re.findall(r"def\s+test_", content))
        assert test_count >= 5, (
            f"Expected at least 5 test functions, found {test_count}"
        )

    def test_agent_tests_pass(self):
        result = subprocess.run(
            [sys.executable, "-m", "pytest",
             "src/helm/benchmark/metrics/test_multi_metric_scorer.py",
             "-v", "--tb=short"],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, (
            f"Agent's evaluation tests failed:\n{result.stdout[-1000:]}\n{result.stderr[-500:]}"
        )
