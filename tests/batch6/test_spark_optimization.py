"""
Test skill: spark-optimization
Verify that the Agent optimizes a PySpark ETL pipeline with AQE config,
broadcast joins, skew handling via salted keys, incremental merge,
partition utilities, and data quality checks.
"""

import os
import re
import ast
import subprocess
import pytest


class TestSparkOptimization:
    REPO_DIR = "/workspace/spark"

    # === File Path Checks ===

    def test_spark_config_exists(self):
        path = os.path.join(self.REPO_DIR, "etl/spark_config.py")
        assert os.path.exists(path), f"spark_config.py not found at {path}"

    def test_clickstream_daily_exists(self):
        path = os.path.join(self.REPO_DIR, "etl/jobs/clickstream_daily.py")
        assert os.path.exists(path), f"clickstream_daily.py not found at {path}"

    def test_session_aggregation_exists(self):
        path = os.path.join(self.REPO_DIR, "etl/jobs/session_aggregation.py")
        assert os.path.exists(path), f"session_aggregation.py not found at {path}"

    def test_incremental_merge_exists(self):
        path = os.path.join(self.REPO_DIR, "etl/jobs/incremental_merge.py")
        assert os.path.exists(path), f"incremental_merge.py not found at {path}"

    def test_partition_utils_exists(self):
        path = os.path.join(self.REPO_DIR, "etl/utils/partition_utils.py")
        assert os.path.exists(path), f"partition_utils.py not found at {path}"

    def test_skew_handler_exists(self):
        path = os.path.join(self.REPO_DIR, "etl/utils/skew_handler.py")
        assert os.path.exists(path), f"skew_handler.py not found at {path}"

    def test_data_checks_exists(self):
        path = os.path.join(self.REPO_DIR, "etl/quality/data_checks.py")
        assert os.path.exists(path), f"data_checks.py not found at {path}"

    # === Semantic Checks ===

    def test_spark_config_has_aqe(self):
        """Verify AQE is enabled with skew join handling"""
        path = os.path.join(self.REPO_DIR, "etl/spark_config.py")
        with open(path, "r") as f:
            content = f.read()

        assert "adaptive.enabled" in content or "adaptive" in content, (
            "Must enable Adaptive Query Execution"
        )
        assert "skewJoin" in content or "skew" in content, (
            "Must enable AQE skew join handling"
        )

    def test_spark_config_has_kryo(self):
        """Verify Kryo serialization is configured"""
        path = os.path.join(self.REPO_DIR, "etl/spark_config.py")
        with open(path, "r") as f:
            content = f.read()

        assert "Kryo" in content or "kryo" in content, (
            "Must use Kryo serializer"
        )

    def test_spark_config_has_dynamic_allocation(self):
        """Verify dynamic allocation is configured"""
        path = os.path.join(self.REPO_DIR, "etl/spark_config.py")
        with open(path, "r") as f:
            content = f.read()

        assert "dynamicAllocation" in content, "Must enable dynamic allocation"

    def test_spark_config_has_zstd(self):
        """Verify zstd Parquet compression"""
        path = os.path.join(self.REPO_DIR, "etl/spark_config.py")
        with open(path, "r") as f:
            content = f.read()

        assert "zstd" in content.lower(), "Must use zstd Parquet compression"

    def test_clickstream_uses_explicit_schema(self):
        """Verify JSON ingestion uses explicit schema (no inference)"""
        path = os.path.join(self.REPO_DIR, "etl/jobs/clickstream_daily.py")
        with open(path, "r") as f:
            content = f.read()

        assert "StructType" in content or "schema" in content, (
            "Must use explicit schema for JSON ingestion"
        )
        has_no_infer = "inferSchema" not in content or "false" in content.lower()
        assert has_no_infer or "StructField" in content, (
            "Should not use schema inference"
        )

    def test_clickstream_uses_broadcast_join(self):
        """Verify dimension joins use broadcast"""
        path = os.path.join(self.REPO_DIR, "etl/jobs/clickstream_daily.py")
        with open(path, "r") as f:
            content = f.read()

        assert "broadcast" in content.lower(), (
            "Dimension joins should use broadcast()"
        )

    def test_clickstream_filters_early(self):
        """Verify heartbeat/ping events are filtered early"""
        path = os.path.join(self.REPO_DIR, "etl/jobs/clickstream_daily.py")
        with open(path, "r") as f:
            content = f.read()

        has_filter = (
            "heartbeat" in content or "ping" in content
        )
        assert has_filter, "Should filter out heartbeat/ping events early"

    def test_session_aggregation_handles_skew(self):
        """Verify session aggregation uses salted keys for skew"""
        path = os.path.join(self.REPO_DIR, "etl/jobs/session_aggregation.py")
        with open(path, "r") as f:
            content = f.read()

        assert "salt" in content.lower(), (
            "Must use salted key strategy for skew handling"
        )

    def test_skew_handler_has_salted_join(self):
        """Verify skew handler implements salted_join"""
        path = os.path.join(self.REPO_DIR, "etl/utils/skew_handler.py")
        with open(path, "r") as f:
            content = f.read()

        assert re.search(r"def\s+salted_join", content), "Missing salted_join function"
        assert re.search(r"def\s+detect_skew", content), "Missing detect_skew function"

    def test_data_checks_validates_completeness(self):
        """Verify data quality checks include completeness, uniqueness, freshness"""
        path = os.path.join(self.REPO_DIR, "etl/quality/data_checks.py")
        with open(path, "r") as f:
            content = f.read()

        content_lower = content.lower()
        assert "completeness" in content_lower or "null" in content, (
            "Must check completeness (null counts)"
        )
        assert "unique" in content_lower or "duplicate" in content_lower, (
            "Must check uniqueness"
        )

    # === Functional Checks ===

    def test_all_python_files_parse(self):
        """Verify all ETL Python files parse without syntax errors"""
        files = [
            "etl/spark_config.py",
            "etl/jobs/clickstream_daily.py",
            "etl/jobs/session_aggregation.py",
            "etl/jobs/incremental_merge.py",
            "etl/utils/partition_utils.py",
            "etl/utils/skew_handler.py",
            "etl/quality/data_checks.py",
        ]
        for filename in files:
            path = os.path.join(self.REPO_DIR, filename)
            with open(path, "r") as f:
                source = f.read()
            try:
                ast.parse(source)
            except SyntaxError as e:
                pytest.fail(f"{filename} has syntax error: {e}")

    def test_partition_utils_imports(self):
        """Verify partition_utils can be imported"""
        result = subprocess.run(
            ["python", "-c",
             "import sys; sys.path.insert(0, '.'); "
             "from etl.utils.partition_utils import calculate_optimal_partitions; "
             "print('OK')"],
            capture_output=True, text=True, timeout=30,
            cwd=self.REPO_DIR,
        )
        assert result.returncode == 0, (
            f"Failed to import partition_utils:\n{result.stderr[:500]}"
        )
