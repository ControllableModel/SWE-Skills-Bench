"""
Test skill: python-background-jobs
Verify that the Agent correctly implements a Celery multi-step order
processing pipeline with task chaining, idempotency, error callbacks,
state tracking, and proper Celery configuration.
"""

import os
import re
import ast
import subprocess
import pytest


class TestPythonBackgroundJobs:
    REPO_DIR = "/workspace/celery"

    # === File Path Checks ===

    def test_tasks_file_exists(self):
        """Verify order pipeline tasks file exists"""
        path = os.path.join(self.REPO_DIR, "examples/order_pipeline/tasks.py")
        assert os.path.exists(path), f"tasks.py not found at {path}"

    def test_models_file_exists(self):
        """Verify order pipeline models file exists"""
        path = os.path.join(self.REPO_DIR, "examples/order_pipeline/models.py")
        assert os.path.exists(path), f"models.py not found at {path}"

    def test_pipeline_file_exists(self):
        """Verify pipeline orchestrator file exists"""
        path = os.path.join(self.REPO_DIR, "examples/order_pipeline/pipeline.py")
        assert os.path.exists(path), f"pipeline.py not found at {path}"

    def test_config_file_exists(self):
        """Verify Celery config file exists"""
        path = os.path.join(self.REPO_DIR, "examples/order_pipeline/config.py")
        assert os.path.exists(path), f"config.py not found at {path}"

    def test_test_file_exists(self):
        """Verify test file exists"""
        path = os.path.join(self.REPO_DIR, "tests/test_order_pipeline.py")
        assert os.path.exists(path), f"test_order_pipeline.py not found"

    # === Semantic Checks ===

    def test_order_status_enum_defined(self):
        """Verify OrderStatus enum has all required states"""
        path = os.path.join(self.REPO_DIR, "examples/order_pipeline/models.py")
        with open(path, "r") as f:
            content = f.read()

        assert "OrderStatus" in content, "Must define OrderStatus enum"
        expected_states = [
            "PENDING", "VALIDATING", "PAYMENT_PROCESSING",
            "RESERVING_INVENTORY", "SENDING_NOTIFICATION",
            "COMPLETED", "FAILED"
        ]
        for state in expected_states:
            assert state in content, f"OrderStatus missing state: {state}"

    def test_four_task_functions_defined(self):
        """Verify all four pipeline tasks are defined"""
        path = os.path.join(self.REPO_DIR, "examples/order_pipeline/tasks.py")
        with open(path, "r") as f:
            content = f.read()

        expected_tasks = [
            "validate_order", "process_payment",
            "reserve_inventory", "send_notification"
        ]
        for task in expected_tasks:
            assert re.search(rf"def\s+{task}", content), (
                f"Missing task function: {task}"
            )

    def test_process_payment_has_retry_config(self):
        """Verify process_payment has autoretry_for, max_retries, exponential backoff"""
        path = os.path.join(self.REPO_DIR, "examples/order_pipeline/tasks.py")
        with open(path, "r") as f:
            content = f.read()

        assert "autoretry_for" in content or "retry" in content, (
            "process_payment should configure auto-retry for transient errors"
        )
        assert "max_retries" in content, (
            "process_payment should set max_retries"
        )
        assert "backoff" in content.lower() or "countdown" in content, (
            "process_payment should use exponential backoff"
        )

    def test_process_payment_has_idempotency_key(self):
        """Verify process_payment uses an idempotency key"""
        path = os.path.join(self.REPO_DIR, "examples/order_pipeline/tasks.py")
        with open(path, "r") as f:
            content = f.read()

        assert "idempotency" in content.lower() or "payment-" in content, (
            "process_payment should use idempotency key (e.g. payment-{order_id})"
        )

    def test_reserve_inventory_is_idempotent(self):
        """Verify reserve_inventory handles already-reserved orders"""
        path = os.path.join(self.REPO_DIR, "examples/order_pipeline/tasks.py")
        with open(path, "r") as f:
            content = f.read()

        # Find reserve_inventory function
        func_match = re.search(
            r"def\s+reserve_inventory.*?\n((?:[ \t]+.*\n)*)",
            content
        )
        assert func_match, "reserve_inventory function not found"
        body = func_match.group(1)

        has_idempotent = (
            "already" in body.lower()
            or "reserved" in body.lower()
            or "RESERVING_INVENTORY" in body
        )
        assert has_idempotent, (
            "reserve_inventory should be idempotent (check if already reserved)"
        )

    def test_send_notification_does_not_fail_order(self):
        """Verify send_notification failure doesn't prevent COMPLETED status"""
        path = os.path.join(self.REPO_DIR, "examples/order_pipeline/tasks.py")
        with open(path, "r") as f:
            content = f.read()

        # Find send_notification function
        func_match = re.search(
            r"def\s+send_notification.*?\n((?:[ \t]+.*\n)*)",
            content
        )
        assert func_match, "send_notification function not found"
        body = func_match.group(1)

        has_error_handling = (
            "except" in body
            or "try" in body
            or "warning" in body.lower()
            or "COMPLETED" in body
        )
        assert has_error_handling, (
            "send_notification should handle errors gracefully and still complete"
        )

    def test_pipeline_uses_chain(self):
        """Verify pipeline orchestrator uses Celery chain()"""
        path = os.path.join(self.REPO_DIR, "examples/order_pipeline/pipeline.py")
        with open(path, "r") as f:
            content = f.read()

        assert "chain" in content, "Pipeline should use Celery chain() primitive"

    def test_submit_order_function_defined(self):
        """Verify submit_order function is defined and returns order_id"""
        path = os.path.join(self.REPO_DIR, "examples/order_pipeline/pipeline.py")
        with open(path, "r") as f:
            content = f.read()

        assert re.search(r"def\s+submit_order", content), (
            "pipeline.py must define submit_order function"
        )
        assert "order_id" in content, (
            "submit_order should return an order_id"
        )

    def test_error_callback_defined(self):
        """Verify handle_pipeline_error callback is defined"""
        path = os.path.join(self.REPO_DIR, "examples/order_pipeline/pipeline.py")
        with open(path, "r") as f:
            content = f.read()

        tasks_path = os.path.join(self.REPO_DIR, "examples/order_pipeline/tasks.py")
        with open(tasks_path, "r") as f:
            tasks_content = f.read()

        combined = content + tasks_content
        assert "handle_pipeline_error" in combined or "on_error" in combined, (
            "Must define an error callback (handle_pipeline_error or on_error)"
        )

    def test_get_order_status_function_defined(self):
        """Verify get_order_status function is defined"""
        path = os.path.join(self.REPO_DIR, "examples/order_pipeline/pipeline.py")
        with open(path, "r") as f:
            content = f.read()

        assert re.search(r"def\s+get_order_status", content), (
            "pipeline.py must define get_order_status function"
        )

    def test_celery_config_settings(self):
        """Verify Celery configuration has required settings"""
        path = os.path.join(self.REPO_DIR, "examples/order_pipeline/config.py")
        with open(path, "r") as f:
            content = f.read()

        assert "json" in content, "Task serializer should be 'json'"
        assert "task_acks_late" in content, "Must set task_acks_late"
        assert "task_reject_on_worker_lost" in content, "Must set task_reject_on_worker_lost"
        assert "worker_prefetch_multiplier" in content, "Must set worker_prefetch_multiplier"
        assert "task_time_limit" in content, "Must set task_time_limit"
        assert "task_soft_time_limit" in content, "Must set task_soft_time_limit"

    def test_celery_config_values(self):
        """Verify Celery configuration values are correct"""
        path = os.path.join(self.REPO_DIR, "examples/order_pipeline/config.py")
        with open(path, "r") as f:
            content = f.read()

        # Check specific values
        assert "300" in content, "task_time_limit should be 300 seconds"
        assert "240" in content, "task_soft_time_limit should be 240 seconds"
        assert re.search(r"worker_prefetch_multiplier.*=.*1\b", content), (
            "worker_prefetch_multiplier should be 1"
        )

    # === Functional Checks ===

    def test_all_python_files_parse(self):
        """Verify all pipeline Python files parse without syntax errors"""
        files = [
            "examples/order_pipeline/tasks.py",
            "examples/order_pipeline/models.py",
            "examples/order_pipeline/pipeline.py",
            "examples/order_pipeline/config.py",
        ]
        for filename in files:
            path = os.path.join(self.REPO_DIR, filename)
            with open(path, "r") as f:
                source = f.read()
            try:
                ast.parse(source)
            except SyntaxError as e:
                pytest.fail(f"{filename} has syntax error: {e}")

    def test_models_import(self):
        """Verify models can be imported"""
        result = subprocess.run(
            ["python", "-c",
             "import sys; sys.path.insert(0, 'examples'); "
             "from order_pipeline.models import OrderStatus; "
             "print(list(OrderStatus))"],
            capture_output=True, text=True, timeout=30,
            cwd=self.REPO_DIR,
        )
        assert result.returncode == 0, (
            f"Failed to import models:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )

    def test_validate_order_rejects_empty_items(self):
        """Verify validate_order rejects orders with empty items list"""
        path = os.path.join(self.REPO_DIR, "examples/order_pipeline/tasks.py")
        with open(path, "r") as f:
            content = f.read()

        # Check for validation logic
        assert "items" in content, "validate_order should check items"
        has_empty_check = (
            "not items" in content
            or "len(items)" in content
            or "empty" in content.lower()
            or "at least one" in content.lower()
        )
        assert has_empty_check, (
            "validate_order should reject empty items list"
        )

    def test_validate_order_checks_total_amount(self):
        """Verify validate_order validates total_amount matches sum"""
        path = os.path.join(self.REPO_DIR, "examples/order_pipeline/tasks.py")
        with open(path, "r") as f:
            content = f.read()

        has_total_check = (
            "total_amount" in content
            and ("mismatch" in content.lower() or "sum" in content.lower() or "!=" in content)
        )
        assert has_total_check, (
            "validate_order should check total_amount matches sum of items"
        )
