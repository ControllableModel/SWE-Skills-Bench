"""
Test skill: grafana-dashboards
Verify that the Agent creates a dashboard provisioning validator for
Grafana in Go with JSON validation, panel checks, data source consistency,
UID uniqueness, and structured error/warning output.
"""

import os
import re
import subprocess
import pytest


class TestGrafanaDashboards:
    REPO_DIR = "/workspace/grafana"

    PKG = "pkg/services/provisioning/dashboards"

    # === File Path Checks ===

    def test_validator_go_exists(self):
        """Verify validator.go exists"""
        path = os.path.join(self.REPO_DIR, self.PKG, "validator.go")
        assert os.path.exists(path), f"validator.go not found at {path}"

    def test_validator_test_go_exists(self):
        """Verify validator_test.go exists"""
        path = os.path.join(self.REPO_DIR, self.PKG, "validator_test.go")
        assert os.path.exists(path), f"validator_test.go not found at {path}"

    # === Semantic Checks ===

    def test_required_top_level_fields(self):
        """Verify validation of required top-level fields (title, uid, panels)"""
        path = os.path.join(self.REPO_DIR, self.PKG, "validator.go")
        with open(path) as f:
            content = f.read()

        field_indicators = ["title", "uid", "panels", "Title", "UID", "Panels"]
        found = [ind for ind in field_indicators if ind in content]
        assert len(found) >= 3, (
            f"Should validate required top-level fields. Found: {found}"
        )

    def test_uid_uniqueness_check(self):
        """Verify duplicate UID detection across dashboards"""
        path = os.path.join(self.REPO_DIR, self.PKG, "validator.go")
        with open(path) as f:
            content = f.read()

        uid_indicators = [
            "uid", "UID", "duplicate", "Duplicate", "unique",
            "seen", "map[",
        ]
        found = [ind for ind in uid_indicators if ind in content]
        assert len(found) >= 3, (
            f"Should detect duplicate UIDs. Found: {found}"
        )

    def test_panel_validation(self):
        """Verify panel validation (type, title, gridPos)"""
        path = os.path.join(self.REPO_DIR, self.PKG, "validator.go")
        with open(path) as f:
            content = f.read()

        panel_indicators = [
            "panel", "Panel", "type", "gridPos", "GridPos",
        ]
        found = [ind for ind in panel_indicators if ind in content]
        assert len(found) >= 3, (
            f"Should validate panel fields. Found: {found}"
        )

    def test_grid_pos_bounds(self):
        """Verify gridPos checks: non-negative, width <= 24"""
        path = os.path.join(self.REPO_DIR, self.PKG, "validator.go")
        with open(path) as f:
            content = f.read()

        grid_indicators = ["24", "negative", "width", "gridPos", "GridPos"]
        found = [ind for ind in grid_indicators if ind in content]
        assert len(found) >= 2, (
            f"Should enforce gridPos constraints. Found: {found}"
        )

    def test_datasource_consistency(self):
        """Verify data source reference validation"""
        path = os.path.join(self.REPO_DIR, self.PKG, "validator.go")
        with open(path) as f:
            content = f.read()

        ds_indicators = [
            "datasource", "DataSource", "data source",
            "known", "reference", "Mixed",
        ]
        found = [ind for ind in ds_indicators if ind in content]
        assert len(found) >= 2, (
            f"Should validate data source references. Found: {found}"
        )

    def test_variable_datasource_allowed(self):
        """Verify variable-based data source refs ($datasource) not flagged"""
        path = os.path.join(self.REPO_DIR, self.PKG, "validator.go")
        with open(path) as f:
            content = f.read()

        var_indicators = ["$", "variable", "Variable", "HasPrefix"]
        found = [ind for ind in var_indicators if ind in content]
        assert len(found) >= 1, (
            f"Should allow variable-based data source references. "
            f"Found: {found}"
        )

    def test_errors_vs_warnings(self):
        """Verify structured output distinguishes errors from warnings"""
        path = os.path.join(self.REPO_DIR, self.PKG, "validator.go")
        with open(path) as f:
            content = f.read()

        level_indicators = [
            "Error", "Warning", "error", "warning",
            "Errors", "Warnings",
        ]
        found = [ind for ind in level_indicators if ind in content]
        assert len(found) >= 2, (
            f"Should distinguish errors and warnings. Found: {found}"
        )

    # === Functional Checks ===

    def test_validator_go_package(self):
        """Verify validator.go has proper package declaration"""
        path = os.path.join(self.REPO_DIR, self.PKG, "validator.go")
        with open(path) as f:
            content = f.read()
        assert "package " in content[:200], (
            "validator.go should start with package declaration"
        )

    def test_validator_test_go_package(self):
        """Verify validator_test.go has proper package declaration"""
        path = os.path.join(self.REPO_DIR, self.PKG, "validator_test.go")
        with open(path) as f:
            content = f.read()
        assert "package " in content[:200], (
            "validator_test.go should start with package declaration"
        )

    def test_test_file_has_tests(self):
        """Verify validator_test.go defines test functions"""
        path = os.path.join(self.REPO_DIR, self.PKG, "validator_test.go")
        with open(path) as f:
            content = f.read()

        test_fns = re.findall(r"func\s+Test\w+", content)
        assert len(test_fns) >= 3, (
            f"Should define at least 3 test functions. Found: {test_fns}"
        )

    def test_struct_definitions(self):
        """Verify validator defines Go structs for results"""
        path = os.path.join(self.REPO_DIR, self.PKG, "validator.go")
        with open(path) as f:
            content = f.read()

        structs = re.findall(r"type\s+\w+\s+struct\s*\{", content)
        assert len(structs) >= 1, (
            f"Should define at least 1 struct. Found: {structs}"
        )

    def test_consistent_package_name(self):
        """Verify both files use the same package name"""
        packages = set()
        for fname in ["validator.go", "validator_test.go"]:
            path = os.path.join(self.REPO_DIR, self.PKG, fname)
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("package "):
                        packages.add(line)
                        break

        assert len(packages) == 1, (
            f"Both files should share the same package. Found: {packages}"
        )
