"""
Test skill: django-patterns
Verify that the Agent correctly adds a Gift Card Template API resource
to the Saleor e-commerce platform following Django/DRF patterns.
"""

import os
import re
import ast
import sys
import subprocess
import pytest


class TestDjangoPatterns:
    REPO_DIR = "/workspace/saleor"

    MODELS = "saleor/giftcard/models.py"
    SERIALIZERS = "saleor/giftcard/serializers.py"
    VIEWS = "saleor/giftcard/views.py"
    URLS = "saleor/giftcard/urls.py"
    PERMISSIONS = "saleor/giftcard/permissions.py"
    TESTS = "saleor/giftcard/tests/test_gift_card_template_api.py"

    def _read_file(self, rel_path):
        filepath = os.path.join(self.REPO_DIR, rel_path)
        with open(filepath) as f:
            return f.read()

    # === File Path Checks ===

    def test_models_file_exists(self):
        """Verify giftcard/models.py exists"""
        filepath = os.path.join(self.REPO_DIR, self.MODELS)
        assert os.path.exists(filepath), f"models.py not found at {filepath}"

    def test_serializers_file_exists(self):
        """Verify giftcard/serializers.py exists"""
        filepath = os.path.join(self.REPO_DIR, self.SERIALIZERS)
        assert os.path.exists(filepath), f"serializers.py not found at {filepath}"

    def test_views_file_exists(self):
        """Verify giftcard/views.py exists"""
        filepath = os.path.join(self.REPO_DIR, self.VIEWS)
        assert os.path.exists(filepath), f"views.py not found at {filepath}"

    def test_urls_file_exists(self):
        """Verify giftcard/urls.py exists"""
        filepath = os.path.join(self.REPO_DIR, self.URLS)
        assert os.path.exists(filepath), f"urls.py not found at {filepath}"

    def test_tests_file_exists(self):
        """Verify gift card template test file exists"""
        filepath = os.path.join(self.REPO_DIR, self.TESTS)
        assert os.path.exists(filepath), f"Test file not found at {filepath}"

    # === Semantic Checks ===

    def test_model_defines_giftcardtemplate(self):
        """Verify GiftCardTemplate model is defined with required fields"""
        content = self._read_file(self.MODELS)
        assert "GiftCardTemplate" in content, \
            "GiftCardTemplate model not defined in models.py"
        for field in ["name", "denominations", "currency", "is_active"]:
            assert field in content, \
                f"GiftCardTemplate missing field: {field}"

    def test_model_has_json_field_for_denominations(self):
        """Verify denominations field uses JSONField for storing decimal list"""
        content = self._read_file(self.MODELS)
        has_json = bool(re.search(r'JSONField|jsonb|ArrayField', content))
        assert has_json, \
            "Denominations should use JSONField or ArrayField"

    def test_serializer_validates_denominations(self):
        """Verify serializer validates denominations as non-empty positive decimals"""
        content = self._read_file(self.SERIALIZERS)
        assert "denominations" in content, \
            "Serializer missing denominations field handling"
        has_validation = bool(re.search(
            r'(validate_denominations|validate.*denomination|positive|> 0|<= 0|min_value)',
            content,
            re.IGNORECASE,
        ))
        assert has_validation, \
            "Serializer missing denominations validation (positive, non-empty)"

    def test_serializer_validates_currency(self):
        """Verify serializer validates currency as valid ISO 4217 code"""
        content = self._read_file(self.SERIALIZERS)
        has_currency_validation = bool(re.search(
            r'(currency|ISO|4217|validate_currency|[A-Z]{3})',
            content,
        ))
        assert has_currency_validation, \
            "Serializer missing currency validation"

    def test_views_define_viewset_with_crud(self):
        """Verify views define a ViewSet with list, create, update, deactivate"""
        content = self._read_file(self.VIEWS)
        assert "ViewSet" in content or "APIView" in content, \
            "Views missing ViewSet or APIView class"
        assert "deactivate" in content, \
            "Views missing deactivate action"

    def test_permissions_class_defined(self):
        """Verify custom permission class for manage_gift_cards exists"""
        content = self._read_file(self.PERMISSIONS)
        assert "Permission" in content, \
            "Permissions file missing Permission class"
        assert "manage_gift_cards" in content or "gift_card" in content.lower(), \
            "Permission class missing manage_gift_cards reference"

    def test_urls_register_gift_card_template_routes(self):
        """Verify URLs register gift-card-templates endpoints"""
        content = self._read_file(self.URLS)
        assert "gift-card-template" in content or "gift_card_template" in content, \
            "URLs missing gift card template route registration"

    # === Functional Checks ===

    def test_models_valid_python(self):
        """Verify models.py is valid Python syntax"""
        filepath = os.path.join(self.REPO_DIR, self.MODELS)
        with open(filepath) as f:
            try:
                ast.parse(f.read())
            except SyntaxError as e:
                pytest.fail(f"models.py has syntax error: {e}")

    def test_serializers_valid_python(self):
        """Verify serializers.py is valid Python syntax"""
        filepath = os.path.join(self.REPO_DIR, self.SERIALIZERS)
        with open(filepath) as f:
            try:
                ast.parse(f.read())
            except SyntaxError as e:
                pytest.fail(f"serializers.py has syntax error: {e}")

    def test_views_valid_python(self):
        """Verify views.py is valid Python syntax"""
        filepath = os.path.join(self.REPO_DIR, self.VIEWS)
        with open(filepath) as f:
            try:
                ast.parse(f.read())
            except SyntaxError as e:
                pytest.fail(f"views.py has syntax error: {e}")

    def test_deactivate_action_returns_error_on_inactive(self):
        """Verify deactivate action handles already-inactive template with 400/409"""
        content = self._read_file(self.VIEWS)
        has_already_inactive_check = bool(re.search(
            r'(is_active.*False|already.*inactive|400|409|Conflict|bad_request)',
            content,
            re.IGNORECASE,
        ))
        assert has_already_inactive_check, \
            "Deactivate action missing check for already-inactive template"

    def test_tests_cover_crud_and_validation(self):
        """Verify test file covers CRUD operations and validation errors"""
        content = self._read_file(self.TESTS)
        test_tree = ast.parse(content)
        test_funcs = [
            node.name for node in ast.walk(test_tree)
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
        ]
        assert len(test_funcs) >= 5, \
            f"Expected at least 5 test functions, found {len(test_funcs)}"
        content_lower = content.lower()
        assert "create" in content_lower or "post" in content_lower, \
            "Tests missing create operation coverage"
        assert "deactivate" in content_lower, \
            "Tests missing deactivate action coverage"
