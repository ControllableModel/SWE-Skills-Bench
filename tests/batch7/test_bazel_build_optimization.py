"""
Test skill: bazel-build-optimization
Verify that the Agent implements a Remote Cache Hit Rate Analyzer for Bazel —
CacheHitAnalyzer (BEP event parsing, per-target and aggregate stats),
CacheAnalysisReport (AggregateStats, TargetCacheStats, FrequentMiss records,
toJson/toText output), and InputChangeTracker (digest history, miss classification).
"""

import os
import re
import subprocess
import pytest


class TestBazelBuildOptimization:
    REPO_DIR = "/workspace/bazel"

    # ────── helpers ──────

    def _read(self, rel_path):
        fpath = os.path.join(self.REPO_DIR, rel_path)
        with open(fpath, "r") as f:
            return f.read()

    def _exists(self, rel_path):
        return os.path.isfile(os.path.join(self.REPO_DIR, rel_path))

    # === File Path Checks ===

    def test_cache_hit_analyzer_exists(self):
        """CacheHitAnalyzer.java must exist"""
        assert self._exists(
            "src/main/java/com/google/devtools/build/lib/remote/CacheHitAnalyzer.java"
        )

    def test_cache_analysis_report_exists(self):
        """CacheAnalysisReport.java must exist"""
        assert self._exists(
            "src/main/java/com/google/devtools/build/lib/remote/CacheAnalysisReport.java"
        )

    def test_input_change_tracker_exists(self):
        """InputChangeTracker.java must exist"""
        assert self._exists(
            "src/main/java/com/google/devtools/build/lib/remote/InputChangeTracker.java"
        )

    def test_cache_hit_analyzer_test_exists(self):
        """CacheHitAnalyzerTest.java must exist"""
        assert self._exists(
            "src/test/java/com/google/devtools/build/lib/remote/CacheHitAnalyzerTest.java"
        )

    def test_input_change_tracker_test_exists(self):
        """InputChangeTrackerTest.java must exist"""
        assert self._exists(
            "src/test/java/com/google/devtools/build/lib/remote/InputChangeTrackerTest.java"
        )

    # === Semantic Checks — CacheHitAnalyzer ===

    def test_analyzer_class_declaration(self):
        """CacheHitAnalyzer class declared"""
        src = self._read(
            "src/main/java/com/google/devtools/build/lib/remote/CacheHitAnalyzer.java"
        )
        assert re.search(r'class\s+CacheHitAnalyzer', src)

    def test_analyzer_constructor_takes_events(self):
        """Constructor accepts List of BuildEvent"""
        src = self._read(
            "src/main/java/com/google/devtools/build/lib/remote/CacheHitAnalyzer.java"
        )
        assert "List" in src and ("BuildEvent" in src or "events" in src.lower())

    def test_analyzer_analyze_method(self):
        """analyze() returns CacheAnalysisReport"""
        src = self._read(
            "src/main/java/com/google/devtools/build/lib/remote/CacheHitAnalyzer.java"
        )
        assert re.search(r'CacheAnalysisReport\s+analyze\s*\(', src)

    def test_analyzer_cache_status_classification(self):
        """Must classify CACHE_HIT, CACHE_MISS, LOCAL_ONLY"""
        src = self._read(
            "src/main/java/com/google/devtools/build/lib/remote/CacheHitAnalyzer.java"
        )
        lower = src.lower()
        assert "cache_hit" in lower or "cachehit" in lower
        assert "cache_miss" in lower or "cachemiss" in lower

    def test_analyzer_per_target_grouping(self):
        """Must group actions by target label"""
        src = self._read(
            "src/main/java/com/google/devtools/build/lib/remote/CacheHitAnalyzer.java"
        )
        lower = src.lower()
        assert "target" in lower and ("label" in lower or "group" in lower)

    # === Semantic Checks — CacheAnalysisReport ===

    def test_report_aggregate_stats(self):
        """AggregateStats record must be defined"""
        src = self._read(
            "src/main/java/com/google/devtools/build/lib/remote/CacheAnalysisReport.java"
        )
        assert "AggregateStats" in src

    def test_report_target_cache_stats(self):
        """TargetCacheStats record must be defined"""
        src = self._read(
            "src/main/java/com/google/devtools/build/lib/remote/CacheAnalysisReport.java"
        )
        assert "TargetCacheStats" in src

    def test_report_frequent_miss(self):
        """FrequentMiss record must be defined"""
        src = self._read(
            "src/main/java/com/google/devtools/build/lib/remote/CacheAnalysisReport.java"
        )
        assert "FrequentMiss" in src

    def test_report_to_json(self):
        """toJson() method must exist"""
        src = self._read(
            "src/main/java/com/google/devtools/build/lib/remote/CacheAnalysisReport.java"
        )
        assert "toJson" in src

    def test_report_to_text(self):
        """toText() method must exist"""
        src = self._read(
            "src/main/java/com/google/devtools/build/lib/remote/CacheAnalysisReport.java"
        )
        assert "toText" in src

    def test_report_hit_rate_percent(self):
        """hitRatePercent field must exist"""
        src = self._read(
            "src/main/java/com/google/devtools/build/lib/remote/CacheAnalysisReport.java"
        )
        assert "hitRatePercent" in src or "hitRate" in src

    # === Semantic Checks — InputChangeTracker ===

    def test_tracker_class_declaration(self):
        """InputChangeTracker class declared"""
        src = self._read(
            "src/main/java/com/google/devtools/build/lib/remote/InputChangeTracker.java"
        )
        assert re.search(r'class\s+InputChangeTracker', src)

    def test_tracker_record_action(self):
        """recordAction method must exist"""
        src = self._read(
            "src/main/java/com/google/devtools/build/lib/remote/InputChangeTracker.java"
        )
        assert "recordAction" in src

    def test_tracker_get_frequently_changed(self):
        """getFrequentlyChangedInputs must exist"""
        src = self._read(
            "src/main/java/com/google/devtools/build/lib/remote/InputChangeTracker.java"
        )
        assert "getFrequentlyChangedInputs" in src

    def test_tracker_primary_cause(self):
        """getPrimaryCauseForTarget method must exist"""
        src = self._read(
            "src/main/java/com/google/devtools/build/lib/remote/InputChangeTracker.java"
        )
        assert "getPrimaryCauseForTarget" in src

    def test_tracker_miss_classification_labels(self):
        """Must classify misses: input_change, config_change, new_target, cache_eviction"""
        src = self._read(
            "src/main/java/com/google/devtools/build/lib/remote/InputChangeTracker.java"
        )
        for cause in ["input_change", "config_change", "new_target", "cache_eviction"]:
            assert cause in src, f"Missing cause classification: {cause}"

    # === Semantic Checks — BUILD file ===

    def test_build_file_references_new_sources(self):
        """BUILD file should list the new source files"""
        src = self._read(
            "src/main/java/com/google/devtools/build/lib/remote/BUILD"
        )
        assert "CacheHitAnalyzer" in src, "CacheHitAnalyzer not in BUILD"
        assert "InputChangeTracker" in src, "InputChangeTracker not in BUILD"

    # === Functional Checks ===

    def test_bazel_build_remote_package(self):
        """Remote package must build"""
        result = subprocess.run(
            ["bazel", "build",
             "//src/main/java/com/google/devtools/build/lib/remote:remote"],
            capture_output=True, text=True, cwd=self.REPO_DIR, timeout=600,
        )
        assert result.returncode == 0, (
            f"bazel build failed:\n{result.stdout}\n{result.stderr}"
        )

    def test_bazel_test_analyzer(self):
        """CacheHitAnalyzer tests must pass"""
        result = subprocess.run(
            ["bazel", "test",
             "//src/test/java/com/google/devtools/build/lib/remote:CacheHitAnalyzerTest"],
            capture_output=True, text=True, cwd=self.REPO_DIR, timeout=600,
        )
        assert result.returncode == 0, (
            f"Tests failed:\n{result.stdout}\n{result.stderr}"
        )

    def test_bazel_test_tracker(self):
        """InputChangeTracker tests must pass"""
        result = subprocess.run(
            ["bazel", "test",
             "//src/test/java/com/google/devtools/build/lib/remote:InputChangeTrackerTest"],
            capture_output=True, text=True, cwd=self.REPO_DIR, timeout=600,
        )
        assert result.returncode == 0, (
            f"Tests failed:\n{result.stdout}\n{result.stderr}"
        )
