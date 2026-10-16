"""
Test skill: slo-implementation
Verify that the Agent implements multi-window SLO evaluation with
error budget calculation, burn rate alerting (fast-burn and slow-burn),
compliance summary, and Python best practices.
"""

import os
import re
import ast
import subprocess
import pytest


class TestSloImplementation:
    REPO_DIR = "/workspace/slo-generator"

    # === File Path Checks ===

    def test_multi_window_py_exists(self):
        """Verify multi_window.py exists"""
        path = os.path.join(self.REPO_DIR, "slo_generator", "multi_window.py")
        assert os.path.exists(path), f"multi_window.py not found at {path}"

    def test_burn_rate_py_exists(self):
        """Verify burn_rate.py exists"""
        path = os.path.join(self.REPO_DIR, "slo_generator", "burn_rate.py")
        assert os.path.exists(path), f"burn_rate.py not found at {path}"

    # === Semantic Checks ===

    def test_multi_window_evaluation(self):
        """Verify multi-window SLO evaluation logic"""
        path = os.path.join(self.REPO_DIR, "slo_generator", "multi_window.py")
        with open(path) as f:
            content = f.read()

        window_indicators = [
            "window", "Window", "evaluate", "Evaluate",
            "period", "1h", "6h", "1d", "3d",
        ]
        found = [ind for ind in window_indicators if ind in content]
        assert len(found) >= 2, (
            f"Should implement multi-window evaluation. Found: {found}"
        )

    def test_error_budget_calculation(self):
        """Verify error budget calculation"""
        combined = ""
        for fname in ["multi_window.py", "burn_rate.py"]:
            path = os.path.join(self.REPO_DIR, "slo_generator", fname)
            if os.path.exists(path):
                with open(path) as f:
                    combined += f.read()

        budget_indicators = [
            "error_budget", "ErrorBudget", "budget",
            "remaining", "consumed", "exhausted",
        ]
        found = [ind for ind in budget_indicators if ind in combined]
        assert len(found) >= 2, (
            f"Should calculate error budget. Found: {found}"
        )

    def test_burn_rate_calculation(self):
        """Verify burn rate calculation"""
        path = os.path.join(self.REPO_DIR, "slo_generator", "burn_rate.py")
        with open(path) as f:
            content = f.read()

        burn_indicators = [
            "burn_rate", "BurnRate", "burn", "rate",
        ]
        found = [ind for ind in burn_indicators if ind in content]
        assert len(found) >= 2, (
            f"Should calculate burn rate. Found: {found}"
        )

    def test_fast_and_slow_burn_alerting(self):
        """Verify fast-burn and slow-burn alerting thresholds"""
        path = os.path.join(self.REPO_DIR, "slo_generator", "burn_rate.py")
        with open(path) as f:
            content = f.read()

        alert_indicators = [
            "fast", "slow", "alert", "threshold",
            "critical", "warning", "severity",
        ]
        found = [ind for ind in alert_indicators if ind in content]
        assert len(found) >= 3, (
            f"Should support fast-burn and slow-burn alerting. Found: {found}"
        )

    def test_exhausted_budget_flagging(self):
        """Verify flagging when error budget is exhausted"""
        combined = ""
        for fname in ["multi_window.py", "burn_rate.py"]:
            path = os.path.join(self.REPO_DIR, "slo_generator", fname)
            if os.path.exists(path):
                with open(path) as f:
                    combined += f.read()

        exhaust_indicators = [
            "exhausted", "depleted", "exceeded", "violation",
            "breached", "<= 0", "< 0", "remaining",
        ]
        found = [ind for ind in exhaust_indicators if ind in combined]
        assert len(found) >= 1, (
            f"Should flag exhausted error budget. Found: {found}"
        )

    def test_compliance_summary(self):
        """Verify compliance summary generation"""
        combined = ""
        for fname in ["multi_window.py", "burn_rate.py"]:
            path = os.path.join(self.REPO_DIR, "slo_generator", fname)
            if os.path.exists(path):
                with open(path) as f:
                    combined += f.read()

        summary_indicators = [
            "summary", "compliance", "report", "status",
            "compliant", "result",
        ]
        found = [ind for ind in summary_indicators if ind in combined]
        assert len(found) >= 2, (
            f"Should produce compliance summary. Found: {found}"
        )

    def test_slo_target_parameter(self):
        """Verify SLO target (e.g. 99.9%) is configurable"""
        combined = ""
        for fname in ["multi_window.py", "burn_rate.py"]:
            path = os.path.join(self.REPO_DIR, "slo_generator", fname)
            if os.path.exists(path):
                with open(path) as f:
                    combined += f.read()

        target_indicators = [
            "target", "objective", "slo", "99.9", "99.5",
            "threshold",
        ]
        found = [ind for ind in target_indicators if ind in combined]
        assert len(found) >= 2, (
            f"Should accept configurable SLO target. Found: {found}"
        )

    # === Functional Checks ===

    def test_multi_window_valid_python(self):
        """Verify multi_window.py is valid Python"""
        path = os.path.join(self.REPO_DIR, "slo_generator", "multi_window.py")
        with open(path) as f:
            source = f.read()
        try:
            ast.parse(source)
        except SyntaxError as e:
            pytest.fail(f"multi_window.py has syntax error: {e}")

    def test_burn_rate_valid_python(self):
        """Verify burn_rate.py is valid Python"""
        path = os.path.join(self.REPO_DIR, "slo_generator", "burn_rate.py")
        with open(path) as f:
            source = f.read()
        try:
            ast.parse(source)
        except SyntaxError as e:
            pytest.fail(f"burn_rate.py has syntax error: {e}")

    def test_multi_window_importable(self):
        """Verify multi_window.py can be imported"""
        result = subprocess.run(
            ["python", "-c",
             f"import sys; sys.path.insert(0, '{self.REPO_DIR}'); "
             "from slo_generator.multi_window import *"],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0, (
            f"multi_window.py import failed: {result.stderr}"
        )

    def test_burn_rate_importable(self):
        """Verify burn_rate.py can be imported"""
        result = subprocess.run(
            ["python", "-c",
             f"import sys; sys.path.insert(0, '{self.REPO_DIR}'); "
             "from slo_generator.burn_rate import *"],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0, (
            f"burn_rate.py import failed: {result.stderr}"
        )

    def test_callable_functions_defined(self):
        """Verify modules define callable functions or classes"""
        combined = ""
        for fname in ["multi_window.py", "burn_rate.py"]:
            path = os.path.join(self.REPO_DIR, "slo_generator", fname)
            with open(path) as f:
                combined += f.read()

        defs = re.findall(r"^(?:def |class )\w+", combined, re.MULTILINE)
        assert len(defs) >= 3, (
            f"Should define at least 3 functions/classes. Found: {defs}"
        )
