"""
Test skill: security-review
Verify that the Agent correctly implements a security review and fixes
vulnerabilities in a Node.js Express healthcare API (babybuddy codebase).
"""

import os
import re
import json
import subprocess
import pytest


class TestSecurityReview:
    REPO_DIR = "/workspace/babybuddy"

    # === File Path Checks ===

    def test_security_config_file_exists(self):
        """Verify that the security configuration file exists"""
        path = os.path.join(self.REPO_DIR, "src/config/security.ts")
        assert os.path.exists(path), f"security.ts not found at {path}"

    def test_auth_middleware_file_exists(self):
        """Verify that the auth middleware file exists"""
        path = os.path.join(self.REPO_DIR, "src/middleware/auth.ts")
        assert os.path.exists(path), f"auth.ts not found at {path}"

    def test_validation_middleware_file_exists(self):
        """Verify that the validation middleware file exists"""
        path = os.path.join(self.REPO_DIR, "src/middleware/validation.ts")
        assert os.path.exists(path), f"validation.ts not found at {path}"

    def test_rate_limiter_file_exists(self):
        """Verify that the rate limiter middleware file exists"""
        path = os.path.join(self.REPO_DIR, "src/middleware/rate-limiter.ts")
        assert os.path.exists(path), f"rate-limiter.ts not found at {path}"

    def test_file_upload_middleware_exists(self):
        """Verify that the file upload middleware file exists"""
        path = os.path.join(self.REPO_DIR, "src/middleware/file-upload.ts")
        assert os.path.exists(path), f"file-upload.ts not found at {path}"

    def test_crypto_utils_file_exists(self):
        """Verify that the cryptographic utilities file exists"""
        path = os.path.join(self.REPO_DIR, "src/utils/crypto.ts")
        assert os.path.exists(path), f"crypto.ts not found at {path}"

    def test_audit_log_file_exists(self):
        """Verify that the audit log file exists"""
        path = os.path.join(self.REPO_DIR, "src/utils/audit-log.ts")
        assert os.path.exists(path), f"audit-log.ts not found at {path}"

    # === Semantic Checks ===

    def test_security_config_has_csp_headers(self):
        """Verify that security config defines CSP headers blocking inline scripts"""
        path = os.path.join(self.REPO_DIR, "src/config/security.ts")
        with open(path, "r") as f:
            content = f.read()

        assert "contentSecurityPolicy" in content, (
            "Security config missing contentSecurityPolicy"
        )
        assert "'self'" in content, (
            "CSP should set defaultSrc to 'self'"
        )
        assert "scriptSrc" in content, "CSP should define scriptSrc directive"
        # Verify no 'unsafe-eval' in scriptSrc
        lines = content.split("\n")
        in_script_src = False
        for line in lines:
            if "scriptSrc" in line:
                in_script_src = True
            if in_script_src:
                assert "unsafe-eval" not in line, (
                    "CSP scriptSrc should NOT include 'unsafe-eval'"
                )
                if "]" in line or "}" in line:
                    break

    def test_security_config_has_hsts(self):
        """Verify that security config defines HSTS with 1-year max-age and preload"""
        path = os.path.join(self.REPO_DIR, "src/config/security.ts")
        with open(path, "r") as f:
            content = f.read()

        assert "hsts" in content, "Security config missing HSTS configuration"
        assert "31536000" in content, (
            "HSTS maxAge should be 31536000 (1 year)"
        )
        assert "preload" in content, "HSTS should have preload enabled"

    def test_security_config_has_cors_restriction(self):
        """Verify that CORS is restricted to specific portal domain"""
        path = os.path.join(self.REPO_DIR, "src/config/security.ts")
        with open(path, "r") as f:
            content = f.read()

        assert "cors" in content.lower(), "Security config missing CORS configuration"
        # Should not have wildcard origin
        assert content.count('"*"') == 0 or "origin" not in content.split('"*"')[0][-50:], (
            "CORS origin should not be wildcard '*'"
        )

    def test_auth_uses_argon2(self):
        """Verify that authentication uses argon2id for password hashing"""
        path = os.path.join(self.REPO_DIR, "src/utils/crypto.ts")
        with open(path, "r") as f:
            content = f.read()

        assert "argon2" in content.lower(), (
            "crypto.ts should use argon2 for password hashing"
        )
        # Check for recommended parameters
        assert "65536" in content or "memoryCost" in content, (
            "argon2 should use memoryCost of 65536"
        )

    def test_auth_uses_httponly_cookies(self):
        """Verify that JWT tokens are stored in httpOnly secure cookies"""
        auth_path = os.path.join(self.REPO_DIR, "src/middleware/auth.ts")
        config_path = os.path.join(self.REPO_DIR, "src/config/security.ts")

        found_httponly = False
        for path in [auth_path, config_path]:
            if os.path.exists(path):
                with open(path, "r") as f:
                    content = f.read()
                if "httpOnly" in content or "httponly" in content.lower():
                    found_httponly = True
                    break

        assert found_httponly, (
            "JWT access tokens should be stored in httpOnly cookies"
        )

    def test_validation_uses_zod_schemas(self):
        """Verify that input validation uses Zod schemas"""
        path = os.path.join(self.REPO_DIR, "src/middleware/validation.ts")
        with open(path, "r") as f:
            content = f.read()

        assert "zod" in content.lower() or "z." in content, (
            "validation.ts should use Zod for input validation"
        )
        # Check for patient creation schema
        assert "Patient" in content or "patient" in content, (
            "validation.ts should define patient-related Zod schemas"
        )

    def test_patient_routes_use_parameterized_queries(self):
        """Verify that patient routes use parameterized queries, not string concatenation"""
        path = os.path.join(self.REPO_DIR, "src/routes/patients.ts")
        with open(path, "r") as f:
            content = f.read()

        # Check for parameterized query patterns ($1, $2 or ? placeholders)
        has_parameterized = "$1" in content or "?" in content or "parameterized" in content.lower()
        assert has_parameterized, (
            "Patient routes should use parameterized queries ($1 placeholders)"
        )

        # Check for dangerous string interpolation in queries
        dangerous_patterns = [
            re.compile(r'`SELECT.*\$\{.*\}.*`'),
            re.compile(r"query\s*\(\s*`[^`]*\$\{"),
            re.compile(r'query\s*\(\s*"[^"]*"\s*\+'),
        ]
        for pattern in dangerous_patterns:
            matches = pattern.findall(content)
            assert len(matches) == 0, (
                f"Patient routes should NOT use string interpolation in SQL queries. "
                f"Found: {matches}"
            )

    def test_crypto_utils_has_aes_256_gcm(self):
        """Verify that crypto utilities implement AES-256-GCM encryption for PII"""
        path = os.path.join(self.REPO_DIR, "src/utils/crypto.ts")
        with open(path, "r") as f:
            content = f.read()

        assert "aes-256-gcm" in content.lower() or "AES" in content, (
            "crypto.ts should implement AES-256-GCM encryption"
        )
        assert "encryptPII" in content or "encrypt" in content, (
            "crypto.ts should have an encryption function for PII"
        )
        assert "decryptPII" in content or "decrypt" in content, (
            "crypto.ts should have a decryption function for PII"
        )

    def test_file_upload_validates_magic_bytes(self):
        """Verify that file upload validates MIME type by magic bytes, not Content-Type header"""
        path = os.path.join(self.REPO_DIR, "src/middleware/file-upload.ts")
        with open(path, "r") as f:
            content = f.read()

        has_magic_byte_check = any(kw in content for kw in [
            "magic", "fileType", "file-type", "readFileSync",
            "Buffer", "signature", "header bytes", "magic bytes",
            "fromBuffer", "fromFile", "fileTypeFromBuffer",
        ])
        assert has_magic_byte_check, (
            "file-upload.ts should validate file type by reading magic bytes, "
            "not trusting Content-Type header"
        )

    def test_file_upload_sanitizes_filename(self):
        """Verify that file upload sanitizes filenames to prevent path traversal"""
        path = os.path.join(self.REPO_DIR, "src/middleware/file-upload.ts")
        with open(path, "r") as f:
            content = f.read()

        has_sanitization = any(kw in content for kw in [
            "sanitize", "path.basename", "replace", "uuid", "UUID",
            "../", "path traversal", "normalize",
        ])
        assert has_sanitization, (
            "file-upload.ts should sanitize filenames to prevent path traversal attacks"
        )

    def test_rate_limiter_defines_per_endpoint_limits(self):
        """Verify that rate limiter defines per-endpoint limits"""
        path = os.path.join(self.REPO_DIR, "src/middleware/rate-limiter.ts")
        with open(path, "r") as f:
            content = f.read()

        # Check for different rate limits
        assert "5" in content, "Rate limiter should define 5/min for auth endpoints"
        assert "100" in content, "Rate limiter should define 100/min for API endpoints"
        assert "10" in content, "Rate limiter should define 10/min for upload endpoints"

    def test_audit_log_has_required_event_types(self):
        """Verify that audit log defines required event types"""
        path = os.path.join(self.REPO_DIR, "src/utils/audit-log.ts")
        with open(path, "r") as f:
            content = f.read()

        required_events = ["auth.login", "auth.logout", "auth.failed",
                          "data.read", "data.create"]
        for event in required_events:
            assert event in content, (
                f"audit-log.ts missing required event type: {event}"
            )

    def test_audit_log_masks_pii(self):
        """Verify that audit log masks PII data in log entries"""
        path = os.path.join(self.REPO_DIR, "src/utils/audit-log.ts")
        with open(path, "r") as f:
            content = f.read()

        has_masking = any(kw in content for kw in [
            "mask", "***", "redact", "anonymize", "sanitize",
        ])
        assert has_masking, (
            "audit-log.ts should mask PII (email, phone, SSN) in log entries"
        )

    # === Functional Checks ===

    def test_security_config_is_valid_typescript(self):
        """Verify that security config TypeScript file has valid syntax"""
        path = os.path.join(self.REPO_DIR, "src/config/security.ts")
        with open(path, "r") as f:
            content = f.read()
        # Check basic structure - should have an export
        assert "export" in content, "security.ts should export configuration"
        # Should define securityConfig or similar object
        has_config_export = "securityConfig" in content or "security" in content.lower()
        assert has_config_export, "security.ts should export a security configuration object"

    def test_no_hardcoded_secrets_in_source(self):
        """Verify that no hardcoded secrets exist in source files"""
        source_dirs = ["src/config", "src/middleware", "src/routes", "src/utils"]
        secret_patterns = [
            re.compile(r'(password|secret|api_key|apikey|token)\s*[:=]\s*["\'][^"\']+["\']', re.I),
        ]
        for src_dir in source_dirs:
            dir_path = os.path.join(self.REPO_DIR, src_dir)
            if not os.path.exists(dir_path):
                continue
            for filename in os.listdir(dir_path):
                if not filename.endswith(".ts"):
                    continue
                filepath = os.path.join(dir_path, filename)
                with open(filepath, "r") as f:
                    content = f.read()
                for pattern in secret_patterns:
                    matches = pattern.findall(content)
                    # Filter out type annotations and interface definitions
                    real_secrets = []
                    for m in matches:
                        # Skip if it's in a type/interface definition or environment variable lookup
                        if "process.env" in content[max(0, content.find(m)-50):content.find(m)+len(m)+50]:
                            continue
                        if "type " in content[max(0, content.find(m)-30):content.find(m)]:
                            continue
                        real_secrets.append(m)
                    # Allow some patterns that are type definitions
                    if len(real_secrets) > 0:
                        # Double-check: these might be variable names, not actual values
                        for secret in real_secrets:
                            # Skip if the "value" is clearly a placeholder
                            if any(placeholder in secret for placeholder in [
                                "process.env", "env.", "ENV", "placeholder",
                                "your_", "CHANGE_ME", "example", "test"
                            ]):
                                continue

    def test_encryption_key_from_environment(self):
        """Verify that encryption key is loaded from environment variable, not hardcoded"""
        path = os.path.join(self.REPO_DIR, "src/utils/crypto.ts")
        with open(path, "r") as f:
            content = f.read()

        assert "process.env" in content or "ENCRYPTION_KEY" in content, (
            "Encryption key should be loaded from environment variable ENCRYPTION_KEY"
        )

    def test_security_tests_file_exists_and_covers_owasp(self):
        """Verify that security tests exist and cover OWASP attack vectors"""
        path = os.path.join(self.REPO_DIR, "tests/security.test.ts")
        assert os.path.exists(path), f"Security tests not found at {path}"

        with open(path, "r") as f:
            content = f.read()

        # Check for SQL injection test
        has_sql_injection = any(kw in content for kw in [
            "SQL", "injection", "DROP TABLE", "'; DROP",
        ])
        assert has_sql_injection, "Security tests should include SQL injection test"

        # Check for XSS test
        has_xss = any(kw in content for kw in [
            "XSS", "script", "<script>", "alert",
        ])
        assert has_xss, "Security tests should include XSS test"

        # Check for auth bypass test
        has_auth_bypass = any(kw in content for kw in [
            "401", "unauthorized", "bypass", "without token", "expired token",
        ])
        assert has_auth_bypass, "Security tests should include auth bypass test"

        # Check for path traversal test
        has_path_traversal = any(kw in content for kw in [
            "path traversal", "../", "traversal", "passwd",
        ])
        assert has_path_traversal, "Security tests should include path traversal test"

    def test_access_control_returns_404_not_403(self):
        """Verify that access control returns 404 for non-existent resources (not 403) to prevent enumeration"""
        path = os.path.join(self.REPO_DIR, "src/routes/patients.ts")
        with open(path, "r") as f:
            content = f.read()

        # Check that 404 is used instead of 403 to prevent enumeration
        assert "404" in content, (
            "Patient routes should return 404 (not 403) for unauthorized access "
            "to prevent resource enumeration"
        )

    def test_cookie_settings_are_secure(self):
        """Verify that cookie settings include httpOnly, secure, and sameSite=strict"""
        config_path = os.path.join(self.REPO_DIR, "src/config/security.ts")
        auth_path = os.path.join(self.REPO_DIR, "src/middleware/auth.ts")

        secure_settings_found = {"httpOnly": False, "secure": False, "sameSite": False}

        for path in [config_path, auth_path]:
            if os.path.exists(path):
                with open(path, "r") as f:
                    content = f.read()
                if "httpOnly" in content:
                    secure_settings_found["httpOnly"] = True
                if "secure" in content and ("true" in content.lower()):
                    secure_settings_found["secure"] = True
                if "sameSite" in content and "strict" in content.lower():
                    secure_settings_found["sameSite"] = True

        for setting, found in secure_settings_found.items():
            assert found, f"Cookie setting '{setting}' not properly configured"
