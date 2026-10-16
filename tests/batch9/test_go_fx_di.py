"""Tests for the `go-fx-di` skill task (variant ext9): a worker-pool example
with reverse-order graceful drain.

Skill under test: go-fx-di (uber-go/fx dependency injection + lifecycle
coordination).

The task asks the agent to create a new `workerpool` package under
`docs/ex/workerpool/` inside the `go.uber.org/fx/docs` module. The package must
expose an exported `Trace` struct (concurrency-safe, with `Add(string)` and
`Events() []string` returning a defensive copy) and a `Module` (`fx.Option`)
wiring a bounded queue, a pool of workers that drain it, and a producer.

Booting `Module` with a supplied `*Trace` and running the full lifecycle must:

  * bring components up in dependency order, appending the start subsequence
    ["queue:start", "workers:start", "producer:start"];
  * have the producer enqueue exactly N == 4 deterministic items at start, with
    the worker pool draining them so that EXACTLY 4 "job:done" events appear;
  * shut down in the exact REVERSE of start order, appending the stop
    subsequence ["producer:stop", "workers:stop", "queue:stop"];
  * never spawn goroutines / open resources from a constructor body (so before
    Start() no "job:done" may appear).

Verification strategy: rather than trusting the agent's own
`workerpool_test.go`, the L2 tests write INDEPENDENT Go driver test files into
fresh sub-directories of the `workerpool` package and run them with the native
`go test` toolchain (from the `docs` module). These drivers boot the real
`Module` via `fxtest`, poll `tr.Events()` deterministically (bounded timeout,
no racy fixed sleep) until 4 "job:done" events appear, then RequireStop() and
assert deeply on the recorded event order/counts. A naive implementation that
does work in constructors, hardcodes events, loses items, or shuts down in the
wrong order cannot pass.

The native acceptance command this drives:  cd docs && go test -race ./ex/workerpool/...
"""

import os
import shutil
import subprocess
import textwrap

import pytest

REPO_DIR = "/workspace/fx"
DOCS_DIR = os.path.join(REPO_DIR, "docs")
PKG_DIR = os.path.join(DOCS_DIR, "ex", "workerpool")

GO_TEST_TIMEOUT = 480

# The import path of the workerpool package and the expected item count.
WORKERPOOL_IMPORT = "go.uber.org/fx/docs/ex/workerpool"
EXPECTED_N = 4


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
    target = "./ex/workerpool/" + subdir_name + "/..."
    return dpath, target


# A reusable Go helper block (poll-until-N-done) shared by drivers. It boots
# the real Module, RequireStart, polls tr.Events() until EXPECTED_N "job:done"
# events appear (bounded; no racy fixed sleep), then RequireStop and returns the
# final event slice.
_BOOT_AND_DRAIN_HELPER = '''
// bootDrainAndStop boots workerpool.Module with a fresh *Trace, starts it,
// waits deterministically (bounded) until {n} "job:done" events are recorded,
// then stops it and returns the final event list.
func bootDrainAndStop(t *testing.T, extra ...fx.Option) []string {{
    tr := &workerpool.Trace{{}}
    opts := append([]fx.Option{{workerpool.Module, fx.Supply(tr)}}, extra...)
    app := fxtest.New(t, opts...)
    app.RequireStart()

    deadline := time.Now().Add(10 * time.Second)
    for {{
        done := 0
        for _, e := range tr.Events() {{
            if e == "job:done" {{
                done++
            }}
        }}
        if done >= {n} {{
            break
        }}
        if time.Now().After(deadline) {{
            t.Fatalf("timed out waiting for {n} job:done events; got %d: %v",
                done, tr.Events())
        }}
        time.Sleep(2 * time.Millisecond)
    }}
    app.RequireStop()
    return tr.Events()
}}
'''


