"""
Test skill: clojure-write
Verify that the Agent correctly adds currency field conversion to
Metabase's query result export pipeline including conversion functions,
configurable exchange rates, and export pipeline integration.
"""

import os
import re
import subprocess
import pytest


class TestClojureWrite:
    REPO_DIR = "/workspace/metabase"

    # === File Path Checks ===

    def test_currency_conversion_file_exists(self):
        """Verify currency_conversion.clj file exists"""
        path = os.path.join(
            self.REPO_DIR,
            "src/metabase/query_processor/middleware/currency_conversion.clj",
        )
        assert os.path.exists(path), f"currency_conversion.clj not found at {path}"

    def test_format_rows_file_exists(self):
        """Verify format_rows.clj file exists"""
        path = os.path.join(
            self.REPO_DIR,
            "src/metabase/query_processor/middleware/format_rows.clj",
        )
        assert os.path.exists(path), f"format_rows.clj not found at {path}"

    # === Semantic Checks ===

    def test_currency_conversion_has_namespace(self):
        """Verify currency_conversion.clj has proper namespace declaration"""
        path = os.path.join(
            self.REPO_DIR,
            "src/metabase/query_processor/middleware/currency_conversion.clj",
        )
        with open(path) as f:
            content = f.read()

        assert "(ns " in content, (
            "currency_conversion.clj should have (ns ...) declaration"
        )
        assert "currency" in content.lower(), (
            "Namespace should reference currency"
        )

    def test_currency_conversion_defines_conversion_function(self):
        """Verify a conversion function accepting value, source currency, target currency"""
        path = os.path.join(
            self.REPO_DIR,
            "src/metabase/query_processor/middleware/currency_conversion.clj",
        )
        with open(path) as f:
            content = f.read()

        func_indicators = [
            "defn", "convert", "currency",
        ]
        found = [ind for ind in func_indicators if ind in content]
        assert len(found) >= 2, (
            f"Should define a currency conversion function. Found: {found}"
        )

        # Should reference source/target currencies
        param_indicators = ["source", "target", "from", "to", "rate"]
        param_found = [ind for ind in param_indicators if ind in content.lower()]
        assert len(param_found) >= 2, (
            f"Conversion function should accept source/target currency params. "
            f"Found: {param_found}"
        )

    def test_currency_conversion_supports_exchange_rates(self):
        """Verify exchange rate configuration is present"""
        path = os.path.join(
            self.REPO_DIR,
            "src/metabase/query_processor/middleware/currency_conversion.clj",
        )
        with open(path) as f:
            content = f.read().lower()

        rate_indicators = ["rate", "exchange", "usd", "eur", "gbp", "currency"]
        found = [ind for ind in rate_indicators if ind in content]
        assert len(found) >= 2, (
            f"Should define exchange rate data. Found: {found}"
        )

    def test_currency_conversion_handles_edge_cases(self):
        """Verify edge case handling (nil, zero, unknown currency)"""
        path = os.path.join(
            self.REPO_DIR,
            "src/metabase/query_processor/middleware/currency_conversion.clj",
        )
        with open(path) as f:
            content = f.read()

        edge_case_indicators = [
            "nil", "zero", "unknown", "not found",
            "when", "if", "cond", "some?",
        ]
        found = [ind for ind in edge_case_indicators if ind in content.lower()]
        assert len(found) >= 2, (
            f"Should handle edge cases (nil, zero, unknown currency). "
            f"Found: {found}"
        )

    def test_format_rows_integrates_conversion(self):
        """Verify format_rows.clj integrates currency conversion"""
        path = os.path.join(
            self.REPO_DIR,
            "src/metabase/query_processor/middleware/format_rows.clj",
        )
        with open(path) as f:
            content = f.read()

        integration_indicators = [
            "currency", "convert", "currency_conversion",
            "currency-conversion",
        ]
        found = [ind for ind in integration_indicators if ind in content]
        assert len(found) >= 1, (
            "format_rows.clj should integrate currency conversion. "
            f"None of {integration_indicators} found."
        )

    def test_conversion_preserves_decimal_precision(self):
        """Verify conversion code handles decimal precision"""
        path = os.path.join(
            self.REPO_DIR,
            "src/metabase/query_processor/middleware/currency_conversion.clj",
        )
        with open(path) as f:
            content = f.read()

        precision_indicators = [
            "BigDecimal", "decimal", "precision", "scale",
            "with-precision", "bigdec", "round",
        ]
        found = [ind for ind in precision_indicators if ind in content]
        # Also check for multiplication/division which implies calculation
        has_math = "*" in content or "/" in content
        assert len(found) >= 1 or has_math, (
            "Conversion should handle decimal precision. "
            f"Found: {found}, has_math: {has_math}"
        )

    # === Functional Checks ===

    def test_currency_conversion_balanced_parens(self):
        """Verify currency_conversion.clj has balanced parentheses"""
        path = os.path.join(
            self.REPO_DIR,
            "src/metabase/query_processor/middleware/currency_conversion.clj",
        )
        with open(path) as f:
            content = f.read()

        assert content.count("(") == content.count(")"), (
            f"Unbalanced parentheses: {content.count('(')} open, "
            f"{content.count(')')} close"
        )
        assert content.count("[") == content.count("]"), (
            f"Unbalanced brackets: {content.count('[')} open, "
            f"{content.count(']')} close"
        )
        assert content.count("{") == content.count("}"), (
            f"Unbalanced braces: {content.count('{')} open, "
            f"{content.count('}')} close"
        )

    def test_format_rows_balanced_parens(self):
        """Verify format_rows.clj has balanced parentheses"""
        path = os.path.join(
            self.REPO_DIR,
            "src/metabase/query_processor/middleware/format_rows.clj",
        )
        with open(path) as f:
            content = f.read()

        assert content.count("(") == content.count(")"), (
            f"Unbalanced parentheses in format_rows.clj"
        )

    def test_currency_conversion_has_proper_requires(self):
        """Verify currency_conversion.clj imports necessary namespaces"""
        path = os.path.join(
            self.REPO_DIR,
            "src/metabase/query_processor/middleware/currency_conversion.clj",
        )
        with open(path) as f:
            content = f.read()

        assert ":require" in content or "require" in content, (
            "currency_conversion.clj should require its dependencies"
        )

    def test_conversion_metadata_column_detection(self):
        """Verify conversion is triggered by column metadata annotations"""
        combined = ""
        for fname in ["currency_conversion.clj", "format_rows.clj"]:
            path = os.path.join(
                self.REPO_DIR,
                f"src/metabase/query_processor/middleware/{fname}",
            )
            if os.path.exists(path):
                with open(path) as f:
                    combined += f.read()

        metadata_indicators = [
            "column", "metadata", "semantic_type", "semantic-type",
            ":currency", "field", "annotation",
        ]
        found = [ind for ind in metadata_indicators if ind in combined.lower()]
        assert len(found) >= 2, (
            f"Conversion should detect currency columns via metadata. "
            f"Found: {found}"
        )

    def test_original_values_not_mutated(self):
        """Verify implementation produces new values without mutating originals"""
        path = os.path.join(
            self.REPO_DIR,
            "src/metabase/query_processor/middleware/currency_conversion.clj",
        )
        with open(path) as f:
            content = f.read()

        # In Clojure, data is immutable by default, but check for atoms/refs
        mutation_indicators = ["atom", "swap!", "reset!", "ref", "alter"]
        mutable = [ind for ind in mutation_indicators if ind in content]
        # Having some is ok, but excessive mutation would be anti-pattern
        assert len(mutable) <= 2, (
            f"Conversion should be pure/functional. Found mutation primitives: {mutable}"
        )
