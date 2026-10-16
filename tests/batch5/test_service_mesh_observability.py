"""
Test skill: service-mesh-observability
Verify that the Agent builds a Go metrics aggregation service for Linkerd
with golden signals, health checker, topology builder, and REST API.
"""

import os
import re
import subprocess
import pytest


class TestServiceMeshObservability:
    REPO_DIR = "/workspace/linkerd2"

    AGGREGATOR = "viz/metrics/aggregator.go"
    GOLDEN_SIGNALS = "viz/metrics/golden_signals.go"
    HEALTH_CHECKER = "viz/metrics/health_checker.go"
    API = "viz/metrics/api.go"
    TOPOLOGY = "viz/metrics/topology.go"
    TESTS = "viz/metrics/aggregator_test.go"

    def _read_file(self, rel_path):
        filepath = os.path.join(self.REPO_DIR, rel_path)
        with open(filepath) as f:
            return f.read()

    # === File Path Checks ===

    def test_aggregator_exists(self):
        filepath = os.path.join(self.REPO_DIR, self.AGGREGATOR)
        assert os.path.exists(filepath), f"aggregator.go not found"

    def test_golden_signals_exists(self):
        filepath = os.path.join(self.REPO_DIR, self.GOLDEN_SIGNALS)
        assert os.path.exists(filepath), f"golden_signals.go not found"

    def test_health_checker_exists(self):
        filepath = os.path.join(self.REPO_DIR, self.HEALTH_CHECKER)
        assert os.path.exists(filepath), f"health_checker.go not found"

    def test_api_exists(self):
        filepath = os.path.join(self.REPO_DIR, self.API)
        assert os.path.exists(filepath), f"api.go not found"

    def test_topology_exists(self):
        filepath = os.path.join(self.REPO_DIR, self.TOPOLOGY)
        assert os.path.exists(filepath), f"topology.go not found"

    def test_aggregator_test_exists(self):
        filepath = os.path.join(self.REPO_DIR, self.TESTS)
        assert os.path.exists(filepath), f"aggregator_test.go not found"

    # === Semantic Checks ===

    def test_golden_signals_struct_fields(self):
        """Verify GoldenSignals struct with RequestRate, SuccessRate, latencies"""
        content = self._read_file(self.GOLDEN_SIGNALS)
        assert "GoldenSignals" in content, "Missing GoldenSignals struct"
        for field in ["RequestRate", "SuccessRate", "P50Latency",
                      "P95Latency", "P99Latency"]:
            assert field in content, f"GoldenSignals missing field: {field}"

    def test_service_health_struct(self):
        """Verify ServiceHealth struct with Status field"""
        content = self._read_file(self.GOLDEN_SIGNALS)
        assert "ServiceHealth" in content, "Missing ServiceHealth struct"
        assert "Status" in content, "ServiceHealth missing Status field"
        assert "ServiceName" in content, "ServiceHealth missing ServiceName"
        assert "Namespace" in content, "ServiceHealth missing Namespace"

    def test_aggregator_constructor(self):
        """Verify NewMetricsAggregator with prometheusURL"""
        content = self._read_file(self.AGGREGATOR)
        assert "NewMetricsAggregator" in content, "Missing NewMetricsAggregator"
        assert "prometheusURL" in content or "prometheus" in content.lower(), \
            "Aggregator missing Prometheus URL parameter"

    def test_aggregator_golden_signals_method(self):
        """Verify GetGoldenSignals method"""
        content = self._read_file(self.AGGREGATOR)
        assert "GetGoldenSignals" in content, "Missing GetGoldenSignals"

    def test_aggregator_promql_queries(self):
        """Verify PromQL queries for rate, success rate, histogram quantile"""
        content = self._read_file(self.AGGREGATOR)
        assert "response_total" in content, "Missing response_total PromQL query"
        assert "histogram_quantile" in content, \
            "Missing histogram_quantile PromQL query"

    def test_health_checker_thresholds(self):
        """Verify HealthChecker with degraded/critical thresholds"""
        content = self._read_file(self.HEALTH_CHECKER)
        assert "HealthChecker" in content, "Missing HealthChecker"
        assert "degraded" in content.lower(), "Missing degraded threshold"
        assert "critical" in content.lower(), "Missing critical threshold"
        assert "0.99" in content, "Missing 99% success rate threshold"
        assert "0.95" in content, "Missing 95% success rate threshold"

    def test_health_checker_evaluate(self):
        """Verify Evaluate method"""
        content = self._read_file(self.HEALTH_CHECKER)
        assert "Evaluate" in content, "Missing Evaluate method"

    def test_topology_builder(self):
        """Verify BuildTopology with Nodes and Edges"""
        content = self._read_file(self.TOPOLOGY)
        assert "BuildTopology" in content, "Missing BuildTopology"
        assert "ServiceEdge" in content, "Missing ServiceEdge type"
        assert "Source" in content, "ServiceEdge missing Source"
        assert "Destination" in content, "ServiceEdge missing Destination"

    def test_api_endpoints(self):
        """Verify /api/services, /api/services/{name}, /api/topology endpoints"""
        content = self._read_file(self.API)
        assert "/api/services" in content, "Missing /api/services endpoint"
        assert "/api/topology" in content, "Missing /api/topology endpoint"

    def test_api_error_codes(self):
        """Verify proper HTTP error codes (400, 502)"""
        content = self._read_file(self.API)
        has_400 = "400" in content or "BadRequest" in content
        has_502 = "502" in content or "BadGateway" in content
        assert has_400, "API missing 400 error handling"
        assert has_502, "API missing 502 error handling"

    # === Functional Checks ===

    def test_go_files_compile(self):
        """Verify Go files compile"""
        metrics_dir = os.path.join(self.REPO_DIR, "viz/metrics")
        result = subprocess.run(
            ["go", "build", "./..."],
            cwd=metrics_dir,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            pytest.fail(f"Go build failed: {result.stderr[:500]}")

    def test_tests_have_assertions(self):
        """Verify test file has test functions"""
        content = self._read_file(self.TESTS)
        test_count = len(re.findall(r'func Test\w+', content))
        assert test_count >= 3, \
            f"Expected >=3 test functions, found {test_count}"
