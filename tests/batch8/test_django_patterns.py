"""
Tests for the django-patterns skill.
Validates implementation of a Wishlist feature with REST API in Saleor,
including models, serializers, views, URL routing, and authorization.
"""

import os
import re
import subprocess

REPO_DIR = "/workspace/saleor"


class TestDjangoPatterns:
    """Tests for the Saleor Wishlist feature implementation."""

    # ── file_path_check ──────────────────────────────────────────────

    def test_wishlist_models_exists(self):
        """Wishlist models.py must exist."""
        path = os.path.join(REPO_DIR, "saleor", "wishlist", "models.py")
        assert os.path.isfile(path), f"Missing {path}"

    def test_wishlist_views_exists(self):
        """Wishlist views.py must exist."""
        path = os.path.join(REPO_DIR, "saleor", "wishlist", "views.py")
        assert os.path.isfile(path), f"Missing {path}"

    def test_wishlist_serializers_exists(self):
        """Wishlist serializers.py must exist."""
        path = os.path.join(REPO_DIR, "saleor", "wishlist", "serializers.py")
        assert os.path.isfile(path), f"Missing {path}"

    def test_wishlist_urls_exists(self):
        """Wishlist urls.py must exist."""
        path = os.path.join(REPO_DIR, "saleor", "wishlist", "urls.py")
        assert os.path.isfile(path), f"Missing {path}"

    def test_wishlist_init_exists(self):
        """Wishlist __init__.py must exist (package)."""
        path = os.path.join(REPO_DIR, "saleor", "wishlist", "__init__.py")
        assert os.path.isfile(path), f"Missing {path}"

    # ── semantic_check ───────────────────────────────────────────────

    def _read_file(self, rel_path):
        """Read a file relative to REPO_DIR."""
        path = os.path.join(REPO_DIR, rel_path)
        if not os.path.isfile(path):
            return ""
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def test_wishlist_model_defined(self):
        """Wishlist model class must be defined with user field."""
        content = self._read_file("saleor/wishlist/models.py")
        assert re.search(r"class\s+Wishlist\b", content), "Wishlist model not defined"
        assert re.search(r"OneToOneField|ForeignKey", content), (
            "Wishlist must have a user relationship"
        )

    def test_wishlist_item_model_defined(self):
        """WishlistItem model must be defined with product_variant and wishlist FK."""
        content = self._read_file("saleor/wishlist/models.py")
        assert re.search(r"class\s+WishlistItem\b", content), "WishlistItem model not defined"
        assert "product_variant" in content, "WishlistItem must reference product_variant"
        assert "wishlist" in content, "WishlistItem must reference wishlist"

    def test_unique_constraint_on_wishlist_item(self):
        """Unique constraint on (wishlist, product_variant) must be enforced."""
        content = self._read_file("saleor/wishlist/models.py")
        assert re.search(
            r"unique_together|UniqueConstraint|unique=True", content
        ), "Unique constraint on (wishlist, product_variant) not found"

    def test_uuid_primary_keys(self):
        """Models should use UUID primary keys."""
        content = self._read_file("saleor/wishlist/models.py")
        assert re.search(r"UUIDField|uuid", content, re.IGNORECASE), (
            "UUID primary keys not found in models"
        )

    def test_serializer_has_nested_product_info(self):
        """Serializer must include nested product variant details."""
        content = self._read_file("saleor/wishlist/serializers.py")
        assert re.search(r"variant_name|product_name|variant_price|is_available", content), (
            "Serializer lacks nested product variant detail fields"
        )

    def test_viewset_has_move_to_cart_action(self):
        """ViewSet must have a move_to_cart custom action."""
        content = self._read_file("saleor/wishlist/views.py")
        assert re.search(r"move_to_cart|move-to-cart", content), (
            "move_to_cart action not found in views"
        )

    def test_authentication_required(self):
        """All endpoints must require authentication."""
        content = self._read_file("saleor/wishlist/views.py")
        assert re.search(
            r"IsAuthenticated|authentication_classes|permission_classes|login_required",
            content,
        ), "Authentication enforcement not found in views"

    # ── functional_check ─────────────────────────────────────────────

    def test_models_valid_python(self):
        """Models file must be valid Python syntax."""
        path = os.path.join(REPO_DIR, "saleor", "wishlist", "models.py")
        result = subprocess.run(
            ["python", "-c", f"import ast; ast.parse(open('{path}').read())"],
            capture_output=True, text=True, cwd=REPO_DIR,
        )
        assert result.returncode == 0, f"models.py has syntax errors: {result.stderr}"

    def test_views_valid_python(self):
        """Views file must be valid Python syntax."""
        path = os.path.join(REPO_DIR, "saleor", "wishlist", "views.py")
        result = subprocess.run(
            ["python", "-c", f"import ast; ast.parse(open('{path}').read())"],
            capture_output=True, text=True, cwd=REPO_DIR,
        )
        assert result.returncode == 0, f"views.py has syntax errors: {result.stderr}"

    def test_serializers_valid_python(self):
        """Serializers file must be valid Python syntax."""
        path = os.path.join(REPO_DIR, "saleor", "wishlist", "serializers.py")
        result = subprocess.run(
            ["python", "-c", f"import ast; ast.parse(open('{path}').read())"],
            capture_output=True, text=True, cwd=REPO_DIR,
        )
        assert result.returncode == 0, f"serializers.py has syntax errors: {result.stderr}"

    def test_urls_valid_python(self):
        """URLs file must be valid Python syntax."""
        path = os.path.join(REPO_DIR, "saleor", "wishlist", "urls.py")
        result = subprocess.run(
            ["python", "-c", f"import ast; ast.parse(open('{path}').read())"],
            capture_output=True, text=True, cwd=REPO_DIR,
        )
        assert result.returncode == 0, f"urls.py has syntax errors: {result.stderr}"

    def test_migration_file_exists(self):
        """Initial migration must exist for wishlist models."""
        migrations_dir = os.path.join(REPO_DIR, "saleor", "wishlist", "migrations")
        if not os.path.isdir(migrations_dir):
            assert False, f"Migrations directory not found: {migrations_dir}"
        files = os.listdir(migrations_dir)
        migration_files = [f for f in files if f.endswith(".py") and f != "__init__.py"]
        assert len(migration_files) >= 1, "No migration files found for wishlist app"

    def test_cascade_delete_configured(self):
        """Models must configure CASCADE deletes for user and product_variant."""
        content = self._read_file("saleor/wishlist/models.py")
        assert content.count("CASCADE") >= 2 or content.count("on_delete") >= 2, (
            "CASCADE deletes not properly configured for user and product_variant"
        )

    def test_queryset_scoped_to_user(self):
        """ViewSet must scope queryset to authenticated user."""
        content = self._read_file("saleor/wishlist/views.py")
        assert re.search(r"get_queryset|request\.user|self\.request\.user", content), (
            "Queryset scoping to authenticated user not found"
        )

    def test_move_to_cart_checks_stock(self):
        """move_to_cart must check stock availability."""
        content = self._read_file("saleor/wishlist/views.py")
        assert re.search(r"stock|quantity|out.of.stock|is_available|in_stock", content, re.IGNORECASE), (
            "Stock check not found in move_to_cart logic"
        )
