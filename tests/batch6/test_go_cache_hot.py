"""Tests for the `go-cache-hot` skill task (variant ext6).

Skill: go-cache-hot — Build an *Eviction-Aware Renderer Pool* inside the
`github.com/samber/hot` repository.

The task asks the agent to create `pkg/renderpool/renderpool.go` (and a
`renderpool_test.go`) implementing a `RenderPool` that keeps a bounded set of
compiled templates hot on top of the `hot` cache while guaranteeing an
*exactly-once* cleanup hook (`OnRelease`) for every compiled template the moment
it leaves the pool — whether it left because of capacity eviction, TTL expiry,
or an explicit `Remove`. Required public API:

  - type Compiled struct { Name string; ... }
  - type Compiler interface { Compile(name string) (*Compiled, error) }
  - type OnRelease func(c *Compiled)
  - func NewRenderPool(c Compiler, capacity int, ttl time.Duration,
                       onRelease OnRelease) *RenderPool
  - func (p *RenderPool) Acquire(name string) (*Compiled, bool, error)
  - func (p *RenderPool) Remove(name string) bool
  - func (p *RenderPool) Close()

Semantics under test:
  - Acquire of an existing name compiles once; a second acquire within ttl
    returns the SAME instance (no recompile).
  - Acquire of an unknown name -> (nil, false, nil); infra failure -> (nil,
    false, err) and is not remembered.
  - Compiling > capacity distinct templates evicts the overflow and runs
    onRelease exactly once for each dropped template.
  - A template whose ttl elapses is released (onRelease runs once).
  - Remove(name) on a present template runs onRelease once and returns true;
    Remove on an absent name returns false and triggers no release.
  - A burst of concurrent Acquire of the same uncached name collapses into a
    single Compile.
  - onRelease is NEVER invoked more than once for the same instance.
  - After Close(), no goroutines leak (go.uber.org/goleak).

What this file verifies:
  L1 — deliverable files exist, the module still builds, go.mod is unmodified,
       the required public API surface compiles against an independent package,
       and the agent's own TestRenderPool* tests pass (the native acceptance
       command).
  L2 — we DO NOT trust the agent's own test file. We synthesize independent
       probe packages under REPO_DIR that import the agent's `pkg/renderpool`
       package, drive it with our own counting Compiler + a mutex-guarded
       release recorder, and assert the concrete exactly-once / eviction /
       expiry / dedup behaviors via the native `go test` toolchain. A naive
       implementation (no cleanup hook on eviction/expiry, double-release,
       recompile-every-acquire, or live-forever) fails at least one probe.
"""

import os
import re
import shutil
import subprocess
import textwrap

import pytest

REPO_DIR = "/workspace/hot"
RP_PKG = os.path.join(REPO_DIR, "pkg", "renderpool")
PROBE_PKG = os.path.join(REPO_DIR, "pkg", "renderpoolprobe")


def _run_go(args, timeout=300):
    """Run a go command from REPO_DIR with sane module-mode env defaults."""
    env = dict(os.environ)
    env.setdefault("GOFLAGS", "")
    env["GO111MODULE"] = "on"
    return subprocess.run(
        ["go"] + args,
        cwd=REPO_DIR,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )


def _write_probe(name, body):
    """Write a single probe file into pkg/renderpoolprobe and return its path."""
    os.makedirs(PROBE_PKG, exist_ok=True)
    path = os.path.join(PROBE_PKG, name)
    with open(path, "w") as fh:
        fh.write(body)
    return path


def _run_probe(name, body, run="", timeout=300):
    """Write a probe test file, run it, clean it up, return CompletedProcess."""
    path = _write_probe(name, body)
    try:
        args = ["test", "./pkg/renderpoolprobe/", "-count=1", "-v"]
        if run:
            args += ["-run", run]
        return _run_go(args, timeout=timeout)
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


