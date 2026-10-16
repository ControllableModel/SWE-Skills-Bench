"""
Test skill: prompt-engineering-patterns
Verify that the Agent implements a SemanticFewShotPromptTemplate with dynamic
example selection (cosine similarity + MMR), chain-of-thought support, and
proper LangChain BasePromptTemplate integration.
"""

import os
import re
import ast
import subprocess
import pytest


class TestPromptEngineeringPatterns:
    REPO_DIR = "/workspace/langchain"
    PROMPTS_DIR = "libs/langchain/langchain/prompts"

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

    def test_semantic_few_shot_module_exists(self):
        """semantic_few_shot.py must exist"""
        assert self._exists(f"{self.PROMPTS_DIR}/semantic_few_shot.py")

    def test_example_store_module_exists(self):
        """example_store.py must exist"""
        assert self._exists(f"{self.PROMPTS_DIR}/example_store.py")

    def test_unit_test_file_exists(self):
        """Unit test file must exist"""
        assert self._exists(
            "libs/langchain/tests/unit_tests/prompts/test_semantic_few_shot.py"
        )

    # === Semantic Checks — ExampleStore ===

    def test_example_store_class_defined(self):
        """ExampleStore class must be defined"""
        tree = self._parse(f"{self.PROMPTS_DIR}/example_store.py")
        classes = [n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
        assert "ExampleStore" in classes, "ExampleStore class not found"

    def test_example_store_select_method(self):
        """ExampleStore must have a select() method"""
        src = self._read(f"{self.PROMPTS_DIR}/example_store.py")
        assert re.search(r'def\s+select\s*\(\s*self', src), (
            "select() method not found in ExampleStore"
        )

    def test_example_store_select_diverse_method(self):
        """ExampleStore must have a select_diverse() method for MMR"""
        src = self._read(f"{self.PROMPTS_DIR}/example_store.py")
        assert re.search(r'def\s+select_diverse\s*\(\s*self', src), (
            "select_diverse() method not found in ExampleStore"
        )

    def test_example_store_add_example_method(self):
        """ExampleStore must have an add_example() method"""
        src = self._read(f"{self.PROMPTS_DIR}/example_store.py")
        assert re.search(r'def\s+add_example\s*\(\s*self', src), (
            "add_example() method not found"
        )

    def test_example_store_remove_example_method(self):
        """ExampleStore must have a remove_example() method"""
        src = self._read(f"{self.PROMPTS_DIR}/example_store.py")
        assert re.search(r'def\s+remove_example\s*\(\s*self', src), (
            "remove_example() method not found"
        )

    def test_cosine_similarity_function(self):
        """cosine_similarity utility function must be defined"""
        src = self._read(f"{self.PROMPTS_DIR}/example_store.py")
        assert re.search(r'def\s+cosine_similarity\s*\(', src), (
            "cosine_similarity function not found"
        )

    # === Semantic Checks — SemanticFewShotPromptTemplate ===

    def test_template_class_defined(self):
        """SemanticFewShotPromptTemplate class must be defined"""
        tree = self._parse(f"{self.PROMPTS_DIR}/semantic_few_shot.py")
        classes = [n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
        assert "SemanticFewShotPromptTemplate" in classes, (
            "SemanticFewShotPromptTemplate class not found"
        )

    def test_template_inherits_base(self):
        """SemanticFewShotPromptTemplate must inherit from BasePromptTemplate"""
        src = self._read(f"{self.PROMPTS_DIR}/semantic_few_shot.py")
        assert "BasePromptTemplate" in src, (
            "SemanticFewShotPromptTemplate should inherit from BasePromptTemplate"
        )

    def test_format_method(self):
        """format() method must be defined"""
        src = self._read(f"{self.PROMPTS_DIR}/semantic_few_shot.py")
        assert re.search(r'def\s+format\s*\(\s*self', src), (
            "format() method not found"
        )

    def test_format_messages_method(self):
        """format_messages() method must be defined"""
        src = self._read(f"{self.PROMPTS_DIR}/semantic_few_shot.py")
        assert re.search(r'def\s+format_messages\s*\(\s*self', src), (
            "format_messages() method not found"
        )

    def test_input_variables_property(self):
        """input_variables property must be defined"""
        src = self._read(f"{self.PROMPTS_DIR}/semantic_few_shot.py")
        assert "input_variables" in src, "input_variables property not found"

    def test_include_reasoning_support(self):
        """Template must support include_reasoning parameter for CoT"""
        src = self._read(f"{self.PROMPTS_DIR}/semantic_few_shot.py")
        assert "include_reasoning" in src, (
            "include_reasoning parameter not found — CoT support missing"
        )

    def test_selection_strategy_options(self):
        """Template must support 'similarity' and 'mmr' selection strategies"""
        src = self._read(f"{self.PROMPTS_DIR}/semantic_few_shot.py")
        assert "similarity" in src and "mmr" in src, (
            "selection_strategy must support 'similarity' and 'mmr'"
        )

    def test_example_separator_configurable(self):
        """example_separator must be a configurable parameter"""
        src = self._read(f"{self.PROMPTS_DIR}/semantic_few_shot.py")
        assert "example_separator" in src, (
            "example_separator parameter not found"
        )

    # === Semantic Checks — __init__.py exports ===

    def test_init_exports_classes(self):
        """__init__.py must export SemanticFewShotPromptTemplate and ExampleStore"""
        src = self._read(f"{self.PROMPTS_DIR}/__init__.py")
        assert "SemanticFewShotPromptTemplate" in src, (
            "SemanticFewShotPromptTemplate not exported from __init__.py"
        )

    # === Functional Checks ===

    def test_example_store_importable(self):
        """ExampleStore must be importable"""
        result = subprocess.run(
            ["python", "-c",
             "from langchain.prompts.example_store import ExampleStore, cosine_similarity; "
             "print('OK')"],
            capture_output=True, text=True, cwd=self.REPO_DIR, timeout=30,
        )
        assert "OK" in result.stdout, (
            f"Import failed:\n{result.stdout}\n{result.stderr}"
        )

    def test_template_importable(self):
        """SemanticFewShotPromptTemplate must be importable"""
        result = subprocess.run(
            ["python", "-c",
             "from langchain.prompts.semantic_few_shot import "
             "SemanticFewShotPromptTemplate; print('OK')"],
            capture_output=True, text=True, cwd=self.REPO_DIR, timeout=30,
        )
        assert "OK" in result.stdout, (
            f"Import failed:\n{result.stdout}\n{result.stderr}"
        )

    def test_cosine_similarity_correctness(self):
        """cosine_similarity must return 1.0 for identical vectors"""
        result = subprocess.run(
            ["python", "-c",
             "from langchain.prompts.example_store import cosine_similarity; "
             "assert abs(cosine_similarity([1.0, 0.0], [1.0, 0.0]) - 1.0) < 1e-6; "
             "print('OK')"],
            capture_output=True, text=True, cwd=self.REPO_DIR, timeout=30,
        )
        assert "OK" in result.stdout, (
            f"cosine_similarity test failed:\n{result.stdout}\n{result.stderr}"
        )

    def test_unit_tests_pass(self):
        """Unit tests for semantic few-shot must pass"""
        result = subprocess.run(
            ["python", "-m", "pytest",
             "libs/langchain/tests/unit_tests/prompts/test_semantic_few_shot.py",
             "-v", "--tb=short"],
            capture_output=True, text=True, cwd=self.REPO_DIR, timeout=120,
        )
        assert result.returncode == 0, (
            f"Unit tests failed:\n{result.stdout}\n{result.stderr}"
        )
