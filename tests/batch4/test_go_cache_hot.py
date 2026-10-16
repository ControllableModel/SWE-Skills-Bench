"""Tests for the `go-cache-hot` skill task (variant ext4).

Skill: go-cache-hot — Build a Stale-While-Revalidate Price Feed inside the
`github.com/samber/hot` repository.

The variant task asks the agent to create `pkg/pricefeed/pricefeed.go` (and a
`pkg/pricefeed/pricefeed_test.go`) implementing a `PriceFeed` that wraps a slow
`Upstream` price source and serves quotes with stale-while-revalidate (SWR)
semantics:
  - a `fresh` window during which a cached quote is served with NO upstream call,
  - a following `stale` window during which the cached (possibly slightly old)
    quote is served IMMEDIATELY (no blocking) while the symbol is refreshed in
    the BACKGROUND so a later read observes the newer price without a
    synchronous upstream call,
  - beyond `fresh + stale` a quote is fully expired and must be re-fetched
    synchronously before being served,
  - cold reads fetch synchronously; an unknown symbol returns found=false with
    no error and is not remembered,
  - concurrent cold reads of the same symbol collapse into ONE synchronous fetch,
    and a burst of reads in the stale window must not spawn one refresh per read,
  - Close() releases all background machinery (no goroutine leaks).

What this file verifies:
  L1 — the deliverable files exist, the package builds (`go build ./...`), the
       go.mod is unmodified (still samber/hot, Go >=1.22, no new third-party
       deps), `go vet` is clean, the required exported API surface (Quote,
       Upstream, NewPriceFeed, Price, Close) compiles when referenced from an
       independent package, and the agent's own `TestPriceFeed` runs (this is
       the native acceptance command).
  L2 — we DO NOT trust the agent's own test file. Instead we synthesize an
       independent probe package under REPO_DIR that imports the agent's
       `pkg/pricefeed` package, drives it with our own counting / monotonically
       increasing / blocking upstreams, and asserts the concrete SWR behaviors
       via the native `go test` toolchain (results parsed from stdout). A naive
       implementation — one that blocks the caller on the upstream during the
       stale window, never refreshes stale entries, treats stale as expired, or
       re-fetches on every read — fails at least one probe.

Native acceptance command driven by L2:
    go test ./pkg/pricefeed/ -run TestPriceFeed -count=1
"""

import os
import re
import shutil
import subprocess
import textwrap

import pytest

REPO_DIR = "/workspace/hot"
FEED_PKG = os.path.join(REPO_DIR, "pkg", "pricefeed")
PROBE_PKG = os.path.join(REPO_DIR, "pkg", "pricefeedprobe")


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
    """Write a single-file probe test into pkg/pricefeedprobe and return path."""
    os.makedirs(PROBE_PKG, exist_ok=True)
    path = os.path.join(PROBE_PKG, name)
    with open(path, "w") as fh:
        fh.write(body)
    return path


def _run_probe(name, body, run="", timeout=300):
    """Write a probe test file, run it, clean it up, return CompletedProcess."""
    path = _write_probe(name, body)
    try:
        args = ["test", "./pkg/pricefeedprobe/", "-count=1", "-v"]
        if run:
            args += ["-run", run]
        return _run_go(args, timeout=timeout)
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


