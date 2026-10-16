"""
Tests for the distributed-tracing skill.

Validates that a custom trace processor with sampling and tail-based
analysis was implemented for the OpenTelemetry Collector.

Repo: opentelemetry-collector (https://github.com/open-telemetry/opentelemetry-collector)
"""

import os
import re
import subprocess

REPO_DIR = "/workspace/opentelemetry-collector"


class TestFilePathCheck:
    """Verify all required files were created."""

    def test_factory_exists(self):
        path = os.path.join(
            REPO_DIR, "processor", "traceanalysisprocessor", "factory.go",
        )
        assert os.path.isfile(path), f"Expected factory.go at {path}"

    def test_config_exists(self):
        path = os.path.join(
            REPO_DIR, "processor", "traceanalysisprocessor", "config.go",
        )
        assert os.path.isfile(path), f"Expected config.go at {path}"

    def test_processor_exists(self):
        path = os.path.join(
            REPO_DIR, "processor", "traceanalysisprocessor", "processor.go",
        )
        assert os.path.isfile(path), f"Expected processor.go at {path}"

    def test_processor_test_exists(self):
        path = os.path.join(
            REPO_DIR, "processor", "traceanalysisprocessor",
            "processor_test.go",
        )
        assert os.path.isfile(path), f"Expected processor_test.go"


class TestSemanticConfig:
    """Verify configuration struct and validation."""

    def _read(self):
        path = os.path.join(
            REPO_DIR, "processor", "traceanalysisprocessor", "config.go",
        )
        with open(path, "r") as f:
            return f.read()

    def test_config_struct(self):
        content = self._read()
        assert re.search(r"type\s+Config\s+struct", content), (
            "Expected Config struct definition"
        )

    def test_sampling_rate_field(self):
        content = self._read()
        assert re.search(r"SamplingRate|sampling_rate|samplingRate", content), (
            "Expected sampling_rate field (float, 0.0-1.0)"
        )

    def test_error_sampling_rate(self):
        content = self._read()
        assert re.search(r"ErrorSamplingRate|error_sampling_rate", content), (
            "Expected error_sampling_rate field"
        )

    def test_latency_threshold(self):
        content = self._read()
        assert re.search(r"LatencyThreshold|latency_threshold_ms", content), (
            "Expected latency_threshold_ms field"
        )

    def test_max_traces_per_second(self):
        content = self._read()
        assert re.search(r"MaxTraces|max_traces_per_second", content), (
            "Expected max_traces_per_second field"
        )

    def test_analysis_enabled(self):
        content = self._read()
        assert re.search(r"AnalysisEnabled|analysis_enabled", content), (
            "Expected analysis_enabled field"
        )

    def test_validation(self):
        content = self._read()
        assert re.search(r"Validate|validate|error", content), (
            "Expected configuration validation"
        )


class TestSemanticFactory:
    """Verify component factory registration."""

    def _read(self):
        path = os.path.join(
            REPO_DIR, "processor", "traceanalysisprocessor", "factory.go",
        )
        with open(path, "r") as f:
            return f.read()

    def test_type_string(self):
        content = self._read()
        assert re.search(r"trace_analysis|traceanalysis", content), (
            "Expected processor type string 'trace_analysis'"
        )

    def test_new_factory(self):
        content = self._read()
        assert re.search(r"NewFactory|newFactory", content), (
            "Expected NewFactory function"
        )


class TestSemanticProcessor:
    """Verify processor implementation with sampling and analysis."""

    def _read(self):
        path = os.path.join(
            REPO_DIR, "processor", "traceanalysisprocessor", "processor.go",
        )
        with open(path, "r") as f:
            return f.read()

    def test_consume_traces(self):
        content = self._read()
        assert re.search(r"ConsumeTraces|consumeTraces", content), (
            "Expected ConsumeTraces method (processor.Traces interface)"
        )

    def test_deterministic_sampling(self):
        content = self._read()
        assert re.search(r"hash|Hash|traceID|TraceID", content), (
            "Expected deterministic hash-based sampling on trace ID"
        )

    def test_error_priority(self):
        content = self._read()
        assert re.search(r"Error|StatusCode|error.*sampl", content, re.IGNORECASE), (
            "Expected error-priority sampling (always keep errors)"
        )

    def test_latency_priority(self):
        content = self._read()
        assert re.search(r"latency|duration|threshold", content, re.IGNORECASE), (
            "Expected latency-priority sampling for slow traces"
        )

    def test_rate_limiting(self):
        content = self._read()
        assert re.search(r"token.*bucket|rate.*limit|RateLimit", content, re.IGNORECASE), (
            "Expected token-bucket rate limiting"
        )

    def test_traces_dropped_counter(self):
        content = self._read()
        assert re.search(r"traces_dropped|dropped|counter", content, re.IGNORECASE), (
            "Expected traces_dropped_total counter metric"
        )

    def test_span_count_attribute(self):
        content = self._read()
        assert re.search(r"trace\.span_count|span_count|SpanCount", content), (
            "Expected trace.span_count resource attribute"
        )

    def test_trace_depth_attribute(self):
        content = self._read()
        assert re.search(r"trace\.depth|depth|Depth", content), (
            "Expected trace.depth computation"
        )

    def test_trace_duration(self):
        content = self._read()
        assert re.search(r"trace\.duration|duration_ms|Duration", content), (
            "Expected trace.duration_ms attribute"
        )

    def test_has_errors_attribute(self):
        content = self._read()
        assert re.search(r"has_errors|HasErrors|trace\.has_errors", content), (
            "Expected trace.has_errors attribute"
        )

    def test_service_count(self):
        content = self._read()
        assert re.search(r"service_count|ServiceCount|service\.name", content), (
            "Expected trace.service_count attribute"
        )

    def test_orphan_span_detection(self):
        content = self._read()
        assert re.search(r"orphan|Orphan|parent.*not.*found", content, re.IGNORECASE), (
            "Expected orphan span detection"
        )


class TestFunctionalGoSyntax:
    """Validate Go files are syntactically correct."""

    def _base_dir(self):
        return os.path.join(
            REPO_DIR, "processor", "traceanalysisprocessor",
        )

    def test_package_declaration(self):
        path = os.path.join(self._base_dir(), "processor.go")
        with open(path, "r") as f:
            content = f.read(500)
        assert re.search(r"^package\s+\w+", content, re.MULTILINE), (
            "Expected package declaration"
        )

    def test_go_vet(self):
        result = subprocess.run(
            ["go", "vet", "./processor/traceanalysisprocessor/..."],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            stderr = result.stderr.lower()
            assert "syntax error" not in stderr, (
                f"Go syntax errors: {result.stderr[:500]}"
            )

    def test_processor_test_funcs(self):
        path = os.path.join(self._base_dir(), "processor_test.go")
        with open(path, "r") as f:
            content = f.read()
        count = len(re.findall(r"func\s+Test\w+", content))
        assert count >= 3, (
            f"Expected >= 3 test functions, found {count}"
        )