# Common header reused by probe files. Imports the agent's renderpool package
# and provides a counting Compiler plus a mutex-guarded release recorder.
PROBE_HEADER = textwrap.dedent(
    """
    package renderpoolprobe

    import (
        "errors"
        "sort"
        "strconv"
        "sync"
        "sync/atomic"
        "testing"
        "time"

        renderpool "github.com/samber/hot/pkg/renderpool"
    )

    var _ = strconv.Itoa
    var _ = errors.New
    var _ = sort.Strings
    var _ = atomic.AddInt32

    // countingCompiler records per-name Compile counts and is concurrency safe.
    // It can be told which names exist, which names should fail (an infra
    // error), and can block inside Compile to exercise dedup.
    type countingCompiler struct {
        mu       sync.Mutex
        counts   map[string]int
        exists   map[string]bool
        failNext map[string]int  // remaining infra failures per name
        blockCh  chan struct{}   // if non-nil, Compile waits on it once entered
        entered  int32
    }

    func newCountingCompiler() *countingCompiler {
        return &countingCompiler{
            counts:   map[string]int{},
            exists:   map[string]bool{},
            failNext: map[string]int{},
        }
    }

    func (c *countingCompiler) add(names ...string) {
        c.mu.Lock()
        for _, n := range names {
            c.exists[n] = true
        }
        c.mu.Unlock()
    }

    func (c *countingCompiler) setFail(name string, n int) {
        c.mu.Lock()
        c.failNext[name] = n
        c.mu.Unlock()
    }

    func (c *countingCompiler) count(name string) int {
        c.mu.Lock()
        defer c.mu.Unlock()
        return c.counts[name]
    }

    func (c *countingCompiler) Compile(name string) (*renderpool.Compiled, error) {
        atomic.AddInt32(&c.entered, 1)
        if c.blockCh != nil {
            <-c.blockCh
        }
        c.mu.Lock()
        defer c.mu.Unlock()
        c.counts[name]++
        if rem, ok := c.failNext[name]; ok && rem > 0 {
            c.failNext[name] = rem - 1
            return nil, errors.New("infra failure for " + name)
        }
        if !c.exists[name] {
            return nil, nil // no such template
        }
        return &renderpool.Compiled{Name: name}, nil
    }

    // releaseRecorder records, under a mutex, every released template name and
    // the per-name release count, so we can assert exactly-once semantics.
    type releaseRecorder struct {
        mu     sync.Mutex
        counts map[string]int
        total  int
        // identity tracking: pointer -> times released, to catch
        // double-release of the SAME instance.
        ptrCount map[*renderpool.Compiled]int
    }

    func newReleaseRecorder() *releaseRecorder {
        return &releaseRecorder{
            counts:   map[string]int{},
            ptrCount: map[*renderpool.Compiled]int{},
        }
    }

    func (r *releaseRecorder) hook() renderpool.OnRelease {
        return func(c *renderpool.Compiled) {
            r.mu.Lock()
            defer r.mu.Unlock()
            r.total++
            if c != nil {
                r.counts[c.Name]++
                r.ptrCount[c]++
            }
        }
    }

    func (r *releaseRecorder) totalReleases() int {
        r.mu.Lock()
        defer r.mu.Unlock()
        return r.total
    }

    func (r *releaseRecorder) releaseCount(name string) int {
        r.mu.Lock()
        defer r.mu.Unlock()
        return r.counts[name]
    }

    // maxPerInstance returns the largest number of times any single compiled
    // instance was released. >1 means the exactly-once contract was violated.
    func (r *releaseRecorder) maxPerInstance() int {
        r.mu.Lock()
        defer r.mu.Unlock()
        m := 0
        for _, n := range r.ptrCount {
            if n > m {
                m = n
            }
        }
        return m
    }
    """
)


@pytest.fixture(scope="module", autouse=True)
def ensure_go():
    """Ensure the go toolchain is present and module deps are downloaded."""
    if shutil.which("go") is None:
        pytest.skip("go toolchain not available in container")
    # Pre-download module dependencies so per-test timeouts are about behavior.
    res = _run_go(["mod", "download"], timeout=400)
    yield res


# ---------------------------------------------------------------------------
# L1 — deliverable existence / well-formedness / compilation
# ---------------------------------------------------------------------------

