"""
Tests for skill: slo-implementation
Repo: google/slo-generator
Image: zhangyiiiiii/swe-skills-bench-python
Task: Implement an SLO framework with SLI computation, error budgets,
      multi-window burn-rate alerting, and status report generation.
"""

import ast
import os
import sys
from datetime import datetime, timedelta

import pytest

REPO_DIR = "/workspace/slo-generator"
PKG_DIR = os.path.join(REPO_DIR, "slo_generator")

SLI_FILE = os.path.join(PKG_DIR, "sli.py")
SLO_FILE = os.path.join(PKG_DIR, "slo.py")
BURN_RATE_FILE = os.path.join(PKG_DIR, "burn_rate.py")
REPORT_FILE = os.path.join(PKG_DIR, "report.py")


# ---------------------------------------------------------------------------
# Layer 1 — file_path_check
# ---------------------------------------------------------------------------

class TestFilePathCheck:
    """Verify all required SLO framework files exist."""

    def test_sli_exists(self):
        assert os.path.isfile(SLI_FILE), f"Missing {SLI_FILE}"

    def test_slo_exists(self):
        assert os.path.isfile(SLO_FILE), f"Missing {SLO_FILE}"

    def test_burn_rate_exists(self):
        assert os.path.isfile(BURN_RATE_FILE), f"Missing {BURN_RATE_FILE}"

    def test_report_exists(self):
        assert os.path.isfile(REPORT_FILE), f"Missing {REPORT_FILE}"


# ---------------------------------------------------------------------------
# Layer 2 — semantic_check
# ---------------------------------------------------------------------------

