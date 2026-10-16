"""
Test skill: python-observability
Verify that the Agent creates an OpenTelemetry Python observability demo
with tracing, metrics, structured logging, and log-trace correlation.
"""

import os
import re
import ast
import subprocess
import pytest


class TestPythonObservability:
    REPO_DIR = "/workspace/opentelemetry-python"

    # === File Path Checks ===

    def test_demo_script_exists(self):
        """Verify docs/examples/observability_demo.py exists"""
        path = os.path.join(
            self.REPO_DIR, "docs/examples/observability_demo.py"
        )
        assert os.path.exists(path), (
            f"observability_demo.py not found at {path}"
        )

    # === Semantic Checks ===

    def test_tracer_provider_setup(self):
        """Verify TracerProvider is initialized"""
        path = os.path.join(
            self.REPO_DIR, "docs/examples/observability_demo.py"
        )
        with open(path) as f:
            content = f.read()

        trace_indicators = [
            "TracerProvider", "tracer", "get_tracer",
            "trace", "Tracer",
        ]
        found = [ind for ind in trace_indicators if ind in content]
        assert len(found) >= 2, (
            f"Should initialize TracerProvider. Found: {found}"
        )

    def test_nested_spans(self):
        """Verify nested spans simulating request flow"""
        path = os.path.join(
            self.REPO_DIR, "docs/examples/observability_demo.py"
        )
        with open(path) as f:
            content = f.read()

        span_indicators = [
            "start_as_current_span", "start_span", "with tracer",
            "span", "Span",
        ]
        found = [ind for ind in span_indicators if ind in content]
        assert len(found) >= 2, (
            f"Should create nested spans. Found: {found}"
        )

    def test_span_attributes(self):
        """Verify span attributes for request metadata"""
        path = os.path.join(
            self.REPO_DIR, "docs/examples/observability_demo.py"
        )
        with open(path) as f:
            content = f.read()

        attr_indicators = [
            "set_attribute", "attributes", "method", "path",
            "status_code", "attribute",
        ]
        found = [ind for ind in attr_indicators if ind in content]
        assert len(found) >= 2, (
            f"Should attach span attributes. Found: {found}"
        )

    def test_meter_provider_setup(self):
        """Verify MeterProvider and Meter are initialized"""
        path = os.path.join(
            self.REPO_DIR, "docs/examples/observability_demo.py"
        )
        with open(path) as f:
            content = f.read()

        meter_indicators = [
            "MeterProvider", "Meter", "get_meter",
            "meter", "metrics",
        ]
        found = [ind for ind in meter_indicators if ind in content]
        assert len(found) >= 2, (
            f"Should initialize MeterProvider. Found: {found}"
        )

    def test_counter_and_histogram(self):
        """Verify counter and histogram metric types"""
        path = os.path.join(
            self.REPO_DIR, "docs/examples/observability_demo.py"
        )
        with open(path) as f:
            content = f.read()

        counter_indicators = ["counter", "Counter", "add("]
        histogram_indicators = ["histogram", "Histogram", "record("]

        counter_found = [ind for ind in counter_indicators if ind in content]
        histogram_found = [ind for ind in histogram_indicators if ind in content]

        assert len(counter_found) >= 1, (
            f"Should create a counter metric. Found: {counter_found}"
        )
        assert len(histogram_found) >= 1, (
            f"Should create a histogram metric. Found: {histogram_found}"
        )

    def test_structured_logging(self):
        """Verify structured logging setup"""
        path = os.path.join(
            self.REPO_DIR, "docs/examples/observability_demo.py"
        )
        with open(path) as f:
            content = f.read()

        log_indicators = [
            "logging", "logger", "LoggerProvider", "log",
            "getLogger", "info", "warning", "error",
        ]
        found = [ind for ind in log_indicators if ind in content]
        assert len(found) >= 3, (
            f"Should set up structured logging. Found: {found}"
        )

    def test_log_trace_correlation(self):
        """Verify trace IDs appear in log output"""
        path = os.path.join(
            self.REPO_DIR, "docs/examples/observability_demo.py"
        )
        with open(path) as f:
            content = f.read()

        correlation_indicators = [
            "trace_id", "span_id", "otelTraceID",
            "otelSpanID", "context", "get_current_span",
        ]
        found = [ind for ind in correlation_indicators if ind in content]
        assert len(found) >= 1, (
            f"Should include log-trace correlation. Found: {found}"
        )

    # === Functional Checks ===

    def test_script_valid_python(self):
        """Verify observability_demo.py is valid Python"""
        path = os.path.join(
            self.REPO_DIR, "docs/examples/observability_demo.py"
        )
        with open(path) as f:
            source = f.read()
        try:
            ast.parse(source)
        except SyntaxError as e:
            pytest.fail(f"observability_demo.py has syntax errors: {e}")

    def test_has_main_entry_point(self):
        """Verify script has __main__ entry point"""
        path = os.path.join(
            self.REPO_DIR, "docs/examples/observability_demo.py"
        )
        with open(path) as f:
            content = f.read()

        assert '__name__' in content and '__main__' in content, (
            "Script should have a __main__ entry point"
        )

    def test_imports_opentelemetry(self):
        """Verify script imports from opentelemetry"""
        path = os.path.join(
            self.REPO_DIR, "docs/examples/observability_demo.py"
        )
        with open(path) as f:
            content = f.read()

        assert "opentelemetry" in content, (
            "Script should import from opentelemetry"
        )
