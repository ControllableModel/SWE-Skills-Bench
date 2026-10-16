"""
Test skill: analytics-events
Verify that the Agent correctly implements analytics event tracking for
Metabase dashboard components.
"""

import os
import re
import pytest


class TestAnalyticsEvents:
    REPO_DIR = "/workspace/metabase"

    ANALYTICS_DEF = "frontend/src/metabase/dashboard/analytics.ts"
    ANALYTICS_HOOK = "frontend/src/metabase/dashboard/hooks/use-dashboard-analytics.ts"
    HEADER_ANALYTICS = "frontend/src/metabase/dashboard/components/DashboardHeader/DashboardHeader.analytics.ts"
    DASHCARD_ANALYTICS = "frontend/src/metabase/dashboard/components/DashCard/DashCard.analytics.ts"
    UNIT_TEST = "frontend/src/metabase/dashboard/analytics.unit.spec.ts"

    def _read_file(self, rel_path):
        filepath = os.path.join(self.REPO_DIR, rel_path)
        with open(filepath) as f:
            return f.read()

    # === File Path Checks ===

    def test_analytics_definitions_file_exists(self):
        """Verify analytics.ts event definitions file exists"""
        filepath = os.path.join(self.REPO_DIR, self.ANALYTICS_DEF)
        assert os.path.exists(filepath), f"analytics.ts not found at {filepath}"

    def test_analytics_hook_file_exists(self):
        """Verify use-dashboard-analytics.ts hook file exists"""
        filepath = os.path.join(self.REPO_DIR, self.ANALYTICS_HOOK)
        assert os.path.exists(filepath), f"Hook file not found at {filepath}"

    def test_header_analytics_exists(self):
        """Verify DashboardHeader analytics integration file exists"""
        filepath = os.path.join(self.REPO_DIR, self.HEADER_ANALYTICS)
        assert os.path.exists(filepath), f"Header analytics not found at {filepath}"

    def test_dashcard_analytics_exists(self):
        """Verify DashCard analytics integration file exists"""
        filepath = os.path.join(self.REPO_DIR, self.DASHCARD_ANALYTICS)
        assert os.path.exists(filepath), f"DashCard analytics not found at {filepath}"

    def test_unit_test_file_exists(self):
        """Verify analytics unit test file exists"""
        filepath = os.path.join(self.REPO_DIR, self.UNIT_TEST)
        assert os.path.exists(filepath), f"Unit test file not found at {filepath}"

    # === Semantic Checks ===

    def test_all_six_event_interfaces_defined(self):
        """Verify all 6 event type interfaces are defined"""
        content = self._read_file(self.ANALYTICS_DEF)
        events = [
            "DashboardViewedEvent", "DashCardAddedEvent",
            "DashCardRemovedEvent", "DashCardResizedEvent",
            "DashboardFilterAppliedEvent", "DashboardSharedEvent",
        ]
        for event in events:
            assert re.search(rf'(interface|type)\s+{event}\b', content), \
                f"Event interface '{event}' not defined in analytics.ts"

    def test_event_interfaces_have_required_fields(self):
        """Verify event interfaces include event name and dashboard_id fields"""
        content = self._read_file(self.ANALYTICS_DEF)
        assert "dashboard_id" in content, \
            "Event interfaces missing 'dashboard_id' field"
        event_names = [
            "dashboard_viewed", "dashcard_added", "dashcard_removed",
            "dashcard_resized", "dashboard_filter_applied", "dashboard_shared",
        ]
        for name in event_names:
            assert name in content, \
                f"Event name '{name}' not found in analytics.ts"

    def test_dashcard_added_event_has_position_and_size(self):
        """Verify DashCardAddedEvent has position and size fields"""
        content = self._read_file(self.ANALYTICS_DEF)
        assert "position" in content, "DashCardAddedEvent missing 'position' field"
        assert "size" in content, "DashCardAddedEvent missing 'size' field"
        # Verify position has row/col
        assert "row" in content, "Position missing 'row' field"
        assert "col" in content, "Position missing 'col' field"

    def test_hook_exports_tracking_functions(self):
        """Verify useDashboardAnalytics hook exports typed tracking functions"""
        content = self._read_file(self.ANALYTICS_HOOK)
        assert "useDashboardAnalytics" in content, \
            "Hook 'useDashboardAnalytics' not found"
        tracking_functions = [
            "trackView", "trackCardAdded", "trackCardRemoved",
            "trackCardResized", "trackFilterApplied", "trackShared",
        ]
        for func in tracking_functions:
            assert func in content, \
                f"Hook missing tracking function: {func}"

    def test_hook_implements_debounce(self):
        """Verify hook uses debouncing to prevent duplicate events"""
        content = self._read_file(self.ANALYTICS_HOOK)
        has_debounce = bool(re.search(
            r'(debounce|setTimeout|useRef.*timer|clearTimeout|300)',
            content,
        ))
        assert has_debounce, \
            "Hook missing debounce logic (should debounce events by 300ms)"

    def test_dashcard_resize_checks_size_change(self):
        """Verify resize event only fires when size actually changes"""
        # Check in hook or DashCard analytics
        hook_content = self._read_file(self.ANALYTICS_HOOK)
        dashcard_content = self._read_file(self.DASHCARD_ANALYTICS)
        combined = hook_content + dashcard_content
        has_size_check = bool(re.search(
            r'(old_size|oldSize|width\s*!==|height\s*!==|JSON\.stringify|equal)',
            combined,
        ))
        assert has_size_check, \
            "Resize event missing size-change check (should skip if size unchanged)"

    # === Functional Checks ===

    def test_header_analytics_tracks_share_event(self):
        """Verify DashboardHeader analytics tracks share events"""
        content = self._read_file(self.HEADER_ANALYTICS)
        assert "trackShared" in content or "dashboard_shared" in content, \
            "DashboardHeader analytics missing share event tracking"
        assert "share_type" in content or "shareType" in content, \
            "DashboardHeader analytics missing share_type field"

    def test_dashcard_analytics_tracks_add_remove(self):
        """Verify DashCard analytics tracks add and remove events"""
        content = self._read_file(self.DASHCARD_ANALYTICS)
        assert "trackCardAdded" in content or "dashcard_added" in content, \
            "DashCard analytics missing add event tracking"
        assert "trackCardRemoved" in content or "dashcard_removed" in content, \
            "DashCard analytics missing remove event tracking"

    def test_validation_logs_warning_for_invalid_data(self):
        """Verify analytics has validation that logs warnings instead of throwing"""
        # Check across analytics files for validation logic
        analytics_content = self._read_file(self.ANALYTICS_DEF)
        hook_content = self._read_file(self.ANALYTICS_HOOK)
        combined = analytics_content + hook_content
        has_validation = bool(re.search(
            r'(console\.warn|validate|isValid|positive|NaN|invalid)',
            combined,
            re.IGNORECASE,
        ))
        assert has_validation, \
            "Analytics missing validation for invalid payloads"

    def test_unit_tests_cover_key_scenarios(self):
        """Verify unit tests cover debounce, validation, and event structure"""
        content = self._read_file(self.UNIT_TEST)
        test_keywords = ["debounce", "valid", "resize", "size"]
        found = sum(1 for kw in test_keywords if kw.lower() in content.lower())
        assert found >= 2, \
            f"Unit tests should cover debounce, validation, resize scenarios. " \
            f"Found {found}/4 keywords"
