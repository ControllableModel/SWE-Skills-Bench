"""
Test skill: distributed-tracing
Verify that the Agent implements a Tail Sampling Processor for the OpenTelemetry
Collector — tailSamplingProcessor, SamplingPolicy interface (StatusCode, Latency,
ServiceName, AlwaysSample), TraceBuffer, factory, and configuration.
"""

import os
import re
import subprocess
import pytest


class TestDistributedTracing:
    REPO_DIR = "/workspace/opentelemetry-collector"

    # ────── helpers ──────

    def _read(self, rel_path):
        fpath = os.path.join(self.REPO_DIR, rel_path)
        with open(fpath, "r") as f:
            return f.read()

    def _exists(self, rel_path):
        return os.path.isfile(os.path.join(self.REPO_DIR, rel_path))

    _PKG = "processor/tailsamplingprocessor"

    # === File Path Checks ===

    def test_processor_go_exists(self):
        """processor.go must exist"""
        assert self._exists(f"{self._PKG}/processor.go")

    def test_config_go_exists(self):
        """config.go must exist"""
        assert self._exists(f"{self._PKG}/config.go")

    def test_policy_go_exists(self):
        """policy.go must exist"""
        assert self._exists(f"{self._PKG}/policy.go")

    def test_trace_buffer_exists(self):
        """trace_buffer.go must exist"""
        assert self._exists(f"{self._PKG}/trace_buffer.go")

    def test_factory_exists(self):
        """factory.go must exist"""
        assert self._exists(f"{self._PKG}/factory.go")

    def test_processor_test_exists(self):
        """processor_test.go must exist"""
        assert self._exists(f"{self._PKG}/processor_test.go")

    # === Semantic Checks — config.go ===

    def test_config_struct(self):
        """Config struct must be defined"""
        src = self._read(f"{self._PKG}/config.go")
        assert re.search(r'type\s+Config\s+struct', src)

    def test_policy_config_struct(self):
        """PolicyConfig struct must be defined"""
        src = self._read(f"{self._PKG}/config.go")
        assert "PolicyConfig" in src

    def test_policy_types(self):
        """Must define policy types: always_sample, status_code, latency, service_name"""
        src = self._read(f"{self._PKG}/config.go")
        for pt in ["always_sample", "status_code", "latency", "service_name"]:
            assert pt in src, f"Missing policy type: {pt}"

    def test_decision_wait_field(self):
        """Config must have DecisionWait"""
        src = self._read(f"{self._PKG}/config.go")
        assert "DecisionWait" in src

    def test_policy_evaluation_field(self):
        """Config must have PolicyEvaluation (any/all)"""
        src = self._read(f"{self._PKG}/config.go")
        assert "PolicyEvaluation" in src

    # === Semantic Checks — policy.go ===

    def test_sampling_policy_interface(self):
        """SamplingPolicy interface must be defined"""
        src = self._read(f"{self._PKG}/policy.go")
        assert re.search(r'type\s+SamplingPolicy\s+interface', src)

    def test_sampling_decision_enum(self):
        """SamplingDecision type with Pending, Sampled, NotSampled"""
        src = self._read(f"{self._PKG}/policy.go")
        assert "SamplingDecision" in src
        for val in ["Pending", "Sampled", "NotSampled"]:
            assert val in src, f"Missing SamplingDecision: {val}"

    def test_trace_data_struct(self):
        """TraceData struct must be defined"""
        src = self._read(f"{self._PKG}/policy.go")
        assert "TraceData" in src

    def test_status_code_policy(self):
        """StatusCodePolicy must be implemented"""
        src = self._read(f"{self._PKG}/policy.go")
        assert "StatusCodePolicy" in src or "statusCodePolicy" in src

    def test_latency_policy(self):
        """LatencyPolicy must be implemented"""
        src = self._read(f"{self._PKG}/policy.go")
        assert "LatencyPolicy" in src or "latencyPolicy" in src

    def test_service_name_policy(self):
        """ServiceNamePolicy must be implemented"""
        src = self._read(f"{self._PKG}/policy.go")
        assert "ServiceNamePolicy" in src or "serviceNamePolicy" in src

    def test_always_sample_policy(self):
        """AlwaysSamplePolicy must be implemented"""
        src = self._read(f"{self._PKG}/policy.go")
        assert "AlwaysSample" in src or "alwaysSample" in src

    # === Semantic Checks — trace_buffer.go ===

    def test_trace_buffer_struct(self):
        """TraceBuffer struct must be defined"""
        src = self._read(f"{self._PKG}/trace_buffer.go")
        assert re.search(r'type\s+TraceBuffer\s+struct', src)

    def test_trace_buffer_mutex(self):
        """TraceBuffer must use sync.RWMutex"""
        src = self._read(f"{self._PKG}/trace_buffer.go")
        assert "RWMutex" in src or "Mutex" in src

    def test_trace_buffer_methods(self):
        """TraceBuffer must have Add, Get, Delete, Evict, Size methods"""
        src = self._read(f"{self._PKG}/trace_buffer.go")
        for method in ["Add", "Get", "Delete", "Evict", "Size"]:
            assert method in src, f"Missing method: {method}"

    # === Semantic Checks — processor.go ===

    def test_tail_sampling_processor_struct(self):
        """tailSamplingProcessor struct must be defined"""
        src = self._read(f"{self._PKG}/processor.go")
        assert "tailSamplingProcessor" in src

    def test_consume_traces_method(self):
        """ConsumeTraces method must be defined"""
        src = self._read(f"{self._PKG}/processor.go")
        assert "ConsumeTraces" in src

    def test_make_decisions_method(self):
        """makeDecisions method must exist"""
        src = self._read(f"{self._PKG}/processor.go")
        assert "makeDecisions" in src or "makeDecision" in src

    def test_start_shutdown(self):
        """Start and Shutdown methods must exist"""
        src = self._read(f"{self._PKG}/processor.go")
        assert "Start" in src and "Shutdown" in src

    # === Semantic Checks — factory.go ===

    def test_new_factory(self):
        """NewFactory function must exist"""
        src = self._read(f"{self._PKG}/factory.go")
        assert "NewFactory" in src

    def test_component_type_name(self):
        """Component type name must be 'tail_sampling'"""
        src = self._read(f"{self._PKG}/factory.go")
        assert "tail_sampling" in src

    # === Functional Checks ===

    def test_go_build(self):
        """Package must build"""
        result = subprocess.run(
            ["go", "build", f"./{self._PKG}/..."],
            capture_output=True, text=True, cwd=self.REPO_DIR, timeout=300,
        )
        assert result.returncode == 0, (
            f"go build failed:\n{result.stdout}\n{result.stderr}"
        )

    def test_unit_tests_pass(self):
        """Processor tests must pass"""
        result = subprocess.run(
            ["go", "test", "-v", f"./{self._PKG}/..."],
            capture_output=True, text=True, cwd=self.REPO_DIR, timeout=300,
        )
        assert result.returncode == 0, (
            f"Tests failed:\n{result.stdout}\n{result.stderr}"
        )
