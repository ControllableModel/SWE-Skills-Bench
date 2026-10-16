"""
Test skill: creating-financial-models
Verify that the Agent correctly builds a DCF valuation model with 5-year
projections, Monte Carlo simulation, sensitivity analysis, and scenario
analysis for a SaaS company.
"""

import os
import re
import ast
import subprocess
import pytest


class TestCreatingFinancialModels:
    REPO_DIR = "/workspace/QuantLib"

    # === File Path Checks ===

    def test_dcf_model_file_exists(self):
        path = os.path.join(self.REPO_DIR, "models/dcf_model.py")
        assert os.path.exists(path), f"dcf_model.py not found at {path}"

    def test_monte_carlo_file_exists(self):
        path = os.path.join(self.REPO_DIR, "models/monte_carlo.py")
        assert os.path.exists(path), f"monte_carlo.py not found at {path}"

    def test_sensitivity_file_exists(self):
        path = os.path.join(self.REPO_DIR, "models/sensitivity.py")
        assert os.path.exists(path), f"sensitivity.py not found at {path}"

    def test_scenario_analysis_file_exists(self):
        path = os.path.join(self.REPO_DIR, "models/scenario_analysis.py")
        assert os.path.exists(path), f"scenario_analysis.py not found at {path}"

    def test_inputs_file_exists(self):
        path = os.path.join(self.REPO_DIR, "models/inputs.py")
        assert os.path.exists(path), f"inputs.py not found at {path}"

    def test_test_dcf_file_exists(self):
        path = os.path.join(self.REPO_DIR, "tests/test_dcf.py")
        assert os.path.exists(path), f"tests/test_dcf.py not found at {path}"

    # === Semantic Checks ===

    def test_dcf_model_class_defined(self):
        """Verify DCFModel class with required methods"""
        path = os.path.join(self.REPO_DIR, "models/dcf_model.py")
        with open(path, "r") as f:
            content = f.read()

        assert "class DCFModel" in content, "Must define DCFModel class"
        expected_methods = [
            "project_financials", "calculate_wacc",
            "terminal_value_perpetuity", "terminal_value_exit_multiple",
            "discount_cash_flows", "enterprise_value", "equity_value"
        ]
        for method in expected_methods:
            assert re.search(rf"def\s+{method}", content), (
                f"DCFModel missing method: {method}"
            )

    def test_inputs_has_historical_data(self):
        """Verify inputs.py has historical financials"""
        path = os.path.join(self.REPO_DIR, "models/inputs.py")
        with open(path, "r") as f:
            content = f.read()

        assert "historical" in content or "revenue" in content, (
            "inputs.py should define historical financial data"
        )
        assert "assumptions" in content, (
            "inputs.py should define base case assumptions"
        )

    def test_wacc_uses_capm(self):
        """Verify WACC calculation uses CAPM formula"""
        path = os.path.join(self.REPO_DIR, "models/dcf_model.py")
        with open(path, "r") as f:
            content = f.read()

        has_capm = (
            "risk_free" in content
            and "beta" in content
            and ("equity_risk_premium" in content or "erp" in content.lower() or "market" in content)
        )
        assert has_capm, "WACC should use CAPM (risk_free + beta * ERP)"

    def test_monte_carlo_class_defined(self):
        """Verify MonteCarloValuation class with required methods"""
        path = os.path.join(self.REPO_DIR, "models/monte_carlo.py")
        with open(path, "r") as f:
            content = f.read()

        assert "MonteCarloValuation" in content or "MonteCarlo" in content, (
            "Must define MonteCarloValuation class"
        )
        assert "5000" in content or "n_iterations" in content, (
            "Monte Carlo should support 5000 iterations"
        )

    def test_monte_carlo_uses_distributions(self):
        """Verify Monte Carlo uses triangular, normal, uniform distributions"""
        path = os.path.join(self.REPO_DIR, "models/monte_carlo.py")
        with open(path, "r") as f:
            content = f.read()

        assert "triangular" in content, "Monte Carlo should use triangular distribution"
        assert "normal" in content, "Monte Carlo should use normal distribution"
        assert "uniform" in content, "Monte Carlo should use uniform distribution"

    def test_monte_carlo_has_statistics(self):
        """Verify Monte Carlo has statistics() and confidence_interval()"""
        path = os.path.join(self.REPO_DIR, "models/monte_carlo.py")
        with open(path, "r") as f:
            content = f.read()

        assert re.search(r"def\s+statistics", content), "Missing statistics() method"
        assert re.search(r"def\s+confidence_interval", content), "Missing confidence_interval() method"

    def test_sensitivity_has_two_way_table(self):
        """Verify sensitivity analysis has two_way_table method"""
        path = os.path.join(self.REPO_DIR, "models/sensitivity.py")
        with open(path, "r") as f:
            content = f.read()

        assert "SensitivityAnalysis" in content, "Must define SensitivityAnalysis class"
        assert re.search(r"def\s+two_way_table", content), "Missing two_way_table method"

    def test_scenario_analysis_has_three_scenarios(self):
        """Verify scenario analysis defines bull/base/bear with weights"""
        path = os.path.join(self.REPO_DIR, "models/scenario_analysis.py")
        with open(path, "r") as f:
            content = f.read()

        content_lower = content.lower()
        assert "bull" in content_lower, "Missing bull scenario"
        assert "base" in content_lower, "Missing base scenario"
        assert "bear" in content_lower, "Missing bear scenario"
        assert "weight" in content_lower or "0.25" in content, (
            "Scenarios should have probability weights"
        )

    # === Functional Checks ===

    def test_all_python_files_parse(self):
        """Verify all model Python files parse without syntax errors"""
        files = [
            "models/dcf_model.py", "models/monte_carlo.py",
            "models/sensitivity.py", "models/scenario_analysis.py",
            "models/inputs.py",
        ]
        for filename in files:
            path = os.path.join(self.REPO_DIR, filename)
            with open(path, "r") as f:
                source = f.read()
            try:
                ast.parse(source)
            except SyntaxError as e:
                pytest.fail(f"{filename} has syntax error: {e}")

    def test_inputs_imports_successfully(self):
        """Verify inputs.py can be imported"""
        result = subprocess.run(
            ["python", "-c",
             "import sys; sys.path.insert(0, '.'); "
             "from models.inputs import historical, assumptions; "
             "print(len(historical['revenue']))"],
            capture_output=True, text=True, timeout=30,
            cwd=self.REPO_DIR,
        )
        assert result.returncode == 0, (
            f"Failed to import inputs:\n{result.stderr[:500]}"
        )

    def test_dcf_model_imports(self):
        """Verify DCFModel can be imported"""
        result = subprocess.run(
            ["python", "-c",
             "import sys; sys.path.insert(0, '.'); "
             "from models.dcf_model import DCFModel; print('OK')"],
            capture_output=True, text=True, timeout=30,
            cwd=self.REPO_DIR,
        )
        assert result.returncode == 0, (
            f"Failed to import DCFModel:\n{result.stderr[:500]}"
        )

    def test_unit_tests_pass(self):
        """Verify the included unit tests pass"""
        result = subprocess.run(
            ["python", "-m", "pytest", "tests/test_dcf.py", "-v", "--tb=short"],
            capture_output=True, text=True, timeout=120,
            cwd=self.REPO_DIR,
        )
        assert result.returncode == 0, (
            f"Unit tests failed:\n{result.stdout[-1000:]}\n{result.stderr[-500:]}"
        )
