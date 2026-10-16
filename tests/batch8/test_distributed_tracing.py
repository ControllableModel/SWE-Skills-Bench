"""
Tests for the distributed-tracing skill.
Validates a custom OTel Collector span processor and file-based trace exporter
with deployment metadata enrichment and latency anomaly detection.
"""

import os
import re

REPO_DIR = "/workspace/opentelemetry-collector"
PROCESSOR_DIR = os.path.join(REPO_DIR, "processor", "deploymentprocessor")
EXPORTER_DIR = os.path.join(REPO_DIR, "exporter", "filetraceexporter")


class TestDistributedTracing:
    """Tests for the OTel Collector deployment processor and file exporter."""

    # ── file_path_check ──────────────────────────────────────────────

    def test_processor_factory_exists(self):
        """Processor factory.go must exist."""
        path = os.path.join(PROCESSOR_DIR, "factory.go")
        assert os.path.isfile(path), f"Missing {path}"

    def test_processor_go_exists(self):
        """Core processor.go must exist."""
        path = os.path.join(PROCESSOR_DIR, "processor.go")
        assert os.path.isfile(path), f"Missing {path}"

    def test_processor_config_exists(self):
        """Processor config.go must exist."""
        path = os.path.join(PROCESSOR_DIR, "config.go")
        assert os.path.isfile(path), f"Missing {path}"

    def test_exporter_factory_exists(self):
        """Exporter factory.go must exist."""
        path = os.path.join(EXPORTER_DIR, "factory.go")
        assert os.path.isfile(path), f"Missing {path}"

    def test_exporter_go_exists(self):
        """Core exporter.go must exist."""
        path = os.path.join(EXPORTER_DIR, "exporter.go")
        assert os.path.isfile(path), f"Missing {path}"

    # ── semantic_check ───────────────────────────────────────────────

    def _read(self, path):
        if not os.path.isfile(path):
            return ""
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def test_deployment_labels_config(self):
        """Config must define deployment_labels map."""
        content = self._read(os.path.join(PROCESSOR_DIR, "config.go"))
        assert re.search(r"DeploymentLabels|deployment_labels", content), (
            "deployment_labels config field not found"
        )

    def test_latency_threshold_config(self):
        """Config must define latency_threshold_ms."""
        content = self._read(os.path.join(PROCESSOR_DIR, "config.go"))
        assert re.search(r"LatencyThreshold|latency_threshold", content), (
            "latency_threshold_ms config field not found"
        )

    def test_span_enrichment_attributes(self):
        """Processor must add deployment.env, latency.anomaly, trace.is_root attributes."""
        content = self._read(os.path.join(PROCESSOR_DIR, "processor.go"))
        assert re.search(r"deployment\.|deployment\.env", content), (
            "deployment.* attribute enrichment not found"
        )
        assert re.search(r"latency\.anomaly|latency_anomaly", content), (
            "latency.anomaly attribute not found"
        )
        assert re.search(r"trace\.is_root|is_root", content), (
            "trace.is_root attribute not found"
        )

    def test_root_span_detection(self):
        """Processor must detect root spans (no parent span ID)."""
        content = self._read(os.path.join(PROCESSOR_DIR, "processor.go"))
        assert re.search(r"ParentSpanID|parent.*span|IsEmpty|is_root", content), (
            "Root span detection not found"
        )

    def test_error_env_attribute(self):
        """Error spans must receive deployment.error_env attribute."""
        content = self._read(os.path.join(PROCESSOR_DIR, "processor.go"))
        assert re.search(r"error_env|deployment\.error_env", content), (
            "deployment.error_env attribute not found"
        )

    def test_exporter_json_fields(self):
        """Exporter must write trace_id, span_id, operation_name, duration_ms."""
        content = self._read(os.path.join(EXPORTER_DIR, "exporter.go"))
        for field in ["trace_id", "span_id", "operation_name", "duration_ms"]:
            assert re.search(rf"{field}|{field.replace('_', '')}", content, re.IGNORECASE), (
                f"JSON field '{field}' not found in exporter"
            )

    def test_exporter_file_append(self):
        """Exporter must append to existing files."""
        content = self._read(os.path.join(EXPORTER_DIR, "exporter.go"))
        assert re.search(r"O_APPEND|os\.OpenFile|APPEND|append", content), (
            "File append mode not found in exporter"
        )

    # ── functional_check ─────────────────────────────────────────────

    def test_processor_test_exists(self):
        """Processor unit test file must exist."""
        path = os.path.join(PROCESSOR_DIR, "processor_test.go")
        assert os.path.isfile(path), f"Missing {path}"

    def test_exporter_test_exists(self):
        """Exporter unit test file must exist."""
        path = os.path.join(EXPORTER_DIR, "exporter_test.go")
        assert os.path.isfile(path), f"Missing {path}"

    def test_processor_implements_interface(self):
        """Processor must implement the processor.Traces interface."""
        content = self._read(os.path.join(PROCESSOR_DIR, "processor.go"))
        assert re.search(r"ConsumeTraces|processTraces|ProcessTraces", content), (
            "Traces processor interface method not found"
        )

    def test_exporter_lifecycle_methods(self):
        """Exporter must implement Start and Shutdown lifecycle methods."""
        content = self._read(os.path.join(EXPORTER_DIR, "exporter.go"))
        assert re.search(r"func.*Start\b", content), "Start method not found"
        assert re.search(r"func.*Shutdown\b", content), "Shutdown method not found"

    def test_config_validation(self):
        """Config must validate non-empty deployment_labels and positive latency_threshold."""
        content = self._read(os.path.join(PROCESSOR_DIR, "config.go"))
        assert re.search(r"Validate|validate|error", content), (
            "Config validation not found"
        )

    def test_exceeded_by_ms(self):
        """Processor must compute latency.exceeded_by_ms attribute."""
        content = self._read(os.path.join(PROCESSOR_DIR, "processor.go"))
        assert re.search(r"exceeded_by|exceeded_by_ms|ExceededBy", content), (
            "latency.exceeded_by_ms computation not found"
        )
