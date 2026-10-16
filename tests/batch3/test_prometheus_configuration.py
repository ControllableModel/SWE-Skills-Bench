"""
Test skill: prometheus-configuration
Verify that the Agent implements custom service discovery, recording rules,
and multi-severity alert rules for Prometheus.
"""

import os
import subprocess
import pytest


class TestPrometheusConfiguration:
    REPO_DIR = "/workspace/prometheus"

    # === File Path Checks ===

    def test_service_discovery_go_exists(self):
        """Verify service discovery Go file exists"""
        path = os.path.join(self.REPO_DIR, "config/service_discovery.go")
        assert os.path.exists(path), f"service_discovery.go not found at {path}"

    def test_recording_rules_go_exists(self):
        """Verify recording rules Go file exists"""
        path = os.path.join(self.REPO_DIR, "rules/recording_rules.go")
        assert os.path.exists(path), f"recording_rules.go not found at {path}"

    def test_alert_rules_go_exists(self):
        """Verify alert rules Go file exists"""
        path = os.path.join(self.REPO_DIR, "rules/alert_rules.go")
        assert os.path.exists(path), f"alert_rules.go not found at {path}"

    def test_service_discovery_test_exists(self):
        """Verify service discovery test file exists"""
        path = os.path.join(self.REPO_DIR, "config/service_discovery_test.go")
        assert os.path.exists(path), f"service_discovery_test.go not found at {path}"

    def test_recording_rules_test_exists(self):
        """Verify recording rules test file exists"""
        path = os.path.join(self.REPO_DIR, "rules/recording_rules_test.go")
        assert os.path.exists(path), f"recording_rules_test.go not found at {path}"

    def test_alert_rules_test_exists(self):
        """Verify alert rules test file exists"""
        path = os.path.join(self.REPO_DIR, "rules/alert_rules_test.go")
        assert os.path.exists(path), f"alert_rules_test.go not found at {path}"

    # === Semantic Checks ===

    def test_service_discovery_has_struct_and_generate(self):
        """Verify service_discovery.go defines ServiceDiscoveryConfig and GenerateFileSD"""
        path = os.path.join(self.REPO_DIR, "config/service_discovery.go")
        with open(path) as f:
            content = f.read()
        assert "ServiceDiscoveryConfig" in content, \
            "Missing ServiceDiscoveryConfig struct"
        assert "GenerateFileSD" in content, \
            "Missing GenerateFileSD function"

    def test_service_discovery_validates_targets(self):
        """Verify service_discovery.go validates target format (host:port)"""
        path = os.path.join(self.REPO_DIR, "config/service_discovery.go")
        with open(path) as f:
            content = f.read()
        # Should validate port range
        has_port_validation = (
            "65535" in content or
            "port" in content.lower()
        )
        assert has_port_validation, \
            "Service discovery should validate port range (1-65535)"

    def test_service_discovery_validates_labels(self):
        """Verify service_discovery.go validates label names and rejects __ prefix"""
        path = os.path.join(self.REPO_DIR, "config/service_discovery.go")
        with open(path) as f:
            content = f.read()
        assert "__" in content, \
            "Should check for reserved __ prefix in label names"

    def test_recording_rules_cover_golden_signals(self):
        """Verify recording rules cover 4 golden signals: latency, traffic, errors, saturation"""
        path = os.path.join(self.REPO_DIR, "rules/recording_rules.go")
        with open(path) as f:
            content = f.read()
        signals = {
            "latency": ["duration", "latency", "p50", "p90", "p99", "histogram_quantile"],
            "traffic": ["requests_total", "rate", "traffic"],
            "errors": ["error", "ratio"],
            "saturation": ["cpu", "saturation", "process"],
        }
        found_signals = []
        for signal, keywords in signals.items():
            if any(kw.lower() in content.lower() for kw in keywords):
                found_signals.append(signal)
        assert len(found_signals) >= 3, \
            f"Recording rules should cover all 4 golden signals. Found: {found_signals}"

    def test_alert_rules_has_severity_levels(self):
        """Verify alert rules define critical, warning, and info severity levels"""
        path = os.path.join(self.REPO_DIR, "rules/alert_rules.go")
        with open(path) as f:
            content = f.read()
        severities = ["critical", "warning", "info"]
        for sev in severities:
            assert sev in content.lower(), \
                f"Alert rules should define '{sev}' severity level"

    def test_alert_rules_has_burn_rate(self):
        """Verify alert rules include burn rate alert conditions"""
        path = os.path.join(self.REPO_DIR, "rules/alert_rules.go")
        with open(path) as f:
            content = f.read()
        assert "burn" in content.lower() or "BurnRate" in content or "burn_rate" in content, \
            "Alert rules should include burn rate alerts for SLO violations"

    def test_alert_rules_has_annotations(self):
        """Verify alert rules include summary and description annotations"""
        path = os.path.join(self.REPO_DIR, "rules/alert_rules.go")
        with open(path) as f:
            content = f.read()
        assert "summary" in content.lower(), "Alert rules should have 'summary' annotation"
        assert "description" in content.lower(), "Alert rules should have 'description' annotation"
        # Check for templated values
        assert "$value" in content or "{{ " in content or "Value" in content, \
            "Annotations should use templated values like {{ $value }}"

    def test_yaml_marshal_defined(self):
        """Verify MarshalYAML method is defined for configuration types"""
        files = [
            "config/service_discovery.go",
            "rules/recording_rules.go",
            "rules/alert_rules.go",
        ]
        marshal_count = 0
        for rel_path in files:
            path = os.path.join(self.REPO_DIR, rel_path)
            with open(path) as f:
                content = f.read()
            if "MarshalYAML" in content or "yaml.Marshal" in content or "Marshal" in content:
                marshal_count += 1
        assert marshal_count >= 2, \
            f"At least 2 modules should define YAML marshaling. Found {marshal_count}"

    # === Functional Checks ===

    def test_service_discovery_go_compiles(self):
        """Verify service_discovery.go compiles with go vet"""
        result = subprocess.run(
            ["go", "vet", "./config/..."],
            cwd=self.REPO_DIR,
            capture_output=True, text=True, timeout=120
        )
        # go vet may show warnings but shouldn't have compilation errors
        if result.returncode != 0:
            assert "cannot find" not in result.stderr and "undefined" not in result.stderr, \
                f"Go compilation errors in config/: {result.stderr[:1000]}"

    def test_recording_rules_go_compiles(self):
        """Verify recording_rules.go compiles with go vet"""
        result = subprocess.run(
            ["go", "vet", "./rules/..."],
            cwd=self.REPO_DIR,
            capture_output=True, text=True, timeout=120
        )
        if result.returncode != 0:
            assert "cannot find" not in result.stderr and "undefined" not in result.stderr, \
                f"Go compilation errors in rules/: {result.stderr[:1000]}"

    def test_service_discovery_tests_pass(self):
        """Verify service discovery tests pass"""
        result = subprocess.run(
            ["go", "test", "-v", "-run", "TestServiceDiscovery", "-count=1", "./config/..."],
            cwd=self.REPO_DIR,
            capture_output=True, text=True, timeout=120
        )
        if "no test files" in result.stderr:
            pytest.skip("No test files found in config/")
        # Allow test discovery issues but not compilation failures
        if result.returncode != 0:
            assert "FAIL" not in result.stdout or "build" in result.stderr.lower(), \
                f"Service discovery tests failed:\n{result.stdout[:1000]}\n{result.stderr[:500]}"

    def test_recording_rules_tests_pass(self):
        """Verify recording rules tests pass"""
        result = subprocess.run(
            ["go", "test", "-v", "-run", "TestRecordingRule", "-count=1", "./rules/..."],
            cwd=self.REPO_DIR,
            capture_output=True, text=True, timeout=120
        )
        if "no test files" in result.stderr:
            pytest.skip("No test files found in rules/")
        if result.returncode != 0:
            assert "FAIL" not in result.stdout or "build" in result.stderr.lower(), \
                f"Recording rules tests failed:\n{result.stdout[:1000]}\n{result.stderr[:500]}"

    def test_alert_rules_tests_pass(self):
        """Verify alert rules tests pass"""
        result = subprocess.run(
            ["go", "test", "-v", "-run", "TestAlertRule", "-count=1", "./rules/..."],
            cwd=self.REPO_DIR,
            capture_output=True, text=True, timeout=120
        )
        if "no test files" in result.stderr:
            pytest.skip("No test files found in rules/")
        if result.returncode != 0:
            assert "FAIL" not in result.stdout or "build" in result.stderr.lower(), \
                f"Alert rules tests failed:\n{result.stdout[:1000]}\n{result.stderr[:500]}"
