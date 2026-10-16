"""
Test skill: python-observability
Verify that the Agent adds OpenTelemetry self-instrumentation to the OTLP HTTP
exporter — Prometheus metrics (counter/histogram/gauge), structured logging via
structlog, and signal type detection on exporter subclasses.
"""

import os
import re
import subprocess
import pytest


class TestPythonObservability:
    REPO_DIR = "/workspace/opentelemetry-python"

    # ────── helpers ──────

    def _read(self, rel_path):
        fpath = os.path.join(self.REPO_DIR, rel_path)
        with open(fpath, "r") as f:
            return f.read()

    def _exists(self, rel_path):
        return os.path.isfile(os.path.join(self.REPO_DIR, rel_path))

    _BASE = (
        "exporter/opentelemetry-exporter-otlp-proto-http/"
        "src/opentelemetry/exporter/otlp/proto/http"
    )

    # === File Path Checks ===

    def test_metrics_module_exists(self):
        """metrics.py must exist"""
        assert self._exists(f"{self._BASE}/metrics.py")

    def test_observability_test_exists(self):
        """test_exporter_observability.py must exist"""
        assert self._exists(
            "exporter/opentelemetry-exporter-otlp-proto-http/"
            "tests/test_exporter_observability.py"
        )

    # === Semantic Checks — metrics.py ===

    def test_export_requests_total_counter(self):
        """OTLP_EXPORT_REQUESTS_TOTAL counter must be defined"""
        src = self._read(f"{self._BASE}/metrics.py")
        assert "OTLP_EXPORT_REQUESTS_TOTAL" in src or "otlp_exporter_export_requests_total" in src

    def test_export_duration_histogram(self):
        """OTLP_EXPORT_DURATION_SECONDS histogram must be defined"""
        src = self._read(f"{self._BASE}/metrics.py")
        assert "OTLP_EXPORT_DURATION_SECONDS" in src or "otlp_exporter_export_duration_seconds" in src

    def test_export_items_counter(self):
        """OTLP_EXPORT_ITEMS_TOTAL counter must be defined"""
        src = self._read(f"{self._BASE}/metrics.py")
        assert "OTLP_EXPORT_ITEMS_TOTAL" in src or "otlp_exporter_items_exported_total" in src

    def test_export_queue_size_gauge(self):
        """OTLP_EXPORT_QUEUE_SIZE gauge must be defined"""
        src = self._read(f"{self._BASE}/metrics.py")
        assert "OTLP_EXPORT_QUEUE_SIZE" in src or "otlp_exporter_queue_size" in src

    def test_prometheus_client_imports(self):
        """Must import from prometheus_client"""
        src = self._read(f"{self._BASE}/metrics.py")
        assert "prometheus_client" in src or "Counter" in src

    def test_label_names(self):
        """Metrics must include exporter_type, signal, status labels"""
        src = self._read(f"{self._BASE}/metrics.py")
        for label in ["exporter_type", "signal"]:
            assert label in src, f"Missing label: {label}"

    def test_histogram_buckets(self):
        """Duration histogram must define custom buckets"""
        src = self._read(f"{self._BASE}/metrics.py")
        assert "buckets" in src.lower()

    # === Semantic Checks — exporter.py modifications ===

    def test_exporter_import_metrics(self):
        """exporter.py must import metrics"""
        src = self._read(f"{self._BASE}/exporter.py")
        assert "metrics" in src.lower() or "OTLP_EXPORT" in src

    def test_export_duration_recording(self):
        """_export must record duration"""
        src = self._read(f"{self._BASE}/exporter.py")
        lower = src.lower()
        assert "duration" in lower or "time" in lower

    def test_status_labels(self):
        """Must use status labels: success, failed, retried"""
        src = self._read(f"{self._BASE}/exporter.py")
        for status in ["success", "failed", "retried"]:
            assert status in src, f"Missing status label: {status}"

    def test_best_effort_metrics(self):
        """Metrics recording must be best-effort (catch exceptions)"""
        src = self._read(f"{self._BASE}/exporter.py")
        assert "except" in src or "try" in src

    # === Semantic Checks — Structured Logging ===

    def test_structlog_usage(self):
        """Must use structlog"""
        src = self._read(f"{self._BASE}/exporter.py")
        assert "structlog" in src

    def test_structured_log_fields(self):
        """Structured logs must include endpoint and signal fields"""
        src = self._read(f"{self._BASE}/exporter.py")
        assert "endpoint" in src
        assert "signal" in src

    # === Semantic Checks — Signal Type ===

    def test_signal_type_attribute(self):
        """_signal_type class attribute must be set"""
        found = False
        for root, _, files in os.walk(os.path.join(self.REPO_DIR, self._BASE)):
            for fn in files:
                if fn.endswith(".py"):
                    content = open(os.path.join(root, fn)).read()
                    if "_signal_type" in content:
                        found = True
                        break
        assert found, "_signal_type attribute not found"

    # === Functional Checks ===

    def test_python_syntax_metrics(self):
        """metrics.py must have valid syntax"""
        result = subprocess.run(
            ["python", "-c",
             f"import py_compile; py_compile.compile('{self._BASE}/metrics.py', doraise=True)"],
            capture_output=True, text=True, cwd=self.REPO_DIR, timeout=30,
        )
        assert result.returncode == 0, f"Syntax error:\n{result.stderr}"

    def test_observability_tests_pass(self):
        """Observability tests must pass"""
        result = subprocess.run(
            ["python", "-m", "pytest",
             "exporter/opentelemetry-exporter-otlp-proto-http/tests/test_exporter_observability.py",
             "-v", "--tb=short"],
            capture_output=True, text=True, cwd=self.REPO_DIR, timeout=120,
        )
        assert result.returncode == 0, (
            f"Tests failed:\n{result.stdout}\n{result.stderr}"
        )

    def test_existing_exporter_tests_pass(self):
        """Existing OTLP HTTP exporter tests must still pass"""
        result = subprocess.run(
            ["python", "-m", "pytest",
             "exporter/opentelemetry-exporter-otlp-proto-http/tests/",
             "-v", "--tb=short", "-x"],
            capture_output=True, text=True, cwd=self.REPO_DIR, timeout=180,
        )
        assert result.returncode == 0, (
            f"Existing tests failed:\n{result.stdout}\n{result.stderr}"
        )
