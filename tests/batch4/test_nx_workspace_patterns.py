"""
Tests for skill: nx-workspace-patterns
Repo: nrwl/nx
Image: zhangyiiiiii/swe-skills-bench-python
Task: Configure an Nx monorepo with project boundaries, caching,
      and affected commands for a multi-app/multi-lib workspace.
"""

import json
import os
import re

import pytest
import yaml

REPO_DIR = "/workspace/nx"
DEMO_DIR = os.path.join(REPO_DIR, "examples", "nx-demo")

NX_JSON = os.path.join(DEMO_DIR, "nx.json")
WEB_PROJECT = os.path.join(DEMO_DIR, "apps", "web", "project.json")
API_PROJECT = os.path.join(DEMO_DIR, "apps", "api", "project.json")
UI_LIB_PROJECT = os.path.join(DEMO_DIR, "libs", "shared", "ui", "project.json")
UTILS_LIB_PROJECT = os.path.join(DEMO_DIR, "libs", "shared", "utils", "project.json")
DATA_ACCESS_PROJECT = os.path.join(DEMO_DIR, "libs", "data-access", "project.json")
ESLINT_CONFIG = os.path.join(DEMO_DIR, ".eslintrc.json")
TSCONFIG_BASE = os.path.join(DEMO_DIR, "tsconfig.base.json")
CI_WORKFLOW = os.path.join(DEMO_DIR, ".github", "workflows", "ci.yml")


def _load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_yaml(path):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------
# Layer 1 — file_path_check
# ---------------------------------------------------------------------------

class TestFilePathCheck:
    """Verify all required Nx workspace configuration files exist."""

    def test_nx_json_exists(self):
        assert os.path.isfile(NX_JSON), f"Missing {NX_JSON}"

    def test_web_project_exists(self):
        assert os.path.isfile(WEB_PROJECT), f"Missing {WEB_PROJECT}"

    def test_api_project_exists(self):
        assert os.path.isfile(API_PROJECT), f"Missing {API_PROJECT}"

    def test_ui_lib_exists(self):
        assert os.path.isfile(UI_LIB_PROJECT), f"Missing {UI_LIB_PROJECT}"

    def test_utils_lib_exists(self):
        assert os.path.isfile(UTILS_LIB_PROJECT), f"Missing {UTILS_LIB_PROJECT}"

    def test_data_access_lib_exists(self):
        assert os.path.isfile(DATA_ACCESS_PROJECT), f"Missing {DATA_ACCESS_PROJECT}"

    def test_eslint_config_exists(self):
        assert os.path.isfile(ESLINT_CONFIG), f"Missing {ESLINT_CONFIG}"

    def test_tsconfig_base_exists(self):
        assert os.path.isfile(TSCONFIG_BASE), f"Missing {TSCONFIG_BASE}"

    def test_ci_workflow_exists(self):
        assert os.path.isfile(CI_WORKFLOW), f"Missing {CI_WORKFLOW}"


# ---------------------------------------------------------------------------
# Layer 2 — semantic_check
# ---------------------------------------------------------------------------

