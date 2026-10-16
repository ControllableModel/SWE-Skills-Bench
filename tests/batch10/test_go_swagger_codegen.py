"""Benchmark test for skill `go-swagger-codegen` (variant ext10).

Task: reject a duplicate `@Router` path+method on a single operation.

The agent must modify `ParseRouterComment` in `operation.go` so that registering
a route whose parsed `Path` and upper-cased `HTTPMethod` exactly match an
already-registered entry on the same `Operation` returns a non-nil error and
does NOT append a second identical `RouteProperties` entry. Distinct-method,
distinct-path, and the very first registration must all still succeed, and the
`deprecated` flag must not change the duplicate semantics. Pre-existing
malformed-comment / invalid-method errors must keep returning errors.

Verification strategy
---------------------
The agent edits `operation.go` (and adds a test to `operation_test.go`) inside
REPO_DIR = /workspace/swag. Rather than trust the agent's own test, these tests
INJECT an independent in-package Go test driver (package swag) into REPO_DIR and
run it with the repo's native toolchain (`go test`). Each driver builds a fresh
`*Operation` via `NewOperation(nil)`, calls `ParseRouterComment(...)` directly,
and asserts on the returned error and the resulting `operation.RouterProperties`
slice (length, Path, HTTPMethod). This exercises the real required behavior; a
naive implementation that always appends (or never appends) will fail.

L1: deliverable files exist and are well-formed; the package compiles.
L2: dynamic execution of `go test` over injected drivers covering duplicate
    rejection, distinct-method / distinct-path acceptance, single-route success,
    deprecated-flag handling, preserved malformed/invalid-method errors, plus the
    repo's own TestParseRouter* suite (no regression).
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
    def test_operation_source_exists(self):
        """L1: operation.go (the file to modify) exists and is non-trivial."""
        path = os.path.join(self.REPO_DIR, "operation.go")
        assert os.path.isfile(path), f"missing {path}"
        assert os.path.getsize(path) > 1000, "operation.go unexpectedly small"

    def test_parse_router_comment_present(self):
        """L1: ParseRouterComment is still defined on *Operation."""
        path = os.path.join(self.REPO_DIR, "operation.go")
        with open(path) as fh:
            content = fh.read()
        assert "func (operation *Operation) ParseRouterComment(" in content, (
            "ParseRouterComment must remain a method on *Operation"
        )
        assert "RouterProperties" in content, (
            "RouterProperties slice must remain on Operation"
        )

    def test_operation_test_source_exists(self):
        """L1: operation_test.go exists and keeps the pre-existing router tests."""
        path = os.path.join(self.REPO_DIR, "operation_test.go")
        assert os.path.isfile(path), f"missing {path}"
        with open(path) as fh:
            content = fh.read()
        assert "func TestParseRouterComment(" in content, (
            "TestParseRouterComment must remain in operation_test.go"
        )
        assert "func TestParseRouterMultipleComments(" in content, (
            "TestParseRouterMultipleComments must remain in operation_test.go"
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
    def test_single_route_succeeds(self):
        """L2: a first `/users [get]` succeeds with one entry, Path/Method correct."""
        body = r'''
        func TestZZSingleRoute(t *testing.T) {
        	op := NewOperation(nil)
        	if err := op.ParseRouterComment("/users [get]", false); err != nil {
        		t.Fatalf("first /users [get] should succeed, got err: %v", err)
        	}
        	if len(op.RouterProperties) != 1 {
        		t.Fatalf("RouterProperties len = %d, want 1", len(op.RouterProperties))
        	}
        	rp := op.RouterProperties[0]
        	if rp.Path != "/users" {
        		t.Fatalf("Path = %q, want %q", rp.Path, "/users")
        	}
        	if rp.HTTPMethod != "GET" {
        		t.Fatalf("HTTPMethod = %q, want %q", rp.HTTPMethod, "GET")
        	}
        }
        '''
        proc = _run_driver("TestZZSingleRoute", body)
        assert proc.returncode == 0, (
            "single route registration regressed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "PASS" in proc.stdout

    def test_exact_duplicate_rejected(self):
        """L2: `/users [get]` twice -> second errors, slice still length 1.

        A naive implementation that always appends would produce length 2 and a
        nil second error; both are caught here.
        """
        body = r'''
        func TestZZDuplicateRejected(t *testing.T) {
        	op := NewOperation(nil)
        	if err := op.ParseRouterComment("/users [get]", false); err != nil {
        		t.Fatalf("first call should succeed, got: %v", err)
        	}
        	err := op.ParseRouterComment("/users [get]", false)
        	if err == nil {
        		t.Fatalf("second identical /users [get] must return a non-nil error")
        	}
        	if len(op.RouterProperties) != 1 {
        		t.Fatalf("after duplicate, RouterProperties len = %d, want 1", len(op.RouterProperties))
        	}
        }
        '''
        proc = _run_driver("TestZZDuplicateRejected", body)
        assert proc.returncode == 0, (
            "exact duplicate path+method must be rejected without appending:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "PASS" in proc.stdout

    def test_same_path_distinct_method_accepted(self):
        """L2: `/users [get]` then `/users [post]` -> both accepted, length 2."""
        body = r'''
        func TestZZSamePathDistinctMethod(t *testing.T) {
        	op := NewOperation(nil)
        	if err := op.ParseRouterComment("/users [get]", false); err != nil {
        		t.Fatalf("get should succeed: %v", err)
        	}
        	if err := op.ParseRouterComment("/users [post]", false); err != nil {
        		t.Fatalf("post on same path should succeed (different method): %v", err)
        	}
        	if len(op.RouterProperties) != 2 {
        		t.Fatalf("RouterProperties len = %d, want 2", len(op.RouterProperties))
        	}
        	if op.RouterProperties[0].HTTPMethod != "GET" || op.RouterProperties[1].HTTPMethod != "POST" {
        		t.Fatalf("methods = %q,%q want GET,POST",
        			op.RouterProperties[0].HTTPMethod, op.RouterProperties[1].HTTPMethod)
        	}
        }
        '''
        proc = _run_driver("TestZZSamePathDistinctMethod", body)
        assert proc.returncode == 0, (
            "same path / different method must both register:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "PASS" in proc.stdout

    def test_same_method_distinct_path_accepted(self):
        """L2: `/users [get]` then `/accounts [get]` -> both accepted, length 2."""
        body = r'''
        func TestZZSameMethodDistinctPath(t *testing.T) {
        	op := NewOperation(nil)
        	if err := op.ParseRouterComment("/users [get]", false); err != nil {
        		t.Fatalf("/users [get] should succeed: %v", err)
        	}
        	if err := op.ParseRouterComment("/accounts [get]", false); err != nil {
        		t.Fatalf("/accounts [get] should succeed (different path): %v", err)
        	}
        	if len(op.RouterProperties) != 2 {
        		t.Fatalf("RouterProperties len = %d, want 2", len(op.RouterProperties))
        	}
        	if op.RouterProperties[0].Path != "/users" || op.RouterProperties[1].Path != "/accounts" {
        		t.Fatalf("paths = %q,%q want /users,/accounts",
        			op.RouterProperties[0].Path, op.RouterProperties[1].Path)
        	}
        }
        '''
        proc = _run_driver("TestZZSameMethodDistinctPath", body)
        assert proc.returncode == 0, (
            "same method / different path must both register:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "PASS" in proc.stdout

    def test_method_case_insensitive_duplicate(self):
        """L2: duplicate detection is on the upper-cased method.

        `/users [get]` then `/users [GET]` are the same route (HTTPMethod is
        upper-cased before comparison) and the second must be rejected.
        """
        body = r'''
        func TestZZCaseInsensitiveDup(t *testing.T) {
        	op := NewOperation(nil)
        	if err := op.ParseRouterComment("/users [get]", false); err != nil {
        		t.Fatalf("first call should succeed: %v", err)
        	}
        	err := op.ParseRouterComment("/users [GET]", false)
        	if err == nil {
        		t.Fatalf("/users [GET] duplicates /users [get] (case-insensitive method); want error")
        	}
        	if len(op.RouterProperties) != 1 {
        		t.Fatalf("len = %d, want 1 after case-variant duplicate", len(op.RouterProperties))
        	}
        }
        '''
        proc = _run_driver("TestZZCaseInsensitiveDup", body)
        assert proc.returncode == 0, (
            "case-variant method must be detected as the same route:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "PASS" in proc.stdout

    def test_deprecated_flag_duplicate_rejected(self):
        """L2: a duplicate is rejected regardless of the deprecated flag.

        First register `/users [get]` non-deprecated, then attempt the same
        path+method with deprecated=true: must still error, slice length 1.
        """
        body = r'''
        func TestZZDeprecatedDup(t *testing.T) {
        	op := NewOperation(nil)
        	if err := op.ParseRouterComment("/users [get]", false); err != nil {
        		t.Fatalf("first call should succeed: %v", err)
        	}
        	err := op.ParseRouterComment("/users [get]", true)
        	if err == nil {
        		t.Fatalf("deprecated duplicate of /users [get] must still be rejected")
        	}
        	if len(op.RouterProperties) != 1 {
        		t.Fatalf("len = %d, want 1 after deprecated duplicate", len(op.RouterProperties))
        	}
        }
        '''
        proc = _run_driver("TestZZDeprecatedDup", body)
        assert proc.returncode == 0, (
            "deprecated flag must not bypass duplicate rejection:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "PASS" in proc.stdout

    def test_deprecated_first_registration_succeeds(self):
        """L2: a deprecated route still registers normally as a first entry.

        Guards against an over-eager implementation that rejects anything with
        deprecated=true. `/items [delete]` with deprecated=true should succeed.
        """
        body = r'''
        func TestZZDeprecatedFirst(t *testing.T) {
        	op := NewOperation(nil)
        	if err := op.ParseRouterComment("/items [delete]", true); err != nil {
        		t.Fatalf("deprecated first registration should succeed: %v", err)
        	}
        	if len(op.RouterProperties) != 1 {
        		t.Fatalf("len = %d, want 1", len(op.RouterProperties))
        	}
        	rp := op.RouterProperties[0]
        	if rp.Path != "/items" || rp.HTTPMethod != "DELETE" {
        		t.Fatalf("entry = (%q,%q), want (/items,DELETE)", rp.Path, rp.HTTPMethod)
        	}
        	if !rp.Deprecated {
        		t.Fatalf("Deprecated flag should be carried through as true")
        	}
        }
        '''
        proc = _run_driver("TestZZDeprecatedFirst", body)
        assert proc.returncode == 0, (
            "deprecated first registration regressed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "PASS" in proc.stdout

    def test_preexisting_errors_preserved(self):
        """L2: malformed comment and invalid method still return errors first.

        The new duplicate check must apply only AFTER a successful parse; the
        original error paths must be untouched and must not append entries.
        """
        body = r'''
        func TestZZPreexistingErrors(t *testing.T) {
        	op := NewOperation(nil)
        	// malformed: no method bracket
        	if err := op.ParseRouterComment("/users", false); err == nil {
        		t.Fatalf("malformed comment must error")
        	}
        	// invalid HTTP method
        	if err := op.ParseRouterComment("/users [bogus]", false); err == nil {
        		t.Fatalf("invalid method must error")
        	}
        	if len(op.RouterProperties) != 0 {
        		t.Fatalf("no entry should be appended on error paths, len = %d", len(op.RouterProperties))
        	}
        }
        '''
        proc = _run_driver("TestZZPreexistingErrors", body)
        assert proc.returncode == 0, (
            "pre-existing malformed/invalid-method errors must be preserved:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "PASS" in proc.stdout

    def test_triplicate_only_keeps_one(self):
        """L2: three identical `/users [get]` calls -> 1 success, 2 errors, len 1.

        Exercises that the duplicate check fires on every subsequent attempt,
        not merely the second.
        """
        body = r'''
        func TestZZTriplicate(t *testing.T) {
        	op := NewOperation(nil)
        	errs := 0
        	for i := 0; i < 3; i++ {
        		if err := op.ParseRouterComment("/users [get]", false); err != nil {
        			errs++
        		}
        	}
        	if errs != 2 {
        		t.Fatalf("expected 2 errors across 3 identical calls, got %d", errs)
        	}
        	if len(op.RouterProperties) != 1 {
        		t.Fatalf("len = %d, want 1 after triplicate", len(op.RouterProperties))
        	}
        }
        '''
        proc = _run_driver("TestZZTriplicate", body)
        assert proc.returncode == 0, (
            "every repeated duplicate must be rejected, only one entry kept:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "PASS" in proc.stdout

    def test_complex_mixed_sequence(self):
        """L2: a mixed sequence ends with exactly the distinct (path,method) pairs.

        Sequence: /users [get], /users [get](dup), /users [post], /accounts [get],
        /accounts [get](dup) -> 3 entries: (/users,GET),(/users,POST),(/accounts,GET).
        """
        body = r'''
        func TestZZMixedSeq(t *testing.T) {
        	op := NewOperation(nil)
        	type call struct {
        		line   string
        		wantOK bool
        	}
        	seq := []call{
        		{"/users [get]", true},
        		{"/users [get]", false},
        		{"/users [post]", true},
        		{"/accounts [get]", true},
        		{"/accounts [get]", false},
        	}
        	for _, c := range seq {
        		err := op.ParseRouterComment(c.line, false)
        		if (err == nil) != c.wantOK {
        			t.Fatalf("%q: wantOK=%v got err=%v", c.line, c.wantOK, err)
        		}
        	}
        	if len(op.RouterProperties) != 3 {
        		t.Fatalf("final len = %d, want 3", len(op.RouterProperties))
        	}
        	type key struct{ p, m string }
        	got := map[key]bool{}
        	for _, rp := range op.RouterProperties {
        		got[key{rp.Path, rp.HTTPMethod}] = true
        	}
        	for _, want := range []key{{"/users", "GET"}, {"/users", "POST"}, {"/accounts", "GET"}} {
        		if !got[want] {
        			t.Fatalf("missing expected route %+v in %v", want, op.RouterProperties)
        		}
        	}
        }
        '''
        proc = _run_driver("TestZZMixedSeq", body)
        assert proc.returncode == 0, (
            "mixed sequence must yield exactly the distinct path+method set:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "PASS" in proc.stdout

    def test_repo_native_parserouter_suite_passes(self):
        """L2: the repo's own `go test -run TestParseRouter ./...` passes.

        This is the variant's native acceptance command. It includes the
        pre-existing TestParseRouterComment / TestParseRouterMultipleComments and
        the agent's new duplicate test (named with the TestParseRouter prefix).
        """
        proc = _run_go(
            ["test", "-run", "TestParseRouter", "-count=1", "./..."]
        )
        assert proc.returncode == 0, (
            "native TestParseRouter suite failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "ok" in proc.stdout, (
            f"expected a passing package line:\nSTDOUT:\n{proc.stdout}"
        )
