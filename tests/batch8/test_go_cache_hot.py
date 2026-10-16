"""Tests for the `go-cache-hot` skill task (variant ext8).

Skill: go-cache-hot — Build a Pre-Warmed Country Catalog inside the
`github.com/samber/hot` repository.

The ext8 task asks the agent to create `pkg/catalog/catalog.go` (and a
`catalog_test.go`) implementing a `Catalog` that wraps the `hot` cache to serve
a small fixed reference dataset of countries. Key behaviors:
  - the catalog PRE-POPULATES itself from a `Bootstrap` during construction, so
    every bootstrap code is already resident before the first `Lookup` (a code
    in the bootstrap set is served from memory and never hits `loader.Load`),
  - a code absent from the bootstrap set falls back to `loader.Load`, then is
    cached; a re-lookup within `ttl` does not call `loader.Load` again,
  - `(nil, false, nil)` for a code neither source knows,
  - `(nil, false, err)` on loader infra failure (failure is NOT remembered),
  - `NewCatalog` propagates a `Bootstrap` error and returns a nil catalog,
  - `Len()` / `Codes()` introspection reflect resident entries,
  - a burst of concurrent lookups of one uncached non-bootstrap code collapses
    into a single `loader.Load`,
  - `Close()` leaks no goroutines.

What this file verifies:
  L1 — the deliverable files exist, the whole module builds, the package vets
       clean, and the required exported API surface (Country, Bootstrap,
       Loader, NewCatalog, Lookup, Len, Codes, Close) compiles against an
       independent package; the agent's own TestCatalog tests run.
  L2 — we DO NOT trust the agent's own test file. We synthesize an independent
       probe package under REPO_DIR that imports the agent's `pkg/catalog`
       package, drives it with our own counting/blocking/failing loaders and
       fixed bootstraps, and asserts concrete behavior via the native `go test`
       toolchain. A naive implementation (lazy-loads bootstrap codes on first
       access instead of pre-populating, ignores a bootstrap error, re-loads on
       every lookup, never expires entries, or fails to dedup concurrent
       loads) fails at least one probe.

Native acceptance command driven by L2:
    go test ./pkg/catalog/ -run TestCatalog -count=1
(plus independent probes under ./pkg/catalogprobe/)
"""

import os
import re
import shutil
import subprocess
import textwrap

import pytest

REPO_DIR = "/workspace/hot"
CAT_PKG = os.path.join(REPO_DIR, "pkg", "catalog")
PROBE_PKG = os.path.join(REPO_DIR, "pkg", "catalogprobe")


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
    """Write a single-file probe test into pkg/catalogprobe and return path."""
    os.makedirs(PROBE_PKG, exist_ok=True)
    path = os.path.join(PROBE_PKG, name)
    with open(path, "w") as fh:
        fh.write(body)
    return path


def _run_probe(name, body, run="", timeout=300):
    """Write a probe test file, run it, clean it up, return CompletedProcess."""
    path = _write_probe(name, body)
    try:
        args = ["test", "./pkg/catalogprobe/", "-count=1", "-v"]
        if run:
            args += ["-run", run]
        return _run_go(args, timeout=timeout)
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


