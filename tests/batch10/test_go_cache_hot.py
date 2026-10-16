"""Tests for the `go-cache-hot` skill task (variant ext10).

Skill: go-cache-hot — Build a Hit-Rate-Reporting Avatar Cache inside the
`github.com/samber/hot` repository (module `github.com/samber/hot`, Go 1.22+).

The variant task asks the agent to create `pkg/avatar/avatar.go` (and an
`avatar_test.go`) implementing an `AvatarCache` that wraps the `hot` cache to
serve user avatar blobs from a slow `ObjectStore` while exposing operational
hit/miss counters:
  - a memory-served read counts as exactly +1 hit / +0 miss,
  - any read that consults the store (uncached / evicted / expired) counts as
    exactly +1 miss / +0 hit — regardless of whether the store had the value,
  - an infrastructure error during a store consultation counts as a miss and
    is NOT cached,
  - counters are monotonic, concurrency-safe, and Hits+Misses always equals the
    total number of completed Fetch calls,
  - a burst of concurrent Fetches for the same uncached id collapses into a
    single store.Get,
  - a TTL governs freshness,
  - Close() leaks no goroutines.

What this file verifies:
  L1 — the deliverable files exist, the module is unmodified (no new
       third-party deps), `go build ./...` succeeds, `go vet` is clean, the
       exact required public API surface (Avatar, ObjectStore, Stats,
       NewAvatarCache, Fetch, Stats, Close) compiles against an independent
       package, and the agent's own TestAvatar tests pass (the native command).
  L2 — we DO NOT trust the agent's own test file. Instead we synthesize an
       independent probe package under REPO_DIR that imports the agent's
       `pkg/avatar` package, drives it with our own counting / failing /
       blocking ObjectStores, and asserts the concrete hit/miss bookkeeping and
       dedup/TTL/error/leak behaviors via the native `go test` toolchain,
       parsing PASS/returncode. A naive implementation (counts a memory-served
       read as a miss, counts a backend read as a hit, re-fetches every call,
       caches errors, or whose counters drift from the call count) fails at
       least one probe.

Native acceptance command driven by L2/L1:
    go test ./pkg/avatar/ -run TestAvatar -count=1
"""

import os
import re
import shutil
import subprocess
import textwrap

import pytest

REPO_DIR = "/workspace/hot"
AVATAR_PKG = os.path.join(REPO_DIR, "pkg", "avatar")
PROBE_PKG = os.path.join(REPO_DIR, "pkg", "avatarprobe")


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
    """Write a single probe file into pkg/avatarprobe and return its path."""
    os.makedirs(PROBE_PKG, exist_ok=True)
    path = os.path.join(PROBE_PKG, name)
    with open(path, "w") as fh:
        fh.write(body)
    return path


def _run_probe(name, body, run="", timeout=300):
    """Write a probe test file, run it via native go test, clean up, return CP."""
    path = _write_probe(name, body)
    try:
        args = ["test", "./pkg/avatarprobe/", "-count=1", "-v"]
        if run:
            args += ["-run", run]
        return _run_go(args, timeout=timeout)
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


