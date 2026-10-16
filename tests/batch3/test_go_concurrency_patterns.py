"""Benchmark test for skill: go-concurrency-patterns (variant ext3).

Task: Add a bounded work pool to consul's ``lib/routine`` package (new file
``lib/routine/pool.go`` in package ``routine``). The pool runs a set of
submitted jobs concurrently with a configurable maximum parallelism. Each job
is a ``func(context.Context) error``. A constructor takes a positive max
concurrency and a parent ``context.Context``; callers submit jobs and then wait,
where the wait returns the first non-nil job error (or nil). When any job
errors -- or the parent context is cancelled -- the context handed to still
running / not-yet-started jobs is cancelled so cooperative jobs stop early and
not-yet-started jobs do not run their body.

The agent picks the exact type/method names, so this test does NOT hard-code
them. Instead it:

  * uses a tiny Go AST program to discover the exported constructor whose
    parameter list is (int, context.Context) (in either order) and that returns
    a single type declared in pool.go,
  * generates an independent Go *reflection driver* test that classifies the
    submit and wait operations by signature on the returned pool value, then
  * compiles and runs that driver under ``go test -race`` to deep-validate the
    documented behaviors: the concurrency cap is never exceeded, all jobs run,
    first-error propagation with cancellation of not-yet-started jobs,
    parent-context cancellation unblocking the wait, the all-success (nil)
    case, concurrent submission safety, and the absence of goroutine leaks.

A naive / stub / files-that-merely-look-related solution fails because the
behavior is exercised independently with this test's own assertions and its own
race-detector harness, not by trusting the agent's own ``pool_test.go``.
"""

import os
import shutil
import subprocess
import textwrap

import pytest

def _find_repo_dir(_fallback):
    """Repo clones to /workspace/<repo-name>, not /workspace/<skill-id>. Prefer the
    harness-provided SWE_REPO_DIR (authoritative); else discover the single real repo
    dir under /workspace; else the known fallback. Reading SWE_REPO_DIR avoids picking
    the wrong repo when a job's rootfs accumulated several repos."""
    _env = os.environ.get("SWE_REPO_DIR")
    if _env and os.path.isdir(_env):
        return _env
    import glob as _glob
    _skip = {"tests", "benchmark_tests", "lost+found"}
    _c = [d for d in sorted(_glob.glob("/workspace/*"))
          if os.path.isdir(d) and os.path.basename(d) not in _skip]
    _git = [d for d in _c if os.path.isdir(os.path.join(d, ".git"))]
    if len(_git) == 1:
        return _git[0]
    if len(_c) == 1:
        return _c[0]
    return _fallback
REPO_DIR = _find_repo_dir("/workspace/consul")
ROUTINE_DIR = os.path.join(REPO_DIR, "lib", "routine")
POOL_GO = os.path.join(ROUTINE_DIR, "pool.go")
POOL_TEST_GO = os.path.join(ROUTINE_DIR, "pool_test.go")

# Helper Go files dropped into the package while testing. Unique names so they
# never collide with agent code; cleaned up after the module finishes.
DRIVER_TEST = os.path.join(ROUTINE_DIR, "zz_pool_driver_test.go")
DRIVER_HELP = os.path.join(ROUTINE_DIR, "zz_pool_helper_test.go")

GO_BUILD_TIMEOUT = 420
GO_TEST_TIMEOUT = 600


