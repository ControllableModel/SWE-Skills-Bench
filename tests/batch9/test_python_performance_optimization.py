"""
Test skill: python-performance-optimization
Verify that the Agent creates flame graph renderer and performance
optimization tools (Rust / py-spy).
"""

import os
import re
import subprocess
import pytest


class TestPythonPerformanceOptimization:
    REPO_DIR = "/workspace/py-spy"

    # === File Path Checks ===

    def test_flame_graph_files_exist(self):
        """Verify flame graph renderer files exist"""
        found = False
        for root, dirs, files in os.walk(self.REPO_DIR):
            if ".git" in root or "target" in root:
                continue
            for f in files:
                if f.endswith(".rs") and ("flame" in f.lower() or "render" in f.lower() or "graph" in f.lower() or "profile" in f.lower()):
                    found = True
                    break
            if found:
                break
        assert found, "Flame graph renderer files not found"

    # === Semantic Checks ===

    def test_flame_graph_renderer_defined(self):
        """Verify flame graph renderer is implemented"""
        content = self._collect_content()
        content_lower = content.lower()
        has_flame = "flame" in content_lower or "flamegraph" in content_lower
        assert has_flame, "Flame graph renderer not found"

    def test_stack_frame_parsing(self):
        """Verify stack frame parsing is implemented"""
        content = self._collect_content()
        content_lower = content.lower()
        has_stack = (
            "stack" in content_lower
            or "frame" in content_lower
            or "backtrace" in content_lower
            or "callstack" in content_lower
        )
        assert has_stack, "Stack frame parsing not found"

    def test_svg_or_html_output(self):
        """Verify SVG or HTML output format"""
        content = self._collect_content()
        content_lower = content.lower()
        has_output = (
            "svg" in content_lower
            or "html" in content_lower
            or "<rect" in content_lower
            or "write" in content_lower
        )
        assert has_output, "SVG/HTML output not found"

    def test_profiling_data_collection(self):
        """Verify profiling data collection"""
        content = self._collect_content()
        content_lower = content.lower()
        has_profiling = (
            "sample" in content_lower
            or "profile" in content_lower
            or "perf" in content_lower
            or "cpu" in content_lower
        )
        assert has_profiling, "Profiling data collection not found"

    # === Functional Checks ===

    def test_rust_files_have_mod_or_use(self):
        """Verify Rust files have proper module structure"""
        rs_files = self._find_rs_files()
        assert len(rs_files) > 0, "No relevant Rust files found"
        for rf in rs_files:
            with open(rf) as fh:
                content = fh.read()
            has_mod = "mod " in content or "use " in content or "fn " in content or "pub " in content
            assert has_mod, f"{rf} missing Rust module structure"

    def test_rust_files_balanced_braces(self):
        """Verify Rust files have balanced braces"""
        rs_files = self._find_rs_files()
        for rf in rs_files:
            with open(rf) as fh:
                content = fh.read()
            cleaned = re.sub(r'"[^"]*"', '', content)
            cleaned = re.sub(r'//[^\n]*', '', cleaned)
            cleaned = re.sub(r'/\*.*?\*/', '', cleaned, flags=re.DOTALL)
            opens = cleaned.count('{')
            closes = cleaned.count('}')
            assert opens == closes, f"Unbalanced braces in {rf}: {opens} vs {closes}"

    def test_cargo_build(self):
        """Verify the Rust project builds"""
        result = subprocess.run(
            ["cargo", "build"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode != 0:
            related = [
                line for line in result.stderr.splitlines()
                if any(kw in line.lower() for kw in ["flame", "render", "graph", "error"])
            ]
            assert len(related) == 0, f"Build errors: {related[:5]}"

    def test_color_palette_defined(self):
        """Verify color palette for flame graph visualization"""
        content = self._collect_content()
        content_lower = content.lower()
        has_color = (
            "color" in content_lower
            or "palette" in content_lower
            or "rgb" in content_lower
            or "hsl" in content_lower
            or "#" in content
        )
        assert has_color, "Color palette not defined for flame graph"

    def _collect_content(self):
        all_content = ""
        for root, dirs, files in os.walk(self.REPO_DIR):
            if ".git" in root or "target" in root:
                continue
            for f in files:
                if f.endswith(".rs"):
                    fpath = os.path.join(root, f)
                    try:
                        with open(fpath) as fh:
                            c = fh.read()
                        if any(kw in c.lower() for kw in ["flame", "render", "graph", "stack", "frame", "svg"]):
                            all_content += c + "\n"
                    except (UnicodeDecodeError, PermissionError):
                        continue
        return all_content

    def _find_rs_files(self):
        rs_files = []
        for root, dirs, files in os.walk(self.REPO_DIR):
            if ".git" in root or "target" in root:
                continue
            for f in files:
                if f.endswith(".rs") and ("flame" in f.lower() or "render" in f.lower() or "graph" in f.lower() or "profile" in f.lower()):
                    rs_files.append(os.path.join(root, f))
        return rs_files
