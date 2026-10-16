"""Tests for the `go-cache-hot` skill task (variant ext9).

Skill: go-cache-hot — Build a Negative-Caching Name Resolver inside the
`github.com/samber/hot` repository.

The ext9 task asks the agent to create a NEW package `pkg/resolver`:
  - `pkg/resolver/resolver.go`      — the `Resolver` implementation
  - `pkg/resolver/resolver_test.go` — the agent's own deterministic tests

The `Resolver` wraps the `hot` cache to resolve hostnames -> addresses through
a slow `Service` backend, with the defining twist of this variant:
  - DISTINCT TTLs for hits vs misses: positive answers live for `positiveTTL`,
    confirmed "no such host" negative answers live only for `negativeTTL`
    (expected shorter). After `negativeTTL` elapses a missing host may be
    re-consulted even while the longer `positiveTTL` has not elapsed.
  - confirmed negatives ARE remembered (negative caching), so a repeat miss
    inside the negative window does NOT consult the backend.
  - infrastructure errors are NEVER cached (neither positive nor negative).
  - concurrent demand for the SAME uncached host collapses to one backend call
    (singleflight dedup), whether that host exists or not.
  - `Close()` releases any background machinery; no goroutine leaks.

Required API (from the requirement doc):
    type Record struct { Host string; Addr string }
    type Service interface { Lookup(host string) (*Record, bool, error) }
    func NewResolver(svc Service, capacity int, positiveTTL, negativeTTL time.Duration) *Resolver
    func (r *Resolver) Resolve(host string) (*Record, bool, error)
    func (r *Resolver) Close()

Verification strategy:
  L1 — deliverables exist, go.mod unmodified, `go build ./...` and `go vet`
       succeed, the exact public API surface compiles from an independent
       package, and the agent's own `go test ./pkg/resolver/ -run TestResolver`
       acceptance command passes.
  L2 — we DO NOT trust the agent's own test file. We synthesize an independent
       probe package `pkg/resolverprobe` under REPO_DIR that imports the
       agent's `pkg/resolver` and drives it with our own counting / blocking /
       flippable / failing Service backends, then asserts concrete fetch counts
       and found/err values via the native `go test` toolchain. A naive
       implementation (no negative cache, one shared TTL for hits and misses,
       caching infra errors, re-querying on every miss, or no dedup) fails at
       least one probe.
"""

import os
import re
import shutil
import subprocess
import textwrap

import pytest

REPO_DIR = "/workspace/hot"
RES_PKG = os.path.join(REPO_DIR, "pkg", "resolver")
PROBE_PKG = os.path.join(REPO_DIR, "pkg", "resolverprobe")


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
    """Write a single-file probe test into pkg/resolverprobe and return path."""
    os.makedirs(PROBE_PKG, exist_ok=True)
    path = os.path.join(PROBE_PKG, name)
    with open(path, "w") as fh:
        fh.write(body)
    return path


def _run_probe(name, body, run="", timeout=300):
    """Write a probe test file, run it, clean it up, return CompletedProcess."""
    path = _write_probe(name, body)
    try:
        args = ["test", "./pkg/resolverprobe/", "-count=1", "-v"]
        if run:
            args += ["-run", run]
        return _run_go(args, timeout=timeout)
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


