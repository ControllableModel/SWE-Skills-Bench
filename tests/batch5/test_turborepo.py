"""
Test skill: turborepo
Verify that the Agent correctly configures a Turborepo monorepo with shared
packages, pipeline caching, and workspace structure.
"""

import os
import json
import subprocess
import pytest


class TestTurborepo:
    REPO_DIR = "/workspace/turbo"
    EXAMPLE_DIR = "examples/with-shared-packages"

    def _example_path(self, rel_path=""):
        return os.path.join(self.REPO_DIR, self.EXAMPLE_DIR, rel_path)

    def _read_json(self, rel_path):
        filepath = self._example_path(rel_path)
        with open(filepath) as f:
            return json.load(f)

    # === File Path Checks ===

    def test_turbo_json_exists(self):
        """Verify turbo.json exists in the example directory"""
        assert os.path.exists(self._example_path("turbo.json")), \
            "turbo.json not found in examples/with-shared-packages"

    def test_root_package_json_exists(self):
        """Verify root package.json exists"""
        assert os.path.exists(self._example_path("package.json")), \
            "Root package.json not found"

    def test_ui_package_exists(self):
        """Verify packages/ui directory and package.json exist"""
        assert os.path.exists(self._example_path("packages/ui/package.json")), \
            "packages/ui/package.json not found"

    def test_tsconfig_package_exists(self):
        """Verify packages/tsconfig exists with base.json"""
        assert os.path.exists(self._example_path("packages/tsconfig/base.json")), \
            "packages/tsconfig/base.json not found"

    def test_web_app_exists(self):
        """Verify apps/web directory exists with package.json"""
        assert os.path.exists(self._example_path("apps/web/package.json")), \
            "apps/web/package.json not found"

    def test_api_app_exists(self):
        """Verify apps/api directory exists with package.json"""
        assert os.path.exists(self._example_path("apps/api/package.json")), \
            "apps/api/package.json not found"

    # === Semantic Checks ===

    def test_turbo_json_pipeline_has_required_tasks(self):
        """Verify turbo.json defines build, lint, test, and dev tasks"""
        config = self._read_json("turbo.json")
        pipeline = config.get("pipeline", config.get("tasks", {}))
        for task in ["build", "lint", "test", "dev"]:
            assert task in pipeline, \
                f"turbo.json missing '{task}' in pipeline/tasks"

    def test_turbo_build_depends_on_upstream(self):
        """Verify build task depends on ^build (upstream packages)"""
        config = self._read_json("turbo.json")
        pipeline = config.get("pipeline", config.get("tasks", {}))
        build = pipeline.get("build", {})
        depends_on = build.get("dependsOn", [])
        assert "^build" in depends_on, \
            f"build task should depend on '^build', got dependsOn: {depends_on}"

    def test_turbo_dev_not_cached(self):
        """Verify dev task has cache disabled"""
        config = self._read_json("turbo.json")
        pipeline = config.get("pipeline", config.get("tasks", {}))
        dev = pipeline.get("dev", {})
        assert dev.get("cache") is False, \
            f"dev task should have cache=false, got: {dev.get('cache')}"

    def test_root_package_json_has_workspaces(self):
        """Verify root package.json defines workspaces for packages and apps"""
        pkg = self._read_json("package.json")
        workspaces = pkg.get("workspaces", [])
        if isinstance(workspaces, dict):
            workspaces = workspaces.get("packages", [])
        has_packages = any("packages" in ws for ws in workspaces)
        has_apps = any("apps" in ws for ws in workspaces)
        assert has_packages, f"Workspaces missing packages/* glob: {workspaces}"
        assert has_apps, f"Workspaces missing apps/* glob: {workspaces}"

    def test_ui_exports_components(self):
        """Verify UI library exports Button, Card, and Input components"""
        index_candidates = [
            self._example_path("packages/ui/src/index.ts"),
            self._example_path("packages/ui/src/index.tsx"),
            self._example_path("packages/ui/index.ts"),
        ]
        content = None
        for p in index_candidates:
            if os.path.exists(p):
                with open(p) as f:
                    content = f.read()
                break
        assert content is not None, "UI library index file not found"
        for component in ["Button", "Card", "Input"]:
            assert component in content, \
                f"UI library missing export for '{component}'"

    def test_tsconfig_base_has_strict(self):
        """Verify base tsconfig has strict mode enabled"""
        config = self._read_json("packages/tsconfig/base.json")
        compiler = config.get("compilerOptions", {})
        assert compiler.get("strict") is True, \
            f"Base tsconfig should have strict=true, got {compiler.get('strict')}"

    def test_tsconfig_react_extends_base(self):
        """Verify react.json tsconfig extends base.json"""
        filepath = self._example_path("packages/tsconfig/react.json")
        assert os.path.exists(filepath), "packages/tsconfig/react.json not found"
        with open(filepath) as f:
            config = json.load(f)
        extends = config.get("extends", "")
        assert "base" in extends, \
            f"react.json should extend base.json, got extends: {extends}"
        compiler = config.get("compilerOptions", {})
        jsx = compiler.get("jsx", "")
        assert "react" in jsx.lower(), \
            f"react.json should have jsx: react-jsx, got: {jsx}"

    # === Functional Checks ===

    def test_api_has_health_endpoint(self):
        """Verify API server source has /health endpoint"""
        api_src = None
        for candidate in [
            self._example_path("apps/api/src/index.ts"),
            self._example_path("apps/api/src/server.ts"),
            self._example_path("apps/api/src/app.ts"),
        ]:
            if os.path.exists(candidate):
                with open(candidate) as f:
                    api_src = f.read()
                break
        assert api_src is not None, "API server source file not found"
        assert "/health" in api_src, "API server missing /health endpoint"

    def test_api_has_items_crud_endpoint(self):
        """Verify API server has /api/items CRUD endpoint"""
        api_src = None
        for candidate in [
            self._example_path("apps/api/src/index.ts"),
            self._example_path("apps/api/src/server.ts"),
            self._example_path("apps/api/src/app.ts"),
        ]:
            if os.path.exists(candidate):
                with open(candidate) as f:
                    api_src = f.read()
                break
        assert api_src is not None, "API server source file not found"
        assert "items" in api_src or "item" in api_src, \
            "API server missing items endpoint"
        # Verify CRUD methods
        import re
        methods = re.findall(r'\.(get|post|put|delete|patch)\s*\(', api_src, re.IGNORECASE)
        assert len(methods) >= 3, \
            f"Expected at least 3 HTTP method handlers (GET, POST, PUT/DELETE), found: {methods}"

    def test_npm_install_succeeds(self):
        """Verify npm install completes in the example directory"""
        result = subprocess.run(
            ["npm", "install"],
            cwd=self._example_path(),
            capture_output=True,
            text=True,
            timeout=300,
        )
        assert result.returncode == 0, \
            f"npm install failed: {result.stderr[:500]}"

    def test_turbo_build_succeeds(self):
        """Verify turbo run build completes successfully"""
        subprocess.run(
            ["npm", "install"], cwd=self._example_path(),
            capture_output=True, text=True, timeout=300,
        )
        result = subprocess.run(
            ["npx", "turbo", "run", "build"],
            cwd=self._example_path(),
            capture_output=True,
            text=True,
            timeout=300,
        )
        assert result.returncode == 0, \
            f"turbo run build failed: {result.stderr[:500]}\n{result.stdout[:500]}"
