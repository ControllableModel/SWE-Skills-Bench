"""Benchmark test for skill: go-concurrency-patterns (variant ext8).

Task: Add a *concurrent pipeline-stage* helper to consul's ``lib/channels``
package (new file ``lib/channels/stage.go`` in package ``channels``). The
exported, generic function reads input values from a ``<-chan IN``, applies a
transform ``func(context.Context, IN) (OUT, error)`` to each using a bounded
number of concurrent workers, and emits per-item results (value + error) on a
returned ``<-chan`` of a small result struct. The function name and the result
struct's field names are chosen by the agent, so this test does NOT hard-code
them. Instead it:

  * uses a tiny Go AST program to discover the exported generic top-level
    function in ``stage.go`` whose parameter list contains a ``context.Context``,
    an input channel type, an int worker count, and a transform func, and whose
    single result is a channel (the pipeline-stage entry point),
  * generates an independent Go *reflection driver* test that instantiates that
    function with ``[int, int]`` and exercises the documented behaviors:
    bounded worker concurrency (never exceeds the configured count while still
    processing every input), per-item error propagation, output closing on
    input completion, output closing + no goroutine leak on context
    cancellation, and back-pressure on a slow consumer,
  * compiles and runs that driver under ``go test -race`` to deep-validate
    those behaviors with this test's own assertions, not the agent's own
    ``stage_test.go``.

A naive / stub / files-that-merely-look-related solution fails: e.g. a stage
that runs all transforms serially or with unbounded concurrency fails the
worker-bound check; one that drops errors fails error-propagation; one that
buffers unboundedly fails back-pressure; one that never closes the output, or
that leaks goroutines on cancellation, fails the completion / leak checks.
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
STAGE_GO = os.path.join(CHANNELS_DIR, "stage.go")

# Helper Go files dropped into the package during testing. Unique prefix so they
# never collide with agent code; cleaned up afterwards.
DRIVER_TEST = os.path.join(CHANNELS_DIR, "zz_stage_driver_test.go")
DRIVER_HELP = os.path.join(CHANNELS_DIR, "zz_stage_helper_test.go")

GO_BUILD_TIMEOUT = 300
GO_TEST_TIMEOUT = 600


# --------------------------------------------------------------------------- #
# Embedded Go: AST function finder.
# Prints "<FuncName>" for each exported top-level generic function whose
# parameter list contains a context.Context, a channel type, an int, and a
# func type, and whose single result is a channel. That uniquely identifies the
# pipeline-stage entry point regardless of the name the agent chose.
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

func isContext(e ast.Expr) bool {
	if sel, ok := e.(*ast.SelectorExpr); ok {
		if id, ok := sel.X.(*ast.Ident); ok {
			return id.Name == "context" && sel.Sel.Name == "Context"
		}
	}
	return false
}

func isIntIdent(e ast.Expr) bool {
	if id, ok := e.(*ast.Ident); ok {
		return id.Name == "int"
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
	for _, d := range f.Decls {
		fn, ok := d.(*ast.FuncDecl)
		if !ok || fn.Recv != nil || !fn.Name.IsExported() {
			continue
		}
		// Must be generic (have type params).
		if fn.Type.TypeParams == nil || len(fn.Type.TypeParams.List) == 0 {
			continue
		}
		// Single channel result.
		if fn.Type.Results == nil || len(fn.Type.Results.List) != 1 {
			continue
		}
		if _, ok := fn.Type.Results.List[0].Type.(*ast.ChanType); !ok {
			continue
		}
		hasCtx, hasChan, hasInt, hasFunc := false, false, false, false
		if fn.Type.Params != nil {
			for _, p := range fn.Type.Params.List {
				n := 1
				if len(p.Names) > 1 {
					n = len(p.Names)
				}
				for k := 0; k < n; k++ {
					switch p.Type.(type) {
					case *ast.ChanType:
						hasChan = true
					case *ast.FuncType:
						hasFunc = true
					}
					if isContext(p.Type) {
						hasCtx = true
					}
					if isIntIdent(p.Type) {
						hasInt = true
					}
				}
			}
		}
		if hasCtx && hasChan && hasInt && hasFunc {
			fmt.Printf("%s\n", fn.Name.Name)
		}
	}
}
'''


# --------------------------------------------------------------------------- #
# Embedded Go: reflection driver test. ``__FUNC__`` is substituted with the
# discovered function name. The function is instantiated with [int, int] via a
# tiny generic shim so we can call it with concrete types; the result element
# type (the per-item result struct) is inspected at runtime to pull out the
# transformed int value and the error, so the agent's chosen field names do not
# matter.
# --------------------------------------------------------------------------- #
DRIVER_HELPER_SRC = r'''
package channels

import (
	"context"
	"runtime"
)

func zzNumGoroutine() int { return runtime.NumGoroutine() }

// zzStage is a concrete shim around the agent's generic stage function,
// instantiated with IN=int, OUT=int. The reflection driver calls only this.
func zzStage(ctx context.Context, in <-chan int, workers int,
	f func(context.Context, int) (int, error)) interface{} {
	return __FUNC__[int, int](ctx, in, workers, f)
}
'''

DRIVER_TEST_SRC = r'''
package channels

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

// zzResult extracts (outValue, err) from one element of the result channel,
// whatever the agent named its struct fields. It scans the struct's fields for
// an int (the transformed value) and an error (the per-item failure).
func zzResult(v reflect.Value) (int, error) {
	val := 0
	var err error
	errType := reflect.TypeOf((*error)(nil)).Elem()
	switch v.Kind() {
	case reflect.Struct:
		for i := 0; i < v.NumField(); i++ {
			fv := v.Field(i)
			switch {
			case fv.Kind() == reflect.Int || fv.Kind() == reflect.Int64 ||
				fv.Kind() == reflect.Int32:
				val = int(fv.Int())
			case fv.Type().Implements(errType):
				if !fv.IsNil() {
					err, _ = fv.Interface().(error)
				}
			}
		}
	case reflect.Int, reflect.Int64, reflect.Int32:
		val = int(v.Int())
	}
	return val, err
}

// zzDrain ranges (via reflection) over the stage's output channel, collecting
// (value, errIsNil) pairs until the channel is closed.
func zzDrain(out reflect.Value) []struct {
	v  int
	ok bool
} {
	var res []struct {
		v  int
		ok bool
	}
	for {
		x, recvOK := out.Recv()
		if !recvOK {
			break
		}
		v, err := zzResult(x)
		res = append(res, struct {
			v  int
			ok bool
		}{v, err == nil})
	}
	return res
}

func TestZZStageAllProcessedBounded(t *testing.T) {
	const N = 100
	const W = 4
	in := make(chan int)
	var live int32
	var maxLive int32
	transform := func(ctx context.Context, x int) (int, error) {
		cur := atomic.AddInt32(&live, 1)
		for {
			m := atomic.LoadInt32(&maxLive)
			if cur <= m || atomic.CompareAndSwapInt32(&maxLive, m, cur) {
				break
			}
		}
		// brief, deterministic busy overlap window without time.Sleep on the
		// assertion path: spin a tiny bounded loop so workers actually overlap.
		runtime.Gosched()
		atomic.AddInt32(&live, -1)
		return x * 2, nil
	}
	outI := zzStage(context.Background(), in, W, transform)
	out := reflect.ValueOf(outI)
	go func() {
		for i := 0; i < N; i++ {
			in <- i
		}
		close(in)
	}()
	got := zzDrain(out)
	if len(got) != N {
		t.Fatalf("want %d results, got %d", N, len(got))
	}
	sum := 0
	for _, r := range got {
		if !r.ok {
			t.Fatalf("unexpected error result: %+v", r)
		}
		sum += r.v
	}
	want := 0
	for i := 0; i < N; i++ {
		want += i * 2
	}
	if sum != want {
		t.Fatalf("transform applied incorrectly: sum=%d want=%d", sum, want)
	}
	if ml := atomic.LoadInt32(&maxLive); ml > W {
		t.Fatalf("worker bound violated: observed concurrency %d > %d", ml, W)
	}
	if ml := atomic.LoadInt32(&maxLive); ml < 2 {
		t.Fatalf("workers did not run concurrently (max observed=%d); a serial "+
			"implementation does not satisfy the task", ml)
	}
}

func TestZZStageErrorPropagation(t *testing.T) {
	const N = 60
	const W = 3
	sentinel := errors.New("zz-boom")
	in := make(chan int)
	transform := func(ctx context.Context, x int) (int, error) {
		if x%2 == 0 {
			return 0, sentinel
		}
		return x + 1000, nil
	}
	outI := zzStage(context.Background(), in, W, transform)
	out := reflect.ValueOf(outI)
	go func() {
		for i := 0; i < N; i++ {
			in <- i
		}
		close(in)
	}()
	errCount, okCount := 0, 0
	var okVals []int
	for {
		x, recvOK := out.Recv()
		if !recvOK {
			break
		}
		v, err := zzResult(x)
		if err != nil {
			errCount++
		} else {
			okCount++
			okVals = append(okVals, v)
		}
	}
	if errCount != N/2 {
		t.Fatalf("want %d error results, got %d", N/2, errCount)
	}
	if okCount != N/2 {
		t.Fatalf("want %d success results, got %d", N/2, okCount)
	}
	for _, v := range okVals {
		if v < 1000 {
			t.Fatalf("successful result lost its transformed value: %d", v)
		}
	}
}

func TestZZStageClosesOnInputDone(t *testing.T) {
	in := make(chan int)
	transform := func(ctx context.Context, x int) (int, error) { return x, nil }
	outI := zzStage(context.Background(), in, 2, transform)
	out := reflect.ValueOf(outI)
	go func() {
		for i := 0; i < 10; i++ {
			in <- i
		}
		close(in)
	}()
	done := make(chan int, 1)
	go func() {
		got := zzDrain(out)
		done <- len(got)
	}()
	select {
	case n := <-done:
		if n != 10 {
			t.Fatalf("want 10 results before close, got %d", n)
		}
	case <-time.After(10 * time.Second):
		t.Fatal("output channel never closed after input completion")
	}
}

func TestZZStageCancelClosesOutput(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	in := make(chan int)
	var started sync.WaitGroup
	started.Add(1)
	var once sync.Once
	block := make(chan struct{})
	transform := func(c context.Context, x int) (int, error) {
		once.Do(func() { started.Done() })
		select {
		case <-c.Done():
			return 0, c.Err()
		case <-block:
			return x, nil
		}
	}
	outI := zzStage(ctx, in, 2, transform)
	out := reflect.ValueOf(outI)
	go func() {
		for i := 0; i < 50; i++ {
			select {
			case in <- i:
			case <-ctx.Done():
				close(in)
				return
			}
		}
	}()
	started.Wait() // at least one transform is in flight
	cancel()
	close(block)
	done := make(chan struct{})
	go func() {
		// drain to closure
		for {
			_, ok := out.Recv()
			if !ok {
				break
			}
		}
		close(done)
	}()
	select {
	case <-done:
	case <-time.After(10 * time.Second):
		t.Fatal("output channel did not close promptly after context cancel")
	}
}

func TestZZStageBackPressure(t *testing.T) {
	// With a consumer that stops reading, the stage must not run far ahead: it
	// cannot have processed an unbounded number of inputs. We feed many inputs
	// and count how many transforms run while the consumer reads nothing.
	const W = 2
	in := make(chan int)
	var processed int32
	transform := func(ctx context.Context, x int) (int, error) {
		atomic.AddInt32(&processed, 1)
		return x, nil
	}
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	outI := zzStage(ctx, in, W, transform)
	out := reflect.ValueOf(outI)
	fedDone := make(chan struct{})
	go func() {
		for i := 0; i < 1000; i++ {
			select {
			case in <- i:
			case <-ctx.Done():
				close(fedDone)
				return
			}
		}
		close(fedDone)
	}()
	// Read exactly one result, then stop reading for a while.
	if _, ok := out.Recv(); !ok {
		t.Fatal("expected at least one result")
	}
	// Give the stage time to do whatever buffering it would do. Bound is
	// generous: a correct, back-pressured stage processes O(W + buffer) items
	// not the whole 1000 while the consumer is idle.
	deadline := time.Now().Add(400 * time.Millisecond)
	for time.Now().Before(deadline) {
		runtime.Gosched()
	}
	p := atomic.LoadInt32(&processed)
	if p >= 1000 {
		t.Fatalf("no back-pressure: stage processed all %d inputs with an idle "+
			"consumer (unbounded buffering)", p)
	}
	// Now drain the rest so goroutines finish.
	cancel()
	for {
		if _, ok := out.Recv(); !ok {
			break
		}
	}
	<-fedDone
}

func TestZZStageNoGoroutineLeak(t *testing.T) {
	base := zzNumGoroutine()
	for c := 0; c < 30; c++ {
		ctx, cancel := context.WithCancel(context.Background())
		in := make(chan int)
		transform := func(c context.Context, x int) (int, error) { return x, nil }
		outI := zzStage(ctx, in, 4, transform)
		out := reflect.ValueOf(outI)
		go func() {
			for i := 0; i < 20; i++ {
				select {
				case in <- i:
				case <-ctx.Done():
					close(in)
					return
				}
			}
			close(in)
		}()
		// Half the cycles drain fully, half cancel mid-stream.
		if c%2 == 0 {
			for {
				if _, ok := out.Recv(); !ok {
					break
				}
			}
			cancel()
		} else {
			out.Recv()
			cancel()
			for {
				if _, ok := out.Recv(); !ok {
					break
				}
			}
		}
	}
	deadline := time.Now().Add(3 * time.Second)
	after := zzNumGoroutine()
	for time.Now().Before(deadline) && after > base+50 {
		time.Sleep(50 * time.Millisecond)
		after = zzNumGoroutine()
	}
	if after > base+50 {
		t.Fatalf("goroutine leak suspected across stage cycles: base=%d after=%d",
			base, after)
	}
}
'''


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _require_go():
    if shutil.which("go") is None:
        pytest.skip("go toolchain not available")


def _find_stage_func():
    """Run the embedded AST finder; return the exported stage function name."""
    assert os.path.isfile(STAGE_GO), "missing deliverable: lib/channels/stage.go"
    tmpdir = os.path.join(REPO_DIR, ".zz_stagefind")
    os.makedirs(tmpdir, exist_ok=True)
    try:
        with open(os.path.join(tmpdir, "main.go"), "w") as fh:
            fh.write(FUNC_FINDER_SRC)
        with open(os.path.join(tmpdir, "go.mod"), "w") as fh:
            fh.write("module zzstagefind\n\ngo 1.21\n")
        proc = subprocess.run(
            ["go", "run", ".", STAGE_GO],
            cwd=tmpdir,
            capture_output=True,
            text=True,
            timeout=GO_BUILD_TIMEOUT,
            env={**os.environ, "GOFLAGS": "-buildvcs=false"},
        )
        assert proc.returncode == 0, (
            f"AST stage-function finder failed:\nSTDOUT:{proc.stdout}\n"
            f"STDERR:{proc.stderr}"
        )
        lines = [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]
        assert lines, (
            "no exported generic pipeline-stage function (taking a "
            "context.Context, an input channel, an int worker count, and a "
            "transform func, returning a channel) found in stage.go; stdout="
            f"{proc.stdout!r}"
        )
        return lines[0]
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _install_driver(func_name):
    with open(DRIVER_TEST, "w") as fh:
        fh.write(DRIVER_TEST_SRC)
    with open(DRIVER_HELP, "w") as fh:
        fh.write(DRIVER_HELPER_SRC.replace("__FUNC__", func_name))


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
    """Discover the stage function and install the reflection driver once."""
    _require_go()
    func_name = _find_stage_func()
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

    def test_l1_stage_file_exists(self):
        """L1: the deliverable lib/channels/stage.go must exist."""
        assert os.path.isfile(STAGE_GO), (
            "missing required deliverable: lib/channels/stage.go"
        )

    def test_l1_in_channels_package(self):
        """L1: stage.go must declare package channels."""
        with open(STAGE_GO) as fh:
            head = fh.read()
        assert "package channels" in head, (
            "stage.go must be in package channels"
        )

    def test_l1_test_file_exists(self):
        """L1: the agent must provide stage_test.go with scenarios."""
        test_file = os.path.join(CHANNELS_DIR, "stage_test.go")
        assert os.path.isfile(test_file), (
            "missing required deliverable: lib/channels/stage_test.go"
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

    def test_l1_exported_generic_stage_func_discoverable(self):
        """L1: an exported generic pipeline-stage function must be discoverable."""
        _require_go()
        func_name = _find_stage_func()
        assert func_name and func_name[0].isupper(), (
            f"stage function {func_name!r} must be exported (capitalized)"
        )

    # ----------------------------- L2 ----------------------------- #

    def test_l2_all_inputs_processed_bounded_concurrency(self):
        """L2: every input is transformed exactly once and the number of
        simultaneously running transforms never exceeds the worker count
        (while still being genuinely concurrent)."""
        _assert_driver_pass(
            _run_driver("TestZZStageAllProcessedBounded"), "bounded-concurrency"
        )

    def test_l2_per_item_error_propagation(self):
        """L2: results for failing inputs carry the error while others carry
        the transformed value -- errors are not dropped or merged."""
        _assert_driver_pass(
            _run_driver("TestZZStageErrorPropagation"), "error-propagation"
        )

    def test_l2_output_closes_on_input_completion(self):
        """L2: closing the input drains all results then closes the output so a
        range loop terminates."""
        _assert_driver_pass(
            _run_driver("TestZZStageClosesOnInputDone"), "close-on-input-done"
        )

    def test_l2_output_closes_on_context_cancel(self):
        """L2: cancelling the context promptly closes the output channel."""
        _assert_driver_pass(
            _run_driver("TestZZStageCancelClosesOutput"), "close-on-cancel"
        )

    def test_l2_back_pressure_on_slow_consumer(self):
        """L2: a stage with an idle consumer must not process an unbounded
        number of inputs ahead (no unbounded buffering)."""
        _assert_driver_pass(
            _run_driver("TestZZStageBackPressure"), "back-pressure"
        )

    def test_l2_no_goroutine_leak_across_cycles(self):
        """L2: repeated stage create/use/cancel cycles do not leak goroutines."""
        _assert_driver_pass(
            _run_driver("TestZZStageNoGoroutineLeak"), "no-goroutine-leak"
        )

    def test_l2_agents_own_race_suite_passes(self):
        """L2: the documented acceptance command
        `go test -race -run Stage ./lib/channels/` passes clean -- no failures,
        no race-detector reports, no panics, and Stage-named tests actually
        ran."""
        _require_go()
        proc = subprocess.run(
            ["go", "test", "-race", "-count=1", "-run", "Stage",
             "./lib/channels/"],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=GO_TEST_TIMEOUT,
            env={**os.environ, "GOFLAGS": "-buildvcs=false"},
        )
        combined = proc.stdout + "\n" + proc.stderr
        assert proc.returncode == 0, (
            "go test -race -run Stage ./lib/channels/ failed:\n" + combined
        )
        assert "DATA RACE" not in combined, "data race reported:\n" + combined
        assert "panic:" not in combined, "panic reported:\n" + combined
        assert "no test files" not in combined, (
            "no Stage tests found in lib/channels/:\n" + combined
        )


# keep linters quiet about the textwrap import guard
_ = textwrap
