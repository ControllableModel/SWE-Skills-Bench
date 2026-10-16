"""
Tests for skill: django-patterns
Repo: saleor/saleor
Image: zhangyiiiiii/swe-skills-bench-python
Task: Implement a Product Review system in Saleor with Django model,
      DRF API, service layer, caching, and signals.
"""

import ast
import importlib
import os
import re
import subprocess
import sys

import pytest

REPO_DIR = "/workspace/saleor"

# Expected file paths
MODEL_FILE = os.path.join(REPO_DIR, "saleor", "product", "models.py")
MANAGERS_FILE = os.path.join(REPO_DIR, "saleor", "product", "managers.py")
SERVICES_FILE = os.path.join(REPO_DIR, "saleor", "product", "services.py")
SIGNALS_FILE = os.path.join(REPO_DIR, "saleor", "product", "signals.py")

# API-related files — may be in different locations
API_SERIALIZERS = os.path.join(REPO_DIR, "saleor", "product", "api", "serializers.py")
API_VIEWS = os.path.join(REPO_DIR, "saleor", "product", "api", "views.py")
API_URLS = os.path.join(REPO_DIR, "saleor", "product", "api", "urls.py")


# ---------------------------------------------------------------------------
# Layer 1 — file_path_check
# ---------------------------------------------------------------------------

class TestFilePathCheck:
    """Verify that all required files exist."""

    def test_models_file_exists(self):
        assert os.path.isfile(MODEL_FILE), (
            f"Expected models file at {MODEL_FILE}"
        )

    def test_services_file_exists(self):
        assert os.path.isfile(SERVICES_FILE), (
            f"Expected services file at {SERVICES_FILE}"
        )

    def test_api_serializers_exist(self):
        """Serializers file must exist (possibly in api/ subdirectory)."""
        candidates = [
            API_SERIALIZERS,
            os.path.join(REPO_DIR, "saleor", "product", "serializers.py"),
        ]
        found = any(os.path.isfile(c) for c in candidates)
        assert found, (
            f"Expected serializers file in one of: {candidates}"
        )

    def test_api_views_exist(self):
        candidates = [
            API_VIEWS,
            os.path.join(REPO_DIR, "saleor", "product", "views.py"),
        ]
        found = any(os.path.isfile(c) for c in candidates)
        assert found, f"Expected views file in one of: {candidates}"

    def test_api_urls_exist(self):
        candidates = [
            API_URLS,
            os.path.join(REPO_DIR, "saleor", "product", "urls.py"),
        ]
        found = any(os.path.isfile(c) for c in candidates)
        assert found, f"Expected urls file in one of: {candidates}"


# ---------------------------------------------------------------------------
# Layer 2 — semantic_check
# ---------------------------------------------------------------------------

class TestSemanticModel:
    """Verify ProductReview model structure in models.py."""

    @pytest.fixture(autouse=True)
    def _load_source(self):
        with open(MODEL_FILE, "r", encoding="utf-8") as f:
            self.src = f.read()
        self.tree = ast.parse(self.src)

    def test_product_review_class_defined(self):
        """ProductReview model class must be defined."""
        classes = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.ClassDef)]
        assert "ProductReview" in classes, (
            f"Expected ProductReview class in models.py; found: {classes}"
        )

    def test_model_has_rating_field(self):
        """Model must have a rating field (PositiveSmallIntegerField)."""
        assert "PositiveSmallIntegerField" in self.src or "rating" in self.src, (
            "Expected PositiveSmallIntegerField for rating field"
        )

    def test_model_has_status_choices(self):
        """Model must define status choices: pending, approved, rejected."""
        for status in ["pending", "approved", "rejected"]:
            assert status in self.src, (
                f"Expected status choice '{status}' in ProductReview model"
            )

    def test_model_has_unique_constraint(self):
        """Model must have a unique constraint on (product, user)."""
        has_unique = (
            "unique_together" in self.src
            or "UniqueConstraint" in self.src
            or "unique=True" in self.src
        )
        assert has_unique, (
            "Expected unique constraint on (product, user) in ProductReview"
        )

    def test_model_has_related_name(self):
        """FK to Product must use related_name='reviews'."""
        assert "reviews" in self.src, (
            "Expected related_name='reviews' on FK to Product"
        )

    def test_model_has_cascade_delete(self):
        """FKs must use on_delete=CASCADE."""
        assert "CASCADE" in self.src, (
            "Expected on_delete=CASCADE in ProductReview FK definitions"
        )


