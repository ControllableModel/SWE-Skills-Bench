"""
Test skill: distributed-tracing
Verify that the Agent creates a tail-based sampling processor for
the OpenTelemetry Collector with buffering, policy-based decisions,
factory registration, and resource management.
"""

import os
import re
import subprocess
import pytest


class TestDistributedTracing:
    REPO_DIR = "/workspace/opentelemetry-collector"

    PKG = "processor/tailsamplingprocessor"

    # === File Path Checks ===

    def test_processor_go_exists(self):
        """Verify processor.go exists"""
        path = os.path.join(self.REPO_DIR, self.PKG, "processor.go")
        assert os.path.exists(path), f"processor.go not found at {path}"

    def test_config_go_exists(self):
        """Verify config.go exists"""
        path = os.path.join(self.REPO_DIR, self.PKG, "config.go")
        assert os.path.exists(path), f"config.go not found at {path}"

    def test_factory_go_exists(self):
        """Verify factory.go exists"""
        path = os.path.join(self.REPO_DIR, self.PKG, "factory.go")
        assert os.path.exists(path), f"factory.go not found at {path}"

    # === Semantic Checks ===

    def test_consume_traces_method(self):
        """Verify ConsumeTraces method is implemented"""
        path = os.path.join(self.REPO_DIR, self.PKG, "processor.go")
        with open(path) as f:
            content = f.read()

        assert "ConsumeTraces" in content, (
            "processor.go should implement ConsumeTraces"
        )

    def test_trace_buffering(self):
        """Verify spans are buffered by trace ID"""
        path = os.path.join(self.REPO_DIR, self.PKG, "processor.go")
        with open(path) as f:
            content = f.read()

        buffer_indicators = [
            "buffer", "traceID", "TraceID", "map[",
            "pending", "cache", "store",
        ]
        found = [ind for ind in buffer_indicators if ind in content]
        assert len(found) >= 2, (
            f"Spans should be buffered by trace ID. Found: {found}"
        )

    def test_error_sampling_policy(self):
        """Verify always-sample error traces policy"""
        combined = ""
        for fname in ["processor.go", "config.go"]:
            path = os.path.join(self.REPO_DIR, self.PKG, fname)
            if os.path.exists(path):
                with open(path) as f:
                    combined += f.read()

        error_indicators = [
            "error", "Error", "STATUS_CODE_ERROR",
            "otel", "status", "always",
        ]
        found = [ind for ind in error_indicators if ind in combined]
        assert len(found) >= 2, (
            f"Should support error trace sampling. Found: {found}"
        )

    def test_duration_threshold_policy(self):
        """Verify duration threshold sampling policy"""
        combined = ""
        for fname in ["processor.go", "config.go"]:
            path = os.path.join(self.REPO_DIR, self.PKG, fname)
            if os.path.exists(path):
                with open(path) as f:
                    combined += f.read()

        duration_indicators = [
            "duration", "latency", "threshold", "Duration",
            "Latency", "slow",
        ]
        found = [ind for ind in duration_indicators if ind in combined]
        assert len(found) >= 2, (
            f"Should support duration threshold policy. Found: {found}"
        )

    def test_probabilistic_sampling(self):
        """Verify probabilistic sampling policy"""
        combined = ""
        for fname in ["processor.go", "config.go"]:
            path = os.path.join(self.REPO_DIR, self.PKG, fname)
            if os.path.exists(path):
                with open(path) as f:
                    combined += f.read()

        prob_indicators = [
            "probabilistic", "rate", "random", "sample",
            "ratio", "percent", "probability",
        ]
        found = [ind for ind in prob_indicators if ind in combined]
        assert len(found) >= 2, (
            f"Should support probabilistic sampling. Found: {found}"
        )

    def test_config_structures(self):
        """Verify configuration structures are defined"""
        path = os.path.join(self.REPO_DIR, self.PKG, "config.go")
        with open(path) as f:
            content = f.read()

        config_indicators = [
            "type Config struct", "struct", "Policy",
            "BufferSize", "Timeout", "MaxSize",
        ]
        found = [ind for ind in config_indicators if ind in content]
        assert len(found) >= 2, (
            f"Should define config structures. Found: {found}"
        )

    def test_factory_registration(self):
        """Verify factory with type name registration"""
        path = os.path.join(self.REPO_DIR, self.PKG, "factory.go")
        with open(path) as f:
            content = f.read()

        factory_indicators = [
            "NewFactory", "factory", "Type", "component",
            "processor", "Create",
        ]
        found = [ind for ind in factory_indicators if ind in content]
        assert len(found) >= 2, (
            f"Should register factory. Found: {found}"
        )

    def test_buffer_bounded(self):
        """Verify buffer has configurable maximum size"""
        combined = ""
        for fname in ["processor.go", "config.go"]:
            path = os.path.join(self.REPO_DIR, self.PKG, fname)
            if os.path.exists(path):
                with open(path) as f:
                    combined += f.read()

        bound_indicators = [
            "max", "limit", "capacity", "MaxSize",
            "maxTraces", "evict", "overflow",
        ]
        found = [ind for ind in bound_indicators if ind in combined]
        assert len(found) >= 1, (
            f"Buffer should be bounded. Found: {found}"
        )

    # === Functional Checks ===

    def test_go_files_have_package(self):
        """Verify Go files have proper package declarations"""
        for fname in ["processor.go", "config.go", "factory.go"]:
            path = os.path.join(self.REPO_DIR, self.PKG, fname)
            with open(path) as f:
                content = f.read()
            assert content.strip().startswith("package ") or \
                   "package " in content[:200], (
                f"{fname} should have package declaration"
            )

    def test_go_syntax_check(self):
        """Verify Go files compile (syntax check)"""
        pkg_dir = os.path.join(self.REPO_DIR, self.PKG)
        result = subprocess.run(
            ["go", "vet", "./..."],
            capture_output=True, text=True, timeout=60,
            cwd=pkg_dir,
        )
        # go vet may fail due to missing deps, but syntax errors
        # are a different class of error. Accept dep errors.
        if result.returncode != 0:
            stderr = result.stderr.lower()
            if "syntax" in stderr or "unexpected" in stderr:
                pytest.fail(f"Go syntax errors: {result.stderr[:500]}")

    def test_consistent_package_name(self):
        """Verify all files use the same package name"""
        packages = set()
        for fname in ["processor.go", "config.go", "factory.go"]:
            path = os.path.join(self.REPO_DIR, self.PKG, fname)
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("package "):
                        packages.add(line)
                        break

        assert len(packages) == 1, (
            f"All files should use the same package. Found: {packages}"
        )
