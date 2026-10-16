"""
Test skill: python-observability
Verify that the Agent creates structured logging, Prometheus metrics,
tracing, and FastAPI middleware for OpenTelemetry-based observability.
"""

import os
import re
import ast
import subprocess
import pytest


class TestPythonObservability:
    REPO_DIR = "/workspace/opentelemetry-python"

    # === File Path Checks ===

    def test_observability_files_exist(self):
        """Verify observability module files exist"""
        found = False
        for root, dirs, files in os.walk(self.REPO_DIR):
            if ".git" in root or "node_modules" in root:
                continue
            for f in files:
                if f.endswith(".py") and ("logging" in f.lower() or "metric" in f.lower() or "trac" in f.lower() or "middleware" in f.lower() or "observ" in f.lower()):
                    found = True
                    break
            if found:
                break
        assert found, "Observability module files not found"

    # === Semantic Checks ===

    def test_structured_logging_defined(self):
        """Verify structured logging is implemented"""
        content = self._collect_content()
        content_lower = content.lower()
        has_logging = (
            "structlog" in content_lower
            or "json_format" in content_lower
            or "structuredlog" in content_lower
            or ("logging" in content_lower and "json" in content_lower)
            or "logrecord" in content_lower
        )
        assert has_logging, "Structured logging not found"

    def test_prometheus_metrics_defined(self):
        """Verify Prometheus metrics are defined"""
        content = self._collect_content()
        content_lower = content.lower()
        has_metrics = (
            "prometheus" in content_lower
            or "counter" in content_lower
            or "histogram" in content_lower
            or "gauge" in content_lower
            or "metric" in content_lower
        )
        assert has_metrics, "Prometheus metrics not found"

    def test_tracing_defined(self):
        """Verify distributed tracing is implemented"""
        content = self._collect_content()
        content_lower = content.lower()
        has_tracing = (
            "tracer" in content_lower
            or "span" in content_lower
            or "opentelemetry" in content_lower
            or "trace" in content_lower
        )
        assert has_tracing, "Distributed tracing not found"

    def test_fastapi_middleware_defined(self):
        """Verify FastAPI middleware is implemented"""
        content = self._collect_content()
        content_lower = content.lower()
        has_middleware = (
            "middleware" in content_lower
            or "fastapi" in content_lower
            or "starlette" in content_lower
            or "asgi" in content_lower
        )
        assert has_middleware, "FastAPI middleware not found"

    # === Functional Checks ===

    def test_python_files_valid_syntax(self):
        """Verify Python files have valid AST"""
        py_files = self._find_py_files()
        assert len(py_files) > 0, "No observability Python files found"
        for pf in py_files:
            with open(pf) as fh:
                source = fh.read()
            try:
                ast.parse(source)
            except SyntaxError as e:
                pytest.fail(f"Syntax error in {pf}: {e}")

    def test_python_files_define_classes_or_functions(self):
        """Verify Python files define classes or functions"""
        py_files = self._find_py_files()
        any_def = False
        for pf in py_files:
            with open(pf) as fh:
                source = fh.read()
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                    any_def = True
                    break
            if any_def:
                break
        assert any_def, "No classes or functions found"

    def test_no_hardcoded_endpoints(self):
        """Verify no hardcoded collector endpoints"""
        content = self._collect_content()
        hardcoded = re.findall(r'https?://\d+\.\d+\.\d+\.\d+:\d+', content)
        assert len(hardcoded) == 0, f"Hardcoded endpoints found: {hardcoded}"

    def test_correlation_ids(self):
        """Verify trace/correlation IDs are propagated"""
        content = self._collect_content()
        content_lower = content.lower()
        has_correlation = (
            "trace_id" in content_lower
            or "correlation_id" in content_lower
            or "request_id" in content_lower
            or "span_id" in content_lower
            or "traceparent" in content_lower
        )
        assert has_correlation, "Trace/correlation ID propagation not found"

    def test_exports_defined(self):
        """Verify exporter configuration is defined"""
        content = self._collect_content()
        content_lower = content.lower()
        has_exporter = (
            "exporter" in content_lower
            or "export" in content_lower
            or "otlp" in content_lower
            or "jaeger" in content_lower
            or "zipkin" in content_lower
        )
        assert has_exporter, "Exporter config not defined"

    def _collect_content(self):
        all_content = ""
        for root, dirs, files in os.walk(self.REPO_DIR):
            if ".git" in root or "node_modules" in root:
                continue
            for f in files:
                if f.endswith(".py"):
                    fpath = os.path.join(root, f)
                    try:
                        with open(fpath) as fh:
                            c = fh.read()
                        if any(kw in c.lower() for kw in ["logging", "metric", "trace", "span", "middleware", "observ", "prometheus"]):
                            all_content += c + "\n"
                    except (UnicodeDecodeError, PermissionError):
                        continue
        return all_content

    def _find_py_files(self):
        result = []
        for root, dirs, files in os.walk(self.REPO_DIR):
            if ".git" in root or "node_modules" in root:
                continue
            for f in files:
                if f.endswith(".py") and ("logging" in f.lower() or "metric" in f.lower() or "trac" in f.lower() or "middleware" in f.lower() or "observ" in f.lower()):
                    result.append(os.path.join(root, f))
        return result
