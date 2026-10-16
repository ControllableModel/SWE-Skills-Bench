"""
Tests for the spark-optimization skill.
Validates a Partition-Aware Caching Advisor for Spark SQL that analyzes
query plans and detects performance anti-patterns.
"""

import os
import re
import ast

REPO_DIR = "/workspace/spark"
ADVISOR_DIR = os.path.join(REPO_DIR, "python", "pyspark", "sql", "advisor")


class TestSparkOptimization:
    """Tests for the Spark SQL Caching Advisor."""

    # ── file_path_check ──────────────────────────────────────────────

    def test_init_file_exists(self):
        """Package __init__.py must exist."""
        path = os.path.join(ADVISOR_DIR, "__init__.py")
        assert os.path.isfile(path), f"Missing {path}"

    def test_analyzer_file_exists(self):
        """Plan analyzer module must exist."""
        path = os.path.join(ADVISOR_DIR, "analyzer.py")
        assert os.path.isfile(path), f"Missing {path}"

    def test_rules_file_exists(self):
        """Anti-pattern rules module must exist."""
        path = os.path.join(ADVISOR_DIR, "rules.py")
        assert os.path.isfile(path), f"Missing {path}"

    def test_report_file_exists(self):
        """Report generator module must exist."""
        path = os.path.join(ADVISOR_DIR, "report.py")
        assert os.path.isfile(path), f"Missing {path}"

    def test_models_file_exists(self):
        """Data models module must exist."""
        path = os.path.join(ADVISOR_DIR, "models.py")
        assert os.path.isfile(path), f"Missing {path}"

    # ── semantic_check ───────────────────────────────────────────────

    def _read(self, filename):
        path = os.path.join(ADVISOR_DIR, filename)
        if not os.path.isfile(path):
            return ""
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def test_analyze_function_defined(self):
        """Public analyze() function must be defined."""
        init_content = self._read("__init__.py")
        analyzer_content = self._read("analyzer.py")
        combined = init_content + analyzer_content
        assert re.search(r"def\s+analyze\b", combined), (
            "analyze() function not defined"
        )

    def test_anti_pattern_rules_defined(self):
        """Rules for excessive_shuffles, redundant_computation, partition_mismatch must exist."""
        content = self._read("rules.py")
        for rule in ["excessive_shuffle", "redundant_computation", "partition_mismatch"]:
            assert re.search(rule, content, re.IGNORECASE), (
                f"Rule '{rule}' not found in rules.py"
            )

    def test_report_to_dict_and_to_text(self):
        """Report must have to_dict() and to_text() methods."""
        content = self._read("report.py") + self._read("models.py")
        assert re.search(r"def\s+to_dict\b", content), "to_dict method not defined"
        assert re.search(r"def\s+to_text\b", content), "to_text method not defined"

    def test_severity_levels(self):
        """Rules must use severity levels: low, medium, high."""
        content = self._read("rules.py") + self._read("models.py")
        for level in ["low", "medium", "high"]:
            assert level in content.lower(), f"Severity level '{level}' not found"

    def test_plan_node_types_recognized(self):
        """Analyzer must recognize Exchange, BroadcastHashJoin, SortMergeJoin nodes."""
        content = self._read("analyzer.py") + self._read("rules.py")
        for node in ["Exchange", "SortMergeJoin", "BroadcastHashJoin"]:
            assert node in content, f"Plan node type '{node}' not recognized"

    def test_invalid_rule_raises_valueerror(self):
        """analyze() with invalid rule name must raise ValueError."""
        content = self._read("analyzer.py")
        assert re.search(r"ValueError|Unknown rule|Available rules", content), (
            "ValueError for unknown rule names not found"
        )

    # ── functional_check ─────────────────────────────────────────────

    def test_all_files_valid_python(self):
        """All advisor Python files must have valid syntax."""
        errors = []
        for fname in ["__init__.py", "analyzer.py", "rules.py", "report.py", "models.py"]:
            content = self._read(fname)
            if not content:
                continue
            try:
                ast.parse(content)
            except SyntaxError as e:
                errors.append(f"{fname}: {e}")
        assert not errors, "Syntax errors:\n" + "\n".join(errors)

    def test_report_sorted_by_severity(self):
        """Recommendations must be sorted by severity (high first)."""
        content = self._read("report.py")
        assert re.search(r"sort|sorted|severity", content, re.IGNORECASE), (
            "Report sorting by severity not found"
        )

    def test_no_issues_empty_message(self):
        """Clean plan produces empty recommendations with summary message."""
        content = self._read("report.py") + self._read("analyzer.py")
        assert re.search(r"No optimization|no.*issue|empty|no.*detect", content, re.IGNORECASE), (
            "No-issues summary message not found"
        )

    def test_test_file_exists(self):
        """Test file for analyzer must exist."""
        test_path = os.path.join(ADVISOR_DIR, "tests", "test_analyzer.py")
        assert os.path.isfile(test_path), f"Missing {test_path}"
