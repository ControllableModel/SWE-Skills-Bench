"""
Test skill: clojure-write
Verify that the Agent implements a Query Result Digest Notification Service in
Metabase — SHA-256 digest middleware, change-detection service, correct change
types, and integration with the Toucan model layer.
"""

import os
import re
import subprocess
import pytest


class TestClojureWrite:
    REPO_DIR = "/workspace/metabase"
    DIGEST_SRC = "src/metabase/query_processor/middleware/result_digest.clj"
    CHANGE_SRC = "src/metabase/notification/result_change.clj"
    DIGEST_TEST = "test/metabase/query_processor/middleware/result_digest_test.clj"
    CHANGE_TEST = "test/metabase/notification/result_change_test.clj"

    # ────────────────── helpers ──────────────────

    def _read(self, rel_path):
        fpath = os.path.join(self.REPO_DIR, rel_path)
        with open(fpath, "r") as f:
            return f.read()

    def _exists(self, rel_path):
        return os.path.isfile(os.path.join(self.REPO_DIR, rel_path))

    # === File Path Checks ===

    def test_result_digest_src_exists(self):
        """result_digest.clj source file must exist"""
        assert self._exists(self.DIGEST_SRC), f"Not found: {self.DIGEST_SRC}"

    def test_result_change_src_exists(self):
        """result_change.clj source file must exist"""
        assert self._exists(self.CHANGE_SRC), f"Not found: {self.CHANGE_SRC}"

    def test_result_digest_test_exists(self):
        """result_digest_test.clj test file must exist"""
        assert self._exists(self.DIGEST_TEST), f"Not found: {self.DIGEST_TEST}"

    def test_result_change_test_exists(self):
        """result_change_test.clj test file must exist"""
        assert self._exists(self.CHANGE_TEST), f"Not found: {self.CHANGE_TEST}"

    # === Semantic Checks — Digest Middleware ===

    def test_digest_namespace_declaration(self):
        """result_digest.clj must declare the correct namespace"""
        src = self._read(self.DIGEST_SRC)
        assert re.search(
            r'\(ns\s+metabase\.query-processor\.middleware\.result-digest', src
        ), "Namespace declaration missing or incorrect"

    def test_compute_digest_function_exists(self):
        """compute-digest function must be defined"""
        src = self._read(self.DIGEST_SRC)
        assert re.search(r'\(defn-?\s+compute-digest\b', src), (
            "compute-digest function not found"
        )

    def test_sha256_usage(self):
        """Digest must use java.security.MessageDigest for SHA-256"""
        src = self._read(self.DIGEST_SRC)
        assert "MessageDigest" in src or "SHA-256" in src, (
            "SHA-256 / java.security.MessageDigest not referenced"
        )

    def test_compute_digest_returns_map_keys(self):
        """compute-digest should return a map with :digest, :row-count, :col-count"""
        src = self._read(self.DIGEST_SRC)
        for key in [":digest", ":row-count", ":col-count"]:
            assert key in src, f"compute-digest missing return key {key}"

    def test_middleware_function_exists(self):
        """result-digest-middleware function must be defined"""
        src = self._read(self.DIGEST_SRC)
        assert re.search(r'\(defn-?\s+result-digest-middleware\b', src), (
            "result-digest-middleware function not found"
        )

    def test_middleware_checks_compute_flag(self):
        """Middleware should check :compute-digest? flag in the query"""
        src = self._read(self.DIGEST_SRC)
        assert ":compute-digest?" in src, (
            "Middleware does not check :compute-digest? flag"
        )

    def test_pr_str_for_canonicalization(self):
        """Rows should be serialised with pr-str for canonical representation"""
        src = self._read(self.DIGEST_SRC)
        assert "pr-str" in src, "pr-str not used for canonical row serialisation"

    # === Semantic Checks — Change Detection Service ===

    def test_change_namespace_declaration(self):
        """result_change.clj must declare the correct namespace"""
        src = self._read(self.CHANGE_SRC)
        assert re.search(
            r'\(ns\s+metabase\.notification\.result-change', src
        ), "Namespace declaration missing or incorrect"

    def test_check_card_function_exists(self):
        """check-card-for-changes function must be defined"""
        src = self._read(self.CHANGE_SRC)
        assert re.search(r'\(defn-?\s+check-card-for-changes\b', src), (
            "check-card-for-changes function not found"
        )

    def test_check_all_monitored_function_exists(self):
        """check-all-monitored-cards function must be defined"""
        src = self._read(self.CHANGE_SRC)
        assert re.search(r'\(defn-?\s+check-all-monitored-cards\b', src), (
            "check-all-monitored-cards function not found"
        )

    def test_update_stored_digest_function_exists(self):
        """update-stored-digest function must be defined"""
        src = self._read(self.CHANGE_SRC)
        assert re.search(r'\(defn-?\s+update-stored-digest\b', src), (
            "update-stored-digest function not found"
        )

    def test_change_types_present(self):
        """All four change-types must appear: :new-results, :schema-change,
        :row-count-change, :data-change"""
        src = self._read(self.CHANGE_SRC)
        for ct in [":new-results", ":schema-change", ":row-count-change", ":data-change"]:
            assert ct in src, f"Change type {ct} not found in result_change.clj"

    def test_notification_payload_keys(self):
        """Notification payload must include :card-id, :card-name, :change-type,
        :previous, :current, :detected-at"""
        src = self._read(self.CHANGE_SRC)
        for key in [":card-id", ":card-name", ":change-type", ":previous",
                     ":current", ":detected-at"]:
            assert key in src, f"Payload key {key} missing in result_change.clj"

    def test_toucan2_usage(self):
        """Service should use Toucan 2 (t2) for database operations"""
        src = self._read(self.CHANGE_SRC)
        assert "t2/" in src or "toucan2" in src or "toucan.db" in src, (
            "Toucan 2 (t2) not used for DB operations"
        )

    def test_uses_metabase_util_log(self):
        """Logging should use metabase.util.log, not println or clojure.tools.logging"""
        src = self._read(self.CHANGE_SRC)
        assert "println" not in src, "Should not use println for logging"
        assert "metabase.util.log" in src or "mu/log" in src or "log/" in src, (
            "Should use metabase.util.log for logging"
        )

    # === Functional Checks ===

    def test_digest_namespace_compiles(self):
        """result_digest namespace must compile successfully"""
        result = subprocess.run(
            ["clojure", "-M", "-e",
             "(require 'metabase.query-processor.middleware.result-digest)"],
            capture_output=True, text=True, cwd=self.REPO_DIR, timeout=120,
        )
        assert result.returncode == 0, (
            f"Compilation failed:\n{result.stdout}\n{result.stderr}"
        )

    def test_change_namespace_compiles(self):
        """result_change namespace must compile successfully"""
        result = subprocess.run(
            ["clojure", "-M", "-e",
             "(require 'metabase.notification.result-change)"],
            capture_output=True, text=True, cwd=self.REPO_DIR, timeout=120,
        )
        assert result.returncode == 0, (
            f"Compilation failed:\n{result.stdout}\n{result.stderr}"
        )

    def test_digest_tests_pass(self):
        """result_digest_test must pass"""
        result = subprocess.run(
            ["clojure", "-X:dev:test",
             ":only", "metabase.query-processor.middleware.result-digest-test"],
            capture_output=True, text=True, cwd=self.REPO_DIR, timeout=300,
        )
        assert result.returncode == 0, (
            f"Digest tests failed:\n{result.stdout}\n{result.stderr}"
        )

    def test_change_tests_pass(self):
        """result_change_test must pass"""
        result = subprocess.run(
            ["clojure", "-X:dev:test",
             ":only", "metabase.notification.result-change-test"],
            capture_output=True, text=True, cwd=self.REPO_DIR, timeout=300,
        )
        assert result.returncode == 0, (
            f"Change tests failed:\n{result.stdout}\n{result.stderr}"
        )
