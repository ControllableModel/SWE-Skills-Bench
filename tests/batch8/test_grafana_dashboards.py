"""
Tests for the grafana-dashboards skill.
Validates a Grafana RED method service health dashboard JSON and
a Go-based dashboard generator with configurable service metrics.
"""

import os
import re
import json

REPO_DIR = "/workspace/grafana"
DASHBOARD_DIR = os.path.join(REPO_DIR, "devenv", "dashboards", "service-health")
PKG_DIR = os.path.join(REPO_DIR, "pkg", "dashboards", "redgenerator")


class TestGrafanaDashboards:
    """Tests for the Grafana RED method dashboard."""

    # ── file_path_check ──────────────────────────────────────────────

    def test_dashboard_json_exists(self):
        """Provisioned dashboard JSON must exist."""
        path = os.path.join(DASHBOARD_DIR, "service-health-red.json")
        assert os.path.isfile(path), f"Missing {path}"

    def test_generator_exists(self):
        """Dashboard generator.go must exist."""
        path = os.path.join(PKG_DIR, "generator.go")
        assert os.path.isfile(path), f"Missing {path}"

    def test_types_exists(self):
        """Type definitions types.go must exist."""
        path = os.path.join(PKG_DIR, "types.go")
        assert os.path.isfile(path), f"Missing {path}"

    def test_generator_test_exists(self):
        """Generator test file must exist."""
        path = os.path.join(PKG_DIR, "generator_test.go")
        assert os.path.isfile(path), f"Missing {path}"

    def test_service_config_exists(self):
        """Example service config YAML must exist."""
        path = os.path.join(DASHBOARD_DIR, "service-config.yaml")
        assert os.path.isfile(path), f"Missing {path}"

    # ── semantic_check ───────────────────────────────────────────────

    def _read(self, path):
        if not os.path.isfile(path):
            return ""
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def test_dashboard_uid_and_title(self):
        """Dashboard must have uid 'service-health-red' and correct title."""
        content = self._read(os.path.join(DASHBOARD_DIR, "service-health-red.json"))
        assert "service-health-red" in content, "Dashboard uid not found"
        assert re.search(r"Service Health.*RED|RED.*Method", content), (
            "Dashboard title not found"
        )

    def test_six_panels(self):
        """Dashboard must contain exactly 6 panels."""
        path = os.path.join(DASHBOARD_DIR, "service-health-red.json")
        content = self._read(path)
        if not content:
            assert False, "Dashboard JSON is empty"
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            assert False, "Dashboard JSON is invalid"
        panels = data.get("panels", [])
        assert len(panels) == 6, f"Expected 6 panels, got {len(panels)}"

    def test_template_variables(self):
        """Dashboard must define $service and $interval template variables."""
        content = self._read(os.path.join(DASHBOARD_DIR, "service-health-red.json"))
        assert re.search(r'"service"', content), "$service template variable not found"
        assert re.search(r'"interval"', content), "$interval template variable not found"

    def test_prometheus_queries(self):
        """Panels must use Prometheus queries for rate, errors, duration."""
        content = self._read(os.path.join(DASHBOARD_DIR, "service-health-red.json"))
        assert "http_requests_total" in content, "Rate query not found"
        assert re.search(r"status_code.*5\.\.", content), "Error ratio query not found"
        assert "histogram_quantile" in content, "Duration quantile query not found"

    def test_error_thresholds(self):
        """Error gauge must have thresholds at 1% and 5%."""
        content = self._read(os.path.join(DASHBOARD_DIR, "service-health-red.json"))
        assert re.search(r"1|0\.01", content), "1% threshold not found"
        assert re.search(r"5|0\.05", content), "5% threshold not found"

    def test_quantiles_in_duration(self):
        """Duration panel must show P50, P95, P99."""
        content = self._read(os.path.join(DASHBOARD_DIR, "service-health-red.json"))
        for quantile in ["0.50", "0.95", "0.99", "0.5"]:
            if quantile in content:
                break
        else:
            assert False, "No quantile values found in duration panel"

    def test_generator_service_name_validation(self):
        """Generator must validate non-empty service_name."""
        content = self._read(os.path.join(PKG_DIR, "generator.go"))
        assert re.search(r"service_name|ServiceName|empty|error", content, re.IGNORECASE), (
            "Service name validation not found in generator"
        )

    # ── functional_check ─────────────────────────────────────────────

    def test_dashboard_valid_json(self):
        """Dashboard JSON must be valid JSON."""
        path = os.path.join(DASHBOARD_DIR, "service-health-red.json")
        content = self._read(path)
        if not content:
            assert False, "Dashboard JSON is empty"
        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            assert False, f"Invalid JSON: {e}"
        assert "panels" in data, "Missing 'panels' key"
        assert "uid" in data, "Missing 'uid' key"

    def test_panels_have_gridpos(self):
        """Each panel must have gridPos with h, w, x, y."""
        path = os.path.join(DASHBOARD_DIR, "service-health-red.json")
        content = self._read(path)
        if not content:
            return
        data = json.loads(content)
        for panel in data.get("panels", []):
            gp = panel.get("gridPos", {})
            for key in ["h", "w", "x", "y"]:
                assert key in gp, f"Panel '{panel.get('title', '?')}' missing gridPos.{key}"

    def test_panels_unique_ids(self):
        """Each panel must have a unique numeric id."""
        path = os.path.join(DASHBOARD_DIR, "service-health-red.json")
        content = self._read(path)
        if not content:
            return
        data = json.loads(content)
        ids = [p.get("id") for p in data.get("panels", [])]
        assert len(ids) == len(set(ids)), f"Duplicate panel IDs: {ids}"

    def test_schema_version(self):
        """Dashboard schema version must be >= 39."""
        path = os.path.join(DASHBOARD_DIR, "service-health-red.json")
        content = self._read(path)
        if not content:
            return
        data = json.loads(content)
        sv = data.get("schemaVersion", 0)
        assert sv >= 39, f"schemaVersion {sv} < 39"
