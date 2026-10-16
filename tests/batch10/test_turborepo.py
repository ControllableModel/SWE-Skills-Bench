"""
Test skill: turborepo
Verify that the Agent correctly adds a shared UI package and cache-demo pipeline
to the Turbo monorepo.
"""

import os
import json
import subprocess
import re
import pytest


class TestTurborepo:
    REPO_DIR = "/workspace/turbo"
    CACHE_DEMO = "/workspace/turbo/examples/cache-demo"

    # === File Path Checks ===

    def test_ui_package_json_exists(self):
        """Verify packages/ui/package.json was created"""
        path = os.path.join(self.CACHE_DEMO, "packages/ui/package.json")
        assert os.path.exists(path), f"UI package.json not found at {path}"

    def test_ui_index_ts_exists(self):
        """Verify packages/ui/src/index.ts barrel export was created"""
        path = os.path.join(self.CACHE_DEMO, "packages/ui/src/index.ts")
        assert os.path.exists(path), f"index.ts not found at {path}"

    def test_button_component_exists(self):
        """Verify packages/ui/src/Button.tsx was created"""
        path = os.path.join(self.CACHE_DEMO, "packages/ui/src/Button.tsx")
        assert os.path.exists(path), f"Button.tsx not found at {path}"

    def test_card_component_exists(self):
        """Verify packages/ui/src/Card.tsx was created"""
        path = os.path.join(self.CACHE_DEMO, "packages/ui/src/Card.tsx")
        assert os.path.exists(path), f"Card.tsx not found at {path}"

    def test_ui_tsconfig_exists(self):
        """Verify packages/ui/tsconfig.json was created"""
        path = os.path.join(self.CACHE_DEMO, "packages/ui/tsconfig.json")
        assert os.path.exists(path), f"tsconfig.json not found at {path}"

    # === Semantic Checks ===

    def test_ui_package_name_correct(self):
        """Verify UI package name is @cache-demo/ui"""
        path = os.path.join(self.CACHE_DEMO, "packages/ui/package.json")
        with open(path) as f:
            pkg = json.load(f)
        assert pkg.get("name") == "@cache-demo/ui", (
            f"Package name should be '@cache-demo/ui', got '{pkg.get('name')}'"
        )

    def test_ui_package_has_required_scripts(self):
        """Verify UI package has build, lint, and test scripts"""
        path = os.path.join(self.CACHE_DEMO, "packages/ui/package.json")
        with open(path) as f:
            pkg = json.load(f)
        scripts = pkg.get("scripts", {})
        for script in ["build", "lint", "test"]:
            assert script in scripts, f"UI package missing '{script}' script"

    def test_ui_package_main_points_to_dist(self):
        """Verify UI package main field points to dist/index.js"""
        path = os.path.join(self.CACHE_DEMO, "packages/ui/package.json")
        with open(path) as f:
            pkg = json.load(f)
        main = pkg.get("main", "")
        assert "dist" in main and "index" in main, (
            f"main field should point to dist/index.js, got '{main}'"
        )

    def test_ui_package_has_react_peer_deps(self):
        """Verify UI package declares react peer dependencies"""
        path = os.path.join(self.CACHE_DEMO, "packages/ui/package.json")
        with open(path) as f:
            pkg = json.load(f)
        peer_deps = pkg.get("peerDependencies", {})
        assert "react" in peer_deps, "UI package missing react peer dependency"

    def test_turbo_json_has_build_task(self):
        """Verify turbo.json defines build task with ^build dependency and dist outputs"""
        path = os.path.join(self.CACHE_DEMO, "turbo.json")
        assert os.path.exists(path), f"turbo.json not found at {path}"
        with open(path) as f:
            content = f.read()
        # Handle jsonc
        clean = re.sub(r'//.*', '', content)
        clean = re.sub(r'/\*.*?\*/', '', clean, flags=re.DOTALL)
        # Remove trailing commas
        clean = re.sub(r',\s*([\]}])', r'\1', clean)
        config = json.loads(clean)

        # turbo.json v2 uses "tasks", v1 uses "pipeline"
        tasks = config.get("tasks", config.get("pipeline", {}))
        assert "build" in tasks, "turbo.json missing 'build' task"
        build_task = tasks["build"]
        depends_on = build_task.get("dependsOn", [])
        assert "^build" in depends_on, (
            f"build task dependsOn should include '^build', got {depends_on}"
        )
        outputs = build_task.get("outputs", [])
        assert any("dist" in o for o in outputs), (
            f"build task outputs should include 'dist/**', got {outputs}"
        )

    def test_turbo_json_has_lint_task(self):
        """Verify turbo.json defines lint task"""
        path = os.path.join(self.CACHE_DEMO, "turbo.json")
        with open(path) as f:
            content = f.read()
        clean = re.sub(r'//.*', '', content)
        clean = re.sub(r'/\*.*?\*/', '', clean, flags=re.DOTALL)
        clean = re.sub(r',\s*([\]}])', r'\1', clean)
        config = json.loads(clean)
        tasks = config.get("tasks", config.get("pipeline", {}))
        assert "lint" in tasks, "turbo.json missing 'lint' task"

    def test_turbo_json_has_test_task_depends_on_build(self):
        """Verify turbo.json defines test task with build dependency"""
        path = os.path.join(self.CACHE_DEMO, "turbo.json")
        with open(path) as f:
            content = f.read()
        clean = re.sub(r'//.*', '', content)
        clean = re.sub(r'/\*.*?\*/', '', clean, flags=re.DOTALL)
        clean = re.sub(r',\s*([\]}])', r'\1', clean)
        config = json.loads(clean)
        tasks = config.get("tasks", config.get("pipeline", {}))
        assert "test" in tasks, "turbo.json missing 'test' task"
        test_task = tasks["test"]
        depends_on = test_task.get("dependsOn", [])
        assert "build" in depends_on, (
            f"test task should depend on 'build', got {depends_on}"
        )

    def test_turbo_json_build_has_node_env(self):
        """Verify build task declares NODE_ENV in env (not globalEnv)"""
        path = os.path.join(self.CACHE_DEMO, "turbo.json")
        with open(path) as f:
            content = f.read()
        clean = re.sub(r'//.*', '', content)
        clean = re.sub(r'/\*.*?\*/', '', clean, flags=re.DOTALL)
        clean = re.sub(r',\s*([\]}])', r'\1', clean)
        config = json.loads(clean)
        tasks = config.get("tasks", config.get("pipeline", {}))
        build_task = tasks.get("build", {})
        env = build_task.get("env", [])
        assert "NODE_ENV" in env, (
            f"build task env should include 'NODE_ENV', got {env}"
        )

    def test_root_package_json_uses_turbo_run(self):
        """Verify root scripts use 'turbo run <task>' not direct tool invocations"""
        path = os.path.join(self.CACHE_DEMO, "package.json")
        with open(path) as f:
            pkg = json.load(f)
        scripts = pkg.get("scripts", {})
        for task in ["build", "lint", "test"]:
            if task in scripts:
                assert "turbo run" in scripts[task] or "turbo" in scripts[task], (
                    f"Root script '{task}' should use 'turbo run', got: {scripts[task]}"
                )
                assert "tsc" not in scripts[task] and "eslint" not in scripts[task], (
                    f"Root script '{task}' should not invoke tools directly: {scripts[task]}"
                )

    def test_web_app_depends_on_ui(self):
        """Verify apps/web/package.json lists @cache-demo/ui as dependency"""
        path = os.path.join(self.CACHE_DEMO, "apps/web/package.json")
        if not os.path.exists(path):
            pytest.skip("apps/web/package.json not found")
        with open(path) as f:
            pkg = json.load(f)
        deps = pkg.get("dependencies", {})
        dev_deps = pkg.get("devDependencies", {})
        all_deps = {**deps, **dev_deps}
        assert "@cache-demo/ui" in all_deps, (
            "apps/web should depend on @cache-demo/ui"
        )

    # === Functional Checks ===

    def test_npm_install_and_build_succeeds(self):
        """Verify npm install && npm run build succeeds in cache-demo"""
        result = subprocess.run(
            ["npm", "install"],
            cwd=self.CACHE_DEMO,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            pytest.skip(f"npm install failed: {result.stderr[:500]}")

        result = subprocess.run(
            ["npm", "run", "build"],
            cwd=self.CACHE_DEMO,
            capture_output=True,
            text=True,
            timeout=300,
        )
        assert result.returncode == 0, (
            f"npm run build failed: {result.stderr[-1000:]}\n{result.stdout[-1000:]}"
        )

    def test_ui_dist_exists_after_build(self):
        """Verify packages/ui/dist/ is created with compiled output after build"""
        # Run build  
        subprocess.run(["npm", "install"], cwd=self.CACHE_DEMO, capture_output=True, timeout=120)
        subprocess.run(["npm", "run", "build"], cwd=self.CACHE_DEMO, capture_output=True, timeout=300)

        dist_dir = os.path.join(self.CACHE_DEMO, "packages/ui/dist")
        assert os.path.isdir(dist_dir), f"packages/ui/dist/ not found after build"
        files = os.listdir(dist_dir)
        assert any(f.endswith('.js') for f in files), "dist/ should contain .js files"
        assert any(f.endswith('.d.ts') for f in files), "dist/ should contain .d.ts files"
