"""Tests for the `go-cache-hot` skill task (variant ext7).

Skill: go-cache-hot — Build a Copy-Isolated Config Snapshot Cache inside the
`github.com/samber/hot` repository.

The ext7 task asks the agent to create a NEW package `pkg/configcache` with:
  - `pkg/configcache/configcache.go`  — the `ConfigCache` implementation
  - `pkg/configcache/configcache_test.go` — the agent's deterministic tests

Required API surface (re-derived from tasks/ext7/go-cache-hot.md):

    type Config struct {
        Namespace string
        Settings  map[string]string  // mutable
        Allow     []string           // mutable
    }

    type Store interface {
        Get(namespace string) (*Config, bool, error)
    }

    func NewConfigCache(store Store, capacity int, ttl time.Duration) *ConfigCache
    func (c *ConfigCache) Resolve(namespace string) (*Config, bool, error)
    func (c *ConfigCache) Close()

Central requirement: **copy / mutation isolation**. Each `Resolve` must hand
back an independently-mutable view — distinct `Settings` map header and `Allow`
backing array — so one caller's edits never leak into a later caller's config
for the same namespace, even though the entry stays cached (no `store` refetch
in between). Plus: TTL-respecting cache hits (re-resolve within ttl => no
store.Get), found=false for unknown namespaces (no error), concurrent dedup of
a burst of resolves for one uncached namespace into a single store.Get, and no
goroutine leak after Close().

What this file verifies:
  L1 — the deliverable files exist, the module is unmodified (still
       samber/hot, Go 1.22+, no new third-party deps), the whole module builds
       and vets, the exact required public API compiles against an independent
       package, and the agent's own TestConfigCache test passes.
  L2 — we DO NOT trust the agent's own test file. Instead we synthesize an
       independent probe package under REPO_DIR that imports the agent's
       `pkg/configcache` package, drives it with our own counting/blocking
       Store, and asserts the concrete behaviors via the native `go test`
       toolchain (parsing PASS/FAIL from stdout). A naive implementation that
       hands back a shared `*Config` pointer, shares inner maps/slices between
       callers, re-fetches on every resolve, or never caches must fail at least
       one probe.

Native acceptance command this drives (per the doc):
    go test ./pkg/configcache/ -run TestConfigCache -count=1
"""

import os
import re
import shutil
import subprocess
import textwrap

import pytest

REPO_DIR = "/workspace/hot"
CC_PKG = os.path.join(REPO_DIR, "pkg", "configcache")
PROBE_PKG = os.path.join(REPO_DIR, "pkg", "configcacheprobe")


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
    """Write a single-file probe test into pkg/configcacheprobe; return path."""
    os.makedirs(PROBE_PKG, exist_ok=True)
    path = os.path.join(PROBE_PKG, name)
    with open(path, "w") as fh:
        fh.write(body)
    return path


def _run_probe(name, body, run="", timeout=300):
    """Write a probe test file, run it, clean it up, return CompletedProcess."""
    path = _write_probe(name, body)
    try:
        args = ["test", "./pkg/configcacheprobe/", "-count=1", "-v"]
        if run:
            args += ["-run", run]
        return _run_go(args, timeout=timeout)
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


