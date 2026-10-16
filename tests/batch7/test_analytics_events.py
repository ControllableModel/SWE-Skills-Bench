"""
Test skill: analytics-events
Verify that the Agent correctly adds dashboard interaction tracking events
to the Metabase frontend with typed event schemas and tracking helpers.
"""

import os
import re
import json
import subprocess
import pytest


class TestAnalyticsEvents:
    REPO_DIR = "/workspace/metabase"

    # === File Path Checks ===

    def test_analytics_module_exists(self):
        """Verify analytics.ts event module exists"""
        fpath = os.path.join(self.REPO_DIR, "frontend/src/metabase/dashboard/analytics.ts")
        assert os.path.isfile(fpath), f"analytics.ts not found at {fpath}"

    def test_dashboard_header_exists(self):
        """Verify DashboardHeader component exists"""
        fpath = os.path.join(
            self.REPO_DIR,
            "frontend/src/metabase/dashboard/components/DashboardHeader/DashboardHeader.tsx"
        )
        assert os.path.isfile(fpath), f"DashboardHeader.tsx not found at {fpath}"

    # === Semantic Checks ===

    def test_analytics_defines_all_seven_events(self):
        """Verify analytics.ts defines all seven event types"""
        fpath = os.path.join(self.REPO_DIR, "frontend/src/metabase/dashboard/analytics.ts")
        with open(fpath, "r") as f:
            content = f.read()
        events = [
            "dashboard_created", "dashboard_saved", "dashboard_card_added",
            "dashboard_card_removed", "dashboard_filter_applied",
            "dashboard_fullscreen_toggled", "dashboard_shared"
        ]
        for event in events:
            assert event in content, f"analytics.ts missing event type: '{event}'"

    def test_analytics_has_tracking_function(self):
        """Verify analytics.ts exports a trackDashboardEvent function"""
        fpath = os.path.join(self.REPO_DIR, "frontend/src/metabase/dashboard/analytics.ts")
        with open(fpath, "r") as f:
            content = f.read()
        has_track = bool(re.search(r'(export\s+.*trackDashboardEvent|function\s+trackDashboardEvent)', content))
        assert has_track, "analytics.ts should export a trackDashboardEvent function"

    def test_event_interfaces_have_required_properties(self):
        """Verify event interfaces define dashboard_id and other required properties"""
        fpath = os.path.join(self.REPO_DIR, "frontend/src/metabase/dashboard/analytics.ts")
        with open(fpath, "r") as f:
            content = f.read()
        assert "dashboard_id" in content, "Events should include 'dashboard_id' property"
        assert "timestamp" in content, "Events should include automatic 'timestamp' metadata"

    def test_dashboard_created_event_schema(self):
        """Verify dashboard_created event has correct properties"""
        fpath = os.path.join(self.REPO_DIR, "frontend/src/metabase/dashboard/analytics.ts")
        with open(fpath, "r") as f:
            content = f.read()
        assert "collection_id" in content, "dashboard_created should have 'collection_id'"
        assert "num_cards" in content, "dashboard_created should have 'num_cards'"
        assert "has_filters" in content, "dashboard_created should have 'has_filters'"

    def test_dashboard_card_added_event_schema(self):
        """Verify dashboard_card_added event defines card_type union"""
        fpath = os.path.join(self.REPO_DIR, "frontend/src/metabase/dashboard/analytics.ts")
        with open(fpath, "r") as f:
            content = f.read()
        assert "card_type" in content, "dashboard_card_added should have 'card_type'"
        # card_type should define union with "question", "text", etc.
        has_card_types = (
            "question" in content and "text" in content and "heading" in content
        )
        assert has_card_types, (
            "card_type should include 'question', 'text', 'heading' union values"
        )

    def test_dashboard_filter_applied_event_schema(self):
        """Verify dashboard_filter_applied event has filter_type property"""
        fpath = os.path.join(self.REPO_DIR, "frontend/src/metabase/dashboard/analytics.ts")
        with open(fpath, "r") as f:
            content = f.read()
        assert "filter_type" in content, "dashboard_filter_applied should have 'filter_type'"
        assert "filter_widget_type" in content, "dashboard_filter_applied should have 'filter_widget_type'"

    def test_dashboard_shared_event_schema(self):
        """Verify dashboard_shared event has share_type property"""
        fpath = os.path.join(self.REPO_DIR, "frontend/src/metabase/dashboard/analytics.ts")
        with open(fpath, "r") as f:
            content = f.read()
        assert "share_type" in content, "dashboard_shared should have 'share_type'"
        has_share_types = (
            "public_link" in content and "embed" in content
        )
        assert has_share_types, "share_type should include 'public_link' and 'embed'"

    def test_tracking_validates_required_properties(self):
        """Verify trackDashboardEvent validates required properties before dispatch"""
        fpath = os.path.join(self.REPO_DIR, "frontend/src/metabase/dashboard/analytics.ts")
        with open(fpath, "r") as f:
            content = f.read()
        has_validation = bool(re.search(
            r'(console\.warn|throw|required|missing|validate)',
            content,
            re.IGNORECASE
        ))
        assert has_validation, (
            "trackDashboardEvent should validate required properties and warn on missing"
        )

    # === Functional Checks ===

    def test_analytics_ts_is_valid_typescript(self):
        """Verify analytics.ts is syntactically valid TypeScript"""
        fpath = os.path.join(self.REPO_DIR, "frontend/src/metabase/dashboard/analytics.ts")
        # Check that the file is at least parseable (no obvious syntax issues)
        with open(fpath, "r") as f:
            content = f.read()
        # Basic validation: should have export statements and interface/type definitions
        assert "export" in content, "analytics.ts should have export statements"
        has_types = bool(re.search(r'(interface|type)\s+\w+', content))
        assert has_types, "analytics.ts should define TypeScript interfaces or types"

    def test_dashboard_header_imports_tracking(self):
        """Verify DashboardHeader.tsx imports tracking from analytics module"""
        fpath = os.path.join(
            self.REPO_DIR,
            "frontend/src/metabase/dashboard/components/DashboardHeader/DashboardHeader.tsx"
        )
        with open(fpath, "r") as f:
            content = f.read()
        has_import = bool(re.search(r'(import.*analytics|trackDashboardEvent)', content))
        assert has_import, "DashboardHeader should import from the analytics module"

    def test_dashboard_header_fires_events(self):
        """Verify DashboardHeader has tracking calls for dashboard actions"""
        fpath = os.path.join(
            self.REPO_DIR,
            "frontend/src/metabase/dashboard/components/DashboardHeader/DashboardHeader.tsx"
        )
        with open(fpath, "r") as f:
            content = f.read()
        has_track_call = bool(re.search(r'trackDashboardEvent\s*\(', content))
        assert has_track_call, "DashboardHeader should call trackDashboardEvent"

    def test_no_pii_in_analytics(self):
        """Verify analytics module does not include PII fields"""
        fpath = os.path.join(self.REPO_DIR, "frontend/src/metabase/dashboard/analytics.ts")
        with open(fpath, "r") as f:
            content = f.read().lower()
        pii_fields = ["email", "username", "user_name", "first_name", "last_name", "password"]
        for field in pii_fields:
            # Allow user_id which is expected
            if field == "user_id":
                continue
            assert field not in content, (
                f"analytics.ts should not include PII field: '{field}'"
            )

    def test_analytics_includes_source_metadata(self):
        """Verify events include automatic metadata: source field"""
        fpath = os.path.join(self.REPO_DIR, "frontend/src/metabase/dashboard/analytics.ts")
        with open(fpath, "r") as f:
            content = f.read()
        has_source = bool(re.search(r'source.*dashboard|["\']dashboard["\']', content))
        assert has_source, "Events should include source: 'dashboard' metadata"
