"""
Tests for the prompt-engineering-patterns skill.
Validates a prompt optimization toolkit for LangChain with few-shot selection,
chain-of-thought formatting, and A/B testing of prompt variants.
"""

import os
import re
import ast

REPO_DIR = "/workspace/langchain"
PROMPTS_DIR = os.path.join(REPO_DIR, "libs", "langchain", "langchain", "prompts")


class TestPromptEngineeringPatterns:
    """Tests for the LangChain prompt optimization toolkit."""

    # ── file_path_check ──────────────────────────────────────────────

    def test_optimizer_file_exists(self):
        """PromptOptimizer module must exist."""
        path = os.path.join(PROMPTS_DIR, "optimizer.py")
        assert os.path.isfile(path), f"Missing {path}"

    def test_few_shot_selector_file_exists(self):
        """SemanticFewShotSelector module must exist."""
        path = os.path.join(PROMPTS_DIR, "few_shot_selector.py")
        assert os.path.isfile(path), f"Missing {path}"

    def test_cot_formatter_file_exists(self):
        """ChainOfThoughtFormatter module must exist."""
        path = os.path.join(PROMPTS_DIR, "cot_formatter.py")
        assert os.path.isfile(path), f"Missing {path}"

    def test_ab_test_file_exists(self):
        """PromptABTest module must exist."""
        path = os.path.join(PROMPTS_DIR, "ab_test.py")
        assert os.path.isfile(path), f"Missing {path}"

    # ── semantic_check ───────────────────────────────────────────────

    def _read(self, filename):
        path = os.path.join(PROMPTS_DIR, filename)
        if not os.path.isfile(path):
            return ""
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def test_semantic_few_shot_selector_class(self):
        """SemanticFewShotSelector class must be defined with select and select_diverse."""
        content = self._read("few_shot_selector.py")
        assert re.search(r"class\s+SemanticFewShotSelector", content), (
            "SemanticFewShotSelector class not defined"
        )
        assert re.search(r"def\s+select\b", content), "select method not defined"
        assert re.search(r"def\s+select_diverse\b", content), "select_diverse method not defined"

    def test_cosine_similarity_used(self):
        """Few-shot selector must use cosine similarity for ranking."""
        content = self._read("few_shot_selector.py")
        assert re.search(r"cosine|dot.*norm|similarity", content, re.IGNORECASE), (
            "Cosine similarity not found in few_shot_selector.py"
        )

    def test_mmr_implementation(self):
        """select_diverse must implement Maximal Marginal Relevance."""
        content = self._read("few_shot_selector.py")
        assert re.search(r"lambda_param|marginal.*relevance|mmr|diversity", content, re.IGNORECASE), (
            "MMR/diversity mechanism not found in select_diverse"
        )

    def test_cot_formatter_styles(self):
        """ChainOfThoughtFormatter must support step_by_step, zero_shot, structured styles."""
        content = self._read("cot_formatter.py")
        assert re.search(r"class\s+ChainOfThoughtFormatter", content), (
            "ChainOfThoughtFormatter class not defined"
        )
        for style in ["step_by_step", "zero_shot", "structured"]:
            assert style in content, f"Style '{style}' not found in cot_formatter.py"

    def test_prompt_optimizer_build_prompt(self):
        """PromptOptimizer must define build_prompt method."""
        content = self._read("optimizer.py")
        assert re.search(r"class\s+PromptOptimizer", content), (
            "PromptOptimizer class not defined"
        )
        assert re.search(r"def\s+build_prompt\b", content), "build_prompt method not defined"

    def test_ab_test_class(self):
        """PromptABTest must define run and best_variant methods."""
        content = self._read("ab_test.py")
        assert re.search(r"class\s+PromptABTest", content), "PromptABTest class not defined"
        assert re.search(r"def\s+run\b", content), "run method not defined"
        assert re.search(r"def\s+best_variant\b", content), "best_variant method not defined"

    # ── functional_check ─────────────────────────────────────────────

    def test_all_files_valid_python(self):
        """All toolkit Python files must have valid syntax."""
        errors = []
        for fname in ["optimizer.py", "few_shot_selector.py", "cot_formatter.py", "ab_test.py"]:
            content = self._read(fname)
            if not content:
                continue
            try:
                ast.parse(content)
            except SyntaxError as e:
                errors.append(f"{fname}: {e}")
        assert not errors, "Syntax errors:\n" + "\n".join(errors)

    def test_zero_vector_handling(self):
        """Cosine similarity must handle zero vectors without division by zero."""
        content = self._read("few_shot_selector.py")
        assert re.search(r"norm.*==.*0|norm.*<|zero|0\.0|epsilon|1e-", content, re.IGNORECASE), (
            "Zero vector handling not found in cosine similarity"
        )

    def test_cot_step_by_step_suffix(self):
        """step_by_step style must append the correct suffix."""
        content = self._read("cot_formatter.py")
        assert re.search(r"step by step|Step 1", content), (
            "step_by_step suffix text not found"
        )

    def test_ab_test_runtime_error_if_not_run(self):
        """best_variant must raise RuntimeError if run() not called."""
        content = self._read("ab_test.py")
        assert re.search(r"RuntimeError|has not been called|no results", content, re.IGNORECASE), (
            "RuntimeError for calling best_variant before run() not found"
        )

    def test_test_file_exists(self):
        """Test suite file must exist."""
        path = os.path.join(REPO_DIR, "tests", "test_prompt_engineering_patterns.py")
        assert os.path.isfile(path), f"Missing {path}"

    def test_max_examples_capping(self):
        """Selector must cap results when max_examples exceeds pool size."""
        content = self._read("few_shot_selector.py")
        assert re.search(r"max_examples|max_ex|len\(.*examples\)", content), (
            "max_examples capping logic not found"
        )