# --------------------------------------------------------------------------- #
# Embedded Go: AST constructor finder.
# Prints "<CtorName>\t<TypeName>" for each exported, top-level function whose
# parameter list is exactly {int, context.Context} in some order and whose
# single return value's named type is declared in pool.go.
# --------------------------------------------------------------------------- #
CTOR_FINDER_SRC = r'''
package main

import (
	"fmt"
	"go/ast"
	"go/parser"
	"go/token"
	"os"
)

// base named type of an expression (strips *, generics, selectors).
func texpr(e ast.Expr) string {
	switch t := e.(type) {
	case *ast.Ident:
		return t.Name
	case *ast.StarExpr:
		return texpr(t.X)
	case *ast.IndexExpr:
		return texpr(t.X)
	case *ast.IndexListExpr:
		return texpr(t.X)
	case *ast.SelectorExpr:
		return t.Sel.Name
	}
	return ""
}

// classify a parameter type as "int", "ctx" (context.Context), or "" (other).
func ptype(e ast.Expr) string {
	switch t := e.(type) {
	case *ast.Ident:
		if t.Name == "int" {
			return "int"
		}
	case *ast.SelectorExpr:
		if id, ok := t.X.(*ast.Ident); ok && id.Name == "context" && t.Sel.Name == "Context" {
			return "ctx"
		}
	}
	return ""
}

func main() {
	fs := token.NewFileSet()
	f, err := parser.ParseFile(fs, os.Args[1], nil, 0)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(2)
	}
	// types declared in this file
	declared := map[string]bool{}
	for _, d := range f.Decls {
		if gd, ok := d.(*ast.GenDecl); ok {
			for _, s := range gd.Specs {
				if ts, ok := s.(*ast.TypeSpec); ok {
					declared[ts.Name.Name] = true
				}
			}
		}
	}
	for _, d := range f.Decls {
		fn, ok := d.(*ast.FuncDecl)
		if !ok || fn.Recv != nil || !fn.Name.IsExported() {
			continue
		}
		// flatten params to individual fields
		var kinds []string
		if fn.Type.Params != nil {
			for _, fl := range fn.Type.Params.List {
				n := len(fl.Names)
				if n == 0 {
					n = 1
				}
				for i := 0; i < n; i++ {
					kinds = append(kinds, ptype(fl.Type))
				}
			}
		}
		if len(kinds) != 2 {
			continue
		}
		haveInt, haveCtx := false, false
		for _, k := range kinds {
			switch k {
			case "int":
				haveInt = true
			case "ctx":
				haveCtx = true
			}
		}
		if !haveInt || !haveCtx {
			continue
		}
		if fn.Type.Results == nil || len(fn.Type.Results.List) != 1 {
			continue
		}
		name := texpr(fn.Type.Results.List[0].Type)
		if declared[name] {
			fmt.Printf("%s\t%s\n", fn.Name.Name, name)
		}
	}
}
'''


# --------------------------------------------------------------------------- #
# Embedded Go: helper exposing the live goroutine count to driver tests.
# --------------------------------------------------------------------------- #
DRIVER_HELPER_SRC = r'''
package routine

import "runtime"

func zzNumGoroutine() int { return runtime.NumGoroutine() }
'''