# Common header reused by probe files. Imports the agent's resolver package and
# provides a concurrency-safe, per-host-counting Service backend that can:
#   - flip a host from "not found" to "found" (flip),
#   - fail a fixed number of times for a host (failNext),
#   - block inside Lookup once entered (blockCh) to test singleflight dedup.
PROBE_HEADER = textwrap.dedent(
    """
    package resolverprobe

    import (
        "errors"
        "strconv"
        "sync"
        "sync/atomic"
        "testing"
        "time"

        resolver "github.com/samber/hot/pkg/resolver"
    )

    var _ = strconv.Itoa
    var _ = errors.New
    var _ = time.Now
    var _ = atomic.AddInt32

    type countingService struct {
        mu       sync.Mutex
        counts   map[string]int
        addrs    map[string]string // host -> addr (present => "found")
        failHost map[string]int    // remaining forced failures per host
        blockCh  chan struct{}     // if non-nil, Lookup waits on it once entered
        entered  int32
    }

    func newCountingService() *countingService {
        return &countingService{
            counts:   map[string]int{},
            addrs:    map[string]string{},
            failHost: map[string]int{},
        }
    }

    func (s *countingService) put(host, addr string) {
        s.mu.Lock()
        s.addrs[host] = addr
        s.mu.Unlock()
    }

    func (s *countingService) remove(host string) {
        s.mu.Lock()
        delete(s.addrs, host)
        s.mu.Unlock()
    }

    func (s *countingService) failNext(host string, n int) {
        s.mu.Lock()
        s.failHost[host] = n
        s.mu.Unlock()
    }

    func (s *countingService) count(host string) int {
        s.mu.Lock()
        defer s.mu.Unlock()
        return s.counts[host]
    }

    func (s *countingService) Lookup(host string) (*resolver.Record, bool, error) {
        atomic.AddInt32(&s.entered, 1)
        if s.blockCh != nil {
            <-s.blockCh
        }
        s.mu.Lock()
        defer s.mu.Unlock()
        s.counts[host]++
        if rem, ok := s.failHost[host]; ok && rem > 0 {
            s.failHost[host] = rem - 1
            return nil, false, errors.New("infra failure for " + host)
        }
        if addr, ok := s.addrs[host]; ok {
            return &resolver.Record{Host: host, Addr: addr}, true, nil
        }
        return nil, false, nil
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

    def test_l1_resolver_source_exists(self):
        """L1: pkg/resolver/resolver.go exists and is non-empty."""
        p = os.path.join(RES_PKG, "resolver.go")
        assert os.path.isfile(p), f"missing {p}"
        assert os.path.getsize(p) > 0, "resolver.go is empty"

    def test_l1_resolver_test_exists(self):
        """L1: pkg/resolver/resolver_test.go exists (agent's own tests)."""
        p = os.path.join(RES_PKG, "resolver_test.go")
        assert os.path.isfile(p), f"missing {p}"
        assert os.path.getsize(p) > 0, "resolver_test.go is empty"

    def test_l1_go_mod_unmodified_module_path(self):
        """L1: still the samber/hot module and Go 1.22+ (no new third-party deps)."""
        gomod = os.path.join(REPO_DIR, "go.mod")
        with open(gomod) as fh:
            text = fh.read()
        assert "module github.com/samber/hot" in text
        m = re.search(r"^go\s+(\d+)\.(\d+)", text, re.MULTILINE)
        assert m, "no go directive in go.mod"
        major, minor = int(m.group(1)), int(m.group(2))
        assert (major, minor) >= (1, 22), f"go {major}.{minor} < 1.22"

    def test_l1_build_whole_module(self):
        """L1: `go build ./...` succeeds with the new resolver package present."""
        res = _run_go(["build", "./..."], timeout=400)
        assert res.returncode == 0, (
            "go build ./... failed:\n" + res.stdout + res.stderr
        )

    def test_l1_vet_resolver_package(self):
        """L1: `go vet` of the resolver package is clean (well-formed Go)."""
        res = _run_go(["vet", "./pkg/resolver/"], timeout=300)
        assert res.returncode == 0, (
            "go vet ./pkg/resolver/ failed:\n" + res.stdout + res.stderr
        )

    def test_l1_public_api_surface_compiles(self):
        """L1: the exact required public API (Record fields, Service interface,
        NewResolver signature with two TTLs, Resolve, Close) compiles when
        referenced from an independent package."""
        body = PROBE_HEADER + textwrap.dedent(
            """
            func TestAPISurface(t *testing.T) {
                // Service interface is satisfied by our counting backend.
                var _ resolver.Service = newCountingService()
                // Record has Host and Addr string fields.
                rec := resolver.Record{Host: "h", Addr: "a"}
                _ = rec.Host
                _ = rec.Addr
                // NewResolver takes (Service, int, positiveTTL, negativeTTL).
                svc := newCountingService()
                r := resolver.NewResolver(svc, 8, time.Minute, time.Second)
                var out *resolver.Record
                var found bool
                var err error
                out, found, err = r.Resolve("h")
                _ = out
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
        """L1: the agent's own TestResolver tests pass (native acceptance cmd:
        `go test ./pkg/resolver/ -run TestResolver -count=1`)."""
        res = _run_go(
            ["test", "./pkg/resolver/", "-run", "TestResolver", "-count=1"],
            timeout=400,
        )
        assert res.returncode == 0, (
            "agent's own go test ./pkg/resolver -run TestResolver failed:\n"
            + res.stdout + res.stderr
        )

# ---------------------------------------------------------------------------
# L2 — independent behavioral probes via native `go test`
# ---------------------------------------------------------------------------

    def test_l2_positive_hit_cached_after_first(self):
        """L2: an existing host resolved twice within positiveTTL triggers
        exactly ONE backend Lookup and returns the correct addr both times."""
        body = PROBE_HEADER + textwrap.dedent(
            """
            func TestPositiveHit(t *testing.T) {
                s := newCountingService()
                s.put("a", "1.2.3.4")
                // long positiveTTL, short negativeTTL
                r := resolver.NewResolver(s, 16, time.Minute, 10*time.Millisecond)
                defer r.Close()

                r1, f1, e1 := r.Resolve("a")
                if e1 != nil || !f1 || r1 == nil {
                    t.Fatalf("first resolve: found=%v err=%v rec=%v", f1, e1, r1)
                }
                r2, f2, e2 := r.Resolve("a")
                if e2 != nil || !f2 || r2 == nil {
                    t.Fatalf("second resolve: found=%v err=%v", f2, e2)
                }
                if r1.Addr != "1.2.3.4" || r2.Addr != "1.2.3.4" {
                    t.Fatalf("addr mismatch r1=%+v r2=%+v", r1, r2)
                }
                if r1.Host != "a" || r2.Host != "a" {
                    t.Fatalf("host mismatch r1=%+v r2=%+v", r1, r2)
                }
                if got := s.count("a"); got != 1 {
                    t.Fatalf("LOOKUPCOUNT want 1 got %d (positive not cached)", got)
                }
            }
            """
        )
        res = _run_probe("pos_test.go", body, run="TestPositiveHit")
        assert res.returncode == 0, res.stdout + res.stderr
        assert "PASS" in res.stdout, res.stdout + res.stderr

    def test_l2_negative_answer_remembered(self):
        """L2: a non-existent host resolved twice within negativeTTL returns
        found=false both times and triggers exactly ONE backend Lookup (the
        negative answer is remembered)."""
        body = PROBE_HEADER + textwrap.dedent(
            """
            func TestNegativeRemembered(t *testing.T) {
                s := newCountingService() // host "z" absent => not found
                // negativeTTL long enough that the repeat is inside the window
                r := resolver.NewResolver(s, 16, time.Minute, time.Minute)
                defer r.Close()

                r1, f1, e1 := r.Resolve("z")
                if e1 != nil || f1 || r1 != nil {
                    t.Fatalf("first miss: found=%v err=%v rec=%v", f1, e1, r1)
                }
                r2, f2, e2 := r.Resolve("z")
                if e2 != nil || f2 || r2 != nil {
                    t.Fatalf("second miss: found=%v err=%v rec=%v", f2, e2, r2)
                }
                if got := s.count("z"); got != 1 {
                    t.Fatalf("LOOKUPCOUNT want 1 got %d (negative not remembered)", got)
                }
            }
            """
        )
        res = _run_probe("negrem_test.go", body, run="TestNegativeRemembered")
        assert res.returncode == 0, res.stdout + res.stderr
        assert "PASS" in res.stdout, res.stdout + res.stderr

    def test_l2_distinct_ttls_negative_expires_before_positive(self):
        """L2: THE defining behavior. With short negativeTTL and long
        positiveTTL, a host that is 'not found' first, then flipped to 'found',
        must NOT be re-queried during the negative window but MUST become
        resolvable shortly after negativeTTL — well before positiveTTL would
        have elapsed. A single-shared-TTL impl fails this."""
        body = PROBE_HEADER + textwrap.dedent(
            """
            func TestDistinctTTLs(t *testing.T) {
                s := newCountingService() // "h" absent initially
                negTTL := 120 * time.Millisecond
                posTTL := 30 * time.Second // much longer than the test
                r := resolver.NewResolver(s, 16, posTTL, negTTL)
                defer r.Close()

                // First call: not found, backend consulted once.
                if _, f, e := r.Resolve("h"); e != nil || f {
                    t.Fatalf("first resolve found=%v err=%v (want miss)", f, e)
                }
                if got := s.count("h"); got != 1 {
                    t.Fatalf("after first: LOOKUPCOUNT want 1 got %d", got)
                }

                // Flip the service so "h" now exists.
                s.put("h", "9.9.9.9")

                // Still inside the negative window: must be served from the
                // remembered negative (no backend call), still found=false.
                if _, f, e := r.Resolve("h"); e != nil || f {
                    t.Fatalf("within negTTL found=%v err=%v (want cached miss)", f, e)
                }
                if got := s.count("h"); got != 1 {
                    t.Fatalf("within negTTL: LOOKUPCOUNT want 1 got %d (re-queried during negative window)", got)
                }

                // Wait past negativeTTL but nowhere near positiveTTL.
                time.Sleep(negTTL + 200*time.Millisecond)

                rec, f, e := r.Resolve("h")
                if e != nil {
                    t.Fatalf("post-negTTL resolve errored: %v", e)
                }
                if !f || rec == nil || rec.Addr != "9.9.9.9" {
                    t.Fatalf("post-negTTL resolve found=%v rec=%+v (negative did not expire / single shared TTL)", f, rec)
                }
                if got := s.count("h"); got < 2 {
                    t.Fatalf("post-negTTL: LOOKUPCOUNT want >=2 got %d (backend not re-consulted after negTTL)", got)
                }
            }
            """
        )
        res = _run_probe("distinctttl_test.go", body, run="TestDistinctTTLs")
        assert res.returncode == 0, res.stdout + res.stderr
        assert "PASS" in res.stdout, res.stdout + res.stderr

    def test_l2_positive_outlives_negative_window(self):
        """L2: a positive answer must remain cached past the (short) negativeTTL
        — proving hits use positiveTTL, not negativeTTL. After waiting longer
        than negativeTTL (but well under positiveTTL) a previously-found host is
        still served from memory with no extra backend Lookup."""
        body = PROBE_HEADER + textwrap.dedent(
            """
            func TestPositiveOutlivesNeg(t *testing.T) {
                s := newCountingService()
                s.put("p", "7.7.7.7")
                negTTL := 100 * time.Millisecond
                posTTL := 30 * time.Second
                r := resolver.NewResolver(s, 16, posTTL, negTTL)
                defer r.Close()

                if _, f, e := r.Resolve("p"); e != nil || !f {
                    t.Fatalf("first resolve found=%v err=%v", f, e)
                }
                if got := s.count("p"); got != 1 {
                    t.Fatalf("after first: LOOKUPCOUNT want 1 got %d", got)
                }
                // Sleep past negativeTTL but far under positiveTTL.
                time.Sleep(negTTL + 200*time.Millisecond)
                rec, f, e := r.Resolve("p")
                if e != nil || !f || rec == nil || rec.Addr != "7.7.7.7" {
                    t.Fatalf("post-negTTL positive resolve found=%v rec=%+v err=%v", f, rec, e)
                }
                if got := s.count("p"); got != 1 {
                    t.Fatalf("LOOKUPCOUNT want 1 got %d (positive expired at negTTL -> shared TTL bug)", got)
                }
            }
            """
        )
        res = _run_probe("posout_test.go", body, run="TestPositiveOutlivesNeg")
        assert res.returncode == 0, res.stdout + res.stderr
        assert "PASS" in res.stdout, res.stdout + res.stderr

    def test_l2_error_not_cached_positive_or_negative(self):
        """L2: a backend infrastructure error is returned to the caller and NOT
        remembered as positive OR negative; a subsequent healthy Resolve for the
        same host succeeds (forcing a refetch)."""
        body = PROBE_HEADER + textwrap.dedent(
            """
            func TestErrorNotCached(t *testing.T) {
                s := newCountingService()
                s.put("b", "5.5.5.5")
                s.failNext("b", 1) // first Lookup for b is an infra failure
                r := resolver.NewResolver(s, 16, time.Minute, time.Minute)
                defer r.Close()

                _, _, e1 := r.Resolve("b")
                if e1 == nil {
                    t.Fatalf("expected error on first resolve of b, got nil")
                }
                rec, f2, e2 := r.Resolve("b")
                if e2 != nil {
                    t.Fatalf("second resolve unexpectedly errored: %v (failure was cached)", e2)
                }
                if !f2 || rec == nil || rec.Addr != "5.5.5.5" {
                    t.Fatalf("second resolve found=%v rec=%+v (error cached as negative?)", f2, rec)
                }
                if got := s.count("b"); got < 2 {
                    t.Fatalf("LOOKUPCOUNT want >=2 got %d (error must trigger refetch)", got)
                }
            }
            """
        )
        res = _run_probe("err_test.go", body, run="TestErrorNotCached")
        assert res.returncode == 0, res.stdout + res.stderr
        assert "PASS" in res.stdout, res.stdout + res.stderr

    def test_l2_concurrent_dedup_existing_host(self):
        """L2: a burst of 50+ concurrent Resolve calls for the same uncached
        EXISTING host collapses into exactly ONE backend Lookup (singleflight),
        and every goroutine sees found=true with the right addr."""
        body = PROBE_HEADER + textwrap.dedent(
            """
            func TestConcurrentDedupExisting(t *testing.T) {
                s := newCountingService()
                s.put("c", "8.8.8.8")
                s.blockCh = make(chan struct{}) // hold the single Lookup until all are queued
                r := resolver.NewResolver(s, 64, time.Minute, time.Minute)
                defer r.Close()

                const N = 64
                var wg sync.WaitGroup
                var ok, bad int32
                ready := make(chan struct{}, N)
                wg.Add(N)
                for i := 0; i < N; i++ {
                    go func() {
                        defer wg.Done()
                        ready <- struct{}{}
                        rec, f, e := r.Resolve("c")
                        if e == nil && f && rec != nil && rec.Addr == "8.8.8.8" {
                            atomic.AddInt32(&ok, 1)
                        } else {
                            atomic.AddInt32(&bad, 1)
                        }
                    }()
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
                if o := atomic.LoadInt32(&ok); o != N {
                    t.Fatalf("want %d ok results got %d", N, o)
                }
                if got := s.count("c"); got != 1 {
                    t.Fatalf("LOOKUPCOUNT want 1 got %d (no singleflight dedup)", got)
                }
            }
            """
        )
        res = _run_probe(
            "dedupexist_test.go", body, run="TestConcurrentDedupExisting",
            timeout=300,
        )
        assert res.returncode == 0, res.stdout + res.stderr
        assert "PASS" in res.stdout, res.stdout + res.stderr

    def test_l2_concurrent_dedup_missing_host(self):
        """L2: a burst of 50+ concurrent Resolve calls for the same uncached
        NON-EXISTENT host also collapses into exactly ONE backend Lookup; every
        goroutine sees found=false with no error."""
        body = PROBE_HEADER + textwrap.dedent(
            """
            func TestConcurrentDedupMissing(t *testing.T) {
                s := newCountingService() // "m" absent
                s.blockCh = make(chan struct{})
                r := resolver.NewResolver(s, 64, time.Minute, time.Minute)
                defer r.Close()

                const N = 64
                var wg sync.WaitGroup
                var ok, bad int32
                ready := make(chan struct{}, N)
                wg.Add(N)
                for i := 0; i < N; i++ {
                    go func() {
                        defer wg.Done()
                        ready <- struct{}{}
                        rec, f, e := r.Resolve("m")
                        if e == nil && !f && rec == nil {
                            atomic.AddInt32(&ok, 1)
                        } else {
                            atomic.AddInt32(&bad, 1)
                        }
                    }()
                }
                for i := 0; i < N; i++ {
                    <-ready
                }
                time.Sleep(50 * time.Millisecond)
                close(s.blockCh)
                wg.Wait()

                if b := atomic.LoadInt32(&bad); b != 0 {
                    t.Fatalf("%d goroutines got wrong/err result for missing host", b)
                }
                if o := atomic.LoadInt32(&ok); o != N {
                    t.Fatalf("want %d miss results got %d", N, o)
                }
                if got := s.count("m"); got != 1 {
                    t.Fatalf("LOOKUPCOUNT want 1 got %d (missing-host dedup failed)", got)
                }
            }
            """
        )
        res = _run_probe(
            "dedupmiss_test.go", body, run="TestConcurrentDedupMissing",
            timeout=300,
        )
        assert res.returncode == 0, res.stdout + res.stderr
        assert "PASS" in res.stdout, res.stdout + res.stderr

    def test_l2_distinct_hosts_isolated(self):
        """L2: distinct hosts return their own records (no key mixups), and each
        distinct existing host is looked up exactly once across repeats."""
        body = PROBE_HEADER + textwrap.dedent(
            """
            func TestDistinctHosts(t *testing.T) {
                s := newCountingService()
                s.put("x", "10.0.0.1")
                s.put("y", "10.0.0.2")
                r := resolver.NewResolver(s, 16, time.Minute, time.Minute)
                defer r.Close()

                for round := 0; round < 3; round++ {
                    rx, fx, ex := r.Resolve("x")
                    ry, fy, ey := r.Resolve("y")
                    if ex != nil || ey != nil || !fx || !fy {
                        t.Fatalf("round %d: x(found=%v err=%v) y(found=%v err=%v)", round, fx, ex, fy, ey)
                    }
                    if rx.Addr != "10.0.0.1" || ry.Addr != "10.0.0.2" {
                        t.Fatalf("round %d: key mixup x=%q y=%q", round, rx.Addr, ry.Addr)
                    }
                    if rx.Host != "x" || ry.Host != "y" {
                        t.Fatalf("round %d: host field mixup x=%q y=%q", round, rx.Host, ry.Host)
                    }
                }
                if cx, cy := s.count("x"), s.count("y"); cx != 1 || cy != 1 {
                    t.Fatalf("LOOKUPCOUNT want x=1 y=1 got x=%d y=%d", cx, cy)
                }
            }
            """
        )
        res = _run_probe("distinct_test.go", body, run="TestDistinctHosts")
        assert res.returncode == 0, res.stdout + res.stderr
        assert "PASS" in res.stdout, res.stdout + res.stderr

    def test_l2_no_goroutine_leak_after_close(self):
        """L2: after Close(), goleak reports no leaked goroutines (the resolver
        must release any background machinery, e.g. a janitor, it started)."""
        body = textwrap.dedent(
            """
            package resolverprobe

            import (
                "testing"
                "time"

                resolver "github.com/samber/hot/pkg/resolver"
                "go.uber.org/goleak"
            )

            type leakService struct{}

            func (leakService) Lookup(host string) (*resolver.Record, bool, error) {
                if host == "L" {
                    return &resolver.Record{Host: "L", Addr: "1.1.1.1"}, true, nil
                }
                return nil, false, nil
            }

            func TestNoLeakAfterClose(t *testing.T) {
                func() {
                    r := resolver.NewResolver(leakService{}, 16, 30*time.Millisecond, 20*time.Millisecond)
                    for i := 0; i < 5; i++ {
                        r.Resolve("L")
                        r.Resolve("missing")
                    }
                    r.Close()
                }()
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
