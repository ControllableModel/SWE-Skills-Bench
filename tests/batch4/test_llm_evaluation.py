"""
Tests for skill: llm-evaluation
Repo: stanford-crfm/helm
Image: zhangyiiiiii/swe-skills-bench-python
Task: Build an LLM evaluation framework with automated metrics,
      LLM-as-Judge scoring, and statistical comparison reporting.
"""

import ast
import os
import re
import subprocess

import pytest

REPO_DIR = "/workspace/helm"
EVAL_DIR = os.path.join(REPO_DIR, "src", "helm", "benchmark", "evaluation")

SUITE_FILE = os.path.join(EVAL_DIR, "eval_suite.py")
METRICS_FILE = os.path.join(EVAL_DIR, "metrics.py")
JUDGE_FILE = os.path.join(EVAL_DIR, "llm_judge.py")
REPORTER_FILE = os.path.join(EVAL_DIR, "reporter.py")
TEST_FILE = os.path.join(EVAL_DIR, "test_evaluation.py")


# ---------------------------------------------------------------------------
# Layer 1 — file_path_check
# ---------------------------------------------------------------------------

class TestFilePathCheck:
    """Verify all required evaluation files were created."""

    def test_eval_suite_exists(self):
        assert os.path.isfile(SUITE_FILE), f"Expected {SUITE_FILE}"

    def test_metrics_exists(self):
        assert os.path.isfile(METRICS_FILE), f"Expected {METRICS_FILE}"

    def test_llm_judge_exists(self):
        assert os.path.isfile(JUDGE_FILE), f"Expected {JUDGE_FILE}"

    def test_reporter_exists(self):
        assert os.path.isfile(REPORTER_FILE), f"Expected {REPORTER_FILE}"

    def test_test_file_exists(self):
        assert os.path.isfile(TEST_FILE), f"Expected {TEST_FILE}"


# ---------------------------------------------------------------------------
# Layer 2 — semantic_check
# ---------------------------------------------------------------------------

