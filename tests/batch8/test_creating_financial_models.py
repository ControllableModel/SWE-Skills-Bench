"""
Tests for the creating-financial-models skill.
Validates a DCF valuation, sensitivity analysis, Monte Carlo simulation,
and scenario comparison module built on QuantLib.
"""

import os
import re
import ast
import subprocess

REPO_DIR = "/workspace/QuantLib"
EXAMPLES_DIR = os.path.join(REPO_DIR, "Examples", "python")


class TestCreatingFinancialModels:
    """Tests for the DCF valuation and financial modeling module."""

    # ── file_path_check ──────────────────────────────────────────────

    def test_dcf_valuation_exists(self):
        """DCF valuation module must exist."""
        path = os.path.join(EXAMPLES_DIR, "dcf_valuation.py")
        assert os.path.isfile(path), f"Missing {path}"

    def test_sensitivity_analysis_exists(self):
        """Sensitivity analysis module must exist."""
        path = os.path.join(EXAMPLES_DIR, "sensitivity_analysis.py")
        assert os.path.isfile(path), f"Missing {path}"

    def test_monte_carlo_valuation_exists(self):
        """Monte Carlo valuation module must exist."""
        path = os.path.join(EXAMPLES_DIR, "monte_carlo_valuation.py")
        assert os.path.isfile(path), f"Missing {path}"

    def test_scenario_comparison_exists(self):
        """Scenario comparison module must exist."""
        path = os.path.join(EXAMPLES_DIR, "scenario_comparison.py")
        assert os.path.isfile(path), f"Missing {path}"

    def test_financial_utils_exists(self):
        """Shared financial utilities module must exist."""
        path = os.path.join(EXAMPLES_DIR, "financial_utils.py")
        assert os.path.isfile(path), f"Missing {path}"

    # ── semantic_check ───────────────────────────────────────────────

    def _read(self, filename):
        path = os.path.join(EXAMPLES_DIR, filename)
        if not os.path.isfile(path):
            return ""
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def test_wacc_calculation_defined(self):
        """financial_utils must define calculate_wacc function."""
        content = self._read("financial_utils.py")
        assert re.search(r"def\s+calculate_wacc\b", content), (
            "calculate_wacc function not defined in financial_utils.py"
        )

    def test_dcf_computes_terminal_value_both_methods(self):
        """DCF module must compute terminal value via both perpetuity growth and exit multiple."""
        content = self._read("dcf_valuation.py") + self._read("financial_utils.py")
        assert re.search(r"perpetuity|perp.*growth|terminal_growth", content, re.IGNORECASE), (
            "Perpetuity growth terminal value method not found"
        )
        assert re.search(r"exit.mult|exit_multiple", content, re.IGNORECASE), (
            "Exit multiple terminal value method not found"
        )

    def test_dcf_inputs_accepted(self):
        """DCF must accept key inputs: revenue_base, wacc, shares_outstanding, etc."""
        content = self._read("dcf_valuation.py")
        for field in ["revenue_base", "wacc", "shares_outstanding", "net_debt"]:
            assert field in content, f"Input field '{field}' not found in dcf_valuation.py"

    def test_sensitivity_table_dimensions(self):
        """Sensitivity analysis must produce a WACC-vs-growth table."""
        content = self._read("sensitivity_analysis.py")
        assert re.search(r"wacc|WACC", content), "WACC not referenced in sensitivity analysis"
        assert re.search(r"terminal_growth|growth_rate", content), (
            "Terminal growth rate not referenced in sensitivity analysis"
        )

    def test_monte_carlo_iterations(self):
        """Monte Carlo must run 10,000 iterations with seed=42."""
        content = self._read("monte_carlo_valuation.py")
        assert "10000" in content or "10_000" in content, (
            "10,000 iterations not specified in Monte Carlo module"
        )
        assert "42" in content, "Random seed 42 not found in Monte Carlo module"

    def test_scenario_definitions(self):
        """Scenario comparison must define bull, base, and bear scenarios."""
        content = self._read("scenario_comparison.py")
        for scenario in ["bull", "base", "bear"]:
            assert re.search(scenario, content, re.IGNORECASE), (
                f"'{scenario}' scenario not defined in scenario_comparison.py"
            )

    def test_tornado_chart_data(self):
        """Sensitivity analysis must produce tornado chart data."""
        content = self._read("sensitivity_analysis.py")
        assert re.search(r"tornado|single.variable|impact", content, re.IGNORECASE), (
            "Tornado chart data generation not found"
        )

    # ── functional_check ─────────────────────────────────────────────

    def test_all_files_valid_python(self):
        """All Python files must have valid syntax."""
        errors = []
        for fname in [
            "dcf_valuation.py", "sensitivity_analysis.py",
            "monte_carlo_valuation.py", "scenario_comparison.py",
            "financial_utils.py",
        ]:
            content = self._read(fname)
            if not content:
                continue
            try:
                ast.parse(content)
            except SyntaxError as e:
                errors.append(f"{fname}: {e}")
        assert not errors, "Syntax errors:\n" + "\n".join(errors)

    def test_value_error_for_growth_ge_wacc(self):
        """DCF must raise ValueError when terminal_growth_rate >= wacc."""
        content = self._read("dcf_valuation.py") + self._read("financial_utils.py")
        assert re.search(r"ValueError|growth.*wacc|terminal.*less", content, re.IGNORECASE), (
            "ValueError for growth >= WACC not found"
        )

    def test_probability_weighted_expected_value(self):
        """Scenario comparison must compute probability-weighted expected value."""
        content = self._read("scenario_comparison.py")
        assert re.search(r"probability|weight|expected", content, re.IGNORECASE), (
            "Probability-weighted expected value not found"
        )

    def test_monte_carlo_percentiles(self):
        """Monte Carlo module must compute percentile statistics."""
        content = self._read("monte_carlo_valuation.py")
        assert re.search(r"percentile|quantile|5th|95th", content, re.IGNORECASE), (
            "Percentile computation not found in Monte Carlo module"
        )

    def test_test_dcf_file_exists(self):
        """Test suite for DCF must exist."""
        path = os.path.join(EXAMPLES_DIR, "test_dcf.py")
        assert os.path.isfile(path), f"Missing {path}"
