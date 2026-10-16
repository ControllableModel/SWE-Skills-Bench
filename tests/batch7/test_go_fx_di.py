"""Tests for the `go-fx-di` skill task (ext7 variant): a cache-optional service
example with a degraded fallback.

Skill under test: go-fx-di (uber-go/fx dependency injection — here exercising
*optional* dependencies and a degraded-mode fallback).

The task asks the agent to create a new `optcache` package under
`docs/ex/optcache/` inside the `go.uber.org/fx/docs` module. The package must
expose:

  * `Cache` (interface: `Get(key string) (string, bool)`, `Set(key, val string)`)
    and `NewMemoryCache` (concurrency-safe in-memory implementation);
  * `Lookup` (struct) with `Resolve(key string) string` and
    `CacheEnabled() bool`, plus a `NewLookup` constructor whose graph builds
    whether or not a `Cache` is present (optional dependency);
  * `Module` (`fx.Option`) — provides `Lookup` only (degraded, no cache);
  * `CacheModule` (`fx.Option`) — adds the `Cache`.

Behavioral contract:
  * boot `Module` alone        -> Resolve("k")      == "miss:k",      CacheEnabled() == false
  * boot Module + CacheModule, set k->v on cache:
        Resolve("k")           == "v",              CacheEnabled() == true
        Resolve("absent")      == "miss:absent"

Verification strategy: rather than trusting the agent's own
`optcache_test.go`, the L2 tests write INDEPENDENT Go driver test files into a
fresh sub-directory of the `optcache` package and run them with the native
`go test` toolchain (from the `docs` module). These drivers boot the real
`Module` / `CacheModule` via `fxtest`, populate `*Lookup` (and the `Cache`
interface), seed keys, and assert concrete return values. This means:

  * a naive `Resolve` that always returns "miss:"+key fails the cache-enabled
    value-return case;
  * a naive `Resolve` that always returns the cached value fails the
    absent-key / degraded cases;
  * a `Lookup` that hard-requires the cache fails the cache-absent boot with a
    missing-dependency error (asserted via fx.New(...).Err()).

Native acceptance command driven: `go test ./ex/optcache/...` (run from docs).
"""

import os
import shutil
import subprocess
import textwrap

import pytest

REPO_DIR = "/workspace/fx"
DOCS_DIR = os.path.join(REPO_DIR, "docs")
PKG_DIR = os.path.join(DOCS_DIR, "ex", "optcache")

GO_TEST_TIMEOUT = 480


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _go_env():
    env = os.environ.copy()
    env.setdefault("GOFLAGS", "")
    return env


def _run_go_test(target, extra_args=None, timeout=GO_TEST_TIMEOUT):
    """Run `go test <target>` from the docs module directory."""
    args = ["go", "test"]
    if extra_args:
        args.extend(extra_args)
    args.append(target)
    return subprocess.run(
        args,
        cwd=DOCS_DIR,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=_go_env(),
    )


def _write_driver(subdir_name, filename, source):
    """Write an independent driver test file into a fresh subpackage dir.

    Returns (dir_path, go_test_target). Caller is responsible for cleanup.
    """
    dpath = os.path.join(PKG_DIR, subdir_name)
    if os.path.isdir(dpath):
        shutil.rmtree(dpath)
    os.makedirs(dpath, exist_ok=True)
    with open(os.path.join(dpath, filename), "w") as fh:
        fh.write(source)
    target = "./ex/optcache/" + subdir_name + "/..."
    return dpath, target


# Import path of the optcache package under the docs module.
OPTCACHE_IMPORT = "go.uber.org/fx/docs/ex/optcache"


# --------------------------------------------------------------------------- #
# Dependency / build readiness (module-scope, autouse)
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module", autouse=True)
def _ensure_go_ready():
    """Ensure the Go toolchain + docs module deps are available.

    Warm the build/module cache once (paying the heavy download cost before
    the per-test timeouts apply). Tolerates failure here; the individual tests
    surface real errors with better messages.
    """
    assert os.path.isdir(REPO_DIR), f"missing repo dir {REPO_DIR}"
    assert os.path.isdir(DOCS_DIR), f"missing docs module dir {DOCS_DIR}"
    try:
        subprocess.run(
            ["go", "build", "./ex/optcache/..."],
            cwd=DOCS_DIR,
            capture_output=True,
            text=True,
            timeout=GO_TEST_TIMEOUT,
            env=_go_env(),
        )
    except Exception:
        pass
    yield


