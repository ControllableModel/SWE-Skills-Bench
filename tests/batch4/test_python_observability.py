"""
Tests for skill: python-observability
Repo: open-telemetry/opentelemetry-python
Image: zhangyiiiiii/swe-skills-bench-python
Task: Implement an observability library with structured logging (structlog),
      Prometheus metrics, correlation ID propagation, and ASGI middleware.
"""

import ast
import os
import sys

import pytest

REPO_DIR = "/workspace/opentelemetry-python"
OBS_DIR = os.path.join(REPO_DIR, "docs", "examples", "observability")

INIT_FILE = os.path.join(OBS_DIR, "__init__.py")
LOGGING_FILE = os.path.join(OBS_DIR, "logging_config.py")
METRICS_FILE = os.path.join(OBS_DIR, "metrics_collector.py")
CORRELATION_FILE = os.path.join(OBS_DIR, "correlation.py")
MIDDLEWARE_FILE = os.path.join(OBS_DIR, "middleware.py")


# ---------------------------------------------------------------------------
# Layer 1 — file_path_check
# ---------------------------------------------------------------------------

class TestFilePathCheck:
    """Verify all required observability files exist."""

    def test_init_exists(self):
        assert os.path.isfile(INIT_FILE), f"Missing {INIT_FILE}"

    def test_logging_config_exists(self):
        assert os.path.isfile(LOGGING_FILE), f"Missing {LOGGING_FILE}"

    def test_metrics_collector_exists(self):
        assert os.path.isfile(METRICS_FILE), f"Missing {METRICS_FILE}"

    def test_correlation_exists(self):
        assert os.path.isfile(CORRELATION_FILE), f"Missing {CORRELATION_FILE}"

    def test_middleware_exists(self):
        assert os.path.isfile(MIDDLEWARE_FILE), f"Missing {MIDDLEWARE_FILE}"


# ---------------------------------------------------------------------------
# Layer 2 — semantic_check
# ---------------------------------------------------------------------------

