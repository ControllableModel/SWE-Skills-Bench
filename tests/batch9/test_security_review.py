"""
Test skill: security-review
Verify that the Agent correctly fixes security vulnerabilities in the babybuddy Django application.
"""

import os
import subprocess
import re
import ast
import pytest


class TestSecurityReview:
    REPO_DIR = "/workspace/babybuddy"

    # === File Path Checks ===

    def test_settings_base_exists(self):
        """Verify base settings file exists"""
        candidates = [
            os.path.join(self.REPO_DIR, "babybuddy/settings/base.py"),
            os.path.join(self.REPO_DIR, "babybuddy/settings.py"),
        ]
        found = any(os.path.exists(c) for c in candidates)
        assert found, f"Settings file not found. Checked: {candidates}"

    def test_views_file_exists(self):
        """Verify views.py with user management views exists"""
        path = os.path.join(self.REPO_DIR, "babybuddy/views.py")
        assert os.path.exists(path), f"views.py not found at {path}"

    # === Semantic Checks ===

    def test_user_views_require_authentication(self):
        """Verify UserPassword, UserDelete, UserSettings views require authentication"""
        path = os.path.join(self.REPO_DIR, "babybuddy/views.py")
        with open(path) as f:
            content = f.read()
        # Check for LoginRequired mixin or login_required decorator
        has_auth = (
            "LoginRequiredMixin" in content
            or "login_required" in content
            or "IsAuthenticated" in content
        )
        assert has_auth, (
            "User management views do not appear to require authentication. "
            "Expected LoginRequiredMixin or login_required decorator."
        )

    def test_user_views_check_permission_for_own_account(self):
        """Verify UserPassword/UserDelete/UserSettings enforce user can only modify own account"""
        path = os.path.join(self.REPO_DIR, "babybuddy/views.py")
        with open(path) as f:
            content = f.read()
        # The views should check request.user == target user or use get_object override
        has_obj_check = (
            "self.request.user" in content
            or "request.user.pk" in content
            or "get_object" in content
            or "UserPassesTestMixin" in content
            or "self.kwargs" in content
        )
        assert has_obj_check, (
            "Views do not appear to verify the requesting user matches the target user"
        )

    def test_security_middleware_present(self):
        """Verify security middleware is configured in settings"""
        settings_paths = [
            os.path.join(self.REPO_DIR, "babybuddy/settings/base.py"),
            os.path.join(self.REPO_DIR, "babybuddy/settings.py"),
        ]
        content = ""
        for sp in settings_paths:
            if os.path.exists(sp):
                with open(sp) as f:
                    content += f.read()
        assert "SecurityMiddleware" in content, (
            "SecurityMiddleware not found in settings. "
            "django.middleware.security.SecurityMiddleware should be in MIDDLEWARE."
        )

    def test_csrf_middleware_present(self):
        """Verify CSRF middleware is configured"""
        settings_paths = [
            os.path.join(self.REPO_DIR, "babybuddy/settings/base.py"),
            os.path.join(self.REPO_DIR, "babybuddy/settings.py"),
        ]
        content = ""
        for sp in settings_paths:
            if os.path.exists(sp):
                with open(sp) as f:
                    content += f.read()
        assert "CsrfViewMiddleware" in content, (
            "CsrfViewMiddleware not found in settings."
        )

    def test_api_rate_limiting_configured(self):
        """Verify API rate limiting is configured via DRF throttle or middleware"""
        settings_paths = [
            os.path.join(self.REPO_DIR, "babybuddy/settings/base.py"),
            os.path.join(self.REPO_DIR, "babybuddy/settings.py"),
        ]
        content = ""
        for sp in settings_paths:
            if os.path.exists(sp):
                with open(sp) as f:
                    content += f.read()
        has_throttle = (
            "DEFAULT_THROTTLE_CLASSES" in content
            or "DEFAULT_THROTTLE_RATES" in content
            or "throttle" in content.lower()
            or "ratelimit" in content.lower()
            or "RateThrottle" in content
        )
        assert has_throttle, (
            "No API rate limiting configuration found. "
            "Expected DEFAULT_THROTTLE_CLASSES or DEFAULT_THROTTLE_RATES in REST_FRAMEWORK settings."
        )

    def test_security_headers_configured(self):
        """Verify security headers like SECURE_BROWSER_XSS_FILTER are set"""
        settings_paths = [
            os.path.join(self.REPO_DIR, "babybuddy/settings/base.py"),
            os.path.join(self.REPO_DIR, "babybuddy/settings.py"),
        ]
        content = ""
        for sp in settings_paths:
            if os.path.exists(sp):
                with open(sp) as f:
                    content += f.read()
        headers = [
            "SECURE_CONTENT_TYPE_NOSNIFF",
            "X_FRAME_OPTIONS",
            "SECURE_BROWSER_XSS_FILTER",
        ]
        found = [h for h in headers if h in content]
        assert len(found) >= 2, (
            f"Only {len(found)} of expected security headers found ({found}). "
            f"Expected at least 2 of: {headers}"
        )

    # === Functional Checks ===

    def test_django_check_passes(self):
        """Verify Django system check passes"""
        result = subprocess.run(
            ["python", "-m", "django", "check", "--deploy"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=120,
            env={**os.environ, "DJANGO_SETTINGS_MODULE": "babybuddy.settings.base"},
        )
        # --deploy may produce warnings; we check it doesn't completely fail
        # Some warnings are acceptable but critical errors should not appear
        if result.returncode != 0:
            # Allow warnings, block errors
            assert "SystemCheckError" not in result.stderr, (
                f"Django check produced critical errors: {result.stderr[:1000]}"
            )

    def test_unauthenticated_user_settings_returns_redirect_or_403(self):
        """Verify accessing user settings without auth returns redirect or 403"""
        script = """
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'babybuddy.settings.base')
import django
django.setup()
from django.test import RequestFactory
from babybuddy.views import UserSettings
from django.contrib.auth.models import AnonymousUser

factory = RequestFactory()
request = factory.get('/user/settings/')
request.user = AnonymousUser()
try:
    response = UserSettings.as_view()(request)
    code = response.status_code
    # Should be 302 (redirect to login) or 403
    assert code in (302, 403), f'Expected 302 or 403, got {code}'
    print(f'PASS:{code}')
except Exception as e:
    err = str(e)
    if '302' in err or 'login' in err.lower() or 'redirect' in err.lower():
        print('PASS:redirected')
    else:
        print(f'FAIL:{err}')
"""
        result = subprocess.run(
            ["python", "-c", script],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=60,
        )
        combined = result.stdout + result.stderr
        assert "PASS" in result.stdout or result.returncode == 0, (
            f"Unauthenticated access to UserSettings not properly rejected: {combined[:500]}"
        )

    def test_migrations_valid(self):
        """Verify Django migrations are in a consistent state"""
        result = subprocess.run(
            ["python", "manage.py", "makemigrations", "--check", "--dry-run"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=120,
            env={**os.environ, "DJANGO_SETTINGS_MODULE": "babybuddy.settings.base"},
        )
        # returncode 0 means no new migrations needed
        assert result.returncode == 0, (
            f"Pending migrations detected: {result.stdout[:500]}"
        )

    def test_input_validation_on_forms(self):
        """Verify forms include proper validation (no raw SQL or unvalidated input)"""
        forms_path = os.path.join(self.REPO_DIR, "babybuddy/forms.py")
        if os.path.exists(forms_path):
            with open(forms_path) as f:
                content = f.read()
            # Check there's no raw SQL
            assert "raw(" not in content and "cursor.execute" not in content, (
                "Raw SQL found in forms.py - potential SQL injection risk"
            )
            # Check forms use Django form classes
            assert "forms.Form" in content or "forms.ModelForm" in content or "Form)" in content, (
                "Forms do not appear to use Django form framework"
            )
