"""
Test skill: creating-financial-models
Verify that the Agent correctly implements a DCF valuation engine
in QuantLib including C++ header/impl files, NPV computation,
sensitivity analysis, term-structure discounting, and CMake integration.
"""

import os
import re
import subprocess
import pytest


class TestCreatingFinancialModels:
    REPO_DIR = "/workspace/QuantLib"

    # === File Path Checks ===

    def test_header_file_exists(self):
        """Verify dcfvaluation.hpp header exists"""
        path = os.path.join(self.REPO_DIR, "ql/instruments/dcfvaluation.hpp")
        assert os.path.exists(path), f"dcfvaluation.hpp not found at {path}"

    def test_impl_file_exists(self):
        """Verify dcfvaluation.cpp implementation exists"""
        path = os.path.join(self.REPO_DIR, "ql/instruments/dcfvaluation.cpp")
        assert os.path.exists(path), f"dcfvaluation.cpp not found at {path}"

    def test_cmake_lists_exists(self):
        """Verify ql/CMakeLists.txt exists"""
        path = os.path.join(self.REPO_DIR, "ql/CMakeLists.txt")
        assert os.path.exists(path), f"CMakeLists.txt not found at {path}"

    # === Semantic Checks ===

    def test_header_declares_class(self):
        """Verify header declares a DCF valuation class"""
        path = os.path.join(self.REPO_DIR, "ql/instruments/dcfvaluation.hpp")
        with open(path) as f:
            content = f.read()

        assert re.search(r"class\s+\w*[Dd][Cc][Ff]\w*", content), (
            "Header should declare a DCF valuation class"
        )

    def test_header_has_include_guard(self):
        """Verify header has proper include guard or pragma once"""
        path = os.path.join(self.REPO_DIR, "ql/instruments/dcfvaluation.hpp")
        with open(path) as f:
            content = f.read()

        has_guard = "#ifndef" in content or "#pragma once" in content
        assert has_guard, "Header should have include guard or #pragma once"

    def test_npv_method_declared(self):
        """Verify NPV computation method is declared"""
        path = os.path.join(self.REPO_DIR, "ql/instruments/dcfvaluation.hpp")
        with open(path) as f:
            content = f.read().lower()

        npv_indicators = ["npv", "net_present_value", "netpresentvalue", "presentvalue"]
        found = [ind for ind in npv_indicators if ind in content]
        assert len(found) >= 1, (
            f"Header should declare an NPV method. Found: {found}"
        )

    def test_supports_flat_and_term_structure_discounting(self):
        """Verify both flat rate and term structure discounting are supported"""
        combined = ""
        for fname in ["dcfvaluation.hpp", "dcfvaluation.cpp"]:
            path = os.path.join(self.REPO_DIR, f"ql/instruments/{fname}")
            if os.path.exists(path):
                with open(path) as f:
                    combined += f.read()

        flat_indicators = ["flat", "rate", "discount_rate", "discountRate"]
        term_indicators = [
            "term_structure", "TermStructure", "YieldTermStructure",
            "term_struct", "yield_curve", "yieldCurve",
        ]

        flat_found = [ind for ind in flat_indicators if ind in combined]
        term_found = [ind for ind in term_indicators if ind in combined]

        assert len(flat_found) >= 1, (
            f"Should support flat rate discounting. Found: {flat_found}"
        )
        assert len(term_found) >= 1, (
            f"Should support term structure discounting. Found: {term_found}"
        )

    def test_sensitivity_analysis(self):
        """Verify sensitivity analysis across discount rate scenarios"""
        combined = ""
        for fname in ["dcfvaluation.hpp", "dcfvaluation.cpp"]:
            path = os.path.join(self.REPO_DIR, f"ql/instruments/{fname}")
            if os.path.exists(path):
                with open(path) as f:
                    combined += f.read()

        sensitivity_indicators = [
            "sensitivity", "scenario", "range", "sweep",
            "sensitivityAnalysis", "sensitivity_analysis",
            "vector", "std::vector",
        ]
        found = [ind for ind in sensitivity_indicators if ind in combined]
        assert len(found) >= 2, (
            f"Should support sensitivity analysis. Found: {found}"
        )

    def test_input_validation(self):
        """Verify input validation for negative rates, empty series, past dates"""
        combined = ""
        for fname in ["dcfvaluation.hpp", "dcfvaluation.cpp"]:
            path = os.path.join(self.REPO_DIR, f"ql/instruments/{fname}")
            if os.path.exists(path):
                with open(path) as f:
                    combined += f.read()

        validation_indicators = [
            "throw", "QL_REQUIRE", "QL_ENSURE", "invalid",
            "empty", "negative", "error", "exception",
        ]
        found = [ind for ind in validation_indicators if ind in combined]
        assert len(found) >= 2, (
            f"Should validate inputs (negative rates, empty series). "
            f"Found: {found}"
        )

    def test_cash_flow_timing_support(self):
        """Verify support for irregular cash flow timing"""
        combined = ""
        for fname in ["dcfvaluation.hpp", "dcfvaluation.cpp"]:
            path = os.path.join(self.REPO_DIR, f"ql/instruments/{fname}")
            if os.path.exists(path):
                with open(path) as f:
                    combined += f.read()

        timing_indicators = [
            "Date", "date", "schedule", "CashFlow",
            "cashflow", "Leg", "time", "dayCounter",
        ]
        found = [ind for ind in timing_indicators if ind in combined]
        assert len(found) >= 2, (
            f"Should support cash flow timing. Found: {found}"
        )

    def test_terminal_value_support(self):
        """Verify terminal value estimation for perpetuity models"""
        combined = ""
        for fname in ["dcfvaluation.hpp", "dcfvaluation.cpp"]:
            path = os.path.join(self.REPO_DIR, f"ql/instruments/{fname}")
            if os.path.exists(path):
                with open(path) as f:
                    combined += f.read()

        terminal_indicators = [
            "terminal", "perpetuity", "growth", "terminal_value",
            "terminalValue", "gordon",
        ]
        found = [ind for ind in terminal_indicators if ind in combined]
        assert len(found) >= 1, (
            f"Should support terminal value estimation. Found: {found}"
        )

    # === Functional Checks ===

    def test_cmake_references_new_files(self):
        """Verify CMakeLists.txt references the new source files"""
        path = os.path.join(self.REPO_DIR, "ql/CMakeLists.txt")
        with open(path) as f:
            content = f.read()

        assert "dcfvaluation" in content.lower(), (
            "CMakeLists.txt should reference dcfvaluation files"
        )

    def test_impl_includes_header(self):
        """Verify implementation includes its own header"""
        path = os.path.join(self.REPO_DIR, "ql/instruments/dcfvaluation.cpp")
        with open(path) as f:
            content = f.read()

        assert "dcfvaluation.hpp" in content or "dcfvaluation.h" in content, (
            "Implementation should include its own header"
        )

    def test_follows_quantlib_namespace(self):
        """Verify code uses QuantLib namespace"""
        path = os.path.join(self.REPO_DIR, "ql/instruments/dcfvaluation.hpp")
        with open(path) as f:
            content = f.read()

        assert "QuantLib" in content or "quantlib" in content.lower(), (
            "Code should use QuantLib namespace"
        )
