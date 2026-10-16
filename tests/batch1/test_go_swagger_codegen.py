"""Benchmark test for skill `go-swagger-codegen`.

Task: add regular-expression (`regexp=<expr>`) constraint support to the
`validate` struct tag in swaggo/swag's field parser, so the expression is
carried onto the generated OpenAPI schema's `Pattern` field via
`ComplementSchema`.

Verification strategy
---------------------
The agent edits `field_parser.go` (and `field_parser_test.go`) inside
REPO_DIR = /workspace/swag.  Rather than trust the test file the agent itself
may write, these tests INJECT an independent in-package Go test driver into
REPO_DIR and run it with the repo's native toolchain (`go test`).  The driver
calls the package-internal `newTagBaseFieldParser(...).ComplementSchema(&schema)`
directly and asserts on the resulting `spec.Schema.Pattern` (and
`schema.Items.Schema.Pattern` for arrays).  This exercises the real behavior
required by the task and a naive / cosmetic edit will not pass.

L1: deliverable files exist and are well-formed; package compiles.
L2: dynamic execution of `go test` over injected drivers + the repo's own
    `TestValidTags` suite, deep-validating Pattern placement, type handling,
    array-items handling, edge cases, error-freedom, and coexistence with
    other constraints.
"""

import os
import subprocess
import textwrap
import uuid

import pytest

REPO_DIR = "/workspace/swag"
GO_TIMEOUT = 420


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _go_env():
    env = dict(os.environ)
    # Keep module/cache resolution working inside the container.
    env.setdefault("GOFLAGS", "-mod=mod")
    env["CGO_ENABLED"] = "0"
    return env


def _run_go(args, timeout=GO_TIMEOUT):
    """Run a `go ...` command in REPO_DIR and return CompletedProcess."""
    return subprocess.run(
        ["go", *args],
        cwd=REPO_DIR,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=_go_env(),
    )


def _write_driver(body: str) -> str:
    """Write an in-package Go test file (package swag) into REPO_DIR.

    Returns the absolute path so the caller can remove it afterwards.
    `body` must contain one or more `func TestXxx(t *testing.T) { ... }`.
    """
    fname = f"zz_bench_{uuid.uuid4().hex[:12]}_test.go"
    path = os.path.join(REPO_DIR, fname)
    header = textwrap.dedent(
        """\
        package swag

        import (
        \t"go/ast"
        \t"testing"

        \t"github.com/go-openapi/spec"
        )

        """
    )
    with open(path, "w") as fh:
        fh.write(header + textwrap.dedent(body))
    return path


def _run_driver(test_name: str, body: str):
    """Inject driver, run `go test -run <test_name>`, clean up.

    Returns the CompletedProcess from `go test`.
    """
    path = _write_driver(body)
    try:
        return _run_go(
            ["test", "-run", f"^{test_name}$", "-v", "-count=1", "."]
        )
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


# --------------------------------------------------------------------------- #
# Module-scope sanity: deps available / package compiles.
# --------------------------------------------------------------------------- #
def _purge_stale_drivers():
    """Remove any leftover injected driver files (defensive, e.g. on NFS)."""
    try:
        for name in os.listdir(REPO_DIR):
            if name.startswith("zz_bench_") and name.endswith("_test.go"):
                try:
                    os.remove(os.path.join(REPO_DIR, name))
                except OSError:
                    pass
    except OSError:
        pass


@pytest.fixture(scope="module", autouse=True)
def _ensure_build():
    assert os.path.isdir(REPO_DIR), f"REPO_DIR missing: {REPO_DIR}"
    _purge_stale_drivers()
    # `go build ./...` both warms the module cache and proves the agent's edit
    # compiles before we run any behavioral driver. It does not compile *_test.go,
    # so it is immune to injected driver files.
    proc = _run_go(["build", "./..."], timeout=GO_TIMEOUT)
    assert proc.returncode == 0, (
        "repository does not build after the change:\n"
        f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    )
    yield
    _purge_stale_drivers()


