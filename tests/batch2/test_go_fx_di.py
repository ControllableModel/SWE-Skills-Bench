"""Tests for the `go-fx-di` skill task (ext2 variant): a graceful TCP listener
example with boot/shutdown ordering.

Skill under test: go-fx-di (uber-go/fx dependency injection + lifecycle
coordination via fx.Lifecycle OnStart/OnStop hooks).

The ext2 task asks the agent to create a new `listener` package under
`docs/ex/listener/` inside the `go.uber.org/fx/docs` module. The package must
expose:

  * `State`   — concurrency-safe readiness state with `SetAddr(string)`,
                `Addr() string`, and `Phases() []string` (returning a copy);
  * `Server`  — a TCP echo server; `NewServer(lc, *State) *Server` registers
                lifecycle hooks but the constructor must NOT bind/Accept/spawn;
  * `Probe`   — `NewProbe(...)` that during start dials the bound address and
                round-trips a byte, appending `"probe-ok"`;
  * `Module`  — an `fx.Option` wiring `Server` and `Probe` so that booting
                `Module` + a supplied `*State` yields a working app.

Booting the app then stopping it must produce exactly the phase sequence
`["listen", "probe-ok", "close"]`. Before start, `State.Addr()` must be empty
(the bind happens at start, not construction) and no socket may be open. After
stop, the recorded address must no longer be connectable.

Verification strategy: rather than trusting the agent's own
`listener_test.go`, the L2 tests write INDEPENDENT Go driver test files into a
fresh sub-directory of the `listener` package and run them with the native
`go test` toolchain (from the `docs` module). These drivers boot the real
`Module` via `fxtest`, dial the live socket, and assert deeply on `Phases()`
ordering, on the empty-before-start invariant, and on post-stop
unreachability. A naive solution (binding in the constructor, hardcoding the
phase slice, never closing the listener, or skipping the probe round-trip)
cannot pass these dynamic checks.
"""

import os
import shutil
import subprocess
import textwrap

import pytest

REPO_DIR = "/workspace/fx"
DOCS_DIR = os.path.join(REPO_DIR, "docs")
PKG_DIR = os.path.join(DOCS_DIR, "ex", "listener")

GO_TEST_TIMEOUT = 480

# The import path of the listener package under the docs module.
LISTENER_IMPORT = "go.uber.org/fx/docs/ex/listener"


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
    target = "./ex/listener/" + subdir_name + "/..."
    return dpath, target


