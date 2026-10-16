"""Benchmark test for skill `samber-lo-functional` (variant ext7).

Verifies the agent-built **Permission Set Resolver** under `examples/perm`
of the `github.com/samber/lo` module.

The ext7 task asks for `examples/perm/resolve.go` (package perm) exporting
the types `Role` and `Resolution` and the function
`func Resolve(roles []Role) Resolution`, with strict rules:

  * `Granted`   = de-duplicated union of every role's Grants, sorted ascending.
  * A permission is denied if it appears in ANY role's Denies (deny wins,
    including within the same role).
  * `Effective` = Granted minus every denied permission, sorted ascending.
  * `Denied`    = only denials that actually removed a *granted* permission
    (no-op denials excluded), de-duplicated and sorted ascending.
  * All three slices are non-nil even when empty.
  * `Resolve` must not mutate the caller's input slices.

Verification strategy (discriminative power): rather than trusting the
agent's own `resolve_test.go`, the L2 cases write an INDEPENDENT Go test
file (its own package directory under REPO_DIR/examples) that imports the
real `github.com/samber/lo/examples/perm` package and asserts on the actual
returned `Resolution` struct via the native `go test` toolchain. A naive
implementation (leaves duplicates in Granted, lets denied perms leak into
Effective, lists no-op denials, forgets to sort, or mutates input) fails
these drivers. This variant is distinct from ext1 (sales report): different
package, types, function, and assertions.
"""

import os
import shutil
import subprocess
import uuid

import pytest

REPO_DIR_DEFAULT = "/workspace/lo"


