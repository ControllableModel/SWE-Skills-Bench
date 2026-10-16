"""Tests for the go-errors-oops skill task (variant ext8):
"Build a Multi-Tenant Authorization Error Module".

Verifies that the agent created a self-contained Go example module at
examples/authz that uses github.com/samber/oops to model an authorization
decision and attaches the acting user + tenant (with attributes) and the
request context onto the denial error so an audit trail can be reconstructed
from the error alone.

Strategy
--------
L1 cases check the required deliverable files exist, are minimally well-formed,
and that go.work / go.mod wiring is present (module path
github.com/samber/oops/examples/authz, ./examples/authz in go.work).

L2 cases EXERCISE the agent's actual Authorize function. Rather than trusting
the agent-authored authz_test.go, this file injects its OWN independent Go
driver test (oops_zz_bench_driver_test.go) into the module and runs it with
`go test`, deep-validating per the requirement doc:

  * the permit path: admin Role -> Authorize returns nil.
  * the deny path: non-admin -> oops.AsOops(err) ok==true,
      Code() == "permission_denied",
      GetPublic == "You do not have access to this resource.",
      User()  -> (UserID, {email, role}),
      Tenant()-> (TenantID, {plan}),
      Context()["resource"]/["action"].
  * low cardinality: two denials with different principals produce byte-identical
      Error() strings while User()/Tenant()/Context() values differ, and the
      message contains none of the variable identity/resource/action data.

A naive implementation that interpolates the user/tenant/resource into the
message, or that omits the user/tenant attributes, fails these tests. The
driver is removed in teardown.
"""

import os
import re
import subprocess

import pytest

REPO_DIR = "/workspace/oops"
MODULE_DIR = os.path.join(REPO_DIR, "examples", "authz")
AUTHZ_GO = os.path.join(MODULE_DIR, "authz.go")
AUTHZ_TEST_GO = os.path.join(MODULE_DIR, "authz_test.go")
MODULE_GO_MOD = os.path.join(MODULE_DIR, "go.mod")
GO_WORK = os.path.join(REPO_DIR, "go.work")

DRIVER_NAME = "oops_zz_bench_driver_test.go"
DRIVER_PATH = os.path.join(MODULE_DIR, DRIVER_NAME)

