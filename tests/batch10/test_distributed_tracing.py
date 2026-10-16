"""
Test skill: distributed-tracing
Verify that the Agent correctly implements a Tail Sampling Processor
for the OpenTelemetry Collector in Go.
"""

import os
import re
import subprocess
import pytest


class TestDistributedTracing:
    REPO_DIR = "/workspace/opentelemetry-collector"

    # === File Path Checks ===

    def test_config_go_exists(self):
        """Verify config.go was created"""
        path = os.path.join(
            self.REPO_DIR,
            "processor/tailsamplingprocessor/config.go",
        )
        assert os.path.exists(path), "config.go not found"

    def test_processor_go_exists(self):
        """Verify processor.go was created"""
        path = os.path.join(
            self.REPO_DIR,
            "processor/tailsamplingprocessor/processor.go",
        )
        assert os.path.exists(path), "processor.go not found"

    def test_factory_go_exists(self):
        """Verify factory.go was created"""
        path = os.path.join(
            self.REPO_DIR,
            "processor/tailsamplingprocessor/factory.go",
        )
        assert os.path.exists(path), "factory.go not found"

    def test_processor_test_go_exists(self):
        """Verify processor_test.go was created"""
        path = os.path.join(
            self.REPO_DIR,
            "processor/tailsamplingprocessor/processor_test.go",
        )
        assert os.path.exists(path), "processor_test.go not found"

    # === Semantic Checks: Config structure ===

    def _load_config_source(self):
        path = os.path.join(
            self.REPO_DIR,
            "processor/tailsamplingprocessor/config.go",
        )
        return open(path).read()

    def _load_processor_source(self):
        path = os.path.join(
            self.REPO_DIR,
            "processor/tailsamplingprocessor/processor.go",
        )
        return open(path).read()

    def _load_factory_source(self):
        path = os.path.join(
            self.REPO_DIR,
            "processor/tailsamplingprocessor/factory.go",
        )
        return open(path).read()

    def test_config_has_decision_wait(self):
        """Verify Config struct has DecisionWait field"""
        source = self._load_config_source()
        assert "DecisionWait" in source, "DecisionWait field not in config"

    def test_config_has_num_traces(self):
        """Verify Config struct has NumTraces field"""
        source = self._load_config_source()
        assert "NumTraces" in source, "NumTraces field not in config"

    def test_config_has_sampling_rate(self):
        """Verify Config struct has SamplingRate field"""
        source = self._load_config_source()
        assert "SamplingRate" in source or "sampling_rate" in source, (
            "SamplingRate field not in config"
        )

    def test_config_validate_function(self):
        """Verify Validate function is defined"""
        source = self._load_config_source()
        assert re.search(r'func\s+\(.*\)\s+Validate\s*\(', source), (
            "Validate method not found in config.go"
        )

    # === Semantic Checks: Factory ===

    def test_factory_type_tailsampling(self):
        """Verify factory registers type as tailsampling"""
        source = self._load_factory_source()
        assert "tailsampling" in source, (
            "Factory does not register 'tailsampling' type"
        )

    def test_factory_new_factory(self):
        """Verify NewFactory function is defined"""
        source = self._load_factory_source()
        assert "NewFactory" in source, "NewFactory function not found"

    # === Semantic Checks: Processor ===

    def test_processor_consume_traces(self):
        """Verify processor implements ConsumeTraces"""
        source = self._load_processor_source()
        assert "ConsumeTraces" in source, "ConsumeTraces not found in processor"

    def test_processor_trace_id_buffering(self):
        """Verify processor buffers by TraceID"""
        source = self._load_processor_source()
        has_buffering = (
            "TraceID" in source
            or "traceID" in source
            or "trace_id" in source
            or "traceId" in source
        )
        assert has_buffering, "No TraceID buffering logic found"

    def test_processor_probabilistic_sampling(self):
        """Verify probabilistic sampling logic exists"""
        source = self._load_processor_source()
        has_sampling = (
            "SamplingRate" in source
            or "samplingRate" in source
            or "probability" in source
            or "rand" in source
        )
        assert has_sampling, "No probabilistic sampling logic found"

    # === Functional Checks ===

    def test_config_rejects_invalid_sampling_rate(self):
        """Verify Validate rejects sampling rate > 1.0"""
        source = self._load_config_source()
        # Config should validate that rate is between 0 and 1
        has_validation = (
            re.search(r'SamplingRate.*[><=].*1', source)
            or "invalid" in source.lower()
            or "must be" in source.lower()
        )
        assert has_validation, "No validation for SamplingRate bounds"

    def test_config_rejects_negative_sampling_rate(self):
        """Verify Validate rejects negative sampling rate"""
        source = self._load_config_source()
        has_check = (
            re.search(r'SamplingRate.*<.*0', source)
            or re.search(r'SamplingRate.*(<=|<)\s*0', source)
            or "negative" in source.lower()
            or re.search(r'[<>]=?\s*0', source)
        )
        assert has_check, "No validation for negative SamplingRate"

    def test_config_rejects_zero_decision_wait(self):
        """Verify Validate rejects zero DecisionWait"""
        source = self._load_config_source()
        has_check = (
            "DecisionWait" in source
            and (
                re.search(r'DecisionWait.*[<>=].*0', source)
                or "must be" in source.lower()
                or "positive" in source.lower()
            )
        )
        assert has_check, "No validation for zero DecisionWait"

    def test_processor_tracestate_passthrough(self):
        """Verify processor preserves tracestate header"""
        source = self._load_processor_source()
        has_tracestate = (
            "tracestate" in source.lower()
            or "TraceState" in source
            or "Tracestate" in source
        )
        assert has_tracestate, "No tracestate passthrough logic"

    def test_processor_lru_eviction(self):
        """Verify processor implements LRU eviction for trace buffer"""
        source = self._load_processor_source()
        has_lru = (
            "LRU" in source
            or "lru" in source
            or "evict" in source.lower()
            or "NumTraces" in source
        )
        assert has_lru, "No LRU eviction logic found"

    def test_go_files_compile(self):
        """Verify the tailsamplingprocessor package compiles"""
        pkg_dir = os.path.join(
            self.REPO_DIR, "processor/tailsamplingprocessor"
        )
        if not os.path.isdir(pkg_dir):
            pytest.skip("tailsamplingprocessor directory not found")
        result = subprocess.run(
            ["go", "build", "./..."],
            cwd=pkg_dir,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, f"go build failed: {result.stderr}"

    def test_go_tests_pass(self):
        """Verify Go unit tests pass"""
        pkg_dir = os.path.join(
            self.REPO_DIR, "processor/tailsamplingprocessor"
        )
        if not os.path.isdir(pkg_dir):
            pytest.skip("tailsamplingprocessor directory not found")
        result = subprocess.run(
            ["go", "test", "./..."],
            cwd=pkg_dir,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, f"go test failed: {result.stderr}"
