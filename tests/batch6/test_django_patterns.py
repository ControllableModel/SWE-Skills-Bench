"""
Test skill: django-patterns
Verify that the Agent correctly implements a Wishlist feature for Saleor
with Django models, GraphQL queries/mutations, UUID PKs, unique
constraints, pagination, and permission checks.
"""

import os
import re
import subprocess
import pytest


class TestDjangoPatterns:
    REPO_DIR = "/workspace/saleor"

    # === File Path Checks ===

    def test_wishlist_models_file_exists(self):
        """Verify wishlist/models.py exists"""
        path = os.path.join(self.REPO_DIR, "saleor/wishlist/models.py")
        assert os.path.exists(path), f"wishlist/models.py not found at {path}"

    def test_wishlist_init_file_exists(self):
        """Verify wishlist/__init__.py exists"""
        path = os.path.join(self.REPO_DIR, "saleor/wishlist/__init__.py")
        assert os.path.exists(path), f"wishlist/__init__.py not found at {path}"

    def test_wishlist_migration_exists(self):
        """Verify initial migration for wishlist exists"""
        migration_dir = os.path.join(self.REPO_DIR, "saleor/wishlist/migrations")
        assert os.path.isdir(migration_dir), f"migrations dir not found at {migration_dir}"
        migration_files = [f for f in os.listdir(migration_dir) if f.endswith(".py") and f != "__init__.py"]
        assert len(migration_files) >= 1, "No migration files found"

    def test_graphql_schema_file_exists(self):
        """Verify GraphQL wishlist schema file exists"""
        path = os.path.join(self.REPO_DIR, "saleor/graphql/wishlist/schema.py")
        assert os.path.exists(path), f"graphql/wishlist/schema.py not found"

    def test_graphql_mutations_file_exists(self):
        """Verify GraphQL wishlist mutations file exists"""
        path = os.path.join(self.REPO_DIR, "saleor/graphql/wishlist/mutations.py")
        assert os.path.exists(path), f"graphql/wishlist/mutations.py not found"

    def test_graphql_types_file_exists(self):
        """Verify GraphQL wishlist types file exists"""
        path = os.path.join(self.REPO_DIR, "saleor/graphql/wishlist/types.py")
        assert os.path.exists(path), f"graphql/wishlist/types.py not found"

    # === Semantic Checks ===

    def test_wishlist_model_has_uuid_pk(self):
        """Verify Wishlist model uses UUID primary key"""
        path = os.path.join(self.REPO_DIR, "saleor/wishlist/models.py")
        with open(path, "r") as f:
            content = f.read()

        assert "UUIDField" in content, "Wishlist model should use UUIDField as primary key"
        assert "primary_key=True" in content or "primary_key" in content, (
            "Wishlist model should have UUID primary_key"
        )

    def test_wishlist_model_has_user_fk(self):
        """Verify Wishlist model has ForeignKey to User with CASCADE"""
        path = os.path.join(self.REPO_DIR, "saleor/wishlist/models.py")
        with open(path, "r") as f:
            content = f.read()

        assert "ForeignKey" in content, "Wishlist model should have ForeignKey"
        assert "CASCADE" in content, "User FK should use on_delete=CASCADE"
        assert "wishlists" in content, "User FK should have related_name='wishlists'"

    def test_wishlist_model_unique_constraint(self):
        """Verify unique constraint on (user, name)"""
        path = os.path.join(self.REPO_DIR, "saleor/wishlist/models.py")
        with open(path, "r") as f:
            content = f.read()

        has_unique = (
            "unique_together" in content
            or "UniqueConstraint" in content
            or "unique=True" in content
        )
        assert has_unique, "Wishlist should have unique constraint on (user, name)"

    def test_wishlist_item_model_has_product_fk(self):
        """Verify WishlistItem has ForeignKey to Product"""
        path = os.path.join(self.REPO_DIR, "saleor/wishlist/models.py")
        with open(path, "r") as f:
            content = f.read()

        assert "WishlistItem" in content, "WishlistItem model should be defined"
        assert "product" in content.lower(), "WishlistItem should have product FK"

    def test_wishlist_item_unique_constraint(self):
        """Verify unique constraint on (wishlist, product)"""
        path = os.path.join(self.REPO_DIR, "saleor/wishlist/models.py")
        with open(path, "r") as f:
            content = f.read()

        # Look for unique_together or UniqueConstraint for wishlist+product
        assert re.search(
            r"unique_together|UniqueConstraint.*wishlist.*product|UniqueConstraint.*product.*wishlist",
            content, re.DOTALL
        ), "WishlistItem should have unique constraint on (wishlist, product)"

    def test_wishlist_item_ordering(self):
        """Verify WishlistItem has Meta.ordering = ['-added_at']"""
        path = os.path.join(self.REPO_DIR, "saleor/wishlist/models.py")
        with open(path, "r") as f:
            content = f.read()

        assert "ordering" in content, "WishlistItem should define Meta.ordering"
        assert "added_at" in content, "WishlistItem ordering should reference added_at"

    def test_mutations_include_add_remove_clear(self):
        """Verify all three mutations are defined"""
        path = os.path.join(self.REPO_DIR, "saleor/graphql/wishlist/mutations.py")
        with open(path, "r") as f:
            content = f.read()

        assert "WishlistAddProduct" in content or "wishlist_add_product" in content.lower(), (
            "Missing WishlistAddProduct mutation"
        )
        assert "WishlistRemoveProduct" in content or "wishlist_remove_product" in content.lower(), (
            "Missing WishlistRemoveProduct mutation"
        )
        assert "WishlistClear" in content or "wishlist_clear" in content.lower(), (
            "Missing WishlistClear mutation"
        )

    def test_add_product_mutation_is_idempotent(self):
        """Verify WishlistAddProduct handles existing item gracefully"""
        path = os.path.join(self.REPO_DIR, "saleor/graphql/wishlist/mutations.py")
        with open(path, "r") as f:
            content = f.read()

        has_idempotent = (
            "get_or_create" in content
            or "exists()" in content
            or "filter(" in content
            or "IntegrityError" in content
        )
        assert has_idempotent, (
            "WishlistAddProduct should be idempotent (handle duplicate adds)"
        )

    def test_item_limit_enforced(self):
        """Verify 200-item limit is enforced"""
        path = os.path.join(self.REPO_DIR, "saleor/graphql/wishlist/mutations.py")
        with open(path, "r") as f:
            content = f.read()

        assert "200" in content, (
            "Should enforce 200-item limit for wishlist"
        )
        assert "LIMIT_EXCEEDED" in content or "limit" in content.lower(), (
            "Should return LIMIT_EXCEEDED error when over 200 items"
        )

    def test_queries_use_prefetch(self):
        """Verify GraphQL queries use prefetch_related to avoid N+1"""
        resolvers_path = os.path.join(self.REPO_DIR, "saleor/graphql/wishlist/resolvers.py")
        types_path = os.path.join(self.REPO_DIR, "saleor/graphql/wishlist/types.py")

        found_prefetch = False
        for path in [resolvers_path, types_path]:
            if os.path.exists(path):
                with open(path, "r") as f:
                    content = f.read()
                if "prefetch_related" in content or "select_related" in content:
                    found_prefetch = True
                    break

        assert found_prefetch, (
            "Wishlist queries should use prefetch_related or select_related"
        )

    def test_authentication_required(self):
        """Verify mutations require authentication"""
        path = os.path.join(self.REPO_DIR, "saleor/graphql/wishlist/mutations.py")
        with open(path, "r") as f:
            content = f.read()

        has_auth_check = (
            "PermissionDenied" in content
            or "permission" in content.lower()
            or "login_required" in content
            or "is_authenticated" in content
        )
        assert has_auth_check, (
            "Mutations should require authentication"
        )

    # === Functional Checks ===

    def test_models_import_successfully(self):
        """Verify wishlist models can be imported"""
        result = subprocess.run(
            [
                "python", "-c",
                "import django; django.setup(); "
                "from saleor.wishlist.models import Wishlist, WishlistItem; "
                "print('OK')"
            ],
            capture_output=True, text=True, timeout=60,
            cwd=self.REPO_DIR,
            env={**os.environ, "DJANGO_SETTINGS_MODULE": "saleor.settings"},
        )
        assert result.returncode == 0, (
            f"Failed to import wishlist models:\n{result.stderr[:1000]}"
        )

    def test_migration_is_valid(self):
        """Verify migration file is valid Python"""
        migration_dir = os.path.join(self.REPO_DIR, "saleor/wishlist/migrations")
        if not os.path.isdir(migration_dir):
            pytest.fail("migrations directory not found")

        for f in os.listdir(migration_dir):
            if f.endswith(".py") and f != "__init__.py":
                path = os.path.join(migration_dir, f)
                result = subprocess.run(
                    ["python", "-c", f"import ast; ast.parse(open('{path}').read())"],
                    capture_output=True, text=True, timeout=30,
                )
                assert result.returncode == 0, (
                    f"Migration {f} has syntax errors: {result.stderr}"
                )

    def test_graphql_schema_registered(self):
        """Verify wishlist is registered in root GraphQL schema"""
        path = os.path.join(self.REPO_DIR, "saleor/graphql/schema.py")
        with open(path, "r") as f:
            content = f.read()

        assert "wishlist" in content.lower(), (
            "Wishlist should be registered in the root GraphQL schema"
        )
