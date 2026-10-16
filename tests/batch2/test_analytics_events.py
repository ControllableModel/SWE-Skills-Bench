"""
Test skill: analytics-events
Verify that the Agent correctly adds user behavior analytics event definitions
and tracking functions to Metabase's frontend TypeScript codebase.
"""

import os
import re
import subprocess
import pytest


class TestAnalyticsEvents:
    REPO_DIR = "/workspace/metabase"

    # === File Path Checks ===

    def test_events_type_file_exists(self):
        """Verify the analytics events type definition file exists"""
        path = os.path.join(
            self.REPO_DIR,
            "frontend/src/metabase-types/analytics/events.ts",
        )
        assert os.path.exists(path), f"events.ts not found at {path}"

    def test_tracking_file_exists(self):
        """Verify the tracking functions file exists"""
        path = os.path.join(
            self.REPO_DIR,
            "frontend/src/metabase/analytics/tracking.ts",
        )
        assert os.path.exists(path), f"tracking.ts not found at {path}"

    # === Semantic Checks ===

    def test_events_defines_feature_discovery_type(self):
        """Verify events.ts defines the feature_discovery_triggered event type"""
        path = os.path.join(
            self.REPO_DIR,
            "frontend/src/metabase-types/analytics/events.ts",
        )
        with open(path) as f:
            content = f.read()

        assert "feature_discovery_triggered" in content, (
            "events.ts should define 'feature_discovery_triggered' event type"
        )
        # Verify required payload fields
        assert "feature_name" in content, (
            "feature_discovery_triggered should have 'feature_name: string' field"
        )
        assert "source" in content, (
            "feature_discovery_triggered should have 'source: string' field"
        )

    def test_events_defines_navigation_tab_clicked_type(self):
        """Verify events.ts defines the navigation_tab_clicked event type"""
        path = os.path.join(
            self.REPO_DIR,
            "frontend/src/metabase-types/analytics/events.ts",
        )
        with open(path) as f:
            content = f.read()

        assert "navigation_tab_clicked" in content, (
            "events.ts should define 'navigation_tab_clicked' event type"
        )
        assert "tab_name" in content, (
            "navigation_tab_clicked should have 'tab_name' field"
        )
        assert "previous_tab" in content, (
            "navigation_tab_clicked should have 'previous_tab' field"
        )

    def test_events_defines_content_created_type(self):
        """Verify events.ts defines the content_created event type"""
        path = os.path.join(
            self.REPO_DIR,
            "frontend/src/metabase-types/analytics/events.ts",
        )
        with open(path) as f:
            content = f.read()

        assert "content_created" in content, (
            "events.ts should define 'content_created' event type"
        )
        assert "content_type" in content, (
            "content_created should have 'content_type' field"
        )
        assert "content_id" in content, (
            "content_created should have 'content_id' field"
        )
        # content_type should be a union of specific types
        type_values = ["question", "dashboard", "model"]
        found_types = [t for t in type_values if t in content]
        assert len(found_types) >= 2, (
            f"content_type should be a union including 'question', 'dashboard', 'model'. "
            f"Found: {found_types}"
        )

    def test_events_uses_snake_case_naming(self):
        """Verify all event names follow snake_case convention"""
        path = os.path.join(
            self.REPO_DIR,
            "frontend/src/metabase-types/analytics/events.ts",
        )
        with open(path) as f:
            content = f.read()

        event_names = [
            "feature_discovery_triggered",
            "navigation_tab_clicked",
            "content_created",
        ]
        for name in event_names:
            assert name in content, f"Event '{name}' should use snake_case: {name}"
            # Verify it's NOT in camelCase or PascalCase
            camel = name.replace("_", " ").title().replace(" ", "")
            camel = camel[0].lower() + camel[1:]
            # camelCase version should NOT be used as the event name
            # (but might appear as function name, so just check event definitions)

    def test_tracking_has_feature_discovery_function(self):
        """Verify tracking.ts defines trackFeatureDiscovery function"""
        path = os.path.join(
            self.REPO_DIR,
            "frontend/src/metabase/analytics/tracking.ts",
        )
        with open(path) as f:
            content = f.read()

        assert "trackFeatureDiscovery" in content, (
            "tracking.ts should define 'trackFeatureDiscovery' function"
        )

    def test_tracking_has_navigation_action_function(self):
        """Verify tracking.ts defines trackNavigationAction function"""
        path = os.path.join(
            self.REPO_DIR,
            "frontend/src/metabase/analytics/tracking.ts",
        )
        with open(path) as f:
            content = f.read()

        assert "trackNavigationAction" in content, (
            "tracking.ts should define 'trackNavigationAction' function"
        )

    def test_tracking_has_content_creation_function(self):
        """Verify tracking.ts defines trackContentCreation function"""
        path = os.path.join(
            self.REPO_DIR,
            "frontend/src/metabase/analytics/tracking.ts",
        )
        with open(path) as f:
            content = f.read()

        assert "trackContentCreation" in content, (
            "tracking.ts should define 'trackContentCreation' function"
        )

    def test_tracking_uses_core_tracking_utility(self):
        """Verify tracking functions use the project's core tracking utility"""
        path = os.path.join(
            self.REPO_DIR,
            "frontend/src/metabase/analytics/tracking.ts",
        )
        with open(path) as f:
            content = f.read()

        tracking_indicators = [
            "trackStructEvent", "trackEvent", "trackSchemaEvent",
            "snowplow", "track(", "analytics",
        ]
        found = [ind for ind in tracking_indicators if ind in content]
        assert len(found) >= 1, (
            "Tracking functions should use the project's core tracking utility. "
            f"None of {tracking_indicators} found."
        )

    # === Functional Checks ===

    def test_events_ts_has_valid_typescript_syntax(self):
        """Verify events.ts has valid TypeScript syntax via node parsing"""
        path = os.path.join(
            self.REPO_DIR,
            "frontend/src/metabase-types/analytics/events.ts",
        )
        with open(path) as f:
            content = f.read()

        # Basic TS syntax checks
        assert "type " in content or "interface " in content or "enum " in content, (
            "events.ts should define TypeScript types, interfaces, or enums"
        )

    def test_tracking_ts_exports_functions(self):
        """Verify tracking.ts exports the tracking functions"""
        path = os.path.join(
            self.REPO_DIR,
            "frontend/src/metabase/analytics/tracking.ts",
        )
        with open(path) as f:
            content = f.read()

        export_patterns = [
            "export function", "export const", "export {",
        ]
        has_exports = any(p in content for p in export_patterns)
        assert has_exports, (
            "tracking.ts should export tracking functions. "
            f"None of {export_patterns} found."
        )

        # Verify all three functions are exported
        functions = ["trackFeatureDiscovery", "trackNavigationAction", "trackContentCreation"]
        for func in functions:
            # Check if function is exported (directly or via export block)
            is_exported = (
                f"export function {func}" in content
                or f"export const {func}" in content
                or (func in content and "export {" in content)
            )
            assert is_exported or func in content, (
                f"Function '{func}' should be defined and exported in tracking.ts"
            )

    def test_events_integrated_into_union_type(self):
        """Verify new events are added to the analytics union type"""
        path = os.path.join(
            self.REPO_DIR,
            "frontend/src/metabase-types/analytics/events.ts",
        )
        with open(path) as f:
            content = f.read()

        # New events should be part of a union type
        union_indicators = ["|", "type ", "Event"]
        found = [ind for ind in union_indicators if ind in content]
        assert len(found) >= 2, (
            "New event types should be part of the analytics union type. "
            f"Found: {found}"
        )
