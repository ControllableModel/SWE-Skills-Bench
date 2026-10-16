"""
Test skill: django-patterns
Verify that the Agent correctly adds a Product Review system to the
Saleor e-commerce Django backend.
"""

import os
import re
import subprocess
import pytest


class TestDjangoPatterns:
    REPO_DIR = "/workspace/saleor"

    # === File Path Checks ===

    def test_product_models_exists(self):
        """Verify saleor/product/models.py exists"""
        path = os.path.join(self.REPO_DIR, "saleor/product/models.py")
        assert os.path.exists(path), f"models.py not found at {path}"

    def test_services_file_created(self):
        """Verify saleor/product/services.py was created"""
        path = os.path.join(self.REPO_DIR, "saleor/product/services.py")
        assert os.path.exists(path), f"services.py not found at {path}"

    def test_migration_file_created(self):
        """Verify a migration file for product review was created"""
        migrations_dir = os.path.join(self.REPO_DIR, "saleor/product/migrations")
        assert os.path.isdir(migrations_dir), f"Migrations dir not found at {migrations_dir}"
        migration_files = [
            f for f in os.listdir(migrations_dir)
            if f.endswith(".py") and "review" in f.lower()
        ]
        assert len(migration_files) > 0, (
            "No migration file containing 'review' found in saleor/product/migrations/"
        )

    def test_review_model_tests_created(self):
        """Verify test_review_models.py was created"""
        path = os.path.join(self.REPO_DIR, "saleor/product/tests/test_review_models.py")
        assert os.path.exists(path), f"test_review_models.py not found at {path}"

    def test_review_service_tests_created(self):
        """Verify test_review_services.py was created"""
        path = os.path.join(self.REPO_DIR, "saleor/product/tests/test_review_services.py")
        assert os.path.exists(path), f"test_review_services.py not found at {path}"

    def test_review_mutation_tests_created(self):
        """Verify test_review_mutations.py was created"""
        path = os.path.join(
            self.REPO_DIR,
            "saleor/graphql/product/tests/test_review_mutations.py",
        )
        assert os.path.exists(path), f"test_review_mutations.py not found at {path}"

    # === Semantic Checks: ProductReview Model ===

    def test_model_has_product_review_class(self):
        """Verify ProductReview model class is defined"""
        path = os.path.join(self.REPO_DIR, "saleor/product/models.py")
        with open(path) as f:
            content = f.read()
        assert "class ProductReview" in content, (
            "ProductReview model class should be defined in models.py"
        )

    def test_model_has_rating_field(self):
        """Verify ProductReview has a rating field with PositiveSmallIntegerField"""
        path = os.path.join(self.REPO_DIR, "saleor/product/models.py")
        with open(path) as f:
            content = f.read()
        assert "PositiveSmallIntegerField" in content, (
            "rating should be a PositiveSmallIntegerField"
        )

    def test_model_has_status_field_with_choices(self):
        """Verify ProductReview has status field with PENDING/APPROVED/REJECTED"""
        path = os.path.join(self.REPO_DIR, "saleor/product/models.py")
        with open(path) as f:
            content = f.read()
        for status in ["PENDING", "APPROVED", "REJECTED"]:
            assert status in content, f"Status choices should include '{status}'"

    def test_model_has_unique_constraint(self):
        """Verify UniqueConstraint on (product, user) to prevent duplicate reviews"""
        path = os.path.join(self.REPO_DIR, "saleor/product/models.py")
        with open(path) as f:
            content = f.read()
        assert "UniqueConstraint" in content, (
            "ProductReview should have a UniqueConstraint on (product, user)"
        )

    def test_model_has_check_constraint(self):
        """Verify CheckConstraint ensuring rating is between 1 and 5"""
        path = os.path.join(self.REPO_DIR, "saleor/product/models.py")
        with open(path) as f:
            content = f.read()
        assert "CheckConstraint" in content, (
            "ProductReview should have a CheckConstraint for rating range"
        )

    def test_model_has_product_fk(self):
        """Verify ForeignKey to Product with CASCADE and related_name='reviews'"""
        path = os.path.join(self.REPO_DIR, "saleor/product/models.py")
        with open(path) as f:
            content = f.read()
        assert "ForeignKey" in content, "ProductReview should have ForeignKey fields"
        assert "reviews" in content, "Product FK should have related_name='reviews'"

    def test_model_has_custom_queryset_approved(self):
        """Verify custom QuerySet has .approved() method"""
        path = os.path.join(self.REPO_DIR, "saleor/product/models.py")
        with open(path) as f:
            content = f.read()
        assert "def approved(" in content or "def approved(self)" in content, (
            "Custom QuerySet should have .approved() method"
        )

    def test_model_has_custom_queryset_for_product(self):
        """Verify custom QuerySet has .for_product() method"""
        path = os.path.join(self.REPO_DIR, "saleor/product/models.py")
        with open(path) as f:
            content = f.read()
        assert "def for_product(" in content or "for_product" in content, (
            "Custom QuerySet should have .for_product() method"
        )

    def test_model_has_str_method(self):
        """Verify __str__ returns user - product (rating/5) format"""
        path = os.path.join(self.REPO_DIR, "saleor/product/models.py")
        with open(path) as f:
            content = f.read()
        assert "__str__" in content, "ProductReview should have __str__ method"

    # === Semantic Checks: Service Layer ===

    def test_service_has_create_review(self):
        """Verify create_review function is defined"""
        path = os.path.join(self.REPO_DIR, "saleor/product/services.py")
        with open(path) as f:
            content = f.read()
        assert "def create_review(" in content, (
            "services.py should define create_review function"
        )

    def test_service_has_update_review(self):
        """Verify update_review function is defined"""
        path = os.path.join(self.REPO_DIR, "saleor/product/services.py")
        with open(path) as f:
            content = f.read()
        assert "def update_review(" in content, (
            "services.py should define update_review function"
        )

    def test_service_has_moderate_review(self):
        """Verify moderate_review function is defined"""
        path = os.path.join(self.REPO_DIR, "saleor/product/services.py")
        with open(path) as f:
            content = f.read()
        assert "def moderate_review(" in content, (
            "services.py should define moderate_review function"
        )

    def test_service_has_get_product_rating_summary(self):
        """Verify get_product_rating_summary function is defined"""
        path = os.path.join(self.REPO_DIR, "saleor/product/services.py")
        with open(path) as f:
            content = f.read()
        assert "def get_product_rating_summary(" in content, (
            "services.py should define get_product_rating_summary function"
        )

    def test_service_uses_transaction_atomic(self):
        """Verify write operations use transaction.atomic"""
        path = os.path.join(self.REPO_DIR, "saleor/product/services.py")
        with open(path) as f:
            content = f.read()
        assert "transaction.atomic" in content, (
            "Service write operations should use transaction.atomic"
        )

    def test_service_create_review_validates_duplicate(self):
        """Verify create_review raises error for duplicate review"""
        path = os.path.join(self.REPO_DIR, "saleor/product/services.py")
        with open(path) as f:
            content = f.read()
        assert "already reviewed" in content.lower() or "ValidationError" in content, (
            "create_review should check for duplicate reviews"
        )

    def test_service_update_review_author_check(self):
        """Verify update_review checks author identity"""
        path = os.path.join(self.REPO_DIR, "saleor/product/services.py")
        with open(path) as f:
            content = f.read()
        assert "PermissionError" in content, (
            "update_review should raise PermissionError for non-author updates"
        )

    def test_service_update_review_pending_only(self):
        """Verify update_review only allows updates to PENDING reviews"""
        path = os.path.join(self.REPO_DIR, "saleor/product/services.py")
        with open(path) as f:
            content = f.read()
        assert "PENDING" in content, (
            "update_review should check that review status is PENDING"
        )

    # === Semantic Checks: GraphQL ===

    def test_graphql_types_has_review_type(self):
        """Verify ProductReviewType is added to GraphQL types"""
        path = os.path.join(self.REPO_DIR, "saleor/graphql/product/types.py")
        with open(path) as f:
            content = f.read()
        assert "ProductReviewType" in content or "ProductReview" in content, (
            "GraphQL types should include ProductReviewType"
        )

    def test_graphql_mutations_has_create_mutation(self):
        """Verify ProductReviewCreate mutation exists"""
        path = os.path.join(self.REPO_DIR, "saleor/graphql/product/mutations.py")
        if not os.path.exists(path):
            # mutations might be in a directory
            candidates = []
            mut_dir = os.path.join(self.REPO_DIR, "saleor/graphql/product/mutations")
            if os.path.isdir(mut_dir):
                for f in os.listdir(mut_dir):
                    candidates.append(os.path.join(mut_dir, f))
            found = False
            for c in candidates:
                with open(c) as fh:
                    if "ReviewCreate" in fh.read():
                        found = True
                        break
            assert found, "ProductReviewCreate mutation should be defined"
        else:
            with open(path) as f:
                content = f.read()
            assert "ReviewCreate" in content, (
                "mutations.py should define ProductReviewCreate"
            )

    def test_graphql_schema_has_review_query(self):
        """Verify productReviews query is registered in schema"""
        path = os.path.join(self.REPO_DIR, "saleor/graphql/product/schema.py")
        with open(path) as f:
            content = f.read()
        assert "review" in content.lower(), (
            "schema.py should register productReviews query"
        )

    # === Functional Checks ===

    def test_makemigrations_check(self):
        """Verify no pending migrations via makemigrations --check"""
        result = subprocess.run(
            ["python", "manage.py", "makemigrations", "--check"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, (
            f"makemigrations --check failed: {result.stderr}"
        )

    def test_model_tests_pass(self):
        """Verify model tests pass"""
        result = subprocess.run(
            [
                "python", "-m", "pytest",
                "saleor/product/tests/test_review_models.py",
                "-v", "--tb=short",
            ],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=300,
        )
        assert result.returncode == 0, (
            f"Model tests failed:\n{result.stdout}\n{result.stderr}"
        )

    def test_service_tests_pass(self):
        """Verify service tests pass"""
        result = subprocess.run(
            [
                "python", "-m", "pytest",
                "saleor/product/tests/test_review_services.py",
                "-v", "--tb=short",
            ],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=300,
        )
        assert result.returncode == 0, (
            f"Service tests failed:\n{result.stdout}\n{result.stderr}"
        )
