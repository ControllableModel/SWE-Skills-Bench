"""
Tests for the nx-workspace-patterns skill.

Validates that Nx workspace configuration was implemented including
project.json files, module boundary ESLint rules, tsconfig path aliases,
and nx.json configuration.

Repo: nx (https://github.com/nrwl/nx)
"""

import json
import os
import re

REPO_DIR = "/workspace/nx"


class TestFilePathCheck:
    """Verify that project.json and config files were created."""

    def test_dashboard_project_json_exists(self):
        candidates = [
            os.path.join(REPO_DIR, "apps", "dashboard", "project.json"),
            os.path.join(REPO_DIR, "packages", "dashboard", "project.json"),
        ]
        found = any(os.path.isfile(c) for c in candidates)
        assert found, "Expected project.json for dashboard app"

    def test_nx_json_exists(self):
        path = os.path.join(REPO_DIR, "nx.json")
        assert os.path.isfile(path), f"Expected nx.json at {path}"

    def test_tsconfig_base_exists(self):
        path = os.path.join(REPO_DIR, "tsconfig.base.json")
        assert os.path.isfile(path), f"Expected tsconfig.base.json at {path}"

    def test_eslintrc_exists(self):
        candidates = [
            os.path.join(REPO_DIR, ".eslintrc.json"),
            os.path.join(REPO_DIR, ".eslintrc.js"),
            os.path.join(REPO_DIR, "eslint.config.js"),
            os.path.join(REPO_DIR, ".eslintrc"),
        ]
        found = any(os.path.isfile(c) for c in candidates)
        assert found, "Expected ESLint config file at workspace root"


class TestSemanticProjectJson:
    """Verify project.json structure and tags."""

    def _find_project_json_files(self):
        results = []
        for root, dirs, files in os.walk(REPO_DIR):
            # Skip node_modules / .git
            dirs[:] = [d for d in dirs if d not in ("node_modules", ".git")]
            for f in files:
                if f == "project.json":
                    results.append(os.path.join(root, f))
        return results

    def test_at_least_four_projects(self):
        """Dashboard app + 3 libraries."""
        projects = self._find_project_json_files()
        assert len(projects) >= 4, (
            f"Expected >= 4 project.json files, found {len(projects)}"
        )

    def test_dashboard_is_application(self):
        projects = self._find_project_json_files()
        found_app = False
        for p in projects:
            with open(p, "r") as f:
                data = json.load(f)
            if data.get("projectType") == "application":
                found_app = True
                break
        assert found_app, "Expected at least one project with projectType: application"

    def test_libraries_have_correct_type(self):
        projects = self._find_project_json_files()
        lib_count = 0
        for p in projects:
            with open(p, "r") as f:
                data = json.load(f)
            if data.get("projectType") == "library":
                lib_count += 1
        assert lib_count >= 3, (
            f"Expected >= 3 libraries, found {lib_count}"
        )

    def test_project_tags(self):
        projects = self._find_project_json_files()
        tagged = 0
        for p in projects:
            with open(p, "r") as f:
                data = json.load(f)
            if "tags" in data and len(data["tags"]) > 0:
                tagged += 1
        assert tagged >= 3, (
            f"Expected >= 3 projects with tags, found {tagged}"
        )

    def test_tag_type_scope(self):
        """Tags should include type: and/or scope: prefixes."""
        projects = self._find_project_json_files()
        type_tags = []
        for p in projects:
            with open(p, "r") as f:
                data = json.load(f)
            for tag in data.get("tags", []):
                if tag.startswith("type:") or tag.startswith("scope:"):
                    type_tags.append(tag)
        assert len(type_tags) >= 2, (
            f"Expected tags with type:/scope: prefix, found {type_tags}"
        )


