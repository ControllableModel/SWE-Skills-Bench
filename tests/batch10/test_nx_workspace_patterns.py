"""
Test skill: nx-workspace-patterns
Verify that the Agent correctly implements a project dependency graph
analyzer with module boundary enforcement for Nx workspace.
"""

import os
import re
import subprocess
import pytest


class TestNxWorkspacePatterns:
    REPO_DIR = "/workspace/nx"

    # === File Path Checks ===

    def test_dependency_analyzer_exists(self):
        """Verify dependency-analyzer.ts was created"""
        path = os.path.join(
            self.REPO_DIR,
            "packages/nx/src/graph/dependency-analyzer.ts",
        )
        assert os.path.exists(path), "dependency-analyzer.ts not found"

    def test_dependency_analyzer_spec_exists(self):
        """Verify dependency-analyzer.spec.ts was created"""
        path = os.path.join(
            self.REPO_DIR,
            "packages/nx/src/graph/dependency-analyzer.spec.ts",
        )
        assert os.path.exists(path), "dependency-analyzer.spec.ts not found"

    def test_boundary_enforcer_exists(self):
        """Verify boundary-enforcer.ts was created"""
        path = os.path.join(
            self.REPO_DIR,
            "packages/nx/src/graph/boundary-enforcer.ts",
        )
        assert os.path.exists(path), "boundary-enforcer.ts not found"

    def test_boundary_enforcer_spec_exists(self):
        """Verify boundary-enforcer.spec.ts was created"""
        path = os.path.join(
            self.REPO_DIR,
            "packages/nx/src/graph/boundary-enforcer.spec.ts",
        )
        assert os.path.exists(path), "boundary-enforcer.spec.ts not found"

    def test_affected_calculator_exists(self):
        """Verify affected-calculator.ts was created"""
        path = os.path.join(
            self.REPO_DIR,
            "packages/nx/src/graph/affected-calculator.ts",
        )
        assert os.path.exists(path), "affected-calculator.ts not found"

    def test_affected_calculator_spec_exists(self):
        """Verify affected-calculator.spec.ts was created"""
        path = os.path.join(
            self.REPO_DIR,
            "packages/nx/src/graph/affected-calculator.spec.ts",
        )
        assert os.path.exists(path), "affected-calculator.spec.ts not found"

    def test_cache_manager_exists(self):
        """Verify cache-manager.ts was created"""
        path = os.path.join(
            self.REPO_DIR,
            "packages/nx/src/graph/cache-manager.ts",
        )
        assert os.path.exists(path), "cache-manager.ts not found"

    def test_cache_manager_spec_exists(self):
        """Verify cache-manager.spec.ts was created"""
        path = os.path.join(
            self.REPO_DIR,
            "packages/nx/src/graph/cache-manager.spec.ts",
        )
        assert os.path.exists(path), "cache-manager.spec.ts not found"

    # === Semantic Checks: DependencyAnalyzer ===

    def test_dependency_analyzer_class(self):
        """Verify DependencyAnalyzer class is exported"""
        path = os.path.join(
            self.REPO_DIR,
            "packages/nx/src/graph/dependency-analyzer.ts",
        )
        with open(path) as f:
            content = f.read()
        assert "class DependencyAnalyzer" in content, (
            "DependencyAnalyzer class should be defined"
        )

    def test_build_graph_method(self):
        """Verify buildGraph method is defined"""
        path = os.path.join(
            self.REPO_DIR,
            "packages/nx/src/graph/dependency-analyzer.ts",
        )
        with open(path) as f:
            content = f.read()
        assert "buildGraph" in content, "Should have buildGraph method"

    def test_topological_order_method(self):
        """Verify getTopologicalOrder method is defined"""
        path = os.path.join(
            self.REPO_DIR,
            "packages/nx/src/graph/dependency-analyzer.ts",
        )
        with open(path) as f:
            content = f.read()
        assert "getTopologicalOrder" in content, (
            "Should have getTopologicalOrder method"
        )

    def test_circular_dependency_error(self):
        """Verify CircularDependencyError is defined"""
        path = os.path.join(
            self.REPO_DIR,
            "packages/nx/src/graph/dependency-analyzer.ts",
        )
        with open(path) as f:
            content = f.read()
        assert "CircularDependencyError" in content, (
            "CircularDependencyError should be defined"
        )

    def test_project_graph_type(self):
        """Verify ProjectGraph type with nodes and dependencies"""
        path = os.path.join(
            self.REPO_DIR,
            "packages/nx/src/graph/dependency-analyzer.ts",
        )
        with open(path) as f:
            content = f.read()
        assert "ProjectGraph" in content, "ProjectGraph type should be defined"
        assert "nodes" in content, "ProjectGraph should have nodes"
        assert "dependencies" in content, "ProjectGraph should have dependencies"

    # === Semantic Checks: BoundaryEnforcer ===

    def test_boundary_enforcer_class(self):
        """Verify BoundaryEnforcer class is exported"""
        path = os.path.join(
            self.REPO_DIR,
            "packages/nx/src/graph/boundary-enforcer.ts",
        )
        with open(path) as f:
            content = f.read()
        assert "class BoundaryEnforcer" in content, (
            "BoundaryEnforcer class should be defined"
        )

    def test_enforce_method(self):
        """Verify enforce method is defined"""
        path = os.path.join(
            self.REPO_DIR,
            "packages/nx/src/graph/boundary-enforcer.ts",
        )
        with open(path) as f:
            content = f.read()
        assert "enforce" in content, "Should have enforce method"

    def test_dep_constraint_type(self):
        """Verify DepConstraint type with sourceTag and onlyDependOnLibsWithTags"""
        path = os.path.join(
            self.REPO_DIR,
            "packages/nx/src/graph/boundary-enforcer.ts",
        )
        with open(path) as f:
            content = f.read()
        assert "DepConstraint" in content, "DepConstraint type should be defined"
        assert "sourceTag" in content, "Should have sourceTag field"
        assert "onlyDependOnLibsWithTags" in content, (
            "Should have onlyDependOnLibsWithTags field"
        )

    def test_boundary_violation_type(self):
        """Verify BoundaryViolation type is defined"""
        path = os.path.join(
            self.REPO_DIR,
            "packages/nx/src/graph/boundary-enforcer.ts",
        )
        with open(path) as f:
            content = f.read()
        assert "BoundaryViolation" in content, (
            "BoundaryViolation type should be defined"
        )

    def test_type_tag_rules(self):
        """Verify type:app, type:feature, type:ui, type:util rules"""
        path = os.path.join(
            self.REPO_DIR,
            "packages/nx/src/graph/boundary-enforcer.ts",
        )
        with open(path) as f:
            content = f.read()
        for tag in ["type:app", "type:feature", "type:ui", "type:util"]:
            assert tag in content, f"Should have rule for {tag}"

    # === Semantic Checks: AffectedCalculator ===

    def test_affected_calculator_class(self):
        """Verify AffectedCalculator class is exported"""
        path = os.path.join(
            self.REPO_DIR,
            "packages/nx/src/graph/affected-calculator.ts",
        )
        with open(path) as f:
            content = f.read()
        assert "class AffectedCalculator" in content, (
            "AffectedCalculator class should be defined"
        )

    def test_get_affected_projects_method(self):
        """Verify getAffectedProjects method is defined"""
        path = os.path.join(
            self.REPO_DIR,
            "packages/nx/src/graph/affected-calculator.ts",
        )
        with open(path) as f:
            content = f.read()
        assert "getAffectedProjects" in content, (
            "Should have getAffectedProjects method"
        )

    def test_affected_handles_global_files(self):
        """Verify nx.json or package.json change marks all affected"""
        path = os.path.join(
            self.REPO_DIR,
            "packages/nx/src/graph/affected-calculator.ts",
        )
        with open(path) as f:
            content = f.read()
        assert "nx.json" in content or "package.json" in content, (
            "Should treat global config changes as all-affected"
        )

    # === Semantic Checks: CacheManager ===

    def test_cache_manager_class(self):
        """Verify CacheManager class is exported"""
        path = os.path.join(
            self.REPO_DIR,
            "packages/nx/src/graph/cache-manager.ts",
        )
        with open(path) as f:
            content = f.read()
        assert "class CacheManager" in content, (
            "CacheManager class should be defined"
        )

    def test_compute_hash_method(self):
        """Verify computeHash method uses SHA-256"""
        path = os.path.join(
            self.REPO_DIR,
            "packages/nx/src/graph/cache-manager.ts",
        )
        with open(path) as f:
            content = f.read()
        assert "computeHash" in content, "Should have computeHash method"
        assert "sha256" in content.lower() or "SHA-256" in content, (
            "Should use SHA-256"
        )

    def test_store_and_retrieve(self):
        """Verify store and retrieve methods"""
        path = os.path.join(
            self.REPO_DIR,
            "packages/nx/src/graph/cache-manager.ts",
        )
        with open(path) as f:
            content = f.read()
        assert "store" in content, "Should have store method"
        assert "retrieve" in content, "Should have retrieve method"

    def test_invalidate_method(self):
        """Verify invalidate method"""
        path = os.path.join(
            self.REPO_DIR,
            "packages/nx/src/graph/cache-manager.ts",
        )
        with open(path) as f:
            content = f.read()
        assert "invalidate" in content, "Should have invalidate method"

    def test_get_stats_method(self):
        """Verify getStats method with hits/misses"""
        path = os.path.join(
            self.REPO_DIR,
            "packages/nx/src/graph/cache-manager.ts",
        )
        with open(path) as f:
            content = f.read()
        assert "getStats" in content, "Should have getStats method"
        assert "hits" in content, "Should track hits"
        assert "misses" in content, "Should track misses"

    # === Functional Checks ===

    def test_dependency_analyzer_tests_pass(self):
        """Verify dependency analyzer tests pass"""
        result = subprocess.run(
            [
                "pnpm", "jest",
                "packages/nx/src/graph/dependency-analyzer.spec.ts",
            ],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, (
            f"Tests failed:\n{result.stdout}\n{result.stderr}"
        )

    def test_boundary_enforcer_tests_pass(self):
        """Verify boundary enforcer tests pass"""
        result = subprocess.run(
            [
                "pnpm", "jest",
                "packages/nx/src/graph/boundary-enforcer.spec.ts",
            ],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, (
            f"Tests failed:\n{result.stdout}\n{result.stderr}"
        )

    def test_affected_calculator_tests_pass(self):
        """Verify affected calculator tests pass"""
        result = subprocess.run(
            [
                "pnpm", "jest",
                "packages/nx/src/graph/affected-calculator.spec.ts",
            ],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, (
            f"Tests failed:\n{result.stdout}\n{result.stderr}"
        )

    def test_cache_manager_tests_pass(self):
        """Verify cache manager tests pass"""
        result = subprocess.run(
            [
                "pnpm", "jest",
                "packages/nx/src/graph/cache-manager.spec.ts",
            ],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, (
            f"Tests failed:\n{result.stdout}\n{result.stderr}"
        )