class TestSemanticServices:
    """Verify service layer structure."""

    @pytest.fixture(autouse=True)
    def _load_source(self):
        with open(SERVICES_FILE, "r", encoding="utf-8") as f:
            self.src = f.read()
        self.tree = ast.parse(self.src)

    def test_submit_review_function(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "submit_review" in funcs, (
            f"Expected submit_review function in services.py; found: {funcs}"
        )

    def test_moderate_review_function(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "moderate_review" in funcs, (
            f"Expected moderate_review function in services.py; found: {funcs}"
        )

    def test_get_product_review_summary_function(self):
        funcs = [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]
        assert "get_product_review_summary" in funcs, (
            f"Expected get_product_review_summary in services.py; found: {funcs}"
        )

    def test_purchase_verification_in_submit(self):
        """submit_review must check order history / purchase before allowing review."""
        has_purchase_check = (
            "order" in self.src.lower()
            or "purchase" in self.src.lower()
            or "PermissionDenied" in self.src
        )
        assert has_purchase_check, (
            "Expected purchase/order verification in submit_review"
        )

    def test_summary_uses_caching(self):
        """get_product_review_summary must use caching."""
        has_cache = (
            "cache" in self.src.lower()
            or "django.core.cache" in self.src
        )
        assert has_cache, (
            "Expected caching in get_product_review_summary"
        )


class TestSemanticSignals:
    """Verify signal handlers exist for cache invalidation."""

    def _find_signals_file(self):
        candidates = [
            SIGNALS_FILE,
            os.path.join(REPO_DIR, "saleor", "product", "signals.py"),
        ]
        for c in candidates:
            if os.path.isfile(c):
                return c
        # Signals may also be defined in models.py or services.py
        return MODEL_FILE

    def test_post_save_signal(self):
        """post_save signal must be connected for cache invalidation."""
        path = self._find_signals_file()
        with open(path, "r", encoding="utf-8") as f:
            src = f.read()
        # Also check services.py and models.py for signals
        all_src = src
        for extra in [SERVICES_FILE, MODEL_FILE]:
            if os.path.isfile(extra) and extra != path:
                with open(extra, "r", encoding="utf-8") as f:
                    all_src += f.read()
        has_signal = (
            "post_save" in all_src
            or "post_delete" in all_src
            or "signal" in all_src.lower()
        )
        assert has_signal, (
            "Expected post_save/post_delete signal for cache invalidation"
        )


# ---------------------------------------------------------------------------
# Layer 3 — functional_check
# ---------------------------------------------------------------------------

class TestFunctionalDjangoPatterns:
    """Functional tests for the product review implementation."""

    def _run(self, cmd, cwd=REPO_DIR, timeout=120):
        result = subprocess.run(
            cmd, shell=True, cwd=cwd,
            capture_output=True, text=True, timeout=timeout,
        )
        return result

    def test_models_file_parses(self):
        """models.py must be valid Python."""
        with open(MODEL_FILE, "r", encoding="utf-8") as f:
            src = f.read()
        try:
            ast.parse(src)
        except SyntaxError as e:
            pytest.fail(f"models.py has syntax error: {e}")

    def test_services_file_parses(self):
        """services.py must be valid Python."""
        with open(SERVICES_FILE, "r", encoding="utf-8") as f:
            src = f.read()
        try:
            ast.parse(src)
        except SyntaxError as e:
            pytest.fail(f"services.py has syntax error: {e}")

    def test_view_file_parses(self):
        """views.py must be valid Python."""
        candidates = [API_VIEWS, os.path.join(REPO_DIR, "saleor", "product", "views.py")]
        for path in candidates:
            if os.path.isfile(path):
                with open(path, "r", encoding="utf-8") as f:
                    src = f.read()
                try:
                    ast.parse(src)
                except SyntaxError as e:
                    pytest.fail(f"{path} has syntax error: {e}")
                return
        pytest.skip("views.py not found")

    def test_serializer_file_parses(self):
        """serializers.py must be valid Python."""
        candidates = [API_SERIALIZERS, os.path.join(REPO_DIR, "saleor", "product", "serializers.py")]
        for path in candidates:
            if os.path.isfile(path):
                with open(path, "r", encoding="utf-8") as f:
                    src = f.read()
                try:
                    ast.parse(src)
                except SyntaxError as e:
                    pytest.fail(f"{path} has syntax error: {e}")
                return
        pytest.skip("serializers.py not found")

    def test_review_api_uses_viewset_or_apiview(self):
        """Views must use DRF ViewSet or APIView."""
        candidates = [API_VIEWS, os.path.join(REPO_DIR, "saleor", "product", "views.py")]
        for path in candidates:
            if os.path.isfile(path):
                with open(path, "r", encoding="utf-8") as f:
                    src = f.read()
                has_drf = (
                    "ViewSet" in src
                    or "APIView" in src
                    or "ModelViewSet" in src
                    or "GenericViewSet" in src
                )
                assert has_drf, (
                    "Expected DRF ViewSet or APIView in views.py"
                )
                return
        pytest.skip("views.py not found")

    def test_django_check_passes(self):
        """Django system check must pass (or at least not crash on import)."""
        result = self._run(
            "python -c \"import django; import os; "
            "os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'saleor.settings'); "
            "django.setup(); print('OK')\"",
            timeout=60,
        )
        # We allow warnings; only fail if Python itself errors
        assert result.returncode == 0 or "OK" in result.stdout, (
            f"Django setup failed:\nstdout: {result.stdout[:500]}\nstderr: {result.stderr[:500]}"
        )

    def test_rating_validators_in_model(self):
        """Rating field must have validators constraining range 1-5."""
        with open(MODEL_FILE, "r", encoding="utf-8") as f:
            src = f.read()
        has_validators = (
            "MinValueValidator" in src
            or "MaxValueValidator" in src
            or "validators" in src
            or "IntegerRangeField" in src
            or re.search(r"validators\s*=\s*\[", src)
        )
        assert has_validators, (
            "Expected MinValueValidator/MaxValueValidator for rating (1-5)"
        )
