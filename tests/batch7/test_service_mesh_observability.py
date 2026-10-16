"""
Test skill: service-mesh-observability
Verify that the Agent implements a Per-Service Golden Signals Dashboard generator
in Linkerd2 — DashboardGenerator, panel builders (SuccessRate, RequestRate, Latency,
TCPConnections), Grafana types, and deterministic UID generation.
"""

import os
import re
import subprocess
import pytest


class TestServiceMeshObservability:
    REPO_DIR = "/workspace/linkerd2"

    # ────── helpers ──────

    def _read(self, rel_path):
        fpath = os.path.join(self.REPO_DIR, rel_path)
        with open(fpath, "r") as f:
            return f.read()

    def _exists(self, rel_path):
        return os.path.isfile(os.path.join(self.REPO_DIR, rel_path))

    _PKG = "viz/pkg/dashboard"

    # === File Path Checks ===

    def test_generator_exists(self):
        """generator.go must exist"""
        assert self._exists(f"{self._PKG}/generator.go")

    def test_panels_exists(self):
        """panels.go must exist"""
        assert self._exists(f"{self._PKG}/panels.go")

    def test_types_exists(self):
        """types.go must exist"""
        assert self._exists(f"{self._PKG}/types.go")

    def test_generator_test_exists(self):
        """generator_test.go must exist"""
        assert self._exists(f"{self._PKG}/generator_test.go")

    # === Semantic Checks — types.go ===

    def test_dashboard_struct(self):
        """Dashboard struct must be defined"""
        src = self._read(f"{self._PKG}/types.go")
        assert re.search(r'type\s+Dashboard\s+struct', src)

    def test_panel_struct(self):
        """Panel struct must be defined"""
        src = self._read(f"{self._PKG}/types.go")
        assert re.search(r'type\s+Panel\s+struct', src)

    def test_target_struct(self):
        """Target struct must be defined"""
        src = self._read(f"{self._PKG}/types.go")
        assert "Target" in src and "Expr" in src

    def test_grid_pos_struct(self):
        """GridPos struct must be defined"""
        src = self._read(f"{self._PKG}/types.go")
        assert "GridPos" in src

    def test_alert_struct(self):
        """Alert struct must be defined"""
        src = self._read(f"{self._PKG}/types.go")
        assert "Alert" in src

    def test_json_tags(self):
        """Structs must have json tags"""
        src = self._read(f"{self._PKG}/types.go")
        assert 'json:"' in src

    # === Semantic Checks — panels.go ===

    def test_success_rate_panel(self):
        """SuccessRatePanel function must exist"""
        src = self._read(f"{self._PKG}/panels.go")
        assert "SuccessRatePanel" in src or "successRatePanel" in src

    def test_request_rate_panel(self):
        """RequestRatePanel function must exist"""
        src = self._read(f"{self._PKG}/panels.go")
        assert "RequestRatePanel" in src or "requestRatePanel" in src

    def test_latency_panel(self):
        """LatencyPanel function must exist"""
        src = self._read(f"{self._PKG}/panels.go")
        assert "LatencyPanel" in src or "latencyPanel" in src

    def test_tcp_connections_panel(self):
        """TCPConnectionsPanel function must exist"""
        src = self._read(f"{self._PKG}/panels.go")
        assert "TCPConnectionsPanel" in src or "tcpConnectionsPanel" in src

    def test_linkerd_metric_names(self):
        """Must use Linkerd standard metrics"""
        src = self._read(f"{self._PKG}/panels.go")
        assert "response_total" in src
        assert "response_latency_ms_bucket" in src
        assert "tcp_open_connections" in src

    def test_latency_quantiles(self):
        """Latency panel must have P50, P95, P99"""
        src = self._read(f"{self._PKG}/panels.go")
        assert "0.50" in src or "0.5" in src
        assert "0.95" in src
        assert "0.99" in src

    def test_classification_label(self):
        """Success rate must filter by classification='success'"""
        src = self._read(f"{self._PKG}/panels.go")
        assert "classification" in src

    # === Semantic Checks — generator.go ===

    def test_dashboard_generator_struct(self):
        """DashboardGenerator struct must be defined"""
        src = self._read(f"{self._PKG}/generator.go")
        assert "DashboardGenerator" in src

    def test_generate_method(self):
        """Generate method must exist"""
        src = self._read(f"{self._PKG}/generator.go")
        assert re.search(r'func\s+\(.*DashboardGenerator\)\s+Generate\b', src)

    def test_to_json_method(self):
        """ToJSON method must exist"""
        src = self._read(f"{self._PKG}/generator.go")
        assert "ToJSON" in src

    def test_uid_generation(self):
        """Must generate deterministic UID from service+namespace"""
        src = self._read(f"{self._PKG}/generator.go")
        assert "sha256" in src.lower() or "generateUID" in src

    def test_default_tags(self):
        """Must include linkerd and service-mesh tags"""
        src = self._read(f"{self._PKG}/generator.go")
        assert "linkerd" in src
        assert "service-mesh" in src

    # === Functional Checks ===

    def test_go_build(self):
        """Dashboard package must build"""
        result = subprocess.run(
            ["go", "build", f"./{self._PKG}/..."],
            capture_output=True, text=True, cwd=self.REPO_DIR, timeout=300,
        )
        assert result.returncode == 0, (
            f"go build failed:\n{result.stdout}\n{result.stderr}"
        )

    def test_unit_tests_pass(self):
        """Dashboard tests must pass"""
        result = subprocess.run(
            ["go", "test", "-v", f"./{self._PKG}/..."],
            capture_output=True, text=True, cwd=self.REPO_DIR, timeout=300,
        )
        assert result.returncode == 0, (
            f"Tests failed:\n{result.stdout}\n{result.stderr}"
        )
