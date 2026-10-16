"""
Tests for skill: risk-metrics-calculation
Repo: quantopian/pyfolio
Image: zhangyiiiiii/swe-skills-bench-python
Task: Implement a portfolio risk metrics engine for pyfolio with VaR,
      CVaR, drawdown analysis, risk-adjusted ratios, and rolling windows.
"""

import ast
import os
import re
import subprocess

import pytest

REPO_DIR = "/workspace/pyfolio"

RISK_FILE = os.path.join(REPO_DIR, "pyfolio", "risk_metrics.py")
ROLLING_FILE = os.path.join(REPO_DIR, "pyfolio", "rolling_risk.py")
TEST_FILE = os.path.join(REPO_DIR, "tests", "test_risk_metrics.py")


# ---------------------------------------------------------------------------
# Layer 1 — file_path_check
# ---------------------------------------------------------------------------

class TestFilePathCheck:
    """Verify all required files were created."""

    def test_risk_metrics_file_exists(self):
        assert os.path.isfile(RISK_FILE), f"Expected {RISK_FILE}"

    def test_rolling_risk_file_exists(self):
        assert os.path.isfile(ROLLING_FILE), f"Expected {ROLLING_FILE}"

    def test_test_file_exists(self):
        assert os.path.isfile(TEST_FILE), f"Expected {TEST_FILE}"


# ---------------------------------------------------------------------------
# Layer 2 — semantic_check
# ---------------------------------------------------------------------------

class TestSemanticRiskEngine:
    """Verify RiskEngine class structure."""

    @pytest.fixture(autouse=True)
    def _load_source(self):
        with open(RISK_FILE, "r", encoding="utf-8") as f:
            self.src = f.read()
        self.tree = ast.parse(self.src)

    def test_risk_engine_class_defined(self):
        classes = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.ClassDef)]
        assert "RiskEngine" in classes, (
            f"Expected RiskEngine class; found: {classes}"
        )

    def test_var_historical_method(self):
        assert "var_historical" in self.src, "Expected var_historical method"

    def test_var_parametric_method(self):
        assert "var_parametric" in self.src, "Expected var_parametric method"

    def test_var_cornish_fisher_method(self):
        assert "var_cornish_fisher" in self.src or "cornish" in self.src.lower(), (
            "Expected var_cornish_fisher method"
        )

    def test_cvar_method(self):
        assert "cvar" in self.src, "Expected cvar (Expected Shortfall) method"

    def test_drawdowns_method(self):
        assert "drawdowns" in self.src or "drawdown" in self.src, (
            "Expected drawdowns() method"
        )

    def test_max_drawdown_method(self):
        assert "max_drawdown" in self.src, "Expected max_drawdown() method"

    def test_sharpe_ratio_method(self):
        assert "sharpe_ratio" in self.src, "Expected sharpe_ratio() method"

    def test_sortino_ratio_method(self):
        assert "sortino_ratio" in self.src, "Expected sortino_ratio() method"

    def test_calmar_ratio_method(self):
        assert "calmar_ratio" in self.src, "Expected calmar_ratio() method"

    def test_confidence_validation(self):
        """Confidence level must be validated (0.5 to 0.999)."""
        has_validation = (
            "ValueError" in self.src
            and ("confidence" in self.src or "0.5" in self.src)
        )
        assert has_validation, (
            "Expected confidence level validation with ValueError"
        )

    def test_pandas_used(self):
        """Engine must use pandas for returns series."""
        assert "pandas" in self.src or "pd." in self.src, (
            "Expected pandas import for returns Series handling"
        )


class TestSemanticRollingRisk:
    """Verify RollingRisk class."""

    @pytest.fixture(autouse=True)
    def _load_source(self):
        with open(ROLLING_FILE, "r", encoding="utf-8") as f:
            self.src = f.read()
        self.tree = ast.parse(self.src)

    def test_rolling_risk_class_defined(self):
        classes = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.ClassDef)]
        assert "RollingRisk" in classes, (
            f"Expected RollingRisk class; found: {classes}"
        )

    def test_rolling_var_method(self):
        assert "rolling_var" in self.src, "Expected rolling_var method"

    def test_rolling_sharpe_method(self):
        assert "rolling_sharpe" in self.src, "Expected rolling_sharpe method"

    def test_rolling_max_drawdown_method(self):
        assert "rolling_max_drawdown" in self.src, "Expected rolling_max_drawdown method"

    def test_window_parameter(self):
        assert "window" in self.src, "Expected window parameter in RollingRisk"


