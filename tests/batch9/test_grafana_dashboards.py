"""
Test skill: grafana-dashboards
Verify that the Agent creates Grafana dashboard JSON generator (Go).
"""

import os
import re
import json
import subprocess
import pytest


class TestGrafanaDashboards:
    REPO_DIR = "/workspace/grafana"

    # === File Path Checks ===

    def test_dashboard_generator_files_exist(self):
        """Verify Grafana dashboard generator files exist"""
        found = False
        for root, dirs, files in os.walk(self.REPO_DIR):
            if ".git" in root or "vendor" in root or "node_modules" in root:
                continue
            for f in files:
                if ("dashboard" in f.lower() or "panel" in f.lower()) and (f.endswith(".go") or f.endswith(".json")):
                    found = True
                    break
            if found:
                break
        assert found, "Grafana dashboard generator files not found"

    # === Semantic Checks ===

    def test_dashboard_model_defined(self):
        """Verify dashboard model or struct is defined"""
        content = self._collect_go_content()
        has_model = "Dashboard" in content or "dashboard" in content
        assert has_model, "Dashboard model not found"

    def test_panel_types_defined(self):
        """Verify panel types are defined (graph, gauge, table, etc.)"""
        content = self._collect_all_content()
        content_lower = content.lower()
        has_panels = (
            "graph" in content_lower
            or "timeseries" in content_lower
            or "gauge" in content_lower
            or "stat" in content_lower
            or "table" in content_lower
            or "panel" in content_lower
        )
        assert has_panels, "Panel types not defined"

    def test_datasource_configuration(self):
        """Verify datasource configuration is present"""
        content = self._collect_all_content()
        content_lower = content.lower()
        has_ds = (
            "datasource" in content_lower
            or "prometheus" in content_lower
            or "data_source" in content_lower
        )
        assert has_ds, "Datasource configuration not found"

    def test_promql_queries(self):
        """Verify PromQL queries are used"""
        content = self._collect_all_content()
        content_lower = content.lower()
        has_promql = (
            "rate(" in content_lower
            or "sum(" in content_lower
            or "histogram_quantile" in content_lower
            or "avg(" in content_lower
            or "expr" in content_lower
        )
        assert has_promql, "PromQL queries not found"

    # === Functional Checks ===

    def test_json_dashboards_valid(self):
        """Verify JSON dashboard files are valid"""
        json_files = self._find_json_dashboards()
        for jf in json_files:
            with open(jf) as fh:
                data = json.load(fh)
            assert isinstance(data, dict), f"{jf} is not a valid JSON object"

    def test_go_files_have_package(self):
        """Verify Go generator files have proper package declarations"""
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

    def test_dashboard_has_templating(self):
        """Verify dashboard supports templating/variables"""
        content = self._collect_all_content()
        content_lower = content.lower()
        has_template = (
            "templat" in content_lower
            or "variable" in content_lower
            or "$" in content
        )
        assert has_template, "Dashboard templating not found"

    def test_dashboard_has_time_range(self):
        """Verify dashboard defines time range"""
        content = self._collect_all_content()
        content_lower = content.lower()
        has_time = (
            "time" in content_lower
            or "from" in content_lower
            or "refresh" in content_lower
        )
        assert has_time, "Dashboard time range not defined"

    def test_dashboard_has_rows_or_panels(self):
        """Verify dashboard has rows or panels layout"""
        content = self._collect_all_content()
        content_lower = content.lower()
        has_layout = "rows" in content_lower or "panels" in content_lower or "gridpos" in content_lower
        assert has_layout, "Dashboard layout (rows/panels) not found"

    def _collect_go_content(self):
        all_content = ""
        for root, dirs, files in os.walk(self.REPO_DIR):
            if ".git" in root or "vendor" in root or "node_modules" in root:
                continue
            for f in files:
                if f.endswith(".go") and ("dashboard" in f.lower() or "panel" in f.lower()):
                    fpath = os.path.join(root, f)
                    try:
                        with open(fpath) as fh:
                            all_content += fh.read() + "\n"
                    except (UnicodeDecodeError, PermissionError):
                        continue
        return all_content

    def _collect_all_content(self):
        all_content = self._collect_go_content()
        for root, dirs, files in os.walk(self.REPO_DIR):
            if ".git" in root or "vendor" in root or "node_modules" in root:
                continue
            for f in files:
                if ("dashboard" in f.lower() or "grafana" in f.lower()) and f.endswith(".json"):
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
            if ".git" in root or "vendor" in root or "node_modules" in root:
                continue
            for f in files:
                if ("dashboard" in f.lower() or "grafana" in f.lower()) and f.endswith(".json"):
                    result.append(os.path.join(root, f))
        return result

    def _find_go_files(self):
        result = []
        for root, dirs, files in os.walk(self.REPO_DIR):
            if ".git" in root or "vendor" in root or "node_modules" in root:
                continue
            for f in files:
                if f.endswith(".go") and ("dashboard" in f.lower() or "panel" in f.lower()):
                    result.append(os.path.join(root, f))
        return result
