"""
Test skill: llm-evaluation
Verify that the Agent builds an LLM chatbot evaluation framework with
automated metrics (BLEU, BERTScore), LLM-as-judge, pairwise comparison,
safety checks, and structured report generation.
"""

import os
import re
import ast
import json
import subprocess
import pytest


class TestLlmEvaluation:
    REPO_DIR = "/workspace/helm"

    # === File Path Checks ===

    def test_metrics_file_exists(self):
        path = os.path.join(self.REPO_DIR, "src/evaluation/metrics.py")
        assert os.path.exists(path), f"metrics.py not found"

    def test_llm_judge_file_exists(self):
        path = os.path.join(self.REPO_DIR, "src/evaluation/llm_judge.py")
        assert os.path.exists(path), f"llm_judge.py not found"

    def test_suite_file_exists(self):
        path = os.path.join(self.REPO_DIR, "src/evaluation/suite.py")
        assert os.path.exists(path), f"suite.py not found"

    def test_report_file_exists(self):
        path = os.path.join(self.REPO_DIR, "src/evaluation/report.py")
        assert os.path.exists(path), f"report.py not found"

    def test_test_cases_file_exists(self):
        path = os.path.join(self.REPO_DIR, "data/test_cases.jsonl")
        assert os.path.exists(path), f"test_cases.jsonl not found"

    # === Semantic Checks ===

    def test_test_cases_has_20_entries(self):
        """Verify test_cases.jsonl has at least 20 entries"""
        path = os.path.join(self.REPO_DIR, "data/test_cases.jsonl")
        with open(path, "r") as f:
            lines = [l.strip() for l in f if l.strip()]
        examples = []
        for line in lines:
            try:
                examples.append(json.loads(line))
            except json.JSONDecodeError:
                pass
        assert len(examples) >= 20, (
            f"Expected 20 test cases, found {len(examples)}"
        )

    def test_test_cases_cover_all_categories(self):
        """Verify test cases cover all 5 categories"""
        path = os.path.join(self.REPO_DIR, "data/test_cases.jsonl")
        with open(path, "r") as f:
            lines = [l.strip() for l in f if l.strip()]
        categories = set()
        for line in lines:
            try:
                obj = json.loads(line)
                categories.add(obj.get("category", ""))
            except json.JSONDecodeError:
                pass
        expected = {"factual", "troubleshooting", "policy", "out_of_scope", "adversarial"}
        missing = expected - categories
        assert not missing, f"Missing categories: {missing}. Found: {categories}"

    def test_metrics_has_all_methods(self):
        """Verify MetricsCalculator has BLEU, BERTScore, exact_match, keyword_recall"""
        path = os.path.join(self.REPO_DIR, "src/evaluation/metrics.py")
        with open(path, "r") as f:
            content = f.read()

        assert "MetricsCalculator" in content, "Must define MetricsCalculator"
        for method in ["bleu", "bertscore", "exact_match", "keyword_recall", "compute_all"]:
            assert re.search(rf"def\s+{method}", content), f"Missing {method} method"

    def test_llm_judge_has_pointwise_and_pairwise(self):
        """Verify LLMJudge has pointwise, pairwise, and safety checking"""
        path = os.path.join(self.REPO_DIR, "src/evaluation/llm_judge.py")
        with open(path, "r") as f:
            content = f.read()

        assert "LLMJudge" in content, "Must define LLMJudge class"
        assert re.search(r"def\s+score_pointwise", content), "Missing score_pointwise"
        assert re.search(r"def\s+compare_pairwise", content), "Missing compare_pairwise"
        assert re.search(r"def\s+check_safety", content), "Missing check_safety"

    def test_pairwise_randomizes_order(self):
        """Verify pairwise comparison randomizes order to avoid position bias"""
        path = os.path.join(self.REPO_DIR, "src/evaluation/llm_judge.py")
        with open(path, "r") as f:
            content = f.read()

        has_randomize = (
            "random" in content
            or "shuffle" in content
            or "position" in content.lower()
            or "order" in content
        )
        assert has_randomize, (
            "Pairwise comparison should randomize order to avoid position bias"
        )

    def test_judge_scores_five_criteria(self):
        """Verify LLM judge uses 5 criteria: accuracy, groundedness, relevance, completeness, safety"""
        path = os.path.join(self.REPO_DIR, "src/evaluation/llm_judge.py")
        with open(path, "r") as f:
            content = f.read()

        criteria = ["accuracy", "groundedness", "relevance", "completeness", "safety"]
        found = [c for c in criteria if c in content]
        assert len(found) >= 4, (
            f"Judge should score on 5 criteria. Found: {found}"
        )

    def test_suite_has_evaluate_and_compare(self):
        """Verify EvaluationSuite has evaluate and compare methods"""
        path = os.path.join(self.REPO_DIR, "src/evaluation/suite.py")
        with open(path, "r") as f:
            content = f.read()

        assert "EvaluationSuite" in content, "Must define EvaluationSuite class"
        assert re.search(r"def\s+evaluate", content), "Missing evaluate method"
        assert re.search(r"def\s+compare", content), "Missing compare method"

    def test_report_generates_markdown(self):
        """Verify ReportGenerator produces Markdown output"""
        path = os.path.join(self.REPO_DIR, "src/evaluation/report.py")
        with open(path, "r") as f:
            content = f.read()

        assert "ReportGenerator" in content, "Must define ReportGenerator"
        assert re.search(r"def\s+to_markdown", content), "Missing to_markdown"
        assert re.search(r"def\s+to_json", content), "Missing to_json"

    def test_safety_detects_injection_attacks(self):
        """Verify safety check detects instruction following attacks"""
        path = os.path.join(self.REPO_DIR, "src/evaluation/llm_judge.py")
        with open(path, "r") as f:
            content = f.read()

        content_lower = content.lower()
        assert (
            "instruction" in content_lower
            or "injection" in content_lower
            or "pii" in content_lower
            or "harmful" in content_lower
        ), "Safety check should detect instruction following attacks and PII"

    # === Functional Checks ===

    def test_all_python_files_parse(self):
        """Verify all Python files parse without syntax errors"""
        files = [
            "src/evaluation/__init__.py",
            "src/evaluation/metrics.py",
            "src/evaluation/llm_judge.py",
            "src/evaluation/suite.py",
            "src/evaluation/report.py",
            "src/evaluation/test_cases.py",
        ]
        for filename in files:
            path = os.path.join(self.REPO_DIR, filename)
            with open(path, "r") as f:
                source = f.read()
            try:
                ast.parse(source)
            except SyntaxError as e:
                pytest.fail(f"{filename} has syntax error: {e}")

    def test_test_cases_is_valid_jsonl(self):
        """Verify all test case lines are valid JSON"""
        path = os.path.join(self.REPO_DIR, "data/test_cases.jsonl")
        with open(path, "r") as f:
            lines = [l.strip() for l in f if l.strip()]
        for i, line in enumerate(lines):
            try:
                json.loads(line)
            except json.JSONDecodeError as e:
                pytest.fail(f"Line {i+1} is invalid JSON: {e}")

    def test_init_exports_main_classes(self):
        """Verify __init__.py exports main classes"""
        path = os.path.join(self.REPO_DIR, "src/evaluation/__init__.py")
        with open(path, "r") as f:
            content = f.read()

        for cls in ["EvaluationSuite", "LLMJudge", "MetricsCalculator", "ReportGenerator"]:
            assert cls in content, f"__init__.py should export {cls}"
