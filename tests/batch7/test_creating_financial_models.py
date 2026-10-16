"""
Test skill: creating-financial-models
Verify that the Agent implements a DCF Valuation Instrument and Sensitivity
Analyzer in QuantLib — C++ instrument/engine classes, sensitivity table, and
CMake build integration.
"""

import os
import re
import subprocess
import pytest


class TestCreatingFinancialModels:
    REPO_DIR = "/workspace/QuantLib"

    # ────────────────── helpers ──────────────────

    def _read(self, rel_path):
        fpath = os.path.join(self.REPO_DIR, rel_path)
        with open(fpath, "r") as f:
            return f.read()

    def _exists(self, rel_path):
        return os.path.isfile(os.path.join(self.REPO_DIR, rel_path))

    # === File Path Checks ===

    def test_dcfvaluation_header_exists(self):
        """ql/instruments/dcfvaluation.hpp must exist"""
        assert self._exists("ql/instruments/dcfvaluation.hpp")

    def test_dcfvaluation_impl_exists(self):
        """ql/instruments/dcfvaluation.cpp must exist"""
        assert self._exists("ql/instruments/dcfvaluation.cpp")

    def test_dcfengine_header_exists(self):
        """ql/pricingengines/dcf/dcfengine.hpp must exist"""
        assert self._exists("ql/pricingengines/dcf/dcfengine.hpp")

    def test_dcfengine_impl_exists(self):
        """ql/pricingengines/dcf/dcfengine.cpp must exist"""
        assert self._exists("ql/pricingengines/dcf/dcfengine.cpp")

    def test_sensitivity_header_exists(self):
        """ql/pricingengines/dcf/sensitivityanalyzer.hpp must exist"""
        assert self._exists("ql/pricingengines/dcf/sensitivityanalyzer.hpp")

    def test_sensitivity_impl_exists(self):
        """ql/pricingengines/dcf/sensitivityanalyzer.cpp must exist"""
        assert self._exists("ql/pricingengines/dcf/sensitivityanalyzer.cpp")

    def test_test_suite_cpp_exists(self):
        """test-suite/dcfvaluation.cpp must exist"""
        assert self._exists("test-suite/dcfvaluation.cpp")

    def test_test_suite_header_exists(self):
        """test-suite/dcfvaluation.hpp must exist"""
        assert self._exists("test-suite/dcfvaluation.hpp")

    # === Semantic Checks — DcfValuation Instrument ===

    def test_dcfvaluation_inherits_instrument(self):
        """DcfValuation must inherit from Instrument"""
        src = self._read("ql/instruments/dcfvaluation.hpp")
        assert re.search(r'class\s+DcfValuation\s*:\s*public\s+Instrument', src), (
            "DcfValuation does not inherit from Instrument"
        )

    def test_dcfvaluation_constructor_params(self):
        """DcfValuation constructor must accept projectedFCF, terminalGrowthRate,
        wacc, netDebt, sharesOutstanding"""
        src = self._read("ql/instruments/dcfvaluation.hpp")
        for param in ["projectedFCF", "terminalGrowthRate", "wacc",
                       "netDebt", "sharesOutstanding"]:
            assert param in src, f"Constructor missing parameter: {param}"

    def test_enterprise_value_method(self):
        """enterpriseValue() must be declared"""
        src = self._read("ql/instruments/dcfvaluation.hpp")
        assert "enterpriseValue" in src, "enterpriseValue() method not found"

    def test_equity_value_method(self):
        """equityValue() must be declared"""
        src = self._read("ql/instruments/dcfvaluation.hpp")
        assert "equityValue" in src, "equityValue() method not found"

    def test_value_per_share_method(self):
        """valuePerShare() must be declared"""
        src = self._read("ql/instruments/dcfvaluation.hpp")
        assert "valuePerShare" in src, "valuePerShare() method not found"

    def test_terminal_value_method(self):
        """terminalValue() must be declared"""
        src = self._read("ql/instruments/dcfvaluation.hpp")
        assert "terminalValue" in src, "terminalValue() method not found"

    # === Semantic Checks — Validation Logic ===

    def test_wacc_exceeds_growth_validation(self):
        """Implementation must validate WACC > terminal growth rate"""
        src = self._read("ql/instruments/dcfvaluation.cpp")
        assert "WACC" in src and ("terminal" in src.lower() or "growth" in src.lower()), (
            "Validation that WACC exceeds terminal growth rate not found"
        )

    # === Semantic Checks — DcfEngine ===

    def test_dcfengine_inherits_generic_engine(self):
        """DcfEngine must inherit from GenericEngine"""
        src = self._read("ql/pricingengines/dcf/dcfengine.hpp")
        assert "GenericEngine" in src, "DcfEngine does not inherit from GenericEngine"

    def test_dcfengine_calculate_method(self):
        """DcfEngine must implement a calculate() method"""
        src = self._read("ql/pricingengines/dcf/dcfengine.cpp")
        assert re.search(r'void\s+DcfEngine::calculate\s*\(', src), (
            "DcfEngine::calculate() implementation not found"
        )

    # === Semantic Checks — Sensitivity Analyzer ===

    def test_sensitivity_compute_table(self):
        """SensitivityAnalyzer must have computeTable returning a Matrix"""
        src = self._read("ql/pricingengines/dcf/sensitivityanalyzer.hpp")
        assert "computeTable" in src, "computeTable method not found"
        assert "Matrix" in src, "Matrix return type not found"

    def test_sensitivity_base_case(self):
        """SensitivityAnalyzer must have a baseCase method"""
        src = self._read("ql/pricingengines/dcf/sensitivityanalyzer.hpp")
        assert "baseCase" in src, "baseCase method not found"

    def test_sensitivity_pareto_bounds(self):
        """SensitivityAnalyzer must have maxValue/minValue methods"""
        src = self._read("ql/pricingengines/dcf/sensitivityanalyzer.hpp")
        assert "maxValue" in src and "minValue" in src, (
            "maxValue/minValue methods not found"
        )

    # === Semantic Checks — CMake Integration ===

    def test_ql_cmake_includes_dcfvaluation(self):
        """ql/CMakeLists.txt must reference dcfvaluation.cpp"""
        src = self._read("ql/CMakeLists.txt")
        assert "dcfvaluation" in src, (
            "dcfvaluation.cpp not added to ql/CMakeLists.txt"
        )

    def test_test_cmake_includes_dcfvaluation(self):
        """test-suite/CMakeLists.txt must reference dcfvaluation.cpp"""
        src = self._read("test-suite/CMakeLists.txt")
        assert "dcfvaluation" in src, (
            "dcfvaluation.cpp not added to test-suite/CMakeLists.txt"
        )

    # === Functional Checks ===

    def test_cmake_configure_succeeds(self):
        """CMake configuration must succeed with the new files"""
        build_dir = os.path.join(self.REPO_DIR, "build")
        os.makedirs(build_dir, exist_ok=True)
        result = subprocess.run(
            ["cmake", "..", "-DCMAKE_BUILD_TYPE=Release"],
            capture_output=True, text=True, cwd=build_dir, timeout=120,
        )
        assert result.returncode == 0, (
            f"CMake configure failed:\n{result.stdout}\n{result.stderr}"
        )

    def test_build_compiles(self):
        """The project must compile without errors"""
        build_dir = os.path.join(self.REPO_DIR, "build")
        result = subprocess.run(
            ["cmake", "--build", ".", "--parallel", "4"],
            capture_output=True, text=True, cwd=build_dir, timeout=600,
        )
        assert result.returncode == 0, (
            f"Build failed:\n{result.stdout[-2000:]}\n{result.stderr[-2000:]}"
        )

    def test_unit_tests_pass(self):
        """DCF valuation test suite must pass"""
        build_dir = os.path.join(self.REPO_DIR, "build")
        result = subprocess.run(
            ["ctest", "--test-dir", ".", "-R", "dcf", "--output-on-failure"],
            capture_output=True, text=True, cwd=build_dir, timeout=120,
        )
        assert result.returncode == 0, (
            f"Test suite failed:\n{result.stdout}\n{result.stderr}"
        )
