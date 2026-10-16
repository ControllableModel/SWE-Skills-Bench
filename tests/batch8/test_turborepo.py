"""
Test skill: turborepo
Verify that the Agent correctly creates a Turborepo-managed monorepo example
with shared UI package and two apps, properly configured task pipelines and caching.
"""

import os
import subprocess
import json
import re
import pytest


class TestTurborepo:
    REPO_DIR = "/workspace/turbo"
    EXAMPLE_DIR = "/workspace/turbo/examples/with-shared-ui"

    # === File Path Checks ===

    def test_turbo_json_exists(self):
        """Verify that turbo.json exists in the example directory"""
        filepath = os.path.join(self.EXAMPLE_DIR, "turbo.json")
        assert os.path.exists(filepath), f"turbo.json not found at {filepath}"

    def test_root_package_json_exists(self):
        """Verify that root package.json exists"""
        filepath = os.path.join(self.EXAMPLE_DIR, "package.json")
        assert os.path.exists(filepath), f"package.json not found at {filepath}"

    def test_shared_ui_package_exists(self):
        """Verify that the shared UI package directory structure exists"""
        ui_dir = os.path.join(self.EXAMPLE_DIR, "packages/ui")
        assert os.path.exists(ui_dir), f"packages/ui not found at {ui_dir}"
        assert os.path.exists(os.path.join(ui_dir, "package.json")), "packages/ui/package.json not found"

    def test_web_app_exists(self):
        """Verify that the web app directory exists"""
        web_dir = os.path.join(self.EXAMPLE_DIR, "apps/web")
        assert os.path.exists(web_dir), f"apps/web not found at {web_dir}"
        assert os.path.exists(os.path.join(web_dir, "package.json")), "apps/web/package.json not found"

    def test_docs_app_exists(self):
        """Verify that the docs app directory exists"""
        docs_dir = os.path.join(self.EXAMPLE_DIR, "apps/docs")
        assert os.path.exists(docs_dir), f"apps/docs not found at {docs_dir}"
        assert os.path.exists(os.path.join(docs_dir, "package.json")), "apps/docs/package.json not found"

    # === Semantic Checks ===

    def test_turbo_json_defines_tasks(self):
        """Verify turbo.json defines build, lint, test, and typecheck tasks"""
        filepath = os.path.join(self.EXAMPLE_DIR, "turbo.json")
        with open(filepath) as f:
            data = json.load(f)

        # turbo.json v2 uses "tasks" key, v1 uses "pipeline"
        tasks = data.get("tasks", data.get("pipeline", {}))
        required_tasks = ["build", "lint", "test", "typecheck"]
        for task in required_tasks:
            assert task in tasks, (
                f"turbo.json missing task definition for '{task}'. "
                f"Found tasks: {list(tasks.keys())}"
            )

    def test_turbo_build_task_has_dependencies(self):
        """Verify build task has dependsOn: ['^build'] for topological ordering"""
        filepath = os.path.join(self.EXAMPLE_DIR, "turbo.json")
        with open(filepath) as f:
            data = json.load(f)

        tasks = data.get("tasks", data.get("pipeline", {}))
        build_task = tasks.get("build", {})
        depends_on = build_task.get("dependsOn", [])
        assert "^build" in depends_on, (
            f"build task should have dependsOn: ['^build']. Found: {depends_on}"
        )

    def test_turbo_build_task_has_outputs(self):
        """Verify build task declares appropriate output directories"""
        filepath = os.path.join(self.EXAMPLE_DIR, "turbo.json")
        with open(filepath) as f:
            data = json.load(f)

        tasks = data.get("tasks", data.get("pipeline", {}))
        build_task = tasks.get("build", {})
        outputs = build_task.get("outputs", [])
        assert len(outputs) > 0, (
            "build task should declare outputs (e.g., dist/**, .next/**)"
        )
        output_str = str(outputs)
        assert "dist" in output_str or ".next" in output_str, (
            f"build task outputs should include dist/** or .next/**. Found: {outputs}"
        )

    def test_root_package_json_delegates_to_turbo(self):
        """Verify root package.json scripts delegate to turbo run"""
        filepath = os.path.join(self.EXAMPLE_DIR, "package.json")
        with open(filepath) as f:
            data = json.load(f)

        scripts = data.get("scripts", {})
        for script_name in ["build", "lint"]:
            if script_name in scripts:
                assert "turbo" in scripts[script_name], (
                    f"Root script '{script_name}' should delegate to turbo. "
                    f"Found: '{scripts[script_name]}'"
                )

    def test_root_package_json_has_workspaces(self):
        """Verify root package.json defines workspaces"""
        filepath = os.path.join(self.EXAMPLE_DIR, "package.json")
        with open(filepath) as f:
            data = json.load(f)

        workspaces = data.get("workspaces", [])
        if isinstance(workspaces, dict):
            workspaces = workspaces.get("packages", [])
        assert len(workspaces) >= 2, (
            f"Root package.json should define at least 2 workspace patterns. Found: {workspaces}"
        )
        ws_str = str(workspaces)
        assert "apps" in ws_str, "Workspaces should include 'apps/*'"
        assert "packages" in ws_str, "Workspaces should include 'packages/*'"

    def test_ui_package_has_exports_field(self):
        """Verify UI package.json uses exports field"""
        filepath = os.path.join(self.EXAMPLE_DIR, "packages/ui/package.json")
        with open(filepath) as f:
            data = json.load(f)

        has_exports = "exports" in data or "main" in data
        assert has_exports, (
            "UI package.json should have 'exports' or 'main' field for component access"
        )

    def test_web_app_depends_on_ui(self):
        """Verify web app declares workspace dependency on shared UI"""
        filepath = os.path.join(self.EXAMPLE_DIR, "apps/web/package.json")
        with open(filepath) as f:
            data = json.load(f)

        all_deps = {}
        all_deps.update(data.get("dependencies", {}))
        all_deps.update(data.get("devDependencies", {}))

        ui_dep = None
        for key, value in all_deps.items():
            if "ui" in key.lower():
                ui_dep = (key, value)
                break

        assert ui_dep is not None, (
            "apps/web/package.json should declare a dependency on the shared UI package"
        )
        assert "workspace" in str(ui_dep[1]).lower() or "*" in str(ui_dep[1]), (
            f"UI dependency should use workspace protocol. Found: {ui_dep}"
        )

    # === Functional Checks ===

    def test_button_component_exists(self):
        """Verify Button component file exists and defines variant props"""
        filepath = os.path.join(self.EXAMPLE_DIR, "packages/ui/src/Button.tsx")
        assert os.path.exists(filepath), f"Button.tsx not found at {filepath}"
        with open(filepath) as f:
            content = f.read()

        assert "primary" in content, "Button.tsx should define 'primary' variant"
        assert "secondary" in content or "outline" in content, (
            "Button.tsx should define 'secondary' or 'outline' variant"
        )

    def test_card_component_exists(self):
        """Verify Card component file exists with title and description props"""
        filepath = os.path.join(self.EXAMPLE_DIR, "packages/ui/src/Card.tsx")
        assert os.path.exists(filepath), f"Card.tsx not found at {filepath}"
        with open(filepath) as f:
            content = f.read()

        assert "title" in content, "Card.tsx should accept 'title' prop"
        assert "description" in content, "Card.tsx should accept 'description' prop"

    def test_index_barrel_export(self):
        """Verify the barrel export file exists and exports components"""
        filepath = os.path.join(self.EXAMPLE_DIR, "packages/ui/src/index.ts")
        assert os.path.exists(filepath), f"index.ts not found at {filepath}"
        with open(filepath) as f:
            content = f.read()

        assert "Button" in content, "index.ts should export Button"
        assert "Card" in content, "index.ts should export Card"

    def test_npm_install_and_turbo_build(self):
        """Verify that npm install and turbo build succeed"""
        # Install dependencies
        install_result = subprocess.run(
            ["npm", "install"],
            cwd=self.EXAMPLE_DIR,
            capture_output=True,
            text=True,
            timeout=300
        )
        if install_result.returncode != 0:
            pytest.skip(f"npm install failed: {install_result.stderr[:1000]}")

        # Run turbo build
        build_result = subprocess.run(
            ["npx", "turbo", "run", "build"],
            cwd=self.EXAMPLE_DIR,
            capture_output=True,
            text=True,
            timeout=300
        )
        assert build_result.returncode == 0, (
            f"turbo run build failed:\nstdout: {build_result.stdout[:2000]}\n"
            f"stderr: {build_result.stderr[:2000]}"
        )
