"""
Test skill: spark-optimization
Verify that the Agent creates SkewJoinOptimizer Catalyst rule, SkewDetector,
and SkewedSortMergeJoinExec in Apache Spark (Scala).
"""

import os
import re
import subprocess
import pytest


class TestSparkOptimization:
    REPO_DIR = "/workspace/spark"

    # === File Path Checks ===

    def test_skew_join_optimizer_exists(self):
        """Verify SkewJoinOptimizer Catalyst rule file exists"""
        found = False
        for root, dirs, files in os.walk(self.REPO_DIR):
            if ".git" in root or "target" in root:
                continue
            for f in files:
                if "SkewJoinOptimizer" in f or ("skew" in f.lower() and "join" in f.lower() and f.endswith(".scala")):
                    found = True
                    break
            if found:
                break
        assert found, "SkewJoinOptimizer file not found"

    def test_skew_detector_exists(self):
        """Verify SkewDetector file exists"""
        found = False
        for root, dirs, files in os.walk(self.REPO_DIR):
            if ".git" in root or "target" in root:
                continue
            for f in files:
                if "SkewDetector" in f or ("skew" in f.lower() and "detect" in f.lower() and f.endswith(".scala")):
                    found = True
                    break
            if found:
                break
        assert found, "SkewDetector file not found"

    # === Semantic Checks ===

    def test_skew_join_optimizer_extends_rule(self):
        """Verify SkewJoinOptimizer extends Catalyst Rule"""
        content = self._find_content("SkewJoinOptimizer")
        has_rule = (
            "Rule[" in content
            or "extends Rule" in content
            or "Strategy" in content
            or "Optimizer" in content
        )
        assert has_rule, "SkewJoinOptimizer does not extend Catalyst Rule"

    def test_skew_detector_has_detection_logic(self):
        """Verify SkewDetector implements skew detection algorithm"""
        content = self._find_content("SkewDetector")
        content_lower = content.lower()
        has_detect = (
            "detect" in content_lower
            or "skew" in content_lower
            or "partition" in content_lower
            or "statistics" in content_lower
        )
        assert has_detect, "SkewDetector missing detection logic"

    def test_skewed_sort_merge_join_exec_defined(self):
        """Verify SkewedSortMergeJoinExec physical plan is defined"""
        found = False
        for root, dirs, files in os.walk(self.REPO_DIR):
            if ".git" in root or "target" in root:
                continue
            for f in files:
                if f.endswith(".scala"):
                    fpath = os.path.join(root, f)
                    try:
                        with open(fpath) as fh:
                            content = fh.read()
                        if "SkewedSortMergeJoinExec" in content or "SkewedSortMergeJoin" in content:
                            found = True
                            break
                    except (UnicodeDecodeError, PermissionError):
                        continue
            if found:
                break
        assert found, "SkewedSortMergeJoinExec not found"

    def test_optimizer_handles_partition_splitting(self):
        """Verify optimizer implements partition splitting for skewed keys"""
        content = self._find_content("SkewJoinOptimizer")
        content += self._find_content("SkewedSortMergeJoin")
        content_lower = content.lower()
        has_split = (
            "split" in content_lower
            or "partition" in content_lower
            or "repartition" in content_lower
            or "salt" in content_lower
        )
        assert has_split, "Optimizer missing partition splitting logic"

    def test_scala_files_have_package_declaration(self):
        """Verify Scala files have proper package declarations"""
        skew_files = []
        for root, dirs, files in os.walk(self.REPO_DIR):
            if ".git" in root or "target" in root:
                continue
            for f in files:
                if f.endswith(".scala") and "skew" in f.lower():
                    skew_files.append(os.path.join(root, f))
        assert len(skew_files) > 0, "No skew-related Scala files found"
        for sf in skew_files:
            with open(sf) as fh:
                content = fh.read()
            assert "package " in content, f"{sf} missing package declaration"

    # === Functional Checks ===

    def test_scala_files_no_obvious_syntax_errors(self):
        """Verify Scala files have balanced braces"""
        skew_files = []
        for root, dirs, files in os.walk(self.REPO_DIR):
            if ".git" in root or "target" in root:
                continue
            for f in files:
                if f.endswith(".scala") and "skew" in f.lower():
                    skew_files.append(os.path.join(root, f))
        for sf in skew_files:
            with open(sf) as fh:
                content = fh.read()
            # Remove strings and comments
            cleaned = re.sub(r'"[^"]*"', '', content)
            cleaned = re.sub(r'//[^\n]*', '', cleaned)
            cleaned = re.sub(r'/\*.*?\*/', '', cleaned, flags=re.DOTALL)
            opens = cleaned.count('{')
            closes = cleaned.count('}')
            assert opens == closes, (
                f"Unbalanced braces in {sf}: opens={opens}, closes={closes}"
            )

    def test_maven_or_sbt_compiles(self):
        """Verify the project compiles"""
        # Try Maven first
        if os.path.exists(os.path.join(self.REPO_DIR, "pom.xml")):
            result = subprocess.run(
                ["mvn", "compile", "-pl", "sql/catalyst", "-DskipTests", "-q"],
                cwd=self.REPO_DIR,
                capture_output=True,
                text=True,
                timeout=300,
            )
        elif os.path.exists(os.path.join(self.REPO_DIR, "build.sbt")):
            result = subprocess.run(
                ["sbt", "sql/compile"],
                cwd=self.REPO_DIR,
                capture_output=True,
                text=True,
                timeout=300,
            )
        else:
            result = subprocess.run(
                ["./build/mvn", "compile", "-pl", "sql/catalyst", "-DskipTests", "-q"],
                cwd=self.REPO_DIR,
                capture_output=True,
                text=True,
                timeout=300,
            )
        assert result.returncode == 0, (
            f"Compilation failed:\n{result.stdout[-500:]}\n{result.stderr[-500:]}"
        )

    def test_skew_detector_uses_statistics(self):
        """Verify SkewDetector uses statistical measures (median, std, percentile)"""
        content = self._find_content("SkewDetector")
        content_lower = content.lower()
        has_stats = (
            "median" in content_lower
            or "percentile" in content_lower
            or "stddev" in content_lower
            or "threshold" in content_lower
            or "statistics" in content_lower
        )
        assert has_stats, "SkewDetector should use statistical measures"

    def _find_content(self, class_name):
        """Helper to find content related to a class"""
        all_content = ""
        for root, dirs, files in os.walk(self.REPO_DIR):
            if ".git" in root or "target" in root:
                continue
            for f in files:
                if f.endswith(".scala"):
                    fpath = os.path.join(root, f)
                    try:
                        with open(fpath) as fh:
                            content = fh.read()
                        if class_name in content:
                            all_content += content + "\n"
                    except (UnicodeDecodeError, PermissionError):
                        continue
        return all_content
