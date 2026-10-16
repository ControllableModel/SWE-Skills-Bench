"""
Tests for the service-mesh-observability skill.
Validates a Linkerd viz traffic health summary CLI command with golden signal
aggregation, status classification, and JSON/table output.
"""

import os
import re

REPO_DIR = "/workspace/linkerd2"
VIZ_CMD_DIR = os.path.join(REPO_DIR, "viz", "cmd")
PKG_DIR = os.path.join(REPO_DIR, "viz", "pkg", "healthsummary")


class TestServiceMeshObservability:
    """Tests for the Linkerd viz health-summary command."""

    # ── file_path_check ──────────────────────────────────────────────

    def test_health_summary_cmd_exists(self):
        """CLI subcommand health_summary.go must exist."""
        path = os.path.join(VIZ_CMD_DIR, "health_summary.go")
        assert os.path.isfile(path), f"Missing {path}"

    def test_aggregator_exists(self):
        """Aggregation module aggregator.go must exist."""
        path = os.path.join(PKG_DIR, "aggregator.go")
        assert os.path.isfile(path), f"Missing {path}"

    def test_types_exists(self):
        """Types module types.go must exist."""
        path = os.path.join(PKG_DIR, "types.go")
        assert os.path.isfile(path), f"Missing {path}"

    def test_aggregator_test_exists(self):
        """Aggregator test file must exist."""
        path = os.path.join(PKG_DIR, "aggregator_test.go")
        assert os.path.isfile(path), f"Missing {path}"

    # ── semantic_check ───────────────────────────────────────────────

    def _read(self, path):
        if not os.path.isfile(path):
            return ""
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def test_golden_signals(self):
        """Aggregator must compute request rate, error rate, latency percentiles, saturation."""
        content = self._read(os.path.join(PKG_DIR, "aggregator.go"))
        for signal in ["RequestRate", "ErrorRate", "LatencyP50", "LatencyP95", "LatencyP99", "Saturation"]:
            assert re.search(rf"{signal}|{signal.lower()}|{signal.replace('Latency', 'latency_')}", content, re.IGNORECASE), (
                f"Golden signal '{signal}' not found"
            )

    def test_status_classification(self):
        """Types must define healthy, degraded, critical, unknown statuses."""
        content = self._read(os.path.join(PKG_DIR, "types.go")) + self._read(os.path.join(PKG_DIR, "aggregator.go"))
        for status in ["healthy", "degraded", "critical", "unknown"]:
            assert re.search(rf'"{status}"|{status.upper()}|Status{status.title()}', content), (
                f"Status '{status}' not defined"
            )

    def test_critical_thresholds(self):
        """Critical threshold: error_rate > 10% or P99 > 5000ms."""
        content = self._read(os.path.join(PKG_DIR, "aggregator.go"))
        assert re.search(r"10|0\.10|0\.1", content), "Critical error rate threshold not found"
        assert re.search(r"5000", content), "Critical P99 latency threshold (5000ms) not found"

    def test_json_output_fields(self):
        """Types must include namespace, window, generated_at, summary, deployments."""
        content = self._read(os.path.join(PKG_DIR, "types.go"))
        for field in ["Namespace", "Window", "GeneratedAt", "Summary", "Deployments"]:
            assert re.search(rf"{field}|{field.lower()}", content), (
                f"JSON field '{field}' not found in types"
            )

    def test_cli_flags(self):
        """CLI must accept --namespace, --output, --window flags."""
        content = self._read(os.path.join(VIZ_CMD_DIR, "health_summary.go"))
        for flag in ["namespace", "output", "window"]:
            assert flag in content, f"CLI flag '--{flag}' not found"

    def test_table_output_columns(self):
        """Table output must include DEPLOYMENT, STATUS, RPS, ERR%, P50, P95, P99 columns."""
        content = self._read(os.path.join(VIZ_CMD_DIR, "health_summary.go")) + self._read(os.path.join(PKG_DIR, "aggregator.go"))
        for col in ["DEPLOYMENT", "STATUS", "RPS", "ERR"]:
            assert re.search(rf"{col}|{col.lower()}", content), (
                f"Table column '{col}' not found"
            )

    def test_weighted_average(self):
        """Namespace summary must use weighted average by request count."""
        content = self._read(os.path.join(PKG_DIR, "aggregator.go"))
        assert re.search(r"weight|weighted|totalRequests", content, re.IGNORECASE), (
            "Weighted average computation not found"
        )

    # ── functional_check ─────────────────────────────────────────────

    def test_root_cmd_registration(self):
        """root.go must register the health-summary subcommand."""
        content = self._read(os.path.join(VIZ_CMD_DIR, "root.go"))
        assert re.search(r"health.summary|healthSummary|health_summary", content), (
            "health-summary subcommand not registered in root.go"
        )

    def test_zero_traffic_handling(self):
        """Deployments with zero requests must show 'unknown' status."""
        content = self._read(os.path.join(PKG_DIR, "aggregator.go"))
        assert re.search(r"zero|no.*request|unknown|null", content, re.IGNORECASE), (
            "Zero-traffic deployment handling not found"
        )

    def test_prometheus_error_handling(self):
        """Command must handle Prometheus API unreachable error."""
        content = self._read(os.path.join(VIZ_CMD_DIR, "health_summary.go")) + self._read(os.path.join(PKG_DIR, "aggregator.go"))
        assert re.search(r"error|unreachable|connection.*fail", content, re.IGNORECASE), (
            "Prometheus error handling not found"
        )

    def test_sort_by_severity(self):
        """Table output must sort deployments by severity (critical first)."""
        content = self._read(os.path.join(VIZ_CMD_DIR, "health_summary.go")) + self._read(os.path.join(PKG_DIR, "aggregator.go"))
        assert re.search(r"sort|Sort|order|critical.*first|severity", content, re.IGNORECASE), (
            "Severity-based sorting not found"
        )
