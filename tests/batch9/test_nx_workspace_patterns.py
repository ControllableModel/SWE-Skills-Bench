"""
Test skill: nx-workspace-patterns
Verify that the Agent creates nx.json pipeline configuration, multiple project.json files,
.eslintrc.json module boundaries, and tsconfig.base.json in an Nx workspace.
"""

import os
import re
import json
import subprocess
import pytest


class TestNxWorkspacePatterns:
    REPO_DIR = "/workspace/nx"

    # === File Path Checks ===

    def test_nx_json_exists(self):
        """Verify nx.json exists at project root"""
        assert os.path.isfile(os.path.join(self.REPO_DIR, "nx.json")), "nx.json not found"

    def test_project_json_files_exist(self):
        """Verify at least 6 project.json files exist"""
        project_jsons = []
        for root, dirs, files in os.walk(self.REPO_DIR):
            if "node_modules" in root or ".git" in root:
                continue
            for f in files:
                if f == "project.json":
                    project_jsons.append(os.path.join(root, f))
        assert len(project_jsons) >= 6, f"Expected at least 6 project.json files, found {len(project_jsons)}"

    # === Semantic Checks ===

    def test_nx_json_valid_json(self):
        """Verify nx.json is valid JSON"""
        nx_path = os.path.join(self.REPO_DIR, "nx.json")
        with open(nx_path) as fh:
            data = json.load(fh)
        assert isinstance(data, dict), "nx.json is not a JSON object"

    def test_nx_json_has_target_defaults(self):
        """Verify nx.json defines targetDefaults or tasksRunnerOptions"""
        nx_path = os.path.join(self.REPO_DIR, "nx.json")
        with open(nx_path) as fh:
            data = json.load(fh)
        has_config = (
            "targetDefaults" in data
            or "tasksRunnerOptions" in data
            or "namedInputs" in data
        )
        assert has_config, "nx.json missing targetDefaults or tasksRunnerOptions"

    def test_project_json_has_targets(self):
        """Verify project.json files define build/test targets"""
        project_jsons = self._find_project_jsons()
        any_target = False
        for pj in project_jsons[:6]:
            with open(pj) as fh:
                data = json.load(fh)
            if "targets" in data:
                any_target = True
                break
        assert any_target, "No project.json files with 'targets' found"

    def test_eslintrc_module_boundaries(self):
        """Verify .eslintrc.json has module boundary rule"""
        found = False
        for root, dirs, files in os.walk(self.REPO_DIR):
            if "node_modules" in root or ".git" in root:
                continue
            for f in files:
                if f in (".eslintrc.json", ".eslintrc"):
                    fpath = os.path.join(root, f)
                    with open(fpath) as fh:
                        content = fh.read()
                    if "enforce-module-boundaries" in content or "module-boundary" in content.lower():
                        found = True
                        break
            if found:
                break
        assert found, ".eslintrc.json with module boundary rules not found"

    def test_tsconfig_base_exists(self):
        """Verify tsconfig.base.json exists"""
        ts_path = os.path.join(self.REPO_DIR, "tsconfig.base.json")
        assert os.path.isfile(ts_path), "tsconfig.base.json not found"

    def test_tsconfig_base_has_paths(self):
        """Verify tsconfig.base.json defines path aliases"""
        ts_path = os.path.join(self.REPO_DIR, "tsconfig.base.json")
        with open(ts_path) as fh:
            data = json.load(fh)
        compiler_opts = data.get("compilerOptions", {})
        assert "paths" in compiler_opts, "tsconfig.base.json missing compilerOptions.paths"
        assert len(compiler_opts["paths"]) >= 1, "tsconfig.base.json paths is empty"

    # === Functional Checks ===

    def test_project_json_valid_json(self):
        """Verify all project.json files are valid JSON"""
        project_jsons = self._find_project_jsons()
        for pj in project_jsons:
            with open(pj) as fh:
                data = json.load(fh)
            assert isinstance(data, dict), f"{pj} is not a JSON object"

    def test_project_json_has_name(self):
        """Verify project.json files have a name field"""
        project_jsons = self._find_project_jsons()
        named = 0
        for pj in project_jsons[:6]:
            with open(pj) as fh:
                data = json.load(fh)
            if "name" in data:
                named += 1
        assert named >= 3, f"Only {named} project.json files have a name field"

    def test_no_circular_dependencies(self):
        """Verify project dependencies don't create obvious circular references"""
        project_jsons = self._find_project_jsons()
        dep_map = {}
        for pj in project_jsons:
            with open(pj) as fh:
                data = json.load(fh)
            name = data.get("name")
            if name:
                deps = []
                targets = data.get("targets", {})
                for tgt in targets.values():
                    if isinstance(tgt, dict) and "dependsOn" in tgt:
                        for dep in tgt["dependsOn"]:
                            if isinstance(dep, dict) and "projects" in dep:
                                deps.extend(dep["projects"])
                            elif isinstance(dep, str) and dep.startswith("^"):
                                pass
                dep_map[name] = deps
        for name, deps in dep_map.items():
            if name in deps:
                pytest.fail(f"Project {name} depends on itself")

    def _find_project_jsons(self):
        result = []
        for root, dirs, files in os.walk(self.REPO_DIR):
            if "node_modules" in root or ".git" in root:
                continue
            for f in files:
                if f == "project.json":
                    result.append(os.path.join(root, f))
        return result
