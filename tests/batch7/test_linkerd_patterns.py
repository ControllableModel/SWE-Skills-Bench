"""
Test skill: linkerd-patterns
Verify that the Agent implements Retry Budget and Request Timeout Policy
in Linkerd2 — RetryBudgetCalculator with sliding-window ring buffer,
TimeoutPolicyResolver with per-route timeout derivation, and profile watcher
extension.
"""

import os
import re
import subprocess
import pytest


class TestLinkerdPatterns:
    REPO_DIR = "/workspace/linkerd2"

    # ────── helpers ──────

    def _read(self, rel_path):
        fpath = os.path.join(self.REPO_DIR, rel_path)
        with open(fpath, "r") as f:
            return f.read()

    def _exists(self, rel_path):
        return os.path.isfile(os.path.join(self.REPO_DIR, rel_path))

    # === File Path Checks ===

    def test_retry_budget_file_exists(self):
        """retry_budget.go must exist"""
        assert self._exists("controller/api/destination/retry_budget.go")

    def test_timeout_policy_file_exists(self):
        """timeout_policy.go must exist"""
        assert self._exists("controller/api/destination/timeout_policy.go")

    def test_retry_budget_test_exists(self):
        """retry_budget_test.go must exist"""
        assert self._exists("controller/api/destination/retry_budget_test.go")

    def test_timeout_policy_test_exists(self):
        """timeout_policy_test.go must exist"""
        assert self._exists("controller/api/destination/timeout_policy_test.go")

    # === Semantic Checks — RetryBudgetCalculator ===

    def test_retry_budget_calculator_struct(self):
        """RetryBudgetCalculator struct must be defined"""
        src = self._read("controller/api/destination/retry_budget.go")
        assert re.search(r'type\s+RetryBudgetCalculator\s+struct', src), (
            "RetryBudgetCalculator struct not found"
        )

    def test_ring_buffer_sliding_window(self):
        """Must use a ring buffer or sliding window approach"""
        src = self._read("controller/api/destination/retry_budget.go")
        lower = src.lower()
        assert any(k in lower for k in ["ring", "window", "circular", "bucket"]), (
            "Sliding-window / ring buffer approach not found"
        )

    def test_should_retry_method(self):
        """ShouldRetry method must be defined"""
        src = self._read("controller/api/destination/retry_budget.go")
        assert re.search(r'func\s+\(.*RetryBudgetCalculator\)\s+ShouldRetry\b', src), (
            "ShouldRetry method not found"
        )

    def test_record_methods(self):
        """RecordRequest and RecordRetry methods must exist"""
        src = self._read("controller/api/destination/retry_budget.go")
        assert "RecordRequest" in src, "RecordRequest method not found"
        assert "RecordRetry" in src, "RecordRetry method not found"

    def test_retry_ratio_check(self):
        """ShouldRetry must enforce a ratio-based budget"""
        src = self._read("controller/api/destination/retry_budget.go")
        lower = src.lower()
        assert any(k in lower for k in ["ratio", "budget", "percent", "fraction"]), (
            "Ratio-based budget logic not found"
        )

    def test_min_retries_floor(self):
        """Must support min retries per second floor"""
        src = self._read("controller/api/destination/retry_budget.go")
        lower = src.lower()
        assert any(k in lower for k in ["min", "floor", "minretries", "minimum"]), (
            "Min-retry floor not found"
        )

    def test_reset_method(self):
        """Reset method must exist"""
        src = self._read("controller/api/destination/retry_budget.go")
        assert "Reset" in src, "Reset method not found"

    # === Semantic Checks — TimeoutPolicyResolver ===

    def test_timeout_policy_resolver_struct(self):
        """TimeoutPolicyResolver struct must be defined"""
        src = self._read("controller/api/destination/timeout_policy.go")
        assert re.search(r'type\s+TimeoutPolicyResolver\s+struct', src), (
            "TimeoutPolicyResolver struct not found"
        )

    def test_resolve_timeouts_method(self):
        """ResolveTimeouts method must be defined"""
        src = self._read("controller/api/destination/timeout_policy.go")
        assert re.search(r'func\s+\(.*TimeoutPolicyResolver\)\s+ResolveTimeout', src), (
            "ResolveTimeouts method not found"
        )

    def test_duration_parsing(self):
        """Must parse duration strings"""
        src = self._read("controller/api/destination/timeout_policy.go")
        assert "time.Duration" in src or "ParseDuration" in src or "Duration" in src, (
            "Duration parsing not found"
        )

    def test_default_timeout(self):
        """Must provide a default timeout"""
        src = self._read("controller/api/destination/timeout_policy.go")
        lower = src.lower()
        assert any(k in lower for k in ["default", "fallback"]), (
            "Default timeout logic not found"
        )

    def test_per_route_timeout(self):
        """Must support per-route timeout derivation"""
        src = self._read("controller/api/destination/timeout_policy.go")
        lower = src.lower()
        assert any(k in lower for k in ["route", "path", "annotation"]), (
            "Per-route timeout logic not found"
        )

    # === Semantic Checks — Watcher Extension ===

    def test_get_retry_budget_watcher(self):
        """Profile watcher must expose GetRetryBudget"""
        found = False
        for root, _, files in os.walk(os.path.join(self.REPO_DIR, "controller/api/destination")):
            for fn in files:
                if fn.endswith(".go"):
                    content = open(os.path.join(root, fn)).read()
                    if "GetRetryBudget" in content:
                        found = True
                        break
        assert found, "GetRetryBudget not found in destination package"

    def test_get_timeout_policies_watcher(self):
        """Profile watcher must expose GetTimeoutPolicies or GetTimeoutPolicy"""
        found = False
        for root, _, files in os.walk(os.path.join(self.REPO_DIR, "controller/api/destination")):
            for fn in files:
                if fn.endswith(".go"):
                    content = open(os.path.join(root, fn)).read()
                    if "GetTimeoutPolic" in content:
                        found = True
                        break
        assert found, "GetTimeoutPolicies not found in destination package"

    # === Functional Checks ===

    def test_go_build_destination_package(self):
        """Destination package must build"""
        result = subprocess.run(
            ["go", "build", "./controller/api/destination/..."],
            capture_output=True, text=True, cwd=self.REPO_DIR, timeout=300,
        )
        assert result.returncode == 0, (
            f"go build failed:\n{result.stdout}\n{result.stderr}"
        )

    def test_retry_budget_tests_pass(self):
        """RetryBudget tests must pass"""
        result = subprocess.run(
            ["go", "test", "-v",
             "./controller/api/destination/...",
             "-run", "TestRetryBudget"],
            capture_output=True, text=True, cwd=self.REPO_DIR, timeout=300,
        )
        assert result.returncode == 0, (
            f"Tests failed:\n{result.stdout}\n{result.stderr}"
        )

    def test_timeout_policy_tests_pass(self):
        """TimeoutPolicy tests must pass"""
        result = subprocess.run(
            ["go", "test", "-v",
             "./controller/api/destination/...",
             "-run", "TestTimeout"],
            capture_output=True, text=True, cwd=self.REPO_DIR, timeout=300,
        )
        assert result.returncode == 0, (
            f"Tests failed:\n{result.stdout}\n{result.stderr}"
        )
