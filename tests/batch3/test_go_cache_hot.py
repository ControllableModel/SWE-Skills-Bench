"""Tests for the `go-cache-hot` skill task (variant ext3).

Skill: go-cache-hot — Build a Batch Profile Enrichment Service inside the
`github.com/samber/hot` repository.

The ext3 task asks the agent to create `pkg/enrich/enrich.go` (and an
`enrich_test.go`) implementing an `Enricher` that wraps the `hot` cache to
serve user profiles in BATCHES from a slow `Source` while:
  - resolving each requested id to either `found` (exists) or `missing`
    (source confirms it does not exist), with the two sets together covering
    exactly the requested ids on success,
  - consulting `Source.FetchBatch` only for ids not already resolved in memory
    (and not yet expired) — already-resolved ids are never re-fetched,
  - coalescing duplicate ids within a single batch so the source never sees
    the same id twice in one `FetchBatch`,
  - collapsing concurrent overlapping demand for the same uncached id into a
    single shared fetch,
  - honoring a TTL (a resolved id may be re-fetched once its ttl elapses),
  - keeping in-memory records bounded to ~capacity,
  - leaking no goroutines after Close().

NOTE: This is a DIFFERENT task than ext1's read-through *Directory* service.
The public surface here is BATCH-oriented:
    type Profile struct { ID, DisplayName string }
    type Source interface { FetchBatch(ids []string) (map[string]*Profile, error) }
    func NewEnricher(src Source, capacity int, ttl time.Duration) *Enricher
    func (e *Enricher) Enrich(ids []string) (map[string]*Profile, []string, error)
    func (e *Enricher) Close()

What this file verifies:
  L1 — the deliverable files exist, the package builds (`go build ./...`),
       `go vet` is clean, go.mod is unmodified, the required exported API
       surface compiles against an independent package, and the agent's own
       TestEnrich* tests pass (the doc's native acceptance command).
  L2 — we DO NOT trust the agent's own test file. Instead we synthesize an
       independent probe package under REPO_DIR that imports the agent's
       `pkg/enrich` package, drives it with our own counting/blocking batch
       sources, and asserts concrete behaviors. Each probe is run via the
       native `go test` toolchain and its result parsed from stdout, so a
       naive implementation (re-fetch already-resolved ids, no intra-batch
       dedup, mislabel existing vs missing, fan-out concurrent identical ids,
       no TTL, unbounded growth, leaked goroutines) fails at least one test.

The native acceptance command the L2 layer drives:
    go test ./pkg/enrich/ -run TestEnrich -count=1
"""

import os
import shutil
import subprocess
import textwrap

import pytest

REPO_DIR = "/workspace/hot"
ENRICH_PKG = os.path.join(REPO_DIR, "pkg", "enrich")
PROBE_PKG = os.path.join(REPO_DIR, "pkg", "enrichprobe")


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
    """Write a single-file probe test into pkg/enrichprobe and return its path."""
    os.makedirs(PROBE_PKG, exist_ok=True)
    path = os.path.join(PROBE_PKG, name)
    with open(path, "w") as fh:
        fh.write(body)
    return path


def _run_probe(name, body, run="", timeout=300):
    """Write a probe test file, run it via native `go test`, clean up, return CP."""
    path = _write_probe(name, body)
    try:
        args = ["test", "./pkg/enrichprobe/", "-count=1", "-v"]
        if run:
            args += ["-run", run]
        return _run_go(args, timeout=timeout)
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


