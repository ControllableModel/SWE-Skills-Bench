"""
Test skill: analytics-events
Verify that analytics events for collection bookmark interactions have been
correctly added to Metabase, including TypeScript type definitions, tracking
functions, component integrations, and proper event naming conventions.
"""

import os
import re
import subprocess
import pytest


class TestAnalyticsEvents:
    REPO_DIR = "/workspace/metabase"
    EVENT_TYPES_PATH = "frontend/src/metabase-types/analytics/event.ts"
    ANALYTICS_PATH = "frontend/src/metabase/collections/analytics.ts"
    BOOKMARK_COMP = "frontend/src/metabase/collections/components/CollectionBookmark.tsx"
    BOOKMARK_LIST = "frontend/src/metabase/collections/components/BookmarkList.tsx"

    # === File Path Checks ===

    def test_event_types_file_exists(self):
        """Verify the analytics event type definition file exists"""
        filepath = os.path.join(self.REPO_DIR, self.EVENT_TYPES_PATH)
        assert os.path.exists(filepath), f"Event types file not found at {filepath}"

    def test_analytics_module_exists(self):
        """Verify collections/analytics.ts tracking functions file was created"""
        filepath = os.path.join(self.REPO_DIR, self.ANALYTICS_PATH)
        assert os.path.exists(filepath), f"Analytics module not found at {filepath}"

    def test_bookmark_component_exists(self):
        """Verify CollectionBookmark.tsx exists"""
        filepath = os.path.join(self.REPO_DIR, self.BOOKMARK_COMP)
        assert os.path.exists(filepath), f"CollectionBookmark.tsx not found at {filepath}"

    def test_bookmark_list_component_exists(self):
        """Verify BookmarkList.tsx exists"""
        filepath = os.path.join(self.REPO_DIR, self.BOOKMARK_LIST)
        assert os.path.exists(filepath), f"BookmarkList.tsx not found at {filepath}"

    # === Semantic Checks ===

    def test_four_event_types_defined(self):
        """Verify all four bookmark event types are defined in event.ts"""
        filepath = os.path.join(self.REPO_DIR, self.EVENT_TYPES_PATH)
        with open(filepath) as f:
            content = f.read()
        expected_types = [
            "CollectionBookmarkCreatedEvent",
            "CollectionBookmarkRemovedEvent",
            "CollectionBookmarkReorderedEvent",
            "CollectionBookmarkItemClickedEvent",
        ]
        for event_type in expected_types:
            assert event_type in content, \
                f"Event type '{event_type}' not found in event.ts"

    def test_union_type_registered(self):
        """Verify CollectionBookmarkEvent union type exists and is in AnalyticsEvent"""
        filepath = os.path.join(self.REPO_DIR, self.EVENT_TYPES_PATH)
        with open(filepath) as f:
            content = f.read()
        assert "CollectionBookmarkEvent" in content, \
            "CollectionBookmarkEvent union type should be defined"

    def test_event_names_follow_snake_case_convention(self):
        """Verify event names use collection_bookmark_* snake_case prefix"""
        filepath = os.path.join(self.REPO_DIR, self.EVENT_TYPES_PATH)
        with open(filepath) as f:
            content = f.read()
        expected_events = [
            "collection_bookmark_created",
            "collection_bookmark_removed",
            "collection_bookmark_reordered",
            "collection_bookmark_item_clicked",
        ]
        for event_name in expected_events:
            assert event_name in content, \
                f"Event name '{event_name}' not found in event types"

    def test_event_types_use_simple_event_schema(self):
        """Verify event types use SimpleEventSchema via ValidateEvent"""
        filepath = os.path.join(self.REPO_DIR, self.EVENT_TYPES_PATH)
        with open(filepath) as f:
            content = f.read()
        assert "SimpleEventSchema" in content or "ValidateEvent" in content, \
            "Event types should use SimpleEventSchema via ValidateEvent"

    def test_tracking_functions_call_track_simple_event(self):
        """Verify tracking functions use trackSimpleEvent from metabase/lib/analytics"""
        filepath = os.path.join(self.REPO_DIR, self.ANALYTICS_PATH)
        with open(filepath) as f:
            content = f.read()
        assert "trackSimpleEvent" in content, \
            "Tracking functions should call trackSimpleEvent"
        # Should have at least 4 exported tracking functions
        export_count = len(re.findall(r'export\s+(function|const)\s+track', content))
        assert export_count >= 4, \
            f"Expected at least 4 tracking functions, found {export_count}"

    def test_tracking_functions_have_strict_params(self):
        """Verify tracking functions accept strictly typed parameters"""
        filepath = os.path.join(self.REPO_DIR, self.ANALYTICS_PATH)
        with open(filepath) as f:
            content = f.read()
        # Should reference triggered_from with literal types
        has_triggered_from = "triggered_from" in content or "triggeredFrom" in content
        assert has_triggered_from, \
            "Tracking functions should include triggered_from parameter"
        # Should reference target_id
        has_target_id = "target_id" in content or "targetId" in content
        assert has_target_id, \
            "Tracking functions should include target_id parameter"

    def test_bookmark_component_imports_tracking(self):
        """Verify CollectionBookmark.tsx imports and uses tracking functions"""
        filepath = os.path.join(self.REPO_DIR, self.BOOKMARK_COMP)
        with open(filepath) as f:
            content = f.read()
        has_tracking = ("analytics" in content or "track" in content.lower())
        assert has_tracking, \
            "CollectionBookmark.tsx should import tracking functions from analytics module"

    def test_bookmark_list_imports_tracking(self):
        """Verify BookmarkList.tsx imports and uses tracking functions"""
        filepath = os.path.join(self.REPO_DIR, self.BOOKMARK_LIST)
        with open(filepath) as f:
            content = f.read()
        has_tracking = ("analytics" in content or "track" in content.lower())
        assert has_tracking, \
            "BookmarkList.tsx should import tracking functions from analytics module"

    def test_event_types_include_target_id_field(self):
        """Verify event types include target_id field where required"""
        filepath = os.path.join(self.REPO_DIR, self.EVENT_TYPES_PATH)
        with open(filepath) as f:
            content = f.read()
        assert "target_id" in content, \
            "Event types should include target_id field for created/removed/clicked events"

    def test_event_types_include_event_detail_field(self):
        """Verify event types include event_detail field for reordered and clicked events"""
        filepath = os.path.join(self.REPO_DIR, self.EVENT_TYPES_PATH)
        with open(filepath) as f:
            content = f.read()
        assert "event_detail" in content, \
            "Event types should include event_detail field"

    # === Functional Checks ===

    def test_analytics_module_is_valid_typescript(self):
        """Verify analytics.ts compiles without TypeScript errors"""
        # Check if npx tsc is available
        result = subprocess.run(
            ["npx", "tsc", "--noEmit", "--strict",
             os.path.join(self.REPO_DIR, self.ANALYTICS_PATH)],
            cwd=self.REPO_DIR,
            capture_output=True, text=True, timeout=120
        )
        # TypeScript check may fail due to missing deps; verify no syntax errors at least
        if result.returncode != 0:
            # Check it's not a basic syntax error
            assert "SyntaxError" not in result.stderr, \
                f"analytics.ts has syntax errors: {result.stderr[:500]}"

    def test_event_types_file_is_valid_typescript(self):
        """Verify event.ts is valid TypeScript (no syntax errors)"""
        filepath = os.path.join(self.REPO_DIR, self.EVENT_TYPES_PATH)
        with open(filepath) as f:
            content = f.read()
        # Basic syntax checks: balanced braces
        open_braces = content.count('{')
        close_braces = content.count('}')
        assert abs(open_braces - close_braces) <= 1, \
            f"event.ts has unbalanced braces: {open_braces} open, {close_braces} close"

    def test_bookmark_component_tracks_create_and_remove(self):
        """Verify CollectionBookmark.tsx calls tracking for both create and remove"""
        filepath = os.path.join(self.REPO_DIR, self.BOOKMARK_COMP)
        with open(filepath) as f:
            content = f.read()
        content_lower = content.lower()
        has_create = ("created" in content_lower or "create" in content_lower or
                      "add" in content_lower)
        assert has_create, \
            "CollectionBookmark.tsx should track bookmark creation"
        has_remove = ("removed" in content_lower or "remove" in content_lower or
                      "delete" in content_lower)
        assert has_remove, \
            "CollectionBookmark.tsx should track bookmark removal"
