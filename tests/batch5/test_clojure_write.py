"""
Test skill: clojure-write
Verify that the Agent correctly implements a notification dispatch system
in Clojure for the Metabase backend.
"""

import os
import re
import pytest


class TestClojureWrite:
    REPO_DIR = "/workspace/metabase"

    CORE_NS = "src/metabase/notification/core.clj"
    EMAIL_NS = "src/metabase/notification/channels/email.clj"
    SLACK_NS = "src/metabase/notification/channels/slack.clj"
    WEBHOOK_NS = "src/metabase/notification/channels/webhook.clj"
    CONDITIONS_NS = "src/metabase/notification/conditions.clj"
    SCHEDULER_NS = "src/metabase/notification/scheduler.clj"
    CORE_TEST = "test/metabase/notification/core_test.clj"

    def _read_file(self, rel_path):
        filepath = os.path.join(self.REPO_DIR, rel_path)
        with open(filepath) as f:
            return f.read()

    # === File Path Checks ===

    def test_core_namespace_exists(self):
        """Verify notification/core.clj exists"""
        filepath = os.path.join(self.REPO_DIR, self.CORE_NS)
        assert os.path.exists(filepath), f"core.clj not found at {filepath}"

    def test_channel_files_exist(self):
        """Verify email, slack, and webhook channel files exist"""
        for path in [self.EMAIL_NS, self.SLACK_NS, self.WEBHOOK_NS]:
            filepath = os.path.join(self.REPO_DIR, path)
            assert os.path.exists(filepath), f"Channel file not found: {filepath}"

    def test_conditions_file_exists(self):
        """Verify conditions.clj exists"""
        filepath = os.path.join(self.REPO_DIR, self.CONDITIONS_NS)
        assert os.path.exists(filepath), f"conditions.clj not found at {filepath}"

    def test_scheduler_file_exists(self):
        """Verify scheduler.clj exists"""
        filepath = os.path.join(self.REPO_DIR, self.SCHEDULER_NS)
        assert os.path.exists(filepath), f"scheduler.clj not found at {filepath}"

    def test_test_file_exists(self):
        """Verify core_test.clj exists"""
        filepath = os.path.join(self.REPO_DIR, self.CORE_TEST)
        assert os.path.exists(filepath), f"Test file not found at {filepath}"

    # === Semantic Checks ===

    def test_core_defines_notification_record(self):
        """Verify core.clj defines a Notification record"""
        content = self._read_file(self.CORE_NS)
        assert "defrecord" in content and "Notification" in content, \
            "core.clj missing Notification defrecord"

    def test_core_defines_multimethod_dispatch(self):
        """Verify core.clj defines dispatch-notification multimethod"""
        content = self._read_file(self.CORE_NS)
        assert "defmulti" in content, "core.clj missing defmulti declaration"
        assert "dispatch-notification" in content, \
            "core.clj missing dispatch-notification multimethod"
        assert "channel-type" in content or ":channel-type" in content, \
            "dispatch-notification should dispatch on :channel-type"

    def test_email_channel_formats_html(self):
        """Verify email channel formats HTML message"""
        content = self._read_file(self.EMAIL_NS)
        assert "defmethod" in content or "dispatch-notification" in content, \
            "Email channel missing defmethod implementation"
        has_html = bool(re.search(r'(html|<table|<tr|<td|hiccup)', content, re.IGNORECASE))
        assert has_html, "Email channel missing HTML formatting"

    def test_slack_channel_uses_block_kit(self):
        """Verify Slack channel builds Block Kit payload"""
        content = self._read_file(self.SLACK_NS)
        assert "blocks" in content or ":blocks" in content, \
            "Slack channel missing Block Kit :blocks key"
        assert "header" in content, "Slack channel missing header block type"

    def test_webhook_channel_uses_hmac_signature(self):
        """Verify webhook channel includes HMAC-SHA256 signature"""
        content = self._read_file(self.WEBHOOK_NS)
        has_hmac = bool(re.search(
            r'(hmac|sha256|signature|HMAC|MessageDigest|Mac)',
            content,
            re.IGNORECASE,
        ))
        assert has_hmac, "Webhook channel missing HMAC-SHA256 signature"

    def test_conditions_define_four_evaluators(self):
        """Verify conditions.clj defines 4 condition evaluators"""
        content = self._read_file(self.CONDITIONS_NS)
        evaluators = [
            "rows-above-threshold", "rows-below-threshold",
            "column-value-changed", "query-returns-results",
        ]
        for ev in evaluators:
            assert ev in content, \
                f"conditions.clj missing evaluator: {ev}"

    def test_conditions_return_triggered_map(self):
        """Verify condition evaluators return {:triggered? :context} maps"""
        content = self._read_file(self.CONDITIONS_NS)
        assert ":triggered?" in content, \
            "Conditions missing :triggered? key in return map"
        assert ":context" in content, \
            "Conditions missing :context key in return map"

    def test_scheduler_uses_core_async(self):
        """Verify scheduler uses core.async for non-blocking processing"""
        content = self._read_file(self.SCHEDULER_NS)
        assert "core.async" in content or "async" in content.lower(), \
            "Scheduler missing core.async usage"
        has_go = bool(re.search(r'(go-loop|go\s|pipeline|<!\s|>!\s)', content))
        assert has_go, "Scheduler missing core.async go-loop or pipeline"

    # === Functional Checks ===

    def test_all_files_have_clojure_namespace(self):
        """Verify all source files declare proper Clojure namespaces"""
        for path in [self.CORE_NS, self.EMAIL_NS, self.SLACK_NS,
                     self.WEBHOOK_NS, self.CONDITIONS_NS, self.SCHEDULER_NS]:
            content = self._read_file(path)
            assert "(ns " in content, \
                f"{path} missing Clojure namespace declaration"

    def test_core_test_has_tests(self):
        """Verify test file has meaningful test definitions"""
        content = self._read_file(self.CORE_TEST)
        assert "deftest" in content, "Test file missing deftest definitions"
        test_count = content.count("deftest")
        assert test_count >= 3, \
            f"Expected at least 3 tests, found {test_count}"

    def test_webhook_uses_http_post(self):
        """Verify webhook channel makes HTTP POST requests"""
        content = self._read_file(self.WEBHOOK_NS)
        has_post = bool(re.search(
            r'(http/post|client/post|POST|post-request|clj-http)',
            content,
        ))
        assert has_post, "Webhook channel missing HTTP POST implementation"

    def test_scheduler_has_start_and_stop(self):
        """Verify scheduler has start-scheduler! and stop-scheduler! functions"""
        content = self._read_file(self.SCHEDULER_NS)
        assert "start-scheduler" in content, \
            "Scheduler missing start-scheduler! function"
        assert "stop-scheduler" in content, \
            "Scheduler missing stop-scheduler! function"
