"""
Tests for the analyze-ci skill.

Validates that a CI failure analysis engine was implemented for Sentry,
including GitHub Actions log parsing, failure classification, root cause
identification, and failure report generation.

Repo: sentry (https://github.com/getsentry/sentry)
"""

import ast
import os
import re
import subprocess
import sys

REPO_DIR = "/workspace/sentry"


class TestFilePathCheck:
    """Verify that all required files were created."""

    def test_ci_analyzer_exists(self):
        path = os.path.join(REPO_DIR, "src", "sentry", "utils", "ci_analyzer.py")
        assert os.path.isfile(path), f"Expected ci_analyzer.py at {path}"

    def test_ci_models_exists(self):
        path = os.path.join(REPO_DIR, "src", "sentry", "utils", "ci_models.py")
        assert os.path.isfile(path), f"Expected ci_models.py at {path}"

    def test_test_file_exists(self):
        path = os.path.join(REPO_DIR, "tests", "sentry", "utils", "test_ci_analyzer.py")
        assert os.path.isfile(path), f"Expected test_ci_analyzer.py at {path}"


class TestSemanticLogParser:
    """Verify CILogParser recognizes GitHub Actions log format."""

    def _read_analyzer(self):
        path = os.path.join(REPO_DIR, "src", "sentry", "utils", "ci_analyzer.py")
        with open(path, "r") as f:
            return f.read()

    def test_ci_log_parser_class(self):
        content = self._read_analyzer()
        assert re.search(r"class\s+CILogParser", content), (
            "Expected CILogParser class"
        )

    def test_group_marker_parsing(self):
        """Should recognize ::group:: and ::endgroup:: markers."""
        content = self._read_analyzer()
        assert "::group::" in content, (
            "Expected ::group:: marker parsing"
        )
        assert "::endgroup::" in content, (
            "Expected ::endgroup:: marker parsing"
        )

    def test_error_annotation_parsing(self):
        """Should recognize ::error:: and ::warning:: annotations."""
        content = self._read_analyzer()
        assert "::error::" in content, (
            "Expected ::error:: annotation parsing"
        )

    def test_step_extraction(self):
        content = self._read_analyzer()
        assert re.search(r"step|Step|job|Job", content), (
            "Expected step/job extraction from log structure"
        )


class TestSemanticFailureClassification:
    """Verify failure classification into categories."""

    def _read_analyzer(self):
        path = os.path.join(REPO_DIR, "src", "sentry", "utils", "ci_analyzer.py")
        with open(path, "r") as f:
            return f.read()

    def test_test_failure_category(self):
        content = self._read_analyzer()
        assert re.search(r"test_failure", content), (
            "Expected test_failure classification category"
        )

    def test_build_failure_category(self):
        content = self._read_analyzer()
        assert re.search(r"build_failure", content), (
            "Expected build_failure classification category"
        )

    def test_dependency_failure_category(self):
        content = self._read_analyzer()
        assert re.search(r"dependency_failure", content), (
            "Expected dependency_failure classification category"
        )

    def test_timeout_category(self):
        content = self._read_analyzer()
        assert re.search(r"timeout", content, re.IGNORECASE), (
            "Expected timeout classification category"
        )

    def test_infrastructure_category(self):
        content = self._read_analyzer()
        assert re.search(r"infrastructure", content), (
            "Expected infrastructure classification category"
        )

    def test_flaky_category(self):
        content = self._read_analyzer()
        assert re.search(r"flaky", content), (
            "Expected flaky test classification category"
        )

    def test_confidence_score(self):
        content = self._read_analyzer()
        assert re.search(r"confidence", content), (
            "Expected confidence score in failure classification"
        )

    def test_classification_patterns(self):
        """Should include error patterns for classification."""
        content = self._read_analyzer()
        patterns = [
            "ModuleNotFoundError", "ImportError", "npm ERR",
            "AssertionError", "AssertError", "FAILED",
        ]
        found = sum(1 for p in patterns if p in content)
        assert found >= 3, (
            f"Expected at least 3 error patterns for classification, found {found}"
        )


