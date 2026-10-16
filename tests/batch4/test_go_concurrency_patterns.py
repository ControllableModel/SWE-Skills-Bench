"""Benchmark test for skill: go-concurrency-patterns (variant ext4).

Task: Add a *context-aware single-flight barrier* to consul's ``lib/semaphore``
package (new file ``lib/semaphore/singleflight.go`` in package ``semaphore``).
The exported single-flight type, its constructor, and its call-method names are
chosen by the agent, so this test does NOT hard-code them. Instead it:

  * uses a tiny Go AST program to discover the exported single-flight type and
    its constructor (a top-level exported func returning that type / pointer),
  * generates an independent Go *reflection driver* test that classifies the
    call operation by signature -- the method that accepts a ``context.Context``,
    a ``string`` key, and a work function, and returns ``(value, error)`` -- so
    the agent's chosen names do not matter,
  * compiles and runs that driver under ``go test -race`` to deep-validate the
    documented behaviors:

      - exactly-once execution with a shared result under 50 concurrent
        same-key callers (a naive "just call fn every time" impl fails this);
      - per-key independence (two different keys both execute concurrently);
      - per-waiter context cancellation (one waiter's cancelled ctx returns its
        ctx error while the remaining waiters still get the shared result, and
        the in-flight work is NOT abandoned);
      - re-execution after the in-flight window completes (results are not
        cached beyond the in-flight window);

    plus a goroutine-leak check and the package's ``go build`` / agent-supplied
    ``SingleFlight`` race suite.

A naive / stub / files-that-merely-look-related solution fails because each
behavior is exercised independently with this test's own assertions, driven
through reflection, not by trusting the agent's own ``singleflight_test.go``.

Native acceptance command (from the doc):
    go test -race -run 'SingleFlight' ./lib/semaphore/
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
SINGLEFLIGHT_GO = os.path.join(SEM_DIR, "singleflight.go")
SINGLEFLIGHT_TEST_GO = os.path.join(SEM_DIR, "singleflight_test.go")

# Helper Go files dropped into the package while testing. Names are unique
# enough to never collide with agent code and are cleaned up afterwards.
DRIVER_TEST = os.path.join(SEM_DIR, "zz_sf_driver_test.go")

GO_BUILD_TIMEOUT = 300
GO_TEST_TIMEOUT = 600


# --------------------------------------------------------------------------- #
# Embedded Go: AST type/constructor finder.
#
# Prints "<CtorName>\t<TypeName>" for each exported, top-level function that
# returns (as its single result) an exported struct type declared in the same
# file (directly or via *T). This discovers the single-flight type together
# with its constructor without hard-coding names. The reflection driver later
# resolves the actual call method by signature.
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
	case *ast.IndexExpr:
		return texpr(t.X)
	case *ast.IndexListExpr:
		return texpr(t.X)
	case *ast.SelectorExpr:
		return t.Sel.Name
	}
	return ""
}

func isExported(s string) bool {
	return s != "" && s[0] >= 'A' && s[0] <= 'Z'
}

func main() {
	fs := token.NewFileSet()
	f, err := parser.ParseFile(fs, os.Args[1], nil, 0)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(2)
	}
	// Collect exported struct type names declared in this file.
	structs := map[string]bool{}
	for _, d := range f.Decls {
		if gd, ok := d.(*ast.GenDecl); ok {
			for _, s := range gd.Specs {
				if ts, ok := s.(*ast.TypeSpec); ok && isExported(ts.Name.Name) {
					if _, isStruct := ts.Type.(*ast.StructType); isStruct {
						structs[ts.Name.Name] = true
					}
				}
			}
		}
	}
	// Find exported, top-level funcs whose single result is one of those types.
	for _, d := range f.Decls {
		if fn, ok := d.(*ast.FuncDecl); ok && fn.Recv == nil && fn.Name.IsExported() {
			if fn.Type.Results == nil || len(fn.Type.Results.List) != 1 {
				continue
			}
			name := texpr(fn.Type.Results.List[0].Type)
			if structs[name] {
				fmt.Printf("%s\t%s\n", fn.Name.Name, name)
			}
		}
	}
}
'''


# --------------------------------------------------------------------------- #
# Embedded Go: the reflection driver test. ``__CTOR__`` is substituted with the
# discovered constructor name. The single call operation is discovered at
# runtime by signature, so the agent's chosen method name does not matter.
#
# Call-op classification: a method on the single-flight value (or its pointer)
# whose inputs include a context.Context, a string, and exactly one func-typed
# argument, and whose results include an error (and at least one other value).
# The work func is constructed dynamically to match the discovered func type:
# it takes a context.Context (if present) and returns (interface{} value, nil
# error) typed to the discovered result types.
# --------------------------------------------------------------------------- #
DRIVER_TEST_SRC = r'''
package semaphore

import (
	"context"
	"errors"
	"reflect"
	"runtime"
	"sync"
	"sync/atomic"
	"testing"
	"time"
)

var zzCtxType = reflect.TypeOf((*context.Context)(nil)).Elem()
var zzErrType = reflect.TypeOf((*error)(nil)).Elem()
var zzStrType = reflect.TypeOf("")

func zzNumGoroutine() int { return runtime.NumGoroutine() }

type zzCallOp struct {
	recv     reflect.Value // the single-flight value (or ptr)
	method   reflect.Method
	ctxIdx   int           // input index of context.Context, or -1
	keyIdx   int           // input index of the string key
	fnIdx    int           // input index of the func argument
	fnType   reflect.Type  // type of the func argument
	valIdx   int           // result index of the (non-error) value
	errIdx   int           // result index of the error
	ninExtra int           // number of inputs besides receiver
}

func zzNew(t *testing.T) reflect.Value {
	t.Helper()
	v := reflect.ValueOf(__CTOR__())
	if !v.IsValid() {
		t.Fatalf("constructor returned an invalid value")
	}
	return v
}

// zzFindCall classifies the call operation by signature on the receiver and
// (if the receiver is addressable-as-pointer) on its pointer type.
func zzFindCall(t *testing.T, recv reflect.Value) *zzCallOp {
	t.Helper()
	candidates := []reflect.Value{recv}
	if recv.Kind() != reflect.Ptr && recv.CanAddr() {
		candidates = append(candidates, recv.Addr())
	}
	// Also try a pointer to a fresh copy if the ctor returned a value type.
	if recv.Kind() != reflect.Ptr {
		p := reflect.New(recv.Type())
		p.Elem().Set(recv)
		candidates = append(candidates, p)
	}
	for _, rv := range candidates {
		rt := rv.Type()
		for i := 0; i < rt.NumMethod(); i++ {
			m := rt.Method(i)
			if !m.IsExported() {
				continue
			}
			mt := m.Func.Type()
			nin := mt.NumIn() - 1 // minus receiver
			ctxIdx, keyIdx, fnIdx := -1, -1, -1
			var fnType reflect.Type
			for j := 1; j <= nin; j++ {
				in := mt.In(j)
				switch {
				case in == zzCtxType && ctxIdx < 0:
					ctxIdx = j
				case in.Kind() == reflect.String && keyIdx < 0:
					keyIdx = j
				case in.Kind() == reflect.Func && fnIdx < 0:
					fnIdx = j
					fnType = in
				}
			}
			if keyIdx < 0 || fnIdx < 0 {
				continue
			}
			// results: must include an error and at least one other value.
			errIdx, valIdx := -1, -1
			for k := 0; k < mt.NumOut(); k++ {
				out := mt.Out(k)
				if out == zzErrType && errIdx < 0 {
					errIdx = k
				} else if valIdx < 0 {
					valIdx = k
				}
			}
			if errIdx < 0 || valIdx < 0 {
				continue
			}
			// The work func must itself return at least (value, error)-ish.
			if fnType.NumOut() < 1 {
				continue
			}
			return &zzCallOp{
				recv: rv, method: m, ctxIdx: ctxIdx, keyIdx: keyIdx,
				fnIdx: fnIdx, fnType: fnType, valIdx: valIdx, errIdx: errIdx,
				ninExtra: nin,
			}
		}
	}
	t.Fatalf("no single-flight call method found (need a method taking a "+
		"context, a string key, and a func arg, returning a value and an "+
		"error) on type %s", recv.Type())
	return nil
}

// zzMakeWork builds a reflect.Value matching op.fnType. ``produce`` returns the
// interface{} value the work should yield; the returned func also bumps the
// shared call counter and invokes ``onCall`` (used to coordinate the in-flight
// window). It honors a context argument if the func type has one.
func (op *zzCallOp) zzMakeWork(produce func() interface{}, onCall func(ctx context.Context)) reflect.Value {
	ft := op.fnType
	// locate a context arg in the work func, if any.
	workCtxIdx := -1
	for i := 0; i < ft.NumIn(); i++ {
		if ft.In(i) == zzCtxType {
			workCtxIdx = i
		}
	}
	return reflect.MakeFunc(ft, func(args []reflect.Value) []reflect.Value {
		var ctx context.Context = context.Background()
		if workCtxIdx >= 0 && args[workCtxIdx].IsValid() && !args[workCtxIdx].IsNil() {
			ctx = args[workCtxIdx].Interface().(context.Context)
		}
		onCall(ctx)
		out := make([]reflect.Value, ft.NumOut())
		val := produce()
		for i := 0; i < ft.NumOut(); i++ {
			ot := ft.Out(i)
			if ot == zzErrType {
				out[i] = reflect.Zero(ot)
			} else {
				rv := reflect.ValueOf(val)
				if rv.IsValid() && rv.Type().AssignableTo(ot) {
					out[i] = rv
				} else if rv.IsValid() && rv.Type().ConvertibleTo(ot) {
					out[i] = rv.Convert(ot)
				} else {
					out[i] = reflect.Zero(ot)
				}
			}
		}
		return out
	})
}

// zzCall invokes the discovered call op with the supplied ctx, key, and work
// func value. Returns (valueInterface, errorInterface).
func (op *zzCallOp) zzCall(ctx context.Context, key string, work reflect.Value) (interface{}, error) {
	args := make([]reflect.Value, op.ninExtra+1)
	args[0] = op.recv
	for j := 1; j <= op.ninExtra; j++ {
		switch j {
		case op.ctxIdx:
			args[j] = reflect.ValueOf(ctx)
		case op.keyIdx:
			args[j] = reflect.ValueOf(key).Convert(op.method.Func.Type().In(j))
		case op.fnIdx:
			args[j] = work
		default:
			args[j] = reflect.Zero(op.method.Func.Type().In(j))
		}
	}
	res := op.method.Func.Call(args)
	var err error
	if e := res[op.errIdx]; !e.IsNil() {
		err = e.Interface().(error)
	}
	var val interface{}
	if v := res[op.valIdx]; v.IsValid() && v.CanInterface() {
		val = v.Interface()
	}
	return val, err
}

func zzToInt(v interface{}) (int, bool) {
	rv := reflect.ValueOf(v)
	if !rv.IsValid() {
		return 0, false
	}
	switch rv.Kind() {
	case reflect.Int, reflect.Int8, reflect.Int16, reflect.Int32, reflect.Int64:
		return int(rv.Int()), true
	case reflect.Uint, reflect.Uint8, reflect.Uint16, reflect.Uint32, reflect.Uint64:
		return int(rv.Uint()), true
	}
	return 0, false
}

// --- scenario tests (run individually by the Python harness via -run) --- //

// TestZZExactlyOnceSharedResult: 50 goroutines call with the same key while the
// work blocks on a signal; after release, fn must have run exactly once and all
// 50 callers must observe the same returned value.
func TestZZExactlyOnceSharedResult(t *testing.T) {
	recv := zzNew(t)
	op := zzFindCall(t, recv)

	const N = 50
	var calls int32
	gate := make(chan struct{})   // released to unblock the in-flight work
	entered := make(chan struct{}, 1)
	produce := func() interface{} { return 12345 }
	work := op.zzMakeWork(produce, func(ctx context.Context) {
		atomic.AddInt32(&calls, 1)
		select {
		case entered <- struct{}{}:
		default:
		}
		<-gate // hold the in-flight window open
	})

	results := make([]int, N)
	okFlags := make([]bool, N)
	var wg sync.WaitGroup
	for i := 0; i < N; i++ {
		wg.Add(1)
		go func(idx int) {
			defer wg.Done()
			v, err := op.zzCall(context.Background(), "same-key", work)
			if err != nil {
				return
			}
			if iv, ok := zzToInt(v); ok {
				results[idx] = iv
				okFlags[idx] = true
			}
		}(i)
	}

	// wait until at least one call has entered the work, then give the rest a
	// moment to coalesce, then release.
	select {
	case <-entered:
	case <-time.After(5 * time.Second):
		close(gate)
		t.Fatal("work never entered; call op did not invoke fn")
	}
	// busy-wait a brief deterministic window for coalescing (no time.Sleep on
	// the critical correctness path -- this is just scheduling slack).
	deadline := time.Now().Add(500 * time.Millisecond)
	for time.Now().Before(deadline) {
		runtime.Gosched()
	}
	close(gate)
	wg.Wait()

	if got := atomic.LoadInt32(&calls); got != 1 {
		t.Fatalf("exactly-once violated: fn ran %d times for one in-flight key (want 1)", got)
	}
	delivered := 0
	for i := 0; i < N; i++ {
		if okFlags[i] {
			delivered++
			if results[i] != 12345 {
				t.Fatalf("caller %d got shared value %d, want 12345", i, results[i])
			}
		}
	}
	if delivered != N {
		t.Fatalf("not all callers shared the result: %d/%d delivered", delivered, N)
	}
}

// TestZZPerKeyIndependence: two different keys called concurrently must both
// execute (dedup is per-key, not global). Each is held until BOTH have entered.
func TestZZPerKeyIndependence(t *testing.T) {
	recv := zzNew(t)
	op := zzFindCall(t, recv)

	var bothIn sync.WaitGroup
	bothIn.Add(2)
	release := make(chan struct{})
	var calls int32

	mkWork := func(val int) reflect.Value {
		var once sync.Once
		return op.zzMakeWork(func() interface{} { return val }, func(ctx context.Context) {
			atomic.AddInt32(&calls, 1)
			once.Do(func() { bothIn.Done() })
			<-release
		})
	}
	workA := mkWork(11)
	workB := mkWork(22)

	type res struct {
		v   int
		ok  bool
	}
	chA := make(chan res, 1)
	chB := make(chan res, 1)
	go func() {
		v, err := op.zzCall(context.Background(), "key-A", workA)
		iv, _ := zzToInt(v)
		chA <- res{iv, err == nil}
	}()
	go func() {
		v, err := op.zzCall(context.Background(), "key-B", workB)
		iv, _ := zzToInt(v)
		chB <- res{iv, err == nil}
	}()

	done := make(chan struct{})
	go func() { bothIn.Wait(); close(done) }()
	select {
	case <-done: // both keys are in flight concurrently -> independence holds
	case <-time.After(5 * time.Second):
		close(release)
		t.Fatal("two different keys did not run concurrently (global dedup?)")
	}
	close(release)

	a := <-chA
	b := <-chB
	if !a.ok || a.v != 11 {
		t.Fatalf("key-A result wrong: v=%d ok=%v", a.v, a.ok)
	}
	if !b.ok || b.v != 22 {
		t.Fatalf("key-B result wrong: v=%d ok=%v", b.v, b.ok)
	}
	if c := atomic.LoadInt32(&calls); c != 2 {
		t.Fatalf("want exactly 2 executions across the two keys, got %d", c)
	}
}

// TestZZWaiterCancelOthersGetResult: with several same-key callers, one waiter
// cancels its own context before the result is ready. That waiter must return
// its context error; the in-flight work must NOT be abandoned; the remaining
// waiters must still receive the shared result.
func TestZZWaiterCancelOthersGetResult(t *testing.T) {
	recv := zzNew(t)
	op := zzFindCall(t, recv)
	if op.ctxIdx < 0 {
		t.Fatalf("call op has no context.Context parameter (required for per-waiter cancellation)")
	}

	gate := make(chan struct{})
	entered := make(chan struct{}, 1)
	var calls int32
	work := op.zzMakeWork(func() interface{} { return 777 }, func(ctx context.Context) {
		atomic.AddInt32(&calls, 1)
		select {
		case entered <- struct{}{}:
		default:
		}
		<-gate
	})

	// One "leader" with background ctx keeps the work alive.
	type res struct {
		v   int
		err error
	}
	leaderCh := make(chan res, 1)
	go func() {
		v, err := op.zzCall(context.Background(), "k", work)
		iv, _ := zzToInt(v)
		leaderCh <- res{iv, err}
	}()

	// Wait for the work to actually start.
	select {
	case <-entered:
	case <-time.After(5 * time.Second):
		close(gate)
		t.Fatal("work never started")
	}

	// A waiter that joins the same in-flight call and then cancels.
	ctx, cancel := context.WithCancel(context.Background())
	waiterCh := make(chan res, 1)
	go func() {
		v, err := op.zzCall(ctx, "k", work)
		iv, _ := zzToInt(v)
		waiterCh <- res{iv, err}
	}()
	// give the waiter a moment to enqueue, then cancel it.
	deadline := time.Now().Add(300 * time.Millisecond)
	for time.Now().Before(deadline) {
		runtime.Gosched()
	}
	cancel()

	select {
	case r := <-waiterCh:
		if r.err == nil {
			t.Fatalf("cancelled waiter must return a non-nil (context) error, got value %d", r.v)
		}
		if !errors.Is(r.err, context.Canceled) {
			t.Fatalf("cancelled waiter should return context.Canceled, got %v", r.err)
		}
	case <-time.After(5 * time.Second):
		close(gate)
		t.Fatal("cancelled waiter did not return promptly")
	}

	// The in-flight work must still be alive -> release it now.
	close(gate)
	select {
	case r := <-leaderCh:
		if r.err != nil {
			t.Fatalf("leader (uncancelled) should succeed, got err %v", r.err)
		}
		if r.v != 777 {
			t.Fatalf("leader should get shared value 777, got %d", r.v)
		}
	case <-time.After(5 * time.Second):
		t.Fatal("leader never completed; in-flight work was abandoned on waiter cancel")
	}
	if c := atomic.LoadInt32(&calls); c != 1 {
		t.Fatalf("work should have run exactly once despite a cancel, ran %d", c)
	}
}

// TestZZReExecAfterComplete: call a key, let it complete, then call the same
// key again -> the work runs a second time (no caching beyond in-flight).
func TestZZReExecAfterComplete(t *testing.T) {
	recv := zzNew(t)
	op := zzFindCall(t, recv)

	var calls int32
	produce := func() interface{} { return int(atomic.LoadInt32(&calls)) }
	work := op.zzMakeWork(produce, func(ctx context.Context) {
		atomic.AddInt32(&calls, 1)
	})

	_, err1 := op.zzCall(context.Background(), "rk", work)
	if err1 != nil {
		t.Fatalf("first call errored: %v", err1)
	}
	_, err2 := op.zzCall(context.Background(), "rk", work)
	if err2 != nil {
		t.Fatalf("second call errored: %v", err2)
	}
	if c := atomic.LoadInt32(&calls); c != 2 {
		t.Fatalf("sequential same-key calls must each execute; ran %d (want 2)", c)
	}
}

// TestZZNoGoroutineLeak: many create/use cycles across many keys must not leak
// goroutines once all calls have returned.
func TestZZNoGoroutineLeak(t *testing.T) {
	recv := zzNew(t)
	op := zzFindCall(t, recv)

	base := zzNumGoroutine()
	for c := 0; c < 200; c++ {
		var wg sync.WaitGroup
		work := op.zzMakeWork(func() interface{} { return c }, func(ctx context.Context) {})
		for i := 0; i < 8; i++ {
			wg.Add(1)
			key := "leak-key"
			if i%2 == 0 {
				key = "leak-key2"
			}
			go func(k string) {
				defer wg.Done()
				op.zzCall(context.Background(), k, work)
			}(key)
		}
		wg.Wait()
	}
	deadline := time.Now().Add(3 * time.Second)
	after := zzNumGoroutine()
	for time.Now().Before(deadline) && after > base+50 {
		runtime.Gosched()
		after = zzNumGoroutine()
	}
	if after > base+50 {
		t.Fatalf("goroutine leak suspected: base=%d after=%d", base, after)
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
    assert os.path.isfile(SINGLEFLIGHT_GO), (
        "missing deliverable: lib/semaphore/singleflight.go"
    )
    tmpdir = os.path.join(REPO_DIR, ".zz_sf_ctorfind")
    os.makedirs(tmpdir, exist_ok=True)
    try:
        with open(os.path.join(tmpdir, "main.go"), "w") as fh:
            fh.write(CTOR_FINDER_SRC)
        with open(os.path.join(tmpdir, "go.mod"), "w") as fh:
            fh.write("module zzsfctorfind\n\ngo 1.21\n")
        proc = subprocess.run(
            ["go", "run", ".", SINGLEFLIGHT_GO],
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
            "no exported single-flight constructor (a top-level exported func "
            "returning an exported struct type declared in singleflight.go) "
            f"found; stdout={proc.stdout!r}"
        )
        ctor = lines[0].split("\t", 1)[0]
        return ctor
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _install_driver(ctor):
    src = DRIVER_TEST_SRC.replace("__CTOR__", ctor)
    with open(DRIVER_TEST, "w") as fh:
        fh.write(src)


def _cleanup_driver():
    try:
        os.remove(DRIVER_TEST)
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
    assert "--- PASS" in proc.stdout or "PASS" in proc.stdout, (
        f"{scenario}: no PASS marker in output:\n{combined}"
    )
    assert "panic:" not in combined, f"{scenario}: panic in output:\n{combined}"
    assert "DATA RACE" not in combined, f"{scenario}: data race detected:\n{combined}"


class TestGoConcurrencyPatterns:
    REPO_DIR = _find_repo_dir("/workspace/consul")

    # ----------------------------- L1 ----------------------------- #

    def test_l1_singleflight_file_exists(self):
        """L1: the deliverable lib/semaphore/singleflight.go must exist."""
        assert os.path.isfile(SINGLEFLIGHT_GO), (
            "missing required deliverable: lib/semaphore/singleflight.go"
        )

    def test_l1_in_semaphore_package(self):
        """L1: singleflight.go must declare package semaphore."""
        with open(SINGLEFLIGHT_GO) as fh:
            head = fh.read()
        assert "package semaphore" in head, (
            "singleflight.go must be in package semaphore"
        )

    def test_l1_test_file_exists(self):
        """L1: the agent must provide singleflight_test.go with scenarios."""
        assert os.path.isfile(SINGLEFLIGHT_TEST_GO), (
            "missing required deliverable: lib/semaphore/singleflight_test.go"
        )

    def test_l1_no_time_sleep_coordination_in_tests(self):
        """L1: the agent's tests must coordinate the in-flight window with
        synchronization primitives, not time.Sleep (per the doc)."""
        with open(SINGLEFLIGHT_TEST_GO) as fh:
            content = fh.read()
        assert "time.Sleep" not in content, (
            "singleflight_test.go must not use time.Sleep to coordinate the "
            "in-flight window; use channels/WaitGroup/sync primitives instead"
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
        """L1: an exported single-flight constructor must be discoverable."""
        _require_go()
        ctor = _find_constructor()
        assert ctor and ctor[0].isupper(), (
            f"constructor {ctor!r} must be exported (capitalized)"
        )

    # ----------------------------- L2 ----------------------------- #

    def test_l2_exactly_once_shared_result(self):
        """L2: 50 same-key callers -> fn runs exactly once, all share result."""
        _assert_driver_pass(
            _run_driver("TestZZExactlyOnceSharedResult"), "exactly-once-shared"
        )

    def test_l2_per_key_independence(self):
        """L2: two different keys both execute concurrently (per-key dedup)."""
        _assert_driver_pass(
            _run_driver("TestZZPerKeyIndependence"), "per-key-independence"
        )

    def test_l2_waiter_cancel_others_still_get_result(self):
        """L2: one waiter's cancelled ctx returns its ctx error; the in-flight
        work survives and the remaining waiter gets the shared result."""
        _assert_driver_pass(
            _run_driver("TestZZWaiterCancelOthersGetResult"),
            "waiter-cancel-shared",
        )

    def test_l2_reexec_after_complete(self):
        """L2: same key called again after completion re-executes the work."""
        _assert_driver_pass(
            _run_driver("TestZZReExecAfterComplete"), "reexec-after-complete"
        )

    def test_l2_no_goroutine_leak(self):
        """L2: many create/use cycles across keys do not leak goroutines."""
        _assert_driver_pass(
            _run_driver("TestZZNoGoroutineLeak"), "no-goroutine-leak"
        )

    def test_l2_native_singleflight_race_suite_passes(self):
        """L2: the native acceptance command
        `go test -race -run 'SingleFlight' ./lib/semaphore/` passes clean
        (no failures, no race, no goroutine-leak reports), and actual
        SingleFlight-named tests ran."""
        _require_go()
        proc = subprocess.run(
            ["go", "test", "-race", "-count=1", "-run", "SingleFlight",
             "-v", "./lib/semaphore/"],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=GO_TEST_TIMEOUT,
            env={**os.environ, "GOFLAGS": "-buildvcs=false"},
        )
        combined = proc.stdout + "\n" + proc.stderr
        assert proc.returncode == 0, (
            "go test -race -run 'SingleFlight' ./lib/semaphore/ failed:\n"
            + combined
        )
        assert "DATA RACE" not in combined, "data race reported:\n" + combined
        assert "panic:" not in combined, "panic reported:\n" + combined
        assert "no test files" not in combined, (
            "no test files in lib/semaphore/:\n" + combined
        )
        # at least one SingleFlight-named test must have actually run & passed.
        assert "--- PASS" in proc.stdout, (
            "no SingleFlight tests appear to have run/passed:\n" + combined
        )


# keep linters quiet about the imported helper module
_ = textwrap
