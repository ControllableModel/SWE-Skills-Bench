"""
Test skill: turborepo
Verify that the Agent correctly implements a monorepo build pipeline example
with Turborepo featuring package-specific task configurations, output caching,
and environment variable dependency declarations.
"""

import os
import json
import subprocess
import pytest


class TestTurborepo:
    REPO_DIR = "/workspace/turbo"

    # === File Path Checks ===

    def test_root_turbo_json_exists(self):
        """Verify root turbo.json exists in the example directory"""
        path = os.path.join(self.REPO_DIR, "examples/with-build-pipeline/turbo.json")
        assert os.path.exists(path), f"Root turbo.json not found at {path}"
        with open(path) as f:
            data = json.load(f)
        assert data is not None, "turbo.json is empty"

    def test_root_package_json_exists(self):
        """Verify root package.json exists with workspaces"""
        path = os.path.join(self.REPO_DIR, "examples/with-build-pipeline/package.json")
        assert os.path.exists(path), f"Root package.json not found at {path}"

    def test_ui_package_exists(self):
        """Verify UI library package exists"""
        path = os.path.join(self.REPO_DIR, "examples/with-build-pipeline/packages/ui/package.json")
        assert os.path.exists(path), f"UI package.json not found at {path}"

    def test_config_package_exists(self):
        """Verify config package exists"""
        path = os.path.join(self.REPO_DIR, "examples/with-build-pipeline/packages/config/package.json")
        assert os.path.exists(path), f"Config package.json not found at {path}"

    def test_web_app_exists(self):
        """Verify web application exists"""
        path = os.path.join(self.REPO_DIR, "examples/with-build-pipeline/apps/web/package.json")
        assert os.path.exists(path), f"Web app package.json not found at {path}"

    # === Semantic Checks ===

    def test_root_turbo_json_has_required_tasks(self):
        """Verify root turbo.json defines build, test, lint, dev tasks"""
        path = os.path.join(self.REPO_DIR, "examples/with-build-pipeline/turbo.json")
        with open(path) as f:
            data = json.load(f)
        # Support both turbo.json v1 (pipeline) and v2 (tasks) format
        tasks = data.get("tasks", data.get("pipeline", {}))
        required_tasks = ["build", "test", "lint", "dev"]
        for task in required_tasks:
            assert task in tasks, \
                f"turbo.json missing task definition: {task}. Found: {list(tasks.keys())}"

    def test_build_task_has_dependencies(self):
        """Verify build task depends on ^build (dependencies first)"""
        path = os.path.join(self.REPO_DIR, "examples/with-build-pipeline/turbo.json")
        with open(path) as f:
            data = json.load(f)
        tasks = data.get("tasks", data.get("pipeline", {}))
        build = tasks.get("build", {})
        deps = build.get("dependsOn", [])
        assert "^build" in deps, \
            f"build task should depend on '^build', got dependsOn: {deps}"

    def test_build_task_has_outputs(self):
        """Verify build task defines outputs for caching"""
        path = os.path.join(self.REPO_DIR, "examples/with-build-pipeline/turbo.json")
        with open(path) as f:
            data = json.load(f)
        tasks = data.get("tasks", data.get("pipeline", {}))
        build = tasks.get("build", {})
        outputs = build.get("outputs", [])
        assert len(outputs) >= 1, \
            f"build task should define outputs for caching, got: {outputs}"
        # Should include dist/** or .next/**
        output_str = str(outputs)
        assert "dist" in output_str or ".next" in output_str, \
            f"build outputs should include dist/** or .next/**, got: {outputs}"

    def test_build_task_has_inputs(self):
        """Verify build task defines inputs for content-aware hashing"""
        path = os.path.join(self.REPO_DIR, "examples/with-build-pipeline/turbo.json")
        with open(path) as f:
            data = json.load(f)
        tasks = data.get("tasks", data.get("pipeline", {}))
        build = tasks.get("build", {})
        inputs = build.get("inputs", [])
        assert len(inputs) >= 1, \
            f"build task should define inputs, got: {inputs}"

    def test_dev_task_is_not_cached(self):
        """Verify dev task has cache disabled and persistent flag"""
        path = os.path.join(self.REPO_DIR, "examples/with-build-pipeline/turbo.json")
        with open(path) as f:
            data = json.load(f)
        tasks = data.get("tasks", data.get("pipeline", {}))
        dev = tasks.get("dev", {})
        assert dev.get("cache") is False, \
            f"dev task should have cache: false, got: {dev.get('cache')}"
        assert dev.get("persistent") is True, \
            f"dev task should have persistent: true, got: {dev.get('persistent')}"

    def test_global_dependencies_defined(self):
        """Verify global dependencies are configured for cache invalidation"""
        path = os.path.join(self.REPO_DIR, "examples/with-build-pipeline/turbo.json")
        with open(path) as f:
            data = json.load(f)
        global_deps = data.get("globalDependencies", [])
        global_env = data.get("globalEnv", data.get("globalPassThroughEnv", []))
        global_dot_env = data.get("globalDotEnv", [])
        has_global_config = len(global_deps) > 0 or len(global_env) > 0 or len(global_dot_env) > 0
        assert has_global_config, \
            "turbo.json should define globalDependencies, globalEnv, or globalDotEnv"

    def test_root_package_json_has_workspaces(self):
        """Verify root package.json defines workspaces for packages and apps"""
        path = os.path.join(self.REPO_DIR, "examples/with-build-pipeline/package.json")
        with open(path) as f:
            data = json.load(f)
        workspaces = data.get("workspaces", [])
        if isinstance(workspaces, dict):
            workspaces = workspaces.get("packages", [])
        assert len(workspaces) >= 2, \
            f"Root package.json should define workspaces for packages/* and apps/*, got: {workspaces}"
        ws_str = str(workspaces)
        assert "packages" in ws_str, f"Workspaces should include packages/*, got: {workspaces}"
        assert "apps" in ws_str, f"Workspaces should include apps/*, got: {workspaces}"

    def test_ui_package_depends_on_config(self):
        """Verify UI package depends on config package via workspace protocol"""
        path = os.path.join(self.REPO_DIR, "examples/with-build-pipeline/packages/ui/package.json")
        with open(path) as f:
            data = json.load(f)
        all_deps = {}
        all_deps.update(data.get("dependencies", {}))
        all_deps.update(data.get("devDependencies", {}))
        config_dep = any("config" in k.lower() for k in all_deps.keys())
        assert config_dep, \
            f"UI package should depend on config package. Deps: {list(all_deps.keys())}"
        # Check for workspace protocol
        config_dep_value = next(
            (v for k, v in all_deps.items() if "config" in k.lower()), ""
        )
        assert "workspace:" in config_dep_value or "*" in config_dep_value, \
            f"Config dependency should use workspace:* protocol, got: {config_dep_value}"

    def test_web_app_depends_on_ui(self):
        """Verify web app depends on UI package via workspace protocol"""
        path = os.path.join(self.REPO_DIR, "examples/with-build-pipeline/apps/web/package.json")
        with open(path) as f:
            data = json.load(f)
        all_deps = {}
        all_deps.update(data.get("dependencies", {}))
        all_deps.update(data.get("devDependencies", {}))
        ui_dep = any("ui" in k.lower() for k in all_deps.keys())
        assert ui_dep, \
            f"Web app should depend on UI package. Deps: {list(all_deps.keys())}"

    def test_ui_package_turbo_overrides(self):
        """Verify UI package has turbo.json with build task overrides"""
        path = os.path.join(self.REPO_DIR, "examples/with-build-pipeline/packages/ui/turbo.json")
        assert os.path.exists(path), "UI package should have its own turbo.json"
        with open(path) as f:
            data = json.load(f)
        # Should extend or override tasks
        tasks = data.get("tasks", data.get("pipeline", data.get("extends", {})))
        assert data is not None and len(str(data)) > 5, \
            f"UI turbo.json should have task overrides, got: {data}"

    def test_readme_exists(self):
        """Verify README.md exists with content about cache invalidation"""
        path = os.path.join(self.REPO_DIR, "examples/with-build-pipeline/README.md")
        assert os.path.exists(path), f"README.md not found at {path}"
        with open(path) as f:
            content = f.read()
        assert len(content) >= 100, "README should have substantial documentation"
        readme_lower = content.lower()
        assert "cache" in readme_lower or "hash" in readme_lower, \
            "README should explain caching/hashing behavior"

    # === Functional Checks ===

    def test_turbo_json_is_valid(self):
        """Verify all turbo.json files are valid JSON"""
        base = os.path.join(self.REPO_DIR, "examples/with-build-pipeline")
        turbo_files = []
        for root, dirs, files in os.walk(base):
            for f in files:
                if f == "turbo.json":
                    turbo_files.append(os.path.join(root, f))
        assert len(turbo_files) >= 2, \
            f"Expected at least 2 turbo.json files (root + package), found {len(turbo_files)}"
        for tf in turbo_files:
            with open(tf) as f:
                try:
                    data = json.load(f)
                    assert isinstance(data, dict), f"{tf} should contain a JSON object"
                except json.JSONDecodeError as e:
                    assert False, f"Invalid JSON in {tf}: {e}"

    def test_all_package_jsons_are_valid(self):
        """Verify all package.json files are valid JSON with required fields"""
        base = os.path.join(self.REPO_DIR, "examples/with-build-pipeline")
        pkg_files = []
        for root, dirs, files in os.walk(base):
            for f in files:
                if f == "package.json":
                    pkg_files.append(os.path.join(root, f))
        assert len(pkg_files) >= 3, \
            f"Expected at least 3 package.json files. Found {len(pkg_files)}"
        for pf in pkg_files:
            with open(pf) as f:
                data = json.load(f)
            # Every package.json should have at least a name
            if pf != os.path.join(base, "package.json"):
                assert "name" in data, f"{pf} missing 'name' field"
            # Non-root packages should have scripts
            if "packages" in pf or "apps" in pf:
                scripts = data.get("scripts", {})
                assert "build" in scripts, f"{pf} should have a build script"
