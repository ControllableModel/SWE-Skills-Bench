"""
Test skill: github-actions-templates
Verify that the Agent correctly creates reusable CI/CD workflow templates
for Node.js libraries in the GitHub Actions starter-workflows repository.
"""

import os
import re
import json
import subprocess
import pytest


class TestGithubActionsTemplates:
    REPO_DIR = "/workspace/starter-workflows"

    # === File Path Checks ===

    def test_ci_workflow_exists(self):
        """Verify CI workflow template exists"""
        fpath = os.path.join(self.REPO_DIR, "ci/node-library-ci.yml")
        assert os.path.isfile(fpath), f"CI workflow not found at {fpath}"

    def test_publish_workflow_exists(self):
        """Verify publish workflow template exists"""
        fpath = os.path.join(self.REPO_DIR, "deployments/node-library-publish.yml")
        assert os.path.isfile(fpath), f"Publish workflow not found at {fpath}"

    def test_ci_properties_exists(self):
        """Verify CI properties.json exists"""
        fpath = os.path.join(self.REPO_DIR, "ci/node-library-ci.properties.json")
        assert os.path.isfile(fpath), f"CI properties.json not found at {fpath}"

    def test_publish_properties_exists(self):
        """Verify publish properties.json exists"""
        fpath = os.path.join(self.REPO_DIR, "deployments/node-library-publish.properties.json")
        assert os.path.isfile(fpath), f"Publish properties.json not found at {fpath}"

    # === Semantic Checks ===

    def test_ci_workflow_has_matrix_strategy(self):
        """Verify CI workflow defines matrix for Node.js 18, 20, and 22"""
        fpath = os.path.join(self.REPO_DIR, "ci/node-library-ci.yml")
        with open(fpath, "r") as f:
            content = f.read()
        assert "matrix" in content, "CI workflow should use matrix strategy"
        for version in ["18", "20", "22"]:
            assert version in content, f"CI workflow matrix should include Node.js {version}"
        assert "fail-fast" in content, "CI workflow should set fail-fast: false"

    def test_ci_workflow_has_required_steps(self):
        """Verify CI workflow has checkout, setup-node, npm ci, npm test, npm audit steps"""
        fpath = os.path.join(self.REPO_DIR, "ci/node-library-ci.yml")
        with open(fpath, "r") as f:
            content = f.read()
        assert "actions/checkout" in content, "CI workflow should use actions/checkout"
        assert "actions/setup-node" in content, "CI workflow should use actions/setup-node"
        assert "npm ci" in content, "CI workflow should run 'npm ci'"
        assert "npm test" in content, "CI workflow should run 'npm test'"
        assert "npm audit" in content, "CI workflow should run 'npm audit'"

    def test_ci_workflow_has_concurrency(self):
        """Verify CI workflow defines concurrency group"""
        fpath = os.path.join(self.REPO_DIR, "ci/node-library-ci.yml")
        with open(fpath, "r") as f:
            content = f.read()
        assert "concurrency" in content, "CI workflow should define concurrency group"

    def test_ci_workflow_has_correct_triggers(self):
        """Verify CI workflow triggers on push and pull_request to main/master"""
        fpath = os.path.join(self.REPO_DIR, "ci/node-library-ci.yml")
        with open(fpath, "r") as f:
            content = f.read()
        assert "push" in content, "CI workflow should trigger on push"
        assert "pull_request" in content, "CI workflow should trigger on pull_request"

    def test_publish_workflow_triggers_on_version_tags(self):
        """Verify publish workflow triggers on v*.*.* tags"""
        fpath = os.path.join(self.REPO_DIR, "deployments/node-library-publish.yml")
        with open(fpath, "r") as f:
            content = f.read()
        has_tag_trigger = bool(re.search(r'v\*\.\*\.\*|tags', content))
        assert has_tag_trigger, "Publish workflow should trigger on version tags (v*.*.*)"

    def test_publish_workflow_has_npm_publish(self):
        """Verify publish workflow runs npm publish with auth token"""
        fpath = os.path.join(self.REPO_DIR, "deployments/node-library-publish.yml")
        with open(fpath, "r") as f:
            content = f.read()
        assert "npm publish" in content, "Publish workflow should run 'npm publish'"
        assert "NODE_AUTH_TOKEN" in content, "Publish workflow should use NODE_AUTH_TOKEN"
        assert "NPM_TOKEN" in content, "Publish workflow should reference NPM_TOKEN secret"

    def test_publish_workflow_verifies_version(self):
        """Verify publish workflow checks tag version matches package.json"""
        fpath = os.path.join(self.REPO_DIR, "deployments/node-library-publish.yml")
        with open(fpath, "r") as f:
            content = f.read()
        has_version_check = bool(re.search(r'(package\.json|version.*match|tag.*version)', content, re.IGNORECASE))
        assert has_version_check, "Publish workflow should verify tag-to-package.json version consistency"

    def test_publish_workflow_creates_github_release(self):
        """Verify publish workflow creates a GitHub Release"""
        fpath = os.path.join(self.REPO_DIR, "deployments/node-library-publish.yml")
        with open(fpath, "r") as f:
            content = f.read()
        has_release = bool(re.search(r'(create-release|gh release|softprops/action-gh-release)', content, re.IGNORECASE))
        assert has_release, "Publish workflow should create a GitHub Release"

    def test_ci_properties_json_valid(self):
        """Verify CI properties.json has required fields with correct categories"""
        fpath = os.path.join(self.REPO_DIR, "ci/node-library-ci.properties.json")
        with open(fpath, "r") as f:
            props = json.load(f)
        assert "name" in props, "Properties missing 'name'"
        assert "description" in props, "Properties missing 'description'"
        assert "iconName" in props, "Properties missing 'iconName'"
        assert "categories" in props, "Properties missing 'categories'"
        assert isinstance(props["categories"], list), "categories should be an array"
        cats = [c.lower() for c in props["categories"]]
        assert any("node" in c for c in cats), f"CI categories should include 'Node.js'. Got: {props['categories']}"

    def test_publish_properties_json_valid(self):
        """Verify publish properties.json has required fields with correct categories"""
        fpath = os.path.join(self.REPO_DIR, "deployments/node-library-publish.properties.json")
        with open(fpath, "r") as f:
            props = json.load(f)
        assert "name" in props, "Properties missing 'name'"
        assert "description" in props, "Properties missing 'description'"
        assert "categories" in props, "Properties missing 'categories'"
        cats = [c.lower() for c in props["categories"]]
        assert any("npm" in c or "deploy" in c for c in cats), (
            f"Publish categories should include 'npm' or 'Deployment'. Got: {props['categories']}"
        )

    def test_ci_workflow_has_minimal_permissions(self):
        """Verify CI workflow sets permissions to contents: read"""
        fpath = os.path.join(self.REPO_DIR, "ci/node-library-ci.yml")
        with open(fpath, "r") as f:
            content = f.read()
        assert "permissions" in content, "CI workflow should declare permissions"
        assert "read" in content, "CI workflow permissions should include 'contents: read'"

    # === Functional Checks ===

    def test_ci_workflow_is_valid_yaml(self):
        """Verify CI workflow is valid YAML"""
        import yaml
        fpath = os.path.join(self.REPO_DIR, "ci/node-library-ci.yml")
        with open(fpath, "r") as f:
            try:
                data = yaml.safe_load(f)
            except yaml.YAMLError as e:
                pytest.fail(f"CI workflow is not valid YAML: {e}")
        assert isinstance(data, dict), "CI workflow should parse to a dict"
        assert "on" in data or True in data, "CI workflow should have 'on' trigger"
        assert "jobs" in data, "CI workflow should have 'jobs' section"

    def test_publish_workflow_is_valid_yaml(self):
        """Verify publish workflow is valid YAML"""
        import yaml
        fpath = os.path.join(self.REPO_DIR, "deployments/node-library-publish.yml")
        with open(fpath, "r") as f:
            try:
                data = yaml.safe_load(f)
            except yaml.YAMLError as e:
                pytest.fail(f"Publish workflow is not valid YAML: {e}")
        assert isinstance(data, dict), "Publish workflow should parse to a dict"
        assert "jobs" in data, "Publish workflow should have 'jobs' section"

    def test_ci_workflow_uses_cache_action(self):
        """Verify CI workflow uses dependency caching"""
        fpath = os.path.join(self.REPO_DIR, "ci/node-library-ci.yml")
        with open(fpath, "r") as f:
            content = f.read()
        has_cache = bool(re.search(r'(actions/cache|cache.*npm|setup-node.*cache)', content))
        assert has_cache, "CI workflow should cache npm dependencies"
