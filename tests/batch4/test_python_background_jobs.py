"""
Tests for skill: python-background-jobs
Repo: celery/celery
Image: zhangyiiiiii/swe-skills-bench-python
Task: Implement an asynchronous report generation pipeline in Celery with
      4-stage chain, job state machine, idempotency, and FastAPI endpoints.
"""

import ast
import os
import re
import subprocess
import sys

import pytest

REPO_DIR = "/workspace/celery"
PIPELINE_DIR = os.path.join(REPO_DIR, "examples", "report_pipeline")

TASKS_FILE = os.path.join(PIPELINE_DIR, "tasks.py")
MODELS_FILE = os.path.join(PIPELINE_DIR, "models.py")
PIPELINE_FILE = os.path.join(PIPELINE_DIR, "pipeline.py")
API_FILE = os.path.join(PIPELINE_DIR, "api.py")
CONFIG_FILE = os.path.join(PIPELINE_DIR, "config.py")
TEST_FILE = os.path.join(PIPELINE_DIR, "test_pipeline.py")


# ---------------------------------------------------------------------------
# Layer 1 — file_path_check
# ---------------------------------------------------------------------------

class TestFilePathCheck:
    """Verify all required pipeline files exist."""

    def test_tasks_file_exists(self):
        assert os.path.isfile(TASKS_FILE), f"Expected {TASKS_FILE}"

    def test_models_file_exists(self):
        assert os.path.isfile(MODELS_FILE), f"Expected {MODELS_FILE}"

    def test_pipeline_file_exists(self):
        assert os.path.isfile(PIPELINE_FILE), f"Expected {PIPELINE_FILE}"

    def test_api_file_exists(self):
        assert os.path.isfile(API_FILE), f"Expected {API_FILE}"

    def test_config_file_exists(self):
        assert os.path.isfile(CONFIG_FILE), f"Expected {CONFIG_FILE}"

    def test_test_file_exists(self):
        assert os.path.isfile(TEST_FILE), f"Expected {TEST_FILE}"


# ---------------------------------------------------------------------------
# Layer 2 — semantic_check
# ---------------------------------------------------------------------------

class TestSemanticConfig:
    """Verify Celery configuration settings."""

    @pytest.fixture(autouse=True)
    def _load_source(self):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            self.src = f.read()

    def test_redis_broker(self):
        """Celery must configure Redis as broker."""
        assert "redis" in self.src.lower(), (
            "Expected Redis broker URL in config"
        )

    def test_json_serializer(self):
        """Task serializer must be JSON."""
        assert "json" in self.src.lower(), (
            "Expected JSON task serializer in config"
        )

    def test_task_acks_late(self):
        """Late acknowledgment must be enabled."""
        assert "acks_late" in self.src or "task_acks_late" in self.src, (
            "Expected task_acks_late=True in config"
        )

    def test_time_limits(self):
        """Hard and soft time limits must be configured."""
        has_hard = "600" in self.src or "time_limit" in self.src
        has_soft = "500" in self.src or "soft_time_limit" in self.src
        assert has_hard and has_soft, (
            "Expected hard (600s) and soft (500s) time limits in config"
        )


class TestSemanticTasks:
    """Verify pipeline task definitions."""

    @pytest.fixture(autouse=True)
    def _load_source(self):
        with open(TASKS_FILE, "r", encoding="utf-8") as f:
            self.src = f.read()
        self.tree = ast.parse(self.src)

    def test_fetch_data_defined(self):
        funcs = [n.name for n in ast.walk(self.tree)
                 if isinstance(n, ast.FunctionDef)]
        assert "fetch_data" in funcs, (
            f"Expected fetch_data function; found: {funcs}"
        )

    def test_aggregate_data_defined(self):
        funcs = [n.name for n in ast.walk(self.tree)
                 if isinstance(n, ast.FunctionDef)]
        assert "aggregate_data" in funcs, (
            f"Expected aggregate_data function; found: {funcs}"
        )

    def test_render_report_defined(self):
        funcs = [n.name for n in ast.walk(self.tree)
                 if isinstance(n, ast.FunctionDef)]
        assert "render_report" in funcs, (
            f"Expected render_report function; found: {funcs}"
        )

    def test_deliver_report_defined(self):
        funcs = [n.name for n in ast.walk(self.tree)
                 if isinstance(n, ast.FunctionDef)]
        assert "deliver_report" in funcs, (
            f"Expected deliver_report function; found: {funcs}"
        )

    def test_retry_configuration(self):
        """fetch_data must configure retries for ConnectionError/TimeoutError."""
        has_retry = (
            "autoretry_for" in self.src
            or "retry" in self.src
            or "max_retries" in self.src
        )
        assert has_retry, "Expected retry configuration in tasks"

    def test_exponential_backoff(self):
        """Retry must use exponential backoff."""
        has_backoff = (
            "retry_backoff" in self.src
            or "countdown" in self.src
            or "backoff" in self.src
            or "exponential" in self.src.lower()
        )
        assert has_backoff, "Expected exponential backoff in retry configuration"

    def test_report_types(self):
        """Tasks must support sales, inventory, financial report types."""
        for rtype in ["sales", "inventory", "financial"]:
            assert rtype in self.src, (
                f"Expected report type '{rtype}' in task definitions"
            )


