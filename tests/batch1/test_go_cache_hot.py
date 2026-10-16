"""Tests for the `go-cache-hot` skill task.

Skill: go-cache-hot — Build a Read-Through Contact Directory Service inside the
`github.com/samber/hot` repository.

The task asks the agent to create `pkg/directory/directory.go` (and a
`directory_test.go`) implementing a `DirectoryService` that wraps the `hot`
cache to serve contact records from a slow `Backend` while:
  - caching hits AND confirmed misses (negative caching),
  - never caching backend errors,
  - collapsing concurrent demand for the same uncached id into one fetch,
  - honoring a TTL,
  - returning records insulated from caller mutation,
  - keeping memory bounded to ~capacity,
  - leaking no goroutines after Close().

What this file verifies:
  L1 — the deliverable files exist, the package builds, the required exported
       API surface (Contact, Backend, NewDirectoryService, Lookup, Close)
       compiles against, and the agent's own test runs.
  L2 — we DO NOT trust the agent's own test file. Instead we synthesize an
       independent probe package under REPO_DIR that imports the agent's
       `pkg/directory` package, drives it with our own counting/blocking
       backends, and asserts the concrete behaviors. Each probe is run via the
       native `go test` toolchain and its results parsed from stdout, so a
       naive implementation (fetch-every-time, no negative cache, shared
       mutable slices, no dedup, no TTL, unbounded growth) fails.
"""

import os
import shutil
import subprocess
import textwrap

import pytest

REPO_DIR = "/workspace/hot"
DIR_PKG = os.path.join(REPO_DIR, "pkg", "directory")
PROBE_PKG = os.path.join(REPO_DIR, "pkg", "directoryprobe")


def _run_go(args, timeout=300):
    """Run a go command from REPO_DIR with module-mode env sane defaults."""
    env = dict(os.environ)
    env.setdefault("GOFLAGS", "")
    env["GO111MODULE"] = "on"
    # Keep the default module cache; do not clear PYTHONPATH-style envs go needs.
    return subprocess.run(
        ["go"] + args,
        cwd=REPO_DIR,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )


def _write_probe(name, body):
    """Write a single-file probe test into pkg/directoryprobe and return path.

    The probe imports the agent's directory package via the module path so it
    compiles only against the real public API.
    """
    os.makedirs(PROBE_PKG, exist_ok=True)
    # A minimal go file declaring the package so `go test` recognizes it even
    # if the agent's package import fails to resolve names (compile error then
    # surfaces clearly).
    path = os.path.join(PROBE_PKG, name)
    with open(path, "w") as fh:
        fh.write(body)
    return path


def _run_probe(name, body, run="", timeout=300):
    """Write a probe test file, run it, clean it up, return CompletedProcess."""
    path = _write_probe(name, body)
    try:
        args = ["test", "./pkg/directoryprobe/", "-count=1", "-v"]
        if run:
            args += ["-run", run]
        return _run_go(args, timeout=timeout)
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


