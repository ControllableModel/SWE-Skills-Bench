"""Tests for the `go-cache-hot` skill task — variant ext5.

Skill: go-cache-hot — Build a *Sharded Feature-Flag Resolver* inside the
`github.com/samber/hot` repository.

The ext5 task asks the agent to create `pkg/flags/flags.go` (and a
`pkg/flags/flags_test.go`) implementing a `FlagResolver` that answers
"is flag F enabled for tenant T?" at high concurrency while:
  - deriving a single DETERMINISTIC composite cache key from (tenant, flag),
  - partitioning cached entries across exactly `shards` independent partitions
    (a hot key must not serialize all readers; per-partition capacity bounds
    memory and eviction is independent per partition),
  - caching resolvable AND confirmed-unresolvable answers within the TTL,
  - NEVER caching infrastructure errors,
  - collapsing a burst of concurrent identical lookups into ONE Resolve,
  - honoring a TTL (a fresh Resolve is permitted after it elapses),
  - leaking no goroutines after Close().

Required public API (from the requirement doc):
  type FlagState struct { Tenant, Flag string; Enabled bool }
  type Provider interface { Resolve(keys []string) (map[string]*FlagState, error) }
  func NewFlagResolver(p Provider, shards uint64, capacityPerShard int, ttl time.Duration) *FlagResolver
  func (r *FlagResolver) IsEnabled(tenant, flag string) (enabled bool, found bool, err error)
  func (r *FlagResolver) Close()

Verification strategy:
  L1 — the deliverable files exist, go.mod is unmodified (still samber/hot,
       Go >= 1.22), `go build ./...` and `go vet ./pkg/flags/` pass, the exact
       required public API surface compiles when referenced from an independent
       package, and the agent's own `TestFlags*` tests pass (the native
       acceptance command).
  L2 — we DO NOT trust the agent's own test file. Instead we synthesize an
       INDEPENDENT probe package under REPO_DIR that imports the agent's
       `pkg/flags` package, drives it with our own counting/blocking Provider,
       and asserts concrete behaviors via the native `go test` toolchain:
         * resolvable pair cached after first Resolve (exactly one Resolve);
         * deterministic + partition-independent keys: distinct pairs spread
           across shards and evict independently of one another;
         * confirmed-unresolvable pair cached (found=false, asked at most once);
         * infrastructure error returned and NOT cached;
         * 50+ concurrent identical lookups collapse into ONE Resolve;
         * TTL expiry permits a fresh Resolve;
         * a determinism check that the SAME pair always lands consistently.
       A naive implementation (single undivided cache, re-resolve every call,
       non-deterministic keys, no concurrent dedup, error-caching, or no TTL)
       fails at least one probe.
"""

import os
import re
import shutil
import subprocess
import textwrap

import pytest

REPO_DIR = "/workspace/hot"
FLAGS_PKG = os.path.join(REPO_DIR, "pkg", "flags")
PROBE_PKG = os.path.join(REPO_DIR, "pkg", "flagsprobe")


def _run_go(args, timeout=300):
    """Run a go command from REPO_DIR with module-mode sane defaults."""
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
    """Write a single probe test file into pkg/flagsprobe and return its path."""
    os.makedirs(PROBE_PKG, exist_ok=True)
    path = os.path.join(PROBE_PKG, name)
    with open(path, "w") as fh:
        fh.write(body)
    return path


def _run_probe(name, body, run="", timeout=300):
    """Write a probe test file, run it, clean it up, return CompletedProcess."""
    path = _write_probe(name, body)
    try:
        args = ["test", "./pkg/flagsprobe/", "-count=1", "-v"]
        if run:
            args += ["-run", run]
        return _run_go(args, timeout=timeout)
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


