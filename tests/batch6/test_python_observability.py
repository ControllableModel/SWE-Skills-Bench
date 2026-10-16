"""
Test skill: python-observability
Verify that the Agent builds a FastAPI observability demo with structured
logging (structlog JSON), correlation ID middleware, custom SpanProcessor,
and OpenTelemetry metrics instruments.
"""

import os
import re
import ast
import pytest


class TestPythonObservability:
    REPO_DIR = "/workspace/opentelemetry-python"

    # === File Path Checks ===

    def test_app_exists(self):
        assert os.path.exists(
            os.path.join(self.REPO_DIR, "docs/examples/observability_demo/app.py")
        )

    def test_logging_config_exists(self):
        assert os.path.exists(
            os.path.join(self.REPO_DIR, "docs/examples/observability_demo/logging_config.py")
        )

    def test_tracing_config_exists(self):
        assert os.path.exists(
            os.path.join(self.REPO_DIR, "docs/examples/observability_demo/tracing_config.py")
        )

    def test_metrics_config_exists(self):
        assert os.path.exists(
            os.path.join(self.REPO_DIR, "docs/examples/observability_demo/metrics_config.py")
        )

    def test_middleware_exists(self):
        assert os.path.exists(
            os.path.join(self.REPO_DIR, "docs/examples/observability_demo/middleware.py")
        )

    # === Semantic Checks ===

    def test_logging_uses_structlog(self):
        """Logging config should use structlog with JSON output"""
        path = os.path.join(self.REPO_DIR, "docs/examples/observability_demo/logging_config.py")
        with open(path) as f:
            content = f.read()
        assert "structlog" in content, "Should use structlog"
        assert "json" in content.lower(), "Should output JSON format"

    def test_middleware_has_correlation_id(self):
        """Middleware should extract/generate correlation IDs"""
        path = os.path.join(self.REPO_DIR, "docs/examples/observability_demo/middleware.py")
        with open(path) as f:
            content = f.read()
        assert "correlation" in content.lower() or "X-Correlation-ID" in content, (
            "Middleware should handle correlation IDs"
        )
        assert "ContextVar" in content or "contextvars" in content, (
            "Should store correlation ID in ContextVar"
        )

    def test_middleware_records_metrics(self):
        """Middleware should record request duration and counters"""
        path = os.path.join(self.REPO_DIR, "docs/examples/observability_demo/middleware.py")
        with open(path) as f:
            content = f.read()
        content_lower = content.lower()
        assert "duration" in content_lower or "histogram" in content_lower or "time" in content_lower, (
            "Middleware should record request duration"
        )

    def test_tracing_has_custom_span_processor(self):
        """Tracing config should define MetadataSpanProcessor"""
        path = os.path.join(self.REPO_DIR, "docs/examples/observability_demo/tracing_config.py")
        with open(path) as f:
            content = f.read()
        assert "MetadataSpanProcessor" in content or "SpanProcessor" in content, (
            "Should define a custom SpanProcessor"
        )
        assert "on_start" in content, "Processor should implement on_start"
        assert "on_end" in content, "Processor should implement on_end"

    def test_tracing_adds_service_attributes(self):
        """SpanProcessor should enrich spans with service attributes"""
        path = os.path.join(self.REPO_DIR, "docs/examples/observability_demo/tracing_config.py")
        with open(path) as f:
            content = f.read()
        assert "service.instance.id" in content or "instance" in content, (
            "Should add service.instance.id attribute"
        )
        assert "deployment.environment" in content or "environment" in content, (
            "Should add deployment.environment attribute"
        )

    def test_metrics_has_four_instruments(self):
        """Metrics config should create histogram, counters, and gauge"""
        path = os.path.join(self.REPO_DIR, "docs/examples/observability_demo/metrics_config.py")
        with open(path) as f:
            content = f.read()
        assert "Histogram" in content or "histogram" in content, "Missing Histogram"
        assert "Counter" in content or "counter" in content, "Missing Counter"
        assert "UpDownCounter" in content or "up_down" in content or "active" in content, (
            "Missing UpDownCounter/gauge for active requests"
        )

    def test_app_has_three_endpoints(self):
        """App should have /health, /items/{item_id}, and POST /items"""
        path = os.path.join(self.REPO_DIR, "docs/examples/observability_demo/app.py")
        with open(path) as f:
            content = f.read()
        assert "/health" in content, "Missing /health endpoint"
        assert "/items" in content, "Missing /items endpoint"
        assert "item_id" in content, "Missing /items/{item_id} endpoint"

    def test_app_handles_error_case(self):
        """App should handle item_id='error' to demonstrate error tracing"""
        path = os.path.join(self.REPO_DIR, "docs/examples/observability_demo/app.py")
        with open(path) as f:
            content = f.read()
        assert '"error"' in content or "'error'" in content, (
            "App should handle 'error' item_id case"
        )

    def test_metrics_uses_bounded_cardinality(self):
        """Metrics should use route templates not actual paths"""
        path = os.path.join(self.REPO_DIR, "docs/examples/observability_demo/metrics_config.py")
        with open(path) as f:
            content = f.read()
        path2 = os.path.join(self.REPO_DIR, "docs/examples/observability_demo/middleware.py")
        with open(path2) as f:
            content2 = f.read()
        combined = content + content2
        assert "route" in combined.lower() or "path" in combined.lower(), (
            "Should use route templates for label cardinality"
        )

    # === Functional Checks ===

    def test_all_python_files_parse(self):
        """All Python files should parse without syntax errors"""
        base = os.path.join(self.REPO_DIR, "docs/examples/observability_demo")
        for root, _dirs, files in os.walk(base):
            for fname in files:
                if fname.endswith(".py"):
                    filepath = os.path.join(root, fname)
                    with open(filepath) as f:
                        source = f.read()
                    try:
                        ast.parse(source)
                    except SyntaxError as e:
                        pytest.fail(f"{filepath} syntax error: {e}")

    def test_test_file_exists_and_has_tests(self):
        """Test file should exist and have test methods"""
        path = os.path.join(self.REPO_DIR, "tests/test_observability_demo.py")
        assert os.path.exists(path), "Test file not found"
        with open(path) as f:
            content = f.read()
        tests = re.findall(r"def (test_\w+)", content)
        assert len(tests) >= 3, f"Should have at least 3 tests, found {len(tests)}"

    def test_logging_config_has_mandatory_fields(self):
        """Logging config should include timestamp, level, event, correlation_id, service_name"""
        path = os.path.join(self.REPO_DIR, "docs/examples/observability_demo/logging_config.py")
        with open(path) as f:
            content = f.read()
        for field in ("timestamp", "level", "event", "correlation_id", "service_name"):
            assert field in content, f"Logging config missing field: {field}"
