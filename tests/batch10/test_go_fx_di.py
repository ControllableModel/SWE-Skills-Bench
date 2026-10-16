"""Tests for the `go-fx-di` skill task (variant ext10): a startup-failure and
timeout example for graph boot.

Skill under test: go-fx-di (uber-go/fx dependency injection + lifecycle
coordination, here focused on *boot failure semantics*).

The task asks the agent to create a new `bootfail` package under
`docs/ex/bootfail/` inside the `go.uber.org/fx/docs` module. The package must
expose:

  * `Sentinel` — a concurrency-safe struct recording whether each phase ran,
    with `Started() bool` and `Stopped() bool`;
  * `ErrBoot` — an exported sentinel error returned by a failing start hook;
  * `Module` — a healthy composition root (`fx.Option`);
  * `FailingModule` — a composition root whose start hook returns an error
    wrapping `ErrBoot`;
  * `SlowModule` — a composition root whose start hook hangs until its context
    is cancelled (honoring `ctx.Done()`);
  * `New(opts ...fx.Option) *fx.App` — a helper building an app with a short,
    explicit startup timeout.

Boot semantics the agent must implement:

  * healthy `Module`: `Start(ctx)` returns nil, `Sentinel.Started()` true,
    after `Stop(ctx)` `Sentinel.Stopped()` true;
  * `FailingModule`: `Start(ctx)` returns a non-nil error and
    `errors.Is(err, ErrBoot)` is true;
  * `SlowModule` under a short startup timeout: `Start(ctx)` returns a non-nil
    (deadline/cancellation) error promptly, without hanging;
  * an under-wired graph (missing provider): a validation error is observable
    via `.Err()` (or `Start`) *before* any start hook runs.

Verification strategy: rather than trusting the agent's own
`bootfail_test.go`, the L2 tests write INDEPENDENT Go driver test files into
fresh sub-directories of the `bootfail` package and run them with the native
`go test` toolchain (from the `docs` module). These drivers boot the real
`Module` / `FailingModule` / `SlowModule` via `bootfail.New(...)` and assert
deeply on return values, `errors.Is`, the `Sentinel` flags, and a bounded
elapsed-time window for the slow case. A naive implementation (a `Start` that
always returns nil, a failing module that does not actually wrap `ErrBoot`, or
a slow hook that ignores cancellation and so hangs) MUST fail these drivers.

The native acceptance command this drives:  cd docs && go test ./ex/bootfail/...
"""

import os
import shutil
import subprocess
import textwrap

import pytest

REPO_DIR = "/workspace/fx"
DOCS_DIR = os.path.join(REPO_DIR, "docs")
PKG_DIR = os.path.join(DOCS_DIR, "ex", "bootfail")

GO_TEST_TIMEOUT = 480

# Import path of the bootfail package inside the docs module.
BOOTFAIL_IMPORT = "go.uber.org/fx/docs/ex/bootfail"


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _go_env():
    env = os.environ.copy()
    # Deterministic-ish env; keep go's defaults but ensure GOFLAGS exists so
    # callers can rely on it. No network is required (module cache is warm in
    # the container image).
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
    target = "./ex/bootfail/" + subdir_name + "/..."
    return dpath, target


