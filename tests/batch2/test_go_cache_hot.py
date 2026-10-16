"""Tests for the `go-cache-hot` skill task (variant ext2).

Skill: go-cache-hot — Build a Sliding-Expiry Session Store inside the
`github.com/samber/hot` repository.

The task asks the agent to create `pkg/session/session.go` (and a
`session_test.go`) implementing a `SessionStore` that wraps the `hot` cache to
serve web sessions from a slow `Store` (source of truth) while:
  - refreshing a session's in-memory lifetime on every successful Access
    (sliding / recency-driven expiry),
  - re-loading from `store` once a session has been idle longer than idleTTL,
  - evicting the LEAST-RECENTLY-ACCESSED sessions when distinct live sessions
    exceed `capacity` (a continuously-touched hot id must stay resident while
    a flood of cold ids gets evicted),
  - never remembering a failed (errored) Access,
  - collapsing a burst of concurrent Access calls for the same uncached id
    into a single `store.Load`,
  - leaking no goroutines after Close().

What this file verifies:
  L1 — the deliverable files exist, the package builds (`go build ./...`),
       `go vet` is clean, go.mod is unmodified (still samber/hot, Go >= 1.22,
       no new third-party deps), the exact required public API surface
       (Session fields, Store interface, NewSessionStore, Access, Close)
       compiles when referenced from an independent package, and the agent's
       own `go test ./pkg/session/ -run TestSession -count=1` passes.
  L2 — we DO NOT trust the agent's own test file. Instead we synthesize an
       independent probe package under REPO_DIR that imports the agent's
       `pkg/session` package, drives it with our own per-id counting /
       blocking / failing Stores, and asserts the concrete behaviors via the
       native `go test` toolchain (results parsed from stdout). A naive
       implementation (load-every-time, fixed expiry not refreshed on access,
       arbitrary eviction rather than LRU, caching failures, never expiring,
       or no singleflight dedup) fails at least one probe.

Native acceptance command driven at L2:
    go test ./pkg/sessionprobe/ -count=1 -v
(mirrors the doc's `go test ./pkg/session/ -run TestSession -count=1` but
against an independent harness we control).
"""

import os
import re
import shutil
import subprocess
import textwrap

import pytest

REPO_DIR = "/workspace/hot"
SESSION_PKG = os.path.join(REPO_DIR, "pkg", "session")
PROBE_PKG = os.path.join(REPO_DIR, "pkg", "sessionprobe")


def _run_go(args, timeout=300):
    """Run a go command from REPO_DIR with module-mode env sane defaults."""
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
    """Write a single probe test file into pkg/sessionprobe and return path.

    The probe imports the agent's session package via the module path so it
    compiles only against the real public API.
    """
    os.makedirs(PROBE_PKG, exist_ok=True)
    path = os.path.join(PROBE_PKG, name)
    with open(path, "w") as fh:
        fh.write(body)
    return path


def _run_probe(name, body, run="", timeout=300):
    """Write a probe test file, run it, clean it up, return CompletedProcess."""
    path = _write_probe(name, body)
    try:
        args = ["test", "./pkg/sessionprobe/", "-count=1", "-v"]
        if run:
            args += ["-run", run]
        return _run_go(args, timeout=timeout)
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


