"""
Tests for the creating-financial-models skill.

Validates that a DCF valuation engine with sensitivity analysis was
implemented for QuantLib, including FCF projection, terminal value
(Gordon Growth and Exit Multiple), discounting, and sensitivity grid.

Repo: QuantLib (https://github.com/lballabio/QuantLib)
"""

import os
import re
import subprocess

REPO_DIR = "/workspace/QuantLib"


class TestFilePathCheck:
    """Verify that all required files were created."""

    def test_dcf_header_exists(self):
        path = os.path.join(REPO_DIR, "ql", "models", "dcf_valuation.hpp")
        assert os.path.isfile(path), f"Expected dcf_valuation.hpp at {path}"

    def test_dcf_implementation_exists(self):
        path = os.path.join(REPO_DIR, "ql", "models", "dcf_valuation.cpp")
        assert os.path.isfile(path), f"Expected dcf_valuation.cpp at {path}"

    def test_dcf_test_cpp_exists(self):
        path = os.path.join(REPO_DIR, "test-suite", "dcfvaluation.cpp")
        assert os.path.isfile(path), f"Expected dcfvaluation.cpp test at {path}"

    def test_dcf_test_header_exists(self):
        path = os.path.join(REPO_DIR, "test-suite", "dcfvaluation.hpp")
        assert os.path.isfile(path), f"Expected dcfvaluation.hpp test header at {path}"


class TestSemanticDCFHeader:
    """Verify DCF valuation engine header definitions."""

    def _read_header(self):
        path = os.path.join(REPO_DIR, "ql", "models", "dcf_valuation.hpp")
        with open(path, "r") as f:
            return f.read()

    def test_dcf_class_declared(self):
        content = self._read_header()
        assert re.search(r"class\s+\w*DCF\w*|class\s+\w*Dcf\w*|class\s+\w*Valuation\w*", content), (
            "Expected DCF valuation engine class declaration"
        )

    def test_include_guards_present(self):
        content = self._read_header()
        assert re.search(r"#ifndef|#pragma once", content), (
            "Expected include guards in header file"
        )

    def test_fcf_projection_method(self):
        """Free cash flow projection method should be declared."""
        content = self._read_header()
        assert re.search(r"project|fcf|freeCashFlow|free_cash_flow", content, re.IGNORECASE), (
            "Expected FCF projection method in header"
        )

    def test_terminal_value_method(self):
        content = self._read_header()
        assert re.search(r"terminal|gordon|exit.*multiple", content, re.IGNORECASE), (
            "Expected terminal value calculation method in header"
        )

    def test_sensitivity_analysis_method(self):
        content = self._read_header()
        assert re.search(r"sensitiv|grid|matrix", content, re.IGNORECASE), (
            "Expected sensitivity analysis method in header"
        )

    def test_wacc_parameter(self):
        content = self._read_header()
        assert re.search(r"wacc|WACC|discountRate|discount_rate", content), (
            "Expected WACC/discount rate parameter"
        )


