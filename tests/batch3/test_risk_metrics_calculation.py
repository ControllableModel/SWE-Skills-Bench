"""
Tests for the risk-metrics-calculation skill.

Validates that a portfolio risk metrics module was implemented for pyfolio,
including VaR (historical/parametric), CVaR, drawdown analysis,
risk-adjusted ratios (Sharpe/Sortino/Calmar), and rolling analytics.

Repo: pyfolio (https://github.com/quantopian/pyfolio)
"""

import ast
import os
import re
import subprocess
import sys

REPO_DIR = "/workspace/pyfolio"


class TestFilePathCheck:
    """Verify that all required files were created."""

    def test_risk_metrics_file_exists(self):
        path = os.path.join(REPO_DIR, "pyfolio", "risk_metrics.py")
        assert os.path.isfile(path), f"Expected risk_metrics.py at {path}"

    def test_risk_metrics_test_exists(self):
        path = os.path.join(REPO_DIR, "tests", "test_risk_metrics.py")
        assert os.path.isfile(path), f"Expected test_risk_metrics.py at {path}"


class TestSemanticVaR:
    """Verify Value at Risk implementations."""

    def _read_module(self):
        path = os.path.join(REPO_DIR, "pyfolio", "risk_metrics.py")
        with open(path, "r") as f:
            return f.read()

    def test_historical_var_function(self):
        content = self._read_module()
        assert re.search(r"def\s+\w*historical\w*var\w*|def\s+\w*var\w*historical", content, re.IGNORECASE), (
            "Expected historical VaR function"
        )

    def test_parametric_var_function(self):
        content = self._read_module()
        assert re.search(r"def\s+\w*parametric\w*var\w*|def\s+\w*var\w*parametric|gaussian", content, re.IGNORECASE), (
            "Expected parametric VaR function"
        )

    def test_confidence_level_parameter(self):
        content = self._read_module()
        assert re.search(r"confidence|alpha|quantile", content, re.IGNORECASE), (
            "Expected confidence level parameter in VaR functions"
        )

    def test_insufficient_data_error(self):
        content = self._read_module()
        assert re.search(r"InsufficientDataError|insufficient.*data", content, re.IGNORECASE), (
            "Expected InsufficientDataError for short return series"
        )

    def test_minimum_observations_check(self):
        """Should check for at least 30 observations."""
        content = self._read_module()
        assert "30" in content, (
            "Expected minimum 30 observations check for VaR"
        )


class TestSemanticCVaR:
    """Verify Conditional Value at Risk implementations."""

    def _read_module(self):
        path = os.path.join(REPO_DIR, "pyfolio", "risk_metrics.py")
        with open(path, "r") as f:
            return f.read()

    def test_cvar_function(self):
        content = self._read_module()
        assert re.search(r"def\s+\w*cvar\w*|def\s+\w*expected.shortfall\w*|CVaR", content, re.IGNORECASE), (
            "Expected CVaR / Expected Shortfall function"
        )

    def test_cvar_uses_tail_mean(self):
        """CVaR should compute mean of returns below VaR threshold."""
        content = self._read_module()
        assert re.search(r"mean|average|tail", content, re.IGNORECASE), (
            "Expected tail mean computation for CVaR"
        )


class TestSemanticDrawdown:
    """Verify maximum drawdown analysis."""

    def _read_module(self):
        path = os.path.join(REPO_DIR, "pyfolio", "risk_metrics.py")
        with open(path, "r") as f:
            return f.read()

    def test_max_drawdown_function(self):
        content = self._read_module()
        assert re.search(r"def\s+\w*max.*drawdown\w*|def\s+\w*drawdown", content, re.IGNORECASE), (
            "Expected max drawdown function"
        )

    def test_drawdown_result_structure(self):
        content = self._read_module()
        assert re.search(r"DrawdownResult|peak_date|trough_date|recovery_date", content), (
            "Expected DrawdownResult with peak/trough/recovery dates"
        )

    def test_top_n_drawdowns(self):
        content = self._read_module()
        assert re.search(r"top.*drawdown|n.*drawdown|drawdown.*periods", content, re.IGNORECASE), (
            "Expected top N drawdown periods computation"
        )

    def test_duration_tracking(self):
        content = self._read_module()
        assert re.search(r"duration|days|peak.*trough", content, re.IGNORECASE), (
            "Expected duration tracking in drawdown analysis"
        )