class TestSemanticRootCause:
    """Verify root cause identification."""

    def _read_all(self):
        content = ""
        for fname in ["ci_analyzer.py", "ci_models.py"]:
            path = os.path.join(REPO_DIR, "src", "sentry", "utils", fname)
            with open(path, "r") as f:
                content += f.read()
        return content

    def test_root_cause_class(self):
        content = self._read_all()
        assert re.search(r"class\s+RootCause|RootCause", content), (
            "Expected RootCause class or dataclass"
        )

    def test_log_excerpt_extraction(self):
        content = self._read_all()
        assert re.search(r"log_excerpt|excerpt|10.*lines|lines.*around", content, re.IGNORECASE), (
            "Expected log_excerpt (10 lines around error)"
        )

    def test_summary_field(self):
        content = self._read_all()
        assert re.search(r"summary", content), (
            "Expected summary field in RootCause"
        )


class TestSemanticFailureReport:
    """Verify failure report generation."""

    def _read_all(self):
        content = ""
        for fname in ["ci_analyzer.py", "ci_models.py"]:
            path = os.path.join(REPO_DIR, "src", "sentry", "utils", fname)
            with open(path, "r") as f:
                content += f.read()
        return content

    def test_generate_report_function(self):
        content = self._read_all()
        assert re.search(r"def\s+generate_report", content), (
            "Expected generate_report function"
        )

    def test_failure_report_class(self):
        content = self._read_all()
        assert re.search(r"class\s+FailureReport|FailureReport", content), (
            "Expected FailureReport class"
        )

    def test_suggested_actions(self):
        content = self._read_all()
        assert re.search(r"suggested_actions|suggest", content), (
            "Expected suggested_actions in failure report"
        )

    def test_previous_results_parameter(self):
        """Flaky detection requires previous_results."""
        content = self._read_all()
        assert re.search(r"previous_results", content), (
            "Expected previous_results parameter for flaky detection"
        )

    def test_workflow_name_tracked(self):
        content = self._read_all()
        assert re.search(r"workflow_name", content), (
            "Expected workflow_name in FailureReport"
        )


class TestFunctionalPythonSyntax:
    """Validate Python syntax of all created files."""

    def _check_syntax(self, filepath):
        with open(filepath, "r") as f:
            source = f.read()
        ast.parse(source)

    def test_ci_analyzer_syntax(self):
        self._check_syntax(
            os.path.join(REPO_DIR, "src", "sentry", "utils", "ci_analyzer.py")
        )

    def test_ci_models_syntax(self):
        self._check_syntax(
            os.path.join(REPO_DIR, "src", "sentry", "utils", "ci_models.py")
        )

    def test_test_file_syntax(self):
        self._check_syntax(
            os.path.join(REPO_DIR, "tests", "sentry", "utils", "test_ci_analyzer.py")
        )


class TestFunctionalAgentTests:
    """Verify the agent's own test coverage and correctness."""

    def _read_test(self):
        path = os.path.join(REPO_DIR, "tests", "sentry", "utils", "test_ci_analyzer.py")
        with open(path, "r") as f:
            return f.read()

    def test_sufficient_test_count(self):
        content = self._read_test()
        test_count = len(re.findall(r"def\s+test_", content))
        assert test_count >= 5, (
            f"Expected at least 5 test functions, found {test_count}"
        )

    def test_covers_multiple_failure_categories(self):
        content = self._read_test()
        categories = ["test_failure", "build_failure", "dependency_failure",
                       "timeout", "infrastructure", "flaky"]
        found = sum(1 for c in categories if c in content)
        assert found >= 3, (
            f"Expected tests covering at least 3 failure categories, found {found}"
        )

    def test_agent_tests_pass(self):
        result = subprocess.run(
            [sys.executable, "-m", "pytest",
             "tests/sentry/utils/test_ci_analyzer.py", "-v", "--tb=short"],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, (
            f"Agent's CI analyzer tests failed:\n{result.stdout[-1000:]}\n{result.stderr[-500:]}"
        )
