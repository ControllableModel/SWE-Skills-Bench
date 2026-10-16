"""
Tests for the clojure-write skill.

Validates that a Clojure query preprocessing pipeline was implemented for
Metabase, including normalization, validation, transformation, default
values, wildcard expansion, and idempotency of normalization.

Repo: metabase (https://github.com/metabase/metabase)
"""

import os
import re
import subprocess

REPO_DIR = "/workspace/metabase"


class TestFilePathCheck:
    """Verify that all required files were created."""

    def test_preprocess_file_exists(self):
        path = os.path.join(REPO_DIR, "src", "metabase", "query_processor", "preprocess.clj")
        assert os.path.isfile(path), f"Expected preprocess.clj at {path}"

    def test_normalize_file_exists(self):
        path = os.path.join(
            REPO_DIR, "src", "metabase", "query_processor", "preprocess", "normalize.clj"
        )
        assert os.path.isfile(path), f"Expected normalize.clj at {path}"

    def test_validate_file_exists(self):
        path = os.path.join(
            REPO_DIR, "src", "metabase", "query_processor", "preprocess", "validate.clj"
        )
        assert os.path.isfile(path), f"Expected validate.clj at {path}"

    def test_preprocess_test_file_exists(self):
        path = os.path.join(
            REPO_DIR, "test", "metabase", "query_processor", "preprocess_test.clj"
        )
        assert os.path.isfile(path), f"Expected preprocess_test.clj at {path}"


class TestSemanticNormalization:
    """Verify normalize-query function characteristics."""

    def _read_normalize_file(self):
        path = os.path.join(
            REPO_DIR, "src", "metabase", "query_processor", "preprocess", "normalize.clj"
        )
        with open(path, "r") as f:
            return f.read()

    def test_normalize_query_function_defined(self):
        content = self._read_normalize_file()
        assert re.search(r"normalize-query", content), (
            "Expected normalize-query function in normalize.clj"
        )

    def test_kebab_case_conversion(self):
        """Normalization should convert underscore keys to kebab-case."""
        content = self._read_normalize_file()
        assert re.search(r"kebab|snake.*case|_.*-|camel|->kebab", content, re.IGNORECASE), (
            "Expected key case conversion logic (underscore to kebab-case)"
        )

    def test_nil_removal(self):
        """Normalization should remove nil-valued entries."""
        content = self._read_normalize_file()
        assert re.search(r"nil\?|remove.*nil|dissoc.*nil|filter.*nil", content, re.IGNORECASE), (
            "Expected nil value removal logic in normalize-query"
        )

    def test_order_by_shorthand_normalization(self):
        """order-by shorthand [:field-id N] should expand to [:asc [:field-id N]]."""
        content = self._read_normalize_file()
        assert re.search(r"order-by|:asc", content), (
            "Expected order-by normalization (shorthand to full :asc form)"
        )

    def test_field_deduplication(self):
        """Duplicate :fields entries should be removed."""
        content = self._read_normalize_file()
        assert re.search(r"dedupe|distinct|set|unique", content, re.IGNORECASE), (
            "Expected field deduplication logic in normalize-query"
        )

    def test_namespace_declaration(self):
        content = self._read_normalize_file()
        assert re.search(
            r"\(ns\s+metabase\.query.processor\.preprocess\.normalize", content
        ), "Expected proper namespace declaration for normalize.clj"


class TestSemanticValidation:
    """Verify validate-query function characteristics."""

    def _read_validate_file(self):
        path = os.path.join(
            REPO_DIR, "src", "metabase", "query_processor", "preprocess", "validate.clj"
        )
        with open(path, "r") as f:
            return f.read()

    def test_validate_query_function_defined(self):
        content = self._read_validate_file()
        assert re.search(r"validate-query", content), (
            "Expected validate-query function in validate.clj"
        )

    def test_source_table_validation(self):
        content = self._read_validate_file()
        assert re.search(r"source-table", content), (
            "Expected source-table validation in validate-query"
        )

    def test_filter_operator_validation(self):
        """Validation should check filter operators against a whitelist."""
        content = self._read_validate_file()
        filter_ops = [":=", ":!=", ":<", ":>", ":between", ":contains", ":is-null", ":not-null"]
        found_count = sum(1 for op in filter_ops if op in content)
        assert found_count >= 4, (
            f"Expected at least 4 filter operators in validation whitelist, found {found_count}"
        )

    def test_limit_validation(self):
        """Limit must be a positive integer <= 10000."""
        content = self._read_validate_file()
        assert re.search(r":limit|10000", content), (
            "Expected :limit validation (positive int <= 10000)"
        )

    def test_returns_valid_structure(self):
        """Validation should return {:valid true/false, :errors [...]}."""
        content = self._read_validate_file()
        assert ":valid" in content, "Expected :valid key in validation results"

    def test_collects_all_errors(self):
        """Validation should collect all errors, not short-circuit on the first."""
        content = self._read_validate_file()
        assert re.search(r":errors|errors|concat|conj|into", content), (
            "Expected error accumulation logic (collect all errors)"
        )


