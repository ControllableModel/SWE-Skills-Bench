"""
Test skill: risk-metrics-calculation
Verify that the Agent builds a portfolio risk analytics engine with VaR,
CVaR, drawdown analysis, risk-adjusted ratios, stress testing, and a
risk report generator.
"""

import os
import re
import ast
import subprocess
import pytest


class TestRiskMetricsCalculation:
    REPO_DIR = "/workspace/pyfolio"

    # === File Path Checks ===

    def test_metrics_file_exists(self):
        path = os.path.join(self.REPO_DIR, "risk/metrics.py")
        assert os.path.exists(path), f"risk/metrics.py not found at {path}"

    def test_portfolio_file_exists(self):
        path = os.path.join(self.REPO_DIR, "risk/portfolio.py")
        assert os.path.exists(path), f"risk/portfolio.py not found at {path}"

    def test_drawdown_file_exists(self):
        path = os.path.join(self.REPO_DIR, "risk/drawdown.py")
        assert os.path.exists(path), f"risk/drawdown.py not found at {path}"

    def test_ratios_file_exists(self):
        path = os.path.join(self.REPO_DIR, "risk/ratios.py")
        assert os.path.exists(path), f"risk/ratios.py not found at {path}"

    def test_stress_test_file_exists(self):
        path = os.path.join(self.REPO_DIR, "risk/stress_test.py")
        assert os.path.exists(path), f"risk/stress_test.py not found at {path}"

    def test_report_file_exists(self):
        path = os.path.join(self.REPO_DIR, "risk/report.py")
        assert os.path.exists(path), f"risk/report.py not found at {path}"

    def test_unit_tests_file_exists(self):
        path = os.path.join(self.REPO_DIR, "tests/test_risk_metrics.py")
        assert os.path.exists(path), f"tests/test_risk_metrics.py not found"

    # === Semantic Checks ===

    def test_risk_metrics_class_has_var_methods(self):
        """Verify RiskMetrics has 3 VaR methods + CVaR"""
        path = os.path.join(self.REPO_DIR, "risk/metrics.py")
        with open(path, "r") as f:
            content = f.read()

        assert "class RiskMetrics" in content, "Must define RiskMetrics class"
        assert re.search(r"def\s+var_historical", content), "Missing var_historical"
        assert re.search(r"def\s+var_parametric", content), "Missing var_parametric"
        assert re.search(r"def\s+var_cornish_fisher", content), "Missing var_cornish_fisher"
        assert re.search(r"def\s+cvar", content), "Missing cvar"

    def test_cornish_fisher_uses_skewness_kurtosis(self):
        """Verify Cornish-Fisher expansion uses skewness and kurtosis"""
        path = os.path.join(self.REPO_DIR, "risk/metrics.py")
        with open(path, "r") as f:
            content = f.read()

        assert "skewness" in content.lower() or "skew" in content, (
            "Cornish-Fisher should use skewness"
        )
        assert "kurtosis" in content.lower() or "kurt" in content, (
            "Cornish-Fisher should use kurtosis"
        )

    def test_var_n_day_scaling(self):
        """Verify VaR supports n-day scaling with sqrt(days)"""
        path = os.path.join(self.REPO_DIR, "risk/metrics.py")
        with open(path, "r") as f:
            content = f.read()

        assert re.search(r"def\s+var_n_day", content), "Missing var_n_day method"
        assert "sqrt" in content, "n-day VaR should scale by sqrt(days)"

    def test_portfolio_risk_class_defined(self):
        """Verify PortfolioRisk class with required methods"""
        path = os.path.join(self.REPO_DIR, "risk/portfolio.py")
        with open(path, "r") as f:
            content = f.read()

        assert "class PortfolioRisk" in content, "Must define PortfolioRisk class"
        expected = ["covariance_matrix", "marginal_var", "component_var", "diversification_ratio"]
        for method in expected:
            assert re.search(rf"def\s+{method}", content), (
                f"PortfolioRisk missing method: {method}"
            )

    def test_portfolio_supports_shrinkage(self):
        """Verify covariance matrix supports Ledoit-Wolf shrinkage"""
        path = os.path.join(self.REPO_DIR, "risk/portfolio.py")
        with open(path, "r") as f:
            content = f.read()

        assert "shrinkage" in content.lower() or "ledoit" in content.lower(), (
            "Covariance should support Ledoit-Wolf shrinkage estimator"
        )

    def test_drawdown_analyzer_defined(self):
        """Verify DrawdownAnalyzer class with required methods"""
        path = os.path.join(self.REPO_DIR, "risk/drawdown.py")
        with open(path, "r") as f:
            content = f.read()

        assert "DrawdownAnalyzer" in content, "Must define DrawdownAnalyzer class"
        expected = ["max_drawdown", "top_n_drawdowns", "current_drawdown", "time_underwater"]
        for method in expected:
            assert re.search(rf"def\s+{method}", content), (
                f"DrawdownAnalyzer missing method: {method}"
            )

    def test_ratios_class_has_all_ratios(self):
        """Verify all risk-adjusted ratios are implemented"""
        path = os.path.join(self.REPO_DIR, "risk/ratios.py")
        with open(path, "r") as f:
            content = f.read()

        expected = ["sharpe_ratio", "sortino_ratio", "calmar_ratio",
                     "information_ratio", "treynor_ratio", "omega_ratio"]
        for ratio in expected:
            assert re.search(rf"def\s+{ratio}", content), f"Missing {ratio}"

    def test_stress_test_has_historical_scenarios(self):
        """Verify stress test defines 2008, 2020, 2022 scenarios"""
        path = os.path.join(self.REPO_DIR, "risk/stress_test.py")
        with open(path, "r") as f:
            content = f.read()

        assert "2008" in content or "GFC" in content, "Missing 2008 GFC scenario"
        assert "2020" in content or "COVID" in content, "Missing 2020 COVID scenario"
        assert "2022" in content, "Missing 2022 rate hike scenario"

    def test_report_generates_limit_breaches(self):
        """Verify report checks and flags limit breaches"""
        path = os.path.join(self.REPO_DIR, "risk/report.py")
        with open(path, "r") as f:
            content = f.read()

        assert "limit_breaches" in content or "breach" in content, (
            "Report should flag limit breaches"
        )
        assert "generate_risk_report" in content, (
            "Must define generate_risk_report function"
        )

    # === Functional Checks ===

    def test_all_python_files_parse(self):
        """Verify all Python files parse without syntax errors"""
        files = [
            "risk/metrics.py", "risk/portfolio.py", "risk/drawdown.py",
            "risk/ratios.py", "risk/stress_test.py", "risk/report.py",
        ]
        for filename in files:
            path = os.path.join(self.REPO_DIR, filename)
            with open(path, "r") as f:
                source = f.read()
            try:
                ast.parse(source)
            except SyntaxError as e:
                pytest.fail(f"{filename} has syntax error: {e}")

    def test_metrics_import(self):
        """Verify RiskMetrics can be imported"""
        result = subprocess.run(
            ["python", "-c",
             "import sys; sys.path.insert(0, '.'); "
             "from risk.metrics import RiskMetrics; print('OK')"],
            capture_output=True, text=True, timeout=30,
            cwd=self.REPO_DIR,
        )
        assert result.returncode == 0, (
            f"Failed to import RiskMetrics:\n{result.stderr[:500]}"
        )

    def test_unit_tests_pass(self):
        """Verify included unit tests pass"""
        result = subprocess.run(
            ["python", "-m", "pytest", "tests/test_risk_metrics.py",
             "-v", "--tb=short"],
            capture_output=True, text=True, timeout=120,
            cwd=self.REPO_DIR,
        )
        assert result.returncode == 0, (
            f"Unit tests failed:\n{result.stdout[-1000:]}\n{result.stderr[-500:]}"
        )
