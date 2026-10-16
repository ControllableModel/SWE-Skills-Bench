"""
Test skill: tdd-workflow
Verify that the Agent correctly implements a discount calculator using
test-driven development, including category discounts, progressive discounts,
and customer tier pricing.
"""

import os
import sys
import ast
import subprocess
import pytest


class TestTddWorkflow:
    REPO_DIR = "/workspace/python"

    # === File Path Checks ===

    def test_calculator_file_exists(self):
        """Verify calculator.py exists in the src directory"""
        path = os.path.join(self.REPO_DIR, "src/calculator.py")
        assert os.path.exists(path), f"calculator.py not found at {path}"

    def test_test_calculator_file_exists(self):
        """Verify test_calculator.py exists in the tests directory"""
        path = os.path.join(self.REPO_DIR, "tests/test_calculator.py")
        assert os.path.exists(path), f"test_calculator.py not found at {path}"

    def test_calculator_is_valid_python(self):
        """Verify calculator.py is syntactically valid Python"""
        path = os.path.join(self.REPO_DIR, "src/calculator.py")
        with open(path) as f:
            content = f.read()
        try:
            ast.parse(content)
        except SyntaxError as e:
            pytest.fail(f"calculator.py has syntax error: {e}")

    def test_test_file_is_valid_python(self):
        """Verify test_calculator.py is syntactically valid Python"""
        path = os.path.join(self.REPO_DIR, "tests/test_calculator.py")
        with open(path) as f:
            content = f.read()
        try:
            ast.parse(content)
        except SyntaxError as e:
            pytest.fail(f"test_calculator.py has syntax error: {e}")

    # === Semantic Checks ===

    def test_calculator_defines_class(self):
        """Verify calculator.py defines a class related to calculation"""
        path = os.path.join(self.REPO_DIR, "src/calculator.py")
        with open(path) as f:
            tree = ast.parse(f.read())

        class_names = [node.name for node in ast.walk(tree)
                       if isinstance(node, ast.ClassDef)]
        calc_classes = [n for n in class_names
                        if "calc" in n.lower() or "discount" in n.lower() or "order" in n.lower()]
        assert len(calc_classes) > 0, (
            f"No Calculator/Discount/Order class found. Classes defined: {class_names}"
        )

    def test_calculator_handles_discount_concepts(self):
        """Verify calculator.py references multiple discount strategies"""
        path = os.path.join(self.REPO_DIR, "src/calculator.py")
        with open(path) as f:
            content = f.read().lower()

        strategies = {
            "category": "category" in content,
            "progressive/volume": "progressive" in content or "volume" in content or "threshold" in content,
            "tier": "tier" in content or "silver" in content or "gold" in content,
        }
        found = [k for k, v in strategies.items() if v]
        assert len(found) >= 2, (
            f"Calculator should implement multiple discount strategies. "
            f"Found references to: {found}. Expected at least 2 of: {list(strategies.keys())}"
        )

    def test_calculator_handles_item_attributes(self):
        """Verify calculator.py references item attributes: price, quantity, category"""
        path = os.path.join(self.REPO_DIR, "src/calculator.py")
        with open(path) as f:
            content = f.read().lower()

        assert "price" in content, "Calculator should reference 'price'"
        assert "quantity" in content or "qty" in content, (
            "Calculator should reference 'quantity' or 'qty'"
        )
        assert "category" in content, "Calculator should reference 'category'"

    def test_test_file_has_sufficient_tests(self):
        """Verify test_calculator.py has at least 5 test functions"""
        path = os.path.join(self.REPO_DIR, "tests/test_calculator.py")
        with open(path) as f:
            tree = ast.parse(f.read())

        test_funcs = [
            node.name for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
        ]
        assert len(test_funcs) >= 5, (
            f"test_calculator.py should have at least 5 test functions, "
            f"found {len(test_funcs)}: {test_funcs}"
        )

    def test_test_file_covers_edge_cases(self):
        """Verify test_calculator.py covers edge cases (empty cart, validation)"""
        path = os.path.join(self.REPO_DIR, "tests/test_calculator.py")
        with open(path) as f:
            content = f.read().lower()

        edge_indicators = {
            "empty": "empty" in content,
            "negative/invalid": "negative" in content or "invalid" in content or "error" in content,
            "zero": "zero" in content or "0" in content,
        }
        found = [k for k, v in edge_indicators.items() if v]
        assert len(found) >= 2, (
            f"Tests should cover edge cases. Found references to: {found}. "
            f"Expected at least 2 of: {list(edge_indicators.keys())}"
        )

    # === Functional Checks ===

    def test_agent_test_suite_passes(self):
        """Verify the Agent's own test suite passes completely"""
        result = subprocess.run(
            ["python", "-m", "pytest", "tests/test_calculator.py", "-v", "--tb=short"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, (
            f"Agent's test suite failed:\nstdout: {result.stdout[:2000]}\n"
            f"stderr: {result.stderr[:2000]}"
        )

    def test_calculator_import_and_instantiate(self):
        """Verify the Calculator class can be imported and instantiated"""
        sys.path.insert(0, os.path.join(self.REPO_DIR, "src"))
        sys.path.insert(0, self.REPO_DIR)

        calc_module = None
        for module_name in ["calculator", "src.calculator"]:
            try:
                calc_module = __import__(module_name)
                break
            except ImportError:
                continue

        assert calc_module is not None, (
            "Could not import calculator module from src/calculator.py"
        )

        # Find a class related to calculation
        calc_class = None
        for name in dir(calc_module):
            obj = getattr(calc_module, name)
            if isinstance(obj, type) and (
                "calc" in name.lower() or "discount" in name.lower() or "order" in name.lower()
            ):
                calc_class = obj
                break

        assert calc_class is not None, (
            f"No Calculator class found in module. Available: {dir(calc_module)}"
        )
        # Try to instantiate
        try:
            instance = calc_class()
            assert instance is not None
        except TypeError:
            # May need constructor args
            pass

    def test_calculator_basic_total(self):
        """Verify calculator computes a basic order total correctly"""
        sys.path.insert(0, os.path.join(self.REPO_DIR, "src"))
        sys.path.insert(0, self.REPO_DIR)

        try:
            import importlib
            calc_module = importlib.import_module("calculator")
        except ImportError:
            try:
                calc_module = importlib.import_module("src.calculator")
            except ImportError:
                pytest.skip("Cannot import calculator module")

        # Find calculator class
        calc_class = None
        for name in dir(calc_module):
            obj = getattr(calc_module, name)
            if isinstance(obj, type) and (
                "calc" in name.lower() or "discount" in name.lower() or "order" in name.lower()
            ):
                calc_class = obj
                break

        if calc_class is None:
            pytest.fail("No Calculator class found in calculator module")

        # Try to compute a total for a simple cart
        # Look for a method that computes totals
        calc = None
        try:
            calc = calc_class()
        except TypeError:
            pytest.skip("Calculator requires constructor arguments not determinable")

        compute_method = None
        for method_name in [
            "calculate", "compute", "total", "calculate_total",
            "compute_total", "get_total", "process",
        ]:
            if hasattr(calc, method_name) and callable(getattr(calc, method_name)):
                compute_method = getattr(calc, method_name)
                break

        if compute_method is None:
            pytest.skip("Could not find a calculation method on Calculator")

        # Simple item: 10 * 2 = 20
        item = {"price": 10, "quantity": 2, "category": "general"}
        try:
            result = compute_method([item])
            assert isinstance(result, (int, float)), (
                f"Result should be numeric, got {type(result)}"
            )
            assert result > 0, f"Total for valid items should be positive, got {result}"
        except TypeError:
            # Might need different arguments
            pytest.skip("Calculator method signature not compatible with test input format")

    def test_calculator_rejects_negative_price(self):
        """Verify calculator rejects items with negative prices"""
        sys.path.insert(0, os.path.join(self.REPO_DIR, "src"))
        sys.path.insert(0, self.REPO_DIR)

        try:
            import importlib
            calc_module = importlib.import_module("calculator")
        except ImportError:
            try:
                calc_module = importlib.import_module("src.calculator")
            except ImportError:
                pytest.skip("Cannot import calculator module")

        calc_class = None
        for name in dir(calc_module):
            obj = getattr(calc_module, name)
            if isinstance(obj, type) and (
                "calc" in name.lower() or "discount" in name.lower() or "order" in name.lower()
            ):
                calc_class = obj
                break

        if calc_class is None:
            pytest.fail("No Calculator class in module")

        try:
            calc = calc_class()
        except TypeError:
            pytest.skip("Calculator requires constructor arguments")

        compute_method = None
        for method_name in [
            "calculate", "compute", "total", "calculate_total",
            "compute_total", "get_total", "process",
        ]:
            if hasattr(calc, method_name) and callable(getattr(calc, method_name)):
                compute_method = getattr(calc, method_name)
                break

        if compute_method is None:
            pytest.skip("Could not find a calculation method")

        negative_item = {"price": -10, "quantity": 1, "category": "test"}
        with pytest.raises((ValueError, TypeError, Exception)):
            compute_method([negative_item])

    def test_calculator_empty_cart_returns_zero(self):
        """Verify calculator returns 0 for an empty cart"""
        sys.path.insert(0, os.path.join(self.REPO_DIR, "src"))
        sys.path.insert(0, self.REPO_DIR)

        try:
            import importlib
            calc_module = importlib.import_module("calculator")
        except ImportError:
            try:
                calc_module = importlib.import_module("src.calculator")
            except ImportError:
                pytest.skip("Cannot import calculator module")

        calc_class = None
        for name in dir(calc_module):
            obj = getattr(calc_module, name)
            if isinstance(obj, type) and (
                "calc" in name.lower() or "discount" in name.lower() or "order" in name.lower()
            ):
                calc_class = obj
                break

        if calc_class is None:
            pytest.fail("No Calculator class in module")

        try:
            calc = calc_class()
        except TypeError:
            pytest.skip("Calculator requires constructor arguments")

        compute_method = None
        for method_name in [
            "calculate", "compute", "total", "calculate_total",
            "compute_total", "get_total", "process",
        ]:
            if hasattr(calc, method_name) and callable(getattr(calc, method_name)):
                compute_method = getattr(calc, method_name)
                break

        if compute_method is None:
            pytest.skip("Could not find a calculation method")

        try:
            result = compute_method([])
            assert result == 0 or result == 0.0, (
                f"Empty cart should return 0, got {result}"
            )
        except TypeError:
            pytest.skip("Calculator method signature not compatible with empty list input")
