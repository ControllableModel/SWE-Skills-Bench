"""
Test skill: linkerd-patterns
Verify that the Agent creates Linkerd mTLS demo configurations
including Server/ServerAuthorization resources, verification scripts,
workload deployments, and documentation.
"""

import os
import re
import subprocess
import pytest


class TestLinkerdPatterns:
    REPO_DIR = "/workspace/linkerd2"

    BASE = "examples/mtls-demo"

    # === File Path Checks ===

    def test_server_authorization_exists(self):
        """Verify server-authorization.yaml exists"""
        path = os.path.join(self.REPO_DIR, self.BASE, "server-authorization.yaml")
        assert os.path.exists(path), f"server-authorization.yaml not found"

    def test_server_yaml_exists(self):
        """Verify server.yaml exists"""
        path = os.path.join(self.REPO_DIR, self.BASE, "server.yaml")
        assert os.path.exists(path), f"server.yaml not found"

    def test_deployments_yaml_exists(self):
        """Verify deployments.yaml exists"""
        path = os.path.join(self.REPO_DIR, self.BASE, "deployments.yaml")
        assert os.path.exists(path), f"deployments.yaml not found"

    def test_verify_script_exists(self):
        """Verify verify-mtls.sh script exists"""
        path = os.path.join(self.REPO_DIR, self.BASE, "verify-mtls.sh")
        assert os.path.exists(path), f"verify-mtls.sh not found"

    def test_readme_exists(self):
        """Verify README.md documentation exists"""
        path = os.path.join(self.REPO_DIR, self.BASE, "README.md")
        assert os.path.exists(path), f"README.md not found"

    # === Semantic Checks ===

    def test_server_authorization_modes(self):
        """Verify both permissive and strict mTLS modes are defined"""
        path = os.path.join(self.REPO_DIR, self.BASE, "server-authorization.yaml")
        with open(path) as f:
            content = f.read().lower()

        assert "serverauthorization" in content or "authorization" in content, (
            "Should define ServerAuthorization resources"
        )
        mode_indicators = ["permissive", "strict", "unauthenticated", "authenticated"]
        found = [ind for ind in mode_indicators if ind in content]
        assert len(found) >= 1, (
            f"Should include permissive/strict modes. Found: {found}"
        )

    def test_server_resource_defined(self):
        """Verify Server resource definitions for mTLS services"""
        path = os.path.join(self.REPO_DIR, self.BASE, "server.yaml")
        with open(path) as f:
            content = f.read()

        assert "Server" in content, "Should define Server resources"
        server_indicators = ["port", "proxyProtocol", "selector"]
        found = [ind for ind in server_indicators if ind in content]
        assert len(found) >= 1, (
            f"Server should specify port/protocol/selector. Found: {found}"
        )

    def test_deployments_define_workloads(self):
        """Verify workload deployments are defined"""
        path = os.path.join(self.REPO_DIR, self.BASE, "deployments.yaml")
        with open(path) as f:
            content = f.read()

        assert "Deployment" in content, "Should define Deployment resources"
        assert "containers" in content or "container" in content, (
            "Deployments should define containers"
        )

    def test_verify_script_checks_mtls(self):
        """Verify verification script checks mTLS status"""
        path = os.path.join(self.REPO_DIR, self.BASE, "verify-mtls.sh")
        with open(path) as f:
            content = f.read()

        verify_indicators = [
            "linkerd", "check", "edges", "tap",
            "viz", "stat", "tls",
        ]
        found = [ind for ind in verify_indicators if ind in content]
        assert len(found) >= 2, (
            f"Script should verify mTLS status. Found: {found}"
        )

    def test_readme_explains_trust_hierarchy(self):
        """Verify README documents trust hierarchy and certificate management"""
        path = os.path.join(self.REPO_DIR, self.BASE, "README.md")
        with open(path) as f:
            content = f.read().lower()

        trust_indicators = [
            "trust", "certificate", "ca", "identity",
            "tls", "mutual", "mtls",
        ]
        found = [ind for ind in trust_indicators if ind in content]
        assert len(found) >= 3, (
            f"README should explain trust hierarchy. Found: {found}"
        )

    # === Functional Checks ===

    def test_yaml_files_valid(self):
        """Verify all YAML files are syntactically valid"""
        import yaml

        yaml_files = []
        base_dir = os.path.join(self.REPO_DIR, self.BASE)
        for root, _, files in os.walk(base_dir):
            for fname in files:
                if fname.endswith((".yaml", ".yml")):
                    yaml_files.append(os.path.join(root, fname))

        assert len(yaml_files) >= 3, (
            f"Should have at least 3 YAML files. Found: {len(yaml_files)}"
        )
        for yf in yaml_files:
            with open(yf) as f:
                try:
                    list(yaml.safe_load_all(f.read()))
                except yaml.YAMLError as e:
                    pytest.fail(f"Invalid YAML in {yf}: {e}")

    def test_verify_script_is_executable_format(self):
        """Verify verify-mtls.sh has proper shell script format"""
        path = os.path.join(self.REPO_DIR, self.BASE, "verify-mtls.sh")
        with open(path) as f:
            content = f.read()

        assert content.startswith("#!") or "#!/" in content[:50], (
            "verify-mtls.sh should have a shebang line"
        )
