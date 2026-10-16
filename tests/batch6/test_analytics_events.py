"""
Test skill: analytics-events
Verify that the Agent correctly adds Snowplow analytics events for dashboard
filter interactions in Metabase frontend code.
"""

import os
import re
import subprocess
import pytest


class TestAnalyticsEvents:
    REPO_DIR = "/workspace/metabase"

    # === File Path Checks ===

    def test_analytics_module_file_exists(self):
        """Verify that the dashboard analytics tracking module exists"""
        path = os.path.join(self.REPO_DIR, "frontend/src/metabase/dashboard/analytics.ts")
        assert os.path.exists(path), f"analytics.ts not found at {path}"

    def test_event_type_file_exists(self):
        """Verify that the event type definitions file exists"""
        path = os.path.join(self.REPO_DIR, "frontend/src/metabase-types/analytics/event.ts")
        assert os.path.exists(path), f"event.ts not found at {path}"

    # === Semantic Checks ===

    def test_event_types_define_five_dashboard_filter_events(self):
        """Verify that event.ts defines all 5 dashboard filter event types"""
        path = os.path.join(self.REPO_DIR, "frontend/src/metabase-types/analytics/event.ts")
        with open(path, "r") as f:
            content = f.read()

        expected_events = [
            "dashboard_filter_applied",
            "dashboard_filter_cleared",
            "dashboard_filter_all_cleared",
            "dashboard_filter_default_saved",
            "dashboard_filter_visibility_toggled",
        ]
        for event in expected_events:
            assert event in content, (
                f"event.ts missing event type definition: {event}"
            )

    def test_event_types_have_correct_fields(self):
        """Verify that event types define target_id and appropriate detail fields"""
        path = os.path.join(self.REPO_DIR, "frontend/src/metabase-types/analytics/event.ts")
        with open(path, "r") as f:
            content = f.read()

        # target_id should appear for dashboard events
        assert "target_id" in content, (
            "Event types should include target_id field for dashboard ID"
        )
        # event_detail for applied, all_cleared, default_saved
        assert "event_detail" in content, (
            "Event types should include event_detail field"
        )
        # result for visibility toggled
        assert "result" in content, (
            "Visibility toggled event should include result field"
        )

    def test_event_types_added_to_dashboard_event_union(self):
        """Verify that new event types are added to the DashboardEvent union type"""
        path = os.path.join(self.REPO_DIR, "frontend/src/metabase-types/analytics/event.ts")
        with open(path, "r") as f:
            content = f.read()

        # Check for DashboardEvent union type
        assert "DashboardEvent" in content, (
            "event.ts should define or extend DashboardEvent union type"
        )
        # Verify that filter events are part of the union
        filter_types_in_union = sum(1 for t in [
            "DashboardFilterAppliedEvent",
            "DashboardFilterClearedEvent",
            "DashboardFilterAllClearedEvent",
            "DashboardFilterDefaultSavedEvent",
            "DashboardFilterVisibilityToggledEvent",
        ] if t in content)
        assert filter_types_in_union >= 3, (
            f"Only {filter_types_in_union} filter event types found in event.ts. "
            f"Expected at least 3 of the 5 event type interfaces."
        )

    def test_analytics_module_has_five_tracking_functions(self):
        """Verify that analytics.ts defines all 5 tracking functions"""
        path = os.path.join(self.REPO_DIR, "frontend/src/metabase/dashboard/analytics.ts")
        with open(path, "r") as f:
            content = f.read()

        expected_functions = [
            "trackDashboardFilterApplied",
            "trackDashboardFilterCleared",
            "trackDashboardFilterAllCleared",
            "trackDashboardFilterDefaultSaved",
            "trackDashboardFilterVisibilityToggled",
        ]
        for func in expected_functions:
            assert func in content, (
                f"analytics.ts missing tracking function: {func}"
            )

    def test_analytics_module_uses_track_simple_event(self):
        """Verify that tracking functions use trackSimpleEvent()"""
        path = os.path.join(self.REPO_DIR, "frontend/src/metabase/dashboard/analytics.ts")
        with open(path, "r") as f:
            content = f.read()

        assert "trackSimpleEvent" in content, (
            "Tracking functions should call trackSimpleEvent()"
        )

    def test_analytics_module_accepts_dashboard_id(self):
        """Verify that tracking functions accept dashboardId parameter"""
        path = os.path.join(self.REPO_DIR, "frontend/src/metabase/dashboard/analytics.ts")
        with open(path, "r") as f:
            content = f.read()

        assert "dashboardId" in content, (
            "Tracking functions should accept dashboardId parameter"
        )

    def test_visibility_function_maps_boolean_to_string(self):
        """Verify that visibility toggle function maps isVisible boolean to 'visible'/'hidden' string"""
        path = os.path.join(self.REPO_DIR, "frontend/src/metabase/dashboard/analytics.ts")
        with open(path, "r") as f:
            content = f.read()

        has_mapping = ("visible" in content and "hidden" in content) or "isVisible" in content
        assert has_mapping, (
            "Visibility toggle function should map boolean to 'visible'/'hidden' string"
        )

    # === Functional Checks ===

    def test_filter_bar_component_imports_tracking(self):
        """Verify that DashboardFilterBar.tsx imports and calls tracking functions"""
        path = os.path.join(
            self.REPO_DIR,
            "frontend/src/metabase/dashboard/components/DashboardFilterBar.tsx"
        )
        if not os.path.exists(path):
            # Try alternative path patterns
            for root, dirs, files in os.walk(
                os.path.join(self.REPO_DIR, "frontend/src/metabase/dashboard")
            ):
                for f in files:
                    if "filterbar" in f.lower() and f.endswith(".tsx"):
                        path = os.path.join(root, f)
                        break

        assert os.path.exists(path), f"DashboardFilterBar component not found"
        with open(path, "r") as f:
            content = f.read()

        has_tracking_import = any(kw in content for kw in [
            "trackDashboardFilter",
            "analytics",
            "tracking",
        ])
        assert has_tracking_import, (
            "DashboardFilterBar.tsx should import tracking functions from analytics module"
        )

    def test_filter_panel_component_imports_tracking(self):
        """Verify that DashboardFilterPanel.tsx imports and calls tracking functions"""
        path = os.path.join(
            self.REPO_DIR,
            "frontend/src/metabase/dashboard/components/DashboardFilterPanel.tsx"
        )
        if not os.path.exists(path):
            for root, dirs, files in os.walk(
                os.path.join(self.REPO_DIR, "frontend/src/metabase/dashboard")
            ):
                for f in files:
                    if "filterpanel" in f.lower() and f.endswith(".tsx"):
                        path = os.path.join(root, f)
                        break

        assert os.path.exists(path), f"DashboardFilterPanel component not found"
        with open(path, "r") as f:
            content = f.read()

        has_tracking_import = any(kw in content for kw in [
            "trackDashboardFilter",
            "analytics",
            "tracking",
        ])
        assert has_tracking_import, (
            "DashboardFilterPanel.tsx should import tracking functions"
        )

    def test_event_names_use_snake_case(self):
        """Verify that all event names follow Metabase's snake_case convention"""
        path = os.path.join(self.REPO_DIR, "frontend/src/metabase/dashboard/analytics.ts")
        with open(path, "r") as f:
            content = f.read()

        # Extract event name strings
        event_pattern = re.compile(r'"(dashboard_filter_\w+)"')
        event_names = event_pattern.findall(content)
        assert len(event_names) >= 3, (
            f"Expected at least 3 event name strings, found {len(event_names)}"
        )
        for name in event_names:
            assert name == name.lower(), (
                f"Event name '{name}' should be snake_case"
            )
            assert "_" in name, (
                f"Event name '{name}' should use underscore separators"
            )

    def test_analytics_ts_is_valid_typescript(self):
        """Verify that analytics.ts file has valid TypeScript structure"""
        path = os.path.join(self.REPO_DIR, "frontend/src/metabase/dashboard/analytics.ts")
        with open(path, "r") as f:
            content = f.read()

        # Basic structural checks
        assert "export" in content, "analytics.ts should export tracking functions"
        assert "function" in content or "=>" in content, (
            "analytics.ts should define functions"
        )
        # Verify it imports from analytics types or tracking utility
        assert "import" in content, "analytics.ts should have import statements"
