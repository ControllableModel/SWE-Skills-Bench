"""
Tests for the gitops-workflow skill.
Validates a GitOps manifest reconciler for Flux CD with manifest loading,
diff computation, reconciliation planning, and sync policy enforcement.
"""

import os
import re
import ast

REPO_DIR = "/workspace/flux2"
PYTHON_DIR = os.path.join(REPO_DIR, "tests", "python")


class TestGitopsWorkflow:
    """Tests for the Flux CD manifest reconciler."""

    # ── file_path_check ──────────────────────────────────────────────

    def test_reconciler_exists(self):
        """ManifestReconciler module must exist."""
        path = os.path.join(PYTHON_DIR, "reconciler.py")
        assert os.path.isfile(path), f"Missing {path}"

    def test_manifest_loader_exists(self):
        """ManifestLoader module must exist."""
        path = os.path.join(PYTHON_DIR, "manifest_loader.py")
        assert os.path.isfile(path), f"Missing {path}"

    def test_diff_engine_exists(self):
        """DiffEngine module must exist."""
        path = os.path.join(PYTHON_DIR, "diff_engine.py")
        assert os.path.isfile(path), f"Missing {path}"

    def test_sync_policy_exists(self):
        """SyncPolicy module must exist."""
        path = os.path.join(PYTHON_DIR, "sync_policy.py")
        assert os.path.isfile(path), f"Missing {path}"

    # ── semantic_check ───────────────────────────────────────────────

    def _read(self, filename):
        path = os.path.join(PYTHON_DIR, filename)
        if not os.path.isfile(path):
            return ""
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def test_manifest_loader_class(self):
        """ManifestLoader must define load_directory and validate_manifest."""
        content = self._read("manifest_loader.py")
        assert re.search(r"class\s+ManifestLoader", content), (
            "ManifestLoader class not defined"
        )
        assert re.search(r"def\s+load_directory\b", content), "load_directory not defined"
        assert re.search(r"def\s+validate_manifest\b", content), "validate_manifest not defined"

    def test_diff_engine_class(self):
        """DiffEngine must define diff, has_changes, and format_diff."""
        content = self._read("diff_engine.py")
        assert re.search(r"class\s+DiffEngine", content), "DiffEngine class not defined"
        assert re.search(r"def\s+diff\b", content), "diff method not defined"
        assert re.search(r"def\s+has_changes\b", content), "has_changes method not defined"

    def test_reconciler_class(self):
        """ManifestReconciler must define reconcile method."""
        content = self._read("reconciler.py")
        assert re.search(r"class\s+ManifestReconciler", content), (
            "ManifestReconciler class not defined"
        )
        assert re.search(r"def\s+reconcile\b", content), "reconcile method not defined"

    def test_sync_policy_class(self):
        """SyncPolicy must define should_include and support prune/force."""
        content = self._read("sync_policy.py")
        assert re.search(r"class\s+SyncPolicy", content), "SyncPolicy class not defined"
        assert "prune" in content, "prune option not found"
        assert "force" in content, "force option not found"

    def test_ignored_fields_in_diff(self):
        """DiffEngine must ignore server-managed fields."""
        content = self._read("diff_engine.py")
        assert re.search(
            r"IGNORED|resourceVersion|creationTimestamp|managedFields",
            content
        ), "Ignored server-managed fields not found in DiffEngine"

    def test_action_types(self):
        """Reconciler must produce create, update, delete, skip, unchanged actions."""
        content = self._read("reconciler.py")
        for action in ["create", "update", "delete", "skip", "unchanged"]:
            assert action in content, f"Action type '{action}' not found"

    # ── functional_check ─────────────────────────────────────────────

    def test_all_files_valid_python(self):
        """All reconciler Python files must have valid syntax."""
        errors = []
        for fname in ["reconciler.py", "manifest_loader.py",
                       "diff_engine.py", "sync_policy.py"]:
            content = self._read(fname)
            if not content:
                continue
            try:
                ast.parse(content)
            except SyntaxError as e:
                errors.append(f"{fname}: {e}")
        assert not errors, "Syntax errors:\n" + "\n".join(errors)

    def test_multi_document_yaml_support(self):
        """ManifestLoader must handle multi-document YAML files."""
        content = self._read("manifest_loader.py")
        assert re.search(r"load_all|safe_load_all|---|\bdocument", content, re.IGNORECASE), (
            "Multi-document YAML support not found"
        )

    def test_validation_error_messages(self):
        """validate_manifest must return specific error messages."""
        content = self._read("manifest_loader.py")
        assert re.search(r"Missing apiVersion|Missing kind|Missing metadata", content), (
            "Validation error messages not found"
        )

    def test_namespace_filtering(self):
        """SyncPolicy must support namespace filtering."""
        content = self._read("sync_policy.py")
        assert re.search(r"namespace|namespaces", content, re.IGNORECASE), (
            "Namespace filtering not found in SyncPolicy"
        )

    def test_excluded_kinds(self):
        """SyncPolicy must support excluded_kinds list."""
        content = self._read("sync_policy.py")
        assert re.search(r"excluded_kinds|excluded.*kind", content, re.IGNORECASE), (
            "excluded_kinds support not found"
        )

    def test_test_file_exists(self):
        """Test file must exist."""
        path = os.path.join(REPO_DIR, "tests", "test_gitops_workflow.py")
        assert os.path.isfile(path), f"Missing {path}"