class TestGoFxDi:
    REPO_DIR = "/workspace/fx"

    _DRIVER_DIRS = (
        "extdrive_degraded",
        "extdrive_enabled",
        "extdrive_absent",
        "extdrive_optional",
        "extdrive_cache",
    )

    @classmethod
    def teardown_class(cls):
        for d in cls._DRIVER_DIRS:
            p = os.path.join(PKG_DIR, d)
            if os.path.isdir(p):
                shutil.rmtree(p, ignore_errors=True)

    # ------------------------------------------------------------------ #
    # L1 — deliverable files exist and are minimally well-formed
    # ------------------------------------------------------------------ #
    def test_package_directory_exists(self):
        """L1: the optcache example directory exists under docs/ex."""
        assert os.path.isdir(PKG_DIR), f"expected package dir at {PKG_DIR}"

    def test_required_source_files_present(self):
        """L1: required deliverable .go source files all exist."""
        for fname in ("cache.go", "lookup.go", "app.go"):
            fpath = os.path.join(PKG_DIR, fname)
            assert os.path.isfile(fpath), f"missing required file {fpath}"

    def test_package_uses_optcache_name_and_no_new_module(self):
        """L1: files declare `package optcache`; no new go.mod was added."""
        go_files = [f for f in os.listdir(PKG_DIR) if f.endswith(".go")]
        assert go_files, "no .go files found in package dir"
        for f in go_files:
            with open(os.path.join(PKG_DIR, f)) as fh:
                head = fh.read()
            assert "package optcache" in head, (
                f"{f} does not declare `package optcache`"
            )
        assert not os.path.isfile(os.path.join(PKG_DIR, "go.mod")), (
            "a new go.mod must NOT be created inside the example dir"
        )

    def test_package_compiles(self):
        """L1: the optcache package compiles under the docs module."""
        proc = subprocess.run(
            ["go", "build", "./ex/optcache/..."],
            cwd=DOCS_DIR,
            capture_output=True,
            text=True,
            timeout=GO_TEST_TIMEOUT,
            env=_go_env(),
        )
        assert proc.returncode == 0, (
            "optcache package failed to compile:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    def test_authors_own_test_passes(self):
        """L1: the task's native command passes for this package.

        `go test ./ex/optcache/...` (run from docs) must succeed.
        """
        proc = _run_go_test("./ex/optcache/...")
        assert proc.returncode == 0, (
            "`go test ./ex/optcache/...` failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    # ------------------------------------------------------------------ #
    # L2 — independent dynamic execution against the real Module(s)
    # ------------------------------------------------------------------ #
    def test_degraded_boot_returns_miss_and_disabled(self):
        """L2: boot Module alone -> Resolve("k")=="miss:k", CacheEnabled()==false.

        Independent driver: boot Module via fxtest, Populate a *Lookup, and
        assert the degraded outcomes exactly. A solution that returns cached
        values unconditionally, or that reports CacheEnabled()==true without a
        cache, fails here.
        """
        source = textwrap.dedent(
            f'''
            package extdrive_degraded

            import (
                "testing"

                optcache "{OPTCACHE_IMPORT}"
                "go.uber.org/fx"
                "go.uber.org/fx/fxtest"
            )

            func TestDegradedBoot(t *testing.T) {{
                var lk *optcache.Lookup
                app := fxtest.New(t,
                    optcache.Module,
                    fx.Populate(&lk),
                )
                app.RequireStart().RequireStop()

                if lk == nil {{
                    t.Fatalf("Lookup was not populated")
                }}
                if got := lk.Resolve("k"); got != "miss:k" {{
                    t.Fatalf("degraded Resolve(\\"k\\") = %q, want \\"miss:k\\"", got)
                }}
                if lk.CacheEnabled() {{
                    t.Fatalf("CacheEnabled() = true with no cache wired, want false")
                }}
                // a different key must produce its own miss string
                if got := lk.Resolve("zzz"); got != "miss:zzz" {{
                    t.Fatalf("degraded Resolve(\\"zzz\\") = %q, want \\"miss:zzz\\"", got)
                }}
            }}
            '''
        )
        dpath, target = _write_driver(
            "extdrive_degraded", "degraded_test.go", source
        )
        try:
            proc = _run_go_test(target, extra_args=["-count=1", "-v"])
            assert proc.returncode == 0, (
                "independent degraded-boot driver failed:\n"
                f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
            )
            assert "TestDegradedBoot" in proc.stdout
        finally:
            shutil.rmtree(dpath, ignore_errors=True)

    def test_enabled_boot_returns_cached_value(self):
        """L2: boot Module+CacheModule, seed k->v -> Resolve("k")=="v".

        Independent driver: Populate both *Lookup and the Cache interface,
        Set("k","v") through the resolved Cache, then assert Resolve reads it
        back and CacheEnabled()==true. A naive Resolve that always returns
        "miss:"+key fails this.
        """
        source = textwrap.dedent(
            f'''
            package extdrive_enabled

            import (
                "testing"

                optcache "{OPTCACHE_IMPORT}"
                "go.uber.org/fx"
                "go.uber.org/fx/fxtest"
            )

            func TestEnabledBoot(t *testing.T) {{
                var lk *optcache.Lookup
                var c optcache.Cache
                app := fxtest.New(t,
                    optcache.Module,
                    optcache.CacheModule,
                    fx.Populate(&lk),
                    fx.Populate(&c),
                )
                app.RequireStart().RequireStop()

                if lk == nil {{
                    t.Fatalf("Lookup was not populated")
                }}
                if c == nil {{
                    t.Fatalf("Cache was not populated by CacheModule")
                }}
                if !lk.CacheEnabled() {{
                    t.Fatalf("CacheEnabled() = false with CacheModule wired, want true")
                }}
                c.Set("k", "v")
                if got := lk.Resolve("k"); got != "v" {{
                    t.Fatalf("enabled Resolve(\\"k\\") = %q, want \\"v\\" (cache hit)", got)
                }}
                // distinct populated key returns its own distinct value
                c.Set("k2", "w")
                if got := lk.Resolve("k2"); got != "w" {{
                    t.Fatalf("enabled Resolve(\\"k2\\") = %q, want \\"w\\"", got)
                }}
            }}
            '''
        )
        dpath, target = _write_driver(
            "extdrive_enabled", "enabled_test.go", source
        )
        try:
            proc = _run_go_test(target, extra_args=["-count=1", "-v"])
            assert proc.returncode == 0, (
                "independent enabled-boot driver failed:\n"
                f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
            )
            assert "TestEnabledBoot" in proc.stdout
        finally:
            shutil.rmtree(dpath, ignore_errors=True)

    def test_enabled_boot_absent_key_returns_miss(self):
        """L2: with the cache enabled, an unpopulated key still returns miss.

        Boot Module+CacheModule but do NOT seed "absent"; Resolve("absent")
        must be "miss:absent". This catches a solution that returns the cache's
        zero value ("") instead of the degraded miss string on a cache miss.
        """
        source = textwrap.dedent(
            f'''
            package extdrive_absent

            import (
                "testing"

                optcache "{OPTCACHE_IMPORT}"
                "go.uber.org/fx"
                "go.uber.org/fx/fxtest"
            )

            func TestEnabledAbsentKey(t *testing.T) {{
                var lk *optcache.Lookup
                var c optcache.Cache
                app := fxtest.New(t,
                    optcache.Module,
                    optcache.CacheModule,
                    fx.Populate(&lk),
                    fx.Populate(&c),
                )
                app.RequireStart().RequireStop()

                if got := lk.Resolve("absent"); got != "miss:absent" {{
                    t.Fatalf("Resolve(\\"absent\\") on enabled-but-unpopulated cache "+
                        "= %q, want \\"miss:absent\\"", got)
                }}
                // seed one key, confirm only that one hits and another still misses
                c.Set("hit", "yes")
                if got := lk.Resolve("hit"); got != "yes" {{
                    t.Fatalf("Resolve(\\"hit\\") = %q, want \\"yes\\"", got)
                }}
                if got := lk.Resolve("other"); got != "miss:other" {{
                    t.Fatalf("Resolve(\\"other\\") = %q, want \\"miss:other\\"", got)
                }}
            }}
            '''
        )
        dpath, target = _write_driver(
            "extdrive_absent", "absent_test.go", source
        )
        try:
            proc = _run_go_test(target, extra_args=["-count=1", "-v"])
            assert proc.returncode == 0, (
                "independent absent-key driver failed:\n"
                f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
            )
        finally:
            shutil.rmtree(dpath, ignore_errors=True)

    def test_module_alone_has_no_dependency_error(self):
        """L2: fx.New(Module) graph builds with no missing-dependency/cycle err.

        Uses fx.New (not fxtest) and inspects App.Err(). A Lookup that
        hard-requires the *Cache would surface a missing-dependency error here;
        an optional dependency must not.
        """
        source = textwrap.dedent(
            f'''
            package extdrive_optional

            import (
                "context"
                "testing"
                "time"

                optcache "{OPTCACHE_IMPORT}"
                "go.uber.org/fx"
            )

            func TestModuleAloneNoDepError(t *testing.T) {{
                var lk *optcache.Lookup
                app := fx.New(optcache.Module, fx.Populate(&lk))
                if err := app.Err(); err != nil {{
                    t.Fatalf("Module alone produced graph error (cache must be "+
                        "optional): %v", err)
                }}
                ctx, cancel := context.WithTimeout(
                    context.Background(), 10*time.Second)
                defer cancel()
                if err := app.Start(ctx); err != nil {{
                    t.Fatalf("Module alone failed to start: %v", err)
                }}
                stopCtx, cancel2 := context.WithTimeout(
                    context.Background(), 10*time.Second)
                defer cancel2()
                if err := app.Stop(stopCtx); err != nil {{
                    t.Fatalf("Module alone failed to stop: %v", err)
                }}
                if lk == nil {{
                    t.Fatalf("Lookup not populated by Module alone")
                }}
                if lk.CacheEnabled() {{
                    t.Fatalf("CacheEnabled()=true with Module alone, want false")
                }}
            }}
            '''
        )
        dpath, target = _write_driver(
            "extdrive_optional", "optional_test.go", source
        )
        try:
            proc = _run_go_test(target, extra_args=["-count=1", "-v"])
            assert proc.returncode == 0, (
                "independent optional-dependency driver failed:\n"
                f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
            )
        finally:
            shutil.rmtree(dpath, ignore_errors=True)

    def test_hard_required_cache_would_fail_cache_absent_boot(self):
        """L2: a Lookup that hard-requires *Cache fails the cache-absent boot.

        This is the doc's discriminative negative case. We construct an
        INDEPENDENT 'strict' service that takes the package's Cache as a
        *non-optional* fx dependency, and confirm that booting it with Module
        alone (no CacheModule) yields a missing-dependency error. This proves
        the environment genuinely lacks a Cache under Module alone — so the
        real Lookup's success there is due to making the dep optional, not to
        the cache being present anyway.
        """
        source = textwrap.dedent(
            f'''
            package extdrive_optional

            import (
                "strings"
                "testing"

                optcache "{OPTCACHE_IMPORT}"
                "go.uber.org/fx"
            )

            // strict hard-requires a Cache (no optional tag).
            type strict struct{{ c optcache.Cache }}

            func newStrict(c optcache.Cache) *strict {{ return &strict{{c: c}} }}

            func TestHardRequiredCacheFails(t *testing.T) {{
                var s *strict
                app := fx.New(
                    optcache.Module,
                    fx.Provide(newStrict),
                    fx.Populate(&s),
                )
                err := app.Err()
                if err == nil {{
                    t.Fatalf("expected a missing-dependency error when hard-"+
                        "requiring Cache under Module alone, got nil")
                }}
                msg := strings.ToLower(err.Error())
                if !strings.Contains(msg, "cache") &&
                    !strings.Contains(msg, "missing") &&
                    !strings.Contains(msg, "not provided") {{
                    t.Fatalf("error did not look like a missing-Cache error: %v", err)
                }}
            }}
            '''
        )
        dpath, target = _write_driver(
            "extdrive_optional", "strict_test.go", source
        )
        try:
            proc = _run_go_test(target, extra_args=["-count=1", "-v"])
            assert proc.returncode == 0, (
                "independent hard-required-cache driver failed:\n"
                f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
            )
        finally:
            shutil.rmtree(dpath, ignore_errors=True)

    def test_memory_cache_get_set_roundtrip(self):
        """L2: NewMemoryCache round-trips values and reports presence correctly.

        Drives the Cache contract directly (independent of Lookup): Get on a
        missing key returns ("", false); after Set, Get returns (val, true);
        overwrite updates the value. A stub Cache that ignores Set or always
        reports found=false fails here.
        """
        source = textwrap.dedent(
            f'''
            package extdrive_cache

            import (
                "testing"

                optcache "{OPTCACHE_IMPORT}"
            )

            func TestMemoryCacheRoundtrip(t *testing.T) {{
                c := optcache.NewMemoryCache()
                if c == nil {{
                    t.Fatalf("NewMemoryCache returned nil")
                }}
                if v, ok := c.Get("missing"); ok || v != "" {{
                    t.Fatalf("Get(missing) = (%q,%v), want (\\"\\",false)", v, ok)
                }}
                c.Set("a", "1")
                if v, ok := c.Get("a"); !ok || v != "1" {{
                    t.Fatalf("Get(a) after Set = (%q,%v), want (\\"1\\",true)", v, ok)
                }}
                c.Set("a", "2") // overwrite
                if v, ok := c.Get("a"); !ok || v != "2" {{
                    t.Fatalf("Get(a) after overwrite = (%q,%v), want (\\"2\\",true)", v, ok)
                }}
                // independent key unaffected
                if _, ok := c.Get("b"); ok {{
                    t.Fatalf("Get(b) reported present, want absent")
                }}
            }}
            '''
        )
        dpath, target = _write_driver(
            "extdrive_cache", "cache_test.go", source
        )
        try:
            proc = _run_go_test(target, extra_args=["-count=1", "-v"])
            assert proc.returncode == 0, (
                "independent memory-cache driver failed:\n"
                f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
            )
        finally:
            shutil.rmtree(dpath, ignore_errors=True)

    def test_memory_cache_is_concurrency_safe(self):
        """L2: NewMemoryCache is concurrency-safe under the race detector.

        The doc requires the in-memory cache be backed by a concurrency-safe
        map. Concurrent Set/Get under `go test -race` must not report a data
        race. Skipped (not failed) when no cgo toolchain is available.
        """
        source = textwrap.dedent(
            f'''
            package extdrive_cache

            import (
                "strconv"
                "sync"
                "testing"

                optcache "{OPTCACHE_IMPORT}"
            )

            func TestMemoryCacheRace(t *testing.T) {{
                c := optcache.NewMemoryCache()
                var wg sync.WaitGroup
                for i := 0; i < 16; i++ {{
                    wg.Add(1)
                    go func(n int) {{
                        defer wg.Done()
                        k := "k" + strconv.Itoa(n%4)
                        c.Set(k, strconv.Itoa(n))
                        _, _ = c.Get(k)
                    }}(i)
                }}
                wg.Wait()
            }}
            '''
        )
        dpath, target = _write_driver(
            "extdrive_cache", "race_test.go", source
        )
        try:
            env = _go_env()
            env["CGO_ENABLED"] = "1"
            proc = subprocess.run(
                ["go", "test", "-count=1", "-race", "-v", target],
                cwd=DOCS_DIR,
                capture_output=True,
                text=True,
                timeout=GO_TEST_TIMEOUT,
                env=env,
            )
            combined = proc.stdout + proc.stderr
            if "-race requires cgo" in combined or (
                "gcc" in combined and "executable file not found" in combined
            ):
                pytest.skip(
                    "race detector unavailable (no cgo toolchain): " + combined
                )
            assert "DATA RACE" not in combined, (
                "race detector reported a data race in the memory cache:\n"
                + combined
            )
            assert proc.returncode == 0, (
                "race driver failed:\n"
                f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
            )
        finally:
            shutil.rmtree(dpath, ignore_errors=True)

    def test_same_lookup_serves_both_wirings(self):
        """L2: one Lookup constructor serves both boots; only CacheModule differs.

        Boot Module alone (degraded) and Module+CacheModule (enabled) within the
        SAME driver and assert opposite behavior for the same key value. This
        proves the single constructor adapts to the graph rather than two
        divergent code paths, and that CacheModule is the only differentiator.
        """
        source = textwrap.dedent(
            f'''
            package extdrive_enabled

            import (
                "testing"

                optcache "{OPTCACHE_IMPORT}"
                "go.uber.org/fx"
                "go.uber.org/fx/fxtest"
            )

            func TestBothWirings(t *testing.T) {{
                // degraded
                var lk1 *optcache.Lookup
                app1 := fxtest.New(t, optcache.Module, fx.Populate(&lk1))
                app1.RequireStart().RequireStop()
                if lk1.CacheEnabled() {{
                    t.Fatalf("degraded boot reported CacheEnabled()=true")
                }}
                if got := lk1.Resolve("same"); got != "miss:same" {{
                    t.Fatalf("degraded Resolve(\\"same\\") = %q, want \\"miss:same\\"", got)
                }}

                // enabled
                var lk2 *optcache.Lookup
                var c optcache.Cache
                app2 := fxtest.New(t,
                    optcache.Module,
                    optcache.CacheModule,
                    fx.Populate(&lk2),
                    fx.Populate(&c),
                )
                app2.RequireStart().RequireStop()
                if !lk2.CacheEnabled() {{
                    t.Fatalf("enabled boot reported CacheEnabled()=false")
                }}
                c.Set("same", "VALUE")
                if got := lk2.Resolve("same"); got != "VALUE" {{
                    t.Fatalf("enabled Resolve(\\"same\\") = %q, want \\"VALUE\\"", got)
                }}
            }}
            '''
        )
        dpath, target = _write_driver(
            "extdrive_enabled", "both_test.go", source
        )
        try:
            proc = _run_go_test(target, extra_args=["-count=1", "-v"])
            assert proc.returncode == 0, (
                "independent both-wirings driver failed:\n"
                f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
            )
        finally:
            shutil.rmtree(dpath, ignore_errors=True)