# --------------------------------------------------------------------------- #
# Dependency / build readiness (module-scope, autouse)
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module", autouse=True)
def _ensure_go_ready():
    """Ensure the Go toolchain + docs module deps are available, warming the
    build/module cache once before per-test timeouts apply."""
    assert os.path.isdir(REPO_DIR), f"missing repo dir {REPO_DIR}"
    assert os.path.isdir(DOCS_DIR), f"missing docs module dir {DOCS_DIR}"
    try:
        subprocess.run(
            ["go", "build", "./ex/workerpool/..."],
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
        "extdrive_count",
        "extdrive_copy",
        "extdrive_preboot",
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
        """L1: the workerpool example directory exists under docs/ex."""
        assert os.path.isdir(PKG_DIR), f"expected package dir at {PKG_DIR}"

    def test_required_source_files_present(self):
        """L1: required deliverable .go source files all exist."""
        for fname in ("queue.go", "worker.go", "producer.go", "app.go"):
            fpath = os.path.join(PKG_DIR, fname)
            assert os.path.isfile(fpath), f"missing required file {fpath}"

    def test_package_uses_workerpool_name_and_no_new_module(self):
        """L1: files declare `package workerpool`; no new go.mod was added."""
        go_files = [f for f in os.listdir(PKG_DIR) if f.endswith(".go")]
        assert go_files, "no .go files found in package dir"
        for f in go_files:
            with open(os.path.join(PKG_DIR, f)) as fh:
                head = fh.read()
            assert "package workerpool" in head, (
                f"{f} does not declare `package workerpool`"
            )
        assert not os.path.isfile(os.path.join(PKG_DIR, "go.mod")), (
            "a new go.mod must NOT be created inside the example dir"
        )

    def test_package_compiles(self):
        """L1: the workerpool package compiles under the docs module."""
        proc = subprocess.run(
            ["go", "build", "./ex/workerpool/..."],
            cwd=DOCS_DIR,
            capture_output=True,
            text=True,
            timeout=GO_TEST_TIMEOUT,
            env=_go_env(),
        )
        assert proc.returncode == 0, (
            "workerpool package failed to compile:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    def test_authors_own_test_passes(self):
        """L1: the task's native command passes for this package (with -race)."""
        # Prefer the documented -race form; fall back to plain go test if the
        # container lacks a cgo toolchain for the race detector.
        env = _go_env()
        env["CGO_ENABLED"] = "1"
        proc = subprocess.run(
            ["go", "test", "-race", "./ex/workerpool/..."],
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
            proc = _run_go_test("./ex/workerpool/...")
        assert proc.returncode == 0, (
            "`go test -race ./ex/workerpool/...` failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    # ------------------------------------------------------------------ #
    # L2 — independent dynamic execution against the real Module
    # ------------------------------------------------------------------ #
    def test_module_boots_and_drains_n_jobs(self):
        """L2: booting Module via fxtest drains exactly N=4 jobs.

        Independent driver: supply a fresh *Trace, RequireStart, poll Events()
        deterministically until 4 "job:done" appear, RequireStop, then assert
        EXACTLY 4 "job:done" events (no more, no fewer) so a producer that
        enqueues the wrong count or a pool that double-processes/loses items
        fails.
        """
        helper = _BOOT_AND_DRAIN_HELPER.format(n=EXPECTED_N)
        source = textwrap.dedent(
            f'''
            package extdrive_boot

            import (
                "testing"
                "time"

                workerpool "{WORKERPOOL_IMPORT}"
                "go.uber.org/fx"
                "go.uber.org/fx/fxtest"
            )
            {helper}
            func TestDrainsExactlyN(t *testing.T) {{
                events := bootDrainAndStop(t)
                done := 0
                for _, e := range events {{
                    if e == "job:done" {{
                        done++
                    }}
                }}
                if done != {EXPECTED_N} {{
                    t.Fatalf("expected exactly {EXPECTED_N} job:done events, "+
                        "got %d in %v", done, events)
                }}
            }}
            '''
        )
        dpath, target = _write_driver("extdrive_boot", "boot_test.go", source)
        try:
            proc = _run_go_test(target, extra_args=["-count=1", "-v"])
            assert proc.returncode == 0, (
                "independent drain driver failed:\n"
                f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
            )
            assert "TestDrainsExactlyN" in proc.stdout
        finally:
            shutil.rmtree(dpath, ignore_errors=True)

    def test_start_subsequence_is_queue_workers_producer(self):
        """L2: the start lifecycle subsequence is exactly
        ["queue:start","workers:start","producer:start"] in that order.

        Filters the recorded events down to the three start markers and asserts
        their relative order, enforcing dependency-ordered boot. A solution that
        starts components in constructor order or out of dependency order fails.
        """
        helper = _BOOT_AND_DRAIN_HELPER.format(n=EXPECTED_N)
        source = textwrap.dedent(
            f'''
            package extdrive_order

            import (
                "reflect"
                "strings"
                "testing"
                "time"

                workerpool "{WORKERPOOL_IMPORT}"
                "go.uber.org/fx"
                "go.uber.org/fx/fxtest"
            )
            {helper}
            func TestStartSubsequence(t *testing.T) {{
                events := bootDrainAndStop(t)
                want := []string{{"queue:start", "workers:start", "producer:start"}}
                wantSet := map[string]bool{{
                    "queue:start": true, "workers:start": true,
                    "producer:start": true,
                }}
                var got []string
                for _, e := range events {{
                    if strings.HasSuffix(e, ":start") && wantSet[e] {{
                        got = append(got, e)
                    }}
                }}
                if !reflect.DeepEqual(got, want) {{
                    t.Fatalf("start subsequence mismatch: got %v want %v "+
                        "(all events: %v)", got, want, events)
                }}
            }}
            '''
        )
        dpath, target = _write_driver("extdrive_order", "start_test.go", source)
        try:
            proc = _run_go_test(target, extra_args=["-count=1", "-v"])
            assert proc.returncode == 0, (
                "independent start-order driver failed:\n"
                f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
            )
        finally:
            shutil.rmtree(dpath, ignore_errors=True)

    def test_stop_subsequence_is_reverse_of_start(self):
        """L2: the stop subsequence is the EXACT reverse of the start
        subsequence: ["producer:stop","workers:stop","queue:stop"].

        This is the core reverse-order graceful-drain invariant. It is derived
        dynamically from the actual recorded start markers (not hardcoded), so
        any non-reversed shutdown ordering fails.
        """
        helper = _BOOT_AND_DRAIN_HELPER.format(n=EXPECTED_N)
        source = textwrap.dedent(
            f'''
            package extdrive_order

            import (
                "reflect"
                "strings"
                "testing"
                "time"

                workerpool "{WORKERPOOL_IMPORT}"
                "go.uber.org/fx"
                "go.uber.org/fx/fxtest"
            )
            {helper}
            func TestStopReverseOfStart(t *testing.T) {{
                events := bootDrainAndStop(t)
                var starts, stops []string
                for _, e := range events {{
                    switch {{
                    case strings.HasSuffix(e, ":start"):
                        starts = append(starts, strings.TrimSuffix(e, ":start"))
                    case strings.HasSuffix(e, ":stop"):
                        stops = append(stops, strings.TrimSuffix(e, ":stop"))
                    }}
                }}
                if len(starts) != 3 {{
                    t.Fatalf("expected 3 start markers, got %d: %v",
                        len(starts), events)
                }}
                if len(starts) != len(stops) {{
                    t.Fatalf("start count %d != stop count %d: %v",
                        len(starts), len(stops), events)
                }}
                // build expected reverse of the actual start names
                wantStop := make([]string, len(starts))
                for i := range starts {{
                    wantStop[i] = starts[len(starts)-1-i]
                }}
                if !reflect.DeepEqual(stops, wantStop) {{
                    t.Fatalf("stop order not reverse of start: starts=%v "+
                        "stops=%v wantStop=%v", starts, stops, wantStop)
                }}
                // and the absolute expected ordering for this task
                wantAbs := []string{{"producer", "workers", "queue"}}
                if !reflect.DeepEqual(stops, wantAbs) {{
                    t.Fatalf("stop subsequence %v != expected %v (events=%v)",
                        stops, wantAbs, events)
                }}
            }}
            '''
        )
        dpath, target = _write_driver(
            "extdrive_order", "reverse_test.go", source
        )
        try:
            proc = _run_go_test(target, extra_args=["-count=1", "-v"])
            assert proc.returncode == 0, (
                "independent reverse-order driver failed:\n"
                f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
            )
        finally:
            shutil.rmtree(dpath, ignore_errors=True)

    def test_all_workers_exit_before_queue_stop(self):
        """L2: every "job:done" is recorded before "queue:stop".

        The drain must be clean: no item lost, no worker goroutine still
        processing after the queue is torn down. We assert that the index of
        "queue:stop" is strictly greater than the index of the last "job:done",
        and that exactly N job:done precede it. A pool that leaks goroutines or
        stops the queue mid-drain fails.
        """
        helper = _BOOT_AND_DRAIN_HELPER.format(n=EXPECTED_N)
        source = textwrap.dedent(
            f'''
            package extdrive_order

            import (
                "testing"
                "time"

                workerpool "{WORKERPOOL_IMPORT}"
                "go.uber.org/fx"
                "go.uber.org/fx/fxtest"
            )
            {helper}
            func TestWorkersExitBeforeQueueStop(t *testing.T) {{
                events := bootDrainAndStop(t)
                lastDone := -1
                queueStop := -1
                done := 0
                for i, e := range events {{
                    switch e {{
                    case "job:done":
                        done++
                        lastDone = i
                    case "queue:stop":
                        queueStop = i
                    }}
                }}
                if done != {EXPECTED_N} {{
                    t.Fatalf("expected {EXPECTED_N} job:done, got %d: %v",
                        done, events)
                }}
                if queueStop < 0 {{
                    t.Fatalf("no queue:stop event recorded: %v", events)
                }}
                if lastDone < 0 {{
                    t.Fatalf("no job:done event recorded: %v", events)
                }}
                if !(lastDone < queueStop) {{
                    t.Fatalf("queue:stop (idx %d) not after last job:done "+
                        "(idx %d); drain not clean: %v",
                        queueStop, lastDone, events)
                }}
            }}
            '''
        )
        dpath, target = _write_driver(
            "extdrive_order", "drainclean_test.go", source
        )
        try:
            proc = _run_go_test(target, extra_args=["-count=1", "-v"])
            assert proc.returncode == 0, (
                "independent clean-drain driver failed:\n"
                f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
            )
        finally:
            shutil.rmtree(dpath, ignore_errors=True)

    def test_jobs_done_strictly_after_producer_start(self):
        """L2: no "job:done" appears before "producer:start".

        The producer enqueues at start; items cannot be processed before the
        producer has begun enqueuing. Asserts the first job:done index is
        greater than the producer:start index, catching solutions that
        pre-seed/process work out of lifecycle order.
        """
        helper = _BOOT_AND_DRAIN_HELPER.format(n=EXPECTED_N)
        source = textwrap.dedent(
            f'''
            package extdrive_order

            import (
                "testing"
                "time"

                workerpool "{WORKERPOOL_IMPORT}"
                "go.uber.org/fx"
                "go.uber.org/fx/fxtest"
            )
            {helper}
            func TestDoneAfterProducerStart(t *testing.T) {{
                events := bootDrainAndStop(t)
                prodStart := -1
                firstDone := -1
                for i, e := range events {{
                    if e == "producer:start" && prodStart < 0 {{
                        prodStart = i
                    }}
                    if e == "job:done" && firstDone < 0 {{
                        firstDone = i
                    }}
                }}
                if prodStart < 0 {{
                    t.Fatalf("no producer:start event: %v", events)
                }}
                if firstDone < 0 {{
                    t.Fatalf("no job:done event: %v", events)
                }}
                if !(prodStart < firstDone) {{
                    t.Fatalf("job:done (idx %d) appeared before producer:start "+
                        "(idx %d): %v", firstDone, prodStart, events)
                }}
            }}
            '''
        )
        dpath, target = _write_driver(
            "extdrive_order", "doneorder_test.go", source
        )
        try:
            proc = _run_go_test(target, extra_args=["-count=1", "-v"])
            assert proc.returncode == 0, (
                "independent done-order driver failed:\n"
                f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
            )
        finally:
            shutil.rmtree(dpath, ignore_errors=True)

    def test_no_work_done_before_start_constructor_purity(self):
        """L2: no "job:done"/start/stop events exist before Start() is called.

        Constructs the graph with fx.New (runs all constructors) WITHOUT
        Start(). A correct implementation opens no resources and spawns no
        goroutines from constructor bodies, so NO "job:done", ":start", or
        ":stop" event may exist. This is the doc's explicit "naive
        implementation that does work in constructors must fail" check.
        """
        source = textwrap.dedent(
            f'''
            package extdrive_preboot

            import (
                "strings"
                "testing"

                workerpool "{WORKERPOOL_IMPORT}"
                "go.uber.org/fx"
            )

            func TestNoWorkBeforeStart(t *testing.T) {{
                tr := &workerpool.Trace{{}}
                app := fx.New(workerpool.Module, fx.Supply(tr))
                if err := app.Err(); err != nil {{
                    t.Fatalf("graph construction error (missing dep/cycle?): %v", err)
                }}
                // Graph constructed; Start() NOT called.
                for _, e := range tr.Events() {{
                    if e == "job:done" ||
                        strings.HasSuffix(e, ":start") ||
                        strings.HasSuffix(e, ":stop") {{
                        t.Fatalf("lifecycle side effect %q recorded before "+
                            "Start(); constructors must not do work. events=%v",
                            e, tr.Events())
                    }}
                }}
            }}
            '''
        )
        dpath, target = _write_driver(
            "extdrive_preboot", "preboot_test.go", source
        )
        try:
            proc = _run_go_test(target, extra_args=["-count=1", "-v"])
            assert proc.returncode == 0, (
                "independent constructor-purity driver failed:\n"
                f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
            )
        finally:
            shutil.rmtree(dpath, ignore_errors=True)

    def test_module_self_contained_only_trace_needed(self):
        """L2: Module + a supplied *Trace is sufficient to boot via fx.New.

        Uses fx.New (not fxtest) with bounded Start/Stop contexts to confirm no
        other wiring (no extra Provide/Supply) is required and the graph has no
        missing-dependency or cycle errors, then validates the full event
        invariants (start order, exactly N done, reverse stop order).
        """
        source = textwrap.dedent(
            f'''
            package extdrive_boot

            import (
                "context"
                "reflect"
                "strings"
                "testing"
                "time"

                workerpool "{WORKERPOOL_IMPORT}"
                "go.uber.org/fx"
            )

            func TestSelfContained(t *testing.T) {{
                tr := &workerpool.Trace{{}}
                app := fx.New(workerpool.Module, fx.Supply(tr))
                if err := app.Err(); err != nil {{
                    t.Fatalf("graph construction error (missing dep/cycle?): %v", err)
                }}
                startCtx, cancel := context.WithTimeout(
                    context.Background(), 10*time.Second)
                defer cancel()
                if err := app.Start(startCtx); err != nil {{
                    t.Fatalf("app.Start failed: %v", err)
                }}
                // Poll until N done before stopping.
                deadline := time.Now().Add(10 * time.Second)
                for {{
                    done := 0
                    for _, e := range tr.Events() {{
                        if e == "job:done" {{
                            done++
                        }}
                    }}
                    if done >= {EXPECTED_N} {{
                        break
                    }}
                    if time.Now().After(deadline) {{
                        t.Fatalf("timed out waiting for {EXPECTED_N} job:done: %v",
                            tr.Events())
                    }}
                    time.Sleep(2 * time.Millisecond)
                }}
                stopCtx, cancel2 := context.WithTimeout(
                    context.Background(), 10*time.Second)
                defer cancel2()
                if err := app.Stop(stopCtx); err != nil {{
                    t.Fatalf("app.Stop failed: %v", err)
                }}

                ev := tr.Events()
                var starts, stops []string
                done := 0
                for _, e := range ev {{
                    switch {{
                    case e == "job:done":
                        done++
                    case strings.HasSuffix(e, ":start"):
                        starts = append(starts, strings.TrimSuffix(e, ":start"))
                    case strings.HasSuffix(e, ":stop"):
                        stops = append(stops, strings.TrimSuffix(e, ":stop"))
                    }}
                }}
                if done != {EXPECTED_N} {{
                    t.Fatalf("expected {EXPECTED_N} job:done, got %d: %v", done, ev)
                }}
                if !reflect.DeepEqual(starts,
                    []string{{"queue", "workers", "producer"}}) {{
                    t.Fatalf("start order %v != [queue workers producer]: %v",
                        starts, ev)
                }}
                if !reflect.DeepEqual(stops,
                    []string{{"producer", "workers", "queue"}}) {{
                    t.Fatalf("stop order %v != [producer workers queue]: %v",
                        stops, ev)
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

    def test_trace_events_returns_defensive_copy(self):
        """L2: mutating the slice returned by Events() must not corrupt the
        Trace's internal state.

        Boots once, grabs Events(), mutates the returned slice in place, then
        calls Events() again and confirms the internal state is unchanged. A
        Trace that returns its backing slice directly fails.
        """
        source = textwrap.dedent(
            f'''
            package extdrive_copy

            import (
                "testing"
                "time"

                workerpool "{WORKERPOOL_IMPORT}"
                "go.uber.org/fx"
                "go.uber.org/fx/fxtest"
            )

            func TestEventsDefensiveCopy(t *testing.T) {{
                tr := &workerpool.Trace{{}}
                app := fxtest.New(t, workerpool.Module, fx.Supply(tr))
                app.RequireStart()
                deadline := time.Now().Add(10 * time.Second)
                for {{
                    done := 0
                    for _, e := range tr.Events() {{
                        if e == "job:done" {{
                            done++
                        }}
                    }}
                    if done >= {EXPECTED_N} {{
                        break
                    }}
                    if time.Now().After(deadline) {{
                        t.Fatalf("timed out: %v", tr.Events())
                    }}
                    time.Sleep(2 * time.Millisecond)
                }}
                app.RequireStop()

                first := tr.Events()
                if len(first) == 0 {{
                    t.Fatalf("no events recorded")
                }}
                pristine := make([]string, len(first))
                copy(pristine, first)
                for i := range first {{
                    first[i] = "MUTATED"
                }}
                second := tr.Events()
                if len(second) != len(pristine) {{
                    t.Fatalf("Events() length changed after caller mutation: "+
                        "was %d now %d", len(pristine), len(second))
                }}
                for i := range pristine {{
                    if second[i] != pristine[i] {{
                        t.Fatalf("Events() not defensive: index %d became %q "+
                            "(want %q)", i, second[i], pristine[i])
                    }}
                }}
            }}
            '''
        )
        dpath, target = _write_driver("extdrive_copy", "copy_test.go", source)
        try:
            proc = _run_go_test(target, extra_args=["-count=1", "-v"])
            assert proc.returncode == 0, (
                "independent defensive-copy driver failed:\n"
                f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
            )
        finally:
            shutil.rmtree(dpath, ignore_errors=True)

    def test_race_detector_clean_on_full_cycle(self):
        """L2: the Trace/queue/workers are concurrency-safe (go test -race).

        The task's native command uses -race precisely because workers drain
        concurrently. Running a full boot/drain/stop cycle under the race
        detector several times must not report a data race.
        """
        helper = _BOOT_AND_DRAIN_HELPER.format(n=EXPECTED_N)
        source = textwrap.dedent(
            f'''
            package extdrive_boot

            import (
                "testing"
                "time"

                workerpool "{WORKERPOOL_IMPORT}"
                "go.uber.org/fx"
                "go.uber.org/fx/fxtest"
            )
            {helper}
            func TestRaceClean(t *testing.T) {{
                for i := 0; i < 3; i++ {{
                    events := bootDrainAndStop(t)
                    done := 0
                    for _, e := range events {{
                        if e == "job:done" {{
                            done++
                        }}
                    }}
                    if done != {EXPECTED_N} {{
                        t.Fatalf("iteration %d: expected {EXPECTED_N} job:done, "+
                            "got %d: %v", i, done, events)
                    }}
                }}
            }}
            '''
        )
        dpath, target = _write_driver("extdrive_boot", "race_test.go", source)
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
                "race detector reported a data race:\n" + combined
            )
            assert proc.returncode == 0, (
                "race driver failed:\n"
                f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
            )
        finally:
            shutil.rmtree(dpath, ignore_errors=True)
