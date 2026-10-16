"""
Tests for skill: prompt-engineering-patterns
Repo: langchain-ai/langchain
Image: zhangyiiiiii/swe-skills-bench-python
Task: Implement a prompt template library with few-shot selection,
      chain-of-thought formatting, and self-consistency verification.
"""

import ast
import os
import re
import subprocess

import pytest

REPO_DIR = "/workspace/langchain"
LIB_DIR = os.path.join(REPO_DIR, "libs", "langchain", "langchain", "prompts")
TEST_DIR = os.path.join(REPO_DIR, "libs", "langchain", "tests", "unit_tests", "prompts")

TEMPLATE_FILE = os.path.join(LIB_DIR, "structured_template.py")
SELECTOR_FILE = os.path.join(LIB_DIR, "few_shot_selector.py")
COT_FILE = os.path.join(LIB_DIR, "chain_of_thought.py")
TEST_TEMPLATE = os.path.join(TEST_DIR, "test_structured_template.py")
TEST_SELECTOR = os.path.join(TEST_DIR, "test_few_shot_selector.py")


# ---------------------------------------------------------------------------
# Layer 1 — file_path_check
# ---------------------------------------------------------------------------

class TestFilePathCheck:
    """Verify all required files were created."""

    def test_structured_template_exists(self):
        assert os.path.isfile(TEMPLATE_FILE), f"Expected {TEMPLATE_FILE}"

    def test_few_shot_selector_exists(self):
        assert os.path.isfile(SELECTOR_FILE), f"Expected {SELECTOR_FILE}"

    def test_chain_of_thought_exists(self):
        assert os.path.isfile(COT_FILE), f"Expected {COT_FILE}"

    def test_template_tests_exist(self):
        assert os.path.isfile(TEST_TEMPLATE), f"Expected {TEST_TEMPLATE}"

    def test_selector_tests_exist(self):
        assert os.path.isfile(TEST_SELECTOR), f"Expected {TEST_SELECTOR}"


# ---------------------------------------------------------------------------
# Layer 2 — semantic_check
# ---------------------------------------------------------------------------

class TestSemanticStructuredTemplate:
    """Verify StructuredPromptTemplate class."""

    @pytest.fixture(autouse=True)
    def _load_source(self):
        with open(TEMPLATE_FILE, "r", encoding="utf-8") as f:
            self.src = f.read()
        self.tree = ast.parse(self.src)

    def test_class_defined(self):
        classes = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.ClassDef)]
        assert "StructuredPromptTemplate" in classes, (
            f"Expected StructuredPromptTemplate class; found: {classes}"
        )

    def test_render_method(self):
        """Must have a render method."""
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "render" in funcs, "Expected render() method"

    def test_validate_method(self):
        """Must have a validate method."""
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "validate" in funcs, "Expected validate() method"

    def test_sections_supported(self):
        """Template must support system, instruction, output_format, examples."""
        for section in ["system", "instruction", "output_format", "examples"]:
            assert section in self.src, (
                f"Expected section '{section}' in StructuredPromptTemplate"
            )

    def test_missing_variable_raises_valueerror(self):
        """Missing variables must raise ValueError."""
        assert "ValueError" in self.src, (
            "Expected ValueError for missing template variables"
        )


