"""
Test skill: spark-optimization
Verify that the Agent creates a Spark job optimization demo showing
partitioning, caching, broadcast joins, shuffle minimization, and
before/after performance comparisons.
"""

import os
import re
import ast
import subprocess
import pytest


class TestSparkOptimization:
    REPO_DIR = "/workspace/spark"

    # === File Path Checks ===

    def test_demo_script_exists(self):
        """Verify spark_optimization_demo.py exists"""
        path = os.path.join(
            self.REPO_DIR,
            "examples/src/main/python/spark_optimization_demo.py",
        )
        assert os.path.exists(path), (
            f"spark_optimization_demo.py not found at {path}"
        )

    # === Semantic Checks ===

    def test_uses_spark_session(self):
        """Verify SparkSession is created"""
        path = os.path.join(
            self.REPO_DIR,
            "examples/src/main/python/spark_optimization_demo.py",
        )
        with open(path) as f:
            content = f.read()

        assert "SparkSession" in content, (
            "Demo should create a SparkSession"
        )

    def test_repartitioning(self):
        """Verify repartitioning technique is demonstrated"""
        path = os.path.join(
            self.REPO_DIR,
            "examples/src/main/python/spark_optimization_demo.py",
        )
        with open(path) as f:
            content = f.read()

        partition_indicators = [
            "repartition", "coalesce", "partitionBy",
            "numPartitions", "partition",
        ]
        found = [ind for ind in partition_indicators if ind in content]
        assert len(found) >= 1, (
            f"Should demonstrate repartitioning. Found: {found}"
        )

    def test_caching(self):
        """Verify caching/persistence is demonstrated"""
        path = os.path.join(
            self.REPO_DIR,
            "examples/src/main/python/spark_optimization_demo.py",
        )
        with open(path) as f:
            content = f.read()

        cache_indicators = [
            ".cache()", ".persist()", "StorageLevel",
            "MEMORY_ONLY", "MEMORY_AND_DISK",
        ]
        found = [ind for ind in cache_indicators if ind in content]
        assert len(found) >= 1, (
            f"Should demonstrate caching. Found: {found}"
        )

    def test_broadcast_join(self):
        """Verify broadcast variable/join optimization"""
        path = os.path.join(
            self.REPO_DIR,
            "examples/src/main/python/spark_optimization_demo.py",
        )
        with open(path) as f:
            content = f.read()

        broadcast_indicators = [
            "broadcast", "Broadcast", "sc.broadcast",
            "F.broadcast", "broadcast(",
        ]
        found = [ind for ind in broadcast_indicators if ind in content]
        assert len(found) >= 1, (
            f"Should demonstrate broadcast optimization. Found: {found}"
        )

    def test_performance_comparison(self):
        """Verify before/after performance comparison"""
        path = os.path.join(
            self.REPO_DIR,
            "examples/src/main/python/spark_optimization_demo.py",
        )
        with open(path) as f:
            content = f.read().lower()

        perf_indicators = [
            "time", "duration", "elapsed", "before", "after",
            "baseline", "optimized", "speedup", "improvement",
        ]
        found = [ind for ind in perf_indicators if ind in content]
        assert len(found) >= 3, (
            f"Should include performance comparisons. Found: {found}"
        )

    def test_dataset_generation(self):
        """Verify a non-trivial dataset is used"""
        path = os.path.join(
            self.REPO_DIR,
            "examples/src/main/python/spark_optimization_demo.py",
        )
        with open(path) as f:
            content = f.read()

        data_indicators = [
            "createDataFrame", "range(", "parallelize",
            "read.", "toDF", "spark.range",
        ]
        found = [ind for ind in data_indicators if ind in content]
        assert len(found) >= 1, (
            f"Should create/load a dataset. Found: {found}"
        )

    def test_explains_optimization_rationale(self):
        """Verify the example explains why optimizations help"""
        path = os.path.join(
            self.REPO_DIR,
            "examples/src/main/python/spark_optimization_demo.py",
        )
        with open(path) as f:
            content = f.read()

        # Should have comments or prints explaining optimizations
        explanation_indicators = [
            "#", '"""', "print(", "shuffle", "network",
            "data skew", "locality", "overhead",
        ]
        found = [ind for ind in explanation_indicators if ind in content]
        assert len(found) >= 3, (
            f"Should explain optimization rationale. Found: {found}"
        )

    # === Functional Checks ===

    def test_script_valid_python(self):
        """Verify script is valid Python syntax"""
        path = os.path.join(
            self.REPO_DIR,
            "examples/src/main/python/spark_optimization_demo.py",
        )
        with open(path) as f:
            source = f.read()
        try:
            ast.parse(source)
        except SyntaxError as e:
            pytest.fail(f"spark_optimization_demo.py has syntax errors: {e}")

    def test_imports_pyspark(self):
        """Verify script imports PySpark"""
        path = os.path.join(
            self.REPO_DIR,
            "examples/src/main/python/spark_optimization_demo.py",
        )
        with open(path) as f:
            content = f.read()

        assert "pyspark" in content, "Script should import pyspark"

    def test_no_hardcoded_paths(self):
        """Verify no hardcoded absolute file paths that would break portability"""
        path = os.path.join(
            self.REPO_DIR,
            "examples/src/main/python/spark_optimization_demo.py",
        )
        with open(path) as f:
            content = f.read()

        # Check for obvious hardcoded paths
        suspicious = re.findall(r'["\']/(home|Users|tmp)/\S+["\']', content)
        assert len(suspicious) == 0, (
            f"Should not have hardcoded absolute paths: {suspicious}"
        )