class TestSamberLoFunctional:
    REPO_DIR = "/workspace/lo"

    # ------------------------------------------------------------------ #
    # helpers
    # ------------------------------------------------------------------ #
    @classmethod
    def _repo(cls):
        return cls.REPO_DIR if os.path.isdir(cls.REPO_DIR) else REPO_DIR_DEFAULT

    @classmethod
    def _go_env(cls):
        env = dict(os.environ)
        env.setdefault("GOFLAGS", "-mod=mod")
        env.setdefault("GO111MODULE", "on")
        env.setdefault("CGO_ENABLED", "0")
        return env

    @classmethod
    def _run_go(cls, args, timeout=300, cwd=None):
        return subprocess.run(
            args,
            cwd=cwd or cls._repo(),
            capture_output=True,
            text=True,
            timeout=timeout,
            env=cls._go_env(),
        )

    @classmethod
    def _make_driver_pkg(cls, body_go):
        """Create a fresh test-only sub-package under examples/ containing only
        a driver test that imports the real `perm` package. Returns the
        `./examples/<name>/` relative path and the absolute dir for cleanup.
        """
        name = "permverify_" + uuid.uuid4().hex[:10]
        abs_dir = os.path.join(cls._repo(), "examples", name)
        os.makedirs(abs_dir, exist_ok=True)
        with open(os.path.join(abs_dir, "driver_test.go"), "w") as fh:
            fh.write(body_go)
        rel = "./examples/" + name + "/"
        return rel, abs_dir

    @classmethod
    def _run_driver(cls, body_go, run="TestDriver", timeout=300):
        rel, abs_dir = cls._make_driver_pkg(body_go)
        try:
            res = cls._run_go(
                ["go", "test", rel, "-run", run, "-count=1", "-v"],
                timeout=timeout,
            )
            return res
        finally:
            shutil.rmtree(abs_dir, ignore_errors=True)

    # Common Go preamble for drivers: import the real package + reflect/sort helpers.
    _IMPORT = (
        'package permdriver\n\n'
        'import (\n'
        '\t"reflect"\n'
        '\t"testing"\n\n'
        '\tperm "github.com/samber/lo/examples/perm"\n'
        ')\n\n'
    )

    # ------------------------------------------------------------------ #
    # L1 — deliverables exist & are minimally well-formed
    # ------------------------------------------------------------------ #
    def test_resolve_go_exists(self):
        """L1: examples/perm/resolve.go exists and declares package perm."""
        p = os.path.join(self._repo(), "examples", "perm", "resolve.go")
        assert os.path.isfile(p), "examples/perm/resolve.go is missing"
        with open(p) as fh:
            head = fh.read(8000)
        assert "package perm" in head, "resolve.go must declare `package perm`"

    def test_resolve_test_go_exists(self):
        """L1: examples/perm/resolve_test.go exists (agent's own table-driven test)."""
        p = os.path.join(self._repo(), "examples", "perm", "resolve_test.go")
        assert os.path.isfile(p), "examples/perm/resolve_test.go is missing"
        with open(p) as fh:
            head = fh.read(8000)
        assert "package perm" in head, "resolve_test.go must declare `package perm`"

    def test_package_compiles(self):
        """L1: the new package compiles via `go build`."""
        res = self._run_go(["go", "build", "./examples/perm/"], timeout=300)
        assert res.returncode == 0, (
            "package github.com/samber/lo/examples/perm failed to build:\n"
            + res.stdout + res.stderr
        )

    def test_agents_own_tests_pass(self):
        """L1/L2: the exact acceptance command passes.

        `go test ./examples/perm/ -run TestResolve -count=1`
        """
        res = self._run_go(
            ["go", "test", "./examples/perm/", "-run", "TestResolve", "-count=1"],
            timeout=300,
        )
        assert res.returncode == 0, (
            "acceptance command failed:\n" + res.stdout + res.stderr
        )

    # ------------------------------------------------------------------ #
    # L2 — independent dynamic execution against real Resolve
    # ------------------------------------------------------------------ #
    def test_granted_union_dedup_sorted(self):
        """L2: Granted is the de-duplicated, ascending-sorted union of all grants."""
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	roles := []perm.Role{
		{Name: "r1", Grants: []string{"write", "read"}},
		{Name: "r2", Grants: []string{"read", "admin", "write"}},
	}
	r := perm.Resolve(roles)
	want := []string{"admin", "read", "write"}
	if !reflect.DeepEqual(r.Granted, want) {
		t.Fatalf("Granted want %v got %v", want, r.Granted)
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_cross_role_deny_precedence(self):
        """L2: a permission granted by one role and denied by another is removed
        from Effective and listed in Denied."""
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	roles := []perm.Role{
		{Name: "r1", Grants: []string{"read", "write", "admin"}},
		{Name: "r2", Denies: []string{"admin"}},
	}
	r := perm.Resolve(roles)
	wantEff := []string{"read", "write"}
	if !reflect.DeepEqual(r.Effective, wantEff) {
		t.Fatalf("Effective want %v got %v", wantEff, r.Effective)
	}
	wantDen := []string{"admin"}
	if !reflect.DeepEqual(r.Denied, wantDen) {
		t.Fatalf("Denied want %v got %v", wantDen, r.Denied)
	}
	for _, e := range r.Effective {
		if e == "admin" {
			t.Fatalf("admin must not leak into Effective: %v", r.Effective)
		}
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_same_role_deny_wins(self):
        """L2: a permission granted AND denied within the SAME role is denied."""
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	roles := []perm.Role{
		{Name: "r1", Grants: []string{"read", "write"}, Denies: []string{"write"}},
	}
	r := perm.Resolve(roles)
	wantEff := []string{"read"}
	if !reflect.DeepEqual(r.Effective, wantEff) {
		t.Fatalf("Effective want %v got %v (deny must win in same role)", wantEff, r.Effective)
	}
	wantDen := []string{"write"}
	if !reflect.DeepEqual(r.Denied, wantDen) {
		t.Fatalf("Denied want %v got %v", wantDen, r.Denied)
	}
	// write was granted (union) before denial:
	if len(r.Granted) != 2 || r.Granted[0] != "read" || r.Granted[1] != "write" {
		t.Fatalf("Granted want [read write] got %v", r.Granted)
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_noop_deny_excluded_from_denied(self):
        """L2: a deny for a never-granted permission appears in neither Denied
        nor Effective (no-op denials are excluded)."""
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	roles := []perm.Role{
		{Name: "r1", Grants: []string{"read"}},
		{Name: "r2", Denies: []string{"superuser", "root"}}, // never granted
	}
	r := perm.Resolve(roles)
	wantEff := []string{"read"}
	if !reflect.DeepEqual(r.Effective, wantEff) {
		t.Fatalf("Effective want %v got %v", wantEff, r.Effective)
	}
	if len(r.Denied) != 0 {
		t.Fatalf("no-op denials must not appear in Denied, got %v", r.Denied)
	}
	for _, d := range r.Denied {
		if d == "superuser" || d == "root" {
			t.Fatalf("no-op deny leaked into Denied: %v", r.Denied)
		}
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_denied_dedup_and_sorted(self):
        """L2: Denied is de-duplicated and ascending-sorted even when the same
        effective deny appears in several roles."""
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	roles := []perm.Role{
		{Name: "r1", Grants: []string{"read", "write", "delete"}},
		{Name: "r2", Denies: []string{"write", "delete"}},
		{Name: "r3", Denies: []string{"delete", "write"}}, // duplicate effective denials
	}
	r := perm.Resolve(roles)
	wantDen := []string{"delete", "write"}
	if !reflect.DeepEqual(r.Denied, wantDen) {
		t.Fatalf("Denied want %v (dedup+sorted) got %v", wantDen, r.Denied)
	}
	wantEff := []string{"read"}
	if !reflect.DeepEqual(r.Effective, wantEff) {
		t.Fatalf("Effective want %v got %v", wantEff, r.Effective)
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_effective_sorted_ascending(self):
        """L2: Effective is emitted in ascending order regardless of input order."""
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	roles := []perm.Role{
		{Name: "r1", Grants: []string{"zeta", "alpha", "mike", "bravo"}},
	}
	r := perm.Resolve(roles)
	want := []string{"alpha", "bravo", "mike", "zeta"}
	if !reflect.DeepEqual(r.Effective, want) {
		t.Fatalf("Effective not sorted ascending: want %v got %v", want, r.Effective)
	}
	if !reflect.DeepEqual(r.Granted, want) {
		t.Fatalf("Granted not sorted ascending: want %v got %v", want, r.Granted)
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_all_denied_effective_empty_nonnil(self):
        """L2: when every granted permission is denied, Effective is empty & non-nil."""
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	roles := []perm.Role{
		{Name: "r1", Grants: []string{"read", "write"}},
		{Name: "r2", Denies: []string{"read", "write"}},
	}
	r := perm.Resolve(roles)
	if r.Effective == nil {
		t.Fatalf("Effective must be non-nil")
	}
	if len(r.Effective) != 0 {
		t.Fatalf("Effective must be empty when all denied, got %v", r.Effective)
	}
	wantDen := []string{"read", "write"}
	if !reflect.DeepEqual(r.Denied, wantDen) {
		t.Fatalf("Denied want %v got %v", wantDen, r.Denied)
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_empty_input_three_empty_nonnil_slices(self):
        """L2: empty roles yields three empty, non-nil slices."""
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	r := perm.Resolve([]perm.Role{})
	if r.Effective == nil || r.Granted == nil || r.Denied == nil {
		t.Fatalf("all slices must be non-nil: eff=%v gr=%v den=%v",
			r.Effective == nil, r.Granted == nil, r.Denied == nil)
	}
	if len(r.Effective) != 0 || len(r.Granted) != 0 || len(r.Denied) != 0 {
		t.Fatalf("all slices must be empty: %+v", r)
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_input_not_mutated(self):
        """L2: Resolve must not mutate or reorder the caller's input or any role's
        Grants/Denies slice."""
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	g1 := []string{"write", "read", "admin"}
	d2 := []string{"admin", "ghost"}
	roles := []perm.Role{
		{Name: "r1", Grants: g1},
		{Name: "r2", Denies: d2},
	}
	// snapshots
	g1snap := append([]string(nil), g1...)
	d2snap := append([]string(nil), d2...)
	rolesLen := len(roles)

	_ = perm.Resolve(roles)

	if !reflect.DeepEqual(g1, g1snap) {
		t.Fatalf("role Grants mutated/reordered: got %v want %v", g1, g1snap)
	}
	if !reflect.DeepEqual(d2, d2snap) {
		t.Fatalf("role Denies mutated/reordered: got %v want %v", d2, d2snap)
	}
	if len(roles) != rolesLen {
		t.Fatalf("roles slice length changed: %d != %d", len(roles), rolesLen)
	}
	if roles[0].Name != "r1" || roles[1].Name != "r2" {
		t.Fatalf("roles reordered: %+v", roles)
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_combined_realistic_resolution(self):
        """L2: end-to-end scenario exercising union dedup, cross-role and
        same-role deny precedence, no-op deny exclusion, and full sorting."""
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	roles := []perm.Role{
		// r1 grants read/write/delete; denies "write" in same role (deny wins).
		{Name: "r1", Grants: []string{"write", "read", "delete"}, Denies: []string{"write"}},
		// r2 grants admin + duplicate read; denies "delete" (cross-role) and
		// "nonexistent" (no-op).
		{Name: "r2", Grants: []string{"admin", "read"}, Denies: []string{"delete", "nonexistent"}},
		// r3 grants nothing new, denies "admin"? no -> keep admin effective.
		{Name: "r3", Grants: []string{"audit"}},
	}
	r := perm.Resolve(roles)

	// Granted = union of all grants, deduped + sorted.
	wantGr := []string{"admin", "audit", "delete", "read", "write"}
	if !reflect.DeepEqual(r.Granted, wantGr) {
		t.Fatalf("Granted want %v got %v", wantGr, r.Granted)
	}

	// Denied (effective only): write (same-role), delete (cross-role).
	// "nonexistent" is a no-op deny -> excluded.
	wantDen := []string{"delete", "write"}
	if !reflect.DeepEqual(r.Denied, wantDen) {
		t.Fatalf("Denied want %v got %v", wantDen, r.Denied)
	}

	// Effective = Granted minus denied = admin, audit, read.
	wantEff := []string{"admin", "audit", "read"}
	if !reflect.DeepEqual(r.Effective, wantEff) {
		t.Fatalf("Effective want %v got %v", wantEff, r.Effective)
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr


if __name__ == "__main__":
    raise SystemExit(pytest.main([os.path.abspath(__file__), "-v", "--tb=short"]))