# --------------------------------------------------------------------------- #
# Embedded Go: the reflection driver test. ``__CTOR__`` is substituted with the
# discovered constructor name. The submit and wait operations are discovered at
# runtime by signature, so the agent's chosen method names do not matter.
#
#   submit: a method taking exactly one argument that is a
#           func(context.Context) error (a job), returning at most one value.
#   wait:   a method taking no arguments and returning exactly one error.
# --------------------------------------------------------------------------- #
DRIVER_TEST_SRC = r'''
package routine

import (
	"context"
	"errors"
	"reflect"
	"sync"
	"sync/atomic"
	"testing"
	"time"
)

var zzErrType = reflect.TypeOf((*error)(nil)).Elem()
var zzCtxType = reflect.TypeOf((*context.Context)(nil)).Elem()

// zzJobType is func(context.Context) error
var zzJobType = reflect.FuncOf(
	[]reflect.Type{zzCtxType},
	[]reflect.Type{zzErrType},
	false,
)

type zzAPI struct {
	pool   reflect.Value
	submit string
	wait   string
}

func zzNew(limit int) reflect.Value {
	// Constructor takes (int, context.Context) in some order; try both.
	ctx := context.Background()
	ctor := reflect.ValueOf(__CTOR__)
	t := ctor.Type()
	a0, a1 := t.In(0), t.In(1)
	var args []reflect.Value
	switch {
	case a0.Kind() == reflect.Int && a1 == zzCtxType:
		args = []reflect.Value{reflect.ValueOf(limit), reflect.ValueOf(ctx)}
	case a0 == zzCtxType && a1.Kind() == reflect.Int:
		args = []reflect.Value{reflect.ValueOf(ctx), reflect.ValueOf(limit)}
	default:
		// fall back: place int where an int param is.
		if a0.Kind() == reflect.Int {
			args = []reflect.Value{reflect.ValueOf(limit), reflect.ValueOf(ctx)}
		} else {
			args = []reflect.Value{reflect.ValueOf(ctx), reflect.ValueOf(limit)}
		}
	}
	return ctor.Call(args)[0]
}

// zzNewCtx constructs a pool using the supplied parent context.
func zzNewCtx(limit int, ctx context.Context) reflect.Value {
	ctor := reflect.ValueOf(__CTOR__)
	t := ctor.Type()
	a0 := t.In(0)
	var args []reflect.Value
	if a0.Kind() == reflect.Int {
		args = []reflect.Value{reflect.ValueOf(limit), reflect.ValueOf(ctx)}
	} else {
		args = []reflect.Value{reflect.ValueOf(ctx), reflect.ValueOf(limit)}
	}
	return ctor.Call(args)[0]
}

func zzClassify(t *testing.T, p reflect.Value) *zzAPI {
	t.Helper()
	if !p.IsValid() {
		t.Fatalf("constructor returned an invalid value")
	}
	pt := p.Type()
	a := &zzAPI{pool: p}

	// submit: exactly one input arg assignable from a func(ctx) error; result
	// count 0 or 1 (some impls return an error/bool on submit).
	for i := 0; i < pt.NumMethod(); i++ {
		m := pt.Method(i)
		mt := m.Func.Type()
		if mt.NumIn()-1 != 1 {
			continue
		}
		in := mt.In(1)
		if in.Kind() == reflect.Func && zzJobType.AssignableTo(in) {
			a.submit = m.Name
		}
	}
	if a.submit == "" {
		t.Fatalf("no submit-like method (one func(context.Context) error arg) on %s", pt)
	}

	// wait: zero input args, exactly one result of error type.
	for i := 0; i < pt.NumMethod(); i++ {
		m := pt.Method(i)
		mt := m.Func.Type()
		if mt.NumIn()-1 != 0 {
			continue
		}
		if mt.NumOut() == 1 && mt.Out(0) == zzErrType {
			a.wait = m.Name
		}
	}
	if a.wait == "" {
		t.Fatalf("no wait-like method (no args -> error) on %s", pt)
	}
	t.Logf("discovered api: submit=%s wait=%s", a.submit, a.wait)
	return a
}

// submitJob submits a job func(context.Context) error to the pool.
func (a *zzAPI) submitJob(job func(context.Context) error) {
	jv := reflect.MakeFunc(zzJobType, func(in []reflect.Value) []reflect.Value {
		var ctx context.Context
		if c, ok := in[0].Interface().(context.Context); ok {
			ctx = c
		}
		err := job(ctx)
		var ev reflect.Value
		if err == nil {
			ev = reflect.Zero(zzErrType)
		} else {
			ev = reflect.ValueOf(err)
		}
		return []reflect.Value{ev}
	})
	a.pool.MethodByName(a.submit).Call([]reflect.Value{jv})
}

// waitErr waits for completion and returns the first job error.
func (a *zzAPI) waitErr() error {
	res := a.pool.MethodByName(a.wait).Call(nil)
	if len(res) == 1 && !res[0].IsNil() {
		if e, ok := res[0].Interface().(error); ok {
			return e
		}
	}
	return nil
}

// --- scenario tests (run individually by the Python harness via -run) --- //

// TestZZConcurrencyCap submits far more jobs than the limit and asserts the
// observed simultaneous job count never exceeds the limit, while every job
// still runs. A stub that ignores the limit (unbounded) blows past the cap.
func TestZZConcurrencyCap(t *testing.T) {
	const limit = 3
	const njobs = 20
	a := zzClassify(t, zzNew(limit))

	var cur int32
	var peak int32
	var ran int32
	// gate keeps all running jobs alive until the harness has measured peak,
	// forcing the pool to hold `limit` jobs concurrently.
	var started sync.WaitGroup
	started.Add(njobs)
	release := make(chan struct{})

	for i := 0; i < njobs; i++ {
		a.submitJob(func(ctx context.Context) error {
			atomic.AddInt32(&ran, 1)
			n := atomic.AddInt32(&cur, 1)
			for {
				old := atomic.LoadInt32(&peak)
				if n <= old || atomic.CompareAndSwapInt32(&peak, old, n) {
					break
				}
			}
			started.Done()
			<-release
			atomic.AddInt32(&cur, -1)
			return nil
		})
	}

	// Once `limit` jobs are concurrently parked on <-release, release a batch
	// so the next wave can start; repeat until all have started.
	go func() {
		for i := 0; i < njobs; i++ {
			release <- struct{}{}
		}
	}()

	if err := a.waitErr(); err != nil {
		t.Fatalf("all-success run returned error: %v", err)
	}
	if got := atomic.LoadInt32(&ran); int(got) != njobs {
		t.Fatalf("not all jobs ran: want %d, got %d", njobs, got)
	}
	if got := atomic.LoadInt32(&peak); int(got) > limit {
		t.Fatalf("concurrency cap violated: peak=%d > limit=%d", got, limit)
	}
	if got := atomic.LoadInt32(&peak); int(got) < 1 {
		t.Fatalf("no job ever observed running (peak=%d)", got)
	}
}

// TestZZAllSuccessNil submits only successful jobs; wait must return nil and
// every job must have run.
func TestZZAllSuccessNil(t *testing.T) {
	a := zzClassify(t, zzNew(4))
	const njobs = 25
	var ran int32
	for i := 0; i < njobs; i++ {
		a.submitJob(func(ctx context.Context) error {
			atomic.AddInt32(&ran, 1)
			return nil
		})
	}
	if err := a.waitErr(); err != nil {
		t.Fatalf("all-success wait must return nil, got %v", err)
	}
	if int(atomic.LoadInt32(&ran)) != njobs {
		t.Fatalf("want %d jobs run, got %d", njobs, atomic.LoadInt32(&ran))
	}
}

// TestZZFirstErrorPropagates submits jobs where one returns a sentinel error;
// the wait must surface that error and not-yet-started jobs must observe a
// cancelled context (and must not run their body). A stub that returns nil from
// wait, or swallows the error, fails here.
func TestZZFirstErrorPropagates(t *testing.T) {
	a := zzClassify(t, zzNew(2))
	sentinel := errors.New("zz-boom")

	failGate := make(chan struct{})
	var bodyRanAfterCancel int32
	var cancelObserved int32
	var lateScheduled int32

	// 2 slots; first two jobs occupy them. One fails after we let it.
	// Submit one failing job and many "late" jobs that should be cancelled.
	a.submitJob(func(ctx context.Context) error {
		<-failGate
		return sentinel
	})
	// Occupy the other slot with a cooperative long job.
	a.submitJob(func(ctx context.Context) error {
		<-ctx.Done()
		return ctx.Err()
	})
	// Many not-yet-started jobs: when cancellation hits, their context should
	// already be cancelled and they must not execute their "real" body.
	for i := 0; i < 30; i++ {
		a.submitJob(func(ctx context.Context) error {
			atomic.AddInt32(&lateScheduled, 1)
			if ctx.Err() != nil {
				atomic.AddInt32(&cancelObserved, 1)
				return ctx.Err()
			}
			atomic.AddInt32(&bodyRanAfterCancel, 1)
			return nil
		})
	}

	// trigger the failure
	close(failGate)

	err := a.waitErr()
	if !errors.Is(err, sentinel) {
		t.Fatalf("wait must return the first job error %v, got %v", sentinel, err)
	}
	// At least some late jobs must have observed cancellation. (Jobs that never
	// got scheduled won't increment anything, which is also acceptable -- the
	// doc says not-yet-started jobs must not run their body.)
	if atomic.LoadInt32(&lateScheduled) > 0 && atomic.LoadInt32(&cancelObserved) == 0 {
		t.Fatalf("scheduled late jobs but none observed a cancelled context "+
			"(scheduled=%d, ranBody=%d)",
			atomic.LoadInt32(&lateScheduled), atomic.LoadInt32(&bodyRanAfterCancel))
	}
}

// TestZZParentCancelUnblocks builds a pool from a cancellable parent context,
// submits cooperative long-running jobs that block on ctx.Done(), cancels the
// parent, and asserts the wait returns promptly and the jobs saw cancellation.
func TestZZParentCancelUnblocks(t *testing.T) {
	parent, cancel := context.WithCancel(context.Background())
	a := zzClassify(t, zzNewCtx(3, parent))

	var sawCancel int32
	var started sync.WaitGroup
	started.Add(3)
	for i := 0; i < 3; i++ {
		a.submitJob(func(ctx context.Context) error {
			started.Done()
			<-ctx.Done()
			atomic.AddInt32(&sawCancel, 1)
			return ctx.Err()
		})
	}

	done := make(chan error, 1)
	go func() {
		started.Wait()
		cancel()
		done <- a.waitErr()
	}()

	select {
	case <-done:
		// wait returned promptly after parent cancellation
	case <-time.After(8 * time.Second):
		t.Fatal("wait did not return promptly after parent context cancellation")
	}
	if atomic.LoadInt32(&sawCancel) == 0 {
		t.Fatalf("in-flight jobs never observed parent-context cancellation")
	}
}

// TestZZConcurrentSubmit submits jobs from many goroutines simultaneously; the
// pool must remain race-free and run every job exactly once, respecting the cap.
func TestZZConcurrentSubmit(t *testing.T) {
	const limit = 4
	const submitters = 8
	const per = 25
	a := zzClassify(t, zzNew(limit))

	var cur int32
	var peak int32
	var ran int32

	var wg sync.WaitGroup
	for s := 0; s < submitters; s++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for j := 0; j < per; j++ {
				a.submitJob(func(ctx context.Context) error {
					n := atomic.AddInt32(&cur, 1)
					for {
						old := atomic.LoadInt32(&peak)
						if n <= old || atomic.CompareAndSwapInt32(&peak, old, n) {
							break
						}
					}
					atomic.AddInt32(&ran, 1)
					atomic.AddInt32(&cur, -1)
					return nil
				})
			}
		}()
	}
	wg.Wait()

	if err := a.waitErr(); err != nil {
		t.Fatalf("concurrent-submit run returned error: %v", err)
	}
	want := submitters * per
	if int(atomic.LoadInt32(&ran)) != want {
		t.Fatalf("want %d jobs run, got %d", want, atomic.LoadInt32(&ran))
	}
	if int(atomic.LoadInt32(&peak)) > limit {
		t.Fatalf("concurrency cap violated under concurrent submission: peak=%d > %d",
			atomic.LoadInt32(&peak), limit)
	}
}

// TestZZNoGoroutineLeak runs many create/use/wait cycles and asserts goroutine
// count returns near baseline -- no pool goroutine outlives the wait.
func TestZZNoGoroutineLeak(t *testing.T) {
	base := zzNumGoroutine()
	for c := 0; c < 30; c++ {
		a := zzClassify(t, zzNew(3))
		var ran int32
		for i := 0; i < 12; i++ {
			a.submitJob(func(ctx context.Context) error {
				atomic.AddInt32(&ran, 1)
				return nil
			})
		}
		if err := a.waitErr(); err != nil {
			t.Fatalf("cycle %d returned error: %v", c, err)
		}
		if int(atomic.LoadInt32(&ran)) != 12 {
			t.Fatalf("cycle %d: want 12 jobs, got %d", c, ran)
		}
	}
	deadline := time.Now().Add(3 * time.Second)
	after := zzNumGoroutine()
	for time.Now().Before(deadline) && after > base+50 {
		time.Sleep(50 * time.Millisecond)
		after = zzNumGoroutine()
	}
	if after > base+50 {
		t.Fatalf("goroutine leak suspected across create/use/wait cycles: base=%d after=%d", base, after)
	}
}
'''


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _require_go():
    if shutil.which("go") is None:
        pytest.skip("go toolchain not available")