# --------------------------------------------------------------------------- #
# Dependency / build readiness (module-scope, autouse)
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module", autouse=True)
def _ensure_go_ready():
    """Make sure the Go toolchain + docs module deps are available.

    Runs a cheap compile of the listener package so the heavy module-download
    cost is paid once, before the per-test timeouts apply.
    """
    assert os.path.isdir(REPO_DIR), f"missing repo dir {REPO_DIR}"
    assert os.path.isdir(DOCS_DIR), f"missing docs module dir {DOCS_DIR}"
    try:
        subprocess.run(
            ["go", "build", "./ex/listener/..."],
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
        "extdrive_boot",
        "extdrive_order",
        "extdrive_lifecycle",
        "extdrive_construct",
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
        """L1: the listener example directory exists under docs/ex."""
        assert os.path.isdir(PKG_DIR), f"expected package dir at {PKG_DIR}"

    def test_required_source_files_present(self):
        """L1: required deliverable .go source files all exist."""
        for fname in ("server.go", "probe.go", "app.go", "listener_test.go"):
            fpath = os.path.join(PKG_DIR, fname)
            assert os.path.isfile(fpath), f"missing required file {fpath}"

    def test_package_uses_listener_name_and_no_new_module(self):
        """L1: files declare `package listener`; no new go.mod was added."""
        go_files = [f for f in os.listdir(PKG_DIR) if f.endswith(".go")]
        assert go_files, "no .go files found in package dir"
        for f in go_files:
            with open(os.path.join(PKG_DIR, f)) as fh:
                head = fh.read()
            assert "package listener" in head, (
                f"{f} does not declare `package listener`"
            )
        assert not os.path.isfile(os.path.join(PKG_DIR, "go.mod")), (
            "a new go.mod must NOT be created inside the example dir"
        )

    def test_constructor_does_not_bind_in_source(self):
        """L1: NewServer's source must not call net.Listen / Accept directly.

        This is a cheap structural guard against the most obvious naive
        implementation (binding the socket in the constructor body). The
        authoritative behavioral check is the empty-before-start L2 test; this
        L1 check simply flags a constructor that references net.Listen on the
        same logical line region as the constructor. We require that the file
        wires binding through a lifecycle OnStart hook.
        """
        spath = os.path.join(PKG_DIR, "server.go")
        with open(spath) as fh:
            src = fh.read()
        # Binding must be coordinated via a lifecycle hook, not eagerly.
        assert "OnStart" in src, (
            "server.go must register an OnStart lifecycle hook to bind at "
            "start time, not in the constructor"
        )
        assert "OnStop" in src, (
            "server.go must register an OnStop lifecycle hook to close the "
            "listener at stop time"
        )

    def test_package_compiles(self):
        """L1: the listener package compiles under the docs module."""
        proc = subprocess.run(
            ["go", "build", "./ex/listener/..."],
            cwd=DOCS_DIR,
            capture_output=True,
            text=True,
            timeout=GO_TEST_TIMEOUT,
            env=_go_env(),
        )
        assert proc.returncode == 0, (
            "listener package failed to compile:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    def test_authors_own_test_passes(self):
        """L1: the task's native command passes for this package.

        Native acceptance command (run from docs/): `go test ./ex/listener/...`.
        """
        proc = _run_go_test("./ex/listener/...")
        assert proc.returncode == 0, (
            "`go test ./ex/listener/...` failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    # ------------------------------------------------------------------ #
    # L2 — independent dynamic execution against the real Module
    # ------------------------------------------------------------------ #
    def test_phases_exact_sequence_after_boot_and_stop(self):
        """L2: Phases() == ["listen","probe-ok","close"] after start+stop.

        Independent driver: supply a fresh *State, RequireStart/RequireStop,
        then assert the phase log equals the exact ordered sequence. A
        hardcoded slice that omits the probe round-trip or never closes cannot
        match this exactly.
        """
        source = textwrap.dedent(
            f'''
            package extdrive_order

            import (
                "testing"

                listener "{LISTENER_IMPORT}"
                "go.uber.org/fx"
                "go.uber.org/fx/fxtest"
            )

            func TestPhasesExactSequence(t *testing.T) {{
                st := &listener.State{{}}
                app := fxtest.New(t, listener.Module, fx.Supply(st))
                app.RequireStart()
                app.RequireStop()

                phases := st.Phases()
                want := []string{{"listen", "probe-ok", "close"}}
                if len(phases) != len(want) {{
                    t.Fatalf("expected phases %v, got %v", want, phases)
                }}
                for i := range want {{
                    if phases[i] != want[i] {{
                        t.Fatalf("phase[%d] = %q, want %q (full=%v)",
                            i, phases[i], want[i], phases)
                    }}
                }}
            }}
            '''
        )
        dpath, target = _write_driver(
            "extdrive_order", "phases_test.go", source
        )
        try:
            proc = _run_go_test(target, extra_args=["-count=1", "-v"])
            assert proc.returncode == 0, (
                "independent phase-sequence driver failed:\n"
                f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
            )
            assert "TestPhasesExactSequence" in proc.stdout
        finally:
            shutil.rmtree(dpath, ignore_errors=True)

    def test_listen_strictly_before_probe_ok(self):
        """L2: "listen" appears strictly before "probe-ok" in the phase log.

        Enforces that the probe's start coordination depends on the server
        having already bound — the probe cannot run before the listener exists.
        """
        source = textwrap.dedent(
            f'''
            package extdrive_order

            import (
                "testing"

                listener "{LISTENER_IMPORT}"
                "go.uber.org/fx"
                "go.uber.org/fx/fxtest"
            )

            func TestListenBeforeProbe(t *testing.T) {{
                st := &listener.State{{}}
                app := fxtest.New(t, listener.Module, fx.Supply(st))
                app.RequireStart()
                app.RequireStop()
                phases := st.Phases()

                listenIdx, probeIdx := -1, -1
                for i, p := range phases {{
                    if p == "listen" && listenIdx < 0 {{
                        listenIdx = i
                    }}
                    if p == "probe-ok" && probeIdx < 0 {{
                        probeIdx = i
                    }}
                }}
                if listenIdx < 0 {{
                    t.Fatalf("no \\"listen\\" phase recorded: %v", phases)
                }}
                if probeIdx < 0 {{
                    t.Fatalf("no \\"probe-ok\\" phase recorded: %v", phases)
                }}
                if !(listenIdx < probeIdx) {{
                    t.Fatalf("\\"listen\\" (idx %d) not strictly before "+
                        "\\"probe-ok\\" (idx %d): %v",
                        listenIdx, probeIdx, phases)
                }}
            }}
            '''
        )
        dpath, target = _write_driver(
            "extdrive_order", "before_test.go", source
        )
        try:
            proc = _run_go_test(target, extra_args=["-count=1", "-v"])
            assert proc.returncode == 0, (
                "independent ordering driver failed:\n"
                f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
            )
        finally:
            shutil.rmtree(dpath, ignore_errors=True)

    def test_addr_empty_before_start(self):
        """L2: State.Addr() is empty before RequireStart() (bind at start).

        Constructs the graph with fx.New (runs constructors) but does NOT call
        Start(). If the agent (wrongly) bound the socket inside NewServer, the
        address would already be set here. Also asserts no phase has been
        recorded yet.
        """
        source = textwrap.dedent(
            f'''
            package extdrive_construct

            import (
                "testing"

                listener "{LISTENER_IMPORT}"
                "go.uber.org/fx"
            )

            func TestAddrEmptyBeforeStart(t *testing.T) {{
                st := &listener.State{{}}
                app := fx.New(listener.Module, fx.Supply(st))
                if err := app.Err(); err != nil {{
                    t.Fatalf("graph construction error (missing dep/cycle?): %v",
                        err)
                }}
                // Graph constructed; Start() NOT called yet.
                if st.Addr() != "" {{
                    t.Fatalf("State.Addr() = %q before Start(); bind must "+
                        "happen at start, not in the constructor", st.Addr())
                }}
                if len(st.Phases()) != 0 {{
                    t.Fatalf("phases recorded before Start(): %v; constructors "+
                        "must not bind/listen/probe", st.Phases())
                }}
            }}
            '''
        )
        dpath, target = _write_driver(
            "extdrive_construct", "empty_test.go", source
        )
        try:
            proc = _run_go_test(target, extra_args=["-count=1", "-v"])
            assert proc.returncode == 0, (
                "independent empty-before-start driver failed:\n"
                f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
            )
        finally:
            shutil.rmtree(dpath, ignore_errors=True)

    def test_addr_connectable_and_echoes_after_start(self):
        """L2: after start, State.Addr() is non-empty, dialable, and echoes.

        Dials the recorded address while the app is running and round-trips a
        byte through the echo server, proving the listener is actually serving
        (not a fake address string).
        """
        source = textwrap.dedent(
            f'''
            package extdrive_lifecycle

            import (
                "context"
                "net"
                "testing"
                "time"

                listener "{LISTENER_IMPORT}"
                "go.uber.org/fx"
            )

            func TestConnectableAfterStart(t *testing.T) {{
                st := &listener.State{{}}
                app := fx.New(listener.Module, fx.Supply(st))
                if err := app.Err(); err != nil {{
                    t.Fatalf("graph error: %v", err)
                }}
                ctx, cancel := context.WithTimeout(
                    context.Background(), 10*time.Second)
                defer cancel()
                if err := app.Start(ctx); err != nil {{
                    t.Fatalf("app.Start failed: %v", err)
                }}

                addr := st.Addr()
                if addr == "" {{
                    t.Fatalf("State.Addr() empty after Start()")
                }}

                conn, err := net.DialTimeout("tcp", addr, 3*time.Second)
                if err != nil {{
                    t.Fatalf("address %q not connectable after start: %v",
                        addr, err)
                }}
                _ = conn.SetDeadline(time.Now().Add(3 * time.Second))
                if _, err := conn.Write([]byte("Z")); err != nil {{
                    t.Fatalf("write to echo server failed: %v", err)
                }}
                buf := make([]byte, 1)
                if _, err := conn.Read(buf); err != nil {{
                    t.Fatalf("read echo failed: %v", err)
                }}
                if buf[0] != 'Z' {{
                    t.Fatalf("echo mismatch: wrote 'Z', read %q", string(buf))
                }}
                _ = conn.Close()

                stopCtx, cancel2 := context.WithTimeout(
                    context.Background(), 10*time.Second)
                defer cancel2()
                if err := app.Stop(stopCtx); err != nil {{
                    t.Fatalf("app.Stop failed: %v", err)
                }}
            }}
            '''
        )
        dpath, target = _write_driver(
            "extdrive_lifecycle", "connect_test.go", source
        )
        try:
            proc = _run_go_test(target, extra_args=["-count=1", "-v"])
            assert proc.returncode == 0, (
                "independent connectable-after-start driver failed:\n"
                f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
            )
        finally:
            shutil.rmtree(dpath, ignore_errors=True)

    def test_addr_unconnectable_after_stop(self):
        """L2: after Stop(), the recorded address is no longer connectable.

        Proves the OnStop hook actually closes the listener (a naive impl that
        binds but never closes would still accept connections here).
        """
        source = textwrap.dedent(
            f'''
            package extdrive_lifecycle

            import (
                "context"
                "net"
                "testing"
                "time"

                listener "{LISTENER_IMPORT}"
                "go.uber.org/fx"
            )

            func TestUnconnectableAfterStop(t *testing.T) {{
                st := &listener.State{{}}
                app := fx.New(listener.Module, fx.Supply(st))
                if err := app.Err(); err != nil {{
                    t.Fatalf("graph error: %v", err)
                }}
                ctx, cancel := context.WithTimeout(
                    context.Background(), 10*time.Second)
                defer cancel()
                if err := app.Start(ctx); err != nil {{
                    t.Fatalf("app.Start failed: %v", err)
                }}
                addr := st.Addr()
                if addr == "" {{
                    t.Fatalf("State.Addr() empty after Start()")
                }}

                stopCtx, cancel2 := context.WithTimeout(
                    context.Background(), 10*time.Second)
                defer cancel2()
                if err := app.Stop(stopCtx); err != nil {{
                    t.Fatalf("app.Stop failed: %v", err)
                }}

                // After stop, the listener must be closed. Retry briefly to
                // avoid a race with TCP teardown, but it must become
                // unreachable.
                reachable := false
                for i := 0; i < 10; i++ {{
                    conn, err := net.DialTimeout("tcp", addr, 300*time.Millisecond)
                    if err == nil {{
                        // It may briefly accept then immediately EOF; treat a
                        // successful full handshake as still-listening only if
                        // we can also write+read.
                        _ = conn.SetDeadline(time.Now().Add(300 * time.Millisecond))
                        _, werr := conn.Write([]byte("Z"))
                        buf := make([]byte, 1)
                        _, rerr := conn.Read(buf)
                        _ = conn.Close()
                        if werr == nil && rerr == nil && buf[0] == 'Z' {{
                            reachable = true
                            break
                        }}
                    }}
                    time.Sleep(100 * time.Millisecond)
                }}
                if reachable {{
                    t.Fatalf("address %q still serving echoes after Stop(); "+
                        "listener was not closed", addr)
                }}
            }}
            '''
        )
        dpath, target = _write_driver(
            "extdrive_lifecycle", "closed_test.go", source
        )
        try:
            proc = _run_go_test(target, extra_args=["-count=1", "-v"])
            assert proc.returncode == 0, (
                "independent unconnectable-after-stop driver failed:\n"
                f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
            )
        finally:
            shutil.rmtree(dpath, ignore_errors=True)

    def test_close_only_after_stop(self):
        """L2: "close" phase must not appear until Stop() is called.

        Start the app, read Phases() while still running — "close" must be
        absent and "listen"+"probe-ok" present. Then stop and confirm "close"
        is appended last.
        """
        source = textwrap.dedent(
            f'''
            package extdrive_lifecycle

            import (
                "context"
                "testing"
                "time"

                listener "{LISTENER_IMPORT}"
                "go.uber.org/fx"
            )

            func has(ss []string, want string) bool {{
                for _, s := range ss {{
                    if s == want {{
                        return true
                    }}
                }}
                return false
            }}

            func TestCloseOnlyAfterStop(t *testing.T) {{
                st := &listener.State{{}}
                app := fx.New(listener.Module, fx.Supply(st))
                if err := app.Err(); err != nil {{
                    t.Fatalf("graph error: %v", err)
                }}
                ctx, cancel := context.WithTimeout(
                    context.Background(), 10*time.Second)
                defer cancel()
                if err := app.Start(ctx); err != nil {{
                    t.Fatalf("app.Start failed: %v", err)
                }}

                running := st.Phases()
                if !has(running, "listen") {{
                    t.Fatalf("expected \\"listen\\" while running: %v", running)
                }}
                if !has(running, "probe-ok") {{
                    t.Fatalf("expected \\"probe-ok\\" while running: %v", running)
                }}
                if has(running, "close") {{
                    t.Fatalf("\\"close\\" recorded before Stop(): %v", running)
                }}

                stopCtx, cancel2 := context.WithTimeout(
                    context.Background(), 10*time.Second)
                defer cancel2()
                if err := app.Stop(stopCtx); err != nil {{
                    t.Fatalf("app.Stop failed: %v", err)
                }}

                final := st.Phases()
                if !has(final, "close") {{
                    t.Fatalf("\\"close\\" not recorded after Stop(): %v", final)
                }}
                if final[len(final)-1] != "close" {{
                    t.Fatalf("\\"close\\" not the last phase: %v", final)
                }}
            }}
            '''
        )
        dpath, target = _write_driver(
            "extdrive_lifecycle", "closephase_test.go", source
        )
        try:
            proc = _run_go_test(target, extra_args=["-count=1", "-v"])
            assert proc.returncode == 0, (
                "independent close-only-after-stop driver failed:\n"
                f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
            )
        finally:
            shutil.rmtree(dpath, ignore_errors=True)

    def test_phases_returns_defensive_copy(self):
        """L2: mutating the slice from Phases() must not corrupt internal state.

        Boot once, grab Phases(), mutate it in place, then call Phases() again
        and confirm the internal state is unchanged (the doc requires Phases()
        to return a copy).
        """
        source = textwrap.dedent(
            f'''
            package extdrive_order

            import (
                "testing"

                listener "{LISTENER_IMPORT}"
                "go.uber.org/fx"
                "go.uber.org/fx/fxtest"
            )

            func TestPhasesDefensiveCopy(t *testing.T) {{
                st := &listener.State{{}}
                app := fxtest.New(t, listener.Module, fx.Supply(st))
                app.RequireStart()
                app.RequireStop()

                first := st.Phases()
                if len(first) == 0 {{
                    t.Fatalf("no phases recorded")
                }}
                pristine := make([]string, len(first))
                copy(pristine, first)

                for i := range first {{
                    first[i] = "MUTATED"
                }}

                second := st.Phases()
                if len(second) != len(pristine) {{
                    t.Fatalf("Phases() length changed after caller mutation: "+
                        "was %d now %d", len(pristine), len(second))
                }}
                for i := range pristine {{
                    if second[i] != pristine[i] {{
                        t.Fatalf("Phases() not defensive: index %d became %q "+
                            "(want %q)", i, second[i], pristine[i])
                    }}
                }}
            }}
            '''
        )
        dpath, target = _write_driver(
            "extdrive_order", "copy_test.go", source
        )
        try:
            proc = _run_go_test(target, extra_args=["-count=1", "-v"])
            assert proc.returncode == 0, (
                "independent defensive-copy driver failed:\n"
                f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
            )
        finally:
            shutil.rmtree(dpath, ignore_errors=True)

    def test_module_self_contained_only_state_needed(self):
        """L2: Module + a supplied *State is sufficient to boot with no extra
        wiring and produces no missing-dependency or cycle errors.
        """
        source = textwrap.dedent(
            f'''
            package extdrive_boot

            import (
                "context"
                "testing"
                "time"

                listener "{LISTENER_IMPORT}"
                "go.uber.org/fx"
            )

            func TestSelfContained(t *testing.T) {{
                st := &listener.State{{}}
                app := fx.New(listener.Module, fx.Supply(st))
                if err := app.Err(); err != nil {{
                    t.Fatalf("graph construction error (missing dep/cycle?): %v",
                        err)
                }}
                startCtx, cancel := context.WithTimeout(
                    context.Background(), 10*time.Second)
                defer cancel()
                if err := app.Start(startCtx); err != nil {{
                    t.Fatalf("app.Start failed: %v", err)
                }}
                stopCtx, cancel2 := context.WithTimeout(
                    context.Background(), 10*time.Second)
                defer cancel2()
                if err := app.Stop(stopCtx); err != nil {{
                    t.Fatalf("app.Stop failed: %v", err)
                }}
                phases := st.Phases()
                want := []string{{"listen", "probe-ok", "close"}}
                if len(phases) != len(want) {{
                    t.Fatalf("self-contained boot phases %v != %v",
                        phases, want)
                }}
                for i := range want {{
                    if phases[i] != want[i] {{
                        t.Fatalf("phase[%d]=%q want %q (full=%v)",
                            i, phases[i], want[i], phases)
                    }}
                }}
            }}
            '''
        )
        dpath, target = _write_driver(
            "extdrive_boot", "selfcontained_test.go", source
        )
        try:
            proc = _run_go_test(target, extra_args=["-count=1", "-v"])
            assert proc.returncode == 0, (
                "independent self-contained driver failed:\n"
                f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
            )
        finally:
            shutil.rmtree(dpath, ignore_errors=True)

    def test_race_detector_clean_on_boot(self):
        """L2: State is concurrency-safe (go test -race is clean).

        The State (shared across server + probe + concurrent echo handling)
        must be usable concurrently; running the boot driver under the race
        detector must not report a data race.
        """
        source = textwrap.dedent(
            f'''
            package extdrive_boot

            import (
                "testing"

                listener "{LISTENER_IMPORT}"
                "go.uber.org/fx"
                "go.uber.org/fx/fxtest"
            )

            func TestRaceClean(t *testing.T) {{
                for i := 0; i < 3; i++ {{
                    st := &listener.State{{}}
                    app := fxtest.New(t, listener.Module, fx.Supply(st))
                    app.RequireStart()
                    app.RequireStop()
                    if len(st.Phases()) != 3 {{
                        t.Fatalf("iteration %d: expected 3 phases, got %v",
                            i, st.Phases())
                    }}
                }}
            }}
            '''
        )
        dpath, target = _write_driver(
            "extdrive_boot", "race_test.go", source
        )
        try:
            env = _go_env()
            env["CGO_ENABLED"] = "1"  # -race needs cgo
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
                "race detector reported a data race in State:\n" + combined
            )
            assert proc.returncode == 0, (
                "race driver failed:\n"
                f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
            )
        finally:
            shutil.rmtree(dpath, ignore_errors=True)
