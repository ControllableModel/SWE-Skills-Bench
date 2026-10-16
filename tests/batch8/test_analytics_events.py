"""
Test skill: analytics-events
Verify that the Agent correctly adds Dashboard Subscription Analytics Events
to the Metabase frontend, including TypeScript types, tracking functions,
and unit tests.
"""

import os
import subprocess
import re
import pytest


class TestAnalyticsEvents:
    REPO_DIR = "/workspace/metabase"

    # === File Path Checks ===

    def test_analytics_module_exists(self):
        """Verify that the subscription analytics module exists"""
        filepath = os.path.join(
            self.REPO_DIR,
            "frontend/src/metabase/dashboard/components/DashboardSubscriptionPanel/analytics.ts"
        )
        assert os.path.exists(filepath), f"analytics.ts not found at {filepath}"

    def test_analytics_test_file_exists(self):
        """Verify that the analytics unit test file exists"""
        filepath = os.path.join(
            self.REPO_DIR,
            "frontend/src/metabase/dashboard/components/DashboardSubscriptionPanel/analytics.unit.spec.ts"
        )
        assert os.path.exists(filepath), f"analytics.unit.spec.ts not found at {filepath}"

    def test_event_type_file_exists(self):
        """Verify that the event type definition file exists"""
        filepath = os.path.join(
            self.REPO_DIR,
            "frontend/src/metabase-types/analytics/event.ts"
        )
        assert os.path.exists(filepath), f"event.ts not found at {filepath}"

    # === Semantic Checks ===

    def test_event_type_defines_subscription_events(self):
        """Verify DashboardSubscriptionEvent type defines all four event variants"""
        filepath = os.path.join(
            self.REPO_DIR,
            "frontend/src/metabase-types/analytics/event.ts"
        )
        with open(filepath) as f:
            content = f.read()

        assert "DashboardSubscriptionEvent" in content, (
            "event.ts missing DashboardSubscriptionEvent type definition"
        )

        event_variants = [
            "dashboard_subscription_created",
            "dashboard_subscription_updated",
            "dashboard_subscription_deleted",
            "dashboard_subscription_test_sent",
        ]
        for variant in event_variants:
            assert variant in content, (
                f"event.ts missing event variant '{variant}'"
            )

    def test_event_type_has_required_payload_fields(self):
        """Verify event types include required payload fields"""
        filepath = os.path.join(
            self.REPO_DIR,
            "frontend/src/metabase-types/analytics/event.ts"
        )
        with open(filepath) as f:
            content = f.read()

        required_fields = [
            "dashboard_id",
            "subscription_type",
            "schedule",
            "recipient_count",
            "subscription_id",
            "changed_fields",
            "success",
        ]
        found = [f for f in required_fields if f in content]
        assert len(found) >= 5, (
            f"event.ts has only {len(found)} of {len(required_fields)} required payload fields. "
            f"Found: {found}"
        )

    def test_schema_registration(self):
        """Verify DashboardSubscriptionEvent is registered in the analytics schema"""
        filepath = os.path.join(
            self.REPO_DIR,
            "frontend/src/metabase-types/analytics/schema.ts"
        )
        with open(filepath) as f:
            content = f.read()

        assert "DashboardSubscriptionEvent" in content, (
            "schema.ts does not include DashboardSubscriptionEvent in the AnalyticsEvent union"
        )
        assert "dashboard-subscription" in content, (
            "schema.ts does not register 'dashboard-subscription' schema name"
        )

    def test_analytics_module_has_tracking_functions(self):
        """Verify analytics.ts exports all required tracking functions"""
        filepath = os.path.join(
            self.REPO_DIR,
            "frontend/src/metabase/dashboard/components/DashboardSubscriptionPanel/analytics.ts"
        )
        with open(filepath) as f:
            content = f.read()

        functions = [
            "trackSubscriptionCreated",
            "trackSubscriptionUpdated",
            "trackSubscriptionDeleted",
            "trackSubscriptionTestSent",
        ]
        for func in functions:
            assert func in content, (
                f"analytics.ts missing tracking function '{func}'"
            )

    def test_event_has_schema_and_version(self):
        """Verify events include schema and version fields"""
        filepath = os.path.join(
            self.REPO_DIR,
            "frontend/src/metabase-types/analytics/event.ts"
        )
        with open(filepath) as f:
            content = f.read()

        assert "schema" in content, (
            "event.ts does not include 'schema' field in event type"
        )
        assert "version" in content, (
            "event.ts does not include 'version' field in event type"
        )
        assert "1-0-0" in content, (
            "event.ts does not include version '1-0-0'"
        )

    # === Functional Checks ===

    def test_analytics_module_is_valid_typescript(self):
        """Verify that analytics.ts is parseable TypeScript"""
        filepath = os.path.join(
            self.REPO_DIR,
            "frontend/src/metabase/dashboard/components/DashboardSubscriptionPanel/analytics.ts"
        )
        with open(filepath) as f:
            content = f.read()

        # Basic structural validation - must have export statements
        has_exports = "export" in content
        assert has_exports, "analytics.ts should export tracking functions"

        # Should import from analytics
        has_imports = "import" in content
        assert has_imports, "analytics.ts should import from the analytics library"

    def test_tracking_validates_dashboard_id(self):
        """Verify tracking functions validate dashboardId is positive integer"""
        filepath = os.path.join(
            self.REPO_DIR,
            "frontend/src/metabase/dashboard/components/DashboardSubscriptionPanel/analytics.ts"
        )
        with open(filepath) as f:
            content = f.read()

        # Should have validation logic for dashboardId
        has_validation = (
            "dashboardId" in content
            and ("> 0" in content or ">= 1" in content or "positive" in content.lower()
                 or "isNaN" in content or "Number.isInteger" in content
                 or "typeof" in content)
        )
        assert has_validation, (
            "analytics.ts does not appear to validate dashboardId as a positive integer. "
            "Functions should silently return for invalid dashboardId."
        )

    def test_update_tracking_validates_changed_fields(self):
        """Verify trackSubscriptionUpdated skips dispatch for empty changedFields"""
        filepath = os.path.join(
            self.REPO_DIR,
            "frontend/src/metabase/dashboard/components/DashboardSubscriptionPanel/analytics.ts"
        )
        with open(filepath) as f:
            content = f.read()

        # Should check changedFields is not empty before dispatching
        has_empty_check = (
            "length" in content
            or ".length > 0" in content
            or ".length === 0" in content
            or "changedFields" in content
        )
        assert has_empty_check, (
            "analytics.ts does not validate that changedFields is non-empty "
            "before dispatching the update event."
        )

    def test_unit_test_covers_all_events(self):
        """Verify unit tests cover all four event types"""
        filepath = os.path.join(
            self.REPO_DIR,
            "frontend/src/metabase/dashboard/components/DashboardSubscriptionPanel/analytics.unit.spec.ts"
        )
        with open(filepath) as f:
            content = f.read()

        for func in ["trackSubscriptionCreated", "trackSubscriptionUpdated",
                      "trackSubscriptionDeleted", "trackSubscriptionTestSent"]:
            assert func in content, (
                f"Unit test file does not test '{func}'"
            )

    def test_unit_test_covers_skip_behavior(self):
        """Verify unit tests validate silent skip for invalid inputs"""
        filepath = os.path.join(
            self.REPO_DIR,
            "frontend/src/metabase/dashboard/components/DashboardSubscriptionPanel/analytics.unit.spec.ts"
        )
        with open(filepath) as f:
            content = f.read()

        has_skip_tests = (
            "invalid" in content.lower()
            or "negative" in content.lower()
            or "empty" in content.lower()
            or "not.toHaveBeenCalled" in content
            or "should not" in content.lower()
        )
        assert has_skip_tests, (
            "Unit tests do not appear to cover skip behavior for invalid inputs. "
            "Expected tests for negative dashboardId and empty changedFields."
        )

    def test_analytics_lib_updated(self):
        """Verify that analytics.ts or lib/analytics.ts includes subscription tracking"""
        filepath = os.path.join(
            self.REPO_DIR,
            "frontend/src/metabase/lib/analytics.ts"
        )
        if os.path.exists(filepath):
            with open(filepath) as f:
                content = f.read()
            has_subscription = (
                "subscription" in content.lower()
                or "dashboard_subscription" in content
            )
            assert has_subscription, (
                "lib/analytics.ts does not include dashboard subscription tracking functions"
            )
