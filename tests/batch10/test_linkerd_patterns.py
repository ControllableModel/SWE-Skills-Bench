"""
Test skill: linkerd-patterns
Verify that the Agent correctly implements a service mesh policy engine
with ServiceProfile, TrafficSplit, and Authorization resources for Linkerd2.
"""

import os
import re
import subprocess
import pytest


class TestLinkerdPatterns:
    REPO_DIR = "/workspace/linkerd2"

    # === File Path Checks ===

    def test_engine_go_exists(self):
        """Verify engine.go was created"""
        path = os.path.join(self.REPO_DIR, "controller/policy/engine.go")
        assert os.path.exists(path), f"engine.go not found at {path}"

    def test_engine_test_go_exists(self):
        """Verify engine_test.go was created"""
        path = os.path.join(self.REPO_DIR, "controller/policy/engine_test.go")
        assert os.path.exists(path), f"engine_test.go not found at {path}"

    def test_spec_go_exists(self):
        """Verify spec.go was created"""
        path = os.path.join(self.REPO_DIR, "pkg/profiles/spec.go")
        assert os.path.exists(path), f"spec.go not found at {path}"

    def test_spec_test_go_exists(self):
        """Verify spec_test.go was created"""
        path = os.path.join(self.REPO_DIR, "pkg/profiles/spec_test.go")
        assert os.path.exists(path), f"spec_test.go not found at {path}"

    def test_traffic_split_go_exists(self):
        """Verify traffic_split.go was created"""
        path = os.path.join(self.REPO_DIR, "pkg/split/traffic_split.go")
        assert os.path.exists(path), f"traffic_split.go not found at {path}"

    def test_traffic_split_test_go_exists(self):
        """Verify traffic_split_test.go was created"""
        path = os.path.join(self.REPO_DIR, "pkg/split/traffic_split_test.go")
        assert os.path.exists(path), f"traffic_split_test.go not found at {path}"

    def test_server_auth_go_exists(self):
        """Verify server_authorization.go was created"""
        path = os.path.join(self.REPO_DIR, "pkg/auth/server_authorization.go")
        assert os.path.exists(path), f"server_authorization.go not found at {path}"

    def test_server_auth_test_go_exists(self):
        """Verify server_authorization_test.go was created"""
        path = os.path.join(self.REPO_DIR, "pkg/auth/server_authorization_test.go")
        assert os.path.exists(path), f"server_authorization_test.go not found at {path}"

    # === Semantic Checks: ServiceProfile ===

    def test_service_profile_struct(self):
        """Verify ServiceProfile struct is defined with FQDN"""
        path = os.path.join(self.REPO_DIR, "pkg/profiles/spec.go")
        with open(path) as f:
            content = f.read()
        assert "ServiceProfile" in content, "ServiceProfile struct should be defined"
        assert "FQDN" in content, "Should have FQDN field"

    def test_route_spec_struct(self):
        """Verify RouteSpec with Method, PathRegex, Timeout"""
        path = os.path.join(self.REPO_DIR, "pkg/profiles/spec.go")
        with open(path) as f:
            content = f.read()
        assert "RouteSpec" in content, "RouteSpec struct should be defined"
        assert "PathRegex" in content, "Should have PathRegex field"

    def test_retry_budget_spec(self):
        """Verify RetryBudgetSpec with RetryRatio, MinRetriesPerSecond, TTL"""
        path = os.path.join(self.REPO_DIR, "pkg/profiles/spec.go")
        with open(path) as f:
            content = f.read()
        assert "RetryBudgetSpec" in content, "RetryBudgetSpec should be defined"
        assert "RetryRatio" in content, "Should have RetryRatio field"

    def test_response_class_spec(self):
        """Verify ResponseClassSpec with StatusMin, StatusMax"""
        path = os.path.join(self.REPO_DIR, "pkg/profiles/spec.go")
        with open(path) as f:
            content = f.read()
        assert "ResponseClassSpec" in content, "ResponseClassSpec should be defined"

    def test_fqdn_validation(self):
        """Verify FQDN validates svc.cluster.local pattern"""
        path = os.path.join(self.REPO_DIR, "pkg/profiles/spec.go")
        with open(path) as f:
            content = f.read()
        assert "svc.cluster.local" in content, (
            "Should validate FQDN against svc.cluster.local pattern"
        )

    def test_match_route_function(self):
        """Verify MatchRoute method is defined"""
        path = os.path.join(self.REPO_DIR, "pkg/profiles/spec.go")
        with open(path) as f:
            content = f.read()
        assert "MatchRoute" in content, "Should have MatchRoute method"

    # === Semantic Checks: TrafficSplit ===

    def test_traffic_split_struct(self):
        """Verify TrafficSplit struct with Backends"""
        path = os.path.join(self.REPO_DIR, "pkg/split/traffic_split.go")
        with open(path) as f:
            content = f.read()
        assert "TrafficSplit" in content, "TrafficSplit struct should be defined"
        assert "TrafficBackend" in content, "TrafficBackend should be defined"

    def test_traffic_split_validate(self):
        """Verify Validate method rejects invalid weights"""
        path = os.path.join(self.REPO_DIR, "pkg/split/traffic_split.go")
        with open(path) as f:
            content = f.read()
        assert "Validate" in content, "Should have Validate method"
        assert "1000" in content, "Should check weights sum to 1000"

    def test_normalize_weights(self):
        """Verify NormalizeWeights method is defined"""
        path = os.path.join(self.REPO_DIR, "pkg/split/traffic_split.go")
        with open(path) as f:
            content = f.read()
        assert "NormalizeWeights" in content, (
            "Should have NormalizeWeights method"
        )

    def test_get_backend_for_value(self):
        """Verify GetBackendForValue method is defined"""
        path = os.path.join(self.REPO_DIR, "pkg/split/traffic_split.go")
        with open(path) as f:
            content = f.read()
        assert "GetBackendForValue" in content, (
            "Should have GetBackendForValue method"
        )

    # === Semantic Checks: ServerAuthorization ===

    def test_server_authorization_struct(self):
        """Verify ServerAuthorization struct"""
        path = os.path.join(self.REPO_DIR, "pkg/auth/server_authorization.go")
        with open(path) as f:
            content = f.read()
        assert "ServerAuthorization" in content, (
            "ServerAuthorization struct should be defined"
        )

    def test_server_struct(self):
        """Verify Server struct with PodSelector"""
        path = os.path.join(self.REPO_DIR, "pkg/auth/server_authorization.go")
        with open(path) as f:
            content = f.read()
        assert "Server" in content, "Server struct should be defined"
        assert "PodSelector" in content, "Should have PodSelector field"

    def test_identity_struct(self):
        """Verify Identity struct with ServiceAccount, Namespace"""
        path = os.path.join(self.REPO_DIR, "pkg/auth/server_authorization.go")
        with open(path) as f:
            content = f.read()
        assert "Identity" in content, "Identity struct should be defined"
        assert "ServiceAccount" in content, "Should have ServiceAccount field"

    def test_auth_evaluate(self):
        """Verify Evaluate method returns Allow/Deny"""
        path = os.path.join(self.REPO_DIR, "pkg/auth/server_authorization.go")
        with open(path) as f:
            content = f.read()
        assert "Evaluate" in content, "Should have Evaluate method"
        assert "Allow" in content or "Deny" in content, (
            "Should return Allow or Deny"
        )

    def test_auth_cidr_validation(self):
        """Verify CIDR validation in Networks"""
        path = os.path.join(self.REPO_DIR, "pkg/auth/server_authorization.go")
        with open(path) as f:
            content = f.read()
        assert "CIDR" in content or "ParseCIDR" in content, (
            "Should validate CIDR notation"
        )

    def test_unauthenticated_mutex(self):
        """Verify UnauthenticatedAccess + MeshTLSIdentities mutual exclusivity"""
        path = os.path.join(self.REPO_DIR, "pkg/auth/server_authorization.go")
        with open(path) as f:
            content = f.read()
        assert "UnauthenticatedAccess" in content, (
            "Should have UnauthenticatedAccess field"
        )
        assert "MeshTLSIdentities" in content, (
            "Should have MeshTLSIdentities field"
        )

    # === Semantic Checks: PolicyEngine ===

    def test_policy_engine_struct(self):
        """Verify PolicyEngine struct is defined"""
        path = os.path.join(self.REPO_DIR, "controller/policy/engine.go")
        with open(path) as f:
            content = f.read()
        assert "PolicyEngine" in content, "PolicyEngine should be defined"

    def test_policy_engine_apply(self):
        """Verify Apply method for storing resources"""
        path = os.path.join(self.REPO_DIR, "controller/policy/engine.go")
        with open(path) as f:
            content = f.read()
        assert "Apply" in content, "Should have Apply method"

    def test_policy_engine_remove(self):
        """Verify Remove method for deleting resources"""
        path = os.path.join(self.REPO_DIR, "controller/policy/engine.go")
        with open(path) as f:
            content = f.read()
        assert "Remove" in content, "Should have Remove method"

    def test_policy_engine_evaluate_request(self):
        """Verify EvaluateRequest method"""
        path = os.path.join(self.REPO_DIR, "controller/policy/engine.go")
        with open(path) as f:
            content = f.read()
        assert "EvaluateRequest" in content, (
            "Should have EvaluateRequest method"
        )

    # === Functional Checks ===

    def test_go_files_have_package(self):
        """Verify Go files have proper package declarations"""
        files = [
            "controller/policy/engine.go",
            "pkg/profiles/spec.go",
            "pkg/split/traffic_split.go",
            "pkg/auth/server_authorization.go",
        ]
        for rel_path in files:
            path = os.path.join(self.REPO_DIR, rel_path)
            with open(path) as f:
                content = f.read()
            assert content.startswith("package "), (
                f"{rel_path} should start with package declaration"
            )

    def test_policy_tests_pass(self):
        """Verify go test passes for controller/policy/"""
        result = subprocess.run(
            ["go", "test", "./controller/policy/", "-v"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, (
            f"Policy tests failed:\n{result.stdout}\n{result.stderr}"
        )

    def test_profiles_tests_pass(self):
        """Verify go test passes for pkg/profiles/"""
        result = subprocess.run(
            ["go", "test", "./pkg/profiles/", "-v"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, (
            f"Profiles tests failed:\n{result.stdout}\n{result.stderr}"
        )

    def test_split_tests_pass(self):
        """Verify go test passes for pkg/split/"""
        result = subprocess.run(
            ["go", "test", "./pkg/split/", "-v"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, (
            f"Split tests failed:\n{result.stdout}\n{result.stderr}"
        )

    def test_auth_tests_pass(self):
        """Verify go test passes for pkg/auth/"""
        result = subprocess.run(
            ["go", "test", "./pkg/auth/", "-v"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, (
            f"Auth tests failed:\n{result.stdout}\n{result.stderr}"
        )
