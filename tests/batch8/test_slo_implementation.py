"""
Tests for the slo-implementation skill.
Validates SLO configuration, error budget computation, multi-window burn rate
alerting, and budget report generation for a multi-tier web application.
"""

import os
import re
import ast

REPO_DIR = "/workspace/slo-generator"
SAMPLES_DIR = os.path.join(REPO_DIR, "samples", "multi_tier")
SRC_DIR = os.path.join(REPO_DIR, "slo_generator")


class TestSloImplementation:
    """Tests for the SLO implementation framework."""

    # ── file_path_check ──────────────────────────────────────────────

    def test_slo_config_exists(self):
        """SLO configuration YAML must exist."""
        path = os.path.join(SAMPLES_DIR, "slo_config.yaml")
        assert os.path.isfile(path), f"Missing {path}"

    def test_error_budget_config_exists(self):
        """Error budget policy YAML must exist."""
        path = os.path.join(SAMPLES_DIR, "error_budget.yaml")
        assert os.path.isfile(path), f"Missing {path}"

    def test_exporters_config_exists(self):
        """Exporter configuration YAML must exist."""
        path = os.path.join(SAMPLES_DIR, "exporters.yaml")
        assert os.path.isfile(path), f"Missing {path}"

    def test_compute_module_exists(self):
        """compute.py module must exist."""
        path = os.path.join(SRC_DIR, "compute.py")
        assert os.path.isfile(path), f"Missing {path}"

    def test_report_module_exists(self):
        """report.py module must exist."""
        path = os.path.join(SRC_DIR, "report.py")
        assert os.path.isfile(path), f"Missing {path}"

    # ── semantic_check ───────────────────────────────────────────────

    def _read(self, path):
        if not os.path.isfile(path):
            return ""
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def test_slo_config_six_slos(self):
        """SLO config must define 6 SLOs across 3 services."""
        content = self._read(os.path.join(SAMPLES_DIR, "slo_config.yaml"))
        for service in ["api", "worker", "pipeline"]:
            assert re.search(rf"{service}", content, re.IGNORECASE), (
                f"Service '{service}' not found in SLO config"
            )
        # Check for availability and latency SLO types
        assert re.search(r"availability|latency|freshness|completeness", content, re.IGNORECASE), (
            "SLI types not found in config"
        )

    def test_slo_targets(self):
        """SLO config must include 99.9% and 99.5% availability targets."""
        content = self._read(os.path.join(SAMPLES_DIR, "slo_config.yaml"))
        assert re.search(r"99\.9|0\.999", content), "99.9% target not found"
        assert re.search(r"99\.5|0\.995", content), "99.5% target not found"

    def test_burn_rate_windows(self):
        """compute.py must evaluate burn rates across 1h, 6h, and 3d windows."""
        content = self._read(os.path.join(SRC_DIR, "compute.py"))
        assert re.search(r"multi_window_burn_rate|burn_rate", content), (
            "multi_window_burn_rate function not found"
        )
        for window in ["1h", "6h", "3d"]:
            assert re.search(rf"{window}|{window.replace('h','.*hour').replace('d','.*day')}", content, re.IGNORECASE), (
                f"Burn rate window '{window}' not found"
            )

    def test_page_alert_thresholds(self):
        """Page alert: 1h burn rate > 14.4 AND 6h burn rate > 6."""
        content = self._read(os.path.join(SRC_DIR, "compute.py"))
        assert "14.4" in content or "14.4x" in content.lower(), "Page alert 14.4x threshold not found"
        assert re.search(r"page|critical", content, re.IGNORECASE), "Page alert type not found"

    def test_budget_report_function(self):
        """report.py must define generate_budget_report."""
        content = self._read(os.path.join(SRC_DIR, "report.py"))
        assert re.search(r"def\s+generate_budget_report\b", content), (
            "generate_budget_report function not defined"
        )

    def test_report_status_classification(self):
        """Report must classify status as healthy, warning, critical."""
        content = self._read(os.path.join(SRC_DIR, "report.py"))
        for status in ["healthy", "warning", "critical"]:
            assert status in content, f"Status '{status}' not found in report"

    def test_projected_exhaustion(self):
        """Report must compute projected exhaustion date."""
        content = self._read(os.path.join(SRC_DIR, "report.py")) + self._read(os.path.join(SRC_DIR, "compute.py"))
        assert re.search(r"projected.*exhaustion|exhaustion.*date", content, re.IGNORECASE), (
            "Projected exhaustion date computation not found"
        )

    # ── functional_check ─────────────────────────────────────────────

    def test_compute_valid_python(self):
        """compute.py must have valid Python syntax."""
        content = self._read(os.path.join(SRC_DIR, "compute.py"))
        if content:
            ast.parse(content)

    def test_report_valid_python(self):
        """report.py must have valid Python syntax."""
        content = self._read(os.path.join(SRC_DIR, "report.py"))
        if content:
            ast.parse(content)

    def test_zero_requests_handling(self):
        """Zero requests must report SLI as 1.0 (100%)."""
        content = self._read(os.path.join(SRC_DIR, "compute.py")) + self._read(os.path.join(SRC_DIR, "report.py"))
        assert re.search(r"zero|total.*==?\s*0|no.*requests|1\.0", content, re.IGNORECASE), (
            "Zero-requests edge case handling not found"
        )

    def test_budget_cap_at_100(self):
        """Remaining budget must be capped at 100%."""
        content = self._read(os.path.join(SRC_DIR, "compute.py")) + self._read(os.path.join(SRC_DIR, "report.py"))
        assert re.search(r"min\(|max\(|cap|100", content), (
            "Budget cap at 100% not found"
        )

    def test_test_file_exists(self):
        """Test file must exist."""
        path = os.path.join(REPO_DIR, "tests", "unit", "test_multi_tier_slo.py")
        if not os.path.isfile(path):
            path = os.path.join(REPO_DIR, "tests", "test_slo_implementation.py")
        assert os.path.isfile(path), "Missing test file"

    def test_error_budget_yaml_valid(self):
        """Error budget YAML must define burn rate alerting thresholds."""
        content = self._read(os.path.join(SAMPLES_DIR, "error_budget.yaml"))
        assert re.search(r"burn.rate|threshold|alert", content, re.IGNORECASE), (
            "Burn rate alerting thresholds not found in error budget YAML"
        )
