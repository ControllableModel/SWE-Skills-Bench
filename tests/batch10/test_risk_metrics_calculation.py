"""
Test skill: risk-metrics-calculation
Verify that the Agent correctly implements portfolio risk analytics
(VaR, CVaR, drawdowns, ratios, rolling risk) for pyfolio.
"""

import os
import re
import ast
import subprocess
import pytest


class TestRiskMetricsCalculation:
    REPO_DIR = "/workspace/pyfolio"

    # === File Path Checks ===

    def test_risk_metrics_module_exists(self):
        """Verify pyfolio/risk_metrics.py was created"""
        path = os.path.join(self.REPO_DIR, "pyfolio/risk_metrics.py")
        assert os.path.exists(path), f"risk_metrics.py not found at {path}"

    def test_portfolio_risk_module_exists(self):
        """Verify pyfolio/portfolio_risk.py was created"""
        path = os.path.join(self.REPO_DIR, "pyfolio/portfolio_risk.py")
        assert os.path.exists(path), f"portfolio_risk.py not found at {path}"

    def test_rolling_risk_module_exists(self):
        """Verify pyfolio/rolling_risk.py was created"""
        path = os.path.join(self.REPO_DIR, "pyfolio/rolling_risk.py")
        assert os.path.exists(path), f"rolling_risk.py not found at {path}"

    def test_test_file_exists(self):
        """Verify tests/test_risk_metrics.py was created"""
        path = os.path.join(self.REPO_DIR, "tests/test_risk_metrics.py")
        assert os.path.exists(path), f"test_risk_metrics.py not found at {path}"

    # === Semantic Checks: RiskMetrics Class ===

    def test_risk_metrics_class_defined(self):
        """Verify RiskMetrics class is defined"""
        path = os.path.join(self.REPO_DIR, "pyfolio/risk_metrics.py")
        with open(path) as f:
            content = f.read()
        assert "class RiskMetrics" in content, "RiskMetrics class should be defined"

    def test_has_volatility_method(self):
        """Verify volatility method exists"""
        path = os.path.join(self.REPO_DIR, "pyfolio/risk_metrics.py")
        with open(path) as f:
            content = f.read()
        assert "def volatility(" in content, "Should have volatility method"

    def test_has_var_historical(self):
        """Verify var_historical method exists"""
        path = os.path.join(self.REPO_DIR, "pyfolio/risk_metrics.py")
        with open(path) as f:
            content = f.read()
        assert "var_historical" in content, "Should have var_historical method"

    def test_has_var_parametric(self):
        """Verify var_parametric method exists"""
        path = os.path.join(self.REPO_DIR, "pyfolio/risk_metrics.py")
        with open(path) as f:
            content = f.read()
        assert "var_parametric" in content, "Should have var_parametric method"

    def test_has_var_cornish_fisher(self):
        """Verify var_cornish_fisher method exists"""
        path = os.path.join(self.REPO_DIR, "pyfolio/risk_metrics.py")
        with open(path) as f:
            content = f.read()
        assert "var_cornish_fisher" in content, "Should have var_cornish_fisher method"

    def test_has_cvar(self):
        """Verify cvar method exists"""
        path = os.path.join(self.REPO_DIR, "pyfolio/risk_metrics.py")
        with open(path) as f:
            content = f.read()
        assert "def cvar(" in content, "Should have cvar method"

    def test_has_drawdowns(self):
        """Verify drawdowns method exists"""
        path = os.path.join(self.REPO_DIR, "pyfolio/risk_metrics.py")
        with open(path) as f:
            content = f.read()
        assert "def drawdowns(" in content, "Should have drawdowns method"

    def test_has_max_drawdown(self):
        """Verify max_drawdown method exists"""
        path = os.path.join(self.REPO_DIR, "pyfolio/risk_metrics.py")
        with open(path) as f:
            content = f.read()
        assert "max_drawdown" in content, "Should have max_drawdown method"

    def test_has_sharpe_ratio(self):
        """Verify sharpe_ratio method exists"""
        path = os.path.join(self.REPO_DIR, "pyfolio/risk_metrics.py")
        with open(path) as f:
            content = f.read()
        assert "sharpe_ratio" in content, "Should have sharpe_ratio method"

    def test_has_sortino_ratio(self):
        """Verify sortino_ratio method exists"""
        path = os.path.join(self.REPO_DIR, "pyfolio/risk_metrics.py")
        with open(path) as f:
            content = f.read()
        assert "sortino_ratio" in content, "Should have sortino_ratio method"

    def test_has_calmar_ratio(self):
        """Verify calmar_ratio method exists"""
        path = os.path.join(self.REPO_DIR, "pyfolio/risk_metrics.py")
        with open(path) as f:
            content = f.read()
        assert "calmar_ratio" in content, "Should have calmar_ratio method"

    def test_has_omega_ratio(self):
        """Verify omega_ratio method exists"""
        path = os.path.join(self.REPO_DIR, "pyfolio/risk_metrics.py")
        with open(path) as f:
            content = f.read()
        assert "omega_ratio" in content, "Should have omega_ratio method"

    def test_has_summary_method(self):
        """Verify summary method exists"""
        path = os.path.join(self.REPO_DIR, "pyfolio/risk_metrics.py")
        with open(path) as f:
            content = f.read()
        assert "def summary(" in content, "Should have summary method"

    # === Semantic Checks: PortfolioRisk ===

    def test_portfolio_risk_class_defined(self):
        """Verify PortfolioRisk class is defined"""
        path = os.path.join(self.REPO_DIR, "pyfolio/portfolio_risk.py")
        with open(path) as f:
            content = f.read()
        assert "class PortfolioRisk" in content, (
            "PortfolioRisk class should be defined"
        )

    def test_has_portfolio_volatility(self):
        """Verify portfolio_volatility method exists"""
        path = os.path.join(self.REPO_DIR, "pyfolio/portfolio_risk.py")
        with open(path) as f:
            content = f.read()
        assert "portfolio_volatility" in content, (
            "Should have portfolio_volatility method"
        )

    def test_has_component_risk(self):
        """Verify component_risk method exists"""
        path = os.path.join(self.REPO_DIR, "pyfolio/portfolio_risk.py")
        with open(path) as f:
            content = f.read()
        assert "component_risk" in content, "Should have component_risk method"

    def test_has_diversification_ratio(self):
        """Verify diversification_ratio method exists"""
        path = os.path.join(self.REPO_DIR, "pyfolio/portfolio_risk.py")
        with open(path) as f:
            content = f.read()
        assert "diversification_ratio" in content, (
            "Should have diversification_ratio method"
        )

    def test_has_stress_test(self):
        """Verify stress_test method exists"""
        path = os.path.join(self.REPO_DIR, "pyfolio/portfolio_risk.py")
        with open(path) as f:
            content = f.read()
        assert "stress_test" in content, "Should have stress_test method"

    # === Semantic Checks: RollingRisk ===

    def test_rolling_risk_class_defined(self):
        """Verify RollingRiskMetrics class is defined"""
        path = os.path.join(self.REPO_DIR, "pyfolio/rolling_risk.py")
        with open(path) as f:
            content = f.read()
        assert "class RollingRiskMetrics" in content, (
            "RollingRiskMetrics class should be defined"
        )

    def test_has_rolling_volatility(self):
        """Verify rolling_volatility method exists"""
        path = os.path.join(self.REPO_DIR, "pyfolio/rolling_risk.py")
        with open(path) as f:
            content = f.read()
        assert "rolling_volatility" in content, (
            "Should have rolling_volatility method"
        )

    def test_has_rolling_sharpe(self):
        """Verify rolling_sharpe method exists"""
        path = os.path.join(self.REPO_DIR, "pyfolio/rolling_risk.py")
        with open(path) as f:
            content = f.read()
        assert "rolling_sharpe" in content, "Should have rolling_sharpe method"

    def test_has_volatility_regime(self):
        """Verify volatility_regime method exists"""
        path = os.path.join(self.REPO_DIR, "pyfolio/rolling_risk.py")
        with open(path) as f:
            content = f.read()
        assert "volatility_regime" in content, (
            "Should have volatility_regime method"
        )

    # === Functional Checks ===

    def test_risk_metrics_parses(self):
        """Verify risk_metrics.py has valid Python syntax"""
        path = os.path.join(self.REPO_DIR, "pyfolio/risk_metrics.py")
        with open(path) as f:
            source = f.read()
        try:
            ast.parse(source)
        except SyntaxError as e:
            pytest.fail(f"risk_metrics.py has syntax error: {e}")

    def test_portfolio_risk_parses(self):
        """Verify portfolio_risk.py has valid Python syntax"""
        path = os.path.join(self.REPO_DIR, "pyfolio/portfolio_risk.py")
        with open(path) as f:
            source = f.read()
        try:
            ast.parse(source)
        except SyntaxError as e:
            pytest.fail(f"portfolio_risk.py has syntax error: {e}")

    def test_rolling_risk_parses(self):
        """Verify rolling_risk.py has valid Python syntax"""
        path = os.path.join(self.REPO_DIR, "pyfolio/rolling_risk.py")
        with open(path) as f:
            source = f.read()
        try:
            ast.parse(source)
        except SyntaxError as e:
            pytest.fail(f"rolling_risk.py has syntax error: {e}")

    def test_risk_metrics_tests_pass(self):
        """Verify all risk metrics tests pass"""
        result = subprocess.run(
            [
                "python", "-m", "pytest",
                "tests/test_risk_metrics.py",
                "-v", "--tb=short",
            ],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, (
            f"Risk metrics tests failed:\n{result.stdout}\n{result.stderr}"
        )
