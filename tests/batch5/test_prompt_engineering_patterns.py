"""
Test skill: prompt-engineering-patterns
Verify that the Agent correctly builds a reusable prompt template library
for LangChain with classification, chain-of-thought, and constrained output templates.
"""

import os
import re
import ast
import sys
import pytest


class TestPromptEngineeringPatterns:
    REPO_DIR = "/workspace/langchain"

    CLASSIFICATION = "libs/langchain/langchain/prompts/library/classification.py"
    COT = "libs/langchain/langchain/prompts/library/chain_of_thought.py"
    CONSTRAINED = "libs/langchain/langchain/prompts/library/constrained_output.py"
    INIT = "libs/langchain/langchain/prompts/library/__init__.py"
    TESTS = "tests/unit_tests/prompts/test_prompt_library.py"

    def _read_file(self, rel_path):
        filepath = os.path.join(self.REPO_DIR, rel_path)
        with open(filepath) as f:
            return f.read()

    # === File Path Checks ===

    def test_classification_file_exists(self):
        filepath = os.path.join(self.REPO_DIR, self.CLASSIFICATION)
        assert os.path.exists(filepath), f"classification.py not found at {filepath}"

    def test_cot_file_exists(self):
        filepath = os.path.join(self.REPO_DIR, self.COT)
        assert os.path.exists(filepath), f"chain_of_thought.py not found at {filepath}"

    def test_constrained_file_exists(self):
        filepath = os.path.join(self.REPO_DIR, self.CONSTRAINED)
        assert os.path.exists(filepath), f"constrained_output.py not found at {filepath}"

    def test_init_file_exists(self):
        filepath = os.path.join(self.REPO_DIR, self.INIT)
        assert os.path.exists(filepath), f"__init__.py not found at {filepath}"

    def test_tests_file_exists(self):
        filepath = os.path.join(self.REPO_DIR, self.TESTS)
        assert os.path.exists(filepath), f"Test file not found at {filepath}"

    # === Semantic Checks ===

    def test_classification_defines_class(self):
        """Verify FewShotClassificationPrompt class with format and add_example"""
        content = self._read_file(self.CLASSIFICATION)
        assert "FewShotClassificationPrompt" in content, \
            "Missing FewShotClassificationPrompt class"
        assert "format" in content, "Missing format method"
        assert "add_example" in content, "Missing add_example method"
        assert "labels" in content, "Missing labels parameter"

    def test_classification_validates_labels(self):
        """Verify label validation raises ValueError for invalid labels"""
        content = self._read_file(self.CLASSIFICATION)
        assert "ValueError" in content, \
            "Classification missing ValueError for invalid labels"
        has_label_check = bool(re.search(
            r'label.*not.*in.*labels|label.*not.*labels|invalid.*label',
            content,
            re.IGNORECASE,
        ))
        assert has_label_check, "Missing label validation logic"

    def test_cot_defines_class_with_parse(self):
        """Verify ChainOfThoughtPrompt with format and parse_response"""
        content = self._read_file(self.COT)
        assert "ChainOfThoughtPrompt" in content, \
            "Missing ChainOfThoughtPrompt class"
        assert "parse_response" in content, "Missing parse_response method"
        assert "max_steps" in content, "Missing max_steps parameter"

    def test_cot_uses_markers(self):
        """Verify parse_response uses [REASONING] and [ANSWER] markers"""
        content = self._read_file(self.COT)
        assert "[REASONING]" in content, "Missing [REASONING] marker"
        assert "[ANSWER]" in content, "Missing [ANSWER] marker"

    def test_constrained_defines_class_with_validate(self):
        """Verify ConstrainedOutputPrompt with format and validate_output"""
        content = self._read_file(self.CONSTRAINED)
        assert "ConstrainedOutputPrompt" in content, \
            "Missing ConstrainedOutputPrompt class"
        assert "validate_output" in content, "Missing validate_output method"
        assert "output_schema" in content, "Missing output_schema parameter"

    def test_constrained_uses_jsonschema(self):
        """Verify validate_output uses jsonschema for validation"""
        content = self._read_file(self.CONSTRAINED)
        assert "jsonschema" in content, \
            "Missing jsonschema import for output validation"

    def test_init_exports_all_classes(self):
        """Verify __init__.py exports all three template classes"""
        content = self._read_file(self.INIT)
        for cls in [
            "FewShotClassificationPrompt",
            "ChainOfThoughtPrompt",
            "ConstrainedOutputPrompt",
        ]:
            assert cls in content, f"__init__.py missing export: {cls}"

    # === Functional Checks ===

    def test_all_files_valid_python(self):
        """Verify all Python files have valid syntax"""
        for path in [self.CLASSIFICATION, self.COT, self.CONSTRAINED, self.INIT]:
            filepath = os.path.join(self.REPO_DIR, path)
            with open(filepath) as f:
                try:
                    ast.parse(f.read())
                except SyntaxError as e:
                    pytest.fail(f"{path} syntax error: {e}")

    def test_classification_format_output_structure(self):
        """Verify classification format produces expected prompt structure"""
        content = self._read_file(self.CLASSIFICATION)
        has_examples_section = "Examples" in content or "examples" in content
        has_arrow = "→" in content or "->" in content or "Label:" in content
        assert has_examples_section and has_arrow, \
            "Classification format missing structured prompt with examples section"

    def test_constrained_extracts_json_block(self):
        """Verify validate_output extracts first {...} JSON block from text"""
        content = self._read_file(self.CONSTRAINED)
        has_json_extraction = bool(re.search(
            r'(\{.*\}|json\.loads|re\.search.*\{)',
            content,
        ))
        assert has_json_extraction, \
            "validate_output missing JSON block extraction logic"

    def test_tests_cover_all_templates(self):
        """Verify test file covers all three template classes"""
        content = self._read_file(self.TESTS)
        tree = ast.parse(content)
        test_funcs = [
            n.name for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")
        ]
        assert len(test_funcs) >= 6, \
            f"Expected at least 6 tests, found {len(test_funcs)}"
        content_lower = content.lower()
        assert "classification" in content_lower, "Tests missing classification coverage"
        assert "chain_of_thought" in content_lower or "cot" in content_lower, \
            "Tests missing chain-of-thought coverage"
        assert "constrained" in content_lower, "Tests missing constrained output coverage"
