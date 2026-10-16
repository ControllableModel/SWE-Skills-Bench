"""Benchmark test for skill: go-concurrency-patterns (variant ext5).

Task: Add a fan-in channel merger to consul's ``lib/channels`` package
(new file ``lib/channels/merge.go`` in package ``channels``). The merger is an
exported *generic* function that takes a ``context.Context`` plus a variadic set
of receive-only input channels ``<-chan T`` and returns a single receive-only
output channel ``<-chan T`` carrying every value sent on any input.

The exact function name is chosen by the agent, so this test does NOT hard-code
it. Instead it:

  * uses a tiny Go AST program to discover the exported generic top-level
    function whose signature is (context, variadic chan) -> chan, and
  * generates an independent Go *reflection driver* test that calls the
    discovered function by reflection and deep-validates the documented
    behaviors under ``go test -race``:
      - every value forwarded exactly once across multiple inputs,
      - per-input relative order preserved,
      - output closes after all inputs close (range terminates),
      - output closes promptly on context cancellation even with non-closing
        inputs,
      - the zero-input case closes immediately,
      - no goroutine leak across repeated create/use cycles.

A naive / stub / files-that-merely-look-related solution fails because the
behavior is exercised independently with this test's own assertions and its own
input channels, NOT by trusting the agent's own ``merge_test.go``. A merger that
drops values, never closes, leaks goroutines, ignores the context, or hangs on
zero inputs is caught by a distinct scenario.
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
CHANNELS_DIR = os.path.join(REPO_DIR, "lib", "channels")
MERGE_GO = os.path.join(CHANNELS_DIR, "merge.go")
MERGE_TEST_GO = os.path.join(CHANNELS_DIR, "merge_test.go")

# Helper Go files dropped into the package while testing. Unique names that will
# not collide with agent code; cleaned up after the module finishes.
DRIVER_TEST = os.path.join(CHANNELS_DIR, "zz_merge_driver_test.go")
DRIVER_HELP = os.path.join(CHANNELS_DIR, "zz_merge_helper_test.go")

GO_BUILD_TIMEOUT = 300
GO_TEST_TIMEOUT = 420


# --------------------------------------------------------------------------- #
# Embedded Go: AST finder for the merge function.
# Prints "<FuncName>" for each exported, top-level, NON-method function whose
# signature looks like (context.Context, ...<-chan T) -> <-chan T, i.e.:
#   * has type parameters (generic),
#   * has a variadic final parameter that is a channel type,
#   * returns exactly one result that is a channel type.
# The first such function is used.
# --------------------------------------------------------------------------- #
FUNC_FINDER_SRC = r'''
package main

import (
	"fmt"
	"go/ast"
	"go/parser"
	"go/token"
	"os"
)

// isChan reports whether an expression denotes a channel type (chan T,
// <-chan T, or chan<- T).
func isChan(e ast.Expr) bool {
	_, ok := e.(*ast.ChanType)
	return ok
}

func main() {
	fs := token.NewFileSet()
	f, err := parser.ParseFile(fs, os.Args[1], nil, 0)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(2)
	}
	for _, d := range f.Decls {
		fn, ok := d.(*ast.FuncDecl)
		if !ok || fn.Recv != nil || !fn.Name.IsExported() {
			continue
		}
		// generic (has type parameters)
		if fn.Type.TypeParams == nil || len(fn.Type.TypeParams.List) == 0 {
			continue
		}
		if fn.Type.Params == nil || len(fn.Type.Params.List) == 0 {
			continue
		}
		// exactly one result, a channel type
		if fn.Type.Results == nil || len(fn.Type.Results.List) != 1 {
			continue
		}
		if !isChan(fn.Type.Results.List[0].Type) {
			continue
		}
		// final parameter must be variadic (Ellipsis) of channel type
		last := fn.Type.Params.List[len(fn.Type.Params.List)-1]
		ell, ok := last.Type.(*ast.Ellipsis)
		if !ok {
			continue
		}
		if !isChan(ell.Elt) {
			continue
		}
		fmt.Printf("%s\n", fn.Name.Name)
	}
}
'''


# --------------------------------------------------------------------------- #
# Embedded Go: helper exposing the runtime goroutine count to the test package.
# --------------------------------------------------------------------------- #
DRIVER_HELPER_SRC = r'''
package channels

import "runtime"

func zzMergeNumGoroutine() int { return runtime.NumGoroutine() }
'''


# --------------------------------------------------------------------------- #
# Embedded Go: the reflection driver test. ``__FUNC__`` is substituted with the
# discovered merge function name (instantiated with int via reflection).
#
# The merge function is called by reflection so that the agent's choice of name
# / param order (beyond the documented contract) does not matter. We build:
#   * a context (and cancel), and
#   * N input channels of type ``chan int`` passed as the variadic tail.
# The output channel is drained with a typed reflect.Select.
# --------------------------------------------------------------------------- #
DRIVER_TEST_SRC = r'''
package channels

import (
	"context"
	"reflect"
	"sort"
	"sync"
	"testing"
	"time"
)

var zzMergeFn = reflect.ValueOf(__FUNC__[int])
var zzCtxType = reflect.TypeOf((*context.Context)(nil)).Elem()

// zzInElemType returns the element type the variadic input channels must have
// (the element type of the last, variadic, parameter's channel). We require it
// to be ``int`` for our int instantiation.
func zzInElemType(t *testing.T) reflect.Type {
	ft := zzMergeFn.Type()
	if ft.NumIn() < 1 {
		t.Fatalf("merge function takes no parameters; want (context, ...<-chan T)")
	}
	if !ft.IsVariadic() {
		t.Fatalf("merge function is not variadic; want (context, ...<-chan T)")
	}
	// last param is a slice-of-chan for a variadic chan param.
	lastSlice := ft.In(ft.NumIn() - 1)
	if lastSlice.Kind() != reflect.Slice || lastSlice.Elem().Kind() != reflect.Chan {
		t.Fatalf("variadic param is not ...chan; got %s", lastSlice)
	}
	return lastSlice.Elem().Elem()
}

// zzCtxArgIndex returns the index of the context.Context parameter, or -1.
func zzCtxArgIndex() int {
	ft := zzMergeFn.Type()
	for i := 0; i < ft.NumIn(); i++ {
		if ft.In(i) == zzCtxType {
			return i
		}
	}
	return -1
}

// zzCall invokes the merge function with the given context and the given input
// channels (each a chan int created by the caller). Returns the output channel
// reflect.Value (a recv-capable chan).
func zzCall(t *testing.T, ctx context.Context, inputs []reflect.Value) reflect.Value {
	t.Helper()
	ft := zzMergeFn.Type()
	ctxIdx := zzCtxArgIndex()
	if ctxIdx < 0 {
		t.Fatalf("merge function has no context.Context parameter")
	}
	// Fixed (non-variadic) leading args. We only support the documented shape:
	// a single context parameter followed by the variadic channel tail.
	fixed := ft.NumIn() - 1 // number of non-variadic params
	args := make([]reflect.Value, 0, fixed+len(inputs))
	for i := 0; i < fixed; i++ {
		if i == ctxIdx {
			args = append(args, reflect.ValueOf(ctx))
		} else {
			t.Fatalf("unexpected non-context fixed parameter at index %d (%s)", i, ft.In(i))
		}
	}
	// Convert each caller chan to the function's expected input chan type
	// (e.g. chan int -> <-chan int) so reflection Call accepts it.
	wantElem := ft.In(ft.NumIn() - 1).Elem() // <-chan int
	for _, in := range inputs {
		args = append(args, in.Convert(wantElem))
	}
	out := zzMergeFn.Call(args)
	if len(out) != 1 {
		t.Fatalf("merge returned %d values; want exactly 1 (the output channel)", len(out))
	}
	if out[0].Kind() != reflect.Chan {
		t.Fatalf("merge result kind is %s; want a channel", out[0].Kind())
	}
	return out[0]
}

// zzMakeIntChan makes a buffered chan int with the given capacity, typed so it
// can be converted to the function's input element type.
func zzMakeIntChan(cap int) reflect.Value {
	return reflect.MakeChan(reflect.ChanOf(reflect.BothDir, reflect.TypeOf(int(0))), cap)
}

// zzDrain reads all values from the output channel until it is closed or the
// deadline elapses. Returns the collected ints and whether the channel closed.
func zzDrain(out reflect.Value, deadline time.Duration) ([]int, bool) {
	got := []int{}
	timer := time.NewTimer(deadline)
	defer timer.Stop()
	timerCase := reflect.SelectCase{Dir: reflect.SelectRecv, Chan: reflect.ValueOf(timer.C)}
	recvCase := reflect.SelectCase{Dir: reflect.SelectRecv, Chan: out}
	for {
		chosen, v, ok := reflect.Select([]reflect.SelectCase{recvCase, timerCase})
		if chosen == 1 {
			return got, false // timed out: channel never closed
		}
		if !ok {
			return got, true // channel closed cleanly
		}
		got = append(got, int(v.Int()))
	}
}

func zzInElemCheck(t *testing.T) {
	if et := zzInElemType(t); et.Kind() != reflect.Int {
		t.Fatalf("instantiated input element type is %s; want int", et)
	}
}

// --- scenario tests (run individually by the Python harness via -run) --- //

// TestZZMergeAllValuesOnce: three inputs each carrying distinct values; after
// all close, the output yields every value exactly once and then closes.
func TestZZMergeAllValuesOnce(t *testing.T) {
	zzInElemCheck(t)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	const perInput = 200
	c1 := zzMakeIntChan(0)
	c2 := zzMakeIntChan(0)
	c3 := zzMakeIntChan(0)
	out := zzCall(t, ctx, []reflect.Value{c1, c2, c3})

	// Each input owns a disjoint value range so we can verify "exactly once".
	feed := func(ch reflect.Value, base int) {
		for i := 0; i < perInput; i++ {
			ch.Send(reflect.ValueOf(base + i))
		}
		ch.Close()
	}
	go feed(c1, 0)
	go feed(c2, 1000)
	go feed(c3, 2000)

	got, closed := zzDrain(out, 10*time.Second)
	if !closed {
		t.Fatalf("output channel never closed after all inputs closed; got %d values", len(got))
	}
	if len(got) != 3*perInput {
		t.Fatalf("forwarded %d values; want %d (some dropped or duplicated)", len(got), 3*perInput)
	}
	seen := map[int]int{}
	for _, v := range got {
		seen[v]++
	}
	for base := 0; base < 3; base++ {
		for i := 0; i < perInput; i++ {
			v := base*1000 + i
			if seen[v] != 1 {
				t.Fatalf("value %d appeared %d times; want exactly once", v, seen[v])
			}
		}
	}
}

// TestZZMergePerInputOrder: relative order of values from a single input is
// preserved on the merged output.
func TestZZMergePerInputOrder(t *testing.T) {
	zzInElemCheck(t)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	const perInput = 300
	c1 := zzMakeIntChan(0)
	c2 := zzMakeIntChan(0)
	out := zzCall(t, ctx, []reflect.Value{c1, c2})

	// Input 1 emits even numbers in increasing order, input 2 odd numbers.
	go func() {
		for i := 0; i < perInput; i++ {
			c1.Send(reflect.ValueOf(2 * i))
		}
		c1.Close()
	}()
	go func() {
		for i := 0; i < perInput; i++ {
			c2.Send(reflect.ValueOf(2*i + 1))
		}
		c2.Close()
	}()

	got, closed := zzDrain(out, 10*time.Second)
	if !closed {
		t.Fatalf("output never closed; got %d", len(got))
	}
	if len(got) != 2*perInput {
		t.Fatalf("forwarded %d values; want %d", len(got), 2*perInput)
	}
	var evens, odds []int
	for _, v := range got {
		if v%2 == 0 {
			evens = append(evens, v)
		} else {
			odds = append(odds, v)
		}
	}
	if !sort.IntsAreSorted(evens) {
		t.Fatalf("input-1 (even) order not preserved on output: %v", evens)
	}
	if !sort.IntsAreSorted(odds) {
		t.Fatalf("input-2 (odd) order not preserved on output: %v", odds)
	}
	if len(evens) != perInput || len(odds) != perInput {
		t.Fatalf("partition counts wrong: evens=%d odds=%d want %d each", len(evens), len(odds), perInput)
	}
}

// TestZZMergeRangeTerminates: ranging over the merged output terminates after
// all inputs close (the output is actually closed, not merely drained).
func TestZZMergeRangeTerminates(t *testing.T) {
	zzInElemCheck(t)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	c1 := zzMakeIntChan(4)
	c2 := zzMakeIntChan(4)
	for i := 0; i < 4; i++ {
		c1.Send(reflect.ValueOf(i))
		c2.Send(reflect.ValueOf(100 + i))
	}
	c1.Close()
	c2.Close()
	out := zzCall(t, ctx, []reflect.Value{c1, c2})

	got, closed := zzDrain(out, 10*time.Second)
	if !closed {
		t.Fatalf("range over output did not terminate (output never closed); got %d", len(got))
	}
	if len(got) != 8 {
		t.Fatalf("buffered values lost on close: got %d want 8", len(got))
	}
}

// TestZZMergeContextCancelCloses: with inputs that never close, cancelling the
// context closes the output promptly. Ranging over it then terminates.
func TestZZMergeContextCancelCloses(t *testing.T) {
	zzInElemCheck(t)
	ctx, cancel := context.WithCancel(context.Background())

	c1 := zzMakeIntChan(0) // never closed
	c2 := zzMakeIntChan(0) // never closed
	out := zzCall(t, ctx, []reflect.Value{c1, c2})

	// Push a couple of values, then cancel without closing the inputs.
	go func() {
		c1.TrySend(reflect.ValueOf(1))
		c2.TrySend(reflect.ValueOf(2))
		cancel()
	}()

	// After cancellation the output must close promptly; drain must observe a
	// clean close, not a timeout.
	_, closed := zzDrain(out, 8*time.Second)
	if !closed {
		t.Fatalf("output did not close after context cancellation with non-closing inputs")
	}
}

// TestZZMergeZeroInputs: merging zero inputs yields an output that is closed
// immediately; ranging over it does nothing.
func TestZZMergeZeroInputs(t *testing.T) {
	zzInElemCheck(t)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	out := zzCall(t, ctx, nil)
	got, closed := zzDrain(out, 5*time.Second)
	if !closed {
		t.Fatalf("zero-input merge output did not close")
	}
	if len(got) != 0 {
		t.Fatalf("zero-input merge produced %d values; want 0", len(got))
	}
}

// TestZZMergeNoGoroutineLeak: repeated create/use cycles (closing via inputs and
// via cancellation) must not accumulate goroutines.
func TestZZMergeNoGoroutineLeak(t *testing.T) {
	zzInElemCheck(t)
	base := zzMergeNumGoroutine()
	var wg sync.WaitGroup

	for c := 0; c < 50; c++ {
		ctx, cancel := context.WithCancel(context.Background())
		c1 := zzMakeIntChan(0)
		c2 := zzMakeIntChan(0)
		out := zzCall(t, ctx, []reflect.Value{c1, c2})

		wg.Add(1)
		go func(ch1, ch2, o reflect.Value, cancelFn func(), idx int) {
			defer wg.Done()
			// Half the cycles end by closing inputs, half by cancelling.
			if idx%2 == 0 {
				for i := 0; i < 3; i++ {
					ch1.Send(reflect.ValueOf(i))
				}
				ch1.Close()
				ch2.Close()
				zzDrain(o, 5*time.Second)
				cancelFn()
			} else {
				ch1.TrySend(reflect.ValueOf(1))
				cancelFn()
				zzDrain(o, 5*time.Second)
			}
		}(c1, c2, out, cancel, c)
	}
	wg.Wait()

	deadline := time.Now().Add(3 * time.Second)
	after := zzMergeNumGoroutine()
	for time.Now().Before(deadline) && after > base+100 {
		time.Sleep(50 * time.Millisecond)
		after = zzMergeNumGoroutine()
	}
	if after > base+100 {
		t.Fatalf("goroutine leak suspected across merge create/use cycles: base=%d after=%d", base, after)
	}
}

// TestZZMergeManyInputs: an arbitrary positive number of inputs are all merged.
func TestZZMergeManyInputs(t *testing.T) {
	zzInElemCheck(t)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	const n = 16
	const per = 50
	chans := make([]reflect.Value, n)
	for i := range chans {
		chans[i] = zzMakeIntChan(0)
	}
	out := zzCall(t, ctx, chans)
	for i := 0; i < n; i++ {
		go func(ch reflect.Value, base int) {
			for j := 0; j < per; j++ {
				ch.Send(reflect.ValueOf(base*1000 + j))
			}
			ch.Close()
		}(chans[i], i)
	}
	got, closed := zzDrain(out, 12*time.Second)
	if !closed {
		t.Fatalf("output never closed with %d inputs; got %d values", n, len(got))
	}
	if len(got) != n*per {
		t.Fatalf("forwarded %d values; want %d", len(got), n*per)
	}
}
'''


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _require_go():
    if shutil.which("go") is None:
        pytest.skip("go toolchain not available")


def _find_merge_func():
    """Run the embedded AST finder; return the exported merge function name."""
    assert os.path.isfile(MERGE_GO), "missing deliverable: lib/channels/merge.go"
    tmpdir = os.path.join(REPO_DIR, ".zz_mergefind")
    os.makedirs(tmpdir, exist_ok=True)
    try:
        with open(os.path.join(tmpdir, "main.go"), "w") as fh:
            fh.write(FUNC_FINDER_SRC)
        with open(os.path.join(tmpdir, "go.mod"), "w") as fh:
            fh.write("module zzmergefind\n\ngo 1.21\n")
        proc = subprocess.run(
            ["go", "run", ".", MERGE_GO],
            cwd=tmpdir,
            capture_output=True,
            text=True,
            timeout=GO_BUILD_TIMEOUT,
            env={**os.environ, "GOFLAGS": "-buildvcs=false"},
        )
        assert proc.returncode == 0, (
            f"AST merge-function finder failed:\nSTDOUT:{proc.stdout}\nSTDERR:{proc.stderr}"
        )
        names = [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]
        assert names, (
            "no exported generic merge function (a top-level generic func "
            "(context, ...<-chan T) -> <-chan T) found in merge.go; stdout="
            f"{proc.stdout!r}"
        )
        return names[0]
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _install_driver(func_name):
    src = DRIVER_TEST_SRC.replace("__FUNC__", func_name)
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
         "-v", "./lib/channels/"],
        cwd=REPO_DIR,
        capture_output=True,
        text=True,
        timeout=GO_TEST_TIMEOUT,
        env={**os.environ, "GOFLAGS": "-buildvcs=false"},
    )


@pytest.fixture(scope="module", autouse=True)
def _driver_setup():
    """Discover the merge function and install the reflection driver once."""
    _require_go()
    func_name = _find_merge_func()
    _install_driver(func_name)
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

    def test_l1_merge_file_exists(self):
        """L1: the deliverable lib/channels/merge.go must exist."""
        assert os.path.isfile(MERGE_GO), (
            "missing required deliverable: lib/channels/merge.go"
        )

    def test_l1_in_channels_package(self):
        """L1: merge.go must declare package channels."""
        with open(MERGE_GO) as fh:
            head = fh.read()
        assert "package channels" in head, (
            "merge.go must be in package channels"
        )

    def test_l1_test_file_exists(self):
        """L1: the agent must provide merge_test.go with scenarios."""
        assert os.path.isfile(MERGE_TEST_GO), (
            "missing required deliverable: lib/channels/merge_test.go"
        )

    def test_l1_package_builds(self):
        """L1: `go build ./lib/channels/` must succeed."""
        _require_go()
        proc = subprocess.run(
            ["go", "build", "./lib/channels/"],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=GO_BUILD_TIMEOUT,
            env={**os.environ, "GOFLAGS": "-buildvcs=false"},
        )
        assert proc.returncode == 0, (
            f"go build ./lib/channels/ failed:\n{proc.stdout}\n{proc.stderr}"
        )

    def test_l1_exported_generic_merge_func_discoverable(self):
        """L1: an exported generic merge function (context, ...<-chan T) ->
        <-chan T must be discoverable via AST."""
        _require_go()
        name = _find_merge_func()
        assert name and name[0].isupper(), (
            f"merge function {name!r} must be exported (capitalized)"
        )

    # ----------------------------- L2 ----------------------------- #

    def test_l2_all_values_forwarded_exactly_once(self):
        """L2: every value from three distinct inputs appears exactly once."""
        _assert_driver_pass(
            _run_driver("TestZZMergeAllValuesOnce"), "all-values-once"
        )

    def test_l2_per_input_order_preserved(self):
        """L2: the relative order of each input's values is preserved."""
        _assert_driver_pass(
            _run_driver("TestZZMergePerInputOrder"), "per-input-order"
        )

    def test_l2_range_terminates_after_inputs_close(self):
        """L2: output closes (range terminates) after all inputs close,
        without losing buffered values."""
        _assert_driver_pass(
            _run_driver("TestZZMergeRangeTerminates"), "range-terminates"
        )

    def test_l2_context_cancel_closes_output(self):
        """L2: cancelling the context closes the output promptly even when
        inputs never close."""
        _assert_driver_pass(
            _run_driver("TestZZMergeContextCancelCloses"), "context-cancel"
        )

    def test_l2_zero_inputs_closes_immediately(self):
        """L2: merging zero inputs yields an immediately-closed output."""
        _assert_driver_pass(
            _run_driver("TestZZMergeZeroInputs"), "zero-inputs"
        )

    def test_l2_many_inputs_all_merged(self):
        """L2: an arbitrary positive number of inputs are all merged."""
        _assert_driver_pass(
            _run_driver("TestZZMergeManyInputs"), "many-inputs"
        )

    def test_l2_no_goroutine_leak_across_cycles(self):
        """L2: repeated create/use cycles (close + cancel) do not leak."""
        _assert_driver_pass(
            _run_driver("TestZZMergeNoGoroutineLeak"), "no-goroutine-leak"
        )

    def test_l2_agents_own_race_suite_passes(self):
        """L2: the documented acceptance command
        `go test -race -run 'Merge' ./lib/channels/` passes clean (no
        failures, no race or goroutine-leak reports)."""
        _require_go()
        proc = subprocess.run(
            ["go", "test", "-race", "-count=1", "-run", "Merge",
             "./lib/channels/"],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=GO_TEST_TIMEOUT,
            env={**os.environ, "GOFLAGS": "-buildvcs=false"},
        )
        combined = proc.stdout + "\n" + proc.stderr
        assert proc.returncode == 0, (
            "go test -race -run 'Merge' ./lib/channels/ failed:\n" + combined
        )
        assert "DATA RACE" not in combined, "data race reported:\n" + combined
        assert "panic:" not in combined, "panic reported:\n" + combined
        assert "no test files" not in combined, (
            "no Merge tests found in lib/channels/:\n" + combined
        )


# keep linters quiet about the textwrap import (kept for parity with template)
_ = textwrap