class TestSemanticLogging:
    """Verify structured logging module."""

    @pytest.fixture(autouse=True)
    def _load(self):
        with open(LOGGING_FILE, "r", encoding="utf-8") as f:
            self.src = f.read()
        self.tree = ast.parse(self.src)

    def test_configure_logging_function(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "configure_logging" in funcs, f"Expected configure_logging; found {funcs}"

    def test_get_logger_function(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "get_logger" in funcs, f"Expected get_logger; found {funcs}"

    def test_structlog_usage(self):
        assert "structlog" in self.src, "Should use structlog for structured logging"

    def test_json_renderer(self):
        assert "JSONRenderer" in self.src, "Should support JSON output via JSONRenderer"

    def test_console_renderer(self):
        assert "ConsoleRenderer" in self.src, "Should support ConsoleRenderer for dev"

    def test_correlation_id_injection(self):
        assert "correlation_id" in self.src, (
            "Logging must inject correlation_id from context"
        )

    def test_contextvars_usage(self):
        assert "contextvars" in self.src or "ContextVar" in self.src, (
            "Should use contextvars for correlation ID"
        )


class TestSemanticMetrics:
    """Verify metrics collector module."""

    @pytest.fixture(autouse=True)
    def _load(self):
        with open(METRICS_FILE, "r", encoding="utf-8") as f:
            self.src = f.read()
        self.tree = ast.parse(self.src)

    def test_metrics_collector_class(self):
        classes = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.ClassDef)]
        assert "MetricsCollector" in classes, f"Expected MetricsCollector; found {classes}"

    def test_record_request_method(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "record_request" in funcs, f"Expected record_request; found {funcs}"

    def test_track_in_progress(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "track_in_progress" in funcs, f"Expected track_in_progress; found {funcs}"

    def test_record_error(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "record_error" in funcs, f"Expected record_error; found {funcs}"

    def test_get_metrics(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "get_metrics" in funcs, f"Expected get_metrics; found {funcs}"

    def test_counter_metric(self):
        assert "Counter" in self.src or "counter" in self.src, (
            "MetricsCollector should define Counter metrics"
        )

    def test_histogram_metric(self):
        assert "Histogram" in self.src or "histogram" in self.src, (
            "MetricsCollector should define Histogram metrics"
        )

    def test_gauge_metric(self):
        assert "Gauge" in self.src or "gauge" in self.src, (
            "MetricsCollector should define Gauge metrics"
        )

    def test_histogram_buckets(self):
        assert "0.005" in self.src or "0.01" in self.src, (
            "Histogram should have fine-grained buckets"
        )


class TestSemanticCorrelation:
    """Verify correlation ID module."""

    @pytest.fixture(autouse=True)
    def _load(self):
        with open(CORRELATION_FILE, "r", encoding="utf-8") as f:
            self.src = f.read()
        self.tree = ast.parse(self.src)

    def test_context_var(self):
        assert "ContextVar" in self.src, "Must use ContextVar for correlation ID"

    def test_generate_correlation_id(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "generate_correlation_id" in funcs, (
            f"Expected generate_correlation_id; found {funcs}"
        )

    def test_get_correlation_id(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "get_correlation_id" in funcs, (
            f"Expected get_correlation_id; found {funcs}"
        )

    def test_set_correlation_id(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "set_correlation_id" in funcs, (
            f"Expected set_correlation_id; found {funcs}"
        )

    def test_middleware_class(self):
        classes = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.ClassDef)]
        assert any("Correlation" in c and "Middleware" in c for c in classes), (
            f"Expected CorrelationIDMiddleware class; found {classes}"
        )

    def test_x_correlation_header(self):
        assert "X-Correlation-ID" in self.src or "x-correlation-id" in self.src, (
            "Should read/write X-Correlation-ID header"
        )


class TestSemanticMiddleware:
    """Verify observability middleware."""

    @pytest.fixture(autouse=True)
    def _load(self):
        with open(MIDDLEWARE_FILE, "r", encoding="utf-8") as f:
            self.src = f.read()
        self.tree = ast.parse(self.src)

    def test_middleware_class(self):
        classes = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.ClassDef)]
        assert "ObservabilityMiddleware" in classes, (
            f"Expected ObservabilityMiddleware; found {classes}"
        )

    def test_request_logging(self):
        assert "Request started" in self.src or "request_started" in self.src.lower(), (
            "Middleware should log request start"
        )

    def test_completion_logging(self):
        assert "Request completed" in self.src or "request_completed" in self.src.lower(), (
            "Middleware should log request completion"
        )

    def test_exception_handling(self):
        assert "except" in self.src or "Exception" in self.src, (
            "Middleware should handle exceptions"
        )


# ---------------------------------------------------------------------------
# Layer 3 — functional_check
# ---------------------------------------------------------------------------

class TestFunctionalCorrelation:
    """Run correlation ID functions and verify behavior."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        sys.path.insert(0, OBS_DIR)
        sys.path.insert(0, os.path.dirname(OBS_DIR))
        try:
            from observability.correlation import (
                generate_correlation_id,
                get_correlation_id,
                set_correlation_id,
            )
            self.generate = generate_correlation_id
            self.get = get_correlation_id
            self.set = set_correlation_id
        except ImportError:
            try:
                from correlation import (
                    generate_correlation_id,
                    get_correlation_id,
                    set_correlation_id,
                )
                self.generate = generate_correlation_id
                self.get = get_correlation_id
                self.set = set_correlation_id
            except ImportError:
                pytest.skip("Cannot import correlation module")

    def test_generate_returns_uuid(self):
        cid = self.generate()
        assert len(cid) == 36, f"Expected UUID4 (36 chars); got '{cid}' ({len(cid)})"
        assert cid.count("-") == 4, "UUID4 should have 4 hyphens"

    def test_set_and_get(self):
        self.set("test-correlation-123")
        assert self.get() == "test-correlation-123"

    def test_default_when_not_set(self):
        # Reset context
        import contextvars
        from importlib import reload
        try:
            from observability import correlation as mod
        except ImportError:
            from correlation import correlation as mod
            mod = None
        if mod:
            reload(mod)
        # Fresh context should give default
        cid = self.get()
        assert cid is not None, "get_correlation_id should not return None"


class TestFunctionalMetricsCollector:
    """Run MetricsCollector and verify metric recording."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        sys.path.insert(0, OBS_DIR)
        sys.path.insert(0, os.path.dirname(OBS_DIR))
        try:
            from observability.metrics_collector import MetricsCollector
            self.MetricsCollector = MetricsCollector
        except ImportError:
            try:
                from metrics_collector import MetricsCollector
                self.MetricsCollector = MetricsCollector
            except ImportError:
                pytest.skip("Cannot import MetricsCollector")

    def test_record_request(self):
        mc = self.MetricsCollector()
        mc.record_request("GET", "/users", 200, 0.05)
        # Should not raise

    def test_record_error(self):
        mc = self.MetricsCollector()
        mc.record_error("ValueError", "/users")
        # Should not raise

    def test_get_metrics_returns_string(self):
        mc = self.MetricsCollector()
        mc.record_request("GET", "/users", 200, 0.1)
        output = mc.get_metrics()
        assert isinstance(output, str), "get_metrics should return a string"
        assert len(output) > 0, "Metrics output should not be empty"

    def test_track_in_progress(self):
        mc = self.MetricsCollector()
        with mc.track_in_progress("/users"):
            pass  # gauge incremented then decremented


class TestFunctionalLogging:
    """Run configure_logging and get_logger."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        sys.path.insert(0, OBS_DIR)
        sys.path.insert(0, os.path.dirname(OBS_DIR))
        try:
            from observability.logging_config import configure_logging, get_logger
            self.configure = configure_logging
            self.get_logger = get_logger
        except ImportError:
            try:
                from logging_config import configure_logging, get_logger
                self.configure = configure_logging
                self.get_logger = get_logger
            except ImportError:
                pytest.skip("Cannot import logging_config")

    def test_configure_json(self):
        self.configure(log_level="INFO", json_output=True)
        logger = self.get_logger("test")
        assert logger is not None

    def test_configure_console(self):
        self.configure(log_level="DEBUG", json_output=False)
        logger = self.get_logger("test")
        assert logger is not None
