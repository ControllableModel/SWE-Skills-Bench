"""
Test skill: security-review
Verify that the Agent correctly hardens authentication, input validation,
session security, and rate limiting in the Baby Buddy Django application.
"""

import os
import re
import ast
import subprocess
import pytest


class TestSecurityReview:
    REPO_DIR = "/workspace/babybuddy"

    # === File Path Checks ===

    def test_settings_base_exists(self):
        """Verify base settings file exists"""
        fpath = os.path.join(self.REPO_DIR, "babybuddy/settings/base.py")
        assert os.path.isfile(fpath), f"Settings file not found at {fpath}"

    def test_middleware_file_exists(self):
        """Verify rate-limiting middleware file was created"""
        fpath = os.path.join(self.REPO_DIR, "babybuddy/middleware.py")
        assert os.path.isfile(fpath), f"Middleware file not found at {fpath}"

    def test_api_serializers_exists(self):
        """Verify API serializers file exists"""
        fpath = os.path.join(self.REPO_DIR, "api/serializers.py")
        assert os.path.isfile(fpath), f"API serializers not found at {fpath}"

    def test_core_forms_exists(self):
        """Verify core forms file exists"""
        fpath = os.path.join(self.REPO_DIR, "core/forms.py")
        assert os.path.isfile(fpath), f"Core forms not found at {fpath}"

    # === Semantic Checks ===

    def test_session_cookie_secure_setting(self):
        """Verify SESSION_COOKIE_SECURE is set to True"""
        fpath = os.path.join(self.REPO_DIR, "babybuddy/settings/base.py")
        with open(fpath, "r") as f:
            content = f.read()
        match = re.search(r'SESSION_COOKIE_SECURE\s*=\s*(True|False)', content)
        assert match is not None, "SESSION_COOKIE_SECURE not found in settings"
        assert match.group(1) == "True", (
            f"SESSION_COOKIE_SECURE should be True, found {match.group(1)}"
        )

    def test_session_cookie_httponly_setting(self):
        """Verify SESSION_COOKIE_HTTPONLY is set to True"""
        fpath = os.path.join(self.REPO_DIR, "babybuddy/settings/base.py")
        with open(fpath, "r") as f:
            content = f.read()
        match = re.search(r'SESSION_COOKIE_HTTPONLY\s*=\s*(True|False)', content)
        assert match is not None, "SESSION_COOKIE_HTTPONLY not found in settings"
        assert match.group(1) == "True", (
            f"SESSION_COOKIE_HTTPONLY should be True, found {match.group(1)}"
        )

    def test_session_cookie_samesite_setting(self):
        """Verify SESSION_COOKIE_SAMESITE is Lax or Strict"""
        fpath = os.path.join(self.REPO_DIR, "babybuddy/settings/base.py")
        with open(fpath, "r") as f:
            content = f.read()
        match = re.search(r'SESSION_COOKIE_SAMESITE\s*=\s*["\'](\w+)["\']', content)
        assert match is not None, "SESSION_COOKIE_SAMESITE not found in settings"
        value = match.group(1)
        assert value in ("Lax", "Strict"), (
            f"SESSION_COOKIE_SAMESITE should be 'Lax' or 'Strict', got '{value}'"
        )

    def test_csrf_cookie_httponly_setting(self):
        """Verify CSRF_COOKIE_HTTPONLY is set to True"""
        fpath = os.path.join(self.REPO_DIR, "babybuddy/settings/base.py")
        with open(fpath, "r") as f:
            content = f.read()
        match = re.search(r'CSRF_COOKIE_HTTPONLY\s*=\s*(True|False)', content)
        assert match is not None, "CSRF_COOKIE_HTTPONLY not found in settings"
        assert match.group(1) == "True", (
            f"CSRF_COOKIE_HTTPONLY should be True, found {match.group(1)}"
        )

    def test_x_frame_options_setting(self):
        """Verify X_FRAME_OPTIONS is DENY or SAMEORIGIN"""
        fpath = os.path.join(self.REPO_DIR, "babybuddy/settings/base.py")
        with open(fpath, "r") as f:
            content = f.read()
        match = re.search(r'X_FRAME_OPTIONS\s*=\s*["\'](\w+)["\']', content)
        assert match is not None, "X_FRAME_OPTIONS not found in settings"
        assert match.group(1) in ("DENY", "SAMEORIGIN"), (
            f"X_FRAME_OPTIONS should be 'DENY' or 'SAMEORIGIN', got '{match.group(1)}'"
        )

    def test_session_cookie_age_not_excessive(self):
        """Verify SESSION_COOKIE_AGE does not exceed 14 days (1209600 seconds)"""
        fpath = os.path.join(self.REPO_DIR, "babybuddy/settings/base.py")
        with open(fpath, "r") as f:
            content = f.read()
        match = re.search(r'SESSION_COOKIE_AGE\s*=\s*(\d+)', content)
        if match:
            age = int(match.group(1))
            assert age <= 1209600, (
                f"SESSION_COOKIE_AGE is {age}, should not exceed 1209600 (14 days)"
            )

    def test_middleware_has_rate_limiting_class(self):
        """Verify middleware.py contains a rate-limiting middleware class"""
        fpath = os.path.join(self.REPO_DIR, "babybuddy/middleware.py")
        with open(fpath, "r") as f:
            content = f.read()
        has_class = bool(re.search(r'class\s+\w*[Rr]ate\w*', content))
        has_429 = "429" in content or "HttpResponse" in content or "JsonResponse" in content
        assert has_class or has_429, (
            "middleware.py should contain a rate-limiting class that returns 429 responses"
        )

    def test_serializers_have_max_length_validation(self):
        """Verify API serializers enforce max_length on text fields"""
        fpath = os.path.join(self.REPO_DIR, "api/serializers.py")
        with open(fpath, "r") as f:
            content = f.read()
        has_max_length = bool(re.search(r'max_length\s*=\s*\d+', content))
        has_validators = bool(re.search(r'(validate|MaxLengthValidator|validators)', content))
        assert has_max_length or has_validators, (
            "Serializers should enforce max_length constraints on text fields"
        )

    def test_forms_have_input_validation(self):
        """Verify core forms have validation for date ordering and text constraints"""
        fpath = os.path.join(self.REPO_DIR, "core/forms.py")
        with open(fpath, "r") as f:
            content = f.read()
        has_clean = bool(re.search(r'def\s+clean', content))
        has_validation = bool(re.search(r'(ValidationError|validate|strip|start.*end|end.*start)', content))
        assert has_clean or has_validation, (
            "Core forms should have clean methods or validation for input constraints"
        )

    # === Functional Checks ===

    def test_middleware_is_importable(self):
        """Verify the middleware module can be imported without errors"""
        import sys
        sys.path.insert(0, self.REPO_DIR)
        try:
            import importlib
            spec = importlib.util.spec_from_file_location(
                "babybuddy.middleware",
                os.path.join(self.REPO_DIR, "babybuddy/middleware.py")
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        except Exception as e:
            pytest.fail(f"Failed to import middleware module: {e}")

    def test_middleware_has_rate_limit_config(self):
        """Verify middleware defines rate limit parameters (attempts and time window)"""
        fpath = os.path.join(self.REPO_DIR, "babybuddy/middleware.py")
        with open(fpath, "r") as f:
            content = f.read()
        # Should have numeric rate limit config
        has_limit = bool(re.search(r'(\d+)\s*(attempts|requests|limit|MAX|RATE)', content, re.IGNORECASE))
        has_window = bool(re.search(r'(\d+)\s*(seconds?|minutes?|window|PERIOD|TIMEOUT)', content, re.IGNORECASE))
        assert has_limit or has_window, (
            "Middleware should define rate limit parameters (max attempts and time window)"
        )

    def test_settings_security_middleware_configured(self):
        """Verify security-related middleware is in MIDDLEWARE setting"""
        fpath = os.path.join(self.REPO_DIR, "babybuddy/settings/base.py")
        with open(fpath, "r") as f:
            content = f.read()
        has_security_middleware = bool(
            re.search(r'SecurityMiddleware', content) or
            re.search(r'XFrameOptionsMiddleware', content)
        )
        assert has_security_middleware, (
            "MIDDLEWARE should include SecurityMiddleware or XFrameOptionsMiddleware"
        )

    def test_serializer_validates_time_range(self):
        """Verify serializers validate that start time is before end time"""
        fpath = os.path.join(self.REPO_DIR, "api/serializers.py")
        with open(fpath, "r") as f:
            content = f.read()
        has_time_validation = bool(re.search(
            r'(start.*end|end.*start|time.*range|validate.*start|validate.*end)',
            content,
            re.IGNORECASE | re.DOTALL
        ))
        assert has_time_validation, (
            "Serializers should validate that 'start' time is before 'end' time"
        )

    def test_serializer_validates_enum_fields(self):
        """Verify serializers validate enumerated fields like feeding method and diaper color"""
        fpath = os.path.join(self.REPO_DIR, "api/serializers.py")
        with open(fpath, "r") as f:
            content = f.read()
        has_choice_validation = bool(re.search(
            r'(choices|ChoiceField|validate_method|validate_color|breast.milk|formula|solid.food|black|brown|green|yellow)',
            content,
            re.IGNORECASE
        ))
        assert has_choice_validation, (
            "Serializers should validate enumerated fields (feeding method, diaper color)"
        )

    def test_forms_strip_whitespace(self):
        """Verify core forms strip leading/trailing whitespace from text inputs"""
        fpath = os.path.join(self.REPO_DIR, "core/forms.py")
        with open(fpath, "r") as f:
            content = f.read()
        has_strip = bool(re.search(r'\.strip\(\)', content))
        assert has_strip, "Core forms should strip whitespace from text inputs"

    def test_secure_browser_xss_filter_enabled(self):
        """Verify SECURE_BROWSER_XSS_FILTER is enabled"""
        fpath = os.path.join(self.REPO_DIR, "babybuddy/settings/base.py")
        with open(fpath, "r") as f:
            content = f.read()
        # Check for XSS filter setting or Content-Security-Policy headers
        has_xss = bool(re.search(r'SECURE_BROWSER_XSS_FILTER\s*=\s*True', content))
        has_csp = bool(re.search(r'(SECURE_CONTENT_TYPE_NOSNIFF|Content.Security.Policy)', content))
        assert has_xss or has_csp, (
            "SECURE_BROWSER_XSS_FILTER should be True or equivalent security headers configured"
        )
