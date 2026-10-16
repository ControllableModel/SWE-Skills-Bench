"""
Test skill: llm-evaluation
Verify that the Agent adds BERTScore, Semantic Similarity, and Answer Relevance
metrics to the HELM evaluation framework — metric classes, registration, and
test coverage.
"""

import os
import re
import ast
import subprocess
import pytest


class TestLlmEvaluation:
    REPO_DIR = "/workspace/helm"
    METRICS = "src/helm/benchmark/metrics"

    # ────────────────── helpers ──────────────────

    def _read(self, rel_path):
        fpath = os.path.join(self.REPO_DIR, rel_path)
        with open(fpath, "r") as f:
            return f.read()

    def _exists(self, rel_path):
        return os.path.isfile(os.path.join(self.REPO_DIR, rel_path))

    def _parse(self, rel_path):
        fpath = os.path.join(self.REPO_DIR, rel_path)
        with open(fpath, "r") as f:
            return ast.parse(f.read())

    # === File Path Checks ===

    def test_bertscore_metric_exists(self):
        """bertscore_metric.py must exist"""
        assert self._exists(f"{self.METRICS}/bertscore_metric.py")

    def test_semantic_similarity_metric_exists(self):
        """semantic_similarity_metric.py must exist"""
        assert self._exists(f"{self.METRICS}/semantic_similarity_metric.py")

    def test_answer_relevance_metric_exists(self):
        """answer_relevance_metric.py must exist"""
        assert self._exists(f"{self.METRICS}/answer_relevance_metric.py")

    def test_bertscore_test_exists(self):
        """test_bertscore_metric.py must exist"""
        assert self._exists("tests/benchmark/metrics/test_bertscore_metric.py")

    def test_semantic_similarity_test_exists(self):
        """test_semantic_similarity_metric.py must exist"""
        assert self._exists("tests/benchmark/metrics/test_semantic_similarity_metric.py")

    def test_answer_relevance_test_exists(self):
        """test_answer_relevance_metric.py must exist"""
        assert self._exists("tests/benchmark/metrics/test_answer_relevance_metric.py")

    # === Semantic Checks — BERTScoreMetric ===

    def test_bertscore_class_defined(self):
        """BERTScoreMetric class must be defined"""
        src = self._read(f"{self.METRICS}/bertscore_metric.py")
        assert re.search(r'class\s+BERTScoreMetric\b', src), (
            "BERTScoreMetric class not found"
        )

    def test_bertscore_evaluate_method(self):
        """BERTScoreMetric must have evaluate() method"""
        src = self._read(f"{self.METRICS}/bertscore_metric.py")
        assert re.search(r'def\s+evaluate\s*\(\s*self', src), (
            "evaluate() method not found in BERTScoreMetric"
        )

    def test_bertscore_returns_three_stats(self):
        """BERTScore must return precision, recall, and F1 stats"""
        src = self._read(f"{self.METRICS}/bertscore_metric.py")
        for stat in ["precision", "recall", "f1"]:
            assert stat in src, f"BERTScore missing {stat} stat"

    def test_bertscore_batch_size_param(self):
        """BERTScoreMetric must support batch_size parameter"""
        src = self._read(f"{self.METRICS}/bertscore_metric.py")
        assert "batch_size" in src, "batch_size parameter not found"

    def test_bertscore_idf_option(self):
        """BERTScoreMetric should support use_idf option"""
        src = self._read(f"{self.METRICS}/bertscore_metric.py")
        assert "idf" in src.lower(), "IDF weighting option not found"

    # === Semantic Checks — SemanticSimilarityMetric ===

    def test_semantic_similarity_class_defined(self):
        """SemanticSimilarityMetric class must be defined"""
        src = self._read(f"{self.METRICS}/semantic_similarity_metric.py")
        assert re.search(r'class\s+SemanticSimilarityMetric\b', src), (
            "SemanticSimilarityMetric class not found"
        )

    def test_semantic_similarity_cosine(self):
        """Must compute cosine similarity between embeddings"""
        src = self._read(f"{self.METRICS}/semantic_similarity_metric.py")
        assert "cosine" in src.lower(), (
            "Cosine similarity computation not found"
        )

    def test_semantic_similarity_sentence_transformer(self):
        """Must reference sentence-transformers model"""
        src = self._read(f"{self.METRICS}/semantic_similarity_metric.py")
        assert "sentence" in src.lower() or "MiniLM" in src, (
            "Sentence transformer model not referenced"
        )

    # === Semantic Checks — AnswerRelevanceMetric ===

    def test_answer_relevance_class_defined(self):
        """AnswerRelevanceMetric class must be defined"""
        src = self._read(f"{self.METRICS}/answer_relevance_metric.py")
        assert re.search(r'class\s+AnswerRelevanceMetric\b', src), (
            "AnswerRelevanceMetric class not found"
        )

    def test_answer_relevance_judge_prompt(self):
        """Must construct a judge prompt with rating criteria"""
        src = self._read(f"{self.METRICS}/answer_relevance_metric.py")
        assert "1" in src and "5" in src and ("rating" in src.lower() or "score" in src.lower()), (
            "Judge prompt with 1-5 rating criteria not found"
        )

    def test_answer_relevance_parses_rating(self):
        """Must parse numeric rating from LLM response"""
        src = self._read(f"{self.METRICS}/answer_relevance_metric.py")
        # Should have digit extraction logic
        assert re.search(r'int\(|digit|re\.|findall|search', src), (
            "Numeric rating parsing logic not found"
        )

    # === Semantic Checks — Metric Registration ===

    def test_metric_names_registered(self):
        """New metric names must be registered in metric_name.py"""
        src = self._read(f"{self.METRICS}/metric_name.py")
        for name in ["bertscore", "semantic_similarity", "answer_relevance"]:
            assert name in src, f"Metric name '{name}' not registered"

    # === Semantic Checks — __init__.py exports ===

    def test_init_exports_new_metrics(self):
        """__init__.py must export new metric classes"""
        src = self._read(f"{self.METRICS}/__init__.py")
        assert "BERTScoreMetric" in src, "BERTScoreMetric not exported"

    # === Functional Checks ===

    def test_bertscore_importable(self):
        """BERTScoreMetric must be importable"""
        result = subprocess.run(
            ["python", "-c",
             "from helm.benchmark.metrics.bertscore_metric import BERTScoreMetric; "
             "print('OK')"],
            capture_output=True, text=True, cwd=self.REPO_DIR, timeout=30,
        )
        assert "OK" in result.stdout, (
            f"Import failed:\n{result.stdout}\n{result.stderr}"
        )

    def test_semantic_similarity_importable(self):
        """SemanticSimilarityMetric must be importable"""
        result = subprocess.run(
            ["python", "-c",
             "from helm.benchmark.metrics.semantic_similarity_metric import "
             "SemanticSimilarityMetric; print('OK')"],
            capture_output=True, text=True, cwd=self.REPO_DIR, timeout=30,
        )
        assert "OK" in result.stdout, (
            f"Import failed:\n{result.stdout}\n{result.stderr}"
        )

    def test_answer_relevance_importable(self):
        """AnswerRelevanceMetric must be importable"""
        result = subprocess.run(
            ["python", "-c",
             "from helm.benchmark.metrics.answer_relevance_metric import "
             "AnswerRelevanceMetric; print('OK')"],
            capture_output=True, text=True, cwd=self.REPO_DIR, timeout=30,
        )
        assert "OK" in result.stdout, (
            f"Import failed:\n{result.stdout}\n{result.stderr}"
        )

    def test_bertscore_tests_pass(self):
        """BERTScore unit tests must pass"""
        result = subprocess.run(
            ["python", "-m", "pytest",
             "tests/benchmark/metrics/test_bertscore_metric.py",
             "-v", "--tb=short"],
            capture_output=True, text=True, cwd=self.REPO_DIR, timeout=120,
        )
        assert result.returncode == 0, (
            f"Tests failed:\n{result.stdout}\n{result.stderr}"
        )
