"""
Test skill: service-mesh-observability
Verify that the Agent creates Linkerd viz mesh-wide metrics aggregation
with Go structs, HTTP handler, per-service metrics, namespace filtering,
and time-windowed aggregation.
"""

import os
import re
import subprocess
import pytest


class TestServiceMeshObservability:
    REPO_DIR = "/workspace/linkerd2"

    PKG = "viz/metrics"

    # === File Path Checks ===

    def test_aggregator_go_exists(self):
        """Verify aggregator.go exists"""
        path = os.path.join(self.REPO_DIR, self.PKG, "aggregator.go")
        assert os.path.exists(path), f"aggregator.go not found at {path}"

    def test_types_go_exists(self):
        """Verify types.go exists"""
        path = os.path.join(self.REPO_DIR, self.PKG, "types.go")
        assert os.path.exists(path), f"types.go not found at {path}"

    def test_handler_go_exists(self):
        """Verify handler.go exists"""
        path = os.path.join(self.REPO_DIR, self.PKG, "handler.go")
        assert os.path.exists(path), f"handler.go not found at {path}"

    # === Semantic Checks ===

    def test_per_service_metrics(self):
        """Verify per-service metrics: request rate, success rate, latency"""
        combined = ""
        for fname in ["aggregator.go", "types.go"]:
            path = os.path.join(self.REPO_DIR, self.PKG, fname)
            if os.path.exists(path):
                with open(path) as f:
                    combined += f.read()

        metric_indicators = [
            "RequestRate", "SuccessRate", "Latency",
            "request_rate", "success_rate", "latency",
            "P50", "P95", "P99", "p50", "p95", "p99",
        ]
        found = [ind for ind in metric_indicators if ind in combined]
        assert len(found) >= 3, (
            f"Should define per-service metrics. Found: {found}"
        )

    def test_latency_percentiles(self):
        """Verify latency percentile calculation (p50, p95, p99)"""
        combined = ""
        for fname in ["aggregator.go", "types.go"]:
            path = os.path.join(self.REPO_DIR, self.PKG, fname)
            if os.path.exists(path):
                with open(path) as f:
                    combined += f.read()

        percentile_indicators = [
            "50", "95", "99", "percentile", "quantile",
            "P50", "P95", "P99",
        ]
        found = [ind for ind in percentile_indicators if ind in combined]
        assert len(found) >= 2, (
            f"Should compute latency percentiles. Found: {found}"
        )

    def test_namespace_filtering(self):
        """Verify namespace filtering support"""
        combined = ""
        for fname in ["aggregator.go", "handler.go"]:
            path = os.path.join(self.REPO_DIR, self.PKG, fname)
            if os.path.exists(path):
                with open(path) as f:
                    combined += f.read()

        ns_indicators = [
            "namespace", "Namespace", "filter", "query",
        ]
        found = [ind for ind in ns_indicators if ind in combined]
        assert len(found) >= 2, (
            f"Should support namespace filtering. Found: {found}"
        )

    def test_time_window_support(self):
        """Verify time-windowed aggregation"""
        combined = ""
        for fname in ["aggregator.go", "handler.go", "types.go"]:
            path = os.path.join(self.REPO_DIR, self.PKG, fname)
            if os.path.exists(path):
                with open(path) as f:
                    combined += f.read()

        window_indicators = [
            "window", "Window", "duration", "Duration",
            "1m", "5m", "1h", "interval", "time",
        ]
        found = [ind for ind in window_indicators if ind in combined]
        assert len(found) >= 2, (
            f"Should support time-windowed aggregation. Found: {found}"
        )

    def test_http_handler(self):
        """Verify HTTP handler returns JSON"""
        path = os.path.join(self.REPO_DIR, self.PKG, "handler.go")
        with open(path) as f:
            content = f.read()

        http_indicators = [
            "http.Handler", "http.ResponseWriter", "ServeHTTP",
            "HandleFunc", "json.Marshal", "json.Encode",
            "application/json",
        ]
        found = [ind for ind in http_indicators if ind in content]
        assert len(found) >= 2, (
            f"Should implement HTTP handler with JSON. Found: {found}"
        )

    def test_mesh_wide_summary(self):
        """Verify mesh-wide summary statistics"""
        combined = ""
        for fname in ["aggregator.go", "types.go"]:
            path = os.path.join(self.REPO_DIR, self.PKG, fname)
            if os.path.exists(path):
                with open(path) as f:
                    combined += f.read()

        summary_indicators = [
            "Summary", "Total", "Aggregate", "MeshWide",
            "summary", "total", "overall",
        ]
        found = [ind for ind in summary_indicators if ind in combined]
        assert len(found) >= 1, (
            f"Should compute mesh-wide summary. Found: {found}"
        )

    def test_zero_traffic_handling(self):
        """Verify services with zero traffic are handled gracefully"""
        combined = ""
        for fname in ["aggregator.go", "types.go"]:
            path = os.path.join(self.REPO_DIR, self.PKG, fname)
            if os.path.exists(path):
                with open(path) as f:
                    combined += f.read()

        zero_indicators = [
            "zero", "0", "nil", "empty", "no traffic",
            "default", "NoData",
        ]
        found = [ind for ind in zero_indicators if ind in combined]
        assert len(found) >= 1, (
            f"Should handle zero-traffic services. Found: {found}"
        )

    # === Functional Checks ===

    def test_go_files_have_package(self):
        """Verify Go files have proper package declarations"""
        for fname in ["aggregator.go", "types.go", "handler.go"]:
            path = os.path.join(self.REPO_DIR, self.PKG, fname)
            with open(path) as f:
                content = f.read()
            assert "package " in content[:200], (
                f"{fname} should have package declaration"
            )

    def test_types_define_structs(self):
        """Verify types.go defines Go structs"""
        path = os.path.join(self.REPO_DIR, self.PKG, "types.go")
        with open(path) as f:
            content = f.read()

        struct_count = content.count("struct {")
        assert struct_count >= 2, (
            f"types.go should define at least 2 structs. "
            f"Found: {struct_count}"
        )

    def test_json_tags_on_structs(self):
        """Verify struct fields have JSON tags for serialization"""
        path = os.path.join(self.REPO_DIR, self.PKG, "types.go")
        with open(path) as f:
            content = f.read()

        json_tags = re.findall(r'`json:"[^"]+"`', content)
        assert len(json_tags) >= 3, (
            f"Struct fields should have JSON tags. Found: {len(json_tags)}"
        )

    def test_consistent_package_name(self):
        """Verify all files use the same package name"""
        packages = set()
        for fname in ["aggregator.go", "types.go", "handler.go"]:
            path = os.path.join(self.REPO_DIR, self.PKG, fname)
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("package "):
                        packages.add(line)
                        break

        assert len(packages) == 1, (
            f"All files should use same package. Found: {packages}"
        )