def _find_constructor():
    """Run the embedded AST finder; return the exported constructor name."""
    assert os.path.isfile(POOL_GO), "missing deliverable: lib/routine/pool.go"
    tmpdir = os.path.join(REPO_DIR, ".zz_poolctorfind")
    os.makedirs(tmpdir, exist_ok=True)
    try:
        with open(os.path.join(tmpdir, "main.go"), "w") as fh:
            fh.write(CTOR_FINDER_SRC)
        with open(os.path.join(tmpdir, "go.mod"), "w") as fh:
            fh.write("module zzpoolctorfind\n\ngo 1.21\n")
        proc = subprocess.run(
            ["go", "run", ".", POOL_GO],
            cwd=tmpdir,
            capture_output=True,
            text=True,
            timeout=GO_BUILD_TIMEOUT,
            env={**os.environ, "GOFLAGS": "-buildvcs=false"},
        )
        assert proc.returncode == 0, (
            f"AST constructor finder failed:\nSTDOUT:{proc.stdout}\nSTDERR:{proc.stderr}"
        )
        lines = [ln for ln in proc.stdout.splitlines() if "\t" in ln]
        assert lines, (
            "no exported constructor (a top-level func taking (int, "
            "context.Context) and returning a type declared in pool.go) found "
            f"in pool.go; stdout={proc.stdout!r}"
        )
        ctor = lines[0].split("\t", 1)[0]
        return ctor
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _install_driver(ctor):
    src = DRIVER_TEST_SRC.replace("__CTOR__", ctor)
    with open(DRIVER_TEST, "w") as fh:
        fh.write(src)
    with open(DRIVER_HELP, "w") as fh:
        fh.write(DRIVER_HELPER_SRC)


