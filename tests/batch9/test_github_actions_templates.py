"""
Test skill: github-actions-templates
Verify that the Agent creates 4 workflow YAML files and 4 properties.json files for starter-workflows.
"""

import os
import subprocess
import json
import re
import pytest

try:
    import yaml
except ImportError:
    yaml = None


class TestGithubActionsTemplates:
    REPO_DIR = "/workspace/starter-workflows"

    # === File Path Checks ===

    def test_fastapi_ci_workflow_exists(self):
        """Verify FastAPI CI workflow YAML exists"""
        candidates = [
            os.path.join(self.REPO_DIR, "ci/fastapi-ci.yml"),
            os.path.join(self.REPO_DIR, "ci/fastapi.yml"),
        ]
        found = any(os.path.exists(c) for c in candidates)
        assert found, f"FastAPI CI workflow not found. Checked: {candidates}"

    def test_react_vite_ci_workflow_exists(self):
        """Verify React Vite CI workflow YAML exists"""
        found = False
        ci_dir = os.path.join(self.REPO_DIR, "ci")
        if os.path.isdir(ci_dir):
            for f in os.listdir(ci_dir):
                if "react" in f.lower() and "vite" in f.lower():
                    found = True
                    break
                if "react" in f.lower() and f.endswith((".yml", ".yaml")):
                    found = True
                    break
        assert found, "React Vite CI workflow not found in ci/"

    def test_ecs_deploy_workflow_exists(self):
        """Verify ECS deploy workflow YAML exists"""
        found = False
        deploy_dirs = ["deployments", "ci"]
        for dd in deploy_dirs:
            d = os.path.join(self.REPO_DIR, dd)
            if os.path.isdir(d):
                for f in os.listdir(d):
                    if "ecs" in f.lower() and f.endswith((".yml", ".yaml")):
                        found = True
                        break
        assert found, "ECS deploy workflow not found"

    def test_dependency_review_workflow_exists(self):
        """Verify dependency review workflow YAML exists"""
        found = False
        for root, dirs, files in os.walk(self.REPO_DIR):
            if ".git" in root:
                continue
            for f in files:
                if "dependency" in f.lower() and "review" in f.lower() and f.endswith((".yml", ".yaml")):
                    found = True
                    break
            if found:
                break
        assert found, "Dependency review workflow not found"

    # === Semantic Checks ===

    def test_fastapi_ci_has_python_setup(self):
        """Verify FastAPI CI sets up Python and installs dependencies"""
        ci_dir = os.path.join(self.REPO_DIR, "ci")
        workflow_file = None
        for f in os.listdir(ci_dir):
            if "fastapi" in f.lower() and f.endswith((".yml", ".yaml")):
                workflow_file = os.path.join(ci_dir, f)
                break
        assert workflow_file is not None, "FastAPI CI workflow not found"
        with open(workflow_file) as fh:
            content = fh.read()
        assert "setup-python" in content or "python-version" in content, (
            "FastAPI CI missing Python setup step"
        )
        assert "pip install" in content or "requirements" in content or "poetry" in content, (
            "FastAPI CI missing dependency installation"
        )

    def test_workflows_have_proper_triggers(self):
        """Verify workflows have on: push/pull_request triggers"""
        ci_dir = os.path.join(self.REPO_DIR, "ci")
        if not os.path.isdir(ci_dir):
            pytest.skip("ci directory not found")
        for f in os.listdir(ci_dir):
            if f.endswith((".yml", ".yaml")):
                fpath = os.path.join(ci_dir, f)
                with open(fpath) as fh:
                    content = fh.read()
                has_trigger = ("on:" in content or "push:" in content or "pull_request:" in content
                               or "workflow_dispatch:" in content)
                assert has_trigger, f"{f} missing workflow trigger (on: push/pull_request)"

    def test_properties_json_files_exist(self):
        """Verify each workflow has a corresponding properties.json"""
        workflow_dirs = ["ci", "deployments"]
        yml_files = []
        for wd in workflow_dirs:
            d = os.path.join(self.REPO_DIR, wd)
            if os.path.isdir(d):
                for f in os.listdir(d):
                    if f.endswith((".yml", ".yaml")):
                        yml_files.append(os.path.join(d, f))
        # Check that at least some have properties.json files nearby
        props_found = 0
        for yml in yml_files:
            base = os.path.splitext(yml)[0]
            props_path = base + ".properties.json"
            if os.path.exists(props_path):
                props_found += 1
        agent_yml_count = min(len(yml_files), 4)
        assert props_found >= 3, (
            f"Only {props_found} properties.json files found for {len(yml_files)} workflows"
        )

    def test_properties_json_has_required_fields(self):
        """Verify properties.json files contain name and description"""
        props_files = []
        for root, dirs, files in os.walk(self.REPO_DIR):
            if ".git" in root:
                continue
            for f in files:
                if f.endswith(".properties.json"):
                    props_files.append(os.path.join(root, f))
        assert len(props_files) > 0, "No properties.json files found"
        for pf in props_files[:4]:
            with open(pf) as fh:
                data = json.load(fh)
            assert "name" in data, f"{pf} missing 'name' field"
            assert "description" in data, f"{pf} missing 'description' field"

    # === Functional Checks ===

    def test_yaml_files_are_valid(self):
        """Verify all workflow YAML files are valid YAML"""
        if yaml is None:
            pytest.skip("PyYAML not installed")
        for root, dirs, files in os.walk(self.REPO_DIR):
            if ".git" in root:
                continue
            for f in files:
                if f.endswith((".yml", ".yaml")):
                    fpath = os.path.join(root, f)
                    with open(fpath) as fh:
                        try:
                            yaml.safe_load(fh)
                        except yaml.YAMLError as e:
                            pytest.fail(f"Invalid YAML in {fpath}: {e}")

    def test_ecs_deploy_references_aws_actions(self):
        """Verify ECS deploy workflow uses AWS-related actions"""
        deploy_dirs = ["deployments", "ci"]
        ecs_file = None
        for dd in deploy_dirs:
            d = os.path.join(self.REPO_DIR, dd)
            if os.path.isdir(d):
                for f in os.listdir(d):
                    if "ecs" in f.lower() and f.endswith((".yml", ".yaml")):
                        ecs_file = os.path.join(d, f)
                        break
        assert ecs_file is not None, "ECS deploy workflow not found"
        with open(ecs_file) as fh:
            content = fh.read()
        has_aws = (
            "aws-actions" in content
            or "configure-aws-credentials" in content
            or "amazon-ecs" in content
            or "ecr" in content.lower()
        )
        assert has_aws, "ECS deploy workflow missing AWS-related actions"

    def test_dependency_review_uses_correct_action(self):
        """Verify dependency review workflow uses actions/dependency-review-action"""
        dep_file = None
        for root, dirs, files in os.walk(self.REPO_DIR):
            if ".git" in root:
                continue
            for f in files:
                if "dependency" in f.lower() and f.endswith((".yml", ".yaml")):
                    dep_file = os.path.join(root, f)
                    break
            if dep_file:
                break
        assert dep_file is not None
        with open(dep_file) as fh:
            content = fh.read()
        assert "dependency-review-action" in content, (
            "Dependency review workflow missing dependency-review-action"
        )