# Common header reused by probe files. Imports the agent package.
PROBE_HEADER = textwrap.dedent(
    """
    package directoryprobe

    import (
        "errors"
        "strconv"
        "sync"
        "sync/atomic"
        "testing"
        "time"

        directory "github.com/samber/hot/pkg/directory"
    )

    var _ = strconv.Itoa
    var _ = errors.New
    var _ = time.Now
    var _ = atomic.AddInt32

    // countingBackend records per-id fetch counts and is concurrency safe.
    type countingBackend struct {
        mu       sync.Mutex
        counts   map[string]int
        data     map[string]*directory.Contact
        failIDs  map[string]int // remaining failures per id
        blockCh  chan struct{}  // if non-nil, Fetch waits on it once entered
        entered  int32
    }

    func newCountingBackend() *countingBackend {
        return &countingBackend{
            counts:  map[string]int{},
            data:    map[string]*directory.Contact{},
            failIDs: map[string]int{},
        }
    }

    func (b *countingBackend) put(c *directory.Contact) {
        b.mu.Lock()
        b.data[c.ID] = c
        b.mu.Unlock()
    }

    func (b *countingBackend) failNext(id string, n int) {
        b.mu.Lock()
        b.failIDs[id] = n
        b.mu.Unlock()
    }

    func (b *countingBackend) count(id string) int {
        b.mu.Lock()
        defer b.mu.Unlock()
        return b.counts[id]
    }

    func (b *countingBackend) Fetch(ids []string) (map[string]*directory.Contact, error) {
        atomic.AddInt32(&b.entered, 1)
        if b.blockCh != nil {
            <-b.blockCh
        }
        b.mu.Lock()
        defer b.mu.Unlock()
        out := map[string]*directory.Contact{}
        for _, id := range ids {
            b.counts[id]++
            if rem, ok := b.failIDs[id]; ok && rem > 0 {
                b.failIDs[id] = rem - 1
                return nil, errors.New("infra failure for " + id)
            }
            if c, ok := b.data[id]; ok {
                // hand back a copy so the service's own isolation is what we test
                cp := *c
                cp.Tags = append([]string(nil), c.Tags...)
                out[id] = &cp
            }
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
    # Pre-download module dependencies so per-test timeouts are about behavior.
    res = _run_go(["mod", "download"], timeout=400)
    # Not fatal if this fails (offline cache may already exist); build steps
    # below will surface real problems.
    yield res


# ---------------------------------------------------------------------------
# L1 — deliverable existence / well-formedness / compilation
# ---------------------------------------------------------------------------

class TestGoCacheHot:
    REPO_DIR = "/workspace/hot"

    def test_l1_directory_source_exists(self):
        """L1: pkg/directory/directory.go exists and is non-empty."""
        p = os.path.join(DIR_PKG, "directory.go")
        assert os.path.isfile(p), f"missing {p}"
        assert os.path.getsize(p) > 0, "directory.go is empty"

    def test_l1_directory_test_exists(self):
        """L1: pkg/directory/directory_test.go exists (agent's own tests)."""
        p = os.path.join(DIR_PKG, "directory_test.go")
        assert os.path.isfile(p), f"missing {p}"
        assert os.path.getsize(p) > 0, "directory_test.go is empty"

    def test_l1_go_mod_unmodified_module_path(self):
        """L1: still the samber/hot module and Go 1.22+ (no new third-party deps)."""
        gomod = os.path.join(REPO_DIR, "go.mod")
        with open(gomod) as fh:
            text = fh.read()
        assert "module github.com/samber/hot" in text
        # go directive present and >= 1.22
        import re
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

    def test_l1_vet_directory_package(self):
        """L1: `go vet` of the directory package is clean (well-formed Go)."""
        res = _run_go(["vet", "./pkg/directory/"], timeout=300)
        assert res.returncode == 0, (
            "go vet ./pkg/directory/ failed:\n" + res.stdout + res.stderr
        )

    def test_l1_public_api_surface_compiles(self):
        """L1: the exact required public API (Contact fields, Backend, ctor,
        Lookup, Close) compiles when referenced from an independent package."""
        body = PROBE_HEADER + textwrap.dedent(
            """
            func TestAPISurface(t *testing.T) {
                var _ directory.Backend = newCountingBackend()
                c := directory.Contact{ID: "x", Name: "n", Email: "e", Tags: []string{"t"}}
                _ = c.ID
                _ = c.Name
                _ = c.Email
                _ = c.Tags
                b := newCountingBackend()
                svc := directory.NewDirectoryService(b, 8, time.Second)
                var rec *directory.Contact
                var found bool
                var err error
                rec, found, err = svc.Lookup("x")
                _ = rec
                _ = found
                _ = err
                svc.Close()
            }
            """
        )
        res = _run_probe("api_surface_test.go", body, run="TestAPISurface")
        assert res.returncode == 0, (
            "API surface probe failed to compile/run:\n" + res.stdout + res.stderr
        )
        assert "PASS" in res.stdout, res.stdout + res.stderr

    def test_l1_agent_tests_run(self):
        """L1: the agent's own TestDirectory* tests pass (acceptance command)."""
        res = _run_go(
            ["test", "./pkg/directory/", "-run", "TestDirectory", "-count=1"],
            timeout=400,
        )
        assert res.returncode == 0, (
            "agent's own go test ./pkg/directory -run TestDirectory failed:\n"
            + res.stdout + res.stderr
        )


# ---------------------------------------------------------------------------
# L2 — independent behavioral probes via native `go test`
# ---------------------------------------------------------------------------

    def test_l2_hit_cached_after_first(self):
        """L2: existing id looked up twice triggers exactly ONE backend fetch
        and returns identical data both times."""
        body = PROBE_HEADER + textwrap.dedent(
            """
            func TestHitCached(t *testing.T) {
                b := newCountingBackend()
                b.put(&directory.Contact{ID: "A", Name: "Alice", Email: "a@x", Tags: []string{"vip"}})
                svc := directory.NewDirectoryService(b, 16, time.Minute)
                defer svc.Close()

                r1, f1, e1 := svc.Lookup("A")
                if e1 != nil || !f1 || r1 == nil {
                    t.Fatalf("first lookup: found=%v err=%v rec=%v", f1, e1, r1)
                }
                r2, f2, e2 := svc.Lookup("A")
                if e2 != nil || !f2 || r2 == nil {
                    t.Fatalf("second lookup: found=%v err=%v", f2, e2)
                }
                if r1.Name != "Alice" || r2.Name != "Alice" || r1.Email != "a@x" {
                    t.Fatalf("data mismatch r1=%+v r2=%+v", r1, r2)
                }
                if got := b.count("A"); got != 1 {
                    t.Fatalf("FETCHCOUNT want 1 got %d", got)
                }
            }
            """
        )
        res = _run_probe("hit_test.go", body, run="TestHitCached")
        assert res.returncode == 0, res.stdout + res.stderr
        assert "PASS" in res.stdout, res.stdout + res.stderr

    def test_l2_negative_cache_for_missing_id(self):
        """L2: a non-existent id looked up twice returns found=false both times
        and triggers exactly ONE backend fetch (negative caching)."""
        body = PROBE_HEADER + textwrap.dedent(
            """
            func TestNegativeCache(t *testing.T) {
                b := newCountingBackend() // no data => everything missing
                svc := directory.NewDirectoryService(b, 16, time.Minute)
                defer svc.Close()

                r1, f1, e1 := svc.Lookup("Z")
                if e1 != nil || f1 || r1 != nil {
                    t.Fatalf("first miss: found=%v err=%v rec=%v", f1, e1, r1)
                }
                r2, f2, e2 := svc.Lookup("Z")
                if e2 != nil || f2 || r2 != nil {
                    t.Fatalf("second miss: found=%v err=%v", f2, e2)
                }
                if got := b.count("Z"); got != 1 {
                    t.Fatalf("FETCHCOUNT want 1 got %d (missing id not cached)", got)
                }
            }
            """
        )
        res = _run_probe("neg_test.go", body, run="TestNegativeCache")
        assert res.returncode == 0, res.stdout + res.stderr
        assert "PASS" in res.stdout, res.stdout + res.stderr

    def test_l2_error_not_cached(self):
        """L2: a backend error is returned to the caller and NOT cached; a later
        healthy lookup for the same id succeeds."""
        body = PROBE_HEADER + textwrap.dedent(
            """
            func TestErrorNotCached(t *testing.T) {
                b := newCountingBackend()
                b.put(&directory.Contact{ID: "B", Name: "Bob", Email: "b@x"})
                b.failNext("B", 1) // first fetch for B fails
                svc := directory.NewDirectoryService(b, 16, time.Minute)
                defer svc.Close()

                _, _, e1 := svc.Lookup("B")
                if e1 == nil {
                    t.Fatalf("expected error on first lookup of B, got nil")
                }
                r2, f2, e2 := svc.Lookup("B")
                if e2 != nil {
                    t.Fatalf("second lookup unexpectedly errored: %v (failure was cached)", e2)
                }
                if !f2 || r2 == nil || r2.Name != "Bob" {
                    t.Fatalf("second lookup: found=%v rec=%+v", f2, r2)
                }
                if got := b.count("B"); got < 2 {
                    t.Fatalf("FETCHCOUNT want >=2 got %d (failure must trigger a refetch)", got)
                }
            }
            """
        )
        res = _run_probe("err_test.go", body, run="TestErrorNotCached")
        assert res.returncode == 0, res.stdout + res.stderr
        assert "PASS" in res.stdout, res.stdout + res.stderr

    def test_l2_concurrent_dedup_single_fetch(self):
        """L2: 100 concurrent lookups of the same uncached id collapse into a
        single backend fetch; every goroutine sees found=true with correct data."""
        body = PROBE_HEADER + textwrap.dedent(
            """
            func TestConcurrentDedup(t *testing.T) {
                b := newCountingBackend()
                b.put(&directory.Contact{ID: "C", Name: "Carol", Email: "c@x", Tags: []string{"q"}})
                b.blockCh = make(chan struct{})
                svc := directory.NewDirectoryService(b, 64, time.Minute)
                defer svc.Close()

                const N = 100
                var wg sync.WaitGroup
                var okCount int32
                var badCount int32
                ready := make(chan struct{}, N)
                wg.Add(N)
                for i := 0; i < N; i++ {
                    go func() {
                        defer wg.Done()
                        ready <- struct{}{}
                        r, f, e := svc.Lookup("C")
                        if e == nil && f && r != nil && r.Name == "Carol" {
                            atomic.AddInt32(&okCount, 1)
                        } else {
                            atomic.AddInt32(&badCount, 1)
                        }
                    }()
                }
                // wait until all goroutines have entered before releasing the backend
                for i := 0; i < N; i++ {
                    <-ready
                }
                time.Sleep(50 * time.Millisecond)
                close(b.blockCh)
                wg.Wait()

                if bad := atomic.LoadInt32(&badCount); bad != 0 {
                    t.Fatalf("%d goroutines got wrong/err result", bad)
                }
                if ok := atomic.LoadInt32(&okCount); ok != N {
                    t.Fatalf("want %d ok results got %d", N, ok)
                }
                if got := b.count("C"); got != 1 {
                    t.Fatalf("FETCHCOUNT want 1 got %d (no singleflight dedup)", got)
                }
            }
            """
        )
        res = _run_probe("dedup_test.go", body, run="TestConcurrentDedup", timeout=300)
        assert res.returncode == 0, res.stdout + res.stderr
        assert "PASS" in res.stdout, res.stdout + res.stderr

    def test_l2_ttl_expiry_triggers_refetch(self):
        """L2: after TTL elapses, the next lookup consults the backend again."""
        body = PROBE_HEADER + textwrap.dedent(
            """
            func TestTTLExpiry(t *testing.T) {
                b := newCountingBackend()
                b.put(&directory.Contact{ID: "D", Name: "Dave", Email: "d@x"})
                svc := directory.NewDirectoryService(b, 16, 80*time.Millisecond)
                defer svc.Close()

                if _, f, e := svc.Lookup("D"); e != nil || !f {
                    t.Fatalf("first lookup found=%v err=%v", f, e)
                }
                if _, f, e := svc.Lookup("D"); e != nil || !f { // still within ttl -> cached
                    t.Fatalf("cached lookup found=%v err=%v", f, e)
                }
                if got := b.count("D"); got != 1 {
                    t.Fatalf("FETCHCOUNT before expiry want 1 got %d", got)
                }
                time.Sleep(200 * time.Millisecond) // exceed ttl
                if _, f, e := svc.Lookup("D"); e != nil || !f {
                    t.Fatalf("post-ttl lookup found=%v err=%v", f, e)
                }
                if got := b.count("D"); got < 2 {
                    t.Fatalf("FETCHCOUNT after expiry want >=2 got %d (ttl not honored)", got)
                }
            }
            """
        )
        res = _run_probe("ttl_test.go", body, run="TestTTLExpiry")
        assert res.returncode == 0, res.stdout + res.stderr
        assert "PASS" in res.stdout, res.stdout + res.stderr

    def test_l2_mutation_isolation_tags(self):
        """L2: mutating the returned Tags slice must not corrupt the record a
        later caller receives for the same id."""
        body = PROBE_HEADER + textwrap.dedent(
            """
            func TestMutationIsolation(t *testing.T) {
                b := newCountingBackend()
                b.put(&directory.Contact{ID: "E", Name: "Eve", Email: "e@x", Tags: []string{"a", "b"}})
                svc := directory.NewDirectoryService(b, 16, time.Minute)
                defer svc.Close()

                r1, f1, e1 := svc.Lookup("E")
                if e1 != nil || !f1 {
                    t.Fatalf("first lookup found=%v err=%v", f1, e1)
                }
                if len(r1.Tags) != 2 {
                    t.Fatalf("want 2 tags got %d", len(r1.Tags))
                }
                // mutate in place AND append
                r1.Tags[0] = "HACKED"
                r1.Tags = append(r1.Tags, "EXTRA")
                r1.Name = "Mallory"

                r2, f2, e2 := svc.Lookup("E")
                if e2 != nil || !f2 {
                    t.Fatalf("second lookup found=%v err=%v", f2, e2)
                }
                if len(r2.Tags) != 2 {
                    t.Fatalf("isolation broken: want 2 tags got %d (%v)", len(r2.Tags), r2.Tags)
                }
                if r2.Tags[0] != "a" || r2.Tags[1] != "b" {
                    t.Fatalf("isolation broken: tags mutated -> %v", r2.Tags)
                }
                if r2.Name != "Eve" {
                    t.Fatalf("isolation broken: name mutated -> %q", r2.Name)
                }
            }
            """
        )
        res = _run_probe("mut_test.go", body, run="TestMutationIsolation")
        assert res.returncode == 0, res.stdout + res.stderr
        assert "PASS" in res.stdout, res.stdout + res.stderr

    def test_l2_capacity_bounded_eviction(self):
        """L2: resolving far more distinct ids than capacity keeps memory bounded
        to ~capacity — observed via an evicted id forcing a fresh backend fetch."""
        body = PROBE_HEADER + textwrap.dedent(
            """
            func TestCapacityBounded(t *testing.T) {
                const cap = 8
                b := newCountingBackend()
                for i := 0; i < 1000; i++ {
                    id := "k" + strconv.Itoa(i)
                    b.put(&directory.Contact{ID: id, Name: id, Email: id + "@x"})
                }
                svc := directory.NewDirectoryService(b, cap, time.Minute)
                defer svc.Close()

                // Resolve far more than capacity distinct ids.
                for i := 0; i < 1000; i++ {
                    id := "k" + strconv.Itoa(i)
                    if _, f, e := svc.Lookup(id); e != nil || !f {
                        t.Fatalf("lookup %s found=%v err=%v", id, f, e)
                    }
                }
                // k0 was resolved at the very start; with cap=8 it must have been
                // evicted long ago. Re-looking it up must hit the backend AGAIN.
                before := b.count("k0")
                if _, f, e := svc.Lookup("k0"); e != nil || !f {
                    t.Fatalf("re-lookup k0 found=%v err=%v", f, e)
                }
                after := b.count("k0")
                if after <= before {
                    t.Fatalf("k0 was not evicted: fetch count stayed %d (unbounded growth)", after)
                }
            }
            """
        )
        res = _run_probe("cap_test.go", body, run="TestCapacityBounded")
        assert res.returncode == 0, res.stdout + res.stderr
        assert "PASS" in res.stdout, res.stdout + res.stderr

    def test_l2_distinct_ids_isolated(self):
        """L2: distinct ids return their own records (no key mixups), and each
        distinct existing id is fetched exactly once."""
        body = PROBE_HEADER + textwrap.dedent(
            """
            func TestDistinctIDs(t *testing.T) {
                b := newCountingBackend()
                b.put(&directory.Contact{ID: "P", Name: "Pam", Email: "p@x"})
                b.put(&directory.Contact{ID: "Q", Name: "Quinn", Email: "q@x"})
                svc := directory.NewDirectoryService(b, 16, time.Minute)
                defer svc.Close()

                for round := 0; round < 3; round++ {
                    rp, fp, ep := svc.Lookup("P")
                    rq, fq, eq := svc.Lookup("Q")
                    if ep != nil || eq != nil || !fp || !fq {
                        t.Fatalf("round %d: P(found=%v err=%v) Q(found=%v err=%v)", round, fp, ep, fq, eq)
                    }
                    if rp.Name != "Pam" || rq.Name != "Quinn" {
                        t.Fatalf("round %d: key mixup P=%q Q=%q", round, rp.Name, rq.Name)
                    }
                }
                if cp, cq := b.count("P"), b.count("Q"); cp != 1 || cq != 1 {
                    t.Fatalf("FETCHCOUNT want P=1 Q=1 got P=%d Q=%d", cp, cq)
                }
            }
            """
        )
        res = _run_probe("distinct_test.go", body, run="TestDistinctIDs")
        assert res.returncode == 0, res.stdout + res.stderr
        assert "PASS" in res.stdout, res.stdout + res.stderr

    def test_l2_no_goroutine_leak_after_close(self):
        """L2: after Close(), goleak reports no leaked goroutines (the service
        must release any background machinery it started)."""
        body = textwrap.dedent(
            """
            package directoryprobe

            import (
                "testing"
                "time"

                directory "github.com/samber/hot/pkg/directory"
                "go.uber.org/goleak"
            )

            type leakBackend struct{}

            func (leakBackend) Fetch(ids []string) (map[string]*directory.Contact, error) {
                out := map[string]*directory.Contact{}
                for _, id := range ids {
                    if id == "L" {
                        out[id] = &directory.Contact{ID: "L", Name: "Leo", Email: "l@x"}
                    }
                }
                return out, nil
            }

            func TestNoLeakAfterClose(t *testing.T) {
                func() {
                    svc := directory.NewDirectoryService(leakBackend{}, 16, 20*time.Millisecond)
                    for i := 0; i < 5; i++ {
                        svc.Lookup("L")
                    }
                    svc.Close()
                }()
                // give any janitor a moment to stop
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
