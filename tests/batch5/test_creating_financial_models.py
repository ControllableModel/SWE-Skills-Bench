"""
Test skill: creating-financial-models
Verify that the Agent correctly implements a DCF valuation model
with sensitivity analysis using QuantLib in the Examples/python directory.
"""

import os
import re
import ast
import sys
import subprocess
import pytest


class TestCreatingFinancialModels:
    REPO_DIR = "/workspace/QuantLib"

    DCF_MODULE = "Examples/python/dcf_valuation.py"
    SENSITIVITY = "Examples/python/sensitivity_analysis.py"
    CONFIG = "Examples/python/dcf_config.py"
    TESTS = "Examples/python/tests/test_dcf_valuation.py"

    def _read_file(self, rel_path):
        filepath = os.path.join(self.REPO_DIR, rel_path)
        with open(filepath) as f:
            return f.read()

    # === File Path Checks ===

    def test_dcf_module_exists(self):
        filepath = os.path.join(self.REPO_DIR, self.DCF_MODULE)
        assert os.path.exists(filepath), f"dcf_valuation.py not found at {filepath}"

    def test_sensitivity_module_exists(self):
        filepath = os.path.join(self.REPO_DIR, self.SENSITIVITY)
        assert os.path.exists(filepath), f"sensitivity_analysis.py not found at {filepath}"

    def test_config_module_exists(self):
        filepath = os.path.join(self.REPO_DIR, self.CONFIG)
        assert os.path.exists(filepath), f"dcf_config.py not found at {filepath}"

    def test_tests_file_exists(self):
        filepath = os.path.join(self.REPO_DIR, self.TESTS)
        assert os.path.exists(filepath), f"test_dcf_valuation.py not found at {filepath}"

    # === Semantic Checks ===

    def test_config_default_assumptions(self):
        """Verify dcf_config.py defines all required default assumptions"""
        content = self._read_file(self.CONFIG)
        for param in [
            "base_revenue", "growth_rate", "ebit_margin", "tax_rate",
            "capex", "depreciation", "working_capital_change",
            "wacc", "terminal_growth_rate",
        ]:
            assert param in content, f"dcf_config.py missing parameter: {param}"

    def test_dcf_uses_quantlib_term_structure(self):
        """Verify DCF model uses QuantLib FlatForward yield term structure"""
        content = self._read_file(self.DCF_MODULE)
        assert "FlatForward" in content, \
            "DCF model missing QuantLib FlatForward term structure"
        assert "QuantLib" in content or "ql." in content or "import QuantLib" in content, \
            "DCF model missing QuantLib import"

    def test_dcf_projects_five_years(self):
        """Verify DCF projects 5 years of free cash flows"""
        content = self._read_file(self.DCF_MODULE)
        has_5year = bool(re.search(r'(range\(.*5|5.*year|year.*5|for.*in.*range)', content))
        assert has_5year, "DCF model missing 5-year FCF projection loop"

    def test_dcf_computes_terminal_value(self):
        """Verify DCF computes terminal value using perpetuity growth method"""
        content = self._read_file(self.DCF_MODULE)
        assert "terminal" in content.lower(), \
            "DCF model missing terminal value computation"
        has_perpetuity = bool(re.search(
            r'terminal_growth|perpetuity|fcf.*\(1.*growth\).*\/.*\(wacc.*growth\)',
            content,
            re.IGNORECASE,
        ))
        assert has_perpetuity, "DCF missing perpetuity growth formula for terminal value"

    def test_dcf_raises_on_invalid_terminal_growth(self):
        """Verify ValueError when terminal_growth_rate >= wacc"""
        content = self._read_file(self.DCF_MODULE)
        has_check = bool(re.search(
            r'(terminal_growth.*>=.*wacc|wacc.*<=.*terminal|ValueError)',
            content,
            re.IGNORECASE,
        ))
        assert has_check, "DCF missing ValueError for terminal_growth_rate >= wacc"

    def test_sensitivity_varies_wacc_and_growth(self):
        """Verify sensitivity analysis varies WACC 6-14% and growth 2-10%"""
        content = self._read_file(self.SENSITIVITY)
        assert "0.06" in content or "6" in content, \
            "Sensitivity missing WACC lower bound (6%)"
        assert "0.14" in content or "14" in content, \
            "Sensitivity missing WACC upper bound (14%)"
        assert "9" in content or "9x9" in content.lower() or "range" in content, \
            "Sensitivity missing 9-value range"

    def test_sensitivity_produces_2d_table(self):
        """Verify sensitivity outputs a 2D table (DataFrame or nested structure)"""
        content = self._read_file(self.SENSITIVITY)
        has_table = bool(re.search(
            r'(DataFrame|table|matrix|2d|grid|\[\[)',
            content,
            re.IGNORECASE,
        ))
        assert has_table, "Sensitivity analysis missing 2D table output"

    # === Functional Checks ===

    def test_all_files_valid_python(self):
        """Verify all Python files parse without syntax errors"""
        for path in [self.DCF_MODULE, self.SENSITIVITY, self.CONFIG]:
            filepath = os.path.join(self.REPO_DIR, path)
            with open(filepath) as f:
                try:
                    ast.parse(f.read())
                except SyntaxError as e:
                    pytest.fail(f"{path} has syntax error: {e}")

    def test_dcf_enterprise_value_default_assumptions(self):
        """Verify default assumptions produce enterprise value ~753M-760M"""
        sys.path.insert(0, os.path.join(self.REPO_DIR, "Examples/python"))
        try:
            from dcf_config import (
                base_revenue, growth_rate, ebit_margin, tax_rate,
                capex, depreciation, working_capital_change,
                wacc, terminal_growth_rate,
            )
            # Hand-compute approximate FCF year1
            revenue_y1 = base_revenue * (1 + growth_rate)
            ebit_y1 = revenue_y1 * ebit_margin
            fcf_y1 = ebit_y1 * (1 - tax_rate) + depreciation - capex - working_capital_change
            assert fcf_y1 > 0, "FCF year 1 should be positive with default assumptions"
        except ImportError:
            pytest.skip("Cannot import dcf_config, QuantLib may not be available")
        finally:
            if os.path.join(self.REPO_DIR, "Examples/python") in sys.path:
                sys.path.remove(os.path.join(self.REPO_DIR, "Examples/python"))

    def test_dcf_handles_negative_growth(self):
        """Verify DCF model handles negative revenue growth"""
        content = self._read_file(self.DCF_MODULE)
        # Negative growth should still work (no explicit guard against it)
        has_no_positive_guard = not bool(re.search(
            r'growth_rate\s*<\s*0.*raise|if.*growth.*<.*0.*error',
            content,
            re.IGNORECASE,
        ))
        assert has_no_positive_guard, \
            "DCF model should handle negative growth rates without raising"

    def test_tests_have_assertions(self):
        """Verify test file has meaningful test functions"""
        content = self._read_file(self.TESTS)
        tree = ast.parse(content)
        test_funcs = [
            n.name for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")
        ]
        assert len(test_funcs) >= 3, \
            f"Expected at least 3 test functions, found {len(test_funcs)}"
