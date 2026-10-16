"""Tests for the go-errors-oops skill task (ext5 variant): "Build a Panic-Safe Job Runner Module".

Verifies that the agent created a self-contained Go example module at
examples/jobrunner that uses github.com/samber/oops to run a batch of
user-supplied job functions where any single job may panic, recovering every
panic and collecting all outcomes into a single aggregate oops error.

Strategy
--------
L1 cases check the required deliverable files exist, are minimally well-formed,
and that go.work / go.mod wiring is present (module path, samber/oops require,
go.work `use ./examples/jobrunner`).

L2 cases EXERCISE the agent's actual RunOne / RunAll functions. Rather than
trusting the agent-authored jobrunner_test.go, this file injects its OWN
independent Go driver test (oops_zz_bench_driver_test.go) into the module and
runs it with `go test`. The driver deep-validates, per the requirement doc:

  * RunOne on a nil-returning job  -> nil
  * RunOne on an error-returning job -> oops error, code "job_failed",
        domain "job-runner", context job == name, and errors.Is reaches the
        underlying sentinel error.
  * RunOne on a PANICKING job -> the panic does NOT escape (the driver would
        crash otherwise), returns an oops error, code "job_panic",
        domain "job-runner", context job == name.
  * RunAll over [ok, bad, boom, ok] -> a single non-nil aggregate that
        (a) satisfies oops.AsOops, (b) is reachable via errors.Is to BOTH the
        bad failure AND the boom panic, (c) executed the trailing ok job
        (proving a panic did not stop the batch), and (d) returns nil when
        every job succeeds.
  * The number of contributing errors equals the number of failed/panicked
        jobs (successful jobs contribute nothing) -> exactly 2 of 4.

A naive solution that stops at the first panic, lets a panic escape, returns a
single hardcoded error, or drops one of the two failures fails these tests.
The driver is removed in teardown.
"""

import os
import re
import subprocess

import pytest

REPO_DIR = "/workspace/oops"
MODULE_DIR = os.path.join(REPO_DIR, "examples", "jobrunner")
JOBRUNNER_GO = os.path.join(MODULE_DIR, "jobrunner.go")
JOBRUNNER_TEST_GO = os.path.join(MODULE_DIR, "jobrunner_test.go")
MODULE_GO_MOD = os.path.join(MODULE_DIR, "go.mod")
GO_WORK = os.path.join(REPO_DIR, "go.work")

DRIVER_NAME = "oops_zz_bench_driver_test.go"
DRIVER_PATH = os.path.join(MODULE_DIR, DRIVER_NAME)

