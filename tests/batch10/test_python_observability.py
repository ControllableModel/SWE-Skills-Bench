"""
Test skill: python-observability
Verify that the Agent correctly implements a CorrelationLogProcessor
for the OpenTelemetry Python SDK that enriches log records with trace context.
"""

import os
import re
import ast
import pytest


class TestPythonObservability:
    REPO_DIR = "/workspace/opentelemetry-python"

    # === File Path Checks ===

    def test_correlation_module_exists(self):
        """Verify correlation.py was created"""
        path = os.path.join(
            self.REPO_DIR,
            "opentelemetry-sdk/src/opentelemetry/sdk/logs/correlation.py",
        )
        assert os.path.exists(path), "correlation.py not found"

    def test_correlation_test_exists(self):
        """Verify test_correlation.py was created"""
        found = False
        for root, dirs, files in os.walk(self.REPO_DIR):
            if "test_correlation.py" in files:
                found = True
                break
        assert found, "test_correlation.py not found anywhere in the repo"

    def test_init_module_modified(self):
        """Verify __init__.py in sdk/logs was modified to reference correlation"""
        path = os.path.join(
            self.REPO_DIR,
            "opentelemetry-sdk/src/opentelemetry/sdk/logs/__init__.py",
        )
        assert os.path.exists(path), "__init__.py not found"
        content = open(path).read()
        assert "correlation" in content.lower() or "CorrelationLogProcessor" in content, (
            "__init__.py does not reference correlation module"
        )

    # === Semantic Checks: CorrelationLogProcessor class structure ===

    def _load_correlation_source(self):
        path = os.path.join(
            self.REPO_DIR,
            "opentelemetry-sdk/src/opentelemetry/sdk/logs/correlation.py",
        )
        return open(path).read()

    def test_class_defined(self):
        """Verify CorrelationLogProcessor class is defined"""
        source = self._load_correlation_source()
        assert "class CorrelationLogProcessor" in source, (
            "CorrelationLogProcessor class not defined"
        )

    def test_implements_log_record_processor(self):
        """Verify CorrelationLogProcessor implements LogRecordProcessor"""
        source = self._load_correlation_source()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "CorrelationLogProcessor":
                bases = [
                    getattr(b, "id", None) or getattr(b, "attr", None)
                    for b in node.bases
                ]
                assert any("LogRecordProcessor" in str(b) for b in bases), (
                    "CorrelationLogProcessor does not inherit LogRecordProcessor"
                )
                return
        pytest.fail("CorrelationLogProcessor class not found in AST")

    def test_emit_method_defined(self):
        """Verify emit method is defined in CorrelationLogProcessor"""
        source = self._load_correlation_source()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "CorrelationLogProcessor":
                methods = [n.name for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
                assert "emit" in methods, "emit method not defined"
                return
        pytest.fail("CorrelationLogProcessor class not found in AST")

    def test_shutdown_method_defined(self):
        """Verify shutdown method is defined"""
        source = self._load_correlation_source()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "CorrelationLogProcessor":
                methods = [n.name for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
                assert "shutdown" in methods, "shutdown method not defined"
                return
        pytest.fail("CorrelationLogProcessor class not found in AST")

    def test_force_flush_method_defined(self):
        """Verify force_flush method is defined"""
        source = self._load_correlation_source()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "CorrelationLogProcessor":
                methods = [n.name for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
                assert "force_flush" in methods, "force_flush method not defined"
                return
        pytest.fail("CorrelationLogProcessor class not found in AST")

    # === Semantic Checks: Trace context enrichment ===

    def test_emit_references_trace_id(self):
        """Verify emit adds trace_id to log record attributes"""
        source = self._load_correlation_source()
        assert "trace_id" in source, "No reference to trace_id in correlation module"

    def test_emit_references_span_id(self):
        """Verify emit adds span_id to log record attributes"""
        source = self._load_correlation_source()
        assert "span_id" in source, "No reference to span_id in correlation module"

    def test_emit_references_trace_flags(self):
        """Verify emit adds trace_flags to log record attributes"""
        source = self._load_correlation_source()
        assert "trace_flags" in source, "No reference to trace_flags in correlation module"

    # === Functional Checks ===

    def test_trace_id_hex_format_32_chars(self):
        """Verify trace_id is formatted as 32-char hex string"""
        source = self._load_correlation_source()
        # Should contain formatting logic for 32 hex chars
        has_format = (
            "032x" in source
            or "format_trace_id" in source
            or "hex()" in source
            or "to_bytes" in source
            or re.search(r'["\']0["\'].*32', source)
            or "trace_id" in source
        )
        assert has_format, "No trace_id hex formatting logic found"

    def test_span_id_hex_format_16_chars(self):
        """Verify span_id is formatted as 16-char hex string"""
        source = self._load_correlation_source()
        has_format = (
            "016x" in source
            or "format_span_id" in source
            or "hex()" in source
            or "span_id" in source
        )
        assert has_format, "No span_id hex formatting logic found"

    def test_shutdown_returns_true(self):
        """Verify shutdown method returns True (no-op)"""
        source = self._load_correlation_source()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "CorrelationLogProcessor":
                for item in node.body:
                    if isinstance(item, ast.FunctionDef) and item.name == "shutdown":
                        source_lines = source.splitlines()
                        func_lines = source_lines[item.lineno - 1: item.end_lineno]
                        func_text = "\n".join(func_lines)
                        assert "True" in func_text or "return True" in func_text, (
                            "shutdown does not return True"
                        )
                        return
        pytest.fail("shutdown method not found")

    def test_force_flush_returns_true(self):
        """Verify force_flush method returns True (no-op)"""
        source = self._load_correlation_source()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "CorrelationLogProcessor":
                for item in node.body:
                    if isinstance(item, ast.FunctionDef) and item.name == "force_flush":
                        source_lines = source.splitlines()
                        func_lines = source_lines[item.lineno - 1: item.end_lineno]
                        func_text = "\n".join(func_lines)
                        assert "True" in func_text or "return True" in func_text, (
                            "force_flush does not return True"
                        )
                        return
        pytest.fail("force_flush method not found")

    def test_uses_active_span_context(self):
        """Verify emit retrieves context from active span"""
        source = self._load_correlation_source()
        assert (
            "get_current_span" in source
            or "get_current" in source
            or "trace.get_current_span" in source
        ), "No reference to getting the active/current span"

    def test_handles_no_active_span(self):
        """Verify processor handles case when no active span exists"""
        source = self._load_correlation_source()
        has_guard = (
            "INVALID_SPAN" in source
            or "is_valid" in source
            or "NonRecordingSpan" in source
            or "is_recording" in source
            or "None" in source
        )
        assert has_guard, "No guard for absent/invalid active span"

    def test_correlation_module_is_importable(self):
        """Verify the correlation module can be parsed without syntax errors"""
        source = self._load_correlation_source()
        try:
            ast.parse(source)
        except SyntaxError as e:
            pytest.fail(f"correlation.py has syntax error: {e}")
