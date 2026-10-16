"""
Test skill: spark-optimization
Verify that the Agent correctly implements adaptive partitioning and
skew-resistant join optimization for Spark SQL Catalyst.
"""

import os
import re
import subprocess
import pytest


class TestSparkOptimization:
    REPO_DIR = "/workspace/spark"

    # === File Path Checks ===

    def test_skew_join_rule_exists(self):
        """Verify SkewJoinOptimizationRule.scala was created"""
        path = os.path.join(
            self.REPO_DIR,
            "sql/catalyst/src/main/scala/org/apache/spark/sql/catalyst/optimizer/SkewJoinOptimizationRule.scala",
        )
        assert os.path.exists(path), f"SkewJoinOptimizationRule.scala not found"

    def test_partition_estimator_exists(self):
        """Verify AdaptivePartitionEstimator.scala was created"""
        path = os.path.join(
            self.REPO_DIR,
            "sql/catalyst/src/main/scala/org/apache/spark/sql/catalyst/optimizer/AdaptivePartitionEstimator.scala",
        )
        assert os.path.exists(path), f"AdaptivePartitionEstimator.scala not found"

    def test_skewed_join_exec_exists(self):
        """Verify SkewedSortMergeJoinExec.scala was created"""
        path = os.path.join(
            self.REPO_DIR,
            "sql/core/src/main/scala/org/apache/spark/sql/execution/joins/SkewedSortMergeJoinExec.scala",
        )
        assert os.path.exists(path), f"SkewedSortMergeJoinExec.scala not found"

    def test_dynamic_join_selection_exists(self):
        """Verify DynamicJoinSelection.scala was created"""
        path = os.path.join(
            self.REPO_DIR,
            "sql/core/src/main/scala/org/apache/spark/sql/execution/adaptive/DynamicJoinSelection.scala",
        )
        assert os.path.exists(path), f"DynamicJoinSelection.scala not found"

    def test_skew_rule_test_exists(self):
        """Verify SkewJoinOptimizationRuleSuite.scala was created"""
        path = os.path.join(
            self.REPO_DIR,
            "sql/catalyst/src/test/scala/org/apache/spark/sql/catalyst/optimizer/SkewJoinOptimizationRuleSuite.scala",
        )
        assert os.path.exists(path), f"SkewJoinOptimizationRuleSuite.scala not found"

    def test_skew_exec_test_exists(self):
        """Verify SkewedSortMergeJoinExecSuite.scala was created"""
        path = os.path.join(
            self.REPO_DIR,
            "sql/core/src/test/scala/org/apache/spark/sql/execution/joins/SkewedSortMergeJoinExecSuite.scala",
        )
        assert os.path.exists(path), f"SkewedSortMergeJoinExecSuite.scala not found"

    # === Semantic Checks: SkewJoinOptimizationRule ===

    def test_rule_extends_rule_trait(self):
        """Verify rule extends Rule[LogicalPlan]"""
        path = os.path.join(
            self.REPO_DIR,
            "sql/catalyst/src/main/scala/org/apache/spark/sql/catalyst/optimizer/SkewJoinOptimizationRule.scala",
        )
        with open(path) as f:
            content = f.read()
        assert "Rule[LogicalPlan]" in content or "Rule[" in content, (
            "Should extend Rule[LogicalPlan]"
        )

    def test_rule_handles_join_types(self):
        """Verify rule triggers on Inner, LeftOuter, RightOuter joins"""
        path = os.path.join(
            self.REPO_DIR,
            "sql/catalyst/src/main/scala/org/apache/spark/sql/catalyst/optimizer/SkewJoinOptimizationRule.scala",
        )
        with open(path) as f:
            content = f.read()
        assert "Inner" in content, "Should handle Inner joins"
        for join_type in ["LeftOuter", "RightOuter"]:
            assert join_type in content, f"Should handle {join_type} joins"

    def test_rule_uses_skew_factor(self):
        """Verify configurable skew factor threshold"""
        path = os.path.join(
            self.REPO_DIR,
            "sql/catalyst/src/main/scala/org/apache/spark/sql/catalyst/optimizer/SkewJoinOptimizationRule.scala",
        )
        with open(path) as f:
            content = f.read()
        assert "skewFactor" in content or "skew" in content.lower(), (
            "Should use configurable skew factor"
        )

    def test_rule_adds_salt_column(self):
        """Verify salting logic for skewed keys"""
        path = os.path.join(
            self.REPO_DIR,
            "sql/catalyst/src/main/scala/org/apache/spark/sql/catalyst/optimizer/SkewJoinOptimizationRule.scala",
        )
        with open(path) as f:
            content = f.read()
        assert "salt" in content.lower(), "Should add salt column for skewed joins"

    def test_rule_has_enabled_config(self):
        """Verify spark.sql.optimizer.skewJoin.enabled config"""
        path = os.path.join(
            self.REPO_DIR,
            "sql/catalyst/src/main/scala/org/apache/spark/sql/catalyst/optimizer/SkewJoinOptimizationRule.scala",
        )
        with open(path) as f:
            content = f.read()
        assert "enabled" in content.lower() or "skewJoin" in content, (
            "Should have enabled/disabled config option"
        )

    # === Semantic Checks: AdaptivePartitionEstimator ===

    def test_estimator_has_estimate_partitions(self):
        """Verify estimatePartitions method"""
        path = os.path.join(
            self.REPO_DIR,
            "sql/catalyst/src/main/scala/org/apache/spark/sql/catalyst/optimizer/AdaptivePartitionEstimator.scala",
        )
        with open(path) as f:
            content = f.read()
        assert "estimatePartitions" in content, (
            "Should have estimatePartitions method"
        )

    def test_estimator_has_compute_skew_ratio(self):
        """Verify computeSkewRatio method"""
        path = os.path.join(
            self.REPO_DIR,
            "sql/catalyst/src/main/scala/org/apache/spark/sql/catalyst/optimizer/AdaptivePartitionEstimator.scala",
        )
        with open(path) as f:
            content = f.read()
        assert "computeSkewRatio" in content or "skewRatio" in content, (
            "Should have computeSkewRatio method"
        )

    def test_estimator_has_recommend_repartition(self):
        """Verify recommendRepartition method"""
        path = os.path.join(
            self.REPO_DIR,
            "sql/catalyst/src/main/scala/org/apache/spark/sql/catalyst/optimizer/AdaptivePartitionEstimator.scala",
        )
        with open(path) as f:
            content = f.read()
        assert "recommendRepartition" in content or "repartition" in content.lower(), (
            "Should have recommendRepartition method"
        )

    # === Semantic Checks: SkewedSortMergeJoinExec ===

    def test_exec_extends_spark_plan(self):
        """Verify SkewedSortMergeJoinExec extends SparkPlan"""
        path = os.path.join(
            self.REPO_DIR,
            "sql/core/src/main/scala/org/apache/spark/sql/execution/joins/SkewedSortMergeJoinExec.scala",
        )
        with open(path) as f:
            content = f.read()
        assert "SparkPlan" in content or "BinaryExecNode" in content, (
            "Should extend SparkPlan or BinaryExecNode"
        )

    def test_exec_has_skewed_keys_param(self):
        """Verify skewedKeys parameter"""
        path = os.path.join(
            self.REPO_DIR,
            "sql/core/src/main/scala/org/apache/spark/sql/execution/joins/SkewedSortMergeJoinExec.scala",
        )
        with open(path) as f:
            content = f.read()
        assert "skewedKeys" in content, "Should accept skewedKeys parameter"

    def test_exec_has_do_execute(self):
        """Verify doExecute method"""
        path = os.path.join(
            self.REPO_DIR,
            "sql/core/src/main/scala/org/apache/spark/sql/execution/joins/SkewedSortMergeJoinExec.scala",
        )
        with open(path) as f:
            content = f.read()
        assert "doExecute" in content, "Should implement doExecute method"

    # === Semantic Checks: DynamicJoinSelection ===

    def test_dynamic_selection_checks_broadcast_threshold(self):
        """Verify broadcast threshold check"""
        path = os.path.join(
            self.REPO_DIR,
            "sql/core/src/main/scala/org/apache/spark/sql/execution/adaptive/DynamicJoinSelection.scala",
        )
        with open(path) as f:
            content = f.read()
        assert "broadcast" in content.lower(), (
            "Should check broadcast threshold"
        )

    def test_dynamic_selection_references_aqe(self):
        """Verify integration with AQE"""
        path = os.path.join(
            self.REPO_DIR,
            "sql/core/src/main/scala/org/apache/spark/sql/execution/adaptive/DynamicJoinSelection.scala",
        )
        with open(path) as f:
            content = f.read()
        assert "Shuffle" in content or "adaptive" in content.lower(), (
            "Should integrate with AQE shuffle stage"
        )

    # === Functional Checks ===

    def test_scala_files_have_package_declaration(self):
        """Verify all Scala files have proper package declarations"""
        files = [
            "sql/catalyst/src/main/scala/org/apache/spark/sql/catalyst/optimizer/SkewJoinOptimizationRule.scala",
            "sql/catalyst/src/main/scala/org/apache/spark/sql/catalyst/optimizer/AdaptivePartitionEstimator.scala",
        ]
        for rel_path in files:
            path = os.path.join(self.REPO_DIR, rel_path)
            with open(path) as f:
                content = f.read()
            assert "package " in content, (
                f"{rel_path} should have a package declaration"
            )

    def test_maven_compile(self):
        """Verify project compiles with new files"""
        result = subprocess.run(
            ["./build/mvn", "-DskipTests", "package", "-pl", "sql/catalyst,sql/core"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=600,
        )
        assert result.returncode == 0, (
            f"Maven compile failed:\n{result.stderr[-2000:]}"
        )
