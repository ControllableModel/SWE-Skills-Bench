"""
Test skill: slo-implementation
Verify that the Agent implements a Multi-Window SLO Evaluator for slo-generator —
BurnRateCalculator (WindowResult properties, BurnRateAlert, multi-window alerting),
MultiWindowSloEvaluator (backend call per window, SloEvaluationReport).
"""

import os
import re
import subprocess
import pytest


class TestSloImplementation:
    REPO_DIR = "/workspace/slo-generator"

    # ────── helpers ──────

    def _read(self, rel_path):
        fpath = os.path.join(self.REPO_DIR, rel_path)
        with open(fpath, "r") as f:
            return f.read()

    def _exists(self, rel_path):
        return os.path.isfile(os.path.join(self.REPO_DIR, rel_path))

    # === File Path Checks ===

    def test_multi_window_exists(self):
        """multi_window.py must exist"""
        assert self._exists("slo_generator/evaluators/multi_window.py")

    def test_burnrate_exists(self):
        """burnrate.py must exist"""
        assert self._exists("slo_generator/evaluators/burnrate.py")

    def test_unit_test_exists(self):
        """test_multi_window_evaluator.py must exist"""
        assert self._exists("tests/unit/test_multi_window_evaluator.py")

    # === Semantic Checks — burnrate.py ===

    def test_window_result_dataclass(self):
        """WindowResult dataclass must be defined"""
        src = self._read("slo_generator/evaluators/burnrate.py")
        assert "WindowResult" in src
        assert "dataclass" in src

    def test_window_result_properties(self):
        """WindowResult must have error_rate, sli, error_budget_consumed, compliant, burnrate"""
        src = self._read("slo_generator/evaluators/burnrate.py")
        for prop in ["error_rate", "sli", "error_budget_consumed", "compliant", "burnrate"]:
            assert prop in src, f"Missing property: {prop}"

    def test_window_result_fields(self):
        """WindowResult must have window_hours, good_events, total_events, slo_target"""
        src = self._read("slo_generator/evaluators/burnrate.py")
        for field in ["window_hours", "good_events", "total_events", "slo_target"]:
            assert field in src, f"Missing field: {field}"

    def test_burnrate_alert_dataclass(self):
        """BurnRateAlert dataclass must be defined"""
        src = self._read("slo_generator/evaluators/burnrate.py")
        assert "BurnRateAlert" in src

    def test_burnrate_alert_fields(self):
        """BurnRateAlert must have severity, short/long window hours, threshold, triggered"""
        src = self._read("slo_generator/evaluators/burnrate.py")
        for field in ["severity", "short_window", "long_window", "threshold", "triggered"]:
            assert field in src.lower(), f"Missing field: {field}"

    def test_burnrate_calculator_class(self):
        """BurnRateCalculator class must be defined"""
        src = self._read("slo_generator/evaluators/burnrate.py")
        assert re.search(r'class\s+BurnRateCalculator', src)

    def test_alert_configs(self):
        """Must define alert configs: (1h,6h,14.4), (6h,24h,6.0), (24h,72h,3.0)"""
        src = self._read("slo_generator/evaluators/burnrate.py")
        assert "14.4" in src
        assert "6.0" in src or "6," in src
        assert "3.0" in src or "3," in src

    def test_compute_alerts_method(self):
        """compute_alerts method must be defined"""
        src = self._read("slo_generator/evaluators/burnrate.py")
        assert "compute_alerts" in src

    def test_alert_severities(self):
        """Must define page and ticket severity levels"""
        src = self._read("slo_generator/evaluators/burnrate.py")
        assert "page" in src
        assert "ticket" in src

    # === Semantic Checks — multi_window.py ===

    def test_multi_window_evaluator_class(self):
        """MultiWindowSloEvaluator class must be defined"""
        src = self._read("slo_generator/evaluators/multi_window.py")
        assert re.search(r'class\s+MultiWindowSloEvaluator', src)

    def test_default_windows(self):
        """Must define default windows [1, 6, 24, 72]"""
        src = self._read("slo_generator/evaluators/multi_window.py")
        for w in ["1", "6", "24", "72"]:
            assert w in src

    def test_evaluate_method(self):
        """evaluate method must exist"""
        src = self._read("slo_generator/evaluators/multi_window.py")
        assert re.search(r'def\s+evaluate\b', src)

    def test_slo_evaluation_report(self):
        """SloEvaluationReport must be defined"""
        src = self._read("slo_generator/evaluators/multi_window.py")
        assert "SloEvaluationReport" in src

    def test_overall_compliant_property(self):
        """SloEvaluationReport must have overall_compliant"""
        src = self._read("slo_generator/evaluators/multi_window.py")
        assert "overall_compliant" in src

    def test_worst_window_property(self):
        """SloEvaluationReport must have worst_window"""
        src = self._read("slo_generator/evaluators/multi_window.py")
        assert "worst_window" in src

    def test_to_dict_method(self):
        """SloEvaluationReport must have to_dict"""
        src = self._read("slo_generator/evaluators/multi_window.py")
        assert "to_dict" in src

    def test_sli_backend_protocol(self):
        """SliBackend protocol must be defined"""
        src = self._read("slo_generator/evaluators/multi_window.py")
        assert "SliBackend" in src or "Protocol" in src

    # === Functional Checks ===

    def test_python_syntax_multi_window(self):
        """multi_window.py must have valid syntax"""
        result = subprocess.run(
            ["python", "-c",
             "import py_compile; py_compile.compile('slo_generator/evaluators/multi_window.py', doraise=True)"],
            capture_output=True, text=True, cwd=self.REPO_DIR, timeout=30,
        )
        assert result.returncode == 0, f"Syntax error:\n{result.stderr}"

    def test_python_syntax_burnrate(self):
        """burnrate.py must have valid syntax"""
        result = subprocess.run(
            ["python", "-c",
             "import py_compile; py_compile.compile('slo_generator/evaluators/burnrate.py', doraise=True)"],
            capture_output=True, text=True, cwd=self.REPO_DIR, timeout=30,
        )
        assert result.returncode == 0, f"Syntax error:\n{result.stderr}"

    def test_unit_tests_pass(self):
        """Unit tests must pass"""
        result = subprocess.run(
            ["python", "-m", "pytest",
             "tests/unit/test_multi_window_evaluator.py",
             "-v", "--tb=short"],
            capture_output=True, text=True, cwd=self.REPO_DIR, timeout=120,
        )
        assert result.returncode == 0, (
            f"Tests failed:\n{result.stdout}\n{result.stderr}"
        )