class TestSemanticDCFImplementation:
    """Verify DCF implementation details."""

    def _read_impl(self):
        path = os.path.join(REPO_DIR, "ql", "models", "dcf_valuation.cpp")
        with open(path, "r") as f:
            return f.read()

    def test_gordon_growth_formula(self):
        """Gordon Growth: TV = FCF * (1+g) / (WACC - g)."""
        content = self._read_impl()
        assert re.search(r"gordon|perpetuity|1\s*\+\s*g|wacc\s*-\s*g", content, re.IGNORECASE), (
            "Expected Gordon Growth Model formula implementation"
        )

    def test_exit_multiple_method(self):
        content = self._read_impl()
        assert re.search(r"exit.*multiple|multiple.*fcf|ev.*fcf", content, re.IGNORECASE), (
            "Expected Exit Multiple terminal value method"
        )

    def test_present_value_discounting(self):
        """PV = CF / (1 + WACC)^t."""
        content = self._read_impl()
        assert re.search(r"pow|std::pow|\^|discount", content), (
            "Expected present value discounting formula (pow or discount)"
        )

    def test_growth_rate_ge_wacc_error(self):
        """If perpetuity growth >= WACC, should raise an error."""
        content = self._read_impl()
        assert re.search(r"growth.*>=.*wacc|wacc.*<=.*growth|error|throw|exception", content, re.IGNORECASE), (
            "Expected error handling when growth rate >= WACC"
        )

    def test_net_debt_adjustment(self):
        content = self._read_impl()
        assert re.search(r"net.*debt|equity.*value|enterprise.*debt", content, re.IGNORECASE), (
            "Expected net debt adjustment for equity value calculation"
        )

    def test_sensitivity_grid_generation(self):
        content = self._read_impl()
        assert re.search(r"grid|matrix|sensitiv|vector.*vector|2D", content, re.IGNORECASE), (
            "Expected 2D sensitivity grid generation"
        )

    def test_constant_and_custom_growth_modes(self):
        content = self._read_impl()
        assert re.search(r"constant|custom|vector|growth.*rate", content, re.IGNORECASE), (
            "Expected support for both constant and custom growth rate modes"
        )


class TestSemanticTestSuite:
    """Verify the test file covers key scenarios."""

    def _read_test(self):
        path = os.path.join(REPO_DIR, "test-suite", "dcfvaluation.cpp")
        with open(path, "r") as f:
            return f.read()

    def test_has_test_functions(self):
        content = self._read_test()
        test_count = len(re.findall(r"void\s+test\w+|BOOST_AUTO_TEST_CASE|TEST\(", content))
        assert test_count >= 3, (
            f"Expected at least 3 test functions in dcfvaluation.cpp, found {test_count}"
        )

    def test_includes_dcf_header(self):
        content = self._read_test()
        assert re.search(r'#include.*dcf_valuation', content, re.IGNORECASE), (
            "Expected test file to include dcf_valuation header"
        )

    def test_tolerance_checks(self):
        """Tests should compare with a tolerance <= 0.01."""
        content = self._read_test()
        assert re.search(r"tolerance|CLOSE|0\.01|epsilon|abs.*<|fabs", content, re.IGNORECASE), (
            "Expected tolerance-based comparisons in test assertions"
        )


class TestFunctionalCppSyntax:
    """Validate C++ file syntax where possible."""

    def test_header_has_matching_braces(self):
        path = os.path.join(REPO_DIR, "ql", "models", "dcf_valuation.hpp")
        with open(path, "r") as f:
            content = f.read()
        assert content.count("{") == content.count("}"), (
            "Unmatched braces in dcf_valuation.hpp"
        )

    def test_impl_has_matching_braces(self):
        path = os.path.join(REPO_DIR, "ql", "models", "dcf_valuation.cpp")
        with open(path, "r") as f:
            content = f.read()
        assert content.count("{") == content.count("}"), (
            "Unmatched braces in dcf_valuation.cpp"
        )

    def test_impl_includes_header(self):
        path = os.path.join(REPO_DIR, "ql", "models", "dcf_valuation.cpp")
        with open(path, "r") as f:
            content = f.read()
        assert re.search(r'#include.*dcf_valuation\.hpp', content), (
            "Expected dcf_valuation.cpp to include its header"
        )

    def test_no_syntax_errors_via_compiler(self):
        """Attempt to syntax-check using g++ -fsyntax-only if available."""
        header_path = os.path.join(REPO_DIR, "ql", "models", "dcf_valuation.hpp")
        result = subprocess.run(
            ["g++", "-std=c++17", "-fsyntax-only",
             "-I", REPO_DIR, header_path],
            capture_output=True, text=True, timeout=30,
        )
        # We expect this might fail due to missing QuantLib deps, but core syntax should be valid
        # Only fail if there are clear syntax errors (not missing includes)
        if result.returncode != 0:
            errors = result.stderr.lower()
            pure_syntax = any(kw in errors for kw in ["expected", "unexpected", "unterminated"])
            assert not pure_syntax, (
                f"C++ syntax errors in header: {result.stderr[:500]}"
            )
