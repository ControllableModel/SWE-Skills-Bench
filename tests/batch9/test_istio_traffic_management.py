"""
Test skill: istio-traffic-management
Verify that the Agent creates VirtualService, DestinationRule, and Gateway
generators using Python/Pydantic for Istio traffic management.
"""

import os
import re
import ast
import subprocess
import pytest


class TestIstioTrafficManagement:
    REPO_DIR = "/workspace/istio"

    # === File Path Checks ===

    def test_istio_generator_files_exist(self):
        """Verify Istio traffic management generator files exist"""
        found = False
        for root, dirs, files in os.walk(self.REPO_DIR):
            if ".git" in root or "vendor" in root or "node_modules" in root:
                continue
            for f in files:
                if f.endswith(".py") and ("virtual" in f.lower() or "destination" in f.lower() or "gateway" in f.lower() or "traffic" in f.lower() or "istio" in f.lower()):
                    found = True
                    break
            if found:
                break
        assert found, "Istio generator Python files not found"

    # === Semantic Checks ===

    def test_virtual_service_generator_defined(self):
        """Verify VirtualService generator is implemented"""
        content = self._collect_python_content()
        assert "VirtualService" in content or "virtual_service" in content, "VirtualService generator not found"

    def test_destination_rule_generator_defined(self):
        """Verify DestinationRule generator is implemented"""
        content = self._collect_python_content()
        assert "DestinationRule" in content or "destination_rule" in content, "DestinationRule generator not found"

    def test_gateway_generator_defined(self):
        """Verify Gateway generator is implemented"""
        content = self._collect_python_content()
        assert "Gateway" in content or "gateway" in content, "Gateway generator not found"

    def test_pydantic_models_used(self):
        """Verify Pydantic models are used for configuration"""
        content = self._collect_python_content()
        has_pydantic = "BaseModel" in content or "pydantic" in content
        assert has_pydantic, "Pydantic models not used"

    def test_traffic_routing_defined(self):
        """Verify traffic routing configuration is defined"""
        content = self._collect_python_content()
        content_lower = content.lower()
        has_routing = (
            "route" in content_lower
            or "match" in content_lower
            or "weight" in content_lower
            or "subset" in content_lower
        )
        assert has_routing, "Traffic routing configuration not found"

    # === Functional Checks ===

    def test_python_files_valid_syntax(self):
        """Verify Python files have valid AST"""
        py_files = self._find_py_files()
        assert len(py_files) > 0, "No Istio generator Python files found"
        for pf in py_files:
            with open(pf) as fh:
                source = fh.read()
            try:
                ast.parse(source)
            except SyntaxError as e:
                pytest.fail(f"Syntax error in {pf}: {e}")

    def test_python_files_have_classes(self):
        """Verify Python files define classes"""
        py_files = self._find_py_files()
        any_class = False
        for pf in py_files:
            with open(pf) as fh:
                source = fh.read()
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    any_class = True
                    break
            if any_class:
                break
        assert any_class, "No classes found in Istio generator files"

    def test_yaml_output_capability(self):
        """Verify generators can produce YAML output"""
        content = self._collect_python_content()
        has_yaml = (
            "yaml" in content.lower()
            or "to_dict" in content
            or "to_yaml" in content
            or "json" in content.lower()
            or "apiVersion" in content
        )
        assert has_yaml, "No YAML/dict output capability found"

    def test_api_version_specified(self):
        """Verify Istio API version is specified"""
        content = self._collect_python_content()
        has_api = (
            "networking.istio.io" in content
            or "security.istio.io" in content
            or "apiVersion" in content
            or "api_version" in content
        )
        assert has_api, "Istio API version not specified"

    def _collect_python_content(self):
        all_content = ""
        for root, dirs, files in os.walk(self.REPO_DIR):
            if ".git" in root or "vendor" in root or "node_modules" in root:
                continue
            for f in files:
                if f.endswith(".py"):
                    fpath = os.path.join(root, f)
                    try:
                        with open(fpath) as fh:
                            c = fh.read()
                        if any(kw in c for kw in ["VirtualService", "DestinationRule", "Gateway", "virtual_service", "destination_rule", "gateway", "istio"]):
                            all_content += c + "\n"
                    except (UnicodeDecodeError, PermissionError):
                        continue
        return all_content

    def _find_py_files(self):
        py_files = []
        for root, dirs, files in os.walk(self.REPO_DIR):
            if ".git" in root or "vendor" in root or "node_modules" in root:
                continue
            for f in files:
                if f.endswith(".py") and ("virtual" in f.lower() or "destination" in f.lower() or "gateway" in f.lower() or "traffic" in f.lower() or "istio" in f.lower() or "model" in f.lower()):
                    py_files.append(os.path.join(root, f))
        return py_files
