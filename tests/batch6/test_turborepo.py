"""
Test skill: turborepo
Verify that the Agent correctly configures a Turborepo monorepo for a design system
with proper task pipelines, caching, environment variables, and CI workflow.
"""

import os
import re
import json
import subprocess
import pytest


class TestTurborepo:
    REPO_DIR = "/workspace/turbo"

    # === File Path Checks ===

    def test_turbo_json_exists(self):
        """Verify that turbo.json configuration file exists"""
        path = os.path.join(self.REPO_DIR, "turbo.json")
        assert os.path.exists(path), f"turbo.json not found at {path}"

    def test_root_package_json_exists(self):
        """Verify that root package.json exists"""
        path = os.path.join(self.REPO_DIR, "package.json")
        assert os.path.exists(path), f"Root package.json not found at {path}"

    def test_ui_package_json_exists(self):
        """Verify that packages/ui/package.json exists"""
        path = os.path.join(self.REPO_DIR, "packages/ui/package.json")
        assert os.path.exists(path), f"packages/ui/package.json not found at {path}"

    def test_utils_package_json_exists(self):
        """Verify that packages/utils/package.json exists"""
        path = os.path.join(self.REPO_DIR, "packages/utils/package.json")
        assert os.path.exists(path), f"packages/utils/package.json not found at {path}"

    def test_web_app_package_json_exists(self):
        """Verify that apps/web/package.json exists"""
        path = os.path.join(self.REPO_DIR, "apps/web/package.json")
        assert os.path.exists(path), f"apps/web/package.json not found at {path}"

    def test_docs_app_package_json_exists(self):
        """Verify that apps/docs/package.json exists"""
        path = os.path.join(self.REPO_DIR, "apps/docs/package.json")
        assert os.path.exists(path), f"apps/docs/package.json not found at {path}"

    def test_ci_workflow_exists(self):
        """Verify that GitHub Actions CI workflow file exists"""
        path = os.path.join(self.REPO_DIR, ".github/workflows/ci.yml")
        alt_path = os.path.join(self.REPO_DIR, ".github/workflows/ci.yaml")
        assert os.path.exists(path) or os.path.exists(alt_path), (
            f"CI workflow file not found at {path} or {alt_path}"
        )

    # === Semantic Checks ===

    def test_turbo_json_has_required_tasks(self):
        """Verify that turbo.json defines all required task pipelines"""
        path = os.path.join(self.REPO_DIR, "turbo.json")
        with open(path, "r") as f:
            turbo = json.load(f)

        # turbo.json may have tasks under "pipeline" (v1) or "tasks" (v2)
        tasks = turbo.get("tasks", turbo.get("pipeline", {}))
        assert isinstance(tasks, dict), "turbo.json should have tasks/pipeline object"

        required_tasks = ["build", "lint", "test", "dev"]
        for task in required_tasks:
            assert task in tasks, (
                f"turbo.json missing required task: {task}"
            )

    def test_turbo_build_depends_on_caret_build(self):
        """Verify that build task has ^build dependency (packages build before apps)"""
        path = os.path.join(self.REPO_DIR, "turbo.json")
        with open(path, "r") as f:
            turbo = json.load(f)

        tasks = turbo.get("tasks", turbo.get("pipeline", {}))
        build_task = tasks.get("build", {})
        depends_on = build_task.get("dependsOn", [])
        assert "^build" in depends_on, (
            f"build task should depend on '^build', got dependsOn: {depends_on}"
        )

    def test_turbo_dev_is_persistent_and_not_cached(self):
        """Verify that dev task is persistent: true and cache: false"""
        path = os.path.join(self.REPO_DIR, "turbo.json")
        with open(path, "r") as f:
            turbo = json.load(f)

        tasks = turbo.get("tasks", turbo.get("pipeline", {}))
        dev_task = tasks.get("dev", {})
        assert dev_task.get("persistent") == True, (
            "dev task should have persistent: true"
        )
        assert dev_task.get("cache") == False, (
            "dev task should have cache: false"
        )

    def test_turbo_build_has_outputs(self):
        """Verify that build task defines correct output directories for caching"""
        path = os.path.join(self.REPO_DIR, "turbo.json")
        with open(path, "r") as f:
            turbo = json.load(f)

        tasks = turbo.get("tasks", turbo.get("pipeline", {}))
        build_task = tasks.get("build", {})
        outputs = build_task.get("outputs", [])
        assert len(outputs) >= 1, (
            "build task should define outputs for caching"
        )
        # Check for common output patterns
        outputs_str = str(outputs)
        assert "dist" in outputs_str or ".next" in outputs_str or "storybook" in outputs_str, (
            f"build outputs should include dist/**, .next/**, or storybook-static/**. Got: {outputs}"
        )

    def test_root_package_json_uses_turbo_run(self):
        """Verify that root package.json scripts delegate via turbo run"""
        path = os.path.join(self.REPO_DIR, "package.json")
        with open(path, "r") as f:
            pkg = json.load(f)

        scripts = pkg.get("scripts", {})
        for task in ["build", "lint", "test"]:
            if task in scripts:
                assert "turbo" in scripts[task], (
                    f"Root script '{task}' should delegate via 'turbo run', "
                    f"got: {scripts[task]}"
                )

    def test_root_package_json_has_workspaces(self):
        """Verify that root package.json defines workspace directories"""
        path = os.path.join(self.REPO_DIR, "package.json")
        with open(path, "r") as f:
            pkg = json.load(f)

        workspaces = pkg.get("workspaces", [])
        if isinstance(workspaces, dict):
            workspaces = workspaces.get("packages", [])
        assert len(workspaces) >= 2, (
            f"Root package.json should define workspaces, got: {workspaces}"
        )
        workspaces_str = str(workspaces)
        assert "apps" in workspaces_str or "packages" in workspaces_str, (
            f"Workspaces should include apps/* and packages/*. Got: {workspaces}"
        )

    def test_ui_package_uses_workspace_deps(self):
        """Verify that apps/web depends on @myorg/ui via workspace protocol"""
        path = os.path.join(self.REPO_DIR, "apps/web/package.json")
        with open(path, "r") as f:
            pkg = json.load(f)

        deps = pkg.get("dependencies", {})
        # Check for workspace dependency (could be @myorg/ui or similar)
        has_workspace_dep = any(
            "workspace" in str(v) for v in deps.values()
        ) or any("@myorg" in k or "ui" in k for k in deps.keys())
        assert has_workspace_dep, (
            f"apps/web should depend on UI package via workspace:* protocol. "
            f"Dependencies: {deps}"
        )

    def test_ci_workflow_uses_affected(self):
        """Verify that CI workflow uses --affected flag for changed packages"""
        ci_path = None
        for ext in ["yml", "yaml"]:
            p = os.path.join(self.REPO_DIR, f".github/workflows/ci.{ext}")
            if os.path.exists(p):
                ci_path = p
                break

        assert ci_path is not None, "CI workflow file not found"
        with open(ci_path, "r") as f:
            content = f.read()

        assert "--affected" in content, (
            "CI workflow should use --affected flag for changed packages"
        )

    def test_ci_workflow_has_fetch_depth_zero(self):
        """Verify that CI checkout uses fetch-depth: 0 (needed for --affected)"""
        ci_path = None
        for ext in ["yml", "yaml"]:
            p = os.path.join(self.REPO_DIR, f".github/workflows/ci.{ext}")
            if os.path.exists(p):
                ci_path = p
                break

        assert ci_path is not None, "CI workflow file not found"
        with open(ci_path, "r") as f:
            content = f.read()

        assert "fetch-depth" in content and "0" in content, (
            "CI workflow checkout should use fetch-depth: 0 for --affected to work"
        )

    def test_turbo_json_has_environment_variables(self):
        """Verify that turbo.json declares environment variables for build task"""
        path = os.path.join(self.REPO_DIR, "turbo.json")
        with open(path, "r") as f:
            turbo = json.load(f)

        tasks = turbo.get("tasks", turbo.get("pipeline", {}))
        build_task = tasks.get("build", {})

        has_env = "env" in build_task or "passThroughEnv" in build_task
        assert has_env, (
            "build task should declare env or passThroughEnv variables"
        )

    def test_ui_package_has_peer_dependencies(self):
        """Verify that packages/ui defines peerDependencies for react"""
        path = os.path.join(self.REPO_DIR, "packages/ui/package.json")
        with open(path, "r") as f:
            pkg = json.load(f)

        peer_deps = pkg.get("peerDependencies", {})
        assert "react" in peer_deps, (
            f"packages/ui should declare react as peerDependency. "
            f"peerDependencies: {peer_deps}"
        )
