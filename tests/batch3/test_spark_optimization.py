"""
Tests for the spark-optimization skill.

Validates that an optimized Spark SQL pipeline with joins, aggregations,
window functions, AQE configuration, caching strategy, and metrics
collection was implemented for Apache Spark.

Repo: spark (https://github.com/apache/spark)
"""

import os
import re

REPO_DIR = "/workspace/spark"

SCALA_DIR = os.path.join(
    REPO_DIR, "examples", "src", "main", "scala",
    "org", "apache", "spark", "examples", "sql",
)

TEST_DIR = os.path.join(
    REPO_DIR, "examples", "src", "test", "scala",
    "org", "apache", "spark", "examples", "sql",
)


class TestFilePathCheck:
    """Verify that all required files were created."""

    def test_optimized_pipeline_exists(self):
        path = os.path.join(SCALA_DIR, "OptimizedPipeline.scala")
        assert os.path.isfile(path), f"Expected OptimizedPipeline.scala at {path}"

    def test_pipeline_config_exists(self):
        path = os.path.join(SCALA_DIR, "PipelineConfig.scala")
        assert os.path.isfile(path), f"Expected PipelineConfig.scala at {path}"

    def test_pipeline_metrics_exists(self):
        path = os.path.join(SCALA_DIR, "PipelineMetrics.scala")
        assert os.path.isfile(path), f"Expected PipelineMetrics.scala at {path}"

    def test_test_suite_exists(self):
        path = os.path.join(TEST_DIR, "OptimizedPipelineSuite.scala")
        assert os.path.isfile(path), f"Expected OptimizedPipelineSuite.scala at {path}"


class TestSemanticJoinOptimization:
    """Verify join strategy choices in the pipeline."""

    def _read_pipeline(self):
        path = os.path.join(SCALA_DIR, "OptimizedPipeline.scala")
        with open(path, "r") as f:
            return f.read()

    def test_broadcast_join_for_products(self):
        content = self._read_pipeline()
        assert re.search(r"broadcast\s*\(|BroadcastHashJoin|broadcast", content, re.IGNORECASE), (
            "Expected broadcast join for products (small dimension table)"
        )

    def test_sort_merge_join_for_users(self):
        """Transactions joined with users should use sort-merge (default for large tables)."""
        content = self._read_pipeline()
        assert re.search(r"join\s*\(|\.join\b", content), (
            "Expected join operation for transactions and users"
        )

    def test_repartition_by_user_id(self):
        content = self._read_pipeline()
        assert re.search(r'repartition.*user_id|repartition.*"user_id"', content, re.IGNORECASE), (
            "Expected repartition by user_id before join with users"
        )

    def test_auto_broadcast_threshold(self):
        content = self._read_pipeline()
        config_path = os.path.join(SCALA_DIR, "PipelineConfig.scala")
        with open(config_path, "r") as f:
            config_content = f.read()
        combined = content + config_content
        assert re.search(r"autoBroadcastJoinThreshold|100.*MB|100MB|104857600", combined), (
            "Expected autoBroadcastJoinThreshold set to 100MB"
        )


class TestSemanticAQEConfiguration:
    """Verify Adaptive Query Execution settings."""

    def _read_config(self):
        path = os.path.join(SCALA_DIR, "PipelineConfig.scala")
        with open(path, "r") as f:
            return f.read()

    def _read_pipeline(self):
        path = os.path.join(SCALA_DIR, "OptimizedPipeline.scala")
        with open(path, "r") as f:
            return f.read()

    def test_aqe_enabled(self):
        combined = self._read_config() + self._read_pipeline()
        assert re.search(r"adaptive\.enabled.*true|adaptive.*enabled", combined, re.IGNORECASE), (
            "Expected AQE enabled configuration"
        )

    def test_coalesce_partitions_enabled(self):
        combined = self._read_config() + self._read_pipeline()
        assert re.search(r"coalescePartitions", combined), (
            "Expected coalescePartitions.enabled configuration"
        )

    def test_skew_join_enabled(self):
        combined = self._read_config() + self._read_pipeline()
        assert re.search(r"skewJoin", combined), (
            "Expected skewJoin.enabled configuration"
        )

    def test_shuffle_partitions_computed(self):
        """Shuffle partitions should be computed from data size, not hardcoded 200."""
        combined = self._read_config() + self._read_pipeline()
        assert re.search(r"shuffle\.partitions|128|max\(200", combined, re.IGNORECASE), (
            "Expected dynamic shuffle partition computation"
        )