# Common header reused by probe files. Imports the agent package and defines a
# concurrency-safe counting Provider that records per-composite-key Resolve
# counts and can optionally block to exercise singleflight-style dedup.
PROBE_HEADER = textwrap.dedent(
    """
    package flagsprobe

    import (
        "errors"
        "strconv"
        "sync"
        "sync/atomic"
        "testing"
        "time"

        flags "github.com/samber/hot/pkg/flags"
    )

    var _ = strconv.Itoa
    var _ = errors.New
    var _ = time.Now
    var _ = atomic.AddInt32

    // countingProvider records per-composite-key Resolve invocation counts and
    // per-key total entries seen. It is safe for concurrent use.
    type countingProvider struct {
        mu        sync.Mutex
        counts    map[string]int  // composite-key -> times that key appeared in a Resolve batch
        calls      int32          // total number of Resolve(...) invocations entered
        states    map[string]*flags.FlagState // composite-key -> resolvable state
        failKeys  map[string]int  // remaining infra failures per composite key
        blockCh   chan struct{}   // if non-nil, Resolve waits on it once entered
    }

    func newCountingProvider() *countingProvider {
        return &countingProvider{
            counts:   map[string]int{},
            states:   map[string]*flags.FlagState{},
            failKeys: map[string]int{},
        }
    }

    // put registers a resolvable state under the composite key that the
    // resolver is expected to derive. The resolver derives the key from
    // (tenant, flag); since the exact derivation is the agent's, the probe
    // accepts a state under ANY key the resolver asks for by matching on the
    // (tenant, flag) fields it carries. To make that robust we register by a
    // predicate map instead: see resolvableFor below.
    func (p *countingProvider) put(key string, st *flags.FlagState) {
        p.mu.Lock()
        p.states[key] = st
        p.mu.Unlock()
    }

    func (p *countingProvider) failNext(key string, n int) {
        p.mu.Lock()
        p.failKeys[key] = n
        p.mu.Unlock()
    }

    func (p *countingProvider) count(key string) int {
        p.mu.Lock()
        defer p.mu.Unlock()
        return p.counts[key]
    }

    func (p *countingProvider) totalCalls() int32 {
        return atomic.LoadInt32(&p.calls)
    }

    // distinctKeysSeen returns how many distinct composite keys this provider
    // was ever asked to resolve.
    func (p *countingProvider) distinctKeysSeen() int {
        p.mu.Lock()
        defer p.mu.Unlock()
        return len(p.counts)
    }
    """
)

# A provider that decides resolvability from the (tenant,flag) embedded in the
# state map keyed by the composite key. Because the resolver derives the
# composite key itself and we cannot know it in advance, our providers in the
# probes below are written to react to WHATEVER composite key arrives, using the
# fact that the resolver passes a stable composite key per (tenant,flag). We use
# an "enabled by default unless explicitly absent" strategy per probe. The
# common Resolve impl is appended here so all probes share identical semantics.
PROBE_HEADER += textwrap.dedent(
    """
    // Resolve answers every key present in p.states; honors per-key failures
    // and the optional block channel. Records counts and total call count.
    func (p *countingProvider) Resolve(keys []string) (map[string]*flags.FlagState, error) {
        atomic.AddInt32(&p.calls, 1)
        if p.blockCh != nil {
            <-p.blockCh
        }
        p.mu.Lock()
        defer p.mu.Unlock()
        out := map[string]*flags.FlagState{}
        for _, k := range keys {
            p.counts[k]++
            if rem, ok := p.failKeys[k]; ok && rem > 0 {
                p.failKeys[k] = rem - 1
                return nil, errors.New("infra failure for " + k)
            }
            if st, ok := p.states[k]; ok {
                cp := *st
                out[k] = &cp
            }
            // keys absent from p.states are simply not returned => unresolvable
        }
        return out, nil
    }
    """
)


@pytest.fixture(scope="module", autouse=True)
def ensure_go():
    """Ensure the go toolchain is present and module deps are downloaded."""
    if shutil.which("go") is None:
        pytest.skip("go toolchain not available in container")
    res = _run_go(["mod", "download"], timeout=400)
    yield res


# ---------------------------------------------------------------------------
# L1 — deliverable existence / well-formedness / compilation
# ---------------------------------------------------------------------------

