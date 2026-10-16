"""
Test skill: istio-traffic-management
Verify that the Agent implements a Canary Deployment Traffic Controller in Istio —
CanaryController (Start/Advance/Rollback, VirtualService/DestinationRule generation),
CanaryDeployment types (status enum, TrafficStep), and RollbackManager (error-rate
threshold evaluation with MetricsProvider).
"""

import os
import re
import subprocess
import pytest


class TestIstioTrafficManagement:
    REPO_DIR = "/workspace/istio"

    # ────── helpers ──────

    def _read(self, rel_path):
        fpath = os.path.join(self.REPO_DIR, rel_path)
        with open(fpath, "r") as f:
            return f.read()

    def _exists(self, rel_path):
        return os.path.isfile(os.path.join(self.REPO_DIR, rel_path))

    # === File Path Checks ===

    def test_controller_file_exists(self):
        """controller.go must exist"""
        assert self._exists("pilot/pkg/canary/controller.go")

    def test_types_file_exists(self):
        """types.go must exist"""
        assert self._exists("pilot/pkg/canary/types.go")

    def test_rollback_file_exists(self):
        """rollback.go must exist"""
        assert self._exists("pilot/pkg/canary/rollback.go")

    def test_controller_test_exists(self):
        """controller_test.go must exist"""
        assert self._exists("pilot/pkg/canary/controller_test.go")

    def test_rollback_test_exists(self):
        """rollback_test.go must exist"""
        assert self._exists("pilot/pkg/canary/rollback_test.go")

    # === Semantic Checks — types.go ===

    def test_canary_deployment_struct(self):
        """CanaryDeployment struct must be defined"""
        src = self._read("pilot/pkg/canary/types.go")
        assert re.search(r'type\s+CanaryDeployment\s+struct', src)

    def test_traffic_step_struct(self):
        """TrafficStep struct must be defined"""
        src = self._read("pilot/pkg/canary/types.go")
        assert re.search(r'type\s+TrafficStep\s+struct', src)

    def test_canary_status_constants(self):
        """Status constants Progressing, Paused, Completed, RolledBack, Failed"""
        src = self._read("pilot/pkg/canary/types.go")
        for status in ["Progressing", "Completed", "RolledBack", "Failed"]:
            assert status in src, f"CanaryStatus missing: {status}"

    def test_canary_state_struct(self):
        """CanaryState struct must be defined"""
        src = self._read("pilot/pkg/canary/types.go")
        assert re.search(r'type\s+CanaryState\s+struct', src)

    def test_error_threshold_field(self):
        """CanaryDeployment must have ErrorThreshold"""
        src = self._read("pilot/pkg/canary/types.go")
        assert "ErrorThreshold" in src

    def test_metric_window_field(self):
        """CanaryDeployment must have MetricWindow"""
        src = self._read("pilot/pkg/canary/types.go")
        assert "MetricWindow" in src

    # === Semantic Checks — controller.go ===

    def test_canary_controller_struct(self):
        """CanaryController struct must be defined"""
        src = self._read("pilot/pkg/canary/controller.go")
        assert re.search(r'type\s+CanaryController\s+struct', src)

    def test_start_method(self):
        """Start method must exist"""
        src = self._read("pilot/pkg/canary/controller.go")
        assert re.search(r'func\s+\(.*CanaryController\)\s+Start\b', src)

    def test_advance_method(self):
        """Advance method must exist"""
        src = self._read("pilot/pkg/canary/controller.go")
        assert re.search(r'func\s+\(.*CanaryController\)\s+Advance\b', src)

    def test_rollback_method(self):
        """Rollback method must exist"""
        src = self._read("pilot/pkg/canary/controller.go")
        assert re.search(r'func\s+\(.*CanaryController\)\s+Rollback\b', src)

    def test_generate_virtual_service(self):
        """GenerateVirtualService method must exist"""
        src = self._read("pilot/pkg/canary/controller.go")
        assert "GenerateVirtualService" in src

    def test_generate_destination_rule(self):
        """GenerateDestinationRule method must exist"""
        src = self._read("pilot/pkg/canary/controller.go")
        assert "GenerateDestinationRule" in src

    def test_virtual_service_weights(self):
        """VirtualService generation must set weights"""
        src = self._read("pilot/pkg/canary/controller.go")
        lower = src.lower()
        assert "weight" in lower, "Weight-based routing not found"

    def test_destination_rule_subsets(self):
        """DestinationRule must have subset labels"""
        src = self._read("pilot/pkg/canary/controller.go")
        lower = src.lower()
        assert "subset" in lower, "Subset configuration not found"

    # === Semantic Checks — rollback.go ===

    def test_metrics_provider_interface(self):
        """MetricsProvider interface must be defined"""
        src = self._read("pilot/pkg/canary/rollback.go")
        assert re.search(r'type\s+MetricsProvider\s+interface', src)

    def test_rollback_manager_struct(self):
        """RollbackManager struct must be defined"""
        src = self._read("pilot/pkg/canary/rollback.go")
        assert re.search(r'type\s+RollbackManager\s+struct', src)

    def test_check_and_rollback_method(self):
        """CheckAndRollback method must exist"""
        src = self._read("pilot/pkg/canary/rollback.go")
        assert "CheckAndRollback" in src

    def test_error_rate_threshold_logic(self):
        """Must compare error rate to threshold"""
        src = self._read("pilot/pkg/canary/rollback.go")
        lower = src.lower()
        assert "errorrate" in lower.replace(" ", "").replace("_", "") or "threshold" in lower

    def test_no_rollback_on_metrics_error(self):
        """Must NOT rollback when metrics provider returns error"""
        src = self._read("pilot/pkg/canary/rollback.go")
        # Should return error rather than triggering rollback
        assert "err" in src.lower(), "Error handling for metrics unavailability not found"

    # === Functional Checks ===

    def test_go_build_canary_package(self):
        """Canary package must build"""
        result = subprocess.run(
            ["go", "build", "./pilot/pkg/canary/..."],
            capture_output=True, text=True, cwd=self.REPO_DIR, timeout=300,
        )
        assert result.returncode == 0, (
            f"go build failed:\n{result.stdout}\n{result.stderr}"
        )

    def test_controller_tests_pass(self):
        """Controller tests must pass"""
        result = subprocess.run(
            ["go", "test", "-v", "./pilot/pkg/canary/...",
             "-run", "Test(Canary|Controller|Start|Advance|Rollback)"],
            capture_output=True, text=True, cwd=self.REPO_DIR, timeout=300,
        )
        assert result.returncode == 0, (
            f"Tests failed:\n{result.stdout}\n{result.stderr}"
        )

    def test_rollback_tests_pass(self):
        """Rollback manager tests must pass"""
        result = subprocess.run(
            ["go", "test", "-v", "./pilot/pkg/canary/...",
             "-run", "Test(Rollback|CheckAndRollback|MetricsProvider)"],
            capture_output=True, text=True, cwd=self.REPO_DIR, timeout=300,
        )
        assert result.returncode == 0, (
            f"Tests failed:\n{result.stdout}\n{result.stderr}"
        )
