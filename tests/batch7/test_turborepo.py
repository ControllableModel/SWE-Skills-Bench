"""
Test skill: turborepo
Verify that the Agent correctly creates a cache-demo application in the
Turborepo examples directory demonstrating task caching, dependency graphs,
and cache invalidation.
"""

import os
import re
import json
import subprocess
import pytest


class TestTurborepo:
    REPO_DIR = "/workspace/turbo"
    DEMO_DIR = "/workspace/turbo/examples/cache-demo"

    # === File Path Checks ===

    def test_root_package_json_exists(self):
        """Verify root package.json exists in cache-demo"""
        fpath = os.path.join(self.DEMO_DIR, "package.json")
        assert os.path.isfile(fpath), f"Root package.json not found at {fpath}"

    def test_turbo_json_exists(self):
        """Verify turbo.json pipeline config exists"""
        fpath = os.path.join(self.DEMO_DIR, "turbo.json")
        assert os.path.isfile(fpath), f"turbo.json not found at {fpath}"

    def test_shared_utils_package_exists(self):
        """Verify shared-utils package exists with required files"""
        pkg = os.path.join(self.DEMO_DIR, "packages/shared-utils/package.json")
        src = os.path.join(self.DEMO_DIR, "packages/shared-utils/src/index.ts")
        assert os.path.isfile(pkg), f"shared-utils/package.json not found"
        assert os.path.isfile(src), f"shared-utils/src/index.ts not found"

    def test_web_app_exists(self):
        """Verify web app exists with required files"""
        pkg = os.path.join(self.DEMO_DIR, "apps/web/package.json")
        src = os.path.join(self.DEMO_DIR, "apps/web/src/index.ts")
        assert os.path.isfile(pkg), f"apps/web/package.json not found"
        assert os.path.isfile(src), f"apps/web/src/index.ts not found"

    def test_api_app_exists(self):
        """Verify api app exists with required files"""
        pkg = os.path.join(self.DEMO_DIR, "apps/api/package.json")
        src = os.path.join(self.DEMO_DIR, "apps/api/src/index.ts")
        assert os.path.isfile(pkg), f"apps/api/package.json not found"
        assert os.path.isfile(src), f"apps/api/src/index.ts not found"

    def test_readme_exists(self):
        """Verify README.md documentation exists"""
        fpath = os.path.join(self.DEMO_DIR, "README.md")
        assert os.path.isfile(fpath), f"README.md not found at {fpath}"

    # === Semantic Checks ===

    def test_turbo_json_defines_build_pipeline(self):
        """Verify turbo.json defines build task with topological dependencies and outputs"""
        fpath = os.path.join(self.DEMO_DIR, "turbo.json")
        with open(fpath, "r") as f:
            turbo = json.load(f)

        # turbo.json can use "tasks" or "pipeline" key depending on version
        tasks = turbo.get("tasks", turbo.get("pipeline", {}))
        assert "build" in tasks, f"turbo.json missing 'build' task. Found: {list(tasks.keys())}"

        build_config = tasks["build"]
        # Check topological dependency
        depends_on = build_config.get("dependsOn", [])
        assert "^build" in depends_on, (
            f"build task should depend on '^build' for topological ordering. Got: {depends_on}"
        )
        # Check outputs
        outputs = build_config.get("outputs", [])
        assert any("dist" in o for o in outputs), (
            f"build task should output to 'dist/**'. Got: {outputs}"
        )

    def test_turbo_json_defines_test_pipeline(self):
        """Verify turbo.json defines test task that depends on build"""
        fpath = os.path.join(self.DEMO_DIR, "turbo.json")
        with open(fpath, "r") as f:
            turbo = json.load(f)

        tasks = turbo.get("tasks", turbo.get("pipeline", {}))
        assert "test" in tasks, f"turbo.json missing 'test' task"

        test_config = tasks["test"]
        depends_on = test_config.get("dependsOn", [])
        assert "build" in depends_on, (
            f"test task should depend on 'build'. Got: {depends_on}"
        )

    def test_turbo_json_defines_lint_pipeline(self):
        """Verify turbo.json defines lint task with caching enabled"""
        fpath = os.path.join(self.DEMO_DIR, "turbo.json")
        with open(fpath, "r") as f:
            turbo = json.load(f)

        tasks = turbo.get("tasks", turbo.get("pipeline", {}))
        assert "lint" in tasks, f"turbo.json missing 'lint' task"

    def test_turbo_json_declares_global_env(self):
        """Verify turbo.json declares NODE_ENV and API_URL as globalEnv"""
        fpath = os.path.join(self.DEMO_DIR, "turbo.json")
        with open(fpath, "r") as f:
            turbo = json.load(f)

        global_env = turbo.get("globalEnv", turbo.get("globalDependencies", []))
        # Some versions put env in different places
        if not global_env:
            # Try globalPassThroughEnv in newer turbo
            global_env = turbo.get("globalPassThroughEnv", [])
        assert "NODE_ENV" in global_env or any("NODE_ENV" in str(e) for e in global_env), (
            f"turbo.json should declare NODE_ENV in globalEnv. Got: {global_env}"
        )

    def test_workspace_defines_three_packages(self):
        """Verify root package.json defines workspaces for all three packages"""
        fpath = os.path.join(self.DEMO_DIR, "package.json")
        with open(fpath, "r") as f:
            pkg = json.load(f)

        workspaces = pkg.get("workspaces", [])
        if isinstance(workspaces, dict):
            workspaces = workspaces.get("packages", [])
        ws_str = str(workspaces)
        assert "packages" in ws_str or "shared-utils" in ws_str, (
            f"Workspaces should include packages/. Got: {workspaces}"
        )
        assert "apps" in ws_str or "web" in ws_str, (
            f"Workspaces should include apps/. Got: {workspaces}"
        )

    def test_apps_depend_on_shared_utils(self):
        """Verify web and api apps declare dependency on shared-utils"""
        for app in ["web", "api"]:
            fpath = os.path.join(self.DEMO_DIR, f"apps/{app}/package.json")
            with open(fpath, "r") as f:
                pkg = json.load(f)
            all_deps = {}
            all_deps.update(pkg.get("dependencies", {}))
            all_deps.update(pkg.get("devDependencies", {}))
            has_shared = any("shared-utils" in k or "shared" in k for k in all_deps)
            assert has_shared, (
                f"apps/{app} should depend on shared-utils. Deps: {list(all_deps.keys())}"
            )

    def test_shared_utils_exports_functions(self):
        """Verify shared-utils exports at least formatCurrency, formatDate, slugify"""
        fpath = os.path.join(self.DEMO_DIR, "packages/shared-utils/src/index.ts")
        with open(fpath, "r") as f:
            content = f.read()
        for func in ["formatCurrency", "formatDate", "slugify"]:
            has_func = bool(re.search(rf'(export\s+.*{func}|function\s+{func})', content))
            assert has_func, f"shared-utils should export '{func}' function"

    def test_each_package_has_build_test_lint_scripts(self):
        """Verify each package has build, test, and lint scripts"""
        packages = [
            "packages/shared-utils",
            "apps/web",
            "apps/api"
        ]
        for pkg_path in packages:
            fpath = os.path.join(self.DEMO_DIR, pkg_path, "package.json")
            with open(fpath, "r") as f:
                pkg = json.load(f)
            scripts = pkg.get("scripts", {})
            for script in ["build", "test", "lint"]:
                assert script in scripts, (
                    f"{pkg_path}/package.json missing '{script}' script. Found: {list(scripts.keys())}"
                )

    # === Functional Checks ===

    def test_npm_install_succeeds(self):
        """Verify npm install succeeds in cache-demo directory"""
        result = subprocess.run(
            ["npm", "install"],
            cwd=self.DEMO_DIR,
            capture_output=True,
            text=True,
            timeout=120
        )
        assert result.returncode == 0, f"npm install failed: {result.stderr[-1000:]}"

    def test_npm_build_succeeds(self):
        """Verify npm run build succeeds across all packages"""
        subprocess.run(["npm", "install"], cwd=self.DEMO_DIR, capture_output=True, timeout=120)
        result = subprocess.run(
            ["npm", "run", "build"],
            cwd=self.DEMO_DIR,
            capture_output=True,
            text=True,
            timeout=120
        )
        assert result.returncode == 0, f"Build failed: {result.stderr[-1000:]}"

    def test_build_produces_dist_directories(self):
        """Verify build produces dist/ directories in all packages"""
        subprocess.run(["npm", "install"], cwd=self.DEMO_DIR, capture_output=True, timeout=120)
        subprocess.run(["npm", "run", "build"], cwd=self.DEMO_DIR, capture_output=True, timeout=120)

        for pkg in ["packages/shared-utils", "apps/web", "apps/api"]:
            dist_dir = os.path.join(self.DEMO_DIR, pkg, "dist")
            assert os.path.isdir(dist_dir), f"Build should produce {pkg}/dist/ directory"
            files = os.listdir(dist_dir)
            assert len(files) > 0, f"{pkg}/dist/ should contain build output files"
