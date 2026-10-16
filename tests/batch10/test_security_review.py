"""
Test skill: security-review
Verify that the Agent correctly performs security review and remediation
on the Baby Buddy Django application.
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
        """Verify that babybuddy/settings/base.py exists"""
        path = os.path.join(self.REPO_DIR, "babybuddy/settings/base.py")
        assert os.path.exists(path), f"Settings file not found at {path}"

    def test_api_views_exists(self):
        """Verify that api/views.py exists"""
        path = os.path.join(self.REPO_DIR, "api/views.py")
        assert os.path.exists(path), f"API views not found at {path}"

    def test_settings_base_is_valid_python(self):
        """Verify that base.py is syntactically valid Python"""
        path = os.path.join(self.REPO_DIR, "babybuddy/settings/base.py")
        with open(path) as f:
            source = f.read()
        try:
            ast.parse(source)
        except SyntaxError as e:
            pytest.fail(f"base.py has syntax errors: {e}")

    # === Semantic Checks: Secret Management ===

    def test_secret_key_not_hardcoded(self):
        """Verify SECRET_KEY is not a hardcoded string literal in settings"""
        path = os.path.join(self.REPO_DIR, "babybuddy/settings/base.py")
        with open(path) as f:
            content = f.read()
        # Parse AST to find SECRET_KEY assignments
        tree = ast.parse(content)
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "SECRET_KEY":
                        # The value should NOT be a string constant
                        assert not isinstance(node.value, ast.Constant) or not isinstance(node.value.value, str), (
                            "SECRET_KEY is hardcoded as a string literal. "
                            "It should be loaded from environment variable DJANGO_SECRET_KEY."
                        )

    def test_secret_key_loaded_from_env(self):
        """Verify SECRET_KEY references environment variable DJANGO_SECRET_KEY"""
        path = os.path.join(self.REPO_DIR, "babybuddy/settings/base.py")
        with open(path) as f:
            content = f.read()
        assert "DJANGO_SECRET_KEY" in content, (
            "Settings should load SECRET_KEY from DJANGO_SECRET_KEY environment variable"
        )
        # Verify os.environ or os.getenv is used
        uses_env = (
            "os.environ" in content
            or "os.getenv" in content
            or "environ.get" in content
            or "environ[" in content
            or "config(" in content  # django-environ pattern
            or "env(" in content  # django-environ pattern
        )
        assert uses_env, (
            "SECRET_KEY should be read from environment using os.environ, os.getenv, or similar"
        )

    def test_improperly_configured_on_missing_secret(self):
        """Verify that missing DJANGO_SECRET_KEY raises ImproperlyConfigured"""
        path = os.path.join(self.REPO_DIR, "babybuddy/settings/base.py")
        with open(path) as f:
            content = f.read()
        assert "ImproperlyConfigured" in content, (
            "Settings should raise ImproperlyConfigured when DJANGO_SECRET_KEY is absent"
        )

    # === Semantic Checks: Security Settings ===

    def test_session_cookie_httponly_set(self):
        """Verify SESSION_COOKIE_HTTPONLY is set to True"""
        path = os.path.join(self.REPO_DIR, "babybuddy/settings/base.py")
        with open(path) as f:
            content = f.read()
        assert "SESSION_COOKIE_HTTPONLY" in content, "Missing SESSION_COOKIE_HTTPONLY setting"
        match = re.search(r'SESSION_COOKIE_HTTPONLY\s*=\s*(True|False)', content)
        assert match is not None, "SESSION_COOKIE_HTTPONLY assignment not found"
        assert match.group(1) == "True", (
            f"SESSION_COOKIE_HTTPONLY should be True, found {match.group(1)}"
        )

    def test_csrf_cookie_httponly_set(self):
        """Verify CSRF_COOKIE_HTTPONLY is set to True"""
        path = os.path.join(self.REPO_DIR, "babybuddy/settings/base.py")
        with open(path) as f:
            content = f.read()
        assert "CSRF_COOKIE_HTTPONLY" in content, "Missing CSRF_COOKIE_HTTPONLY setting"
        match = re.search(r'CSRF_COOKIE_HTTPONLY\s*=\s*(True|False)', content)
        assert match is not None, "CSRF_COOKIE_HTTPONLY assignment not found"
        assert match.group(1) == "True", (
            f"CSRF_COOKIE_HTTPONLY should be True, found {match.group(1)}"
        )

    def test_secure_browser_xss_filter_set(self):
        """Verify SECURE_BROWSER_XSS_FILTER is set to True"""
        path = os.path.join(self.REPO_DIR, "babybuddy/settings/base.py")
        with open(path) as f:
            content = f.read()
        assert "SECURE_BROWSER_XSS_FILTER" in content, "Missing SECURE_BROWSER_XSS_FILTER setting"
        match = re.search(r'SECURE_BROWSER_XSS_FILTER\s*=\s*(True|False)', content)
        assert match is not None, "SECURE_BROWSER_XSS_FILTER assignment not found"
        assert match.group(1) == "True", (
            f"SECURE_BROWSER_XSS_FILTER should be True, found {match.group(1)}"
        )

    def test_secure_content_type_nosniff_set(self):
        """Verify SECURE_CONTENT_TYPE_NOSNIFF is set to True"""
        path = os.path.join(self.REPO_DIR, "babybuddy/settings/base.py")
        with open(path) as f:
            content = f.read()
        assert "SECURE_CONTENT_TYPE_NOSNIFF" in content, "Missing SECURE_CONTENT_TYPE_NOSNIFF setting"
        match = re.search(r'SECURE_CONTENT_TYPE_NOSNIFF\s*=\s*(True|False)', content)
        assert match is not None, "SECURE_CONTENT_TYPE_NOSNIFF assignment not found"
        assert match.group(1) == "True", (
            f"SECURE_CONTENT_TYPE_NOSNIFF should be True, found {match.group(1)}"
        )

    def test_x_frame_options_deny(self):
        """Verify X_FRAME_OPTIONS is set to 'DENY'"""
        path = os.path.join(self.REPO_DIR, "babybuddy/settings/base.py")
        with open(path) as f:
            content = f.read()
        assert "X_FRAME_OPTIONS" in content, "Missing X_FRAME_OPTIONS setting"
        match = re.search(r'X_FRAME_OPTIONS\s*=\s*["\'](\w+)["\']', content)
        assert match is not None, "X_FRAME_OPTIONS assignment not found"
        assert match.group(1) == "DENY", (
            f"X_FRAME_OPTIONS should be 'DENY', found '{match.group(1)}'"
        )

    # === Semantic Checks: SQL Injection Prevention ===

    def test_no_raw_sql_with_string_formatting(self):
        """Verify no raw SQL uses string formatting with user input"""
        files_to_check = [
            "core/models.py",
            "api/views.py",
        ]
        violations = []
        for rel_path in files_to_check:
            fpath = os.path.join(self.REPO_DIR, rel_path)
            if not os.path.exists(fpath):
                continue
            with open(fpath) as f:
                content = f.read()
            # Check for .raw() or .extra() with f-strings or .format()
            # Pattern: .raw(f"...) or .raw("...".format( or .raw("..." %
            if re.search(r'\.raw\s*\(\s*f["\']', content):
                violations.append(f"{rel_path}: .raw() with f-string")
            if re.search(r'\.raw\s*\([^)]*\.format\s*\(', content):
                violations.append(f"{rel_path}: .raw() with .format()")
            if re.search(r'\.extra\s*\(\s*.*f["\']', content):
                violations.append(f"{rel_path}: .extra() with f-string")
        assert len(violations) == 0, (
            f"SQL injection risks found: {violations}"
        )

    # === Semantic Checks: XSS Prevention ===

    def test_template_tags_no_unescaped_mark_safe(self):
        """Verify custom template tags don't pass user-controlled data to mark_safe unescaped"""
        tags_path = os.path.join(self.REPO_DIR, "dashboard/templatetags/dashboard_tags.py")
        if not os.path.exists(tags_path):
            pytest.skip("dashboard_tags.py not found")
        with open(tags_path) as f:
            content = f.read()
        # If mark_safe is used, django.utils.html.escape should also be present
        if "mark_safe" in content:
            has_escape = "escape" in content or "format_html" in content or "conditional_escape" in content
            assert has_escape, (
                "dashboard_tags.py uses mark_safe but does not import escape/format_html. "
                "User-controlled content must be escaped before mark_safe."
            )

    # === Functional Checks ===

    def test_settings_raise_on_missing_secret_key(self):
        """Verify that importing settings without DJANGO_SECRET_KEY raises ImproperlyConfigured"""
        result = subprocess.run(
            [
                "python", "-c",
                "import os; "
                "os.environ.pop('DJANGO_SECRET_KEY', None); "
                "os.environ.pop('SECRET_KEY', None); "
                "os.environ['DJANGO_SETTINGS_MODULE'] = 'babybuddy.settings.base'; "
                "from django.conf import settings; "
                "try:\n"
                "    _ = settings.SECRET_KEY\n"
                "    print('NO_ERROR')\n"
                "except Exception as e:\n"
                "    print(f'ERROR:{type(e).__name__}:{e}')\n"
            ],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=30,
        )
        output = result.stdout.strip()
        # We expect an error related to ImproperlyConfigured
        assert "NO_ERROR" not in output or "ImproperlyConfigured" in output, (
            f"Expected ImproperlyConfigured when DJANGO_SECRET_KEY is missing, got: {output}"
        )

    def test_api_views_require_authentication(self):
        """Verify API views have authentication requirements"""
        path = os.path.join(self.REPO_DIR, "api/views.py")
        with open(path) as f:
            content = f.read()
        auth_patterns = [
            "IsAuthenticated",
            "login_required",
            "LoginRequiredMixin",
            "permission_classes",
            "authentication_classes",
        ]
        has_auth = any(pattern in content for pattern in auth_patterns)
        assert has_auth, (
            "api/views.py does not appear to enforce authentication. "
            "Expected IsAuthenticated, login_required, or similar."
        )

    def test_core_views_require_authentication(self):
        """Verify core views require authentication for data access"""
        path = os.path.join(self.REPO_DIR, "core/views.py")
        if not os.path.exists(path):
            pytest.skip("core/views.py not found")
        with open(path) as f:
            content = f.read()
        auth_patterns = [
            "LoginRequiredMixin",
            "login_required",
            "IsAuthenticated",
            "PermissionRequiredMixin",
            "@method_decorator(login_required",
        ]
        has_auth = any(pattern in content for pattern in auth_patterns)
        assert has_auth, (
            "core/views.py does not appear to enforce authentication. "
            "Expected LoginRequiredMixin, login_required, or similar."
        )

    def test_serializers_have_field_validation(self):
        """Verify API serializers enforce field-level validation constraints"""
        path = os.path.join(self.REPO_DIR, "api/serializers.py")
        if not os.path.exists(path):
            pytest.skip("api/serializers.py not found")
        with open(path) as f:
            content = f.read()
        # Check for max_length or validate_ methods
        has_validation = (
            "max_length" in content
            or "def validate_" in content
            or "MaxLengthValidator" in content
            or "validators=" in content
            or "validators =" in content
        )
        assert has_validation, (
            "api/serializers.py does not appear to enforce field-level validation. "
            "Expected max_length constraints or validate_ methods."
        )

    def test_no_hardcoded_secrets_in_codebase(self):
        """Verify no hardcoded secrets (API keys, passwords) in settings files"""
        settings_dir = os.path.join(self.REPO_DIR, "babybuddy/settings")
        if not os.path.isdir(settings_dir):
            pytest.skip("Settings directory not found")

        secret_patterns = [
            r"(?i)password\s*=\s*['\"][^'\"]{8,}['\"]",
            r"(?i)api_key\s*=\s*['\"][^'\"]{8,}['\"]",
            r"(?i)token\s*=\s*['\"][^'\"]{8,}['\"]",
        ]
        violations = []
        for fname in os.listdir(settings_dir):
            if fname.endswith('.py'):
                fpath = os.path.join(settings_dir, fname)
                with open(fpath) as f:
                    content = f.read()
                for pattern in secret_patterns:
                    matches = re.findall(pattern, content)
                    if matches:
                        violations.append(f"{fname}: {matches[:2]}")
        assert len(violations) == 0, (
            f"Potential hardcoded secrets found in settings: {violations}"
        )
