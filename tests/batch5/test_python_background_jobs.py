"""
Test skill: python-background-jobs
Verify that the Agent correctly implements an idempotent data export task
with state management in the Celery examples directory.
"""

import os
import re
import ast
import sys
import subprocess
import pytest


class TestPythonBackgroundJobs:
    REPO_DIR = "/workspace/celery"

    TASKS = "examples/data_export/tasks.py"
    MODELS = "examples/data_export/models.py"
    CONFIG = "examples/data_export/celeryconfig.py"
    API = "examples/data_export/api.py"
    TESTS = "examples/data_export/tests/test_tasks.py"

    def _read_file(self, rel_path):
        filepath = os.path.join(self.REPO_DIR, rel_path)
        with open(filepath) as f:
            return f.read()

    # === File Path Checks ===

    def test_tasks_file_exists(self):
        """Verify tasks.py exists in examples/data_export"""
        filepath = os.path.join(self.REPO_DIR, self.TASKS)
        assert os.path.exists(filepath), f"tasks.py not found at {filepath}"

    def test_models_file_exists(self):
        """Verify models.py exists"""
        filepath = os.path.join(self.REPO_DIR, self.MODELS)
        assert os.path.exists(filepath), f"models.py not found at {filepath}"

    def test_config_file_exists(self):
        """Verify celeryconfig.py exists"""
        filepath = os.path.join(self.REPO_DIR, self.CONFIG)
        assert os.path.exists(filepath), f"celeryconfig.py not found at {filepath}"

    def test_api_file_exists(self):
        """Verify api.py exists"""
        filepath = os.path.join(self.REPO_DIR, self.API)
        assert os.path.exists(filepath), f"api.py not found at {filepath}"

    def test_tests_file_exists(self):
        """Verify tests/test_tasks.py exists"""
        filepath = os.path.join(self.REPO_DIR, self.TESTS)
        assert os.path.exists(filepath), f"Test file not found at {filepath}"

    # === Semantic Checks ===

    def test_task_defines_state_machine(self):
        """Verify tasks.py defines states: PENDING, PROCESSING, COMPLETED, FAILED"""
        content = self._read_file(self.TASKS)
        for state in ["PENDING", "PROCESSING", "COMPLETED", "FAILED"]:
            assert state in content, \
                f"tasks.py missing state: {state}"

    def test_task_has_idempotency_key(self):
        """Verify task supports idempotency_key for duplicate detection"""
        content = self._read_file(self.TASKS)
        assert "idempotency_key" in content or "idempotency" in content, \
            "tasks.py missing idempotency_key support"

    def test_task_has_retry_configuration(self):
        """Verify task has retry with exponential backoff configuration"""
        content = self._read_file(self.TASKS)
        has_retry = bool(re.search(
            r'(max_retries|retry|autoretry_for|bind=True)',
            content,
        ))
        assert has_retry, "tasks.py missing retry configuration"
        has_backoff = bool(re.search(
            r'(retry_backoff|exponential|countdown|backoff)',
            content,
            re.IGNORECASE,
        ))
        assert has_backoff, "tasks.py missing exponential backoff for retries"

    def test_task_retries_on_ioerror(self):
        """Verify task retries on IOError and ConnectionError"""
        content = self._read_file(self.TASKS)
        has_ioerror = "IOError" in content or "OSError" in content
        has_connection = "ConnectionError" in content
        assert has_ioerror or has_connection, \
            "tasks.py should retry on IOError/ConnectionError"

    def test_model_tracks_job_fields(self):
        """Verify ExportJob model has required fields"""
        content = self._read_file(self.MODELS)
        assert "ExportJob" in content, "models.py missing ExportJob class"
        for field in ["status", "progress", "result_url", "error"]:
            assert field in content, \
                f"ExportJob missing field: {field}"

    def test_api_defines_endpoints(self):
        """Verify API has POST /exports, GET /exports/{id}, DELETE /exports/{id}"""
        content = self._read_file(self.API)
        assert "POST" in content or "post" in content.lower(), \
            "API missing POST endpoint"
        assert "GET" in content or "get" in content.lower(), \
            "API missing GET endpoint"
        assert "DELETE" in content or "delete" in content.lower(), \
            "API missing DELETE endpoint"

    def test_api_handles_cancellation(self):
        """Verify API handles DELETE for cancellation with conflict on completed jobs"""
        content = self._read_file(self.API)
        has_cancel = "CANCEL" in content.upper() or "cancel" in content
        assert has_cancel, "API missing cancellation handling"
        has_conflict = bool(re.search(r'(409|Conflict|already.*(completed|failed))', content, re.IGNORECASE))
        assert has_conflict, "API missing 409 Conflict for cancelling completed/failed jobs"

    def test_celeryconfig_has_required_settings(self):
        """Verify celeryconfig.py has broker, backend, and serialization settings"""
        content = self._read_file(self.CONFIG)
        assert "broker" in content.lower(), \
            "celeryconfig.py missing broker URL setting"
        assert "result_backend" in content.lower() or "backend" in content.lower(), \
            "celeryconfig.py missing result backend setting"

    # === Functional Checks ===

    def test_all_files_valid_python(self):
        """Verify all Python source files have valid syntax"""
        for path in [self.TASKS, self.MODELS, self.CONFIG, self.API]:
            filepath = os.path.join(self.REPO_DIR, path)
            with open(filepath) as f:
                try:
                    ast.parse(f.read())
                except SyntaxError as e:
                    pytest.fail(f"{path} has syntax error: {e}")

    def test_task_defines_progress_reporting(self):
        """Verify task reports progress during execution"""
        content = self._read_file(self.TASKS)
        has_progress = bool(re.search(
            r'(update_state|progress|update_progress|percentage|percent)',
            content,
            re.IGNORECASE,
        ))
        assert has_progress, "tasks.py missing progress reporting mechanism"

    def test_tests_cover_key_scenarios(self):
        """Verify test file covers happy path, idempotency, retry, and cancellation"""
        content = self._read_file(self.TESTS)
        test_tree = ast.parse(content)
        test_funcs = [
            node.name for node in ast.walk(test_tree)
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
        ]
        assert len(test_funcs) >= 5, \
            f"Expected at least 5 test functions, found {len(test_funcs)}: {test_funcs}"
        content_lower = content.lower()
        assert "idempoten" in content_lower, "Tests missing idempotency coverage"
        assert "retry" in content_lower or "fail" in content_lower, \
            "Tests missing retry/failure coverage"
