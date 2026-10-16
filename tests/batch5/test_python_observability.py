"""
Test skill: python-observability
Verify that the Agent adds structured logging and custom metrics
to the OpenTelemetry WSGI instrumentation module.
"""

import os
import re
import ast
import pytest


class TestPythonObservability:
    REPO_DIR = "/workspace/opentelemetry-python"

    BASE = "instrumentation/opentelemetry-instrumentation-wsgi/src/opentelemetry/instrumentation/wsgi"
    MIDDLEWARE = f"{BASE}/middleware.py"
    METRICS = f"{BASE}/metrics.py"
    LOGGING_UTILS = f"{BASE}/logging_utils.py"
    TEST_METRICS = "instrumentation/opentelemetry-instrumentation-wsgi/tests/test_metrics.py"
    TEST_LOGGING = "instrumentation/opentelemetry-instrumentation-wsgi/tests/test_logging_correlation.py"

    def _read_file(self, rel_path):
        filepath = os.path.join(self.REPO_DIR, rel_path)
        with open(filepath) as f:
            return f.read()

    # === File Path Checks ===

    def test_metrics_module_exists(self):
        filepath = os.path.join(self.REPO_DIR, self.METRICS)
        assert os.path.exists(filepath), f"metrics.py not found"

    def test_logging_utils_exists(self):
        filepath = os.path.join(self.REPO_DIR, self.LOGGING_UTILS)
        assert os.path.exists(filepath), f"logging_utils.py not found"

    def test_middleware_exists(self):
        filepath = os.path.join(self.REPO_DIR, self.MIDDLEWARE)
        assert os.path.exists(filepath), f"middleware.py not found"

    def test_test_metrics_exists(self):
        filepath = os.path.join(self.REPO_DIR, self.TEST_METRICS)
        assert os.path.exists(filepath), f"test_metrics.py not found"

    def test_test_logging_exists(self):
        filepath = os.path.join(self.REPO_DIR, self.TEST_LOGGING)
        assert os.path.exists(filepath), f"test_logging_correlation.py not found"

    # === Semantic Checks ===

    def test_metrics_defines_duration_histogram(self):
        """Verify http_server_request_duration_seconds histogram exists"""
        content = self._read_file(self.METRICS)
        assert "http_server_request_duration_seconds" in content, \
            "metrics.py missing duration histogram"
        assert "histogram" in content.lower() or "Histogram" in content, \
            "metrics.py missing Histogram instrument type"

    def test_metrics_defines_request_counter(self):
        """Verify http_server_requests_total counter"""
        content = self._read_file(self.METRICS)
        assert "http_server_requests_total" in content, \
            "metrics.py missing request counter"

    def test_metrics_defines_error_counter(self):
        """Verify http_server_errors_total counter"""
        content = self._read_file(self.METRICS)
        assert "http_server_errors_total" in content, \
            "metrics.py missing error counter"

    def test_metrics_labels(self):
        """Verify labels include method, route, status_code"""
        content = self._read_file(self.METRICS)
        for label in ["method", "route", "status_code"]:
            assert label in content, f"metrics.py missing label: {label}"

    def test_metrics_histogram_bucket_boundaries(self):
        """Verify histogram uses correct bucket boundaries"""
        content = self._read_file(self.METRICS)
        assert "0.005" in content, "Missing bucket boundary 0.005"
        assert "10.0" in content, "Missing bucket boundary 10.0"

    def test_logging_utils_trace_injection(self):
        """Verify logging_utils injects trace_id and span_id"""
        content = self._read_file(self.LOGGING_UTILS)
        assert "trace_id" in content, "logging_utils missing trace_id injection"
        assert "span_id" in content, "logging_utils missing span_id injection"

    def test_middleware_opt_in_flags(self):
        """Verify middleware has enable_metrics and enable_log_correlation flags"""
        content = self._read_file(self.MIDDLEWARE)
        assert "enable_metrics" in content, "middleware missing enable_metrics flag"
        assert "enable_log_correlation" in content, \
            "middleware missing enable_log_correlation flag"

    def test_middleware_records_latency(self):
        """Verify middleware records request duration"""
        content = self._read_file(self.MIDDLEWARE)
        has_timing = bool(re.search(r'(time\.|duration|elapsed|latency)', content))
        assert has_timing, "middleware missing request duration recording"

    def test_middleware_uses_meter_provider(self):
        """Verify metrics obtained from global MeterProvider"""
        content = self._read_file(self.METRICS)
        has_meter = bool(re.search(r'(MeterProvider|get_meter|meter)', content))
        assert has_meter, "metrics.py missing MeterProvider usage"

    # === Functional Checks ===

    def test_all_new_files_valid_python(self):
        """Verify all new Python files have valid syntax"""
        for path in [self.METRICS, self.LOGGING_UTILS,
                     self.TEST_METRICS, self.TEST_LOGGING]:
            filepath = os.path.join(self.REPO_DIR, path)
            with open(filepath) as f:
                try:
                    ast.parse(f.read())
                except SyntaxError as e:
                    pytest.fail(f"{path} syntax error: {e}")

    def test_test_metrics_has_assertions(self):
        """Verify test_metrics.py has meaningful test functions"""
        content = self._read_file(self.TEST_METRICS)
        tree = ast.parse(content)
        test_funcs = [
            n.name for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")
        ]
        assert len(test_funcs) >= 3, \
            f"test_metrics.py has only {len(test_funcs)} tests, expected >=3"

    def test_test_logging_has_assertions(self):
        """Verify test_logging_correlation.py has meaningful tests"""
        content = self._read_file(self.TEST_LOGGING)
        tree = ast.parse(content)
        test_funcs = [
            n.name for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")
        ]
        assert len(test_funcs) >= 2, \
            f"test_logging.py has only {len(test_funcs)} tests, expected >=2"
