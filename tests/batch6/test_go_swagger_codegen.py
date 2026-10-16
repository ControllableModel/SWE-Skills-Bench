"""Benchmark test for skill `go-swagger-codegen` (variant ext6).

Task: support AND-combined security requirements in the `@Security`
annotation of swaggo/swag.  `Operation.ParseSecurityComment` must collect
schemes joined by `&&` on a single `@Security` line into **one** requirement
map appended to `operation.Security` (logical AND), while preserving the
existing single-scheme behavior, bracketed scope parsing, whitespace
trimming, and the empty-line reset semantics.

  | @Security line                  | appended requirement object                    |
  | ------------------------------- | ---------------------------------------------- |
  | Bearer                          | { "Bearer": [] }                               |
  | BasicAuth && ApiKeyAuth         | { "BasicAuth": [], "ApiKeyAuth": [] }          |
  | OAuth2[read, write] && ApiKeyAuth | { "OAuth2": ["read","write"], "ApiKeyAuth": [] } |

Verification strategy
---------------------
The agent edits `operation.go` (and adds a `TestParseSecurityComment` to
`operation_test.go`) inside REPO_DIR = /workspace/swag.  Rather than trust the
agent's own test, these checks INJECT independent in-package Go test drivers
into REPO_DIR and run them with the repo's native toolchain (`go test`).  Each
driver builds an `Operation` via `NewOperation(nil)`, calls
`ParseSecurityComment(...)` directly, and deep-asserts on the resulting
`operation.Security` ([]map[string][]string): the number of appended
requirement objects, the exact key set inside each object, and the scope
slices.  A naive implementation that emits one map per scheme (OR semantics),
ignores `&&`, drops scopes, or fails to trim whitespace will FAIL.

L1: deliverable files exist / are well-formed; the package compiles; the
    native `go test -run TestParseSecurityComment ./...` command succeeds.
L2: dynamic AND-combining behavior via injected drivers — single map for
    `&&` lines, exact key sets, scope ordering/trimming, multi-scheme AND,
    plain-line and empty-line semantics, and non-regression of OR (`||`)
    legacy combining and separate-call appends.
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
    A small reflect-free helper for comparing requirement maps is included.
    """
    fname = f"zz_bench_{uuid.uuid4().hex[:12]}_test.go"
    path = os.path.join(REPO_DIR, fname)
    header = textwrap.dedent(
        """\
        package swag

        import (
        \t"sort"
        \t"testing"
        )

        // zzKeys returns the sorted key set of a requirement map.
        func zzKeys(m map[string][]string) []string {
        \tks := make([]string, 0, len(m))
        \tfor k := range m {
        \t\tks = append(ks, k)
        \t}
        \tsort.Strings(ks)
        \treturn ks
        }

        // zzScopeNonEmpty reports the scopes that are not the empty string,
        // so we tolerate either nil/[] or [""] representations of "no scopes".
        func zzScopeNonEmpty(s []string) []string {
        \tout := make([]string, 0, len(s))
        \tfor _, v := range s {
        \t\tif v != "" {
        \t\t\tout = append(out, v)
        \t\t}
        \t}
        \treturn out
        }

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
    # compiles before any behavioral driver runs. It does not compile *_test.go.
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

    def test_parse_security_comment_present(self):
        """L1: operation.go still defines ParseSecurityComment."""
        path = os.path.join(self.REPO_DIR, "operation.go")
        with open(path) as fh:
            content = fh.read()
        assert "func (operation *Operation) ParseSecurityComment(" in content, (
            "ParseSecurityComment method must remain on *Operation"
        )

    def test_operation_test_has_named_test(self):
        """L1: operation_test.go exists and defines TestParseSecurityComment."""
        path = os.path.join(self.REPO_DIR, "operation_test.go")
        assert os.path.isfile(path), f"missing {path}"
        with open(path) as fh:
            content = fh.read()
        assert "func TestParseSecurityComment(" in content, (
            "a test named TestParseSecurityComment must exist in operation_test.go"
        )

    def test_package_compiles(self):
        """L1: the swag package and its commands compile after the change."""
        _purge_stale_drivers()
        proc = _run_go(["build", "./..."], timeout=GO_TIMEOUT)
        assert proc.returncode == 0, (
            f"go build ./... failed:\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    # ------------------------------------------------------------------ #
    # L2 — dynamic AND-combining behavior via injected drivers.
    # ------------------------------------------------------------------ #
    def test_and_combined_two_schemes_single_map(self):
        """L2: `BasicAuth && ApiKeyAuth` -> exactly ONE map with BOTH keys.

        Defeats a naive OR implementation that appends one map per scheme.
        """
        body = r'''
        func TestZZAndTwoSchemes(t *testing.T) {
        	op := NewOperation(nil)
        	if err := op.ParseSecurityComment("BasicAuth && ApiKeyAuth"); err != nil {
        		t.Fatalf("unexpected error: %v", err)
        	}
        	if len(op.Security) != 1 {
        		t.Fatalf("AND line must append exactly 1 requirement object, got %d: %#v",
        			len(op.Security), op.Security)
        	}
        	m := op.Security[0]
        	keys := zzKeys(m)
        	if len(keys) != 2 || keys[0] != "ApiKeyAuth" || keys[1] != "BasicAuth" {
        		t.Fatalf("AND map keys = %v, want [ApiKeyAuth BasicAuth]", keys)
        	}
        	if s := zzScopeNonEmpty(m["BasicAuth"]); len(s) != 0 {
        		t.Fatalf("BasicAuth scopes = %v, want empty", s)
        	}
        	if s := zzScopeNonEmpty(m["ApiKeyAuth"]); len(s) != 0 {
        		t.Fatalf("ApiKeyAuth scopes = %v, want empty", s)
        	}
        }
        '''
        proc = _run_driver("TestZZAndTwoSchemes", body)
        assert proc.returncode == 0, (
            "AND-combined `&&` line must produce a single map with both keys:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "PASS" in proc.stdout

    def test_and_combined_preserves_scopes(self):
        """L2: `OAuth2[read, write] && ApiKeyAuth` -> one map, OAuth2 keeps ordered scopes."""
        body = r'''
        func TestZZAndScopes(t *testing.T) {
        	op := NewOperation(nil)
        	if err := op.ParseSecurityComment("OAuth2[read, write] && ApiKeyAuth"); err != nil {
        		t.Fatalf("unexpected error: %v", err)
        	}
        	if len(op.Security) != 1 {
        		t.Fatalf("want 1 requirement object, got %d: %#v", len(op.Security), op.Security)
        	}
        	m := op.Security[0]
        	keys := zzKeys(m)
        	if len(keys) != 2 || keys[0] != "ApiKeyAuth" || keys[1] != "OAuth2" {
        		t.Fatalf("keys = %v, want [ApiKeyAuth OAuth2]", keys)
        	}
        	got := m["OAuth2"]
        	if len(got) != 2 || got[0] != "read" || got[1] != "write" {
        		t.Fatalf("OAuth2 scopes = %v, want [read write] (ordered, trimmed)", got)
        	}
        	if s := zzScopeNonEmpty(m["ApiKeyAuth"]); len(s) != 0 {
        		t.Fatalf("ApiKeyAuth scopes = %v, want empty", s)
        	}
        }
        '''
        proc = _run_driver("TestZZAndScopes", body)
        assert proc.returncode == 0, (
            "AND line with scoped scheme must keep one map and ordered scopes:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "PASS" in proc.stdout

    def test_scope_whitespace_trimmed(self):
        """L2: scopes inside brackets are trimmed of surrounding whitespace."""
        body = r'''
        func TestZZScopeTrim(t *testing.T) {
        	op := NewOperation(nil)
        	if err := op.ParseSecurityComment("OAuth2[  read ,   write  ] && ApiKeyAuth"); err != nil {
        		t.Fatalf("unexpected error: %v", err)
        	}
        	if len(op.Security) != 1 {
        		t.Fatalf("want 1 requirement object, got %d", len(op.Security))
        	}
        	got := op.Security[0]["OAuth2"]
        	if len(got) != 2 || got[0] != "read" || got[1] != "write" {
        		t.Fatalf("trimmed scopes = %q, want [read write]", got)
        	}
        }
        '''
        proc = _run_driver("TestZZScopeTrim", body)
        assert proc.returncode == 0, (
            "scope list must be trimmed of whitespace:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "PASS" in proc.stdout

    def test_scheme_name_whitespace_trimmed(self):
        """L2: scheme names are trimmed so keys have no surrounding spaces."""
        body = r'''
        func TestZZSchemeTrim(t *testing.T) {
        	op := NewOperation(nil)
        	if err := op.ParseSecurityComment("  BasicAuth   &&   ApiKeyAuth  "); err != nil {
        		t.Fatalf("unexpected error: %v", err)
        	}
        	if len(op.Security) != 1 {
        		t.Fatalf("want 1 requirement object, got %d", len(op.Security))
        	}
        	keys := zzKeys(op.Security[0])
        	if len(keys) != 2 || keys[0] != "ApiKeyAuth" || keys[1] != "BasicAuth" {
        		t.Fatalf("trimmed keys = %v, want [ApiKeyAuth BasicAuth] (no spaces)", keys)
        	}
        }
        '''
        proc = _run_driver("TestZZSchemeTrim", body)
        assert proc.returncode == 0, (
            "scheme names must be whitespace-trimmed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "PASS" in proc.stdout

    def test_plain_single_scheme(self):
        """L2: a plain `Bearer` line appends one map keyed by Bearer with no scopes."""
        body = r'''
        func TestZZPlainScheme(t *testing.T) {
        	op := NewOperation(nil)
        	if err := op.ParseSecurityComment("Bearer"); err != nil {
        		t.Fatalf("unexpected error: %v", err)
        	}
        	if len(op.Security) != 1 {
        		t.Fatalf("plain line must append exactly 1 map, got %d", len(op.Security))
        	}
        	keys := zzKeys(op.Security[0])
        	if len(keys) != 1 || keys[0] != "Bearer" {
        		t.Fatalf("keys = %v, want [Bearer]", keys)
        	}
        	if s := zzScopeNonEmpty(op.Security[0]["Bearer"]); len(s) != 0 {
        		t.Fatalf("Bearer scopes = %v, want empty", s)
        	}
        }
        '''
        proc = _run_driver("TestZZPlainScheme", body)
        assert proc.returncode == 0, (
            "plain single-scheme line must append one keyed map:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "PASS" in proc.stdout

    def test_empty_line_resets_security(self):
        """L2: an empty line resets Security to a non-nil empty slice."""
        body = r'''
        func TestZZEmptyResets(t *testing.T) {
        	op := NewOperation(nil)
        	if err := op.ParseSecurityComment("BasicAuth && ApiKeyAuth"); err != nil {
        		t.Fatalf("unexpected error: %v", err)
        	}
        	if len(op.Security) != 1 {
        		t.Fatalf("setup: want 1 object, got %d", len(op.Security))
        	}
        	if err := op.ParseSecurityComment(""); err != nil {
        		t.Fatalf("unexpected error on empty line: %v", err)
        	}
        	if op.Security == nil {
        		t.Fatalf("empty line must yield non-nil empty slice, got nil")
        	}
        	if len(op.Security) != 0 {
        		t.Fatalf("empty line must reset to length 0, got %d: %#v",
        			len(op.Security), op.Security)
        	}
        }
        '''
        proc = _run_driver("TestZZEmptyResets", body)
        assert proc.returncode == 0, (
            "empty line must reset Security to a non-nil empty slice:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "PASS" in proc.stdout

    def test_separate_calls_append_separate_maps(self):
        """L2: two ParseSecurityComment calls append two maps (OR across calls).

        Guards that AND-combining is scoped to a single line, not collapsing
        successive annotations into one object.
        """
        body = r'''
        func TestZZSeparateCalls(t *testing.T) {
        	op := NewOperation(nil)
        	if err := op.ParseSecurityComment("BasicAuth"); err != nil {
        		t.Fatalf("unexpected error: %v", err)
        	}
        	if err := op.ParseSecurityComment("ApiKeyAuth"); err != nil {
        		t.Fatalf("unexpected error: %v", err)
        	}
        	if len(op.Security) != 2 {
        		t.Fatalf("two separate calls must append two maps, got %d: %#v",
        			len(op.Security), op.Security)
        	}
        	if k := zzKeys(op.Security[0]); len(k) != 1 || k[0] != "BasicAuth" {
        		t.Fatalf("first map keys = %v, want [BasicAuth]", k)
        	}
        	if k := zzKeys(op.Security[1]); len(k) != 1 || k[0] != "ApiKeyAuth" {
        		t.Fatalf("second map keys = %v, want [ApiKeyAuth]", k)
        	}
        }
        '''
        proc = _run_driver("TestZZSeparateCalls", body)
        assert proc.returncode == 0, (
            "successive calls must append distinct requirement objects:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "PASS" in proc.stdout

    def test_three_schemes_and_combined(self):
        """L2: three `&&`-joined schemes collapse into ONE map of three keys."""
        body = r'''
        func TestZZThreeAnd(t *testing.T) {
        	op := NewOperation(nil)
        	if err := op.ParseSecurityComment("A && B && C"); err != nil {
        		t.Fatalf("unexpected error: %v", err)
        	}
        	if len(op.Security) != 1 {
        		t.Fatalf("three AND schemes must be one map, got %d objects: %#v",
        			len(op.Security), op.Security)
        	}
        	keys := zzKeys(op.Security[0])
        	if len(keys) != 3 || keys[0] != "A" || keys[1] != "B" || keys[2] != "C" {
        		t.Fatalf("keys = %v, want [A B C]", keys)
        	}
        }
        '''
        proc = _run_driver("TestZZThreeAnd", body)
        assert proc.returncode == 0, (
            "three `&&`-joined schemes must collapse into one map:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "PASS" in proc.stdout

    def test_legacy_or_separator_still_combines(self):
        """L2: legacy `||` separator on one line still AND-combines (back-compat)."""
        body = r'''
        func TestZZLegacyOr(t *testing.T) {
        	op := NewOperation(nil)
        	if err := op.ParseSecurityComment("OAuth2[read, write] || Firebase[]"); err != nil {
        		t.Fatalf("unexpected error: %v", err)
        	}
        	if len(op.Security) != 1 {
        		t.Fatalf("`||` one-line combine must be one map, got %d: %#v",
        			len(op.Security), op.Security)
        	}
        	keys := zzKeys(op.Security[0])
        	if len(keys) != 2 || keys[0] != "Firebase" || keys[1] != "OAuth2" {
        		t.Fatalf("keys = %v, want [Firebase OAuth2]", keys)
        	}
        	got := op.Security[0]["OAuth2"]
        	if len(got) != 2 || got[0] != "read" || got[1] != "write" {
        		t.Fatalf("OAuth2 scopes = %v, want [read write]", got)
        	}
        }
        '''
        proc = _run_driver("TestZZLegacyOr", body)
        assert proc.returncode == 0, (
            "legacy `||` on one line must still combine into a single map:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "PASS" in proc.stdout

    def test_native_named_test_passes(self):
        """L2: native acceptance command `go test -run TestParseSecurityComment ./...`."""
        proc = _run_go(
            ["test", "-run", "TestParseSecurityComment", "-count=1", "./..."]
        )
        assert proc.returncode == 0, (
            "native `go test -run TestParseSecurityComment ./...` failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "ok" in proc.stdout, (
            f"expected a passing package line:\nSTDOUT:\n{proc.stdout}"
        )

    def test_native_full_operation_suite_no_regression(self):
        """L2: the repo's broader security tests still pass (no regression)."""
        proc = _run_go(
            ["test", "-run", "TestParseSecurityComment", "-v", "-count=1", "."]
        )
        assert proc.returncode == 0, (
            "operation-package security tests regressed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "PASS" in proc.stdout
