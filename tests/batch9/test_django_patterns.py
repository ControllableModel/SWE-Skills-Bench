"""
Test skill: django-patterns
Verify that the Agent adds a ProductReview feature to Saleor including model,
GraphQL types/mutations, dataloader, Celery task, and signal.
"""

import os
import subprocess
import ast
import re
import pytest


class TestDjangoPatterns:
    REPO_DIR = "/workspace/saleor"

    # === File Path Checks ===

    def test_review_model_file_exists(self):
        """Verify ProductReview model file exists"""
        found = False
        for root, dirs, files in os.walk(os.path.join(self.REPO_DIR, "saleor")):
            for f in files:
                if "review" in f.lower() and f.endswith(".py"):
                    found = True
                    break
            if found:
                break
        assert found, "ProductReview model file not found"

    # === Semantic Checks ===

    def test_product_review_model_defined(self):
        """Verify ProductReview Django model is defined with required fields"""
        model_content = ""
        for root, dirs, files in os.walk(os.path.join(self.REPO_DIR, "saleor")):
            for f in files:
                if "review" in f.lower() and "model" in f.lower() and f.endswith(".py"):
                    with open(os.path.join(root, f)) as fh:
                        model_content += fh.read()
                elif f == "models.py" and "review" in root.lower():
                    with open(os.path.join(root, f)) as fh:
                        model_content += fh.read()
        if not model_content:
            # Search more broadly
            for root, dirs, files in os.walk(os.path.join(self.REPO_DIR, "saleor")):
                for f in files:
                    if f.endswith(".py"):
                        fpath = os.path.join(root, f)
                        with open(fpath) as fh:
                            content = fh.read()
                        if "ProductReview" in content and "class " in content:
                            model_content = content
                            break
                if model_content:
                    break
        assert "ProductReview" in model_content, "ProductReview class not defined"
        assert "models.Model" in model_content or "Model)" in model_content, (
            "ProductReview does not extend Django Model"
        )

    def test_product_review_has_required_fields(self):
        """Verify ProductReview has rating, title, content, product FK"""
        all_content = ""
        for root, dirs, files in os.walk(os.path.join(self.REPO_DIR, "saleor")):
            for f in files:
                if f.endswith(".py"):
                    fpath = os.path.join(root, f)
                    with open(fpath) as fh:
                        content = fh.read()
                    if "ProductReview" in content:
                        all_content += content
        assert "rating" in all_content.lower(), "ProductReview missing rating field"
        assert "product" in all_content.lower(), "ProductReview missing product reference"

    def test_graphql_type_defined(self):
        """Verify GraphQL type for ProductReview exists"""
        found = False
        for root, dirs, files in os.walk(os.path.join(self.REPO_DIR, "saleor")):
            if "graphql" in root.lower():
                for f in files:
                    if f.endswith(".py"):
                        fpath = os.path.join(root, f)
                        with open(fpath) as fh:
                            content = fh.read()
                        if "ProductReview" in content and ("ObjectType" in content or "graphene" in content or "Type" in content):
                            found = True
                            break
            if found:
                break
        assert found, "GraphQL type for ProductReview not found"

    def test_graphql_mutations_defined(self):
        """Verify GraphQL mutations for ProductReview exist"""
        mutation_content = ""
        for root, dirs, files in os.walk(os.path.join(self.REPO_DIR, "saleor")):
            if "graphql" in root.lower():
                for f in files:
                    if ("mutation" in f.lower() or "review" in f.lower()) and f.endswith(".py"):
                        fpath = os.path.join(root, f)
                        with open(fpath) as fh:
                            content = fh.read()
                        if "Review" in content:
                            mutation_content += content
        has_create = "Create" in mutation_content or "create" in mutation_content
        assert has_create, "No create mutation for ProductReview found"

    def test_dataloader_defined(self):
        """Verify dataloader for ProductReview exists"""
        found = False
        for root, dirs, files in os.walk(os.path.join(self.REPO_DIR, "saleor")):
            for f in files:
                if f.endswith(".py"):
                    fpath = os.path.join(root, f)
                    try:
                        with open(fpath) as fh:
                            content = fh.read()
                        if "dataloader" in content.lower() and "review" in content.lower():
                            found = True
                            break
                    except (UnicodeDecodeError, PermissionError):
                        continue
            if found:
                break
        assert found, "DataLoader for ProductReview not found"

    def test_celery_task_exists(self):
        """Verify Celery task related to reviews exists"""
        found = False
        for root, dirs, files in os.walk(os.path.join(self.REPO_DIR, "saleor")):
            for f in files:
                if f.endswith(".py") and ("task" in f.lower() or "review" in f.lower()):
                    fpath = os.path.join(root, f)
                    with open(fpath) as fh:
                        content = fh.read()
                    if "@" in content and ("task" in content.lower() or "celery" in content.lower()) and "review" in content.lower():
                        found = True
                        break
            if found:
                break
        assert found, "Celery task for reviews not found"

    # === Functional Checks ===

    def test_review_model_file_parses(self):
        """Verify review model Python file has valid syntax"""
        for root, dirs, files in os.walk(os.path.join(self.REPO_DIR, "saleor")):
            for f in files:
                if f.endswith(".py") and "review" in f.lower():
                    fpath = os.path.join(root, f)
                    with open(fpath) as fh:
                        source = fh.read()
                    if "ProductReview" in source:
                        try:
                            ast.parse(source)
                        except SyntaxError as e:
                            pytest.fail(f"Syntax error in {fpath}: {e}")
                        return
        pytest.skip("No ProductReview model file found to parse")

    def test_django_check_passes(self):
        """Verify Django system check passes"""
        result = subprocess.run(
            ["python", "-m", "django", "check"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=120,
            env={**os.environ, "DJANGO_SETTINGS_MODULE": "saleor.settings"},
        )
        if result.returncode != 0:
            assert "review" not in result.stderr.lower(), (
                f"Django check errors related to reviews: {result.stderr[:500]}"
            )

    def test_migrations_makeable(self):
        """Verify Django can create migrations for the review model"""
        result = subprocess.run(
            ["python", "manage.py", "makemigrations", "--check", "--dry-run"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=120,
            env={**os.environ, "DJANGO_SETTINGS_MODULE": "saleor.settings"},
        )
        # returncode 0 means no pending migrations (they've been created already)
        # returncode 1 means there are pending migrations that need creating
        assert result.returncode in (0, 1), (
            f"makemigrations failed unexpectedly: {result.stderr[:500]}"
        )
