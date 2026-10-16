"""
Test skill: nx-workspace-patterns
Verify that the Agent implements a Project Constraint Enforcement Plugin for Nx —
ConstraintChecker (checkAll, checkProject, checkDependency), plus four rules:
layer-rule, circular-rule, public-api-rule, depth-rule.
"""

import os
import re
import subprocess
import pytest


class TestNxWorkspacePatterns:
    REPO_DIR = "/workspace/nx"

    # ────── helpers ──────

    def _read(self, rel_path):
        fpath = os.path.join(self.REPO_DIR, rel_path)
        with open(fpath, "r") as f:
            return f.read()

    def _exists(self, rel_path):
        return os.path.isfile(os.path.join(self.REPO_DIR, rel_path))

    def _find_file(self, candidates):
        for c in candidates:
            if self._exists(c):
                return c
        return None

    # === File Path Checks ===

    def test_constraint_checker_exists(self):
        """constraint-checker.ts must exist"""
        assert self._exists(
            "packages/nx/src/plugins/project-constraints/constraint-checker.ts"
        )

    def test_layer_rule_exists(self):
        """layer-rule.ts must exist"""
        assert self._exists(
            "packages/nx/src/plugins/project-constraints/layer-rule.ts"
        )

    def test_circular_rule_exists(self):
        """circular-rule.ts must exist"""
        assert self._exists(
            "packages/nx/src/plugins/project-constraints/circular-rule.ts"
        )

    def test_public_api_rule_exists(self):
        """public-api-rule.ts must exist"""
        assert self._exists(
            "packages/nx/src/plugins/project-constraints/public-api-rule.ts"
        )

    def test_depth_rule_exists(self):
        """depth-rule.ts must exist"""
        assert self._exists(
            "packages/nx/src/plugins/project-constraints/depth-rule.ts"
        )

    # === Semantic Checks — ConstraintChecker ===

    def test_constraint_checker_class_or_function(self):
        """ConstraintChecker must be defined"""
        src = self._read(
            "packages/nx/src/plugins/project-constraints/constraint-checker.ts"
        )
        assert "ConstraintChecker" in src, "ConstraintChecker not found"

    def test_check_all_method(self):
        """checkAll method must exist"""
        src = self._read(
            "packages/nx/src/plugins/project-constraints/constraint-checker.ts"
        )
        assert "checkAll" in src, "checkAll method not found"

    def test_check_project_method(self):
        """checkProject method must exist"""
        src = self._read(
            "packages/nx/src/plugins/project-constraints/constraint-checker.ts"
        )
        assert "checkProject" in src, "checkProject method not found"

    def test_check_dependency_method(self):
        """checkDependency method must exist"""
        src = self._read(
            "packages/nx/src/plugins/project-constraints/constraint-checker.ts"
        )
        assert "checkDependency" in src, "checkDependency method not found"

    def test_constraint_violation_interface(self):
        """ConstraintViolation interface or type must be defined"""
        base = "packages/nx/src/plugins/project-constraints"
        found = False
        for fn in os.listdir(os.path.join(self.REPO_DIR, base)):
            if fn.endswith(".ts"):
                content = self._read(os.path.join(base, fn))
                if "ConstraintViolation" in content:
                    found = True
                    break
        assert found, "ConstraintViolation interface/type not found"

    # === Semantic Checks — layer-rule ===

    def test_layer_rule_export(self):
        """layer-rule must export a rule function or class"""
        src = self._read(
            "packages/nx/src/plugins/project-constraints/layer-rule.ts"
        )
        assert re.search(r'export\s+(function|class|const)', src), (
            "No exported rule in layer-rule.ts"
        )

    def test_layer_order_enforcement(self):
        """Must enforce layer ordering"""
        src = self._read(
            "packages/nx/src/plugins/project-constraints/layer-rule.ts"
        )
        lower = src.lower()
        assert any(k in lower for k in ["layer", "order", "level", "hierarchy"]), (
            "Layer order enforcement not found"
        )

    # === Semantic Checks — circular-rule ===

    def test_circular_rule_dfs(self):
        """circular-rule must detect cycles (DFS or similar)"""
        src = self._read(
            "packages/nx/src/plugins/project-constraints/circular-rule.ts"
        )
        lower = src.lower()
        assert any(k in lower for k in ["cycle", "circular", "visited", "dfs", "stack"]), (
            "Cycle detection algorithm not found"
        )

    # === Semantic Checks — public-api-rule ===

    def test_public_api_boundary(self):
        """public-api-rule must enforce public API boundary (index.ts / barrel)"""
        src = self._read(
            "packages/nx/src/plugins/project-constraints/public-api-rule.ts"
        )
        lower = src.lower()
        assert any(k in lower for k in ["public", "barrel", "index", "export", "boundary"]), (
            "Public API boundary enforcement not found"
        )

    # === Semantic Checks — depth-rule ===

    def test_depth_rule_max_depth(self):
        """depth-rule must enforce max dependency depth (BFS or similar)"""
        src = self._read(
            "packages/nx/src/plugins/project-constraints/depth-rule.ts"
        )
        lower = src.lower()
        assert any(k in lower for k in ["depth", "bfs", "breadth", "max", "level"]), (
            "Depth enforcement not found"
        )

    # === Semantic Checks — Tests ===

    def test_constraint_checker_test_exists(self):
        """Test file for constraint-checker must exist"""
        base = "packages/nx/src/plugins/project-constraints"
        found = False
        for fn in os.listdir(os.path.join(self.REPO_DIR, base)):
            if "constraint-checker" in fn and ("spec" in fn or "test" in fn):
                found = True
                break
        assert found, "constraint-checker test file not found"

    # === Functional Checks ===

    def test_typescript_compile(self):
        """TypeScript files must compile without errors"""
        result = subprocess.run(
            ["npx", "tsc", "--noEmit", "--project",
             "packages/nx/tsconfig.lib.json"],
            capture_output=True, text=True, cwd=self.REPO_DIR, timeout=300,
        )
        # Fallback: try project-level tsconfig
        if result.returncode != 0:
            result = subprocess.run(
                ["npx", "tsc", "--noEmit",
                 "packages/nx/src/plugins/project-constraints/constraint-checker.ts",
                 "--skipLibCheck"],
                capture_output=True, text=True, cwd=self.REPO_DIR, timeout=300,
            )
        assert result.returncode == 0, (
            f"TypeScript compilation failed:\n{result.stdout}\n{result.stderr}"
        )

    def test_jest_constraint_checker(self):
        """Jest tests for constraint-checker must pass"""
        result = subprocess.run(
            ["npx", "jest", "--testPathPattern",
             "project-constraints", "--passWithNoTests"],
            capture_output=True, text=True, cwd=self.REPO_DIR, timeout=300,
        )
        assert result.returncode == 0, (
            f"Jest tests failed:\n{result.stdout}\n{result.stderr}"
        )

    def test_build_nx_package(self):
        """Nx package must build"""
        result = subprocess.run(
            ["npx", "nx", "build", "nx"],
            capture_output=True, text=True, cwd=self.REPO_DIR, timeout=300,
        )
        # Accept either success or the project might use a different build target
        if result.returncode != 0:
            result = subprocess.run(
                ["npm", "run", "build", "--", "--scope=nx"],
                capture_output=True, text=True, cwd=self.REPO_DIR, timeout=300,
            )
        assert result.returncode == 0, (
            f"Build failed:\n{result.stdout}\n{result.stderr}"
        )
