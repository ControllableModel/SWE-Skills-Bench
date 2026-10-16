"""
Test skill: llm-evaluation
Verify that the Agent creates an LLM evaluation demo for HELM
with evaluation scenarios, multiple metrics, configurable thresholds,
and a summary report.
"""

import os
import re
import ast
import subprocess
import pytest


class TestLlmEvaluation:
    REPO_DIR = "/workspace/helm"

    # === File Path Checks ===

    def test_eval_demo_exists(self):
        """Verify examples/llm_eval_demo.py exists"""
        path = os.path.join(self.REPO_DIR, "examples/llm_eval_demo.py")
        assert os.path.exists(path), f"llm_eval_demo.py not found at {path}"

    # === Semantic Checks ===

    def test_evaluation_scenarios_defined(self):
        """Verify evaluation scenarios (QA, summarization, classification)"""
        path = os.path.join(self.REPO_DIR, "examples/llm_eval_demo.py")
        with open(path) as f:
            content = f.read().lower()

        scenario_indicators = [
            "scenario", "question", "answer", "summariz",
            "classif", "qa", "prompt", "task",
        ]
        found = [ind for ind in scenario_indicators if ind in content]
        assert len(found) >= 3, (
            f"Should define evaluation scenarios. Found: {found}"
        )

    def test_multiple_metrics(self):
        """Verify multiple evaluation metrics are implemented"""
        path = os.path.join(self.REPO_DIR, "examples/llm_eval_demo.py")
        with open(path) as f:
            content = f.read().lower()

        metric_indicators = [
            "exact_match", "exact match", "f1", "similarity",
            "format", "compliance", "bleu", "rouge", "score",
        ]
        found = [ind for ind in metric_indicators if ind in content]
        assert len(found) >= 2, (
            f"Should implement multiple evaluation metrics. Found: {found}"
        )

    def test_model_interface(self):
        """Verify scenarios run through a model interface"""
        path = os.path.join(self.REPO_DIR, "examples/llm_eval_demo.py")
        with open(path) as f:
            content = f.read()

        model_indicators = [
            "model", "generate", "predict", "invoke",
            "completion", "mock", "response",
        ]
        found = [ind for ind in model_indicators if ind in content.lower()]
        assert len(found) >= 2, (
            f"Should use a model interface. Found: {found}"
        )

    def test_configurable_evaluation(self):
        """Verify evaluation configuration is supported"""
        path = os.path.join(self.REPO_DIR, "examples/llm_eval_demo.py")
        with open(path) as f:
            content = f.read().lower()

        config_indicators = [
            "config", "weight", "threshold", "parameter",
            "json", "yaml", "argparse", "args",
        ]
        found = [ind for ind in config_indicators if ind in content]
        assert len(found) >= 2, (
            f"Should support evaluation configuration. Found: {found}"
        )

    def test_pass_fail_status(self):
        """Verify pass/fail status per scenario"""
        path = os.path.join(self.REPO_DIR, "examples/llm_eval_demo.py")
        with open(path) as f:
            content = f.read().lower()

        status_indicators = [
            "pass", "fail", "threshold", "status",
            "passed", "failed", "result",
        ]
        found = [ind for ind in status_indicators if ind in content]
        assert len(found) >= 2, (
            f"Should show pass/fail status. Found: {found}"
        )

    def test_summary_report(self):
        """Verify summary report with per-scenario and aggregate scores"""
        path = os.path.join(self.REPO_DIR, "examples/llm_eval_demo.py")
        with open(path) as f:
            content = f.read().lower()

        report_indicators = [
            "summary", "report", "aggregate", "average",
            "total", "overall", "print",
        ]
        found = [ind for ind in report_indicators if ind in content]
        assert len(found) >= 3, (
            f"Should produce a summary report. Found: {found}"
        )

    def test_scenario_loading(self):
        """Verify scenarios can be loaded from structured data"""
        path = os.path.join(self.REPO_DIR, "examples/llm_eval_demo.py")
        with open(path) as f:
            content = f.read()

        loading_indicators = [
            "json", "yaml", "load", "open(", "dict",
            "scenarios", "data", "config",
        ]
        found = [ind for ind in loading_indicators if ind in content.lower()]
        assert len(found) >= 2, (
            f"Should support loading scenarios from data. Found: {found}"
        )

    # === Functional Checks ===

    def test_script_valid_python(self):
        """Verify llm_eval_demo.py is valid Python"""
        path = os.path.join(self.REPO_DIR, "examples/llm_eval_demo.py")
        with open(path) as f:
            source = f.read()
        try:
            ast.parse(source)
        except SyntaxError as e:
            pytest.fail(f"llm_eval_demo.py has syntax errors: {e}")

    def test_has_main_entry_point(self):
        """Verify script has __main__ entry point"""
        path = os.path.join(self.REPO_DIR, "examples/llm_eval_demo.py")
        with open(path) as f:
            content = f.read()

        assert '__name__' in content and '__main__' in content, (
            "Script should have a __main__ entry point"
        )

    def test_defines_reusable_functions(self):
        """Verify script defines reusable evaluation functions"""
        path = os.path.join(self.REPO_DIR, "examples/llm_eval_demo.py")
        with open(path) as f:
            source = f.read()

        tree = ast.parse(source)
        func_names = [
            node.name for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        assert len(func_names) >= 3, (
            f"Should define evaluation functions. Found: {func_names}"
        )

    def test_metric_scoring_functions(self):
        """Verify dedicated scoring functions exist for metrics"""
        path = os.path.join(self.REPO_DIR, "examples/llm_eval_demo.py")
        with open(path) as f:
            source = f.read()

        tree = ast.parse(source)
        func_names = [
            node.name.lower() for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef)
        ]
        scoring_keywords = [
            "score", "metric", "eval", "match", "f1",
            "similarity", "compute",
        ]
        scoring_funcs = [
            fn for fn in func_names
            if any(kw in fn for kw in scoring_keywords)
        ]
        assert len(scoring_funcs) >= 1, (
            f"Should define scoring functions. Functions: {func_names}"
        )