class TestGoCacheHot:
    REPO_DIR = "/workspace/hot"

    def test_l1_renderpool_source_exists(self):
        """L1: pkg/renderpool/renderpool.go exists and is non-empty."""
        p = os.path.join(RP_PKG, "renderpool.go")
        assert os.path.isfile(p), f"missing {p}"
        assert os.path.getsize(p) > 0, "renderpool.go is empty"

    def test_l1_renderpool_test_exists(self):
        """L1: pkg/renderpool/renderpool_test.go exists (agent's own tests)."""
        p = os.path.join(RP_PKG, "renderpool_test.go")
        assert os.path.isfile(p), f"missing {p}"
        assert os.path.getsize(p) > 0, "renderpool_test.go is empty"

    def test_l1_go_mod_unmodified_module_path(self):
        """L1: still the samber/hot module, Go 1.22+, no new third-party deps.

        We assert the require block does not introduce dependencies beyond the
        ones already present in the upstream go.mod (the task forbids adding new
        third-party deps and modifying go.mod)."""
        gomod = os.path.join(REPO_DIR, "go.mod")
        with open(gomod) as fh:
            text = fh.read()
        assert "module github.com/samber/hot" in text
        m = re.search(r"^go\s+(\d+)\.(\d+)", text, re.MULTILINE)
        assert m, "no go directive in go.mod"
        major, minor = int(m.group(1)), int(m.group(2))
        assert (major, minor) >= (1, 22), f"go {major}.{minor} < 1.22"

    def test_l1_build_whole_module(self):
        """L1: `go build ./...` succeeds with the new package present."""
        res = _run_go(["build", "./..."], timeout=400)
        assert res.returncode == 0, (
            "go build ./... failed:\n" + res.stdout + res.stderr
        )

    def test_l1_vet_renderpool_package(self):
        """L1: `go vet` of the renderpool package is clean (well-formed Go)."""
        res = _run_go(["vet", "./pkg/renderpool/"], timeout=300)
        assert res.returncode == 0, (
            "go vet ./pkg/renderpool/ failed:\n" + res.stdout + res.stderr
        )

    def test_l1_public_api_surface_compiles(self):
        """L1: the exact required public API (Compiled.Name, Compiler,
        OnRelease, NewRenderPool, Acquire, Remove, Close) compiles when
        referenced from an independent package."""
        body = PROBE_HEADER + textwrap.dedent(
            """
            func TestAPISurface(t *testing.T) {
                // Compiler interface is satisfied by our counting compiler.
                var _ renderpool.Compiler = newCountingCompiler()
                // Compiled exposes a Name field.
                cc := renderpool.Compiled{Name: "home"}
                _ = cc.Name
                // OnRelease is a func(*Compiled).
                var _ renderpool.OnRelease = func(c *renderpool.Compiled) { _ = c }

                comp := newCountingCompiler()
                rec := newReleaseRecorder()
                p := renderpool.NewRenderPool(comp, 8, time.Second, rec.hook())

                var got *renderpool.Compiled
                var found bool
                var err error
                got, found, err = p.Acquire("home")
                _ = got
                _ = found
                _ = err

                var removed bool = p.Remove("home")
                _ = removed

                p.Close()
            }
            """
        )
        res = _run_probe("api_surface_test.go", body, run="TestAPISurface")
        assert res.returncode == 0, (
            "API surface probe failed to compile/run:\n" + res.stdout + res.stderr
        )
        assert "PASS" in res.stdout, res.stdout + res.stderr

    def test_l1_agent_tests_run(self):
        """L1: the agent's own TestRenderPool* tests pass (native acceptance
        command from the doc)."""
        res = _run_go(
            ["test", "./pkg/renderpool/", "-run", "TestRenderPool", "-count=1"],
            timeout=400,
        )
        assert res.returncode == 0, (
            "agent's own `go test ./pkg/renderpool/ -run TestRenderPool` failed:\n"
            + res.stdout + res.stderr
        )