class TestSemanticPipeline:
    """Verify the preprocessing pipeline in preprocess.clj."""

    def _read_preprocess_file(self):
        path = os.path.join(REPO_DIR, "src", "metabase", "query_processor", "preprocess.clj")
        with open(path, "r") as f:
            return f.read()

    def test_preprocess_function_defined(self):
        content = self._read_preprocess_file()
        assert re.search(r"\(defn\s+preprocess\b", content), (
            "Expected preprocess function defined in preprocess.clj"
        )

    def test_default_limit_added(self):
        """Pipeline should add a default limit of 2000 when none specified."""
        content = self._read_preprocess_file()
        assert "2000" in content, (
            "Expected default limit value 2000 in pipeline"
        )

    def test_field_resolver_parameter(self):
        """Pipeline should accept a field-resolver parameter."""
        content = self._read_preprocess_file()
        assert re.search(r"field-resolver", content), (
            "Expected field-resolver parameter in preprocess function"
        )

    def test_pipeline_uses_threading_or_comp(self):
        """Pipeline should use comp or threading macros."""
        content = self._read_preprocess_file()
        assert re.search(r"\bcomp\b|->|->>", content), (
            "Expected pipeline composition using comp, -> or ->>"
        )

    def test_warnings_support(self):
        """Non-fatal issues should produce :warnings instead of errors."""
        content = self._read_preprocess_file()
        assert re.search(r":warnings|warn", content, re.IGNORECASE), (
            "Expected :warnings support for non-fatal issues"
        )


class TestFunctionalClojureSyntax:
    """Validate that Clojure files are syntactically well-formed."""

    def _check_balanced(self, filepath):
        with open(filepath, "r") as f:
            content = f.read()
        open_count = content.count("(") + content.count("[") + content.count("{")
        close_count = content.count(")") + content.count("]") + content.count("}")
        return open_count == close_count, open_count, close_count

    def test_preprocess_balanced(self):
        path = os.path.join(REPO_DIR, "src", "metabase", "query_processor", "preprocess.clj")
        balanced, o, c = self._check_balanced(path)
        assert balanced, f"Unbalanced delimiters in preprocess.clj: {o} open vs {c} close"

    def test_normalize_balanced(self):
        path = os.path.join(
            REPO_DIR, "src", "metabase", "query_processor", "preprocess", "normalize.clj"
        )
        balanced, o, c = self._check_balanced(path)
        assert balanced, f"Unbalanced delimiters in normalize.clj: {o} open vs {c} close"

    def test_validate_balanced(self):
        path = os.path.join(
            REPO_DIR, "src", "metabase", "query_processor", "preprocess", "validate.clj"
        )
        balanced, o, c = self._check_balanced(path)
        assert balanced, f"Unbalanced delimiters in validate.clj: {o} open vs {c} close"

    def test_test_file_has_deftest(self):
        path = os.path.join(
            REPO_DIR, "test", "metabase", "query_processor", "preprocess_test.clj"
        )
        with open(path, "r") as f:
            content = f.read()
        matches = re.findall(r"\(deftest\s+", content)
        assert len(matches) >= 3, (
            f"Expected at least 3 deftest forms in preprocess_test.clj, found {len(matches)}"
        )

    def test_test_file_uses_clojure_test(self):
        path = os.path.join(
            REPO_DIR, "test", "metabase", "query_processor", "preprocess_test.clj"
        )
        with open(path, "r") as f:
            content = f.read()
        assert re.search(r"clojure\.test", content), (
            "Expected clojure.test in preprocess_test.clj"
        )

    def test_test_imports_preprocess_namespace(self):
        path = os.path.join(
            REPO_DIR, "test", "metabase", "query_processor", "preprocess_test.clj"
        )
        with open(path, "r") as f:
            content = f.read()
        assert re.search(r"metabase\.query.processor\.preprocess", content), (
            "Expected preprocess namespace import in test file"
        )

    def test_normalize_requires_walk_or_postwalk(self):
        """Recursive normalization likely uses clojure.walk."""
        path = os.path.join(
            REPO_DIR, "src", "metabase", "query_processor", "preprocess", "normalize.clj"
        )
        with open(path, "r") as f:
            content = f.read()
        assert re.search(r"walk|postwalk|prewalk|reduce|map", content), (
            "Expected recursive traversal (walk/reduce/map) for deep normalization"
        )
