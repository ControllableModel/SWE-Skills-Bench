"""Benchmark test for skill: go-concurrency-patterns.

Task: Add a latest-value, non-blocking fan-out broadcaster to consul's
``lib/channels`` package (new file ``lib/channels/broadcaster.go`` in package
``channels``). The public API method names are chosen by the agent, so this
test does NOT hard-code them. Instead it:

  * uses a tiny Go AST program to discover the exported generic constructor,
  * generates an independent Go *reflection driver* test that classifies the
    publish / subscribe / receive / release / shutdown operations by signature,
  * compiles and runs that driver under ``go test -race`` to deep-validate the
    documented behaviors (latest-wins coalescing, fan-out, non-blocking publish
    under a slow consumer, caller-cancelled receive, shutdown unblocking, and
    publish-after-shutdown not panicking), plus a goroutine-leak check.

A naive / stub / files-that-merely-look-related solution fails because the
behavior is exercised independently with this test's own assertions, not by
trusting the agent's own ``broadcaster_test.go``.
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
BROADCASTER_GO = os.path.join(CHANNELS_DIR, "broadcaster.go")

# Names of the helper Go files we drop into the package while testing. They are
# unique enough to never collide with agent code and are cleaned up after.
DRIVER_TEST = os.path.join(CHANNELS_DIR, "zz_bench_driver_test.go")
DRIVER_HELP = os.path.join(CHANNELS_DIR, "zz_bench_helper_test.go")

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
# Embedded Go: the reflection driver test. ``__CTOR__`` is substituted with the
# discovered constructor name (instantiated with int). All operations other than
# the constructor are discovered at runtime by signature, so the agent's chosen
# method names do not matter.
# --------------------------------------------------------------------------- #
DRIVER_HELPER_SRC = r'''
package channels

import "runtime"

func zzNumGoroutine() int { return runtime.NumGoroutine() }
'''

DRIVER_TEST_SRC = r'''
package channels

import (
	"context"
	"reflect"
	"sync"
	"testing"
	"time"
)

var zzCtxType = reflect.TypeOf((*context.Context)(nil)).Elem()
var zzIntType = reflect.TypeOf(int(0))

type zzAPI struct {
	b          reflect.Value
	publish    string
	subscribe  string
	shutdown   string
	subType    reflect.Type
	recv       string
	recvCancel reflect.Type // type of the cancellation param, or nil if none
	release    string
}

func zzNew() reflect.Value {
	return reflect.ValueOf(__CTOR__[int]())
}

func zzClassify(t *testing.T) *zzAPI {
	t.Helper()
	b := zzNew()
	if !b.IsValid() {
		t.Fatalf("constructor returned an invalid value")
	}
	bt := b.Type()
	a := &zzAPI{b: b}

	// subscribe: 0 input args, exactly one result that itself has methods and
	// is not the broadcaster type.
	for i := 0; i < bt.NumMethod(); i++ {
		m := bt.Method(i)
		mt := m.Func.Type()
		if mt.NumIn()-1 == 0 && mt.NumOut() == 1 {
			rt := mt.Out(0)
			if rt.NumMethod() > 0 && rt != bt {
				a.subscribe = m.Name
				a.subType = rt
			}
		}
	}
	if a.subscribe == "" {
		t.Fatalf("no subscribe-like method (0 args -> 1 result with methods) on %s", bt)
	}

	// publish: exactly one input arg of the value type (int), no result.
	for i := 0; i < bt.NumMethod(); i++ {
		m := bt.Method(i)
		mt := m.Func.Type()
		if mt.NumIn()-1 == 1 && mt.NumOut() == 0 && mt.In(1) == zzIntType {
			a.publish = m.Name
		}
	}
	if a.publish == "" {
		t.Fatalf("no publish-like method (one int arg, no result) on %s", bt)
	}

	// shutdown: 0 input args, 0 results, not the subscribe method.
	for i := 0; i < bt.NumMethod(); i++ {
		m := bt.Method(i)
		mt := m.Func.Type()
		if mt.NumIn()-1 == 0 && mt.NumOut() == 0 && m.Name != a.subscribe {
			a.shutdown = m.Name
		}
	}
	if a.shutdown == "" {
		t.Fatalf("no shutdown-like method (no args, no result) on %s", bt)
	}

	// receive (returns value type) + release (no args, no result) on the sub.
	st := a.subType
	for i := 0; i < st.NumMethod(); i++ {
		m := st.Method(i)
		mt := m.Func.Type()
		nin := mt.NumIn() - 1
		nout := mt.NumOut()
		retHasInt := false
		for j := 0; j < nout; j++ {
			if mt.Out(j) == zzIntType {
				retHasInt = true
			}
		}
		if retHasInt && nout >= 1 {
			a.recv = m.Name
			if nin >= 1 {
				a.recvCancel = mt.In(1)
			}
		}
		if nin == 0 && nout == 0 {
			a.release = m.Name
		}
	}
	if a.recv == "" {
		t.Fatalf("no receive-like method (returns the value type) on subscription %s", st)
	}
	if a.release == "" {
		t.Fatalf("no release-like method (no args, no result) on subscription %s", st)
	}
	t.Logf("discovered api: pub=%s sub=%s shut=%s recv=%s cancel=%v rel=%s",
		a.publish, a.subscribe, a.shutdown, a.recv, a.recvCancel, a.release)
	return a
}

func (a *zzAPI) pub(v int)            { a.b.MethodByName(a.publish).Call([]reflect.Value{reflect.ValueOf(v)}) }
func (a *zzAPI) sub() reflect.Value   { return a.b.MethodByName(a.subscribe).Call(nil)[0] }
func (a *zzAPI) shut()                { a.b.MethodByName(a.shutdown).Call(nil) }
func (a *zzAPI) rel(s reflect.Value)  { s.MethodByName(a.release).Call(nil) }

// makeCancel builds the cancellation arg (context or chan) and a cancel func.
func (a *zzAPI) makeCancel() (reflect.Value, func()) {
	if a.recvCancel == nil {
		return reflect.Value{}, func() {}
	}
	if a.recvCancel == zzCtxType {
		ctx, cancel := context.WithCancel(context.Background())
		return reflect.ValueOf(ctx), cancel
	}
	if a.recvCancel.Kind() == reflect.Chan {
		ch := reflect.MakeChan(reflect.ChanOf(reflect.BothDir, a.recvCancel.Elem()), 0)
		var mu sync.Mutex
		closed := false
		return ch, func() {
			mu.Lock()
			defer mu.Unlock()
			if !closed {
				closed = true
				ch.Close()
			}
		}
	}
	return reflect.Zero(a.recvCancel), func() {}
}

func (a *zzAPI) recvAsync(s reflect.Value, cancelArg reflect.Value) <-chan []reflect.Value {
	out := make(chan []reflect.Value, 1)
	m := s.MethodByName(a.recv)
	go func() {
		var args []reflect.Value
		if a.recvCancel != nil {
			args = []reflect.Value{cancelArg}
		}
		out <- m.Call(args)
	}()
	return out
}

func zzErrIsNil(res []reflect.Value) bool {
	for _, r := range res {
		if r.Kind() == reflect.Interface && r.Type().Implements(
			reflect.TypeOf((*error)(nil)).Elem()) {
			return r.IsNil()
		}
	}
	return true
}

// zzDelivered reports the int value and whether the receive actually delivered
// a value (a present-flag bool, if any, is true AND any error result is nil).
func zzDelivered(res []reflect.Value) (int, bool) {
	val := 0
	ok := true
	for _, r := range res {
		switch r.Kind() {
		case reflect.Int, reflect.Int8, reflect.Int16, reflect.Int32, reflect.Int64:
			val = int(r.Int())
		case reflect.Bool:
			ok = r.Bool()
		}
	}
	return val, ok && zzErrIsNil(res)
}

// --- scenario tests (run individually by the Python harness via -run) --- //

func TestZZLatestWins(t *testing.T) {
	a := zzClassify(t)
	s := a.sub()
	for i := 0; i < 500; i++ {
		a.pub(i)
	}
	ca, cancel := a.makeCancel()
	defer cancel()
	res := a.recvAsync(s, ca)
	select {
	case r := <-res:
		v, ok := zzDelivered(r)
		if !ok {
			t.Fatalf("expected a delivered value after rapid publishes, got %v", r)
		}
		if v != 499 {
			t.Fatalf("latest-wins violated: want most recent 499, got %d", v)
		}
	case <-time.After(5 * time.Second):
		t.Fatal("receive timed out after rapid publishes")
	}
	a.shut()
}

func TestZZSubscribeThenPublish(t *testing.T) {
	a := zzClassify(t)
	s := a.sub() // subscription created BEFORE publish must observe the publish
	a.pub(7)
	ca, cancel := a.makeCancel()
	defer cancel()
	res := a.recvAsync(s, ca)
	select {
	case r := <-res:
		v, ok := zzDelivered(r)
		if !ok || v != 7 {
			t.Fatalf("want delivered 7, got v=%d ok=%v (%v)", v, ok, r)
		}
	case <-time.After(5 * time.Second):
		t.Fatal("receive timed out")
	}
	a.shut()
}

func TestZZFanout(t *testing.T) {
	a := zzClassify(t)
	s1 := a.sub()
	s2 := a.sub()
	a.pub(123) // published once -> both subs observe it independently
	for idx, s := range []reflect.Value{s1, s2} {
		ca, cancel := a.makeCancel()
		res := a.recvAsync(s, ca)
		select {
		case r := <-res:
			v, ok := zzDelivered(r)
			if !ok || v != 123 {
				t.Fatalf("sub %d: want 123, got v=%d ok=%v", idx, v, ok)
			}
		case <-time.After(5 * time.Second):
			cancel()
			t.Fatalf("sub %d receive timed out", idx)
		}
		cancel()
	}
	a.shut()
}

func TestZZCancelReceive(t *testing.T) {
	a := zzClassify(t)
	if a.recvCancel == nil {
		t.Fatalf("receive operation has no cancellation parameter (required by task)")
	}
	s := a.sub()
	ca, cancel := a.makeCancel()
	res := a.recvAsync(s, ca) // nothing published; blocks
	cancel()                  // caller abandons the receive
	select {
	case r := <-res:
		if _, ok := zzDelivered(r); ok {
			t.Fatalf("cancelled receive must not deliver a value, got %v", r)
		}
	case <-time.After(5 * time.Second):
		t.Fatal("cancelled receive did not return")
	}
	a.shut()
}

func TestZZNonBlockingPublish(t *testing.T) {
	a := zzClassify(t)
	_ = a.sub() // a slow consumer that never reads
	done := make(chan struct{})
	go func() {
		for i := 0; i < 2000; i++ {
			a.pub(i)
		}
		close(done)
	}()
	select {
	case <-done:
	case <-time.After(15 * time.Second):
		t.Fatal("producer blocked: publish stalled on a non-reading consumer")
	}
	a.shut()
}

func TestZZShutdownUnblocks(t *testing.T) {
	a := zzClassify(t)
	s := a.sub()
	ca, cancel := a.makeCancel()
	defer cancel()
	res := a.recvAsync(s, ca) // blocked, nothing published
	a.shut()
	select {
	case <-res: // any return (value or not) is acceptable; hanging is not
	case <-time.After(5 * time.Second):
		t.Fatal("receive did not unblock when broadcaster was shut down")
	}
}

func TestZZPublishAfterShutdownNoPanic(t *testing.T) {
	a := zzClassify(t)
	_ = a.sub()
	a.shut()
	// Must not panic; recover guards the assertion explicitly.
	defer func() {
		if r := recover(); r != nil {
			t.Fatalf("publish after shutdown panicked: %v", r)
		}
	}()
	a.pub(1)
	a.pub(2)
}

func TestZZReleaseThenNewSubWorks(t *testing.T) {
	a := zzClassify(t)
	s := a.sub()
	a.rel(s) // released; should stop receiving further values
	a.pub(55)
	s2 := a.sub() // a fresh, active subscription
	a.pub(66)
	ca, cancel := a.makeCancel()
	defer cancel()
	res := a.recvAsync(s2, ca)
	select {
	case r := <-res:
		v, ok := zzDelivered(r)
		if !ok || v != 66 {
			t.Fatalf("new subscription want 66, got v=%d ok=%v", v, ok)
		}
	case <-time.After(5 * time.Second):
		t.Fatal("new subscription receive timed out after a release")
	}
	a.shut()
}

func TestZZNoGoroutineLeak(t *testing.T) {
	base := zzNumGoroutine()
	var wg sync.WaitGroup
	for c := 0; c < 40; c++ {
		a := zzClassify(t)
		for i := 0; i < 5; i++ {
			s := a.sub()
			a.pub(i)
			ca, cancel := a.makeCancel()
			wg.Add(1)
			go func() {
				defer wg.Done()
				<-a.recvAsync(s, ca)
			}()
			cancel()
		}
		a.shut()
	}
	wg.Wait()
	// allow scheduler to reap finished goroutines
	deadline := time.Now().Add(2 * time.Second)
	after := zzNumGoroutine()
	for time.Now().Before(deadline) && after > base+100 {
		time.Sleep(50 * time.Millisecond)
		after = zzNumGoroutine()
	}
	if after > base+100 {
		t.Fatalf("goroutine leak suspected across create/use/shutdown cycles: base=%d after=%d", base, after)
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
    assert os.path.isfile(BROADCASTER_GO), (
        "missing deliverable: lib/channels/broadcaster.go"
    )
    tmpdir = os.path.join(REPO_DIR, ".zz_ctorfind")
    os.makedirs(tmpdir, exist_ok=True)
    try:
        with open(os.path.join(tmpdir, "main.go"), "w") as fh:
            fh.write(CTOR_FINDER_SRC)
        with open(os.path.join(tmpdir, "go.mod"), "w") as fh:
            fh.write("module zzctorfind\n\ngo 1.21\n")
        proc = subprocess.run(
            ["go", "run", ".", BROADCASTER_GO],
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
            "generic broadcaster type) found in broadcaster.go; stdout="
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

    def test_l1_broadcaster_file_exists(self):
        """L1: the deliverable lib/channels/broadcaster.go must exist."""
        assert os.path.isfile(BROADCASTER_GO), (
            "missing required deliverable: lib/channels/broadcaster.go"
        )

    def test_l1_in_channels_package(self):
        """L1: broadcaster.go must declare package channels."""
        with open(BROADCASTER_GO) as fh:
            head = fh.read()
        assert "package channels" in head, (
            "broadcaster.go must be in package channels"
        )

    def test_l1_test_file_exists(self):
        """L1: the agent must provide broadcaster_test.go with scenarios."""
        test_file = os.path.join(CHANNELS_DIR, "broadcaster_test.go")
        assert os.path.isfile(test_file), (
            "missing required deliverable: lib/channels/broadcaster_test.go"
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

    def test_l2_subscribe_then_publish_received(self):
        """L2: a subscription made before a publish observes that publish."""
        _assert_driver_pass(
            _run_driver("TestZZSubscribeThenPublish"), "subscribe-then-publish"
        )

    def test_l2_latest_wins_coalescing(self):
        """L2: after rapid publishes, a late reader observes the newest value."""
        _assert_driver_pass(_run_driver("TestZZLatestWins"), "latest-wins")

    def test_l2_fanout_independent_subscriptions(self):
        """L2: one publish is observable by every active subscription."""
        _assert_driver_pass(_run_driver("TestZZFanout"), "fan-out")

    def test_l2_caller_cancelled_receive_returns(self):
        """L2: an abandoned receive returns without a value (no hang)."""
        _assert_driver_pass(_run_driver("TestZZCancelReceive"), "cancel-receive")

    def test_l2_publish_non_blocking_with_slow_consumer(self):
        """L2: publish never stalls on a consumer that never reads."""
        _assert_driver_pass(
            _run_driver("TestZZNonBlockingPublish"), "non-blocking-publish"
        )

    def test_l2_receive_unblocks_on_shutdown(self):
        """L2: a blocked receive returns when the broadcaster is shut down."""
        _assert_driver_pass(
            _run_driver("TestZZShutdownUnblocks"), "shutdown-unblocks"
        )

    def test_l2_publish_after_shutdown_no_panic(self):
        """L2: publishing after shutdown must not panic."""
        _assert_driver_pass(
            _run_driver("TestZZPublishAfterShutdownNoPanic"),
            "publish-after-shutdown",
        )

    def test_l2_release_then_new_subscription_works(self):
        """L2: after a subscription is released, a fresh one still receives."""
        _assert_driver_pass(
            _run_driver("TestZZReleaseThenNewSubWorks"), "release-then-new-sub"
        )

    def test_l2_no_goroutine_leak_across_cycles(self):
        """L2: repeated create/use/shutdown cycles do not leak goroutines."""
        _assert_driver_pass(
            _run_driver("TestZZNoGoroutineLeak"), "no-goroutine-leak"
        )

    def test_l2_agents_own_race_suite_passes(self):
        """L2: the agent's `go test -race -run Broadcaster ./lib/channels/`
        passes clean (no failures, no race, no goroutine-leak reports)."""
        _require_go()
        proc = subprocess.run(
            ["go", "test", "-race", "-count=1", "-run", "Broadcaster",
             "./lib/channels/"],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=GO_TEST_TIMEOUT,
            env={**os.environ, "GOFLAGS": "-buildvcs=false"},
        )
        combined = proc.stdout + "\n" + proc.stderr
        assert proc.returncode == 0, (
            "go test -race -run Broadcaster ./lib/channels/ failed:\n" + combined
        )
        assert "DATA RACE" not in combined, "data race reported:\n" + combined
        assert "panic:" not in combined, "panic reported:\n" + combined
        # the agent must actually have Broadcaster-named tests that ran
        assert "no test files" not in combined, (
            "no Broadcaster tests found in lib/channels/:\n" + combined
        )


# expose constants used by textwrap import guard (keeps linters quiet)
_ = textwrap
