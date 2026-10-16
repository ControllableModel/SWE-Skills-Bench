"""
Test skill: prompt-engineering-patterns
Verify that the Agent correctly implements few-shot, chain-of-thought,
and system prompt template patterns for LangChain.
"""

import os
import re
import ast
import subprocess
import pytest


class TestPromptEngineeringPatterns:
    REPO_DIR = "/workspace/langchain"

    # === File Path Checks ===

    def test_advanced_templates_exists(self):
        """Verify advanced_templates.py was created"""
        path = os.path.join(
            self.REPO_DIR,
            "libs/langchain/langchain/prompts/advanced_templates.py",
        )
        assert os.path.exists(path), f"advanced_templates.py not found at {path}"

    def test_example_selector_exists(self):
        """Verify example_selector.py was created"""
        path = os.path.join(
            self.REPO_DIR,
            "libs/langchain/langchain/prompts/example_selector.py",
        )
        assert os.path.exists(path), f"example_selector.py not found at {path}"

    def test_test_file_exists(self):
        """Verify test file was created"""
        path = os.path.join(
            self.REPO_DIR,
            "libs/core/tests/unit_tests/prompts/test_advanced_templates.py",
        )
        assert os.path.exists(path), f"test_advanced_templates.py not found at {path}"

    # === Semantic Checks: FewShotPromptTemplate ===

    def test_few_shot_template_class_defined(self):
        """Verify FewShotPromptTemplate class is defined"""
        path = os.path.join(
            self.REPO_DIR,
            "libs/langchain/langchain/prompts/advanced_templates.py",
        )
        with open(path) as f:
            content = f.read()
        assert "class FewShotPromptTemplate" in content, (
            "FewShotPromptTemplate class should be defined"
        )

    def test_few_shot_has_format_method(self):
        """Verify FewShotPromptTemplate has format method"""
        path = os.path.join(
            self.REPO_DIR,
            "libs/langchain/langchain/prompts/advanced_templates.py",
        )
        with open(path) as f:
            content = f.read()
        assert "def format(" in content, (
            "FewShotPromptTemplate should have format method"
        )

    def test_few_shot_has_max_examples(self):
        """Verify FewShotPromptTemplate respects max_examples"""
        path = os.path.join(
            self.REPO_DIR,
            "libs/langchain/langchain/prompts/advanced_templates.py",
        )
        with open(path) as f:
            content = f.read()
        assert "max_examples" in content, (
            "FewShotPromptTemplate should have max_examples parameter"
        )

    def test_few_shot_has_example_separator(self):
        """Verify FewShotPromptTemplate has example_separator"""
        path = os.path.join(
            self.REPO_DIR,
            "libs/langchain/langchain/prompts/advanced_templates.py",
        )
        with open(path) as f:
            content = f.read()
        assert "example_separator" in content, (
            "FewShotPromptTemplate should have example_separator"
        )

    def test_few_shot_raises_key_error_on_missing_kwargs(self):
        """Verify missing template variables raise KeyError"""
        path = os.path.join(
            self.REPO_DIR,
            "libs/langchain/langchain/prompts/advanced_templates.py",
        )
        with open(path) as f:
            content = f.read()
        assert "KeyError" in content, (
            "Should raise KeyError for missing template variables"
        )

    # === Semantic Checks: Example Selectors ===

    def test_semantic_similarity_selector_defined(self):
        """Verify SemanticSimilaritySelector class is defined"""
        path = os.path.join(
            self.REPO_DIR,
            "libs/langchain/langchain/prompts/example_selector.py",
        )
        with open(path) as f:
            content = f.read()
        assert "class SemanticSimilaritySelector" in content, (
            "SemanticSimilaritySelector class should be defined"
        )

    def test_diversity_selector_defined(self):
        """Verify DiversitySelector class is defined"""
        path = os.path.join(
            self.REPO_DIR,
            "libs/langchain/langchain/prompts/example_selector.py",
        )
        with open(path) as f:
            content = f.read()
        assert "class DiversitySelector" in content, (
            "DiversitySelector class should be defined"
        )

    def test_selectors_have_select_method(self):
        """Verify both selectors have select method"""
        path = os.path.join(
            self.REPO_DIR,
            "libs/langchain/langchain/prompts/example_selector.py",
        )
        with open(path) as f:
            content = f.read()
        assert "def select(" in content, (
            "Selectors should have select method"
        )

    def test_cosine_similarity_used(self):
        """Verify cosine similarity is computed for semantic selection"""
        path = os.path.join(
            self.REPO_DIR,
            "libs/langchain/langchain/prompts/example_selector.py",
        )
        with open(path) as f:
            content = f.read()
        assert "cosine" in content.lower() or "dot" in content.lower(), (
            "Should compute cosine similarity for example selection"
        )

    def test_diversity_selector_has_lambda(self):
        """Verify DiversitySelector uses lambda_param for MMR"""
        path = os.path.join(
            self.REPO_DIR,
            "libs/langchain/langchain/prompts/example_selector.py",
        )
        with open(path) as f:
            content = f.read()
        assert "lambda" in content, (
            "DiversitySelector should use lambda_param for MMR"
        )

    # === Semantic Checks: ChainOfThoughtTemplate ===

    def test_cot_template_class_defined(self):
        """Verify ChainOfThoughtTemplate class is defined"""
        path = os.path.join(
            self.REPO_DIR,
            "libs/langchain/langchain/prompts/advanced_templates.py",
        )
        with open(path) as f:
            content = f.read()
        assert "class ChainOfThoughtTemplate" in content, (
            "ChainOfThoughtTemplate class should be defined"
        )

    def test_cot_has_reasoning_prefix(self):
        """Verify ChainOfThoughtTemplate has reasoning_prefix"""
        path = os.path.join(
            self.REPO_DIR,
            "libs/langchain/langchain/prompts/advanced_templates.py",
        )
        with open(path) as f:
            content = f.read()
        assert "reasoning_prefix" in content, (
            "Should have reasoning_prefix parameter"
        )
        assert "step by step" in content.lower(), (
            "Default reasoning_prefix should include 'step by step'"
        )

    def test_cot_has_answer_prefix(self):
        """Verify ChainOfThoughtTemplate has answer_prefix"""
        path = os.path.join(
            self.REPO_DIR,
            "libs/langchain/langchain/prompts/advanced_templates.py",
        )
        with open(path) as f:
            content = f.read()
        assert "answer_prefix" in content, "Should have answer_prefix parameter"

    # === Semantic Checks: SystemPromptComposer ===

    def test_system_prompt_composer_defined(self):
        """Verify SystemPromptComposer class is defined"""
        path = os.path.join(
            self.REPO_DIR,
            "libs/langchain/langchain/prompts/advanced_templates.py",
        )
        with open(path) as f:
            content = f.read()
        assert "class SystemPromptComposer" in content, (
            "SystemPromptComposer class should be defined"
        )

    def test_composer_has_compose_method(self):
        """Verify SystemPromptComposer has compose method"""
        path = os.path.join(
            self.REPO_DIR,
            "libs/langchain/langchain/prompts/advanced_templates.py",
        )
        with open(path) as f:
            content = f.read()
        assert "def compose(" in content, (
            "SystemPromptComposer should have compose method"
        )

    def test_composer_has_constraints_section(self):
        """Verify compose outputs Constraints section"""
        path = os.path.join(
            self.REPO_DIR,
            "libs/langchain/langchain/prompts/advanced_templates.py",
        )
        with open(path) as f:
            content = f.read()
        assert "Constraints" in content, (
            "compose should output a 'Constraints:' section"
        )

    # === Functional Checks ===

    def test_advanced_templates_parses(self):
        """Verify advanced_templates.py has valid Python syntax"""
        path = os.path.join(
            self.REPO_DIR,
            "libs/langchain/langchain/prompts/advanced_templates.py",
        )
        with open(path) as f:
            source = f.read()
        try:
            ast.parse(source)
        except SyntaxError as e:
            pytest.fail(f"advanced_templates.py has syntax error: {e}")

    def test_example_selector_parses(self):
        """Verify example_selector.py has valid Python syntax"""
        path = os.path.join(
            self.REPO_DIR,
            "libs/langchain/langchain/prompts/example_selector.py",
        )
        with open(path) as f:
            source = f.read()
        try:
            ast.parse(source)
        except SyntaxError as e:
            pytest.fail(f"example_selector.py has syntax error: {e}")

    def test_unit_tests_pass(self):
        """Verify unit tests pass"""
        result = subprocess.run(
            [
                "python", "-m", "pytest",
                "libs/core/tests/unit_tests/prompts/test_advanced_templates.py",
                "-v", "--tb=short",
            ],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, (
            f"Unit tests failed:\n{result.stdout}\n{result.stderr}"
        )