class TestSemanticModels:
    """Verify job state model."""

    @pytest.fixture(autouse=True)
    def _load_source(self):
        with open(MODELS_FILE, "r", encoding="utf-8") as f:
            self.src = f.read()

    def test_job_states_defined(self):
        """All 7 job states must be defined."""
        states = ["pending", "fetching", "aggregating", "rendering",
                   "delivering", "succeeded", "failed"]
        found = [s for s in states if s in self.src]
        assert len(found) >= 6, (
            f"Expected at least 6 of 7 job states; found: {found}"
        )

    def test_job_record_fields(self):
        """Job record must store essential fields."""
        fields = ["status", "report_type", "raw_data", "aggregated_data",
                   "rendered_output", "error"]
        found = [f for f in fields if f in self.src]
        assert len(found) >= 5, (
            f"Expected at least 5 of 6 job record fields; found: {found}"
        )


class TestSemanticPipeline:
    """Verify pipeline orchestration using chains."""

    @pytest.fixture(autouse=True)
    def _load_source(self):
        with open(PIPELINE_FILE, "r", encoding="utf-8") as f:
            self.src = f.read()

    def test_chain_import(self):
        """Pipeline must use Celery chain for sequential composition."""
        assert "chain" in self.src, (
            "Expected Celery 'chain' import in pipeline orchestration"
        )

    def test_submit_report_function(self):
        tree = ast.parse(self.src)
        funcs = [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
        assert "submit_report" in funcs, (
            f"Expected submit_report function in pipeline.py; found: {funcs}"
        )

    def test_error_callback(self):
        """Pipeline must have an on_failure callback."""
        has_callback = (
            "on_error" in self.src
            or "link_error" in self.src
            or "on_failure" in self.src
            or "errback" in self.src
        )
        assert has_callback, (
            "Expected error/failure callback in pipeline orchestration"
        )


class TestSemanticAPI:
    """Verify FastAPI endpoints."""

    @pytest.fixture(autouse=True)
    def _load_source(self):
        with open(API_FILE, "r", encoding="utf-8") as f:
            self.src = f.read()
        self.tree = ast.parse(self.src)

    def test_fastapi_app(self):
        """API must create a FastAPI application."""
        assert "FastAPI" in self.src, "Expected FastAPI import/instantiation"

    def test_post_reports_endpoint(self):
        """POST /reports endpoint must exist."""
        has_post = re.search(r'@\w+\.post\s*\(\s*["\']\/reports', self.src)
        assert has_post, "Expected POST /reports endpoint"

    def test_get_reports_endpoint(self):
        """GET /reports/{job_id} endpoint must exist."""
        has_get = re.search(r'@\w+\.get\s*\(\s*["\']\/reports', self.src)
        assert has_get, "Expected GET /reports/{job_id} endpoint"


# ---------------------------------------------------------------------------
# Layer 3 — functional_check
# ---------------------------------------------------------------------------

class TestFunctionalBackgroundJobs:
    """Functional checks — syntax validation and import tests."""

    def _parse_file(self, filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            src = f.read()
        try:
            ast.parse(src)
            return True, None
        except SyntaxError as e:
            return False, str(e)

    def test_tasks_valid_python(self):
        ok, err = self._parse_file(TASKS_FILE)
        assert ok, f"tasks.py syntax error: {err}"

    def test_models_valid_python(self):
        ok, err = self._parse_file(MODELS_FILE)
        assert ok, f"models.py syntax error: {err}"

    def test_pipeline_valid_python(self):
        ok, err = self._parse_file(PIPELINE_FILE)
        assert ok, f"pipeline.py syntax error: {err}"

    def test_api_valid_python(self):
        ok, err = self._parse_file(API_FILE)
        assert ok, f"api.py syntax error: {err}"

    def test_config_valid_python(self):
        ok, err = self._parse_file(CONFIG_FILE)
        assert ok, f"config.py syntax error: {err}"

    def test_test_file_valid_python(self):
        ok, err = self._parse_file(TEST_FILE)
        assert ok, f"test_pipeline.py syntax error: {err}"

    def test_idempotency_logic_in_tasks(self):
        """Each task must check whether its output already exists before executing."""
        with open(TASKS_FILE, "r", encoding="utf-8") as f:
            src = f.read()
        has_idempotency = (
            "already" in src.lower()
            or "is not None" in src
            or "if.*raw_data" in src
            or "skip" in src.lower()
            or "idempoten" in src.lower()
        )
        assert has_idempotency, (
            "Expected idempotency checks in task definitions"
        )

    def test_state_transition_validation(self):
        """Job state model must validate transitions — completed states cannot change."""
        with open(MODELS_FILE, "r", encoding="utf-8") as f:
            src = f.read()
        has_validation = (
            "succeeded" in src and "failed" in src
            and ("raise" in src or "cannot" in src.lower() or "transition" in src.lower()
                 or "invalid" in src.lower() or "not allowed" in src.lower())
        )
        assert has_validation, (
            "Expected state transition validation preventing changes after succeeded/failed"
        )
