"""
Test skill: analytics-events
Verify that the Agent correctly adds Snowplow analytics events for
collection bulk actions in the Metabase frontend.
"""

import os
import re
import pytest


class TestAnalyticsEvents:
    REPO_DIR = "/workspace/metabase"

    # === File Path Checks ===

    def test_analytics_module_exists(self):
        """Verify collections/analytics.ts was created"""
        path = os.path.join(
            self.REPO_DIR,
            "frontend/src/metabase/collections/analytics.ts",
        )
        assert os.path.exists(path), f"analytics.ts not found at {path}"

    def test_event_types_file_exists(self):
        """Verify analytics event type definitions file exists"""
        path = os.path.join(
            self.REPO_DIR,
            "frontend/src/metabase-types/analytics/event.ts",
        )
        assert os.path.exists(path), f"event.ts not found at {path}"

    # === Semantic Checks: Event Type Definitions ===

    def test_event_types_defined(self):
        """Verify all 5 event types are defined in the event types file"""
        path = os.path.join(
            self.REPO_DIR,
            "frontend/src/metabase-types/analytics/event.ts",
        )
        with open(path) as f:
            content = f.read()
        expected_types = [
            "CollectionBulkSelectStartedEvent",
            "CollectionBulkMoveEvent",
            "CollectionBulkArchiveEvent",
            "CollectionBulkChangeVisibilityEvent",
            "CollectionBulkSelectAllEvent",
        ]
        for t in expected_types:
            assert t in content, f"Missing event type definition: {t}"

    def test_event_names_snake_case(self):
        """Verify event names use snake_case format"""
        path = os.path.join(
            self.REPO_DIR,
            "frontend/src/metabase-types/analytics/event.ts",
        )
        with open(path) as f:
            content = f.read()
        expected_events = [
            "collection_bulk_select_started",
            "collection_bulk_move_completed",
            "collection_bulk_archive_completed",
            "collection_bulk_visibility_changed",
            "collection_bulk_select_all_toggled",
        ]
        for ev in expected_events:
            assert ev in content, f"Missing event name: {ev}"

    def test_collection_bulk_event_union_type(self):
        """Verify CollectionBulkEvent union type exists"""
        path = os.path.join(
            self.REPO_DIR,
            "frontend/src/metabase-types/analytics/event.ts",
        )
        with open(path) as f:
            content = f.read()
        assert "CollectionBulkEvent" in content, (
            "Missing CollectionBulkEvent union type"
        )

    def test_union_added_to_simple_event(self):
        """Verify CollectionBulkEvent is included in SimpleEvent union"""
        path = os.path.join(
            self.REPO_DIR,
            "frontend/src/metabase-types/analytics/event.ts",
        )
        with open(path) as f:
            content = f.read()
        # Check that CollectionBulkEvent appears near SimpleEvent definition
        assert "SimpleEvent" in content, "SimpleEvent type should exist"
        # Find SimpleEvent definition and check it includes CollectionBulkEvent
        simple_event_idx = content.find("SimpleEvent")
        if simple_event_idx != -1:
            # Look in a reasonable range after the SimpleEvent definition
            context = content[max(0, simple_event_idx - 500):simple_event_idx + 1000]
            assert "CollectionBulkEvent" in context, (
                "CollectionBulkEvent should be included in the SimpleEvent union"
            )

    def test_event_fields_use_schema_fields_only(self):
        """Verify events only use SimpleEventSchema fields"""
        path = os.path.join(
            self.REPO_DIR,
            "frontend/src/metabase-types/analytics/event.ts",
        )
        with open(path) as f:
            content = f.read()
        # Check that no custom fields outside schema are used
        forbidden_fields = ["item_count", "source_collection", "filter_state"]
        for field in forbidden_fields:
            assert field not in content, (
                f"Event types should not use custom field '{field}' "
                "outside SimpleEventSchema"
            )

    # === Semantic Checks: Tracking Functions ===

    def test_tracking_functions_exist(self):
        """Verify all 5 tracking functions are defined in analytics.ts"""
        path = os.path.join(
            self.REPO_DIR,
            "frontend/src/metabase/collections/analytics.ts",
        )
        with open(path) as f:
            content = f.read()
        expected_functions = [
            "trackCollectionBulkSelectStarted",
            "trackCollectionBulkMoveCompleted",
            "trackCollectionBulkArchiveCompleted",
            "trackCollectionBulkVisibilityChanged",
            "trackCollectionBulkSelectAllToggled",
        ]
        for fn in expected_functions:
            assert fn in content, f"Missing tracking function: {fn}"

    def test_tracking_functions_import_track_simple_event(self):
        """Verify analytics.ts imports trackSimpleEvent from metabase/lib/analytics"""
        path = os.path.join(
            self.REPO_DIR,
            "frontend/src/metabase/collections/analytics.ts",
        )
        with open(path) as f:
            content = f.read()
        assert "trackSimpleEvent" in content, (
            "analytics.ts must import and use trackSimpleEvent"
        )
        assert "analytics" in content.lower(), (
            "analytics.ts should import from analytics module"
        )

    def test_tracking_functions_call_track_simple_event(self):
        """Verify each tracking function calls trackSimpleEvent"""
        path = os.path.join(
            self.REPO_DIR,
            "frontend/src/metabase/collections/analytics.ts",
        )
        with open(path) as f:
            content = f.read()
        # Count calls to trackSimpleEvent
        call_count = content.count("trackSimpleEvent(")
        assert call_count >= 5, (
            f"Expected at least 5 calls to trackSimpleEvent, found {call_count}"
        )

    # === Semantic Checks: Component Integration ===

    def test_bulk_action_bar_imports_tracking(self):
        """Verify BulkActionBar.tsx imports tracking functions"""
        path = os.path.join(
            self.REPO_DIR,
            "frontend/src/metabase/collections/components/BulkActionBar.tsx",
        )
        if not os.path.exists(path):
            pytest.skip("BulkActionBar.tsx not found")
        with open(path) as f:
            content = f.read()
        tracking_imports = [
            "trackCollectionBulkSelectStarted",
            "trackCollectionBulkMoveCompleted",
            "trackCollectionBulkArchiveCompleted",
        ]
        found = sum(1 for t in tracking_imports if t in content)
        assert found >= 2, (
            f"BulkActionBar.tsx should import tracking functions, found {found}/3"
        )

    def test_bulk_action_bar_tracks_duration(self):
        """Verify BulkActionBar captures timing for async operations"""
        path = os.path.join(
            self.REPO_DIR,
            "frontend/src/metabase/collections/components/BulkActionBar.tsx",
        )
        if not os.path.exists(path):
            pytest.skip("BulkActionBar.tsx not found")
        with open(path) as f:
            content = f.read()
        assert "Date.now()" in content or "performance.now()" in content, (
            "BulkActionBar should capture timing using Date.now() or performance.now()"
        )

    def test_move_event_has_required_fields(self):
        """Verify move event type includes target_id, event_detail, result, duration_ms"""
        path = os.path.join(
            self.REPO_DIR,
            "frontend/src/metabase-types/analytics/event.ts",
        )
        with open(path) as f:
            content = f.read()
        # Find the CollectionBulkMoveEvent section
        move_idx = content.find("CollectionBulkMoveEvent")
        assert move_idx != -1, "CollectionBulkMoveEvent not found"
        # Look at the type definition (next ~500 chars)
        move_section = content[move_idx:move_idx + 500]
        for field in ["target_id", "event_detail", "result", "duration_ms"]:
            assert field in move_section, (
                f"CollectionBulkMoveEvent missing field: {field}"
            )

    def test_archive_event_has_result_field(self):
        """Verify archive event type includes result field"""
        path = os.path.join(
            self.REPO_DIR,
            "frontend/src/metabase-types/analytics/event.ts",
        )
        with open(path) as f:
            content = f.read()
        archive_idx = content.find("CollectionBulkArchiveEvent")
        assert archive_idx != -1, "CollectionBulkArchiveEvent not found"
        archive_section = content[archive_idx:archive_idx + 500]
        assert "result" in archive_section, (
            "CollectionBulkArchiveEvent missing 'result' field"
        )
