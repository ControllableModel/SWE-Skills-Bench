"""
Tests for the django-patterns skill.

Validates that a product review system with GraphQL API was implemented
in Saleor, including Review/ReviewVote models, GraphQL types/mutations/queries,
moderation workflow, purchase verification, and permission checks.

Repo: saleor (https://github.com/saleor/saleor)
"""

import ast
import os
import re
import subprocess

REPO_DIR = "/workspace/saleor"


class TestFilePathCheck:
    """Verify that all required files were created or modified."""

    def test_review_init_exists(self):
        path = os.path.join(REPO_DIR, "saleor", "review", "__init__.py")
        assert os.path.isfile(path), f"Expected review app __init__.py at {path}"

    def test_review_models_exists(self):
        path = os.path.join(REPO_DIR, "saleor", "review", "models.py")
        assert os.path.isfile(path), f"Expected review models at {path}"

    def test_review_migration_exists(self):
        migration_dir = os.path.join(REPO_DIR, "saleor", "review", "migrations")
        assert os.path.isdir(migration_dir), f"Expected migrations directory at {migration_dir}"
        migrations = [f for f in os.listdir(migration_dir) if f.startswith("0001")]
        assert len(migrations) > 0, "Expected initial migration 0001_initial.py"

    def test_graphql_review_types_exists(self):
        path = os.path.join(REPO_DIR, "saleor", "graphql", "review", "types.py")
        assert os.path.isfile(path), f"Expected GraphQL types at {path}"

    def test_graphql_review_mutations_exists(self):
        path = os.path.join(REPO_DIR, "saleor", "graphql", "review", "mutations.py")
        assert os.path.isfile(path), f"Expected GraphQL mutations at {path}"

    def test_graphql_review_resolvers_exists(self):
        path = os.path.join(REPO_DIR, "saleor", "graphql", "review", "resolvers.py")
        assert os.path.isfile(path), f"Expected GraphQL resolvers at {path}"

    def test_graphql_review_schema_exists(self):
        path = os.path.join(REPO_DIR, "saleor", "graphql", "review", "schema.py")
        assert os.path.isfile(path), f"Expected GraphQL schema at {path}"


class TestSemanticReviewModel:
    """Verify the Review model has correct fields, constraints, and indexes."""

    def _read_models(self):
        path = os.path.join(REPO_DIR, "saleor", "review", "models.py")
        with open(path, "r") as f:
            return f.read()

    def test_review_class_defined(self):
        content = self._read_models()
        assert re.search(r"class\s+Review\b", content), (
            "Expected Review model class in models.py"
        )

    def test_review_vote_class_defined(self):
        content = self._read_models()
        assert re.search(r"class\s+ReviewVote\b", content), (
            "Expected ReviewVote model class in models.py"
        )

    def test_review_rating_field(self):
        content = self._read_models()
        assert re.search(r"PositiveSmallIntegerField|rating", content), (
            "Expected rating field (PositiveSmallIntegerField) in Review model"
        )

    def test_review_status_choices(self):
        """Status field should have PENDING, APPROVED, REJECTED choices."""
        content = self._read_models()
        for status in ["PENDING", "APPROVED", "REJECTED"]:
            assert status in content, f"Expected status choice '{status}' in Review model"

    def test_unique_constraint_product_user(self):
        """One review per user per product — unique constraint on (product, user)."""
        content = self._read_models()
        assert re.search(r"unique_together|UniqueConstraint|unique.*product.*user", content, re.IGNORECASE), (
            "Expected unique constraint on (product, user) in Review model"
        )

    def test_rating_check_constraint(self):
        """Rating must be between 1 and 5 — database check constraint."""
        content = self._read_models()
        assert re.search(r"CheckConstraint|check.*rating|validators", content, re.IGNORECASE), (
            "Expected check constraint for rating range (1-5)"
        )

    def test_review_vote_unique_constraint(self):
        """One vote per user per review — unique constraint on (review, user)."""
        content = self._read_models()
        # Look for unique constraint on review vote
        assert re.search(
            r"unique_together|UniqueConstraint", content
        ), "Expected unique constraint on (review, user) in ReviewVote model"

    def test_review_product_foreign_key(self):
        content = self._read_models()
        assert re.search(r"ForeignKey.*Product|product.*ForeignKey", content, re.DOTALL), (
            "Expected product ForeignKey in Review model"
        )

    def test_review_user_foreign_key(self):
        content = self._read_models()
        assert re.search(r"ForeignKey.*User|user.*ForeignKey", content, re.DOTALL), (
            "Expected user ForeignKey in Review model"
        )


class TestSemanticGraphQLMutations:
    """Verify GraphQL mutations are defined correctly."""

    def _read_mutations(self):
        path = os.path.join(REPO_DIR, "saleor", "graphql", "review", "mutations.py")
        with open(path, "r") as f:
            return f.read()

    def test_review_create_mutation(self):
        content = self._read_mutations()
        assert re.search(r"class\s+ReviewCreate\b", content), (
            "Expected ReviewCreate mutation class"
        )

    def test_review_update_mutation(self):
        content = self._read_mutations()
        assert re.search(r"class\s+ReviewUpdate\b", content), (
            "Expected ReviewUpdate mutation class"
        )

    def test_review_delete_mutation(self):
        content = self._read_mutations()
        assert re.search(r"class\s+ReviewDelete\b", content), (
            "Expected ReviewDelete mutation class"
        )

    def test_review_moderate_mutation(self):
        content = self._read_mutations()
        assert re.search(r"class\s+ReviewModerate\b", content), (
            "Expected ReviewModerate mutation class"
        )

    def test_review_vote_mutation(self):
        content = self._read_mutations()
        assert re.search(r"class\s+ReviewVote\b", content), (
            "Expected ReviewVote mutation class"
        )

    def test_purchase_verification_in_create(self):
        """ReviewCreate must check the user has a fulfilled order for the product."""
        content = self._read_mutations()
        assert re.search(r"FULFILLED|fulfilled|order.*product|purchase", content, re.IGNORECASE), (
            "Expected purchase verification logic in ReviewCreate mutation"
        )

    def test_status_reset_on_author_edit(self):
        """ReviewUpdate should reset status to PENDING when author edits."""
        content = self._read_mutations()
        assert re.search(r"PENDING|pending|status.*reset|reset.*status", content, re.IGNORECASE), (
            "Expected status reset to PENDING logic in ReviewUpdate"
        )


