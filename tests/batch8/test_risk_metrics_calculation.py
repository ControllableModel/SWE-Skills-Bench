"""
Tests for the risk-metrics-calculation skill.
Validates a portfolio risk analytics module for pyfolio with VaR, CVaR,
drawdown analysis, risk-adjusted ratios, and factor-based risk decomposition.
"""

import os
import re
import ast

REPO_DIR = "/workspace/pyfolio"


class TestRiskMetricsCalculation:
    """Tests for the pyfolio risk metrics module."""

    # ── file_path_check ──────────────────────────────────────────────

    def test_risk_metrics_file_exists(self):
        """RiskAnalyzer module must exist."""
        path = os.path.join(REPO_DIR, "pyfolio", "risk_metrics.py")
        assert os.path.isfile(path), f"Missing {path}"

    def test_factor_risk_file_exists(self):
        """FactorRiskModel module must exist."""
        path = os.path.join(REPO_DIR, "pyfolio", "factor_risk.py")
        assert os.path.isfile(path), f"Missing {path}"

    def test_risk_report_file_exists(self):
        """Risk report generator must exist."""
        path = os.path.join(REPO_DIR, "pyfolio", "risk_report.py")
        assert os.path.isfile(path), f"Missing {path}"

    # ── semantic_check ───────────────────────────────────────────────

    def _read(self, rel_path):
        path = os.path.join(REPO_DIR, rel_path)
        if not os.path.isfile(path):
            return ""
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def test_risk_analyzer_class_defined(self):
        """RiskAnalyzer class must be defined."""
        content = self._read("pyfolio/risk_metrics.py")
        assert re.search(r"class\s+RiskAnalyzer", content), "RiskAnalyzer class not defined"

    def test_var_methods_defined(self):
        """VaR must be computed via historical, parametric, and Cornish-Fisher methods."""
        content = self._read("pyfolio/risk_metrics.py")
        for method in ["var_historical", "var_parametric", "var_cornish_fisher"]:
            assert re.search(rf"def\s+{method}\b", content), (
                f"{method} method not defined in RiskAnalyzer"
            )

    def test_cvar_defined(self):
        """Conditional VaR (Expected Shortfall) must be defined."""
        content = self._read("pyfolio/risk_metrics.py")
        assert re.search(r"def\s+cvar\b", content), "cvar method not defined"

    def test_risk_adjusted_ratios_defined(self):
        """Sharpe, Sortino, and Calmar ratios must be defined."""
        content = self._read("pyfolio/risk_metrics.py")
        for ratio in ["sharpe_ratio", "sortino_ratio", "calmar_ratio"]:
            assert re.search(rf"def\s+{ratio}\b", content), (
                f"{ratio} method not defined"
            )

    def test_drawdown_methods_defined(self):
        """Drawdown methods must be defined: max_drawdown, drawdown_series, top_drawdowns."""
        content = self._read("pyfolio/risk_metrics.py")
        for method in ["max_drawdown", "drawdown_series", "top_drawdowns"]:
            assert re.search(rf"def\s+{method}\b", content), (
                f"{method} method not defined"
            )

    def test_factor_risk_model_class(self):
        """FactorRiskModel class must be defined with factor_exposures, systematic_risk."""
        content = self._read("pyfolio/factor_risk.py")
        assert re.search(r"class\s+FactorRiskModel", content), (
            "FactorRiskModel class not defined"
        )
        assert re.search(r"def\s+factor_exposures\b", content), (
            "factor_exposures method not defined"
        )
        assert re.search(r"def\s+systematic_risk\b", content), (
            "systematic_risk method not defined"
        )

    def test_information_ratio_defined(self):
        """Information ratio must be defined."""
        content = self._read("pyfolio/risk_metrics.py")
        assert re.search(r"def\s+information_ratio\b", content), (
            "information_ratio method not defined"
        )

    def test_generate_risk_report_defined(self):
        """generate_risk_report function must be defined."""
        content = self._read("pyfolio/risk_report.py")
        assert re.search(r"def\s+generate_risk_report\b", content), (
            "generate_risk_report function not defined"
        )

    # ── functional_check ─────────────────────────────────────────────

    def test_all_files_valid_python(self):
        """All module files must have valid syntax."""
        errors = []
        for rel in [
            "pyfolio/risk_metrics.py",
            "pyfolio/factor_risk.py",
            "pyfolio/risk_report.py",
        ]:
            content = self._read(rel)
            if not content:
                continue
            try:
                ast.parse(content)
            except SyntaxError as e:
                errors.append(f"{rel}: {e}")
        assert not errors, "Syntax errors:\n" + "\n".join(errors)

    def test_nan_handling(self):
        """RiskAnalyzer must handle NaN values (forward-fill, drop)."""
        content = self._read("pyfolio/risk_metrics.py")
        assert re.search(r"fillna|ffill|dropna|forward.fill|isna", content, re.IGNORECASE), (
            "NaN handling not found in RiskAnalyzer"
        )

    def test_minimum_observations_check(self):
        """RiskAnalyzer must require at least 30 observations."""
        content = self._read("pyfolio/risk_metrics.py")
        assert re.search(r"30|min.*obs|ValueError", content), (
            "Minimum 30 observations check not found"
        )

    def test_zero_denominator_handling(self):
        """Risk ratios must handle zero-denominator cases gracefully."""
        content = self._read("pyfolio/risk_metrics.py")
        # Look for checks like "if volatility == 0" or "if ... == 0"
        assert re.search(r"== 0|<= 0|is 0|return 0\.0", content), (
            "Zero-denominator handling not found in risk ratios"
        )

    def test_cornish_fisher_uses_skewness_kurtosis(self):
        """Cornish-Fisher VaR must use skewness and kurtosis adjustments."""
        content = self._read("pyfolio/risk_metrics.py")
        assert re.search(r"skew|kurtosis", content, re.IGNORECASE), (
            "Cornish-Fisher VaR does not use skewness/kurtosis"
        )

    def test_ols_regression_in_factor_model(self):
        """FactorRiskModel must use OLS regression for factor exposures."""
        content = self._read("pyfolio/factor_risk.py")
        assert re.search(r"OLS|ols|regression|lstsq|linalg|LinearRegression", content, re.IGNORECASE), (
            "OLS regression not found in FactorRiskModel"
        )

    def test_test_files_exist(self):
        """Test files for risk metrics and factor risk must exist."""
        for rel in ["tests/test_risk_metrics.py", "tests/test_factor_risk.py"]:
            path = os.path.join(REPO_DIR, rel)
            assert os.path.isfile(path), f"Missing {path}"
