"""Benchmark test for skill: go-concurrency-patterns (variant ext10).

Task: Add a *one-shot future / promise* helper to consul's ``lib/channels``
package (new file ``lib/channels/future.go`` in package ``channels``). The
future carries a generic value of type ``T`` plus an error, is produced exactly
once, and supports:

  * a constructor returning an uncompleted future of ``T``,
  * a single "complete" operation (value + error) where the first completion
    wins and subsequent completions are harmless no-ops,
  * a context-aware blocking "get" that returns the completed (value, error) or
    the context error when cancelled first,
  * a non-blocking "poll" that reports whether the future is completed and, if
    so, returns its value and error without blocking.

The agent chooses the actual method/field names, so this test does NOT hard-code
them. Instead it:

  * uses a tiny Go AST program to discover the exported generic constructor,
  * generates an independent Go *reflection driver* test that classifies the
    complete / get / poll operations by signature,
  * compiles and runs that driver under ``go test -race`` to deep-validate the
    documented behaviors (blocked getters released on completion observing the
    same result, immediate get after completion, context-cancelled get,
    first-completion-wins on double completion without panic, poll before/after
    completion), plus a goroutine-leak check.

A naive / stub / files-that-merely-look-related solution fails because each
behavior is exercised independently with this test's own assertions, not by
trusting the agent's own ``future_test.go``.

Native acceptance command driven by L2:
    go test -race -run 'Future' ./lib/channels/
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
FUTURE_GO = os.path.join(CHANNELS_DIR, "future.go")

# Helper Go files dropped into the package while testing. Unique enough to never
# collide with agent code; cleaned up afterwards.
DRIVER_TEST = os.path.join(CHANNELS_DIR, "zz_future_driver_test.go")
DRIVER_HELP = os.path.join(CHANNELS_DIR, "zz_future_helper_test.go")

GO_BUILD_TIMEOUT = 300
GO_TEST_TIMEOUT = 420


# --------------------------------------------------------------------------- #
# Embedded Go: AST constructor finder.
# Prints "<CtorName>\t<TypeName>" for each exported, no-required-arg, top-level
# function whose single return value is a generic type declared in the file.
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

func isGeneric(e ast.Expr) bool {
	switch t := e.(type) {
	case *ast.StarExpr:
		return isGeneric(t.X)
	case *ast.IndexExpr, *ast.IndexListExpr:
		_ = t
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
	gen := map[string]bool{}
	for _, d := range f.Decls {
		if gd, ok := d.(*ast.GenDecl); ok {
			for _, s := range gd.Specs {
				if ts, ok := s.(*ast.TypeSpec); ok {
					if ts.TypeParams != nil && len(ts.TypeParams.List) > 0 {
						gen[ts.Name.Name] = true
					}
				}
			}
		}
	}
	for _, d := range f.Decls {
		if fn, ok := d.(*ast.FuncDecl); ok && fn.Recv == nil && fn.Name.IsExported() {
			if fn.Type.Params != nil && len(fn.Type.Params.List) > 0 {
				continue
			}
			if fn.Type.Results == nil || len(fn.Type.Results.List) != 1 {
				continue
			}
			r := fn.Type.Results.List[0].Type
			name := texpr(r)
			if isGeneric(r) && gen[name] {
				fmt.Printf("%s\t%s\n", fn.Name.Name, name)
			}
		}
	}
}
'''


# --------------------------------------------------------------------------- #
# Embedded Go: helper exposing the live goroutine count.
# --------------------------------------------------------------------------- #
DRIVER_HELPER_SRC = r'''
package channels

import "runtime"

func zzNumGoroutine() int { return runtime.NumGoroutine() }
'''


# --------------------------------------------------------------------------- #
# Embedded Go: the reflection driver test. ``__CTOR__`` is substituted with the
# discovered constructor name (instantiated with int). All operations other than
# the constructor are discovered at runtime by signature, so the agent's chosen
# method names do not matter.
#
# Classification rules (future of int + error):
#   complete : method, exactly one INPUT that is int (the value). A second input
#              that is the error type is accepted (value + error). Used to set
#              the result. (At least one such method must exist.)
#   get      : method whose FIRST input is context.Context and whose results
#              include an int (the value) and an error.
#   poll     : method with NO context input, that returns a bool (completed flag)
#              and an int (value); error in the results is accepted.
# --------------------------------------------------------------------------- #
DRIVER_TEST_SRC = r'''
package channels

import (
	"context"
	"errors"
	"reflect"
	"sync"
	"testing"
	"time"
)

var zzCtxType = reflect.TypeOf((*context.Context)(nil)).Elem()
var zzErrType = reflect.TypeOf((*error)(nil)).Elem()
var zzIntType = reflect.TypeOf(int(0))

type zzAPI struct {
	f            reflect.Value
	complete     string // sets (value, [error])
	completeHasE bool   // complete takes an error arg too
	get          string // context-aware blocking get
	getHasE      bool   // get returns an error
	poll         string // non-blocking poll
	pollHasE     bool   // poll returns an error
}

func zzNew() reflect.Value {
	return reflect.ValueOf(__CTOR__[int]())
}

func zzImplementsErr(t reflect.Type) bool {
	return t == zzErrType || t.Implements(zzErrType)
}

func zzClassify(t *testing.T) *zzAPI {
	t.Helper()
	f := zzNew()
	if !f.IsValid() {
		t.Fatalf("constructor returned an invalid value")
	}
	ft := f.Type()
	a := &zzAPI{f: f}

	for i := 0; i < ft.NumMethod(); i++ {
		m := ft.Method(i)
		mt := m.Func.Type()
		nin := mt.NumIn() - 1 // minus receiver
		nout := mt.NumOut()

		inHasCtx := nin >= 1 && mt.In(1) == zzCtxType
		inHasInt := false
		inHasErr := false
		for j := 1; j <= nin; j++ {
			if mt.In(j) == zzIntType {
				inHasInt = true
			}
			if zzImplementsErr(mt.In(j)) {
				inHasErr = true
			}
		}
		outHasInt := false
		outHasBool := false
		outHasErr := false
		for j := 0; j < nout; j++ {
			switch {
			case mt.Out(j) == zzIntType:
				outHasInt = true
			case mt.Out(j).Kind() == reflect.Bool:
				outHasBool = true
			case zzImplementsErr(mt.Out(j)):
				outHasErr = true
			}
		}

		// complete: takes the int value as input, does not take a context.
		// Prefer the variant that also takes an error (value+error completion).
		if !inHasCtx && inHasInt {
			if a.complete == "" || (inHasErr && !a.completeHasE) {
				a.complete = m.Name
				a.completeHasE = inHasErr
			}
			continue
		}

		// get: context-aware blocking retrieval returning the int value.
		if inHasCtx && outHasInt {
			a.get = m.Name
			a.getHasE = outHasErr
			continue
		}

		// poll: no context input, returns a bool (completed) plus the int value.
		if !inHasCtx && nin == 0 && outHasBool && outHasInt {
			a.poll = m.Name
			a.pollHasE = outHasErr
			continue
		}
	}

	if a.complete == "" {
		t.Fatalf("no complete-like method (takes the int value, no context) on %s", ft)
	}
	if a.get == "" {
		t.Fatalf("no get-like method (context.Context input, returns the int value) on %s", ft)
	}
	if a.poll == "" {
		t.Fatalf("no poll-like method (no context, returns bool+int) on %s", ft)
	}
	t.Logf("discovered api: complete=%s(+err=%v) get=%s(+err=%v) poll=%s(+err=%v)",
		a.complete, a.completeHasE, a.get, a.getHasE, a.poll, a.pollHasE)
	return a
}

// doComplete invokes the completion op with value v and error e (e may be nil).
func (a *zzAPI) doComplete(v int, e error) {
	args := []reflect.Value{reflect.ValueOf(v)}
	if a.completeHasE {
		ev := reflect.New(zzErrType).Elem()
		if e != nil {
			ev.Set(reflect.ValueOf(e))
		}
		args = append(args, ev)
	}
	a.f.MethodByName(a.complete).Call(args)
}

// doGet performs a blocking get with the given context. Returns (value, errIsNil).
func (a *zzAPI) doGet(ctx context.Context) (int, error) {
	res := a.f.MethodByName(a.get).Call([]reflect.Value{reflect.ValueOf(ctx)})
	return zzExtractValErr(res)
}

// doPoll performs a non-blocking poll. Returns (completed, value, errIsNil).
func (a *zzAPI) doPoll() (bool, int, error) {
	res := a.f.MethodByName(a.poll).Call(nil)
	done := false
	for _, r := range res {
		if r.Kind() == reflect.Bool {
			done = r.Bool()
		}
	}
	v, e := zzExtractValErr(res)
	return done, v, e
}

func zzExtractValErr(res []reflect.Value) (int, error) {
	val := 0
	var err error
	for _, r := range res {
		switch {
		case r.Kind() == reflect.Int || r.Kind() == reflect.Int8 ||
			r.Kind() == reflect.Int16 || r.Kind() == reflect.Int32 ||
			r.Kind() == reflect.Int64:
			val = int(r.Int())
		case r.Kind() == reflect.Interface && r.Type().Implements(zzErrType):
			if !r.IsNil() {
				err = r.Interface().(error)
			}
		}
	}
	return val, err
}

type zzGetResult struct {
	val int
	err error
}

func (a *zzAPI) getAsync(ctx context.Context) <-chan zzGetResult {
	out := make(chan zzGetResult, 1)
	go func() {
		v, e := a.doGet(ctx)
		out <- zzGetResult{v, e}
	}()
	return out
}

// --- scenario tests (run individually by the Python harness via -run) --- //

// Many blocked getters are all released by a single completion and observe the
// same value and (nil) error.
func TestFutureBlockedGettersReleased(t *testing.T) {
	a := zzClassify(t)
	const n = 50
	results := make([]<-chan zzGetResult, n)
	ctx := context.Background()
	// Start getters that must block (nothing completed yet).
	for i := 0; i < n; i++ {
		results[i] = a.getAsync(ctx)
	}
	// Ensure they are genuinely waiting: poll must report not-completed.
	if done, _, _ := a.doPoll(); done {
		t.Fatalf("future reported completed before any complete call")
	}
	a.doComplete(42, nil)
	for i := 0; i < n; i++ {
		select {
		case r := <-results[i]:
			if r.err != nil {
				t.Fatalf("getter %d got unexpected error %v", i, r.err)
			}
			if r.val != 42 {
				t.Fatalf("getter %d observed %d, want 42", i, r.val)
			}
		case <-time.After(5 * time.Second):
			t.Fatalf("getter %d not released after completion", i)
		}
	}
}

// Completing first, then getting, returns immediately with the result.
func TestFutureGetAfterComplete(t *testing.T) {
	a := zzClassify(t)
	a.doComplete(7, nil)
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	done := make(chan zzGetResult, 1)
	go func() {
		v, e := a.doGet(ctx)
		done <- zzGetResult{v, e}
	}()
	select {
	case r := <-done:
		if r.err != nil {
			t.Fatalf("get on completed future returned error %v", r.err)
		}
		if r.val != 7 {
			t.Fatalf("get on completed future returned %d, want 7", r.val)
		}
	case <-time.After(5 * time.Second):
		t.Fatal("get on already-completed future did not return promptly")
	}
}

// The completed error is propagated to getters.
func TestFutureCompleteWithError(t *testing.T) {
	a := zzClassify(t)
	if !a.completeHasE {
		t.Skip("completion does not accept an error argument")
	}
	sentinel := errors.New("zz-sentinel-boom")
	a.doComplete(0, sentinel)
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	_, e := a.doGet(ctx)
	if e == nil {
		t.Fatalf("get did not propagate the completion error")
	}
	if e.Error() != sentinel.Error() {
		t.Fatalf("get returned error %q, want %q", e.Error(), sentinel.Error())
	}
}

// A get whose context is cancelled before completion returns the context error;
// a later completion still works for other consumers.
func TestFutureContextCancelled(t *testing.T) {
	a := zzClassify(t)
	ctx, cancel := context.WithCancel(context.Background())
	res := a.getAsync(ctx) // nothing completed; blocks
	cancel()               // caller abandons the get
	select {
	case r := <-res:
		if r.err == nil {
			t.Fatalf("cancelled get must return a non-nil (context) error, got val=%d", r.val)
		}
		if !errors.Is(r.err, context.Canceled) {
			t.Fatalf("cancelled get returned %v, want context.Canceled", r.err)
		}
	case <-time.After(5 * time.Second):
		t.Fatal("cancelled get did not return")
	}
	// A later completion must still be observable by a fresh getter.
	a.doComplete(99, nil)
	ctx2, cancel2 := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel2()
	v, e := a.doGet(ctx2)
	if e != nil || v != 99 {
		t.Fatalf("after a cancelled getter, completion broken: v=%d err=%v", v, e)
	}
}

// First completion wins; the second completion is a no-op and must not panic.
func TestFutureFirstCompletionWins(t *testing.T) {
	a := zzClassify(t)
	defer func() {
		if r := recover(); r != nil {
			t.Fatalf("double completion panicked: %v", r)
		}
	}()
	a.doComplete(11, nil)
	a.doComplete(22, errors.New("should-be-ignored")) // must not overwrite
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	v, e := a.doGet(ctx)
	if e != nil {
		t.Fatalf("first-completion-wins violated: got error %v, want nil", e)
	}
	if v != 11 {
		t.Fatalf("first-completion-wins violated: got %d, want 11", v)
	}
	// poll must also see the first result.
	done, pv, pe := a.doPoll()
	if !done {
		t.Fatalf("poll after completion reported not-completed")
	}
	if pe != nil || pv != 11 {
		t.Fatalf("poll observed wrong result: v=%d err=%v, want 11/nil", pv, pe)
	}
}

// Poll before completion reports not-completed; poll after reports completed
// with the value.
func TestFuturePollBeforeAndAfter(t *testing.T) {
	a := zzClassify(t)
	if done, _, _ := a.doPoll(); done {
		t.Fatalf("poll reported completed on a fresh future")
	}
	a.doComplete(314, nil)
	done, v, e := a.doPoll()
	if !done {
		t.Fatalf("poll reported not-completed after a completion")
	}
	if e != nil {
		t.Fatalf("poll returned unexpected error %v", e)
	}
	if v != 314 {
		t.Fatalf("poll returned %d, want 314", v)
	}
}

// Concurrent complete/get/poll from many goroutines: every consumer observes the
// single consistent value once completion occurs, with no data race.
func TestFutureConcurrentConsistency(t *testing.T) {
	a := zzClassify(t)
	const want = 12345
	var wg sync.WaitGroup
	start := make(chan struct{})

	// many getters
	for i := 0; i < 32; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			<-start
			ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
			defer cancel()
			v, e := a.doGet(ctx)
			if e != nil {
				t.Errorf("getter observed error %v", e)
				return
			}
			if v != want {
				t.Errorf("getter observed %d, want %d", v, want)
			}
		}()
	}
	// many pollers (must never see a torn/partial value: if completed, value==want)
	for i := 0; i < 32; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			<-start
			deadline := time.Now().Add(5 * time.Second)
			for time.Now().Before(deadline) {
				done, v, e := a.doPoll()
				if done {
					if e != nil {
						t.Errorf("poller observed error %v", e)
					}
					if v != want {
						t.Errorf("poller observed torn value %d, want %d", v, want)
					}
					return
				}
			}
		}()
	}
	// several racing completers; first wins.
	for i := 0; i < 4; i++ {
		wg.Add(1)
		val := want + i // only the first (want) is correct; others must be ignored
		if i == 0 {
			val = want
		} else {
			val = want + 1000 + i
		}
		go func(v int) {
			defer wg.Done()
			<-start
			if v == want {
				a.doComplete(v, nil)
			} else {
				// these may or may not run first; correctness is guaranteed by
				// the single completer below racing them is intentional.
				a.doComplete(v, nil)
			}
		}(val)
	}
	close(start)
	wg.Wait()
}

// No internal goroutine remains running after completion and all getters return.
func TestFutureNoGoroutineLeak(t *testing.T) {
	base := zzNumGoroutine()
	var wg sync.WaitGroup
	for c := 0; c < 60; c++ {
		a := zzClassify(t)
		ctx, cancel := context.WithCancel(context.Background())
		for i := 0; i < 4; i++ {
			wg.Add(1)
			go func() {
				defer wg.Done()
				a.doGet(ctx)
			}()
		}
		a.doComplete(c, nil)
		cancel()
	}
	wg.Wait()
	deadline := time.Now().Add(2 * time.Second)
	after := zzNumGoroutine()
	for time.Now().Before(deadline) && after > base+100 {
		time.Sleep(50 * time.Millisecond)
		after = zzNumGoroutine()
	}
	if after > base+100 {
		t.Fatalf("goroutine leak suspected across complete cycles: base=%d after=%d", base, after)
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
    assert os.path.isfile(FUTURE_GO), (
        "missing deliverable: lib/channels/future.go"
    )
    tmpdir = os.path.join(REPO_DIR, ".zz_ctorfind_future")
    os.makedirs(tmpdir, exist_ok=True)
    try:
        with open(os.path.join(tmpdir, "main.go"), "w") as fh:
            fh.write(CTOR_FINDER_SRC)
        with open(os.path.join(tmpdir, "go.mod"), "w") as fh:
            fh.write("module zzctorfindfuture\n\ngo 1.21\n")
        proc = subprocess.run(
            ["go", "run", ".", FUTURE_GO],
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
            "no exported generic constructor (a top-level func returning a "
            "generic future type) found in future.go; stdout="
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

    def test_l1_future_file_exists(self):
        """L1: the deliverable lib/channels/future.go must exist."""
        assert os.path.isfile(FUTURE_GO), (
            "missing required deliverable: lib/channels/future.go"
        )

    def test_l1_in_channels_package(self):
        """L1: future.go must declare package channels."""
        with open(FUTURE_GO) as fh:
            head = fh.read()
        assert "package channels" in head, (
            "future.go must be in package channels"
        )

    def test_l1_test_file_exists(self):
        """L1: the agent must provide future_test.go with scenarios."""
        test_file = os.path.join(CHANNELS_DIR, "future_test.go")
        assert os.path.isfile(test_file), (
            "missing required deliverable: lib/channels/future_test.go"
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

    def test_l1_exported_generic_constructor_discoverable(self):
        """L1: an exported generic constructor must be discoverable via AST."""
        _require_go()
        ctor = _find_constructor()
        assert ctor and ctor[0].isupper(), (
            f"constructor {ctor!r} must be exported (capitalized)"
        )

    # ----------------------------- L2 ----------------------------- #

    def test_l2_blocked_getters_released_on_completion(self):
        """L2: many blocked getters are all released by one completion and
        observe the same value and (nil) error."""
        _assert_driver_pass(
            _run_driver("TestFutureBlockedGettersReleased"),
            "blocked-getters-released",
        )

    def test_l2_get_after_complete_returns_immediately(self):
        """L2: a get on an already-completed future returns the result promptly."""
        _assert_driver_pass(
            _run_driver("TestFutureGetAfterComplete"), "get-after-complete"
        )

    def test_l2_complete_with_error_propagates(self):
        """L2: a completion error is propagated to getters."""
        _assert_driver_pass(
            _run_driver("TestFutureCompleteWithError"), "complete-with-error"
        )

    def test_l2_context_cancelled_get_returns_ctx_error(self):
        """L2: a get cancelled before completion returns the context error, and
        a later completion still works for other consumers."""
        _assert_driver_pass(
            _run_driver("TestFutureContextCancelled"), "context-cancelled-get"
        )

    def test_l2_first_completion_wins_no_panic(self):
        """L2: the first completion wins; a second completion is a no-op and
        must not panic; pollers/getters see the first result."""
        _assert_driver_pass(
            _run_driver("TestFutureFirstCompletionWins"),
            "first-completion-wins",
        )

    def test_l2_poll_before_and_after_completion(self):
        """L2: poll reports not-completed before completion and completed with
        the value afterwards."""
        _assert_driver_pass(
            _run_driver("TestFuturePollBeforeAndAfter"), "poll-before-after"
        )

    def test_l2_concurrent_consistency_no_race(self):
        """L2: concurrent complete/get/poll from many goroutines observe a
        single consistent value with no data race or torn read."""
        _assert_driver_pass(
            _run_driver("TestFutureConcurrentConsistency"),
            "concurrent-consistency",
        )

    def test_l2_no_goroutine_leak_across_cycles(self):
        """L2: repeated complete cycles do not leak internal goroutines."""
        _assert_driver_pass(
            _run_driver("TestFutureNoGoroutineLeak"), "no-goroutine-leak"
        )

    def test_l2_agents_own_race_suite_passes(self):
        """L2: the native acceptance command
        `go test -race -run 'Future' ./lib/channels/` passes clean (no
        failures, no race, no goroutine-leak reports), and the agent actually
        provided Future-named tests that ran."""
        _require_go()
        proc = subprocess.run(
            ["go", "test", "-race", "-count=1", "-run", "Future",
             "./lib/channels/"],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=GO_TEST_TIMEOUT,
            env={**os.environ, "GOFLAGS": "-buildvcs=false"},
        )
        combined = proc.stdout + "\n" + proc.stderr
        assert proc.returncode == 0, (
            "go test -race -run Future ./lib/channels/ failed:\n" + combined
        )
        assert "DATA RACE" not in combined, "data race reported:\n" + combined
        assert "panic:" not in combined, "panic reported:\n" + combined
        assert "no test files" not in combined, (
            "no Future tests found in lib/channels/:\n" + combined
        )


# keep linters quiet about the textwrap import guard
_ = textwrap