# Independent driver test. Package name is filled in at write time to match the
# agent's chosen package. It exercises RunOne / RunAll directly. Any panic that
# escapes RunOne would crash this test binary, which the harness reports as a
# failure (non-zero exit).
DRIVER_TEMPLATE = r'''package %(pkg)s

import (
	"errors"
	"fmt"
	"testing"

	"github.com/samber/oops"
)

var zzErrBad = errors.New("zz-bad-sentinel")
var zzErrBoom = errors.New("zz-boom-sentinel")

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

func TestZZRunOneNil(t *testing.T) {
	if err := RunOne(Job{Name: "ok", Run: func() error { return nil }}); err != nil {
		t.Fatalf("RunOne(nil-returning job) = %%v, want nil", err)
	}
}

func TestZZRunOneFailed(t *testing.T) {
	err := RunOne(Job{Name: "bad", Run: func() error { return zzErrBad }})
	oe := zzAsOops(t, err)
	if got := fmt.Sprint(oe.Code()); got != "job_failed" {
		t.Fatalf("Code() = %%q, want job_failed", got)
	}
	if got := oe.Domain(); got != "job-runner" {
		t.Fatalf("Domain() = %%q, want job-runner", got)
	}
	if v, ok := oe.Context()["job"]; !ok {
		t.Fatalf("Context() missing key job; got %%v", oe.Context())
	} else if fmt.Sprint(v) != "bad" {
		t.Fatalf("Context()[job] = %%v, want bad", v)
	}
	// The aggregate/individual error must remain reachable to the underlying cause.
	if !errors.Is(err, zzErrBad) {
		t.Fatalf("errors.Is(RunOne err, zzErrBad) = false, want true (cause not preserved)")
	}
}

func TestZZRunOnePanicRecovered(t *testing.T) {
	// If RunOne lets the panic escape, this test binary crashes -> failure.
	err := RunOne(Job{Name: "boom", Run: func() error { panic("kaboom") }})
	oe := zzAsOops(t, err)
	if got := fmt.Sprint(oe.Code()); got != "job_panic" {
		t.Fatalf("Code() = %%q, want job_panic", got)
	}
	if got := oe.Domain(); got != "job-runner" {
		t.Fatalf("Domain() = %%q, want job-runner", got)
	}
	if v, ok := oe.Context()["job"]; !ok {
		t.Fatalf("Context() missing key job; got %%v", oe.Context())
	} else if fmt.Sprint(v) != "boom" {
		t.Fatalf("Context()[job] = %%v, want boom", v)
	}
}

func TestZZRunOnePanicDoesNotEscape(t *testing.T) {
	// Sanity: calling RunOne on a panicking job returns normally (does not panic).
	defer func() {
		if r := recover(); r != nil {
			t.Fatalf("RunOne let a panic escape: %%v", r)
		}
	}()
	if err := RunOne(Job{Name: "boom2", Run: func() error { panic(zzErrBoom) }}); err == nil {
		t.Fatalf("RunOne(panicking job) = nil, want non-nil oops error")
	}
}

func TestZZRunAllAllSucceed(t *testing.T) {
	jobs := []Job{
		{Name: "a", Run: func() error { return nil }},
		{Name: "b", Run: func() error { return nil }},
	}
	if err := RunAll(jobs); err != nil {
		t.Fatalf("RunAll(all-succeeding) = %%v, want nil", err)
	}
}

func TestZZRunAllEmpty(t *testing.T) {
	if err := RunAll(nil); err != nil {
		t.Fatalf("RunAll(nil slice) = %%v, want nil", err)
	}
	if err := RunAll([]Job{}); err != nil {
		t.Fatalf("RunAll(empty slice) = %%v, want nil", err)
	}
}

func TestZZRunAllAggregate(t *testing.T) {
	trailingRan := false
	jobs := []Job{
		{Name: "ok1", Run: func() error { return nil }},
		{Name: "bad", Run: func() error { return zzErrBad }},
		{Name: "boom", Run: func() error { panic(zzErrBoom) }},
		{Name: "ok2", Run: func() error { trailingRan = true; return nil }},
	}

	err := RunAll(jobs)
	if err == nil {
		t.Fatalf("RunAll over [ok, bad, boom, ok] = nil, want non-nil aggregate")
	}

	// (a) the aggregate must itself be an oops error.
	if _, ok := oops.AsOops(err); !ok {
		t.Fatalf("aggregate does not satisfy oops.AsOops: %%v", err)
	}

	// (c) the job AFTER the panicking job must have executed (batch did not stop).
	if !trailingRan {
		t.Fatalf("trailing ok job did not run: a panic stopped the batch")
	}

	// (b) errors.Is must reach BOTH the bad failure and the boom panic cause.
	if !errors.Is(err, zzErrBad) {
		t.Fatalf("errors.Is(aggregate, zzErrBad) = false; bad failure not reachable")
	}
	if !errors.Is(err, zzErrBoom) {
		t.Fatalf("errors.Is(aggregate, zzErrBoom) = false; boom panic not reachable")
	}
}

func TestZZRunAllContributionCount(t *testing.T) {
	// Exactly the failed/panicked jobs contribute; successes contribute nothing.
	// Build the expected individual error values by invoking RunOne ourselves,
	// then assert each is reachable in the aggregate and that a non-contributor
	// (a fresh, never-run sentinel) is NOT reachable.
	jobs := []Job{
		{Name: "ok1", Run: func() error { return nil }},
		{Name: "bad", Run: func() error { return zzErrBad }},
		{Name: "boom", Run: func() error { panic(zzErrBoom) }},
		{Name: "ok2", Run: func() error { return nil }},
	}
	err := RunAll(jobs)
	if err == nil {
		t.Fatalf("expected non-nil aggregate")
	}

	// Walk the aggregate's tree and count leaf contributors that match our two
	// distinct sentinels. There must be exactly two contributing failures.
	matchBad := errors.Is(err, zzErrBad)
	matchBoom := errors.Is(err, zzErrBoom)
	if !matchBad || !matchBoom {
		t.Fatalf("aggregate missing a contributor: bad=%%v boom=%%v", matchBad, matchBoom)
	}

	// A sentinel for a job that never failed must NOT be reachable.
	neverErr := errors.New("zz-never-sentinel")
	if errors.Is(err, neverErr) {
		t.Fatalf("aggregate erroneously reaches an unrelated/never-run error")
	}

	// Count direct contributors via Unwrap() []error if exposed (errors.Join shape).
	n := zzCountContributors(err)
	if n != 2 {
		t.Fatalf("aggregate has %%d contributing errors, want 2 (only failed/panicked jobs)", n)
	}
}

// zzCountContributors counts the leaf errors reachable in err that correspond
// to distinct failed jobs. It tolerates the oops wrapper around an errors.Join
// node by descending through both single Unwrap() and multi Unwrap() []error.
func zzCountContributors(err error) int {
	leaves := 0
	var walk func(e error, atJoin bool)
	walk = func(e error, atJoin bool) {
		if e == nil {
			return
		}
		if m, ok := e.(interface{ Unwrap() []error }); ok {
			for _, c := range m.Unwrap() {
				// Each direct child of the join is one contributing job error.
				leaves++
				walk(c, true)
			}
			return
		}
		if u, ok := e.(interface{ Unwrap() error }); ok {
			walk(u.Unwrap(), atJoin)
		}
	}
	walk(err, false)
	if leaves == 0 {
		// No multi-error join found; fall back to counting distinct reachable
		// sentinels among the two we know failed.
		if errors.Is(err, zzErrBad) {
			leaves++
		}
		if errors.Is(err, zzErrBoom) {
			leaves++
		}
	}
	return leaves
}

func TestZZRunAllSingleAggregate(t *testing.T) {
	// One failing job -> a single non-nil aggregate, still an oops error, still
	// reachable to its cause. (Guards "returns nil unless something failed".)
	jobs := []Job{
		{Name: "ok", Run: func() error { return nil }},
		{Name: "bad", Run: func() error { return zzErrBad }},
	}
	err := RunAll(jobs)
	if err == nil {
		t.Fatalf("RunAll with one failure = nil, want non-nil")
	}
	if _, ok := oops.AsOops(err); !ok {
		t.Fatalf("single-failure aggregate is not an oops error: %%v", err)
	}
	if !errors.Is(err, zzErrBad) {
		t.Fatalf("single-failure aggregate not reachable to cause")
	}
}
'''