class TestGoCacheHot:
    REPO_DIR = "/workspace/hot"

    def test_l1_flags_source_exists(self):
        """L1: pkg/flags/flags.go exists and is non-empty."""
        p = os.path.join(FLAGS_PKG, "flags.go")
        assert os.path.isfile(p), f"missing {p}"
        assert os.path.getsize(p) > 0, "flags.go is empty"

    def test_l1_flags_test_exists(self):
        """L1: pkg/flags/flags_test.go exists (agent's own tests)."""
        p = os.path.join(FLAGS_PKG, "flags_test.go")
        assert os.path.isfile(p), f"missing {p}"
        assert os.path.getsize(p) > 0, "flags_test.go is empty"

    def test_l1_go_mod_unmodified_module_path(self):
        """L1: still the samber/hot module and Go 1.22+ (no new 3rd-party deps)."""
        gomod = os.path.join(REPO_DIR, "go.mod")
        with open(gomod) as fh:
            text = fh.read()
        assert "module github.com/samber/hot" in text
        m = re.search(r"^go\s+(\d+)\.(\d+)", text, re.MULTILINE)
        assert m, "no go directive in go.mod"
        major, minor = int(m.group(1)), int(m.group(2))
        assert (major, minor) >= (1, 22), f"go {major}.{minor} < 1.22"

    def test_l1_build_whole_module(self):
        """L1: `go build ./...` succeeds with the new flags package present."""
        res = _run_go(["build", "./..."], timeout=400)
        assert res.returncode == 0, (
            "go build ./... failed:\n" + res.stdout + res.stderr
        )

    def test_l1_vet_flags_package(self):
        """L1: `go vet ./pkg/flags/` is clean (well-formed Go)."""
        res = _run_go(["vet", "./pkg/flags/"], timeout=300)
        assert res.returncode == 0, (
            "go vet ./pkg/flags/ failed:\n" + res.stdout + res.stderr
        )

    def test_l1_public_api_surface_compiles(self):
        """L1: the exact required public API (FlagState fields, Provider,
        NewFlagResolver(p, shards uint64, capacityPerShard int, ttl), IsEnabled
        returning (bool, bool, error), Close) compiles from an independent
        package."""
        body = PROBE_HEADER + textwrap.dedent(
            """
            func TestAPISurface(t *testing.T) {
                // Provider interface satisfied by our counting provider.
                var _ flags.Provider = newCountingProvider()

                // FlagState exported fields with expected types.
                st := flags.FlagState{Tenant: "t", Flag: "f", Enabled: true}
                _ = st.Tenant
                _ = st.Flag
                _ = st.Enabled

                p := newCountingProvider()
                // Constructor signature: (Provider, uint64, int, time.Duration).
                var shards uint64 = 8
                var capPer int = 16
                r := flags.NewFlagResolver(p, shards, capPer, time.Second)

                var enabled, found bool
                var err error
                enabled, found, err = r.IsEnabled("tenant", "flag")
                _ = enabled
                _ = found
                _ = err
                r.Close()
            }
            """
        )
        res = _run_probe("api_surface_test.go", body, run="TestAPISurface")
        assert res.returncode == 0, (
            "API surface probe failed to compile/run:\n" + res.stdout + res.stderr
        )
        assert "PASS" in res.stdout, res.stdout + res.stderr

    def test_l1_agent_tests_run(self):
        """L1: the agent's own TestFlags* tests pass (native acceptance command:
        `go test ./pkg/flags/ -run TestFlags -count=1`)."""
        res = _run_go(
            ["test", "./pkg/flags/", "-run", "TestFlags", "-count=1"],
            timeout=400,
        )
        assert res.returncode == 0, (
            "agent's own `go test ./pkg/flags/ -run TestFlags -count=1` failed:\n"
            + res.stdout + res.stderr
        )


