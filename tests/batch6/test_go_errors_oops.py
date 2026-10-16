"""Tests for the go-errors-oops skill task (ext6 variant):
"Build a Request-Scoped Error Context Propagation Module".

Verifies that the agent created a self-contained Go example module at
examples/reqscope that uses github.com/samber/oops to propagate
request-scoped error metadata through a Go context.Context. An *edge* stage
(Seed) enriches a context with a trace id, a domain, and a tenant attribute;
a *handler* stage (Handle), several calls deep, emits an oops error that
INHERITS that seeded metadata without it being threaded through Handle's
signature.

Strategy
--------
L1 cases check the required deliverable files exist, are minimally well-formed,
and that go.work / go.mod wiring is present (module path + samber/oops require
+ ./examples/reqscope in the workspace).

L2 cases EXERCISE the agent's actual Seed / Handle functions. Rather than
trusting the agent-authored reqscope_test.go, this file injects its OWN
independent Go driver test (oops_zz_bench_driver_test.go) into the module and
runs it with `go test`, deep-validating, via oops accessors:
  * Handle(Seed(...), "allow")  -> nil
  * Handle(Seed(ctx,"trace-9","tenant-7"),"delete") ->
        Trace()=="trace-9", Context()["tenant_id"]=="tenant-7",
        Context()["action"]=="delete", Code()=="action_rejected"
  * Handle(context.Background(),"delete") -> usable oops error with
        Code()=="action_rejected" and Context()["action"]=="delete",
        but NO inherited trace/tenant.
  * Seed must NOT mutate the parent context (derived context only).

Because Handle's signature is fixed as `Handle(ctx, action string) error`, a
naive implementation that threads traceID/tenantID as explicit parameters
cannot inherit them from the context and FAILS the inheritance driver test.
The driver is removed in teardown.
"""

import os
import re
import subprocess

import pytest

REPO_DIR = "/workspace/oops"
MODULE_DIR = os.path.join(REPO_DIR, "examples", "reqscope")
REQSCOPE_GO = os.path.join(MODULE_DIR, "reqscope.go")
REQSCOPE_TEST_GO = os.path.join(MODULE_DIR, "reqscope_test.go")
MODULE_GO_MOD = os.path.join(MODULE_DIR, "go.mod")
GO_WORK = os.path.join(REPO_DIR, "go.work")

DRIVER_NAME = "oops_zz_bench_driver_test.go"
DRIVER_PATH = os.path.join(MODULE_DIR, DRIVER_NAME)

