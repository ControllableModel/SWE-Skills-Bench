"""
Tests for the prompt-engineering-patterns skill.

Validates that a prompt template library with few-shot builder,
chain-of-thought formatter, and prompt testing framework was
implemented for LangChain.

Repo: langchain (https://github.com/langchain-ai/langchain)
"""

import ast
import os
import re
import subprocess
import sys

REPO_DIR = "/workspace/langchain"


class TestFilePathCheck:
    """Verify that all required files were created."""

    def test_template_library_file_exists(self):
        path = os.path.join(
            REPO_DIR, "libs", "core", "langchain_core", "prompts", "template_library.py"
        )
        assert os.path.isfile(path), f"Expected template_library.py at {path}"

    def test_prompt_tester_file_exists(self):
        path = os.path.join(
            REPO_DIR, "libs", "core", "langchain_core", "prompts", "prompt_tester.py"
        )
        assert os.path.isfile(path), f"Expected prompt_tester.py at {path}"

    def test_template_library_test_exists(self):
        path = os.path.join(
            REPO_DIR, "libs", "core", "tests", "unit_tests", "prompts", "test_template_library.py"
        )
        assert os.path.isfile(path), f"Expected test_template_library.py at {path}"

    def test_prompt_tester_test_exists(self):
        path = os.path.join(
            REPO_DIR, "libs", "core", "tests", "unit_tests", "prompts", "test_prompt_tester.py"
        )
        assert os.path.isfile(path), f"Expected test_prompt_tester.py at {path}"


class TestSemanticTemplateLibrary:
    """Verify the TemplateLibrary class structure and features."""

    def _read_library(self):
        path = os.path.join(
            REPO_DIR, "libs", "core", "langchain_core", "prompts", "template_library.py"
        )
        with open(path, "r") as f:
            return f.read()

    def test_template_library_class(self):
        content = self._read_library()
        assert re.search(r"class\s+TemplateLibrary", content), (
            "Expected TemplateLibrary class"
        )

    def test_register_method(self):
        content = self._read_library()
        assert re.search(r"def\s+register\b", content), (
            "Expected register method in TemplateLibrary"
        )

    def test_get_by_category_method(self):
        content = self._read_library()
        assert re.search(r"def\s+get_by_category\b", content), (
            "Expected get_by_category method in TemplateLibrary"
        )

    def test_versioned_get_method(self):
        content = self._read_library()
        assert re.search(r"def\s+get\b", content), (
            "Expected get method in TemplateLibrary"
        )
        assert re.search(r"version", content), (
            "Expected version parameter support in TemplateLibrary"
        )

    def test_duplicate_template_error(self):
        content = self._read_library()
        assert re.search(r"class\s+DuplicateTemplateError|DuplicateTemplateError", content), (
            "Expected DuplicateTemplateError exception"
        )

    def test_category_support(self):
        content = self._read_library()
        assert re.search(r"category", content), (
            "Expected category parameter in template registration"
        )


class TestSemanticFewShotBuilder:
    """Verify the FewShotBuilder class."""

    def _read_library(self):
        path = os.path.join(
            REPO_DIR, "libs", "core", "langchain_core", "prompts", "template_library.py"
        )
        with open(path, "r") as f:
            return f.read()

    def test_few_shot_builder_class(self):
        content = self._read_library()
        assert re.search(r"class\s+FewShotBuilder", content), (
            "Expected FewShotBuilder class"
        )

    def test_max_examples_parameter(self):
        content = self._read_library()
        assert re.search(r"max_examples", content), (
            "Expected max_examples parameter in FewShotBuilder"
        )

    def test_selector_support(self):
        """FewShotBuilder should support dynamic example selection."""
        content = self._read_library()
        assert re.search(r"selector|select", content, re.IGNORECASE), (
            "Expected selector function support for dynamic example selection"
        )

    def test_example_formatting(self):
        content = self._read_library()
        assert re.search(r"Input:|Output:|format|template", content), (
            "Expected example formatting logic (Input/Output pattern)"
        )


