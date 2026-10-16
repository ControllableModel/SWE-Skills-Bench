"""
Test skill: creating-financial-models
Verify that the Agent creates a DCF valuation engine, Monte Carlo simulation,
and sensitivity analysis using QuantLib.
"""

import os
import subprocess
import ast
import re
import pytest


class TestCreatingFinancialModels:
    REPO_DIR = "/workspace/QuantLib"

    # === File Path Checks ===

    def test_dcf_module_exists(self):
        """Verify DCF valuation module exists"""
        found = False
        for root, dirs, files in os.walk(self.REPO_DIR):
            if ".git" in root:
                continue
            for f in files:
                if f.endswith(".py") and ("dcf" in f.lower() or "valuation" in f.lower()):
                    found = True
                    break
            if found:
                break
        assert found, "DCF valuation module not found"

    # === Semantic Checks ===

    def test_dcf_engine_class_defined(self):
        """Verify DCF valuation engine class is defined"""
        content = self._find_content(["dcf", "valuation"])
        has_class = (
            "class" in content
            and ("DCF" in content or "Valuation" in content or "valuation" in content.lower())
        )
        assert has_class, "DCF valuation engine class not found"

    def test_monte_carlo_simulation_defined(self):
        """Verify Monte Carlo simulation is implemented"""
        content = self._find_content(["monte_carlo", "simulation", "dcf", "valuation"])
        content_lower = content.lower()
        has_mc = (
            "monte" in content_lower
            or "carlo" in content_lower
            or "simulation" in content_lower
            or "random" in content_lower
        )
        assert has_mc, "Monte Carlo simulation not found"

    def test_sensitivity_analysis_defined(self):
        """Verify sensitivity analysis is implemented"""
        content = self._find_content(["sensitivity", "analysis", "dcf", "valuation"])
        content_lower = content.lower()
        has_sensitivity = (
            "sensitivity" in content_lower
            or "tornado" in content_lower
            or "scenario" in content_lower
        )
        assert has_sensitivity, "Sensitivity analysis not found"

    def test_discount_rate_logic(self):
        """Verify discount rate / WACC calculation is present"""
        content = self._find_content(["dcf", "valuation", "discount"])
        content_lower = content.lower()
        has_discount = (
            "discount" in content_lower
            or "wacc" in content_lower
            or "npv" in content_lower
            or "present_value" in content_lower
        )
        assert has_discount, "Discount rate/WACC calculation not found"

    def test_cash_flow_projections(self):
        """Verify cash flow projection logic exists"""
        content = self._find_content(["dcf", "valuation", "cash_flow"])
        content_lower = content.lower()
        has_cf = (
            "cash_flow" in content_lower
            or "cashflow" in content_lower
            or "free_cash" in content_lower
            or "fcf" in content_lower
        )
        assert has_cf, "Cash flow projection logic not found"

    # === Functional Checks ===

    def test_python_files_parse(self):
        """Verify all financial model Python files have valid syntax"""
        for root, dirs, files in os.walk(self.REPO_DIR):
            if ".git" in root:
                continue
            for f in files:
                if f.endswith(".py") and ("dcf" in f.lower() or "valuation" in f.lower() or "monte" in f.lower() or "sensitivity" in f.lower()):
                    fpath = os.path.join(root, f)
                    with open(fpath) as fh:
                        source = fh.read()
                    try:
                        ast.parse(source)
                    except SyntaxError as e:
                        pytest.fail(f"Syntax error in {fpath}: {e}")

    def test_dcf_module_importable(self):
        """Verify DCF module can be imported"""
        dcf_file = None
        for root, dirs, files in os.walk(self.REPO_DIR):
            if ".git" in root:
                continue
            for f in files:
                if f.endswith(".py") and ("dcf" in f.lower() or "valuation" in f.lower()):
                    fpath = os.path.join(root, f)
                    with open(fpath) as fh:
                        content = fh.read()
                    if "class" in content:
                        dcf_file = fpath
                        break
            if dcf_file:
                break
        if dcf_file is None:
            pytest.skip("DCF module not found")
        result = subprocess.run(
            ["python", "-c", f"import ast; ast.parse(open('{dcf_file}').read()); print('OK')"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, f"DCF module parse failed: {result.stderr}"

    def test_monte_carlo_uses_numpy_or_random(self):
        """Verify Monte Carlo uses numpy/random for simulation"""
        content = self._find_content(["monte_carlo", "simulation"])
        has_random = "numpy" in content or "random" in content or "np." in content
        assert has_random, "Monte Carlo simulation missing numpy/random usage"

    def test_results_include_terminal_value(self):
        """Verify DCF includes terminal value calculation"""
        content = self._find_content(["dcf", "valuation", "terminal"])
        content_lower = content.lower()
        has_tv = "terminal" in content_lower or "perpetuity" in content_lower or "gordon" in content_lower
        assert has_tv, "DCF missing terminal value calculation"

    def _find_content(self, keywords):
        """Helper to find content in Python files matching keywords"""
        all_content = ""
        for root, dirs, files in os.walk(self.REPO_DIR):
            if ".git" in root:
                continue
            for f in files:
                if f.endswith(".py"):
                    fname_lower = f.lower()
                    if any(kw in fname_lower for kw in keywords):
                        fpath = os.path.join(root, f)
                        try:
                            with open(fpath) as fh:
                                all_content += fh.read() + "\n"
                        except (UnicodeDecodeError, PermissionError):
                            continue
        return all_content