class TestSemanticGraphQLTypes:
    """Verify GraphQL types and computed fields."""

    def _read_types(self):
        path = os.path.join(REPO_DIR, "saleor", "graphql", "review", "types.py")
        with open(path, "r") as f:
            return f.read()

    def test_review_graphql_type(self):
        content = self._read_types()
        assert re.search(r"class\s+Review\b|ReviewType\b", content), (
            "Expected Review GraphQL type definition"
        )

    def test_helpful_count_computed_field(self):
        content = self._read_types()
        assert re.search(r"helpful.count|helpful_count|helpfulCount", content, re.IGNORECASE), (
            "Expected helpfulCount computed field in Review GraphQL type"
        )

    def test_not_helpful_count_computed_field(self):
        content = self._read_types()
        assert re.search(
            r"not.helpful.count|not_helpful_count|notHelpfulCount", content, re.IGNORECASE
        ), "Expected notHelpfulCount computed field in Review GraphQL type"


class TestSemanticGraphQLSchema:
    """Verify schema registration and query definitions."""

    def _read_schema(self):
        path = os.path.join(REPO_DIR, "saleor", "graphql", "review", "schema.py")
        with open(path, "r") as f:
            return f.read()

    def test_review_queries_class(self):
        content = self._read_schema()
        assert re.search(r"class\s+ReviewQueries\b", content), (
            "Expected ReviewQueries class in review/schema.py"
        )

    def test_review_mutations_class(self):
        content = self._read_schema()
        assert re.search(r"class\s+ReviewMutations\b", content), (
            "Expected ReviewMutations class in review/schema.py"
        )

    def test_root_schema_includes_reviews(self):
        """Root schema.py should import and register review queries/mutations."""
        path = os.path.join(REPO_DIR, "saleor", "graphql", "schema.py")
        with open(path, "r") as f:
            content = f.read()
        assert re.search(r"review|Review", content), (
            "Expected review module imported in root graphql schema.py"
        )


class TestSemanticInstalledApps:
    """Verify the review app is registered in Django settings."""

    def test_review_in_installed_apps(self):
        settings_path = os.path.join(REPO_DIR, "saleor", "settings.py")
        with open(settings_path, "r") as f:
            content = f.read()
        assert re.search(r"saleor\.review", content), (
            "Expected 'saleor.review' in INSTALLED_APPS in settings.py"
        )


class TestFunctionalPythonSyntax:
    """Validate Python files have correct syntax."""

    def _check_syntax(self, filepath):
        with open(filepath, "r") as f:
            source = f.read()
        ast.parse(source)

    def test_models_syntax(self):
        self._check_syntax(os.path.join(REPO_DIR, "saleor", "review", "models.py"))

    def test_mutations_syntax(self):
        self._check_syntax(os.path.join(REPO_DIR, "saleor", "graphql", "review", "mutations.py"))

    def test_types_syntax(self):
        self._check_syntax(os.path.join(REPO_DIR, "saleor", "graphql", "review", "types.py"))

    def test_resolvers_syntax(self):
        self._check_syntax(os.path.join(REPO_DIR, "saleor", "graphql", "review", "resolvers.py"))

    def test_schema_syntax(self):
        self._check_syntax(os.path.join(REPO_DIR, "saleor", "graphql", "review", "schema.py"))


class TestFunctionalDjangoValidation:
    """Validate Django-specific integration points."""

    def test_django_check_no_errors(self):
        """Run Django system checks to detect configuration errors."""
        result = subprocess.run(
            ["python", "-c", "import django; django.setup(); from django.core.management import call_command; call_command('check', '--deploy', verbosity=0)"],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=60,
            env={**os.environ, "DJANGO_SETTINGS_MODULE": "saleor.settings"},
        )
        # Warnings are acceptable; only hard errors (non-zero exit with specific issues) fail
        # Note: --deploy may produce warnings; we mainly check it doesn't crash
        assert result.returncode == 0 or "SystemCheckError" not in result.stderr, (
            f"Django system check failed: {result.stderr[:500]}"
        )

    def test_models_import_django_models(self):
        path = os.path.join(REPO_DIR, "saleor", "review", "models.py")
        with open(path, "r") as f:
            content = f.read()
        assert re.search(r"from django\.db import models|from django\.db\.models import", content), (
            "Expected Django models import in review/models.py"
        )

    def test_self_vote_prevention_logic(self):
        """ReviewVote mutation should prevent users from voting on their own review."""
        path = os.path.join(REPO_DIR, "saleor", "graphql", "review", "mutations.py")
        with open(path, "r") as f:
            content = f.read()
        assert re.search(r"own.review|self.vote|user.*==.*review.*user|author", content, re.IGNORECASE), (
            "Expected self-vote prevention logic in ReviewVote mutation"
        )
