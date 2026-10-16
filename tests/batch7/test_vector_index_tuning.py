"""
Test skill: vector-index-tuning
Verify that the Agent implements an HNSW Auto-Tuning Utility for FAISS —
C++ HNSWAutoTuner class, Pareto frontier, best-for-recall/QPS selectors,
Python wrapper, and CMake integration.
"""

import os
import re
import subprocess
import pytest


class TestVectorIndexTuning:
    REPO_DIR = "/workspace/faiss"

    # ────────────────── helpers ──────────────────

    def _read(self, rel_path):
        fpath = os.path.join(self.REPO_DIR, rel_path)
        with open(fpath, "r") as f:
            return f.read()

    def _exists(self, rel_path):
        return os.path.isfile(os.path.join(self.REPO_DIR, rel_path))

    # === File Path Checks ===

    def test_autotune_header_exists(self):
        """faiss/AutoTuneHNSW.h must exist"""
        assert self._exists("faiss/AutoTuneHNSW.h")

    def test_autotune_impl_exists(self):
        """faiss/AutoTuneHNSW.cpp must exist"""
        assert self._exists("faiss/AutoTuneHNSW.cpp")

    def test_python_test_exists(self):
        """tests/test_autotune_hnsw.py must exist"""
        assert self._exists("tests/test_autotune_hnsw.py")

    # === Semantic Checks — C++ Structs ===

    def test_hnsw_parameter_set_struct(self):
        """HNSWParameterSet struct must be defined with M, efConstruction, efSearch"""
        src = self._read("faiss/AutoTuneHNSW.h")
        assert re.search(r'struct\s+HNSWParameterSet', src), (
            "HNSWParameterSet struct not found"
        )
        for field in ["M", "efConstruction", "efSearch"]:
            assert field in src, f"HNSWParameterSet missing field: {field}"

    def test_hnsw_tuning_result_struct(self):
        """HNSWTuningResult struct must be defined"""
        src = self._read("faiss/AutoTuneHNSW.h")
        assert re.search(r'struct\s+HNSWTuningResult', src), (
            "HNSWTuningResult struct not found"
        )
        for field in ["recall_at_1", "recall_at_10", "qps",
                       "index_build_time", "memory_usage_mb"]:
            assert field in src, f"HNSWTuningResult missing field: {field}"

    # === Semantic Checks — HNSWAutoTuner Class ===

    def test_auto_tuner_class(self):
        """HNSWAutoTuner class must be defined"""
        src = self._read("faiss/AutoTuneHNSW.h")
        assert re.search(r'class\s+HNSWAutoTuner', src), (
            "HNSWAutoTuner class not found"
        )

    def test_tune_method(self):
        """HNSWAutoTuner must have a tune() method"""
        src = self._read("faiss/AutoTuneHNSW.h")
        assert "tune" in src, "tune() method not found"

    def test_pareto_frontier_method(self):
        """HNSWAutoTuner must have a paretoFrontier() method"""
        src = self._read("faiss/AutoTuneHNSW.h")
        assert "paretoFrontier" in src, "paretoFrontier() method not found"

    def test_best_for_recall_method(self):
        """HNSWAutoTuner must have a bestForRecall() method"""
        src = self._read("faiss/AutoTuneHNSW.h")
        assert "bestForRecall" in src, "bestForRecall() method not found"

    def test_best_for_qps_method(self):
        """HNSWAutoTuner must have a bestForQPS() method"""
        src = self._read("faiss/AutoTuneHNSW.h")
        assert "bestForQPS" in src, "bestForQPS() method not found"

    def test_set_range_methods(self):
        """HNSWAutoTuner must have setMRange, setEfConstructionRange, setEfSearchRange"""
        src = self._read("faiss/AutoTuneHNSW.h")
        for method in ["setMRange", "setEfConstructionRange", "setEfSearchRange"]:
            assert method in src, f"{method}() method not found"

    # === Semantic Checks — Implementation ===

    def test_uses_index_hnsw_flat(self):
        """Implementation must build IndexHNSWFlat indexes"""
        src = self._read("faiss/AutoTuneHNSW.cpp")
        assert "IndexHNSWFlat" in src, "IndexHNSWFlat not used in implementation"

    def test_pareto_dominance_logic(self):
        """Pareto frontier must filter dominated configurations"""
        src = self._read("faiss/AutoTuneHNSW.cpp")
        assert "recall" in src.lower() and "qps" in src.lower(), (
            "Pareto frontier must compare recall and QPS"
        )

    # === Semantic Checks — Python Wrapper ===

    def test_python_wrapper_function(self):
        """extra_wrappers.py must have auto_tune_hnsw function"""
        src = self._read("faiss/python/extra_wrappers.py")
        assert re.search(r'def\s+auto_tune_hnsw\s*\(', src), (
            "auto_tune_hnsw function not found in extra_wrappers.py"
        )

    def test_python_pareto_frontier_function(self):
        """extra_wrappers.py must have pareto_frontier function"""
        src = self._read("faiss/python/extra_wrappers.py")
        assert re.search(r'def\s+pareto_frontier\s*\(', src), (
            "pareto_frontier function not found in extra_wrappers.py"
        )

    def test_python_best_for_recall_function(self):
        """extra_wrappers.py must have best_for_recall function"""
        src = self._read("faiss/python/extra_wrappers.py")
        assert re.search(r'def\s+best_for_recall\s*\(', src), (
            "best_for_recall function not found in extra_wrappers.py"
        )

    # === Semantic Checks — CMake ===

    def test_cmake_includes_autotune(self):
        """faiss/CMakeLists.txt must include AutoTuneHNSW.cpp"""
        src = self._read("faiss/CMakeLists.txt")
        assert "AutoTuneHNSW" in src, (
            "AutoTuneHNSW.cpp not added to faiss/CMakeLists.txt"
        )

    # === Functional Checks ===

    def test_cmake_configure(self):
        """CMake configuration must succeed"""
        build_dir = os.path.join(self.REPO_DIR, "build")
        os.makedirs(build_dir, exist_ok=True)
        result = subprocess.run(
            ["cmake", "..", "-DCMAKE_BUILD_TYPE=Release",
             "-DFAISS_ENABLE_GPU=OFF"],
            capture_output=True, text=True, cwd=build_dir, timeout=120,
        )
        assert result.returncode == 0, (
            f"CMake configure failed:\n{result.stdout}\n{result.stderr}"
        )

    def test_build_compiles(self):
        """Project must compile with new files"""
        build_dir = os.path.join(self.REPO_DIR, "build")
        result = subprocess.run(
            ["cmake", "--build", ".", "--parallel", "4"],
            capture_output=True, text=True, cwd=build_dir, timeout=600,
        )
        assert result.returncode == 0, (
            f"Build failed:\n{result.stdout[-2000:]}\n{result.stderr[-2000:]}"
        )

    def test_python_tests_pass(self):
        """Python tests for autotune HNSW must pass"""
        result = subprocess.run(
            ["python", "-m", "pytest",
             "tests/test_autotune_hnsw.py",
             "-v", "--tb=short"],
            capture_output=True, text=True, cwd=self.REPO_DIR, timeout=300,
        )
        assert result.returncode == 0, (
            f"Tests failed:\n{result.stdout}\n{result.stderr}"
        )