class TestGoSwaggerCodegen:
    REPO_DIR = "/workspace/swag"

    # ------------------------------------------------------------------ #
    # L1 — deliverables exist and are well-formed.
    # ------------------------------------------------------------------ #
    def test_field_parser_source_exists(self):
        """L1: field_parser.go (the file to modify) exists and is non-trivial."""
        path = os.path.join(self.REPO_DIR, "field_parser.go")
        assert os.path.isfile(path), f"missing {path}"
        assert os.path.getsize(path) > 1000, "field_parser.go unexpectedly small"

    def test_field_parser_test_source_exists(self):
        """L1: field_parser_test.go exists and contains TestValidTags."""
        path = os.path.join(self.REPO_DIR, "field_parser_test.go")
        assert os.path.isfile(path), f"missing {path}"
        with open(path) as fh:
            content = fh.read()
        assert "func TestValidTags(" in content, (
            "TestValidTags function must remain in field_parser_test.go"
        )

    def test_package_compiles(self):
        """L1: the swag package and its commands compile after the change."""
        _purge_stale_drivers()
        proc = _run_go(["build", "./..."], timeout=GO_TIMEOUT)
        assert proc.returncode == 0, (
            f"go build ./... failed:\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    # ------------------------------------------------------------------ #
    # L2 — dynamic behavior via injected drivers.
    # ------------------------------------------------------------------ #
    def test_string_field_pattern_set(self):
        """L2: regexp on a string field lands on schema.Pattern, no error."""
        body = r'''
        func TestZZStringPattern(t *testing.T) {
        	schema := spec.Schema{}
        	schema.Type = []string{"string"}
        	err := newTagBaseFieldParser(
        		&Parser{},
        		&ast.Field{Tag: &ast.BasicLit{
        			Value: `json:"test" validate:"required,regexp=^[a-z0-9_]+$"`,
        		}},
        	).ComplementSchema(&schema)
        	if err != nil {
        		t.Fatalf("unexpected error: %v", err)
        	}
        	if schema.Pattern != "^[a-z0-9_]+$" {
        		t.Fatalf("Pattern = %q, want %q", schema.Pattern, "^[a-z0-9_]+$")
        	}
        }
        '''
        proc = _run_driver("TestZZStringPattern", body)
        assert proc.returncode == 0, (
            "string-field regexp not applied to schema.Pattern:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "PASS" in proc.stdout

    def test_string_field_pattern_no_required(self):
        """L2: regexp works without `required` present in the tag (order-independent)."""
        body = r'''
        func TestZZStringPatternNoReq(t *testing.T) {
        	schema := spec.Schema{}
        	schema.Type = []string{"string"}
        	err := newTagBaseFieldParser(
        		&Parser{},
        		&ast.Field{Tag: &ast.BasicLit{
        			Value: `json:"slug" validate:"regexp=^[a-z]+(-[a-z]+)*$"`,
        		}},
        	).ComplementSchema(&schema)
        	if err != nil {
        		t.Fatalf("unexpected error: %v", err)
        	}
        	if schema.Pattern != "^[a-z]+(-[a-z]+)*$" {
        		t.Fatalf("Pattern = %q, want %q", schema.Pattern, "^[a-z]+(-[a-z]+)*$")
        	}
        }
        '''
        proc = _run_driver("TestZZStringPatternNoReq", body)
        assert proc.returncode == 0, (
            "regexp without `required` not applied:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "PASS" in proc.stdout

    def test_integer_field_pattern_ignored(self):
        """L2: regexp on a non-string (integer) field is silently ignored, no error."""
        body = r'''
        func TestZZIntPatternIgnored(t *testing.T) {
        	schema := spec.Schema{}
        	schema.Type = []string{"integer"}
        	err := newTagBaseFieldParser(
        		&Parser{},
        		&ast.Field{Tag: &ast.BasicLit{
        			Value: `json:"test" validate:"regexp=^[a-z]+$"`,
        		}},
        	).ComplementSchema(&schema)
        	if err != nil {
        		t.Fatalf("unexpected error on integer field: %v", err)
        	}
        	if schema.Pattern != "" {
        		t.Fatalf("integer schema.Pattern = %q, want empty", schema.Pattern)
        	}
        }
        '''
        proc = _run_driver("TestZZIntPatternIgnored", body)
        assert proc.returncode == 0, (
            "regexp on integer field must be ignored without error:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "PASS" in proc.stdout

    def test_array_of_strings_items_pattern(self):
        """L2: for []string the regexp lands on items schema, not the array schema."""
        body = r'''
        func TestZZArrayItemsPattern(t *testing.T) {
        	schema := spec.Schema{}
        	schema.Type = []string{"array"}
        	schema.Items = &spec.SchemaOrArray{
        		Schema: &spec.Schema{
        			SchemaProps: spec.SchemaProps{Type: []string{"string"}},
        		},
        	}
        	err := newTagBaseFieldParser(
        		&Parser{},
        		&ast.Field{Tag: &ast.BasicLit{
        			Value: `json:"test" validate:"regexp=^[a-z]+$"`,
        		}},
        	).ComplementSchema(&schema)
        	if err != nil {
        		t.Fatalf("unexpected error on array field: %v", err)
        	}
        	if schema.Pattern != "" {
        		t.Fatalf("array schema.Pattern = %q, want empty", schema.Pattern)
        	}
        	if schema.Items == nil || schema.Items.Schema == nil {
        		t.Fatalf("items schema missing")
        	}
        	if schema.Items.Schema.Pattern != "^[a-z]+$" {
        		t.Fatalf("items.Pattern = %q, want %q", schema.Items.Schema.Pattern, "^[a-z]+$")
        	}
        }
        '''
        proc = _run_driver("TestZZArrayItemsPattern", body)
        assert proc.returncode == 0, (
            "array-of-strings regexp must land on items schema only:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "PASS" in proc.stdout

    def test_empty_regexp_value_is_noop(self):
        """L2: `validate:"regexp="` leaves Pattern empty and returns no error."""
        body = r'''
        func TestZZEmptyRegexp(t *testing.T) {
        	schema := spec.Schema{}
        	schema.Type = []string{"string"}
        	err := newTagBaseFieldParser(
        		&Parser{},
        		&ast.Field{Tag: &ast.BasicLit{
        			Value: `json:"test" validate:"regexp="`,
        		}},
        	).ComplementSchema(&schema)
        	if err != nil {
        		t.Fatalf("unexpected error for empty regexp: %v", err)
        	}
        	if schema.Pattern != "" {
        		t.Fatalf("Pattern = %q, want empty for regexp=", schema.Pattern)
        	}
        }
        '''
        proc = _run_driver("TestZZEmptyRegexp", body)
        assert proc.returncode == 0, (
            "empty regexp value must be a no-op:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "PASS" in proc.stdout

    def test_no_regexp_rule_keeps_pattern_empty(self):
        """L2: a validate tag without regexp leaves Pattern empty (unchanged)."""
        body = r'''
        func TestZZNoRegexp(t *testing.T) {
        	schema := spec.Schema{}
        	schema.Type = []string{"string"}
        	err := newTagBaseFieldParser(
        		&Parser{},
        		&ast.Field{Tag: &ast.BasicLit{
        			Value: `json:"test" validate:"required,max=10"`,
        		}},
        	).ComplementSchema(&schema)
        	if err != nil {
        		t.Fatalf("unexpected error: %v", err)
        	}
        	if schema.Pattern != "" {
        		t.Fatalf("Pattern = %q, want empty when no regexp rule", schema.Pattern)
        	}
        	if schema.MaxLength == nil || *schema.MaxLength != 10 {
        		got := "nil"
        		if schema.MaxLength != nil {
        			got = "set-but-wrong"
        		}
        		t.Fatalf("MaxLength regression: %s (want 10)", got)
        	}
        }
        '''
        proc = _run_driver("TestZZNoRegexp", body)
        assert proc.returncode == 0, (
            "non-regexp tag must keep Pattern empty and preserve max:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "PASS" in proc.stdout

    def test_regexp_coexists_with_other_constraints(self):
        """L2: regexp does not suppress max/min derived from the same tag."""
        body = r'''
        func TestZZCoexist(t *testing.T) {
        	schema := spec.Schema{}
        	schema.Type = []string{"string"}
        	err := newTagBaseFieldParser(
        		&Parser{},
        		&ast.Field{Tag: &ast.BasicLit{
        			Value: `json:"test" validate:"required,min=3,max=12,regexp=^[A-Za-z]+$"`,
        		}},
        	).ComplementSchema(&schema)
        	if err != nil {
        		t.Fatalf("unexpected error: %v", err)
        	}
        	if schema.Pattern != "^[A-Za-z]+$" {
        		t.Fatalf("Pattern = %q, want %q", schema.Pattern, "^[A-Za-z]+$")
        	}
        	if schema.MinLength == nil || *schema.MinLength != 3 {
        		t.Fatalf("MinLength not preserved alongside regexp")
        	}
        	if schema.MaxLength == nil || *schema.MaxLength != 12 {
        		t.Fatalf("MaxLength not preserved alongside regexp")
        	}
        }
        '''
        proc = _run_driver("TestZZCoexist", body)
        assert proc.returncode == 0, (
            "regexp must coexist with min/max constraints:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "PASS" in proc.stdout

    def test_regexp_expression_with_equals_char(self):
        """L2: only the first `=` splits key/value; later `=` belong to the expression."""
        body = r'''
        func TestZZEqualsInExpr(t *testing.T) {
        	schema := spec.Schema{}
        	schema.Type = []string{"string"}
        	err := newTagBaseFieldParser(
        		&Parser{},
        		&ast.Field{Tag: &ast.BasicLit{
        			Value: `json:"test" validate:"regexp=^a=b$"`,
        		}},
        	).ComplementSchema(&schema)
        	if err != nil {
        		t.Fatalf("unexpected error: %v", err)
        	}
        	if schema.Pattern != "^a=b$" {
        		t.Fatalf("Pattern = %q, want %q (full remainder after first =)", schema.Pattern, "^a=b$")
        	}
        }
        '''
        proc = _run_driver("TestZZEqualsInExpr", body)
        assert proc.returncode == 0, (
            "expression containing '=' must be preserved in full:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "PASS" in proc.stdout

    def test_array_top_schema_not_polluted_when_other_constraints(self):
        """L2: array regexp on items must not also appear on the array schema."""
        body = r'''
        func TestZZArrayNoTopPattern(t *testing.T) {
        	schema := spec.Schema{}
        	schema.Type = []string{"array"}
        	schema.Items = &spec.SchemaOrArray{
        		Schema: &spec.Schema{
        			SchemaProps: spec.SchemaProps{Type: []string{"string"}},
        		},
        	}
        	err := newTagBaseFieldParser(
        		&Parser{},
        		&ast.Field{Tag: &ast.BasicLit{
        			Value: `json:"test" validate:"required,regexp=^x[0-9]+$"`,
        		}},
        	).ComplementSchema(&schema)
        	if err != nil {
        		t.Fatalf("unexpected error: %v", err)
        	}
        	if schema.Pattern != "" {
        		t.Fatalf("top-level array Pattern must stay empty, got %q", schema.Pattern)
        	}
        	if schema.Items.Schema.Pattern != "^x[0-9]+$" {
        		t.Fatalf("items.Pattern = %q, want %q", schema.Items.Schema.Pattern, "^x[0-9]+$")
        	}
        }
        '''
        proc = _run_driver("TestZZArrayNoTopPattern", body)
        assert proc.returncode == 0, (
            "array regexp must only touch items schema:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "PASS" in proc.stdout

    def test_repo_native_validtags_suite_passes(self):
        """L2: the repo's own `go test -run TestValidTags ./...` passes (no regression)."""
        proc = _run_go(["test", "-run", "TestValidTags", "-count=1", "./..."])
        assert proc.returncode == 0, (
            "native TestValidTags suite failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        # `go test ./...` prints "ok" for the package(s) that ran.
        assert "ok" in proc.stdout, (
            f"expected a passing package line:\nSTDOUT:\n{proc.stdout}"
        )

    def test_existing_validtags_assertions_preserved(self):
        """L2: a driver re-checks the pre-existing validate-tag constraints
        (max/min length, oneof, unique) still derive correctly — guarding that
        the regexp addition did not regress sibling constraint handling.
        """
        body = r'''
        func TestZZSiblingConstraints(t *testing.T) {
        	// string max/min length via validate
        	s1 := spec.Schema{}
        	s1.Type = []string{"string"}
        	if err := newTagBaseFieldParser(&Parser{},
        		&ast.Field{Tag: &ast.BasicLit{Value: `json:"t" validate:"max=10,min=2"`}},
        	).ComplementSchema(&s1); err != nil {
        		t.Fatalf("string len err: %v", err)
        	}
        	if s1.MaxLength == nil || *s1.MaxLength != 10 || s1.MinLength == nil || *s1.MinLength != 2 {
        		t.Fatalf("string len constraints wrong: max=%v min=%v", s1.MaxLength, s1.MinLength)
        	}

        	// oneof -> enum
        	s2 := spec.Schema{}
        	s2.Type = []string{"string"}
        	if err := newTagBaseFieldParser(&Parser{},
        		&ast.Field{Tag: &ast.BasicLit{Value: `json:"t" validate:"oneof=red green"`}},
        	).ComplementSchema(&s2); err != nil {
        		t.Fatalf("oneof err: %v", err)
        	}
        	if len(s2.Enum) != 2 || s2.Enum[0] != "red" || s2.Enum[1] != "green" {
        		t.Fatalf("oneof enum wrong: %v", s2.Enum)
        	}

        	// unique on array
        	s3 := spec.Schema{}
        	s3.Type = []string{"array"}
        	s3.Items = &spec.SchemaOrArray{Schema: &spec.Schema{SchemaProps: spec.SchemaProps{Type: []string{"string"}}}}
        	if err := newTagBaseFieldParser(&Parser{},
        		&ast.Field{Tag: &ast.BasicLit{Value: `json:"t" validate:"unique"`}},
        	).ComplementSchema(&s3); err != nil {
        		t.Fatalf("unique err: %v", err)
        	}
        	if !s3.UniqueItems {
        		t.Fatalf("unique not set on array schema")
        	}
        }
        '''
        proc = _run_driver("TestZZSiblingConstraints", body)
        assert proc.returncode == 0, (
            "sibling validate-tag constraints regressed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "PASS" in proc.stdout
