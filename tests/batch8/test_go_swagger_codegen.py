"""Benchmark test for skill `go-swagger-codegen` (variant ext8).

Task: add three MIME-type aliases to swaggo/swag's `mimeTypeAliases` table in
`operation.go` so that the short forms used in `@Accept` / `@Produce` handler
annotations expand to full media types:

    csv  -> text/csv
    yaml -> application/x-yaml
    pdf  -> application/pdf

These aliases are consumed by `parseMimeTypeList`, which backs both
`(*Operation).ParseAcceptComment` (appends to `operation.Consumes`) and
`(*Operation).ParseProduceComment` (appends to `operation.Produces`).

Verification strategy
---------------------
The agent edits `operation.go` (alias table) and extends `operation_test.go`.
Rather than trust the agent's own test edits, these tests INJECT an independent
in-package Go test driver (`package swag`) into REPO_DIR = /workspace/swag and
run it with the repo's native toolchain (`go test`). Each driver constructs a
fresh `NewOperation(&Parser{})`, calls the real `ParseAcceptComment` /
`ParseProduceComment`, and deep-asserts the resulting `Consumes` / `Produces`
slices (exact contents and order). A naive edit that hardcodes a single alias,
breaks ordering, or drops pass-through / error behavior will FAIL.

L1: deliverable files exist and are well-formed; the package compiles.
L2: dynamic execution of injected `go test` drivers + the repo's own
    `TestParseAcceptComment|TestParseProduceComment` suite, deep-validating
    each new alias, comma-list ordering, full-MIME pass-through, unknown-alias
    error, and no regression of pre-existing aliases.
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
        \t"testing"
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


# A small Go helper, embedded into each driver, that exercises the *public*
# parse path and returns the resulting slice. Defined per-driver to keep each
# injected file self-contained.
_PARSE_HELPERS = r'''
func zzAccept(arg string) ([]string, error) {
	op := NewOperation(&Parser{})
	err := op.ParseAcceptComment(arg)
	return op.Consumes, err
}

func zzProduce(arg string) ([]string, error) {
	op := NewOperation(&Parser{})
	err := op.ParseProduceComment(arg)
	return op.Produces, err
}

func zzEqual(got, want []string) bool {
	if len(got) != len(want) {
		return false
	}
	for i := range got {
		if got[i] != want[i] {
			return false
		}
	}
	return true
}
'''


class TestGoSwaggerCodegen:
    REPO_DIR = "/workspace/swag"

    # ------------------------------------------------------------------ #
    # L1 — deliverables exist and are well-formed.
    # ------------------------------------------------------------------ #
    def test_operation_source_exists(self):
        """L1: operation.go (the file to modify) exists and is non-trivial."""
        path = os.path.join(self.REPO_DIR, "operation.go")
        assert os.path.isfile(path), f"missing {path}"
        assert os.path.getsize(path) > 1000, "operation.go unexpectedly small"

    def test_alias_table_present_in_source(self):
        """L1: the mimeTypeAliases table still exists in operation.go.

        Existence/structure only (an L1 well-formedness check); behavioral
        correctness of the new aliases is validated dynamically in L2.
        """
        path = os.path.join(self.REPO_DIR, "operation.go")
        with open(path) as fh:
            content = fh.read()
        assert "mimeTypeAliases" in content, (
            "mimeTypeAliases table must remain in operation.go"
        )
        assert "func parseMimeTypeList(" in content, (
            "parseMimeTypeList must remain in operation.go"
        )

    def test_operation_test_source_exists(self):
        """L1: operation_test.go exists and retains the accept/produce tests."""
        path = os.path.join(self.REPO_DIR, "operation_test.go")
        assert os.path.isfile(path), f"missing {path}"
        with open(path) as fh:
            content = fh.read()
        assert "func TestParseAcceptComment(" in content, (
            "TestParseAcceptComment must remain in operation_test.go"
        )
        assert "func TestParseProduceComment(" in content, (
            "TestParseProduceComment must remain in operation_test.go"
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
    def test_accept_csv_alias(self):
        """L2: `@Accept csv` -> operation.Consumes == ["text/csv"]."""
        body = _PARSE_HELPERS + r'''
        func TestZZAcceptCSV(t *testing.T) {
        	got, err := zzAccept("csv")
        	if err != nil {
        		t.Fatalf("unexpected error: %v", err)
        	}
        	want := []string{"text/csv"}
        	if !zzEqual(got, want) {
        		t.Fatalf("Consumes = %#v, want %#v", got, want)
        	}
        }
        '''
        proc = _run_driver("TestZZAcceptCSV", body)
        assert proc.returncode == 0, (
            "@Accept csv did not expand to text/csv:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "PASS" in proc.stdout

    def test_produce_yaml_alias(self):
        """L2: `@Produce yaml` -> operation.Produces == ["application/x-yaml"]."""
        body = _PARSE_HELPERS + r'''
        func TestZZProduceYAML(t *testing.T) {
        	got, err := zzProduce("yaml")
        	if err != nil {
        		t.Fatalf("unexpected error: %v", err)
        	}
        	want := []string{"application/x-yaml"}
        	if !zzEqual(got, want) {
        		t.Fatalf("Produces = %#v, want %#v", got, want)
        	}
        }
        '''
        proc = _run_driver("TestZZProduceYAML", body)
        assert proc.returncode == 0, (
            "@Produce yaml did not expand to application/x-yaml:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "PASS" in proc.stdout

    def test_produce_pdf_alias(self):
        """L2: `@Produce pdf` -> operation.Produces == ["application/pdf"]."""
        body = _PARSE_HELPERS + r'''
        func TestZZProducePDF(t *testing.T) {
        	got, err := zzProduce("pdf")
        	if err != nil {
        		t.Fatalf("unexpected error: %v", err)
        	}
        	want := []string{"application/pdf"}
        	if !zzEqual(got, want) {
        		t.Fatalf("Produces = %#v, want %#v", got, want)
        	}
        }
        '''
        proc = _run_driver("TestZZProducePDF", body)
        assert proc.returncode == 0, (
            "@Produce pdf did not expand to application/pdf:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "PASS" in proc.stdout

    def test_accept_csv_also_on_accept_path(self):
        """L2: csv alias works on the Accept path too (not just Produce).

        Guards against a stub that registers an alias only for one direction;
        aliases live in a shared table consulted by both.
        """
        body = _PARSE_HELPERS + r'''
        func TestZZAcceptYAMLandPDF(t *testing.T) {
        	got, err := zzAccept("yaml")
        	if err != nil {
        		t.Fatalf("unexpected error on accept yaml: %v", err)
        	}
        	if !zzEqual(got, []string{"application/x-yaml"}) {
        		t.Fatalf("Accept yaml Consumes = %#v, want [application/x-yaml]", got)
        	}
        	got2, err2 := zzAccept("pdf")
        	if err2 != nil {
        		t.Fatalf("unexpected error on accept pdf: %v", err2)
        	}
        	if !zzEqual(got2, []string{"application/pdf"}) {
        		t.Fatalf("Accept pdf Consumes = %#v, want [application/pdf]", got2)
        	}
        }
        '''
        proc = _run_driver("TestZZAcceptYAMLandPDF", body)
        assert proc.returncode == 0, (
            "yaml/pdf aliases must resolve on the Accept path as well:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "PASS" in proc.stdout

    def test_comma_list_ordering(self):
        """L2: `@Accept json,csv` -> ["application/json", "text/csv"] in order.

        A naive implementation that resolves only one entry, reorders, or
        de-duplicates will fail.
        """
        body = _PARSE_HELPERS + r'''
        func TestZZCommaList(t *testing.T) {
        	got, err := zzAccept("json,csv")
        	if err != nil {
        		t.Fatalf("unexpected error: %v", err)
        	}
        	want := []string{"application/json", "text/csv"}
        	if !zzEqual(got, want) {
        		t.Fatalf("Consumes = %#v, want %#v (order matters)", got, want)
        	}
        }
        '''
        proc = _run_driver("TestZZCommaList", body)
        assert proc.returncode == 0, (
            "comma-separated alias list did not resolve each entry in order:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "PASS" in proc.stdout

    def test_comma_list_mixed_new_aliases(self):
        """L2: a mixed list of the three new aliases resolves each independently.

        `@Produce csv,yaml,pdf` -> [text/csv, application/x-yaml, application/pdf].
        """
        body = _PARSE_HELPERS + r'''
        func TestZZMixedNew(t *testing.T) {
        	got, err := zzProduce("csv,yaml,pdf")
        	if err != nil {
        		t.Fatalf("unexpected error: %v", err)
        	}
        	want := []string{"text/csv", "application/x-yaml", "application/pdf"}
        	if !zzEqual(got, want) {
        		t.Fatalf("Produces = %#v, want %#v", got, want)
        	}
        }
        '''
        proc = _run_driver("TestZZMixedNew", body)
        assert proc.returncode == 0, (
            "mixed new-alias list did not resolve each entry correctly:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "PASS" in proc.stdout

    def test_full_mime_passthrough(self):
        """L2: a fully-qualified `type/subtype` still passes through unchanged.

        Ensures the alias addition did not break the regex pass-through branch.
        """
        body = _PARSE_HELPERS + r'''
        func TestZZPassthrough(t *testing.T) {
        	got, err := zzAccept("application/vnd.custom+json")
        	if err != nil {
        		t.Fatalf("unexpected error: %v", err)
        	}
        	if !zzEqual(got, []string{"application/vnd.custom+json"}) {
        		t.Fatalf("Consumes = %#v, want passthrough", got)
        	}
        	// mix a raw MIME with a new alias
        	got2, err2 := zzProduce("text/csv,pdf")
        	if err2 != nil {
        		t.Fatalf("unexpected error: %v", err2)
        	}
        	if !zzEqual(got2, []string{"text/csv", "application/pdf"}) {
        		t.Fatalf("Produces = %#v, want [text/csv application/pdf]", got2)
        	}
        }
        '''
        proc = _run_driver("TestZZPassthrough", body)
        assert proc.returncode == 0, (
            "fully-qualified MIME pass-through regressed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "PASS" in proc.stdout

    def test_unknown_alias_errors(self):
        """L2: an unknown alias (not an alias, not type/subtype) returns error.

        Unchanged behavior — guards against a too-permissive edit that swallows
        bad input.
        """
        body = _PARSE_HELPERS + r'''
        func TestZZUnknownErrors(t *testing.T) {
        	_, err := zzAccept("bogus")
        	if err == nil {
        		t.Fatalf("expected error for unknown alias 'bogus', got nil")
        	}
        	// a valid alias mixed with a bogus one must still error.
        	_, err2 := zzProduce("csv,definitelynotamime")
        	if err2 == nil {
        		t.Fatalf("expected error for list containing unknown alias, got nil")
        	}
        }
        '''
        proc = _run_driver("TestZZUnknownErrors", body)
        assert proc.returncode == 0, (
            "unknown alias must still produce an error:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "PASS" in proc.stdout

    def test_preexisting_aliases_preserved(self):
        """L2: pre-existing aliases (json, xml, plain, octet-stream) still work.

        Guards against an edit that replaces, rather than extends, the table.
        """
        body = _PARSE_HELPERS + r'''
        func TestZZPreexisting(t *testing.T) {
        	cases := []struct {
        		in   string
        		want string
        	}{
        		{"json", "application/json"},
        		{"xml", "text/xml"},
        		{"plain", "text/plain"},
        		{"html", "text/html"},
        		{"octet-stream", "application/octet-stream"},
        	}
        	for _, c := range cases {
        		got, err := zzAccept(c.in)
        		if err != nil {
        			t.Fatalf("alias %q: unexpected error %v", c.in, err)
        		}
        		if !zzEqual(got, []string{c.want}) {
        			t.Fatalf("alias %q -> %#v, want [%s]", c.in, got, c.want)
        		}
        	}
        }
        '''
        proc = _run_driver("TestZZPreexisting", body)
        assert proc.returncode == 0, (
            "pre-existing aliases regressed after adding new ones:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "PASS" in proc.stdout

    def test_new_aliases_distinct_values(self):
        """L2: each new alias maps to its OWN distinct media type.

        A stub that hardcodes a single output for any of the three new aliases
        (e.g. always 'text/csv') is caught here: csv/yaml/pdf must differ.
        """
        body = _PARSE_HELPERS + r'''
        func TestZZDistinct(t *testing.T) {
        	csv, _ := zzAccept("csv")
        	yaml, _ := zzAccept("yaml")
        	pdf, _ := zzAccept("pdf")
        	if len(csv) != 1 || len(yaml) != 1 || len(pdf) != 1 {
        		t.Fatalf("each alias must yield exactly one entry: csv=%v yaml=%v pdf=%v", csv, yaml, pdf)
        	}
        	if csv[0] == yaml[0] || csv[0] == pdf[0] || yaml[0] == pdf[0] {
        		t.Fatalf("new aliases must map to distinct types: csv=%s yaml=%s pdf=%s", csv[0], yaml[0], pdf[0])
        	}
        	if csv[0] != "text/csv" || yaml[0] != "application/x-yaml" || pdf[0] != "application/pdf" {
        		t.Fatalf("wrong mappings: csv=%s yaml=%s pdf=%s", csv[0], yaml[0], pdf[0])
        	}
        }
        '''
        proc = _run_driver("TestZZDistinct", body)
        assert proc.returncode == 0, (
            "new aliases must map to distinct, correct media types:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "PASS" in proc.stdout

    def test_repo_native_accept_produce_suite_passes(self):
        """L2: the repo's own accept/produce suite passes (native acceptance cmd).

        Drives exactly the doc's command:
            go test -run 'TestParseAcceptComment|TestParseProduceComment' ./...
        """
        proc = _run_go(
            [
                "test",
                "-run",
                "TestParseAcceptComment|TestParseProduceComment",
                "-count=1",
                "./...",
            ]
        )
        assert proc.returncode == 0, (
            "native accept/produce suite failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "ok" in proc.stdout, (
            f"expected a passing package line:\nSTDOUT:\n{proc.stdout}"
        )
