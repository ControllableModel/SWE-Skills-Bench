"""
Test skill: nx-workspace-patterns
Verify that the Agent configures an Nx monorepo with React/Express apps,
shared libraries, module boundary enforcement, cacheable targets,
TypeScript path aliases, and CI workflow with nx affected.
"""

import os
import re
import json
import pytest

try:
    import yaml
except ImportError:
    yaml = None


def load_json(path):
    with open(path) as f:
        return json.load(f)


class TestNxWorkspacePatterns:
    REPO_DIR = "/workspace/nx"

    # === File Path Checks ===

    def test_nx_json_exists(self):
        assert os.path.exists(os.path.join(self.REPO_DIR, "nx.json"))

    def test_storefront_project_json_exists(self):
        assert os.path.exists(
            os.path.join(self.REPO_DIR, "apps/storefront/project.json")
        )

    def test_api_project_json_exists(self):
        assert os.path.exists(
            os.path.join(self.REPO_DIR, "apps/api/project.json")
        )

    def test_library_project_jsons_exist(self):
        for lib in (
            "feature-product",
            "feature-cart",
            "ui-components",
            "data-access-api",
            "util-formatting",
        ):
            path = os.path.join(self.REPO_DIR, f"libs/{lib}/project.json")
            assert os.path.exists(path), f"Missing libs/{lib}/project.json"

    def test_eslintrc_exists(self):
        assert os.path.exists(os.path.join(self.REPO_DIR, ".eslintrc.json"))

    def test_ci_workflow_exists(self):
        assert os.path.exists(
            os.path.join(self.REPO_DIR, ".github/workflows/ci.yml")
        )

    def test_tsconfig_base_exists(self):
        assert os.path.exists(os.path.join(self.REPO_DIR, "tsconfig.base.json"))

    # === Semantic Checks ===

    def test_nx_json_has_cacheable_operations(self):
        """nx.json should define cacheable operations for build/lint/test"""
        data = load_json(os.path.join(self.REPO_DIR, "nx.json"))
        content_str = json.dumps(data)
        # Check either in tasksRunnerOptions or targetDefaults
        assert "cache" in content_str or "cacheableOperations" in content_str, (
            "nx.json should configure caching"
        )

    def test_nx_json_has_named_inputs(self):
        """nx.json should define named inputs (default, production, sharedGlobals)"""
        data = load_json(os.path.join(self.REPO_DIR, "nx.json"))
        named = data.get("namedInputs", {})
        assert "default" in named, "Missing 'default' named input"
        assert "production" in named, "Missing 'production' named input"

    def test_nx_json_build_depends_on_caret_build(self):
        """Build target should depend on ^build for topological ordering"""
        path = os.path.join(self.REPO_DIR, "nx.json")
        with open(path) as f:
            content = f.read()
        assert "^build" in content, "Build should depend on ^build"

    def test_storefront_tags(self):
        """Storefront should have type:app and scope:storefront tags"""
        data = load_json(
            os.path.join(self.REPO_DIR, "apps/storefront/project.json")
        )
        tags = data.get("tags", [])
        assert "type:app" in tags, "Missing type:app tag"
        assert "scope:storefront" in tags, "Missing scope:storefront tag"

    def test_storefront_is_application(self):
        """Storefront should be projectType: application"""
        data = load_json(
            os.path.join(self.REPO_DIR, "apps/storefront/project.json")
        )
        assert data.get("projectType") == "application"

    def test_api_tags(self):
        """API should have type:app and scope:api tags"""
        data = load_json(
            os.path.join(self.REPO_DIR, "apps/api/project.json")
        )
        tags = data.get("tags", [])
        assert "type:app" in tags, "Missing type:app tag"
        assert "scope:api" in tags, "Missing scope:api tag"

    def test_library_tags_follow_convention(self):
        """Libraries should have proper type and scope tags"""
        expected = {
            "feature-product": ("type:feature", "scope:product"),
            "feature-cart": ("type:feature", "scope:cart"),
            "ui-components": ("type:ui", "scope:shared"),
            "data-access-api": ("type:data-access", "scope:shared"),
            "util-formatting": ("type:util", "scope:shared"),
        }
        for lib, (type_tag, scope_tag) in expected.items():
            data = load_json(
                os.path.join(self.REPO_DIR, f"libs/{lib}/project.json")
            )
            tags = data.get("tags", [])
            assert type_tag in tags, f"{lib} missing {type_tag}"
            assert scope_tag in tags, f"{lib} missing {scope_tag}"

    def test_module_boundary_rules(self):
        """ESLint config should have enforce-module-boundaries rule"""
        path = os.path.join(self.REPO_DIR, ".eslintrc.json")
        with open(path) as f:
            content = f.read()
        assert "enforce-module-boundaries" in content or "@nx/enforce-module-boundaries" in content, (
            "Missing module boundary enforcement rule"
        )

    def test_module_boundary_constraints(self):
        """Module boundaries should define dependency constraints by type"""
        data = load_json(os.path.join(self.REPO_DIR, ".eslintrc.json"))
        content_str = json.dumps(data)
        for tag in ("type:app", "type:feature", "type:ui", "type:data-access", "type:util"):
            assert tag in content_str, f"Missing constraint for {tag}"

    def test_tsconfig_path_aliases(self):
        """tsconfig.base.json should define @eshop/* path aliases"""
        data = load_json(os.path.join(self.REPO_DIR, "tsconfig.base.json"))
        paths = data.get("compilerOptions", {}).get("paths", {})
        for lib in (
            "feature-product",
            "feature-cart",
            "ui-components",
            "data-access-api",
            "util-formatting",
        ):
            key = f"@eshop/{lib}"
            assert key in paths, f"Missing path alias for {key}"

    def test_ci_workflow_uses_nx_affected(self):
        """CI workflow should use nx affected for optimized builds"""
        path = os.path.join(self.REPO_DIR, ".github/workflows/ci.yml")
        with open(path) as f:
            content = f.read()
        assert "nx affected" in content or "nx:affected" in content, (
            "CI should use nx affected"
        )

    def test_ci_workflow_derives_shas(self):
        """CI workflow should derive SHAs for affected calculation"""
        path = os.path.join(self.REPO_DIR, ".github/workflows/ci.yml")
        with open(path) as f:
            content = f.read()
        assert "nrwl/nx-set-shas" in content or "nx-set-shas" in content, (
            "CI should derive SHAs with nx-set-shas"
        )

    # === Functional Checks ===

    def test_all_json_files_valid(self):
        """All project.json and config JSON files should be valid"""
        json_files = [
            "nx.json",
            ".eslintrc.json",
            "tsconfig.base.json",
            "apps/storefront/project.json",
            "apps/api/project.json",
        ]
        for lib in ("feature-product", "feature-cart", "ui-components", "data-access-api", "util-formatting"):
            json_files.append(f"libs/{lib}/project.json")
        for jf in json_files:
            path = os.path.join(self.REPO_DIR, jf)
            try:
                with open(path) as f:
                    json.load(f)
            except (json.JSONDecodeError, FileNotFoundError) as e:
                pytest.fail(f"{jf} is invalid: {e}")

    def test_ci_workflow_valid_yaml(self):
        """CI workflow should be valid YAML"""
        if yaml is None:
            pytest.skip("PyYAML not available")
        path = os.path.join(self.REPO_DIR, ".github/workflows/ci.yml")
        with open(path) as f:
            try:
                data = yaml.safe_load(f)
            except yaml.YAMLError as e:
                pytest.fail(f"ci.yml YAML error: {e}")
        assert "jobs" in data, "Workflow must have jobs"

    def test_libraries_are_project_type_library(self):
        """All libs should have projectType: library"""
        for lib in ("feature-product", "feature-cart", "ui-components", "data-access-api", "util-formatting"):
            data = load_json(
                os.path.join(self.REPO_DIR, f"libs/{lib}/project.json")
            )
            assert data.get("projectType") == "library", (
                f"{lib} should be projectType: library"
            )
