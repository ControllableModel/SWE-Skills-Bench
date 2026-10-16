"""
Tests for the python-performance-optimization skill.
Validates a py-spy profiling benchmark suite with CPU/memory/IO/threaded
workloads, benchmark runner, analysis, and regression detection.
"""

import os
import re
import ast

REPO_DIR = "/workspace/py-spy"
BENCH_DIR = os.path.join(REPO_DIR, "benchmarks")
WORKLOADS_DIR = os.path.join(BENCH_DIR, "workloads")


class TestPythonPerformanceOptimization:
    """Tests for the py-spy profiling benchmark suite."""

    # ── file_path_check ──────────────────────────────────────────────

    def test_cpu_bound_exists(self):
        """CPU-bound workload must exist."""
        path = os.path.join(WORKLOADS_DIR, "cpu_bound.py")
        assert os.path.isfile(path), f"Missing {path}"

    def test_memory_bound_exists(self):
        """Memory-bound workload must exist."""
        path = os.path.join(WORKLOADS_DIR, "memory_bound.py")
        assert os.path.isfile(path), f"Missing {path}"

    def test_io_bound_exists(self):
        """I/O-bound workload must exist."""
        path = os.path.join(WORKLOADS_DIR, "io_bound.py")
        assert os.path.isfile(path), f"Missing {path}"

    def test_threaded_exists(self):
        """Multi-threaded workload must exist."""
        path = os.path.join(WORKLOADS_DIR, "threaded.py")
        assert os.path.isfile(path), f"Missing {path}"

    def test_runner_exists(self):
        """Benchmark runner must exist."""
        path = os.path.join(BENCH_DIR, "runner.py")
        assert os.path.isfile(path), f"Missing {path}"

    def test_analysis_exists(self):
        """Analysis module must exist."""
        path = os.path.join(BENCH_DIR, "analysis.py")
        assert os.path.isfile(path), f"Missing {path}"

    # ── semantic_check ───────────────────────────────────────────────

    def _read(self, rel_path):
        path = os.path.join(BENCH_DIR, rel_path)
        if not os.path.isfile(path):
            return ""
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def test_cpu_distinct_functions(self):
        """CPU workload must define fibonacci, prime_sieve, matrix_multiply."""
        content = self._read("workloads/cpu_bound.py")
        for func in ["fibonacci", "prime_sieve", "matrix_multiply"]:
            assert re.search(rf"def\s+{func}\b", content), f"{func} function not defined"

    def test_threaded_four_threads(self):
        """Threaded workload must use 4 threads with distinct names."""
        content = self._read("workloads/threaded.py")
        assert re.search(r"Thread|threading", content), "threading module not used"
        for name in ["compute", "sleep", "allocate", "io"]:
            assert name in content, f"Thread name '{name}' not found"

    def test_ready_signal(self):
        """Workloads must print READY signal for synchronization."""
        for wl in ["workloads/cpu_bound.py", "workloads/memory_bound.py",
                    "workloads/io_bound.py", "workloads/threaded.py"]:
            content = self._read(wl)
            assert "READY" in content, f"READY signal not found in {wl}"

    def test_duration_argument(self):
        """Workloads must accept --duration CLI argument."""
        content = self._read("workloads/cpu_bound.py")
        assert re.search(r"--duration|duration|argparse", content), (
            "--duration argument not found"
        )

    def test_runner_subprocess_launch(self):
        """Runner must launch workloads via subprocess."""
        content = self._read("runner.py")
        assert re.search(r"subprocess|Popen", content), "subprocess usage not found in runner"
        assert re.search(r"py-spy|py.spy|record", content), "py-spy invocation not found"

    def test_overhead_calculation(self):
        """Runner must calculate profiling overhead percentage."""
        content = self._read("runner.py")
        assert re.search(r"overhead|overhead_pct", content, re.IGNORECASE), (
            "Overhead calculation not found"
        )

    def test_analysis_regression_detection(self):
        """Analysis must detect regressions against baseline."""
        content = self._read("analysis.py")
        assert re.search(r"regression|baseline|PASS|FAIL", content, re.IGNORECASE), (
            "Regression detection not found"
        )

    # ── functional_check ─────────────────────────────────────────────

    def test_workloads_valid_python(self):
        """All workload files must have valid Python syntax."""
        errors = []
        for wl in ["workloads/cpu_bound.py", "workloads/memory_bound.py",
                    "workloads/io_bound.py", "workloads/threaded.py"]:
            content = self._read(wl)
            if not content:
                continue
            try:
                ast.parse(content)
            except SyntaxError as e:
                errors.append(f"{wl}: {e}")
        assert not errors, "Syntax errors:\n" + "\n".join(errors)

    def test_runner_valid_python(self):
        """Runner must have valid Python syntax."""
        content = self._read("runner.py")
        if content:
            ast.parse(content)

    def test_analysis_valid_python(self):
        """Analysis module must have valid Python syntax."""
        content = self._read("analysis.py")
        if content:
            ast.parse(content)

    def test_no_external_deps_in_workloads(self):
        """Workloads must use only standard library (no pip packages)."""
        third_party = ["numpy", "pandas", "scipy", "torch", "requests"]
        for wl in ["workloads/cpu_bound.py", "workloads/memory_bound.py",
                    "workloads/io_bound.py", "workloads/threaded.py"]:
            content = self._read(wl)
            for pkg in third_party:
                assert not re.search(rf"^\s*import\s+{pkg}|^\s*from\s+{pkg}", content, re.MULTILINE), (
                    f"External dependency '{pkg}' found in {wl}"
                )

    def test_baseline_json_exists(self):
        """Baseline reference file must exist."""
        path = os.path.join(BENCH_DIR, "baseline.json")
        assert os.path.isfile(path), f"Missing {path}"

    def test_lock_in_threaded(self):
        """Threaded workload must use threading.Lock for shared counter."""
        content = self._read("workloads/threaded.py")
        assert re.search(r"Lock|lock|threading\.Lock", content), (
            "threading.Lock not found in threaded workload"
        )