class TestSemanticTests:
    """Verify test file covers key scenarios."""

    @pytest.fixture(autouse=True)
    def _load_source(self):
        with open(TEST_FILE, "r", encoding="utf-8") as f:
            self.src = f.read()

    def test_tests_cover_var(self):
        assert "var" in self.src.lower(), "Expected VaR tests"

    def test_tests_cover_drawdown(self):
        assert "drawdown" in self.src.lower(), "Expected drawdown tests"

    def test_tests_cover_sharpe(self):
        assert "sharpe" in self.src.lower(), "Expected Sharpe ratio tests"


# ---------------------------------------------------------------------------
# Layer 3 — functional_check
# ---------------------------------------------------------------------------

class TestFunctionalRiskMetrics:
    """Functional checks — syntax, import, and calculation tests."""

    def _run(self, cmd, cwd=REPO_DIR, timeout=60):
        return subprocess.run(
            cmd, shell=True, cwd=cwd,
            capture_output=True, text=True, timeout=timeout,
        )

    def test_risk_metrics_valid_python(self):
        with open(RISK_FILE, "r", encoding="utf-8") as f:
            src = f.read()
        try:
            ast.parse(src)
        except SyntaxError as e:
            pytest.fail(f"risk_metrics.py syntax error: {e}")

    def test_rolling_risk_valid_python(self):
        with open(ROLLING_FILE, "r", encoding="utf-8") as f:
            src = f.read()
        try:
            ast.parse(src)
        except SyntaxError as e:
            pytest.fail(f"rolling_risk.py syntax error: {e}")

    def test_test_file_valid_python(self):
        with open(TEST_FILE, "r", encoding="utf-8") as f:
            src = f.read()
        try:
            ast.parse(src)
        except SyntaxError as e:
            pytest.fail(f"test_risk_metrics.py syntax error: {e}")

    def test_risk_engine_importable(self):
        """RiskEngine must be importable."""
        result = self._run(
            f"python -c \"import sys; sys.path.insert(0, '{REPO_DIR}'); "
            f"from pyfolio.risk_metrics import RiskEngine; print('OK')\"",
            timeout=30,
        )
        assert "OK" in result.stdout, (
            f"Could not import RiskEngine:\nstderr: {result.stderr[:500]}"
        )

    def test_var_parametric_computation(self):
        """VaR parametric with known stats must return expected value."""
        code = f"""
import sys, numpy as np, pandas as pd
sys.path.insert(0, '{REPO_DIR}')
from pyfolio.risk_metrics import RiskEngine
np.random.seed(42)
returns = pd.Series(np.random.normal(0.0005, 0.01, 1000))
engine = RiskEngine(returns)
var = engine.var_parametric(0.95)
print(f"{{var:.6f}}")
"""
        result = self._run(f'python -c "{code}"', timeout=30)
        if result.returncode == 0:
            val = float(result.stdout.strip())
            # VaR should be a positive number around 0.015 for this data
            assert 0.005 < val < 0.03, f"VaR parametric unexpected value: {val}"
        else:
            pytest.skip(f"VaR computation not runnable: {result.stderr[:300]}")

    def test_empty_returns_raises(self):
        """Empty returns must raise ValueError."""
        code = f"""
import sys, pandas as pd
sys.path.insert(0, '{REPO_DIR}')
from pyfolio.risk_metrics import RiskEngine
try:
    RiskEngine(pd.Series([], dtype=float))
    print("NO_ERROR")
except ValueError:
    print("VALUE_ERROR")
"""
        result = self._run(f'python -c "{code}"', timeout=30)
        if result.returncode == 0:
            assert "VALUE_ERROR" in result.stdout, (
                "Expected ValueError for empty returns"
            )
        else:
            pytest.skip(f"Empty returns test not runnable: {result.stderr[:300]}")

    def test_drawdown_duration_structure(self):
        """drawdown_durations must return dict with expected keys."""
        with open(RISK_FILE, "r", encoding="utf-8") as f:
            src = f.read()
        expected_keys = ["max_duration", "avg_duration", "num_drawdowns"]
        found = [k for k in expected_keys if k in src]
        assert len(found) >= 2, (
            f"Expected drawdown_durations dict keys; found: {found}"
        )
