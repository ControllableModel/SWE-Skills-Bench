"""
Tests for the python-background-jobs skill.

Validates that an idempotent email delivery pipeline with state machine,
retry behavior, timeouts, and status visibility was implemented for Celery.

Repo: celery (https://github.com/celery/celery)
"""

import ast
import os
import re
import subprocess
import sys

REPO_DIR = "/workspace/celery"


class TestFilePathCheck:
    """Verify that all required files were created."""

    def test_email_pipeline_file_exists(self):
        path = os.path.join(REPO_DIR, "celery", "contrib", "email_pipeline.py")
        assert os.path.isfile(path), f"Expected email_pipeline.py at {path}"

    def test_email_models_file_exists(self):
        path = os.path.join(REPO_DIR, "celery", "contrib", "email_models.py")
        assert os.path.isfile(path), f"Expected email_models.py at {path}"

    def test_email_pipeline_test_file_exists(self):
        path = os.path.join(REPO_DIR, "t", "unit", "contrib", "test_email_pipeline.py")
        assert os.path.isfile(path), f"Expected test_email_pipeline.py at {path}"


class TestSemanticStateMachine:
    """Verify the email delivery state machine is correctly defined."""

    def _read_models(self):
        path = os.path.join(REPO_DIR, "celery", "contrib", "email_models.py")
        with open(path, "r") as f:
            return f.read()

    def _read_pipeline(self):
        path = os.path.join(REPO_DIR, "celery", "contrib", "email_pipeline.py")
        with open(path, "r") as f:
            return f.read()

    def test_all_states_defined(self):
        """States: PENDING, SENDING, SENT, FAILED, CANCELLED."""
        content = self._read_models() + self._read_pipeline()
        for state in ["PENDING", "SENDING", "SENT", "FAILED", "CANCELLED"]:
            assert state in content, f"Expected delivery state '{state}' to be defined"

    def test_invalid_state_transition_exception(self):
        content = self._read_models() + self._read_pipeline()
        assert re.search(r"class\s+InvalidStateTransition", content), (
            "Expected InvalidStateTransition exception class"
        )

    def test_duplicate_delivery_error_exception(self):
        content = self._read_models() + self._read_pipeline()
        assert re.search(r"class\s+DuplicateDeliveryError", content), (
            "Expected DuplicateDeliveryError exception class"
        )

    def test_state_transitions_defined(self):
        """Valid transitions should be explicitly defined."""
        content = self._read_models() + self._read_pipeline()
        # Look for transition mapping/dict or transition validation logic
        assert re.search(
            r"transition|PENDING.*SENDING|valid.*state|allowed.*transition",
            content, re.IGNORECASE
        ), "Expected state transition mapping or validation logic"

    def test_transition_records_timestamp(self):
        """Each state transition should record a timestamp."""
        content = self._read_models() + self._read_pipeline()
        assert re.search(r"timestamp|datetime|time\.time|created_at|transition.*time", content, re.IGNORECASE), (
            "Expected timestamp recording on state transitions"
        )

    def test_transition_history_maintained(self):
        """Transition history should be maintained for status visibility."""
        content = self._read_models() + self._read_pipeline()
        assert re.search(r"history|transitions|log|record", content, re.IGNORECASE), (
            "Expected transition history tracking"
        )


class TestSemanticIdempotency:
    """Verify idempotency enforcement."""

    def _read_pipeline(self):
        path = os.path.join(REPO_DIR, "celery", "contrib", "email_pipeline.py")
        with open(path, "r") as f:
            return f.read()

    def test_idempotency_key_parameter(self):
        content = self._read_pipeline()
        assert re.search(r"idempotency_key", content), (
            "Expected idempotency_key parameter in email delivery pipeline"
        )

    def test_sent_state_early_return(self):
        """If already SENT, task should return without resending."""
        content = self._read_pipeline()
        assert re.search(r"SENT|already.*sent|skip|return", content, re.IGNORECASE), (
            "Expected early return logic for already-SENT deliveries"
        )

    def test_atomic_check_and_transition(self):
        """Idempotency check and SENDING transition must be atomic."""
        content = self._read_pipeline()
        assert re.search(r"atomic|lock|mutex|compare.*swap|cas|threading", content, re.IGNORECASE), (
            "Expected atomic/lock mechanism for idempotency check"
        )