class TestSemanticChainOfThought:
    """Verify the ChainOfThoughtFormatter class."""

    def _read_library(self):
        path = os.path.join(
            REPO_DIR, "libs", "core", "langchain_core", "prompts", "template_library.py"
        )
        with open(path, "r") as f:
            return f.read()

    def test_cot_formatter_class(self):
        content = self._read_library()
        assert re.search(r"class\s+ChainOfThoughtFormatter", content), (
            "Expected ChainOfThoughtFormatter class"
        )

    def test_step_by_step_instruction(self):
        content = self._read_library()
        assert re.search(r"step by step|step-by-step", content, re.IGNORECASE), (
            "Expected 'step by step' instruction in CoT formatter"
        )

    def test_answer_tag_support(self):
        content = self._read_library()
        assert re.search(r"<answer>|answer.*tag", content, re.IGNORECASE), (
            "Expected <answer> tag support in CoT formatter"
        )

    def test_parse_answer_method(self):
        content = self._read_library()
        assert re.search(r"def\s+parse_answer", content), (
            "Expected parse_answer method in ChainOfThoughtFormatter"
        )

    def test_parse_error_exception(self):
        content = self._read_library()
        assert re.search(r"ParseError|parse_error", content), (
            "Expected ParseError exception for missing answer tag"
        )


class TestSemanticPromptTester:
    """Verify the PromptTester class."""

    def _read_tester(self):
        path = os.path.join(
            REPO_DIR, "libs", "core", "langchain_core", "prompts", "prompt_tester.py"
        )
        with open(path, "r") as f:
            return f.read()

    def test_prompt_tester_class(self):
        content = self._read_tester()
        assert re.search(r"class\s+PromptTester", content), (
            "Expected PromptTester class"
        )

    def test_run_method(self):
        content = self._read_tester()
        assert re.search(r"def\s+run\b", content), (
            "Expected run method in PromptTester"
        )

    def test_test_report_class(self):
        content = self._read_tester()
        assert re.search(r"class\s+TestReport|TestReport", content), (
            "Expected TestReport class or usage"
        )

    def test_regex_match_mode(self):
        content = self._read_tester()
        assert re.search(r"regex|match_mode", content, re.IGNORECASE), (
            "Expected regex match mode support in PromptTester"
        )

    def test_pass_rate_tracking(self):
        content = self._read_tester()
        assert re.search(r"pass_rate|passed|failed", content), (
            "Expected pass/fail rate tracking in TestReport"
        )


class TestFunctionalPythonSyntax:
    """Validate Python syntax of all created files."""

    def _check_syntax(self, filepath):
        with open(filepath, "r") as f:
            source = f.read()
        ast.parse(source)

    def test_template_library_syntax(self):
        self._check_syntax(
            os.path.join(
                REPO_DIR, "libs", "core", "langchain_core", "prompts", "template_library.py"
            )
        )

    def test_prompt_tester_syntax(self):
        self._check_syntax(
            os.path.join(
                REPO_DIR, "libs", "core", "langchain_core", "prompts", "prompt_tester.py"
            )
        )

    def test_template_library_test_syntax(self):
        self._check_syntax(
            os.path.join(
                REPO_DIR, "libs", "core", "tests", "unit_tests", "prompts",
                "test_template_library.py",
            )
        )

    def test_prompt_tester_test_syntax(self):
        self._check_syntax(
            os.path.join(
                REPO_DIR, "libs", "core", "tests", "unit_tests", "prompts",
                "test_prompt_tester.py",
            )
        )


class TestFunctionalAgentTests:
    """Verify the agent's own tests pass."""

    def test_template_library_tests_pass(self):
        result = subprocess.run(
            [sys.executable, "-m", "pytest",
             "libs/core/tests/unit_tests/prompts/test_template_library.py",
             "-v", "--tb=short"],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, (
            f"Template library tests failed:\n{result.stdout[-1000:]}\n{result.stderr[-500:]}"
        )

    def test_prompt_tester_tests_pass(self):
        result = subprocess.run(
            [sys.executable, "-m", "pytest",
             "libs/core/tests/unit_tests/prompts/test_prompt_tester.py",
             "-v", "--tb=short"],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, (
            f"Prompt tester tests failed:\n{result.stdout[-1000:]}\n{result.stderr[-500:]}"
        )
