"""Benchmark test for skill `go-swagger-codegen` (variant ext7).

Task: add `multiple=<n>` constraint support to the `validate` struct tag in
swaggo/swag's field parser, so the "must be a multiple of N" rule is carried
onto the generated OpenAPI schema's `MultipleOf` field via `ComplementSchema`.

Today `multipleOf` can only be expressed through the dedicated `multipleOf:"..."`
struct tag. This variant lets the comma-separated `validate` tag express it via
a `multiple=<number>` rule, mirroring how `min`/`max`/`gte`/`lte` already flow
through the `validate` tag.

Verification strategy
---------------------
The agent edits `field_parser.go` (and `field_parser_test.go`) inside
REPO_DIR = /workspace/swag.  Rather than trust the test file the agent itself
may write, these tests INJECT an independent in-package Go test driver into
REPO_DIR and run it with the repo's native toolchain (`go test`).  Each driver
constructs `newTagBaseFieldParser(...).ComplementSchema(&schema)` directly and
asserts on the resulting `spec.Schema.MultipleOf` (a `*float64`) — and on
`schema.Items.Schema.MultipleOf` for arrays.  This exercises the real behavior
required by the task; a naive / cosmetic edit (hardcoding, ignoring the value,
setting it on the wrong schema, or suppressing sibling constraints) will fail.

L1: deliverable files exist and are well-formed; package compiles.
L2: dynamic execution of `go test` over injected drivers + the repo's own
    `TestValidTags` suite, deep-validating MultipleOf placement & numeric value,
    integer vs number vs string type handling, array-items placement, edge
    cases (non-numeric / empty value / absent rule), error-freedom, and
    coexistence with `required`/`min`/`max`.
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
    def test_integer_field_multipleof_set(self):
        """L2: `multiple=5` on an integer field sets MultipleOf == 5, no error."""
        body = r'''
        func TestZZIntMultiple(t *testing.T) {
        	schema := spec.Schema{}
        	schema.Type = []string{"integer"}
        	err := newTagBaseFieldParser(
        		&Parser{},
        		&ast.Field{Tag: &ast.BasicLit{
        			Value: `json:"quantity" validate:"multiple=5"`,
        		}},
        	).ComplementSchema(&schema)
        	if err != nil {
        		t.Fatalf("unexpected error: %v", err)
        	}
        	if schema.MultipleOf == nil {
        		t.Fatalf("MultipleOf is nil, want 5")
        	}
        	if *schema.MultipleOf != 5 {
        		t.Fatalf("MultipleOf = %v, want 5", *schema.MultipleOf)
        	}
        }
        '''
        proc = _run_driver("TestZZIntMultiple", body)
        assert proc.returncode == 0, (
            "integer-field multiple=5 not applied to schema.MultipleOf:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "PASS" in proc.stdout

    def test_number_field_fractional_multipleof(self):
        """L2: `multiple=0.25` on a number field sets MultipleOf == 0.25 exactly.

        Guards against a stub that only handles integers or truncates the value.
        """
        body = r'''
        func TestZZNumberMultiple(t *testing.T) {
        	schema := spec.Schema{}
        	schema.Type = []string{"number"}
        	err := newTagBaseFieldParser(
        		&Parser{},
        		&ast.Field{Tag: &ast.BasicLit{
        			Value: `json:"step" validate:"multiple=0.25"`,
        		}},
        	).ComplementSchema(&schema)
        	if err != nil {
        		t.Fatalf("unexpected error: %v", err)
        	}
        	if schema.MultipleOf == nil {
        		t.Fatalf("MultipleOf is nil, want 0.25")
        	}
        	if *schema.MultipleOf != 0.25 {
        		t.Fatalf("MultipleOf = %v, want 0.25", *schema.MultipleOf)
        	}
        }
        '''
        proc = _run_driver("TestZZNumberMultiple", body)
        assert proc.returncode == 0, (
            "number-field multiple=0.25 not applied exactly:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "PASS" in proc.stdout

    def test_string_field_multipleof_ignored(self):
        """L2: `multiple=5` on a string field is silently ignored (nil, no error)."""
        body = r'''
        func TestZZStringMultipleIgnored(t *testing.T) {
        	schema := spec.Schema{}
        	schema.Type = []string{"string"}
        	err := newTagBaseFieldParser(
        		&Parser{},
        		&ast.Field{Tag: &ast.BasicLit{
        			Value: `json:"name" validate:"multiple=5"`,
        		}},
        	).ComplementSchema(&schema)
        	if err != nil {
        		t.Fatalf("unexpected error on string field: %v", err)
        	}
        	if schema.MultipleOf != nil {
        		t.Fatalf("string schema.MultipleOf = %v, want nil", *schema.MultipleOf)
        	}
        }
        '''
        proc = _run_driver("TestZZStringMultipleIgnored", body)
        assert proc.returncode == 0, (
            "multiple on string field must be ignored without error:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "PASS" in proc.stdout

    def test_boolean_field_multipleof_ignored(self):
        """L2: `multiple=2` on a boolean field is silently ignored (nil, no error)."""
        body = r'''
        func TestZZBoolMultipleIgnored(t *testing.T) {
        	schema := spec.Schema{}
        	schema.Type = []string{"boolean"}
        	err := newTagBaseFieldParser(
        		&Parser{},
        		&ast.Field{Tag: &ast.BasicLit{
        			Value: `json:"flag" validate:"multiple=2"`,
        		}},
        	).ComplementSchema(&schema)
        	if err != nil {
        		t.Fatalf("unexpected error on boolean field: %v", err)
        	}
        	if schema.MultipleOf != nil {
        		t.Fatalf("boolean schema.MultipleOf = %v, want nil", *schema.MultipleOf)
        	}
        }
        '''
        proc = _run_driver("TestZZBoolMultipleIgnored", body)
        assert proc.returncode == 0, (
            "multiple on boolean field must be ignored without error:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "PASS" in proc.stdout

    def test_multiple_coexists_with_required_and_min(self):
        """L2: `required,min=10,multiple=5` sets BOTH Minimum==10 and MultipleOf==5.

        Order independent; enabling `multiple` must not suppress min/max, and the
        sibling bound must not suppress `multiple`.
        """
        body = r'''
        func TestZZCoexistMinMultiple(t *testing.T) {
        	schema := spec.Schema{}
        	schema.Type = []string{"integer"}
        	err := newTagBaseFieldParser(
        		&Parser{},
        		&ast.Field{Tag: &ast.BasicLit{
        			Value: `json:"q" validate:"required,min=10,multiple=5"`,
        		}},
        	).ComplementSchema(&schema)
        	if err != nil {
        		t.Fatalf("unexpected error: %v", err)
        	}
        	if schema.Minimum == nil || *schema.Minimum != 10 {
        		got := "nil"
        		if schema.Minimum != nil {
        			got = "set-but-wrong"
        		}
        		t.Fatalf("Minimum not preserved alongside multiple: %s (want 10)", got)
        	}
        	if schema.MultipleOf == nil || *schema.MultipleOf != 5 {
        		t.Fatalf("MultipleOf not set alongside min: %v", schema.MultipleOf)
        	}
        }
        '''
        proc = _run_driver("TestZZCoexistMinMultiple", body)
        assert proc.returncode == 0, (
            "multiple must coexist with required/min:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "PASS" in proc.stdout

    def test_multiple_coexists_with_max_order_independent(self):
        """L2: `multiple=4,max=40` (multiple first) sets BOTH MultipleOf and Maximum."""
        body = r'''
        func TestZZCoexistMaxMultiple(t *testing.T) {
        	schema := spec.Schema{}
        	schema.Type = []string{"integer"}
        	err := newTagBaseFieldParser(
        		&Parser{},
        		&ast.Field{Tag: &ast.BasicLit{
        			Value: `json:"q" validate:"multiple=4,max=40"`,
        		}},
        	).ComplementSchema(&schema)
        	if err != nil {
        		t.Fatalf("unexpected error: %v", err)
        	}
        	if schema.MultipleOf == nil || *schema.MultipleOf != 4 {
        		t.Fatalf("MultipleOf = %v, want 4", schema.MultipleOf)
        	}
        	if schema.Maximum == nil || *schema.Maximum != 40 {
        		t.Fatalf("Maximum not preserved alongside multiple (want 40): %v", schema.Maximum)
        	}
        }
        '''
        proc = _run_driver("TestZZCoexistMaxMultiple", body)
        assert proc.returncode == 0, (
            "multiple must coexist with max, order-independent:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "PASS" in proc.stdout

    def test_array_of_integers_items_multipleof(self):
        """L2: for an array of integers, multiple lands on the items schema only.

        The top-level array schema must NOT gain MultipleOf.
        """
        body = r'''
        func TestZZArrayItemsMultiple(t *testing.T) {
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
        			Value: `json:"vals" validate:"multiple=2"`,
        		}},
        	).ComplementSchema(&schema)
        	if err != nil {
        		t.Fatalf("unexpected error on array field: %v", err)
        	}
        	if schema.MultipleOf != nil {
        		t.Fatalf("top-level array MultipleOf = %v, want nil", *schema.MultipleOf)
        	}
        	if schema.Items == nil || schema.Items.Schema == nil {
        		t.Fatalf("items schema missing")
        	}
        	if schema.Items.Schema.MultipleOf == nil {
        		t.Fatalf("items MultipleOf is nil, want 2")
        	}
        	if *schema.Items.Schema.MultipleOf != 2 {
        		t.Fatalf("items.MultipleOf = %v, want 2", *schema.Items.Schema.MultipleOf)
        	}
        }
        '''
        proc = _run_driver("TestZZArrayItemsMultiple", body)
        assert proc.returncode == 0, (
            "array-of-integers multiple must land on items schema only:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "PASS" in proc.stdout

    def test_non_numeric_value_ignored(self):
        """L2: `multiple=abc` (non-numeric value) is ignored without error."""
        body = r'''
        func TestZZNonNumericMultiple(t *testing.T) {
        	schema := spec.Schema{}
        	schema.Type = []string{"integer"}
        	err := newTagBaseFieldParser(
        		&Parser{},
        		&ast.Field{Tag: &ast.BasicLit{
        			Value: `json:"q" validate:"multiple=abc"`,
        		}},
        	).ComplementSchema(&schema)
        	if err != nil {
        		t.Fatalf("unexpected error for non-numeric multiple: %v", err)
        	}
        	if schema.MultipleOf != nil {
        		t.Fatalf("MultipleOf = %v, want nil for non-numeric value", *schema.MultipleOf)
        	}
        }
        '''
        proc = _run_driver("TestZZNonNumericMultiple", body)
        assert proc.returncode == 0, (
            "non-numeric multiple value must be ignored without error:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "PASS" in proc.stdout

    def test_empty_multiple_value_is_noop(self):
        """L2: `validate:"multiple="` leaves MultipleOf nil and returns no error."""
        body = r'''
        func TestZZEmptyMultiple(t *testing.T) {
        	schema := spec.Schema{}
        	schema.Type = []string{"integer"}
        	err := newTagBaseFieldParser(
        		&Parser{},
        		&ast.Field{Tag: &ast.BasicLit{
        			Value: `json:"q" validate:"multiple="`,
        		}},
        	).ComplementSchema(&schema)
        	if err != nil {
        		t.Fatalf("unexpected error for empty multiple: %v", err)
        	}
        	if schema.MultipleOf != nil {
        		t.Fatalf("MultipleOf = %v, want nil for multiple=", *schema.MultipleOf)
        	}
        }
        '''
        proc = _run_driver("TestZZEmptyMultiple", body)
        assert proc.returncode == 0, (
            "empty multiple value must be a no-op:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "PASS" in proc.stdout

    def test_no_multiple_rule_keeps_multipleof_nil(self):
        """L2: a validate tag without `multiple` leaves MultipleOf nil (unchanged).

        Also asserts the sibling `max` it carries is still derived — guarding the
        edit did not regress the existing numeric constraint handling.
        """
        body = r'''
        func TestZZNoMultiple(t *testing.T) {
        	schema := spec.Schema{}
        	schema.Type = []string{"integer"}
        	err := newTagBaseFieldParser(
        		&Parser{},
        		&ast.Field{Tag: &ast.BasicLit{
        			Value: `json:"q" validate:"required,max=10"`,
        		}},
        	).ComplementSchema(&schema)
        	if err != nil {
        		t.Fatalf("unexpected error: %v", err)
        	}
        	if schema.MultipleOf != nil {
        		t.Fatalf("MultipleOf = %v, want nil when no multiple rule", *schema.MultipleOf)
        	}
        	if schema.Maximum == nil || *schema.Maximum != 10 {
        		got := "nil"
        		if schema.Maximum != nil {
        			got = "set-but-wrong"
        		}
        		t.Fatalf("Maximum regression: %s (want 10)", got)
        	}
        }
        '''
        proc = _run_driver("TestZZNoMultiple", body)
        assert proc.returncode == 0, (
            "non-multiple tag must keep MultipleOf nil and preserve max:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "PASS" in proc.stdout

    def test_dedicated_multipleof_tag_still_works(self):
        """L2: the pre-existing dedicated `multipleOf:"..."` tag is unaffected.

        Guards that wiring `multiple=` through `validate` did not break or shadow
        the original `multipleOf` struct tag.
        """
        body = r'''
        func TestZZDedicatedMultipleOf(t *testing.T) {
        	schema := spec.Schema{}
        	schema.Type = []string{"integer"}
        	err := newTagBaseFieldParser(
        		&Parser{},
        		&ast.Field{Tag: &ast.BasicLit{
        			Value: `json:"q" multipleOf:"7"`,
        		}},
        	).ComplementSchema(&schema)
        	if err != nil {
        		t.Fatalf("unexpected error: %v", err)
        	}
        	if schema.MultipleOf == nil || *schema.MultipleOf != 7 {
        		t.Fatalf("dedicated multipleOf tag regressed: %v (want 7)", schema.MultipleOf)
        	}
        }
        '''
        proc = _run_driver("TestZZDedicatedMultipleOf", body)
        assert proc.returncode == 0, (
            "dedicated multipleOf struct tag must still work:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "PASS" in proc.stdout

    def test_repo_native_validtags_suite_passes(self):
        """L2: the repo's own `go test -run TestValidTags ./...` passes (no regression).

        This is the native acceptance command from the variant doc.
        """
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
        """L2: a driver re-checks pre-existing validate-tag constraints
        (numeric min/max, string length, oneof->enum) still derive correctly —
        guarding that the `multiple` addition did not regress sibling handling.
        """
        body = r'''
        func TestZZSiblingConstraints(t *testing.T) {
        	// integer min/max via validate
        	s0 := spec.Schema{}
        	s0.Type = []string{"integer"}
        	if err := newTagBaseFieldParser(&Parser{},
        		&ast.Field{Tag: &ast.BasicLit{Value: `json:"t" validate:"max=100,min=1"`}},
        	).ComplementSchema(&s0); err != nil {
        		t.Fatalf("int bounds err: %v", err)
        	}
        	if s0.Maximum == nil || *s0.Maximum != 100 || s0.Minimum == nil || *s0.Minimum != 1 {
        		t.Fatalf("int bounds wrong: max=%v min=%v", s0.Maximum, s0.Minimum)
        	}

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
        }
        '''
        proc = _run_driver("TestZZSiblingConstraints", body)
        assert proc.returncode == 0, (
            "sibling validate-tag constraints regressed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "PASS" in proc.stdout