# Independent driver test. Package name is filled in at write time to match the
# agent's chosen package. It exercises Authorize directly via the spec types.
DRIVER_TEMPLATE = r'''package %(pkg)s

import (
	"fmt"
	"testing"

	"github.com/samber/oops"
)

func zzReq(userID, email, role, tenantID, plan, resource, action string) AccessRequest {
	return AccessRequest{
		Principal: Principal{
			UserID:   userID,
			Email:    email,
			Role:     role,
			TenantID: tenantID,
			Plan:     plan,
		},
		Resource: resource,
		Action:   action,
	}
}

func zzDenyReq() AccessRequest {
	return zzReq("u1", "u1@x.io", "viewer", "t1", "pro", "billing", "delete")
}

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

func TestZZPermitAdmin(t *testing.T) {
	// admin Role -> permitted -> nil, regardless of resource/action.
	if err := Authorize(zzReq("a1", "a1@x.io", "admin", "t9", "ent", "billing", "delete")); err != nil {
		t.Fatalf("admin Authorize returned error: %%v", err)
	}
	if err := Authorize(zzReq("a2", "a2@x.io", "admin", "t0", "free", "secrets", "read")); err != nil {
		t.Fatalf("admin Authorize (2) returned error: %%v", err)
	}
}

func TestZZDenyNonAdmin(t *testing.T) {
	// Any non-admin role must be denied with a structured oops error.
	for _, role := range []string{"viewer", "editor", "guest", "", "Admin", "ADMIN", "superuser"} {
		req := zzReq("u1", "u1@x.io", role, "t1", "pro", "billing", "delete")
		err := Authorize(req)
		if err == nil {
			t.Fatalf("role %%q should be denied but Authorize returned nil", role)
		}
		zzAsOops(t, err)
	}
}

func TestZZDenyCode(t *testing.T) {
	oe := zzAsOops(t, Authorize(zzDenyReq()))
	if got := fmt.Sprint(oe.Code()); got != "permission_denied" {
		t.Fatalf("Code() = %%q, want permission_denied", got)
	}
}

func TestZZDenyPublicMessage(t *testing.T) {
	err := Authorize(zzDenyReq())
	zzAsOops(t, err)
	if got := oops.GetPublic(err, "FALLBACK"); got != "You do not have access to this resource." {
		t.Fatalf("GetPublic() = %%q, want %%q", got, "You do not have access to this resource.")
	}
}

func TestZZDenyUserAccessor(t *testing.T) {
	oe := zzAsOops(t, Authorize(zzDenyReq()))
	id, data := oe.User()
	if id != "u1" {
		t.Fatalf("User() id = %%q, want u1", id)
	}
	if v, ok := data["email"]; !ok {
		t.Fatalf("User() data missing key email; got %%v", data)
	} else if fmt.Sprint(v) != "u1@x.io" {
		t.Fatalf("User() data[email] = %%v, want u1@x.io", v)
	}
	if v, ok := data["role"]; !ok {
		t.Fatalf("User() data missing key role; got %%v", data)
	} else if fmt.Sprint(v) != "viewer" {
		t.Fatalf("User() data[role] = %%v, want viewer", v)
	}
}

func TestZZDenyTenantAccessor(t *testing.T) {
	oe := zzAsOops(t, Authorize(zzDenyReq()))
	id, data := oe.Tenant()
	if id != "t1" {
		t.Fatalf("Tenant() id = %%q, want t1", id)
	}
	if v, ok := data["plan"]; !ok {
		t.Fatalf("Tenant() data missing key plan; got %%v", data)
	} else if fmt.Sprint(v) != "pro" {
		t.Fatalf("Tenant() data[plan] = %%v, want pro", v)
	}
}

func TestZZDenyContext(t *testing.T) {
	oe := zzAsOops(t, Authorize(zzDenyReq()))
	ctx := oe.Context()
	if v, ok := ctx["resource"]; !ok {
		t.Fatalf("Context() missing key resource; got %%v", ctx)
	} else if fmt.Sprint(v) != "billing" {
		t.Fatalf("Context()[resource] = %%v, want billing", v)
	}
	if v, ok := ctx["action"]; !ok {
		t.Fatalf("Context() missing key action; got %%v", ctx)
	} else if fmt.Sprint(v) != "delete" {
		t.Fatalf("Context()[action] = %%v, want delete", v)
	}
}

func TestZZDenyAttributesTrackInput(t *testing.T) {
	// A different denied request must surface its OWN identity/tenant/context,
	// proving the accessors are not hardcoded to one principal.
	req := zzReq("zoe", "zoe@corp.io", "editor", "tenant-42", "enterprise", "reports", "export")
	oe := zzAsOops(t, Authorize(req))
	uid, udata := oe.User()
	if uid != "zoe" {
		t.Fatalf("User() id = %%q, want zoe", uid)
	}
	if fmt.Sprint(udata["email"]) != "zoe@corp.io" || fmt.Sprint(udata["role"]) != "editor" {
		t.Fatalf("User() data = %%v, want email=zoe@corp.io role=editor", udata)
	}
	tid, tdata := oe.Tenant()
	if tid != "tenant-42" {
		t.Fatalf("Tenant() id = %%q, want tenant-42", tid)
	}
	if fmt.Sprint(tdata["plan"]) != "enterprise" {
		t.Fatalf("Tenant() data[plan] = %%v, want enterprise", tdata["plan"])
	}
	ctx := oe.Context()
	if fmt.Sprint(ctx["resource"]) != "reports" || fmt.Sprint(ctx["action"]) != "export" {
		t.Fatalf("Context() resource/action = %%v/%%v, want reports/export", ctx["resource"], ctx["action"])
	}
}

func TestZZMessageCardinality(t *testing.T) {
	// Two denials with different principals/resources/actions: the Error()
	// string must be byte-identical (low cardinality), while the structured
	// user/tenant/context values differ.
	r1 := zzReq("alice", "alice@a.io", "viewer", "ta", "pro", "billing", "delete")
	r2 := zzReq("bob", "bob@b.io", "editor", "tb", "free", "secrets", "read")
	e1 := Authorize(r1)
	e2 := Authorize(r2)
	o1 := zzAsOops(t, e1)
	o2 := zzAsOops(t, e2)

	if e1.Error() != e2.Error() {
		t.Fatalf("Error() differs across denials: %%q vs %%q", e1.Error(), e2.Error())
	}

	id1, _ := o1.User()
	id2, _ := o2.User()
	if id1 == id2 {
		t.Fatalf("expected differing User() ids across denials, both %%q", id1)
	}
	if id1 != "alice" || id2 != "bob" {
		t.Fatalf("User() ids = %%q/%%q, want alice/bob", id1, id2)
	}
	t1id, _ := o1.Tenant()
	t2id, _ := o2.Tenant()
	if t1id == t2id {
		t.Fatalf("expected differing Tenant() ids across denials, both %%q", t1id)
	}
	if fmt.Sprint(o1.Context()["resource"]) == fmt.Sprint(o2.Context()["resource"]) {
		t.Fatalf("expected differing Context()[resource] across denials")
	}
	if fmt.Sprint(o1.Context()["action"]) == fmt.Sprint(o2.Context()["action"]) {
		t.Fatalf("expected differing Context()[action] across denials")
	}
}

func TestZZMessageNoInterpolation(t *testing.T) {
	// The variable identity/resource/action data must NOT appear in the
	// message string -- it lives only in the structured accessors.
	r := zzReq("alice", "alice@a.io", "viewer", "tenant-secret", "pro", "billing", "delete")
	e := Authorize(r)
	zzAsOops(t, e)
	msg := e.Error()
	for _, frag := range []string{"alice", "alice@a.io", "viewer", "tenant-secret", "pro", "billing", "delete"} {
		if zzContains(msg, frag) {
			t.Fatalf("Error() message %%q must not contain variable data %%q", msg, frag)
		}
	}
}

func zzContains(s, sub string) bool {
	return len(sub) > 0 && len(s) >= len(sub) && (indexOf(s, sub) >= 0)
}

func indexOf(s, sub string) int {
	for i := 0; i+len(sub) <= len(s); i++ {
		if s[i:i+len(sub)] == sub {
			return i
		}
	}
	return -1
}
'''


