"""Benchmark test for skill: go-concurrency-patterns (variant ext6).

Task: Add a *keyed lock manager* to consul's ``lib/mutex`` package — a new file
``lib/mutex/keyed.go`` in package ``mutex`` exposing an exported type that hands
out a logical lock per string key. Locking one key serializes only against other
holders of the *same* key; different keys proceed in parallel. The public API
must offer: a constructor, a blocking lock + unlock keyed by a string, and a
context-aware lock keyed by a string that returns the context error on
cancellation. Per-key state must be reclaimable so memory does not grow without
bound, and everything must be clean under ``go test -race``.

The agent chooses the exact type / method names, so this test does NOT hard-code
them. Instead it:

  * uses a small Go AST program to discover the exported manager type and its
    constructor, plus classify the keyed methods by signature
    (lock = ``func(string)``, unlock = ``func(string)``,
    context-lock = ``func(context.Context, string) error`` — order may vary),
  * generates an independent Go *reflection driver* test that, at runtime,
    disambiguates lock vs. unlock by probing behavior (the method that, once
    called, makes a second same-key acquire block is the lock; its inverse is
    the unlock), and
  * compiles and runs that driver under ``go test -race`` to deep-validate the
    documented behaviors: same-key serialization with a correct final counter,
    parallel different-key progress, context-cancelled acquire leaving
    consistent state, freed-key reuse, and a goroutine-leak check.

A naive / stub / files-that-merely-look-related solution fails because the
behavior is exercised independently with this test's own assertions and a real
race detector, not by trusting the agent's own ``keyed_test.go``.

Native acceptance command this drives:
    go test -race -run 'Keyed' ./lib/mutex/
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
MUTEX_DIR = os.path.join(REPO_DIR, "lib", "mutex")
KEYED_GO = os.path.join(MUTEX_DIR, "keyed.go")
KEYED_TEST_GO = os.path.join(MUTEX_DIR, "keyed_test.go")

# Helper Go files we drop into the package while testing. Their names are unique
# enough to never collide with agent code and are cleaned up afterwards.
DRIVER_TEST = os.path.join(MUTEX_DIR, "zz_bench_keyed_driver_test.go")

GO_BUILD_TIMEOUT = 300
GO_TEST_TIMEOUT = 420


# --------------------------------------------------------------------------- #
# Embedded Go: AST discovery program.
#
# Scans every .go file in the package (so the manager type does not need to be
# declared in keyed.go alone) and prints, tab-separated lines:
#
#   CTOR\t<ctorName>\t<typeName>     for exported top-level funcs that take no
#                                     required args and return *<typeName>,
#                                     where <typeName> is a struct declared in
#                                     the package.
#
# It deliberately does not try to name lock/unlock/trylock — those are
# disambiguated at runtime by the reflection driver.
# --------------------------------------------------------------------------- #
AST_FINDER_SRC = r'''
package main

import (
	"fmt"
	"go/ast"
	"go/parser"
	"go/token"
	"os"
	"path/filepath"
	"strings"
)

func baseType(e ast.Expr) (string, bool) {
	// returns (typeName, isPointer-or-value-of-a-local-named-type)
	switch t := e.(type) {
	case *ast.StarExpr:
		return baseType(t.X)
	case *ast.Ident:
		return t.Name, true
	}
	return "", false
}

func main() {
	dir := os.Args[1]
	entries, err := os.ReadDir(dir)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(2)
	}
	fs := token.NewFileSet()
	structTypes := map[string]bool{}
	type fn struct {
		name string
		decl *ast.FuncDecl
	}
	var funcs []fn
	for _, e := range entries {
		name := e.Name()
		if e.IsDir() || !strings.HasSuffix(name, ".go") {
			continue
		}
		if strings.HasSuffix(name, "_test.go") {
			continue
		}
		f, err := parser.ParseFile(fs, filepath.Join(dir, name), nil, 0)
		if err != nil {
			fmt.Fprintln(os.Stderr, err)
			os.Exit(2)
		}
		for _, d := range f.Decls {
			if gd, ok := d.(*ast.GenDecl); ok {
				for _, s := range gd.Specs {
					if ts, ok := s.(*ast.TypeSpec); ok {
						if _, isStruct := ts.Type.(*ast.StructType); isStruct {
							structTypes[ts.Name.Name] = true
						}
					}
				}
			}
			if fd, ok := d.(*ast.FuncDecl); ok && fd.Recv == nil && fd.Name.IsExported() {
				funcs = append(funcs, fn{fd.Name.Name, fd})
			}
		}
	}
	for _, fdwrap := range funcs {
		fd := fdwrap.decl
		// no required parameters
		if fd.Type.Params != nil && len(fd.Type.Params.List) > 0 {
			continue
		}
		if fd.Type.Results == nil || len(fd.Type.Results.List) != 1 {
			continue
		}
		tn, ok := baseType(fd.Type.Results.List[0].Type)
		if !ok {
			continue
		}
		if structTypes[tn] {
			fmt.Printf("CTOR\t%s\t%s\n", fdwrap.name, tn)
		}
	}
}
'''


# --------------------------------------------------------------------------- #
# Embedded Go: reflection driver test.
#
# ``__CTOR__`` is substituted with the discovered constructor name. The driver
# discovers the keyed operations purely by signature on the manager type:
#
#   lockCandidates : methods with exactly one string arg, no results.
#   ctxLock        : a method with (context.Context, string) -> error
#                    (arg order tolerant) returning the ctx error on cancel.
#
# Lock vs. unlock is disambiguated at runtime: for each ordered pair (p, q) of
# string-only methods, calling p("k") must make a second same-key acquire block,
# and then calling q("k") must unblock it. The pair that satisfies this is
# (lock=p, unlock=q).
# --------------------------------------------------------------------------- #
DRIVER_TEST_SRC = r'''
package mutex

import (
	"context"
	"reflect"
	"runtime"
	"sync"
	"sync/atomic"
	"testing"
	"time"
)

var zzCtxType = reflect.TypeOf((*context.Context)(nil)).Elem()
var zzStrType = reflect.TypeOf("")
var zzErrType = reflect.TypeOf((*error)(nil)).Elem()

func zzNumGoroutine() int { return runtime.NumGoroutine() }

type zzAPI struct {
	mgr    reflect.Value
	lock   string // func(string)
	unlock string // func(string)
	ctxL   string // func(context.Context, string) error  (arg order tolerant)
	ctxArg int    // index (0-based, excluding receiver) of context arg in ctxL
}

func zzNew() reflect.Value { return reflect.ValueOf(__CTOR__()) }

// stringOnlyMethods returns method names with exactly one string arg, no result.
func zzStringOnlyMethods(mt reflect.Type) []string {
	var out []string
	for i := 0; i < mt.NumMethod(); i++ {
		m := mt.Method(i)
		ft := m.Func.Type()
		if ft.NumIn()-1 == 1 && ft.NumOut() == 0 && ft.In(1) == zzStrType {
			out = append(out, m.Name)
		}
	}
	return out
}

func zzCallStr(v reflect.Value, name, key string) {
	v.MethodByName(name).Call([]reflect.Value{reflect.ValueOf(key)})
}

// acquireBlocks reports whether calling lockName(key) in a fresh goroutine
// blocks (does not complete within d) -- i.e. the key is currently held.
func zzAcquireBlocks(v reflect.Value, lockName, key string, d time.Duration) bool {
	done := make(chan struct{})
	go func() {
		zzCallStr(v, lockName, key)
		close(done)
	}()
	select {
	case <-done:
		return false
	case <-time.After(d):
		return true
	}
}

func zzClassify(t *testing.T) *zzAPI {
	t.Helper()
	mv := zzNew()
	if !mv.IsValid() {
		t.Fatalf("constructor returned an invalid value")
	}
	mt := mv.Type()
	a := &zzAPI{mgr: mv}

	// Context-aware lock: (context.Context, string) -> error, order tolerant.
	for i := 0; i < mt.NumMethod(); i++ {
		m := mt.Method(i)
		ft := m.Func.Type()
		if ft.NumIn()-1 != 2 || ft.NumOut() != 1 {
			continue
		}
		if ft.Out(0) != zzErrType {
			continue
		}
		i1, i2 := ft.In(1), ft.In(2)
		if i1 == zzCtxType && i2 == zzStrType {
			a.ctxL, a.ctxArg = m.Name, 0
		} else if i1 == zzStrType && i2 == zzCtxType {
			a.ctxL, a.ctxArg = m.Name, 1
		}
	}
	if a.ctxL == "" {
		t.Fatalf("no context-aware lock method (context.Context,string)->error on %s", mt)
	}

	// Disambiguate lock vs unlock among the string-only methods by behavior.
	cands := zzStringOnlyMethods(mt)
	if len(cands) < 2 {
		t.Fatalf("expected >=2 string-only methods (lock+unlock), found %v on %s", cands, mt)
	}
	const key = "zz-probe-key"
	for _, p := range cands {
		for _, q := range cands {
			if p == q {
				continue
			}
			// Fresh manager per probe to avoid cross-contamination.
			fresh := zzNew()
			// p must acquire without blocking on an idle key.
			pdone := make(chan struct{})
			go func() { zzCallStr(fresh, p, key); close(pdone) }()
			select {
			case <-pdone:
			case <-time.After(500 * time.Millisecond):
				continue // p blocked on an idle key -> p is not a lock
			}
			// Now a second same-key acquire via p must block (held).
			if !zzAcquireBlocks(fresh, p, key, 150*time.Millisecond) {
				continue // holding p did not make same key block -> not mutual excl.
			}
			// q must release: after q, p on the key must succeed quickly.
			zzCallStr(fresh, q, key)
			if zzAcquireBlocks(fresh, p, key, 300*time.Millisecond) {
				continue // q did not release
			}
			a.lock, a.unlock = p, q
			t.Logf("discovered api: lock=%s unlock=%s ctxLock=%s ctxArg=%d",
				a.lock, a.unlock, a.ctxL, a.ctxArg)
			return a
		}
	}
	t.Fatalf("could not identify a lock/unlock pair among %v on %s", cands, mt)
	return nil
}

func (a *zzAPI) Lock(key string)   { zzCallStr(a.mgr, a.lock, key) }
func (a *zzAPI) Unlock(key string) { zzCallStr(a.mgr, a.unlock, key) }

// CtxLock calls the context-aware lock with the supplied ctx + key, returns err.
func (a *zzAPI) CtxLock(ctx context.Context, key string) error {
	m := a.mgr.MethodByName(a.ctxL)
	var args []reflect.Value
	if a.ctxArg == 0 {
		args = []reflect.Value{reflect.ValueOf(ctx), reflect.ValueOf(key)}
	} else {
		args = []reflect.Value{reflect.ValueOf(key), reflect.ValueOf(ctx)}
	}
	res := m.Call(args)
	if res[0].IsNil() {
		return nil
	}
	return res[0].Interface().(error)
}

// --- scenario tests (run individually by the Python harness via -run) --- //

// Same-key access is serialized and a guarded counter ends exactly at N with no
// race report. A naive impl that does not actually serialize same-key callers
// trips the race detector / yields a wrong total.
func TestKeyedSameKeySerialized(t *testing.T) {
	a := zzClassify(t)
	const N = 200
	const key = "shared"
	var counter int
	var wg sync.WaitGroup
	start := make(chan struct{})
	for i := 0; i < N; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			<-start
			a.Lock(key)
			counter++ // guarded only by the key's lock
			a.Unlock(key)
		}()
	}
	close(start)
	wg.Wait()
	if counter != N {
		t.Fatalf("same-key serialization broken: counter=%d want %d", counter, N)
	}
}

// Different keys proceed in parallel: holding key "a" must NOT block acquiring
// key "b". A broken impl using a single global lock would deadlock/timeout.
func TestKeyedDifferentKeysParallel(t *testing.T) {
	a := zzClassify(t)
	a.Lock("a") // held for the duration
	got := make(chan struct{})
	go func() {
		a.Lock("b") // different key: must acquire immediately
		a.Unlock("b")
		close(got)
	}()
	select {
	case <-got:
	case <-time.After(2 * time.Second):
		a.Unlock("a")
		t.Fatal("locking key b blocked while key a was held (no per-key isolation)")
	}
	a.Unlock("a")
}

// Holding a key serializes a second same-key holder: it must wait until the
// first unlocks, then proceed. Verified with synchronization, not sleeps.
func TestKeyedSameKeyBlocksUntilUnlock(t *testing.T) {
	a := zzClassify(t)
	const key = "serial"
	a.Lock(key)
	acquired := make(chan struct{})
	go func() {
		a.Lock(key) // must block until the holder below unlocks
		close(acquired)
		a.Unlock(key)
	}()
	// It must still be blocked while we hold it.
	select {
	case <-acquired:
		t.Fatal("second same-key Lock acquired while key was held")
	case <-time.After(150 * time.Millisecond):
	}
	a.Unlock(key)
	select {
	case <-acquired:
	case <-time.After(2 * time.Second):
		t.Fatal("second same-key Lock did not acquire after unlock")
	}
}

// A context-aware lock on a held key with a cancelled context returns the ctx
// error and leaves state consistent: the holder can still unlock and the key is
// re-lockable afterwards.
func TestKeyedCtxCancelConsistent(t *testing.T) {
	a := zzClassify(t)
	const key = "ctxk"
	a.Lock(key) // held

	ctx, cancel := context.WithCancel(context.Background())
	errCh := make(chan error, 1)
	go func() { errCh <- a.CtxLock(ctx, key) }() // blocks: key is held
	cancel()                                     // abandon the acquire
	select {
	case err := <-errCh:
		if err == nil {
			t.Fatal("context-cancelled acquire returned nil error (acquired a held key)")
		}
		if err != context.Canceled && ctx.Err() == nil {
			t.Fatalf("expected context error, got %v", err)
		}
	case <-time.After(2 * time.Second):
		t.Fatal("context-cancelled acquire did not return")
	}
	// State must be consistent: holder unlocks, key re-lockable.
	a.Unlock(key)
	relocked := make(chan struct{})
	go func() { a.Lock(key); close(relocked) }()
	select {
	case <-relocked:
		a.Unlock(key)
	case <-time.After(2 * time.Second):
		t.Fatal("key not re-lockable after a cancelled acquire (corrupted state)")
	}
}

// The context-aware lock actually acquires when the key is free (returns nil and
// excludes others) -- proves it is a real lock, not a no-op returning nil.
func TestKeyedCtxLockAcquires(t *testing.T) {
	a := zzClassify(t)
	const key = "ctxacq"
	ctx, cancel := context.WithTimeout(context.Background(), time.Second)
	defer cancel()
	if err := a.CtxLock(ctx, key); err != nil {
		t.Fatalf("context lock of a free key failed: %v", err)
	}
	// Now the key is held: a blocking Lock of the same key must block.
	if !zzAcquireBlocks(a.mgr, a.lock, key, 200*time.Millisecond) {
		t.Fatal("context lock did not actually hold the key (others not excluded)")
	}
	a.Unlock(key)
}

// Many distinct keys used sequentially, each released -> reusing a freed key
// behaves normally (serializes correctly). This exercises the reclaim path.
func TestKeyedFreedKeyReuse(t *testing.T) {
	a := zzClassify(t)
	for i := 0; i < 500; i++ {
		k := "k-" + string(rune('A'+(i%26))) + "-" + itoa(i)
		a.Lock(k)
		a.Unlock(k)
	}
	// Reuse one of the (now released) keys: it must still serialize correctly.
	const key = "k-A-0"
	const N = 100
	var counter int64
	var wg sync.WaitGroup
	start := make(chan struct{})
	for i := 0; i < N; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			<-start
			a.Lock(key)
			atomic.AddInt64(&counter, 1)
			a.Unlock(key)
		}()
	}
	close(start)
	wg.Wait()
	if counter != N {
		t.Fatalf("reused freed key serialization broken: counter=%d want %d", counter, N)
	}
}

// Heavy concurrent lock/unlock across many keys from many goroutines: must be
// race-free and produce correct per-key counts.
func TestKeyedConcurrentManyKeys(t *testing.T) {
	a := zzClassify(t)
	const keys = 16
	const perKey = 80
	counters := make([]int64, keys)
	var wg sync.WaitGroup
	start := make(chan struct{})
	for k := 0; k < keys; k++ {
		for j := 0; j < perKey; j++ {
			wg.Add(1)
			go func(k int) {
				defer wg.Done()
				<-start
				key := "mk-" + itoa(k)
				a.Lock(key)
				counters[k]++ // guarded by per-key lock; -race must stay clean
				a.Unlock(key)
			}(k)
		}
	}
	close(start)
	wg.Wait()
	for k := 0; k < keys; k++ {
		if counters[k] != perKey {
			t.Fatalf("key %d: counter=%d want %d", k, counters[k], perKey)
		}
	}
}

// Repeated create/use/destroy of keys must not leak goroutines.
func TestKeyedNoGoroutineLeak(t *testing.T) {
	base := zzNumGoroutine()
	for cycle := 0; cycle < 50; cycle++ {
		a := zzClassify(t)
		for i := 0; i < 20; i++ {
			key := "leak-" + itoa(i)
			a.Lock(key)
			a.Unlock(key)
		}
	}
	deadline := time.Now().Add(2 * time.Second)
	after := zzNumGoroutine()
	for time.Now().Before(deadline) && after > base+100 {
		time.Sleep(50 * time.Millisecond)
		runtime.GC()
		after = zzNumGoroutine()
	}
	if after > base+100 {
		t.Fatalf("goroutine leak suspected: base=%d after=%d", base, after)
	}
}

// small sleep-free itoa to avoid importing strconv in a way that perturbs deps.
func itoa(n int) string {
	if n == 0 {
		return "0"
	}
	neg := n < 0
	if neg {
		n = -n
	}
	var buf [20]byte
	i := len(buf)
	for n > 0 {
		i--
		buf[i] = byte('0' + n%10)
		n /= 10
	}
	if neg {
		i--
		buf[i] = '-'
	}
	return string(buf[i:])
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
    assert os.path.isfile(KEYED_GO), "missing deliverable: lib/mutex/keyed.go"
    tmpdir = os.path.join(REPO_DIR, ".zz_keyed_ctorfind")
    os.makedirs(tmpdir, exist_ok=True)
    try:
        with open(os.path.join(tmpdir, "main.go"), "w") as fh:
            fh.write(AST_FINDER_SRC)
        with open(os.path.join(tmpdir, "go.mod"), "w") as fh:
            fh.write("module zzkeyedctorfind\n\ngo 1.21\n")
        proc = subprocess.run(
            ["go", "run", ".", MUTEX_DIR],
            cwd=tmpdir,
            capture_output=True,
            text=True,
            timeout=GO_BUILD_TIMEOUT,
            env={**os.environ, "GOFLAGS": "-buildvcs=false"},
        )
        assert proc.returncode == 0, (
            f"AST constructor finder failed:\nSTDOUT:{proc.stdout}\nSTDERR:{proc.stderr}"
        )
        ctors = [
            ln.split("\t")[1]
            for ln in proc.stdout.splitlines()
            if ln.startswith("CTOR\t") and len(ln.split("\t")) >= 3
        ]
        assert ctors, (
            "no exported constructor (top-level func with no required args "
            "returning a struct type declared in package mutex) found; stdout="
            f"{proc.stdout!r}"
        )
        # Prefer a constructor that is NOT the package's existing Mutex `New`
        # if multiple exist; the keyed manager's constructor returns a distinct
        # struct type. We pick the first whose returned type name is not "Mutex".
        chosen = None
        for ln in proc.stdout.splitlines():
            parts = ln.split("\t")
            if len(parts) >= 3 and parts[0] == "CTOR" and parts[2] != "Mutex":
                chosen = parts[1]
                break
        return chosen or ctors[0]
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
         "-v", "./lib/mutex/"],
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

    def test_l1_keyed_file_exists(self):
        """L1: the deliverable lib/mutex/keyed.go must exist."""
        assert os.path.isfile(KEYED_GO), (
            "missing required deliverable: lib/mutex/keyed.go"
        )

    def test_l1_in_mutex_package(self):
        """L1: keyed.go must declare package mutex."""
        with open(KEYED_GO) as fh:
            head = fh.read()
        assert "package mutex" in head, "keyed.go must be in package mutex"

    def test_l1_test_file_exists(self):
        """L1: the agent must provide lib/mutex/keyed_test.go with scenarios."""
        assert os.path.isfile(KEYED_TEST_GO), (
            "missing required deliverable: lib/mutex/keyed_test.go"
        )

    def test_l1_package_builds(self):
        """L1: `go build ./lib/mutex/` must succeed."""
        _require_go()
        proc = subprocess.run(
            ["go", "build", "./lib/mutex/"],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=GO_BUILD_TIMEOUT,
            env={**os.environ, "GOFLAGS": "-buildvcs=false"},
        )
        assert proc.returncode == 0, (
            f"go build ./lib/mutex/ failed:\n{proc.stdout}\n{proc.stderr}"
        )

    def test_l1_exported_constructor_discoverable(self):
        """L1: an exported keyed-manager constructor must be discoverable via AST."""
        _require_go()
        ctor = _find_constructor()
        assert ctor and ctor[0].isupper(), (
            f"constructor {ctor!r} must be exported (capitalized)"
        )

    # ----------------------------- L2 ----------------------------- #

    def test_l2_same_key_serialized_counter(self):
        """L2: N goroutines locking the same key yield an exact final counter,
        race-clean (proves real same-key serialization)."""
        _assert_driver_pass(
            _run_driver("TestKeyedSameKeySerialized"), "same-key-serialized"
        )

    def test_l2_different_keys_parallel(self):
        """L2: holding one key does not block acquiring a different key."""
        _assert_driver_pass(
            _run_driver("TestKeyedDifferentKeysParallel"), "different-keys-parallel"
        )

    def test_l2_same_key_blocks_until_unlock(self):
        """L2: a second same-key locker blocks until the holder unlocks."""
        _assert_driver_pass(
            _run_driver("TestKeyedSameKeyBlocksUntilUnlock"),
            "same-key-blocks-until-unlock",
        )

    def test_l2_ctx_cancel_leaves_consistent_state(self):
        """L2: a context-cancelled acquire of a held key returns the ctx error
        and leaves state consistent (key re-lockable afterwards)."""
        _assert_driver_pass(
            _run_driver("TestKeyedCtxCancelConsistent"), "ctx-cancel-consistent"
        )

    def test_l2_ctx_lock_actually_acquires(self):
        """L2: the context-aware lock truly acquires a free key and excludes
        others (not a no-op that returns nil)."""
        _assert_driver_pass(
            _run_driver("TestKeyedCtxLockAcquires"), "ctx-lock-acquires"
        )

    def test_l2_freed_key_reuse(self):
        """L2: after many distinct keys are used and released, reusing a freed
        key still serializes correctly (reclaim path is correct)."""
        _assert_driver_pass(
            _run_driver("TestKeyedFreedKeyReuse"), "freed-key-reuse"
        )

    def test_l2_concurrent_many_keys_race_clean(self):
        """L2: heavy concurrent lock/unlock across many keys is race-free with
        correct per-key counts."""
        _assert_driver_pass(
            _run_driver("TestKeyedConcurrentManyKeys"), "concurrent-many-keys"
        )

    def test_l2_no_goroutine_leak(self):
        """L2: repeated key create/use cycles do not leak goroutines."""
        _assert_driver_pass(
            _run_driver("TestKeyedNoGoroutineLeak"), "no-goroutine-leak"
        )

    def test_l2_agents_own_keyed_race_suite_passes(self):
        """L2: the native acceptance command
        `go test -race -run 'Keyed' ./lib/mutex/` passes clean (no failures,
        no race, no goroutine-leak/panic reports) and the agent's own
        Keyed-named tests actually ran."""
        _require_go()
        proc = subprocess.run(
            ["go", "test", "-race", "-count=1", "-run", "Keyed",
             "./lib/mutex/"],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=GO_TEST_TIMEOUT,
            env={**os.environ, "GOFLAGS": "-buildvcs=false"},
        )
        combined = proc.stdout + "\n" + proc.stderr
        assert proc.returncode == 0, (
            "go test -race -run Keyed ./lib/mutex/ failed:\n" + combined
        )
        assert "DATA RACE" not in combined, "data race reported:\n" + combined
        assert "panic:" not in combined, "panic reported:\n" + combined
        assert "no test files" not in combined, (
            "no test files in lib/mutex/:\n" + combined
        )
        # The agent must actually have Keyed-named tests that ran (not just an
        # empty filter matching nothing -> "ok ... no tests to run").
        assert "no tests to run" not in combined, (
            "no Keyed-named tests found in lib/mutex/ (the suite ran nothing):\n"
            + combined
        )


# keep linters quiet about the textwrap import (kept for parity with template)
_ = textwrap