# Common header reused by probe files. Imports the agent package and defines a
# concurrency-safe Store that records per-id Load call counts and can be told
# to fail or block on demand.
PROBE_HEADER = textwrap.dedent(
    """
    package sessionprobe

    import (
        "errors"
        "strconv"
        "sync"
        "sync/atomic"
        "testing"
        "time"

        session "github.com/samber/hot/pkg/session"
    )

    var _ = strconv.Itoa
    var _ = errors.New
    var _ = time.Now
    var _ = atomic.AddInt32

    // countingStore is the slow source of truth. It records per-id Load call
    // counts, can fail the next N loads for an id, and can block inside Load on
    // a channel so a concurrency window is real. Safe for concurrent use.
    type countingStore struct {
        mu      sync.Mutex
        counts  map[string]int
        data    map[string]*session.Session
        failIDs map[string]int // remaining forced failures per id
        blockCh chan struct{}  // if non-nil, Load waits on it once entered
        entered int32
    }

    func newCountingStore() *countingStore {
        return &countingStore{
            counts:  map[string]int{},
            data:    map[string]*session.Session{},
            failIDs: map[string]int{},
        }
    }

    func (s *countingStore) put(sess *session.Session) {
        s.mu.Lock()
        s.data[sess.ID] = sess
        s.mu.Unlock()
    }

    func (s *countingStore) failNext(id string, n int) {
        s.mu.Lock()
        s.failIDs[id] = n
        s.mu.Unlock()
    }

    func (s *countingStore) count(id string) int {
        s.mu.Lock()
        defer s.mu.Unlock()
        return s.counts[id]
    }

    func (s *countingStore) Load(id string) (*session.Session, bool, error) {
        atomic.AddInt32(&s.entered, 1)
        if s.blockCh != nil {
            <-s.blockCh
        }
        s.mu.Lock()
        defer s.mu.Unlock()
        s.counts[id]++
        if rem, ok := s.failIDs[id]; ok && rem > 0 {
            s.failIDs[id] = rem - 1
            return nil, false, errors.New("infra failure for " + id)
        }
        if sess, ok := s.data[id]; ok {
            // hand back a copy so the store's own isolation is irrelevant.
            cp := *sess
            cp.Roles = append([]string(nil), sess.Roles...)
            return &cp, true, nil
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
    # Pre-download module dependencies so per-test timeouts are about behavior.
    res = _run_go(["mod", "download"], timeout=400)
    yield res


# ---------------------------------------------------------------------------
# L1 — deliverable existence / well-formedness / compilation
# ---------------------------------------------------------------------------

class TestGoCacheHot:
    REPO_DIR = "/workspace/hot"

    def test_l1_session_source_exists(self):
        """L1: pkg/session/session.go exists and is non-empty."""
        p = os.path.join(SESSION_PKG, "session.go")
        assert os.path.isfile(p), f"missing {p}"
        assert os.path.getsize(p) > 0, "session.go is empty"

    def test_l1_session_test_exists(self):
        """L1: pkg/session/session_test.go exists (agent's own tests)."""
        p = os.path.join(SESSION_PKG, "session_test.go")
        assert os.path.isfile(p), f"missing {p}"
        assert os.path.getsize(p) > 0, "session_test.go is empty"

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
        """L1: `go build ./...` succeeds with the new session package present."""
        res = _run_go(["build", "./..."], timeout=400)
        assert res.returncode == 0, (
            "go build ./... failed:\n" + res.stdout + res.stderr
        )

    def test_l1_vet_session_package(self):
        """L1: `go vet` of the session package is clean (well-formed Go)."""
        res = _run_go(["vet", "./pkg/session/"], timeout=300)
        assert res.returncode == 0, (
            "go vet ./pkg/session/ failed:\n" + res.stdout + res.stderr
        )

    def test_l1_public_api_surface_compiles(self):
        """L1: the exact required public API (Session fields, Store interface,
        NewSessionStore, Access, Close) compiles from an independent package."""
        body = PROBE_HEADER + textwrap.dedent(
            """
            func TestAPISurface(t *testing.T) {
                var _ session.Store = newCountingStore()
                sess := session.Session{ID: "x", UserID: "u", Roles: []string{"admin"}}
                _ = sess.ID
                _ = sess.UserID
                _ = sess.Roles
                st := newCountingStore()
                store := session.NewSessionStore(st, 8, time.Second)
                var rec *session.Session
                var found bool
                var err error
                rec, found, err = store.Access("x")
                _ = rec
                _ = found
                _ = err
                store.Close()
            }
            """
        )
        res = _run_probe("api_surface_test.go", body, run="TestAPISurface")
        assert res.returncode == 0, (
            "API surface probe failed to compile/run:\n" + res.stdout + res.stderr
        )
        assert "PASS" in res.stdout, res.stdout + res.stderr

    def test_l1_agent_tests_run(self):
        """L1: the agent's own TestSession* tests pass (doc acceptance command)."""
        res = _run_go(
            ["test", "./pkg/session/", "-run", "TestSession", "-count=1"],
            timeout=400,
        )
        assert res.returncode == 0, (
            "agent's own go test ./pkg/session -run TestSession failed:\n"
            + res.stdout + res.stderr
        )

# ---------------------------------------------------------------------------
# L2 — independent behavioral probes via native `go test`
# ---------------------------------------------------------------------------

    def test_l2_hit_cached_within_ttl(self):
        """L2: an existing id accessed twice within idleTTL triggers exactly ONE
        store.Load and returns identical data both times."""
        body = PROBE_HEADER + textwrap.dedent(
            """
            func TestHitCached(t *testing.T) {
                st := newCountingStore()
                st.put(&session.Session{ID: "A", UserID: "alice", Roles: []string{"vip"}})
                store := session.NewSessionStore(st, 16, time.Minute)
                defer store.Close()

                r1, f1, e1 := store.Access("A")
                if e1 != nil || !f1 || r1 == nil {
                    t.Fatalf("first access: found=%v err=%v rec=%v", f1, e1, r1)
                }
                r2, f2, e2 := store.Access("A")
                if e2 != nil || !f2 || r2 == nil {
                    t.Fatalf("second access: found=%v err=%v", f2, e2)
                }
                if r1.UserID != "alice" || r2.UserID != "alice" {
                    t.Fatalf("data mismatch r1=%+v r2=%+v", r1, r2)
                }
                if got := st.count("A"); got != 1 {
                    t.Fatalf("LOADCOUNT want 1 got %d (re-loaded a cached session)", got)
                }
            }
            """
        )
        res = _run_probe("hit_test.go", body, run="TestHitCached")
        assert res.returncode == 0, res.stdout + res.stderr
        assert "PASS" in res.stdout, res.stdout + res.stderr

    def test_l2_missing_id_not_found(self):
        """L2: a non-existent id returns (nil, false, nil)."""
        body = PROBE_HEADER + textwrap.dedent(
            """
            func TestMissing(t *testing.T) {
                st := newCountingStore() // no data => everything missing
                store := session.NewSessionStore(st, 16, time.Minute)
                defer store.Close()

                r, f, e := store.Access("Z")
                if e != nil {
                    t.Fatalf("unexpected error for missing id: %v", e)
                }
                if f {
                    t.Fatalf("missing id reported found=true")
                }
                if r != nil {
                    t.Fatalf("missing id returned non-nil session %+v", r)
                }
            }
            """
        )
        res = _run_probe("missing_test.go", body, run="TestMissing")
        assert res.returncode == 0, res.stdout + res.stderr
        assert "PASS" in res.stdout, res.stdout + res.stderr

    def test_l2_sliding_expiry_refreshes_on_access(self):
        """L2: repeatedly touching a session within idleTTL keeps it resident
        (no re-load), even though wall-clock time exceeds idleTTL overall —
        a FIXED (non-sliding) expiry would force a re-load."""
        body = PROBE_HEADER + textwrap.dedent(
            """
            func TestSlidingRefresh(t *testing.T) {
                st := newCountingStore()
                st.put(&session.Session{ID: "S", UserID: "sam", Roles: []string{"u"}})
                // idleTTL is short; we touch faster than it, for longer than it.
                const ttl = 120 * time.Millisecond
                store := session.NewSessionStore(st, 16, ttl)
                defer store.Close()

                // Prime the cache.
                if _, f, e := store.Access("S"); e != nil || !f {
                    t.Fatalf("prime access found=%v err=%v", f, e)
                }
                // Touch every 40ms for ~400ms (>> ttl). Sliding expiry must keep
                // it resident the whole time.
                deadline := time.Now().Add(400 * time.Millisecond)
                for time.Now().Before(deadline) {
                    time.Sleep(40 * time.Millisecond)
                    r, f, e := store.Access("S")
                    if e != nil || !f || r == nil || r.UserID != "sam" {
                        t.Fatalf("touch access found=%v err=%v rec=%v", f, e, r)
                    }
                }
                if got := st.count("S"); got != 1 {
                    t.Fatalf("LOADCOUNT want 1 got %d (expiry not refreshed on access)", got)
                }
            }
            """
        )
        res = _run_probe("sliding_test.go", body, run="TestSlidingRefresh", timeout=300)
        assert res.returncode == 0, res.stdout + res.stderr
        assert "PASS" in res.stdout, res.stdout + res.stderr

    def test_l2_idle_past_ttl_triggers_reload(self):
        """L2: a session left idle longer than idleTTL is re-loaded from store
        on its next access."""
        body = PROBE_HEADER + textwrap.dedent(
            """
            func TestIdleReload(t *testing.T) {
                st := newCountingStore()
                st.put(&session.Session{ID: "I", UserID: "ivy", Roles: []string{"u"}})
                store := session.NewSessionStore(st, 16, 80*time.Millisecond)
                defer store.Close()

                if _, f, e := store.Access("I"); e != nil || !f {
                    t.Fatalf("first access found=%v err=%v", f, e)
                }
                if _, f, e := store.Access("I"); e != nil || !f { // within ttl -> cached
                    t.Fatalf("cached access found=%v err=%v", f, e)
                }
                if got := st.count("I"); got != 1 {
                    t.Fatalf("LOADCOUNT before idle want 1 got %d", got)
                }
                // Stay idle past idleTTL.
                time.Sleep(250 * time.Millisecond)
                if _, f, e := store.Access("I"); e != nil || !f {
                    t.Fatalf("post-idle access found=%v err=%v", f, e)
                }
                if got := st.count("I"); got < 2 {
                    t.Fatalf("LOADCOUNT after idle want >=2 got %d (idleTTL not honored)", got)
                }
            }
            """
        )
        res = _run_probe("idle_test.go", body, run="TestIdleReload")
        assert res.returncode == 0, res.stdout + res.stderr
        assert "PASS" in res.stdout, res.stdout + res.stderr

    def test_l2_lru_recency_eviction(self):
        """L2: a continuously-touched HOT id survives a flood of > capacity cold
        ids (loaded exactly once), while a cold id re-accessed after the flood is
        loaded AGAIN — eviction must be by recency, not arbitrary."""
        body = PROBE_HEADER + textwrap.dedent(
            """
            func TestLRURecency(t *testing.T) {
                const cap = 8
                st := newCountingStore()
                st.put(&session.Session{ID: "HOT", UserID: "hot", Roles: []string{"u"}})
                for i := 0; i < 500; i++ {
                    id := "c" + strconv.Itoa(i)
                    st.put(&session.Session{ID: id, UserID: id, Roles: []string{"u"}})
                }
                // idleTTL long so nothing expires by time; only capacity/LRU evicts.
                store := session.NewSessionStore(st, cap, time.Hour)
                defer store.Close()

                // Prime HOT.
                if _, f, e := store.Access("HOT"); e != nil || !f {
                    t.Fatalf("prime HOT found=%v err=%v", f, e)
                }
                // Access cold ids c0..c1 first so they are the oldest, then flood.
                if _, f, e := store.Access("c0"); e != nil || !f {
                    t.Fatalf("prime c0 found=%v err=%v", f, e)
                }
                c0Before := st.count("c0")

                // Flood far more than capacity distinct cold ids, touching HOT
                // every round so it stays the most-recently-used.
                for i := 1; i < 500; i++ {
                    id := "c" + strconv.Itoa(i)
                    if _, f, e := store.Access(id); e != nil || !f {
                        t.Fatalf("cold %s found=%v err=%v", id, f, e)
                    }
                    if _, f, e := store.Access("HOT"); e != nil || !f {
                        t.Fatalf("touch HOT found=%v err=%v", f, e)
                    }
                }

                // HOT must have been loaded exactly once across the whole test.
                if got := st.count("HOT"); got != 1 {
                    t.Fatalf("HOT LOADCOUNT want 1 got %d (hot set not retained by recency)", got)
                }
                // c0 was the least-recently accessed; with cap=8 it must have been
                // evicted. Re-accessing it must hit the store AGAIN.
                if _, f, e := store.Access("c0"); e != nil || !f {
                    t.Fatalf("re-access c0 found=%v err=%v", f, e)
                }
                if after := st.count("c0"); after <= c0Before {
                    t.Fatalf("c0 not evicted: LOADCOUNT stayed %d (eviction not LRU/unbounded)", after)
                }
            }
            """
        )
        res = _run_probe("lru_test.go", body, run="TestLRURecency", timeout=300)
        assert res.returncode == 0, res.stdout + res.stderr
        assert "PASS" in res.stdout, res.stdout + res.stderr

    def test_l2_concurrent_dedup_single_load(self):
        """L2: a burst of 50+ concurrent Access calls for the same uncached id
        collapses into exactly ONE store.Load; every goroutine sees found=true
        with correct data."""
        body = PROBE_HEADER + textwrap.dedent(
            """
            func TestConcurrentDedup(t *testing.T) {
                st := newCountingStore()
                st.put(&session.Session{ID: "C", UserID: "carol", Roles: []string{"q"}})
                st.blockCh = make(chan struct{})
                store := session.NewSessionStore(st, 64, time.Minute)
                defer store.Close()

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
                        r, f, e := store.Access("C")
                        if e == nil && f && r != nil && r.UserID == "carol" {
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
                close(st.blockCh)
                wg.Wait()

                if bad := atomic.LoadInt32(&badCount); bad != 0 {
                    t.Fatalf("%d goroutines got wrong/err result", bad)
                }
                if ok := atomic.LoadInt32(&okCount); ok != N {
                    t.Fatalf("want %d ok results got %d", N, ok)
                }
                if got := st.count("C"); got != 1 {
                    t.Fatalf("LOADCOUNT want 1 got %d (no singleflight dedup)", got)
                }
            }
            """
        )
        res = _run_probe("dedup_test.go", body, run="TestConcurrentDedup", timeout=300)
        assert res.returncode == 0, res.stdout + res.stderr
        assert "PASS" in res.stdout, res.stdout + res.stderr

    def test_l2_error_not_cached(self):
        """L2: a store.Load error is returned to the caller and NOT remembered;
        a later healthy Access for the same id succeeds (failure not cached)."""
        body = PROBE_HEADER + textwrap.dedent(
            """
            func TestErrorNotCached(t *testing.T) {
                st := newCountingStore()
                st.put(&session.Session{ID: "B", UserID: "bob", Roles: []string{"u"}})
                st.failNext("B", 1) // first load for B fails
                store := session.NewSessionStore(st, 16, time.Minute)
                defer store.Close()

                _, _, e1 := store.Access("B")
                if e1 == nil {
                    t.Fatalf("expected error on first access of B, got nil")
                }
                r2, f2, e2 := store.Access("B")
                if e2 != nil {
                    t.Fatalf("second access unexpectedly errored: %v (failure was cached)", e2)
                }
                if !f2 || r2 == nil || r2.UserID != "bob" {
                    t.Fatalf("second access: found=%v rec=%+v", f2, r2)
                }
                if got := st.count("B"); got < 2 {
                    t.Fatalf("LOADCOUNT want >=2 got %d (failure must trigger a reload)", got)
                }
            }
            """
        )
        res = _run_probe("err_test.go", body, run="TestErrorNotCached")
        assert res.returncode == 0, res.stdout + res.stderr
        assert "PASS" in res.stdout, res.stdout + res.stderr

    def test_l2_distinct_ids_isolated(self):
        """L2: distinct ids return their own sessions (no key mixups) and each
        existing id is loaded exactly once when re-accessed within idleTTL."""
        body = PROBE_HEADER + textwrap.dedent(
            """
            func TestDistinctIDs(t *testing.T) {
                st := newCountingStore()
                st.put(&session.Session{ID: "P", UserID: "pam", Roles: []string{"r1"}})
                st.put(&session.Session{ID: "Q", UserID: "quinn", Roles: []string{"r2"}})
                store := session.NewSessionStore(st, 16, time.Minute)
                defer store.Close()

                for round := 0; round < 3; round++ {
                    rp, fp, ep := store.Access("P")
                    rq, fq, eq := store.Access("Q")
                    if ep != nil || eq != nil || !fp || !fq {
                        t.Fatalf("round %d: P(found=%v err=%v) Q(found=%v err=%v)", round, fp, ep, fq, eq)
                    }
                    if rp.UserID != "pam" || rq.UserID != "quinn" {
                        t.Fatalf("round %d: key mixup P=%q Q=%q", round, rp.UserID, rq.UserID)
                    }
                }
                if cp, cq := st.count("P"), st.count("Q"); cp != 1 || cq != 1 {
                    t.Fatalf("LOADCOUNT want P=1 Q=1 got P=%d Q=%d", cp, cq)
                }
            }
            """
        )
        res = _run_probe("distinct_test.go", body, run="TestDistinctIDs")
        assert res.returncode == 0, res.stdout + res.stderr
        assert "PASS" in res.stdout, res.stdout + res.stderr

    def test_l2_no_goroutine_leak_after_close(self):
        """L2: after Close(), goleak reports no leaked goroutines (the store must
        release any background machinery it started)."""
        body = textwrap.dedent(
            """
            package sessionprobe

            import (
                "testing"
                "time"

                session "github.com/samber/hot/pkg/session"
                "go.uber.org/goleak"
            )

            type leakStore struct{}

            func (leakStore) Load(id string) (*session.Session, bool, error) {
                if id == "L" {
                    return &session.Session{ID: "L", UserID: "leo", Roles: []string{"u"}}, true, nil
                }
                return nil, false, nil
            }

            func TestNoLeakAfterClose(t *testing.T) {
                func() {
                    store := session.NewSessionStore(leakStore{}, 16, 20*time.Millisecond)
                    for i := 0; i < 5; i++ {
                        store.Access("L")
                    }
                    store.Close()
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
