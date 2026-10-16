"""
Test skill: security-review
Verify that the Agent correctly implements security hardening for Baby Buddy's
user input, authentication, and security headers.
"""

import os
import sys
import ast
import subprocess
import pytest


class TestSecurityReview:
    REPO_DIR = "/workspace/babybuddy"

    # === File Path Checks ===

    def test_security_middleware_file_exists(self):
        """Verify that the security middleware file was created"""
        path = os.path.join(self.REPO_DIR, "babybuddy/middleware/security.py")
        assert os.path.exists(path), f"security.py not found at {path}"
        with open(path) as f:
            ast.parse(f.read())

    def test_validators_file_exists(self):
        """Verify that the API validators file was created"""
        path = os.path.join(self.REPO_DIR, "api/validators.py")
        assert os.path.exists(path), f"validators.py not found at {path}"
        with open(path) as f:
            ast.parse(f.read())

    def test_auth_hardening_file_exists(self):
        """Verify that the auth hardening file was created"""
        path = os.path.join(self.REPO_DIR, "babybuddy/auth_hardening.py")
        assert os.path.exists(path), f"auth_hardening.py not found at {path}"
        with open(path) as f:
            ast.parse(f.read())

    def test_security_tests_file_exists(self):
        """Verify that the security tests file was created"""
        path = os.path.join(self.REPO_DIR, "tests/test_security.py")
        assert os.path.exists(path), f"test_security.py not found at {path}"
        with open(path) as f:
            ast.parse(f.read())

    # === Semantic Checks ===

    def test_input_validator_class_defined(self):
        """Verify InputValidator class exists with expected interface"""
        sys.path.insert(0, self.REPO_DIR)
        try:
            from api.validators import InputValidator
            assert callable(InputValidator), "InputValidator should be a class"
        finally:
            sys.path.pop(0)
            for m in list(sys.modules.keys()):
                if "api.validators" in m or "validators" in m:
                    del sys.modules[m]

    def test_safe_query_builder_class_defined(self):
        """Verify SafeQueryBuilder class exists and has reject logic"""
        validators_path = os.path.join(self.REPO_DIR, "api/validators.py")
        with open(validators_path) as f:
            content = f.read()
        assert "SafeQueryBuilder" in content, "SafeQueryBuilder class not found in validators.py"
        assert "SecurityError" in content or "security" in content.lower(), \
            "SafeQueryBuilder should reference SecurityError for rejected queries"

    def test_password_policy_defined(self):
        """Verify password policy enforcement is implemented"""
        auth_path = os.path.join(self.REPO_DIR, "babybuddy/auth_hardening.py")
        with open(auth_path) as f:
            content = f.read()
        # Must check for password validation logic
        assert "PasswordPolicyError" in content or "password" in content.lower(), \
            "auth_hardening.py should define password policy"
        # Check for minimum requirements
        has_length_check = "10" in content or "min" in content.lower()
        has_upper_check = "upper" in content.lower() or "A-Z" in content
        has_digit_check = "digit" in content.lower() or "0-9" in content
        assert has_length_check, "Password policy should check minimum length (10)"
        assert has_upper_check or has_digit_check, \
            "Password policy should check character variety (uppercase, digits, etc.)"

    def test_lockout_functions_defined(self):
        """Verify account lockout functions are defined"""
        auth_path = os.path.join(self.REPO_DIR, "babybuddy/auth_hardening.py")
        with open(auth_path) as f:
            content = f.read()
        assert "check_lockout" in content, "check_lockout function not found"
        assert "record_failed_attempt" in content, \
            "record_failed_attempt function not found"

    def test_security_headers_in_middleware(self):
        """Verify security headers are configured in the middleware"""
        middleware_path = os.path.join(self.REPO_DIR, "babybuddy/middleware/security.py")
        with open(middleware_path) as f:
            content = f.read()
        required_headers = [
            "X-Content-Type-Options",
            "X-Frame-Options",
            "X-XSS-Protection",
            "Content-Security-Policy",
            "Referrer-Policy",
        ]
        for header in required_headers:
            assert header in content, \
                f"Security middleware missing header: {header}"

    def test_hsts_conditional_on_ssl(self):
        """Verify HSTS header is conditional on SSL configuration"""
        middleware_path = os.path.join(self.REPO_DIR, "babybuddy/middleware/security.py")
        with open(middleware_path) as f:
            content = f.read()
        assert "Strict-Transport-Security" in content, \
            "HSTS header not found in middleware"
        assert "SSL" in content.upper() or "SECURE_SSL_REDIRECT" in content, \
            "HSTS should be conditional on SSL configuration"

    # === Functional Checks ===

    def _setup_sys_path(self):
        """Helper to add REPO_DIR to sys.path"""
        if self.REPO_DIR not in sys.path:
            sys.path.insert(0, self.REPO_DIR)

    def _cleanup_modules(self, *patterns):
        """Helper to remove imported modules matching patterns"""
        for mod_name in list(sys.modules.keys()):
            if any(p in mod_name for p in patterns):
                del sys.modules[mod_name]

    def test_input_validator_rejects_xss_script(self):
        """Verify InputValidator rejects strings containing <script> tags"""
        self._setup_sys_path()
        try:
            from api.validators import InputValidator
            validator = InputValidator()
            xss_inputs = [
                "<script>alert('xss')</script>",
                "Hello<script>evil()</script>world",
                "<SCRIPT>document.cookie</SCRIPT>",
            ]
            for xss_input in xss_inputs:
                with pytest.raises(Exception) as exc_info:
                    validator.validate_string("name", xss_input)
                msg = str(exc_info.value).lower()
                assert "xss" in msg or "script" in msg or "invalid" in msg or "reject" in msg, \
                    f"XSS rejection should have descriptive message, got: {exc_info.value}"
        finally:
            self._cleanup_modules("api", "validators")

    def test_input_validator_rejects_null_bytes(self):
        """Verify InputValidator rejects strings with null bytes"""
        self._setup_sys_path()
        try:
            from api.validators import InputValidator
            validator = InputValidator()
            with pytest.raises(Exception) as exc_info:
                validator.validate_string("name", "hello\x00world")
            msg = str(exc_info.value).lower()
            assert "null" in msg or "byte" in msg or "invalid" in msg, \
                f"Null byte rejection message unclear: {exc_info.value}"
        finally:
            self._cleanup_modules("api", "validators")

    def test_input_validator_sanitizes_html_entities(self):
        """Verify InputValidator sanitizes HTML entities in text fields"""
        self._setup_sys_path()
        try:
            from api.validators import InputValidator
            validator = InputValidator()
            # Sanitize should convert < > & " to entities
            # The validator might either reject or sanitize - test sanitization path
            try:
                result = validator.sanitize_html("Tom & Jerry <friends>")
                assert "&lt;" in result, f"< should be converted to &lt;, got: {result}"
                assert "&gt;" in result, f"> should be converted to &gt;, got: {result}"
                assert "&amp;" in result, f"& should be converted to &amp;, got: {result}"
            except AttributeError:
                # If sanitize_html is not a separate method, check if validate does it
                pytest.skip("sanitize_html method not found, sanitization may be inline")
        finally:
            self._cleanup_modules("api", "validators")

    def test_input_validator_rejects_nan_infinity(self):
        """Verify InputValidator rejects NaN and Infinity numeric values"""
        self._setup_sys_path()
        try:
            from api.validators import InputValidator
            validator = InputValidator()
            invalid_values = [float("nan"), float("inf"), float("-inf")]
            for val in invalid_values:
                with pytest.raises(Exception) as exc_info:
                    validator.validate_numeric("amount", val)
                msg = str(exc_info.value).lower()
                assert "nan" in msg or "infinity" in msg or "invalid" in msg or "finite" in msg, \
                    f"NaN/Infinity rejection message unclear: {exc_info.value}"
        finally:
            self._cleanup_modules("api", "validators")

    def test_safe_query_builder_rejects_unlisted_fields(self):
        """Verify SafeQueryBuilder rejects fields not in the whitelist"""
        self._setup_sys_path()
        try:
            from api.validators import SafeQueryBuilder
            allowed_fields = ["name", "age", "created_at"]
            allowed_operators = ["exact", "contains", "gt", "lt"]
            builder = SafeQueryBuilder(
                allowed_fields=allowed_fields,
                allowed_operators=allowed_operators,
            )
            with pytest.raises(Exception) as exc_info:
                builder.build_query({"password__regex": ".*"})
            msg = str(exc_info.value).lower()
            assert "password" in msg or "not allowed" in msg or "whitelist" in msg or "security" in msg, \
                f"Should reject unwhitelisted field with clear message: {exc_info.value}"
        finally:
            self._cleanup_modules("api", "validators")

    def test_password_policy_rejects_short_password(self):
        """Verify password policy rejects passwords shorter than 10 characters"""
        self._setup_sys_path()
        try:
            from babybuddy.auth_hardening import PasswordPolicyError
            # Try multiple import paths for the validation function
            try:
                from babybuddy.auth_hardening import validate_password
            except ImportError:
                from babybuddy.auth_hardening import check_password_policy as validate_password

            with pytest.raises(PasswordPolicyError) as exc_info:
                validate_password("short")
            msg = str(exc_info.value).lower()
            assert "length" in msg or "character" in msg or "minimum" in msg or "10" in msg, \
                f"Policy error should list specific failures: {exc_info.value}"
        finally:
            self._cleanup_modules("babybuddy", "auth_hardening")

    def test_account_lockout_after_5_failures(self):
        """Verify account locks after 5 consecutive failed login attempts"""
        self._setup_sys_path()
        try:
            from babybuddy.auth_hardening import check_lockout, record_failed_attempt
            test_user = "test_lockout_user_12345"

            # Ensure user starts unlocked
            assert not check_lockout(test_user), \
                "User should not be locked out initially"

            # Record 5 failed attempts
            for i in range(5):
                record_failed_attempt(test_user)

            # User should be locked out after 5 failures
            assert check_lockout(test_user), \
                "User should be locked out after 5 failed attempts"
        finally:
            self._cleanup_modules("babybuddy", "auth_hardening")

    def test_agent_security_tests_pass(self):
        """Verify the Agent's own security tests pass"""
        test_path = os.path.join(self.REPO_DIR, "tests/test_security.py")
        if not os.path.exists(test_path):
            pytest.skip("Agent's test_security.py not found")
        result = subprocess.run(
            ["python", "-m", "pytest", test_path, "-v", "--tb=short", "-x"],
            cwd=self.REPO_DIR,
            capture_output=True, text=True, timeout=120
        )
        assert result.returncode == 0, \
            f"Agent's security tests failed:\n{result.stdout[:2000]}\n{result.stderr[:500]}"
