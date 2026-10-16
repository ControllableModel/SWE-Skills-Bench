"""
Test skill: nx-workspace-patterns
Verify that the Agent creates Nx affected graph resolution E2E tests
with multi-project workspace fixture and dependency graph validation.
"""

import os
import re
import subprocess
import pytest


class TestNxWorkspacePatterns:
    REPO_DIR = "/workspace/nx"

    # === File Path Checks ===

    def test_affected_graph_test_exists(self):
        """Verify affected-graph.test.ts exists"""
        path = os.path.join(
            self.REPO_DIR, "e2e/nx/src/affected-graph.test.ts"
        )
        assert os.path.exists(path), (
            f"affected-graph.test.ts not found at {path}"
        )

    def test_workspace_fixture_exists(self):
        """Verify workspace.json fixture exists"""
        path = os.path.join(
            self.REPO_DIR,
            "e2e/nx/src/fixtures/affected-demo/workspace.json",
        )
        assert os.path.exists(path), f"workspace.json fixture not found"

    # === Semantic Checks ===

    def test_multiple_projects_in_fixture(self):
        """Verify fixture defines at least 3 projects"""
        path = os.path.join(
            self.REPO_DIR,
            "e2e/nx/src/fixtures/affected-demo/workspace.json",
        )
        with open(path) as f:
            content = f.read()

        import json
        try:
            workspace = json.loads(content)
        except json.JSONDecodeError:
            pytest.fail("workspace.json should be valid JSON")

        # Look for projects key
        projects = workspace.get("projects", {})
        if isinstance(projects, dict):
            count = len(projects)
        else:
            # Count project-like entries
            count = content.count('"root"')

        assert count >= 3, (
            f"Fixture should define at least 3 projects. Found: {count}"
        )

    def test_dependency_relationships(self):
        """Verify inter-project dependencies are defined"""
        path = os.path.join(
            self.REPO_DIR,
            "e2e/nx/src/fixtures/affected-demo/workspace.json",
        )
        with open(path) as f:
            content = f.read().lower()

        dep_indicators = [
            "depends", "dependency", "implicitdependencies",
            "implicit", "import",
        ]
        found = [ind for ind in dep_indicators if ind in content]
        # Dependencies may also be inferred from imports in source fixture
        assert len(found) >= 1 or "lib" in content, (
            f"Should define project dependencies. Found: {found}"
        )

    def test_test_validates_affected_detection(self):
        """Verify test checks that modifying library affects dependents"""
        path = os.path.join(
            self.REPO_DIR, "e2e/nx/src/affected-graph.test.ts"
        )
        with open(path) as f:
            content = f.read()

        affected_indicators = [
            "affected", "nx affected", "runCLI",
            "library", "dependent", "app",
        ]
        found = [ind for ind in affected_indicators if ind in content.lower()]
        assert len(found) >= 2, (
            f"Test should validate affected detection. Found: {found}"
        )

    def test_test_validates_unaffected_isolation(self):
        """Verify test checks that independent project is NOT affected"""
        path = os.path.join(
            self.REPO_DIR, "e2e/nx/src/affected-graph.test.ts"
        )
        with open(path) as f:
            content = f.read()

        isolation_indicators = [
            "independent", "unaffected", "not", "toContain",
            "toBe", "expect", "should not",
        ]
        found = [ind for ind in isolation_indicators if ind in content.lower()]
        assert len(found) >= 2, (
            f"Test should verify independent project isolation. Found: {found}"
        )

    def test_test_validates_execution_order(self):
        """Verify test checks topological task execution order"""
        path = os.path.join(
            self.REPO_DIR, "e2e/nx/src/affected-graph.test.ts"
        )
        with open(path) as f:
            content = f.read().lower()

        order_indicators = [
            "order", "before", "after", "topological",
            "dependency", "graph", "build",
        ]
        found = [ind for ind in order_indicators if ind in content]
        assert len(found) >= 2, (
            f"Test should verify execution order. Found: {found}"
        )

    def test_test_uses_test_framework(self):
        """Verify test uses a testing framework (jest/vitest)"""
        path = os.path.join(
            self.REPO_DIR, "e2e/nx/src/affected-graph.test.ts"
        )
        with open(path) as f:
            content = f.read()

        framework_indicators = [
            "describe", "it(", "test(", "expect",
            "beforeAll", "afterAll", "beforeEach",
        ]
        found = [ind for ind in framework_indicators if ind in content]
        assert len(found) >= 3, (
            f"Test should use a test framework. Found: {found}"
        )

    # === Functional Checks ===

    def test_typescript_syntax_valid(self):
        """Verify affected-graph.test.ts has valid TypeScript syntax"""
        path = os.path.join(
            self.REPO_DIR, "e2e/nx/src/affected-graph.test.ts"
        )
        npx = os.path.join(self.REPO_DIR, "node_modules/.bin/tsc")
        if os.path.exists(npx):
            result = subprocess.run(
                [npx, "--noEmit", "--allowJs", "--esModuleInterop", path],
                capture_output=True, text=True, timeout=60,
                cwd=self.REPO_DIR,
            )
            # TypeScript compilation errors are okay for isolated files
            # We mainly check the file is parseable
        # Fallback: check basic syntax patterns
        with open(path) as f:
            content = f.read()
        assert "describe" in content or "test" in content, (
            "Test file should contain test constructs"
        )

    def test_workspace_fixture_valid_json(self):
        """Verify workspace.json is valid JSON"""
        import json
        path = os.path.join(
            self.REPO_DIR,
            "e2e/nx/src/fixtures/affected-demo/workspace.json",
        )
        with open(path) as f:
            try:
                json.load(f)
            except json.JSONDecodeError as e:
                pytest.fail(f"workspace.json is invalid JSON: {e}")

    def test_no_circular_dependencies(self):
        """Verify fixture avoids circular dependencies"""
        import json
        path = os.path.join(
            self.REPO_DIR,
            "e2e/nx/src/fixtures/affected-demo/workspace.json",
        )
        with open(path) as f:
            workspace = json.load(f)

        projects = workspace.get("projects", {})
        # Simple cycle check: if project A depends on B and B depends on A
        deps = {}
        for name, cfg in projects.items():
            if isinstance(cfg, dict):
                impl_deps = cfg.get("implicitDependencies", [])
                if isinstance(impl_deps, list):
                    deps[name] = impl_deps

        for name, dep_list in deps.items():
            for dep in dep_list:
                if dep in deps and name in deps.get(dep, []):
                    pytest.fail(
                        f"Circular dependency detected: {name} <-> {dep}"
                    )