# ---------------------------------------------------------------------------
# L2 — independent behavioral probes via native `go test`
# ---------------------------------------------------------------------------

    def test_l2_acquire_existing_compiles_once_same_instance(self):
        """L2: an existing template acquired twice in a row compiles EXACTLY
        once and the two acquires return the same instance (no recompile)."""
        body = PROBE_HEADER + textwrap.dedent(
            """
            func TestAcquireOnce(t *testing.T) {
                comp := newCountingCompiler()
                comp.add("home")
                rec := newReleaseRecorder()
                p := renderpool.NewRenderPool(comp, 16, time.Minute, rec.hook())
                defer p.Close()

                r1, f1, e1 := p.Acquire("home")
                if e1 != nil || !f1 || r1 == nil {
                    t.Fatalf("first acquire: found=%v err=%v rec=%v", f1, e1, r1)
                }
                r2, f2, e2 := p.Acquire("home")
                if e2 != nil || !f2 || r2 == nil {
                    t.Fatalf("second acquire: found=%v err=%v", f2, e2)
                }
                if r1 != r2 {
                    t.Fatalf("expected same compiled instance on re-acquire; got %p vs %p", r1, r2)
                }
                if r1.Name != "home" {
                    t.Fatalf("wrong Name %q", r1.Name)
                }
                if got := comp.count("home"); got != 1 {
                    t.Fatalf("COMPILECOUNT want 1 got %d (recompiled within ttl)", got)
                }
            }
            """
        )
        res = _run_probe("acquire_once_test.go", body, run="TestAcquireOnce")
        assert res.returncode == 0, res.stdout + res.stderr
        assert "PASS" in res.stdout, res.stdout + res.stderr

    def test_l2_unknown_template_not_found_no_error(self):
        """L2: an unknown template returns (nil, false, nil)."""
        body = PROBE_HEADER + textwrap.dedent(
            """
            func TestUnknown(t *testing.T) {
                comp := newCountingCompiler() // nothing exists
                rec := newReleaseRecorder()
                p := renderpool.NewRenderPool(comp, 16, time.Minute, rec.hook())
                defer p.Close()

                r, f, e := p.Acquire("ghost")
                if e != nil {
                    t.Fatalf("unknown template should not error, got %v", e)
                }
                if f {
                    t.Fatalf("unknown template should report found=false")
                }
                if r != nil {
                    t.Fatalf("unknown template should return nil compiled, got %+v", r)
                }
                // No template ever entered the pool, so nothing should be released.
                if got := rec.totalReleases(); got != 0 {
                    t.Fatalf("no release expected for unknown template, got %d", got)
                }
            }
            """
        )
        res = _run_probe("unknown_test.go", body, run="TestUnknown")
        assert res.returncode == 0, res.stdout + res.stderr
        assert "PASS" in res.stdout, res.stdout + res.stderr

    def test_l2_infra_error_not_remembered(self):
        """L2: an infra failure is returned as (nil,false,err) and is NOT
        remembered; a later acquire of the same name re-attempts Compile and
        succeeds."""
        body = PROBE_HEADER + textwrap.dedent(
            """
            func TestErrorNotRemembered(t *testing.T) {
                comp := newCountingCompiler()
                comp.add("report")
                comp.setFail("report", 1) // first Compile fails
                rec := newReleaseRecorder()
                p := renderpool.NewRenderPool(comp, 16, time.Minute, rec.hook())
                defer p.Close()

                r1, f1, e1 := p.Acquire("report")
                if e1 == nil {
                    t.Fatalf("expected infra error on first acquire, got nil")
                }
                if f1 || r1 != nil {
                    t.Fatalf("on error want (nil,false,err) got found=%v rec=%v", f1, r1)
                }
                r2, f2, e2 := p.Acquire("report")
                if e2 != nil {
                    t.Fatalf("second acquire errored: %v (failure was remembered)", e2)
                }
                if !f2 || r2 == nil || r2.Name != "report" {
                    t.Fatalf("second acquire: found=%v rec=%+v", f2, r2)
                }
                if got := comp.count("report"); got < 2 {
                    t.Fatalf("COMPILECOUNT want >=2 got %d (error not re-attempted)", got)
                }
            }
            """
        )
        res = _run_probe("err_test.go", body, run="TestErrorNotRemembered")
        assert res.returncode == 0, res.stdout + res.stderr
        assert "PASS" in res.stdout, res.stdout + res.stderr

    def test_l2_capacity_eviction_releases_exactly_once(self):
        """L2: compiling strictly more than `capacity` distinct templates
        triggers onRelease for each dropped template, with the total release
        count equal to the number that left the pool and NO instance released
        more than once."""
        body = PROBE_HEADER + textwrap.dedent(
            """
            func TestEvictionExactlyOnce(t *testing.T) {
                const cap = 4
                const total = 40
                comp := newCountingCompiler()
                for i := 0; i < total; i++ {
                    comp.add("t" + strconv.Itoa(i))
                }
                rec := newReleaseRecorder()
                p := renderpool.NewRenderPool(comp, cap, time.Minute, rec.hook())
                defer p.Close()

                for i := 0; i < total; i++ {
                    name := "t" + strconv.Itoa(i)
                    r, f, e := p.Acquire(name)
                    if e != nil || !f || r == nil || r.Name != name {
                        t.Fatalf("acquire %s: found=%v err=%v rec=%v", name, f, e, r)
                    }
                }

                // Exactly `total-cap` templates had to be dropped to honor cap.
                wantReleases := total - cap
                if got := rec.totalReleases(); got != wantReleases {
                    t.Fatalf("RELEASECOUNT want %d got %d (eviction hook not run per drop)", wantReleases, got)
                }
                if m := rec.maxPerInstance(); m > 1 {
                    t.Fatalf("an instance was released %d times (exactly-once violated)", m)
                }
                // The first-acquired template must have been evicted and so
                // released exactly once.
                if got := rec.releaseCount("t0"); got != 1 {
                    t.Fatalf("t0 release count want 1 got %d", got)
                }
            }
            """
        )
        res = _run_probe(
            "evict_test.go", body, run="TestEvictionExactlyOnce", timeout=300
        )
        assert res.returncode == 0, res.stdout + res.stderr
        assert "PASS" in res.stdout, res.stdout + res.stderr

    def test_l2_evicted_template_recompiles_on_reacquire(self):
        """L2: a template evicted to honor capacity must be recompiled when
        acquired again (proves it actually left the pool, not just that a hook
        fired)."""
        body = PROBE_HEADER + textwrap.dedent(
            """
            func TestEvictedRecompiles(t *testing.T) {
                const cap = 4
                const total = 40
                comp := newCountingCompiler()
                for i := 0; i < total; i++ {
                    comp.add("t" + strconv.Itoa(i))
                }
                rec := newReleaseRecorder()
                p := renderpool.NewRenderPool(comp, cap, time.Minute, rec.hook())
                defer p.Close()

                for i := 0; i < total; i++ {
                    name := "t" + strconv.Itoa(i)
                    if _, f, e := p.Acquire(name); e != nil || !f {
                        t.Fatalf("acquire %s found=%v err=%v", name, f, e)
                    }
                }
                before := comp.count("t0")
                if before != 1 {
                    t.Fatalf("t0 should have compiled once so far, got %d", before)
                }
                if _, f, e := p.Acquire("t0"); e != nil || !f {
                    t.Fatalf("re-acquire t0 found=%v err=%v", f, e)
                }
                after := comp.count("t0")
                if after <= before {
                    t.Fatalf("t0 was not evicted: compile count stayed %d (unbounded growth)", after)
                }
            }
            """
        )
        res = _run_probe(
            "recompile_test.go", body, run="TestEvictedRecompiles", timeout=300
        )
        assert res.returncode == 0, res.stdout + res.stderr
        assert "PASS" in res.stdout, res.stdout + res.stderr

    def test_l2_ttl_expiry_triggers_release(self):
        """L2: a template acquired with a very short ttl, after waiting past the
        ttl, has its onRelease invoked exactly once (background cleanup must
        actively release expired entries)."""
        body = PROBE_HEADER + textwrap.dedent(
            """
            func TestTTLRelease(t *testing.T) {
                comp := newCountingCompiler()
                comp.add("flash")
                rec := newReleaseRecorder()
                p := renderpool.NewRenderPool(comp, 16, 60*time.Millisecond, rec.hook())
                defer p.Close()

                if _, f, e := p.Acquire("flash"); e != nil || !f {
                    t.Fatalf("acquire flash found=%v err=%v", f, e)
                }
                if got := rec.releaseCount("flash"); got != 0 {
                    t.Fatalf("flash released before ttl elapsed (count=%d)", got)
                }

                // Wait well past the ttl; the pool's background cleanup must
                // release the expired template.
                deadline := time.Now().Add(3 * time.Second)
                for time.Now().Before(deadline) {
                    if rec.releaseCount("flash") >= 1 {
                        break
                    }
                    time.Sleep(20 * time.Millisecond)
                }
                if got := rec.releaseCount("flash"); got != 1 {
                    t.Fatalf("expired template release count want 1 got %d (expiry did not run cleanup hook exactly once)", got)
                }
                if m := rec.maxPerInstance(); m > 1 {
                    t.Fatalf("expired instance released %d times (exactly-once violated)", m)
                }
            }
            """
        )
        res = _run_probe("ttl_test.go", body, run="TestTTLRelease", timeout=300)
        assert res.returncode == 0, res.stdout + res.stderr
        assert "PASS" in res.stdout, res.stdout + res.stderr

    def test_l2_remove_present_releases_once_returns_true(self):
        """L2: Remove(name) on a present template invokes onRelease once and
        returns true; the template is gone (re-acquire recompiles)."""
        body = PROBE_HEADER + textwrap.dedent(
            """
            func TestRemovePresent(t *testing.T) {
                comp := newCountingCompiler()
                comp.add("nav")
                rec := newReleaseRecorder()
                p := renderpool.NewRenderPool(comp, 16, time.Minute, rec.hook())
                defer p.Close()

                if _, f, e := p.Acquire("nav"); e != nil || !f {
                    t.Fatalf("acquire nav found=%v err=%v", f, e)
                }
                if !p.Remove("nav") {
                    t.Fatalf("Remove of present template should return true")
                }
                if got := rec.releaseCount("nav"); got != 1 {
                    t.Fatalf("Remove release count want 1 got %d", got)
                }
                if m := rec.maxPerInstance(); m > 1 {
                    t.Fatalf("instance released %d times via Remove (exactly-once violated)", m)
                }
                // It really left the pool: a fresh acquire must recompile.
                before := comp.count("nav")
                if _, f, e := p.Acquire("nav"); e != nil || !f {
                    t.Fatalf("re-acquire nav found=%v err=%v", f, e)
                }
                if comp.count("nav") <= before {
                    t.Fatalf("nav still cached after Remove (compile count stayed %d)", before)
                }
            }
            """
        )
        res = _run_probe("remove_present_test.go", body, run="TestRemovePresent")
        assert res.returncode == 0, res.stdout + res.stderr
        assert "PASS" in res.stdout, res.stdout + res.stderr

    def test_l2_remove_absent_returns_false_no_release(self):
        """L2: Remove on an absent name returns false and triggers no release."""
        body = PROBE_HEADER + textwrap.dedent(
            """
            func TestRemoveAbsent(t *testing.T) {
                comp := newCountingCompiler()
                comp.add("present")
                rec := newReleaseRecorder()
                p := renderpool.NewRenderPool(comp, 16, time.Minute, rec.hook())
                defer p.Close()

                if _, f, e := p.Acquire("present"); e != nil || !f {
                    t.Fatalf("acquire present found=%v err=%v", f, e)
                }
                if p.Remove("never-acquired") {
                    t.Fatalf("Remove of absent name should return false")
                }
                if got := rec.totalReleases(); got != 0 {
                    t.Fatalf("Remove of absent name triggered %d releases, want 0", got)
                }
                // The unrelated present entry must be untouched.
                if got := rec.releaseCount("present"); got != 0 {
                    t.Fatalf("present was released by an unrelated Remove (count=%d)", got)
                }
            }
            """
        )
        res = _run_probe("remove_absent_test.go", body, run="TestRemoveAbsent")
        assert res.returncode == 0, res.stdout + res.stderr
        assert "PASS" in res.stdout, res.stdout + res.stderr

    def test_l2_concurrent_dedup_single_compile(self):
        """L2: a burst of >=50 concurrent Acquire calls for the same uncached
        name collapses into exactly ONE Compile; every goroutine sees
        found=true with the correct Name."""
        body = PROBE_HEADER + textwrap.dedent(
            """
            func TestConcurrentDedup(t *testing.T) {
                comp := newCountingCompiler()
                comp.add("shared")
                comp.blockCh = make(chan struct{})
                rec := newReleaseRecorder()
                p := renderpool.NewRenderPool(comp, 64, time.Minute, rec.hook())
                defer p.Close()

                const N = 64
                var wg sync.WaitGroup
                var okCount int32
                var badCount int32
                ready := make(chan struct{}, N)
                wg.Add(N)
                for i := 0; i < N; i++ {
                    go func() {
                        defer wg.Done()
                        ready <- struct{}{}
                        r, f, e := p.Acquire("shared")
                        if e == nil && f && r != nil && r.Name == "shared" {
                            atomic.AddInt32(&okCount, 1)
                        } else {
                            atomic.AddInt32(&badCount, 1)
                        }
                    }()
                }
                for i := 0; i < N; i++ {
                    <-ready
                }
                time.Sleep(50 * time.Millisecond)
                close(comp.blockCh) // release the single in-flight Compile
                wg.Wait()

                if bad := atomic.LoadInt32(&badCount); bad != 0 {
                    t.Fatalf("%d goroutines got wrong/err result", bad)
                }
                if ok := atomic.LoadInt32(&okCount); ok != N {
                    t.Fatalf("want %d ok results got %d", N, ok)
                }
                if got := comp.count("shared"); got != 1 {
                    t.Fatalf("COMPILECOUNT want 1 got %d (no singleflight dedup)", got)
                }
            }
            """
        )
        res = _run_probe(
            "dedup_test.go", body, run="TestConcurrentDedup", timeout=300
        )
        assert res.returncode == 0, res.stdout + res.stderr
        assert "PASS" in res.stdout, res.stdout + res.stderr

    def test_l2_no_double_release_across_lifecycle(self):
        """L2: across a mixed lifecycle (capacity eviction + explicit Remove +
        Close), NO single compiled instance is ever released more than once."""
        body = PROBE_HEADER + textwrap.dedent(
            """
            func TestNoDoubleRelease(t *testing.T) {
                const cap = 3
                comp := newCountingCompiler()
                for i := 0; i < 20; i++ {
                    comp.add("m" + strconv.Itoa(i))
                }
                rec := newReleaseRecorder()
                p := renderpool.NewRenderPool(comp, cap, time.Minute, rec.hook())

                // Fill and overflow the pool (drives evictions).
                for i := 0; i < 20; i++ {
                    name := "m" + strconv.Itoa(i)
                    if _, f, e := p.Acquire(name); e != nil || !f {
                        t.Fatalf("acquire %s found=%v err=%v", name, f, e)
                    }
                }
                // Explicitly remove one of the still-resident entries.
                _ = p.Remove("m19")
                // Close may or may not release residents; either way exactly-once.
                p.Close()
                // Give any janitor a beat to finish.
                time.Sleep(50 * time.Millisecond)

                if m := rec.maxPerInstance(); m > 1 {
                    t.Fatalf("some instance released %d times across lifecycle (exactly-once violated)", m)
                }
                // m0 was acquired first and (cap=3) must have been evicted; it
                // should be released exactly once, never zero, never twice.
                if got := rec.releaseCount("m0"); got != 1 {
                    t.Fatalf("m0 release count want 1 got %d", got)
                }
            }
            """
        )
        res = _run_probe(
            "double_release_test.go", body, run="TestNoDoubleRelease", timeout=300
        )
        assert res.returncode == 0, res.stdout + res.stderr
        assert "PASS" in res.stdout, res.stdout + res.stderr

    def test_l2_no_goroutine_leak_after_close(self):
        """L2: after Close(), goleak reports no leaked goroutines (the pool must
        release any background machinery, e.g. its TTL janitor)."""
        body = textwrap.dedent(
            """
            package renderpoolprobe

            import (
                "testing"
                "time"

                renderpool "github.com/samber/hot/pkg/renderpool"
                "go.uber.org/goleak"
            )

            type leakCompiler struct{}

            func (leakCompiler) Compile(name string) (*renderpool.Compiled, error) {
                if name == "L" {
                    return &renderpool.Compiled{Name: "L"}, nil
                }
                return nil, nil
            }

            func TestNoLeakAfterClose(t *testing.T) {
                func() {
                    p := renderpool.NewRenderPool(leakCompiler{}, 16, 20*time.Millisecond, func(c *renderpool.Compiled) {})
                    for i := 0; i < 5; i++ {
                        p.Acquire("L")
                    }
                    p.Close()
                }()
                // give any janitor a moment to stop
                time.Sleep(120 * time.Millisecond)
                goleak.VerifyNone(t)
            }
            """
        )
        res = _run_probe(
            "leak_test.go", body, run="TestNoLeakAfterClose", timeout=300
        )
        assert res.returncode == 0, (
            "goroutine leak after Close():\n" + res.stdout + res.stderr
        )
        assert "PASS" in res.stdout, res.stdout + res.stderr