class TestSemanticFewShotSelector:
    """Verify FewShotSelector class."""

    @pytest.fixture(autouse=True)
    def _load_source(self):
        with open(SELECTOR_FILE, "r", encoding="utf-8") as f:
            self.src = f.read()
        self.tree = ast.parse(self.src)

    def test_class_defined(self):
        classes = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.ClassDef)]
        assert "FewShotSelector" in classes, (
            f"Expected FewShotSelector class; found: {classes}"
        )

    def test_select_method(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "select" in funcs, "Expected select() method"

    def test_strategies_supported(self):
        """Must support random, similarity, and diverse strategies."""
        for strategy in ["random", "similarity", "diverse"]:
            assert strategy in self.src, (
                f"Expected selection strategy '{strategy}'"
            )

    def test_tfidf_or_similarity_computation(self):
        """Similarity strategy must use TF-IDF or cosine similarity."""
        has_tfidf = (
            "TfidfVectorizer" in self.src
            or "tfidf" in self.src.lower()
            or "cosine_similarity" in self.src
            or "cosine" in self.src
        )
        assert has_tfidf, (
            "Expected TF-IDF or cosine similarity for the similarity strategy"
        )

    def test_max_examples_parameter(self):
        assert "max_examples" in self.src, "Expected max_examples parameter"


class TestSemanticChainOfThought:
    """Verify ChainOfThoughtTemplate class."""

    @pytest.fixture(autouse=True)
    def _load_source(self):
        with open(COT_FILE, "r", encoding="utf-8") as f:
            self.src = f.read()
        self.tree = ast.parse(self.src)

    def test_class_defined(self):
        classes = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.ClassDef)]
        assert "ChainOfThoughtTemplate" in classes, (
            f"Expected ChainOfThoughtTemplate class; found: {classes}"
        )

    def test_extends_structured_template(self):
        """Must extend StructuredPromptTemplate."""
        found = False
        for node in ast.walk(self.tree):
            if isinstance(node, ast.ClassDef) and node.name == "ChainOfThoughtTemplate":
                for base in node.bases:
                    if isinstance(base, ast.Name) and "Structured" in base.id:
                        found = True
                    elif isinstance(base, ast.Attribute) and "Structured" in base.attr:
                        found = True
        # Fallback: check source text
        if not found:
            found = "StructuredPromptTemplate" in self.src
        assert found, "Expected ChainOfThoughtTemplate to extend StructuredPromptTemplate"

    def test_reasoning_steps(self):
        assert "reasoning_steps" in self.src, (
            "Expected reasoning_steps parameter"
        )

    def test_verification_step(self):
        assert "verification" in self.src.lower() or "verify" in self.src.lower(), (
            "Expected add_verification_step option"
        )

    def test_conclusion_prefix(self):
        """Rendered prompt must include 'Therefore' conclusion prefix."""
        assert "Therefore" in self.src or "therefore" in self.src, (
            "Expected 'Therefore, the answer is:' conclusion prefix"
        )


# ---------------------------------------------------------------------------
# Layer 3 — functional_check
# ---------------------------------------------------------------------------

class TestFunctionalPromptEngineering:
    """Functional checks — syntax and import verification."""

    def _parse(self, filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            src = f.read()
        try:
            ast.parse(src)
            return True, None
        except SyntaxError as e:
            return False, str(e)

    def test_template_valid_python(self):
        ok, err = self._parse(TEMPLATE_FILE)
        assert ok, f"structured_template.py syntax error: {err}"

    def test_selector_valid_python(self):
        ok, err = self._parse(SELECTOR_FILE)
        assert ok, f"few_shot_selector.py syntax error: {err}"

    def test_cot_valid_python(self):
        ok, err = self._parse(COT_FILE)
        assert ok, f"chain_of_thought.py syntax error: {err}"

    def test_test_template_valid_python(self):
        ok, err = self._parse(TEST_TEMPLATE)
        assert ok, f"test_structured_template.py syntax error: {err}"

    def test_test_selector_valid_python(self):
        ok, err = self._parse(TEST_SELECTOR)
        assert ok, f"test_few_shot_selector.py syntax error: {err}"

    def test_template_importable(self):
        """StructuredPromptTemplate must be importable."""
        result = subprocess.run(
            f"python -c \"import sys; sys.path.insert(0, '{os.path.dirname(LIB_DIR)}'); "
            f"from prompts.structured_template import StructuredPromptTemplate; print('OK')\"",
            shell=True, capture_output=True, text=True, timeout=30,
            cwd=REPO_DIR,
        )
        if result.returncode != 0:
            # Try alternative import path
            result2 = subprocess.run(
                f"python -c \"import sys; sys.path.insert(0, '{LIB_DIR}'); "
                f"from structured_template import StructuredPromptTemplate; print('OK')\"",
                shell=True, capture_output=True, text=True, timeout=30,
                cwd=REPO_DIR,
            )
            assert "OK" in result.stdout or "OK" in result2.stdout, (
                f"Could not import StructuredPromptTemplate:\n"
                f"stderr1: {result.stderr[:300]}\nstderr2: {result2.stderr[:300]}"
            )
        else:
            assert "OK" in result.stdout

    def test_injection_prevention(self):
        """Template must handle curly braces in variable values safely."""
        with open(TEMPLATE_FILE, "r", encoding="utf-8") as f:
            src = f.read()
        has_escape = (
            "escape" in src.lower()
            or "replace" in src
            or "safe_substitute" in src
            or "Template" in src
            or "{{" in src
        )
        assert has_escape, (
            "Expected injection prevention (escaping curly braces in variables)"
        )