# Independent driver test. Package name is filled in at write time to match the
# agent's chosen package. It exercises Seed / Handle directly through the public
# oops accessors. It does NOT rely on any helper the agent might have written.
DRIVER_TEMPLATE = r'''package %(pkg)s

import (
	"context"
	"fmt"
	"testing"

	"github.com/samber/oops"
)

func zzAsOops(t *testing.T, err error) oops.OopsError {
	t.Helper()
	if err == nil {
		t.Fatalf("expected non-nil error")
	}
	oe, ok := oops.AsOops(err)
	if !ok {
		t.Fatalf("error is not an oops error: %%v", err)
	}
	return oe
}

// Seeded + allow action must succeed (nil).
func TestZZAllowReturnsNil(t *testing.T) {
	ctx := Seed(context.Background(), "trace-9", "tenant-7")
	if err := Handle(ctx, "allow"); err != nil {
		t.Fatalf("Handle(seeded, allow) = %%v, want nil", err)
	}
}

// Inheritance: an error from a seeded context carries trace + tenant (inherited)
// AND the action (added by the handler) AND the action_rejected code, even
// though Handle's signature never received trace/tenant.
func TestZZSeededInheritance(t *testing.T) {
	ctx := Seed(context.Background(), "trace-9", "tenant-7")
	oe := zzAsOops(t, Handle(ctx, "delete"))

	if got := oe.Trace(); got != "trace-9" {
		t.Fatalf("Trace() = %%q, want trace-9 (inherited from Seed)", got)
	}
	if got := fmt.Sprint(oe.Code()); got != "action_rejected" {
		t.Fatalf("Code() = %%q, want action_rejected", got)
	}
	c := oe.Context()
	if v, ok := c["tenant_id"]; !ok {
		t.Fatalf("Context() missing inherited key tenant_id; got %%v", c)
	} else if fmt.Sprint(v) != "tenant-7" {
		t.Fatalf("Context()[tenant_id] = %%v, want tenant-7 (inherited)", v)
	}
	if v, ok := c["action"]; !ok {
		t.Fatalf("Context() missing key action; got %%v", c)
	} else if fmt.Sprint(v) != "delete" {
		t.Fatalf("Context()[action] = %%v, want delete (added by handler)", v)
	}
}

// Seed sets domain "http-edge"; verify it inherits onto the error.
func TestZZSeededDomain(t *testing.T) {
	ctx := Seed(context.Background(), "trace-9", "tenant-7")
	oe := zzAsOops(t, Handle(ctx, "delete"))
	if got := oe.Domain(); got != "http-edge" {
		t.Fatalf("Domain() = %%q, want http-edge (seeded domain)", got)
	}
}

// Unseeded fallback: still a usable oops error with code + action, but no
// inherited trace/tenant.
func TestZZUnseededFallback(t *testing.T) {
	oe := zzAsOops(t, Handle(context.Background(), "delete"))
	if got := fmt.Sprint(oe.Code()); got != "action_rejected" {
		t.Fatalf("Code() = %%q, want action_rejected (unseeded)", got)
	}
	c := oe.Context()
	if v, ok := c["action"]; !ok {
		t.Fatalf("Context() missing key action; got %%v", c)
	} else if fmt.Sprint(v) != "delete" {
		t.Fatalf("Context()[action] = %%v, want delete (unseeded)", v)
	}
	// Must NOT have inherited the seeded tenant from a different request.
	if v, ok := c["tenant_id"]; ok {
		t.Fatalf("unseeded Context() unexpectedly has tenant_id=%%v", v)
	}
}

// The non-allow action is rejected regardless of the specific action string,
// and the action value is faithfully reflected (not hardcoded to "delete").
func TestZZActionValueReflected(t *testing.T) {
	ctx := Seed(context.Background(), "trace-1", "tenant-1")
	oe := zzAsOops(t, Handle(ctx, "drop-table"))
	if v := fmt.Sprint(oe.Context()["action"]); v != "drop-table" {
		t.Fatalf("Context()[action] = %%v, want drop-table (must not hardcode)", v)
	}
	if got := fmt.Sprint(oe.Code()); got != "action_rejected" {
		t.Fatalf("Code() = %%q, want action_rejected", got)
	}
}

// Trace/tenant must reflect the ACTUAL seed args, not a hardcoded constant.
func TestZZSeedArgsAreDynamic(t *testing.T) {
	a := zzAsOops(t, Handle(Seed(context.Background(), "trace-A", "tenant-A"), "x"))
	b := zzAsOops(t, Handle(Seed(context.Background(), "trace-B", "tenant-B"), "y"))
	if a.Trace() != "trace-A" {
		t.Fatalf("first Trace() = %%q, want trace-A", a.Trace())
	}
	if b.Trace() != "trace-B" {
		t.Fatalf("second Trace() = %%q, want trace-B", b.Trace())
	}
	if a.Trace() == b.Trace() {
		t.Fatalf("traces must differ per seed (got both %%q)", a.Trace())
	}
	if fmt.Sprint(a.Context()["tenant_id"]) == fmt.Sprint(b.Context()["tenant_id"]) {
		t.Fatalf("tenant_id must differ per seed")
	}
	if fmt.Sprint(b.Context()["tenant_id"]) != "tenant-B" {
		t.Fatalf("second tenant_id = %%v, want tenant-B", b.Context()["tenant_id"])
	}
}

// Seed must return a DERIVED context and must NOT mutate the parent: a handler
// run against the original parent must not see the seeded trace/tenant.
func TestZZSeedDoesNotMutateParent(t *testing.T) {
	parent := context.Background()
	_ = Seed(parent, "trace-9", "tenant-7")
	oe := zzAsOops(t, Handle(parent, "delete"))
	if got := oe.Trace(); got == "trace-9" {
		t.Fatalf("parent context was mutated: Trace()=%%q", got)
	}
	if v, ok := oe.Context()["tenant_id"]; ok {
		t.Fatalf("parent context was mutated: tenant_id=%%v", v)
	}
}

// Seed must return a context distinct from its parent (derivation, not identity).
func TestZZSeedReturnsDerivedContext(t *testing.T) {
	parent := context.Background()
	derived := Seed(parent, "trace-9", "tenant-7")
	if derived == nil {
		t.Fatalf("Seed returned nil context")
	}
	// The derived context must carry data the parent lacks: prove via Handle.
	seededErr := zzAsOops(t, Handle(derived, "delete"))
	if seededErr.Trace() != "trace-9" {
		t.Fatalf("derived context did not carry trace; Trace()=%%q", seededErr.Trace())
	}
}

// The call chain is at least two deep: regardless, the entry point Handle must
// surface the structured error for any non-allow action including odd strings.
func TestZZRejectsVariousActions(t *testing.T) {
	ctx := Seed(context.Background(), "trace-Z", "tenant-Z")
	for _, action := range []string{"delete", "update", "", "ALLOW", "allow "} {
		err := Handle(ctx, action)
		if err == nil {
			t.Fatalf("Handle(seeded, %%q) = nil, want rejection (only exact \"allow\" passes)", action)
		}
		oe := zzAsOops(t, err)
		if got := fmt.Sprint(oe.Code()); got != "action_rejected" {
			t.Fatalf("action %%q: Code() = %%q, want action_rejected", action, got)
		}
		if got := fmt.Sprint(oe.Context()["action"]); got != action {
			t.Fatalf("action %%q: Context()[action] = %%q", action, got)
		}
	}
}
'''