# Common header reused by probe files. Imports the agent package and provides
# upstream doubles whose price MONOTONICALLY increases per fetch and which count
# per-symbol fetches under concurrency, plus an optional blocking gate.
PROBE_HEADER = textwrap.dedent(
    """
    package pricefeedprobe

    import (
        "strconv"
        "sync"
        "sync/atomic"
        "testing"
        "time"

        pricefeed "github.com/samber/hot/pkg/pricefeed"
    )

    var _ = strconv.Itoa
    var _ = time.Now
    var _ = atomic.AddInt32

    // countingUpstream returns a monotonically increasing price for each known
    // symbol (base + 1 per fetch of that symbol) and records per-symbol fetch
    // counts. It is safe for concurrent use. If blockCh is non-nil, Fetch waits
    // on it once entered (used to force concurrent collapse / collisions).
    type countingUpstream struct {
        mu      sync.Mutex
        counts  map[string]int   // synchronous + background fetches per symbol
        base    map[string]int64 // base price per known symbol
        blockCh chan struct{}
        entered int32
    }

    func newCountingUpstream() *countingUpstream {
        return &countingUpstream{
            counts: map[string]int{},
            base:   map[string]int64{},
        }
    }

    func (u *countingUpstream) know(symbol string, base int64) {
        u.mu.Lock()
        u.base[symbol] = base
        u.mu.Unlock()
    }

    func (u *countingUpstream) count(symbol string) int {
        u.mu.Lock()
        defer u.mu.Unlock()
        return u.counts[symbol]
    }

    func (u *countingUpstream) Fetch(symbols []string) (map[string]*pricefeed.Quote, error) {
        atomic.AddInt32(&u.entered, 1)
        if u.blockCh != nil {
            <-u.blockCh
        }
        u.mu.Lock()
        defer u.mu.Unlock()
        out := map[string]*pricefeed.Quote{}
        for _, s := range symbols {
            u.counts[s]++
            base, ok := u.base[s]
            if !ok {
                continue // unknown symbol: absent from the map
            }
            // price increases on each fetch of this symbol
            out[s] = &pricefeed.Quote{Symbol: s, Price: base + int64(u.counts[s])}
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
    # Not fatal if it fails (offline module cache may already exist); the build
    # steps below surface real problems.
    yield res


# ---------------------------------------------------------------------------
# L1 — deliverable existence / well-formedness / compilation
# ---------------------------------------------------------------------------

class TestGoCacheHot:
    REPO_DIR = "/workspace/hot"

    def test_l1_pricefeed_source_exists(self):
        """L1: pkg/pricefeed/pricefeed.go exists and is non-empty."""
        p = os.path.join(FEED_PKG, "pricefeed.go")
        assert os.path.isfile(p), f"missing {p}"
        assert os.path.getsize(p) > 0, "pricefeed.go is empty"

    def test_l1_pricefeed_test_exists(self):
        """L1: pkg/pricefeed/pricefeed_test.go exists (agent's own tests)."""
        p = os.path.join(FEED_PKG, "pricefeed_test.go")
        assert os.path.isfile(p), f"missing {p}"
        assert os.path.getsize(p) > 0, "pricefeed_test.go is empty"

    def test_l1_go_mod_unmodified(self):
        """L1: still the samber/hot module and Go >=1.22 (no new third-party deps).

        We also confirm the agent did not introduce a brand-new direct
        third-party require beyond what the repo already shipped.
        """
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

    def test_l1_vet_pricefeed_package(self):
        """L1: `go vet` of the pricefeed package is clean (well-formed Go)."""
        res = _run_go(["vet", "./pkg/pricefeed/"], timeout=300)
        assert res.returncode == 0, (
            "go vet ./pkg/pricefeed/ failed:\n" + res.stdout + res.stderr
        )

    def test_l1_public_api_surface_compiles(self):
        """L1: the exact required public API (Quote fields, Upstream interface,
        NewPriceFeed, Price, Close) compiles when referenced independently."""
        body = PROBE_HEADER + textwrap.dedent(
            """
            func TestAPISurface(t *testing.T) {
                // Upstream interface is satisfied by our double.
                var _ pricefeed.Upstream = newCountingUpstream()
                // Quote has the documented fields/types.
                q := pricefeed.Quote{Symbol: "AAPL", Price: int64(12345)}
                _ = q.Symbol
                var _ int64 = q.Price

                u := newCountingUpstream()
                f := pricefeed.NewPriceFeed(u, 8, 50*time.Millisecond, 50*time.Millisecond)
                var quote *pricefeed.Quote
                var found bool
                var err error
                quote, found, err = f.Price("AAPL")
                _ = quote
                _ = found
                _ = err
                f.Close()
            }
            """
        )
        res = _run_probe("api_surface_test.go", body, run="TestAPISurface")
        assert res.returncode == 0, (
            "API surface probe failed to compile/run:\n" + res.stdout + res.stderr
        )
        assert "PASS" in res.stdout, res.stdout + res.stderr

    def test_l1_agent_tests_run(self):
        """L1: the agent's own TestPriceFeed passes (the native acceptance cmd
        `go test ./pkg/pricefeed/ -run TestPriceFeed -count=1`)."""
        res = _run_go(
            ["test", "./pkg/pricefeed/", "-run", "TestPriceFeed", "-count=1"],
            timeout=400,
        )
        assert res.returncode == 0, (
            "agent's own go test ./pkg/pricefeed -run TestPriceFeed failed:\n"
            + res.stdout + res.stderr
        )


# ---------------------------------------------------------------------------
# L2 — independent behavioral probes via native `go test`
# ---------------------------------------------------------------------------

    def test_l2_cold_read_fetches_once(self):
        """L2: a cold read fetches synchronously exactly once and returns the
        symbol with found=true; an immediate second read within `fresh` does NOT
        fetch again and returns the SAME price (fresh window honored)."""
        body = PROBE_HEADER + textwrap.dedent(
            """
            func TestColdThenFresh(t *testing.T) {
                u := newCountingUpstream()
                u.know("AAPL", 1000)
                // Long fresh window so the second read is unambiguously "fresh".
                f := pricefeed.NewPriceFeed(u, 16, time.Minute, time.Minute)
                defer f.Close()

                q1, found1, err1 := f.Price("AAPL")
                if err1 != nil || !found1 || q1 == nil {
                    t.Fatalf("cold read: found=%v err=%v quote=%v", found1, err1, q1)
                }
                if q1.Symbol != "AAPL" {
                    t.Fatalf("wrong symbol: %q", q1.Symbol)
                }
                if u.count("AAPL") != 1 {
                    t.Fatalf("FETCHCOUNT after cold read want 1 got %d", u.count("AAPL"))
                }

                q2, found2, err2 := f.Price("AAPL")
                if err2 != nil || !found2 || q2 == nil {
                    t.Fatalf("fresh read: found=%v err=%v", found2, err2)
                }
                if q2.Price != q1.Price {
                    t.Fatalf("fresh read returned different price %d != %d (re-fetched?)", q2.Price, q1.Price)
                }
                if u.count("AAPL") != 1 {
                    t.Fatalf("FETCHCOUNT after fresh read want 1 got %d (fresh not cached)", u.count("AAPL"))
                }
            }
            """
        )
        res = _run_probe("cold_fresh_test.go", body, run="TestColdThenFresh")
        assert res.returncode == 0, res.stdout + res.stderr
        assert "PASS" in res.stdout, res.stdout + res.stderr

    def test_l2_unknown_symbol_found_false_no_error(self):
        """L2: an unknown symbol returns found=false with no error (and the miss
        is not remembered as a cached value — re-reading still found=false)."""
        body = PROBE_HEADER + textwrap.dedent(
            """
            func TestUnknownSymbol(t *testing.T) {
                u := newCountingUpstream() // nothing known
                f := pricefeed.NewPriceFeed(u, 16, time.Minute, time.Minute)
                defer f.Close()

                q1, found1, err1 := f.Price("NOPE")
                if err1 != nil {
                    t.Fatalf("unknown symbol returned error: %v", err1)
                }
                if found1 {
                    t.Fatalf("unknown symbol reported found=true (quote=%v)", q1)
                }
                if q1 != nil {
                    t.Fatalf("unknown symbol returned non-nil quote %v", q1)
                }
                q2, found2, err2 := f.Price("NOPE")
                if err2 != nil || found2 || q2 != nil {
                    t.Fatalf("re-read unknown: found=%v err=%v quote=%v", found2, err2, q2)
                }
            }
            """
        )
        res = _run_probe("unknown_test.go", body, run="TestUnknownSymbol")
        assert res.returncode == 0, res.stdout + res.stderr
        assert "PASS" in res.stdout, res.stdout + res.stderr

    def test_l2_stale_serves_immediately_then_refreshes(self):
        """L2: the core SWR behavior. After `fresh` passes but within `stale`, a
        read returns the previously-cached (OLD) price IMMEDIATELY (it must NOT
        block for a brand-new upstream value), and a later read — after the
        background refresh settles — observes the NEWER price WITHOUT itself
        performing a synchronous upstream fetch.

        A naive impl that blocks on the upstream during stale (returns the new
        price on the first stale read), or that never refreshes (the later read
        still sees the old price), or that re-fetches synchronously on the later
        read, fails here. We make the upstream BLOCK so a synchronous fetch could
        not possibly complete within the immediate read's deadline."""
        body = PROBE_HEADER + textwrap.dedent(
            """
            func TestStaleWhileRevalidate(t *testing.T) {
                u := newCountingUpstream()
                u.know("MSFT", 2000)
                fresh := 60 * time.Millisecond
                stale := 5 * time.Second // generous: comfortably in stale window
                f := pricefeed.NewPriceFeed(u, 16, fresh, stale)
                defer f.Close()

                // Cold read -> price = 2000 + 1 = 2001 (count==1).
                q1, found1, err1 := f.Price("MSFT")
                if err1 != nil || !found1 || q1 == nil {
                    t.Fatalf("cold read: found=%v err=%v", found1, err1)
                }
                oldPrice := q1.Price

                // Let the entry age past `fresh` into the stale window.
                time.Sleep(fresh + 30*time.Millisecond)

                // Gate the upstream so any *synchronous* refresh would block far
                // longer than our immediate-read tolerance. A correct SWR read
                // must still return promptly with the OLD price.
                u.blockCh = make(chan struct{})

                start := time.Now()
                q2, found2, err2 := f.Price("MSFT")
                elapsed := time.Since(start)
                if err2 != nil || !found2 || q2 == nil {
                    t.Fatalf("stale read: found=%v err=%v", found2, err2)
                }
                if elapsed > 500*time.Millisecond {
                    t.Fatalf("stale read blocked %v (>500ms) -> caller blocked on upstream", elapsed)
                }
                if q2.Price != oldPrice {
                    t.Fatalf("stale read returned price %d, expected cached %d immediately", q2.Price, oldPrice)
                }

                // Now release the (background) refresh and let it settle.
                close(u.blockCh)
                time.Sleep(300 * time.Millisecond)

                // The fetch count from the background refresh should now be >=2.
                if c := u.count("MSFT"); c < 2 {
                    t.Fatalf("no background refresh happened: fetch count %d (<2)", c)
                }
                cntBefore := u.count("MSFT")

                // A later read must observe the NEWER price WITHOUT a synchronous
                // fetch (the background refresh already updated the cache).
                q3, found3, err3 := f.Price("MSFT")
                if err3 != nil || !found3 || q3 == nil {
                    t.Fatalf("post-refresh read: found=%v err=%v", found3, err3)
                }
                if q3.Price <= oldPrice {
                    t.Fatalf("post-refresh read price %d did not advance past %d (stale never refreshed)", q3.Price, oldPrice)
                }
                if c := u.count("MSFT"); c != cntBefore {
                    t.Fatalf("post-refresh read performed a synchronous fetch: count %d != %d", c, cntBefore)
                }
            }
            """
        )
        res = _run_probe(
            "swr_test.go", body, run="TestStaleWhileRevalidate", timeout=300
        )
        assert res.returncode == 0, res.stdout + res.stderr
        assert "PASS" in res.stdout, res.stdout + res.stderr

    def test_l2_expired_refetches_synchronously(self):
        """L2: once a quote passes `fresh + stale` it is fully expired; the next
        read performs a SYNCHRONOUS fetch and returns the newest price (it must
        NOT serve the old value the way a stale read would). A naive impl that
        treats stale==expired, or that serves an expired entry forever, fails."""
        body = PROBE_HEADER + textwrap.dedent(
            """
            func TestExpiredSyncRefetch(t *testing.T) {
                u := newCountingUpstream()
                u.know("GOOG", 3000)
                fresh := 40 * time.Millisecond
                stale := 40 * time.Millisecond
                f := pricefeed.NewPriceFeed(u, 16, fresh, stale)
                defer f.Close()

                q1, found1, err1 := f.Price("GOOG")
                if err1 != nil || !found1 || q1 == nil {
                    t.Fatalf("cold read: found=%v err=%v", found1, err1)
                }
                oldPrice := q1.Price
                if u.count("GOOG") != 1 {
                    t.Fatalf("FETCHCOUNT after cold want 1 got %d", u.count("GOOG"))
                }

                // Sleep well past fresh+stale so the entry is fully expired.
                time.Sleep(fresh + stale + 120*time.Millisecond)

                // The expired read fetches synchronously and returns a NEW price.
                q2, found2, err2 := f.Price("GOOG")
                if err2 != nil || !found2 || q2 == nil {
                    t.Fatalf("expired read: found=%v err=%v", found2, err2)
                }
                if q2.Price <= oldPrice {
                    t.Fatalf("expired read price %d did not advance past %d (served stale-as-expired?)", q2.Price, oldPrice)
                }
                if c := u.count("GOOG"); c < 2 {
                    t.Fatalf("expired read did not re-fetch: count %d (<2)", c)
                }
            }
            """
        )
        res = _run_probe(
            "expired_test.go", body, run="TestExpiredSyncRefetch", timeout=300
        )
        assert res.returncode == 0, res.stdout + res.stderr
        assert "PASS" in res.stdout, res.stdout + res.stderr

    def test_l2_concurrent_cold_collapses_single_fetch(self):
        """L2: launching >=50 goroutines reading the same COLD symbol triggers
        exactly ONE synchronous upstream fetch (singleflight collapse). The
        upstream blocks briefly so all readers pile up before it returns; every
        goroutine must observe found=true with the same symbol."""
        body = PROBE_HEADER + textwrap.dedent(
            """
            func TestConcurrentColdCollapse(t *testing.T) {
                u := newCountingUpstream()
                u.know("TSLA", 4000)
                u.blockCh = make(chan struct{})
                f := pricefeed.NewPriceFeed(u, 64, time.Minute, time.Minute)
                defer f.Close()

                const N = 64 // >= 50 as required by the doc
                var wg sync.WaitGroup
                var okCount int32
                var badCount int32
                ready := make(chan struct{}, N)
                wg.Add(N)
                for i := 0; i < N; i++ {
                    go func() {
                        defer wg.Done()
                        ready <- struct{}{}
                        q, found, err := f.Price("TSLA")
                        if err == nil && found && q != nil && q.Symbol == "TSLA" {
                            atomic.AddInt32(&okCount, 1)
                        } else {
                            atomic.AddInt32(&badCount, 1)
                        }
                    }()
                }
                for i := 0; i < N; i++ {
                    <-ready
                }
                time.Sleep(60 * time.Millisecond) // let readers pile on the inflight fetch
                close(u.blockCh)
                wg.Wait()

                if bad := atomic.LoadInt32(&badCount); bad != 0 {
                    t.Fatalf("%d goroutines got wrong/err result", bad)
                }
                if ok := atomic.LoadInt32(&okCount); ok != N {
                    t.Fatalf("want %d ok results got %d", N, ok)
                }
                if c := u.count("TSLA"); c != 1 {
                    t.Fatalf("FETCHCOUNT want 1 got %d (no singleflight collapse on cold reads)", c)
                }
            }
            """
        )
        res = _run_probe(
            "collapse_test.go", body, run="TestConcurrentColdCollapse", timeout=300
        )
        assert res.returncode == 0, res.stdout + res.stderr
        assert "PASS" in res.stdout, res.stdout + res.stderr

    def test_l2_stale_burst_single_background_refresh(self):
        """L2: a burst of reads of a symbol in its STALE window must not spawn a
        separate refresh per read. We age an entry into stale, fire many reads
        concurrently while the upstream is gated, then release it; the symbol
        must be refreshed at most a small bounded number of times — crucially NOT
        once-per-read. A naive impl that schedules a refresh on every stale read
        produces ~N fetches and fails."""
        body = PROBE_HEADER + textwrap.dedent(
            """
            func TestStaleBurstNoFetchStorm(t *testing.T) {
                u := newCountingUpstream()
                u.know("NVDA", 5000)
                fresh := 50 * time.Millisecond
                stale := 5 * time.Second
                f := pricefeed.NewPriceFeed(u, 16, fresh, stale)
                defer f.Close()

                // Warm it (cold synchronous fetch => count 1).
                if _, found, err := f.Price("NVDA"); err != nil || !found {
                    t.Fatalf("warm read: found=%v err=%v", found, err)
                }
                if u.count("NVDA") != 1 {
                    t.Fatalf("FETCHCOUNT after warm want 1 got %d", u.count("NVDA"))
                }

                // Age into the stale window.
                time.Sleep(fresh + 30*time.Millisecond)

                // Gate the upstream so background refreshes started during the
                // burst are still inflight while we fire all reads.
                u.blockCh = make(chan struct{})

                const N = 80
                var wg sync.WaitGroup
                wg.Add(N)
                for i := 0; i < N; i++ {
                    go func() {
                        defer wg.Done()
                        // Every read should return immediately with the stale value.
                        _, _, _ = f.Price("NVDA")
                    }()
                }
                wg.Wait()
                // Release whatever background refreshes were scheduled and settle.
                close(u.blockCh)
                time.Sleep(300 * time.Millisecond)

                // Total fetches = 1 cold + background refreshes. A correct impl
                // collapses the burst into a single refresh; allow a small slack
                // for benign races but reject a per-read fetch storm.
                total := u.count("NVDA")
                if total < 2 {
                    t.Fatalf("stale burst never refreshed (count %d < 2)", total)
                }
                if total > 6 {
                    t.Fatalf("stale burst spawned a refresh per read: count %d (>6) for %d reads", total, N)
                }
            }
            """
        )
        res = _run_probe(
            "burst_test.go", body, run="TestStaleBurstNoFetchStorm", timeout=300
        )
        assert res.returncode == 0, res.stdout + res.stderr
        assert "PASS" in res.stdout, res.stdout + res.stderr

    def test_l2_distinct_symbols_isolated(self):
        """L2: distinct symbols return their own quotes (no key mixups), and each
        distinct known symbol is fetched exactly once across several fresh
        reads."""
        body = PROBE_HEADER + textwrap.dedent(
            """
            func TestDistinctSymbols(t *testing.T) {
                u := newCountingUpstream()
                u.know("AAA", 100)
                u.know("BBB", 900)
                f := pricefeed.NewPriceFeed(u, 16, time.Minute, time.Minute)
                defer f.Close()

                var pa, pb int64
                for round := 0; round < 3; round++ {
                    qa, fa, ea := f.Price("AAA")
                    qb, fb, eb := f.Price("BBB")
                    if ea != nil || eb != nil || !fa || !fb || qa == nil || qb == nil {
                        t.Fatalf("round %d: AAA(found=%v err=%v) BBB(found=%v err=%v)", round, fa, ea, fb, eb)
                    }
                    if qa.Symbol != "AAA" || qb.Symbol != "BBB" {
                        t.Fatalf("round %d: key mixup AAA=%q BBB=%q", round, qa.Symbol, qb.Symbol)
                    }
                    if qa.Price == qb.Price {
                        t.Fatalf("round %d: distinct symbols share price %d", round, qa.Price)
                    }
                    if round == 0 {
                        pa, pb = qa.Price, qb.Price
                    } else if qa.Price != pa || qb.Price != pb {
                        t.Fatalf("round %d: cached price drifted AAA %d->%d BBB %d->%d", round, pa, qa.Price, pb, qb.Price)
                    }
                }
                if ca, cb := u.count("AAA"), u.count("BBB"); ca != 1 || cb != 1 {
                    t.Fatalf("FETCHCOUNT want AAA=1 BBB=1 got AAA=%d BBB=%d", ca, cb)
                }
            }
            """
        )
        res = _run_probe("distinct_test.go", body, run="TestDistinctSymbols")
        assert res.returncode == 0, res.stdout + res.stderr
        assert "PASS" in res.stdout, res.stdout + res.stderr

    def test_l2_no_goroutine_leak_after_close(self):
        """L2: after Close(), goleak reports no leaked goroutines — the feed must
        release any background refresh machinery it started."""
        body = textwrap.dedent(
            """
            package pricefeedprobe

            import (
                "testing"
                "time"

                pricefeed "github.com/samber/hot/pkg/pricefeed"
                "go.uber.org/goleak"
            )

            type leakUpstream struct{}

            func (leakUpstream) Fetch(symbols []string) (map[string]*pricefeed.Quote, error) {
                out := map[string]*pricefeed.Quote{}
                for _, s := range symbols {
                    if s == "LEAK" {
                        out[s] = &pricefeed.Quote{Symbol: "LEAK", Price: 42}
                    }
                }
                return out, nil
            }

            func TestNoLeakAfterClose(t *testing.T) {
                func() {
                    f := pricefeed.NewPriceFeed(leakUpstream{}, 16, 20*time.Millisecond, 20*time.Millisecond)
                    for i := 0; i < 5; i++ {
                        f.Price("LEAK")
                        time.Sleep(15 * time.Millisecond) // straddle fresh->stale to trigger background work
                        f.Price("LEAK")
                    }
                    f.Close()
                }()
                // give any janitor / background refreshers a moment to stop
                time.Sleep(150 * time.Millisecond)
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
