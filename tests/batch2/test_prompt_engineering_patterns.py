"""
Test skill: prompt-engineering-patterns
Verify that the Agent creates a prompt evaluation runner for LangChain
including test case loading, scoring metrics, configurable parameters,
and summary report output.
"""

import os
import re
import ast
import subprocess
import pytest


class TestPromptEngineeringPatterns:
    REPO_DIR = "/workspace/langchain"

    # === File Path Checks ===

    def test_eval_script_exists(self):
        """Verify scripts/run_prompt_eval.py exists"""
        path = os.path.join(self.REPO_DIR, "scripts/run_prompt_eval.py")
        assert os.path.exists(path), f"run_prompt_eval.py not found at {path}"

    # === Semantic Checks ===

    def test_accepts_prompt_templates(self):
        """Verify script handles prompt templates as input"""
        path = os.path.join(self.REPO_DIR, "scripts/run_prompt_eval.py")
        with open(path) as f:
            content = f.read().lower()

        template_indicators = [
            "template", "prompt", "prompttemplate", "prompt_template",
        ]
        found = [ind for ind in template_indicators if ind in content]
        assert len(found) >= 2, (
            f"Script should handle prompt templates. Found: {found}"
        )

    def test_test_case_loading(self):
        """Verify script loads test cases from JSON or YAML"""
        path = os.path.join(self.REPO_DIR, "scripts/run_prompt_eval.py")
        with open(path) as f:
            content = f.read()

        file_indicators = ["json", "yaml", "yml", "load", "open("]
        found = [ind for ind in file_indicators if ind in content.lower()]
        assert len(found) >= 2, (
            f"Script should support loading test cases from files. Found: {found}"
        )

    def test_scoring_metrics_defined(self):
        """Verify at least two automated scoring metrics"""
        path = os.path.join(self.REPO_DIR, "scripts/run_prompt_eval.py")
        with open(path) as f:
            content = f.read().lower()

        metric_indicators = [
            "similarity", "keyword", "format", "compliance",
            "relevance", "score", "bleu", "rouge", "cosine",
            "exact_match", "f1", "precision", "recall",
        ]
        found = [ind for ind in metric_indicators if ind in content]
        assert len(found) >= 2, (
            f"Should define at least two scoring metrics. Found: {found}"
        )

    def test_results_capture(self):
        """Verify results capture prompt, inputs, output, and scores"""
        path = os.path.join(self.REPO_DIR, "scripts/run_prompt_eval.py")
        with open(path) as f:
            content = f.read().lower()

        result_fields = ["prompt", "input", "output", "score"]
        found = [f for f in result_fields if f in content]
        assert len(found) >= 3, (
            f"Results should capture prompt/input/output/score. Found: {found}"
        )

    def test_configurable_model_params(self):
        """Verify configurable model parameters (temperature, max_tokens)"""
        path = os.path.join(self.REPO_DIR, "scripts/run_prompt_eval.py")
        with open(path) as f:
            content = f.read().lower()

        param_indicators = [
            "temperature", "max_tokens", "max_length",
            "argparse", "config", "args",
        ]
        found = [ind for ind in param_indicators if ind in content]
        assert len(found) >= 2, (
            f"Should support configurable model params. Found: {found}"
        )

    def test_summary_report(self):
        """Verify summary report with pass/fail rates and average scores"""
        path = os.path.join(self.REPO_DIR, "scripts/run_prompt_eval.py")
        with open(path) as f:
            content = f.read().lower()

        report_indicators = [
            "summary", "report", "average", "mean", "pass",
            "fail", "print", "aggregate",
        ]
        found = [ind for ind in report_indicators if ind in content]
        assert len(found) >= 3, (
            f"Should produce summary report. Found: {found}"
        )

    def test_export_results(self):
        """Verify optional export to JSON or CSV"""
        path = os.path.join(self.REPO_DIR, "scripts/run_prompt_eval.py")
        with open(path) as f:
            content = f.read().lower()

        export_indicators = ["json", "csv", "export", "save", "write", "dump"]
        found = [ind for ind in export_indicators if ind in content]
        assert len(found) >= 1, (
            f"Should support exporting results. Found: {found}"
        )

    # === Functional Checks ===

    def test_script_valid_python(self):
        """Verify run_prompt_eval.py is valid Python"""
        path = os.path.join(self.REPO_DIR, "scripts/run_prompt_eval.py")
        with open(path) as f:
            source = f.read()
        try:
            ast.parse(source)
        except SyntaxError as e:
            pytest.fail(f"run_prompt_eval.py has syntax errors: {e}")

    def test_has_main_entry_point(self):
        """Verify script has a __main__ entry point"""
        path = os.path.join(self.REPO_DIR, "scripts/run_prompt_eval.py")
        with open(path) as f:
            content = f.read()

        assert '__name__' in content and '__main__' in content, (
            "Script should have a __main__ entry point"
        )

    def test_defines_callable_functions(self):
        """Verify script defines reusable evaluation functions"""
        path = os.path.join(self.REPO_DIR, "scripts/run_prompt_eval.py")
        with open(path) as f:
            source = f.read()

        tree = ast.parse(source)
        func_names = [
            node.name for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        assert len(func_names) >= 3, (
            f"Script should define multiple functions. Found: {func_names}"
        )

    def test_multiple_templates_comparison(self):
        """Verify support for comparing multiple templates"""
        path = os.path.join(self.REPO_DIR, "scripts/run_prompt_eval.py")
        with open(path) as f:
            content = f.read().lower()

        comparison_indicators = [
            "templates", "compare", "multiple", "for ", "each",
            "results[", "template_name",
        ]
        found = [ind for ind in comparison_indicators if ind in content]
        assert len(found) >= 2, (
            f"Should support comparing multiple templates. Found: {found}"
        )