def _run_go(args, timeout=600):
    env = dict(os.environ)
    env.setdefault("GOFLAGS", "")
    return subprocess.run(
        ["go"] + args,
        cwd=REPO_DIR,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )


def _detect_package():
    """Read the package name the agent used in reqscope.go."""
    try:
        with open(REQSCOPE_GO, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                m = re.match(r"\s*package\s+([A-Za-z_][A-Za-z0-9_]*)", line)
                if m:
                    return m.group(1)
    except OSError:
        pass
    return "reqscope"


@pytest.fixture(scope="module", autouse=True)
def _driver_lifecycle():
    """Install the independent Go driver test, then remove it on teardown."""
    pkg = "reqscope"
    if os.path.isfile(REQSCOPE_GO):
        pkg = _detect_package()
    if os.path.isdir(MODULE_DIR):
        with open(DRIVER_PATH, "w", encoding="utf-8") as f:
            f.write(DRIVER_TEMPLATE % {"pkg": pkg})
    yield
    try:
        os.remove(DRIVER_PATH)
    except OSError:
        pass


class TestGoErrorsOops:
    REPO_DIR = "/workspace/oops"

    # ---------- L1: deliverables exist and are well-formed ----------

    def test_module_dir_exists(self):
        """L1: the examples/reqscope module directory was created."""
        assert os.path.isdir(MODULE_DIR), f"missing module dir {MODULE_DIR}"

    def test_reqscope_go_exists(self):
        """L1: reqscope.go exists and declares a package + Seed and Handle funcs."""
        assert os.path.isfile(REQSCOPE_GO), "missing examples/reqscope/reqscope.go"
        with open(REQSCOPE_GO, encoding="utf-8", errors="replace") as f:
            src = f.read()
        assert re.search(r"\bpackage\s+\w+", src), "no package clause in reqscope.go"
        assert re.search(r"func\s+Seed\s*\(", src), "no Seed function"
        assert re.search(r"func\s+Handle\s*\(", src), "no Handle function"

    def test_handle_signature_is_fixed(self):
        """L1: Handle's signature is `Handle(ctx ..., action string) error` -- it must
        NOT take traceID/tenantID parameters (the spec forbids threading them)."""
        with open(REQSCOPE_GO, encoding="utf-8", errors="replace") as f:
            src = f.read()
        m = re.search(r"func\s+Handle\s*\(([^)]*)\)", src, re.DOTALL)
        assert m, "could not locate Handle signature"
        params = m.group(1)
        # Exactly two params: a context and an action string.
        assert "context.Context" in params, f"Handle must take a context.Context: {params!r}"
        assert "string" in params, f"Handle must take an action string: {params!r}"
        # Naive guard: no trace/tenant identifiers smuggled into the signature.
        assert not re.search(r"trace", params, re.IGNORECASE), (
            f"Handle signature must not thread a trace param: {params!r}"
        )
        assert not re.search(r"tenant", params, re.IGNORECASE), (
            f"Handle signature must not thread a tenant param: {params!r}"
        )

    def test_go_mod_declares_module(self):
        """L1: go.mod declares the exact module path and requires samber/oops."""
        assert os.path.isfile(MODULE_GO_MOD), "missing examples/reqscope/go.mod"
        with open(MODULE_GO_MOD, encoding="utf-8", errors="replace") as f:
            mod = f.read()
        assert "module github.com/samber/oops/examples/reqscope" in mod, mod
        assert "github.com/samber/oops" in mod, mod

    def test_go_work_lists_module(self):
        """L1: go.work uses ./examples/reqscope so the in-repo lib resolves."""
        assert os.path.isfile(GO_WORK), "missing go.work"
        with open(GO_WORK, encoding="utf-8", errors="replace") as f:
            work = f.read()
        assert "./examples/reqscope" in work, "go.work does not use ./examples/reqscope"

    def test_module_compiles(self):
        """L1/L2: the new module builds against the in-repo library."""
        res = _run_go(["build", "./examples/reqscope/..."])
        assert res.returncode == 0, f"build failed:\nSTDOUT:{res.stdout}\nSTDERR:{res.stderr}"

    # ---------- L2: behavior, driven by the injected independent test ----------

    def _run_driver(self, run_filter):
        return _run_go(
            ["test", "-v", "-count=1", "-run", run_filter, "./examples/reqscope/..."]
        )

    def test_allow_returns_nil(self):
        """L2: Handle(Seed(...), "allow") returns nil."""
        res = self._run_driver("TestZZAllowReturnsNil$")
        assert res.returncode == 0, f"{res.stdout}\n{res.stderr}"
        assert "PASS: TestZZAllowReturnsNil" in res.stdout, (
            f"driver test did not run/pass:\n{res.stdout}\n{res.stderr}"
        )

    def test_seeded_inheritance(self):
        """L2: seeded delete -> Trace=trace-9, tenant_id=tenant-7 (inherited),
        action=delete (added), code=action_rejected. Naive parameter-threading
        impls cannot inherit and fail here."""
        res = self._run_driver("TestZZSeededInheritance$")
        assert res.returncode == 0, f"{res.stdout}\n{res.stderr}"

    def test_seeded_domain(self):
        """L2: the seeded domain http-edge inherits onto the handler's error."""
        res = self._run_driver("TestZZSeededDomain$")
        assert res.returncode == 0, f"{res.stdout}\n{res.stderr}"

    def test_unseeded_fallback(self):
        """L2: Handle(context.Background(), "delete") -> usable oops error with
        action + code, but no inherited trace/tenant."""
        res = self._run_driver("TestZZUnseededFallback$")
        assert res.returncode == 0, f"{res.stdout}\n{res.stderr}"

    def test_action_value_reflected(self):
        """L2: the action context value mirrors the argument (not hardcoded)."""
        res = self._run_driver("TestZZActionValueReflected$")
        assert res.returncode == 0, f"{res.stdout}\n{res.stderr}"

    def test_seed_args_are_dynamic(self):
        """L2: two distinct seeds yield distinct inherited trace/tenant -- proves
        Seed actually carries its args rather than a constant."""
        res = self._run_driver("TestZZSeedArgsAreDynamic$")
        assert res.returncode == 0, f"{res.stdout}\n{res.stderr}"

    def test_seed_does_not_mutate_parent(self):
        """L2: Seed returns a derived context and must not mutate the parent."""
        res = self._run_driver("TestZZSeedDoesNotMutateParent$")
        assert res.returncode == 0, f"{res.stdout}\n{res.stderr}"

    def test_seed_returns_derived_context(self):
        """L2: the derived context carries seeded data the parent lacks."""
        res = self._run_driver("TestZZSeedReturnsDerivedContext$")
        assert res.returncode == 0, f"{res.stdout}\n{res.stderr}"

    def test_rejects_various_actions(self):
        """L2: only exact "allow" passes; every other action is rejected with the
        right code and faithful action context."""
        res = self._run_driver("TestZZRejectsVariousActions$")
        assert res.returncode == 0, f"{res.stdout}\n{res.stderr}"

    def test_agent_native_suite_passes(self):
        """L2: the spec's native command `go test ./examples/reqscope/...` passes."""
        res = _run_go(["test", "-count=1", "./examples/reqscope/..."])
        assert res.returncode == 0, (
            f"native suite failed:\nSTDOUT:{res.stdout}\nSTDERR:{res.stderr}"
        )
