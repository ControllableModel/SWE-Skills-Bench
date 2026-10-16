"""
Test skill: django-patterns
Verify that the Agent correctly implements a low-stock alert feature
in Saleor including Django models, DRF serializers, REST views,
URL routing, duplicate-alert prevention, and acknowledging alerts.
"""

import os
import re
import subprocess
import pytest


class TestDjangoPatterns:
    REPO_DIR = "/workspace/saleor"

    # === File Path Checks ===

    def test_models_file_exists(self):
        """Verify saleor/warehouse/models.py exists"""
        path = os.path.join(self.REPO_DIR, "saleor/warehouse/models.py")
        assert os.path.exists(path), f"models.py not found at {path}"

    def test_views_file_exists(self):
        """Verify saleor/warehouse/views.py was created"""
        path = os.path.join(self.REPO_DIR, "saleor/warehouse/views.py")
        assert os.path.exists(path), f"views.py not found at {path}"

    def test_serializers_file_exists(self):
        """Verify saleor/warehouse/serializers.py was created"""
        path = os.path.join(self.REPO_DIR, "saleor/warehouse/serializers.py")
        assert os.path.exists(path), f"serializers.py not found at {path}"

    def test_urls_file_exists(self):
        """Verify saleor/warehouse/urls.py was created"""
        path = os.path.join(self.REPO_DIR, "saleor/warehouse/urls.py")
        assert os.path.exists(path), f"urls.py not found at {path}"

    # === Semantic Checks ===

    def test_stock_alert_model_defined(self):
        """Verify StockAlert model is defined with required fields"""
        path = os.path.join(self.REPO_DIR, "saleor/warehouse/models.py")
        with open(path) as f:
            content = f.read()

        assert re.search(r"class\s+StockAlert", content), (
            "StockAlert model class not found"
        )
        required_concepts = ["threshold", "stock", "timestamp", "resolved"]
        found = [c for c in required_concepts if c in content.lower()]
        assert len(found) >= 3, (
            f"StockAlert should have threshold/stock/timestamp/resolved fields. "
            f"Found references: {found}"
        )

    def test_stock_alert_config_model_defined(self):
        """Verify StockAlertConfig model links variant to threshold"""
        path = os.path.join(self.REPO_DIR, "saleor/warehouse/models.py")
        with open(path) as f:
            content = f.read()

        assert re.search(r"class\s+StockAlertConfig", content), (
            "StockAlertConfig model class not found"
        )
        assert "threshold" in content.lower(), (
            "StockAlertConfig should include a threshold field"
        )
        assert "variant" in content.lower() or "product" in content.lower(), (
            "StockAlertConfig should reference a product/variant"
        )

    def test_serializers_use_drf(self):
        """Verify serializers.py uses Django REST Framework serializers"""
        path = os.path.join(self.REPO_DIR, "saleor/warehouse/serializers.py")
        with open(path) as f:
            content = f.read()

        assert "rest_framework" in content, (
            "Serializers should import from rest_framework"
        )
        assert re.search(r"class\s+\w+Serializer", content), (
            "At least one serializer class should be defined"
        )

    def test_views_define_api_endpoints(self):
        """Verify views.py defines API views for alert operations"""
        path = os.path.join(self.REPO_DIR, "saleor/warehouse/views.py")
        with open(path) as f:
            content = f.read()

        # Should have list, create, and possibly update operations
        view_indicators = [
            "ViewSet", "APIView", "api_view", "ListAPIView",
            "CreateAPIView", "GenericAPIView", "ModelViewSet",
        ]
        found = [ind for ind in view_indicators if ind in content]
        assert len(found) >= 1, (
            f"views.py should use DRF view classes. Found: {found}"
        )

    def test_urls_define_routes(self):
        """Verify urls.py defines URL patterns for alert endpoints"""
        path = os.path.join(self.REPO_DIR, "saleor/warehouse/urls.py")
        with open(path) as f:
            content = f.read()

        assert "urlpatterns" in content, "urls.py should define urlpatterns"
        path_indicators = ["path(", "re_path(", "router", "url("]
        found = [ind for ind in path_indicators if ind in content]
        assert len(found) >= 1, (
            f"urls.py should use path() or router for URL routing. Found: {found}"
        )

    def test_duplicate_alert_prevention(self):
        """Verify code prevents duplicate unresolved alerts"""
        combined = ""
        for fname in ["models.py", "views.py", "serializers.py"]:
            path = os.path.join(self.REPO_DIR, f"saleor/warehouse/{fname}")
            if os.path.exists(path):
                with open(path) as f:
                    combined += f.read()

        duplicate_indicators = [
            "exists()", "filter(", "get_or_create", "unique_together",
            "UniqueConstraint", "duplicate", "already",
        ]
        found = [ind for ind in duplicate_indicators if ind in combined]
        assert len(found) >= 1, (
            "Code should prevent duplicate unresolved alerts. "
            f"None of {duplicate_indicators} found."
        )

    def test_alert_acknowledge_resolve(self):
        """Verify alerts can be acknowledged or resolved"""
        combined = ""
        for fname in ["models.py", "views.py"]:
            path = os.path.join(self.REPO_DIR, f"saleor/warehouse/{fname}")
            if os.path.exists(path):
                with open(path) as f:
                    combined += f.read()

        resolve_indicators = [
            "acknowledge", "resolve", "resolved", "is_resolved",
            "status", "RESOLVED", "ACKNOWLEDGED",
        ]
        found = [ind for ind in resolve_indicators if ind in combined]
        assert len(found) >= 1, (
            "Should support resolving/acknowledging alerts. "
            f"None of {resolve_indicators} found."
        )

    def test_filtering_support(self):
        """Verify alert filtering by warehouse or product category"""
        combined = ""
        for fname in ["views.py", "serializers.py"]:
            path = os.path.join(self.REPO_DIR, f"saleor/warehouse/{fname}")
            if os.path.exists(path):
                with open(path) as f:
                    combined += f.read()

        filter_indicators = [
            "filter", "warehouse", "category", "filter_backends",
            "filterset", "DjangoFilterBackend", "query_params",
        ]
        found = [ind for ind in filter_indicators if ind in combined]
        assert len(found) >= 2, (
            f"Views should support filtering by warehouse/category. "
            f"Found: {found}"
        )

    # === Functional Checks ===

    def test_models_valid_python(self):
        """Verify models.py is valid Python"""
        path = os.path.join(self.REPO_DIR, "saleor/warehouse/models.py")
        result = subprocess.run(
            ["python", "-c", f"import ast; ast.parse(open('{path}').read())"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, (
            f"models.py has syntax errors: {result.stderr}"
        )

    def test_views_valid_python(self):
        """Verify views.py is valid Python"""
        path = os.path.join(self.REPO_DIR, "saleor/warehouse/views.py")
        result = subprocess.run(
            ["python", "-c", f"import ast; ast.parse(open('{path}').read())"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, (
            f"views.py has syntax errors: {result.stderr}"
        )

    def test_serializers_valid_python(self):
        """Verify serializers.py is valid Python"""
        path = os.path.join(self.REPO_DIR, "saleor/warehouse/serializers.py")
        result = subprocess.run(
            ["python", "-c", f"import ast; ast.parse(open('{path}').read())"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, (
            f"serializers.py has syntax errors: {result.stderr}"
        )

    def test_urls_valid_python(self):
        """Verify urls.py is valid Python"""
        path = os.path.join(self.REPO_DIR, "saleor/warehouse/urls.py")
        result = subprocess.run(
            ["python", "-c", f"import ast; ast.parse(open('{path}').read())"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, (
            f"urls.py has syntax errors: {result.stderr}"
        )