class TestSemanticSLI:
    """Verify SLI definitions module structure."""

    @pytest.fixture(autouse=True)
    def _load(self):
        with open(SLI_FILE, "r", encoding="utf-8") as f:
            self.src = f.read()
        self.tree = ast.parse(self.src)

    def test_availability_sli_class(self):
        classes = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.ClassDef)]
        assert "AvailabilitySLI" in classes, f"Expected AvailabilitySLI; found {classes}"

    def test_latency_sli_class(self):
        classes = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.ClassDef)]
        assert "LatencySLI" in classes, f"Expected LatencySLI; found {classes}"

    def test_value_method(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "value" in funcs, f"Expected value() method; found {funcs}"

    def test_from_prometheus_factory(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "from_prometheus" in funcs, f"Expected from_prometheus; found {funcs}"

    def test_value_error_validation(self):
        assert "ValueError" in self.src, "SLI classes should validate inputs with ValueError"


class TestSemanticSLO:
    """Verify SLO tracking module structure."""

    @pytest.fixture(autouse=True)
    def _load(self):
        with open(SLO_FILE, "r", encoding="utf-8") as f:
            self.src = f.read()
        self.tree = ast.parse(self.src)

    def test_slo_class(self):
        classes = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.ClassDef)]
        assert "SLO" in classes, f"Expected SLO class; found {classes}"

    def test_record_method(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "record" in funcs, f"Expected record(); found {funcs}"

    def test_achievement_method(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "achievement" in funcs, f"Expected achievement(); found {funcs}"

    def test_error_budget_methods(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "error_budget_total" in funcs, f"Expected error_budget_total; found {funcs}"
        assert "error_budget_remaining" in funcs, f"Expected error_budget_remaining; found {funcs}"

    def test_is_met_method(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "is_met" in funcs, f"Expected is_met(); found {funcs}"


class TestSemanticBurnRate:
    """Verify burn-rate alerting module structure."""

    @pytest.fixture(autouse=True)
    def _load(self):
        with open(BURN_RATE_FILE, "r", encoding="utf-8") as f:
            self.src = f.read()
        self.tree = ast.parse(self.src)

    def test_burn_rate_alert_class(self):
        classes = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.ClassDef)]
        assert "BurnRateAlert" in classes, f"Expected BurnRateAlert; found {classes}"

    def test_multi_window_class(self):
        classes = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.ClassDef)]
        assert "MultiWindowBurnRate" in classes, (
            f"Expected MultiWindowBurnRate; found {classes}"
        )

    def test_evaluate_method(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "evaluate" in funcs, f"Expected evaluate(); found {funcs}"

    def test_alert_result(self):
        assert "AlertResult" in self.src, "Should define or use AlertResult"

    def test_standard_thresholds(self):
        assert "14.4" in self.src, "Should include standard burn-rate threshold 14.4"
        assert "6.0" in self.src or "6" in self.src, (
            "Should include burn-rate threshold 6.0"
        )


class TestSemanticReport:
    """Verify report generator module structure."""

    @pytest.fixture(autouse=True)
    def _load(self):
        with open(REPORT_FILE, "r", encoding="utf-8") as f:
            self.src = f.read()
        self.tree = ast.parse(self.src)

    def test_slo_report_class(self):
        classes = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.ClassDef)]
        assert "SLOReport" in classes, f"Expected SLOReport; found {classes}"

    def test_generate_method(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "generate" in funcs, f"Expected generate(); found {funcs}"

    def test_to_markdown_method(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "to_markdown" in funcs, f"Expected to_markdown(); found {funcs}"


# ---------------------------------------------------------------------------
# Layer 3 — functional_check
# ---------------------------------------------------------------------------

class TestFunctionalAvailabilitySLI:
    """Run AvailabilitySLI and verify computations."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        sys.path.insert(0, PKG_DIR)
        sys.path.insert(0, REPO_DIR)
        try:
            from slo_generator.sli import AvailabilitySLI
            self.AvailabilitySLI = AvailabilitySLI
        except ImportError:
            try:
                from sli import AvailabilitySLI
                self.AvailabilitySLI = AvailabilitySLI
            except ImportError:
                pytest.skip("Cannot import AvailabilitySLI")

    def test_basic_computation(self):
        sli = self.AvailabilitySLI(good_events=999, total_events=1000)
        assert abs(sli.value() - 0.999) < 1e-6, (
            f"Expected 0.999; got {sli.value()}"
        )

    def test_perfect_availability(self):
        sli = self.AvailabilitySLI(good_events=100, total_events=100)
        assert sli.value() == 1.0

    def test_zero_total_raises(self):
        with pytest.raises(ValueError):
            self.AvailabilitySLI(good_events=0, total_events=0)

    def test_good_exceeds_total_raises(self):
        with pytest.raises(ValueError):
            self.AvailabilitySLI(good_events=101, total_events=100)


class TestFunctionalLatencySLI:
    """Run LatencySLI and verify computations."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        sys.path.insert(0, PKG_DIR)
        sys.path.insert(0, REPO_DIR)
        try:
            from slo_generator.sli import LatencySLI
            self.LatencySLI = LatencySLI
        except ImportError:
            try:
                from sli import LatencySLI
                self.LatencySLI = LatencySLI
            except ImportError:
                pytest.skip("Cannot import LatencySLI")

    def test_basic_computation(self):
        sli = self.LatencySLI(latencies=[0.1, 0.2, 0.5, 1.0], threshold=0.5)
        assert abs(sli.value() - 0.75) < 1e-6, f"Expected 0.75; got {sli.value()}"

    def test_all_below_threshold(self):
        sli = self.LatencySLI(latencies=[0.1, 0.2, 0.3], threshold=1.0)
        assert sli.value() == 1.0

    def test_empty_latencies_raises(self):
        with pytest.raises(ValueError):
            self.LatencySLI(latencies=[], threshold=0.5)

    def test_negative_threshold_raises(self):
        with pytest.raises(ValueError):
            self.LatencySLI(latencies=[0.1], threshold=-1.0)


class TestFunctionalSLOTracking:
    """Run SLO class and verify error budget computation."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        sys.path.insert(0, PKG_DIR)
        sys.path.insert(0, REPO_DIR)
        try:
            from slo_generator.slo import SLO
            self.SLO = SLO
        except ImportError:
            try:
                from slo import SLO
                self.SLO = SLO
            except ImportError:
                pytest.skip("Cannot import SLO")

    def test_error_budget_total(self):
        slo = self.SLO(name="api-availability", target=0.999, window_days=28)
        budget = slo.error_budget_total()
        assert abs(budget - 0.001) < 1e-6, f"Expected 0.001; got {budget}"

    def test_record_and_achievement(self):
        slo = self.SLO(name="api-availability", target=0.999, window_days=28)
        now = datetime.utcnow()
        for i in range(10):
            slo.record(now - timedelta(hours=i), 0.999)
        ach = slo.achievement(at=now)
        assert abs(ach - 0.999) < 1e-3, f"Achievement should be ~0.999; got {ach}"

    def test_is_met_true(self):
        slo = self.SLO(name="api-availability", target=0.999, window_days=28)
        now = datetime.utcnow()
        for i in range(10):
            slo.record(now - timedelta(hours=i), 1.0)
        assert slo.is_met(at=now) is True

    def test_is_met_false(self):
        slo = self.SLO(name="api-availability", target=0.999, window_days=28)
        now = datetime.utcnow()
        for i in range(10):
            slo.record(now - timedelta(hours=i), 0.99)
        assert slo.is_met(at=now) is False


class TestFunctionalReport:
    """Run SLOReport and verify output structure."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        sys.path.insert(0, PKG_DIR)
        sys.path.insert(0, REPO_DIR)
        try:
            from slo_generator.slo import SLO
            from slo_generator.report import SLOReport
            self.SLO = SLO
            self.SLOReport = SLOReport
        except ImportError:
            try:
                from slo import SLO
                from report import SLOReport
                self.SLO = SLO
                self.SLOReport = SLOReport
            except ImportError:
                pytest.skip("Cannot import SLOReport")

    def test_generate_returns_dict(self):
        slo = self.SLO(name="api-availability", target=0.999, window_days=28)
        now = datetime.utcnow()
        for i in range(10):
            slo.record(now - timedelta(hours=i), 0.999)
        report = self.SLOReport([slo])
        result = report.generate(at=now)
        assert isinstance(result, dict), "generate() should return a dict"
        assert "summary" in result, "Report should have summary field"

    def test_to_markdown_returns_string(self):
        slo = self.SLO(name="api-availability", target=0.999, window_days=28)
        now = datetime.utcnow()
        slo.record(now, 0.999)
        report = self.SLOReport([slo])
        report.generate(at=now)
        md = report.to_markdown()
        assert isinstance(md, str), "to_markdown() should return a string"
        assert len(md) > 0, "Markdown report should not be empty"
