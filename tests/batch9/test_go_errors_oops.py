"""Tests for the go-errors-oops skill task (ext9 variant): "Build an SLA Timing Error Module".

Verifies that the agent created a self-contained Go example module at
examples/slacheck that uses github.com/samber/oops to surface a timing-annotated
failure when an operation breaches its service-level deadline.

The single entry point under test is:

    func CheckSLA(operation string, startedAt time.Time, finishedAt time.Time, budget time.Duration) error

Semantics (from the requirement doc):
  * elapsed = finishedAt.Sub(startedAt)
  * elapsed <= budget                -> nil  (on/under budget, never a breach)
  * negative elapsed (finished<start) -> nil
  * elapsed > budget                 -> oops error with:
        Code()      == "sla_breached"
        Domain()    == "sla-monitor"
        Duration()  == elapsed (the real elapsed carried ON the error)
        Context()["operation"] == operation
        Context()["budget"]    == budget
  * The error must MUST NOT call time.Now() / sleep (fully deterministic).
  * Error() string is LOW CARDINALITY: byte-identical regardless of operation,
    elapsed, or budget. Variable data is reachable only via Duration()/Context().

Strategy
--------
L1 cases check the required deliverable files (slacheck.go, slacheck_test.go,
go.mod) exist, are minimally well-formed, and that go.work / go.mod wiring is
present, and that the module builds against the in-repo oops library.

L2 cases EXERCISE the agent's actual CheckSLA function. Rather than trusting the
agent-authored slacheck_test.go, this file injects its OWN independent Go driver
test (oops_zz_bench_driver_test.go) into the module and runs it with `go test`,
deep-validating Code()/Domain()/Duration()/Context() and message-cardinality
exactly as the requirement doc specifies. The driver is removed in teardown.

A naive solution that embeds the elapsed time in the message, omits Duration()
from the error, or treats the on-budget / negative-elapsed cases as breaches,
fails these tests.
"""

import os
import re
import subprocess

import pytest

REPO_DIR = "/workspace/oops"
MODULE_DIR = os.path.join(REPO_DIR, "examples", "slacheck")
SLACHECK_GO = os.path.join(MODULE_DIR, "slacheck.go")
SLACHECK_TEST_GO = os.path.join(MODULE_DIR, "slacheck_test.go")
MODULE_GO_MOD = os.path.join(MODULE_DIR, "go.mod")
GO_WORK = os.path.join(REPO_DIR, "go.work")

DRIVER_NAME = "oops_zz_bench_driver_test.go"
DRIVER_PATH = os.path.join(MODULE_DIR, DRIVER_NAME)

