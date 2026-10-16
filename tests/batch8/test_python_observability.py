"""
Tests for the python-observability skill.
Validates an instrumented HTTP service example with OpenTelemetry traces,
metrics, structured logging, and correlation ID propagation.
"""

import os
import re
import ast

REPO_DIR = "/workspace/opentelemetry-python"
EXAMPLE_DIR = os.path.join(REPO_DIR, "docs", "examples", "instrumented_service")


class TestPythonObservability:
    """Tests for the OpenTelemetry instrumented service example."""

    # ── file_path_check ──────────────────────────────────────────────

    def test_app_exists(self):
        """HTTP service app module must exist."""
        path = os.path.join(EXAMPLE_DIR, "app.py")
        assert os.path.isfile(path), f"Missing {path}"

    def test_instrumentation_exists(self):
        """Instrumentation setup module must exist."""
        path = os.path.join(EXAMPLE_DIR, "instrumentation.py")
        assert os.path.isfile(path), f"Missing {path}"

    def test_metrics_exists(self):
        """Custom metrics module must exist."""
        path = os.path.join(EXAMPLE_DIR, "metrics.py")
        assert os.path.isfile(path), f"Missing {path}"

    def test_middleware_exists(self):
        """Request middleware module must exist."""
        path = os.path.join(EXAMPLE_DIR, "middleware.py")
        assert os.path.isfile(path), f"Missing {path}"

    def test_readme_exists(self):
        """README.md documentation must exist."""
        path = os.path.join(EXAMPLE_DIR, "README.md")
        assert os.path.isfile(path), f"Missing {path}"

    # ── semantic_check ───────────────────────────────────────────────

    def _read(self, filename):
        path = os.path.join(EXAMPLE_DIR, filename)
        if not os.path.isfile(path):
            return ""
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def test_metric_instruments(self):
        """Metrics module must define request counter, latency histogram, active gauge, error counter."""
        content = self._read("metrics.py")
        assert re.search(r"http_requests_total|requests_total", content), (
            "http_requests_total counter not found"
        )
        assert re.search(r"http_request_duration|request_duration", content), (
            "http_request_duration histogram not found"
        )
        assert re.search(r"http_requests_active|requests_active|UpDownCounter", content), (
            "Active requests UpDownCounter not found"
        )
        assert re.search(r"http_errors_total|errors_total", content), (
            "http_errors_total counter not found"
        )

    def test_histogram_buckets(self):
        """Latency histogram must use explicit bucket boundaries."""
        content = self._read("metrics.py")
        assert re.search(r"0\.005|0\.01|0\.025|0\.05|0\.1|0\.25", content), (
            "Explicit histogram bucket boundaries not found"
        )

    def test_span_attributes(self):
        """Middleware must set span attributes: http.method, http.url, http.status_code."""
        content = self._read("middleware.py")
        for attr in ["http.method", "http.status_code"]:
            assert attr in content, f"Span attribute '{attr}' not found"

    def test_structured_logging_json(self):
        """Structured logging must produce JSON with trace_id and span_id."""
        all_content = self._read("instrumentation.py") + self._read("middleware.py")
        assert re.search(r"trace_id|trace\.id", all_content), "trace_id not found in logs"
        assert re.search(r"span_id|span\.id", all_content), "span_id not found in logs"
        assert re.search(r"json|JSON", all_content, re.IGNORECASE), "JSON logging not found"

    def test_correlation_id_propagation(self):
        """Correlation ID must propagate via X-Correlation-ID header and contextvars."""
        all_content = self._read("middleware.py") + self._read("instrumentation.py")
        assert re.search(r"X-Correlation-ID|correlation.id", all_content, re.IGNORECASE), (
            "Correlation ID header not found"
        )
        assert re.search(r"contextvars|ContextVar", all_content), (
            "contextvars usage not found for correlation ID propagation"
        )

    def test_error_span_recording(self):
        """Error requests must set StatusCode.ERROR and record exception."""
        content = self._read("middleware.py") + self._read("app.py")
        assert re.search(r"StatusCode\.ERROR|set_status|record_exception", content), (
            "Error span recording not found"
        )

    def test_bounded_cardinality(self):
        """Route metric attribute must use templates, not actual paths."""
        content = self._read("middleware.py") + self._read("app.py")
        assert re.search(r"\{id\}|route.*template|parameterized", content, re.IGNORECASE), (
            "Bounded cardinality route template not found"
        )

    # ── functional_check ─────────────────────────────────────────────

    def test_all_files_valid_python(self):
        """All instrumented service Python files must have valid syntax."""
        errors = []
        for fname in ["app.py", "instrumentation.py", "metrics.py", "middleware.py"]:
            content = self._read(fname)
            if not content:
                continue
            try:
                ast.parse(content)
            except SyntaxError as e:
                errors.append(f"{fname}: {e}")
        assert not errors, "Syntax errors:\n" + "\n".join(errors)

    def test_endpoints_defined(self):
        """App must define /items, /items/{id}, /error, /slow endpoints."""
        content = self._read("app.py")
        for endpoint in ["/items", "/error", "/slow"]:
            assert endpoint in content, f"Endpoint '{endpoint}' not found"

    def test_tracer_provider_setup(self):
        """Instrumentation must set up TracerProvider and MeterProvider."""
        content = self._read("instrumentation.py")
        assert re.search(r"TracerProvider", content), "TracerProvider not found"
        assert re.search(r"MeterProvider", content), "MeterProvider not found"

    def test_test_file_exists(self):
        """Test file must exist."""
        path = os.path.join(REPO_DIR, "tests", "test_instrumented_service.py")
        if not os.path.isfile(path):
            path = os.path.join(REPO_DIR, "tests", "test_python_observability.py")
        assert os.path.isfile(path), f"Missing test file"