def _run_go(args, timeout=420):
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
    """Read the package name the agent used in authz.go."""
    with open(AUTHZ_GO, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            m = re.match(r"\s*package\s+([A-Za-z_][A-Za-z0-9_]*)", line)
            if m:
                return m.group(1)
    return "authz"


@pytest.fixture(scope="module", autouse=True)
def _driver_lifecycle():
    """Install the independent Go driver test, then remove it on teardown."""
    pkg = "authz"
    if os.path.isfile(AUTHZ_GO):
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
        """L1: the examples/authz module directory was created."""
        assert os.path.isdir(MODULE_DIR), f"missing module dir {MODULE_DIR}"

    def test_authz_go_exists(self):
        """L1: authz.go exists; declares a package, Authorize, and the spec types."""
        assert os.path.isfile(AUTHZ_GO), "missing examples/authz/authz.go"
        with open(AUTHZ_GO, encoding="utf-8", errors="replace") as f:
            src = f.read()
        assert re.search(r"\bpackage\s+\w+", src), "no package clause in authz.go"
        assert re.search(r"func\s+Authorize\s*\(", src), "no Authorize function"
        assert re.search(r"\btype\s+Principal\s+struct", src), "no Principal struct"
        assert re.search(r"\btype\s+AccessRequest\s+struct", src), "no AccessRequest struct"

    def test_go_mod_declares_module(self):
        """L1: go.mod declares the exact module path and requires samber/oops."""
        assert os.path.isfile(MODULE_GO_MOD), "missing examples/authz/go.mod"
        with open(MODULE_GO_MOD, encoding="utf-8", errors="replace") as f:
            mod = f.read()
        assert "module github.com/samber/oops/examples/authz" in mod, mod
        assert "github.com/samber/oops" in mod

    def test_go_work_lists_module(self):
        """L1: go.work uses ./examples/authz so the in-repo lib resolves."""
        assert os.path.isfile(GO_WORK), "missing go.work"
        with open(GO_WORK, encoding="utf-8", errors="replace") as f:
            work = f.read()
        assert "./examples/authz" in work, "go.work does not use ./examples/authz"

    def test_module_compiles(self):
        """L1/L2: the new module builds against the in-repo library."""
        res = _run_go(["build", "./examples/authz/..."])
        assert res.returncode == 0, f"build failed:\nSTDOUT:{res.stdout}\nSTDERR:{res.stderr}"

    # ---------- L2: behavior, driven by the injected independent test ----------

    def _run_driver(self, run_filter):
        res = _run_go(
            ["test", "-v", "-count=1", "-run", run_filter, "./examples/authz/..."]
        )
        return res

    def test_permit_admin(self):
        """L2: admin Role -> Authorize returns nil regardless of resource/action."""
        res = self._run_driver("TestZZPermitAdmin$")
        assert res.returncode == 0, f"{res.stdout}\n{res.stderr}"
        assert "PASS: TestZZPermitAdmin" in res.stdout, (
            f"driver test did not run/pass:\n{res.stdout}\n{res.stderr}"
        )

    def test_deny_non_admin_roles(self):
        """L2: every non-admin role (incl. case variants & empty) -> structured denial."""
        res = self._run_driver("TestZZDenyNonAdmin$")
        assert res.returncode == 0, f"{res.stdout}\n{res.stderr}"

    def test_deny_code_and_public(self):
        """L2: denial Code() == permission_denied and public message per spec."""
        res = self._run_driver("TestZZDenyCode$|TestZZDenyPublicMessage$")
        assert res.returncode == 0, f"{res.stdout}\n{res.stderr}"

    def test_deny_user_accessor(self):
        """L2: User() -> (UserID, {email, role}) per the denied request."""
        res = self._run_driver("TestZZDenyUserAccessor$")
        assert res.returncode == 0, f"{res.stdout}\n{res.stderr}"

    def test_deny_tenant_accessor(self):
        """L2: Tenant() -> (TenantID, {plan}) per the denied request."""
        res = self._run_driver("TestZZDenyTenantAccessor$")
        assert res.returncode == 0, f"{res.stdout}\n{res.stderr}"

    def test_deny_context_resource_action(self):
        """L2: Context() carries resource and action from the request."""
        res = self._run_driver("TestZZDenyContext$")
        assert res.returncode == 0, f"{res.stdout}\n{res.stderr}"

    def test_attributes_track_input(self):
        """L2: a different denied request surfaces its OWN user/tenant/context (not hardcoded)."""
        res = self._run_driver("TestZZDenyAttributesTrackInput$")
        assert res.returncode == 0, f"{res.stdout}\n{res.stderr}"

    def test_message_cardinality(self):
        """L2: two denials -> byte-identical Error(), differing User()/Tenant()/Context()."""
        res = self._run_driver("TestZZMessageCardinality$")
        assert res.returncode == 0, f"{res.stdout}\n{res.stderr}"

    def test_message_no_interpolation(self):
        """L2: the denial message contains none of the variable identity/resource/action data."""
        res = self._run_driver("TestZZMessageNoInterpolation$")
        assert res.returncode == 0, f"{res.stdout}\n{res.stderr}"

    def test_agent_native_suite_passes(self):
        """L2: the spec's native command `go test ./examples/authz/...` passes overall."""
        res = _run_go(["test", "-count=1", "./examples/authz/..."])
        assert res.returncode == 0, f"native suite failed:\nSTDOUT:{res.stdout}\nSTDERR:{res.stderr}"