class TestSemanticEvalSuite:
    """Verify EvaluationSuite class."""

    @pytest.fixture(autouse=True)
    def _load_source(self):
        with open(SUITE_FILE, "r", encoding="utf-8") as f:
            self.src = f.read()
        self.tree = ast.parse(self.src)

    def test_class_defined(self):
        classes = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.ClassDef)]
        assert "EvaluationSuite" in classes, (
            f"Expected EvaluationSuite class; found: {classes}"
        )

    def test_evaluate_method(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "evaluate" in funcs, "Expected evaluate() method"

    def test_evaluation_result_class(self):
        """Must define or use EvaluationResult."""
        assert "EvaluationResult" in self.src, "Expected EvaluationResult class"

    def test_handles_prediction_failures(self):
        """Failed predictions must be caught, not crash the suite."""
        has_try = "try" in self.src or "except" in self.src
        assert has_try, "Expected exception handling for prediction failures"

    def test_per_case_and_aggregated(self):
        assert "per_case" in self.src, "Expected per_case results"
        assert "aggregated" in self.src, "Expected aggregated scores"


class TestSemanticMetrics:
    """Verify metric implementations."""

    @pytest.fixture(autouse=True)
    def _load_source(self):
        with open(METRICS_FILE, "r", encoding="utf-8") as f:
            self.src = f.read()
        self.tree = ast.parse(self.src)

    def test_exact_match(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "exact_match" in funcs, "Expected exact_match function"

    def test_f1_score(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "f1_score" in funcs, "Expected f1_score function"

    def test_bleu_score(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "bleu_score" in funcs, "Expected bleu_score function"

    def test_rouge_l(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "rouge_l" in funcs, "Expected rouge_l function"

    def test_contains_match(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "contains_match" in funcs, "Expected contains_match function"

    def test_register_metric(self):
        """Must support custom metric registration."""
        assert "register_metric" in self.src, "Expected register_metric function"


class TestSemanticLLMJudge:
    """Verify LLMJudge class."""

    @pytest.fixture(autouse=True)
    def _load_source(self):
        with open(JUDGE_FILE, "r", encoding="utf-8") as f:
            self.src = f.read()
        self.tree = ast.parse(self.src)

    def test_class_defined(self):
        classes = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.ClassDef)]
        assert "LLMJudge" in classes, f"Expected LLMJudge class; found: {classes}"

    def test_score_pointwise_method(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "score_pointwise" in funcs, "Expected score_pointwise() method"

    def test_compare_pairwise_method(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "compare_pairwise" in funcs, "Expected compare_pairwise() method"

    def test_scoring_rubric(self):
        assert "rubric" in self.src.lower(), "Expected scoring_rubric parameter"

    def test_position_debiasing(self):
        """Pairwise comparison must evaluate both orderings."""
        has_debias = (
            "debias" in self.src.lower()
            or "both order" in self.src.lower()
            or "swap" in self.src.lower()
            or "reverse" in self.src.lower()
            or "position" in self.src.lower()
        )
        assert has_debias, "Expected position debiasing in pairwise comparison"


class TestSemanticReporter:
    """Verify EvaluationReporter class."""

    @pytest.fixture(autouse=True)
    def _load_source(self):
        with open(REPORTER_FILE, "r", encoding="utf-8") as f:
            self.src = f.read()
        self.tree = ast.parse(self.src)

    def test_class_defined(self):
        classes = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.ClassDef)]
        assert "EvaluationReporter" in classes, (
            f"Expected EvaluationReporter class; found: {classes}"
        )

    def test_summary_table_method(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "summary_table" in funcs, "Expected summary_table() method"

    def test_compare_method(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "compare" in funcs, "Expected compare() method"

    def test_best_model_method(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "best_model" in funcs, "Expected best_model() method"

    def test_statistical_significance(self):
        """Compare must include p-value and significance testing."""
        has_stats = (
            "p_value" in self.src
            or "ttest" in self.src
            or "t_test" in self.src
            or "scipy.stats" in self.src
        )
        assert has_stats, "Expected statistical significance testing (t-test)"


# ---------------------------------------------------------------------------
# Layer 3 — functional_check
# ---------------------------------------------------------------------------

class TestFunctionalLLMEvaluation:
    """Functional checks — syntax and basic correctness."""

    def _parse(self, filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            src = f.read()
        try:
            ast.parse(src)
            return True, None
        except SyntaxError as e:
            return False, str(e)

    def test_suite_valid_python(self):
        ok, err = self._parse(SUITE_FILE)
        assert ok, f"eval_suite.py syntax error: {err}"

    def test_metrics_valid_python(self):
        ok, err = self._parse(METRICS_FILE)
        assert ok, f"metrics.py syntax error: {err}"

    def test_judge_valid_python(self):
        ok, err = self._parse(JUDGE_FILE)
        assert ok, f"llm_judge.py syntax error: {err}"

    def test_reporter_valid_python(self):
        ok, err = self._parse(REPORTER_FILE)
        assert ok, f"reporter.py syntax error: {err}"

    def test_test_file_valid_python(self):
        ok, err = self._parse(TEST_FILE)
        assert ok, f"test_evaluation.py syntax error: {err}"

    def test_metrics_importable(self):
        """Metrics must be importable."""
        result = subprocess.run(
            f"python -c \"import sys; sys.path.insert(0, '{EVAL_DIR}'); "
            f"from metrics import exact_match, f1_score; print('OK')\"",
            shell=True, capture_output=True, text=True, timeout=30,
            cwd=REPO_DIR,
        )
        if result.returncode != 0:
            # Fallback to package import
            result2 = subprocess.run(
                f"python -c \"import sys; sys.path.insert(0, '{os.path.dirname(os.path.dirname(os.path.dirname(EVAL_DIR)))}'); "
                f"from helm.benchmark.evaluation.metrics import exact_match; print('OK')\"",
                shell=True, capture_output=True, text=True, timeout=30,
                cwd=REPO_DIR,
            )
            assert "OK" in result.stdout or "OK" in result2.stdout, (
                f"Could not import metrics:\n{result.stderr[:300]}\n{result2.stderr[:300]}"
            )

    def test_exact_match_correctness(self):
        """exact_match('hello', 'hello') must return 1.0."""
        result = subprocess.run(
            f"python -c \""
            f"import sys; sys.path.insert(0, '{EVAL_DIR}'); "
            f"from metrics import exact_match; "
            f"print(exact_match('hello', 'hello'))\"",
            shell=True, capture_output=True, text=True, timeout=30,
            cwd=REPO_DIR,
        )
        if result.returncode == 0:
            val = float(result.stdout.strip())
            assert val == 1.0, f"Expected exact_match('hello','hello')=1.0; got {val}"
        else:
            pytest.skip(f"exact_match not runnable: {result.stderr[:300]}")
