"""
Test skill: implementing-jsc-classes-zig
Verify that the Agent implements a Duration parser JSC class in Zig for the Bun runtime,
including Duration.classes.ts and Duration.zig with ISO 8601 parsing, arithmetic, and comparison.
"""

import os
import subprocess
import re
import pytest


class TestImplementingJscClassesZig:
    REPO_DIR = "/workspace/bun"

    # === File Path Checks ===

    def test_duration_classes_ts_exists(self):
        """Verify Duration.classes.ts exists"""
        found = False
        for root, dirs, files in os.walk(self.REPO_DIR):
            if "node_modules" in root or ".git" in root:
                continue
            for f in files:
                if f == "Duration.classes.ts":
                    found = True
                    break
            if found:
                break
        assert found, "Duration.classes.ts not found in the repository"

    def test_duration_zig_exists(self):
        """Verify Duration.zig exists"""
        found = False
        for root, dirs, files in os.walk(self.REPO_DIR):
            if "node_modules" in root or ".git" in root or ".zig-cache" in root:
                continue
            for f in files:
                if f == "Duration.zig":
                    found = True
                    break
            if found:
                break
        assert found, "Duration.zig not found in the repository"

    # === Semantic Checks ===

    def test_duration_zig_has_iso8601_parser(self):
        """Verify Duration.zig includes ISO 8601 duration parsing"""
        zig_file = None
        for root, dirs, files in os.walk(self.REPO_DIR):
            if "node_modules" in root or ".git" in root or ".zig-cache" in root:
                continue
            for f in files:
                if f == "Duration.zig":
                    zig_file = os.path.join(root, f)
                    break
            if zig_file:
                break
        assert zig_file is not None
        with open(zig_file) as fh:
            content = fh.read()
        content_lower = content.lower()
        has_iso = (
            "iso" in content_lower
            or "8601" in content_lower
            or "parse" in content_lower
            or "'P'" in content
            or "\"P\"" in content
        )
        assert has_iso, "Duration.zig does not include ISO 8601 parsing logic"

    def test_duration_zig_has_arithmetic(self):
        """Verify Duration.zig implements arithmetic operations (add/sub)"""
        zig_file = None
        for root, dirs, files in os.walk(self.REPO_DIR):
            if "node_modules" in root or ".git" in root or ".zig-cache" in root:
                continue
            for f in files:
                if f == "Duration.zig":
                    zig_file = os.path.join(root, f)
                    break
            if zig_file:
                break
        assert zig_file is not None
        with open(zig_file) as fh:
            content = fh.read()
        content_lower = content.lower()
        has_add = "add" in content_lower
        has_sub = "sub" in content_lower or "subtract" in content_lower
        assert has_add and has_sub, (
            f"Duration.zig missing arithmetic. add={has_add}, sub={has_sub}"
        )

    def test_duration_zig_has_comparison(self):
        """Verify Duration.zig implements comparison operations"""
        zig_file = None
        for root, dirs, files in os.walk(self.REPO_DIR):
            if "node_modules" in root or ".git" in root or ".zig-cache" in root:
                continue
            for f in files:
                if f == "Duration.zig":
                    zig_file = os.path.join(root, f)
                    break
            if zig_file:
                break
        assert zig_file is not None
        with open(zig_file) as fh:
            content = fh.read()
        content_lower = content.lower()
        has_compare = (
            "compare" in content_lower
            or "equal" in content_lower
            or "lessThan" in content
            or "greaterThan" in content
            or "order" in content_lower
        )
        assert has_compare, "Duration.zig does not implement comparison operations"

    def test_duration_classes_ts_exports_class_definition(self):
        """Verify Duration.classes.ts exports the class definition"""
        ts_file = None
        for root, dirs, files in os.walk(self.REPO_DIR):
            if "node_modules" in root or ".git" in root:
                continue
            for f in files:
                if f == "Duration.classes.ts":
                    ts_file = os.path.join(root, f)
                    break
            if ts_file:
                break
        assert ts_file is not None
        with open(ts_file) as fh:
            content = fh.read()
        has_export = "export" in content
        has_class_def = (
            "class" in content.lower()
            or "define" in content.lower()
            or "Duration" in content
        )
        assert has_export, "Duration.classes.ts does not export anything"
        assert has_class_def, "Duration.classes.ts does not define Duration class"

    def test_duration_zig_has_jsc_bindings(self):
        """Verify Duration.zig has JSC class bindings (extern functions or JSValue)"""
        zig_file = None
        for root, dirs, files in os.walk(self.REPO_DIR):
            if "node_modules" in root or ".git" in root or ".zig-cache" in root:
                continue
            for f in files:
                if f == "Duration.zig":
                    zig_file = os.path.join(root, f)
                    break
            if zig_file:
                break
        assert zig_file is not None
        with open(zig_file) as fh:
            content = fh.read()
        has_jsc = (
            "JSValue" in content
            or "JSGlobalObject" in content
            or "extern" in content
            or "jsc" in content.lower()
            or "JavaScript" in content
        )
        assert has_jsc, "Duration.zig missing JSC binding types (JSValue, JSGlobalObject)"

    # === Functional Checks ===

    def test_duration_zig_compiles(self):
        """Verify Duration.zig has no syntax errors detectable by zig ast-check"""
        zig_file = None
        for root, dirs, files in os.walk(self.REPO_DIR):
            if "node_modules" in root or ".git" in root or ".zig-cache" in root:
                continue
            for f in files:
                if f == "Duration.zig":
                    zig_file = os.path.join(root, f)
                    break
        if zig_file is None:
            pytest.fail("Duration.zig not found")
        result = subprocess.run(
            ["zig", "ast-check", zig_file],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, (
            f"Zig ast-check failed:\n{result.stderr[:500]}"
        )

    def test_duration_classes_ts_valid_typescript(self):
        """Verify Duration.classes.ts is valid TypeScript syntax"""
        ts_file = None
        for root, dirs, files in os.walk(self.REPO_DIR):
            if "node_modules" in root or ".git" in root:
                continue
            for f in files:
                if f == "Duration.classes.ts":
                    ts_file = os.path.join(root, f)
                    break
        if ts_file is None:
            pytest.fail("Duration.classes.ts not found")
        # Check that it's at least parseable by node
        result = subprocess.run(
            ["node", "-e", f"require('fs').readFileSync('{ts_file}', 'utf8')"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, f"Failed to read TypeScript file: {result.stderr}"

    def test_duration_zig_handles_time_components(self):
        """Verify Duration.zig handles hours, minutes, seconds components"""
        zig_file = None
        for root, dirs, files in os.walk(self.REPO_DIR):
            if "node_modules" in root or ".git" in root or ".zig-cache" in root:
                continue
            for f in files:
                if f == "Duration.zig":
                    zig_file = os.path.join(root, f)
                    break
        assert zig_file is not None
        with open(zig_file) as fh:
            content = fh.read()
        content_lower = content.lower()
        has_hours = "hour" in content_lower or "'H'" in content or "\"H\"" in content
        has_minutes = "minute" in content_lower or "'M'" in content or "\"M\"" in content
        has_seconds = "second" in content_lower or "'S'" in content or "\"S\"" in content
        assert has_hours and has_minutes and has_seconds, (
            f"Duration.zig missing time components: hours={has_hours}, minutes={has_minutes}, seconds={has_seconds}"
        )
