"""
Test skill: slo-implementation
Verify that the Agent creates SLI/SLO models, calculator, and burn rate
alerter for SLO implementation (Python).
"""

import os
import re
import ast
import subprocess
import pytest


class TestSloImplementation:
    REPO_DIR = "/workspace/slo-generator"

    # === File Path Checks ===

    def test_slo_files_exist(self):
        """Verify SLO implementation files exist"""
        found = False
        for root, dirs, files in os.walk(self.REPO_DIR):
            if ".git" in root or "node_modules" in root:
                continue
            for f in files:
                if f.endswith(".py") and ("slo" in f.lower() or "sli" in f.lower() or "burn" in f.lower() or "calculator" in f.lower()):
                    found = True
                    break
            if found:
                break
        assert found, "SLO implementation files not found"

    # === Semantic Checks ===

    def test_sli_model_defined(self):
        """Verify SLI model is defined"""
        content = self._collect_content()
        has_sli = "SLI" in content or "sli" in content.lower()
        assert has_sli, "SLI model not found"

    def test_slo_model_defined(self):
        """Verify SLO model is defined"""
        content = self._collect_content()
        has_slo = "SLO" in content or "slo" in content.lower()
        assert has_slo, "SLO model not found"

    def test_calculator_defined(self):
        """Verify SLO calculator is implemented"""
        content = self._collect_content()
        content_lower = content.lower()
        has_calc = "calculator" in content_lower or "compute" in content_lower or "calculate" in content_lower
        assert has_calc, "SLO calculator not found"

    def test_burn_rate_alerter_defined(self):
        """Verify burn rate alerter is implemented"""
        content = self._collect_content()
        content_lower = content.lower()
        has_burn = "burn" in content_lower or "alert" in content_lower or "budget" in content_lower
        assert has_burn, "Burn rate alerter not found"

    def test_error_budget_calculation(self):
        """Verify error budget calculation is present"""
        content = self._collect_content()
        content_lower = content.lower()
        has_budget = "budget" in content_lower or "error_rate" in content_lower or "remaining" in content_lower
        assert has_budget, "Error budget calculation not found"

    # === Functional Checks ===

    def test_python_files_valid_syntax(self):
        """Verify Python files have valid AST"""
        py_files = self._find_py_files()
        assert len(py_files) > 0, "No SLO Python files found"
        for pf in py_files:
            with open(pf) as fh:
                source = fh.read()
            try:
                ast.parse(source)
            except SyntaxError as e:
                pytest.fail(f"Syntax error in {pf}: {e}")

    def test_python_files_define_classes(self):
        """Verify Python files define classes"""
        py_files = self._find_py_files()
        any_class = False
        for pf in py_files:
            with open(pf) as fh:
                source = fh.read()
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    any_class = True
                    break
            if any_class:
                break
        assert any_class, "No classes found in SLO files"

    def test_window_based_calculation(self):
        """Verify window-based SLO calculation"""
        content = self._collect_content()
        content_lower = content.lower()
        has_window = "window" in content_lower or "period" in content_lower or "rolling" in content_lower or "time_range" in content_lower
        assert has_window, "Window-based SLO calculation not found"

    def test_threshold_configuration(self):
        """Verify SLO threshold configuration"""
        content = self._collect_content()
        content_lower = content.lower()
        has_threshold = (
            "threshold" in content_lower
            or "target" in content_lower
            or "objective" in content_lower
            or "99.9" in content
            or "99.5" in content
        )
        assert has_threshold, "SLO threshold configuration not found"

    def _collect_content(self):
        all_content = ""
        for root, dirs, files in os.walk(self.REPO_DIR):
            if ".git" in root or "node_modules" in root:
                continue
            for f in files:
                if f.endswith(".py"):
                    fpath = os.path.join(root, f)
                    try:
                        with open(fpath) as fh:
                            c = fh.read()
                        if any(kw in c.lower() for kw in ["slo", "sli", "burn", "budget", "calculator"]):
                            all_content += c + "\n"
                    except (UnicodeDecodeError, PermissionError):
                        continue
        return all_content

    def _find_py_files(self):
        result = []
        for root, dirs, files in os.walk(self.REPO_DIR):
            if ".git" in root or "node_modules" in root:
                continue
            for f in files:
                if f.endswith(".py") and ("slo" in f.lower() or "sli" in f.lower() or "burn" in f.lower() or "calculator" in f.lower()):
                    result.append(os.path.join(root, f))
        return result