def _cleanup_driver():
    for p in (DRIVER_TEST, DRIVER_HELP):
        try:
            os.remove(p)
        except OSError:
            pass


def _run_driver(test_name):
    """Run a single driver scenario test under -race; return CompletedProcess."""
    return subprocess.run(
        ["go", "test", "-race", "-count=1", "-run", "^" + test_name + "$",
         "-v", "./lib/routine/"],
        cwd=REPO_DIR,
        capture_output=True,
        text=True,
        timeout=GO_TEST_TIMEOUT,
        env={**os.environ, "GOFLAGS": "-buildvcs=false"},
    )


@pytest.fixture(scope="module", autouse=True)
def _driver_setup():
    """Discover the constructor and install the reflection driver once."""
    _require_go()
    ctor = _find_constructor()
    _install_driver(ctor)
    yield
    _cleanup_driver()


def _assert_driver_pass(proc, scenario):
    combined = proc.stdout + "\n" + proc.stderr
    assert proc.returncode == 0, (
        f"{scenario}: driver test failed (rc={proc.returncode}).\n"
        f"--- go test output ---\n{combined}"
    )
    assert "--- PASS" in proc.stdout or "ok " in proc.stdout, (
        f"{scenario}: no PASS marker in output:\n{combined}"
    )
    assert "panic:" not in combined, f"{scenario}: panic in output:\n{combined}"
    assert "DATA RACE" not in combined, f"{scenario}: data race detected:\n{combined}"


