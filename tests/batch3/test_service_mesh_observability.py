"""
Tests for the service-mesh-observability skill.

Validates that a service mesh observability dashboard data generator
was implemented for Linkerd's viz extension, including metrics collection,
health scoring, and topology building.

Repo: linkerd2 (https://github.com/linkerd/linkerd2)
"""

import os
import re
import subprocess

REPO_DIR = "/workspace/linkerd2"


class TestFilePathCheck:
    """Verify all required files were created."""

    def test_collector_exists(self):
        path = os.path.join(REPO_DIR, "viz", "metrics", "collector.go")
        assert os.path.isfile(path), f"Expected viz/metrics/collector.go"

    def test_health_scorer_exists(self):
        path = os.path.join(REPO_DIR, "viz", "metrics", "health_scorer.go")
        assert os.path.isfile(path), f"Expected viz/metrics/health_scorer.go"

    def test_topology_exists(self):
        path = os.path.join(REPO_DIR, "viz", "metrics", "topology.go")
        assert os.path.isfile(path), f"Expected viz/metrics/topology.go"

    def test_collector_test_exists(self):
        path = os.path.join(REPO_DIR, "viz", "metrics", "collector_test.go")
        assert os.path.isfile(path), f"Expected collector_test.go"

    def test_health_scorer_test_exists(self):
        path = os.path.join(REPO_DIR, "viz", "metrics", "health_scorer_test.go")
        assert os.path.isfile(path), f"Expected health_scorer_test.go"


class TestSemanticMetricsCollector:
    """Verify golden signal metrics collection from Prometheus."""

    def _read(self):
        path = os.path.join(REPO_DIR, "viz", "metrics", "collector.go")
        with open(path, "r") as f:
            return f.read()

    def test_struct_definition(self):
        content = self._read()
        assert re.search(r"type\s+MetricsCollector\s+struct", content), (
            "Expected MetricsCollector struct"
        )

    def test_prometheus_querier_interface(self):
        content = self._read()
        assert re.search(r"PrometheusQuerier|interface|Query", content), (
            "Expected PrometheusQuerier interface for testability"
        )

    def test_latency_metric(self):
        content = self._read()
        assert re.search(r"response_latency|latency|p50|p95|p99", content, re.IGNORECASE), (
            "Expected latency histogram query (p50/p95/p99)"
        )

    def test_traffic_metric(self):
        content = self._read()
        assert re.search(r"request_total|traffic|rps|requests.*per.*second", content, re.IGNORECASE), (
            "Expected traffic counter (requests per second)"
        )

    def test_error_metric(self):
        content = self._read()
        assert re.search(r"error.*rate|classification.*failure|failure", content, re.IGNORECASE), (
            "Expected error rate metric (classification=failure)"
        )

    def test_saturation_metric(self):
        content = self._read()
        assert re.search(r"tcp_open_connections|saturation|connection", content, re.IGNORECASE), (
            "Expected saturation metric (tcp_open_connections)"
        )

    def test_service_metrics_struct(self):
        content = self._read()
        assert re.search(r"ServiceMetrics|service_metrics", content), (
            "Expected ServiceMetrics return struct"
        )

    def test_linkerd_labels(self):
        content = self._read()
        assert re.search(r"deployment|namespace|authority|direction", content), (
            "Expected Linkerd label conventions (deployment, namespace, etc.)"
        )


class TestSemanticHealthScorer:
    """Verify health scoring engine."""

    def _read(self):
        path = os.path.join(REPO_DIR, "viz", "metrics", "health_scorer.go")
        with open(path, "r") as f:
            return f.read()

    def test_struct_definition(self):
        content = self._read()
        assert re.search(r"type\s+HealthScorer\s+struct", content), (
            "Expected HealthScorer struct"
        )

    def test_health_config(self):
        content = self._read()
        assert re.search(r"HealthConfig|health_config", content), (
            "Expected HealthConfig struct for configurable thresholds"
        )

    def test_error_score_calculation(self):
        content = self._read()
        assert re.search(r"error.*score|ErrorScore", content, re.IGNORECASE), (
            "Expected error_score calculation"
        )

    def test_latency_score_calculation(self):
        content = self._read()
        assert re.search(r"latency.*score|LatencyScore", content, re.IGNORECASE), (
            "Expected latency_score calculation"
        )

    def test_traffic_anomaly(self):
        content = self._read()
        assert re.search(r"anomal|traffic.*score|penalty|0\.3", content, re.IGNORECASE), (
            "Expected traffic anomaly detection with 0.3 penalty"
        )

    def test_weighted_average(self):
        content = self._read()
        assert re.search(r"0\.5.*0\.3.*0\.2|weight|Weight", content), (
            "Expected weighted average: error(0.5) + latency(0.3) + traffic(0.2)"
        )

    def test_health_classification(self):
        content = self._read()
        for status in ["healthy", "degraded", "critical"]:
            assert status in content.lower(), (
                f"Expected health classification '{status}'"
            )


class TestSemanticTopology:
    """Verify service topology builder."""

    def _read(self):
        path = os.path.join(REPO_DIR, "viz", "metrics", "topology.go")
        with open(path, "r") as f:
            return f.read()

    def test_struct_definition(self):
        content = self._read()
        assert re.search(r"type\s+TopologyBuilder\s+struct", content), (
            "Expected TopologyBuilder struct"
        )

    def test_nodes_and_edges(self):
        content = self._read()
        assert re.search(r"nodes|Nodes", content) and re.search(r"edges|Edges", content), (
            "Expected nodes and edges in topology output"
        )

    def test_circular_dependency(self):
        content = self._read()
        assert re.search(r"circular|cycle|Circular|Cycle", content, re.IGNORECASE), (
            "Expected circular dependency detection"
        )

    def test_gateway_detection(self):
        content = self._read()
        assert re.search(r"gateway|Gateway", content, re.IGNORECASE), (
            "Expected gateway service detection (>5 downstream)"
        )

    def test_leaf_detection(self):
        content = self._read()
        assert re.search(r"leaf|Leaf", content, re.IGNORECASE), (
            "Expected leaf service detection (zero downstream)"
        )

    def test_json_tags(self):
        content = self._read()
        assert re.search(r'`json:"', content), (
            "Expected JSON struct tags for marshaling"
        )


class TestFunctionalGoSyntax:
    """Validate Go files compile."""

    def test_package_declaration(self):
        path = os.path.join(REPO_DIR, "viz", "metrics", "collector.go")
        with open(path, "r") as f:
            content = f.read(500)
        assert re.search(r"^package\s+\w+", content, re.MULTILINE), (
            "Expected package declaration"
        )

    def test_go_build(self):
        result = subprocess.run(
            ["go", "build", "./viz/metrics/..."],
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

    def test_collector_test_funcs(self):
        path = os.path.join(REPO_DIR, "viz", "metrics", "collector_test.go")
        with open(path, "r") as f:
            content = f.read()
        count = len(re.findall(r"func\s+Test\w+", content))
        assert count >= 2, f"Expected >= 2 test functions, found {count}"

    def test_health_scorer_test_funcs(self):
        path = os.path.join(REPO_DIR, "viz", "metrics", "health_scorer_test.go")
        with open(path, "r") as f:
            content = f.read()
        count = len(re.findall(r"func\s+Test\w+", content))
        assert count >= 2, f"Expected >= 2 test functions, found {count}"
