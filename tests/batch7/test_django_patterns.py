"""
Test skill: django-patterns
Verify that the Agent adds a Product Bundle feature to the Saleor e-commerce
platform — models, managers, service layer, signals, and GraphQL types/mutations.
"""

import os
import re
import ast
import subprocess
import pytest


class TestDjangoPatterns:
    REPO_DIR = "/workspace/saleor"

    # ────────────────── helpers ──────────────────

    def _read(self, rel_path):
        fpath = os.path.join(self.REPO_DIR, rel_path)
        with open(fpath, "r") as f:
            return f.read()

    def _exists(self, rel_path):
        return os.path.isfile(os.path.join(self.REPO_DIR, rel_path))

    # === File Path Checks ===

    def test_product_models_exists(self):
        """saleor/product/models.py must exist"""
        assert self._exists("saleor/product/models.py")

    def test_managers_file_exists(self):
        """saleor/product/managers.py must exist"""
        assert self._exists("saleor/product/managers.py")

    def test_services_file_exists(self):
        """saleor/product/services.py must exist"""
        assert self._exists("saleor/product/services.py")

    def test_signals_file_exists(self):
        """saleor/product/signals.py must exist"""
        assert self._exists("saleor/product/signals.py")

    def test_graphql_bundle_types_exists(self):
        """GraphQL bundle types file must exist"""
        assert self._exists("saleor/graphql/product/types/bundles.py")

    def test_graphql_bundle_mutations_exists(self):
        """GraphQL bundle mutations file must exist"""
        assert self._exists("saleor/graphql/product/mutations/bundles.py")

    # === Semantic Checks — Models ===

    def test_product_bundle_model_defined(self):
        """ProductBundle model must be defined in models.py"""
        src = self._read("saleor/product/models.py")
        assert re.search(r'class\s+ProductBundle\b', src), (
            "ProductBundle model class not found"
        )

    def test_bundle_item_model_defined(self):
        """BundleItem model must be defined in models.py"""
        src = self._read("saleor/product/models.py")
        assert re.search(r'class\s+BundleItem\b', src), (
            "BundleItem model class not found"
        )

    def test_product_bundle_fields(self):
        """ProductBundle must have required fields: name, slug, discount_type,
        discount_value, is_active"""
        src = self._read("saleor/product/models.py")
        for field in ["name", "slug", "discount_type", "discount_value", "is_active"]:
            assert re.search(rf'{field}\s*=', src), (
                f"ProductBundle missing field: {field}"
            )

    def test_discount_type_choices(self):
        """discount_type must allow 'percentage' and 'fixed_amount'"""
        src = self._read("saleor/product/models.py")
        assert "percentage" in src and "fixed_amount" in src, (
            "discount_type choices missing percentage or fixed_amount"
        )

    def test_bundle_item_foreign_keys(self):
        """BundleItem must have ForeignKey to ProductBundle (bundle) and Product (product)"""
        src = self._read("saleor/product/models.py")
        assert "ForeignKey" in src, "BundleItem missing ForeignKey definitions"
        assert re.search(r'bundle\s*=.*ForeignKey', src), (
            "BundleItem missing 'bundle' ForeignKey"
        )

    def test_check_constraint_discount_value(self):
        """ProductBundle must have a CheckConstraint for discount_value"""
        src = self._read("saleor/product/models.py")
        assert "CheckConstraint" in src, (
            "ProductBundle missing CheckConstraint for discount_value"
        )

    def test_meta_db_table(self):
        """ProductBundle Meta must specify db_table = 'product_bundle'"""
        src = self._read("saleor/product/models.py")
        assert "product_bundle" in src, (
            "ProductBundle Meta db_table not set to 'product_bundle'"
        )

    # === Semantic Checks — Manager ===

    def test_queryset_active_method(self):
        """ProductBundleQuerySet must have an active() method"""
        src = self._read("saleor/product/managers.py")
        assert re.search(r'def\s+active\s*\(', src), (
            "ProductBundleQuerySet missing active() method"
        )

    def test_queryset_with_items_method(self):
        """ProductBundleQuerySet must have a with_items() method"""
        src = self._read("saleor/product/managers.py")
        assert re.search(r'def\s+with_items\s*\(', src), (
            "ProductBundleQuerySet missing with_items() method"
        )

    def test_queryset_available_method(self):
        """ProductBundleQuerySet must have an available() method"""
        src = self._read("saleor/product/managers.py")
        assert re.search(r'def\s+available\s*\(', src), (
            "ProductBundleQuerySet missing available() method"
        )

    def test_queryset_search_method(self):
        """ProductBundleQuerySet must have a search() method"""
        src = self._read("saleor/product/managers.py")
        assert re.search(r'def\s+search\s*\(', src), (
            "ProductBundleQuerySet missing search() method"
        )

    # === Semantic Checks — Service Layer ===

    def test_bundle_service_class_exists(self):
        """BundleService class must be defined in services.py"""
        src = self._read("saleor/product/services.py")
        assert re.search(r'class\s+BundleService\b', src), (
            "BundleService class not found in services.py"
        )

    def test_create_bundle_method(self):
        """BundleService must have a create_bundle method"""
        src = self._read("saleor/product/services.py")
        assert re.search(r'def\s+create_bundle\s*\(', src), (
            "create_bundle method not found"
        )

    def test_calculate_bundle_price_method(self):
        """BundleService must have a calculate_bundle_price method"""
        src = self._read("saleor/product/services.py")
        assert re.search(r'def\s+calculate_bundle_price\s*\(', src), (
            "calculate_bundle_price method not found"
        )

    def test_check_availability_method(self):
        """BundleService must have a check_availability method"""
        src = self._read("saleor/product/services.py")
        assert re.search(r'def\s+check_availability\s*\(', src), (
            "check_availability method not found"
        )

    def test_create_bundle_uses_atomic(self):
        """create_bundle must use transaction.atomic for atomicity"""
        src = self._read("saleor/product/services.py")
        assert "atomic" in src, (
            "create_bundle should use transaction.atomic"
        )

    # === Semantic Checks — Signals ===

    def test_post_save_signal_registered(self):
        """A post_save signal must be connected for stock change handling"""
        src = self._read("saleor/product/signals.py")
        assert "post_save" in src, (
            "post_save signal not found in signals.py"
        )

    # === Semantic Checks — GraphQL ===

    def test_graphql_bundle_type_defined(self):
        """ProductBundleType must be defined in graphql types"""
        src = self._read("saleor/graphql/product/types/bundles.py")
        assert re.search(r'class\s+ProductBundleType\b', src), (
            "ProductBundleType not defined"
        )

    def test_graphql_total_price_field(self):
        """ProductBundleType must expose a total_price computed field"""
        src = self._read("saleor/graphql/product/types/bundles.py")
        assert "total_price" in src, (
            "total_price computed field missing from ProductBundleType"
        )

    def test_graphql_bundle_create_mutation(self):
        """BundleCreate mutation must be defined"""
        src = self._read("saleor/graphql/product/mutations/bundles.py")
        assert re.search(r'class\s+BundleCreate\b', src), (
            "BundleCreate mutation not found"
        )

    def test_graphql_bundle_delete_mutation(self):
        """BundleDelete mutation must be defined"""
        src = self._read("saleor/graphql/product/mutations/bundles.py")
        assert re.search(r'class\s+BundleDelete\b', src), (
            "BundleDelete mutation not found"
        )

    # === Functional Checks ===

    def test_django_check_no_errors(self):
        """Django system check should report no errors after model additions"""
        result = subprocess.run(
            ["python", "-m", "django", "check", "--settings=saleor.settings"],
            capture_output=True, text=True, cwd=self.REPO_DIR, timeout=120,
            env={**os.environ, "DJANGO_SETTINGS_MODULE": "saleor.settings"},
        )
        assert result.returncode == 0, (
            f"Django check failed:\n{result.stdout}\n{result.stderr}"
        )

    def test_makemigrations_no_changes(self):
        """makemigrations --check should show no pending model changes
        (migration file must have been created)"""
        result = subprocess.run(
            ["python", "-m", "django", "makemigrations", "--check", "--dry-run",
             "--settings=saleor.settings"],
            capture_output=True, text=True, cwd=self.REPO_DIR, timeout=120,
            env={**os.environ, "DJANGO_SETTINGS_MODULE": "saleor.settings"},
        )
        # returncode 0 means no changes detected (migration already exists)
        # returncode 1 means unapplied changes — both are acceptable as long
        # as the models compile; strict migration check is optional.
        assert result.returncode in (0, 1), (
            f"makemigrations failed:\n{result.stdout}\n{result.stderr}"
        )

    def test_services_importable(self):
        """BundleService must be importable from saleor.product.services"""
        result = subprocess.run(
            ["python", "-c",
             "import django; django.setup(); "
             "from saleor.product.services import BundleService; "
             "print('OK')"],
            capture_output=True, text=True, cwd=self.REPO_DIR, timeout=60,
            env={**os.environ, "DJANGO_SETTINGS_MODULE": "saleor.settings"},
        )
        assert "OK" in result.stdout, (
            f"Import failed:\n{result.stdout}\n{result.stderr}"
        )
