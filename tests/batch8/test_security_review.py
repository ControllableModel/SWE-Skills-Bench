"""
Test skill: security-review
Verify that the Agent correctly conducts a security review and applies fixes
to the Baby Buddy Django application, including authentication, authorization,
input validation, security headers, rate limiting, and a security report.
"""

import os
import subprocess
import sys
import ast
import re
import json
import pytest


class TestSecurityReview:
    REPO_DIR = "/workspace/babybuddy"

    # === File Path Checks ===

    def test_security_report_exists(self):
        """Verify that SECURITY_REPORT.md exists at the repository root"""
        filepath = os.path.join(self.REPO_DIR, "SECURITY_REPORT.md")
        assert os.path.exists(filepath), (
            f"SECURITY_REPORT.md not found at {filepath}. "
            "A structured security report must be created."
        )

    def test_settings_file_exists(self):
        """Verify that the Django base settings file exists"""
        filepath = os.path.join(self.REPO_DIR, "babybuddy/settings/base.py")
        assert os.path.exists(filepath), f"base.py settings not found at {filepath}"

    def test_api_views_file_exists(self):
        """Verify that api/views.py exists"""
        filepath = os.path.join(self.REPO_DIR, "api/views.py")
        assert os.path.exists(filepath), f"api/views.py not found at {filepath}"

    # === Semantic Checks ===

    def test_security_report_has_required_sections(self):
        """Verify that SECURITY_REPORT.md contains required sections"""
        filepath = os.path.join(self.REPO_DIR, "SECURITY_REPORT.md")
        with open(filepath) as f:
            content = f.read().lower()

        required_sections = {
            "executive summary": "summary" in content or "executive" in content or "overview" in content,
            "findings": "finding" in content,
            "severity": "critical" in content or "high" in content or "medium" in content or "severity" in content,
        }
        missing = [s for s, found in required_sections.items() if not found]
        assert len(missing) == 0, (
            f"SECURITY_REPORT.md missing required sections: {missing}"
        )

    def test_security_report_has_minimum_findings(self):
        """Verify that SECURITY_REPORT.md contains at least 5 documented findings"""
        filepath = os.path.join(self.REPO_DIR, "SECURITY_REPORT.md")
        with open(filepath) as f:
            content = f.read()

        # Count findings by looking for numbered items, severity markers, or heading patterns
        severity_markers = re.findall(
            r'(?:critical|high|medium|low)\b', content, re.IGNORECASE
        )
        finding_headers = re.findall(
            r'(?:^|\n)\s*(?:#{1,4}\s+)?(?:finding|issue|vulnerability)\s*(?:\d+|:)',
            content, re.IGNORECASE
        )
        numbered_items = re.findall(r'\n\s*\d+\.\s+', content)

        findings_count = max(len(severity_markers) // 1, len(finding_headers), len(numbered_items))
        assert findings_count >= 5, (
            f"Expected at least 5 findings in SECURITY_REPORT.md, detected approximately {findings_count}. "
            "Report should cover authentication, authorization, input validation, security headers, "
            "secrets management, and rate limiting."
        )

    def test_secret_key_not_hardcoded(self):
        """Verify that SECRET_KEY is loaded from environment variable, not hardcoded"""
        filepath = os.path.join(self.REPO_DIR, "babybuddy/settings/base.py")
        with open(filepath) as f:
            content = f.read()

        # Check that SECRET_KEY uses os.environ, os.getenv, or env() pattern
        secret_key_lines = [
            line for line in content.split('\n')
            if 'SECRET_KEY' in line and not line.strip().startswith('#')
        ]
        assert len(secret_key_lines) > 0, "SECRET_KEY not found in settings file"

        has_env_loading = any(
            'os.environ' in line or 'os.getenv' in line or 'env(' in line
            or 'environ' in line or 'config(' in line
            for line in secret_key_lines
        )
        assert has_env_loading, (
            f"SECRET_KEY appears to be hardcoded. Found: {secret_key_lines}. "
            "SECRET_KEY must be loaded from an environment variable."
        )

    def test_session_cookie_httponly(self):
        """Verify that SESSION_COOKIE_HTTPONLY is set to True"""
        filepath = os.path.join(self.REPO_DIR, "babybuddy/settings/base.py")
        with open(filepath) as f:
            content = f.read()

        assert "SESSION_COOKIE_HTTPONLY" in content, (
            "SESSION_COOKIE_HTTPONLY not found in settings"
        )
        # Verify it's set to True
        match = re.search(r'SESSION_COOKIE_HTTPONLY\s*=\s*(True|False)', content)
        assert match is not None, "SESSION_COOKIE_HTTPONLY assignment not found"
        assert match.group(1) == "True", (
            f"SESSION_COOKIE_HTTPONLY should be True, found {match.group(1)}"
        )

    def test_x_frame_options_deny(self):
        """Verify that X_FRAME_OPTIONS is set to DENY"""
        filepath = os.path.join(self.REPO_DIR, "babybuddy/settings/base.py")
        with open(filepath) as f:
            content = f.read()

        assert "X_FRAME_OPTIONS" in content, "X_FRAME_OPTIONS not found in settings"
        match = re.search(r'X_FRAME_OPTIONS\s*=\s*["\'](\w+)["\']', content)
        assert match is not None, "X_FRAME_OPTIONS assignment not found"
        assert match.group(1).upper() == "DENY", (
            f"X_FRAME_OPTIONS should be 'DENY', found '{match.group(1)}'"
        )

    def test_secure_content_type_nosniff(self):
        """Verify that SECURE_CONTENT_TYPE_NOSNIFF is enabled"""
        filepath = os.path.join(self.REPO_DIR, "babybuddy/settings/base.py")
        with open(filepath) as f:
            content = f.read()

        assert "SECURE_CONTENT_TYPE_NOSNIFF" in content, (
            "SECURE_CONTENT_TYPE_NOSNIFF not found in settings"
        )
        match = re.search(r'SECURE_CONTENT_TYPE_NOSNIFF\s*=\s*(True|False)', content)
        assert match is not None, "SECURE_CONTENT_TYPE_NOSNIFF assignment not found"
        assert match.group(1) == "True", (
            f"SECURE_CONTENT_TYPE_NOSNIFF should be True, found {match.group(1)}"
        )

    def test_hsts_configuration(self):
        """Verify that SECURE_HSTS_SECONDS is set to at least 31536000"""
        filepath = os.path.join(self.REPO_DIR, "babybuddy/settings/base.py")
        with open(filepath) as f:
            content = f.read()

        match = re.search(r'SECURE_HSTS_SECONDS\s*=\s*(\d+)', content)
        assert match is not None, "SECURE_HSTS_SECONDS not found in settings"
        hsts_seconds = int(match.group(1))
        assert hsts_seconds >= 31536000, (
            f"SECURE_HSTS_SECONDS should be >= 31536000 (1 year), found {hsts_seconds}"
        )

    # === Functional Checks ===

    def test_api_views_require_authentication(self):
        """Verify that API viewsets enforce authentication via permission classes or defaults"""
        filepath = os.path.join(self.REPO_DIR, "api/views.py")
        with open(filepath) as f:
            content = f.read()

        # Check for authentication enforcement
        has_auth = (
            "IsAuthenticated" in content
            or "permission_classes" in content
            or "authentication_classes" in content
            or "DEFAULT_PERMISSION_CLASSES" in content
        )
        assert has_auth, (
            "api/views.py does not appear to enforce authentication. "
            "Expected IsAuthenticated or permission_classes configuration."
        )

    def test_rest_framework_default_permissions(self):
        """Verify that REST_FRAMEWORK default permission enforces authentication"""
        filepath = os.path.join(self.REPO_DIR, "babybuddy/settings/base.py")
        with open(filepath) as f:
            content = f.read()

        if "REST_FRAMEWORK" in content:
            # Check that DEFAULT_PERMISSION_CLASSES requires authentication
            has_default_auth = (
                "IsAuthenticated" in content
                and "DEFAULT_PERMISSION_CLASSES" in content
            )
            assert has_default_auth, (
                "REST_FRAMEWORK settings should include DEFAULT_PERMISSION_CLASSES "
                "with IsAuthenticated to enforce auth on all API endpoints."
            )

    def test_rate_limiting_configured(self):
        """Verify that rate limiting / throttle classes are configured"""
        filepath = os.path.join(self.REPO_DIR, "babybuddy/settings/base.py")
        with open(filepath) as f:
            content = f.read()

        has_throttle = (
            "DEFAULT_THROTTLE_CLASSES" in content
            or "DEFAULT_THROTTLE_RATES" in content
            or "throttle" in content.lower()
            or "RATELIMIT" in content
            or "ratelimit" in content
        )
        assert has_throttle, (
            "No rate limiting configuration found in settings. "
            "Expected DRF throttle classes or django-ratelimit configuration."
        )

    def test_no_raw_sql_with_string_interpolation(self):
        """Verify no raw SQL queries use string interpolation (potential SQL injection)"""
        python_dirs = [
            os.path.join(self.REPO_DIR, "api"),
            os.path.join(self.REPO_DIR, "core"),
            os.path.join(self.REPO_DIR, "babybuddy"),
        ]
        for dirpath in python_dirs:
            if not os.path.exists(dirpath):
                continue
            for root, _dirs, files in os.walk(dirpath):
                for fname in files:
                    if not fname.endswith(".py"):
                        continue
                    filepath = os.path.join(root, fname)
                    with open(filepath) as f:
                        content = f.read()
                    # Check for dangerous patterns
                    dangerous_patterns = [
                        (r'\.raw\s*\(\s*f["\']', "f-string in .raw() query"),
                        (r'\.raw\s*\(\s*["\'].*%s', "string interpolation in .raw() query"),
                        (r'\.extra\s*\(\s*.*f["\']', "f-string in .extra() call"),
                        (r'cursor\.execute\s*\(\s*f["\']', "f-string in cursor.execute()"),
                    ]
                    for pattern, desc in dangerous_patterns:
                        matches = re.findall(pattern, content)
                        assert len(matches) == 0, (
                            f"Found {desc} in {filepath}: potential SQL injection vulnerability"
                        )

    def test_no_unsafe_mark_safe_on_user_data(self):
        """Verify that mark_safe is not used on user-supplied data without sanitization"""
        python_dirs = [
            os.path.join(self.REPO_DIR, "core"),
            os.path.join(self.REPO_DIR, "babybuddy"),
        ]
        for dirpath in python_dirs:
            if not os.path.exists(dirpath):
                continue
            for root, _dirs, files in os.walk(dirpath):
                for fname in files:
                    if not fname.endswith(".py"):
                        continue
                    filepath = os.path.join(root, fname)
                    with open(filepath) as f:
                        content = f.read()
                    # Flag files using mark_safe - they should be reviewed
                    if "mark_safe" in content:
                        # Check it's not used with user input variables
                        lines_with_mark_safe = [
                            line.strip() for line in content.split('\n')
                            if 'mark_safe' in line and not line.strip().startswith('#')
                        ]
                        for line in lines_with_mark_safe:
                            # Check if mark_safe is applied to f-strings or format() with user data
                            if re.search(r'mark_safe\s*\(\s*f["\']', line):
                                pytest.fail(
                                    f"Found mark_safe with f-string in {filepath}: "
                                    f"'{line}' - potential XSS vulnerability"
                                )

    def test_serializers_have_field_validation(self):
        """Verify that DRF serializers define explicit field-level validation"""
        filepath = os.path.join(self.REPO_DIR, "api/serializers.py")
        if not os.path.exists(filepath):
            pytest.skip("api/serializers.py not found")

        with open(filepath) as f:
            content = f.read()

        # Check for validation patterns
        has_validation = (
            "max_length" in content
            or "min_value" in content
            or "max_value" in content
            or "validate_" in content
            or "validators" in content
            or "ValidationError" in content
        )
        assert has_validation, (
            "api/serializers.py does not contain field-level validation constraints. "
            "Expected max_length, min_value/max_value, or custom validate_ methods."
        )
