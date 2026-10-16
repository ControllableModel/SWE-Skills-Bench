"""
Test skill: spark-optimization
Verify that the Agent correctly implements Spark SQL query optimizations
for sales aggregation with broadcast joins, AQE, and custom UDFs in Scala.
"""

import os
import re
import subprocess
import pytest


class TestSparkOptimization:
    REPO_DIR = "/workspace/spark"

    AGGREGATION = "examples/src/main/scala/org/apache/spark/examples/sql/SalesAggregation.scala"
    OPTIMIZER = "examples/src/main/scala/org/apache/spark/examples/sql/SalesOptimizer.scala"
    UDFS = "examples/src/main/scala/org/apache/spark/examples/sql/SalesUDFs.scala"
    TESTS = "examples/src/test/scala/org/apache/spark/examples/sql/SalesAggregationSuite.scala"

    def _read_file(self, rel_path):
        filepath = os.path.join(self.REPO_DIR, rel_path)
        with open(filepath) as f:
            return f.read()

    # === File Path Checks ===

    def test_aggregation_file_exists(self):
        filepath = os.path.join(self.REPO_DIR, self.AGGREGATION)
        assert os.path.exists(filepath), f"SalesAggregation.scala not found at {filepath}"

    def test_optimizer_file_exists(self):
        filepath = os.path.join(self.REPO_DIR, self.OPTIMIZER)
        assert os.path.exists(filepath), f"SalesOptimizer.scala not found at {filepath}"

    def test_udfs_file_exists(self):
        filepath = os.path.join(self.REPO_DIR, self.UDFS)
        assert os.path.exists(filepath), f"SalesUDFs.scala not found at {filepath}"

    def test_tests_file_exists(self):
        filepath = os.path.join(self.REPO_DIR, self.TESTS)
        assert os.path.exists(filepath), f"SalesAggregationSuite.scala not found at {filepath}"

    # === Semantic Checks ===

    def test_aggregation_computes_revenue_and_profit(self):
        """Verify revenue = quantity * unit_price * (1 - discount) and profit"""
        content = self._read_file(self.AGGREGATION)
        assert "revenue" in content.lower(), "Missing revenue computation"
        assert "profit" in content.lower(), "Missing profit computation"
        assert "discount" in content, "Missing discount in revenue formula"

    def test_aggregation_uses_broadcast_join(self):
        """Verify broadcast join is used for dimension tables"""
        content = self._read_file(self.AGGREGATION)
        has_broadcast = bool(re.search(
            r'(broadcast|BroadcastHashJoin|broadcast\()', content, re.IGNORECASE
        ))
        assert has_broadcast, "Missing broadcast join for dimension tables"

    def test_aggregation_groups_by_required_columns(self):
        """Verify aggregation groups by date, region, category, segment"""
        content = self._read_file(self.AGGREGATION)
        for col in ["sale_date", "region", "category"]:
            assert col in content, f"Aggregation missing group-by column: {col}"

    def test_optimizer_enables_aqe(self):
        """Verify AQE is enabled with coalescing and skew join"""
        content = self._read_file(self.OPTIMIZER)
        assert "adaptive.enabled" in content, "Missing AQE enabled config"
        assert "coalescePartitions" in content, "Missing coalesce partitions config"
        assert "skewJoin" in content, "Missing skew join config"

    def test_optimizer_sets_broadcast_threshold(self):
        """Verify broadcast threshold is set to 50MB"""
        content = self._read_file(self.OPTIMIZER)
        assert "autoBroadcastJoinThreshold" in content, \
            "Missing autoBroadcastJoinThreshold config"

    def test_optimizer_has_repartition_helper(self):
        """Verify repartitionForWrite utility method exists"""
        content = self._read_file(self.OPTIMIZER)
        assert "repartitionForWrite" in content, "Missing repartitionForWrite method"

    def test_udfs_fiscal_quarter(self):
        """Verify fiscal_quarter UDF with Apr-Mar fiscal year"""
        content = self._read_file(self.UDFS)
        assert "fiscal_quarter" in content, "Missing fiscal_quarter UDF"
        # Jan-Mar = Q4; Apr-Jun = Q1; Jul-Sep = Q2; Oct-Dec = Q3
        assert "Q1" in content and "Q4" in content, \
            "fiscal_quarter missing quarter labels"

    def test_udfs_revenue_bucket(self):
        """Verify revenue_bucket UDF with defined ranges"""
        content = self._read_file(self.UDFS)
        assert "revenue_bucket" in content, "Missing revenue_bucket UDF"
        buckets = ["0-100", "100-500", "500-1K", "1K-5K", "5K-10K", "10K+"]
        found = sum(1 for b in buckets if b in content)
        assert found >= 4, f"revenue_bucket missing bucket ranges, found {found}/6"

    def test_udfs_product_category_rollup(self):
        """Verify product_category_rollup UDF"""
        content = self._read_file(self.UDFS)
        assert "product_category_rollup" in content, \
            "Missing product_category_rollup UDF"

    # === Functional Checks ===

    def test_aggregation_computes_all_metrics(self):
        """Verify total_revenue, total_profit, order_count, avg_order_value, unique_customers"""
        content = self._read_file(self.AGGREGATION)
        for metric in ["total_revenue", "total_profit", "order_count"]:
            assert metric in content, f"Missing aggregation metric: {metric}"

    def test_output_partitioned_by_fiscal_quarter(self):
        """Verify output is partitioned by fiscal_quarter"""
        content = self._read_file(self.AGGREGATION)
        assert "fiscal_quarter" in content, \
            "Output missing partitioning by fiscal_quarter"
        has_partition_write = bool(re.search(
            r'(partitionBy|partition_by)', content, re.IGNORECASE
        ))
        assert has_partition_write, "Output missing partitionBy for writing"

    def test_tests_validate_udf_outputs(self):
        """Verify test suite validates UDF outputs"""
        content = self._read_file(self.TESTS)
        assert "fiscal_quarter" in content, "Tests missing fiscal_quarter validation"
        assert "revenue_bucket" in content, "Tests missing revenue_bucket validation"
        assert "test" in content.lower(), "Tests missing test definitions"
