"""
Test skill: distributed-tracing
Verify that the Agent builds an OpenTelemetry Collector pipeline with
a custom dependency processor in Go and a valid collector configuration.
"""

import os
import re
import subprocess
import pytest

try:
    import yaml
except ImportError:
    yaml = None


class TestDistributedTracing:
    REPO_DIR = "/workspace/opentelemetry-collector"

    PROCESSOR_GO = "processor/dependencyprocessor/processor.go"
    CONFIG_GO = "processor/dependencyprocessor/config.go"
    FACTORY_GO = "processor/dependencyprocessor/factory.go"
    PROCESSOR_TEST = "processor/dependencyprocessor/processor_test.go"
    COLLECTOR_CFG = "examples/tracing-pipeline/otel-collector-config.yaml"

    def _read_file(self, rel_path):
        filepath = os.path.join(self.REPO_DIR, rel_path)
        with open(filepath) as f:
            return f.read()

    # === File Path Checks ===

    def test_processor_go_exists(self):
        filepath = os.path.join(self.REPO_DIR, self.PROCESSOR_GO)
        assert os.path.exists(filepath), f"processor.go not found"

    def test_config_go_exists(self):
        filepath = os.path.join(self.REPO_DIR, self.CONFIG_GO)
        assert os.path.exists(filepath), f"config.go not found"

    def test_factory_go_exists(self):
        filepath = os.path.join(self.REPO_DIR, self.FACTORY_GO)
        assert os.path.exists(filepath), f"factory.go not found"

    def test_processor_test_exists(self):
        filepath = os.path.join(self.REPO_DIR, self.PROCESSOR_TEST)
        assert os.path.exists(filepath), f"processor_test.go not found"

    def test_collector_config_exists(self):
        filepath = os.path.join(self.REPO_DIR, self.COLLECTOR_CFG)
        assert os.path.exists(filepath), f"otel-collector-config.yaml not found"

    # === Semantic Checks ===

    def test_processor_implements_traces_interface(self):
        """Verify processTraces method exists"""
        content = self._read_file(self.PROCESSOR_GO)
        assert "processTraces" in content, "Missing processTraces method"
        assert "pdata.Traces" in content, "Missing pdata.Traces parameter"

    def test_processor_extracts_peer_service(self):
        """Verify processor checks peer.service attribute"""
        content = self._read_file(self.PROCESSOR_GO)
        assert "peer.service" in content, "Missing peer.service extraction"

    def test_processor_extracts_net_peer(self):
        """Verify processor checks net.peer.name + net.peer.port"""
        content = self._read_file(self.PROCESSOR_GO)
        assert "net.peer.name" in content, "Missing net.peer.name extraction"

    def test_processor_extracts_http_url(self):
        """Verify processor extracts host from http.url"""
        content = self._read_file(self.PROCESSOR_GO)
        assert "http.url" in content, "Missing http.url extraction"

    def test_processor_sets_dependency_attribute(self):
        """Verify processor sets service.dependency attribute"""
        content = self._read_file(self.PROCESSOR_GO)
        assert "service.dependency" in content, \
            "Missing service.dependency attribute"

    def test_processor_uses_lru_cache(self):
        """Verify LRU cache for dependency pairs"""
        content = self._read_file(self.PROCESSOR_GO)
        has_cache = bool(re.search(r'(lru|cache|LRU|Cache)', content))
        assert has_cache, "Missing LRU cache for dependency pairs"

    def test_config_fields(self):
        """Verify Config struct with CacheTTL, MaxCacheSize, AttributeKey"""
        content = self._read_file(self.CONFIG_GO)
        assert "CacheTTL" in content, "Config missing CacheTTL field"
        assert "MaxCacheSize" in content, "Config missing MaxCacheSize"
        assert "AttributeKey" in content, "Config missing AttributeKey"

    def test_config_validation(self):
        """Verify Validate method rejects invalid config"""
        content = self._read_file(self.CONFIG_GO)
        assert "Validate" in content, "Config missing Validate method"

    def test_factory_new_factory(self):
        """Verify NewFactory function returning processor.Factory"""
        content = self._read_file(self.FACTORY_GO)
        assert "NewFactory" in content, "Missing NewFactory function"
        assert '"dependency"' in content, 'Missing type "dependency"'

    def test_collector_config_receivers(self):
        """Verify OTLP gRPC (4317) and HTTP (4318) receivers"""
        content = self._read_file(self.COLLECTOR_CFG)
        assert "4317" in content, "Config missing OTLP gRPC port 4317"
        assert "4318" in content, "Config missing OTLP HTTP port 4318"

    def test_collector_config_processors(self):
        """Verify memory_limiter, dependency, batch processors"""
        content = self._read_file(self.COLLECTOR_CFG)
        assert "memory_limiter" in content, "Config missing memory_limiter"
        assert "dependency" in content, "Config missing dependency processor"
        assert "batch" in content, "Config missing batch processor"

    def test_collector_config_exporters(self):
        """Verify Jaeger, Prometheus, debug exporters"""
        content = self._read_file(self.COLLECTOR_CFG)
        assert "jaeger" in content, "Config missing Jaeger exporter"
        assert "prometheus" in content, "Config missing Prometheus exporter"
        assert "debug" in content, "Config missing debug exporter"

    def test_collector_config_pipelines(self):
        """Verify traces and metrics pipelines"""
        content = self._read_file(self.COLLECTOR_CFG)
        assert "traces" in content, "Config missing traces pipeline"
        assert "metrics" in content, "Config missing metrics pipeline"

    # === Functional Checks ===

    def test_collector_config_valid_yaml(self):
        """Verify collector config is valid YAML"""
        if yaml is None:
            pytest.skip("PyYAML not installed")
        content = self._read_file(self.COLLECTOR_CFG)
        try:
            doc = yaml.safe_load(content)
        except yaml.YAMLError as e:
            pytest.fail(f"Collector config YAML error: {e}")
        assert "receivers" in doc, "Config missing receivers key"
        assert "exporters" in doc, "Config missing exporters key"
        assert "service" in doc, "Config missing service key"

    def test_go_files_compile(self):
        """Verify Go files compile"""
        proc_dir = os.path.join(self.REPO_DIR, "processor/dependencyprocessor")
        result = subprocess.run(
            ["go", "build", "./..."],
            cwd=proc_dir,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            pytest.fail(f"Go build failed: {result.stderr[:500]}")
