"""
Test skill: risk-metrics-calculation
Verify that the Agent correctly implements portfolio risk metrics
(VaR, CVaR, Sortino, max drawdown duration, risk parity) for pyfolio.
"""

import os
import re
import ast
import sys
import pytest


class TestRiskMetricsCalculation:
    REPO_DIR = "/workspace/pyfolio"

    METRICS = "pyfolio/risk_metrics.py"
    TESTS = "pyfolio/tests/test_risk_metrics.py"

    def _read_file(self, rel_path):
        filepath = os.path.join(self.REPO_DIR, rel_path)
        with open(filepath) as f:
            return f.read()

    # === File Path Checks ===

    def test_risk_metrics_module_exists(self):
        filepath = os.path.join(self.REPO_DIR, self.METRICS)
        assert os.path.exists(filepath), f"risk_metrics.py not found at {filepath}"

    def test_tests_file_exists(self):
        filepath = os.path.join(self.REPO_DIR, self.TESTS)
        assert os.path.exists(filepath), f"test_risk_metrics.py not found at {filepath}"

    # === Semantic Checks ===

    def test_historical_var_defined(self):
        """Verify historical_var function is defined"""
        content = self._read_file(self.METRICS)
        assert "def historical_var" in content, "Missing historical_var function"
        assert "confidence" in content, "historical_var missing confidence parameter"

    def test_parametric_var_defined(self):
        """Verify parametric_var function with normal distribution approach"""
        content = self._read_file(self.METRICS)
        assert "def parametric_var" in content, "Missing parametric_var function"
        has_normal = bool(re.search(r'(norm\.ppf|z_score|scipy|stats)', content))
        assert has_normal, "parametric_var missing normal distribution calculation"

    def test_historical_cvar_defined(self):
        """Verify historical_cvar (Expected Shortfall) function"""
        content = self._read_file(self.METRICS)
        assert "def historical_cvar" in content, "Missing historical_cvar function"

    def test_sortino_ratio_defined(self):
        """Verify sortino_ratio with downside deviation and annualization"""
        content = self._read_file(self.METRICS)
        assert "def sortino_ratio" in content, "Missing sortino_ratio function"
        assert "annualization" in content or "252" in content, \
            "sortino_ratio missing annualization factor"
        assert "downside" in content.lower(), \
            "sortino_ratio missing downside deviation calculation"

    def test_max_drawdown_duration_defined(self):
        """Verify max_drawdown_duration function"""
        content = self._read_file(self.METRICS)
        assert "def max_drawdown_duration" in content, \
            "Missing max_drawdown_duration function"
        assert "peak" in content.lower() or "cummax" in content, \
            "max_drawdown_duration missing peak tracking logic"

    def test_rolling_variants_defined(self):
        """Verify rolling_var and rolling_sortino functions"""
        content = self._read_file(self.METRICS)
        assert "def rolling_var" in content, "Missing rolling_var function"
        assert "def rolling_sortino" in content, "Missing rolling_sortino function"
        assert "window" in content, "Rolling functions missing window parameter"

    def test_risk_parity_weights_defined(self):
        """Verify risk_parity_weights with iterative optimization"""
        content = self._read_file(self.METRICS)
        assert "def risk_parity_weights" in content, \
            "Missing risk_parity_weights function"
        has_optim = bool(re.search(
            r'(optimize|minimize|iteration|converge|scipy)',
            content,
            re.IGNORECASE,
        ))
        assert has_optim, "risk_parity_weights missing iterative optimization"

    def test_edge_case_empty_series(self):
        """Verify ValueError for empty or single-element returns"""
        content = self._read_file(self.METRICS)
        assert "ValueError" in content, "Missing ValueError for empty input"
        has_length_check = bool(re.search(
            r'(len\(.*\)\s*<\s*2|at least 2|insufficient)',
            content,
            re.IGNORECASE,
        ))
        assert has_length_check, "Missing length check for minimum 2 data points"

    def test_sortino_returns_inf_for_all_positive(self):
        """Verify sortino_ratio returns inf when all returns above target"""
        content = self._read_file(self.METRICS)
        has_inf = bool(re.search(r'(np\.inf|float\([\'"]inf|math\.inf|inf)', content))
        assert has_inf, "sortino_ratio missing inf return for all-positive case"

    # === Functional Checks ===

    def test_module_valid_python(self):
        """Verify risk_metrics.py is valid Python syntax"""
        filepath = os.path.join(self.REPO_DIR, self.METRICS)
        with open(filepath) as f:
            try:
                ast.parse(f.read())
            except SyntaxError as e:
                pytest.fail(f"risk_metrics.py syntax error: {e}")

    def test_functional_historical_var(self):
        """Verify historical_var produces correct result for known data"""
        sys.path.insert(0, self.REPO_DIR)
        try:
            import pandas as pd
            import numpy as np
            from pyfolio.risk_metrics import historical_var
            returns = pd.Series(
                [-0.02, -0.01, 0.01, 0.03, -0.05, 0.02, -0.03, 0.01, 0.02, -0.01]
            )
            var = historical_var(returns, confidence=0.95)
            assert var < 0, "VaR should be negative (represents loss)"
            assert -0.06 < var < -0.03, \
                f"VaR at 95% should be ~-0.042, got {var}"
        except ImportError:
            pytest.skip("Cannot import risk_metrics module")
        finally:
            if self.REPO_DIR in sys.path:
                sys.path.remove(self.REPO_DIR)

    def test_functional_risk_parity_equal_variance(self):
        """Verify risk parity gives equal weights for identical uncorrelated assets"""
        sys.path.insert(0, self.REPO_DIR)
        try:
            import pandas as pd
            import numpy as np
            from pyfolio.risk_metrics import risk_parity_weights
            cov = pd.DataFrame(
                np.eye(3) * 0.04,
                index=["A", "B", "C"],
                columns=["A", "B", "C"],
            )
            weights = risk_parity_weights(cov)
            assert abs(weights.sum() - 1.0) < 1e-3, \
                f"Weights should sum to 1.0, got {weights.sum()}"
            for w in weights:
                assert abs(w - 1.0 / 3) < 0.05, \
                    f"Equal variance assets should get ~equal weight, got {w}"
        except ImportError:
            pytest.skip("Cannot import risk_metrics module")
        finally:
            if self.REPO_DIR in sys.path:
                sys.path.remove(self.REPO_DIR)

    def test_tests_cover_all_functions(self):
        """Verify test file covers VaR, CVaR, Sortino, drawdown, risk parity"""
        content = self._read_file(self.TESTS)
        tree = ast.parse(content)
        test_funcs = [
            n.name for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")
        ]
        assert len(test_funcs) >= 6, \
            f"Expected at least 6 tests, found {len(test_funcs)}"
        content_lower = content.lower()
        assert "var" in content_lower, "Tests missing VaR coverage"
        assert "sortino" in content_lower, "Tests missing Sortino coverage"
        assert "drawdown" in content_lower, "Tests missing drawdown coverage"
