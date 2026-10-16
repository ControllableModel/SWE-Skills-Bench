"""
Test skill: risk-metrics-calculation
Verify that the Agent creates RiskMetrics (VaR, CVaR, Sharpe, Sortino, max drawdown),
RollingRiskAnalyzer, and PortfolioRiskReport using pyfolio.
"""

import os
import subprocess
import ast
import re
import pytest


class TestRiskMetricsCalculation:
    REPO_DIR = "/workspace/pyfolio"

    # === File Path Checks ===

    def test_risk_metrics_file_exists(self):
        """Verify risk metrics module exists"""
        found = False
        for root, dirs, files in os.walk(self.REPO_DIR):
            if ".git" in root:
                continue
            for f in files:
                if f.endswith(".py") and ("risk" in f.lower() or "metrics" in f.lower()):
                    found = True
                    break
            if found:
                break
        assert found, "Risk metrics module not found"

    # === Semantic Checks ===

    def test_var_calculation_defined(self):
        """Verify Value at Risk (VaR) calculation is implemented"""
        content = self._find_content()
        content_lower = content.lower()
        has_var = "var" in content_lower and ("value" in content_lower or "risk" in content_lower) or "value_at_risk" in content_lower
        assert has_var, "VaR calculation not found"

    def test_cvar_calculation_defined(self):
        """Verify Conditional VaR (CVaR/Expected Shortfall) is implemented"""
        content = self._find_content()
        content_lower = content.lower()
        has_cvar = "cvar" in content_lower or "conditional" in content_lower or "expected_shortfall" in content_lower
        assert has_cvar, "CVaR/Expected Shortfall not found"

    def test_sharpe_ratio_defined(self):
        """Verify Sharpe ratio calculation is implemented"""
        content = self._find_content()
        content_lower = content.lower()
        assert "sharpe" in content_lower, "Sharpe ratio calculation not found"

    def test_sortino_ratio_defined(self):
        """Verify Sortino ratio calculation is implemented"""
        content = self._find_content()
        content_lower = content.lower()
        assert "sortino" in content_lower, "Sortino ratio calculation not found"

    def test_max_drawdown_defined(self):
        """Verify max drawdown calculation is implemented"""
        content = self._find_content()
        content_lower = content.lower()
        has_dd = "drawdown" in content_lower or "max_dd" in content_lower
        assert has_dd, "Max drawdown calculation not found"

    def test_rolling_risk_analyzer_defined(self):
        """Verify RollingRiskAnalyzer class is defined"""
        content = self._find_content()
        has_rolling = "RollingRisk" in content or "rolling" in content.lower()
        assert has_rolling, "RollingRiskAnalyzer not found"

    def test_portfolio_risk_report_defined(self):
        """Verify PortfolioRiskReport class is defined"""
        content = self._find_content()
        has_report = "PortfolioRiskReport" in content or ("portfolio" in content.lower() and "report" in content.lower())
        assert has_report, "PortfolioRiskReport not found"

    # === Functional Checks ===

    def test_risk_files_parse(self):
        """Verify all risk metric files have valid Python syntax"""
        for root, dirs, files in os.walk(self.REPO_DIR):
            if ".git" in root:
                continue
            for f in files:
                if f.endswith(".py") and ("risk" in f.lower() or "metrics" in f.lower()):
                    fpath = os.path.join(root, f)
                    with open(fpath) as fh:
                        source = fh.read()
                    try:
                        ast.parse(source)
                    except SyntaxError as e:
                        pytest.fail(f"Syntax error in {fpath}: {e}")

    def test_risk_module_importable(self):
        """Verify risk module can be imported"""
        risk_file = None
        for root, dirs, files in os.walk(self.REPO_DIR):
            if ".git" in root:
                continue
            for f in files:
                if f.endswith(".py") and "risk" in f.lower():
                    fpath = os.path.join(root, f)
                    with open(fpath) as fh:
                        content = fh.read()
                    if "class" in content and "Risk" in content:
                        risk_file = fpath
                        break
            if risk_file:
                break
        if risk_file is None:
            pytest.skip("Risk module not found")
        dir_name = os.path.dirname(risk_file)
        module_name = os.path.splitext(os.path.basename(risk_file))[0]
        result = subprocess.run(
            ["python", "-c", f"import sys; sys.path.insert(0, '{dir_name}'); import {module_name}; print('OK')"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0 or "OK" in result.stdout, f"Import failed: {result.stderr[:300]}"

    def test_uses_numpy_pandas(self):
        """Verify risk calculations use numpy/pandas"""
        content = self._find_content()
        has_numpy = "numpy" in content or "np." in content
        has_pandas = "pandas" in content or "pd." in content
        assert has_numpy or has_pandas, "Risk calculations should use numpy or pandas"

    def _find_content(self):
        """Helper to find risk metrics content"""
        all_content = ""
        for root, dirs, files in os.walk(self.REPO_DIR):
            if ".git" in root:
                continue
            for f in files:
                if f.endswith(".py") and ("risk" in f.lower() or "metrics" in f.lower() or "portfolio" in f.lower()):
                    fpath = os.path.join(root, f)
                    try:
                        with open(fpath) as fh:
                            all_content += fh.read() + "\n"
                    except (UnicodeDecodeError, PermissionError):
                        continue
        return all_content
