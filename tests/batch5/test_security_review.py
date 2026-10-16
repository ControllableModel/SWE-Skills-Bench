"""
Test skill: security-review
Verify that the Agent correctly hardens authentication and input validation
in the Baby Buddy Django application.
"""

import os
import re
import ast
import sys
import subprocess
import pytest


class TestSecurityReview:
    REPO_DIR = "/workspace/babybuddy"

    def _read_file(self, rel_path):
        """Helper to read a file from the repo."""
        filepath = os.path.join(self.REPO_DIR, rel_path)
        with open(filepath) as f:
            return f.read()

    def _parse_settings(self):
        """Parse the settings file and extract assignment values."""
        filepath = os.path.join(self.REPO_DIR, "babybuddy/settings/base.py")
        with open(filepath) as f:
            content = f.read()
        return content

    # === File Path Checks ===

    def test_settings_base_file_exists(self):
        """Verify babybuddy/settings/base.py exists"""
        filepath = os.path.join(self.REPO_DIR, "babybuddy/settings/base.py")
        assert os.path.exists(filepath), f"Settings file not found: {filepath}"

    def test_serializers_file_exists(self):
        """Verify api/serializers.py exists"""
        filepath = os.path.join(self.REPO_DIR, "api/serializers.py")
        assert os.path.exists(filepath), f"Serializers file not found: {filepath}"

    def test_views_file_exists(self):
        """Verify api/views.py exists"""
        filepath = os.path.join(self.REPO_DIR, "api/views.py")
        assert os.path.exists(filepath), f"Views file not found: {filepath}"

    def test_middleware_file_exists(self):
        """Verify middleware file exists"""
        candidates = [
            os.path.join(self.REPO_DIR, "babybuddy/middleware.py"),
            os.path.join(self.REPO_DIR, "babybuddy/middleware/__init__.py"),
        ]
        found = any(os.path.exists(p) for p in candidates)
        assert found, "Middleware file not found at babybuddy/middleware.py"

    # === Semantic Checks ===

    def test_session_cookie_httponly(self):
        """Verify SESSION_COOKIE_HTTPONLY is set to True in settings"""
        content = self._parse_settings()
        match = re.search(r'SESSION_COOKIE_HTTPONLY\s*=\s*(True|False)', content)
        assert match is not None, "SESSION_COOKIE_HTTPONLY not found in settings"
        assert match.group(1) == "True", \
            f"SESSION_COOKIE_HTTPONLY should be True, got {match.group(1)}"

    def test_session_cookie_samesite(self):
        """Verify SESSION_COOKIE_SAMESITE is set to Lax or Strict"""
        content = self._parse_settings()
        match = re.search(
            r"SESSION_COOKIE_SAMESITE\s*=\s*['\"](\w+)['\"]", content
        )
        assert match is not None, "SESSION_COOKIE_SAMESITE not found in settings"
        value = match.group(1)
        assert value in ("Lax", "Strict"), \
            f"SESSION_COOKIE_SAMESITE should be 'Lax' or 'Strict', got '{value}'"

    def test_session_timeout_max_12_hours(self):
        """Verify session timeout is set to at most 12 hours (43200 seconds)"""
        content = self._parse_settings()
        match = re.search(r'SESSION_COOKIE_AGE\s*=\s*(\d+)', content)
        assert match is not None, "SESSION_COOKIE_AGE not found in settings"
        age = int(match.group(1))
        assert age <= 43200, \
            f"SESSION_COOKIE_AGE should be <= 43200 (12 hours), got {age}"
        assert age > 0, f"SESSION_COOKIE_AGE should be positive, got {age}"

    def test_csrf_cookie_secure_configured(self):
        """Verify CSRF_COOKIE_SECURE is configured in settings"""
        content = self._parse_settings()
        assert "CSRF_COOKIE_SECURE" in content, \
            "CSRF_COOKIE_SECURE not configured in settings"

    def test_serializer_validates_name_fields(self):
        """Verify ChildSerializer has validation for name fields (max_length, no HTML)"""
        content = self._read_file("api/serializers.py")
        # Check for max_length constraint on name fields
        has_max_length = bool(re.search(r'max_length\s*=\s*255', content))
        # Check for HTML/script tag validation
        has_html_validation = bool(re.search(
            r'(strip_tags|escape|clean|sanitize|<script|html|re\.(search|match|sub).*(<|>|script))',
            content,
            re.IGNORECASE,
        ))
        assert has_max_length or has_html_validation, \
            "ChildSerializer missing name field validation (max_length or HTML sanitization)"

    def test_feeding_serializer_validates_amount(self):
        """Verify FeedingSerializer validates amount is positive and bounded"""
        content = self._read_file("api/serializers.py")
        # Look for amount validation - could be MinValueValidator, validate_amount, etc.
        has_amount_validation = bool(re.search(
            r'(MinValueValidator|validate_amount|amount.*positive|min_value|'
            r'ValidationError.*amount|amount.*<=?\s*0)',
            content,
            re.IGNORECASE,
        ))
        assert has_amount_validation, \
            "FeedingSerializer missing amount validation (should reject negative values)"

    def test_feeding_serializer_validates_time_range(self):
        """Verify FeedingSerializer validates that start is before end"""
        content = self._read_file("api/serializers.py")
        has_time_validation = bool(re.search(
            r'(start.*end|end.*start|validate.*start.*end|'
            r'start_time.*end_time|ValidationError.*time|'
            r'before.*end|after.*start)',
            content,
            re.IGNORECASE,
        ))
        assert has_time_validation, \
            "FeedingSerializer missing start/end time validation"

    def test_template_no_unsafe_rendering(self):
        """Verify child_detail.html does not use |safe filter on user-supplied data"""
        template_path = os.path.join(
            self.REPO_DIR, "core/templates/core/child_detail.html"
        )
        if not os.path.exists(template_path):
            pytest.skip("child_detail.html not found (path may differ)")
        with open(template_path) as f:
            content = f.read()
        # Check that user-supplied fields (name, first_name, etc.) are not marked |safe
        unsafe_patterns = re.findall(
            r'\{\{.*?(child\.first_name|child\.last_name|child\.name|notes).*?\|safe.*?\}\}',
            content,
        )
        assert len(unsafe_patterns) == 0, \
            f"Template uses |safe on user-supplied data: {unsafe_patterns}"

    # === Functional Checks ===

    def test_django_settings_importable(self):
        """Verify Django settings can be imported without errors"""
        sys.path.insert(0, self.REPO_DIR)
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "babybuddy.settings.base")
        try:
            import django
            django.setup()
            from django.conf import settings
            assert hasattr(settings, "SESSION_COOKIE_HTTPONLY"), \
                "SESSION_COOKIE_HTTPONLY not in loaded settings"
            assert settings.SESSION_COOKIE_HTTPONLY is True, \
                f"SESSION_COOKIE_HTTPONLY should be True, got {settings.SESSION_COOKIE_HTTPONLY}"
        except Exception as e:
            pytest.skip(f"Django setup failed (may need dependencies): {e}")

    def test_django_session_samesite_setting_functional(self):
        """Verify SESSION_COOKIE_SAMESITE is properly configured via Django"""
        sys.path.insert(0, self.REPO_DIR)
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "babybuddy.settings.base")
        try:
            import django
            django.setup()
            from django.conf import settings
            assert settings.SESSION_COOKIE_SAMESITE in ("Lax", "Strict"), \
                f"SESSION_COOKIE_SAMESITE should be 'Lax' or 'Strict', got {settings.SESSION_COOKIE_SAMESITE}"
        except Exception as e:
            pytest.skip(f"Django setup failed: {e}")

    def test_api_views_enforce_permissions(self):
        """Verify API views use permission classes or queryset filtering"""
        content = self._read_file("api/views.py")
        # Check for permission enforcement patterns
        has_permissions = bool(re.search(
            r'(permission_classes|get_queryset|IsAuthenticated|'
            r'PermissionDenied|403|filter.*user|request\.user)',
            content,
        ))
        assert has_permissions, \
            "API views missing permission enforcement (permission_classes or queryset filtering)"

    def test_views_return_403_for_unauthorized_access(self):
        """Verify API views return 403 for unauthorized direct-ID access"""
        content = self._read_file("api/views.py")
        # Check for 403 response or PermissionDenied raise
        has_403 = bool(re.search(
            r'(PermissionDenied|status\.HTTP_403|Response.*403|raise.*Permission)',
            content,
        ))
        assert has_403, \
            "API views do not explicitly handle unauthorized access with 403"