# Common header reused by probe files. Imports the agent's enrich package and
# provides a concurrency-safe batch source that records, per id, how many times
# each id appeared across ALL FetchBatch calls plus how many times the same id
# appeared WITHIN a single batch (to catch intra-batch dedup failures).
PROBE_HEADER = textwrap.dedent(
    """
    package enrichprobe

    import (
        "errors"
        "sort"
        "strconv"
        "sync"
        "sync/atomic"
        "testing"
        "time"

        enrich "github.com/samber/hot/pkg/enrich"
    )

    var _ = errors.New
    var _ = strconv.Itoa
    var _ = sort.Strings
    var _ = atomic.AddInt32

    // countingSource is the slow batch backing store. It records, per id, the
    // total number of times that id has been requested across every FetchBatch
    // call, and separately flags any id that appeared more than once inside a
    // single FetchBatch call (an intra-batch dedup violation).
    type countingSource struct {
        mu          sync.Mutex
        totalCounts map[string]int // id -> total times requested across all batches
        batchCount  int            // number of FetchBatch calls made
        intraDup    map[string]int // id -> max times seen within one batch (>1 == bug)
        data        map[string]*enrich.Profile
        failNextN   int32          // if >0, the next N FetchBatch calls error out
        blockCh     chan struct{}  // if non-nil, FetchBatch waits on it once entered
        entered     int32          // number of FetchBatch invocations that began
    }

    func newCountingSource() *countingSource {
        return &countingSource{
            totalCounts: map[string]int{},
            intraDup:    map[string]int{},
            data:        map[string]*enrich.Profile{},
        }
    }

    func (s *countingSource) put(p *enrich.Profile) {
        s.mu.Lock()
        s.data[p.ID] = p
        s.mu.Unlock()
    }

    func (s *countingSource) count(id string) int {
        s.mu.Lock()
        defer s.mu.Unlock()
        return s.totalCounts[id]
    }

    func (s *countingSource) batches() int {
        s.mu.Lock()
        defer s.mu.Unlock()
        return s.batchCount
    }

    // maxIntra returns the largest number of times any id was duplicated within
    // a single FetchBatch call. A correct implementation keeps this <= 1.
    func (s *countingSource) maxIntra() int {
        s.mu.Lock()
        defer s.mu.Unlock()
        m := 0
        for _, v := range s.intraDup {
            if v > m {
                m = v
            }
        }
        return m
    }

    func (s *countingSource) FetchBatch(ids []string) (map[string]*enrich.Profile, error) {
        atomic.AddInt32(&s.entered, 1)
        if s.blockCh != nil {
            <-s.blockCh
        }
        s.mu.Lock()
        defer s.mu.Unlock()
        if s.failNextN > 0 {
            s.failNextN--
            return nil, errors.New("infra failure")
        }
        s.batchCount++
        // record intra-batch occurrences
        seen := map[string]int{}
        for _, id := range ids {
            seen[id]++
        }
        for id, n := range seen {
            if n > s.intraDup[id] {
                s.intraDup[id] = n
            }
            s.totalCounts[id] += n
        }
        out := map[string]*enrich.Profile{}
        for id := range seen {
            if p, ok := s.data[id]; ok {
                cp := *p
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
    res = _run_go(["mod", "download"], timeout=400)
    yield res


class TestGoCacheHot:
    REPO_DIR = "/workspace/hot"

    # -----------------------------------------------------------------------
    # L1 — deliverable existence / well-formedness / compilation
    # -----------------------------------------------------------------------

    def test_l1_enrich_source_exists(self):
        """L1: pkg/enrich/enrich.go exists and is non-empty."""
        p = os.path.join(ENRICH_PKG, "enrich.go")
        assert os.path.isfile(p), f"missing {p}"
        assert os.path.getsize(p) > 0, "enrich.go is empty"

    def test_l1_enrich_test_exists(self):
        """L1: pkg/enrich/enrich_test.go exists (agent's own tests)."""
        p = os.path.join(ENRICH_PKG, "enrich_test.go")
        assert os.path.isfile(p), f"missing {p}"
        assert os.path.getsize(p) > 0, "enrich_test.go is empty"

    def test_l1_go_mod_unmodified_module_path(self):
        """L1: still the samber/hot module and Go 1.22+ (no new third-party deps)."""
        gomod = os.path.join(REPO_DIR, "go.mod")
        with open(gomod) as fh:
            text = fh.read()
        assert "module github.com/samber/hot" in text
        import re
        m = re.search(r"^go\s+(\d+)\.(\d+)", text, re.MULTILINE)
        assert m, "no go directive in go.mod"
        major, minor = int(m.group(1)), int(m.group(2))
        assert (major, minor) >= (1, 22), f"go {major}.{minor} < 1.22"

    def test_l1_build_whole_module(self):
        """L1: `go build ./...` succeeds with the new enrich package present."""
        res = _run_go(["build", "./..."], timeout=400)
        assert res.returncode == 0, (
            "go build ./... failed:\n" + res.stdout + res.stderr
        )

    def test_l1_vet_enrich_package(self):
        """L1: `go vet` of the enrich package is clean (well-formed Go)."""
        res = _run_go(["vet", "./pkg/enrich/"], timeout=300)
        assert res.returncode == 0, (
            "go vet ./pkg/enrich/ failed:\n" + res.stdout + res.stderr
        )

    def test_l1_public_api_surface_compiles(self):
        """L1: the exact required public API (Profile fields, Source interface,
        NewEnricher, Enrich's (found, missing, err) signature, Close) compiles
        when referenced from an independent package."""
        body = PROBE_HEADER + textwrap.dedent(
            """
            func TestAPISurface(t *testing.T) {
                var _ enrich.Source = newCountingSource()
                p := enrich.Profile{ID: "x", DisplayName: "n"}
                _ = p.ID
                _ = p.DisplayName
                s := newCountingSource()
                e := enrich.NewEnricher(s, 8, time.Second)
                var found map[string]*enrich.Profile
                var missing []string
                var err error
                found, missing, err = e.Enrich([]string{"x"})
                _ = found
                _ = missing
                _ = err
                e.Close()
            }
            """
        )
        res = _run_probe("api_surface_test.go", body, run="TestAPISurface")
        assert res.returncode == 0, (
            "API surface probe failed to compile/run:\n" + res.stdout + res.stderr
        )
        assert "PASS" in res.stdout, res.stdout + res.stderr

    def test_l1_agent_tests_run(self):
        """L1: the agent's own TestEnrich* tests pass (the doc's native
        acceptance command: go test ./pkg/enrich/ -run TestEnrich -count=1)."""
        res = _run_go(
            ["test", "./pkg/enrich/", "-run", "TestEnrich", "-count=1"],
            timeout=400,
        )
        assert res.returncode == 0, (
            "agent's own `go test ./pkg/enrich/ -run TestEnrich -count=1` failed:\n"
            + res.stdout + res.stderr
        )

    # -----------------------------------------------------------------------
    # L2 — independent behavioral probes via native `go test`
    # -----------------------------------------------------------------------

    def test_l2_found_missing_partition(self):
        """L2: a mixed batch of existing and non-existent ids returns the
        existing ones in `found` (with correct data) and the non-existent ones
        in `missing`; found-keys and missing together cover EXACTLY the
        requested ids (no extras, no omissions, no double-listing)."""
        body = PROBE_HEADER + textwrap.dedent(
            """
            func TestPartition(t *testing.T) {
                s := newCountingSource()
                s.put(&enrich.Profile{ID: "A", DisplayName: "Alice"})
                s.put(&enrich.Profile{ID: "B", DisplayName: "Bob"})
                // C and D do not exist.
                e := enrich.NewEnricher(s, 32, time.Minute)
                defer e.Close()

                req := []string{"A", "C", "B", "D"}
                found, missing, err := e.Enrich(req)
                if err != nil {
                    t.Fatalf("unexpected error: %v", err)
                }
                if len(found) != 2 {
                    t.Fatalf("want 2 found got %d (%v)", len(found), found)
                }
                if found["A"] == nil || found["A"].DisplayName != "Alice" {
                    t.Fatalf("A wrong: %+v", found["A"])
                }
                if found["B"] == nil || found["B"].DisplayName != "Bob" {
                    t.Fatalf("B wrong: %+v", found["B"])
                }
                if _, ok := found["C"]; ok {
                    t.Fatalf("non-existent C must not be in found")
                }
                ms := append([]string(nil), missing...)
                sort.Strings(ms)
                if len(ms) != 2 || ms[0] != "C" || ms[1] != "D" {
                    t.Fatalf("want missing={C,D} got %v", ms)
                }
                // Together they must cover exactly the requested set.
                cover := map[string]int{}
                for k := range found {
                    cover[k]++
                }
                for _, m := range missing {
                    cover[m]++
                }
                for _, id := range req {
                    if cover[id] != 1 {
                        t.Fatalf("id %s covered %d times (must be exactly once)", id, cover[id])
                    }
                }
                if len(cover) != 4 {
                    t.Fatalf("coverage set size want 4 got %d (%v)", len(cover), cover)
                }
            }
            """
        )
        res = _run_probe("partition_test.go", body, run="TestPartition")
        assert res.returncode == 0, res.stdout + res.stderr
        assert "PASS" in res.stdout, res.stdout + res.stderr

    def test_l2_no_refetch_of_resolved_ids(self):
        """L2: a second Enrich over an overlapping set forwards ONLY the
        genuinely-new ids to the source; ids resolved by the first call are not
        re-fetched. Each id ends up fetched exactly once in total."""
        body = PROBE_HEADER + textwrap.dedent(
            """
            func TestNoRefetch(t *testing.T) {
                s := newCountingSource()
                s.put(&enrich.Profile{ID: "A", DisplayName: "Alice"})
                s.put(&enrich.Profile{ID: "B", DisplayName: "Bob"})
                s.put(&enrich.Profile{ID: "C", DisplayName: "Carol"})
                e := enrich.NewEnricher(s, 32, time.Minute)
                defer e.Close()

                f1, m1, err1 := e.Enrich([]string{"A", "B"})
                if err1 != nil || len(f1) != 2 || len(m1) != 0 {
                    t.Fatalf("first: found=%d missing=%v err=%v", len(f1), m1, err1)
                }
                if s.batches() != 1 {
                    t.Fatalf("first call want 1 batch got %d", s.batches())
                }

                // Second call: A is already resolved, C is new. Only C must hit
                // the source.
                f2, m2, err2 := e.Enrich([]string{"A", "C"})
                if err2 != nil || len(f2) != 2 || len(m2) != 0 {
                    t.Fatalf("second: found=%d missing=%v err=%v", len(f2), m2, err2)
                }
                if f2["A"] == nil || f2["A"].DisplayName != "Alice" {
                    t.Fatalf("second call A wrong: %+v", f2["A"])
                }
                if f2["C"] == nil || f2["C"].DisplayName != "Carol" {
                    t.Fatalf("second call C wrong: %+v", f2["C"])
                }
                if a := s.count("A"); a != 1 {
                    t.Fatalf("A FETCHCOUNT want 1 got %d (resolved id was re-fetched)", a)
                }
                if c := s.count("C"); c != 1 {
                    t.Fatalf("C FETCHCOUNT want 1 got %d", c)
                }
                if b := s.count("B"); b != 1 {
                    t.Fatalf("B FETCHCOUNT want 1 got %d", b)
                }
            }
            """
        )
        res = _run_probe("norefetch_test.go", body, run="TestNoRefetch")
        assert res.returncode == 0, res.stdout + res.stderr
        assert "PASS" in res.stdout, res.stdout + res.stderr

    def test_l2_intra_batch_dedup(self):
        """L2: a single Enrich request containing the same id twice forwards
        that id to the source at most once within that batch."""
        body = PROBE_HEADER + textwrap.dedent(
            """
            func TestIntraDedup(t *testing.T) {
                s := newCountingSource()
                s.put(&enrich.Profile{ID: "A", DisplayName: "Alice"})
                s.put(&enrich.Profile{ID: "D", DisplayName: "Dave"})
                e := enrich.NewEnricher(s, 32, time.Minute)
                defer e.Close()

                found, missing, err := e.Enrich([]string{"A", "A", "D"})
                if err != nil {
                    t.Fatalf("unexpected error: %v", err)
                }
                if len(found) != 2 || found["A"] == nil || found["D"] == nil {
                    t.Fatalf("found wrong: %v", found)
                }
                if len(missing) != 0 {
                    t.Fatalf("want no missing got %v", missing)
                }
                if mi := s.maxIntra(); mi > 1 {
                    t.Fatalf("intra-batch dedup violated: an id was sent %d times in one FetchBatch", mi)
                }
                if a := s.count("A"); a != 1 {
                    t.Fatalf("A total FETCHCOUNT want 1 got %d (duplicate not coalesced)", a)
                }
            }
            """
        )
        res = _run_probe("intradedup_test.go", body, run="TestIntraDedup")
        assert res.returncode == 0, res.stdout + res.stderr
        assert "PASS" in res.stdout, res.stdout + res.stderr

    def test_l2_missing_negative_cached(self):
        """L2: a confirmed-missing id is remembered — re-requesting it does not
        hit the source again, and it stays in `missing` (no spurious refetch)."""
        body = PROBE_HEADER + textwrap.dedent(
            """
            func TestNegative(t *testing.T) {
                s := newCountingSource() // empty => Z missing
                e := enrich.NewEnricher(s, 32, time.Minute)
                defer e.Close()

                f1, m1, e1 := e.Enrich([]string{"Z"})
                if e1 != nil || len(f1) != 0 {
                    t.Fatalf("first: found=%v err=%v", f1, e1)
                }
                if len(m1) != 1 || m1[0] != "Z" {
                    t.Fatalf("first missing want {Z} got %v", m1)
                }
                f2, m2, e2 := e.Enrich([]string{"Z"})
                if e2 != nil || len(f2) != 0 {
                    t.Fatalf("second: found=%v err=%v", f2, e2)
                }
                if len(m2) != 1 || m2[0] != "Z" {
                    t.Fatalf("second missing want {Z} got %v", m2)
                }
                if z := s.count("Z"); z != 1 {
                    t.Fatalf("Z FETCHCOUNT want 1 got %d (missing id not negatively cached)", z)
                }
            }
            """
        )
        res = _run_probe("negative_test.go", body, run="TestNegative")
        assert res.returncode == 0, res.stdout + res.stderr
        assert "PASS" in res.stdout, res.stdout + res.stderr

    def test_l2_error_not_cached(self):
        """L2: an infrastructure error from the source is surfaced and NOT
        cached; a subsequent healthy Enrich for the same ids succeeds."""
        body = PROBE_HEADER + textwrap.dedent(
            """
            func TestErrorNotCached(t *testing.T) {
                s := newCountingSource()
                s.put(&enrich.Profile{ID: "G", DisplayName: "Gina"})
                s.failNextN = 1 // first FetchBatch errors
                e := enrich.NewEnricher(s, 32, time.Minute)
                defer e.Close()

                _, _, err1 := e.Enrich([]string{"G"})
                if err1 == nil {
                    t.Fatalf("expected infra error on first Enrich, got nil")
                }
                f2, m2, err2 := e.Enrich([]string{"G"})
                if err2 != nil {
                    t.Fatalf("second Enrich errored: %v (error was cached)", err2)
                }
                if len(m2) != 0 {
                    t.Fatalf("G must be found not missing after recovery: %v", m2)
                }
                if f2["G"] == nil || f2["G"].DisplayName != "Gina" {
                    t.Fatalf("second Enrich G wrong: %+v", f2["G"])
                }
                if g := s.count("G"); g < 2 {
                    t.Fatalf("G FETCHCOUNT want >=2 got %d (error must trigger a refetch)", g)
                }
            }
            """
        )
        res = _run_probe("errcache_test.go", body, run="TestErrorNotCached")
        assert res.returncode == 0, res.stdout + res.stderr
        assert "PASS" in res.stdout, res.stdout + res.stderr

    def test_l2_concurrent_overlap_single_fetch(self):
        """L2: >=50 concurrent Enrich calls whose batches all share the SAME
        previously-uncached id collapse that demand into a single fetch for the
        id; every goroutine observes it in `found`."""
        body = PROBE_HEADER + textwrap.dedent(
            """
            func TestConcurrentOverlap(t *testing.T) {
                s := newCountingSource()
                s.put(&enrich.Profile{ID: "E", DisplayName: "Eve"})
                s.blockCh = make(chan struct{}) // block FetchBatch until released
                e := enrich.NewEnricher(s, 256, time.Minute)
                defer e.Close()

                const N = 64
                var wg sync.WaitGroup
                var ok int32
                var bad int32
                ready := make(chan struct{}, N)
                wg.Add(N)
                for i := 0; i < N; i++ {
                    go func() {
                        defer wg.Done()
                        ready <- struct{}{}
                        f, _, err := e.Enrich([]string{"E"})
                        if err == nil && f["E"] != nil && f["E"].DisplayName == "Eve" {
                            atomic.AddInt32(&ok, 1)
                        } else {
                            atomic.AddInt32(&bad, 1)
                        }
                    }()
                }
                for i := 0; i < N; i++ {
                    <-ready
                }
                time.Sleep(60 * time.Millisecond) // let demand accumulate
                close(s.blockCh)
                wg.Wait()

                if b := atomic.LoadInt32(&bad); b != 0 {
                    t.Fatalf("%d goroutines got wrong/err result", b)
                }
                if o := atomic.LoadInt32(&ok); o != N {
                    t.Fatalf("want %d ok got %d", N, o)
                }
                if c := s.count("E"); c != 1 {
                    t.Fatalf("E FETCHCOUNT want 1 got %d (no shared-fetch coalescing)", c)
                }
            }
            """
        )
        res = _run_probe(
            "concurrent_test.go", body, run="TestConcurrentOverlap", timeout=300
        )
        assert res.returncode == 0, res.stdout + res.stderr
        assert "PASS" in res.stdout, res.stdout + res.stderr

    def test_l2_ttl_expiry_allows_refetch(self):
        """L2: after the ttl elapses for a previously-resolved id, a later
        Enrich containing that id consults the source again for it."""
        body = PROBE_HEADER + textwrap.dedent(
            """
            func TestTTLRefetch(t *testing.T) {
                s := newCountingSource()
                s.put(&enrich.Profile{ID: "T", DisplayName: "Tom"})
                e := enrich.NewEnricher(s, 32, 80*time.Millisecond)
                defer e.Close()

                if f, _, err := e.Enrich([]string{"T"}); err != nil || f["T"] == nil {
                    t.Fatalf("first: found=%v err=%v", f, err)
                }
                // within ttl -> served from memory, no new fetch
                if f, _, err := e.Enrich([]string{"T"}); err != nil || f["T"] == nil {
                    t.Fatalf("cached: found=%v err=%v", f, err)
                }
                if c := s.count("T"); c != 1 {
                    t.Fatalf("pre-expiry FETCHCOUNT want 1 got %d", c)
                }
                time.Sleep(200 * time.Millisecond) // exceed ttl
                if f, _, err := e.Enrich([]string{"T"}); err != nil || f["T"] == nil {
                    t.Fatalf("post-ttl: found=%v err=%v", f, err)
                }
                if c := s.count("T"); c < 2 {
                    t.Fatalf("post-expiry FETCHCOUNT want >=2 got %d (ttl not honored)", c)
                }
            }
            """
        )
        res = _run_probe("ttl_test.go", body, run="TestTTLRefetch")
        assert res.returncode == 0, res.stdout + res.stderr
        assert "PASS" in res.stdout, res.stdout + res.stderr

    def test_l2_capacity_bounded(self):
        """L2: resolving far more distinct ids than `capacity` keeps in-memory
        records bounded to ~capacity — an early id must have been evicted, so
        re-requesting it forces a fresh source fetch."""
        body = PROBE_HEADER + textwrap.dedent(
            """
            func TestCapacityBounded(t *testing.T) {
                const cap = 8
                s := newCountingSource()
                for i := 0; i < 1000; i++ {
                    id := "k" + strconv.Itoa(i)
                    s.put(&enrich.Profile{ID: id, DisplayName: id})
                }
                e := enrich.NewEnricher(s, cap, time.Minute)
                defer e.Close()

                for i := 0; i < 1000; i++ {
                    id := "k" + strconv.Itoa(i)
                    f, _, err := e.Enrich([]string{id})
                    if err != nil || f[id] == nil {
                        t.Fatalf("enrich %s found=%v err=%v", id, f, err)
                    }
                }
                before := s.count("k0")
                if f, _, err := e.Enrich([]string{"k0"}); err != nil || f["k0"] == nil {
                    t.Fatalf("re-enrich k0 found=%v err=%v", f, err)
                }
                after := s.count("k0")
                if after <= before {
                    t.Fatalf("k0 not evicted: fetch count stayed %d (unbounded growth)", after)
                }
            }
            """
        )
        res = _run_probe("cap_test.go", body, run="TestCapacityBounded")
        assert res.returncode == 0, res.stdout + res.stderr
        assert "PASS" in res.stdout, res.stdout + res.stderr

    def test_l2_distinct_ids_no_mixup(self):
        """L2: distinct ids resolve to their OWN profiles across repeated batches
        (no key mixups), and each distinct existing id is fetched exactly once."""
        body = PROBE_HEADER + textwrap.dedent(
            """
            func TestDistinct(t *testing.T) {
                s := newCountingSource()
                s.put(&enrich.Profile{ID: "P", DisplayName: "Pam"})
                s.put(&enrich.Profile{ID: "Q", DisplayName: "Quinn"})
                s.put(&enrich.Profile{ID: "R", DisplayName: "Rita"})
                e := enrich.NewEnricher(s, 32, time.Minute)
                defer e.Close()

                for round := 0; round < 3; round++ {
                    f, miss, err := e.Enrich([]string{"P", "Q", "R"})
                    if err != nil || len(miss) != 0 {
                        t.Fatalf("round %d: missing=%v err=%v", round, miss, err)
                    }
                    if f["P"] == nil || f["P"].DisplayName != "Pam" {
                        t.Fatalf("round %d: P mixup %+v", round, f["P"])
                    }
                    if f["Q"] == nil || f["Q"].DisplayName != "Quinn" {
                        t.Fatalf("round %d: Q mixup %+v", round, f["Q"])
                    }
                    if f["R"] == nil || f["R"].DisplayName != "Rita" {
                        t.Fatalf("round %d: R mixup %+v", round, f["R"])
                    }
                }
                if s.count("P") != 1 || s.count("Q") != 1 || s.count("R") != 1 {
                    t.Fatalf("FETCHCOUNT want P=Q=R=1 got P=%d Q=%d R=%d",
                        s.count("P"), s.count("Q"), s.count("R"))
                }
            }
            """
        )
        res = _run_probe("distinct_test.go", body, run="TestDistinct")
        assert res.returncode == 0, res.stdout + res.stderr
        assert "PASS" in res.stdout, res.stdout + res.stderr

    def test_l2_no_goroutine_leak_after_close(self):
        """L2: after Close(), goleak reports no leaked goroutines (the Enricher
        must release any background machinery it started)."""
        body = textwrap.dedent(
            """
            package enrichprobe

            import (
                "testing"
                "time"

                enrich "github.com/samber/hot/pkg/enrich"
                "go.uber.org/goleak"
            )

            type leakSource struct{}

            func (leakSource) FetchBatch(ids []string) (map[string]*enrich.Profile, error) {
                out := map[string]*enrich.Profile{}
                for _, id := range ids {
                    if id == "L" {
                        out[id] = &enrich.Profile{ID: "L", DisplayName: "Leo"}
                    }
                }
                return out, nil
            }

            func TestNoLeakAfterClose(t *testing.T) {
                func() {
                    e := enrich.NewEnricher(leakSource{}, 16, 20*time.Millisecond)
                    for i := 0; i < 5; i++ {
                        e.Enrich([]string{"L"})
                    }
                    e.Close()
                }()
                time.Sleep(100 * time.Millisecond) // let any janitor stop
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
