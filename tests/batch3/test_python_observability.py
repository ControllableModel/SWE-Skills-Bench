"""
Tests for the python-observability skill.

Validates that structured logging and HTTP golden signal metrics were
implemented for the OpenTelemetry Python SDK.

Repo: opentelemetry-python (https://github.com/open-telemetry/opentelemetry-python)
"""

import os
import re
import subprocess
import sys

REPO_DIR = "/workspace/opentelemetry-python"


class TestFilePathCheck:
    """Verify all required files were created."""

    def test_structured_formatter_exists(self):
        path = os.path.join(
            REPO_DIR, "opentelemetry-sdk", "src", "opentelemetry", "sdk",
            "logs", "structured_formatter.py",
        )
        assert os.path.isfile(path), f"Expected structured_formatter.py at {path}"

    def test_http_signals_exists(self):
        path = os.path.join(
            REPO_DIR, "opentelemetry-sdk", "src", "opentelemetry", "sdk",
            "metrics", "http_signals.py",
        )
        assert os.path.isfile(path), f"Expected http_signals.py at {path}"

    def test_formatter_test_exists(self):
        path = os.path.join(
            REPO_DIR, "opentelemetry-sdk", "tests", "logs",
            "test_structured_formatter.py",
        )
        assert os.path.isfile(path), f"Expected test_structured_formatter.py"

    def test_http_signals_test_exists(self):
        path = os.path.join(
            REPO_DIR, "opentelemetry-sdk", "tests", "metrics",
            "test_http_signals.py",
        )
        assert os.path.isfile(path), f"Expected test_http_signals.py"


class TestSemanticStructuredFormatter:
    """Verify StructuredFormatter for JSON logging with trace correlation."""

    def _read(self):
        path = os.path.join(
            REPO_DIR, "opentelemetry-sdk", "src", "opentelemetry", "sdk",
            "logs", "structured_formatter.py",
        )
        with open(path, "r") as f:
            return f.read()

    def test_class_definition(self):
        content = self._read()
        assert re.search(r"class\s+StructuredFormatter", content), (
            "Expected StructuredFormatter class"
        )

    def test_inherits_formatter(self):
        content = self._read()
        assert re.search(r"logging\.Formatter|Formatter", content), (
            "Expected StructuredFormatter to extend logging.Formatter"
        )

    def test_json_output(self):
        content = self._read()
        assert re.search(r"json\.dumps|json", content), (
            "Expected JSON serialization of log records"
        )

    def test_timestamp_field(self):
        content = self._read()
        assert re.search(r"timestamp|isoformat|ISO", content, re.IGNORECASE), (
            "Expected ISO 8601 timestamp in output"
        )

    def test_trace_id_field(self):
        content = self._read()
        assert re.search(r"trace_id", content), (
            "Expected trace_id field extraction from span context"
        )

    def test_span_id_field(self):
        content = self._read()
        assert re.search(r"span_id", content), (
            "Expected span_id field extraction from span context"
        )

    def test_service_name(self):
        content = self._read()
        assert re.search(r"service\.name|service_name", content), (
            "Expected service.name from Resource"
        )

    def test_fallback_on_error(self):
        content = self._read()
        assert re.search(r"except|fallback|try", content), (
            "Expected exception handling with fallback plain-text output"
        )


class TestSemanticHttpSignals:
    """Verify HttpSignalsCollector for golden signal metrics."""

    def _read(self):
        path = os.path.join(
            REPO_DIR, "opentelemetry-sdk", "src", "opentelemetry", "sdk",
            "metrics", "http_signals.py",
        )
        with open(path, "r") as f:
            return f.read()

    def test_class_definition(self):
        content = self._read()
        assert re.search(r"class\s+HttpSignalsCollector", content), (
            "Expected HttpSignalsCollector class"
        )

    def test_latency_histogram(self):
        content = self._read()
        assert re.search(r"histogram|Histogram|latency", content, re.IGNORECASE), (
            "Expected latency histogram instrument"
        )

    def test_traffic_counter(self):
        content = self._read()
        assert re.search(r"counter|Counter|traffic|request_total", content, re.IGNORECASE), (
            "Expected traffic counter instrument"
        )

    def test_error_counter(self):
        content = self._read()
        assert re.search(r"error.*counter|error_count|status.*500", content, re.IGNORECASE), (
            "Expected error counter (status >= 500)"
        )

    def test_saturation_gauge(self):
        content = self._read()
        assert re.search(r"UpDownCounter|up_down|saturation|concurrent", content, re.IGNORECASE), (
            "Expected saturation UpDownCounter for concurrent requests"
        )

    def test_before_request(self):
        content = self._read()
        assert re.search(r"def\s+before_request", content), (
            "Expected before_request method"
        )

    def test_after_request(self):
        content = self._read()
        assert re.search(r"def\s+after_request", content), (
            "Expected after_request method"
        )

    def test_path_normalization(self):
        content = self._read()
        assert re.search(r"\{id\}|\{uuid\}|normalize|re\.sub", content), (
            "Expected path normalization (numeric → {id}, UUID → {uuid})"
        )

    def test_max_cardinality(self):
        content = self._read()
        assert re.search(r"max_cardinality|cardinality|1000|\{other\}", content), (
            "Expected cardinality protection with max_cardinality"
        )


class TestFunctionalPythonSyntax:
    """Validate Python files compile and tests pass."""

    def test_formatter_syntax(self):
        path = os.path.join(
            REPO_DIR, "opentelemetry-sdk", "src", "opentelemetry", "sdk",
            "logs", "structured_formatter.py",
        )
        with open(path, "r") as f:
            content = f.read()
        compile(content, path, "exec")

    def test_http_signals_syntax(self):
        path = os.path.join(
            REPO_DIR, "opentelemetry-sdk", "src", "opentelemetry", "sdk",
            "metrics", "http_signals.py",
        )
        with open(path, "r") as f:
            content = f.read()
        compile(content, path, "exec")

    def test_agent_tests_pass(self):
        test_paths = []
        for sub in [
            os.path.join("opentelemetry-sdk", "tests", "logs", "test_structured_formatter.py"),
            os.path.join("opentelemetry-sdk", "tests", "metrics", "test_http_signals.py"),
        ]:
            path = os.path.join(REPO_DIR, sub)
            if os.path.isfile(path):
                test_paths.append(path)
        if test_paths:
            result = subprocess.run(
                [sys.executable, "-m", "pytest"] + test_paths + ["-v", "--tb=short"],
                cwd=REPO_DIR,
                capture_output=True,
                text=True,
                timeout=120,
            )
            assert result.returncode == 0, (
                f"Agent tests failed:\n{result.stdout[-1000:]}\n{result.stderr[-500:]}"
            )