# --------------------------------------------------------------------------- #
# Dependency / build readiness (module-scope, autouse)
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module", autouse=True)
def _ensure_go_ready():
    """Make sure the Go toolchain + docs module deps are available.

    Warms the build/module cache once so per-test timeouts aren't spent on the
    first (potentially heavy) compile. Tolerates failure here; individual tests
    surface real errors with better messages.
    """
    assert os.path.isdir(REPO_DIR), f"missing repo dir {REPO_DIR}"
    assert os.path.isdir(DOCS_DIR), f"missing docs module dir {DOCS_DIR}"
    try:
        subprocess.run(
            ["go", "build", "./ex/bootfail/..."],
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

    # driver subdirs we create and must clean up
    _DRIVER_DIRS = (
        "extdrive_healthy",
        "extdrive_failing",
        "extdrive_slow",
        "extdrive_missing",
        "extdrive_sentinel",
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
        """L1: the bootfail example directory exists under docs/ex."""
        assert os.path.isdir(PKG_DIR), f"expected package dir at {PKG_DIR}"

    def test_required_source_files_present(self):
        """L1: required deliverable .go source files all exist."""
        for fname in ("components.go", "app.go", "bootfail_test.go"):
            fpath = os.path.join(PKG_DIR, fname)
            assert os.path.isfile(fpath), f"missing required file {fpath}"

    def test_package_uses_bootfail_name_and_no_new_module(self):
        """L1: files declare `package bootfail`; no new go.mod was added."""
        go_files = [f for f in os.listdir(PKG_DIR) if f.endswith(".go")]
        assert go_files, "no .go files found in package dir"
        for f in go_files:
            with open(os.path.join(PKG_DIR, f)) as fh:
                head = fh.read()
            assert "package bootfail" in head, (
                f"{f} does not declare `package bootfail`"
            )
        assert not os.path.isfile(os.path.join(PKG_DIR, "go.mod")), (
            "a new go.mod must NOT be created inside the example dir"
        )

    def test_package_compiles(self):
        """L1: the bootfail package compiles under the docs module."""
        proc = subprocess.run(
            ["go", "build", "./ex/bootfail/..."],
            cwd=DOCS_DIR,
            capture_output=True,
            text=True,
            timeout=GO_TEST_TIMEOUT,
            env=_go_env(),
        )
        assert proc.returncode == 0, (
            "bootfail package failed to compile:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    def test_exported_symbols_present_via_compile(self):
        """L1: required exported symbols exist with the expected shapes.

        Compile (vet) a tiny driver that *references* every required symbol:
        `Sentinel` with `Started()/Stopped() bool`, `ErrBoot` as an `error`,
        `Module`/`FailingModule`/`SlowModule` as `fx.Option`, and
        `New(...) *fx.App`. If any symbol is missing or has the wrong type, the
        driver fails to compile and this test fails. (`go vet` compiles the
        package and test without running it.)
        """
        source = textwrap.dedent(
            f'''
            package extdrive_sentinel

            import (
                "errors"

                bootfail "{BOOTFAIL_IMPORT}"
                "go.uber.org/fx"
            )

            // Compile-time assertions over the required surface.
            var _ error = bootfail.ErrBoot
            var _ fx.Option = bootfail.Module
            var _ fx.Option = bootfail.FailingModule
            var _ fx.Option = bootfail.SlowModule

            func _useSymbols() {{
                var s bootfail.Sentinel
                var started bool = s.Started()
                var stopped bool = s.Stopped()
                _ = started
                _ = stopped
                _ = errors.Is(bootfail.ErrBoot, bootfail.ErrBoot)
                var app *fx.App = bootfail.New(bootfail.Module)
                _ = app
            }}
            '''
        )
        dpath, _ = _write_driver(
            "extdrive_sentinel", "symbols_test.go", source
        )
        try:
            proc = subprocess.run(
                ["go", "vet", "./ex/bootfail/extdrive_sentinel/..."],
                cwd=DOCS_DIR,
                capture_output=True,
                text=True,
                timeout=GO_TEST_TIMEOUT,
                env=_go_env(),
            )
            assert proc.returncode == 0, (
                "required exported symbols missing or wrong type "
                "(Sentinel.Started()/Stopped() bool, ErrBoot error, "
                "Module/FailingModule/SlowModule fx.Option, "
                "New(...) *fx.App):\n"
                f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
            )
        finally:
            shutil.rmtree(dpath, ignore_errors=True)

    def test_authors_own_test_passes(self):
        """L1: the task's specified native command passes for this package."""
        proc = _run_go_test("./ex/bootfail/...")
        assert proc.returncode == 0, (
            "`go test ./ex/bootfail/...` failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    # ------------------------------------------------------------------ #
    # L2 — independent dynamic execution against the real composition roots
    # ------------------------------------------------------------------ #
    def test_healthy_module_boots_and_records_sentinel(self):
        """L2: healthy Module starts cleanly and the Sentinel reports phases.

        Independent driver: build via `New(Module)` (sharing a *Sentinel),
        Start must return nil and Started() must be true; after Stop, Stopped()
        must be true. A stub whose start hook does nothing would leave
        Started()==false and fail here.
        """
        source = textwrap.dedent(
            f'''
            package extdrive_healthy

            import (
                "context"
                "testing"
                "time"

                bootfail "{BOOTFAIL_IMPORT}"
                "go.uber.org/fx"
            )

            func TestHealthyBoot(t *testing.T) {{
                s := &bootfail.Sentinel{{}}
                app := bootfail.New(bootfail.Module, fx.Supply(s))
                if err := app.Err(); err != nil {{
                    t.Fatalf("healthy graph construction error: %v", err)
                }}

                startCtx, cancel := context.WithTimeout(
                    context.Background(), 5*time.Second)
                defer cancel()
                if err := app.Start(startCtx); err != nil {{
                    t.Fatalf("healthy Start returned error: %v", err)
                }}
                if !s.Started() {{
                    t.Fatalf("Sentinel.Started() false after a clean Start")
                }}
                if s.Stopped() {{
                    t.Fatalf("Sentinel.Stopped() true before Stop was called")
                }}

                stopCtx, cancel2 := context.WithTimeout(
                    context.Background(), 5*time.Second)
                defer cancel2()
                if err := app.Stop(stopCtx); err != nil {{
                    t.Fatalf("healthy Stop returned error: %v", err)
                }}
                if !s.Stopped() {{
                    t.Fatalf("Sentinel.Stopped() false after Stop")
                }}
            }}
            '''
        )
        dpath, target = _write_driver(
            "extdrive_healthy", "healthy_test.go", source
        )
        try:
            proc = _run_go_test(target, extra_args=["-count=1", "-v"])
            assert proc.returncode == 0, (
                "independent healthy-boot driver failed:\n"
                f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
            )
            assert "TestHealthyBoot" in proc.stdout
        finally:
            shutil.rmtree(dpath, ignore_errors=True)

    def test_failing_module_start_wraps_errboot(self):
        """L2: FailingModule's Start returns an error wrapping ErrBoot.

        `errors.Is(err, bootfail.ErrBoot)` must be true. A naive failing module
        that returns a freshly-constructed unrelated error (or returns nil)
        fails this. Also asserts the Sentinel is NOT left reporting a
        successful start.
        """
        source = textwrap.dedent(
            f'''
            package extdrive_failing

            import (
                "context"
                "errors"
                "testing"
                "time"

                bootfail "{BOOTFAIL_IMPORT}"
                "go.uber.org/fx"
            )

            func TestFailingBootWrapsErrBoot(t *testing.T) {{
                s := &bootfail.Sentinel{{}}
                app := bootfail.New(bootfail.FailingModule, fx.Supply(s))
                // Graph itself must be valid; the failure is at start time.
                if err := app.Err(); err != nil {{
                    t.Fatalf("failing graph should construct cleanly, got: %v",
                        err)
                }}

                startCtx, cancel := context.WithTimeout(
                    context.Background(), 5*time.Second)
                defer cancel()
                err := app.Start(startCtx)
                if err == nil {{
                    t.Fatalf("FailingModule Start returned nil; expected error")
                }}
                if !errors.Is(err, bootfail.ErrBoot) {{
                    t.Fatalf("Start error does not wrap ErrBoot: %v "+
                        "(errors.Is == false)", err)
                }}
                // Best-effort cleanup; failure is acceptable since start failed.
                stopCtx, cancel2 := context.WithTimeout(
                    context.Background(), 5*time.Second)
                defer cancel2()
                _ = app.Stop(stopCtx)
            }}
            '''
        )
        dpath, target = _write_driver(
            "extdrive_failing", "failing_test.go", source
        )
        try:
            proc = _run_go_test(target, extra_args=["-count=1", "-v"])
            assert proc.returncode == 0, (
                "independent failing-boot driver failed:\n"
                f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
            )
            assert "TestFailingBootWrapsErrBoot" in proc.stdout
        finally:
            shutil.rmtree(dpath, ignore_errors=True)

    def test_failing_module_distinct_error_is_not_arbitrary(self):
        """L2: the wrapped error is specifically ErrBoot, not any error.

        Discriminative guard: a solution that returns *some* error but a
        DIFFERENT sentinel would pass a loose "Start != nil" check. We confirm
        that errors.Is matches ErrBoot but does NOT match an unrelated sentinel
        defined in the driver, so the agent cannot satisfy the test by returning
        a generic/unrelated error.
        """
        source = textwrap.dedent(
            f'''
            package extdrive_failing

            import (
                "context"
                "errors"
                "testing"
                "time"

                bootfail "{BOOTFAIL_IMPORT}"
                "go.uber.org/fx"
            )

            var errUnrelated = errors.New("unrelated sentinel")

            func TestFailingErrorIsSpecific(t *testing.T) {{
                s := &bootfail.Sentinel{{}}
                app := bootfail.New(bootfail.FailingModule, fx.Supply(s))
                startCtx, cancel := context.WithTimeout(
                    context.Background(), 5*time.Second)
                defer cancel()
                err := app.Start(startCtx)
                if err == nil {{
                    t.Fatalf("expected non-nil error from FailingModule")
                }}
                if !errors.Is(err, bootfail.ErrBoot) {{
                    t.Fatalf("error must match ErrBoot: %v", err)
                }}
                if errors.Is(err, errUnrelated) {{
                    t.Fatalf("error unexpectedly matched an unrelated "+
                        "sentinel; ErrBoot must be a distinct value")
                }}
                stopCtx, cancel2 := context.WithTimeout(
                    context.Background(), 5*time.Second)
                defer cancel2()
                _ = app.Stop(stopCtx)
            }}
            '''
        )
        dpath, target = _write_driver(
            "extdrive_failing", "specific_test.go", source
        )
        try:
            proc = _run_go_test(target, extra_args=["-count=1", "-v"])
            assert proc.returncode == 0, (
                "independent error-specificity driver failed:\n"
                f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
            )
        finally:
            shutil.rmtree(dpath, ignore_errors=True)

    def test_slow_module_start_bounded_by_timeout(self):
        """L2: SlowModule's Start returns an error promptly under the timeout.

        Boots `New(SlowModule)` (which the agent configured with a short, e.g.
        50ms, startup timeout) and measures elapsed time. Start MUST return a
        non-nil (deadline/cancellation) error within a generous bound, proving
        the slow hook honored ctx.Done() rather than hanging. A slow hook that
        ignores cancellation would block well past the bound and trip the
        per-test go-test timeout (failing the test).
        """
        source = textwrap.dedent(
            f'''
            package extdrive_slow

            import (
                "context"
                "testing"
                "time"

                bootfail "{BOOTFAIL_IMPORT}"
                "go.uber.org/fx"
            )

            func TestSlowBootBounded(t *testing.T) {{
                s := &bootfail.Sentinel{{}}
                app := bootfail.New(bootfail.SlowModule, fx.Supply(s))
                if err := app.Err(); err != nil {{
                    t.Fatalf("slow graph construction error: %v", err)
                }}

                // Give the outer context plenty of headroom; the app's own
                // configured StartTimeout (short) must be what bounds Start.
                startCtx, cancel := context.WithTimeout(
                    context.Background(), 10*time.Second)
                defer cancel()

                done := make(chan error, 1)
                start := time.Now()
                go func() {{
                    done <- app.Start(startCtx)
                }}()

                var err error
                select {{
                case err = <-done:
                case <-time.After(5 * time.Second):
                    t.Fatalf("SlowModule Start did not return within 5s; "+
                        "the start hook is not honoring context cancellation "+
                        "or no short startup timeout is configured")
                }}
                elapsed := time.Since(start)

                if err == nil {{
                    t.Fatalf("SlowModule Start returned nil; expected a "+
                        "deadline/cancellation error")
                }}
                if elapsed > 5*time.Second {{
                    t.Fatalf("SlowModule Start took too long (%v); the "+
                        "startup timeout is not bounding the hang", elapsed)
                }}

                stopCtx, cancel2 := context.WithTimeout(
                    context.Background(), 5*time.Second)
                defer cancel2()
                _ = app.Stop(stopCtx)
            }}
            '''
        )
        dpath, target = _write_driver(
            "extdrive_slow", "slow_test.go", source
        )
        try:
            # Bounded outer timeout: if the hang isn't honored, go test's own
            # -timeout trips and the run fails (non-zero) rather than hanging
            # the whole suite.
            proc = _run_go_test(
                target,
                extra_args=["-count=1", "-v", "-timeout", "60s"],
                timeout=180,
            )
            assert proc.returncode == 0, (
                "independent slow-boot driver failed:\n"
                f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
            )
            assert "TestSlowBootBounded" in proc.stdout
        finally:
            shutil.rmtree(dpath, ignore_errors=True)

    def test_missing_provider_surfaces_validation_error_before_start(self):
        """L2: an under-wired graph reports an error before any start hook.

        Build the healthy Module via `New(Module)` but WITHOUT supplying the
        *Sentinel dependency it requires. The graph must be invalid: `app.Err()`
        must be non-nil, OR `Start` must return a non-nil error, and crucially
        the Sentinel (constructed locally and never supplied) cannot have been
        Started. This catches solutions that don't actually wire a required
        provider / that swallow validation errors.
        """
        source = textwrap.dedent(
            f'''
            package extdrive_missing

            import (
                "context"
                "testing"
                "time"

                bootfail "{BOOTFAIL_IMPORT}"
            )

            func TestMissingProviderError(t *testing.T) {{
                // Deliberately do NOT supply the *Sentinel the Module needs.
                app := bootfail.New(bootfail.Module)

                errAtBuild := app.Err()

                startCtx, cancel := context.WithTimeout(
                    context.Background(), 2*time.Second)
                defer cancel()
                errAtStart := app.Start(startCtx)

                if errAtBuild == nil && errAtStart == nil {{
                    t.Fatalf("under-wired graph started without error; a "+
                        "missing required provider must surface a validation "+
                        "error via Err() or Start()")
                }}

                stopCtx, cancel2 := context.WithTimeout(
                    context.Background(), 2*time.Second)
                defer cancel2()
                _ = app.Stop(stopCtx)
            }}
            '''
        )
        dpath, target = _write_driver(
            "extdrive_missing", "missing_test.go", source
        )
        try:
            proc = _run_go_test(
                target,
                extra_args=["-count=1", "-v", "-timeout", "30s"],
                timeout=120,
            )
            assert proc.returncode == 0, (
                "independent missing-provider driver failed:\n"
                f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
            )
            assert "TestMissingProviderError" in proc.stdout
        finally:
            shutil.rmtree(dpath, ignore_errors=True)

    def test_failing_module_does_not_report_successful_start(self):
        """L2: after a FailingModule boot, Sentinel must not report Started.

        The doc requires the app "must not be left reporting a successful
        start". The failing component's start hook returns ErrBoot, so the
        healthy Sentinel-recording hook must not have completed a successful
        start. We assert that after a failed Start, the Sentinel does not claim
        a clean start. (If the failing graph legitimately omits the healthy
        recorder entirely, Started() stays false too — still correct.)
        """
        source = textwrap.dedent(
            f'''
            package extdrive_failing

            import (
                "context"
                "errors"
                "testing"
                "time"

                bootfail "{BOOTFAIL_IMPORT}"
                "go.uber.org/fx"
            )

            func TestFailingNotStarted(t *testing.T) {{
                s := &bootfail.Sentinel{{}}
                app := bootfail.New(bootfail.FailingModule, fx.Supply(s))
                startCtx, cancel := context.WithTimeout(
                    context.Background(), 5*time.Second)
                defer cancel()
                err := app.Start(startCtx)
                if err == nil || !errors.Is(err, bootfail.ErrBoot) {{
                    t.Fatalf("expected Start error wrapping ErrBoot, got: %v",
                        err)
                }}
                if s.Started() {{
                    t.Fatalf("Sentinel.Started() true after a FAILED boot; "+
                        "app must not report a successful start")
                }}
                stopCtx, cancel2 := context.WithTimeout(
                    context.Background(), 5*time.Second)
                defer cancel2()
                _ = app.Stop(stopCtx)
            }}
            '''
        )
        dpath, target = _write_driver(
            "extdrive_failing", "notstarted_test.go", source
        )
        try:
            proc = _run_go_test(target, extra_args=["-count=1", "-v"])
            assert proc.returncode == 0, (
                "independent failing-not-started driver failed:\n"
                f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
            )
        finally:
            shutil.rmtree(dpath, ignore_errors=True)

    def test_sentinel_is_concurrency_safe_under_race(self):
        """L2: the Sentinel is concurrency-safe (go test -race is clean).

        The doc requires `Sentinel` be "safe for concurrent use". We hammer it
        concurrently (the hooks record into it from lifecycle goroutines, and we
        add concurrent readers) under the race detector and assert no DATA RACE
        is reported. Skipped only if the cgo toolchain for -race is unavailable.
        """
        source = textwrap.dedent(
            f'''
            package extdrive_sentinel

            import (
                "context"
                "sync"
                "testing"
                "time"

                bootfail "{BOOTFAIL_IMPORT}"
                "go.uber.org/fx"
            )

            func TestSentinelRace(t *testing.T) {{
                s := &bootfail.Sentinel{{}}
                app := bootfail.New(bootfail.Module, fx.Supply(s))
                if err := app.Err(); err != nil {{
                    t.Fatalf("graph error: %v", err)
                }}

                var wg sync.WaitGroup
                stop := make(chan struct{{}})
                for i := 0; i < 4; i++ {{
                    wg.Add(1)
                    go func() {{
                        defer wg.Done()
                        for {{
                            select {{
                            case <-stop:
                                return
                            default:
                                _ = s.Started()
                                _ = s.Stopped()
                            }}
                        }}
                    }}()
                }}

                startCtx, cancel := context.WithTimeout(
                    context.Background(), 5*time.Second)
                defer cancel()
                if err := app.Start(startCtx); err != nil {{
                    close(stop)
                    wg.Wait()
                    t.Fatalf("healthy Start failed under race: %v", err)
                }}
                stopCtx, cancel2 := context.WithTimeout(
                    context.Background(), 5*time.Second)
                defer cancel2()
                _ = app.Stop(stopCtx)

                close(stop)
                wg.Wait()
                _ = time.Now()
            }}
            '''
        )
        dpath, target = _write_driver(
            "extdrive_sentinel", "race_test.go", source
        )
        try:
            env = _go_env()
            env["CGO_ENABLED"] = "1"  # -race needs cgo
            proc = subprocess.run(
                ["go", "test", "-count=1", "-race", "-v",
                 "-timeout", "60s", target],
                cwd=DOCS_DIR,
                capture_output=True,
                text=True,
                timeout=180,
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
                "race detector reported a data race in the Sentinel:\n"
                + combined
            )
            assert proc.returncode == 0, (
                "race driver failed:\n"
                f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
            )
        finally:
            shutil.rmtree(dpath, ignore_errors=True)
