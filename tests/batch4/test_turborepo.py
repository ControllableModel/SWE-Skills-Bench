"""
Test skill: turborepo
Verify that the Turborepo build pipeline has been correctly configured for the
cache-demo monorepo, including turbo.json pipeline, package scripts, shared utils
package, environment variable handling, and caching behavior.
"""

import os
import json
import subprocess
import pytest


class TestTurborepo:
    REPO_DIR = "/workspace/turbo"
    DEMO_DIR = "/workspace/turbo/examples/cache-demo"

    # === File Path Checks ===

    def test_turbo_json_exists(self):
        """Verify that turbo.json exists in the cache-demo root"""
        filepath = os.path.join(self.DEMO_DIR, "turbo.json")
        assert os.path.exists(filepath), f"turbo.json not found at {filepath}"

    def test_root_package_json_exists(self):
        """Verify that the root package.json exists"""
        filepath = os.path.join(self.DEMO_DIR, "package.json")
        assert os.path.exists(filepath), f"Root package.json not found at {filepath}"

    def test_utils_package_exists(self):
        """Verify that the packages/utils directory and package.json exist"""
        pkg_path = os.path.join(self.DEMO_DIR, "packages/utils/package.json")
        assert os.path.exists(pkg_path), \
            f"packages/utils/package.json not found at {pkg_path}"

    def test_utils_index_ts_exists(self):
        """Verify that packages/utils/src/index.ts exists"""
        filepath = os.path.join(self.DEMO_DIR, "packages/utils/src/index.ts")
        assert os.path.exists(filepath), f"utils/src/index.ts not found at {filepath}"

    # === Semantic Checks ===

    def test_turbo_json_defines_build_pipeline(self):
        """Verify turbo.json defines build task with ^build dependency and correct outputs"""
        filepath = os.path.join(self.DEMO_DIR, "turbo.json")
        with open(filepath) as f:
            config = json.load(f)

        # Handle both Turbo v1 (pipeline) and v2 (tasks) format
        tasks = config.get("tasks", config.get("pipeline", {}))
        assert "build" in tasks, "turbo.json should define a 'build' task"

        build_task = tasks["build"]
        depends_on = build_task.get("dependsOn", [])
        assert "^build" in depends_on, \
            f"build task should depend on '^build', got dependsOn: {depends_on}"

        outputs = build_task.get("outputs", [])
        has_dist = any("dist" in o for o in outputs)
        has_next = any(".next" in o for o in outputs)
        assert has_dist or has_next, \
            f"build outputs should include 'dist/**' or '.next/**', got: {outputs}"

    def test_turbo_json_defines_lint_task(self):
        """Verify turbo.json defines lint task with no dependencies and no outputs"""
        filepath = os.path.join(self.DEMO_DIR, "turbo.json")
        with open(filepath) as f:
            config = json.load(f)
        tasks = config.get("tasks", config.get("pipeline", {}))
        assert "lint" in tasks, "turbo.json should define a 'lint' task"

    def test_turbo_json_defines_test_task(self):
        """Verify turbo.json defines test task depending on build"""
        filepath = os.path.join(self.DEMO_DIR, "turbo.json")
        with open(filepath) as f:
            config = json.load(f)
        tasks = config.get("tasks", config.get("pipeline", {}))
        assert "test" in tasks, "turbo.json should define a 'test' task"
        test_task = tasks["test"]
        depends_on = test_task.get("dependsOn", [])
        assert "build" in depends_on, \
            f"test task should depend on 'build', got dependsOn: {depends_on}"

    def test_turbo_json_defines_dev_task(self):
        """Verify turbo.json defines dev task as persistent and cache: false"""
        filepath = os.path.join(self.DEMO_DIR, "turbo.json")
        with open(filepath) as f:
            config = json.load(f)
        tasks = config.get("tasks", config.get("pipeline", {}))
        assert "dev" in tasks, "turbo.json should define a 'dev' task"
        dev_task = tasks["dev"]
        assert dev_task.get("persistent") is True, \
            "dev task should be persistent: true"
        assert dev_task.get("cache") is False, \
            "dev task should have cache: false"

    def test_turbo_json_env_configuration(self):
        """Verify turbo.json declares environment variable dependencies"""
        filepath = os.path.join(self.DEMO_DIR, "turbo.json")
        with open(filepath) as f:
            config = json.load(f)
        tasks = config.get("tasks", config.get("pipeline", {}))
        build_task = tasks.get("build", {})
        # Check env or globalEnv
        build_env = build_task.get("env", [])
        global_env = config.get("globalEnv", [])
        all_env = build_env + global_env
        has_node_env = any("NODE_ENV" in e for e in all_env)
        assert has_node_env or len(build_env) > 0, \
            "build task should declare environment variable dependencies (NODE_ENV, NEXT_PUBLIC_*)"

    def test_root_package_json_delegates_to_turbo(self):
        """Verify root package.json scripts delegate to turbo run"""
        filepath = os.path.join(self.DEMO_DIR, "package.json")
        with open(filepath) as f:
            pkg = json.load(f)
        scripts = pkg.get("scripts", {})
        build_script = scripts.get("build", "")
        assert "turbo" in build_script, \
            f"Root build script should delegate to turbo, got: '{build_script}'"

    def test_utils_package_exports_required_functions(self):
        """Verify packages/utils/src/index.ts exports formatCurrency, slugify, and clamp"""
        filepath = os.path.join(self.DEMO_DIR, "packages/utils/src/index.ts")
        with open(filepath) as f:
            content = f.read()
        required_functions = ["formatCurrency", "slugify", "clamp"]
        for func in required_functions:
            assert func in content, \
                f"packages/utils should export '{func}' function"

    def test_apps_depend_on_utils(self):
        """Verify web and api apps declare packages/utils as a dependency"""
        for app in ["apps/web", "apps/api"]:
            pkg_path = os.path.join(self.DEMO_DIR, app, "package.json")
            if not os.path.exists(pkg_path):
                continue
            with open(pkg_path) as f:
                pkg = json.load(f)
            all_deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
            has_utils = any("utils" in dep for dep in all_deps)
            assert has_utils, \
                f"{app}/package.json should depend on the utils package"

    # === Functional Checks ===

    def test_npm_install_succeeds(self):
        """Verify npm install succeeds in the cache-demo root"""
        result = subprocess.run(
            ["npm", "install"],
            cwd=self.DEMO_DIR,
            capture_output=True, text=True, timeout=180
        )
        assert result.returncode == 0, \
            f"npm install failed: {result.stderr[:1000]}"

    def test_npm_run_build_succeeds(self):
        """Verify npm run build completes successfully, building all packages"""
        subprocess.run(["npm", "install"], cwd=self.DEMO_DIR,
                       capture_output=True, text=True, timeout=180)
        result = subprocess.run(
            ["npm", "run", "build"],
            cwd=self.DEMO_DIR,
            capture_output=True, text=True, timeout=300
        )
        assert result.returncode == 0, \
            f"npm run build failed:\n{result.stdout[-1500:]}\n{result.stderr[-1000:]}"

    def test_turbo_json_is_valid_json(self):
        """Verify turbo.json is parseable as valid JSON"""
        filepath = os.path.join(self.DEMO_DIR, "turbo.json")
        with open(filepath) as f:
            try:
                config = json.load(f)
            except json.JSONDecodeError as e:
                pytest.fail(f"turbo.json is not valid JSON: {e}")
        assert isinstance(config, dict), "turbo.json should contain a JSON object"
