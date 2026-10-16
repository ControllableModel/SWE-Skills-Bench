"""
Tests for skill: creating-financial-models
Repo: lballabio/QuantLib
Image: zhangyiiiiii/swe-skills-bench-python
Task: Build a DCF valuation model with sensitivity analysis using QuantLib.
"""

import ast
import os
import re
import subprocess
import sys

import pytest

REPO_DIR = "/workspace/QuantLib"
EXAMPLES_DIR = os.path.join(REPO_DIR, "Python", "examples")

DCF_FILE = os.path.join(EXAMPLES_DIR, "dcf_valuation.py")
SENSITIVITY_FILE = os.path.join(EXAMPLES_DIR, "sensitivity_analysis.py")
RUN_FILE = os.path.join(EXAMPLES_DIR, "run_dcf_example.py")


# ---------------------------------------------------------------------------
# Layer 1 — file_path_check
# ---------------------------------------------------------------------------

class TestFilePathCheck:
    """Verify all required files were created."""

    def test_dcf_valuation_file_exists(self):
        assert os.path.isfile(DCF_FILE), f"Expected {DCF_FILE}"

    def test_sensitivity_analysis_file_exists(self):
        assert os.path.isfile(SENSITIVITY_FILE), f"Expected {SENSITIVITY_FILE}"

    def test_run_example_file_exists(self):
        assert os.path.isfile(RUN_FILE), f"Expected {RUN_FILE}"


# ---------------------------------------------------------------------------
# Layer 2 — semantic_check
# ---------------------------------------------------------------------------

class TestSemanticDCFModel:
    """Verify DCFModel class structure."""

    @pytest.fixture(autouse=True)
    def _load_source(self):
        with open(DCF_FILE, "r", encoding="utf-8") as f:
            self.src = f.read()
        self.tree = ast.parse(self.src)

    def test_dcfmodel_class_defined(self):
        classes = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.ClassDef)]
        assert "DCFModel" in classes, (
            f"Expected DCFModel class; found: {classes}"
        )

    def test_calculate_wacc_method(self):
        """Must have a calculate_wacc method or function."""
        assert "calculate_wacc" in self.src or "wacc" in self.src.lower(), (
            "Expected calculate_wacc method or WACC computation"
        )

    def test_terminal_value_perpetuity(self):
        """Must implement Gordon Growth perpetuity terminal value."""
        assert "terminal_value_perpetuity" in self.src or "perpetuity" in self.src.lower(), (
            "Expected terminal_value_perpetuity method"
        )

    def test_terminal_value_exit_multiple(self):
        """Must implement exit multiple terminal value method."""
        assert "terminal_value_exit_multiple" in self.src or "exit_multiple" in self.src.lower(), (
            "Expected terminal_value_exit_multiple method"
        )

    def test_valuation_summary(self):
        """Must expose get_valuation_summary returning a dict."""
        assert "get_valuation_summary" in self.src or "valuation_summary" in self.src, (
            "Expected get_valuation_summary method"
        )

    def test_fcf_projection_fields(self):
        """Model must project key financial items."""
        expected = ["revenue", "ebitda", "ebit", "nopat", "capex", "fcf"]
        found = [f for f in expected if f in self.src.lower()]
        assert len(found) >= 4, (
            f"Expected at least 4 financial projection fields; found: {found}"
        )

    def test_wacc_formula_components(self):
        """WACC must use CAPM components: risk_free, beta, equity_risk_premium."""
        components = ["risk_free", "beta", "equity_risk_premium", "cost_of_debt"]
        found = [c for c in components if c in self.src]
        assert len(found) >= 3, (
            f"Expected at least 3 WACC formula components; found: {found}"
        )


class TestSemanticSensitivity:
    """Verify SensitivityAnalysis class."""

    @pytest.fixture(autouse=True)
    def _load_source(self):
        with open(SENSITIVITY_FILE, "r", encoding="utf-8") as f:
            self.src = f.read()
        self.tree = ast.parse(self.src)

    def test_sensitivity_class_defined(self):
        classes = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.ClassDef)]
        assert "SensitivityAnalysis" in classes, (
            f"Expected SensitivityAnalysis class; found: {classes}"
        )

    def test_two_way_table_method(self):
        assert "two_way_table" in self.src, (
            "Expected two_way_table method in SensitivityAnalysis"
        )

    def test_tornado_chart_method(self):
        assert "tornado_chart_data" in self.src or "tornado" in self.src.lower(), (
            "Expected tornado_chart_data method"
        )

    def test_numpy_used_for_tables(self):
        """Sensitivity tables should use numpy arrays."""
        assert "numpy" in self.src or "np." in self.src, (
            "Expected numpy for 2D sensitivity tables"
        )


# ---------------------------------------------------------------------------
# Layer 3 — functional_check
# ---------------------------------------------------------------------------

