"""Benchmark test for skill: go-concurrency-patterns (variant ext9).

Task: Add a *resettable countdown barrier* to consul's ``lib/semaphore``
package (new file ``lib/semaphore/barrier.go`` in package ``semaphore``).
A countdown barrier is initialized with a positive count; goroutines mark
units of work "done" (decrementing the count); other goroutines wait on a
context-aware operation until the count reaches zero; and the barrier can be
*reset* to a new positive count to start a fresh generation.

The public method/field names are chosen by the agent, so this test does NOT
hard-code them. Instead it:

  * uses a tiny Go AST program to discover the exported constructor that takes
    a single integer argument and returns the barrier type,
  * generates an independent Go *reflection driver* test that classifies the
    done / wait / reset operations by signature, and
  * compiles and runs that driver under ``go test -race`` to deep-validate the
    documented behaviors:
        - all waiters released (wait returns nil) once the count reaches zero,
        - a context-cancelled wait returns the context error while other
          counting-down goroutines are unaffected,
        - a wait that begins after the count is already zero returns
          immediately,
        - a reset starts a fresh generation: post-reset waiters block on the
          new count and are released only when the new count reaches zero,
        - the under-zero ``done`` behavior is deterministic (panic OR safe
          no-op) and never corrupts a subsequent reset,
    plus a goroutine-leak check across many create/use/reset cycles.

A naive / stub / files-that-merely-look-related solution fails because the
behavior is exercised independently with this test's own assertions and its
own ``-race`` driver, not by trusting the agent's own ``barrier_test.go``.
The driver fails a "wait" that returns immediately without the count reaching
zero (stub returning nil), a "done" that ignores the count, and a "reset"
that does not re-arm the barrier.
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
SEM_DIR = os.path.join(REPO_DIR, "lib", "semaphore")
BARRIER_GO = os.path.join(SEM_DIR, "barrier.go")
BARRIER_TEST_GO = os.path.join(SEM_DIR, "barrier_test.go")

# Helper Go files dropped into the package while testing. Names are unique
# enough to never collide with agent code and are cleaned up after.
DRIVER_TEST = os.path.join(SEM_DIR, "zz_bench_driver_test.go")
DRIVER_HELP = os.path.join(SEM_DIR, "zz_bench_helper_test.go")

GO_BUILD_TIMEOUT = 300
GO_TEST_TIMEOUT = 420


# --------------------------------------------------------------------------- #
# Embedded Go: AST constructor finder.
# Prints "<CtorName>\t<TypeName>" for each exported, top-level function whose
# single (or first) parameter is an integer-typed value and whose single
# return value names a type *declared in the same file* (the barrier type).
# This matches "a constructor accepts an initial count and returns a barrier".
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

func texpr(e ast.Expr) string {
	switch t := e.(type) {
	case *ast.Ident:
		return t.Name
	case *ast.StarExpr:
		return texpr(t.X)
	case *ast.SelectorExpr:
		return t.Sel.Name
	}
	return ""
}

// isIntIdent reports whether the expr names a built-in integer type.
func isIntIdent(e ast.Expr) bool {
	id, ok := e.(*ast.Ident)
	if !ok {
		return false
	}
	switch id.Name {
	case "int", "int8", "int16", "int32", "int64",
		"uint", "uint8", "uint16", "uint32", "uint64":
		return true
	}
	return false
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
		// at least one integer parameter
		if fn.Type.Params == nil || len(fn.Type.Params.List) == 0 {
			continue
		}
		first := fn.Type.Params.List[0]
		if !isIntIdent(first.Type) {
			continue
		}
		// exactly one return value, naming a type declared in this file
		if fn.Type.Results == nil || len(fn.Type.Results.List) != 1 {
			continue
		}
		rname := texpr(fn.Type.Results.List[0].Type)
		if rname != "" && declared[rname] {
			fmt.Printf("%s\t%s\n", fn.Name.Name, rname)
		}
	}
}
'''


# --------------------------------------------------------------------------- #
# Embedded Go helper: exposes runtime.NumGoroutine for the leak test.
# --------------------------------------------------------------------------- #
DRIVER_HELPER_SRC = r'''
package semaphore

import "runtime"

func zzNumGoroutine() int { return runtime.NumGoroutine() }
'''


# --------------------------------------------------------------------------- #
# Embedded Go: the reflection driver test. ``__CTOR__`` is substituted with the
# discovered constructor name. All operations other than the constructor are
# discovered at runtime by signature, so the agent's chosen method names do not
# matter.
#
# Classification (on the barrier type returned by __CTOR__(N)):
#   wait  : method taking a context.Context, returning an error.
#   done  : method with no args (or args not int/ctx) returning no value or a
#           non-error value; decrements the count. We require: 0 input args.
#   reset : method taking a single integer argument (re-arms with new count).
# --------------------------------------------------------------------------- #
DRIVER_TEST_SRC = r'''
package semaphore

import (
	"context"
	"reflect"
	"sync"
	"testing"
	"time"
)

var zzCtxType = reflect.TypeOf((*context.Context)(nil)).Elem()
var zzErrType = reflect.TypeOf((*error)(nil)).Elem()

func zzIsInt(t reflect.Type) bool {
	switch t.Kind() {
	case reflect.Int, reflect.Int8, reflect.Int16, reflect.Int32, reflect.Int64,
		reflect.Uint, reflect.Uint8, reflect.Uint16, reflect.Uint32, reflect.Uint64:
		return true
	}
	return false
}

type zzAPI struct {
	bt      reflect.Type
	wait    string // (ctx) error
	done    string // () [no int/ctx args]  -> decrement
	reset   string // (int) re-arm
	intKind reflect.Type
}

// zzNew constructs a barrier with count n via the discovered constructor.
func zzNew(n int) reflect.Value {
	ctor := reflect.ValueOf(__CTOR__)
	ct := ctor.Type()
	arg := reflect.ValueOf(n)
	if ct.NumIn() >= 1 {
		arg = arg.Convert(ct.In(0))
	}
	// fill remaining params (if any) with zero values
	in := []reflect.Value{arg}
	for i := 1; i < ct.NumIn(); i++ {
		in = append(in, reflect.Zero(ct.In(i)))
	}
	return ctor.Call(in)[0]
}

func zzClassify(t *testing.T) *zzAPI {
	t.Helper()
	b := zzNew(1)
	if !b.IsValid() {
		t.Fatalf("constructor returned an invalid value")
	}
	bt := b.Type()
	a := &zzAPI{bt: bt}

	for i := 0; i < bt.NumMethod(); i++ {
		m := bt.Method(i)
		mt := m.Func.Type()
		nin := mt.NumIn() - 1 // minus receiver

		// wait: exactly one ctx arg, exactly one error result.
		if nin == 1 && mt.In(1) == zzCtxType &&
			mt.NumOut() == 1 && mt.Out(0) == zzErrType {
			a.wait = m.Name
			continue
		}
		// reset: exactly one integer arg (and not a context); re-arm.
		if nin == 1 && zzIsInt(mt.In(1)) {
			a.reset = m.Name
			a.intKind = mt.In(1)
			continue
		}
	}
	// done: no input args, and either no result or a non-error/non-(sub)value
	// result. We pick the no-arg method that is not the wait method.
	for i := 0; i < bt.NumMethod(); i++ {
		m := bt.Method(i)
		mt := m.Func.Type()
		nin := mt.NumIn() - 1
		if nin == 0 && m.Name != a.wait {
			a.done = m.Name
			break
		}
	}

	if a.wait == "" {
		t.Fatalf("no wait-like method (one context.Context arg -> error) on %s", bt)
	}
	if a.done == "" {
		t.Fatalf("no done-like method (no args) on %s", bt)
	}
	if a.reset == "" {
		t.Fatalf("no reset-like method (one integer arg) on %s", bt)
	}
	t.Logf("discovered api: wait=%s done=%s reset=%s", a.wait, a.done, a.reset)
	return a
}

func (a *zzAPI) callDone(b reflect.Value) {
	b.MethodByName(a.done).Call(nil)
}

func (a *zzAPI) callReset(b reflect.Value, n int) {
	arg := reflect.ValueOf(n)
	if a.intKind != nil {
		arg = arg.Convert(a.intKind)
	}
	b.MethodByName(a.reset).Call([]reflect.Value{arg})
}

// waitAsync calls wait(ctx) in a goroutine and returns a channel carrying the
// returned error (nil if the wait returned nil).
func (a *zzAPI) waitAsync(b reflect.Value, ctx context.Context) <-chan error {
	out := make(chan error, 1)
	m := b.MethodByName(a.wait)
	go func() {
		res := m.Call([]reflect.Value{reflect.ValueOf(ctx)})
		var err error
		if len(res) == 1 && !res[0].IsNil() {
			err, _ = res[0].Interface().(error)
		}
		out <- err
	}()
	return out
}

// --- scenario tests (run individually by the Python harness via -run) --- //

// All waiters are released (wait returns nil) once the count reaches zero,
// where the count is driven down by worker goroutines.
func TestZZAllWaitersReleased(t *testing.T) {
	a := zzClassify(t)
	const N = 5
	b := zzNew(N)

	const W = 8
	results := make([]<-chan error, W)
	for i := 0; i < W; i++ {
		ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		results[i] = a.waitAsync(b, ctx)
	}

	// Workers count down. Use a barrier-start channel so all dones race.
	start := make(chan struct{})
	var wg sync.WaitGroup
	for i := 0; i < N; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			<-start
			a.callDone(b)
		}()
	}
	close(start)
	wg.Wait()

	for i := 0; i < W; i++ {
		select {
		case err := <-results[i]:
			if err != nil {
				t.Fatalf("waiter %d: expected nil after count reached zero, got %v", i, err)
			}
		case <-time.After(5 * time.Second):
			t.Fatalf("waiter %d: not released after %d dones", i, N)
		}
	}
}

// A wait that begins after the count has already reached zero returns
// immediately (no blocking).
func TestZZWaitAfterZeroReturnsImmediately(t *testing.T) {
	a := zzClassify(t)
	b := zzNew(2)
	a.callDone(b)
	a.callDone(b) // now at zero

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	select {
	case err := <-a.waitAsync(b, ctx):
		if err != nil {
			t.Fatalf("wait after zero must return nil, got %v", err)
		}
	case <-time.After(3 * time.Second):
		t.Fatal("wait after count already zero did not return immediately")
	}
}

// A context-cancelled wait returns the context error, while other goroutines
// continuing to count down are unaffected (and a non-cancelled waiter still
// gets released when zero is reached).
func TestZZCancelledWaitReturnsCtxErr(t *testing.T) {
	a := zzClassify(t)
	b := zzNew(3) // not yet zero

	cctx, ccancel := context.WithCancel(context.Background())
	cancelled := a.waitAsync(b, cctx)

	okCtx, okCancelFn := context.WithTimeout(context.Background(), 5*time.Second)
	defer okCancelFn()
	okWaiter := a.waitAsync(b, okCtx)

	// Cancel the first waiter before the count reaches zero.
	ccancel()
	select {
	case err := <-cancelled:
		if err == nil {
			t.Fatal("cancelled wait must return a non-nil context error, got nil")
		}
		if err != context.Canceled {
			t.Fatalf("cancelled wait must return context.Canceled, got %v", err)
		}
	case <-time.After(5 * time.Second):
		t.Fatal("cancelled wait did not return")
	}

	// The remaining waiter must still be sitting (count not yet zero).
	select {
	case err := <-okWaiter:
		t.Fatalf("non-cancelled waiter released before count reached zero (err=%v)", err)
	case <-time.After(150 * time.Millisecond):
	}

	// Now drive to zero; the surviving waiter must be released with nil.
	a.callDone(b)
	a.callDone(b)
	a.callDone(b)
	select {
	case err := <-okWaiter:
		if err != nil {
			t.Fatalf("surviving waiter expected nil at zero, got %v", err)
		}
	case <-time.After(5 * time.Second):
		t.Fatal("surviving waiter not released after count reached zero")
	}
}

// Reset starts a fresh generation: after reaching zero, reset to a new count;
// waiters arriving after the reset block on the new count and are released
// only when the new count reaches zero.
func TestZZResetNewGeneration(t *testing.T) {
	a := zzClassify(t)
	b := zzNew(2)
	a.callDone(b)
	a.callDone(b) // generation 1 hits zero

	// confirm gen-1 is released
	g1ctx, g1cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer g1cancel()
	select {
	case err := <-a.waitAsync(b, g1ctx):
		if err != nil {
			t.Fatalf("gen-1 wait at zero expected nil, got %v", err)
		}
	case <-time.After(3 * time.Second):
		t.Fatal("gen-1 wait did not return at zero")
	}

	// Reset to a new positive count: a new generation begins.
	a.callReset(b, 3)

	wctx, wcancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer wcancel()
	waiter := a.waitAsync(b, wctx)

	// Must block: new generation not yet at zero.
	select {
	case err := <-waiter:
		t.Fatalf("post-reset waiter released before new count reached zero (err=%v)", err)
	case <-time.After(200 * time.Millisecond):
	}

	// Drive the new generation to zero.
	a.callDone(b)
	a.callDone(b)
	a.callDone(b)
	select {
	case err := <-waiter:
		if err != nil {
			t.Fatalf("post-reset waiter expected nil at new zero, got %v", err)
		}
	case <-time.After(5 * time.Second):
		t.Fatal("post-reset waiter not released after new count reached zero")
	}
}

// Reset while no waiters block must produce a fully functional new generation,
// and reset after a previously-released generation must not corrupt state:
// two full cycles in a row.
func TestZZResetReuseTwoCycles(t *testing.T) {
	a := zzClassify(t)
	b := zzNew(1)
	for cycle := 0; cycle < 2; cycle++ {
		ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		w := a.waitAsync(b, ctx)
		a.callDone(b)
		select {
		case err := <-w:
			if err != nil {
				cancel()
				t.Fatalf("cycle %d waiter expected nil, got %v", cycle, err)
			}
		case <-time.After(5 * time.Second):
			cancel()
			t.Fatalf("cycle %d waiter not released", cycle)
		}
		cancel()
		a.callReset(b, 1)
	}
}

// The under-zero done behavior must be deterministic: either it panics with a
// clear message, OR it is a safe no-op. Either way, the barrier must remain
// usable for a subsequent reset/countdown (a no-op must not drive the count
// negative such that a later reset is corrupted).
func TestZZUnderZeroDeterministic(t *testing.T) {
	a := zzClassify(t)
	b := zzNew(1)
	a.callDone(b) // count now zero

	panicked := func() (p bool) {
		defer func() {
			if r := recover(); r != nil {
				p = true
			}
		}()
		a.callDone(b) // decrement below zero
		return false
	}()

	// Regardless of the chosen behavior (panic or no-op), a reset must yield a
	// working new generation.
	a.callReset(b, 2)
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	w := a.waitAsync(b, ctx)
	// must block until exactly 2 dones
	select {
	case err := <-w:
		t.Fatalf("after under-zero (%v) + reset(2): waiter released early (err=%v)",
			map[bool]string{true: "panicked", false: "no-op"}[panicked], err)
	case <-time.After(150 * time.Millisecond):
	}
	a.callDone(b)
	a.callDone(b)
	select {
	case err := <-w:
		if err != nil {
			t.Fatalf("post-reset waiter expected nil, got %v", err)
		}
	case <-time.After(5 * time.Second):
		t.Fatalf("post-reset waiter not released; under-zero done corrupted state (behavior=%v)",
			map[bool]string{true: "panicked", false: "no-op"}[panicked])
	}
}

// Many concurrent waiters + concurrent dones must all settle (data-race clean
// is enforced by -race; here we assert every waiter is released exactly once
// the count hits zero, under heavy contention).
func TestZZConcurrentWaitersAndDones(t *testing.T) {
	a := zzClassify(t)
	const N = 64
	b := zzNew(N)

	const W = 50
	errs := make([]<-chan error, W)
	for i := 0; i < W; i++ {
		ctx, cancel := context.WithTimeout(context.Background(), 8*time.Second)
		defer cancel()
		errs[i] = a.waitAsync(b, ctx)
	}

	start := make(chan struct{})
	var wg sync.WaitGroup
	for i := 0; i < N; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			<-start
			a.callDone(b)
		}()
	}
	close(start)
	wg.Wait()

	for i := 0; i < W; i++ {
		select {
		case err := <-errs[i]:
			if err != nil {
				t.Fatalf("waiter %d expected nil under contention, got %v", i, err)
			}
		case <-time.After(8 * time.Second):
			t.Fatalf("waiter %d not released under contention", i)
		}
	}
}

// Repeated create/use/reset cycles must not leak goroutines once all waiters
// have been released.
func TestZZNoGoroutineLeak(t *testing.T) {
	a := zzClassify(t)
	base := zzNumGoroutine()
	for c := 0; c < 40; c++ {
		b := zzNew(3)
		var wg sync.WaitGroup
		for i := 0; i < 4; i++ {
			ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
			ch := a.waitAsync(b, ctx)
			wg.Add(1)
			go func() {
				defer wg.Done()
				defer cancel()
				<-ch
			}()
		}
		a.callDone(b)
		a.callDone(b)
		a.callDone(b)
		wg.Wait()
		a.callReset(b, 1)
		a.callDone(b)
	}
	deadline := time.Now().Add(2 * time.Second)
	after := zzNumGoroutine()
	for time.Now().Before(deadline) && after > base+100 {
		time.Sleep(50 * time.Millisecond)
		after = zzNumGoroutine()
	}
	if after > base+100 {
		t.Fatalf("goroutine leak suspected across create/use/reset cycles: base=%d after=%d", base, after)
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
    assert os.path.isfile(BARRIER_GO), (
        "missing deliverable: lib/semaphore/barrier.go"
    )
    tmpdir = os.path.join(REPO_DIR, ".zz_ctorfind_barrier")
    os.makedirs(tmpdir, exist_ok=True)
    try:
        with open(os.path.join(tmpdir, "main.go"), "w") as fh:
            fh.write(CTOR_FINDER_SRC)
        with open(os.path.join(tmpdir, "go.mod"), "w") as fh:
            fh.write("module zzctorfindbarrier\n\ngo 1.21\n")
        proc = subprocess.run(
            ["go", "run", ".", BARRIER_GO],
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
            "no exported constructor (a top-level func taking an integer count "
            "and returning the barrier type) found in barrier.go; stdout="
            f"{proc.stdout!r}"
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
         "-v", "./lib/semaphore/"],
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
    assert "--- PASS" in proc.stdout or "ok  " in proc.stdout, (
        f"{scenario}: no PASS marker in output:\n{combined}"
    )
    assert "panic:" not in combined, f"{scenario}: panic in output:\n{combined}"
    assert "DATA RACE" not in combined, f"{scenario}: data race detected:\n{combined}"


class TestGoConcurrencyPatterns:
    REPO_DIR = _find_repo_dir("/workspace/consul")

    # ----------------------------- L1 ----------------------------- #

    def test_l1_barrier_file_exists(self):
        """L1: the deliverable lib/semaphore/barrier.go must exist."""
        assert os.path.isfile(BARRIER_GO), (
            "missing required deliverable: lib/semaphore/barrier.go"
        )

    def test_l1_in_semaphore_package(self):
        """L1: barrier.go must declare package semaphore."""
        with open(BARRIER_GO) as fh:
            head = fh.read()
        assert "package semaphore" in head, (
            "barrier.go must be in package semaphore"
        )

    def test_l1_test_file_exists(self):
        """L1: the agent must provide barrier_test.go with scenarios."""
        assert os.path.isfile(BARRIER_TEST_GO), (
            "missing required deliverable: lib/semaphore/barrier_test.go"
        )

    def test_l1_package_builds(self):
        """L1: `go build ./lib/semaphore/` must succeed."""
        _require_go()
        proc = subprocess.run(
            ["go", "build", "./lib/semaphore/"],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=GO_BUILD_TIMEOUT,
            env={**os.environ, "GOFLAGS": "-buildvcs=false"},
        )
        assert proc.returncode == 0, (
            f"go build ./lib/semaphore/ failed:\n{proc.stdout}\n{proc.stderr}"
        )

    def test_l1_exported_constructor_discoverable(self):
        """L1: an exported constructor (int count -> barrier type) must be
        discoverable via AST and be capitalized (exported)."""
        _require_go()
        ctor = _find_constructor()
        assert ctor and ctor[0].isupper(), (
            f"constructor {ctor!r} must be exported (capitalized)"
        )

    # ----------------------------- L2 ----------------------------- #

    def test_l2_all_waiters_released_on_zero(self):
        """L2: every waiter returns nil once worker goroutines drive the
        count to zero (a stub wait returning nil prematurely would still pass
        this, but other L2 cases catch that)."""
        _assert_driver_pass(
            _run_driver("TestZZAllWaitersReleased"), "all-waiters-released"
        )

    def test_l2_wait_after_zero_returns_immediately(self):
        """L2: a wait beginning after the count is already zero returns at once."""
        _assert_driver_pass(
            _run_driver("TestZZWaitAfterZeroReturnsImmediately"),
            "wait-after-zero",
        )

    def test_l2_cancelled_wait_returns_ctx_error(self):
        """L2: a cancelled wait returns context.Canceled while a separate
        waiter still blocks (count not yet zero) and is later released. This
        fails any stub whose wait ignores the context or returns nil early."""
        _assert_driver_pass(
            _run_driver("TestZZCancelledWaitReturnsCtxErr"), "cancelled-wait"
        )

    def test_l2_reset_starts_new_generation(self):
        """L2: after reaching zero, reset re-arms; post-reset waiters block on
        the new count and are released only when it reaches zero. A reset that
        does not re-arm releases the waiter early and fails."""
        _assert_driver_pass(
            _run_driver("TestZZResetNewGeneration"), "reset-new-generation"
        )

    def test_l2_reset_reuse_two_cycles(self):
        """L2: two full countdown cycles separated by reset both work."""
        _assert_driver_pass(
            _run_driver("TestZZResetReuseTwoCycles"), "reset-reuse"
        )

    def test_l2_under_zero_done_deterministic(self):
        """L2: decrementing below zero is deterministic (panic OR safe no-op)
        and does not corrupt a subsequent reset/countdown generation."""
        _assert_driver_pass(
            _run_driver("TestZZUnderZeroDeterministic"), "under-zero"
        )

    def test_l2_concurrent_waiters_and_dones(self):
        """L2: under heavy contention (64 dones, 50 waiters) every waiter is
        released with nil and the run is race-clean."""
        _assert_driver_pass(
            _run_driver("TestZZConcurrentWaitersAndDones"), "concurrent"
        )

    def test_l2_no_goroutine_leak(self):
        """L2: repeated create/use/reset cycles do not leak goroutines."""
        _assert_driver_pass(
            _run_driver("TestZZNoGoroutineLeak"), "no-goroutine-leak"
        )

    def test_l2_agents_own_race_suite_passes(self):
        """L2: the doc's native acceptance command
        `go test -race -run Barrier ./lib/semaphore/` passes clean (no
        failures, no race or goroutine-leak reports) and actually ran
        Barrier-named tests."""
        _require_go()
        proc = subprocess.run(
            ["go", "test", "-race", "-count=1", "-run", "Barrier",
             "./lib/semaphore/"],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=GO_TEST_TIMEOUT,
            env={**os.environ, "GOFLAGS": "-buildvcs=false"},
        )
        combined = proc.stdout + "\n" + proc.stderr
        assert proc.returncode == 0, (
            "go test -race -run Barrier ./lib/semaphore/ failed:\n" + combined
        )
        assert "DATA RACE" not in combined, "data race reported:\n" + combined
        assert "panic:" not in combined, "panic reported:\n" + combined
        assert "no test files" not in combined, (
            "no Barrier tests found in lib/semaphore/:\n" + combined
        )
        # the agent's Barrier tests must actually have executed at least one test
        assert ("ok  " in proc.stdout or "PASS" in proc.stdout), (
            "expected the agent's Barrier tests to run and pass:\n" + combined
        )


# keep textwrap import load-bearing for linters/parity with template
_ = textwrap
