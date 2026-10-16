"""Benchmark test for skill `go-swagger-codegen` (variant: ext2).

Task: add EXCLUSIVE numeric-bound support to the `validate` struct tag in
swaggo/swag's field parser.  Two new rules must be recognized on numeric
fields and carried onto the generated OpenAPI schema via `ComplementSchema`:

  * `gt=<n>`  -> schema.Minimum == <n>  AND schema.ExclusiveMinimum == true
  * `lt=<n>`  -> schema.Maximum == <n>  AND schema.ExclusiveMaximum == true

The inclusive rules (`min`/`gte`, `max`/`lte`) must keep working and must
leave the exclusive flags false.  Rules apply only to `integer`/`number`
scalar fields; on `string`/`boolean` they are silently ignored; for an array
of integers the bound + flag land on the items schema only.  Non-numeric and
empty values are no-ops, and `ComplementSchema` must never return an error in
these cases.

Verification strategy
---------------------
The agent edits `field_parser.go` (and `field_parser_test.go`) inside
REPO_DIR = /workspace/swag.  Rather than trust the test the agent itself may
write, these tests INJECT an independent in-package Go test driver into
REPO_DIR and run it with the repo's native toolchain (`go test`).  Each driver
constructs a `*tagBaseFieldParser` directly via the package-internal
`newTagBaseFieldParser(...)`, calls `.ComplementSchema(&schema)`, and asserts
on the resulting `spec.Schema` (`Minimum`/`Maximum` pointers and the
`ExclusiveMinimum`/`ExclusiveMaximum` booleans, plus `Items.Schema` for the
array case).  A naive / cosmetic edit (ignores the value, never sets the flag,
sets the flag without the bound, or mishandles arrays/strings) fails.

L1: deliverable files exist and are well-formed; the package compiles.
L2: dynamic execution of `go test` over injected drivers + the repo's own
    `TestValidTags` suite, deep-validating bound value + exclusive flag,
    inclusive-vs-exclusive distinction, type handling, array-items placement,
    edge cases, error-freedom and coexistence with `required`.

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
    """Inject driver, run `go test -run <test_name>`, clean up."""
    path = _write_driver(body)
    try:
        return _run_go(["test", "-run", f"^{test_name}$", "-v", "-count=1", "."])
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
    # compiles before any behavioral driver runs. It does not compile *_test.go,
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
    def test_gt_sets_exclusive_minimum_on_integer(self):
        """L2: `gt=0` on an integer sets Minimum==0 and ExclusiveMinimum==true."""
        body = r'''
        func TestZZGtInteger(t *testing.T) {
        	schema := spec.Schema{}
        	schema.Type = []string{"integer"}
        	err := newTagBaseFieldParser(
        		&Parser{},
        		&ast.Field{Tag: &ast.BasicLit{
        			Value: `json:"age" validate:"gt=0"`,
        		}},
        	).ComplementSchema(&schema)
        	if err != nil {
        		t.Fatalf("unexpected error: %v", err)
        	}
        	if schema.Minimum == nil || *schema.Minimum != 0 {
        		t.Fatalf("Minimum = %v, want 0", schema.Minimum)
        	}
        	if !schema.ExclusiveMinimum {
        		t.Fatalf("ExclusiveMinimum = false, want true for gt=")
        	}
        	if schema.ExclusiveMaximum {
        		t.Fatalf("ExclusiveMaximum should stay false when only gt= given")
        	}
        }
        '''
        proc = _run_driver("TestZZGtInteger", body)
        assert proc.returncode == 0, (
            "gt= must set Minimum + ExclusiveMinimum on integer:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "PASS" in proc.stdout

    def test_lt_sets_exclusive_maximum_on_number(self):
        """L2: `lt=10` on a number field sets Maximum==10 and ExclusiveMaximum==true."""
        body = r'''
        func TestZZLtNumber(t *testing.T) {
        	schema := spec.Schema{}
        	schema.Type = []string{"number"}
        	err := newTagBaseFieldParser(
        		&Parser{},
        		&ast.Field{Tag: &ast.BasicLit{
        			Value: `json:"price" validate:"lt=10"`,
        		}},
        	).ComplementSchema(&schema)
        	if err != nil {
        		t.Fatalf("unexpected error: %v", err)
        	}
        	if schema.Maximum == nil || *schema.Maximum != 10 {
        		t.Fatalf("Maximum = %v, want 10", schema.Maximum)
        	}
        	if !schema.ExclusiveMaximum {
        		t.Fatalf("ExclusiveMaximum = false, want true for lt=")
        	}
        	if schema.ExclusiveMinimum {
        		t.Fatalf("ExclusiveMinimum should stay false when only lt= given")
        	}
        }
        '''
        proc = _run_driver("TestZZLtNumber", body)
        assert proc.returncode == 0, (
            "lt= must set Maximum + ExclusiveMaximum on number:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "PASS" in proc.stdout

    def test_gt_and_lt_coexist_with_required(self):
        """L2: `gt=0,lt=130` (with required, order independent) sets both bounds
        and both exclusive flags — the headline acceptance criterion."""
        body = r'''
        func TestZZGtLtCoexist(t *testing.T) {
        	schema := spec.Schema{}
        	schema.Type = []string{"integer"}
        	err := newTagBaseFieldParser(
        		&Parser{},
        		&ast.Field{Tag: &ast.BasicLit{
        			Value: `json:"v" validate:"gt=0,required,lt=130"`,
        		}},
        	).ComplementSchema(&schema)
        	if err != nil {
        		t.Fatalf("unexpected error: %v", err)
        	}
        	if schema.Minimum == nil || *schema.Minimum != 0 {
        		t.Fatalf("Minimum = %v, want 0", schema.Minimum)
        	}
        	if schema.Maximum == nil || *schema.Maximum != 130 {
        		t.Fatalf("Maximum = %v, want 130", schema.Maximum)
        	}
        	if !schema.ExclusiveMinimum {
        		t.Fatalf("ExclusiveMinimum = false, want true")
        	}
        	if !schema.ExclusiveMaximum {
        		t.Fatalf("ExclusiveMaximum = false, want true")
        	}
        }
        '''
        proc = _run_driver("TestZZGtLtCoexist", body)
        assert proc.returncode == 0, (
            "gt= and lt= must coexist (with required) and set both flags:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "PASS" in proc.stdout

    def test_inclusive_gte_does_not_set_exclusive_flag(self):
        """L2: `gte=0` sets Minimum==0 but ExclusiveMinimum stays false
        (discriminates real impl from one that flags every lower bound)."""
        body = r'''
        func TestZZGteInclusive(t *testing.T) {
        	schema := spec.Schema{}
        	schema.Type = []string{"integer"}
        	err := newTagBaseFieldParser(
        		&Parser{},
        		&ast.Field{Tag: &ast.BasicLit{
        			Value: `json:"v" validate:"gte=0"`,
        		}},
        	).ComplementSchema(&schema)
        	if err != nil {
        		t.Fatalf("unexpected error: %v", err)
        	}
        	if schema.Minimum == nil || *schema.Minimum != 0 {
        		t.Fatalf("Minimum = %v, want 0", schema.Minimum)
        	}
        	if schema.ExclusiveMinimum {
        		t.Fatalf("ExclusiveMinimum = true, want false for inclusive gte=")
        	}
        }
        '''
        proc = _run_driver("TestZZGteInclusive", body)
        assert proc.returncode == 0, (
            "gte= must NOT set ExclusiveMinimum:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "PASS" in proc.stdout

    def test_inclusive_lte_does_not_set_exclusive_flag(self):
        """L2: `gte=1,lte=9` sets both bounds, both exclusive flags stay false."""
        body = r'''
        func TestZZLteInclusive(t *testing.T) {
        	schema := spec.Schema{}
        	schema.Type = []string{"integer"}
        	err := newTagBaseFieldParser(
        		&Parser{},
        		&ast.Field{Tag: &ast.BasicLit{
        			Value: `json:"v" validate:"gte=1,lte=9"`,
        		}},
        	).ComplementSchema(&schema)
        	if err != nil {
        		t.Fatalf("unexpected error: %v", err)
        	}
        	if schema.Minimum == nil || *schema.Minimum != 1 {
        		t.Fatalf("Minimum = %v, want 1", schema.Minimum)
        	}
        	if schema.Maximum == nil || *schema.Maximum != 9 {
        		t.Fatalf("Maximum = %v, want 9", schema.Maximum)
        	}
        	if schema.ExclusiveMinimum || schema.ExclusiveMaximum {
        		t.Fatalf("inclusive lte/gte must leave both exclusive flags false: min=%v max=%v",
        			schema.ExclusiveMinimum, schema.ExclusiveMaximum)
        	}
        }
        '''
        proc = _run_driver("TestZZLteInclusive", body)
        assert proc.returncode == 0, (
            "gte=/lte= must leave exclusive flags false while setting bounds:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "PASS" in proc.stdout

    def test_gt_lt_ignored_on_string_field(self):
        """L2: `gt=0,lt=5` on a string field sets no numeric bound and no
        exclusive flag, and returns no error (silently ignored)."""
        body = r'''
        func TestZZGtLtString(t *testing.T) {
        	schema := spec.Schema{}
        	schema.Type = []string{"string"}
        	err := newTagBaseFieldParser(
        		&Parser{},
        		&ast.Field{Tag: &ast.BasicLit{
        			Value: `json:"v" validate:"gt=0,lt=5"`,
        		}},
        	).ComplementSchema(&schema)
        	if err != nil {
        		t.Fatalf("unexpected error on string field: %v", err)
        	}
        	if schema.Minimum != nil {
        		t.Fatalf("string Minimum = %v, want nil", schema.Minimum)
        	}
        	if schema.Maximum != nil {
        		t.Fatalf("string Maximum = %v, want nil", schema.Maximum)
        	}
        	if schema.ExclusiveMinimum || schema.ExclusiveMaximum {
        		t.Fatalf("string field must not gain exclusive flags: min=%v max=%v",
        			schema.ExclusiveMinimum, schema.ExclusiveMaximum)
        	}
        }
        '''
        proc = _run_driver("TestZZGtLtString", body)
        assert proc.returncode == 0, (
            "gt=/lt= on string field must be a no-op:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "PASS" in proc.stdout

    def test_gt_lt_on_array_lands_on_items_schema(self):
        """L2: for an array of integers, `gt=0,lt=5` bounds + exclusive flags
        land on schema.Items.Schema; the top-level array schema stays clean."""
        body = r'''
        func TestZZGtLtArrayItems(t *testing.T) {
        	schema := spec.Schema{}
        	schema.Type = []string{"array"}
        	schema.Items = &spec.SchemaOrArray{
        		Schema: &spec.Schema{
        			SchemaProps: spec.SchemaProps{Type: []string{"integer"}},
        		},
        	}
        	err := newTagBaseFieldParser(
        		&Parser{},
        		&ast.Field{Tag: &ast.BasicLit{
        			Value: `json:"v" validate:"gt=0,lt=5"`,
        		}},
        	).ComplementSchema(&schema)
        	if err != nil {
        		t.Fatalf("unexpected error on array field: %v", err)
        	}
        	if schema.Minimum != nil || schema.Maximum != nil {
        		t.Fatalf("top-level array must not gain bounds: min=%v max=%v",
        			schema.Minimum, schema.Maximum)
        	}
        	if schema.ExclusiveMinimum || schema.ExclusiveMaximum {
        		t.Fatalf("top-level array must not gain exclusive flags")
        	}
        	if schema.Items == nil || schema.Items.Schema == nil {
        		t.Fatalf("items schema missing")
        	}
        	it := schema.Items.Schema
        	if it.Minimum == nil || *it.Minimum != 0 {
        		t.Fatalf("items Minimum = %v, want 0", it.Minimum)
        	}
        	if it.Maximum == nil || *it.Maximum != 5 {
        		t.Fatalf("items Maximum = %v, want 5", it.Maximum)
        	}
        	if !it.ExclusiveMinimum || !it.ExclusiveMaximum {
        		t.Fatalf("items must carry exclusive flags: min=%v max=%v",
        			it.ExclusiveMinimum, it.ExclusiveMaximum)
        	}
        }
        '''
        proc = _run_driver("TestZZGtLtArrayItems", body)
        assert proc.returncode == 0, (
            "array gt=/lt= must land on items schema only:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "PASS" in proc.stdout

    def test_non_numeric_value_is_noop(self):
        """L2: `gt=abc` (unparseable) sets no bound, no flag, and no error."""
        body = r'''
        func TestZZGtNonNumeric(t *testing.T) {
        	schema := spec.Schema{}
        	schema.Type = []string{"integer"}
        	err := newTagBaseFieldParser(
        		&Parser{},
        		&ast.Field{Tag: &ast.BasicLit{
        			Value: `json:"v" validate:"gt=abc"`,
        		}},
        	).ComplementSchema(&schema)
        	if err != nil {
        		t.Fatalf("unexpected error for gt=abc: %v", err)
        	}
        	if schema.Minimum != nil {
        		t.Fatalf("Minimum = %v, want nil for unparseable value", schema.Minimum)
        	}
        	if schema.ExclusiveMinimum {
        		t.Fatalf("ExclusiveMinimum = true, want false for unparseable value")
        	}
        }
        '''
        proc = _run_driver("TestZZGtNonNumeric", body)
        assert proc.returncode == 0, (
            "gt=<non-numeric> must be ignored without error or flag:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "PASS" in proc.stdout

    def test_empty_value_is_noop(self):
        """L2: `validate:"gt="` is treated as no constraint: no bound, no flag."""
        body = r'''
        func TestZZGtEmpty(t *testing.T) {
        	schema := spec.Schema{}
        	schema.Type = []string{"integer"}
        	err := newTagBaseFieldParser(
        		&Parser{},
        		&ast.Field{Tag: &ast.BasicLit{
        			Value: `json:"v" validate:"gt="`,
        		}},
        	).ComplementSchema(&schema)
        	if err != nil {
        		t.Fatalf("unexpected error for empty gt: %v", err)
        	}
        	if schema.Minimum != nil {
        		t.Fatalf("Minimum = %v, want nil for gt=", schema.Minimum)
        	}
        	if schema.ExclusiveMinimum {
        		t.Fatalf("ExclusiveMinimum = true, want false for gt=")
        	}
        }
        '''
        proc = _run_driver("TestZZGtEmpty", body)
        assert proc.returncode == 0, (
            "empty gt= value must be a no-op:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "PASS" in proc.stdout

    def test_no_gt_lt_rule_leaves_flags_false(self):
        """L2: a validate tag without gt/lt leaves both exclusive flags false
        and inclusive bounds intact (no regression to existing behavior)."""
        body = r'''
        func TestZZNoGtLt(t *testing.T) {
        	schema := spec.Schema{}
        	schema.Type = []string{"integer"}
        	err := newTagBaseFieldParser(
        		&Parser{},
        		&ast.Field{Tag: &ast.BasicLit{
        			Value: `json:"v" validate:"required,min=2,max=8"`,
        		}},
        	).ComplementSchema(&schema)
        	if err != nil {
        		t.Fatalf("unexpected error: %v", err)
        	}
        	if schema.ExclusiveMinimum || schema.ExclusiveMaximum {
        		t.Fatalf("exclusive flags must stay false: min=%v max=%v",
        			schema.ExclusiveMinimum, schema.ExclusiveMaximum)
        	}
        	if schema.Minimum == nil || *schema.Minimum != 2 {
        		t.Fatalf("inclusive min regression: Minimum=%v want 2", schema.Minimum)
        	}
        	if schema.Maximum == nil || *schema.Maximum != 8 {
        		t.Fatalf("inclusive max regression: Maximum=%v want 8", schema.Maximum)
        	}
        }
        '''
        proc = _run_driver("TestZZNoGtLt", body)
        assert proc.returncode == 0, (
            "tag without gt/lt must keep flags false and inclusive bounds intact:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "PASS" in proc.stdout

    def test_repo_native_validtags_suite_passes(self):
        """L2: the repo's own `go test -run TestValidTags ./...` passes — the
        native acceptance command from the task doc (no regression)."""
        proc = _run_go(["test", "-run", "TestValidTags", "-count=1", "./..."])
        assert proc.returncode == 0, (
            "native TestValidTags suite failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "ok" in proc.stdout, (
            f"expected a passing package line:\nSTDOUT:\n{proc.stdout}"
        )

    def test_existing_sibling_constraints_preserved(self):
        """L2: a driver re-checks pre-existing validate-tag constraints
        (string max/min length, oneof->enum, array unique) still derive
        correctly — guarding that the gt/lt addition did not regress siblings.
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
