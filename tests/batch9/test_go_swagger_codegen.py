"""Benchmark test for skill `go-swagger-codegen` (variant ext9).

Task: add single-value enum support (`eq=<value>`) to the `validate` struct
tag in swaggo/swag's field parser.  An `eq=<value>` rule must produce a
SINGLE-element enum on the generated OpenAPI schema, typed according to the
field's schema type (string stays string; integer/number parsed numerically;
boolean parsed as bool).  It must NOT overwrite a non-empty enum (so when a
`oneof` rule already set the enum, a later `eq` is ignored), it must silently
ignore values that cannot be converted to the field's type, and an empty value
(`eq=`) must be a no-op.  This is DISTINCT from ext1 (which targeted `regexp=`
-> `schema.Pattern`); here the target is `schema.Enum`.

Verification strategy
---------------------
The agent edits `field_parser.go` (and `field_parser_test.go`) inside
REPO_DIR = /workspace/swag.  Rather than trust the test file the agent itself
may write, these tests INJECT an independent in-package Go test driver into
REPO_DIR and run it with the repo's native toolchain (`go test`).  The driver
constructs a `spec.Schema`, calls the package-internal
`newTagBaseFieldParser(...).ComplementSchema(&schema)` directly, and asserts on
the resulting `schema.Enum` (and `schema.Items.Schema.Enum` for arrays).  This
exercises the real behavior required by the task; a naive / cosmetic edit
(hardcoding a value, ignoring the type, overwriting an existing enum, or
returning an error) will not pass.

L1: deliverable files exist and are well-formed; package compiles.
L2: dynamic execution of injected `go test` drivers + the repo's own
    `TestValidTags` suite, deep-validating enum contents, element type,
    array-items placement, the oneof-wins precedence, type-mismatch and
    empty-value no-ops, error-freedom, and non-regression of sibling
    constraints.

Native acceptance command driven by L2:  go test -run TestValidTags ./...
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


# --------------------------------------------------------------------------- #
# Module-scope sanity: deps available / package compiles.
# --------------------------------------------------------------------------- #
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
        """L1: field_parser_test.go exists and still contains TestValidTags."""
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
    def test_string_eq_single_enum(self):
        """L2: `eq=admin` on a string field yields enum == ["admin"], no error."""
        body = r'''
        func TestZZStringEq(t *testing.T) {
        	schema := spec.Schema{}
        	schema.Type = []string{"string"}
        	err := newTagBaseFieldParser(
        		&Parser{},
        		&ast.Field{Tag: &ast.BasicLit{
        			Value: `json:"kind" validate:"eq=admin"`,
        		}},
        	).ComplementSchema(&schema)
        	if err != nil {
        		t.Fatalf("unexpected error: %v", err)
        	}
        	if len(schema.Enum) != 1 {
        		t.Fatalf("Enum length = %d (%v), want 1", len(schema.Enum), schema.Enum)
        	}
        	if got, ok := schema.Enum[0].(string); !ok || got != "admin" {
        		t.Fatalf("Enum[0] = %#v, want string \"admin\"", schema.Enum[0])
        	}
        }
        '''
        proc = _run_driver("TestZZStringEq", body)
        assert proc.returncode == 0, (
            "string eq= not applied as single-element string enum:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "PASS" in proc.stdout

    def test_string_eq_no_required(self):
        """L2: eq= works as the sole rule (order/independence from `required`)."""
        body = r'''
        func TestZZStringEqSolo(t *testing.T) {
        	schema := spec.Schema{}
        	schema.Type = []string{"string"}
        	err := newTagBaseFieldParser(
        		&Parser{},
        		&ast.Field{Tag: &ast.BasicLit{
        			Value: `json:"role" validate:"required,eq=superuser"`,
        		}},
        	).ComplementSchema(&schema)
        	if err != nil {
        		t.Fatalf("unexpected error: %v", err)
        	}
        	if len(schema.Enum) != 1 {
        		t.Fatalf("Enum length = %d (%v), want 1", len(schema.Enum), schema.Enum)
        	}
        	if got, ok := schema.Enum[0].(string); !ok || got != "superuser" {
        		t.Fatalf("Enum[0] = %#v, want string \"superuser\"", schema.Enum[0])
        	}
        }
        '''
        proc = _run_driver("TestZZStringEqSolo", body)
        assert proc.returncode == 0, (
            "eq= alongside required not applied:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "PASS" in proc.stdout

    def test_integer_eq_numeric_enum(self):
        """L2: `eq=1` on an integer field yields a single NUMERIC enum value 1.

        A naive implementation that always stores the raw string would store
        "1" (a string); this asserts the value is numerically typed.
        """
        body = r'''
        func TestZZIntEq(t *testing.T) {
        	schema := spec.Schema{}
        	schema.Type = []string{"integer"}
        	err := newTagBaseFieldParser(
        		&Parser{},
        		&ast.Field{Tag: &ast.BasicLit{
        			Value: `json:"status" validate:"eq=1"`,
        		}},
        	).ComplementSchema(&schema)
        	if err != nil {
        		t.Fatalf("unexpected error: %v", err)
        	}
        	if len(schema.Enum) != 1 {
        		t.Fatalf("Enum length = %d (%v), want 1", len(schema.Enum), schema.Enum)
        	}
        	if _, isStr := schema.Enum[0].(string); isStr {
        		t.Fatalf("Enum[0] is a string %q, want a numeric value for integer field", schema.Enum[0])
        	}
        	// Compare numerically regardless of the concrete int/float kind defineType yields.
        	var asFloat float64
        	switch v := schema.Enum[0].(type) {
        	case int:
        		asFloat = float64(v)
        	case int64:
        		asFloat = float64(v)
        	case float64:
        		asFloat = v
        	default:
        		t.Fatalf("Enum[0] has unexpected type %T (%v)", schema.Enum[0], schema.Enum[0])
        	}
        	if asFloat != 1 {
        		t.Fatalf("Enum[0] numeric = %v, want 1", asFloat)
        	}
        }
        '''
        proc = _run_driver("TestZZIntEq", body)
        assert proc.returncode == 0, (
            "integer eq= must yield a single numeric enum value:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "PASS" in proc.stdout

    def test_integer_eq_invalid_value_ignored(self):
        """L2: `eq=abc` on an integer field is silently ignored (empty enum, no error)."""
        body = r'''
        func TestZZIntEqInvalid(t *testing.T) {
        	schema := spec.Schema{}
        	schema.Type = []string{"integer"}
        	err := newTagBaseFieldParser(
        		&Parser{},
        		&ast.Field{Tag: &ast.BasicLit{
        			Value: `json:"status" validate:"eq=abc"`,
        		}},
        	).ComplementSchema(&schema)
        	if err != nil {
        		t.Fatalf("unexpected error for unconvertible eq value: %v", err)
        	}
        	if len(schema.Enum) != 0 {
        		t.Fatalf("Enum = %v, want empty for eq=abc on integer field", schema.Enum)
        	}
        }
        '''
        proc = _run_driver("TestZZIntEqInvalid", body)
        assert proc.returncode == 0, (
            "unconvertible eq= value must be ignored without error or enum entry:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "PASS" in proc.stdout

    def test_empty_eq_value_is_noop(self):
        """L2: `validate:"eq="` leaves the enum empty and returns no error."""
        body = r'''
        func TestZZEmptyEq(t *testing.T) {
        	schema := spec.Schema{}
        	schema.Type = []string{"string"}
        	err := newTagBaseFieldParser(
        		&Parser{},
        		&ast.Field{Tag: &ast.BasicLit{
        			Value: `json:"kind" validate:"eq="`,
        		}},
        	).ComplementSchema(&schema)
        	if err != nil {
        		t.Fatalf("unexpected error for empty eq value: %v", err)
        	}
        	if len(schema.Enum) != 0 {
        		t.Fatalf("Enum = %v, want empty for eq=", schema.Enum)
        	}
        }
        '''
        proc = _run_driver("TestZZEmptyEq", body)
        assert proc.returncode == 0, (
            "empty eq= value must be a no-op:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "PASS" in proc.stdout

    def test_no_eq_rule_keeps_enum_empty(self):
        """L2: a validate tag with no eq (and no oneof) leaves the enum empty.

        Also verifies a sibling constraint (max) is still derived, so the eq
        addition did not short-circuit the rest of parseValidTags.
        """
        body = r'''
        func TestZZNoEq(t *testing.T) {
        	schema := spec.Schema{}
        	schema.Type = []string{"string"}
        	err := newTagBaseFieldParser(
        		&Parser{},
        		&ast.Field{Tag: &ast.BasicLit{
        			Value: `json:"name" validate:"required,max=10"`,
        		}},
        	).ComplementSchema(&schema)
        	if err != nil {
        		t.Fatalf("unexpected error: %v", err)
        	}
        	if len(schema.Enum) != 0 {
        		t.Fatalf("Enum = %v, want empty when no eq/oneof rule", schema.Enum)
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
        proc = _run_driver("TestZZNoEq", body)
        assert proc.returncode == 0, (
            "non-eq tag must keep enum empty and preserve max:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "PASS" in proc.stdout

    def test_oneof_wins_over_later_eq(self):
        """L2: `oneof=a b,eq=c` -> enum stays ["a","b"]; eq must not overwrite.

        oneof is set first (left-to-right tag order) and a later eq must
        decline to overwrite a non-empty enum.
        """
        body = r'''
        func TestZZOneofWins(t *testing.T) {
        	schema := spec.Schema{}
        	schema.Type = []string{"string"}
        	err := newTagBaseFieldParser(
        		&Parser{},
        		&ast.Field{Tag: &ast.BasicLit{
        			Value: `json:"v" validate:"oneof=a b,eq=c"`,
        		}},
        	).ComplementSchema(&schema)
        	if err != nil {
        		t.Fatalf("unexpected error: %v", err)
        	}
        	if len(schema.Enum) != 2 {
        		t.Fatalf("Enum = %v, want exactly [a b] (eq must not overwrite oneof)", schema.Enum)
        	}
        	a, aok := schema.Enum[0].(string)
        	b, bok := schema.Enum[1].(string)
        	if !aok || !bok || a != "a" || b != "b" {
        		t.Fatalf("Enum = %v, want [\"a\" \"b\"]", schema.Enum)
        	}
        }
        '''
        proc = _run_driver("TestZZOneofWins", body)
        assert proc.returncode == 0, (
            "eq must not overwrite an enum already set by oneof:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "PASS" in proc.stdout

    def test_eq_does_not_overwrite_when_set_first(self):
        """L2: symmetric precedence — `eq=c,oneof=a b` keeps eq's ["c"].

        The first rule to set a non-empty enum wins; the later oneof must not
        overwrite it.  This guards against an eq impl that ignores the existing
        enum or that is placed after oneof unconditionally.
        """
        body = r'''
        func TestZZEqFirstWins(t *testing.T) {
        	schema := spec.Schema{}
        	schema.Type = []string{"string"}
        	err := newTagBaseFieldParser(
        		&Parser{},
        		&ast.Field{Tag: &ast.BasicLit{
        			Value: `json:"v" validate:"eq=c,oneof=a b"`,
        		}},
        	).ComplementSchema(&schema)
        	if err != nil {
        		t.Fatalf("unexpected error: %v", err)
        	}
        	if len(schema.Enum) != 1 {
        		t.Fatalf("Enum = %v, want exactly [c] (eq set first, oneof must not overwrite)", schema.Enum)
        	}
        	if got, ok := schema.Enum[0].(string); !ok || got != "c" {
        		t.Fatalf("Enum[0] = %#v, want string \"c\"", schema.Enum[0])
        	}
        }
        '''
        proc = _run_driver("TestZZEqFirstWins", body)
        assert proc.returncode == 0, (
            "eq set first must not be overwritten by a later oneof:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "PASS" in proc.stdout

    def test_array_eq_enum_on_items(self):
        """L2: for an array field, eq's enum is typed by the element type and
        lands on the items schema (mirroring oneof), not the top-level array.
        """
        body = r'''
        func TestZZArrayEq(t *testing.T) {
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
        			Value: `json:"tags" validate:"eq=fixed"`,
        		}},
        	).ComplementSchema(&schema)
        	if err != nil {
        		t.Fatalf("unexpected error on array field: %v", err)
        	}
        	if len(schema.Enum) != 0 {
        		t.Fatalf("top-level array Enum must stay empty, got %v", schema.Enum)
        	}
        	if schema.Items == nil || schema.Items.Schema == nil {
        		t.Fatalf("items schema missing")
        	}
        	if len(schema.Items.Schema.Enum) != 1 {
        		t.Fatalf("items Enum = %v, want [fixed]", schema.Items.Schema.Enum)
        	}
        	if got, ok := schema.Items.Schema.Enum[0].(string); !ok || got != "fixed" {
        		t.Fatalf("items Enum[0] = %#v, want string \"fixed\"", schema.Items.Schema.Enum[0])
        	}
        }
        '''
        proc = _run_driver("TestZZArrayEq", body)
        assert proc.returncode == 0, (
            "array eq= must place a single typed enum on the items schema:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "PASS" in proc.stdout

    def test_repo_native_validtags_suite_passes(self):
        """L2: the repo's own `go test -run TestValidTags ./...` passes.

        This is exactly the native acceptance command from the task doc and
        also catches regressions in the pre-existing validate-tag handling.
        """
        proc = _run_go(["test", "-run", "TestValidTags", "-count=1", "./..."])
        assert proc.returncode == 0, (
            "native TestValidTags suite failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "ok" in proc.stdout, (
            f"expected a passing package line:\nSTDOUT:\n{proc.stdout}"
        )

    def test_sibling_constraints_preserved(self):
        """L2: pre-existing validate constraints (max/min length, oneof enum,
        unique on array) still derive correctly — guarding that the eq addition
        did not regress sibling constraint handling.
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

        	// oneof -> multi-value enum (must still work after eq added)
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