class TestSemanticNxJson:
    """Verify nx.json configuration structure."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.cfg = _load_json(NX_JSON)

    def test_affected_default_base(self):
        affected = self.cfg.get("affected", self.cfg.get("defaultBase", {}))
        if isinstance(affected, dict):
            base = affected.get("defaultBase", "")
        else:
            base = str(affected)
        # Also check top-level defaultBase
        top_base = self.cfg.get("defaultBase", "")
        assert "main" in base or "main" in top_base, (
            f"affected.defaultBase should be 'main'; got affected={affected}, top={top_base}"
        )

    def test_cacheable_operations(self):
        raw = json.dumps(self.cfg)
        for op in ["build", "lint", "test"]:
            assert op in raw, f"Expected '{op}' in cacheable operations"

    def test_target_defaults_build(self):
        td = self.cfg.get("targetDefaults", {})
        build = td.get("build", {})
        deps = build.get("dependsOn", [])
        assert "^build" in deps, f"build.dependsOn should include '^build'; got {deps}"

    def test_named_inputs_production(self):
        ni = self.cfg.get("namedInputs", {})
        assert "production" in ni, f"Expected namedInputs.production; found {list(ni.keys())}"

    def test_named_inputs_default(self):
        ni = self.cfg.get("namedInputs", {})
        assert "default" in ni, f"Expected namedInputs.default; found {list(ni.keys())}"

    def test_parallel_setting(self):
        raw = json.dumps(self.cfg)
        assert "parallel" in raw, "Expected parallel setting in task runner options"


class TestSemanticProjectConfigs:
    """Verify project.json files have correct types and tags."""

    def test_web_is_application(self):
        cfg = _load_json(WEB_PROJECT)
        assert cfg.get("projectType") == "application", (
            f"web should be 'application'; got {cfg.get('projectType')}"
        )

    def test_api_is_application(self):
        cfg = _load_json(API_PROJECT)
        assert cfg.get("projectType") == "application", (
            f"api should be 'application'; got {cfg.get('projectType')}"
        )

    def test_ui_is_library(self):
        cfg = _load_json(UI_LIB_PROJECT)
        assert cfg.get("projectType") == "library", (
            f"shared/ui should be 'library'; got {cfg.get('projectType')}"
        )

    def test_utils_is_library(self):
        cfg = _load_json(UTILS_LIB_PROJECT)
        assert cfg.get("projectType") == "library", (
            f"shared/utils should be 'library'; got {cfg.get('projectType')}"
        )

    def test_web_has_app_tag(self):
        cfg = _load_json(WEB_PROJECT)
        tags = cfg.get("tags", [])
        assert "type:app" in tags, f"web tags should include 'type:app'; got {tags}"

    def test_ui_has_ui_tag(self):
        cfg = _load_json(UI_LIB_PROJECT)
        tags = cfg.get("tags", [])
        assert "type:ui" in tags, f"shared/ui tags should include 'type:ui'; got {tags}"

    def test_utils_has_util_tag(self):
        cfg = _load_json(UTILS_LIB_PROJECT)
        tags = cfg.get("tags", [])
        assert "type:util" in tags, f"shared/utils tags should include 'type:util'; got {tags}"

    def test_data_access_has_tag(self):
        cfg = _load_json(DATA_ACCESS_PROJECT)
        tags = cfg.get("tags", [])
        assert "type:data-access" in tags, (
            f"data-access tags should include 'type:data-access'; got {tags}"
        )

    def test_web_has_build_target(self):
        cfg = _load_json(WEB_PROJECT)
        targets = cfg.get("targets", {})
        assert "build" in targets, f"web should have 'build' target; got {list(targets.keys())}"

    def test_api_has_serve_target(self):
        cfg = _load_json(API_PROJECT)
        targets = cfg.get("targets", {})
        assert "serve" in targets, f"api should have 'serve' target; got {list(targets.keys())}"


class TestSemanticEslintBoundaries:
    """Verify ESLint enforce-module-boundaries configuration."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.cfg = _load_json(ESLINT_CONFIG)

    def test_enforce_module_boundaries_rule(self):
        raw = json.dumps(self.cfg)
        assert "enforce-module-boundaries" in raw, (
            "ESLint config must include @nx/enforce-module-boundaries rule"
        )

    def test_dep_constraints_exist(self):
        raw = json.dumps(self.cfg)
        assert "depConstraints" in raw, "Must have depConstraints in module boundary rule"

    def test_enforceable_library_deps(self):
        raw = json.dumps(self.cfg)
        assert "enforceBuildableLibDependency" in raw, (
            "Expected enforceBuildableLibDependency setting"
        )

    def test_allow_array_empty(self):
        """The allow array in module boundaries should be empty."""
        raw = json.dumps(self.cfg)
        # Find the enforce-module-boundaries rule options
        rules = self.cfg.get("overrides", [{}])[0].get("rules", self.cfg.get("rules", {}))
        for key, val in rules.items():
            if "enforce-module-boundaries" in key:
                if isinstance(val, list) and len(val) > 1:
                    options = val[1]
                    allow = options.get("allow", [])
                    assert allow == [], f"allow must be empty; got {allow}"
                    return
        # Fallback: just check that "allow" appears with empty array
        assert '"allow":[]' in raw.replace(" ", "") or '"allow": []' in raw, (
            "allow array should be empty"
        )


