"""
Test skill: python-background-jobs
Verify that the Agent correctly implements a batch report export pipeline
with background workers using Celery.
"""

import os
import re
import ast
import subprocess
import pytest


class TestPythonBackgroundJobs:
    REPO_DIR = "/workspace/celery"

    # === File Path Checks ===

    def test_batch_export_module_exists(self):
        """Verify celery/app/batch_export.py was created"""
        path = os.path.join(self.REPO_DIR, "celery/app/batch_export.py")
        assert os.path.exists(path), f"batch_export.py not found at {path}"

    def test_job_store_module_exists(self):
        """Verify celery/app/job_store.py was created"""
        path = os.path.join(self.REPO_DIR, "celery/app/job_store.py")
        assert os.path.exists(path), f"job_store.py not found at {path}"

    def test_unit_test_file_exists(self):
        """Verify t/unit/app/test_batch_export.py was created"""
        path = os.path.join(self.REPO_DIR, "t/unit/app/test_batch_export.py")
        assert os.path.exists(path), f"test_batch_export.py not found at {path}"

    # === Semantic Checks: Task Definitions ===

    def test_generate_report_task_defined(self):
        """Verify generate_report task is defined with @app.task(bind=True)"""
        path = os.path.join(self.REPO_DIR, "celery/app/batch_export.py")
        with open(path) as f:
            content = f.read()
        assert "generate_report" in content, (
            "generate_report task should be defined"
        )
        assert "bind=True" in content, (
            "generate_report should use bind=True decorator"
        )

    def test_task_has_max_retries(self):
        """Verify generate_report has max_retries=3"""
        path = os.path.join(self.REPO_DIR, "celery/app/batch_export.py")
        with open(path) as f:
            content = f.read()
        assert "max_retries" in content, "Task should configure max_retries"
        assert "3" in content, "max_retries should be 3"

    def test_task_has_time_limits(self):
        """Verify task_time_limit=300 and task_soft_time_limit=240"""
        path = os.path.join(self.REPO_DIR, "celery/app/batch_export.py")
        with open(path) as f:
            content = f.read()
        assert "task_time_limit" in content or "time_limit" in content, (
            "Task should configure time limits"
        )
        assert "300" in content, "task_time_limit should be 300"
        assert "240" in content, "task_soft_time_limit should be 240"

    def test_task_acks_late(self):
        """Verify task_acks_late=True"""
        path = os.path.join(self.REPO_DIR, "celery/app/batch_export.py")
        with open(path) as f:
            content = f.read()
        assert "acks_late" in content, "Task should configure acks_late=True"

    def test_soft_time_limit_handling(self):
        """Verify SoftTimeLimitExceeded is caught and marks job as FAILED"""
        path = os.path.join(self.REPO_DIR, "celery/app/batch_export.py")
        with open(path) as f:
            content = f.read()
        assert "SoftTimeLimitExceeded" in content, (
            "Task should handle SoftTimeLimitExceeded"
        )
        assert "240" in content, (
            "Timeout message should reference 240s limit"
        )

    def test_connection_error_retry_with_backoff(self):
        """Verify ConnectionError triggers retry with exponential backoff"""
        path = os.path.join(self.REPO_DIR, "celery/app/batch_export.py")
        with open(path) as f:
            content = f.read()
        assert "ConnectionError" in content, "Should handle ConnectionError"
        assert "retry" in content, "Should call self.retry for transient errors"
        # Check for exponential backoff formula
        assert "2 **" in content or "2**" in content, (
            "Backoff should be exponential: 2 ** retries * 30"
        )

    def test_value_error_no_retry(self):
        """Verify ValueError causes immediate failure without retry"""
        path = os.path.join(self.REPO_DIR, "celery/app/batch_export.py")
        with open(path) as f:
            content = f.read()
        assert "ValueError" in content, "Should handle ValueError"

    def test_cleanup_expired_jobs_task(self):
        """Verify cleanup_expired_jobs task is defined"""
        path = os.path.join(self.REPO_DIR, "celery/app/batch_export.py")
        with open(path) as f:
            content = f.read()
        assert "cleanup_expired_jobs" in content, (
            "cleanup_expired_jobs task should be defined"
        )

    def test_run_export_pipeline_chain(self):
        """Verify run_export_pipeline task chain is defined with 3 subtasks"""
        path = os.path.join(self.REPO_DIR, "celery/app/batch_export.py")
        with open(path) as f:
            content = f.read()
        assert "run_export_pipeline" in content, (
            "run_export_pipeline should be defined"
        )
        for subtask in ["extract_data", "transform_data", "upload_result"]:
            assert subtask in content, (
                f"Pipeline chain should include {subtask} subtask"
            )

    # === Semantic Checks: Job Store ===

    def test_job_store_class_defined(self):
        """Verify JobStore class is defined"""
        path = os.path.join(self.REPO_DIR, "celery/app/job_store.py")
        with open(path) as f:
            content = f.read()
        assert "class JobStore" in content, "JobStore class should be defined"

    def test_job_dataclass_defined(self):
        """Verify Job dataclass is defined with required fields"""
        path = os.path.join(self.REPO_DIR, "celery/app/job_store.py")
        with open(path) as f:
            content = f.read()
        assert "dataclass" in content or "Job" in content, (
            "Job dataclass should be defined"
        )
        for field in ["status", "params", "created_at", "result", "error", "attempts"]:
            assert field in content, f"Job should have '{field}' field"

    def test_job_store_create_method(self):
        """Verify JobStore.create method exists"""
        path = os.path.join(self.REPO_DIR, "celery/app/job_store.py")
        with open(path) as f:
            content = f.read()
        assert "def create(" in content, "JobStore should have create method"

    def test_job_store_get_method(self):
        """Verify JobStore.get method exists"""
        path = os.path.join(self.REPO_DIR, "celery/app/job_store.py")
        with open(path) as f:
            content = f.read()
        assert "def get(" in content, "JobStore should have get method"

    def test_job_store_update_status_method(self):
        """Verify JobStore.update_status method exists"""
        path = os.path.join(self.REPO_DIR, "celery/app/job_store.py")
        with open(path) as f:
            content = f.read()
        assert "def update_status(" in content, (
            "JobStore should have update_status method"
        )

    def test_job_store_invalid_transition_error(self):
        """Verify InvalidTransitionError is raised for invalid state transitions"""
        path = os.path.join(self.REPO_DIR, "celery/app/job_store.py")
        with open(path) as f:
            content = f.read()
        assert "InvalidTransitionError" in content, (
            "Should define/raise InvalidTransitionError"
        )

    def test_job_store_duplicate_job_error(self):
        """Verify DuplicateJobError is raised for duplicate job IDs"""
        path = os.path.join(self.REPO_DIR, "celery/app/job_store.py")
        with open(path) as f:
            content = f.read()
        assert "DuplicateJobError" in content, (
            "Should define/raise DuplicateJobError"
        )

    def test_job_store_auto_timestamps(self):
        """Verify update_status auto-sets started_at and completed_at"""
        path = os.path.join(self.REPO_DIR, "celery/app/job_store.py")
        with open(path) as f:
            content = f.read()
        assert "started_at" in content, "Should auto-set started_at on RUNNING"
        assert "completed_at" in content, (
            "Should auto-set completed_at on SUCCEEDED/FAILED"
        )

    def test_job_store_delete_expired(self):
        """Verify delete_expired method exists"""
        path = os.path.join(self.REPO_DIR, "celery/app/job_store.py")
        with open(path) as f:
            content = f.read()
        assert "delete_expired" in content, (
            "JobStore should have delete_expired method"
        )

    # === Semantic Checks: Idempotency ===

    def test_idempotent_reexecution(self):
        """Verify generate_report checks for already-succeeded jobs"""
        path = os.path.join(self.REPO_DIR, "celery/app/batch_export.py")
        with open(path) as f:
            content = f.read()
        assert "SUCCEEDED" in content, (
            "Task should check if job is already SUCCEEDED"
        )

    def test_idempotency_key_for_upload(self):
        """Verify upload_result uses idempotency key from job_id"""
        path = os.path.join(self.REPO_DIR, "celery/app/batch_export.py")
        with open(path) as f:
            content = f.read()
        assert "idempotency" in content.lower() or "idempotent" in content.lower(), (
            "upload_result should include idempotency key mechanism"
        )

    # === Semantic Checks: Dead Letter Handling ===

    def test_dead_letter_after_retries(self):
        """Verify dead letter record is written after exhausting retries"""
        path = os.path.join(self.REPO_DIR, "celery/app/batch_export.py")
        with open(path) as f:
            content = f.read()
        assert "dead_letter" in content or "dead-letter" in content, (
            "Should write to dead_letter list after retry exhaustion"
        )

    def test_dead_letter_retrievable(self):
        """Verify dead letters are retrievable via JobStore"""
        path = os.path.join(self.REPO_DIR, "celery/app/job_store.py")
        with open(path) as f:
            content = f.read()
        assert "dead_letter" in content or "get_dead_letters" in content, (
            "JobStore should provide dead letter retrieval"
        )

    # === Functional Checks ===

    def test_batch_export_parses(self):
        """Verify batch_export.py has valid Python syntax"""
        path = os.path.join(self.REPO_DIR, "celery/app/batch_export.py")
        with open(path) as f:
            source = f.read()
        try:
            ast.parse(source)
        except SyntaxError as e:
            pytest.fail(f"batch_export.py has syntax error: {e}")

    def test_job_store_parses(self):
        """Verify job_store.py has valid Python syntax"""
        path = os.path.join(self.REPO_DIR, "celery/app/job_store.py")
        with open(path) as f:
            source = f.read()
        try:
            ast.parse(source)
        except SyntaxError as e:
            pytest.fail(f"job_store.py has syntax error: {e}")

    def test_unit_tests_pass(self):
        """Verify unit tests pass"""
        result = subprocess.run(
            [
                "python", "-m", "pytest",
                "t/unit/app/test_batch_export.py",
                "-v", "--tb=short",
            ],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, (
            f"Unit tests failed:\n{result.stdout}\n{result.stderr}"
        )
