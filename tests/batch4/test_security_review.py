"""
Test skill: security-review
Verify that security hardening has been correctly applied to the Baby Buddy
Django application, including session/CSRF cookie settings, input validation,
rate limiting middleware, error response sanitization, and data scoping.
"""

import os
import re
import ast
import json
import subprocess
import pytest


class TestSecurityReview:
    REPO_DIR = "/workspace/babybuddy"

    # === File Path Checks ===

    def test_base_settings_file_exists(self):
        """Verify that the base settings file exists at the expected path"""
        filepath = os.path.join(self.REPO_DIR, "babybuddy/settings/base.py")
        assert os.path.exists(filepath), f"Base settings not found at {filepath}"

    def test_middleware_file_created(self):
        """Verify that the rate-limiting middleware file was created"""
        filepath = os.path.join(self.REPO_DIR, "babybuddy/middleware.py")
        assert os.path.exists(filepath), f"Middleware file not found at {filepath}"

    def test_api_views_file_exists(self):
        """Verify that api/views.py exists"""
        filepath = os.path.join(self.REPO_DIR, "api/views.py")
        assert os.path.exists(filepath), f"API views not found at {filepath}"

    def test_api_serializers_file_exists(self):
        """Verify that api/serializers.py exists"""
        filepath = os.path.join(self.REPO_DIR, "api/serializers.py")
        assert os.path.exists(filepath), f"API serializers not found at {filepath}"

    # === Semantic Checks ===

    def test_session_cookie_httponly_enabled(self):
        """Verify SESSION_COOKIE_HTTPONLY is set to True in base settings"""
        filepath = os.path.join(self.REPO_DIR, "babybuddy/settings/base.py")
        with open(filepath) as f:
            content = f.read()
        match = re.search(r'SESSION_COOKIE_HTTPONLY\s*=\s*(True|False)', content)
        assert match is not None, "SESSION_COOKIE_HTTPONLY not found in base settings"
        assert match.group(1) == "True", \
            f"SESSION_COOKIE_HTTPONLY should be True, found {match.group(1)}"

    def test_session_cookie_secure_enabled(self):
        """Verify SESSION_COOKIE_SECURE is set to True in base settings"""
        filepath = os.path.join(self.REPO_DIR, "babybuddy/settings/base.py")
        with open(filepath) as f:
            content = f.read()
        match = re.search(r'SESSION_COOKIE_SECURE\s*=\s*(True|False)', content)
        assert match is not None, "SESSION_COOKIE_SECURE not found in base settings"
        assert match.group(1) == "True", \
            f"SESSION_COOKIE_SECURE should be True, found {match.group(1)}"

    def test_session_cookie_samesite_configured(self):
        """Verify SESSION_COOKIE_SAMESITE is set to 'Lax' or 'Strict'"""
        filepath = os.path.join(self.REPO_DIR, "babybuddy/settings/base.py")
        with open(filepath) as f:
            content = f.read()
        match = re.search(r'SESSION_COOKIE_SAMESITE\s*=\s*["\'](\w+)["\']', content)
        assert match is not None, "SESSION_COOKIE_SAMESITE not found in base settings"
        value = match.group(1)
        assert value in ("Lax", "Strict"), \
            f"SESSION_COOKIE_SAMESITE should be 'Lax' or 'Strict', got '{value}'"

    def test_csrf_cookie_secure_enabled(self):
        """Verify CSRF_COOKIE_SECURE is set to True in base settings"""
        filepath = os.path.join(self.REPO_DIR, "babybuddy/settings/base.py")
        with open(filepath) as f:
            content = f.read()
        match = re.search(r'CSRF_COOKIE_SECURE\s*=\s*(True|False)', content)
        assert match is not None, "CSRF_COOKIE_SECURE not found in base settings"
        assert match.group(1) == "True", \
            f"CSRF_COOKIE_SECURE should be True, found {match.group(1)}"

    def test_debug_not_true_in_base_settings(self):
        """Verify that DEBUG is not set to True in base settings"""
        filepath = os.path.join(self.REPO_DIR, "babybuddy/settings/base.py")
        with open(filepath) as f:
            content = f.read()
        debug_true = re.search(r'^\s*DEBUG\s*=\s*True\s*$', content, re.MULTILINE)
        assert debug_true is None, \
            "DEBUG = True found in base settings; this must not be present in production"

    def test_serializers_enforce_max_length_on_strings(self):
        """Verify that API serializer string fields have max_length constraints"""
        filepath = os.path.join(self.REPO_DIR, "api/serializers.py")
        with open(filepath) as f:
            content = f.read()
        assert "max_length" in content, \
            "API serializers should enforce max_length on string fields"
        # Verify a specific reasonable limit (notes ≤ 1024)
        max_length_values = [int(m) for m in re.findall(r'max_length\s*=\s*(\d+)', content)]
        assert len(max_length_values) > 0, "No max_length values found in serializers"
        assert any(v <= 1024 for v in max_length_values), \
            f"max_length values {max_length_values} should include limits ≤ 1024 for text fields"

    def test_serializers_enforce_numeric_bounds(self):
        """Verify that numeric fields have min_value and max_value constraints"""
        filepath = os.path.join(self.REPO_DIR, "api/serializers.py")
        with open(filepath) as f:
            content = f.read()
        assert "min_value" in content, \
            "API serializers should enforce min_value on numeric fields"
        assert "max_value" in content, \
            "API serializers should enforce max_value on numeric fields"

    def test_middleware_implements_rate_limiting(self):
        """Verify that middleware has rate-limiting logic with 429 response and Retry-After"""
        filepath = os.path.join(self.REPO_DIR, "babybuddy/middleware.py")
        with open(filepath) as f:
            content = f.read()
        has_rate_limit = (
            "429" in content or
            "Too Many Requests" in content or
            "rate" in content.lower() or
            "throttle" in content.lower()
        )
        assert has_rate_limit, \
            "Middleware should implement rate limiting (HTTP 429)"
        has_retry_after = (
            "Retry-After" in content or
            "retry_after" in content or
            "retry-after" in content.lower()
        )
        assert has_retry_after, \
            "Rate-limiting middleware should set Retry-After header"

    def test_middleware_is_syntactically_valid(self):
        """Verify that babybuddy/middleware.py is valid Python"""
        filepath = os.path.join(self.REPO_DIR, "babybuddy/middleware.py")
        with open(filepath) as f:
            content = f.read()
        try:
            ast.parse(content)
        except SyntaxError as e:
            pytest.fail(f"Syntax error in middleware.py: {e}")

    # === Functional Checks ===

    def test_middleware_has_django_middleware_interface(self):
        """Verify that middleware implements proper Django middleware interface"""
        filepath = os.path.join(self.REPO_DIR, "babybuddy/middleware.py")
        with open(filepath) as f:
            content = f.read()
        tree = ast.parse(content)

        # Collect all class definitions and their methods
        has_middleware_class = False
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                methods = [n.name for n in ast.walk(node)
                           if isinstance(n, ast.FunctionDef)]
                if ("__call__" in methods or
                    "__init__" in methods or
                    "process_request" in methods or
                    "process_view" in methods):
                    has_middleware_class = True
                    break

        # Also check for function-based middleware (get_response pattern)
        has_func_middleware = False
        if not has_middleware_class:
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    source_segment = ast.get_source_segment(content, node) or ""
                    if "get_response" in source_segment:
                        has_func_middleware = True
                        break

        assert has_middleware_class or has_func_middleware, \
            "Middleware should implement Django middleware interface " \
            "(class with __call__/__init__ or function-based with get_response)"

    def test_settings_can_be_parsed_as_python(self):
        """Verify that base settings file is valid Python (no syntax errors from edits)"""
        filepath = os.path.join(self.REPO_DIR, "babybuddy/settings/base.py")
        with open(filepath) as f:
            content = f.read()
        try:
            ast.parse(content)
        except SyntaxError as e:
            pytest.fail(f"base.py has syntax error: {e}")

    def test_core_views_no_traceback_exposure(self):
        """Verify that core/views.py does not expose tracebacks in error responses"""
        filepath = os.path.join(self.REPO_DIR, "core/views.py")
        if not os.path.exists(filepath):
            pytest.skip("core/views.py not found")
        with open(filepath) as f:
            content = f.read()
        # Check for dangerous patterns: traceback in response body
        has_traceback_in_response = bool(re.search(
            r'traceback\.format_exc\(\).*(?:Response|JsonResponse|HttpResponse)',
            content, re.DOTALL
        ))
        assert not has_traceback_in_response, \
            "core/views.py should not include traceback content in HTTP responses"
        # Should have generic error messages
        has_generic_message = (
            "unexpected error" in content.lower() or
            "internal server error" in content.lower() or
            "an error occurred" in content.lower() or
            "generic" in content.lower()
        )
        assert has_generic_message, \
            "Error handlers in core/views.py should return generic error messages"

    def test_api_views_valid_python(self):
        """Verify that api/views.py is syntactically valid Python"""
        filepath = os.path.join(self.REPO_DIR, "api/views.py")
        with open(filepath) as f:
            content = f.read()
        try:
            ast.parse(content)
        except SyntaxError as e:
            pytest.fail(f"api/views.py has syntax error: {e}")

    def test_django_settings_load_with_security_options(self):
        """Verify that Django settings load correctly and contain security configurations"""
        result = subprocess.run(
            ["python", "-c",
             "import os; os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'babybuddy.settings.base'); "
             "import django; django.setup(); "
             "from django.conf import settings; "
             "import json; print(json.dumps({"
             "'SESSION_COOKIE_HTTPONLY': getattr(settings, 'SESSION_COOKIE_HTTPONLY', None),"
             "'SESSION_COOKIE_SECURE': getattr(settings, 'SESSION_COOKIE_SECURE', None),"
             "'CSRF_COOKIE_SECURE': getattr(settings, 'CSRF_COOKIE_SECURE', None),"
             "'SESSION_COOKIE_SAMESITE': getattr(settings, 'SESSION_COOKIE_SAMESITE', None),"
             "}))"],
            cwd=self.REPO_DIR,
            capture_output=True, text=True, timeout=60,
            env={**os.environ, "PYTHONPATH": self.REPO_DIR}
        )
        if result.returncode != 0:
            # Settings may fail due to missing DB or dependencies
            assert "SyntaxError" not in result.stderr, \
                f"Settings have syntax errors: {result.stderr[:500]}"
            pytest.skip(f"Could not load Django settings: {result.stderr[:300]}")

        data = json.loads(result.stdout.strip())
        assert data["SESSION_COOKIE_HTTPONLY"] is True, \
            f"SESSION_COOKIE_HTTPONLY should be True, got {data['SESSION_COOKIE_HTTPONLY']}"
        assert data["SESSION_COOKIE_SECURE"] is True, \
            f"SESSION_COOKIE_SECURE should be True, got {data['SESSION_COOKIE_SECURE']}"
        assert data["CSRF_COOKIE_SECURE"] is True, \
            f"CSRF_COOKIE_SECURE should be True, got {data['CSRF_COOKIE_SECURE']}"
        assert data["SESSION_COOKIE_SAMESITE"] in ("Lax", "Strict"), \
            f"SESSION_COOKIE_SAMESITE should be 'Lax' or 'Strict', got {data['SESSION_COOKIE_SAMESITE']}"

    def test_rate_limit_thresholds_in_middleware(self):
        """Verify that rate limit thresholds match spec: 10/min for login, 60/min for data"""
        filepath = os.path.join(self.REPO_DIR, "babybuddy/middleware.py")
        with open(filepath) as f:
            content = f.read()
        # Check for numeric thresholds
        numbers = re.findall(r'\b(\d+)\b', content)
        numbers_int = [int(n) for n in numbers]
        # Should contain threshold of 10 (login rate limit)
        has_login_limit = 10 in numbers_int
        # Should contain threshold of 60 (data mutation rate limit)
        has_data_limit = 60 in numbers_int
        assert has_login_limit, \
            "Middleware should define login rate limit of 10 requests per minute"
        assert has_data_limit, \
            "Middleware should define data-mutation rate limit of 60 requests per minute"