class TestGoConcurrencyPatterns:
    REPO_DIR = _find_repo_dir("/workspace/consul")

    # ----------------------------- L1 ----------------------------- #

    def test_l1_pool_file_exists(self):
        """L1: the deliverable lib/routine/pool.go must exist."""
        assert os.path.isfile(POOL_GO), (
            "missing required deliverable: lib/routine/pool.go"
        )

    def test_l1_in_routine_package(self):
        """L1: pool.go must declare package routine."""
        with open(POOL_GO) as fh:
            head = fh.read()
        assert "package routine" in head, (
            "pool.go must be in package routine"
        )

    def test_l1_test_file_exists(self):
        """L1: the agent must provide pool_test.go with scenarios."""
        assert os.path.isfile(POOL_TEST_GO), (
            "missing required deliverable: lib/routine/pool_test.go"
        )

    def test_l1_package_builds(self):
        """L1: `go build ./lib/routine/` must succeed."""
        _require_go()
        proc = subprocess.run(
            ["go", "build", "./lib/routine/"],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=GO_BUILD_TIMEOUT,
            env={**os.environ, "GOFLAGS": "-buildvcs=false"},
        )
        assert proc.returncode == 0, (
            f"go build ./lib/routine/ failed:\n{proc.stdout}\n{proc.stderr}"
        )

    def test_l1_exported_constructor_discoverable(self):
        """L1: an exported constructor taking (int, context.Context) and
        returning a pool type declared in pool.go must be discoverable."""
        _require_go()
        ctor = _find_constructor()
        assert ctor and ctor[0].isupper(), (
            f"constructor {ctor!r} must be exported (capitalized)"
        )

    # ----------------------------- L2 ----------------------------- #

    def test_l2_concurrency_cap_never_exceeded(self):
        """L2: with limit 3 and 20 jobs, observed peak parallelism is <= 3 and
        all 20 jobs run."""
        _assert_driver_pass(
            _run_driver("TestZZConcurrencyCap"), "concurrency-cap"
        )

    def test_l2_all_success_returns_nil(self):
        """L2: when every job succeeds, wait returns a nil error."""
        _assert_driver_pass(
            _run_driver("TestZZAllSuccessNil"), "all-success-nil"
        )

    def test_l2_first_error_propagates_and_cancels(self):
        """L2: a failing job's error is returned by wait and not-yet-started
        jobs observe a cancelled context."""
        _assert_driver_pass(
            _run_driver("TestZZFirstErrorPropagates"), "first-error-cancel"
        )

    def test_l2_parent_cancel_unblocks_wait(self):
        """L2: cancelling the parent context makes in-flight jobs see
        cancellation and the wait return promptly."""
        _assert_driver_pass(
            _run_driver("TestZZParentCancelUnblocks"), "parent-cancel"
        )

    def test_l2_concurrent_submission_safe(self):
        """L2: submitting from many goroutines is race-free, runs every job,
        and never exceeds the cap."""
        _assert_driver_pass(
            _run_driver("TestZZConcurrentSubmit"), "concurrent-submit"
        )

    def test_l2_no_goroutine_leak_across_cycles(self):
        """L2: repeated create/use/wait cycles do not leak goroutines."""
        _assert_driver_pass(
            _run_driver("TestZZNoGoroutineLeak"), "no-goroutine-leak"
        )

    def test_l2_agents_own_race_suite_passes(self):
        """L2: the agent's `go test -race -run Pool ./lib/routine/` passes clean
        (no failures, no race, no goroutine-leak reports)."""
        _require_go()
        proc = subprocess.run(
            ["go", "test", "-race", "-count=1", "-run", "Pool",
             "./lib/routine/"],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=GO_TEST_TIMEOUT,
            env={**os.environ, "GOFLAGS": "-buildvcs=false"},
        )
        combined = proc.stdout + "\n" + proc.stderr
        assert proc.returncode == 0, (
            "go test -race -run Pool ./lib/routine/ failed:\n" + combined
        )
        assert "DATA RACE" not in combined, "data race reported:\n" + combined
        assert "panic:" not in combined, "panic reported:\n" + combined
        # the agent must actually have Pool-named tests that ran
        assert "no test files" not in combined, (
            "no Pool tests found in lib/routine/:\n" + combined
        )


# keep linters quiet about the optional import
_ = textwrap
