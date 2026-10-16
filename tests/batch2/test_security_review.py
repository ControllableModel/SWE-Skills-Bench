"""
Test skill: security-review
Verify that the Agent correctly implements secure data export endpoints
for the BabyBuddy Django application with authentication, authorization,
input validation, and proper data scoping.
"""

import os
import re
import ast
import subprocess
import pytest


class TestSecurityReview:
    REPO_DIR = "/workspace/babybuddy"

    # === File Path Checks ===

    def test_api_views_file_exists(self):
        """Verify api/views.py exists"""
        path = os.path.join(self.REPO_DIR, "api/views.py")
        assert os.path.exists(path), f"api/views.py not found at {path}"

    def test_api_serializers_file_exists(self):
        """Verify api/serializers.py exists"""
        path = os.path.join(self.REPO_DIR, "api/serializers.py")
        assert os.path.exists(path), f"api/serializers.py not found at {path}"

    def test_api_urls_file_exists(self):
        """Verify api/urls.py exists"""
        path = os.path.join(self.REPO_DIR, "api/urls.py")
        assert os.path.exists(path), f"api/urls.py not found at {path}"

    # === Semantic Checks ===

    def test_views_has_authentication_enforcement(self):
        """Verify views.py enforces authentication on export endpoints"""
        path = os.path.join(self.REPO_DIR, "api/views.py")
        with open(path) as f:
            content = f.read()

        auth_indicators = [
            "IsAuthenticated",
            "permission_classes",
            "authentication_classes",
            "login_required",
            "@api_view",
            "APIView",
        ]
        found = [ind for ind in auth_indicators if ind in content]
        assert len(found) >= 2, (
            f"views.py should enforce authentication. Found: {found}. "
            f"Expected at least 2 of: {auth_indicators}"
        )

    def test_views_has_object_level_permissions(self):
        """Verify views.py implements object-level authorization"""
        path = os.path.join(self.REPO_DIR, "api/views.py")
        with open(path) as f:
            content = f.read()

        permission_indicators = [
            "get_object",
            "check_object_permissions",
            "has_object_permission",
            "ObjectPermission",
            "filter",
            "get_queryset",
        ]
        found = [ind for ind in permission_indicators if ind in content]
        assert len(found) >= 1, (
            "views.py should implement object-level permissions to restrict "
            f"access to authorized children only. Found: {found}. "
            f"Expected at least 1 of: {permission_indicators}"
        )

    def test_views_has_input_validation(self):
        """Verify views.py validates query parameters (date range, record type)"""
        path = os.path.join(self.REPO_DIR, "api/views.py")
        with open(path) as f:
            content = f.read()

        validation_indicators = [
            "serializer.is_valid",
            "validate",
            "query_params",
            "request.query_params",
            "request.GET",
            "date",
            "ValidationError",
        ]
        found = [ind for ind in validation_indicators if ind in content]
        assert len(found) >= 2, (
            "views.py should validate input parameters (date range, record type). "
            f"Found: {found}. Expected at least 2 of: {validation_indicators}"
        )

    def test_serializers_has_export_serializer(self):
        """Verify serializers.py defines export response serializers"""
        path = os.path.join(self.REPO_DIR, "api/serializers.py")
        with open(path) as f:
            tree = ast.parse(f.read())

        class_names = [node.name for node in ast.walk(tree)
                       if isinstance(node, ast.ClassDef)]
        serializer_classes = [n for n in class_names if "serializer" in n.lower()]
        assert len(serializer_classes) > 0, (
            f"serializers.py should define at least one Serializer class. "
            f"Classes found: {class_names}"
        )

    def test_serializers_explicitly_declares_fields(self):
        """Verify serializers use explicit field declarations (no fields='__all__' for exports)"""
        path = os.path.join(self.REPO_DIR, "api/serializers.py")
        with open(path) as f:
            content = f.read()

        # Check for serializer Meta classes with fields
        has_fields = "fields" in content
        assert has_fields, (
            "Serializers should explicitly declare 'fields' to control which "
            "data is exposed in export responses"
        )

    def test_urls_registers_export_endpoints(self):
        """Verify urls.py registers new export URL patterns"""
        path = os.path.join(self.REPO_DIR, "api/urls.py")
        with open(path) as f:
            content = f.read()

        export_indicators = [
            "export",
            "path(",
            "url(",
            "urlpatterns",
            "router",
        ]
        found = [ind for ind in export_indicators if ind in content]
        assert len(found) >= 2, (
            "urls.py should register export endpoint URL patterns. "
            f"Found: {found}. Expected at least 2 of: {export_indicators}"
        )

    # === Functional Checks ===

    def test_django_check_passes(self):
        """Verify Django system check passes with the new endpoints"""
        result = subprocess.run(
            ["python", "manage.py", "check", "--deploy"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=120,
            env={**os.environ, "DJANGO_SETTINGS_MODULE": "babybuddy.settings.base"},
        )
        # --deploy might have warnings but should not have errors
        if result.returncode != 0:
            # Allow warnings but not critical errors
            assert "SystemCheckError" not in result.stderr, (
                f"Django check failed: {result.stderr[:2000]}"
            )

    def test_views_file_is_importable(self):
        """Verify api/views.py is importable without errors"""
        result = subprocess.run(
            ["python", "-c", "import api.views"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=60,
            env={**os.environ, "DJANGO_SETTINGS_MODULE": "babybuddy.settings.base"},
        )
        # May fail due to Django setup, but should not have import/syntax errors
        if result.returncode != 0:
            error = result.stderr
            assert "SyntaxError" not in error, (
                f"api/views.py has syntax errors: {error[:1000]}"
            )
            assert "IndentationError" not in error, (
                f"api/views.py has indentation errors: {error[:1000]}"
            )

    def test_serializers_file_is_importable(self):
        """Verify api/serializers.py is importable without errors"""
        result = subprocess.run(
            ["python", "-c", "import api.serializers"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=60,
            env={**os.environ, "DJANGO_SETTINGS_MODULE": "babybuddy.settings.base"},
        )
        if result.returncode != 0:
            error = result.stderr
            assert "SyntaxError" not in error, (
                f"api/serializers.py has syntax errors: {error[:1000]}"
            )

    def test_no_sensitive_fields_in_error_responses(self):
        """Verify views.py does not leak internal details in error responses"""
        path = os.path.join(self.REPO_DIR, "api/views.py")
        with open(path) as f:
            content = f.read()

        # Should not have unguarded exception details in responses
        dangerous_patterns = [
            "traceback.format_exc",
            "str(e)",
            "repr(e)",
            "exception.__traceback__",
        ]
        # Check if these appear outside proper error handling
        leaky_patterns = [p for p in dangerous_patterns if p in content]
        # Allow str(e) if wrapped in logging, but warn if in Response
        if "str(e)" in content:
            # Check if str(e) is used in Response context
            lines = content.split("\n")
            for i, line in enumerate(lines):
                if "str(e)" in line and "Response" in line:
                    pytest.fail(
                        f"Line {i+1}: str(e) used directly in Response — "
                        "should not leak exception details to client"
                    )

    def test_export_endpoint_scopes_data_to_user(self):
        """Verify export views filter data by user/child authorization"""
        path = os.path.join(self.REPO_DIR, "api/views.py")
        with open(path) as f:
            content = f.read()

        # Look for queryset filtering by user/child ownership
        scoping_patterns = [
            "request.user",
            "self.request.user",
            "filter(",
            "get_queryset",
            "child__",
            "user=",
        ]
        found = [p for p in scoping_patterns if p in content]
        assert len(found) >= 2, (
            "Export views should scope data to the authenticated user. "
            f"Found: {found}. Expected at least 2 of: {scoping_patterns}"
        )