class TestSemanticCachingStrategy:
    """Verify caching decisions in the pipeline."""

    def _read_pipeline(self):
        path = os.path.join(SCALA_DIR, "OptimizedPipeline.scala")
        with open(path, "r") as f:
            return f.read()

    def test_cache_or_persist_used(self):
        content = self._read_pipeline()
        assert re.search(r"\.cache\(\)|\.persist\(|MEMORY_AND_DISK", content), (
            "Expected cache() or persist(MEMORY_AND_DISK) on joined-filtered DataFrame"
        )

    def test_unpersist_called(self):
        content = self._read_pipeline()
        assert re.search(r"\.unpersist\(", content), (
            "Expected unpersist() after pipeline completes"
        )

    def test_memory_and_disk_storage_level(self):
        content = self._read_pipeline()
        assert re.search(r"MEMORY_AND_DISK|StorageLevel", content), (
            "Expected MEMORY_AND_DISK storage level"
        )


class TestSemanticWindowFunction:
    """Verify window function usage for ranking."""

    def _read_pipeline(self):
        path = os.path.join(SCALA_DIR, "OptimizedPipeline.scala")
        with open(path, "r") as f:
            return f.read()

    def test_dense_rank_used(self):
        content = self._read_pipeline()
        assert re.search(r"dense_rank|denseRank", content), (
            "Expected dense_rank() window function"
        )

    def test_window_partitioned_by_category(self):
        content = self._read_pipeline()
        assert re.search(r"partitionBy.*category|Window.*category", content, re.IGNORECASE), (
            "Expected window partitioned by category"
        )

    def test_ordered_by_total_spend_desc(self):
        content = self._read_pipeline()
        assert re.search(r"total_spend.*desc|orderBy.*total_spend|desc.*total_spend", content, re.IGNORECASE), (
            "Expected ordering by total_spend DESC"
        )


class TestSemanticOutputFormat:
    """Verify output writing configuration."""

    def _read_pipeline(self):
        path = os.path.join(SCALA_DIR, "OptimizedPipeline.scala")
        with open(path, "r") as f:
            return f.read()

    def test_parquet_output(self):
        content = self._read_pipeline()
        assert re.search(r"parquet|\.parquet\(", content, re.IGNORECASE), (
            "Expected Parquet output format"
        )

    def test_partitioned_by_region_and_category(self):
        content = self._read_pipeline()
        assert re.search(r'partitionBy.*region.*category|partitionBy.*"region"', content, re.IGNORECASE), (
            "Expected output partitioned by region and category"
        )


class TestSemanticPipelineMetrics:
    """Verify metrics collection class."""

    def _read_metrics(self):
        path = os.path.join(SCALA_DIR, "PipelineMetrics.scala")
        with open(path, "r") as f:
            return f.read()

    def test_pipeline_metrics_case_class(self):
        content = self._read_metrics()
        assert re.search(r"case\s+class\s+PipelineMetrics", content), (
            "Expected PipelineMetrics case class"
        )

    def test_stage_name_field(self):
        content = self._read_metrics()
        assert re.search(r"stage_name|stageName", content), (
            "Expected stage_name field in PipelineMetrics"
        )

    def test_duration_field(self):
        content = self._read_metrics()
        assert re.search(r"duration|duration_ms|durationMs", content), (
            "Expected duration field in PipelineMetrics"
        )


class TestFunctionalScalaSyntax:
    """Validate Scala files have balanced braces."""

    def _check_balanced_braces(self, filepath):
        with open(filepath, "r") as f:
            content = f.read()
        assert content.count("{") == content.count("}"), (
            f"Unmatched braces in {os.path.basename(filepath)}"
        )

    def test_pipeline_balanced(self):
        self._check_balanced_braces(os.path.join(SCALA_DIR, "OptimizedPipeline.scala"))

    def test_config_balanced(self):
        self._check_balanced_braces(os.path.join(SCALA_DIR, "PipelineConfig.scala"))

    def test_metrics_balanced(self):
        self._check_balanced_braces(os.path.join(SCALA_DIR, "PipelineMetrics.scala"))

    def test_test_suite_balanced(self):
        self._check_balanced_braces(os.path.join(TEST_DIR, "OptimizedPipelineSuite.scala"))

    def test_test_suite_has_test_methods(self):
        path = os.path.join(TEST_DIR, "OptimizedPipelineSuite.scala")
        with open(path, "r") as f:
            content = f.read()
        test_count = len(re.findall(r'test\s*\("|@Test|def\s+test', content))
        assert test_count >= 2, (
            f"Expected at least 2 test methods in suite, found {test_count}"
        )
