"""
Test skill: risk-metrics-calculation
Verify that the Agent adds CVaR, Sortino, Calmar, max drawdown duration,
Ulcer Index, and Omega ratio to pyfolio — risk_metrics module, timeseries
integration, and tear-sheet output.
"""

import os
import re
import ast
import subprocess
import pytest


class TestRiskMetricsCalculation:
    REPO_DIR = "/workspace/pyfolio"

    # ────────────────── helpers ──────────────────

    def _read(self, rel_path):
        fpath = os.path.join(self.REPO_DIR, rel_path)
        with open(fpath, "r") as f:
            return f.read()

    def _exists(self, rel_path):
        return os.path.isfile(os.path.join(self.REPO_DIR, rel_path))

    def _parse(self, rel_path):
        fpath = os.path.join(self.REPO_DIR, rel_path)
        with open(fpath, "r") as f:
            return ast.parse(f.read())

    # === File Path Checks ===

    def test_risk_metrics_module_exists(self):
        """pyfolio/risk_metrics.py must exist"""
        assert self._exists("pyfolio/risk_metrics.py")

    def test_risk_metrics_test_exists(self):
        """pyfolio/tests/test_risk_metrics.py must exist"""
        assert self._exists("pyfolio/tests/test_risk_metrics.py")

    def test_timeseries_module_exists(self):
        """pyfolio/timeseries.py must exist"""
        assert self._exists("pyfolio/timeseries.py")

    # === Semantic Checks — Function Definitions ===

    def test_conditional_var_function(self):
        """conditional_var function must be defined"""
        src = self._read("pyfolio/risk_metrics.py")
        assert re.search(r'def\s+conditional_var\s*\(', src), (
            "conditional_var function not found"
        )

    def test_sortino_ratio_function(self):
        """sortino_ratio function must be defined"""
        src = self._read("pyfolio/risk_metrics.py")
        assert re.search(r'def\s+sortino_ratio\s*\(', src), (
            "sortino_ratio function not found"
        )

    def test_calmar_ratio_function(self):
        """calmar_ratio function must be defined"""
        src = self._read("pyfolio/risk_metrics.py")
        assert re.search(r'def\s+calmar_ratio\s*\(', src), (
            "calmar_ratio function not found"
        )

    def test_max_drawdown_duration_function(self):
        """max_drawdown_duration function must be defined"""
        src = self._read("pyfolio/risk_metrics.py")
        assert re.search(r'def\s+max_drawdown_duration\s*\(', src), (
            "max_drawdown_duration function not found"
        )

    def test_ulcer_index_function(self):
        """ulcer_index function must be defined"""
        src = self._read("pyfolio/risk_metrics.py")
        assert re.search(r'def\s+ulcer_index\s*\(', src), (
            "ulcer_index function not found"
        )

    def test_omega_ratio_function(self):
        """omega_ratio function must be defined"""
        src = self._read("pyfolio/risk_metrics.py")
        assert re.search(r'def\s+omega_ratio\s*\(', src), (
            "omega_ratio function not found"
        )

    # === Semantic Checks — conditional_var ===

    def test_cvar_supports_historical_method(self):
        """conditional_var must support method='historical'"""
        src = self._read("pyfolio/risk_metrics.py")
        assert "historical" in src, (
            "conditional_var missing 'historical' method support"
        )

    def test_cvar_supports_gaussian_method(self):
        """conditional_var must support method='gaussian'"""
        src = self._read("pyfolio/risk_metrics.py")
        assert "gaussian" in src, (
            "conditional_var missing 'gaussian' method support"
        )

    def test_cvar_confidence_parameter(self):
        """conditional_var must have a confidence parameter (default 0.95)"""
        src = self._read("pyfolio/risk_metrics.py")
        assert "confidence" in src or "0.95" in src, (
            "conditional_var missing confidence parameter"
        )

    # === Semantic Checks — sortino_ratio ===

    def test_sortino_uses_downside_deviation(self):
        """sortino_ratio must compute downside deviation, not total std"""
        src = self._read("pyfolio/risk_metrics.py")
        assert "downside" in src.lower() or "required_return" in src, (
            "sortino_ratio should use downside deviation"
        )

    def test_sortino_annualization(self):
        """sortino_ratio must accept annualization_factor"""
        src = self._read("pyfolio/risk_metrics.py")
        assert "annualization" in src or "252" in src, (
            "sortino_ratio missing annualization factor"
        )

    # === Semantic Checks — timeseries integration ===

    def test_timeseries_includes_cvar(self):
        """timeseries.py must include Conditional VaR in perf_stats"""
        src = self._read("pyfolio/timeseries.py")
        assert "conditional_var" in src or "Conditional VaR" in src or "CVaR" in src, (
            "Conditional VaR not integrated into timeseries.py"
        )

    def test_timeseries_includes_sortino(self):
        """timeseries.py must include Sortino ratio in perf_stats"""
        src = self._read("pyfolio/timeseries.py")
        assert "sortino" in src.lower(), (
            "Sortino ratio not integrated into timeseries.py"
        )

    def test_timeseries_includes_ulcer(self):
        """timeseries.py must include Ulcer Index in perf_stats"""
        src = self._read("pyfolio/timeseries.py")
        assert "ulcer" in src.lower(), (
            "Ulcer Index not integrated into timeseries.py"
        )

    # === Semantic Checks — tears.py integration ===

    def test_tears_advanced_risk_section(self):
        """tears.py must display Advanced Risk Metrics section"""
        src = self._read("pyfolio/tears.py")
        assert "Advanced Risk" in src or "risk_metrics" in src, (
            "Advanced Risk Metrics section not found in tears.py"
        )

    # === Functional Checks ===

    def test_risk_metrics_importable(self):
        """All risk metric functions must be importable"""
        result = subprocess.run(
            ["python", "-c",
             "from pyfolio.risk_metrics import ("
             "conditional_var, sortino_ratio, calmar_ratio, "
             "max_drawdown_duration, ulcer_index, omega_ratio); "
             "print('OK')"],
            capture_output=True, text=True, cwd=self.REPO_DIR, timeout=30,
        )
        assert "OK" in result.stdout, (
            f"Import failed:\n{result.stdout}\n{result.stderr}"
        )

    def test_cvar_returns_positive(self):
        """conditional_var should return a positive number for a loss scenario"""
        result = subprocess.run(
            ["python", "-c",
             "import pandas as pd; import numpy as np; "
             "from pyfolio.risk_metrics import conditional_var; "
             "np.random.seed(42); "
             "rets = pd.Series(np.random.normal(0.0005, 0.015, 500)); "
             "cvar = conditional_var(rets, 0.95, 'historical'); "
             "assert cvar > 0, f'CVaR should be positive, got {cvar}'; "
             "print('OK')"],
            capture_output=True, text=True, cwd=self.REPO_DIR, timeout=30,
        )
        assert "OK" in result.stdout, (
            f"CVaR test failed:\n{result.stdout}\n{result.stderr}"
        )

    def test_ulcer_index_zero_for_monotonic(self):
        """ulcer_index should return 0 for a monotonically increasing series"""
        result = subprocess.run(
            ["python", "-c",
             "import pandas as pd; import numpy as np; "
             "from pyfolio.risk_metrics import ulcer_index; "
             "rets = pd.Series([0.01]*100); "
             "ui = ulcer_index(rets); "
             "assert abs(ui) < 1e-9, f'Ulcer Index should be 0, got {ui}'; "
             "print('OK')"],
            capture_output=True, text=True, cwd=self.REPO_DIR, timeout=30,
        )
        assert "OK" in result.stdout, (
            f"Ulcer Index test failed:\n{result.stdout}\n{result.stderr}"
        )

    def test_unit_tests_pass(self):
        """pyfolio/tests/test_risk_metrics.py must pass"""
        result = subprocess.run(
            ["python", "-m", "pytest",
             "pyfolio/tests/test_risk_metrics.py",
             "-v", "--tb=short"],
            capture_output=True, text=True, cwd=self.REPO_DIR, timeout=120,
        )
        assert result.returncode == 0, (
            f"Tests failed:\n{result.stdout}\n{result.stderr}"
        )