# Common header reused by probe files. Imports the agent's avatar package and
# provides a concurrency-safe ObjectStore that records per-id Get counts and can
# fail or block on demand.
PROBE_HEADER = textwrap.dedent(
    """
    package avatarprobe

    import (
        "errors"
        "strconv"
        "sync"
        "sync/atomic"
        "testing"
        "time"

        avatar "github.com/samber/hot/pkg/avatar"
    )

    var _ = strconv.Itoa
    var _ = errors.New
    var _ = time.Now
    var _ = atomic.AddInt32

    // countingStore is a concurrency-safe ObjectStore recording per-id Get
    // counts. It can be told to fail the next N Gets for an id, and to block
    // every Get on a channel (to exercise singleflight dedup).
    type countingStore struct {
        mu      sync.Mutex
        counts  map[string]int
        data    map[string][]byte
        failIDs map[string]int
        blockCh chan struct{}
        entered int32
    }

    func newCountingStore() *countingStore {
        return &countingStore{
            counts:  map[string]int{},
            data:    map[string][]byte{},
            failIDs: map[string]int{},
        }
    }

    func (s *countingStore) put(id string, blob []byte) {
        s.mu.Lock()
        s.data[id] = blob
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

    func (s *countingStore) Get(userID string) (*avatar.Avatar, bool, error) {
        atomic.AddInt32(&s.entered, 1)
        if s.blockCh != nil {
            <-s.blockCh
        }
        s.mu.Lock()
        defer s.mu.Unlock()
        s.counts[userID]++
        if rem, ok := s.failIDs[userID]; ok && rem > 0 {
            s.failIDs[userID] = rem - 1
            return nil, false, errors.New("infra failure for " + userID)
        }
        if blob, ok := s.data[userID]; ok {
            cp := append([]byte(nil), blob...)
            return &avatar.Avatar{UserID: userID, Blob: cp}, true, nil
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
    _run_go(["mod", "download"], timeout=400)
    yield


# ---------------------------------------------------------------------------
# L1 — deliverable existence / well-formedness / compilation
# ---------------------------------------------------------------------------

class TestGoCacheHot:
    REPO_DIR = "/workspace/hot"

    def test_l1_avatar_source_exists(self):
        """L1: pkg/avatar/avatar.go exists and is non-empty."""
        p = os.path.join(AVATAR_PKG, "avatar.go")
        assert os.path.isfile(p), f"missing {p}"
        assert os.path.getsize(p) > 0, "avatar.go is empty"

    def test_l1_avatar_test_exists(self):
        """L1: pkg/avatar/avatar_test.go exists (agent's own deterministic tests)."""
        p = os.path.join(AVATAR_PKG, "avatar_test.go")
        assert os.path.isfile(p), f"missing {p}"
        assert os.path.getsize(p) > 0, "avatar_test.go is empty"

    def test_l1_go_mod_unmodified_module_path(self):
        """L1: still the samber/hot module and Go 1.22+ (no module-path drift)."""
        gomod = os.path.join(REPO_DIR, "go.mod")
        with open(gomod) as fh:
            text = fh.read()
        assert "module github.com/samber/hot" in text
        m = re.search(r"^go\s+(\d+)\.(\d+)", text, re.MULTILINE)
        assert m, "no go directive in go.mod"
        major, minor = int(m.group(1)), int(m.group(2))
        assert (major, minor) >= (1, 22), f"go {major}.{minor} < 1.22"

    def test_l1_build_whole_module(self):
        """L1: `go build ./...` succeeds with the new avatar package present."""
        res = _run_go(["build", "./..."], timeout=400)
        assert res.returncode == 0, (
            "go build ./... failed:\n" + res.stdout + res.stderr
        )

    def test_l1_vet_avatar_package(self):
        """L1: `go vet ./pkg/avatar/` is clean (well-formed Go)."""
        res = _run_go(["vet", "./pkg/avatar/"], timeout=300)
        assert res.returncode == 0, (
            "go vet ./pkg/avatar/ failed:\n" + res.stdout + res.stderr
        )

    def test_l1_public_api_surface_compiles(self):
        """L1: the exact required public API (Avatar fields, ObjectStore, Stats
        fields, NewAvatarCache, Fetch, Stats, Close) compiles when referenced
        from an independent package with the documented signatures."""
        body = PROBE_HEADER + textwrap.dedent(
            """
            func TestAPISurface(t *testing.T) {
                // ObjectStore is an interface our countingStore satisfies.
                var _ avatar.ObjectStore = newCountingStore()

                // Avatar has UserID string and Blob []byte.
                av := avatar.Avatar{UserID: "x", Blob: []byte("b")}
                _ = av.UserID
                _ = av.Blob

                // Stats has Hits int64 and Misses int64.
                var st avatar.Stats
                var hits int64 = st.Hits
                var misses int64 = st.Misses
                _ = hits
                _ = misses

                store := newCountingStore()
                c := avatar.NewAvatarCache(store, 8, time.Second)

                var rec *avatar.Avatar
                var found bool
                var err error
                rec, found, err = c.Fetch("x")
                _ = rec
                _ = found
                _ = err

                var snap avatar.Stats = c.Stats()
                _ = snap

                c.Close()
            }
            """
        )
        res = _run_probe("api_surface_test.go", body, run="TestAPISurface")
        assert res.returncode == 0, (
            "API surface probe failed to compile/run:\n" + res.stdout + res.stderr
        )
        assert "PASS" in res.stdout, res.stdout + res.stderr

    def test_l1_agent_tests_run(self):
        """L1: the agent's own TestAvatar* tests pass (the native acceptance
        command: `go test ./pkg/avatar/ -run TestAvatar -count=1`)."""
        res = _run_go(
            ["test", "./pkg/avatar/", "-run", "TestAvatar", "-count=1"],
            timeout=400,
        )
        assert res.returncode == 0, (
            "agent's own `go test ./pkg/avatar -run TestAvatar` failed:\n"
            + res.stdout + res.stderr
        )


# ---------------------------------------------------------------------------
# L2 — independent behavioral probes via native `go test`
# ---------------------------------------------------------------------------

    def test_l2_first_fetch_is_a_miss(self):
        """L2: from a fresh cache, the FIRST Fetch of an existing id records
        exactly one miss and zero hits, and consults the store exactly once.
        A naive impl that counts a backend read as a hit fails here."""
        body = PROBE_HEADER + textwrap.dedent(
            """
            func TestFirstMiss(t *testing.T) {
                s := newCountingStore()
                s.put("u1", []byte("pic1"))
                c := avatar.NewAvatarCache(s, 16, time.Minute)
                defer c.Close()

                av, found, err := c.Fetch("u1")
                if err != nil || !found || av == nil {
                    t.Fatalf("first fetch: found=%v err=%v av=%v", found, err, av)
                }
                if string(av.Blob) != "pic1" || av.UserID != "u1" {
                    t.Fatalf("wrong avatar returned: %+v", av)
                }
                st := c.Stats()
                if st.Hits != 0 || st.Misses != 1 {
                    t.Fatalf("STATS want hits=0 misses=1 got hits=%d misses=%d", st.Hits, st.Misses)
                }
                if got := s.count("u1"); got != 1 {
                    t.Fatalf("STORECALLS want 1 got %d", got)
                }
            }
            """
        )
        res = _run_probe("first_miss_test.go", body, run="TestFirstMiss")
        assert res.returncode == 0, res.stdout + res.stderr
        assert "PASS" in res.stdout, res.stdout + res.stderr

    def test_l2_second_fetch_is_a_hit(self):
        """L2: an immediate re-Fetch of the same id within TTL records exactly
        one additional hit, NO additional miss, and does NOT call the store
        again. A naive re-fetch-every-call impl fails here."""
        body = PROBE_HEADER + textwrap.dedent(
            """
            func TestSecondHit(t *testing.T) {
                s := newCountingStore()
                s.put("u2", []byte("pic2"))
                c := avatar.NewAvatarCache(s, 16, time.Minute)
                defer c.Close()

                if _, f, e := c.Fetch("u2"); e != nil || !f {
                    t.Fatalf("first fetch found=%v err=%v", f, e)
                }
                av, found, err := c.Fetch("u2")
                if err != nil || !found || av == nil || string(av.Blob) != "pic2" {
                    t.Fatalf("second fetch found=%v err=%v av=%+v", found, err, av)
                }
                st := c.Stats()
                if st.Hits != 1 || st.Misses != 1 {
                    t.Fatalf("STATS want hits=1 misses=1 got hits=%d misses=%d", st.Hits, st.Misses)
                }
                if got := s.count("u2"); got != 1 {
                    t.Fatalf("STORECALLS want 1 (second served from memory) got %d", got)
                }
            }
            """
        )
        res = _run_probe("second_hit_test.go", body, run="TestSecondHit")
        assert res.returncode == 0, res.stdout + res.stderr
        assert "PASS" in res.stdout, res.stdout + res.stderr

    def test_l2_ttl_expiry_counts_as_miss(self):
        """L2: after the TTL elapses, re-fetching the same id calls the store
        AGAIN and records an additional MISS (not a hit). A naive impl that
        ignores TTL, or that miscounts the post-expiry read as a hit, fails."""
        body = PROBE_HEADER + textwrap.dedent(
            """
            func TestTTLMiss(t *testing.T) {
                s := newCountingStore()
                s.put("u3", []byte("pic3"))
                c := avatar.NewAvatarCache(s, 16, 80*time.Millisecond)
                defer c.Close()

                if _, f, e := c.Fetch("u3"); e != nil || !f { // miss #1
                    t.Fatalf("first fetch found=%v err=%v", f, e)
                }
                if _, f, e := c.Fetch("u3"); e != nil || !f { // hit #1 (within ttl)
                    t.Fatalf("cached fetch found=%v err=%v", f, e)
                }
                st := c.Stats()
                if st.Hits != 1 || st.Misses != 1 {
                    t.Fatalf("pre-expiry STATS want hits=1 misses=1 got hits=%d misses=%d", st.Hits, st.Misses)
                }
                if got := s.count("u3"); got != 1 {
                    t.Fatalf("STORECALLS pre-expiry want 1 got %d", got)
                }

                time.Sleep(220 * time.Millisecond) // exceed ttl

                if _, f, e := c.Fetch("u3"); e != nil || !f { // miss #2 (re-fetch)
                    t.Fatalf("post-ttl fetch found=%v err=%v", f, e)
                }
                st = c.Stats()
                if st.Hits != 1 || st.Misses != 2 {
                    t.Fatalf("post-expiry STATS want hits=1 misses=2 got hits=%d misses=%d", st.Hits, st.Misses)
                }
                if got := s.count("u3"); got < 2 {
                    t.Fatalf("STORECALLS post-expiry want >=2 got %d (ttl not honored)", got)
                }
            }
            """
        )
        res = _run_probe("ttl_miss_test.go", body, run="TestTTLMiss")
        assert res.returncode == 0, res.stdout + res.stderr
        assert "PASS" in res.stdout, res.stdout + res.stderr

    def test_l2_unknown_id_is_a_miss(self):
        """L2: Fetch of an unknown id returns found=false with a nil avatar and
        records a miss (the read went to the backend)."""
        body = PROBE_HEADER + textwrap.dedent(
            """
            func TestUnknownMiss(t *testing.T) {
                s := newCountingStore() // no data => everything unknown
                c := avatar.NewAvatarCache(s, 16, time.Minute)
                defer c.Close()

                av, found, err := c.Fetch("ghost")
                if err != nil || found || av != nil {
                    t.Fatalf("unknown fetch: found=%v err=%v av=%v", found, err, av)
                }
                st := c.Stats()
                if st.Hits != 0 || st.Misses != 1 {
                    t.Fatalf("STATS want hits=0 misses=1 got hits=%d misses=%d", st.Hits, st.Misses)
                }
                if got := s.count("ghost"); got < 1 {
                    t.Fatalf("STORECALLS want >=1 got %d (store must be consulted)", got)
                }
            }
            """
        )
        res = _run_probe("unknown_test.go", body, run="TestUnknownMiss")
        assert res.returncode == 0, res.stdout + res.stderr
        assert "PASS" in res.stdout, res.stdout + res.stderr

    def test_l2_error_is_miss_and_not_cached(self):
        """L2: an infrastructure error counts the attempt as a MISS, is returned
        to the caller, and is NOT cached — a subsequent healthy Fetch of the
        same id resolves normally (and re-consults the store). A naive impl that
        caches errors, or counts an errored read as a hit, fails."""
        body = PROBE_HEADER + textwrap.dedent(
            """
            func TestErrorMiss(t *testing.T) {
                s := newCountingStore()
                s.put("u4", []byte("pic4"))
                s.failNext("u4", 1) // first store Get for u4 fails
                c := avatar.NewAvatarCache(s, 16, time.Minute)
                defer c.Close()

                av, found, err := c.Fetch("u4")
                if err == nil {
                    t.Fatalf("expected error on first fetch, got found=%v av=%v", found, av)
                }
                st := c.Stats()
                if st.Hits != 0 || st.Misses != 1 {
                    t.Fatalf("post-error STATS want hits=0 misses=1 got hits=%d misses=%d", st.Hits, st.Misses)
                }

                av2, found2, err2 := c.Fetch("u4") // healthy now
                if err2 != nil || !found2 || av2 == nil || string(av2.Blob) != "pic4" {
                    t.Fatalf("recovery fetch found=%v err=%v av=%+v (error was cached?)", found2, err2, av2)
                }
                st = c.Stats()
                // second fetch went to the store again (error not cached) -> another miss
                if st.Misses != 2 {
                    t.Fatalf("STATS after recovery want misses=2 got misses=%d", st.Misses)
                }
                if st.Hits != 0 {
                    t.Fatalf("STATS after recovery want hits=0 got hits=%d", st.Hits)
                }
                if got := s.count("u4"); got < 2 {
                    t.Fatalf("STORECALLS want >=2 got %d (error must trigger refetch)", got)
                }
            }
            """
        )
        res = _run_probe("error_miss_test.go", body, run="TestErrorMiss")
        assert res.returncode == 0, res.stdout + res.stderr
        assert "PASS" in res.stdout, res.stdout + res.stderr

    def test_l2_counter_invariant_over_sequence(self):
        """L2: over a deterministic sequence of Fetch calls, Hits+Misses equals
        the exact number of completed Fetch calls, and the per-class totals match
        the expected outcome of each call. This catches counter drift and any
        double-counting (a read counted as both hit and miss)."""
        body = PROBE_HEADER + textwrap.dedent(
            """
            func TestCounterInvariant(t *testing.T) {
                s := newCountingStore()
                s.put("a", []byte("A"))
                s.put("b", []byte("B"))
                c := avatar.NewAvatarCache(s, 16, time.Minute)
                defer c.Close()

                // Sequence (all within ttl, capacity ample so nothing evicts):
                //  a -> miss   (uncached existing)
                //  a -> hit    (resident)
                //  b -> miss   (uncached existing)
                //  ghost -> miss (unknown)
                //  a -> hit    (resident)
                //  b -> hit    (resident)
                //  ghost -> ?  (unknown; negative caching is NOT required by the
                //               spec, so we don't assert hit-vs-miss for it here)
                type step struct{ id string }
                seq := []step{{"a"}, {"a"}, {"b"}, {"ghost"}, {"a"}, {"b"}}
                for _, st := range seq {
                    if _, _, err := c.Fetch(st.id); err != nil {
                        t.Fatalf("fetch %q errored: %v", st.id, err)
                    }
                }
                total := int64(len(seq))
                st := c.Stats()
                if st.Hits+st.Misses != total {
                    t.Fatalf("INVARIANT broken: hits(%d)+misses(%d)=%d != calls(%d)",
                        st.Hits, st.Misses, st.Hits+st.Misses, total)
                }
                // Expected exact split for this sequence:
                //  misses: a(first), b(first), ghost(unknown) = 3
                //  hits:   a(2nd), a(3rd... actually 5th call), b(6th call) = 3
                if st.Misses != 3 {
                    t.Fatalf("STATS want misses=3 got %d", st.Misses)
                }
                if st.Hits != 3 {
                    t.Fatalf("STATS want hits=3 got %d", st.Hits)
                }
            }
            """
        )
        res = _run_probe("invariant_test.go", body, run="TestCounterInvariant")
        assert res.returncode == 0, res.stdout + res.stderr
        assert "PASS" in res.stdout, res.stdout + res.stderr

    def test_l2_eviction_counts_as_miss(self):
        """L2: resolving far more distinct ids than capacity keeps memory bounded;
        an evicted id forces a fresh store Get on re-fetch and that read is
        counted as a MISS (not a hit). Catches unbounded growth AND miscounting
        an evicted-then-refetched read as a hit."""
        body = PROBE_HEADER + textwrap.dedent(
            """
            func TestEvictionMiss(t *testing.T) {
                const cap = 8
                s := newCountingStore()
                for i := 0; i < 500; i++ {
                    id := "k" + strconv.Itoa(i)
                    s.put(id, []byte(id))
                }
                c := avatar.NewAvatarCache(s, cap, time.Minute)
                defer c.Close()

                // Resolve far more than capacity distinct ids (each a miss).
                for i := 0; i < 500; i++ {
                    id := "k" + strconv.Itoa(i)
                    if _, f, e := c.Fetch(id); e != nil || !f {
                        t.Fatalf("fetch %s found=%v err=%v", id, f, e)
                    }
                }
                st := c.Stats()
                // All 500 first-touches were misses; nothing repeated yet.
                if st.Hits != 0 {
                    t.Fatalf("STATS want hits=0 after distinct sweep got %d", st.Hits)
                }
                if st.Misses != 500 {
                    t.Fatalf("STATS want misses=500 got %d", st.Misses)
                }

                // k0 was resolved first; with cap=8 it must be evicted by now.
                before := s.count("k0")
                missesBefore := c.Stats().Misses
                if _, f, e := c.Fetch("k0"); e != nil || !f {
                    t.Fatalf("re-fetch k0 found=%v err=%v", f, e)
                }
                after := s.count("k0")
                missesAfter := c.Stats().Misses
                if after <= before {
                    t.Fatalf("k0 not evicted: store count stayed %d (unbounded growth)", after)
                }
                if missesAfter != missesBefore+1 {
                    t.Fatalf("evicted re-fetch must count as a miss: misses %d -> %d", missesBefore, missesAfter)
                }
            }
            """
        )
        res = _run_probe("eviction_test.go", body, run="TestEvictionMiss")
        assert res.returncode == 0, res.stdout + res.stderr
        assert "PASS" in res.stdout, res.stdout + res.stderr

    def test_l2_concurrent_dedup_single_store_get(self):
        """L2: 50+ concurrent Fetches of the SAME uncached id collapse into a
        single store.Get (blocking Get); afterward a final fetch of that now
        resident id records a hit. The blocked callers went to the backend, so
        Hits+Misses still equals the total completed Fetch count. A naive impl
        without singleflight issues many store Gets and fails."""
        body = PROBE_HEADER + textwrap.dedent(
            """
            func TestConcurrentDedup(t *testing.T) {
                s := newCountingStore()
                s.put("hot", []byte("HOT"))
                s.blockCh = make(chan struct{})
                c := avatar.NewAvatarCache(s, 64, time.Minute)
                defer c.Close()

                const N = 60
                var wg sync.WaitGroup
                var ok, bad int32
                ready := make(chan struct{}, N)
                wg.Add(N)
                for i := 0; i < N; i++ {
                    go func() {
                        defer wg.Done()
                        ready <- struct{}{}
                        av, f, e := c.Fetch("hot")
                        if e == nil && f && av != nil && string(av.Blob) == "HOT" {
                            atomic.AddInt32(&ok, 1)
                        } else {
                            atomic.AddInt32(&bad, 1)
                        }
                    }()
                }
                for i := 0; i < N; i++ {
                    <-ready
                }
                time.Sleep(60 * time.Millisecond) // let all enter Fetch / coalesce
                close(s.blockCh)                   // release the single store Get
                wg.Wait()

                if b := atomic.LoadInt32(&bad); b != 0 {
                    t.Fatalf("%d goroutines got wrong/err result", b)
                }
                if o := atomic.LoadInt32(&ok); o != N {
                    t.Fatalf("want %d ok results got %d", N, o)
                }
                if got := s.count("hot"); got != 1 {
                    t.Fatalf("STORECALLS want 1 got %d (no singleflight dedup)", got)
                }

                // All N concurrent callers consulted the backend -> N misses.
                st := c.Stats()
                if st.Misses != int64(N) {
                    t.Fatalf("STATS want misses=%d (all coalesced callers are backend reads) got %d", N, st.Misses)
                }
                if st.Hits != 0 {
                    t.Fatalf("STATS want hits=0 after dedup burst got %d", st.Hits)
                }

                // Now resident: final fetch must be a hit, no new store call.
                if _, f, e := c.Fetch("hot"); e != nil || !f {
                    t.Fatalf("post-dedup fetch found=%v err=%v", f, e)
                }
                st = c.Stats()
                if st.Hits != 1 {
                    t.Fatalf("STATS want hits=1 after final resident fetch got %d", st.Hits)
                }
                if st.Hits+st.Misses != int64(N)+1 {
                    t.Fatalf("INVARIANT broken: hits+misses=%d != calls=%d", st.Hits+st.Misses, N+1)
                }
                if got := s.count("hot"); got != 1 {
                    t.Fatalf("STORECALLS after resident fetch want 1 got %d", got)
                }
            }
            """
        )
        res = _run_probe(
            "dedup_test.go", body, run="TestConcurrentDedup", timeout=300
        )
        assert res.returncode == 0, res.stdout + res.stderr
        assert "PASS" in res.stdout, res.stdout + res.stderr

    def test_l2_counters_monotonic_under_concurrency(self):
        """L2: under heavy concurrent mixed Fetches, the final Hits+Misses equals
        the exact total number of completed Fetch calls (counters are
        race-free and each call adjusts by exactly one). Run with -race to
        surface data races in the counter implementation."""
        body = PROBE_HEADER + textwrap.dedent(
            """
            func TestConcurrentInvariant(t *testing.T) {
                s := newCountingStore()
                for i := 0; i < 20; i++ {
                    id := "id" + strconv.Itoa(i)
                    s.put(id, []byte(id))
                }
                c := avatar.NewAvatarCache(s, 32, time.Minute)
                defer c.Close()

                const workers = 16
                const perWorker = 200
                var wg sync.WaitGroup
                wg.Add(workers)
                for w := 0; w < workers; w++ {
                    go func(seed int) {
                        defer wg.Done()
                        for j := 0; j < perWorker; j++ {
                            id := "id" + strconv.Itoa((seed*7+j*3)%20)
                            c.Fetch(id)
                        }
                    }(w)
                }
                wg.Wait()

                total := int64(workers * perWorker)
                st := c.Stats()
                if st.Hits+st.Misses != total {
                    t.Fatalf("INVARIANT broken under concurrency: hits(%d)+misses(%d)=%d != calls(%d)",
                        st.Hits, st.Misses, st.Hits+st.Misses, total)
                }
                if st.Hits < 0 || st.Misses < 0 {
                    t.Fatalf("counters went negative: hits=%d misses=%d", st.Hits, st.Misses)
                }
            }
            """
        )
        res = _run_probe(
            "concurrent_invariant_test.go",
            body,
            run="TestConcurrentInvariant",
            timeout=300,
        )
        assert res.returncode == 0, res.stdout + res.stderr
        assert "PASS" in res.stdout, res.stdout + res.stderr

    def test_l2_no_goroutine_leak_after_close(self):
        """L2: after Close(), go.uber.org/goleak reports no leaked goroutines —
        the cache must release any background machinery (e.g. a TTL janitor)."""
        body = textwrap.dedent(
            """
            package avatarprobe

            import (
                "testing"
                "time"

                avatar "github.com/samber/hot/pkg/avatar"
                "go.uber.org/goleak"
            )

            type leakStore struct{}

            func (leakStore) Get(userID string) (*avatar.Avatar, bool, error) {
                if userID == "L" {
                    return &avatar.Avatar{UserID: "L", Blob: []byte("leo")}, true, nil
                }
                return nil, false, nil
            }

            func TestNoLeakAfterClose(t *testing.T) {
                func() {
                    c := avatar.NewAvatarCache(leakStore{}, 16, 20*time.Millisecond)
                    for i := 0; i < 5; i++ {
                        c.Fetch("L")
                    }
                    c.Close()
                }()
                time.Sleep(120 * time.Millisecond) // let any janitor stop
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
