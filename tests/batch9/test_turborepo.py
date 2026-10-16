"""
Test skill: turborepo
Verify that the Agent correctly configures turbo.json pipeline, creates @cache-demo/ui package,
and sets workspace dependencies in the cache-demo example.
"""

import os
import subprocess
import json
import re
import pytest


class TestTurborepo:
    REPO_DIR = "/workspace/turbo"

    # === File Path Checks ===

    def test_turbo_json_exists(self):
        """Verify turbo.json exists in cache-demo example"""
        path = os.path.join(self.REPO_DIR, "examples/cache-demo/turbo.json")
        assert os.path.exists(path), f"turbo.json not found at {path}"

    def test_ui_package_directory_exists(self):
        """Verify @cache-demo/ui package directory exists"""
        candidates = [
            os.path.join(self.REPO_DIR, "examples/cache-demo/packages/ui"),
        ]
        found = any(os.path.isdir(c) for c in candidates)
        assert found, "packages/ui directory not found in cache-demo"

    def test_ui_package_json_exists(self):
        """Verify packages/ui/package.json exists"""
        path = os.path.join(self.REPO_DIR, "examples/cache-demo/packages/ui/package.json")
        assert os.path.exists(path), f"packages/ui/package.json not found"

    # === Semantic Checks ===

    def test_turbo_json_has_pipeline_tasks(self):
        """Verify turbo.json defines build, test, lint, dev pipeline tasks"""
        path = os.path.join(self.REPO_DIR, "examples/cache-demo/turbo.json")
        with open(path) as f:
            config = json.load(f)
        # turbo.json v2 uses "tasks", v1 uses "pipeline"
        tasks = config.get("tasks", config.get("pipeline", {}))
        expected = ["build", "test", "lint", "dev"]
        found = [t for t in expected if t in tasks]
        assert len(found) >= 3, (
            f"Expected pipeline tasks {expected}, found {found}. Config keys: {list(tasks.keys())}"
        )

    def test_turbo_json_build_has_deps_and_outputs(self):
        """Verify build task has dependsOn and outputs configured"""
        path = os.path.join(self.REPO_DIR, "examples/cache-demo/turbo.json")
        with open(path) as f:
            config = json.load(f)
        tasks = config.get("tasks", config.get("pipeline", {}))
        build = tasks.get("build", {})
        has_deps = "dependsOn" in build
        has_outputs = "outputs" in build
        assert has_deps, "build task missing dependsOn"
        assert has_outputs, "build task missing outputs"

    def test_turbo_json_dev_is_persistent(self):
        """Verify dev task is marked as persistent (not cached)"""
        path = os.path.join(self.REPO_DIR, "examples/cache-demo/turbo.json")
        with open(path) as f:
            config = json.load(f)
        tasks = config.get("tasks", config.get("pipeline", {}))
        dev = tasks.get("dev", {})
        is_persistent = dev.get("persistent", False) or dev.get("cache", True) is False
        assert is_persistent, "dev task should be persistent or have cache disabled"

    def test_ui_package_has_correct_name(self):
        """Verify ui package name is @cache-demo/ui"""
        path = os.path.join(self.REPO_DIR, "examples/cache-demo/packages/ui/package.json")
        with open(path) as f:
            pkg = json.load(f)
        name = pkg.get("name", "")
        assert "cache-demo" in name and "ui" in name, (
            f"UI package name should be @cache-demo/ui, got: {name}"
        )

    def test_workspace_dependencies_set(self):
        """Verify workspace apps depend on @cache-demo/ui"""
        apps_dir = os.path.join(self.REPO_DIR, "examples/cache-demo/apps")
        if not os.path.isdir(apps_dir):
            pytest.skip("apps directory not found")
        has_dependency = False
        for app in os.listdir(apps_dir):
            pkg_path = os.path.join(apps_dir, app, "package.json")
            if os.path.exists(pkg_path):
                with open(pkg_path) as f:
                    pkg = json.load(f)
                deps = pkg.get("dependencies", {})
                deps.update(pkg.get("devDependencies", {}))
                if any("ui" in k for k in deps):
                    has_dependency = True
                    break
        assert has_dependency, "No app depends on @cache-demo/ui package"

    # === Functional Checks ===

    def test_npm_install_succeeds(self):
        """Verify npm/yarn/pnpm install succeeds in cache-demo"""
        cache_demo = os.path.join(self.REPO_DIR, "examples/cache-demo")
        # Detect package manager
        if os.path.exists(os.path.join(cache_demo, "pnpm-lock.yaml")):
            cmd = ["pnpm", "install"]
        elif os.path.exists(os.path.join(cache_demo, "yarn.lock")):
            cmd = ["yarn", "install"]
        else:
            cmd = ["npm", "install"]
        result = subprocess.run(
            cmd,
            cwd=cache_demo,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, f"Install failed: {result.stderr[:500]}"

    def test_turbo_build_succeeds(self):
        """Verify turbo build runs successfully in cache-demo"""
        cache_demo = os.path.join(self.REPO_DIR, "examples/cache-demo")
        result = subprocess.run(
            ["npx", "turbo", "run", "build"],
            cwd=cache_demo,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, (
            f"turbo build failed:\n{result.stdout[-500:]}\n{result.stderr[-500:]}"
        )

    def test_turbo_lint_succeeds(self):
        """Verify turbo lint runs successfully"""
        cache_demo = os.path.join(self.REPO_DIR, "examples/cache-demo")
        result = subprocess.run(
            ["npx", "turbo", "run", "lint"],
            cwd=cache_demo,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, (
            f"turbo lint failed:\n{result.stdout[-500:]}\n{result.stderr[-500:]}"
        )

    def test_ui_package_exports_components(self):
        """Verify ui package has an index file that exports components"""
        ui_dir = os.path.join(self.REPO_DIR, "examples/cache-demo/packages/ui")
        index_candidates = ["index.ts", "index.tsx", "index.js", "src/index.ts", "src/index.tsx"]
        found = False
        for ic in index_candidates:
            path = os.path.join(ui_dir, ic)
            if os.path.exists(path):
                with open(path) as f:
                    content = f.read()
                if "export" in content:
                    found = True
                    break
        assert found, "UI package does not export any components"
