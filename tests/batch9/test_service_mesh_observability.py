"""
Test skill: service-mesh-observability
Verify that the Agent creates Grafana dashboard JSON generators
for Linkerd service mesh observability (Go).
"""

import os
import re
import json
import subprocess
import pytest


class TestServiceMeshObservability:
    REPO_DIR = "/workspace/linkerd2"

    # === File Path Checks ===

    def test_dashboard_generator_files_exist(self):
        """Verify Grafana dashboard generator files exist"""
        found = False
        for root, dirs, files in os.walk(self.REPO_DIR):
            if ".git" in root or "vendor" in root:
                continue
            for f in files:
                if ("dashboard" in f.lower() or "grafana" in f.lower()) and (f.endswith(".go") or f.endswith(".json") or f.endswith(".jsonnet")):
                    found = True
                    break
            if found:
                break
        assert found, "Grafana dashboard files not found"

    # === Semantic Checks ===

    def test_grafana_dashboard_structure(self):
        """Verify Grafana dashboard has standard structure"""
        content = self._collect_dashboard_content()
        has_structure = (
            "panels" in content
            or "dashboard" in content.lower()
            or "Panel" in content
            or "datasource" in content.lower()
        )
        assert has_structure, "Grafana dashboard structure not found"

    def test_mesh_metrics_included(self):
        """Verify service mesh metrics are included"""
        content = self._collect_dashboard_content()
        content_lower = content.lower()
        has_metrics = (
            "request_total" in content_lower
            or "latency" in content_lower
            or "success_rate" in content_lower
            or "tcp_" in content_lower
            or "response_total" in content_lower
        )
        assert has_metrics, "Service mesh metrics not included in dashboards"

    def test_promql_queries_present(self):
        """Verify PromQL queries are present"""
        content = self._collect_dashboard_content()
        content_lower = content.lower()
        has_promql = (
            "rate(" in content_lower
            or "sum(" in content_lower
            or "histogram_quantile" in content_lower
            or "irate(" in content_lower
        )
        assert has_promql, "PromQL queries not found in dashboards"

    def test_linkerd_specific_metrics(self):
        """Verify Linkerd-specific metrics are used"""
        content = self._collect_dashboard_content()
        content_lower = content.lower()
        has_linkerd = (
            "linkerd" in content_lower
            or "proxy" in content_lower
            or "meshed" in content_lower
        )
        assert has_linkerd, "Linkerd-specific metrics not found"

    # === Functional Checks ===

    def test_json_dashboards_valid(self):
        """Verify JSON dashboard files are valid"""
        json_files = self._find_json_dashboards()
        for jf in json_files:
            with open(jf) as fh:
                data = json.load(fh)
            assert isinstance(data, dict), f"{jf} is not a JSON object"

    def test_go_generator_files_valid(self):
        """Verify Go generator files have valid package declarations"""
        go_files = self._find_go_files()
        for gf in go_files:
            with open(gf) as fh:
                content = fh.read()
            assert "package " in content[:200], f"{gf} missing package declaration"

    def test_go_files_balanced_braces(self):
        """Verify Go files have balanced braces"""
        go_files = self._find_go_files()
        for gf in go_files:
            with open(gf) as fh:
                content = fh.read()
            cleaned = re.sub(r'"[^"]*"', '', content)
            cleaned = re.sub(r'`[^`]*`', '', cleaned)
            cleaned = re.sub(r'//[^\n]*', '', cleaned)
            cleaned = re.sub(r'/\*.*?\*/', '', cleaned, flags=re.DOTALL)
            opens = cleaned.count('{')
            closes = cleaned.count('}')
            assert opens == closes, f"Unbalanced braces in {gf}: {opens} vs {closes}"

    def test_dashboard_has_title(self):
        """Verify dashboards have titles"""
        content = self._collect_dashboard_content()
        has_title = "title" in content.lower()
        assert has_title, "Dashboard title not found"

    def test_panel_types_defined(self):
        """Verify dashboards define panel types (graph, gauge, etc.)"""
        content = self._collect_dashboard_content()
        content_lower = content.lower()
        has_panels = (
            "graph" in content_lower
            or "timeseries" in content_lower
            or "gauge" in content_lower
            or "stat" in content_lower
            or "table" in content_lower
            or "type" in content_lower
        )
        assert has_panels, "Panel types not defined in dashboards"

    def _collect_dashboard_content(self):
        all_content = ""
        for root, dirs, files in os.walk(self.REPO_DIR):
            if ".git" in root or "vendor" in root:
                continue
            for f in files:
                if ("dashboard" in f.lower() or "grafana" in f.lower()):
                    fpath = os.path.join(root, f)
                    try:
                        with open(fpath) as fh:
                            all_content += fh.read() + "\n"
                    except (UnicodeDecodeError, PermissionError):
                        continue
        return all_content

    def _find_json_dashboards(self):
        result = []
        for root, dirs, files in os.walk(self.REPO_DIR):
            if ".git" in root or "vendor" in root:
                continue
            for f in files:
                if ("dashboard" in f.lower() or "grafana" in f.lower()) and f.endswith(".json"):
                    result.append(os.path.join(root, f))
        return result

    def _find_go_files(self):
        result = []
        for root, dirs, files in os.walk(self.REPO_DIR):
            if ".git" in root or "vendor" in root:
                continue
            for f in files:
                if f.endswith(".go") and ("dashboard" in f.lower() or "grafana" in f.lower()):
                    result.append(os.path.join(root, f))
        return result