def _run_go(args, timeout=600):
    env = dict(os.environ)
    env.setdefault("GOFLAGS", "")
    env.setdefault("CGO_ENABLED", "0")
    return subprocess.run(
        ["go"] + args,
        cwd=REPO_DIR,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )


def _detect_package():
    """Read the package name the agent used in jobrunner.go."""
    try:
        with open(JOBRUNNER_GO, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                m = re.match(r"\s*package\s+([A-Za-z_][A-Za-z0-9_]*)", line)
                if m:
                    return m.group(1)
    except OSError:
        pass
    return "jobrunner"


@pytest.fixture(scope="module", autouse=True)
def _driver_lifecycle():
    """Install the independent Go driver test, then remove it on teardown."""
    pkg = "jobrunner"
    if os.path.isfile(JOBRUNNER_GO):
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
        """L1: the examples/jobrunner module directory was created."""
        assert os.path.isdir(MODULE_DIR), f"missing module dir {MODULE_DIR}"

    def test_jobrunner_go_exists(self):
        """L1: jobrunner.go exists, declares a package, Job type, RunOne and RunAll."""
        assert os.path.isfile(JOBRUNNER_GO), "missing examples/jobrunner/jobrunner.go"
        with open(JOBRUNNER_GO, encoding="utf-8", errors="replace") as f:
            src = f.read()
        assert re.search(r"\bpackage\s+\w+", src), "no package clause in jobrunner.go"
        assert re.search(r"\btype\s+Job\b", src), "no Job type"
        assert re.search(r"func\s+RunOne\s*\(", src), "no RunOne function"
        assert re.search(r"func\s+RunAll\s*\(", src), "no RunAll function"

    def test_go_mod_declares_module(self):
        """L1: go.mod declares the exact module path and requires samber/oops."""
        assert os.path.isfile(MODULE_GO_MOD), "missing examples/jobrunner/go.mod"
        with open(MODULE_GO_MOD, encoding="utf-8", errors="replace") as f:
            mod = f.read()
        assert "module github.com/samber/oops/examples/jobrunner" in mod, mod
        assert "github.com/samber/oops" in mod

    def test_go_work_lists_module(self):
        """L1: go.work uses ./examples/jobrunner so the in-repo lib resolves."""
        assert os.path.isfile(GO_WORK), "missing go.work"
        with open(GO_WORK, encoding="utf-8", errors="replace") as f:
            work = f.read()
        assert "./examples/jobrunner" in work, "go.work does not use ./examples/jobrunner"

    def test_module_compiles(self):
        """L1/L2: the new module builds against the in-repo library."""
        res = _run_go(["build", "./examples/jobrunner/..."])
        assert res.returncode == 0, f"build failed:\nSTDOUT:{res.stdout}\nSTDERR:{res.stderr}"

    # ---------- L2: behavior, driven by the injected independent test ----------

    def _run_driver(self, run_filter, timeout=600):
        return _run_go(
            ["test", "-v", "-count=1", "-run", run_filter, "./examples/jobrunner/..."],
            timeout=timeout,
        )

    def test_runone_nil_returns_nil(self):
        """L2: RunOne on a job whose Run returns nil yields nil."""
        res = self._run_driver("TestZZRunOneNil$")
        assert res.returncode == 0, f"{res.stdout}\n{res.stderr}"
        assert "PASS: TestZZRunOneNil" in res.stdout, (
            f"driver test did not run/pass:\n{res.stdout}\n{res.stderr}"
        )

    def test_runone_failed_metadata(self):
        """L2: RunOne on an error-returning job -> code job_failed, domain job-runner, context job, cause preserved."""
        res = self._run_driver("TestZZRunOneFailed$")
        assert res.returncode == 0, f"{res.stdout}\n{res.stderr}"

    def test_runone_panic_recovered_metadata(self):
        """L2: RunOne on a panicking job recovers -> code job_panic, domain job-runner, context job."""
        res = self._run_driver("TestZZRunOnePanicRecovered$")
        assert res.returncode == 0, f"{res.stdout}\n{res.stderr}"

    def test_runone_panic_does_not_escape(self):
        """L2: a panic inside Run must not propagate out of RunOne."""
        res = self._run_driver("TestZZRunOnePanicDoesNotEscape$")
        assert res.returncode == 0, f"{res.stdout}\n{res.stderr}"

    def test_runall_all_succeed_returns_nil(self):
        """L2: RunAll over only-succeeding jobs returns nil."""
        res = self._run_driver("TestZZRunAllAllSucceed$|TestZZRunAllEmpty$")
        assert res.returncode == 0, f"{res.stdout}\n{res.stderr}"

    def test_runall_aggregate_reaches_both_and_continues(self):
        """L2: RunAll over [ok,bad,boom,ok] -> one oops aggregate, errors.Is reaches both failures, trailing job ran."""
        res = self._run_driver("TestZZRunAllAggregate$")
        assert res.returncode == 0, f"{res.stdout}\n{res.stderr}"
        assert "PASS: TestZZRunAllAggregate" in res.stdout, (
            f"aggregate behavior not verified:\n{res.stdout}\n{res.stderr}"
        )

    def test_runall_contribution_count(self):
        """L2: exactly the 2 failed/panicked jobs contribute; an unrelated error is not reachable."""
        res = self._run_driver("TestZZRunAllContributionCount$")
        assert res.returncode == 0, f"{res.stdout}\n{res.stderr}"

    def test_runall_single_failure_aggregate(self):
        """L2: a single failing job yields a non-nil oops aggregate reachable to its cause."""
        res = self._run_driver("TestZZRunAllSingleAggregate$")
        assert res.returncode == 0, f"{res.stdout}\n{res.stderr}"

    def test_agent_native_suite_passes(self):
        """L2: the spec's native command `go test ./examples/jobrunner/...` passes overall."""
        res = _run_go(["test", "-count=1", "./examples/jobrunner/..."])
        assert res.returncode == 0, (
            f"native suite failed:\nSTDOUT:{res.stdout}\nSTDERR:{res.stderr}"
        )