# Common header reused by probe files. Imports the agent package and defines a
# counting/blocking/failing Loader plus a fixed Bootstrap helper.
PROBE_HEADER = textwrap.dedent(
    """
    package catalogprobe

    import (
        "errors"
        "sort"
        "strconv"
        "sync"
        "sync/atomic"
        "testing"
        "time"

        catalog "github.com/samber/hot/pkg/catalog"
    )

    var _ = strconv.Itoa
    var _ = errors.New
    var _ = sort.Strings
    var _ = time.Now
    var _ = atomic.AddInt32

    // countingLoader records per-code Load counts and is concurrency safe. It
    // can optionally block (to force a concurrency window) and fail.
    type countingLoader struct {
        mu      sync.Mutex
        counts  map[string]int
        data    map[string]*catalog.Country
        failIDs map[string]int // remaining failures per code
        blockCh chan struct{}  // if non-nil, Load waits on it after entering
        entered int32
    }

    func newCountingLoader() *countingLoader {
        return &countingLoader{
            counts:  map[string]int{},
            data:    map[string]*catalog.Country{},
            failIDs: map[string]int{},
        }
    }

    func (l *countingLoader) put(c *catalog.Country) {
        l.mu.Lock()
        l.data[c.Code] = c
        l.mu.Unlock()
    }

    func (l *countingLoader) failNext(code string, n int) {
        l.mu.Lock()
        l.failIDs[code] = n
        l.mu.Unlock()
    }

    func (l *countingLoader) count(code string) int {
        l.mu.Lock()
        defer l.mu.Unlock()
        return l.counts[code]
    }

    func (l *countingLoader) Load(code string) (*catalog.Country, bool, error) {
        atomic.AddInt32(&l.entered, 1)
        if l.blockCh != nil {
            <-l.blockCh
        }
        l.mu.Lock()
        defer l.mu.Unlock()
        l.counts[code]++
        if rem, ok := l.failIDs[code]; ok && rem > 0 {
            l.failIDs[code] = rem - 1
            return nil, false, errors.New("infra failure for " + code)
        }
        if c, ok := l.data[code]; ok {
            cp := *c
            return &cp, true, nil
        }
        return nil, false, nil
    }

    // fixedBootstrap returns a Bootstrap closure yielding the given countries.
    func fixedBootstrap(cs ...*catalog.Country) catalog.Bootstrap {
        return func() (map[string]*catalog.Country, error) {
            m := map[string]*catalog.Country{}
            for _, c := range cs {
                cp := *c
                m[c.Code] = &cp
            }
            return m, nil
        }
    }

    func contains(ss []string, want string) bool {
        for _, s := range ss {
            if s == want {
                return true
            }
        }
        return false
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

    def test_l1_catalog_source_exists(self):
        """L1: pkg/catalog/catalog.go exists and is non-empty."""
        p = os.path.join(CAT_PKG, "catalog.go")
        assert os.path.isfile(p), f"missing {p}"
        assert os.path.getsize(p) > 0, "catalog.go is empty"

    def test_l1_catalog_test_exists(self):
        """L1: pkg/catalog/catalog_test.go exists (agent's own tests)."""
        p = os.path.join(CAT_PKG, "catalog_test.go")
        assert os.path.isfile(p), f"missing {p}"
        assert os.path.getsize(p) > 0, "catalog_test.go is empty"

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
        """L1: `go build ./...` succeeds with the new package present."""
        res = _run_go(["build", "./..."], timeout=400)
        assert res.returncode == 0, (
            "go build ./... failed:\n" + res.stdout + res.stderr
        )

    def test_l1_vet_catalog_package(self):
        """L1: `go vet` of the catalog package is clean (well-formed Go)."""
        res = _run_go(["vet", "./pkg/catalog/"], timeout=300)
        assert res.returncode == 0, (
            "go vet ./pkg/catalog/ failed:\n" + res.stdout + res.stderr
        )

    def test_l1_public_api_surface_compiles(self):
        """L1: the exact required public API (Country fields, Bootstrap, Loader,
        NewCatalog signature, Lookup, Len, Codes, Close) compiles when
        referenced from an independent package."""
        body = PROBE_HEADER + textwrap.dedent(
            """
            func TestAPISurface(t *testing.T) {
                // Loader interface is satisfied by our counting loader.
                var _ catalog.Loader = newCountingLoader()
                // Country fields.
                c := catalog.Country{Code: "US", Name: "United States"}
                _ = c.Code
                _ = c.Name
                // Bootstrap is a func type with the documented signature.
                var boot catalog.Bootstrap = fixedBootstrap(&catalog.Country{Code: "US", Name: "United States"})
                cat, err := catalog.NewCatalog(boot, newCountingLoader(), 16, time.Minute)
                if err != nil || cat == nil {
                    t.Fatalf("NewCatalog err=%v cat=%v", err, cat)
                }
                var rec *catalog.Country
                var found bool
                rec, found, err = cat.Lookup("US")
                _ = rec
                _ = found
                _ = err
                _ = cat.Len()
                _ = cat.Codes()
                cat.Close()
            }
            """
        )
        res = _run_probe("api_surface_test.go", body, run="TestAPISurface")
        assert res.returncode == 0, (
            "API surface probe failed to compile/run:\n" + res.stdout + res.stderr
        )
        assert "PASS" in res.stdout, res.stdout + res.stderr

    def test_l1_agent_tests_run(self):
        """L1: the agent's own TestCatalog* tests pass (native acceptance cmd)."""
        res = _run_go(
            ["test", "./pkg/catalog/", "-run", "TestCatalog", "-count=1"],
            timeout=400,
        )
        assert res.returncode == 0, (
            "agent's own go test ./pkg/catalog -run TestCatalog failed:\n"
            + res.stdout + res.stderr
        )

# ---------------------------------------------------------------------------
# L2 — independent behavioral probes via native `go test`
# ---------------------------------------------------------------------------

    def test_l2_bootstrap_prepopulated_codes_and_len(self):
        """L2: immediately after NewCatalog, Codes() contains every bootstrap
        code and Len() >= bootstrap size — proving WARM-UP populated the cache
        (a lazy implementation that only loads on first access fails)."""
        body = PROBE_HEADER + textwrap.dedent(
            """
            func TestBootstrapPrepopulated(t *testing.T) {
                ld := newCountingLoader()
                boot := fixedBootstrap(
                    &catalog.Country{Code: "US", Name: "United States"},
                    &catalog.Country{Code: "FR", Name: "France"},
                    &catalog.Country{Code: "JP", Name: "Japan"},
                )
                cat, err := catalog.NewCatalog(boot, ld, 64, time.Minute)
                if err != nil || cat == nil {
                    t.Fatalf("NewCatalog err=%v cat=%v", err, cat)
                }
                defer cat.Close()

                // No Lookup performed yet: residency must already exist.
                if n := cat.Len(); n < 3 {
                    t.Fatalf("Len() want >=3 got %d (bootstrap not pre-populated)", n)
                }
                codes := cat.Codes()
                for _, want := range []string{"US", "FR", "JP"} {
                    if !contains(codes, want) {
                        t.Fatalf("Codes()=%v missing bootstrap code %q", codes, want)
                    }
                }
                // The loader must NOT have been consulted during construction.
                if ent := atomic.LoadInt32(&ld.entered); ent != 0 {
                    t.Fatalf("loader.Load called %d times during construction (want 0)", ent)
                }
            }
            """
        )
        res = _run_probe("prepop_test.go", body, run="TestBootstrapPrepopulated")
        assert res.returncode == 0, res.stdout + res.stderr
        assert "PASS" in res.stdout, res.stdout + res.stderr

    def test_l2_bootstrap_code_served_from_memory(self):
        """L2: a bootstrap code's FIRST lookup returns it correctly while the
        loader's Load count for that code stays ZERO."""
        body = PROBE_HEADER + textwrap.dedent(
            """
            func TestBootstrapServedFromMemory(t *testing.T) {
                ld := newCountingLoader()
                boot := fixedBootstrap(&catalog.Country{Code: "DE", Name: "Germany"})
                cat, err := catalog.NewCatalog(boot, ld, 16, time.Minute)
                if err != nil {
                    t.Fatalf("NewCatalog err=%v", err)
                }
                defer cat.Close()

                rec, found, lerr := cat.Lookup("DE")
                if lerr != nil || !found || rec == nil {
                    t.Fatalf("first lookup: found=%v err=%v rec=%v", found, lerr, rec)
                }
                if rec.Code != "DE" || rec.Name != "Germany" {
                    t.Fatalf("wrong data: %+v", rec)
                }
                if got := ld.count("DE"); got != 0 {
                    t.Fatalf("loader.Load called %d times for bootstrap code (want 0)", got)
                }
            }
            """
        )
        res = _run_probe(
            "bootmem_test.go", body, run="TestBootstrapServedFromMemory"
        )
        assert res.returncode == 0, res.stdout + res.stderr
        assert "PASS" in res.stdout, res.stdout + res.stderr

    def test_l2_nonbootstrap_loaded_once_then_cached(self):
        """L2: a non-bootstrap existing code calls Load exactly once; an
        immediate second lookup within ttl does not call Load again."""
        body = PROBE_HEADER + textwrap.dedent(
            """
            func TestNonBootstrapCached(t *testing.T) {
                ld := newCountingLoader()
                ld.put(&catalog.Country{Code: "BR", Name: "Brazil"})
                boot := fixedBootstrap(&catalog.Country{Code: "US", Name: "United States"})
                cat, err := catalog.NewCatalog(boot, ld, 16, time.Minute)
                if err != nil {
                    t.Fatalf("NewCatalog err=%v", err)
                }
                defer cat.Close()

                r1, f1, e1 := cat.Lookup("BR")
                if e1 != nil || !f1 || r1 == nil || r1.Name != "Brazil" {
                    t.Fatalf("first lookup found=%v err=%v rec=%+v", f1, e1, r1)
                }
                r2, f2, e2 := cat.Lookup("BR")
                if e2 != nil || !f2 || r2 == nil || r2.Name != "Brazil" {
                    t.Fatalf("second lookup found=%v err=%v rec=%+v", f2, e2, r2)
                }
                if got := ld.count("BR"); got != 1 {
                    t.Fatalf("LOADCOUNT want 1 got %d (re-loads on every lookup?)", got)
                }
            }
            """
        )
        res = _run_probe("nonboot_test.go", body, run="TestNonBootstrapCached")
        assert res.returncode == 0, res.stdout + res.stderr
        assert "PASS" in res.stdout, res.stdout + res.stderr

    def test_l2_unknown_code_not_found_no_error(self):
        """L2: a code neither source knows returns (nil, false, nil)."""
        body = PROBE_HEADER + textwrap.dedent(
            """
            func TestUnknownCode(t *testing.T) {
                ld := newCountingLoader() // loader has no data
                boot := fixedBootstrap(&catalog.Country{Code: "US", Name: "United States"})
                cat, err := catalog.NewCatalog(boot, ld, 16, time.Minute)
                if err != nil {
                    t.Fatalf("NewCatalog err=%v", err)
                }
                defer cat.Close()

                rec, found, lerr := cat.Lookup("ZZ")
                if lerr != nil {
                    t.Fatalf("unknown code returned error %v (want nil)", lerr)
                }
                if found {
                    t.Fatalf("unknown code found=true (want false)")
                }
                if rec != nil {
                    t.Fatalf("unknown code rec=%+v (want nil)", rec)
                }
            }
            """
        )
        res = _run_probe("unknown_test.go", body, run="TestUnknownCode")
        assert res.returncode == 0, res.stdout + res.stderr
        assert "PASS" in res.stdout, res.stdout + res.stderr

    def test_l2_bootstrap_error_propagates_nil_catalog(self):
        """L2: a Bootstrap that returns an error makes NewCatalog return a
        non-nil error and a nil (unusable) catalog — ignoring the error fails."""
        body = PROBE_HEADER + textwrap.dedent(
            """
            func TestBootstrapErr(t *testing.T) {
                ld := newCountingLoader()
                boot := func() (map[string]*catalog.Country, error) {
                    return nil, errors.New("bootstrap exploded")
                }
                cat, err := catalog.NewCatalog(boot, ld, 16, time.Minute)
                if err == nil {
                    t.Fatalf("NewCatalog returned nil error on failing bootstrap")
                }
                if cat != nil {
                    t.Fatalf("NewCatalog returned a non-nil catalog (%v) on bootstrap error", cat)
                }
            }
            """
        )
        res = _run_probe("booterr_test.go", body, run="TestBootstrapErr")
        assert res.returncode == 0, res.stdout + res.stderr
        assert "PASS" in res.stdout, res.stdout + res.stderr

    def test_l2_loader_error_not_remembered(self):
        """L2: a loader infra failure surfaces (nil,false,err) and is NOT
        cached; a later healthy lookup for the same code succeeds."""
        body = PROBE_HEADER + textwrap.dedent(
            """
            func TestLoaderErrNotRemembered(t *testing.T) {
                ld := newCountingLoader()
                ld.put(&catalog.Country{Code: "IT", Name: "Italy"})
                ld.failNext("IT", 1) // first Load for IT fails
                boot := fixedBootstrap(&catalog.Country{Code: "US", Name: "United States"})
                cat, err := catalog.NewCatalog(boot, ld, 16, time.Minute)
                if err != nil {
                    t.Fatalf("NewCatalog err=%v", err)
                }
                defer cat.Close()

                rec, found, e1 := cat.Lookup("IT")
                if e1 == nil {
                    t.Fatalf("expected error on first lookup of IT, got nil (found=%v rec=%+v)", found, rec)
                }
                if found || rec != nil {
                    t.Fatalf("on error want (nil,false,err) got found=%v rec=%+v", found, rec)
                }
                r2, f2, e2 := cat.Lookup("IT")
                if e2 != nil {
                    t.Fatalf("second lookup errored: %v (failure was remembered)", e2)
                }
                if !f2 || r2 == nil || r2.Name != "Italy" {
                    t.Fatalf("second lookup found=%v rec=%+v", f2, r2)
                }
                if got := ld.count("IT"); got < 2 {
                    t.Fatalf("LOADCOUNT want >=2 got %d (failure must trigger refetch)", got)
                }
            }
            """
        )
        res = _run_probe(
            "loaderr_test.go", body, run="TestLoaderErrNotRemembered"
        )
        assert res.returncode == 0, res.stdout + res.stderr
        assert "PASS" in res.stdout, res.stdout + res.stderr

    def test_l2_concurrent_dedup_single_load(self):
        """L2: 50 concurrent lookups of the same uncached non-bootstrap code
        collapse into a single loader.Load (blocking Load forces the race)."""
        body = PROBE_HEADER + textwrap.dedent(
            """
            func TestConcurrentDedup(t *testing.T) {
                ld := newCountingLoader()
                ld.put(&catalog.Country{Code: "IN", Name: "India"})
                ld.blockCh = make(chan struct{})
                boot := fixedBootstrap(&catalog.Country{Code: "US", Name: "United States"})
                cat, err := catalog.NewCatalog(boot, ld, 64, time.Minute)
                if err != nil {
                    t.Fatalf("NewCatalog err=%v", err)
                }
                defer cat.Close()

                const N = 50
                var wg sync.WaitGroup
                var okCount int32
                var badCount int32
                ready := make(chan struct{}, N)
                wg.Add(N)
                for i := 0; i < N; i++ {
                    go func() {
                        defer wg.Done()
                        ready <- struct{}{}
                        r, f, e := cat.Lookup("IN")
                        if e == nil && f && r != nil && r.Name == "India" {
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
                close(ld.blockCh)
                wg.Wait()

                if bad := atomic.LoadInt32(&badCount); bad != 0 {
                    t.Fatalf("%d goroutines got wrong/err result", bad)
                }
                if ok := atomic.LoadInt32(&okCount); ok != N {
                    t.Fatalf("want %d ok results got %d", N, ok)
                }
                if got := ld.count("IN"); got != 1 {
                    t.Fatalf("LOADCOUNT want 1 got %d (no singleflight dedup)", got)
                }
            }
            """
        )
        res = _run_probe(
            "dedup_test.go", body, run="TestConcurrentDedup", timeout=300
        )
        assert res.returncode == 0, res.stdout + res.stderr
        assert "PASS" in res.stdout, res.stdout + res.stderr

    def test_l2_ttl_expiry_triggers_reload(self):
        """L2: after the ttl elapses, the next lookup of a non-bootstrap code
        consults the loader again (entries actually expire)."""
        body = PROBE_HEADER + textwrap.dedent(
            """
            func TestTTLExpiry(t *testing.T) {
                ld := newCountingLoader()
                ld.put(&catalog.Country{Code: "ES", Name: "Spain"})
                boot := fixedBootstrap(&catalog.Country{Code: "US", Name: "United States"})
                cat, err := catalog.NewCatalog(boot, ld, 16, 80*time.Millisecond)
                if err != nil {
                    t.Fatalf("NewCatalog err=%v", err)
                }
                defer cat.Close()

                if _, f, e := cat.Lookup("ES"); e != nil || !f {
                    t.Fatalf("first lookup found=%v err=%v", f, e)
                }
                if _, f, e := cat.Lookup("ES"); e != nil || !f { // within ttl => cached
                    t.Fatalf("cached lookup found=%v err=%v", f, e)
                }
                if got := ld.count("ES"); got != 1 {
                    t.Fatalf("LOADCOUNT before expiry want 1 got %d", got)
                }
                time.Sleep(200 * time.Millisecond) // exceed ttl
                if _, f, e := cat.Lookup("ES"); e != nil || !f {
                    t.Fatalf("post-ttl lookup found=%v err=%v", f, e)
                }
                if got := ld.count("ES"); got < 2 {
                    t.Fatalf("LOADCOUNT after expiry want >=2 got %d (ttl not honored)", got)
                }
            }
            """
        )
        res = _run_probe("ttl_test.go", body, run="TestTTLExpiry")
        assert res.returncode == 0, res.stdout + res.stderr
        assert "PASS" in res.stdout, res.stdout + res.stderr

    def test_l2_distinct_codes_isolated(self):
        """L2: distinct codes (bootstrap + loader) return their own records with
        no key mixups, and each distinct loader code is fetched exactly once."""
        body = PROBE_HEADER + textwrap.dedent(
            """
            func TestDistinctCodes(t *testing.T) {
                ld := newCountingLoader()
                ld.put(&catalog.Country{Code: "CA", Name: "Canada"})
                ld.put(&catalog.Country{Code: "MX", Name: "Mexico"})
                boot := fixedBootstrap(
                    &catalog.Country{Code: "US", Name: "United States"},
                    &catalog.Country{Code: "GB", Name: "United Kingdom"},
                )
                cat, err := catalog.NewCatalog(boot, ld, 32, time.Minute)
                if err != nil {
                    t.Fatalf("NewCatalog err=%v", err)
                }
                defer cat.Close()

                for round := 0; round < 3; round++ {
                    rus, fus, eus := cat.Lookup("US")
                    rca, fca, eca := cat.Lookup("CA")
                    rmx, fmx, emx := cat.Lookup("MX")
                    if eus != nil || eca != nil || emx != nil || !fus || !fca || !fmx {
                        t.Fatalf("round %d: US(f=%v e=%v) CA(f=%v e=%v) MX(f=%v e=%v)",
                            round, fus, eus, fca, eca, fmx, emx)
                    }
                    if rus.Name != "United States" || rca.Name != "Canada" || rmx.Name != "Mexico" {
                        t.Fatalf("round %d: key mixup US=%q CA=%q MX=%q",
                            round, rus.Name, rca.Name, rmx.Name)
                    }
                }
                // Bootstrap code never hits loader; each loader code loaded once.
                if got := ld.count("US"); got != 0 {
                    t.Fatalf("bootstrap US loaded %d times (want 0)", got)
                }
                if cca, cmx := ld.count("CA"), ld.count("MX"); cca != 1 || cmx != 1 {
                    t.Fatalf("LOADCOUNT want CA=1 MX=1 got CA=%d MX=%d", cca, cmx)
                }
            }
            """
        )
        res = _run_probe("distinct_test.go", body, run="TestDistinctCodes")
        assert res.returncode == 0, res.stdout + res.stderr
        assert "PASS" in res.stdout, res.stdout + res.stderr

    def test_l2_no_goroutine_leak_after_close(self):
        """L2: after Close(), goleak reports no leaked goroutines (the catalog
        must release any background janitor it started)."""
        body = textwrap.dedent(
            """
            package catalogprobe

            import (
                "testing"
                "time"

                catalog "github.com/samber/hot/pkg/catalog"
                "go.uber.org/goleak"
            )

            type leakLoader struct{}

            func (leakLoader) Load(code string) (*catalog.Country, bool, error) {
                if code == "NL" {
                    return &catalog.Country{Code: "NL", Name: "Netherlands"}, true, nil
                }
                return nil, false, nil
            }

            func TestNoLeakAfterClose(t *testing.T) {
                func() {
                    boot := func() (map[string]*catalog.Country, error) {
                        return map[string]*catalog.Country{
                            "US": {Code: "US", Name: "United States"},
                        }, nil
                    }
                    cat, err := catalog.NewCatalog(boot, leakLoader{}, 16, 20*time.Millisecond)
                    if err != nil {
                        t.Fatalf("NewCatalog err=%v", err)
                    }
                    for i := 0; i < 5; i++ {
                        cat.Lookup("NL")
                        cat.Lookup("US")
                    }
                    cat.Close()
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
