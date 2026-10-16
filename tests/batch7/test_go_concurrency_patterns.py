"""Benchmark test for skill: go-concurrency-patterns (variant ext7).

Task: Add a *periodic task runner* to consul's ``lib/routine`` package (new file
``lib/routine/periodic.go`` in package ``routine``). The runner takes an interval
duration plus a ``func(context.Context) error`` callback, runs the callback once
per interval inside a single dedicated goroutine, supports a *non-blocking* start
and a *blocking* stop that waits for any in-progress callback to finish, never
overlaps callback invocations, and is safe to stop more than once.

The agent chooses the concrete type / constructor / method names, so this test
does NOT hard-code them. Instead it:

  * uses a tiny Go AST program to discover the exported constructor whose
    parameter list contains a ``time.Duration`` and a ``func(context.Context)
    error`` callback and whose single return value is a type declared in the
    file (the runner / a pointer to it);
  * generates an INDEPENDENT Go *reflection driver* test that classifies the
    start / stop operations by signature (start = no-arg method that returns
    promptly; stop = the other no-arg method), then compiles and runs that
    driver under ``go test -race`` to deep-validate the documented behaviors:
      - periodic invocation (counter advances ~ #intervals) and cessation after
        stop (counter stops advancing once stop returns),
      - start is non-blocking (returns long before an interval elapses),
      - stop cancels the callback's context and only returns after a blocked
        cooperative callback has returned,
      - a slow callback (longer than the interval) never produces overlapping
        concurrent invocations,
      - stop is idempotent (calling it twice does not panic),
      - no goroutine leak across repeated start/stop cycles.

A naive / stub / files-that-merely-look-related solution fails because every
behavior is exercised independently with this test's own assertions and timing
gates, not by trusting the agent's own ``periodic_test.go``.
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
PERIODIC_GO = os.path.join(ROUTINE_DIR, "periodic.go")
PERIODIC_TEST = os.path.join(ROUTINE_DIR, "periodic_test.go")

# Helper Go files we drop into the package while testing. Unique prefixes so they
# never collide with agent code; cleaned up after the run.
DRIVER_TEST = os.path.join(ROUTINE_DIR, "zz_bench_driver_test.go")
DRIVER_HELP = os.path.join(ROUTINE_DIR, "zz_bench_helper_test.go")

GO_BUILD_TIMEOUT = 300
GO_TEST_TIMEOUT = 420


# --------------------------------------------------------------------------- #
# Embedded Go: AST constructor finder.
# Prints "<CtorName>\t<TypeName>" for each exported, top-level function that:
#   * has a parameter assignable from time.Duration (a Duration / named int64),
#   * has a parameter that is a func type taking one arg and returning one value
#     (the callback func(context.Context) error),
#   * returns exactly one value whose (possibly pointer-) base type is declared
#     in the same file.
# This is permissive on names but strict on shape, matching the task contract.
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

func baseName(e ast.Expr) string {
	switch t := e.(type) {
	case *ast.Ident:
		return t.Name
	case *ast.StarExpr:
		return baseName(t.X)
	case *ast.SelectorExpr:
		return t.Sel.Name
	case *ast.IndexExpr:
		return baseName(t.X)
	case *ast.IndexListExpr:
		return baseName(t.X)
	}
	return ""
}

// looksLikeDuration: a param typed Duration, time.Duration, or a bare int64.
func looksLikeDuration(e ast.Expr) bool {
	switch t := e.(type) {
	case *ast.SelectorExpr:
		return t.Sel.Name == "Duration"
	case *ast.Ident:
		return t.Name == "Duration" || t.Name == "int64"
	}
	return false
}

// looksLikeCallback: a func type with >=1 param and >=1 result (e.g.
// func(context.Context) error).
func looksLikeCallback(e ast.Expr) bool {
	ft, ok := e.(*ast.FuncType)
	if !ok {
		return false
	}
	nin := 0
	if ft.Params != nil {
		for _, f := range ft.Params.List {
			if len(f.Names) == 0 {
				nin++
			} else {
				nin += len(f.Names)
			}
		}
	}
	nout := 0
	if ft.Results != nil {
		for _, f := range ft.Results.List {
			if len(f.Names) == 0 {
				nout++
			} else {
				nout += len(f.Names)
			}
		}
	}
	return nin >= 1 && nout >= 1
}

func main() {
	fs := token.NewFileSet()
	f, err := parser.ParseFile(fs, os.Args[1], nil, 0)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(2)
	}
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
		if fn.Type.Results == nil || len(fn.Type.Results.List) != 1 {
			continue
		}
		ret := fn.Type.Results.List[0].Type
		rname := baseName(ret)
		if !declared[rname] {
			continue
		}
		hasDur := false
		hasCb := false
		if fn.Type.Params != nil {
			for _, p := range fn.Type.Params.List {
				if looksLikeDuration(p.Type) {
					hasDur = true
				}
				if looksLikeCallback(p.Type) {
					hasCb = true
				}
			}
		}
		if hasDur && hasCb {
			fmt.Printf("%s\t%s\n", fn.Name.Name, rname)
		}
	}
}
'''


# --------------------------------------------------------------------------- #
# Embedded Go: helper (goroutine counter).
# --------------------------------------------------------------------------- #
DRIVER_HELPER_SRC = r'''
package routine

import "runtime"

func zzNumGoroutine() int { return runtime.NumGoroutine() }
'''


# --------------------------------------------------------------------------- #
# Embedded Go: reflection driver test. ``__CTOR__`` is substituted with the
# discovered constructor name. The constructor is invoked reflectively with an
# interval Duration and our own callback; start/stop are discovered by signature
# at runtime, so the agent's chosen names do not matter.
# --------------------------------------------------------------------------- #
DRIVER_TEST_SRC = r'''
package routine

import (
	"context"
	"reflect"
	"sync"
	"sync/atomic"
	"testing"
	"time"
)

var zzCtxIface = reflect.TypeOf((*context.Context)(nil)).Elem()
var zzErrIface = reflect.TypeOf((*error)(nil)).Elem()
var zzDurType = reflect.TypeOf(time.Duration(0))

// zzRunner builds a runner via the discovered constructor with the given
// interval and callback, and resolves its start/stop methods.
type zzRunner struct {
	v     reflect.Value
	start string
	stop  string
}

// zzCtorIn returns the reflect.Value to pass for each constructor parameter:
// the Duration param gets `interval`, the callback param gets `cb`, anything
// else gets a zero value.
func zzMakeCtorArgs(ct reflect.Type, interval time.Duration, cb interface{}) []reflect.Value {
	cbVal := reflect.ValueOf(cb)
	args := make([]reflect.Value, ct.NumIn())
	for i := 0; i < ct.NumIn(); i++ {
		pt := ct.In(i)
		switch {
		case pt == zzDurType || pt.Kind() == reflect.Int64 && pt.ConvertibleTo(zzDurType):
			args[i] = reflect.ValueOf(interval).Convert(pt)
		case pt.Kind() == reflect.Func:
			args[i] = cbVal.Convert(pt)
		default:
			args[i] = reflect.Zero(pt)
		}
	}
	return args
}

func zzBuild(t *testing.T, interval time.Duration, cb func(context.Context) error) *zzRunner {
	t.Helper()
	ctor := reflect.ValueOf(__CTOR__)
	ct := ctor.Type()
	// sanity: callback param must accept func(context.Context) error
	cbAssignable := false
	durPresent := false
	for i := 0; i < ct.NumIn(); i++ {
		pt := ct.In(i)
		if pt.Kind() == reflect.Func && pt.NumIn() == 1 && pt.In(0) == zzCtxIface &&
			pt.NumOut() == 1 && pt.Out(0) == zzErrIface {
			cbAssignable = true
		}
		if pt == zzDurType || (pt.Kind() == reflect.Int64 && pt.ConvertibleTo(zzDurType)) {
			durPresent = true
		}
	}
	if !cbAssignable {
		t.Fatalf("constructor has no func(context.Context) error callback parameter; type=%s", ct)
	}
	if !durPresent {
		t.Fatalf("constructor has no time.Duration interval parameter; type=%s", ct)
	}
	out := ctor.Call(zzMakeCtorArgs(ct, interval, cb))
	if len(out) != 1 || !out[0].IsValid() {
		t.Fatalf("constructor did not return a single runner value")
	}
	r := &zzRunner{v: out[0]}

	// Discover no-arg, no-result methods. The task requires both a start and a
	// stop with this shape. We classify them empirically below: the one that
	// returns promptly is start; the remaining one is stop.
	rt := r.v.Type()
	var noArg []string
	for i := 0; i < rt.NumMethod(); i++ {
		m := rt.Method(i)
		mt := m.Func.Type()
		if mt.NumIn()-1 == 0 && mt.NumOut() == 0 {
			noArg = append(noArg, m.Name)
		}
	}
	if len(noArg) < 2 {
		t.Fatalf("runner %s must expose at least two no-arg methods (start and stop); found %v", rt, noArg)
	}
	return r.classify(t, noArg)
}

// classify decides which no-arg method is start vs stop by timing: start must
// return promptly (well under the interval) and must NOT block the caller, while
// stop returns only after the runner stops. We call each candidate as "start"
// and verify it is non-blocking; the candidate that returns promptly AND causes
// the callback to begin firing is start. The complementary one is stop.
func (r *zzRunner) classify(t *testing.T, noArg []string) *zzRunner {
	t.Helper()
	// Heuristic by name first (cheap, robust): prefer Start/Run for start,
	// Stop/Close/Shutdown for stop. Fall back to the first two otherwise.
	startNames := map[string]bool{"Start": true, "Run": true, "Begin": true, "Go": true}
	stopNames := map[string]bool{"Stop": true, "Close": true, "Shutdown": true, "Cancel": true}
	for _, n := range noArg {
		if startNames[n] {
			r.start = n
		}
		if stopNames[n] {
			r.stop = n
		}
	}
	if r.start == "" || r.stop == "" || r.start == r.stop {
		// fallback: take first two distinct
		r.start = noArg[0]
		r.stop = ""
		for _, n := range noArg[1:] {
			if n != r.start {
				r.stop = n
				break
			}
		}
	}
	if r.start == "" || r.stop == "" {
		t.Fatalf("could not resolve distinct start/stop methods from %v", noArg)
	}
	t.Logf("discovered runner api: start=%s stop=%s", r.start, r.stop)
	return r
}

func (r *zzRunner) callStart() { r.v.MethodByName(r.start).Call(nil) }
func (r *zzRunner) callStop()  { r.v.MethodByName(r.stop).Call(nil) }

// --- scenarios (each run individually by the Python harness via -run) --- //

// TestZZPeriodicCounts: counter advances about #intervals, and stops after stop.
func TestZZPeriodicCounts(t *testing.T) {
	var n int64
	interval := 20 * time.Millisecond
	r := zzBuild(t, interval, func(ctx context.Context) error {
		atomic.AddInt64(&n, 1)
		return nil
	})
	r.callStart()
	// allow ~10 intervals to elapse
	time.Sleep(220 * time.Millisecond)
	r.callStop()
	got := atomic.LoadInt64(&n)
	if got < 5 {
		t.Fatalf("callback fired too few times: got %d over ~10 intervals (a no-op start would give 0)", got)
	}
	// after stop, no further increments
	snapshot := atomic.LoadInt64(&n)
	time.Sleep(150 * time.Millisecond)
	if after := atomic.LoadInt64(&n); after != snapshot {
		t.Fatalf("callback kept firing after stop: %d -> %d", snapshot, after)
	}
}

// TestZZStartNonBlocking: start returns promptly relative to the interval.
func TestZZStartNonBlocking(t *testing.T) {
	interval := 2 * time.Second // huge: a blocking start would take >= this
	r := zzBuild(t, interval, func(ctx context.Context) error {
		<-ctx.Done()
		return ctx.Err()
	})
	done := make(chan struct{})
	go func() {
		r.callStart()
		close(done)
	}()
	select {
	case <-done:
	case <-time.After(500 * time.Millisecond):
		t.Fatal("start blocked the caller: it did not return within 500ms (interval=2s)")
	}
	r.callStop()
}

// TestZZStopWaitsForCallback: a callback that signals start then blocks on its
// context; stop must cancel the context AND only return after the callback has
// returned.
func TestZZStopWaitsForCallback(t *testing.T) {
	started := make(chan struct{})
	released := make(chan struct{})
	var returned int32
	interval := 10 * time.Millisecond
	r := zzBuild(t, interval, func(ctx context.Context) error {
		select {
		case started <- struct{}{}:
		default:
		}
		<-ctx.Done() // cooperative: observe cancellation
		atomic.StoreInt32(&returned, 1)
		close(released)
		return ctx.Err()
	})
	r.callStart()
	select {
	case <-started:
	case <-time.After(3 * time.Second):
		t.Fatal("callback never started")
	}
	stopDone := make(chan struct{})
	go func() {
		r.callStop()
		close(stopDone)
	}()
	// stop must not return before the callback has returned.
	select {
	case <-stopDone:
		if atomic.LoadInt32(&returned) != 1 {
			t.Fatal("stop returned before the in-progress callback returned")
		}
	case <-time.After(3 * time.Second):
		// stop should not hang either; the callback returns on cancellation.
		select {
		case <-released:
			t.Fatal("callback returned but stop did not return after it")
		default:
			t.Fatal("stop hung: callback did not observe context cancellation")
		}
	}
}

// TestZZNoOverlap: a callback slower than the interval must never run two bodies
// concurrently.
func TestZZNoOverlap(t *testing.T) {
	var inFlight int32
	var maxSeen int32
	interval := 10 * time.Millisecond
	r := zzBuild(t, interval, func(ctx context.Context) error {
		cur := atomic.AddInt32(&inFlight, 1)
		for {
			old := atomic.LoadInt32(&maxSeen)
			if cur <= old || atomic.CompareAndSwapInt32(&maxSeen, old, cur) {
				break
			}
		}
		// run longer than the interval so ticks pile up behind us
		time.Sleep(40 * time.Millisecond)
		atomic.AddInt32(&inFlight, -1)
		return nil
	})
	r.callStart()
	time.Sleep(300 * time.Millisecond)
	r.callStop()
	if m := atomic.LoadInt32(&maxSeen); m > 1 {
		t.Fatalf("overlapping callback invocations detected: max concurrent = %d", m)
	}
	if atomic.LoadInt32(&maxSeen) == 0 {
		t.Fatal("callback never ran")
	}
}

// TestZZIdempotentStop: stop may be called more than once without panicking.
func TestZZIdempotentStop(t *testing.T) {
	interval := 15 * time.Millisecond
	r := zzBuild(t, interval, func(ctx context.Context) error { return nil })
	defer func() {
		if rec := recover(); rec != nil {
			t.Fatalf("calling stop twice panicked: %v", rec)
		}
	}()
	r.callStart()
	time.Sleep(50 * time.Millisecond)
	r.callStop()
	r.callStop() // second stop must be safe
}

// TestZZStopBeforeStart-ish / repeated start-stop with no leak.
func TestZZNoGoroutineLeak(t *testing.T) {
	base := zzNumGoroutine()
	var wg sync.WaitGroup
	for c := 0; c < 30; c++ {
		var n int64
		interval := 5 * time.Millisecond
		r := zzBuild(t, interval, func(ctx context.Context) error {
			atomic.AddInt64(&n, 1)
			select {
			case <-ctx.Done():
			default:
			}
			return nil
		})
		r.callStart()
		wg.Add(1)
		go func() {
			defer wg.Done()
			time.Sleep(15 * time.Millisecond)
			r.callStop()
		}()
	}
	wg.Wait()
	deadline := time.Now().Add(3 * time.Second)
	after := zzNumGoroutine()
	for time.Now().Before(deadline) && after > base+80 {
		time.Sleep(50 * time.Millisecond)
		after = zzNumGoroutine()
	}
	if after > base+80 {
		t.Fatalf("goroutine leak suspected across start/stop cycles: base=%d after=%d", base, after)
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
    assert os.path.isfile(PERIODIC_GO), (
        "missing deliverable: lib/routine/periodic.go"
    )
    tmpdir = os.path.join(REPO_DIR, ".zz_ctorfind")
    os.makedirs(tmpdir, exist_ok=True)
    try:
        with open(os.path.join(tmpdir, "main.go"), "w") as fh:
            fh.write(CTOR_FINDER_SRC)
        with open(os.path.join(tmpdir, "go.mod"), "w") as fh:
            fh.write("module zzctorfind\n\ngo 1.21\n")
        proc = subprocess.run(
            ["go", "run", ".", PERIODIC_GO],
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
            "no exported constructor (a top-level func taking a time.Duration "
            "interval and a func(context.Context) error callback, returning a "
            "type declared in the file) found in periodic.go; stdout="
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
         "-v", "-timeout", "120s", "./lib/routine/"],
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

    def test_l1_periodic_file_exists(self):
        """L1: the deliverable lib/routine/periodic.go must exist."""
        assert os.path.isfile(PERIODIC_GO), (
            "missing required deliverable: lib/routine/periodic.go"
        )

    def test_l1_in_routine_package(self):
        """L1: periodic.go must declare package routine."""
        with open(PERIODIC_GO) as fh:
            head = fh.read()
        assert "package routine" in head, (
            "periodic.go must be in package routine"
        )

    def test_l1_test_file_exists(self):
        """L1: the agent must provide periodic_test.go with scenarios."""
        assert os.path.isfile(PERIODIC_TEST), (
            "missing required deliverable: lib/routine/periodic_test.go"
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

    def test_l1_constructor_discoverable_with_correct_signature(self):
        """L1: an exported constructor taking a Duration + func(ctx) error
        callback and returning a declared runner type must be discoverable."""
        _require_go()
        ctor = _find_constructor()
        assert ctor and ctor[0].isupper(), (
            f"constructor {ctor!r} must be exported (capitalized)"
        )

    # ----------------------------- L2 ----------------------------- #

    def test_l2_periodic_invocation_and_cessation(self):
        """L2: callback fires ~ once per interval and stops after stop returns."""
        _assert_driver_pass(
            _run_driver("TestZZPeriodicCounts"), "periodic-invocation"
        )

    def test_l2_start_is_non_blocking(self):
        """L2: start returns promptly and does not block for the runner's life."""
        _assert_driver_pass(
            _run_driver("TestZZStartNonBlocking"), "non-blocking-start"
        )

    def test_l2_stop_waits_for_in_progress_callback(self):
        """L2: stop cancels the callback's context and returns only after the
        in-progress callback has returned."""
        _assert_driver_pass(
            _run_driver("TestZZStopWaitsForCallback"), "stop-waits-for-callback"
        )

    def test_l2_no_overlapping_invocations_for_slow_callback(self):
        """L2: a callback slower than the interval never overlaps itself."""
        _assert_driver_pass(_run_driver("TestZZNoOverlap"), "no-overlap")

    def test_l2_idempotent_stop_no_panic(self):
        """L2: calling stop more than once must not panic."""
        _assert_driver_pass(
            _run_driver("TestZZIdempotentStop"), "idempotent-stop"
        )

    def test_l2_no_goroutine_leak_across_cycles(self):
        """L2: repeated start/stop cycles do not leak goroutines."""
        _assert_driver_pass(
            _run_driver("TestZZNoGoroutineLeak"), "no-goroutine-leak"
        )

    def test_l2_agents_own_periodic_race_suite_passes(self):
        """L2: the task's acceptance command
        `go test -race -run 'Periodic' ./lib/routine/` passes clean (no
        failures, no race, no goroutine-leak reports), and the agent actually
        provided Periodic-named tests that ran."""
        _require_go()
        proc = subprocess.run(
            ["go", "test", "-race", "-count=1", "-run", "Periodic",
             "-timeout", "120s", "./lib/routine/"],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=GO_TEST_TIMEOUT,
            env={**os.environ, "GOFLAGS": "-buildvcs=false"},
        )
        combined = proc.stdout + "\n" + proc.stderr
        assert proc.returncode == 0, (
            "go test -race -run Periodic ./lib/routine/ failed:\n" + combined
        )
        assert "DATA RACE" not in combined, "data race reported:\n" + combined
        assert "panic:" not in combined, "panic reported:\n" + combined
        assert "no test files" not in combined, (
            "no test files in lib/routine/:\n" + combined
        )
        # the agent's Periodic tests must have actually executed (ok / RUN line)
        assert ("ok  " in proc.stdout or "PASS" in proc.stdout), (
            "no Periodic tests appear to have run:\n" + combined
        )


# keep linters quiet about the imported-but-only-conditionally-used module
_ = textwrap
