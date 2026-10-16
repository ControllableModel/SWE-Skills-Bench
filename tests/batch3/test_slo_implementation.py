"""
Tests for the slo-implementation skill.

Validates that SLO configuration validation, burn rate calculation,
and error budget tracking were implemented for slo-generator.

Repo: slo-generator (https://github.com/google/slo-generator)
"""

import os
import re
import subprocess
import sys

REPO_DIR = "/workspace/slo-generator"


class TestFilePathCheck:
    """Verify all required files were created."""

    def test_burn_rate_exists(self):
        path = os.path.join(REPO_DIR, "slo_generator", "burn_rate.py")
        assert os.path.isfile(path), f"Expected burn_rate.py at {path}"

    def test_error_budget_exists(self):
        path = os.path.join(REPO_DIR, "slo_generator", "error_budget.py")
        assert os.path.isfile(path), f"Expected error_budget.py at {path}"

    def test_config_validator_exists(self):
        path = os.path.join(
            REPO_DIR, "slo_generator", "slo_config_validator.py",
        )
        assert os.path.isfile(path), f"Expected slo_config_validator.py"

    def test_burn_rate_test_exists(self):
        path = os.path.join(REPO_DIR, "tests", "unit", "test_burn_rate.py")
        assert os.path.isfile(path), f"Expected test_burn_rate.py"

    def test_error_budget_test_exists(self):
        path = os.path.join(REPO_DIR, "tests", "unit", "test_error_budget.py")
        assert os.path.isfile(path), f"Expected test_error_budget.py"


class TestSemanticConfigValidator:
    """Verify SLO configuration schema validation."""

    def _read(self):
        path = os.path.join(
            REPO_DIR, "slo_generator", "slo_config_validator.py",
        )
        with open(path, "r") as f:
            return f.read()

    def test_schema_fields(self):
        content = self._read()
        for field in ["name", "service", "target", "window"]:
            assert field in content, f"Expected field '{field}' in config schema"

    def test_sli_types(self):
        content = self._read()
        for sli in ["availability", "latency"]:
            assert sli in content, f"Expected sli_type '{sli}'"

    def test_target_validation(self):
        content = self._read()
        assert re.search(r"0\.0.*1\.0|target|exclusive", content), (
            "Expected target validation (0.0-1.0 exclusive)"
        )

    def test_availability_minimum(self):
        content = self._read()
        assert re.search(r"0\.9|availability.*target", content), (
            "Expected availability SLI minimum target >= 0.9"
        )

    def test_slo_config_error(self):
        content = self._read()
        assert re.search(r"SLOConfigError|SloConfigError", content), (
            "Expected SLOConfigError exception class"
        )

    def test_window_options(self):
        content = self._read()
        for window in ["rolling_7d", "rolling_28d", "rolling_30d"]:
            assert window in content, f"Expected window option '{window}'"


class TestSemanticBurnRate:
    """Verify burn rate calculation and multi-window alerting."""

    def _read(self):
        path = os.path.join(REPO_DIR, "slo_generator", "burn_rate.py")
        with open(path, "r") as f:
            return f.read()

    def test_class_definition(self):
        content = self._read()
        assert re.search(r"class\s+BurnRateCalculator", content), (
            "Expected BurnRateCalculator class"
        )

    def test_burn_rate_formula(self):
        content = self._read()
        assert re.search(r"error_rate|error_budget_rate|burn.*rate", content), (
            "Expected burn_rate = error_rate / error_budget_rate"
        )

    def test_multi_window(self):
        content = self._read()
        assert re.search(r"short.*window|long.*window|multi.*window", content, re.IGNORECASE), (
            "Expected multi-window burn rate (short + long)"
        )

    def test_critical_severity(self):
        content = self._read()
        assert re.search(r"critical|14\.4", content, re.IGNORECASE), (
            "Expected critical severity with burn_rate_threshold=14.4"
        )

    def test_warning_severity(self):
        content = self._read()
        assert re.search(r"warning|6\.0", content, re.IGNORECASE), (
            "Expected warning severity with burn_rate_threshold=6.0"
        )

    def test_ticket_severity(self):
        content = self._read()
        assert re.search(r"ticket|3\.0", content, re.IGNORECASE), (
            "Expected ticket severity with burn_rate_threshold=3.0"
        )

    def test_evaluate_alerts(self):
        content = self._read()
        assert re.search(r"def\s+evaluate_alerts", content), (
            "Expected evaluate_alerts method"
        )

    def test_both_windows_must_exceed(self):
        content = self._read()
        assert re.search(r"both|and|short.*long", content, re.IGNORECASE), (
            "Expected both windows must exceed thresholds for alert to fire"
        )


class TestSemanticErrorBudget:
    """Verify error budget tracking."""

    def _read(self):
        path = os.path.join(REPO_DIR, "slo_generator", "error_budget.py")
        with open(path, "r") as f:
            return f.read()

    def test_class_definition(self):
        content = self._read()
        assert re.search(r"class\s+ErrorBudgetTracker", content), (
            "Expected ErrorBudgetTracker class"
        )

    def test_total_budget(self):
        content = self._read()
        assert re.search(r"total_budget|total", content), (
            "Expected total_budget calculation"
        )

    def test_consumed_budget(self):
        content = self._read()
        assert re.search(r"consumed_budget|consumed", content), (
            "Expected consumed_budget tracking"
        )

    def test_remaining_budget(self):
        content = self._read()
        assert re.search(r"remaining_budget|remaining", content), (
            "Expected remaining_budget calculation"
        )

    def test_remaining_percentage(self):
        content = self._read()
        assert re.search(r"remaining_percentage|percent", content), (
            "Expected remaining_percentage computation"
        )

    def test_consumption_rate(self):
        content = self._read()
        assert re.search(r"consumption_rate", content), (
            "Expected consumption_rate (budget consumed per hour)"
        )

    def test_exhaustion_date(self):
        content = self._read()
        assert re.search(r"exhaustion_date|exhaustion", content), (
            "Expected exhaustion_date projection (None if rate <= 0)"
        )


class TestFunctionalPythonSyntax:
    """Validate Python files compile and tests pass."""

    def test_burn_rate_syntax(self):
        path = os.path.join(REPO_DIR, "slo_generator", "burn_rate.py")
        with open(path, "r") as f:
            content = f.read()
        compile(content, path, "exec")

    def test_error_budget_syntax(self):
        path = os.path.join(REPO_DIR, "slo_generator", "error_budget.py")
        with open(path, "r") as f:
            content = f.read()
        compile(content, path, "exec")

    def test_config_validator_syntax(self):
        path = os.path.join(
            REPO_DIR, "slo_generator", "slo_config_validator.py",
        )
        with open(path, "r") as f:
            content = f.read()
        compile(content, path, "exec")

    def test_agent_tests_pass(self):
        test_paths = [
            os.path.join(REPO_DIR, "tests", "unit", "test_burn_rate.py"),
            os.path.join(REPO_DIR, "tests", "unit", "test_error_budget.py"),
        ]
        existing = [p for p in test_paths if os.path.isfile(p)]
        if existing:
            result = subprocess.run(
                [sys.executable, "-m", "pytest"] + existing + ["-v", "--tb=short"],
                cwd=REPO_DIR,
                capture_output=True,
                text=True,
                timeout=120,
            )
            assert result.returncode == 0, (
                f"Agent tests failed:\n{result.stdout[-1000:]}\n{result.stderr[-500:]}"
            )