class TestFunctionalFinancialModels:
    """Functional verification of the DCF implementation."""

    def _run(self, cmd, cwd=REPO_DIR, timeout=120):
        return subprocess.run(
            cmd, shell=True, cwd=cwd,
            capture_output=True, text=True, timeout=timeout,
        )

    def test_dcf_file_valid_python(self):
        with open(DCF_FILE, "r", encoding="utf-8") as f:
            src = f.read()
        try:
            ast.parse(src)
        except SyntaxError as e:
            pytest.fail(f"dcf_valuation.py syntax error: {e}")

    def test_sensitivity_file_valid_python(self):
        with open(SENSITIVITY_FILE, "r", encoding="utf-8") as f:
            src = f.read()
        try:
            ast.parse(src)
        except SyntaxError as e:
            pytest.fail(f"sensitivity_analysis.py syntax error: {e}")

    def test_run_example_valid_python(self):
        with open(RUN_FILE, "r", encoding="utf-8") as f:
            src = f.read()
        try:
            ast.parse(src)
        except SyntaxError as e:
            pytest.fail(f"run_dcf_example.py syntax error: {e}")

    def test_dcf_model_importable(self):
        """DCFModel must be importable from dcf_valuation.py."""
        result = self._run(
            f"python -c \"import sys; sys.path.insert(0, '{EXAMPLES_DIR}'); "
            f"from dcf_valuation import DCFModel; print('OK')\"",
            timeout=30,
        )
        assert "OK" in result.stdout, (
            f"Could not import DCFModel:\nstdout: {result.stdout[:500]}\n"
            f"stderr: {result.stderr[:500]}"
        )

    def test_wacc_calculation_correctness(self):
        """WACC with known inputs must produce expected result."""
        code = f"""
import sys
sys.path.insert(0, '{EXAMPLES_DIR}')
from dcf_valuation import DCFModel
m = DCFModel(historical_revenues=[100, 110, 121], historical_margins=[0.2, 0.2, 0.2],
             capex_ratio=0.05, nwc_change_ratio=0.02, tax_rate=0.25)
wacc = m.calculate_wacc(risk_free_rate=0.04, beta=1.2, equity_risk_premium=0.06,
                         cost_of_debt=0.05, tax_rate=0.25, debt_ratio=0.3)
print(f"{{wacc:.4f}}")
"""
        result = self._run(f'python -c "{code}"', timeout=30)
        if result.returncode == 0:
            val = float(result.stdout.strip())
            # Expected: E/V * cost_equity + D/V * cod*(1-t)
            # cost_equity = 0.04 + 1.2*0.06 = 0.112
            # WACC = 0.7*0.112 + 0.3*0.05*0.75 = 0.0784 + 0.01125 = 0.08965
            assert 0.085 < val < 0.095, (
                f"WACC expected ~0.0897; got {val}"
            )
        else:
            pytest.skip(f"calculate_wacc not runnable: {result.stderr[:300]}")

    def test_terminal_value_perpetuity_correctness(self):
        """Gordon Growth with known values must produce ~220.7M."""
        code = f"""
import sys
sys.path.insert(0, '{EXAMPLES_DIR}')
from dcf_valuation import DCFModel
m = DCFModel(historical_revenues=[100], historical_margins=[0.2],
             capex_ratio=0.05, nwc_change_ratio=0.02, tax_rate=0.25)
tv = m.terminal_value_perpetuity(final_fcf=15.0, wacc=0.10, terminal_growth_rate=0.03)
print(f"{{tv:.1f}}")
"""
        result = self._run(f'python -c "{code}"', timeout=30)
        if result.returncode == 0:
            val = float(result.stdout.strip())
            # 15*(1+0.03)/(0.10-0.03) = 15.45/0.07 ≈ 220.7
            assert 218 < val < 225, f"Terminal value expected ~220.7; got {val}"
        else:
            pytest.skip(f"terminal_value_perpetuity not runnable: {result.stderr[:300]}")

    def test_debt_ratio_validation(self):
        """debt_ratio outside 0-1 must raise ValueError."""
        code = f"""
import sys
sys.path.insert(0, '{EXAMPLES_DIR}')
from dcf_valuation import DCFModel
m = DCFModel(historical_revenues=[100], historical_margins=[0.2],
             capex_ratio=0.05, nwc_change_ratio=0.02, tax_rate=0.25)
try:
    m.calculate_wacc(0.04, 1.2, 0.06, 0.05, 0.25, debt_ratio=1.5)
    print("NO_ERROR")
except ValueError:
    print("VALUE_ERROR")
"""
        result = self._run(f'python -c "{code}"', timeout=30)
        if result.returncode == 0:
            assert "VALUE_ERROR" in result.stdout, (
                "Expected ValueError for debt_ratio=1.5"
            )
        else:
            pytest.skip(f"Validation test not runnable: {result.stderr[:300]}")
