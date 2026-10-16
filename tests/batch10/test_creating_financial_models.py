"""
Test skill: creating-financial-models
Verify that the Agent correctly implements a DCF valuation engine,
Monte Carlo simulator, and sensitivity analysis for QuantLib.
"""

import os
import re
import ast
import subprocess
import pytest


class TestCreatingFinancialModels:
    REPO_DIR = "/workspace/QuantLib"

    # === File Path Checks ===

    def test_dcf_valuation_exists(self):
        """Verify ql/python/dcf_valuation.py was created"""
        path = os.path.join(self.REPO_DIR, "ql/python/dcf_valuation.py")
        assert os.path.exists(path), f"dcf_valuation.py not found at {path}"

    def test_monte_carlo_exists(self):
        """Verify ql/python/monte_carlo_valuation.py was created"""
        path = os.path.join(self.REPO_DIR, "ql/python/monte_carlo_valuation.py")
        assert os.path.exists(path), f"monte_carlo_valuation.py not found at {path}"

    def test_sensitivity_exists(self):
        """Verify ql/python/sensitivity.py was created"""
        path = os.path.join(self.REPO_DIR, "ql/python/sensitivity.py")
        assert os.path.exists(path), f"sensitivity.py not found at {path}"

    def test_test_file_exists(self):
        """Verify ql/python/test_financial_models.py was created"""
        path = os.path.join(self.REPO_DIR, "ql/python/test_financial_models.py")
        assert os.path.exists(path), f"test_financial_models.py not found at {path}"

    # === Semantic Checks: DCF Model ===

    def test_dcf_model_class_defined(self):
        """Verify DCFModel class is defined"""
        path = os.path.join(self.REPO_DIR, "ql/python/dcf_valuation.py")
        with open(path) as f:
            content = f.read()
        assert "class DCFModel" in content, "DCFModel class should be defined"

    def test_dcf_has_project_cash_flows(self):
        """Verify DCFModel has project_cash_flows method"""
        path = os.path.join(self.REPO_DIR, "ql/python/dcf_valuation.py")
        with open(path) as f:
            content = f.read()
        assert "def project_cash_flows(" in content, (
            "DCFModel should have project_cash_flows method"
        )

    def test_dcf_has_terminal_value_perpetuity(self):
        """Verify DCFModel has terminal_value_perpetuity method"""
        path = os.path.join(self.REPO_DIR, "ql/python/dcf_valuation.py")
        with open(path) as f:
            content = f.read()
        assert "terminal_value_perpetuity" in content, (
            "DCFModel should have terminal_value_perpetuity method"
        )

    def test_dcf_has_terminal_value_exit_multiple(self):
        """Verify DCFModel has terminal_value_exit_multiple method"""
        path = os.path.join(self.REPO_DIR, "ql/python/dcf_valuation.py")
        with open(path) as f:
            content = f.read()
        assert "terminal_value_exit_multiple" in content, (
            "DCFModel should have terminal_value_exit_multiple method"
        )

    def test_dcf_has_enterprise_value(self):
        """Verify DCFModel has enterprise_value method"""
        path = os.path.join(self.REPO_DIR, "ql/python/dcf_valuation.py")
        with open(path) as f:
            content = f.read()
        assert "def enterprise_value(" in content, (
            "DCFModel should have enterprise_value method"
        )

    def test_dcf_has_equity_value(self):
        """Verify DCFModel has equity_value method"""
        path = os.path.join(self.REPO_DIR, "ql/python/dcf_valuation.py")
        with open(path) as f:
            content = f.read()
        assert "def equity_value(" in content, (
            "DCFModel should have equity_value method"
        )

    def test_dcf_has_price_per_share(self):
        """Verify DCFModel has price_per_share method"""
        path = os.path.join(self.REPO_DIR, "ql/python/dcf_valuation.py")
        with open(path) as f:
            content = f.read()
        assert "def price_per_share(" in content, (
            "DCFModel should have price_per_share method"
        )

    def test_dcf_validates_wacc_vs_growth(self):
        """Verify DCFModel raises ValueError when wacc <= terminal_growth_rate"""
        path = os.path.join(self.REPO_DIR, "ql/python/dcf_valuation.py")
        with open(path) as f:
            content = f.read()
        assert "ValueError" in content, (
            "DCFModel should raise ValueError for invalid inputs"
        )

    def test_dcf_accepts_constructor_params(self):
        """Verify DCFModel constructor accepts all required parameters"""
        path = os.path.join(self.REPO_DIR, "ql/python/dcf_valuation.py")
        with open(path) as f:
            content = f.read()
        for param in ["revenue_base", "revenue_growth_rates", "operating_margin",
                       "tax_rate", "wacc", "terminal_growth_rate", "shares_outstanding", "net_debt"]:
            assert param in content, f"DCFModel should accept '{param}' parameter"

    # === Semantic Checks: Monte Carlo ===

    def test_monte_carlo_class_defined(self):
        """Verify MonteCarloValuation class is defined"""
        path = os.path.join(self.REPO_DIR, "ql/python/monte_carlo_valuation.py")
        with open(path) as f:
            content = f.read()
        assert "class MonteCarloValuation" in content, (
            "MonteCarloValuation class should be defined"
        )

    def test_monte_carlo_has_run_method(self):
        """Verify MonteCarloValuation has run method"""
        path = os.path.join(self.REPO_DIR, "ql/python/monte_carlo_valuation.py")
        with open(path) as f:
            content = f.read()
        assert "def run(" in content, "MonteCarloValuation should have run method"

    def test_monte_carlo_result_dataclass(self):
        """Verify MonteCarloResult dataclass is defined"""
        path = os.path.join(self.REPO_DIR, "ql/python/monte_carlo_valuation.py")
        with open(path) as f:
            content = f.read()
        assert "MonteCarloResult" in content, (
            "MonteCarloResult should be defined"
        )
        for field in ["mean", "median", "std", "percentile_5", "percentile_95"]:
            assert field in content, (
                f"MonteCarloResult should have '{field}' field"
            )

    def test_monte_carlo_supports_random_seed(self):
        """Verify Monte Carlo supports random_seed for reproducibility"""
        path = os.path.join(self.REPO_DIR, "ql/python/monte_carlo_valuation.py")
        with open(path) as f:
            content = f.read()
        assert "random_seed" in content or "seed" in content, (
            "MonteCarloValuation should support random_seed"
        )

    def test_monte_carlo_distribution_types(self):
        """Verify both normal and triangular distributions are supported"""
        path = os.path.join(self.REPO_DIR, "ql/python/monte_carlo_valuation.py")
        with open(path) as f:
            content = f.read()
        assert "normal" in content, "Should support normal distribution"
        assert "triangular" in content, "Should support triangular distribution"

    # === Semantic Checks: Sensitivity Analysis ===

    def test_sensitivity_class_defined(self):
        """Verify SensitivityAnalyzer class is defined"""
        path = os.path.join(self.REPO_DIR, "ql/python/sensitivity.py")
        with open(path) as f:
            content = f.read()
        assert "class SensitivityAnalyzer" in content, (
            "SensitivityAnalyzer class should be defined"
        )

    def test_sensitivity_two_way_table(self):
        """Verify two_way_table method is defined"""
        path = os.path.join(self.REPO_DIR, "ql/python/sensitivity.py")
        with open(path) as f:
            content = f.read()
        assert "def two_way_table(" in content, (
            "SensitivityAnalyzer should have two_way_table method"
        )

    def test_sensitivity_tornado_chart(self):
        """Verify tornado_chart method is defined"""
        path = os.path.join(self.REPO_DIR, "ql/python/sensitivity.py")
        with open(path) as f:
            content = f.read()
        assert "def tornado_chart(" in content, (
            "SensitivityAnalyzer should have tornado_chart method"
        )

    # === Functional Checks ===

    def test_dcf_valuation_parses(self):
        """Verify dcf_valuation.py has valid Python syntax"""
        path = os.path.join(self.REPO_DIR, "ql/python/dcf_valuation.py")
        with open(path) as f:
            source = f.read()
        try:
            ast.parse(source)
        except SyntaxError as e:
            pytest.fail(f"dcf_valuation.py has syntax error: {e}")

    def test_monte_carlo_parses(self):
        """Verify monte_carlo_valuation.py has valid Python syntax"""
        path = os.path.join(self.REPO_DIR, "ql/python/monte_carlo_valuation.py")
        with open(path) as f:
            source = f.read()
        try:
            ast.parse(source)
        except SyntaxError as e:
            pytest.fail(f"monte_carlo_valuation.py has syntax error: {e}")

    def test_sensitivity_parses(self):
        """Verify sensitivity.py has valid Python syntax"""
        path = os.path.join(self.REPO_DIR, "ql/python/sensitivity.py")
        with open(path) as f:
            source = f.read()
        try:
            ast.parse(source)
        except SyntaxError as e:
            pytest.fail(f"sensitivity.py has syntax error: {e}")

    def test_financial_model_tests_pass(self):
        """Verify test_financial_models.py tests pass"""
        result = subprocess.run(
            [
                "python", "-m", "pytest",
                "ql/python/test_financial_models.py",
                "-v", "--tb=short",
            ],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, (
            f"Financial model tests failed:\n{result.stdout}\n{result.stderr}"
        )
