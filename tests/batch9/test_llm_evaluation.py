"""
Test skill: llm-evaluation
Verify that the Agent creates an evaluation framework for HELM with text metrics (BLEU, ROUGE),
classification metrics, retrieval metrics (MRR, NDCG), and LLM-as-judge.
"""

import os
import subprocess
import ast
import re
import pytest


class TestLlmEvaluation:
    REPO_DIR = "/workspace/helm"

    # === File Path Checks ===

    def test_evaluation_files_exist(self):
        """Verify evaluation metric files exist"""
        found = False
        for root, dirs, files in os.walk(self.REPO_DIR):
            if ".git" in root:
                continue
            for f in files:
                if f.endswith(".py") and ("metric" in f.lower() or "eval" in f.lower()):
                    fpath = os.path.join(root, f)
                    with open(fpath) as fh:
                        content = fh.read()
                    if "BLEU" in content or "ROUGE" in content or "MRR" in content:
                        found = True
                        break
            if found:
                break
        assert found, "Evaluation metric files not found"

    # === Semantic Checks ===

    def test_bleu_metric_defined(self):
        """Verify BLEU metric is implemented"""
        content = self._find_content()
        has_bleu = "BLEU" in content or "bleu" in content.lower()
        assert has_bleu, "BLEU metric not found"

    def test_rouge_metric_defined(self):
        """Verify ROUGE metric is implemented"""
        content = self._find_content()
        has_rouge = "ROUGE" in content or "rouge" in content.lower()
        assert has_rouge, "ROUGE metric not found"

    def test_classification_metrics_defined(self):
        """Verify classification metrics (accuracy, F1, precision, recall) exist"""
        content = self._find_content()
        content_lower = content.lower()
        class_metrics = ["accuracy", "f1", "precision", "recall"]
        found = [m for m in class_metrics if m in content_lower]
        assert len(found) >= 2, (
            f"Expected classification metrics, found: {found}"
        )

    def test_mrr_metric_defined(self):
        """Verify MRR (Mean Reciprocal Rank) is implemented"""
        content = self._find_content()
        has_mrr = "MRR" in content or "mean_reciprocal" in content.lower() or "reciprocal_rank" in content.lower()
        assert has_mrr, "MRR metric not found"

    def test_ndcg_metric_defined(self):
        """Verify NDCG is implemented"""
        content = self._find_content()
        has_ndcg = "NDCG" in content or "ndcg" in content.lower() or "normalized_discounted" in content.lower()
        assert has_ndcg, "NDCG metric not found"

    def test_llm_as_judge_defined(self):
        """Verify LLM-as-judge evaluator is implemented"""
        content = self._find_content()
        content_lower = content.lower()
        has_judge = "judge" in content_lower or "llm_eval" in content_lower or "gpt" in content_lower
        assert has_judge, "LLM-as-judge not found"

    # === Functional Checks ===

    def test_metric_files_parse(self):
        """Verify all metric files have valid Python syntax"""
        for root, dirs, files in os.walk(self.REPO_DIR):
            if ".git" in root:
                continue
            for f in files:
                if f.endswith(".py") and ("metric" in f.lower() or "eval" in f.lower()):
                    fpath = os.path.join(root, f)
                    with open(fpath) as fh:
                        source = fh.read()
                    if "BLEU" in source or "ROUGE" in source or "MRR" in source:
                        try:
                            ast.parse(source)
                        except SyntaxError as e:
                            pytest.fail(f"Syntax error in {fpath}: {e}")

    def test_metrics_have_compute_method(self):
        """Verify metric classes define a compute/evaluate method"""
        content = self._find_content()
        has_compute = (
            "def compute" in content
            or "def evaluate" in content
            or "def score" in content
            or "def calculate" in content
        )
        assert has_compute, "Metric classes missing compute/evaluate method"

    def test_metrics_return_numeric_scores(self):
        """Verify metrics return float/numeric scores"""
        content = self._find_content()
        has_return = (
            "float" in content
            or "-> float" in content
            or "return" in content
        )
        assert has_return, "Metrics don't appear to return numeric scores"

    def test_evaluation_module_importable(self):
        """Verify evaluation module can be parsed"""
        eval_file = None
        for root, dirs, files in os.walk(self.REPO_DIR):
            if ".git" in root:
                continue
            for f in files:
                if f.endswith(".py") and ("metric" in f.lower() or "eval" in f.lower()):
                    fpath = os.path.join(root, f)
                    with open(fpath) as fh:
                        content = fh.read()
                    if "BLEU" in content or "ROUGE" in content:
                        eval_file = fpath
                        break
            if eval_file:
                break
        if eval_file is None:
            pytest.skip("Eval module not found")
        result = subprocess.run(
            ["python", "-c", f"import ast; ast.parse(open('{eval_file}').read()); print('OK')"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, f"Parse failed: {result.stderr}"

    def _find_content(self):
        """Helper to find evaluation content"""
        all_content = ""
        for root, dirs, files in os.walk(self.REPO_DIR):
            if ".git" in root:
                continue
            for f in files:
                if f.endswith(".py") and ("metric" in f.lower() or "eval" in f.lower() or "judge" in f.lower()):
                    fpath = os.path.join(root, f)
                    try:
                        with open(fpath) as fh:
                            all_content += fh.read() + "\n"
                    except (UnicodeDecodeError, PermissionError):
                        continue
        return all_content