class TestSemanticRiskRatios:
    """Verify Sharpe, Sortino, and Calmar ratio implementations."""

    def _read_module(self):
        path = os.path.join(REPO_DIR, "pyfolio", "risk_metrics.py")
        with open(path, "r") as f:
            return f.read()

    def test_sharpe_ratio_function(self):
        content = self._read_module()
        assert re.search(r"def\s+\w*sharpe\w*", content, re.IGNORECASE), (
            "Expected Sharpe ratio function"
        )

    def test_sortino_ratio_function(self):
        content = self._read_module()
        assert re.search(r"def\s+\w*sortino\w*", content, re.IGNORECASE), (
            "Expected Sortino ratio function"
        )

    def test_calmar_ratio_function(self):
        content = self._read_module()
        assert re.search(r"def\s+\w*calmar\w*", content, re.IGNORECASE), (
            "Expected Calmar ratio function"
        )

    def test_annualization_factor(self):
        """Ratios should be annualized using sqrt(252)."""
        content = self._read_module()
        assert "252" in content, (
            "Expected annualization factor of 252 trading days"
        )

    def test_risk_free_rate_parameter(self):
        content = self._read_module()
        assert re.search(r"risk_free|risk.free|rf", content, re.IGNORECASE), (
            "Expected risk-free rate parameter"
        )

    def test_zero_variance_handling(self):
        """Zero std should return inf/-inf/0.0 as specified."""
        content = self._read_module()
        assert re.search(r"inf|float\('inf'\)|float\(\"inf\"\)|np\.inf", content), (
            "Expected inf handling for zero-variance edge case"
        )


class TestSemanticRollingAnalytics:
    """Verify rolling VaR and Sharpe implementations."""

    def _read_module(self):
        path = os.path.join(REPO_DIR, "pyfolio", "risk_metrics.py")
        with open(path, "r") as f:
            return f.read()

    def test_rolling_var_function(self):
        content = self._read_module()
        assert re.search(r"def\s+rolling_var|def\s+rolling.*var", content, re.IGNORECASE), (
            "Expected rolling_var function"
        )

    def test_rolling_sharpe_function(self):
        content = self._read_module()
        assert re.search(r"def\s+rolling_sharpe|def\s+rolling.*sharpe", content, re.IGNORECASE), (
            "Expected rolling_sharpe function"
        )

    def test_window_parameter(self):
        content = self._read_module()
        assert re.search(r"window", content), (
            "Expected window parameter in rolling functions"
        )


class TestFunctionalPythonSyntax:
    """Validate Python syntax of created files."""

    def _check_syntax(self, filepath):
        with open(filepath, "r") as f:
            source = f.read()
        ast.parse(source)

    def test_risk_metrics_syntax(self):
        self._check_syntax(os.path.join(REPO_DIR, "pyfolio", "risk_metrics.py"))

    def test_test_file_syntax(self):
        self._check_syntax(os.path.join(REPO_DIR, "tests", "test_risk_metrics.py"))


class TestFunctionalAgentTests:
    """Verify the agent's own tests pass."""

    def test_agent_tests_have_sufficient_coverage(self):
        path = os.path.join(REPO_DIR, "tests", "test_risk_metrics.py")
        with open(path, "r") as f:
            content = f.read()
        test_count = len(re.findall(r"def\s+test_", content))
        assert test_count >= 5, (
            f"Expected at least 5 test functions, found {test_count}"
        )

    def test_agent_tests_pass(self):
        result = subprocess.run(
            [sys.executable, "-m", "pytest",
             "tests/test_risk_metrics.py", "-v", "--tb=short"],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, (
            f"Agent's risk metrics tests failed:\n{result.stdout[-1000:]}\n{result.stderr[-500:]}"
        )

    def test_uses_numpy_or_pandas(self):
        """Risk metrics should use numpy/pandas for computation."""
        path = os.path.join(REPO_DIR, "pyfolio", "risk_metrics.py")
        with open(path, "r") as f:
            content = f.read()
        assert re.search(r"import numpy|import pandas|from numpy|from pandas", content), (
            "Expected numpy or pandas usage in risk_metrics.py"
        )
