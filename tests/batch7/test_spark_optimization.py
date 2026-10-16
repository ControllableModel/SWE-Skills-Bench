"""
Test skill: spark-optimization
Verify that the Agent implements an Adaptive Query Execution Strategy Optimizer
for Spark SQL — SkewedPartitionSplitter, PartitionCoalescer, and
AdaptiveStrategyOptimizer Catalyst rules.
"""

import os
import re
import subprocess
import pytest


class TestSparkOptimization:
    REPO_DIR = "/workspace/spark"
    BASE = "sql/core/src/main/scala/org/apache/spark/sql/execution/adaptive"
    TEST = "sql/core/src/test/scala/org/apache/spark/sql/execution/adaptive"

    # ────────────────── helpers ──────────────────

    def _read(self, rel_path):
        fpath = os.path.join(self.REPO_DIR, rel_path)
        with open(fpath, "r") as f:
            return f.read()

    def _exists(self, rel_path):
        return os.path.isfile(os.path.join(self.REPO_DIR, rel_path))

    # === File Path Checks ===

    def test_skewed_splitter_exists(self):
        """SkewedPartitionSplitter.scala must exist"""
        assert self._exists(f"{self.BASE}/SkewedPartitionSplitter.scala")

    def test_partition_coalescer_exists(self):
        """PartitionCoalescer.scala must exist"""
        assert self._exists(f"{self.BASE}/PartitionCoalescer.scala")

    def test_strategy_optimizer_exists(self):
        """AdaptiveStrategyOptimizer.scala must exist"""
        assert self._exists(f"{self.BASE}/AdaptiveStrategyOptimizer.scala")

    def test_splitter_suite_exists(self):
        """SkewedPartitionSplitterSuite.scala test must exist"""
        assert self._exists(f"{self.TEST}/SkewedPartitionSplitterSuite.scala")

    def test_coalescer_suite_exists(self):
        """PartitionCoalescerSuite.scala test must exist"""
        assert self._exists(f"{self.TEST}/PartitionCoalescerSuite.scala")

    # === Semantic Checks — SkewedPartitionSplitter ===

    def test_splitter_extends_rule(self):
        """SkewedPartitionSplitter must extend Rule[SparkPlan]"""
        src = self._read(f"{self.BASE}/SkewedPartitionSplitter.scala")
        assert "Rule" in src and "SparkPlan" in src, (
            "SkewedPartitionSplitter should extend Rule[SparkPlan]"
        )

    def test_splitter_config_skew_threshold(self):
        """Must reference skewedPartitionThresholdInBytes config key"""
        src = self._read(f"{self.BASE}/SkewedPartitionSplitter.scala")
        assert "skewedPartitionThreshold" in src or "skewThresholdBytes" in src, (
            "Skew threshold configuration not found"
        )

    def test_splitter_config_skew_factor(self):
        """Must reference skewedPartitionFactor config or skewFactor"""
        src = self._read(f"{self.BASE}/SkewedPartitionSplitter.scala")
        assert "skewFactor" in src or "skewedPartitionFactor" in src, (
            "Skew factor configuration not found"
        )

    def test_splitter_max_splits(self):
        """Must have maxSplits parameter"""
        src = self._read(f"{self.BASE}/SkewedPartitionSplitter.scala")
        assert "maxSplits" in src, "maxSplits parameter not found"

    def test_splitter_median_calculation(self):
        """Must compute median partition size"""
        src = self._read(f"{self.BASE}/SkewedPartitionSplitter.scala")
        assert "median" in src.lower(), "Median partition size calculation not found"

    def test_skew_report_case_class(self):
        """SkewReport case class must be defined"""
        src = self._read(f"{self.BASE}/SkewedPartitionSplitter.scala")
        assert re.search(r'case\s+class\s+SkewReport', src), (
            "SkewReport case class not found"
        )

    def test_skewed_partition_info_case_class(self):
        """SkewedPartitionInfo case class must be defined"""
        src = self._read(f"{self.BASE}/SkewedPartitionSplitter.scala")
        assert re.search(r'case\s+class\s+SkewedPartitionInfo', src), (
            "SkewedPartitionInfo case class not found"
        )

    # === Semantic Checks — PartitionCoalescer ===

    def test_coalescer_extends_rule(self):
        """PartitionCoalescer must extend Rule[SparkPlan]"""
        src = self._read(f"{self.BASE}/PartitionCoalescer.scala")
        assert "Rule" in src and "SparkPlan" in src, (
            "PartitionCoalescer should extend Rule[SparkPlan]"
        )

    def test_coalescer_target_size(self):
        """Must reference targetSizeInBytes or targetPartitionSizeBytes"""
        src = self._read(f"{self.BASE}/PartitionCoalescer.scala")
        assert "targetPartitionSizeBytes" in src or "targetSizeInBytes" in src, (
            "Target partition size configuration not found"
        )

    def test_coalescer_min_partitions(self):
        """Must support minPartitions constraint"""
        src = self._read(f"{self.BASE}/PartitionCoalescer.scala")
        assert "minPartitions" in src or "minPartitionNum" in src, (
            "minPartitions parameter not found"
        )

    # === Semantic Checks — AdaptiveStrategyOptimizer ===

    def test_optimizer_applies_both_rules(self):
        """AdaptiveStrategyOptimizer must reference both Splitter and Coalescer"""
        src = self._read(f"{self.BASE}/AdaptiveStrategyOptimizer.scala")
        assert "SkewedPartitionSplitter" in src, (
            "Does not reference SkewedPartitionSplitter"
        )
        assert "PartitionCoalescer" in src, (
            "Does not reference PartitionCoalescer"
        )

    # === Functional Checks ===

    def test_sbt_compile(self):
        """Project must compile with sbt"""
        result = subprocess.run(
            ["build/sbt", "sql/compile"],
            capture_output=True, text=True, cwd=self.REPO_DIR, timeout=600,
        )
        assert result.returncode == 0, (
            f"sbt compile failed:\n{result.stdout[-2000:]}\n{result.stderr[-2000:]}"
        )

    def test_splitter_tests_pass(self):
        """SkewedPartitionSplitter tests must pass"""
        result = subprocess.run(
            ["build/sbt",
             "sql/testOnly *SkewedPartitionSplitterSuite"],
            capture_output=True, text=True, cwd=self.REPO_DIR, timeout=600,
        )
        assert result.returncode == 0, (
            f"Tests failed:\n{result.stdout[-2000:]}\n{result.stderr[-2000:]}"
        )

    def test_coalescer_tests_pass(self):
        """PartitionCoalescer tests must pass"""
        result = subprocess.run(
            ["build/sbt",
             "sql/testOnly *PartitionCoalescerSuite"],
            capture_output=True, text=True, cwd=self.REPO_DIR, timeout=600,
        )
        assert result.returncode == 0, (
            f"Tests failed:\n{result.stdout[-2000:]}\n{result.stderr[-2000:]}"
        )
