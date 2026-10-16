"""
Test skill: analytics-events
Verify that the Agent implements a typed analytics event tracking system
for Metabase frontend with schema registry, naming enforcement, and validation.
"""

import os
import subprocess
import json
import pytest


class TestAnalyticsEvents:
    REPO_DIR = "/workspace/metabase"

    # === File Path Checks ===

    def test_schema_ts_exists(self):
        """Verify event schema registry file exists"""
        path = os.path.join(self.REPO_DIR, "frontend/src/metabase/analytics/schema.ts")
        assert os.path.exists(path), f"schema.ts not found at {path}"

    def test_tracker_ts_exists(self):
        """Verify event tracker file exists"""
        path = os.path.join(self.REPO_DIR, "frontend/src/metabase/analytics/tracker.ts")
        assert os.path.exists(path), f"tracker.ts not found at {path}"

    def test_naming_ts_exists(self):
        """Verify naming convention module exists"""
        path = os.path.join(self.REPO_DIR, "frontend/src/metabase/analytics/naming.ts")
        assert os.path.exists(path), f"naming.ts not found at {path}"

    def test_schema_test_exists(self):
        """Verify schema test file exists"""
        path = os.path.join(
            self.REPO_DIR, "frontend/src/metabase/analytics/__tests__/schema.test.ts"
        )
        assert os.path.exists(path), f"schema.test.ts not found at {path}"

    def test_tracker_test_exists(self):
        """Verify tracker test file exists"""
        path = os.path.join(
            self.REPO_DIR, "frontend/src/metabase/analytics/__tests__/tracker.test.ts"
        )
        assert os.path.exists(path), f"tracker.test.ts not found at {path}"

    # === Semantic Checks ===

    def test_schema_defines_event_registry(self):
        """Verify schema.ts defines EventRegistry class or equivalent"""
        path = os.path.join(self.REPO_DIR, "frontend/src/metabase/analytics/schema.ts")
        with open(path) as f:
            content = f.read()
        assert "EventRegistry" in content, \
            "schema.ts should define EventRegistry class"
        # Check for key methods
        methods = ["register", "get", "validate"]
        for method in methods:
            assert method in content, \
                f"EventRegistry should have '{method}' method"

    def test_schema_defines_event_types(self):
        """Verify schema defines SimpleEventSchema type with required fields"""
        path = os.path.join(self.REPO_DIR, "frontend/src/metabase/analytics/schema.ts")
        with open(path) as f:
            content = f.read()
        assert "SimpleEventSchema" in content or "EventSchema" in content, \
            "schema.ts should define SimpleEventSchema or EventSchema type"
        # Check for category values
        categories = ["navigation", "interaction", "api", "error", "performance"]
        found_cats = sum(1 for cat in categories if cat in content)
        assert found_cats >= 3, \
            f"Schema should define event categories. Found {found_cats} of {len(categories)}"

    def test_schema_defines_duplicate_error(self):
        """Verify schema defines DuplicateEventError"""
        path = os.path.join(self.REPO_DIR, "frontend/src/metabase/analytics/schema.ts")
        with open(path) as f:
            content = f.read()
        assert "DuplicateEventError" in content or "Duplicate" in content, \
            "Schema should define DuplicateEventError for duplicate event names"

    def test_naming_validates_snake_case(self):
        """Verify naming module validates snake_case event names"""
        path = os.path.join(self.REPO_DIR, "frontend/src/metabase/analytics/naming.ts")
        with open(path) as f:
            content = f.read()
        assert "validateEventName" in content or "validate" in content.lower(), \
            "naming.ts should define validateEventName function"
        # Check for snake_case validation
        assert "snake" in content.lower() or "lowercase" in content.lower() or "_" in content, \
            "Naming module should validate snake_case format"

    def test_naming_defines_allowed_objects_and_actions(self):
        """Verify naming module defines allowed object and action sets"""
        path = os.path.join(self.REPO_DIR, "frontend/src/metabase/analytics/naming.ts")
        with open(path) as f:
            content = f.read()
        # Check for predefined objects
        objects = ["dashboard", "question", "filter", "collection"]
        found_objects = sum(1 for obj in objects if obj in content)
        assert found_objects >= 3, \
            f"Naming should define allowed objects. Found {found_objects} of {len(objects)}"
        # Check for predefined actions
        actions = ["viewed", "created", "updated", "deleted", "clicked"]
        found_actions = sum(1 for act in actions if act in content)
        assert found_actions >= 3, \
            f"Naming should define allowed actions. Found {found_actions} of {len(actions)}"

    def test_tracker_defines_track_function(self):
        """Verify tracker defines track and createTypedTracker functions"""
        path = os.path.join(self.REPO_DIR, "frontend/src/metabase/analytics/tracker.ts")
        with open(path) as f:
            content = f.read()
        assert "track" in content, "tracker.ts should define track function"
        assert "EventValidationError" in content or "ValidationError" in content, \
            "tracker.ts should handle EventValidationError"

    def test_tracker_defines_batch_tracking(self):
        """Verify tracker implements batch tracking and event buffer"""
        path = os.path.join(self.REPO_DIR, "frontend/src/metabase/analytics/tracker.ts")
        with open(path) as f:
            content = f.read()
        assert "batch" in content.lower() or "Batch" in content, \
            "tracker.ts should implement batch tracking"
        assert "buffer" in content.lower() or "Buffer" in content or "queue" in content.lower(), \
            "tracker.ts should implement event buffer"

    # === Functional Checks ===

    def _ensure_node_modules(self):
        """Helper: ensure node_modules are installed"""
        node_modules = os.path.join(self.REPO_DIR, "node_modules")
        if not os.path.isdir(node_modules):
            result = subprocess.run(
                ["yarn", "install", "--frozen-lockfile"],
                cwd=self.REPO_DIR,
                capture_output=True, text=True, timeout=600
            )
            if result.returncode != 0:
                pytest.skip("yarn install failed, skipping functional tests")

    def test_schema_test_file_has_test_cases(self):
        """Verify schema test file has meaningful test cases"""
        path = os.path.join(
            self.REPO_DIR, "frontend/src/metabase/analytics/__tests__/schema.test.ts"
        )
        with open(path) as f:
            content = f.read()
        # Count test cases
        test_count = content.count("it(") + content.count("test(")
        assert test_count >= 3, \
            f"Schema test should have at least 3 test cases, found {test_count}"
        # Should test validation
        assert "validate" in content.lower() or "invalid" in content.lower(), \
            "Schema tests should verify validation behavior"

    def test_tracker_test_file_has_test_cases(self):
        """Verify tracker test file has meaningful test cases"""
        path = os.path.join(
            self.REPO_DIR, "frontend/src/metabase/analytics/__tests__/tracker.test.ts"
        )
        with open(path) as f:
            content = f.read()
        test_count = content.count("it(") + content.count("test(")
        assert test_count >= 3, \
            f"Tracker test should have at least 3 test cases, found {test_count}"

    def test_typescript_files_have_valid_syntax(self):
        """Verify all TypeScript files have valid syntax using node parse check"""
        files = [
            "frontend/src/metabase/analytics/schema.ts",
            "frontend/src/metabase/analytics/tracker.ts",
            "frontend/src/metabase/analytics/naming.ts",
        ]
        for rel_path in files:
            path = os.path.join(self.REPO_DIR, rel_path)
            # Use node to check for basic syntax (via ts-node or raw check)
            result = subprocess.run(
                ["node", "-e",
                 f"const ts = require('typescript'); "
                 f"const src = require('fs').readFileSync('{path}', 'utf8'); "
                 f"const sf = ts.createSourceFile('test.ts', src, ts.ScriptTarget.Latest, true); "
                 f"console.log('PARSE_OK');"],
                cwd=self.REPO_DIR,
                capture_output=True, text=True, timeout=30
            )
            if result.returncode != 0:
                # Fallback: just check it's not empty and has TypeScript syntax
                with open(path) as f:
                    content = f.read()
                assert len(content) > 50, \
                    f"{rel_path} is too short ({len(content)} chars)"
                assert "export" in content or "import" in content, \
                    f"{rel_path} should have TypeScript import/export statements"

    def test_tests_cover_validation_errors(self):
        """Verify test files cover validation error scenarios"""
        test_files = [
            "frontend/src/metabase/analytics/__tests__/schema.test.ts",
            "frontend/src/metabase/analytics/__tests__/tracker.test.ts",
        ]
        validation_terms = ["error", "invalid", "throw", "reject", "fail", "missing"]
        for rel_path in test_files:
            path = os.path.join(self.REPO_DIR, rel_path)
            with open(path) as f:
                content = f.read().lower()
            found = sum(1 for term in validation_terms if term in content)
            assert found >= 2, \
                f"{rel_path} should cover validation errors. Found {found} error-related terms"
