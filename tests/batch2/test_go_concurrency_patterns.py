"""Benchmark test for skill: go-concurrency-patterns (variant ext2).

Task: Add a *coalescing event debouncer* to consul's ``lib/channels`` package
(new file ``lib/channels/debounce.go`` in package ``channels``). A burst of
rapid trigger signals must collapse into exactly one debounced output once a
configured quiet-window duration elapses with no further triggers.

The public API method/field names are chosen by the agent, so this test does
NOT hard-code them. Instead it:

  * uses a tiny Go AST program to discover the exported constructor whose sole
    parameter is a ``time.Duration`` and whose single result is a type declared
    in ``debounce.go`` (the debouncer),
  * generates an INDEPENDENT Go reflection driver test that classifies the
    trigger / receive(ctx) / close operations purely by signature *and by
    behavior* (close is the no-arg/no-result method that unblocks a pending
    receive; trigger is the other no-arg/no-result method),
  * compiles and runs that driver under ``go test -race`` to deep-validate the
    documented behaviors: burst coalescing into a single output, a second
    independent debounce cycle, no premature output before the quiet window,
    context-cancelled receive, receive unblocking on close, trigger-after-close
    not panicking, and a goroutine-leak check across create/use/close cycles.

A naive / stub / files-that-merely-look-related solution fails because the
behavior is exercised independently with this test's own assertions and timing,
not by trusting the agent's own ``debounce_test.go``. In particular a stub that
emits an output immediately (ignoring the quiet window) fails the
"no premature output" assertion, and one that emits one output per trigger
fails the burst-coalescing assertion.
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
DEBOUNCE_GO = os.path.join(CHANNELS_DIR, "debounce.go")

# Helper Go files dropped into the package while testing. Names are unique
# enough to never collide with agent code and are cleaned up afterwards.
DRIVER_TEST = os.path.join(CHANNELS_DIR, "zz_bench_debounce_driver_test.go")
DRIVER_HELP = os.path.join(CHANNELS_DIR, "zz_bench_debounce_helper_test.go")

GO_BUILD_TIMEOUT = 300
GO_TEST_TIMEOUT = 420


# --------------------------------------------------------------------------- #
# Embedded Go: AST constructor finder.
# Prints "<CtorName>\t<TypeName>" for each exported top-level function whose
# single parameter is a time.Duration and whose single result is a (pointer to a)
# type declared in the same file. That is the debouncer constructor.
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

// isDuration reports whether the expression denotes time.Duration.
func isDuration(e ast.Expr) bool {
	if se, ok := e.(*ast.SelectorExpr); ok {
		if id, ok := se.X.(*ast.Ident); ok {
			return id.Name == "time" && se.Sel.Name == "Duration"
		}
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
	// Collect type names declared in this file.
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
		if fn, ok := d.(*ast.FuncDecl); ok && fn.Recv == nil && fn.Name.IsExported() {
			// exactly one result, a (pointer to a) type declared here.
			if fn.Type.Results == nil || len(fn.Type.Results.List) != 1 {
				continue
			}
			rname := texpr(fn.Type.Results.List[0].Type)
			if !declared[rname] {
				continue
			}
			// at least one parameter is a time.Duration.
			hasDur := false
			if fn.Type.Params != nil {
				for _, p := range fn.Type.Params.List {
					if isDuration(p.Type) {
						hasDur = true
					}
				}
			}
			if hasDur {
				fmt.Printf("%s\t%s\n", fn.Name.Name, rname)
			}
		}
	}
}
'''


# --------------------------------------------------------------------------- #
# Embedded Go helper (in package channels) exposing goroutine count.
# --------------------------------------------------------------------------- #
DRIVER_HELPER_SRC = r'''
package channels

import "runtime"

func zzNumGoroutineDebounce() int { return runtime.NumGoroutine() }
'''


# --------------------------------------------------------------------------- #
# Embedded Go: the reflection driver test. ``__CTOR__`` is substituted with the
# discovered constructor name. The quiet window is a fixed small value so the
# whole suite runs fast yet the "no premature output" assertion has real teeth.
#
# Classification strategy (method names are agent-chosen):
#   * receive : the method whose first arg is a context.Context. It blocks until
#               an output, ctx cancel, or close. (May be on the debouncer or on a
#               sub-handle; we look on the debouncer value itself per the doc,
#               which says "delivered over a receive operation the caller can
#               wait on".)
#   * close   : a no-arg/no-result method that, when called, unblocks a pending
#               receive. Discovered behaviorally.
#   * trigger : a no-arg/no-result method that is NOT close. Discovered as the
#               remaining no-arg/no-result method; verified behaviorally because
#               firing it makes an output appear after the quiet window.
# --------------------------------------------------------------------------- #
DRIVER_TEST_SRC = r'''
package channels

import (
	"context"
	"reflect"
	"sync"
	"testing"
	"time"
)

// The quiet window used throughout. Small enough to be fast, large enough that
// "no premature output" is a meaningful, race-free assertion.
const zzQuiet = 150 * time.Millisecond

var zzCtxType = reflect.TypeOf((*context.Context)(nil)).Elem()

// zzNew constructs a debouncer with the quiet window. The constructor may take
// extra params beyond the duration; we only support the documented single
// duration-arg form and pass zero values for any others.
func zzNew() reflect.Value {
	ctor := reflect.ValueOf(__CTOR__)
	ct := ctor.Type()
	args := make([]reflect.Value, ct.NumIn())
	durType := reflect.TypeOf(time.Duration(0))
	filledDur := false
	for i := 0; i < ct.NumIn(); i++ {
		if ct.In(i) == durType && !filledDur {
			args[i] = reflect.ValueOf(zzQuiet)
			filledDur = true
		} else {
			args[i] = reflect.Zero(ct.In(i))
		}
	}
	return ctor.Call(args)[0]
}

type zzAPI struct {
	d        reflect.Value
	dt       reflect.Type
	recv     string       // method whose first param is context.Context
	noArg    []string     // names of no-arg/no-result methods (close + trigger)
}

func zzClassify(t *testing.T) *zzAPI {
	t.Helper()
	d := zzNew()
	if !d.IsValid() {
		t.Fatalf("constructor returned an invalid value")
	}
	dt := d.Type()
	a := &zzAPI{d: d, dt: dt}

	for i := 0; i < dt.NumMethod(); i++ {
		m := dt.Method(i)
		mt := m.Func.Type()
		nin := mt.NumIn() - 1
		nout := mt.NumOut()
		// receive: first explicit arg is a context.Context.
		if nin >= 1 && mt.In(1) == zzCtxType {
			a.recv = m.Name
			continue
		}
		// candidate close/trigger: no input args, no results.
		if nin == 0 && nout == 0 {
			a.noArg = append(a.noArg, m.Name)
		}
	}
	if a.recv == "" {
		t.Fatalf("no receive-like method (first arg context.Context) on %s", dt)
	}
	if len(a.noArg) < 2 {
		t.Fatalf("expected >=2 no-arg/no-result methods (trigger and close) on %s, got %v", dt, a.noArg)
	}
	t.Logf("discovered: recv=%s noArg=%v", a.recv, a.noArg)
	return a
}

func (a *zzAPI) call(name string) { a.d.MethodByName(name).Call(nil) }

// recvAsync starts a receive with the given context and returns a channel that
// yields the result values once the receive returns.
func (a *zzAPI) recvAsync(ctx context.Context) <-chan []reflect.Value {
	out := make(chan []reflect.Value, 1)
	m := a.d.MethodByName(a.recv)
	mt := m.Type()
	go func() {
		args := make([]reflect.Value, mt.NumIn())
		args[0] = reflect.ValueOf(ctx)
		for i := 1; i < mt.NumIn(); i++ {
			args[i] = reflect.Zero(mt.In(i))
		}
		out <- m.Call(args)
	}()
	return out
}

var zzErrType = reflect.TypeOf((*error)(nil)).Elem()

// zzDelivered reports whether the receive result represents a genuinely
// delivered output (any present-flag bool true AND any error result nil).
// A receive that returns due to ctx-cancel or close should report false.
func zzDelivered(res []reflect.Value) bool {
	ok := true
	for _, r := range res {
		switch {
		case r.Kind() == reflect.Bool:
			if !r.Bool() {
				ok = false
			}
		case r.Kind() == reflect.Interface && r.Type().Implements(zzErrType):
			if !r.IsNil() {
				ok = false
			}
		}
	}
	return ok
}

// zzDiscoverClose figures out which no-arg method is "close": the one that
// unblocks a pending receive. Returns (closeName, triggerName).
func zzDiscoverClose(t *testing.T) (string, string) {
	t.Helper()
	a := zzClassify(t)
	// Try each no-arg method as the close candidate on a fresh debouncer with a
	// pending (nothing-triggered) receive. The real close unblocks it.
	for _, cand := range a.noArg {
		fresh := zzClassify(t)
		ctx, cancel := context.WithCancel(context.Background())
		res := fresh.recvAsync(ctx)
		// give the receive a moment to actually block
		time.Sleep(20 * time.Millisecond)
		fresh.call(cand)
		select {
		case <-res:
			cancel()
			// cand unblocked the receive -> cand is close.
			other := ""
			for _, n := range a.noArg {
				if n != cand {
					other = n
					break
				}
			}
			if other == "" {
				t.Fatalf("could not identify a distinct trigger method besides close=%s", cand)
			}
			return cand, other
		case <-time.After(zzQuiet + 200*time.Millisecond):
			// cand did NOT unblock the receive within a quiet window -> not close
			// (a bare trigger would only emit after the window, but with no prior
			// trigger before it, semantics vary; we conservatively treat
			// non-unblocking as not-close). Cancel and move on.
			cancel()
			<-res
		}
	}
	t.Fatalf("could not behaviorally identify the close method among %v", a.noArg)
	return "", ""
}

// --- scenario tests (each run individually by the Python harness via -run) -- //

func TestZZDiscoverAPI(t *testing.T) {
	a := zzClassify(t)
	if a.recv == "" || len(a.noArg) < 2 {
		t.Fatalf("incomplete api: recv=%q noArg=%v", a.recv, a.noArg)
	}
	closeName, trigName := zzDiscoverClose(t)
	t.Logf("close=%s trigger=%s recv=%s", closeName, trigName, a.recv)
	if closeName == trigName {
		t.Fatalf("close and trigger resolved to the same method %q", closeName)
	}
}

// Burst of triggers within one quiet window -> exactly ONE output.
func TestZZBurstCoalescesToOne(t *testing.T) {
	closeName, trigName := zzDiscoverClose(t)
	a := zzClassify(t)
	defer a.call(closeName)

	for i := 0; i < 5; i++ {
		a.call(trigName)
	}
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	// First output must arrive after the quiet window.
	res := a.recvAsync(ctx)
	select {
	case r := <-res:
		if !zzDelivered(r) {
			t.Fatalf("expected one delivered output after a burst, got %v", r)
		}
	case <-time.After(zzQuiet + 3*time.Second):
		t.Fatal("no output after a burst of triggers within one quiet window")
	}

	// A SECOND receive must NOT yield another output (burst coalesced to one).
	ctx2, cancel2 := context.WithTimeout(context.Background(), zzQuiet+200*time.Millisecond)
	defer cancel2()
	res2 := a.recvAsync(ctx2)
	select {
	case r := <-res2:
		if zzDelivered(r) {
			t.Fatalf("burst produced more than one output; second receive delivered %v", r)
		}
	case <-time.After(zzQuiet + 3*time.Second):
		t.Fatal("second receive neither delivered nor returned via ctx timeout")
	}
}

// No output is delivered before the quiet window elapses.
func TestZZNoPrematureOutput(t *testing.T) {
	closeName, trigName := zzDiscoverClose(t)
	a := zzClassify(t)
	defer a.call(closeName)

	a.call(trigName)
	// Receive with a context that cancels BEFORE the quiet window elapses.
	short := zzQuiet / 3
	ctx, cancel := context.WithTimeout(context.Background(), short)
	defer cancel()
	res := a.recvAsync(ctx)
	select {
	case r := <-res:
		if zzDelivered(r) {
			t.Fatalf("output delivered before the quiet window elapsed (premature): %v", r)
		}
	case <-time.After(zzQuiet + 3*time.Second):
		t.Fatal("receive did not return even though its context expired early")
	}
}

// A second, independent debounce cycle works after the first is consumed.
func TestZZSecondCycle(t *testing.T) {
	closeName, trigName := zzDiscoverClose(t)
	a := zzClassify(t)
	defer a.call(closeName)

	// cycle 1
	a.call(trigName)
	ctx1, cancel1 := context.WithCancel(context.Background())
	select {
	case r := <-a.recvAsync(ctx1):
		if !zzDelivered(r) {
			cancel1()
			t.Fatalf("cycle 1: expected an output, got %v", r)
		}
	case <-time.After(zzQuiet + 3*time.Second):
		cancel1()
		t.Fatal("cycle 1: no output")
	}
	cancel1()

	// cycle 2 (independent)
	a.call(trigName)
	ctx2, cancel2 := context.WithCancel(context.Background())
	defer cancel2()
	select {
	case r := <-a.recvAsync(ctx2):
		if !zzDelivered(r) {
			t.Fatalf("cycle 2: expected a second independent output, got %v", r)
		}
	case <-time.After(zzQuiet + 3*time.Second):
		t.Fatal("cycle 2: no second output (debouncer not reusable)")
	}
}

// Continuous triggers spaced closer than the quiet window emit NOTHING until
// the stream pauses.
func TestZZContinuousStreamSuppressed(t *testing.T) {
	closeName, trigName := zzDiscoverClose(t)
	a := zzClassify(t)
	defer a.call(closeName)

	stop := make(chan struct{})
	done := make(chan struct{})
	go func() {
		defer close(done)
		for {
			select {
			case <-stop:
				return
			default:
				a.call(trigName)
				time.Sleep(zzQuiet / 4) // strictly faster than the quiet window
			}
		}
	}()

	// While the stream runs, a receive with a deadline of several windows must
	// NOT deliver an output.
	ctx, cancel := context.WithTimeout(context.Background(), 3*zzQuiet)
	res := a.recvAsync(ctx)
	select {
	case r := <-res:
		if zzDelivered(r) {
			close(stop)
			<-done
			cancel()
			t.Fatalf("output delivered while triggers streamed faster than the window: %v", r)
		}
	case <-time.After(3*zzQuiet + 3*time.Second):
		close(stop)
		<-done
		cancel()
		t.Fatal("receive never returned during a continuous stream")
	}
	cancel()
	close(stop)
	<-done

	// After the stream pauses, exactly one output should now be available.
	ctx2, cancel2 := context.WithCancel(context.Background())
	defer cancel2()
	select {
	case r := <-a.recvAsync(ctx2):
		if !zzDelivered(r) {
			t.Fatalf("after the stream paused, expected one output, got %v", r)
		}
	case <-time.After(zzQuiet + 3*time.Second):
		t.Fatal("after the stream paused, no debounced output was emitted")
	}
}

// A receive whose context is cancelled before any trigger returns due to the
// cancellation, NOT a phantom output.
func TestZZCancelledReceiveNoPhantom(t *testing.T) {
	closeName, _ := zzDiscoverClose(t)
	a := zzClassify(t)
	defer a.call(closeName)

	ctx, cancel := context.WithCancel(context.Background())
	res := a.recvAsync(ctx) // nothing triggered; blocks
	time.Sleep(20 * time.Millisecond)
	cancel() // caller abandons the receive
	select {
	case r := <-res:
		if zzDelivered(r) {
			t.Fatalf("cancelled receive delivered a phantom output: %v", r)
		}
	case <-time.After(3 * time.Second):
		t.Fatal("cancelled receive did not return")
	}
}

// Close while a consumer is blocked on receive -> the receive returns.
func TestZZCloseUnblocksReceive(t *testing.T) {
	closeName, _ := zzDiscoverClose(t)
	a := zzClassify(t)

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	res := a.recvAsync(ctx) // blocked, nothing triggered
	time.Sleep(20 * time.Millisecond)
	a.call(closeName)
	select {
	case <-res: // any return (value or not) acceptable; hanging is not
	case <-time.After(3 * time.Second):
		t.Fatal("receive did not unblock when the debouncer was closed")
	}
}

// Submitting a trigger after close must not panic.
func TestZZTriggerAfterCloseNoPanic(t *testing.T) {
	closeName, trigName := zzDiscoverClose(t)
	a := zzClassify(t)
	a.call(closeName)
	defer func() {
		if r := recover(); r != nil {
			t.Fatalf("trigger after close panicked: %v", r)
		}
	}()
	a.call(trigName)
	a.call(trigName)
}

// Repeated create/use/close cycles must not leak goroutines.
func TestZZNoGoroutineLeak(t *testing.T) {
	closeName, trigName := zzDiscoverClose(t)
	base := zzNumGoroutineDebounce()
	var wg sync.WaitGroup
	for c := 0; c < 30; c++ {
		a := zzClassify(t)
		for i := 0; i < 3; i++ {
			a.call(trigName)
		}
		ctx, cancel := context.WithCancel(context.Background())
		wg.Add(1)
		go func() {
			defer wg.Done()
			<-a.recvAsync(ctx)
		}()
		// consume the debounced output deterministically
		time.Sleep(zzQuiet + 30*time.Millisecond)
		cancel()
		a.call(closeName)
	}
	wg.Wait()
	deadline := time.Now().Add(3 * time.Second)
	after := zzNumGoroutineDebounce()
	for time.Now().Before(deadline) && after > base+100 {
		time.Sleep(50 * time.Millisecond)
		after = zzNumGoroutineDebounce()
	}
	if after > base+100 {
		t.Fatalf("goroutine leak suspected across create/use/close cycles: base=%d after=%d", base, after)
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
    assert os.path.isfile(DEBOUNCE_GO), (
        "missing deliverable: lib/channels/debounce.go"
    )
    tmpdir = os.path.join(REPO_DIR, ".zz_debounce_ctorfind")
    os.makedirs(tmpdir, exist_ok=True)
    try:
        with open(os.path.join(tmpdir, "main.go"), "w") as fh:
            fh.write(CTOR_FINDER_SRC)
        with open(os.path.join(tmpdir, "go.mod"), "w") as fh:
            fh.write("module zzdebouncectorfind\n\ngo 1.21\n")
        proc = subprocess.run(
            ["go", "run", ".", DEBOUNCE_GO],
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
            "and returning a type declared in debounce.go) found; stdout="
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
         "-v", "./lib/channels/"],
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

    def test_l1_debounce_file_exists(self):
        """L1: the deliverable lib/channels/debounce.go must exist."""
        assert os.path.isfile(DEBOUNCE_GO), (
            "missing required deliverable: lib/channels/debounce.go"
        )

    def test_l1_in_channels_package(self):
        """L1: debounce.go must declare package channels."""
        with open(DEBOUNCE_GO) as fh:
            head = fh.read()
        assert "package channels" in head, (
            "debounce.go must be in package channels"
        )

    def test_l1_test_file_exists(self):
        """L1: the agent must provide debounce_test.go with the scenarios."""
        test_file = os.path.join(CHANNELS_DIR, "debounce_test.go")
        assert os.path.isfile(test_file), (
            "missing required deliverable: lib/channels/debounce_test.go"
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

    def test_l1_duration_constructor_discoverable(self):
        """L1: an exported constructor taking a time.Duration must exist."""
        _require_go()
        ctor = _find_constructor()
        assert ctor and ctor[0].isupper(), (
            f"constructor {ctor!r} must be exported (capitalized)"
        )

    # ----------------------------- L2 ----------------------------- #

    def test_l2_api_surface_classifiable(self):
        """L2: the trigger / receive(ctx) / close surface is discoverable and
        close is behaviorally distinct from trigger."""
        _assert_driver_pass(_run_driver("TestZZDiscoverAPI"), "discover-api")

    def test_l2_burst_coalesces_to_single_output(self):
        """L2: a burst of triggers within one quiet window yields exactly one
        output (a per-trigger emitter fails the second-receive check)."""
        _assert_driver_pass(
            _run_driver("TestZZBurstCoalescesToOne"), "burst-coalesces"
        )

    def test_l2_no_premature_output_before_window(self):
        """L2: no output is delivered before the quiet window elapses (a stub
        that emits immediately fails here)."""
        _assert_driver_pass(
            _run_driver("TestZZNoPrematureOutput"), "no-premature-output"
        )

    def test_l2_second_independent_debounce_cycle(self):
        """L2: after consuming one output, a second trigger yields a second
        independent output."""
        _assert_driver_pass(_run_driver("TestZZSecondCycle"), "second-cycle")

    def test_l2_continuous_stream_suppresses_until_pause(self):
        """L2: triggers spaced closer than the window emit nothing until the
        stream pauses, then exactly one output is emitted."""
        _assert_driver_pass(
            _run_driver("TestZZContinuousStreamSuppressed"), "continuous-stream"
        )

    def test_l2_cancelled_receive_no_phantom(self):
        """L2: a context-cancelled receive returns due to cancellation, not a
        phantom output."""
        _assert_driver_pass(
            _run_driver("TestZZCancelledReceiveNoPhantom"), "cancel-receive"
        )

    def test_l2_close_unblocks_blocked_receive(self):
        """L2: closing the debouncer unblocks a consumer blocked on receive."""
        _assert_driver_pass(
            _run_driver("TestZZCloseUnblocksReceive"), "close-unblocks"
        )

    def test_l2_trigger_after_close_no_panic(self):
        """L2: submitting a trigger after close must not panic."""
        _assert_driver_pass(
            _run_driver("TestZZTriggerAfterCloseNoPanic"), "trigger-after-close"
        )

    def test_l2_no_goroutine_leak_across_cycles(self):
        """L2: repeated create/use/close cycles do not leak goroutines."""
        _assert_driver_pass(
            _run_driver("TestZZNoGoroutineLeak"), "no-goroutine-leak"
        )

    def test_l2_agents_own_race_suite_passes(self):
        """L2: the documented native acceptance command
        `go test -race -run 'Debounce' ./lib/channels/` passes clean (no
        failures, no race, no goroutine-leak reports), and Debounce-named tests
        actually ran."""
        _require_go()
        proc = subprocess.run(
            ["go", "test", "-race", "-count=1", "-run", "Debounce",
             "./lib/channels/"],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=GO_TEST_TIMEOUT,
            env={**os.environ, "GOFLAGS": "-buildvcs=false"},
        )
        combined = proc.stdout + "\n" + proc.stderr
        assert proc.returncode == 0, (
            "go test -race -run Debounce ./lib/channels/ failed:\n" + combined
        )
        assert "DATA RACE" not in combined, "data race reported:\n" + combined
        assert "panic:" not in combined, "panic reported:\n" + combined
        assert "no test files" not in combined, (
            "no Debounce tests found in lib/channels/:\n" + combined
        )


# keep linters quiet about the imported helper
_ = textwrap