class TestSemanticModuleBoundary:
    """Verify module boundary ESLint rules."""

    def _read_eslint_config(self):
        for candidate in [".eslintrc.json", ".eslintrc"]:
            path = os.path.join(REPO_DIR, candidate)
            if os.path.isfile(path):
                with open(path, "r") as f:
                    return f.read()
        # Also try JS format
        for candidate in [".eslintrc.js", "eslint.config.js"]:
            path = os.path.join(REPO_DIR, candidate)
            if os.path.isfile(path):
                with open(path, "r") as f:
                    return f.read()
        return ""

    def test_enforce_module_boundaries_rule(self):
        content = self._read_eslint_config()
        assert re.search(r"enforce-module-boundaries|@nx/enforce-module-boundaries", content), (
            "Expected @nx/enforce-module-boundaries ESLint rule"
        )

    def test_dep_constraints(self):
        content = self._read_eslint_config()
        assert re.search(r"depConstraints|dep.*constraints", content), (
            "Expected depConstraints in enforce-module-boundaries rule"
        )

    def test_app_can_depend_on_libs(self):
        content = self._read_eslint_config()
        for lib_type in ["ui", "data-access", "util"]:
            if lib_type in content:
                break
        else:
            assert False, (
                "Expected lib types (ui, data-access, util) in dep constraints"
            )


class TestSemanticTsconfig:
    """Verify tsconfig path aliases."""

    def _read_tsconfig(self):
        path = os.path.join(REPO_DIR, "tsconfig.base.json")
        with open(path, "r") as f:
            return f.read()

    def test_paths_defined(self):
        content = self._read_tsconfig()
        assert re.search(r'"paths"', content), (
            "Expected paths in tsconfig.base.json"
        )

    def test_workspace_alias_prefix(self):
        content = self._read_tsconfig()
        assert re.search(r"@workspace/", content), (
            "Expected @workspace/* path alias prefix"
        )


class TestSemanticNxJson:
    """Verify nx.json workspace configuration."""

    def _read_nx_json(self):
        path = os.path.join(REPO_DIR, "nx.json")
        with open(path, "r") as f:
            return json.load(f)

    def test_default_base(self):
        data = self._read_nx_json()
        affected = data.get("affected", data.get("defaultBase", None))
        if isinstance(affected, dict):
            base = affected.get("defaultBase", "")
        else:
            base = data.get("defaultBase", "")
        assert base == "main" or "main" in json.dumps(data), (
            "Expected defaultBase: main in nx.json"
        )

    def test_named_inputs(self):
        data = self._read_nx_json()
        assert "namedInputs" in data, "Expected namedInputs in nx.json"
        named = data["namedInputs"]
        assert "production" in named or "default" in named, (
            "Expected 'production' or 'default' named inputs"
        )

    def test_target_defaults(self):
        data = self._read_nx_json()
        assert "targetDefaults" in data, "Expected targetDefaults in nx.json"
        defaults = data["targetDefaults"]
        target_keys = list(defaults.keys())
        assert len(target_keys) >= 2, (
            f"Expected >= 2 target defaults (build, test, lint), found {target_keys}"
        )

    def test_caching(self):
        data = self._read_nx_json()
        nx_str = json.dumps(data)
        assert re.search(r"cache|cacheableOperations", nx_str), (
            "Expected caching configuration in nx.json"
        )


class TestFunctionalJsonValidity:
    """Validate JSON files are syntactically correct."""

    def test_nx_json_valid(self):
        path = os.path.join(REPO_DIR, "nx.json")
        with open(path, "r") as f:
            data = json.load(f)
        assert isinstance(data, dict), "nx.json should be a valid JSON object"

    def test_tsconfig_base_valid(self):
        path = os.path.join(REPO_DIR, "tsconfig.base.json")
        with open(path, "r") as f:
            content = f.read()
        # tsconfig may have comments — strip // comments for parsing
        stripped = re.sub(r"//.*$", "", content, flags=re.MULTILINE)
        stripped = re.sub(r"/\*.*?\*/", "", stripped, flags=re.DOTALL)
        data = json.loads(stripped)
        assert isinstance(data, dict), "tsconfig.base.json should be valid JSON"

    def test_project_json_files_valid(self):
        for root, dirs, files in os.walk(REPO_DIR):
            dirs[:] = [d for d in dirs if d not in ("node_modules", ".git")]
            for f in files:
                if f == "project.json":
                    path = os.path.join(root, f)
                    with open(path, "r") as fh:
                        data = json.load(fh)
                    assert isinstance(data, dict), (
                        f"{path} should be valid JSON object"
                    )
