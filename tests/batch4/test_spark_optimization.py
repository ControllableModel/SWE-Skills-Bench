"""
Tests for skill: spark-optimization
Repo: apache/spark
Image: zhangyiiiiii/swe-skills-bench-jvm
Task: Implement data skew handling and partition optimization utilities
      for Apache Spark (PySpark).
"""

import ast
import os
import re
import subprocess

import pytest

REPO_DIR = "/workspace/spark"
OPT_DIR = os.path.join(REPO_DIR, "python", "pyspark", "sql", "optimization")

INIT_FILE = os.path.join(OPT_DIR, "__init__.py")
SKEW_FILE = os.path.join(OPT_DIR, "skew_handler.py")
PARTITION_FILE = os.path.join(OPT_DIR, "partition_advisor.py")
CACHE_FILE = os.path.join(OPT_DIR, "cache_manager.py")
CONFIG_FILE = os.path.join(OPT_DIR, "config_tuner.py")
TEST_FILE = os.path.join(REPO_DIR, "python", "pyspark", "tests", "test_optimization.py")


# ---------------------------------------------------------------------------
# Layer 1 — file_path_check
# ---------------------------------------------------------------------------

class TestFilePathCheck:
    """Verify all required optimization files were created."""

    def test_init_exists(self):
        assert os.path.isfile(INIT_FILE), f"Expected {INIT_FILE}"

    def test_skew_handler_exists(self):
        assert os.path.isfile(SKEW_FILE), f"Expected {SKEW_FILE}"

    def test_partition_advisor_exists(self):
        assert os.path.isfile(PARTITION_FILE), f"Expected {PARTITION_FILE}"

    def test_cache_manager_exists(self):
        assert os.path.isfile(CACHE_FILE), f"Expected {CACHE_FILE}"

    def test_config_tuner_exists(self):
        assert os.path.isfile(CONFIG_FILE), f"Expected {CONFIG_FILE}"

    def test_test_file_exists(self):
        assert os.path.isfile(TEST_FILE), f"Expected {TEST_FILE}"


# ---------------------------------------------------------------------------
# Layer 2 — semantic_check
# ---------------------------------------------------------------------------

class TestSemanticSkewHandler:
    """Verify skew handling utilities."""

    @pytest.fixture(autouse=True)
    def _load_source(self):
        with open(SKEW_FILE, "r", encoding="utf-8") as f:
            self.src = f.read()
        self.tree = ast.parse(self.src)

    def test_salted_join_function(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "salted_join" in funcs, f"Expected salted_join function; found: {funcs}"

    def test_detect_skew_function(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "detect_skew" in funcs, f"Expected detect_skew function; found: {funcs}"

    def test_salt_column_logic(self):
        """salted_join must add a random salt column."""
        has_salt = "salt" in self.src.lower() and ("rand" in self.src.lower() or "random" in self.src.lower())
        assert has_salt, "Expected random salt column logic in salted_join"

    def test_num_salts_validation(self):
        """num_salts must be >= 2."""
        assert "ValueError" in self.src, "Expected ValueError for num_salts < 2"

    def test_skew_ratio_in_detect(self):
        """detect_skew must return skew_ratio."""
        assert "skew_ratio" in self.src, "Expected skew_ratio in detect_skew output"

    def test_top_keys_in_detect(self):
        assert "top_keys" in self.src, "Expected top_keys in detect_skew output"


class TestSemanticPartitionAdvisor:
    """Verify partition advisor."""

    @pytest.fixture(autouse=True)
    def _load_source(self):
        with open(PARTITION_FILE, "r", encoding="utf-8") as f:
            self.src = f.read()
        self.tree = ast.parse(self.src)

    def test_class_defined(self):
        classes = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.ClassDef)]
        assert "PartitionAdvisor" in classes, f"Expected PartitionAdvisor; found: {classes}"

    def test_analyze_method(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "analyze" in funcs, "Expected analyze() method"

    def test_repartition_optimally_method(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "repartition_optimally" in funcs, "Expected repartition_optimally() method"

    def test_coalesce_vs_repartition(self):
        """Must use coalesce for reducing and repartition for increasing."""
        assert "coalesce" in self.src and "repartition" in self.src, (
            "Expected both coalesce and repartition logic"
        )

    def test_target_partition_mb(self):
        assert "target_partition_mb" in self.src or "128" in self.src, (
            "Expected configurable target_partition_mb (default 128)"
        )


class TestSemanticCacheManager:
    """Verify smart cache manager."""

    @pytest.fixture(autouse=True)
    def _load_source(self):
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            self.src = f.read()
        self.tree = ast.parse(self.src)

    def test_class_defined(self):
        classes = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.ClassDef)]
        assert "CacheManager" in classes, f"Expected CacheManager; found: {classes}"

    def test_smart_cache_method(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "smart_cache" in funcs, "Expected smart_cache() method"

    def test_storage_levels(self):
        """Must reference MEMORY_ONLY, MEMORY_AND_DISK, DISK_ONLY."""
        for level in ["MEMORY_ONLY", "MEMORY_AND_DISK", "DISK_ONLY"]:
            assert level in self.src, f"Expected storage level {level}"

    def test_invalidate_method(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "invalidate" in funcs, "Expected invalidate() method"


class TestSemanticConfigTuner:
    """Verify configuration tuner."""

    @pytest.fixture(autouse=True)
    def _load_source(self):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            self.src = f.read()
        self.tree = ast.parse(self.src)

    def test_class_defined(self):
        classes = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.ClassDef)]
        assert "ConfigTuner" in classes, f"Expected ConfigTuner; found: {classes}"

    def test_apply_profile_method(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "apply_profile" in funcs, "Expected apply_profile() method"

    def test_profiles_defined(self):
        for profile in ["small", "medium", "large"]:
            assert profile in self.src, f"Expected profile '{profile}'"

    def test_aqe_configuration(self):
        """Must configure AQE (Adaptive Query Execution)."""
        has_aqe = "aqe" in self.src.lower() or "adaptiveQueryExecution" in self.src
        assert has_aqe, "Expected AQE configuration"


# ---------------------------------------------------------------------------
# Layer 3 — functional_check
# ---------------------------------------------------------------------------

class TestFunctionalSparkOptimization:
    """Functional checks — syntax and structure validation."""

    def _parse(self, filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            src = f.read()
        try:
            ast.parse(src)
            return True, None
        except SyntaxError as e:
            return False, str(e)

    def test_skew_handler_valid_python(self):
        ok, err = self._parse(SKEW_FILE)
        assert ok, f"skew_handler.py syntax error: {err}"

    def test_partition_advisor_valid_python(self):
        ok, err = self._parse(PARTITION_FILE)
        assert ok, f"partition_advisor.py syntax error: {err}"

    def test_cache_manager_valid_python(self):
        ok, err = self._parse(CACHE_FILE)
        assert ok, f"cache_manager.py syntax error: {err}"

    def test_config_tuner_valid_python(self):
        ok, err = self._parse(CONFIG_FILE)
        assert ok, f"config_tuner.py syntax error: {err}"

    def test_test_file_valid_python(self):
        ok, err = self._parse(TEST_FILE)
        assert ok, f"test_optimization.py syntax error: {err}"

    def test_init_exports_public_api(self):
        """__init__.py should export the main classes."""
        with open(INIT_FILE, "r", encoding="utf-8") as f:
            src = f.read()
        expected_exports = ["salted_join", "PartitionAdvisor", "CacheManager", "ConfigTuner"]
        found = [e for e in expected_exports if e in src]
        assert len(found) >= 2, (
            f"Expected __init__.py to export at least 2 public APIs; found: {found}"
        )