class TestSemanticTsconfigPaths:
    """Verify TypeScript path mappings."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.cfg = _load_json(TSCONFIG_BASE)

    def test_ui_path_mapping(self):
        paths = self.cfg.get("compilerOptions", {}).get("paths", {})
        assert "@demo/shared/ui" in paths, f"Expected @demo/shared/ui path; got {list(paths.keys())}"

    def test_utils_path_mapping(self):
        paths = self.cfg.get("compilerOptions", {}).get("paths", {})
        assert "@demo/shared/utils" in paths, (
            f"Expected @demo/shared/utils path; got {list(paths.keys())}"
        )

    def test_data_access_path_mapping(self):
        paths = self.cfg.get("compilerOptions", {}).get("paths", {})
        assert "@demo/data-access" in paths, (
            f"Expected @demo/data-access path; got {list(paths.keys())}"
        )

    def test_paths_point_to_src(self):
        paths = self.cfg.get("compilerOptions", {}).get("paths", {})
        for alias, targets in paths.items():
            if "@demo" in alias:
                target_str = str(targets)
                assert "src" in target_str, (
                    f"Path {alias} should point to src/index.ts; got {targets}"
                )


# ---------------------------------------------------------------------------
# Layer 3 — functional_check
# ---------------------------------------------------------------------------

class TestFunctionalBoundaryRules:
    """Functionally verify dependency constraint rules."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.cfg = _load_json(ESLINT_CONFIG)
        # Extract depConstraints
        self.constraints = []
        raw = json.dumps(self.cfg)
        if "depConstraints" in raw:
            rules = self.cfg.get("overrides", [{}])[0].get("rules", self.cfg.get("rules", {}))
            for key, val in rules.items():
                if "enforce-module-boundaries" in key:
                    if isinstance(val, list) and len(val) > 1:
                        self.constraints = val[1].get("depConstraints", [])

    def test_app_can_depend_on_ui(self):
        for c in self.constraints:
            tag = c.get("sourceTag", "")
            allowed = c.get("onlyDependOnLibsWithTags", [])
            if tag == "type:app":
                assert "type:ui" in allowed, (
                    f"type:app should be allowed to depend on type:ui; allowed={allowed}"
                )
                return
        pytest.fail("No constraint found for type:app")

    def test_app_can_depend_on_util(self):
        for c in self.constraints:
            tag = c.get("sourceTag", "")
            allowed = c.get("onlyDependOnLibsWithTags", [])
            if tag == "type:app":
                assert "type:util" in allowed, (
                    f"type:app should depend on type:util; allowed={allowed}"
                )
                return
        pytest.fail("No constraint found for type:app")

    def test_util_cannot_depend_on_others(self):
        for c in self.constraints:
            tag = c.get("sourceTag", "")
            allowed = c.get("onlyDependOnLibsWithTags", [])
            if tag == "type:util":
                # util should only depend on util (or nothing else)
                forbidden = {"type:app", "type:ui", "type:data-access"}
                for f in forbidden:
                    assert f not in allowed, (
                        f"type:util should NOT depend on {f}; allowed={allowed}"
                    )
                return
        pytest.fail("No constraint found for type:util")

    def test_ui_can_only_depend_on_util(self):
        for c in self.constraints:
            tag = c.get("sourceTag", "")
            allowed = c.get("onlyDependOnLibsWithTags", [])
            if tag == "type:ui":
                assert "type:util" in allowed, (
                    f"type:ui should depend on type:util; allowed={allowed}"
                )
                assert "type:app" not in allowed, (
                    f"type:ui should NOT depend on type:app; allowed={allowed}"
                )
                return
        pytest.fail("No constraint found for type:ui")


class TestFunctionalCIWorkflow:
    """Verify CI workflow uses nx affected commands."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.cfg = _load_yaml(CI_WORKFLOW)

    def test_triggers(self):
        triggers = self.cfg.get(True, self.cfg.get("on", {}))
        raw = yaml.dump(self.cfg)
        assert "push" in raw or "pull_request" in raw, (
            "CI should trigger on push and/or pull_request"
        )

    def test_node_setup(self):
        raw = yaml.dump(self.cfg)
        assert "node" in raw.lower() or "setup-node" in raw, (
            "CI must set up Node.js"
        )

    def test_nx_affected_lint(self):
        raw = yaml.dump(self.cfg)
        assert "affected" in raw and "lint" in raw, (
            "CI must run nx affected --target=lint"
        )

    def test_nx_affected_test(self):
        raw = yaml.dump(self.cfg)
        assert "affected" in raw and "test" in raw, (
            "CI must run nx affected --target=test"
        )

    def test_nx_affected_build(self):
        raw = yaml.dump(self.cfg)
        assert "affected" in raw and "build" in raw, (
            "CI must run nx affected --target=build"
        )

    def test_nx_set_shas_action(self):
        raw = yaml.dump(self.cfg)
        assert "nx-set-shas" in raw, (
            "CI should use nrwl/nx-set-shas action for correct base/head"
        )


class TestFunctionalCacheConfig:
    """Verify caching configuration across nx.json and project targets."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.cfg = _load_json(NX_JSON)

    def test_build_cache_enabled(self):
        td = self.cfg.get("targetDefaults", {})
        build = td.get("build", {})
        cache = build.get("cache", None)
        raw = json.dumps(self.cfg)
        assert cache is True or "cacheableOperations" in raw, (
            "Build target should have caching enabled"
        )

    def test_test_cache_enabled(self):
        td = self.cfg.get("targetDefaults", {})
        test = td.get("test", {})
        raw = json.dumps(self.cfg)
        cache = test.get("cache", None)
        assert cache is True or "cacheableOperations" in raw, (
            "Test target should have caching enabled"
        )

    def test_build_depends_on_transitive(self):
        td = self.cfg.get("targetDefaults", {})
        build = td.get("build", {})
        deps = build.get("dependsOn", [])
        assert "^build" in deps, (
            f"build should depend on ^build for transitive deps; got {deps}"
        )

    def test_all_json_valid(self):
        """All JSON files in the demo directory must be parseable."""
        for dirpath, _, filenames in os.walk(DEMO_DIR):
            for fn in filenames:
                if fn.endswith(".json"):
                    fpath = os.path.join(dirpath, fn)
                    with open(fpath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    assert data is not None, f"Failed to parse {fpath}"
