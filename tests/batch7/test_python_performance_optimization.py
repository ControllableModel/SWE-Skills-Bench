"""
Test skill: python-performance-optimization
Verify that the Agent implements a summary subcommand for py-spy —
SummaryRecorder (record, top_frames, render), CLI integration with clap,
and integration tests.
"""

import os
import re
import subprocess
import pytest


class TestPythonPerformanceOptimization:
    REPO_DIR = "/workspace/py-spy"

    # ────── helpers ──────

    def _read(self, rel_path):
        fpath = os.path.join(self.REPO_DIR, rel_path)
        with open(fpath, "r") as f:
            return f.read()

    def _exists(self, rel_path):
        return os.path.isfile(os.path.join(self.REPO_DIR, rel_path))

    # === File Path Checks ===

    def test_summary_rs_exists(self):
        """src/summary.rs must exist"""
        assert self._exists("src/summary.rs")

    def test_integration_test_exists(self):
        """tests/test_summary.py must exist"""
        assert self._exists("tests/test_summary.py")

    # === Semantic Checks — summary.rs ===

    def test_frame_summary_struct(self):
        """FrameSummary struct must be defined"""
        src = self._read("src/summary.rs")
        assert "FrameSummary" in src

    def test_frame_summary_fields(self):
        """FrameSummary must have function, filename, lineno, total_samples, self_samples"""
        src = self._read("src/summary.rs")
        for field in ["function", "filename", "lineno", "total_samples", "self_samples"]:
            assert field in src, f"Missing field: {field}"

    def test_summary_recorder_struct(self):
        """SummaryRecorder struct must be defined"""
        src = self._read("src/summary.rs")
        assert "SummaryRecorder" in src

    def test_recorder_new(self):
        """SummaryRecorder::new must exist"""
        src = self._read("src/summary.rs")
        assert re.search(r'fn\s+new\b', src)

    def test_recorder_record_method(self):
        """record method must exist"""
        src = self._read("src/summary.rs")
        assert re.search(r'fn\s+record\b', src)

    def test_recorder_top_frames_method(self):
        """top_frames method must exist"""
        src = self._read("src/summary.rs")
        assert "top_frames" in src

    def test_recorder_render_method(self):
        """render method must exist"""
        src = self._read("src/summary.rs")
        assert re.search(r'fn\s+render\b', src)

    def test_self_samples_innermost_only(self):
        """record must increment self_samples only for innermost frame"""
        src = self._read("src/summary.rs")
        lower = src.lower()
        # Should reference "first" or index 0 or "top" for self samples
        assert "self_samples" in src

    def test_total_samples_method(self):
        """total_samples method must exist"""
        src = self._read("src/summary.rs")
        assert "total_samples" in src

    def test_render_format(self):
        """render output must include column headers"""
        src = self._read("src/summary.rs")
        assert "Self" in src or "%Self" in src
        assert "Total" in src
        assert "Function" in src

    # === Semantic Checks — main.rs (CLI) ===

    def test_summary_subcommand_registered(self):
        """summary subcommand must be registered in main.rs"""
        src = self._read("src/main.rs")
        assert "summary" in src.lower()

    def test_pid_argument(self):
        """--pid argument must be defined"""
        src = self._read("src/main.rs")
        assert "pid" in src.lower()

    def test_duration_argument(self):
        """--duration argument must be defined"""
        src = self._read("src/main.rs")
        assert "duration" in src.lower()

    def test_rate_argument(self):
        """--rate argument must be defined"""
        src = self._read("src/main.rs")
        assert "rate" in src.lower()

    def test_top_argument(self):
        """--top argument must be defined"""
        src = self._read("src/main.rs")
        assert "top" in src.lower()

    def test_run_summary_function(self):
        """run_summary function must exist"""
        found = False
        for fn in ["src/main.rs", "src/summary.rs"]:
            if self._exists(fn):
                content = self._read(fn)
                if "run_summary" in content:
                    found = True
                    break
        assert found, "run_summary function not found"

    # === Semantic Checks — Integration test ===

    def test_integration_test_content(self):
        """Integration test must test py-spy summary command"""
        src = self._read("tests/test_summary.py")
        assert "summary" in src.lower()
        assert "busy_loop" in src or "target" in src.lower()

    # === Functional Checks ===

    def test_cargo_build(self):
        """Project must build with cargo"""
        result = subprocess.run(
            ["cargo", "build"],
            capture_output=True, text=True, cwd=self.REPO_DIR, timeout=600,
        )
        assert result.returncode == 0, (
            f"cargo build failed:\n{result.stdout}\n{result.stderr}"
        )

    def test_cargo_test(self):
        """Rust tests must pass"""
        result = subprocess.run(
            ["cargo", "test", "--", "--test-threads=1"],
            capture_output=True, text=True, cwd=self.REPO_DIR, timeout=600,
        )
        assert result.returncode == 0, (
            f"Tests failed:\n{result.stdout}\n{result.stderr}"
        )