# Independent driver test. Package name is filled in at write time to match the
# agent's chosen package. It exercises CheckSLA directly with a FIXED reference
# time (no real clock), so all timing is deterministic.
DRIVER_TEMPLATE = r'''package %(pkg)s

import (
	"testing"
	"time"

	"github.com/samber/oops"
)

// zzT0 is a fixed reference instant; CheckSLA must never read the real clock.
func zzT0() time.Time {
	return time.Date(2020, 1, 1, 0, 0, 0, 0, time.UTC)
}

func zzAsOops(t *testing.T, err error) oops.OopsError {
	t.Helper()
	if err == nil {
		t.Fatalf("expected non-nil (breach) error, got nil")
	}
	oe, ok := oops.AsOops(err)
	if !ok {
		t.Fatalf("error is not an oops error: %%v", err)
	}
	return oe
}

// ----- nil (no-breach) cases -----

func TestZZUnderBudget(t *testing.T) {
	t0 := zzT0()
	if err := CheckSLA("fetch", t0, t0.Add(50*time.Millisecond), 100*time.Millisecond); err != nil {
		t.Fatalf("under-budget (50ms<=100ms) must be nil, got %%v", err)
	}
}

func TestZZOnBudget(t *testing.T) {
	t0 := zzT0()
	// elapsed == budget is NOT a breach.
	if err := CheckSLA("fetch", t0, t0.Add(100*time.Millisecond), 100*time.Millisecond); err != nil {
		t.Fatalf("on-budget (100ms==100ms) must be nil, got %%v", err)
	}
	// A second, larger on-budget boundary, to defeat a hardcoded threshold.
	if err := CheckSLA("sync", t0, t0.Add(2*time.Second), 2*time.Second); err != nil {
		t.Fatalf("on-budget (2s==2s) must be nil, got %%v", err)
	}
}

func TestZZNegativeElapsed(t *testing.T) {
	t0 := zzT0()
	// finishedAt earlier than startedAt -> negative elapsed -> nil.
	if err := CheckSLA("fetch", t0, t0.Add(-10*time.Millisecond), 100*time.Millisecond); err != nil {
		t.Fatalf("negative elapsed must be nil, got %%v", err)
	}
	// Even with a zero budget, negative elapsed cannot breach.
	if err := CheckSLA("fetch", t0, t0.Add(-1*time.Nanosecond), 0); err != nil {
		t.Fatalf("negative elapsed with zero budget must be nil, got %%v", err)
	}
}

// ----- breach case: full attribute verification -----

func TestZZBreachAttributes(t *testing.T) {
	t0 := zzT0()
	elapsed := 250 * time.Millisecond
	budget := 100 * time.Millisecond
	err := CheckSLA("fetch", t0, t0.Add(elapsed), budget)
	oe := zzAsOops(t, err)

	if got := oe.Code(); got != "sla_breached" {
		t.Fatalf("Code() = %%v, want \"sla_breached\"", got)
	}
	if got := oe.Domain(); got != "sla-monitor" {
		t.Fatalf("Domain() = %%q, want \"sla-monitor\"", got)
	}
	// The actual elapsed time must be carried ON the error via Duration().
	if got := oe.Duration(); got != elapsed {
		t.Fatalf("Duration() = %%v, want %%v", got, elapsed)
	}

	ctx := oe.Context()
	op, ok := ctx["operation"]
	if !ok {
		t.Fatalf("Context() missing key \"operation\"; got %%v", ctx)
	}
	if op != "fetch" {
		t.Fatalf("Context()[operation] = %%v, want \"fetch\"", op)
	}
	bv, ok := ctx["budget"]
	if !ok {
		t.Fatalf("Context() missing key \"budget\"; got %%v", ctx)
	}
	// budget is the time.Duration value itself.
	if bd, ok := bv.(time.Duration); !ok {
		t.Fatalf("Context()[budget] type = %%T, want time.Duration", bv)
	} else if bd != budget {
		t.Fatalf("Context()[budget] = %%v, want %%v", bd, budget)
	}
}

// Duration() must reflect the *actual* elapsed, not the budget and not a constant.
func TestZZDurationTracksElapsed(t *testing.T) {
	t0 := zzT0()
	budget := 100 * time.Millisecond

	e1 := CheckSLA("a", t0, t0.Add(250*time.Millisecond), budget)
	e2 := CheckSLA("b", t0, t0.Add(900*time.Millisecond), budget)
	o1 := zzAsOops(t, e1)
	o2 := zzAsOops(t, e2)

	if o1.Duration() != 250*time.Millisecond {
		t.Fatalf("Duration() = %%v, want 250ms", o1.Duration())
	}
	if o2.Duration() != 900*time.Millisecond {
		t.Fatalf("Duration() = %%v, want 900ms", o2.Duration())
	}
	// Distinct elapsed -> distinct Duration() (defeats a constant/budget value).
	if o1.Duration() == o2.Duration() {
		t.Fatalf("Duration() identical across distinct elapsed times: %%v", o1.Duration())
	}
	// And Duration() must not just echo the budget.
	if o1.Duration() == budget {
		t.Fatalf("Duration() echoes budget (%%v); must be actual elapsed", budget)
	}
}

// Just-over-budget by 1ns must breach (boundary on the breach side).
func TestZZJustOverBudgetBreaches(t *testing.T) {
	t0 := zzT0()
	budget := 100 * time.Millisecond
	err := CheckSLA("fetch", t0, t0.Add(budget+1), budget)
	oe := zzAsOops(t, err)
	if oe.Code() != "sla_breached" {
		t.Fatalf("just-over-budget Code() = %%v, want \"sla_breached\"", oe.Code())
	}
	if oe.Duration() != budget+1 {
		t.Fatalf("Duration() = %%v, want %%v", oe.Duration(), budget+1)
	}
}

// ----- low cardinality: message must be constant, data lives in structure -----

func TestZZMessageCardinality(t *testing.T) {
	t0 := zzT0()
	e1 := CheckSLA("fetch", t0, t0.Add(250*time.Millisecond), 100*time.Millisecond)
	e2 := CheckSLA("flush", t0, t0.Add(777*time.Millisecond), 200*time.Millisecond)
	o1 := zzAsOops(t, e1)
	o2 := zzAsOops(t, e2)

	// Same failure category -> byte-identical Error() string.
	if e1.Error() != e2.Error() {
		t.Fatalf("Error() differs across breaches: %%q vs %%q", e1.Error(), e2.Error())
	}
	// But structured timing/context must differ.
	if o1.Duration() == o2.Duration() {
		t.Fatalf("expected differing Duration() across the two breaches")
	}
	if o1.Context()["operation"] == o2.Context()["operation"] {
		t.Fatalf("expected differing Context()[operation] across the two breaches")
	}
	if o1.Context()["budget"] == o2.Context()["budget"] {
		t.Fatalf("expected differing Context()[budget] across the two breaches")
	}

	// The message must NOT contain interpolated variable data.
	msg := e1.Error()
	for _, frag := range []string{"fetch", "250", "100ms", "250ms"} {
		if zzContains(msg, frag) {
			t.Fatalf("Error() %%q must not contain variable data %%q", msg, frag)
		}
	}
}

func zzContains(s, sub string) bool {
	return len(sub) > 0 && len(s) >= len(sub) && indexOf(s, sub) >= 0
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
    """Read the package name the agent used in slacheck.go."""
    with open(SLACHECK_GO, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            m = re.match(r"\s*package\s+([A-Za-z_][A-Za-z0-9_]*)", line)
            if m:
                return m.group(1)
    return "slacheck"


@pytest.fixture(scope="module", autouse=True)
def _driver_lifecycle():
    """Install the independent Go driver test, then remove it on teardown."""
    pkg = "slacheck"
    if os.path.isfile(SLACHECK_GO):
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
        """L1: the examples/slacheck module directory was created."""
        assert os.path.isdir(MODULE_DIR), f"missing module dir {MODULE_DIR}"

    def test_slacheck_go_exists(self):
        """L1: slacheck.go exists, declares a package and a CheckSLA func."""
        assert os.path.isfile(SLACHECK_GO), "missing examples/slacheck/slacheck.go"
        with open(SLACHECK_GO, encoding="utf-8", errors="replace") as f:
            src = f.read()
        assert re.search(r"\bpackage\s+\w+", src), "no package clause in slacheck.go"
        assert re.search(r"func\s+CheckSLA\s*\(", src), "no CheckSLA function"
        # Deterministic requirement: must NOT read the real clock or sleep.
        assert "time.Now(" not in src, "CheckSLA must not call time.Now()"
        assert "time.Sleep(" not in src, "CheckSLA must not call time.Sleep()"

    def test_slacheck_test_go_exists(self):
        """L1: the agent's own slacheck_test.go deliverable is present."""
        assert os.path.isfile(SLACHECK_TEST_GO), "missing examples/slacheck/slacheck_test.go"
        with open(SLACHECK_TEST_GO, encoding="utf-8", errors="replace") as f:
            src = f.read()
        assert re.search(r"\bpackage\s+\w+", src), "no package clause in slacheck_test.go"
        assert "func Test" in src, "no Test functions in slacheck_test.go"

    def test_go_mod_declares_module(self):
        """L1: go.mod declares the exact module path and requires samber/oops."""
        assert os.path.isfile(MODULE_GO_MOD), "missing examples/slacheck/go.mod"
        with open(MODULE_GO_MOD, encoding="utf-8", errors="replace") as f:
            mod = f.read()
        assert "module github.com/samber/oops/examples/slacheck" in mod, mod
        assert "github.com/samber/oops" in mod

    def test_go_work_lists_module(self):
        """L1: go.work uses ./examples/slacheck so the in-repo lib resolves."""
        assert os.path.isfile(GO_WORK), "missing go.work"
        with open(GO_WORK, encoding="utf-8", errors="replace") as f:
            work = f.read()
        assert "./examples/slacheck" in work, "go.work does not use ./examples/slacheck"

    def test_module_compiles(self):
        """L1/L2: the new module builds against the in-repo library."""
        res = _run_go(["build", "./examples/slacheck/..."])
        assert res.returncode == 0, f"build failed:\nSTDOUT:{res.stdout}\nSTDERR:{res.stderr}"

    # ---------- L2: behavior, driven by the injected independent test ----------

    def _run_driver(self, run_filter):
        return _run_go(
            ["test", "-v", "-count=1", "-run", run_filter, "./examples/slacheck/..."]
        )

    def test_under_budget_returns_nil(self):
        """L2: elapsed < budget -> nil."""
        res = self._run_driver("TestZZUnderBudget$")
        assert res.returncode == 0, f"{res.stdout}\n{res.stderr}"
        assert "PASS: TestZZUnderBudget" in res.stdout, (
            f"driver test did not run/pass:\n{res.stdout}\n{res.stderr}"
        )

    def test_on_budget_returns_nil(self):
        """L2: elapsed == budget (boundary) -> nil, not a breach."""
        res = self._run_driver("TestZZOnBudget$")
        assert res.returncode == 0, f"{res.stdout}\n{res.stderr}"

    def test_negative_elapsed_returns_nil(self):
        """L2: finishedAt < startedAt -> nil even with a zero budget."""
        res = self._run_driver("TestZZNegativeElapsed$")
        assert res.returncode == 0, f"{res.stdout}\n{res.stderr}"

    def test_breach_attributes(self):
        """L2: breach exposes Code/Domain/Duration and operation+budget context."""
        res = self._run_driver("TestZZBreachAttributes$")
        assert res.returncode == 0, f"{res.stdout}\n{res.stderr}"

    def test_duration_tracks_actual_elapsed(self):
        """L2: Duration() equals real elapsed, varies per call, is not the budget."""
        res = self._run_driver("TestZZDurationTracksElapsed$")
        assert res.returncode == 0, f"{res.stdout}\n{res.stderr}"

    def test_just_over_budget_breaches(self):
        """L2: elapsed == budget+1ns breaches (breach-side boundary)."""
        res = self._run_driver("TestZZJustOverBudgetBreaches$")
        assert res.returncode == 0, f"{res.stdout}\n{res.stderr}"

    def test_message_cardinality(self):
        """L2: two breaches -> identical Error(), differing Duration()/Context(), no interpolation."""
        res = self._run_driver("TestZZMessageCardinality$")
        assert res.returncode == 0, f"{res.stdout}\n{res.stderr}"

    def test_agent_native_suite_passes(self):
        """L2: the spec's native command `go test ./examples/slacheck/...` passes overall."""
        res = _run_go(["test", "-count=1", "./examples/slacheck/..."])
        assert res.returncode == 0, f"native suite failed:\nSTDOUT:{res.stdout}\nSTDERR:{res.stderr}"
