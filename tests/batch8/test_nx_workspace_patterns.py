"""
Tests for the nx-workspace-patterns skill.
Validates an Nx project boundary enforcement plugin with tag resolution,
boundary rules, custom executor, and init generator.
"""

import os
import re

REPO_DIR = "/workspace/nx"
PLUGIN_DIR = os.path.join(REPO_DIR, "packages", "nx-boundary-plugin")
SRC_DIR = os.path.join(PLUGIN_DIR, "src")


class TestNxWorkspacePatterns:
    """Tests for the Nx boundary enforcement plugin."""

    # ── file_path_check ──────────────────────────────────────────────

    def test_package_json_exists(self):
        """Plugin package.json must exist."""
        path = os.path.join(PLUGIN_DIR, "package.json")
        assert os.path.isfile(path), f"Missing {path}"

    def test_index_entry_point_exists(self):
        """Plugin entry point index.ts must exist."""
        path = os.path.join(SRC_DIR, "index.ts")
        assert os.path.isfile(path), f"Missing {path}"

    def test_boundary_rules_exists(self):
        """Boundary rules engine must exist."""
        path = os.path.join(SRC_DIR, "rules", "boundary-rules.ts")
        assert os.path.isfile(path), f"Missing {path}"

    def test_tag_resolver_exists(self):
        """Tag resolver utility must exist."""
        path = os.path.join(SRC_DIR, "utils", "tag-resolver.ts")
        assert os.path.isfile(path), f"Missing {path}"

    def test_init_generator_exists(self):
        """Init generator must exist."""
        path = os.path.join(SRC_DIR, "generators", "init", "generator.ts")
        assert os.path.isfile(path), f"Missing {path}"

    def test_executor_exists(self):
        """Boundary lint executor must exist."""
        path = os.path.join(SRC_DIR, "executors", "boundary-lint", "executor.ts")
        assert os.path.isfile(path), f"Missing {path}"

    # ── semantic_check ───────────────────────────────────────────────

    def _read(self, rel_path):
        path = os.path.join(PLUGIN_DIR, rel_path)
        if not os.path.isfile(path):
            return ""
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def test_tag_resolver_scope_patterns(self):
        """Tag resolver must handle scope:shared, scope:feature, scope:app."""
        content = self._read("src/utils/tag-resolver.ts")
        for scope in ["scope:shared", "scope:feature", "scope:app"]:
            assert scope in content, f"Scope pattern '{scope}' not found in tag resolver"

    def test_boundary_rules_evaluation(self):
        """Boundary rules must evaluate sourceTag and dependency constraints."""
        content = self._read("src/rules/boundary-rules.ts")
        assert re.search(r"sourceTag|onlyDependOn|notDependOn", content), (
            "Boundary rule evaluation logic not found"
        )

    def test_default_boundary_rules(self):
        """Init generator must set default rules (shared cannot depend on feature)."""
        gen_content = self._read("src/generators/init/generator.ts")
        rules_content = self._read("src/rules/boundary-rules.ts")
        combined = gen_content + rules_content
        assert re.search(r"scope:shared.*scope:feature|shared.*may not.*feature", combined, re.IGNORECASE | re.DOTALL), (
            "Default rule: shared cannot depend on feature not found"
        )

    def test_executor_scans_imports(self):
        """Executor must scan TypeScript import statements."""
        content = self._read("src/executors/boundary-lint/executor.ts")
        assert re.search(r"import|require|scan|parse", content, re.IGNORECASE), (
            "Import scanning not found in executor"
        )

    def test_violation_reporting(self):
        """Executor must report violations with file, line, and rule reference."""
        content = self._read("src/executors/boundary-lint/executor.ts")
        assert re.search(r"violation|file|line|importedProject", content, re.IGNORECASE), (
            "Violation reporting not found in executor"
        )

    def test_glob_matching_support(self):
        """Boundary rules must support wildcard glob matching."""
        content = self._read("src/rules/boundary-rules.ts")
        assert re.search(r"\*|glob|wildcard|match|pattern", content, re.IGNORECASE), (
            "Glob/wildcard matching not found in boundary rules"
        )

    # ── functional_check ─────────────────────────────────────────────

    def test_generator_schema_exists(self):
        """Init generator schema.json must exist."""
        path = os.path.join(SRC_DIR, "generators", "init", "schema.json")
        assert os.path.isfile(path), f"Missing {path}"

    def test_executor_schema_exists(self):
        """Boundary lint executor schema.json must exist."""
        path = os.path.join(SRC_DIR, "executors", "boundary-lint", "schema.json")
        assert os.path.isfile(path), f"Missing {path}"

    def test_boundary_rules_spec_exists(self):
        """Unit test file for boundary rules must exist."""
        path = os.path.join(SRC_DIR, "rules", "boundary-rules.spec.ts")
        assert os.path.isfile(path), f"Missing {path}"

    def test_tag_resolver_spec_exists(self):
        """Unit test file for tag resolver must exist."""
        path = os.path.join(SRC_DIR, "utils", "tag-resolver.spec.ts")
        assert os.path.isfile(path), f"Missing {path}"

    def test_package_json_has_nx_metadata(self):
        """package.json must contain Nx plugin metadata."""
        content = self._read("package.json")
        assert re.search(r"nx|generators|executors|plugin", content, re.IGNORECASE), (
            "Nx plugin metadata not found in package.json"
        )

    def test_tag_resolver_handles_unknown(self):
        """Tag resolver must assign scope:unknown for unrecognized paths."""
        content = self._read("src/utils/tag-resolver.ts")
        assert "scope:unknown" in content, "scope:unknown fallback not found"
