"""
Test skill: risk-metrics-calculation
Verify that the Agent correctly implements a risk metrics demo script
for pyfolio computing VaR, CVaR, Sharpe, Sortino, and max drawdown
from a portfolio returns series.
"""

import os
import re
import ast
import subprocess
import pytest


class TestRiskMetricsCalculation:
    REPO_DIR = "/workspace/pyfolio"

    # === File Path Checks ===

    def test_demo_script_exists(self):
        """Verify examples/risk_metrics_demo.py exists"""
        path = os.path.join(self.REPO_DIR, "examples/risk_metrics_demo.py")
        assert os.path.exists(path), f"risk_metrics_demo.py not found at {path}"

    # === Semantic Checks ===

    def test_var_computation(self):
        """Verify Value at Risk computation is implemented"""
        path = os.path.join(self.REPO_DIR, "examples/risk_metrics_demo.py")
        with open(path) as f:
            content = f.read()

        var_indicators = ["var", "value_at_risk", "VaR", "quantile", "percentile"]
        found = [ind for ind in var_indicators if ind in content]
        assert len(found) >= 1, (
            f"Should implement Value at Risk. Found: {found}"
        )

    def test_cvar_computation(self):
        """Verify Conditional VaR (Expected Shortfall) is implemented"""
        path = os.path.join(self.REPO_DIR, "examples/risk_metrics_demo.py")
        with open(path) as f:
            content = f.read()

        cvar_indicators = [
            "cvar", "CVaR", "expected_shortfall", "conditional",
            "tail", "shortfall",
        ]
        found = [ind for ind in cvar_indicators if ind in content]
        assert len(found) >= 1, (
            f"Should implement CVaR/Expected Shortfall. Found: {found}"
        )

    def test_sharpe_ratio(self):
        """Verify Sharpe ratio computation"""
        path = os.path.join(self.REPO_DIR, "examples/risk_metrics_demo.py")
        with open(path) as f:
            content = f.read()

        assert "sharpe" in content.lower(), (
            "Should implement Sharpe ratio computation"
        )
        assert "risk_free" in content.lower() or "rf" in content.lower() or \
               "risk free" in content.lower(), (
            "Sharpe ratio should accept a risk-free rate parameter"
        )

    def test_sortino_ratio(self):
        """Verify Sortino ratio using downside deviation"""
        path = os.path.join(self.REPO_DIR, "examples/risk_metrics_demo.py")
        with open(path) as f:
            content = f.read()

        assert "sortino" in content.lower(), (
            "Should implement Sortino ratio"
        )
        downside_indicators = ["downside", "negative", "below"]
        found = [ind for ind in downside_indicators if ind in content.lower()]
        assert len(found) >= 1, (
            f"Sortino should use downside deviation. Found: {found}"
        )

    def test_max_drawdown(self):
        """Verify maximum drawdown computation"""
        path = os.path.join(self.REPO_DIR, "examples/risk_metrics_demo.py")
        with open(path) as f:
            content = f.read()

        dd_indicators = [
            "drawdown", "max_drawdown", "maximum_drawdown",
            "cumulative", "peak", "trough",
        ]
        found = [ind for ind in dd_indicators if ind in content.lower()]
        assert len(found) >= 2, (
            f"Should implement maximum drawdown. Found: {found}"
        )

    def test_configurable_confidence_level(self):
        """Verify confidence level is configurable"""
        path = os.path.join(self.REPO_DIR, "examples/risk_metrics_demo.py")
        with open(path) as f:
            content = f.read()

        confidence_indicators = [
            "confidence", "alpha", "0.95", "0.99", "95", "99",
            "level", "quantile",
        ]
        found = [ind for ind in confidence_indicators if ind in content]
        assert len(found) >= 2, (
            f"Confidence level should be configurable. Found: {found}"
        )

    def test_input_validation(self):
        """Verify input validation for empty series and invalid values"""
        path = os.path.join(self.REPO_DIR, "examples/risk_metrics_demo.py")
        with open(path) as f:
            content = f.read()

        validation_indicators = [
            "empty", "len(", "ValueError", "raise",
            "invalid", "check", "validate", "assert",
        ]
        found = [ind for ind in validation_indicators if ind in content]
        assert len(found) >= 2, (
            f"Should validate inputs. Found: {found}"
        )

    def test_formatted_output(self):
        """Verify formatted summary table is printed"""
        path = os.path.join(self.REPO_DIR, "examples/risk_metrics_demo.py")
        with open(path) as f:
            content = f.read()

        output_indicators = [
            "print", "format", "table", "summary",
            "f\"", "f'", "tabulate",
        ]
        found = [ind for ind in output_indicators if ind in content]
        assert len(found) >= 2, (
            f"Should produce formatted output. Found: {found}"
        )

    # === Functional Checks ===

    def test_script_valid_python(self):
        """Verify risk_metrics_demo.py is valid Python syntax"""
        path = os.path.join(self.REPO_DIR, "examples/risk_metrics_demo.py")
        with open(path) as f:
            source = f.read()
        try:
            ast.parse(source)
        except SyntaxError as e:
            pytest.fail(f"risk_metrics_demo.py has syntax errors: {e}")

    def test_has_main_entry_point(self):
        """Verify script has __main__ entry point"""
        path = os.path.join(self.REPO_DIR, "examples/risk_metrics_demo.py")
        with open(path) as f:
            content = f.read()

        assert '__name__' in content and '__main__' in content, (
            "Script should have a __main__ entry point"
        )

    def test_importable(self):
        """Verify script is importable"""
        path = os.path.join(self.REPO_DIR, "examples/risk_metrics_demo.py")
        result = subprocess.run(
            ["python", "-c", f"import ast; ast.parse(open('{path}').read())"],
            capture_output=True, text=True, timeout=15,
        )
        assert result.returncode == 0, (
            f"Script should be parseable: {result.stderr}"
        )

    def test_defines_metric_functions(self):
        """Verify distinct functions for each metric"""
        path = os.path.join(self.REPO_DIR, "examples/risk_metrics_demo.py")
        with open(path) as f:
            source = f.read()

        tree = ast.parse(source)
        func_names = [
            node.name.lower() for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef)
        ]
        metric_keywords = ["var", "cvar", "sharpe", "sortino", "drawdown"]
        covered = [
            kw for kw in metric_keywords
            if any(kw in fn for fn in func_names)
        ]
        assert len(covered) >= 3, (
            f"Should define functions for metrics. "
            f"Functions: {func_names}, covered: {covered}"
        )