# Common header reused by probe files. Imports the agent package and declares a
# concurrency-safe Store that records per-namespace Get counts and can block.
PROBE_HEADER = textwrap.dedent(
    """
    package configcacheprobe

    import (
        "errors"
        "strconv"
        "sync"
        "sync/atomic"
        "testing"
        "time"

        configcache "github.com/samber/hot/pkg/configcache"
    )

    var _ = strconv.Itoa
    var _ = errors.New
    var _ = time.Now
    var _ = atomic.AddInt32

    // countingStore records per-namespace Get counts and is concurrency safe.
    // Each Get returns a FRESH deep copy of the stored config, so any isolation
    // failure observed by the probe is the cache's fault, not the store's.
    type countingStore struct {
        mu       sync.Mutex
        counts   map[string]int
        data     map[string]*configcache.Config
        failNS   map[string]int // remaining failures per namespace
        blockCh  chan struct{}  // if non-nil, Get waits on it once entered
        entered  int32
    }

    func newCountingStore() *countingStore {
        return &countingStore{
            counts: map[string]int{},
            data:   map[string]*configcache.Config{},
            failNS: map[string]int{},
        }
    }

    func (s *countingStore) put(c *configcache.Config) {
        s.mu.Lock()
        s.data[c.Namespace] = c
        s.mu.Unlock()
    }

    func (s *countingStore) failNext(ns string, n int) {
        s.mu.Lock()
        s.failNS[ns] = n
        s.mu.Unlock()
    }

    func (s *countingStore) count(ns string) int {
        s.mu.Lock()
        defer s.mu.Unlock()
        return s.counts[ns]
    }

    func (s *countingStore) Get(namespace string) (*configcache.Config, bool, error) {
        atomic.AddInt32(&s.entered, 1)
        if s.blockCh != nil {
            <-s.blockCh
        }
        s.mu.Lock()
        defer s.mu.Unlock()
        s.counts[namespace]++
        if rem, ok := s.failNS[namespace]; ok && rem > 0 {
            s.failNS[namespace] = rem - 1
            return nil, false, errors.New("infra failure for " + namespace)
        }
        c, ok := s.data[namespace]
        if !ok {
            return nil, false, nil
        }
        // hand back a deep copy so the cache's own isolation is what we test
        cp := &configcache.Config{Namespace: c.Namespace}
        cp.Settings = map[string]string{}
        for k, v := range c.Settings {
            cp.Settings[k] = v
        }
        cp.Allow = append([]string(nil), c.Allow...)
        return cp, true, nil
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

    def test_l1_configcache_source_exists(self):
        """L1: pkg/configcache/configcache.go exists and is non-empty."""
        p = os.path.join(CC_PKG, "configcache.go")
        assert os.path.isfile(p), f"missing {p}"
        assert os.path.getsize(p) > 0, "configcache.go is empty"

    def test_l1_configcache_test_exists(self):
        """L1: pkg/configcache/configcache_test.go exists (agent's own tests)."""
        p = os.path.join(CC_PKG, "configcache_test.go")
        assert os.path.isfile(p), f"missing {p}"
        assert os.path.getsize(p) > 0, "configcache_test.go is empty"

    def test_l1_go_mod_unmodified_module_path(self):
        """L1: still the samber/hot module and Go 1.22+ (no module-path edits)."""
        gomod = os.path.join(REPO_DIR, "go.mod")
        with open(gomod) as fh:
            text = fh.read()
        assert "module github.com/samber/hot" in text
        m = re.search(r"^go\s+(\d+)\.(\d+)", text, re.MULTILINE)
        assert m, "no go directive in go.mod"
        major, minor = int(m.group(1)), int(m.group(2))
        assert (major, minor) >= (1, 22), f"go {major}.{minor} < 1.22"

    def test_l1_build_whole_module(self):
        """L1: `go build ./...` succeeds with the new configcache package."""
        res = _run_go(["build", "./..."], timeout=400)
        assert res.returncode == 0, (
            "go build ./... failed:\n" + res.stdout + res.stderr
        )

    def test_l1_vet_configcache_package(self):
        """L1: `go vet` of the configcache package is clean (well-formed Go)."""
        res = _run_go(["vet", "./pkg/configcache/"], timeout=300)
        assert res.returncode == 0, (
            "go vet ./pkg/configcache/ failed:\n" + res.stdout + res.stderr
        )

    def test_l1_public_api_surface_compiles(self):
        """L1: the exact required public API (Config fields, Store, ctor,
        Resolve, Close) compiles when referenced from an independent package."""
        body = PROBE_HEADER + textwrap.dedent(
            """
            func TestAPISurface(t *testing.T) {
                var _ configcache.Store = newCountingStore()
                c := configcache.Config{
                    Namespace: "svc",
                    Settings:  map[string]string{"k": "v"},
                    Allow:     []string{"a"},
                }
                _ = c.Namespace
                _ = c.Settings
                _ = c.Allow
                s := newCountingStore()
                cache := configcache.NewConfigCache(s, 8, time.Second)
                var cfg *configcache.Config
                var found bool
                var err error
                cfg, found, err = cache.Resolve("svc")
                _ = cfg
                _ = found
                _ = err
                cache.Close()
            }
            """
        )
        res = _run_probe("api_surface_test.go", body, run="TestAPISurface")
        assert res.returncode == 0, (
            "API surface probe failed to compile/run:\n" + res.stdout + res.stderr
        )
        assert "PASS" in res.stdout, res.stdout + res.stderr

    def test_l1_agent_tests_run(self):
        """L1: the agent's own TestConfigCache* tests pass (acceptance command:
        go test ./pkg/configcache/ -run TestConfigCache -count=1)."""
        res = _run_go(
            ["test", "./pkg/configcache/", "-run", "TestConfigCache", "-count=1"],
            timeout=400,
        )
        assert res.returncode == 0, (
            "agent's own go test ./pkg/configcache -run TestConfigCache failed:\n"
            + res.stdout + res.stderr
        )


# ---------------------------------------------------------------------------
# L2 — independent behavioral probes via native `go test`
# ---------------------------------------------------------------------------

    def test_l2_hit_cached_within_ttl(self):
        """L2: an existing namespace resolved twice within ttl triggers exactly
        ONE store.Get and returns correct data both times."""
        body = PROBE_HEADER + textwrap.dedent(
            """
            func TestHitCached(t *testing.T) {
                s := newCountingStore()
                s.put(&configcache.Config{
                    Namespace: "svc",
                    Settings:  map[string]string{"region": "eu"},
                    Allow:     []string{"alice"},
                })
                cache := configcache.NewConfigCache(s, 16, time.Minute)
                defer cache.Close()

                r1, f1, e1 := cache.Resolve("svc")
                if e1 != nil || !f1 || r1 == nil {
                    t.Fatalf("first resolve: found=%v err=%v cfg=%v", f1, e1, r1)
                }
                r2, f2, e2 := cache.Resolve("svc")
                if e2 != nil || !f2 || r2 == nil {
                    t.Fatalf("second resolve: found=%v err=%v", f2, e2)
                }
                if r1.Settings["region"] != "eu" || r2.Settings["region"] != "eu" {
                    t.Fatalf("data mismatch r1=%+v r2=%+v", r1, r2)
                }
                if r1.Namespace != "svc" || r2.Namespace != "svc" {
                    t.Fatalf("namespace mismatch r1=%q r2=%q", r1.Namespace, r2.Namespace)
                }
                if got := s.count("svc"); got != 1 {
                    t.Fatalf("FETCHCOUNT want 1 got %d (re-resolve refetched)", got)
                }
            }
            """
        )
        res = _run_probe("hit_test.go", body, run="TestHitCached")
        assert res.returncode == 0, res.stdout + res.stderr
        assert "PASS" in res.stdout, res.stdout + res.stderr

    def test_l2_unknown_namespace(self):
        """L2: an unknown namespace returns found=false with NO error and a nil
        config (the central 'not found' contract)."""
        body = PROBE_HEADER + textwrap.dedent(
            """
            func TestUnknown(t *testing.T) {
                s := newCountingStore() // no data => everything missing
                cache := configcache.NewConfigCache(s, 16, time.Minute)
                defer cache.Close()

                r, f, e := cache.Resolve("nope")
                if e != nil {
                    t.Fatalf("unknown namespace returned error: %v", e)
                }
                if f {
                    t.Fatalf("unknown namespace returned found=true")
                }
                if r != nil {
                    t.Fatalf("unknown namespace returned non-nil config: %+v", r)
                }
            }
            """
        )
        res = _run_probe("unknown_test.go", body, run="TestUnknown")
        assert res.returncode == 0, res.stdout + res.stderr
        assert "PASS" in res.stdout, res.stdout + res.stderr

    def test_l2_error_not_remembered(self):
        """L2: an infrastructure error is surfaced to the caller and NOT cached;
        a later healthy resolve of the same namespace succeeds."""
        body = PROBE_HEADER + textwrap.dedent(
            """
            func TestErrorNotCached(t *testing.T) {
                s := newCountingStore()
                s.put(&configcache.Config{
                    Namespace: "db",
                    Settings:  map[string]string{"host": "primary"},
                    Allow:     []string{"svc"},
                })
                s.failNext("db", 1) // first Get for db fails
                cache := configcache.NewConfigCache(s, 16, time.Minute)
                defer cache.Close()

                _, _, e1 := cache.Resolve("db")
                if e1 == nil {
                    t.Fatalf("expected error on first resolve of db, got nil")
                }
                r2, f2, e2 := cache.Resolve("db")
                if e2 != nil {
                    t.Fatalf("second resolve errored: %v (failure was cached)", e2)
                }
                if !f2 || r2 == nil || r2.Settings["host"] != "primary" {
                    t.Fatalf("second resolve: found=%v cfg=%+v", f2, r2)
                }
                if got := s.count("db"); got < 2 {
                    t.Fatalf("FETCHCOUNT want >=2 got %d (failure must refetch)", got)
                }
            }
            """
        )
        res = _run_probe("err_test.go", body, run="TestErrorNotCached")
        assert res.returncode == 0, res.stdout + res.stderr
        assert "PASS" in res.stdout, res.stdout + res.stderr

    def test_l2_settings_map_isolation(self):
        """L2 (CENTRAL): writing a new key into a returned config's Settings map
        must NOT appear in the config a later caller receives for the same
        namespace — even though no store refetch happens in between."""
        body = PROBE_HEADER + textwrap.dedent(
            """
            func TestSettingsIsolation(t *testing.T) {
                s := newCountingStore()
                s.put(&configcache.Config{
                    Namespace: "svc",
                    Settings:  map[string]string{"a": "1"},
                    Allow:     []string{"x"},
                })
                cache := configcache.NewConfigCache(s, 16, time.Minute)
                defer cache.Close()

                r1, f1, e1 := cache.Resolve("svc")
                if e1 != nil || !f1 {
                    t.Fatalf("first resolve found=%v err=%v", f1, e1)
                }
                // Inject a key + overwrite an existing one.
                r1.Settings["injected"] = "boom"
                r1.Settings["a"] = "HACKED"

                r2, f2, e2 := cache.Resolve("svc")
                if e2 != nil || !f2 {
                    t.Fatalf("second resolve found=%v err=%v", f2, e2)
                }
                // No store refetch should have happened (served from memory).
                if got := s.count("svc"); got != 1 {
                    t.Fatalf("FETCHCOUNT want 1 got %d (refetched, not a true isolation test)", got)
                }
                if _, ok := r2.Settings["injected"]; ok {
                    t.Fatalf("isolation broken: injected key leaked -> %v", r2.Settings)
                }
                if r2.Settings["a"] != "1" {
                    t.Fatalf("isolation broken: Settings[a] mutated -> %q", r2.Settings["a"])
                }
            }
            """
        )
        res = _run_probe("settings_iso_test.go", body, run="TestSettingsIsolation")
        assert res.returncode == 0, res.stdout + res.stderr
        assert "PASS" in res.stdout, res.stdout + res.stderr

    def test_l2_allow_slice_isolation(self):
        """L2 (CENTRAL): appending to / overwriting elements of a returned
        config's Allow slice must NOT affect the slice a later caller receives
        for the same cached namespace."""
        body = PROBE_HEADER + textwrap.dedent(
            """
            func TestAllowIsolation(t *testing.T) {
                s := newCountingStore()
                s.put(&configcache.Config{
                    Namespace: "svc",
                    Settings:  map[string]string{"k": "v"},
                    Allow:     []string{"alice", "bob"},
                })
                cache := configcache.NewConfigCache(s, 16, time.Minute)
                defer cache.Close()

                r1, f1, e1 := cache.Resolve("svc")
                if e1 != nil || !f1 {
                    t.Fatalf("first resolve found=%v err=%v", f1, e1)
                }
                if len(r1.Allow) != 2 {
                    t.Fatalf("want 2 allow entries got %d", len(r1.Allow))
                }
                // Mutate in place AND append (append may share the backing array
                // if the cache returned the same slice header).
                r1.Allow[0] = "HACKED"
                r1.Allow = append(r1.Allow, "intruder")

                r2, f2, e2 := cache.Resolve("svc")
                if e2 != nil || !f2 {
                    t.Fatalf("second resolve found=%v err=%v", f2, e2)
                }
                if got := s.count("svc"); got != 1 {
                    t.Fatalf("FETCHCOUNT want 1 got %d (not a true isolation test)", got)
                }
                if len(r2.Allow) != 2 {
                    t.Fatalf("isolation broken: want 2 allow got %d (%v)", len(r2.Allow), r2.Allow)
                }
                if r2.Allow[0] != "alice" || r2.Allow[1] != "bob" {
                    t.Fatalf("isolation broken: Allow mutated -> %v", r2.Allow)
                }
            }
            """
        )
        res = _run_probe("allow_iso_test.go", body, run="TestAllowIsolation")
        assert res.returncode == 0, res.stdout + res.stderr
        assert "PASS" in res.stdout, res.stdout + res.stderr

    def test_l2_distinct_returned_pointers_and_containers(self):
        """L2: two Resolve results for the same namespace must NOT be the same
        *Config pointer and must NOT share the same underlying Settings map
        header or Allow backing array (independently-mutable views)."""
        body = PROBE_HEADER + textwrap.dedent(
            """
            func TestDistinctViews(t *testing.T) {
                s := newCountingStore()
                s.put(&configcache.Config{
                    Namespace: "svc",
                    Settings:  map[string]string{"a": "1", "b": "2"},
                    Allow:     []string{"p", "q"},
                })
                cache := configcache.NewConfigCache(s, 16, time.Minute)
                defer cache.Close()

                r1, f1, _ := cache.Resolve("svc")
                r2, f2, _ := cache.Resolve("svc")
                if !f1 || !f2 || r1 == nil || r2 == nil {
                    t.Fatalf("resolves failed f1=%v f2=%v", f1, f2)
                }
                if r1 == r2 {
                    t.Fatalf("same *Config pointer returned to two callers (no isolation)")
                }
                // Mutate r1's containers; r2 (resolved independently) must be untouched.
                if len(r1.Allow) > 0 {
                    r1.Allow[0] = "ZZZ"
                }
                r1.Settings["a"] = "ZZZ"
                r1.Settings["new"] = "ZZZ"

                if r2.Settings["a"] != "1" {
                    t.Fatalf("shared Settings map: r2[a]=%q", r2.Settings["a"])
                }
                if _, ok := r2.Settings["new"]; ok {
                    t.Fatalf("shared Settings map: r2 saw injected 'new' key")
                }
                if len(r2.Allow) < 1 || r2.Allow[0] != "p" {
                    t.Fatalf("shared Allow backing array: r2.Allow=%v", r2.Allow)
                }
                if got := s.count("svc"); got != 1 {
                    t.Fatalf("FETCHCOUNT want 1 got %d", got)
                }
            }
            """
        )
        res = _run_probe("views_test.go", body, run="TestDistinctViews")
        assert res.returncode == 0, res.stdout + res.stderr
        assert "PASS" in res.stdout, res.stdout + res.stderr

    def test_l2_store_object_not_corrupted(self):
        """L2: mutating a returned config must not corrupt the object the store
        originally supplied (a later fresh resolve, after the entry is evicted,
        still sees pristine data)."""
        body = PROBE_HEADER + textwrap.dedent(
            """
            func TestStoreNotCorrupted(t *testing.T) {
                const cap = 2
                s := newCountingStore()
                s.put(&configcache.Config{
                    Namespace: "svc",
                    Settings:  map[string]string{"a": "1"},
                    Allow:     []string{"p"},
                })
                cache := configcache.NewConfigCache(s, cap, time.Minute)
                defer cache.Close()

                r1, f1, _ := cache.Resolve("svc")
                if !f1 {
                    t.Fatalf("first resolve not found")
                }
                r1.Settings["a"] = "HACKED"
                r1.Settings["x"] = "boom"
                if len(r1.Allow) > 0 {
                    r1.Allow[0] = "HACKED"
                }

                // Evict "svc" by resolving more distinct namespaces than capacity.
                for i := 0; i < 10; i++ {
                    id := "n" + strconv.Itoa(i)
                    s.put(&configcache.Config{Namespace: id, Settings: map[string]string{}, Allow: nil})
                    cache.Resolve(id)
                }
                // Fresh resolve must re-consult the store and see pristine data.
                rf, ff, _ := cache.Resolve("svc")
                if !ff {
                    t.Fatalf("fresh resolve of svc not found")
                }
                if rf.Settings["a"] != "1" {
                    t.Fatalf("store corrupted: Settings[a]=%q", rf.Settings["a"])
                }
                if _, ok := rf.Settings["x"]; ok {
                    t.Fatalf("store corrupted: injected key 'x' present")
                }
                if len(rf.Allow) < 1 || rf.Allow[0] != "p" {
                    t.Fatalf("store corrupted: Allow=%v", rf.Allow)
                }
            }
            """
        )
        res = _run_probe("store_iso_test.go", body, run="TestStoreNotCorrupted")
        assert res.returncode == 0, res.stdout + res.stderr
        assert "PASS" in res.stdout, res.stdout + res.stderr

    def test_l2_concurrent_dedup_with_isolation(self):
        """L2: a burst of 50+ concurrent resolves of one uncached namespace
        collapses into a SINGLE store.Get, and each goroutine, after
        independently mutating its returned config, does not affect the others'
        or a final fresh resolve's contents."""
        body = PROBE_HEADER + textwrap.dedent(
            """
            func TestConcurrentDedup(t *testing.T) {
                s := newCountingStore()
                s.put(&configcache.Config{
                    Namespace: "svc",
                    Settings:  map[string]string{"a": "1"},
                    Allow:     []string{"p", "q"},
                })
                s.blockCh = make(chan struct{}) // hold the single Get until all enter
                cache := configcache.NewConfigCache(s, 64, time.Minute)
                defer cache.Close()

                const N = 64
                var wg sync.WaitGroup
                var bad int32
                ready := make(chan struct{}, N)
                wg.Add(N)
                for i := 0; i < N; i++ {
                    go func(idx int) {
                        defer wg.Done()
                        ready <- struct{}{}
                        r, f, e := cache.Resolve("svc")
                        if e != nil || !f || r == nil {
                            atomic.AddInt32(&bad, 1)
                            return
                        }
                        // Each goroutine independently mutates its own view.
                        r.Settings["g"] = strconv.Itoa(idx)
                        r.Settings["a"] = "mut"
                        if len(r.Allow) > 0 {
                            r.Allow[0] = "mut"
                        }
                        r.Allow = append(r.Allow, "extra")
                        // Verify our own pristine values before mutation already
                        // matched expectation (sanity).
                        if r.Namespace != "svc" {
                            atomic.AddInt32(&bad, 1)
                        }
                    }(i)
                }
                for i := 0; i < N; i++ {
                    <-ready
                }
                time.Sleep(50 * time.Millisecond)
                close(s.blockCh)
                wg.Wait()

                if b := atomic.LoadInt32(&bad); b != 0 {
                    t.Fatalf("%d goroutines got wrong/err result", b)
                }
                if got := s.count("svc"); got != 1 {
                    t.Fatalf("FETCHCOUNT want 1 got %d (no singleflight dedup)", got)
                }
                // Final fresh resolve (still cached) must be pristine despite all
                // the concurrent per-goroutine mutations.
                rf, ff, _ := cache.Resolve("svc")
                if !ff {
                    t.Fatalf("final resolve not found")
                }
                if rf.Settings["a"] != "1" {
                    t.Fatalf("isolation broken under concurrency: Settings[a]=%q", rf.Settings["a"])
                }
                if _, ok := rf.Settings["g"]; ok {
                    t.Fatalf("isolation broken: a goroutine's injected key leaked")
                }
                if len(rf.Allow) != 2 || rf.Allow[0] != "p" || rf.Allow[1] != "q" {
                    t.Fatalf("isolation broken under concurrency: Allow=%v", rf.Allow)
                }
            }
            """
        )
        res = _run_probe(
            "dedup_test.go", body, run="TestConcurrentDedup", timeout=300
        )
        assert res.returncode == 0, res.stdout + res.stderr
        assert "PASS" in res.stdout, res.stdout + res.stderr

    def test_l2_distinct_namespaces_no_mixup(self):
        """L2: distinct namespaces return their own configs (no key mixups), and
        each distinct existing namespace is fetched exactly once."""
        body = PROBE_HEADER + textwrap.dedent(
            """
            func TestDistinctNamespaces(t *testing.T) {
                s := newCountingStore()
                s.put(&configcache.Config{Namespace: "P", Settings: map[string]string{"who": "pam"}, Allow: []string{"p"}})
                s.put(&configcache.Config{Namespace: "Q", Settings: map[string]string{"who": "quinn"}, Allow: []string{"q"}})
                cache := configcache.NewConfigCache(s, 16, time.Minute)
                defer cache.Close()

                for round := 0; round < 3; round++ {
                    rp, fp, ep := cache.Resolve("P")
                    rq, fq, eq := cache.Resolve("Q")
                    if ep != nil || eq != nil || !fp || !fq {
                        t.Fatalf("round %d P(found=%v err=%v) Q(found=%v err=%v)", round, fp, ep, fq, eq)
                    }
                    if rp.Settings["who"] != "pam" || rq.Settings["who"] != "quinn" {
                        t.Fatalf("round %d key mixup P=%q Q=%q", round, rp.Settings["who"], rq.Settings["who"])
                    }
                }
                if cp, cq := s.count("P"), s.count("Q"); cp != 1 || cq != 1 {
                    t.Fatalf("FETCHCOUNT want P=1 Q=1 got P=%d Q=%d", cp, cq)
                }
            }
            """
        )
        res = _run_probe("distinct_ns_test.go", body, run="TestDistinctNamespaces")
        assert res.returncode == 0, res.stdout + res.stderr
        assert "PASS" in res.stdout, res.stdout + res.stderr

    def test_l2_no_goroutine_leak_after_close(self):
        """L2: after Close(), goleak reports no leaked goroutines — the cache
        must release any background machinery it started (e.g. a TTL janitor)."""
        body = textwrap.dedent(
            """
            package configcacheprobe

            import (
                "testing"
                "time"

                configcache "github.com/samber/hot/pkg/configcache"
                "go.uber.org/goleak"
            )

            type leakStore struct{}

            func (leakStore) Get(namespace string) (*configcache.Config, bool, error) {
                if namespace == "L" {
                    return &configcache.Config{
                        Namespace: "L",
                        Settings:  map[string]string{"k": "v"},
                        Allow:     []string{"x"},
                    }, true, nil
                }
                return nil, false, nil
            }

            func TestNoLeakAfterClose(t *testing.T) {
                func() {
                    cache := configcache.NewConfigCache(leakStore{}, 16, 20*time.Millisecond)
                    for i := 0; i < 5; i++ {
                        cache.Resolve("L")
                    }
                    cache.Close()
                }()
                time.Sleep(100 * time.Millisecond)
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
