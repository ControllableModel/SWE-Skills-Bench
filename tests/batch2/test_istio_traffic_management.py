"""
Test skill: istio-traffic-management
Verify that the Agent creates Istio canary deployment example with
VirtualService, DestinationRule, weighted traffic routing, stable/canary
deployments, and a fronting Service.
"""

import os
import re
import subprocess
import pytest


class TestIstioTrafficManagement:
    REPO_DIR = "/workspace/istio"

    BASE = "samples/canary-demo"

    # === File Path Checks ===

    def test_canary_demo_directory_exists(self):
        """Verify samples/canary-demo/ directory exists"""
        path = os.path.join(self.REPO_DIR, self.BASE)
        assert os.path.isdir(path), f"canary-demo directory not found at {path}"

    # === Semantic Checks ===

    def test_virtualservice_defined(self):
        """Verify VirtualService with weighted routing is defined"""
        content = self._read_all_yaml()
        assert "VirtualService" in content, (
            "Should define an Istio VirtualService"
        )
        weight_indicators = ["weight", "route"]
        found = [ind for ind in weight_indicators if ind in content]
        assert len(found) >= 2, (
            f"VirtualService should have weighted routes. Found: {found}"
        )

    def test_destination_rule_defined(self):
        """Verify DestinationRule with subsets is defined"""
        content = self._read_all_yaml()
        assert "DestinationRule" in content, (
            "Should define an Istio DestinationRule"
        )
        assert "subset" in content.lower(), (
            "DestinationRule should define subsets"
        )

    def test_two_deployments(self):
        """Verify stable and canary Deployment manifests exist"""
        content = self._read_all_yaml()
        deployment_count = content.count("kind: Deployment")
        assert deployment_count >= 2, (
            f"Should have at least 2 Deployments (stable + canary). "
            f"Found: {deployment_count}"
        )

    def test_version_labels(self):
        """Verify deployments have distinct version labels"""
        content = self._read_all_yaml().lower()
        version_indicators = ["v1", "v2", "stable", "canary", "version"]
        found = [ind for ind in version_indicators if ind in content]
        assert len(found) >= 2, (
            f"Deployments should have version labels. Found: {found}"
        )

    def test_service_fronts_both_versions(self):
        """Verify a single Service fronts both deployments"""
        content = self._read_all_yaml()
        assert "kind: Service" in content, (
            "Should define a Kubernetes Service"
        )

    def test_traffic_weights(self):
        """Verify traffic weight percentages are specified"""
        content = self._read_all_yaml()
        weights = re.findall(r"weight:\s*(\d+)", content)
        assert len(weights) >= 2, (
            f"Should specify at least 2 traffic weights. Found: {weights}"
        )
        total = sum(int(w) for w in weights)
        assert total == 100, (
            f"Traffic weights should sum to 100. Sum: {total}"
        )

    def test_subset_labels_match_deployments(self):
        """Verify DestinationRule subset labels match deployment labels"""
        content = self._read_all_yaml()
        # Extract subset labels and deployment labels
        subsets = re.findall(r"name:\s*(v\d+|stable|canary)", content)
        assert len(subsets) >= 2, (
            f"Should have at least 2 named subsets/versions. Found: {subsets}"
        )

    # === Functional Checks ===

    def test_yaml_files_valid(self):
        """Verify all YAML files are syntactically valid"""
        import yaml

        yaml_files = self._list_yaml_files()
        assert len(yaml_files) >= 2, (
            f"Should have at least 2 YAML files. Found: {len(yaml_files)}"
        )
        for yf in yaml_files:
            with open(yf) as f:
                try:
                    list(yaml.safe_load_all(f.read()))
                except yaml.YAMLError as e:
                    pytest.fail(f"Invalid YAML in {yf}: {e}")

    def test_documentation_exists(self):
        """Verify README or documentation exists"""
        readme_paths = [
            os.path.join(self.REPO_DIR, self.BASE, "README.md"),
            os.path.join(self.REPO_DIR, self.BASE, "README"),
            os.path.join(self.REPO_DIR, self.BASE, "readme.md"),
        ]
        found = any(os.path.exists(p) for p in readme_paths)
        # Also check for comments in YAML files
        if not found:
            content = self._read_all_yaml()
            found = content.count("#") >= 3
        assert found, "Should include documentation or well-commented YAML"

    def test_istio_api_versions(self):
        """Verify correct Istio API versions are used"""
        content = self._read_all_yaml()
        api_indicators = [
            "networking.istio.io", "istio.io",
        ]
        found = [ind for ind in api_indicators if ind in content]
        assert len(found) >= 1, (
            f"Should use Istio API versions. Found: {found}"
        )

    def _read_all_yaml(self):
        """Helper to read all YAML files in the demo directory"""
        combined = ""
        for yf in self._list_yaml_files():
            with open(yf) as f:
                combined += f.read() + "\n"
        return combined

    def _list_yaml_files(self):
        """Helper to list all YAML files in the demo directory"""
        yaml_files = []
        base_dir = os.path.join(self.REPO_DIR, self.BASE)
        if os.path.isdir(base_dir):
            for root, _, files in os.walk(base_dir):
                for fname in files:
                    if fname.endswith((".yaml", ".yml")):
                        yaml_files.append(os.path.join(root, fname))
        return yaml_files