# ---------------------------------------------------------------------------
# L2 — independent behavioral probes via native `go test`
# ---------------------------------------------------------------------------

    def test_l2_resolvable_cached_after_first(self):
        """L2: a resolvable (tenant,flag) pair looked up twice triggers exactly
        ONE Resolve and returns the same enabled value both times."""
        body = PROBE_HEADER + textwrap.dedent(
            """
            func TestResolvableCached(t *testing.T) {
                p := newCountingProvider()
                r := flags.NewFlagResolver(p, 16, 64, time.Minute)
                defer r.Close()

                // First lookup of an absent (tenant,flag) is unresolvable; to
                // test the resolvable+cached path we discover the composite key
                // the resolver uses by capturing it on the first Resolve call,
                // then registering a state. To stay independent of the exact
                // key, we instead make EVERY key resolvable-enabled by default.
                p.mu.Lock()
                // sentinel: enable any key seen, returned as Enabled=true
                p.mu.Unlock()

                // Use a provider variant where unknown keys resolve to enabled.
                // Re-wire: register on demand by precomputing nothing; instead
                // rely on the alwaysEnabled provider below for determinism.
                _ = p
                ap := newAlwaysEnabledProvider()
                r2 := flags.NewFlagResolver(ap, 16, 64, time.Minute)
                defer r2.Close()

                e1, f1, err1 := r2.IsEnabled("acme", "beta")
                if err1 != nil || !f1 {
                    t.Fatalf("first: enabled=%v found=%v err=%v", e1, f1, err1)
                }
                e2, f2, err2 := r2.IsEnabled("acme", "beta")
                if err2 != nil || !f2 {
                    t.Fatalf("second: enabled=%v found=%v err=%v", e2, f2, err2)
                }
                if e1 != e2 {
                    t.Fatalf("enabled value differed between cached lookups: %v vs %v", e1, e2)
                }
                if !e1 {
                    t.Fatalf("expected enabled=true, got %v", e1)
                }
                if got := ap.totalCalls(); got != 1 {
                    t.Fatalf("RESOLVECOUNT want 1 got %d (pair not cached within ttl)", got)
                }
            }

            // alwaysEnabledProvider resolves every key to Enabled=true and
            // records counts; lets the probe test caching without knowing the
            // composite key in advance.
            type alwaysEnabledProvider struct {
                mu     sync.Mutex
                calls  int32
                counts map[string]int
            }
            func newAlwaysEnabledProvider() *alwaysEnabledProvider {
                return &alwaysEnabledProvider{counts: map[string]int{}}
            }
            func (a *alwaysEnabledProvider) totalCalls() int32 { return atomic.LoadInt32(&a.calls) }
            func (a *alwaysEnabledProvider) count(k string) int {
                a.mu.Lock(); defer a.mu.Unlock(); return a.counts[k]
            }
            func (a *alwaysEnabledProvider) Resolve(keys []string) (map[string]*flags.FlagState, error) {
                atomic.AddInt32(&a.calls, 1)
                a.mu.Lock(); defer a.mu.Unlock()
                out := map[string]*flags.FlagState{}
                for _, k := range keys {
                    a.counts[k]++
                    out[k] = &flags.FlagState{Enabled: true}
                }
                return out, nil
            }
            """
        )
        res = _run_probe("resolvable_test.go", body, run="TestResolvableCached")
        assert res.returncode == 0, res.stdout + res.stderr
        assert "PASS" in res.stdout, res.stdout + res.stderr

    def test_l2_unresolvable_cached(self):
        """L2: a confirmed-unresolvable pair returns found=false on repeated
        lookups and is resolved at MOST once within the ttl (negative caching)."""
        body = PROBE_HEADER + textwrap.dedent(
            """
            func TestUnresolvableCached(t *testing.T) {
                // never-resolving provider: returns empty map for every key.
                np := &neverProvider{counts: map[string]int{}}
                r := flags.NewFlagResolver(np, 16, 64, time.Minute)
                defer r.Close()

                e1, f1, err1 := r.IsEnabled("ghost", "x")
                if err1 != nil || f1 || e1 {
                    t.Fatalf("first miss: enabled=%v found=%v err=%v", e1, f1, err1)
                }
                e2, f2, err2 := r.IsEnabled("ghost", "x")
                if err2 != nil || f2 || e2 {
                    t.Fatalf("second miss: enabled=%v found=%v err=%v", e2, f2, err2)
                }
                if got := np.totalCalls(); got != 1 {
                    t.Fatalf("RESOLVECOUNT want 1 got %d (unresolvable not negatively cached)", got)
                }
            }

            type neverProvider struct {
                mu     sync.Mutex
                calls  int32
                counts map[string]int
            }
            func (n *neverProvider) totalCalls() int32 { return atomic.LoadInt32(&n.calls) }
            func (n *neverProvider) Resolve(keys []string) (map[string]*flags.FlagState, error) {
                atomic.AddInt32(&n.calls, 1)
                n.mu.Lock(); defer n.mu.Unlock()
                for _, k := range keys { n.counts[k]++ }
                return map[string]*flags.FlagState{}, nil
            }
            """
        )
        res = _run_probe("unresolvable_test.go", body, run="TestUnresolvableCached")
        assert res.returncode == 0, res.stdout + res.stderr
        assert "PASS" in res.stdout, res.stdout + res.stderr

    def test_l2_infra_error_not_cached(self):
        """L2: an infrastructure error is returned to the caller and NOT
        remembered; a later healthy lookup for the same pair succeeds."""
        body = PROBE_HEADER + textwrap.dedent(
            """
            func TestErrorNotCached(t *testing.T) {
                fp := &flakyProvider{counts: map[string]int{}, failFirst: true}
                r := flags.NewFlagResolver(fp, 16, 64, time.Minute)
                defer r.Close()

                _, _, e1 := r.IsEnabled("corp", "feature")
                if e1 == nil {
                    t.Fatalf("expected infra error on first lookup, got nil")
                }
                en, f2, e2 := r.IsEnabled("corp", "feature")
                if e2 != nil {
                    t.Fatalf("second lookup unexpectedly errored: %v (error was cached)", e2)
                }
                if !f2 || !en {
                    t.Fatalf("second lookup: enabled=%v found=%v (expected resolvable true)", en, f2)
                }
                if got := fp.totalCalls(); got < 2 {
                    t.Fatalf("RESOLVECOUNT want >=2 got %d (error must trigger a re-resolve)", got)
                }
            }

            type flakyProvider struct {
                mu        sync.Mutex
                calls     int32
                counts    map[string]int
                failFirst bool
                failed    bool
            }
            func (f *flakyProvider) totalCalls() int32 { return atomic.LoadInt32(&f.calls) }
            func (f *flakyProvider) Resolve(keys []string) (map[string]*flags.FlagState, error) {
                atomic.AddInt32(&f.calls, 1)
                f.mu.Lock(); defer f.mu.Unlock()
                for _, k := range keys { f.counts[k]++ }
                if f.failFirst && !f.failed {
                    f.failed = true
                    return nil, errors.New("transient infra failure")
                }
                out := map[string]*flags.FlagState{}
                for _, k := range keys {
                    out[k] = &flags.FlagState{Enabled: true}
                }
                return out, nil
            }
            """
        )
        res = _run_probe("error_test.go", body, run="TestErrorNotCached")
        assert res.returncode == 0, res.stdout + res.stderr
        assert "PASS" in res.stdout, res.stdout + res.stderr

    def test_l2_concurrent_dedup_single_resolve(self):
        """L2: 50+ concurrent lookups of the SAME uncached pair collapse into a
        single Resolve for that key; all goroutines observe the same result."""
        body = PROBE_HEADER + textwrap.dedent(
            """
            func TestConcurrentDedup(t *testing.T) {
                ap := &blockingEnabledProvider{counts: map[string]int{}, blockCh: make(chan struct{})}
                r := flags.NewFlagResolver(ap, 64, 256, time.Minute)
                defer r.Close()

                const N = 64 // >= 50 goroutines
                var wg sync.WaitGroup
                var okCount int32
                var badCount int32
                var enabledTrue int32
                ready := make(chan struct{}, N)
                wg.Add(N)
                for i := 0; i < N; i++ {
                    go func() {
                        defer wg.Done()
                        ready <- struct{}{}
                        en, f, e := r.IsEnabled("hot", "tenant")
                        if e == nil && f {
                            atomic.AddInt32(&okCount, 1)
                            if en {
                                atomic.AddInt32(&enabledTrue, 1)
                            }
                        } else {
                            atomic.AddInt32(&badCount, 1)
                        }
                    }()
                }
                for i := 0; i < N; i++ {
                    <-ready
                }
                time.Sleep(60 * time.Millisecond) // let all block on the resolver
                close(ap.blockCh)
                wg.Wait()

                if bad := atomic.LoadInt32(&badCount); bad != 0 {
                    t.Fatalf("%d goroutines got wrong/err result", bad)
                }
                if ok := atomic.LoadInt32(&okCount); ok != N {
                    t.Fatalf("want %d ok results got %d", N, ok)
                }
                if et := atomic.LoadInt32(&enabledTrue); et != N {
                    t.Fatalf("want all %d goroutines to observe enabled=true, got %d", N, et)
                }
                if got := ap.totalCalls(); got != 1 {
                    t.Fatalf("RESOLVECOUNT want 1 got %d (no concurrent dedup / singleflight)", got)
                }
            }

            type blockingEnabledProvider struct {
                mu      sync.Mutex
                calls   int32
                counts  map[string]int
                blockCh chan struct{}
            }
            func (b *blockingEnabledProvider) totalCalls() int32 { return atomic.LoadInt32(&b.calls) }
            func (b *blockingEnabledProvider) Resolve(keys []string) (map[string]*flags.FlagState, error) {
                atomic.AddInt32(&b.calls, 1)
                if b.blockCh != nil {
                    <-b.blockCh
                }
                b.mu.Lock(); defer b.mu.Unlock()
                out := map[string]*flags.FlagState{}
                for _, k := range keys {
                    b.counts[k]++
                    out[k] = &flags.FlagState{Enabled: true}
                }
                return out, nil
            }
            """
        )
        res = _run_probe("dedup_test.go", body, run="TestConcurrentDedup", timeout=300)
        assert res.returncode == 0, res.stdout + res.stderr
        assert "PASS" in res.stdout, res.stdout + res.stderr

    def test_l2_ttl_expiry_triggers_refresh(self):
        """L2: after a short TTL elapses, a re-lookup of a previously-resolved
        pair allows a fresh Resolve; within the TTL it does not."""
        body = PROBE_HEADER + textwrap.dedent(
            """
            func TestTTLExpiry(t *testing.T) {
                ap := &countingEnabledProvider{counts: map[string]int{}}
                r := flags.NewFlagResolver(ap, 16, 64, 80*time.Millisecond)
                defer r.Close()

                if _, f, e := r.IsEnabled("t1", "f1"); e != nil || !f {
                    t.Fatalf("first lookup found=%v err=%v", f, e)
                }
                if _, f, e := r.IsEnabled("t1", "f1"); e != nil || !f { // within ttl -> cached
                    t.Fatalf("cached lookup found=%v err=%v", f, e)
                }
                if got := ap.totalCalls(); got != 1 {
                    t.Fatalf("RESOLVECOUNT before expiry want 1 got %d", got)
                }
                time.Sleep(220 * time.Millisecond) // exceed ttl
                if _, f, e := r.IsEnabled("t1", "f1"); e != nil || !f {
                    t.Fatalf("post-ttl lookup found=%v err=%v", f, e)
                }
                if got := ap.totalCalls(); got < 2 {
                    t.Fatalf("RESOLVECOUNT after expiry want >=2 got %d (ttl not honored)", got)
                }
            }

            type countingEnabledProvider struct {
                mu     sync.Mutex
                calls  int32
                counts map[string]int
            }
            func (c *countingEnabledProvider) totalCalls() int32 { return atomic.LoadInt32(&c.calls) }
            func (c *countingEnabledProvider) Resolve(keys []string) (map[string]*flags.FlagState, error) {
                atomic.AddInt32(&c.calls, 1)
                c.mu.Lock(); defer c.mu.Unlock()
                out := map[string]*flags.FlagState{}
                for _, k := range keys {
                    c.counts[k]++
                    out[k] = &flags.FlagState{Enabled: true}
                }
                return out, nil
            }
            """
        )
        res = _run_probe("ttl_test.go", body, run="TestTTLExpiry")
        assert res.returncode == 0, res.stdout + res.stderr
        assert "PASS" in res.stdout, res.stdout + res.stderr

    def test_l2_deterministic_key_same_pair(self):
        """L2: the (tenant,flag) -> composite key derivation is DETERMINISTIC:
        the same pair always maps to the same key, so a repeated lookup hits the
        cache (one Resolve) while a DIFFERENT pair causes a separate Resolve."""
        body = PROBE_HEADER + textwrap.dedent(
            """
            func TestDeterministicKey(t *testing.T) {
                p := newCountingProvider()
                r := flags.NewFlagResolver(p, 16, 64, time.Minute)
                defer r.Close()

                // Register two distinct pairs as resolvable by recording their
                // composite keys on first sight (provider returns enabled for
                // every key, but we count distinct keys to detect collisions/
                // nondeterminism).
                _ = p
                ap := &keyTrackingProvider{counts: map[string]int{}}
                r2 := flags.NewFlagResolver(ap, 16, 64, time.Minute)
                defer r2.Close()

                // Same pair looked up 5x: deterministic key => exactly 1 Resolve.
                for i := 0; i < 5; i++ {
                    if _, f, e := r2.IsEnabled("alpha", "x"); e != nil || !f {
                        t.Fatalf("iter %d alpha/x found=%v err=%v", i, f, e)
                    }
                }
                if got := ap.totalCalls(); got != 1 {
                    t.Fatalf("same pair 5x: RESOLVECOUNT want 1 got %d (non-deterministic key)", got)
                }
                if dk := ap.distinctKeys(); dk != 1 {
                    t.Fatalf("same pair produced %d distinct composite keys (must be 1)", dk)
                }

                // A different pair must produce a NEW key and a new Resolve.
                if _, f, e := r2.IsEnabled("alpha", "y"); e != nil || !f {
                    t.Fatalf("alpha/y found=%v err=%v", f, e)
                }
                if got := ap.totalCalls(); got != 2 {
                    t.Fatalf("distinct pair: RESOLVECOUNT want 2 got %d", got)
                }
                if dk := ap.distinctKeys(); dk != 2 {
                    t.Fatalf("two distinct pairs must yield 2 distinct keys, got %d (key collision)", dk)
                }
            }

            type keyTrackingProvider struct {
                mu     sync.Mutex
                calls  int32
                counts map[string]int
            }
            func (k *keyTrackingProvider) totalCalls() int32 { return atomic.LoadInt32(&k.calls) }
            func (k *keyTrackingProvider) distinctKeys() int {
                k.mu.Lock(); defer k.mu.Unlock(); return len(k.counts)
            }
            func (k *keyTrackingProvider) Resolve(keys []string) (map[string]*flags.FlagState, error) {
                atomic.AddInt32(&k.calls, 1)
                k.mu.Lock(); defer k.mu.Unlock()
                out := map[string]*flags.FlagState{}
                for _, key := range keys {
                    k.counts[key]++
                    out[key] = &flags.FlagState{Enabled: true}
                }
                return out, nil
            }
            """
        )
        res = _run_probe("detkey_test.go", body, run="TestDeterministicKey")
        assert res.returncode == 0, res.stdout + res.stderr
        assert "PASS" in res.stdout, res.stdout + res.stderr

    def test_l2_sharded_independent_eviction(self):
        """L2: entries are partitioned across `shards` and evicted INDEPENDENTLY
        per partition. With a tiny capacityPerShard but many shards, the total
        live cache must exceed a single partition's capacity — i.e. inserting
        more distinct pairs than capacityPerShard does NOT evict everything down
        to capacityPerShard (which a single undivided cache would do).

        Strategy: shards=8, capacityPerShard=2 (single-cache cap would be 2).
        Insert many distinct pairs, then re-look them all up and count how many
        were still cached (no fresh Resolve). With true sharding the number of
        retained-without-refetch pairs must exceed capacityPerShard, because
        capacity is per-partition. A single undivided cache of size 2 could
        retain at most ~2.
        """
        body = PROBE_HEADER + textwrap.dedent(
            """
            func TestShardedEviction(t *testing.T) {
                const shards = 8
                const capPer = 2
                ap := &countAllProvider{counts: map[string]int{}}
                r := flags.NewFlagResolver(ap, shards, capPer, time.Minute)
                defer r.Close()

                const M = 200
                // Insert M distinct pairs.
                for i := 0; i < M; i++ {
                    f := "flag" + strconv.Itoa(i)
                    if _, fo, e := r.IsEnabled("tenant", f); e != nil || !fo {
                        t.Fatalf("insert %d found=%v err=%v", i, fo, e)
                    }
                }
                callsAfterInsert := ap.totalCalls()
                if callsAfterInsert < M {
                    t.Fatalf("expected at least %d resolves on first pass, got %d", M, callsAfterInsert)
                }

                // Re-look up all M; count how many were retained (no extra resolve).
                retained := 0
                for i := 0; i < M; i++ {
                    f := "flag" + strconv.Itoa(i)
                    key := "tenant\\x00" + f // not the real key; we measure via call delta
                    _ = key
                    before := ap.totalCalls()
                    if _, fo, e := r.IsEnabled("tenant", f); e != nil || !fo {
                        t.Fatalf("relookup %d found=%v err=%v", i, fo, e)
                    }
                    after := ap.totalCalls()
                    if after == before {
                        retained++ // served from cache => no new Resolve
                    }
                }

                // A single undivided cache of size capPer=2 could retain at most
                // ~capPer pairs. With 8 independent partitions each holding ~2,
                // the retained set must be materially larger than a single
                // partition's capacity.
                if retained <= capPer {
                    t.Fatalf("sharding not effective: retained=%d <= capacityPerShard=%d "+
                        "(looks like a single undivided cache)", retained, capPer)
                }
                // Sanity upper bound: cannot retain more than shards*capPer.
                if retained > shards*capPer {
                    t.Fatalf("retained=%d exceeds shards*capacityPerShard=%d "+
                        "(per-shard capacity not enforced)", retained, shards*capPer)
                }
            }

            type countAllProvider struct {
                mu     sync.Mutex
                calls  int32
                counts map[string]int
            }
            func (c *countAllProvider) totalCalls() int32 { return atomic.LoadInt32(&c.calls) }
            func (c *countAllProvider) Resolve(keys []string) (map[string]*flags.FlagState, error) {
                atomic.AddInt32(&c.calls, 1)
                c.mu.Lock(); defer c.mu.Unlock()
                out := map[string]*flags.FlagState{}
                for _, k := range keys {
                    c.counts[k]++
                    out[k] = &flags.FlagState{Enabled: true}
                }
                return out, nil
            }
            """
        )
        res = _run_probe("shard_test.go", body, run="TestShardedEviction", timeout=300)
        assert res.returncode == 0, res.stdout + res.stderr
        assert "PASS" in res.stdout, res.stdout + res.stderr

    def test_l2_distinct_pairs_isolated(self):
        """L2: distinct (tenant,flag) pairs return their own answers (no key
        mixups across tenants/flags), and an enabled pair vs a disabled pair are
        not conflated."""
        body = PROBE_HEADER + textwrap.dedent(
            """
            func TestDistinctPairs(t *testing.T) {
                mp := &mappedProvider{
                    counts: map[string]int{},
                    decide: func(k string) (*flags.FlagState, bool) {
                        // enabled iff the composite key contains "on", disabled
                        // iff it contains "off"; absent otherwise. The probe only
                        // controls (tenant,flag), so we encode intent there.
                        return nil, false
                    },
                }
                _ = mp

                // Use a provider that enables flags whose flag name starts with
                // "on" and disables those starting with "off"; unresolvable
                // otherwise. Because the resolver derives the key, we instead key
                // off the tenant/flag we pass — but the provider only sees the
                // composite key. To stay robust, we register concrete enabled and
                // disabled states keyed by capture: first call records mapping.
                pr := newPairProvider()
                r := flags.NewFlagResolver(pr, 16, 64, time.Minute)
                defer r.Close()

                // Provider returns Enabled=true for the FIRST distinct key it
                // sees and Enabled=false for the SECOND; we then verify the two
                // pairs keep their distinct enabled values across repeats.
                eOn, fOn, errOn := r.IsEnabled("t", "alpha")
                if errOn != nil || !fOn {
                    t.Fatalf("alpha found=%v err=%v", fOn, errOn)
                }
                eOff, fOff, errOff := r.IsEnabled("t", "beta")
                if errOff != nil || !fOff {
                    t.Fatalf("beta found=%v err=%v", fOff, errOff)
                }
                if eOn == eOff {
                    t.Fatalf("two distinct pairs got the same enabled value %v (key mixup)", eOn)
                }
                // Repeat several rounds: values must be stable per pair.
                for round := 0; round < 3; round++ {
                    a, fa, ea := r.IsEnabled("t", "alpha")
                    b2, fb, eb := r.IsEnabled("t", "beta")
                    if ea != nil || eb != nil || !fa || !fb {
                        t.Fatalf("round %d alpha(f=%v e=%v) beta(f=%v e=%v)", round, fa, ea, fb, eb)
                    }
                    if a != eOn || b2 != eOff {
                        t.Fatalf("round %d value drift: alpha %v->%v beta %v->%v", round, eOn, a, eOff, b2)
                    }
                }
            }

            // pairProvider returns Enabled=true for the first distinct composite
            // key it ever sees, Enabled=false for every other distinct key. This
            // makes two distinct pairs deterministically differ in Enabled while
            // staying independent of the agent's key-derivation scheme.
            type pairProvider struct {
                mu     sync.Mutex
                seen   map[string]bool // key -> enabled value assigned
                first  bool
            }
            func newPairProvider() *pairProvider { return &pairProvider{seen: map[string]bool{}} }
            func (p *pairProvider) Resolve(keys []string) (map[string]*flags.FlagState, error) {
                p.mu.Lock(); defer p.mu.Unlock()
                out := map[string]*flags.FlagState{}
                for _, k := range keys {
                    if v, ok := p.seen[k]; ok {
                        out[k] = &flags.FlagState{Enabled: v}
                        continue
                    }
                    en := !p.first
                    p.first = true
                    p.seen[k] = en
                    out[k] = &flags.FlagState{Enabled: en}
                }
                return out, nil
            }

            // mappedProvider is unused scaffolding retained for clarity.
            type mappedProvider struct {
                mu     sync.Mutex
                counts map[string]int
                decide func(string) (*flags.FlagState, bool)
            }
            func (m *mappedProvider) Resolve(keys []string) (map[string]*flags.FlagState, error) {
                return map[string]*flags.FlagState{}, nil
            }
            """
        )
        res = _run_probe("distinct_test.go", body, run="TestDistinctPairs")
        assert res.returncode == 0, res.stdout + res.stderr
        assert "PASS" in res.stdout, res.stdout + res.stderr

    def test_l2_no_goroutine_leak_after_close(self):
        """L2: after Close(), goleak reports no leaked goroutines (the resolver
        must release any background machinery it started)."""
        body = textwrap.dedent(
            """
            package flagsprobe

            import (
                "testing"
                "time"

                flags "github.com/samber/hot/pkg/flags"
                "go.uber.org/goleak"
            )

            type leakProvider struct{}

            func (leakProvider) Resolve(keys []string) (map[string]*flags.FlagState, error) {
                out := map[string]*flags.FlagState{}
                for _, k := range keys {
                    out[k] = &flags.FlagState{Enabled: true}
                }
                return out, nil
            }

            func TestNoLeakAfterClose(t *testing.T) {
                func() {
                    r := flags.NewFlagResolver(leakProvider{}, 16, 64, 20*time.Millisecond)
                    for i := 0; i < 5; i++ {
                        r.IsEnabled("tenant", "flag")
                    }
                    r.Close()
                }()
                time.Sleep(120 * time.Millisecond) // let any janitor stop
                goleak.VerifyNone(t)
            }
            """
        )
        res = _run_probe("leak_test.go", body, run="TestNoLeakAfterClose", timeout=300)
        assert res.returncode == 0, (
            "goroutine leak after Close():\n" + res.stdout + res.stderr
        )
        assert "PASS" in res.stdout, res.stdout + res.stderr
