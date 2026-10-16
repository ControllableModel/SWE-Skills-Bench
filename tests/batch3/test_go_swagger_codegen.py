"""Benchmark test for skill `go-swagger-codegen` (variant ext3).

Task: add fixed-length (`len=<n>`) support to the `validate` struct tag in
swaggo/swag's field parser.  A `len=<n>` rule must set BOTH length bounds of
the generated OpenAPI schema:

  * on a STRING field   -> `MinLength == n` AND `MaxLength == n`
  * on an ARRAY field   -> `MinItems  == n` AND `MaxItems  == n`
  * on INTEGER/NUMBER/BOOLEAN fields  -> silently ignored (no constraint, no error)
  * `len=abc` (non-integer) / `len=` (empty)  -> ignored, no constraint, no error
  * `len=0` on a string -> both bounds set to 0
  * coexists with `required` and other `min`/`max` rules (left-to-right order;
    `len` has no special precedence, it just sets both bounds).

Verification strategy
---------------------
The agent edits `field_parser.go` (and `field_parser_test.go`) inside
REPO_DIR = /workspace/swag.  Rather than trust the agent's own test file,
these tests INJECT an independent in-package Go test driver into REPO_DIR and
run it with the repo's native toolchain (`go test`).  Each driver constructs a
`spec.Schema`, runs `newTagBaseFieldParser(...).ComplementSchema(&schema)`
directly, and asserts on the resulting bound pointers
(`*MinLength`, `*MaxLength`, `*MinItems`, `*MaxItems`).  A naive / cosmetic
edit (one that only sets one bound, hardcodes a value, mishandles type, or
errors on a non-integer) will FAIL.

L1: deliverable files exist and are well-formed; the package compiles.
L2: dynamic execution of `go test` over injected drivers + the repo's own
    `TestValidTags` suite, deep-validating both-bound placement, type
    handling, array-items handling, edge cases (len=0, len=abc, len=),
    error-freedom, ordering/precedence, and coexistence with other rules.
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
    # `go build ./...` warms the module cache and proves the agent's edit
    # compiles before we run any behavioral driver. It does not compile
    # *_test.go, so it is immune to injected driver files.
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
        """L1: field_parser_test.go exists and still defines TestValidTags."""
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
    def test_string_len_sets_both_bounds(self):
        """L2: `len=6` on a string sets BOTH MinLength==6 and MaxLength==6."""
        body = r'''
        func TestZZStringLen(t *testing.T) {
        	schema := spec.Schema{}
        	schema.Type = []string{"string"}
        	err := newTagBaseFieldParser(
        		&Parser{},
        		&ast.Field{Tag: &ast.BasicLit{
        			Value: `json:"code" validate:"len=6"`,
        		}},
        	).ComplementSchema(&schema)
        	if err != nil {
        		t.Fatalf("unexpected error: %v", err)
        	}
        	if schema.MinLength == nil || *schema.MinLength != 6 {
        		t.Fatalf("MinLength = %v, want 6", schema.MinLength)
        	}
        	if schema.MaxLength == nil || *schema.MaxLength != 6 {
        		t.Fatalf("MaxLength = %v, want 6", schema.MaxLength)
        	}
        }
        '''
        proc = _run_driver("TestZZStringLen", body)
        assert proc.returncode == 0, (
            "string-field len did not set both length bounds:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "PASS" in proc.stdout

    def test_array_len_sets_both_item_bounds(self):
        """L2: `len=2` on an array sets BOTH MinItems==2 and MaxItems==2."""
        body = r'''
        func TestZZArrayLen(t *testing.T) {
        	schema := spec.Schema{}
        	schema.Type = []string{"array"}
        	schema.Items = &spec.SchemaOrArray{
        		Schema: &spec.Schema{
        			SchemaProps: spec.SchemaProps{Type: []string{"number"}},
        		},
        	}
        	err := newTagBaseFieldParser(
        		&Parser{},
        		&ast.Field{Tag: &ast.BasicLit{
        			Value: `json:"coords" validate:"len=2"`,
        		}},
        	).ComplementSchema(&schema)
        	if err != nil {
        		t.Fatalf("unexpected error on array field: %v", err)
        	}
        	if schema.MinItems == nil || *schema.MinItems != 2 {
        		t.Fatalf("MinItems = %v, want 2", schema.MinItems)
        	}
        	if schema.MaxItems == nil || *schema.MaxItems != 2 {
        		t.Fatalf("MaxItems = %v, want 2", schema.MaxItems)
        	}
        	// length bounds must NOT be set on an array via len.
        	if schema.MinLength != nil || schema.MaxLength != nil {
        		t.Fatalf("array len must not touch length bounds: min=%v max=%v",
        			schema.MinLength, schema.MaxLength)
        	}
        }
        '''
        proc = _run_driver("TestZZArrayLen", body)
        assert proc.returncode == 0, (
            "array-field len did not set both item bounds correctly:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "PASS" in proc.stdout

    def test_integer_len_ignored(self):
        """L2: `len=6` on an integer field is silently ignored, no error, no bounds."""
        body = r'''
        func TestZZIntLenIgnored(t *testing.T) {
        	schema := spec.Schema{}
        	schema.Type = []string{"integer"}
        	err := newTagBaseFieldParser(
        		&Parser{},
        		&ast.Field{Tag: &ast.BasicLit{
        			Value: `json:"n" validate:"len=6"`,
        		}},
        	).ComplementSchema(&schema)
        	if err != nil {
        		t.Fatalf("unexpected error on integer field: %v", err)
        	}
        	if schema.MinLength != nil || schema.MaxLength != nil {
        		t.Fatalf("integer len leaked length bounds: min=%v max=%v",
        			schema.MinLength, schema.MaxLength)
        	}
        	if schema.MinItems != nil || schema.MaxItems != nil {
        		t.Fatalf("integer len leaked item bounds: min=%v max=%v",
        			schema.MinItems, schema.MaxItems)
        	}
        	// numeric Minimum/Maximum must also stay untouched by `len`.
        	if schema.Minimum != nil || schema.Maximum != nil {
        		t.Fatalf("integer len leaked numeric bounds: min=%v max=%v",
        			schema.Minimum, schema.Maximum)
        	}
        }
        '''
        proc = _run_driver("TestZZIntLenIgnored", body)
        assert proc.returncode == 0, (
            "len on integer field must be ignored without error/constraint:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "PASS" in proc.stdout

    def test_len_zero_on_string(self):
        """L2: `len=0` on a string sets both bounds to 0 (not nil, not skipped)."""
        body = r'''
        func TestZZLenZero(t *testing.T) {
        	schema := spec.Schema{}
        	schema.Type = []string{"string"}
        	err := newTagBaseFieldParser(
        		&Parser{},
        		&ast.Field{Tag: &ast.BasicLit{
        			Value: `json:"empty" validate:"len=0"`,
        		}},
        	).ComplementSchema(&schema)
        	if err != nil {
        		t.Fatalf("unexpected error: %v", err)
        	}
        	if schema.MinLength == nil || *schema.MinLength != 0 {
        		t.Fatalf("MinLength = %v, want 0 (set)", schema.MinLength)
        	}
        	if schema.MaxLength == nil || *schema.MaxLength != 0 {
        		t.Fatalf("MaxLength = %v, want 0 (set)", schema.MaxLength)
        	}
        }
        '''
        proc = _run_driver("TestZZLenZero", body)
        assert proc.returncode == 0, (
            "len=0 must set both string length bounds to 0:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "PASS" in proc.stdout

    def test_len_non_integer_ignored(self):
        """L2: `len=abc` is ignored without error and sets no constraint."""
        body = r'''
        func TestZZLenNonInt(t *testing.T) {
        	schema := spec.Schema{}
        	schema.Type = []string{"string"}
        	err := newTagBaseFieldParser(
        		&Parser{},
        		&ast.Field{Tag: &ast.BasicLit{
        			Value: `json:"v" validate:"len=abc"`,
        		}},
        	).ComplementSchema(&schema)
        	if err != nil {
        		t.Fatalf("non-integer len must not error: %v", err)
        	}
        	if schema.MinLength != nil || schema.MaxLength != nil {
        		t.Fatalf("len=abc must set no bounds: min=%v max=%v",
        			schema.MinLength, schema.MaxLength)
        	}
        }
        '''
        proc = _run_driver("TestZZLenNonInt", body)
        assert proc.returncode == 0, (
            "len=abc must be ignored without error or constraint:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "PASS" in proc.stdout

    def test_len_empty_value_is_noop(self):
        """L2: `validate:"len="` leaves bounds nil and returns no error."""
        body = r'''
        func TestZZLenEmpty(t *testing.T) {
        	schema := spec.Schema{}
        	schema.Type = []string{"string"}
        	err := newTagBaseFieldParser(
        		&Parser{},
        		&ast.Field{Tag: &ast.BasicLit{
        			Value: `json:"v" validate:"len="`,
        		}},
        	).ComplementSchema(&schema)
        	if err != nil {
        		t.Fatalf("empty len must not error: %v", err)
        	}
        	if schema.MinLength != nil || schema.MaxLength != nil {
        		t.Fatalf("len= must set no bounds: min=%v max=%v",
        			schema.MinLength, schema.MaxLength)
        	}
        }
        '''
        proc = _run_driver("TestZZLenEmpty", body)
        assert proc.returncode == 0, (
            "len= must be a no-op without error:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "PASS" in proc.stdout

    def test_len_coexists_with_required(self):
        """L2: `required,len=4` on a string sets both bounds to 4 (required unaffected)."""
        body = r'''
        func TestZZLenRequired(t *testing.T) {
        	schema := spec.Schema{}
        	schema.Type = []string{"string"}
        	ps := newTagBaseFieldParser(
        		&Parser{},
        		&ast.Field{Tag: &ast.BasicLit{
        			Value: `json:"pin" validate:"required,len=4"`,
        		}},
        	)
        	err := ps.ComplementSchema(&schema)
        	if err != nil {
        		t.Fatalf("unexpected error: %v", err)
        	}
        	if schema.MinLength == nil || *schema.MinLength != 4 {
        		t.Fatalf("MinLength = %v, want 4", schema.MinLength)
        	}
        	if schema.MaxLength == nil || *schema.MaxLength != 4 {
        		t.Fatalf("MaxLength = %v, want 4", schema.MaxLength)
        	}
        	req, rerr := ps.IsRequired()
        	if rerr != nil {
        		t.Fatalf("IsRequired error: %v", rerr)
        	}
        	if !req {
        		t.Fatalf("required label must still be honored alongside len")
        	}
        }
        '''
        proc = _run_driver("TestZZLenRequired", body)
        assert proc.returncode == 0, (
            "len must coexist with required and set both bounds:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "PASS" in proc.stdout

    def test_len_then_max_left_to_right(self):
        """L2: with `len=5,max=8` the later `max` wins the upper bound (no special
        precedence for len); min stays 5 from len."""
        body = r'''
        func TestZZLenThenMax(t *testing.T) {
        	schema := spec.Schema{}
        	schema.Type = []string{"string"}
        	err := newTagBaseFieldParser(
        		&Parser{},
        		&ast.Field{Tag: &ast.BasicLit{
        			Value: `json:"v" validate:"len=5,max=8"`,
        		}},
        	).ComplementSchema(&schema)
        	if err != nil {
        		t.Fatalf("unexpected error: %v", err)
        	}
        	// len sets min=5,max=5; then max=8 overrides upper bound.
        	if schema.MinLength == nil || *schema.MinLength != 5 {
        		t.Fatalf("MinLength = %v, want 5 (from len)", schema.MinLength)
        	}
        	if schema.MaxLength == nil || *schema.MaxLength != 8 {
        		t.Fatalf("MaxLength = %v, want 8 (later max wins)", schema.MaxLength)
        	}
        }
        '''
        proc = _run_driver("TestZZLenThenMax", body)
        assert proc.returncode == 0, (
            "left-to-right order: a later max must override len's upper bound:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "PASS" in proc.stdout

    def test_min_then_len_left_to_right(self):
        """L2: with `min=2,len=7` the later `len` overrides the lower bound to 7
        and also sets the upper bound to 7."""
        body = r'''
        func TestZZMinThenLen(t *testing.T) {
        	schema := spec.Schema{}
        	schema.Type = []string{"string"}
        	err := newTagBaseFieldParser(
        		&Parser{},
        		&ast.Field{Tag: &ast.BasicLit{
        			Value: `json:"v" validate:"min=2,len=7"`,
        		}},
        	).ComplementSchema(&schema)
        	if err != nil {
        		t.Fatalf("unexpected error: %v", err)
        	}
        	if schema.MinLength == nil || *schema.MinLength != 7 {
        		t.Fatalf("MinLength = %v, want 7 (later len overrides min=2)", schema.MinLength)
        	}
        	if schema.MaxLength == nil || *schema.MaxLength != 7 {
        		t.Fatalf("MaxLength = %v, want 7 (from len)", schema.MaxLength)
        	}
        }
        '''
        proc = _run_driver("TestZZMinThenLen", body)
        assert proc.returncode == 0, (
            "later len must override an earlier min and set both bounds:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "PASS" in proc.stdout

    def test_no_len_rule_leaves_bounds_unchanged(self):
        """L2: a validate tag without `len` keeps existing min/max behavior; len
        addition must not regress sibling constraint handling."""
        body = r'''
        func TestZZNoLen(t *testing.T) {
        	schema := spec.Schema{}
        	schema.Type = []string{"string"}
        	err := newTagBaseFieldParser(
        		&Parser{},
        		&ast.Field{Tag: &ast.BasicLit{
        			Value: `json:"v" validate:"required,min=2,max=10"`,
        		}},
        	).ComplementSchema(&schema)
        	if err != nil {
        		t.Fatalf("unexpected error: %v", err)
        	}
        	if schema.MinLength == nil || *schema.MinLength != 2 {
        		t.Fatalf("MinLength = %v, want 2", schema.MinLength)
        	}
        	if schema.MaxLength == nil || *schema.MaxLength != 10 {
        		t.Fatalf("MaxLength = %v, want 10", schema.MaxLength)
        	}
        }
        '''
        proc = _run_driver("TestZZNoLen", body)
        assert proc.returncode == 0, (
            "non-len tag must preserve existing min/max behavior:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "PASS" in proc.stdout

    def test_existing_validtags_assertions_preserved(self):
        """L2: a driver re-checks pre-existing validate-tag constraints (max/min
        length, oneof, unique) still derive correctly — guarding that the len
        addition did not regress sibling constraint handling."""
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

    def test_repo_native_validtags_suite_passes(self):
        """L2: the repo's own `go test -run TestValidTags ./...` passes (no regression
        and the agent's new subtest is included)."""
        proc = _run_go(["test", "-run", "TestValidTags", "-count=1", "./..."])
        assert proc.returncode == 0, (
            "native TestValidTags suite failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "ok" in proc.stdout, (
            f"expected a passing package line:\nSTDOUT:\n{proc.stdout}"
        )
