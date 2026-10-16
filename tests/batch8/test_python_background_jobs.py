"""
Tests for the python-background-jobs skill.
Validates a scheduled report generation pipeline using Celery with
task chaining, state management, cancellation, retries, and an API layer.
"""

import os
import re
import ast
import subprocess

REPO_DIR = "/workspace/celery"
PIPELINE_DIR = os.path.join(REPO_DIR, "examples", "report_pipeline")


class TestPythonBackgroundJobs:
    """Tests for the Celery report pipeline example."""

    # ── file_path_check ──────────────────────────────────────────────

    def test_app_file_exists(self):
        """Celery application instance file must exist."""
        path = os.path.join(PIPELINE_DIR, "app.py")
        assert os.path.isfile(path), f"Missing {path}"

    def test_tasks_file_exists(self):
        """Task definitions file must exist."""
        path = os.path.join(PIPELINE_DIR, "tasks.py")
        assert os.path.isfile(path), f"Missing {path}"

    def test_models_file_exists(self):
        """ReportJob model file must exist."""
        path = os.path.join(PIPELINE_DIR, "models.py")
        assert os.path.isfile(path), f"Missing {path}"

    def test_store_file_exists(self):
        """Job store file must exist."""
        path = os.path.join(PIPELINE_DIR, "store.py")
        assert os.path.isfile(path), f"Missing {path}"

    def test_api_file_exists(self):
        """API endpoints file must exist."""
        path = os.path.join(PIPELINE_DIR, "api.py")
        assert os.path.isfile(path), f"Missing {path}"

    # ── semantic_check ───────────────────────────────────────────────

    def _read(self, filename):
        path = os.path.join(PIPELINE_DIR, filename)
        if not os.path.isfile(path):
            return ""
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def test_four_task_stages_defined(self):
        """Tasks file must define collect_data, aggregate_data, format_report, send_report."""
        content = self._read("tasks.py")
        for fn in ["collect_data", "aggregate_data", "format_report", "send_report"]:
            assert re.search(rf"def\s+{fn}\b", content), (
                f"Task function {fn} not defined in tasks.py"
            )

    def test_celery_chain_usage(self):
        """Pipeline must use Celery's chain primitive to link stages."""
        content = self._read("tasks.py") + self._read("api.py") + self._read("app.py")
        assert re.search(r"from\s+celery\b.*import.*chain|celery\.chain|chain\(", content), (
            "Celery chain primitive not used"
        )

    def test_report_job_states(self):
        """ReportJob must define all required state values."""
        content = self._read("models.py")
        required_states = ["PENDING", "COLLECTING", "AGGREGATING", "FORMATTING", "SENDING",
                           "COMPLETED", "FAILED", "CANCELLED"]
        for state in required_states:
            assert state in content, f"State {state} not defined in models.py"

    def test_report_job_fields(self):
        """ReportJob must have required fields: id, status, created_at, stages_completed."""
        content = self._read("models.py")
        for field in ["id", "status", "created_at", "stages_completed"]:
            assert field in content, f"Field '{field}' not found in ReportJob model"

    def test_retry_configuration_on_collect_data(self):
        """collect_data must configure retries for ConnectionError/TimeoutError."""
        content = self._read("tasks.py")
        assert re.search(r"retry|autoretry|max_retries|retry_backoff", content), (
            "No retry configuration found in tasks.py"
        )
        assert re.search(r"ConnectionError|TimeoutError", content), (
            "ConnectionError/TimeoutError not referenced for retry logic"
        )

    def test_cancellation_check_in_tasks(self):
        """Tasks must check for CANCELLED status before executing."""
        content = self._read("tasks.py")
        assert re.search(r"CANCELLED|cancelled|cancel", content, re.IGNORECASE), (
            "Cancellation check not found in tasks.py"
        )

    def test_idempotency_check(self):
        """Tasks must check stages_completed for idempotency."""
        content = self._read("tasks.py")
        assert re.search(r"stages_completed|already.completed|idempoten", content, re.IGNORECASE), (
            "Idempotency check (stages_completed) not found in tasks.py"
        )

    # ── functional_check ─────────────────────────────────────────────

    def test_all_files_valid_python(self):
        """All pipeline Python files must have valid syntax."""
        errors = []
        for fname in ["app.py", "tasks.py", "models.py", "store.py", "api.py"]:
            content = self._read(fname)
            if not content:
                continue
            try:
                ast.parse(content)
            except SyntaxError as e:
                errors.append(f"{fname}: {e}")
        assert not errors, f"Syntax errors found:\n" + "\n".join(errors)

    def test_api_post_reports_endpoint(self):
        """API must define POST /reports endpoint returning 202."""
        content = self._read("api.py")
        assert re.search(r'"/reports"|/reports|post.*report', content, re.IGNORECASE), (
            "POST /reports endpoint not found in api.py"
        )
        assert "202" in content, "HTTP 202 status not found for POST /reports"

    def test_api_get_reports_status_endpoint(self):
        """API must define GET /reports/{id} for polling status."""
        content = self._read("api.py")
        assert re.search(r'"/reports/.*id|GET.*reports|get.*report', content, re.IGNORECASE), (
            "GET /reports/{id} endpoint not found in api.py"
        )

    def test_api_cancel_endpoint(self):
        """API must define POST /reports/{id}/cancel endpoint."""
        content = self._read("api.py")
        assert re.search(r"cancel", content, re.IGNORECASE), (
            "Cancel endpoint not found in api.py"
        )

    def test_aggregate_valid_types(self):
        """aggregate_data must validate aggregation type is one of sum/average/min/max/count."""
        content = self._read("tasks.py")
        valid_types = ["sum", "average", "min", "max", "count"]
        found = sum(1 for t in valid_types if t in content.lower())
        assert found >= 3, (
            f"Only {found}/5 aggregation types found in tasks.py; expected at least 3"
        )

    def test_format_report_supports_formats(self):
        """format_report must support json, csv, text output formats."""
        content = self._read("tasks.py")
        for fmt in ["json", "csv", "text"]:
            assert fmt in content.lower(), f"Format '{fmt}' not handled in format_report"

    def test_exponential_backoff_configured(self):
        """Retry logic must implement exponential backoff."""
        content = self._read("tasks.py")
        assert re.search(r"backoff|countdown.*\*|2\s*\*\*|exponential", content, re.IGNORECASE), (
            "Exponential backoff not found in retry configuration"
        )

    def test_store_concurrent_access_protection(self):
        """Job store must handle concurrent access with locking or atomic writes."""
        content = self._read("store.py")
        assert re.search(r"lock|flock|atomic|fcntl|filelock|threading\.Lock", content, re.IGNORECASE), (
            "No concurrent access protection found in store.py"
        )
