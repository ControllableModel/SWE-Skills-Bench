"""
Test skill: nx-workspace-patterns
Verify that the Agent correctly configures an Nx monorepo with shared libraries,
computation caching, and task pipelines.
"""

import os
import re
import json
import pytest


class TestNxWorkspacePatterns:
    REPO_DIR = "/workspace/nx"

    NX_JSON = "nx.json"
    WORKSPACE_JSON = "workspace.json"
    FRONTEND_PROJECT = "apps/frontend/project.json"
    API_PROJECT = "apps/api/project.json"
    MODELS_PROJECT = "libs/shared-models/project.json"
    MODELS_INDEX = "libs/shared-models/src/index.ts"
    UTILS_PROJECT = "libs/utils/project.json"
    UTILS_INDEX = "libs/utils/src/index.ts"
    USER_MODEL = "libs/shared-models/src/models/user.ts"
    PRODUCT_MODEL = "libs/shared-models/src/models/product.ts"
    ORDER_MODEL = "libs/shared-models/src/models/order.ts"

    def _read_file(self, rel_path):
        filepath = os.path.join(self.REPO_DIR, rel_path)
        with open(filepath) as f:
            return f.read()

    def _load_json(self, rel_path):
        return json.loads(self._read_file(rel_path))

    # === File Path Checks ===

    def test_nx_json_exists(self):
        filepath = os.path.join(self.REPO_DIR, self.NX_JSON)
        assert os.path.exists(filepath), f"nx.json not found at {filepath}"

    def test_project_json_files_exist(self):
        for path in [self.FRONTEND_PROJECT, self.API_PROJECT,
                     self.MODELS_PROJECT, self.UTILS_PROJECT]:
            filepath = os.path.join(self.REPO_DIR, path)
            assert os.path.exists(filepath), f"project.json not found: {filepath}"

    def test_model_files_exist(self):
        for path in [self.USER_MODEL, self.PRODUCT_MODEL, self.ORDER_MODEL]:
            filepath = os.path.join(self.REPO_DIR, path)
            assert os.path.exists(filepath), f"Model file not found: {filepath}"

    def test_index_files_exist(self):
        for path in [self.MODELS_INDEX, self.UTILS_INDEX]:
            filepath = os.path.join(self.REPO_DIR, path)
            assert os.path.exists(filepath), f"Index file not found: {filepath}"

    # === Semantic Checks ===

    def test_nx_json_target_defaults(self):
        """Verify nx.json has targetDefaults for build, test, lint"""
        nx_config = self._load_json(self.NX_JSON)
        td = nx_config.get("targetDefaults", {})
        for target in ["build", "test", "lint"]:
            assert target in td, f"nx.json missing targetDefault: {target}"
        assert td["build"].get("cache") is True, "build target missing cache: true"

    def test_nx_json_build_depends_on_deps(self):
        """Verify build dependsOn: ['^build'] for dependency-first builds"""
        nx_config = self._load_json(self.NX_JSON)
        build = nx_config.get("targetDefaults", {}).get("build", {})
        depends = build.get("dependsOn", [])
        assert "^build" in depends, \
            "build targetDefault missing dependsOn: ['^build']"

    def test_nx_json_named_inputs(self):
        """Verify named inputs: default, production, sharedGlobals"""
        nx_config = self._load_json(self.NX_JSON)
        named = nx_config.get("namedInputs", {})
        for name in ["default", "production", "sharedGlobals"]:
            assert name in named, f"nx.json missing namedInput: {name}"

    def test_user_model_interface(self):
        """Verify User interface with required fields"""
        content = self._read_file(self.USER_MODEL)
        assert "User" in content, "user.ts missing User interface"
        for field in ["id", "email", "name", "role"]:
            assert field in content, f"User interface missing field: {field}"
        # Check role enum
        for role in ["admin", "user", "viewer"]:
            assert role in content, f"User missing role option: {role}"

    def test_product_model_interface(self):
        """Verify Product interface with price and inventory"""
        content = self._read_file(self.PRODUCT_MODEL)
        assert "Product" in content, "product.ts missing Product interface"
        for field in ["id", "name", "price", "inventory"]:
            assert field in content, f"Product missing field: {field}"

    def test_order_model_interface(self):
        """Verify Order interface with items and status"""
        content = self._read_file(self.ORDER_MODEL)
        assert "Order" in content, "order.ts missing Order interface"
        assert "OrderItem" in content, "order.ts missing OrderItem"
        for status in ["pending", "confirmed", "shipped", "delivered"]:
            assert status in content, f"Order missing status: {status}"

    def test_validate_user_function(self):
        """Verify validateUser function exists with validation"""
        content = self._read_file(self.USER_MODEL)
        assert "validateUser" in content, "Missing validateUser function"
        assert "@" in content or "email" in content, \
            "validateUser missing email validation"

    def test_utils_exports(self):
        """Verify utils index exports formatDate, slugify, ValidationError, chunk, retry"""
        content = self._read_file(self.UTILS_INDEX)
        for export in ["formatDate", "slugify", "ValidationError", "chunk", "retry"]:
            assert export in content, f"Utils index missing export: {export}"

    def test_models_index_exports(self):
        """Verify models index exports interfaces and validators"""
        content = self._read_file(self.MODELS_INDEX)
        for export in ["User", "Product", "Order", "validateUser", "validateProduct"]:
            assert export in content, f"Models index missing export: {export}"

    def test_project_tags(self):
        """Verify projects have scope and type tags"""
        frontend = self._load_json(self.FRONTEND_PROJECT)
        tags = frontend.get("tags", [])
        assert any("app" in t for t in tags), "Frontend missing scope:app tag"
        utils = self._load_json(self.UTILS_PROJECT)
        tags = utils.get("tags", [])
        assert any("shared" in t or "util" in t for t in tags), \
            "Utils missing scope:shared or type:util tag"

    # === Functional Checks ===

    def test_all_json_files_valid(self):
        """Verify all JSON files are valid"""
        for path in [self.NX_JSON, self.FRONTEND_PROJECT, self.API_PROJECT,
                     self.MODELS_PROJECT, self.UTILS_PROJECT]:
            filepath = os.path.join(self.REPO_DIR, path)
            with open(filepath) as f:
                try:
                    json.loads(f.read())
                except json.JSONDecodeError as e:
                    pytest.fail(f"{path} JSON error: {e}")

    def test_projects_have_build_target(self):
        """Verify all project.json files define a build target"""
        for path in [self.FRONTEND_PROJECT, self.API_PROJECT,
                     self.MODELS_PROJECT, self.UTILS_PROJECT]:
            config = self._load_json(path)
            targets = config.get("targets", {})
            assert "build" in targets, f"{path} missing build target"

    def test_frontend_has_serve_target(self):
        """Verify frontend project has a serve target"""
        config = self._load_json(self.FRONTEND_PROJECT)
        targets = config.get("targets", {})
        assert "serve" in targets, "Frontend missing serve target"
