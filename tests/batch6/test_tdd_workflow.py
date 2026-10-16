"""
Test skill: tdd-workflow
Verify that the Agent correctly implements a URL shortener service
using Test-Driven Development with TypeScript, Express, and PostgreSQL.
"""

import os
import re
import json
import subprocess
import pytest


class TestTddWorkflow:
    REPO_DIR = "/workspace/python"

    # === File Path Checks ===

    def test_url_shortener_service_file_exists(self):
        """Verify that the URL shortener service file exists"""
        path = os.path.join(self.REPO_DIR, "src/services/url-shortener.ts")
        assert os.path.exists(path), f"url-shortener.ts not found at {path}"

    def test_analytics_service_file_exists(self):
        """Verify that the analytics service file exists"""
        path = os.path.join(self.REPO_DIR, "src/services/analytics.ts")
        assert os.path.exists(path), f"analytics.ts not found at {path}"

    def test_api_routes_file_exists(self):
        """Verify that the API routes file exists"""
        path = os.path.join(self.REPO_DIR, "src/routes/api.ts")
        assert os.path.exists(path), f"api.ts not found at {path}"

    def test_db_repository_file_exists(self):
        """Verify that the database repository file exists"""
        path = os.path.join(self.REPO_DIR, "src/db/repository.ts")
        assert os.path.exists(path), f"repository.ts not found at {path}"

    def test_migration_sql_file_exists(self):
        """Verify that the SQL migration file exists"""
        path = os.path.join(self.REPO_DIR, "src/db/migrations/001_create_tables.sql")
        assert os.path.exists(path), f"001_create_tables.sql not found at {path}"

    def test_unit_test_files_exist(self):
        """Verify that unit test files exist"""
        for test_file in [
            "tests/unit/url-shortener.test.ts",
            "tests/unit/analytics.test.ts",
        ]:
            path = os.path.join(self.REPO_DIR, test_file)
            assert os.path.exists(path), f"Test file {test_file} not found at {path}"

    def test_integration_test_file_exists(self):
        """Verify that integration test file exists"""
        path = os.path.join(self.REPO_DIR, "tests/integration/api.test.ts")
        assert os.path.exists(path), f"api.test.ts not found at {path}"

    # === Semantic Checks ===

    def test_migration_sql_has_short_links_table(self):
        """Verify that the SQL migration defines the short_links table with required columns"""
        path = os.path.join(self.REPO_DIR, "src/db/migrations/001_create_tables.sql")
        with open(path, "r") as f:
            content = f.read().lower()

        assert "short_links" in content, "Migration missing short_links table"
        required_columns = ["code", "original_url", "created_at", "expires_at",
                           "click_count", "is_active"]
        for col in required_columns:
            assert col in content, (
                f"short_links table missing required column: {col}"
            )
        # Verify code is unique
        assert "unique" in content, "short_links.code should have UNIQUE constraint"

    def test_migration_sql_has_click_events_table(self):
        """Verify that the SQL migration defines the click_events table with required columns"""
        path = os.path.join(self.REPO_DIR, "src/db/migrations/001_create_tables.sql")
        with open(path, "r") as f:
            content = f.read().lower()

        assert "click_events" in content, "Migration missing click_events table"
        required_columns = ["link_id", "clicked_at", "ip_address", "user_agent",
                           "referer", "country"]
        for col in required_columns:
            assert col in content, (
                f"click_events table missing required column: {col}"
            )
        # Verify foreign key relationship
        assert "foreign key" in content or "references" in content, (
            "click_events should have a foreign key reference to short_links"
        )

    def test_url_shortener_service_has_required_functions(self):
        """Verify that url-shortener.ts exports required functions"""
        path = os.path.join(self.REPO_DIR, "src/services/url-shortener.ts")
        with open(path, "r") as f:
            content = f.read()

        required_functions = ["generateCode", "validateUrl", "createShortLink", "resolveCode"]
        for func in required_functions:
            assert func in content, (
                f"url-shortener.ts missing required function: {func}"
            )

    def test_url_shortener_uses_crypto_random(self):
        """Verify that code generation uses cryptographically random bytes"""
        path = os.path.join(self.REPO_DIR, "src/services/url-shortener.ts")
        with open(path, "r") as f:
            content = f.read()

        assert "crypto" in content.lower() or "randomBytes" in content or "randomUUID" in content, (
            "generateCode should use crypto.randomBytes for cryptographic randomness"
        )

    def test_url_shortener_validates_private_ips(self):
        """Verify that URL validation rejects private IP ranges"""
        path = os.path.join(self.REPO_DIR, "src/services/url-shortener.ts")
        with open(path, "r") as f:
            content = f.read()

        # Check for private IP range handling
        has_private_ip_check = any(kw in content for kw in [
            "127.0.0.1", "localhost", "10.", "172.16", "192.168",
            "private", "isPrivate", "PRIVATE",
        ])
        assert has_private_ip_check, (
            "validateUrl should reject private IP ranges (10.x, 172.16-31.x, 192.168.x) and localhost"
        )

    def test_api_routes_has_required_endpoints(self):
        """Verify that api.ts defines all required REST endpoints"""
        path = os.path.join(self.REPO_DIR, "src/routes/api.ts")
        with open(path, "r") as f:
            content = f.read()

        # Check for route definitions
        assert "shorten" in content or "/api/shorten" in content, (
            "Missing POST /api/shorten endpoint"
        )
        assert "stats" in content or "/api/stats" in content, (
            "Missing GET /api/stats/:code endpoint"
        )
        assert "delete" in content.lower() or "DELETE" in content, (
            "Missing DELETE endpoint for links"
        )

    def test_analytics_service_has_required_functions(self):
        """Verify that analytics.ts exports required functions"""
        path = os.path.join(self.REPO_DIR, "src/services/analytics.ts")
        with open(path, "r") as f:
            content = f.read()

        required_functions = ["recordClick", "getStats"]
        for func in required_functions:
            assert func in content, (
                f"analytics.ts missing required function: {func}"
            )

    # === Functional Checks ===

    def test_unit_tests_cover_code_generation(self):
        """Verify that unit tests include code generation tests (length, uniqueness, charset)"""
        path = os.path.join(self.REPO_DIR, "tests/unit/url-shortener.test.ts")
        with open(path, "r") as f:
            content = f.read()

        # Check for specific test cases about code generation
        assert "generateCode" in content, "Unit tests missing generateCode tests"
        assert "7" in content or "length" in content.lower(), (
            "Unit tests should verify default code length of 7 characters"
        )
        # Check for uniqueness test
        assert "unique" in content.lower(), (
            "Unit tests should verify code uniqueness"
        )
        # Check for alphanumeric character set test
        has_charset_check = any(kw in content for kw in [
            "alphanumeric", "a-zA-Z0-9", "[a-z", "match", "regex", "RegExp"
        ])
        assert has_charset_check, (
            "Unit tests should verify codes are alphanumeric only"
        )

    def test_unit_tests_cover_url_validation(self):
        """Verify that unit tests include URL validation tests"""
        path = os.path.join(self.REPO_DIR, "tests/unit/url-shortener.test.ts")
        with open(path, "r") as f:
            content = f.read()

        assert "validateUrl" in content, "Unit tests missing validateUrl tests"
        # Check for various validation scenarios
        assert "http" in content.lower(), "Tests should check HTTP/HTTPS URLs"
        assert any(kw in content for kw in ["localhost", "127.0.0.1", "private"]), (
            "Tests should check rejection of localhost/private IPs"
        )

    def test_unit_tests_cover_analytics(self):
        """Verify that unit tests include analytics service tests"""
        path = os.path.join(self.REPO_DIR, "tests/unit/analytics.test.ts")
        with open(path, "r") as f:
            content = f.read()

        assert "recordClick" in content, "Analytics tests missing recordClick tests"
        assert "getStats" in content, "Analytics tests missing getStats tests"

    def test_integration_tests_cover_api_endpoints(self):
        """Verify that integration tests cover all API endpoints with success and error cases"""
        path = os.path.join(self.REPO_DIR, "tests/integration/api.test.ts")
        with open(path, "r") as f:
            content = f.read()

        # Check for endpoint coverage
        assert "/api/shorten" in content or "shorten" in content, (
            "Integration tests missing /api/shorten endpoint tests"
        )
        # Check for error case coverage
        assert "400" in content or "BadRequest" in content, (
            "Integration tests should cover 400 validation errors"
        )
        assert "404" in content or "NotFound" in content, (
            "Integration tests should cover 404 not found cases"
        )
        assert "410" in content or "Gone" in content, (
            "Integration tests should cover 410 Gone for expired links"
        )
        assert "201" in content or "Created" in content, (
            "Integration tests should verify 201 Created for successful shortening"
        )
        assert "302" in content or "redirect" in content.lower(), (
            "Integration tests should verify 302 redirect behavior"
        )

    def test_typescript_files_are_valid_syntax(self):
        """Verify that TypeScript source files have valid syntax by running tsc --noEmit"""
        # Install deps first
        install_result = subprocess.run(
            ["npm", "install"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if install_result.returncode != 0:
            pytest.skip(f"npm install failed: {install_result.stderr}")

        result = subprocess.run(
            ["npx", "tsc", "--noEmit", "--skipLibCheck"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        # We check for compilation - not zero errors necessarily (strict mode may flag things)
        # but should not have fundamental syntax errors
        if result.returncode != 0:
            # Check if errors are just type strictness, not syntax
            error_lines = result.stdout.strip().split("\n") if result.stdout else []
            syntax_errors = [l for l in error_lines if "error TS1" in l]  # TS1xxx are syntax errors
            assert len(syntax_errors) == 0, (
                f"TypeScript has syntax errors:\n{chr(10).join(syntax_errors[:10])}"
            )