class TestSemanticRetryBehavior:
    """Verify retry behavior with exponential backoff."""

    def _read_pipeline(self):
        path = os.path.join(REPO_DIR, "celery", "contrib", "email_pipeline.py")
        with open(path, "r") as f:
            return f.read()

    def test_max_retry_count(self):
        """Maximum 5 retry attempts."""
        content = self._read_pipeline()
        assert "5" in content, "Expected max retry count of 5 in pipeline"

    def test_exponential_backoff(self):
        """Retry delays should increase exponentially."""
        content = self._read_pipeline()
        assert re.search(r"exponential|backoff|\*\*|pow|2\s*\*\*", content, re.IGNORECASE), (
            "Expected exponential backoff logic in retry behavior"
        )

    def test_max_delay_cap(self):
        """Delay should be capped at 3600 seconds."""
        content = self._read_pipeline()
        assert "3600" in content, "Expected max delay cap of 3600 seconds"

    def test_initial_delay(self):
        """Starting delay of 60 seconds."""
        content = self._read_pipeline()
        assert "60" in content, "Expected initial retry delay of 60 seconds"

    def test_transient_errors_trigger_retry(self):
        """SMTPTemporaryError, ConnectionError, TimeoutError should trigger retry."""
        content = self._read_pipeline()
        transient_found = sum(1 for err in ["ConnectionError", "TimeoutError", "SMTPTemporary"]
                              if err in content)
        assert transient_found >= 2, (
            f"Expected at least 2 transient error types handled, found {transient_found}"
        )

    def test_permanent_errors_fail_immediately(self):
        """SMTPAuthenticationError, SMTPRecipientsRefused should fail without retry."""
        content = self._read_pipeline()
        permanent_found = sum(1 for err in ["SMTPAuthentication", "SMTPRecipientsRefused"]
                              if err in content)
        assert permanent_found >= 1, (
            "Expected at least 1 permanent error type handled (fail without retry)"
        )


class TestSemanticTimeouts:
    """Verify soft and hard timeout handling."""

    def _read_pipeline(self):
        path = os.path.join(REPO_DIR, "celery", "contrib", "email_pipeline.py")
        with open(path, "r") as f:
            return f.read()

    def test_soft_timeout_value(self):
        """Soft timeout of 30 seconds."""
        content = self._read_pipeline()
        assert "30" in content, "Expected soft timeout value of 30 seconds"

    def test_hard_timeout_value(self):
        """Hard timeout of 60 seconds."""
        content = self._read_pipeline()
        assert "60" in content, "Expected hard timeout value of 60 seconds"

    def test_timeout_logging(self):
        """Soft timeout should trigger warning log."""
        content = self._read_pipeline()
        assert re.search(r"warning|warn|logger|logging", content, re.IGNORECASE), (
            "Expected logging for timeout events"
        )


class TestSemanticStatusVisibility:
    """Verify status query functions."""

    def _read_all(self):
        pipeline = os.path.join(REPO_DIR, "celery", "contrib", "email_pipeline.py")
        models = os.path.join(REPO_DIR, "celery", "contrib", "email_models.py")
        content = ""
        for path in [pipeline, models]:
            with open(path, "r") as f:
                content += f.read()
        return content

    def test_get_delivery_status_function(self):
        content = self._read_all()
        assert re.search(r"def\s+get_delivery_status", content), (
            "Expected get_delivery_status function"
        )

    def test_list_failed_deliveries_function(self):
        content = self._read_all()
        assert re.search(r"def\s+list_failed_deliveries", content), (
            "Expected list_failed_deliveries function"
        )


class TestFunctionalPythonSyntax:
    """Validate Python syntax of all created files."""

    def _check_syntax(self, filepath):
        with open(filepath, "r") as f:
            source = f.read()
        ast.parse(source)

    def test_email_pipeline_syntax(self):
        self._check_syntax(os.path.join(REPO_DIR, "celery", "contrib", "email_pipeline.py"))

    def test_email_models_syntax(self):
        self._check_syntax(os.path.join(REPO_DIR, "celery", "contrib", "email_models.py"))

    def test_test_file_syntax(self):
        self._check_syntax(
            os.path.join(REPO_DIR, "t", "unit", "contrib", "test_email_pipeline.py")
        )


class TestFunctionalTestCoverage:
    """Verify that the agent's own test file has adequate coverage."""

    def _read_test_file(self):
        path = os.path.join(REPO_DIR, "t", "unit", "contrib", "test_email_pipeline.py")
        with open(path, "r") as f:
            return f.read()

    def test_test_file_has_sufficient_tests(self):
        content = self._read_test_file()
        test_count = len(re.findall(r"def\s+test_", content))
        assert test_count >= 5, (
            f"Expected at least 5 test functions in test_email_pipeline.py, found {test_count}"
        )

    def test_test_covers_state_transitions(self):
        content = self._read_test_file()
        assert re.search(r"state|transition|InvalidStateTransition", content), (
            "Expected tests covering state transitions"
        )

    def test_test_covers_idempotency(self):
        content = self._read_test_file()
        assert re.search(r"idempotency|idempotent|duplicate|DuplicateDeliveryError", content, re.IGNORECASE), (
            "Expected tests covering idempotency"
        )

    def test_test_covers_retry(self):
        content = self._read_test_file()
        assert re.search(r"retry|backoff|transient", content, re.IGNORECASE), (
            "Expected tests covering retry behavior"
        )

    def test_agent_tests_pass(self):
        """Run the agent's own tests to verify they pass."""
        result = subprocess.run(
            [sys.executable, "-m", "pytest",
             "t/unit/contrib/test_email_pipeline.py", "-v", "--tb=short"],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, (
            f"Agent's own tests failed:\n{result.stdout[-1000:]}\n{result.stderr[-500:]}"
        )
