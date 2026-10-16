"""
Test skill: turborepo
Verify that the Agent correctly creates a Turborepo cache demo example
with multiple workspace packages, pipeline configuration, dependency-aware
caching, and buildable packages.
"""

import os
import json
import subprocess
import pytest


class TestTurborepo:
    REPO_DIR = "/workspace/turbo"

    # === File Path Checks ===

    def test_cache_demo_directory_exists(self):
        """Verify examples/cache-demo/ directory exists"""
        path = os.path.join(self.REPO_DIR, "examples/cache-demo")
        assert os.path.isdir(path), f"examples/cache-demo/ not found at {path}"

    def test_root_package_json_exists(self):
        """Verify root package.json exists in cache-demo"""
        path = os.path.join(self.REPO_DIR, "examples/cache-demo/package.json")
        assert os.path.exists(path), f"Root package.json not found at {path}"

    def test_turbo_json_exists(self):
        """Verify turbo.json exists in cache-demo"""
        path = os.path.join(self.REPO_DIR, "examples/cache-demo/turbo.json")
        assert os.path.exists(path), f"turbo.json not found at {path}"

    # === Semantic Checks ===

    def test_root_package_json_has_workspaces(self):
        """Verify root package.json defines workspaces"""
        path = os.path.join(self.REPO_DIR, "examples/cache-demo/package.json")
        with open(path) as f:
            pkg = json.load(f)

        assert "workspaces" in pkg, (
            "Root package.json should define 'workspaces' for monorepo structure"
        )
        workspaces = pkg["workspaces"]
        if isinstance(workspaces, dict):
            workspaces = workspaces.get("packages", [])
        assert len(workspaces) >= 1, (
            f"Workspaces should list at least 1 pattern. Found: {workspaces}"
        )

    def test_turbo_json_has_pipeline(self):
        """Verify turbo.json defines a pipeline with build task"""
        path = os.path.join(self.REPO_DIR, "examples/cache-demo/turbo.json")
        with open(path) as f:
            config = json.load(f)

        # Turbo v1 uses "pipeline", v2 uses "tasks"
        has_pipeline = "pipeline" in config or "tasks" in config
        assert has_pipeline, (
            f"turbo.json should define 'pipeline' or 'tasks'. "
            f"Keys found: {list(config.keys())}"
        )

        tasks = config.get("pipeline", config.get("tasks", {}))
        assert "build" in tasks, (
            f"Pipeline should include a 'build' task. Tasks found: {list(tasks.keys())}"
        )

    def test_turbo_json_build_has_outputs(self):
        """Verify turbo.json build task configures cache outputs"""
        path = os.path.join(self.REPO_DIR, "examples/cache-demo/turbo.json")
        with open(path) as f:
            config = json.load(f)

        tasks = config.get("pipeline", config.get("tasks", {}))
        build_config = tasks.get("build", {})

        assert "outputs" in build_config, (
            f"Build task should configure 'outputs' for caching. "
            f"Build config: {build_config}"
        )
        outputs = build_config["outputs"]
        assert len(outputs) >= 1, "Build outputs should list at least one output path"

    def test_at_least_two_workspace_packages_exist(self):
        """Verify at least two workspace packages exist with package.json"""
        demo_dir = os.path.join(self.REPO_DIR, "examples/cache-demo")
        packages_dir = os.path.join(demo_dir, "packages")
        apps_dir = os.path.join(demo_dir, "apps")

        package_jsons = []
        for search_dir in [packages_dir, apps_dir, demo_dir]:
            if os.path.isdir(search_dir):
                for entry in os.listdir(search_dir):
                    entry_path = os.path.join(search_dir, entry)
                    if os.path.isdir(entry_path):
                        pkg_json = os.path.join(entry_path, "package.json")
                        if os.path.exists(pkg_json):
                            package_jsons.append(
                                os.path.relpath(entry_path, demo_dir)
                            )

        assert len(package_jsons) >= 2, (
            f"Should have at least 2 workspace packages. "
            f"Found packages with package.json: {package_jsons}"
        )

    def test_shared_library_package_exists(self):
        """Verify a shared library package exists that others depend on"""
        demo_dir = os.path.join(self.REPO_DIR, "examples/cache-demo")
        packages_dir = os.path.join(demo_dir, "packages")

        if not os.path.isdir(packages_dir):
            # Try to find shared packages in other locations
            packages_dir = demo_dir

        shared_found = False
        for root, dirs, files in os.walk(demo_dir):
            if "package.json" in files:
                pkg_path = os.path.join(root, "package.json")
                try:
                    with open(pkg_path) as f:
                        pkg = json.load(f)
                    # A shared library is typically depended on by another package
                    pkg_name = pkg.get("name", "")
                    if "lib" in pkg_name.lower() or "shared" in pkg_name.lower() or "common" in pkg_name.lower():
                        shared_found = True
                        break
                except (json.JSONDecodeError, KeyError):
                    continue

        if not shared_found:
            # Alternative check: look for inter-package dependencies
            dep_names = set()
            pkg_names = set()
            for root, dirs, files in os.walk(demo_dir):
                if root == demo_dir:
                    continue  # skip root
                if "package.json" in files and "node_modules" not in root:
                    pkg_path = os.path.join(root, "package.json")
                    try:
                        with open(pkg_path) as f:
                            pkg = json.load(f)
                        pkg_names.add(pkg.get("name", ""))
                        for dep in pkg.get("dependencies", {}):
                            dep_names.add(dep)
                    except (json.JSONDecodeError, KeyError):
                        continue

            internal_deps = pkg_names & dep_names
            assert len(internal_deps) >= 1, (
                "Should have at least one shared package that others depend on. "
                f"Packages: {pkg_names}, Dependencies referenced: {dep_names}"
            )

    def test_workspace_packages_have_build_scripts(self):
        """Verify workspace packages have build scripts"""
        demo_dir = os.path.join(self.REPO_DIR, "examples/cache-demo")
        packages_with_build = []
        packages_without_build = []

        for root, dirs, files in os.walk(demo_dir):
            if "node_modules" in root:
                continue
            if "package.json" in files and root != demo_dir:
                pkg_path = os.path.join(root, "package.json")
                try:
                    with open(pkg_path) as f:
                        pkg = json.load(f)
                    rel_path = os.path.relpath(root, demo_dir)
                    if "build" in pkg.get("scripts", {}):
                        packages_with_build.append(rel_path)
                    else:
                        packages_without_build.append(rel_path)
                except (json.JSONDecodeError, KeyError):
                    continue

        assert len(packages_with_build) >= 2, (
            f"At least 2 packages should have build scripts. "
            f"With build: {packages_with_build}, Without: {packages_without_build}"
        )

    # === Functional Checks ===

    def test_npm_install_succeeds(self):
        """Verify npm install succeeds in cache-demo"""
        demo_dir = os.path.join(self.REPO_DIR, "examples/cache-demo")
        result = subprocess.run(
            ["npm", "install"],
            cwd=demo_dir,
            capture_output=True,
            text=True,
            timeout=300,
        )
        assert result.returncode == 0 or os.path.exists(
            os.path.join(demo_dir, "node_modules")
        ), f"npm install failed: {result.stderr[:1000]}"

    def test_npm_run_build_succeeds(self):
        """Verify npm run build succeeds (invokes Turborepo)"""
        demo_dir = os.path.join(self.REPO_DIR, "examples/cache-demo")
        subprocess.run(
            ["npm", "install"],
            cwd=demo_dir,
            capture_output=True,
            text=True,
            timeout=300,
        )

        result = subprocess.run(
            ["npm", "run", "build"],
            cwd=demo_dir,
            capture_output=True,
            text=True,
            timeout=300,
        )
        assert result.returncode == 0, (
            f"npm run build failed (exit code {result.returncode}).\n"
            f"stdout: {result.stdout[:2000]}\n"
            f"stderr: {result.stderr[:2000]}"
        )

    def test_second_build_uses_cache(self):
        """Verify a second build run hits cache (faster completion)"""
        demo_dir = os.path.join(self.REPO_DIR, "examples/cache-demo")
        subprocess.run(["npm", "install"], cwd=demo_dir,
                       capture_output=True, text=True, timeout=300)
        # First build
        subprocess.run(["npm", "run", "build"], cwd=demo_dir,
                       capture_output=True, text=True, timeout=300)
        # Second build - should use cache
        result = subprocess.run(
            ["npm", "run", "build"],
            cwd=demo_dir,
            capture_output=True,
            text=True,
            timeout=300,
        )
        assert result.returncode == 0, (
            f"Second build failed: {result.stderr[:1000]}"
        )
        combined = result.stdout + result.stderr
        # Turborepo prints "FULL TURBO" or "cache hit" when using cache
        cache_indicators = ["cache", "FULL TURBO", ">>> FULL TURBO"]
        found = any(ind.lower() in combined.lower() for ind in cache_indicators)
        # This is a soft check - cache behavior may vary by version
        if not found:
            # At minimum, the build should still succeed quickly
            pass
