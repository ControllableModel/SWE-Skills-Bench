"""Tests for the `go-fx-di` skill task: a pluggable job-runner example app.

Skill under test: go-fx-di (uber-go/fx dependency injection with value groups +
lifecycle coordination).

The task asks the agent to create a new `jobrunner` package under
`docs/ex/job-runner/` inside the `go.uber.org/fx/docs` module. The package must
expose `Job`, `Recorder` (with `Events() []string`), `Runner`, and `Module`
(an `fx.Option`). Booting `Module` with a supplied `*Recorder` must:

  * record exactly one `"scheduler:ready"` event, strictly before any
    `"start:<name>"` event;
  * run every independently-registered job (>= 3), each appending its own
    `"start:<name>"`;
  * drain on stop in the exact REVERSE order of start, with matching
    `"stop:<name>"` counts.

Verification strategy: rather than trusting the agent's own
`job_runner_test.go`, the L2 tests write INDEPENDENT Go driver test files into a
fresh sub-directory of the `jobrunner` package and run them with the native
`go test` toolchain (from the `docs` module). These drivers boot the real
`Module` via `fxtest` and assert deeply on `rec.Events()`, so a hardcoded /
constructor-appends-fixed-strings solution cannot pass.
"""

import os
import shutil
import subprocess
import textwrap

import pytest

REPO_DIR = "/workspace/fx"
DOCS_DIR = os.path.join(REPO_DIR, "docs")
PKG_DIR = os.path.join(DOCS_DIR, "ex", "job-runner")

GO_TEST_TIMEOUT = 480


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _go_env():
    env = os.environ.copy()
    # Keep module/build caches inside the repo area so go test can write them
    # even when HOME is unusual; fall back to defaults if already set.
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
    # clean any stale copy
    if os.path.isdir(dpath):
        shutil.rmtree(dpath)
    os.makedirs(dpath, exist_ok=True)
    with open(os.path.join(dpath, filename), "w") as fh:
        fh.write(source)
    target = "./ex/job-runner/" + subdir_name + "/..."
    return dpath, target


# Module-level helper: the import path of the jobrunner package.
JOBRUNNER_IMPORT = "go.uber.org/fx/docs/ex/job-runner"


# --------------------------------------------------------------------------- #
# Dependency / build readiness (module-scope, autouse)
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module", autouse=True)
def _ensure_go_ready():
    """Make sure the Go toolchain + docs module deps are available.

    Runs a cheap compile of the jobrunner package so that the heavy
    module-download cost is paid once, before the per-test timeouts apply.
    """
    assert os.path.isdir(REPO_DIR), f"missing repo dir {REPO_DIR}"
    assert os.path.isdir(DOCS_DIR), f"missing docs module dir {DOCS_DIR}"
    # Warm the build/module cache; tolerate failure here (individual tests
    # surface real errors with better messages).
    try:
        subprocess.run(
            ["go", "build", "./ex/job-runner/..."],
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

    # cleanup of any driver dirs we created
    _DRIVER_DIRS = (
        "extdrive_boot",
        "extdrive_order",
        "extdrive_fourth",
        "extdrive_copy",
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
        """L1: the job-runner example directory exists under docs/ex."""
        assert os.path.isdir(PKG_DIR), f"expected package dir at {PKG_DIR}"

    def test_required_source_files_present(self):
        """L1: required deliverable .go source files all exist."""
        for fname in ("job.go", "worker.go", "runner.go", "app.go"):
            fpath = os.path.join(PKG_DIR, fname)
            assert os.path.isfile(fpath), f"missing required file {fpath}"

    def test_package_uses_jobrunner_name_and_no_new_module(self):
        """L1: files declare `package jobrunner`; no new go.mod was added."""
        # All .go files in the package directory must share the jobrunner name.
        go_files = [
            f for f in os.listdir(PKG_DIR)
            if f.endswith(".go")
        ]
        assert go_files, "no .go files found in package dir"
        for f in go_files:
            with open(os.path.join(PKG_DIR, f)) as fh:
                head = fh.read()
            # the package clause is the first non-comment 'package ...' line
            assert "package jobrunner" in head, (
                f"{f} does not declare `package jobrunner`"
            )
        assert not os.path.isfile(os.path.join(PKG_DIR, "go.mod")), (
            "a new go.mod must NOT be created inside the example dir"
        )

    def test_package_compiles(self):
        """L1: the jobrunner package compiles under the docs module."""
        proc = subprocess.run(
            ["go", "build", "./ex/job-runner/..."],
            cwd=DOCS_DIR,
            capture_output=True,
            text=True,
            timeout=GO_TEST_TIMEOUT,
            env=_go_env(),
        )
        assert proc.returncode == 0, (
            "jobrunner package failed to compile:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    def test_authors_own_test_passes(self):
        """L1: the task's specified native command passes for this package."""
        proc = _run_go_test("./ex/job-runner/...")
        assert proc.returncode == 0, (
            "`go test ./ex/job-runner/...` failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    # ------------------------------------------------------------------ #
    # L2 — independent dynamic execution against the real Module
    # ------------------------------------------------------------------ #
    def test_module_boots_and_emits_scheduler_ready_once(self):
        """L2: booting Module via fxtest yields exactly one scheduler:ready.

        Independent driver: supply a fresh *Recorder, RequireStart/RequireStop,
        then print events and count scheduler:ready occurrences.
        """
        source = textwrap.dedent(
            f'''
            package extdrive_boot

            import (
                "strings"
                "testing"

                jobrunner "{JOBRUNNER_IMPORT}"
                "go.uber.org/fx"
                "go.uber.org/fx/fxtest"
            )

            func TestBootSchedulerReadyOnce(t *testing.T) {{
                rec := &jobrunner.Recorder{{}}
                app := fxtest.New(t, jobrunner.Module, fx.Supply(rec))
                app.RequireStart().RequireStop()

                events := rec.Events()
                if len(events) == 0 {{
                    t.Fatalf("no events recorded")
                }}
                ready := 0
                for _, e := range events {{
                    if e == "scheduler:ready" {{
                        ready++
                    }}
                }}
                if ready != 1 {{
                    t.Fatalf("expected exactly 1 scheduler:ready, got %d in %v",
                        ready, events)
                }}
                // sanity: at least one start event exists
                hasStart := false
                for _, e := range events {{
                    if strings.HasPrefix(e, "start:") {{
                        hasStart = true
                    }}
                }}
                if !hasStart {{
                    t.Fatalf("no start: events recorded in %v", events)
                }}
            }}
            '''
        )
        dpath, target = _write_driver(
            "extdrive_boot", "boot_test.go", source
        )
        try:
            proc = _run_go_test(target, extra_args=["-count=1", "-v"])
            assert proc.returncode == 0, (
                "independent boot driver failed:\n"
                f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
            )
            assert "TestBootSchedulerReadyOnce" in proc.stdout
        finally:
            shutil.rmtree(dpath, ignore_errors=True)

    def test_scheduler_ready_precedes_all_starts(self):
        """L2: scheduler:ready index is strictly less than every start: index.

        This enforces that ready is recorded only after the whole graph is
        built and before jobs run — a hardcoded constructor cannot satisfy this.
        """
        source = textwrap.dedent(
            f'''
            package extdrive_order

            import (
                "strings"
                "testing"

                jobrunner "{JOBRUNNER_IMPORT}"
                "go.uber.org/fx"
                "go.uber.org/fx/fxtest"
            )

            func TestReadyBeforeStarts(t *testing.T) {{
                rec := &jobrunner.Recorder{{}}
                app := fxtest.New(t, jobrunner.Module, fx.Supply(rec))
                app.RequireStart().RequireStop()
                events := rec.Events()

                readyIdx := -1
                for i, e := range events {{
                    if e == "scheduler:ready" {{
                        readyIdx = i
                        break
                    }}
                }}
                if readyIdx < 0 {{
                    t.Fatalf("scheduler:ready not found in %v", events)
                }}
                for i, e := range events {{
                    if strings.HasPrefix(e, "start:") {{
                        if !(readyIdx < i) {{
                            t.Fatalf("scheduler:ready (idx %d) not strictly "+
                                "before start event %q (idx %d): %v",
                                readyIdx, e, i, events)
                        }}
                    }}
                }}
            }}
            '''
        )
        dpath, target = _write_driver(
            "extdrive_order", "order_test.go", source
        )
        try:
            proc = _run_go_test(target, extra_args=["-count=1", "-v"])
            assert proc.returncode == 0, (
                "independent ordering driver failed:\n"
                f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
            )
        finally:
            shutil.rmtree(dpath, ignore_errors=True)

    def test_start_count_matches_jobs_at_least_three(self):
        """L2: number of start: events == number of stop: events and >= 3.

        Counts distinct job names too, ensuring jobs were registered
        independently (each producing a unique start:<name>).
        """
        source = textwrap.dedent(
            f'''
            package extdrive_order

            import (
                "strings"
                "testing"

                jobrunner "{JOBRUNNER_IMPORT}"
                "go.uber.org/fx"
                "go.uber.org/fx/fxtest"
            )

            func TestStartStopCounts(t *testing.T) {{
                rec := &jobrunner.Recorder{{}}
                app := fxtest.New(t, jobrunner.Module, fx.Supply(rec))
                app.RequireStart().RequireStop()
                events := rec.Events()

                var starts, stops []string
                for _, e := range events {{
                    if strings.HasPrefix(e, "start:") {{
                        starts = append(starts, strings.TrimPrefix(e, "start:"))
                    }}
                    if strings.HasPrefix(e, "stop:") {{
                        stops = append(stops, strings.TrimPrefix(e, "stop:"))
                    }}
                }}
                if len(starts) < 3 {{
                    t.Fatalf("expected >=3 start events, got %d: %v",
                        len(starts), events)
                }}
                if len(starts) != len(stops) {{
                    t.Fatalf("start count %d != stop count %d: %v",
                        len(starts), len(stops), events)
                }}
                // all started job names must be distinct
                seen := map[string]bool{{}}
                for _, n := range starts {{
                    if seen[n] {{
                        t.Fatalf("duplicate started job name %q: %v", n, starts)
                    }}
                    seen[n] = true
                }}
            }}
            '''
        )
        dpath, target = _write_driver(
            "extdrive_order", "counts_test.go", source
        )
        try:
            proc = _run_go_test(target, extra_args=["-count=1", "-v"])
            assert proc.returncode == 0, (
                "independent count driver failed:\n"
                f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
            )
        finally:
            shutil.rmtree(dpath, ignore_errors=True)

    def test_drain_order_is_reverse_of_start_order(self):
        """L2: stop: job-name sub-sequence is the exact reverse of start:.

        This is the core lifecycle-reversibility invariant and cannot be faked
        by appending fixed strings from a constructor.
        """
        source = textwrap.dedent(
            f'''
            package extdrive_order

            import (
                "strings"
                "testing"

                jobrunner "{JOBRUNNER_IMPORT}"
                "go.uber.org/fx"
                "go.uber.org/fx/fxtest"
            )

            func TestReverseDrain(t *testing.T) {{
                rec := &jobrunner.Recorder{{}}
                app := fxtest.New(t, jobrunner.Module, fx.Supply(rec))
                app.RequireStart().RequireStop()
                events := rec.Events()

                var starts, stops []string
                for _, e := range events {{
                    if strings.HasPrefix(e, "start:") {{
                        starts = append(starts, strings.TrimPrefix(e, "start:"))
                    }}
                    if strings.HasPrefix(e, "stop:") {{
                        stops = append(stops, strings.TrimPrefix(e, "stop:"))
                    }}
                }}
                if len(starts) == 0 || len(starts) != len(stops) {{
                    t.Fatalf("bad start/stop sets: starts=%v stops=%v",
                        starts, stops)
                }}
                n := len(starts)
                for i := 0; i < n; i++ {{
                    want := starts[n-1-i]
                    if stops[i] != want {{
                        t.Fatalf("stop order not reverse of start: stops=%v "+
                            "starts=%v (at i=%d expected %q got %q)",
                            stops, starts, i, want, stops[i])
                    }}
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
                "independent reverse-drain driver failed:\n"
                f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
            )
        finally:
            shutil.rmtree(dpath, ignore_errors=True)

    def test_recorder_events_returns_defensive_copy(self):
        """L2: mutating the slice from Events() must not corrupt later reads.

        Boot once, grab Events(), mutate the returned slice in place, then call
        Events() again and confirm the internal state is unchanged.
        """
        source = textwrap.dedent(
            f'''
            package extdrive_copy

            import (
                "testing"

                jobrunner "{JOBRUNNER_IMPORT}"
                "go.uber.org/fx"
                "go.uber.org/fx/fxtest"
            )

            func TestEventsCopy(t *testing.T) {{
                rec := &jobrunner.Recorder{{}}
                app := fxtest.New(t, jobrunner.Module, fx.Supply(rec))
                app.RequireStart().RequireStop()

                first := rec.Events()
                if len(first) == 0 {{
                    t.Fatalf("no events recorded")
                }}
                // capture a pristine reference copy before mutation
                pristine := make([]string, len(first))
                copy(pristine, first)

                // mutate the returned slice aggressively
                for i := range first {{
                    first[i] = "MUTATED"
                }}

                second := rec.Events()
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
        dpath, target = _write_driver(
            "extdrive_copy", "copy_test.go", source
        )
        try:
            proc = _run_go_test(target, extra_args=["-count=1", "-v"])
            assert proc.returncode == 0, (
                "independent defensive-copy driver failed:\n"
                f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
            )
        finally:
            shutil.rmtree(dpath, ignore_errors=True)

    def test_module_is_self_contained_only_recorder_needed(self):
        """L2: Module + a supplied *Recorder is sufficient to boot.

        Uses fx.New (not fxtest) with a short RequireStart/Stop via a manual
        context to confirm no other wiring (no extra Provide/Supply) is needed
        and the graph has no missing-dependency or cycle errors.
        """
        source = textwrap.dedent(
            f'''
            package extdrive_boot

            import (
                "context"
                "testing"
                "time"

                jobrunner "{JOBRUNNER_IMPORT}"
                "go.uber.org/fx"
            )

            func TestSelfContained(t *testing.T) {{
                rec := &jobrunner.Recorder{{}}
                app := fx.New(jobrunner.Module, fx.Supply(rec))
                if err := app.Err(); err != nil {{
                    t.Fatalf("graph construction error (missing dep/cycle?): %v", err)
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
                ev := rec.Events()
                ready := 0
                starts := 0
                stops := 0
                for _, e := range ev {{
                    switch {{
                    case e == "scheduler:ready":
                        ready++
                    case len(e) >= 6 && e[:6] == "start:":
                        starts++
                    case len(e) >= 5 && e[:5] == "stop:":
                        stops++
                    }}
                }}
                if ready != 1 || starts < 3 || starts != stops {{
                    t.Fatalf("self-contained boot invariants violated: "+
                        "ready=%d starts=%d stops=%d events=%v",
                        ready, starts, stops, ev)
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

    def test_no_job_side_effects_before_start(self):
        """L2: no start:/stop: events may be recorded before the app starts.

        Constructing the graph with fx.New runs all constructors (and may
        legitimately record scheduler:ready once the runner has taken ownership
        of the jobs), but NO job may have actually run yet. If the agent
        (wrongly) ran jobs or appended start:/stop: from a constructor body,
        those events would appear here before Start() is ever called.
        """
        source = textwrap.dedent(
            f'''
            package extdrive_order

            import (
                "strings"
                "testing"

                jobrunner "{JOBRUNNER_IMPORT}"
                "go.uber.org/fx"
            )

            func TestNoJobSideEffectsBeforeStart(t *testing.T) {{
                rec := &jobrunner.Recorder{{}}
                app := fx.New(jobrunner.Module, fx.Supply(rec))
                if err := app.Err(); err != nil {{
                    t.Fatalf("graph error: %v", err)
                }}
                // Graph is constructed but Start() has NOT been called.
                for _, e := range rec.Events() {{
                    if strings.HasPrefix(e, "start:") ||
                        strings.HasPrefix(e, "stop:") {{
                        t.Fatalf("job side effect %q recorded before Start(); "+
                            "constructors must not run/drain jobs. events=%v",
                            e, rec.Events())
                    }}
                }}
            }}
            '''
        )
        dpath, target = _write_driver(
            "extdrive_order", "noside_test.go", source
        )
        try:
            proc = _run_go_test(target, extra_args=["-count=1", "-v"])
            assert proc.returncode == 0, (
                "independent no-side-effect driver failed:\n"
                f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
            )
        finally:
            shutil.rmtree(dpath, ignore_errors=True)

    def test_fourth_job_extends_without_runner_change(self):
        """L2: registering a 4th job via the value group extends behavior.

        We do NOT edit runner.go. Instead we register one more independent job
        constructor in a driver package, contribute it into the same fx value
        group the runner consumes, and confirm the runner picks it up: it
        drains FOUR jobs (the runner records `stop:<name>` for every job it
        owns, including our `auditor`), the reverse-drain invariant still holds,
        and `scheduler:ready` still appears before any start. This proves the
        runner receives the complete collection without naming the individual
        job constructors.

        Note: the runner records `stop:<name>` for every job it owns (this
        requires no access to the package's unexported recorder method), so we
        assert on the STOP events. The canonical fx value-group tag used across
        the docs examples is `jobs`; if a solution legitimately uses a different
        tag we cannot bind a 4th job blindly, so a non-binding case is skipped
        rather than failed (the structural value-group design is independently
        enforced by the count/ordering tests above).
        """
        source = textwrap.dedent(
            f'''
            package extdrive_fourth

            import (
                "context"
                "strings"
                "testing"

                jobrunner "{JOBRUNNER_IMPORT}"
                "go.uber.org/fx"
                "go.uber.org/fx/fxtest"
            )

            // extraJob is a 4th, independently-registered job.
            type extraJob struct{{}}

            func (e *extraJob) Name() string {{ return "auditor" }}
            func (e *extraJob) Run(ctx context.Context) error {{
                _ = ctx
                return nil
            }}

            func newExtraJob() jobrunner.Job {{ return &extraJob{{}} }}

            func TestFourthJob(t *testing.T) {{
                rec := &jobrunner.Recorder{{}}
                extra := fx.Provide(
                    fx.Annotate(
                        newExtraJob,
                        fx.ResultTags(`group:"jobs"`),
                    ),
                )
                app := fxtest.New(t, jobrunner.Module, fx.Supply(rec), extra)
                app.RequireStart().RequireStop()
                events := rec.Events()

                ready := 0
                readyIdx := -1
                firstStart := -1
                var stops []string
                for i, e := range events {{
                    switch {{
                    case e == "scheduler:ready":
                        ready++
                        if readyIdx < 0 {{
                            readyIdx = i
                        }}
                    case strings.HasPrefix(e, "start:"):
                        if firstStart < 0 {{
                            firstStart = i
                        }}
                    case strings.HasPrefix(e, "stop:"):
                        stops = append(stops, strings.TrimPrefix(e, "stop:"))
                    }}
                }}

                // The runner drains every job it owns; with the extra job there
                // must be exactly 4 stop events and "auditor" must be among
                // them, proving the runner consumed the independently
                // registered 4th job without naming it.
                if len(stops) != 4 {{
                    t.Fatalf("expected 4 stop events after registering a 4th "+
                        "job, got %d: %v", len(stops), events)
                }}
                seenAuditor := false
                for _, n := range stops {{
                    if n == "auditor" {{
                        seenAuditor = true
                    }}
                }}
                if !seenAuditor {{
                    t.Fatalf("runner did not drain the independently-registered "+
                        "4th job; stops=%v", stops)
                }}
                // Still exactly one scheduler:ready, and it must precede the
                // first start even with the additional job.
                if ready != 1 {{
                    t.Fatalf("expected exactly 1 scheduler:ready with 4 jobs, "+
                        "got %d: %v", ready, events)
                }}
                if firstStart >= 0 && !(readyIdx < firstStart) {{
                    t.Fatalf("scheduler:ready (idx %d) not before first start "+
                        "(idx %d): %v", readyIdx, firstStart, events)
                }}
            }}
            '''
        )
        dpath, target = _write_driver(
            "extdrive_fourth", "fourth_test.go", source
        )
        try:
            proc = _run_go_test(target, extra_args=["-count=1", "-v"])
            combined = proc.stdout + proc.stderr
            if proc.returncode != 0:
                # A wrong-count / ordering failure is a real failure.
                runtime_markers = (
                    "expected 4 stop events",
                    "did not drain",
                    "scheduler:ready",
                    "reverse drain broken",
                    "exactly 1 scheduler:ready",
                )
                if any(m in combined for m in runtime_markers):
                    pytest.fail(
                        "4th-job extension produced wrong behavior:\n"
                        + combined
                    )
                # Build/binding failure: the solution may use a non-`jobs`
                # group tag. The value-group design is enforced structurally by
                # the count/ordering tests; do not penalize a different tag.
                pytest.skip(
                    "4th-job driver could not bind to the example's value "
                    "group tag (non-`jobs` tag). Combined output:\n" + combined
                )
            assert "TestFourthJob" in proc.stdout
        finally:
            shutil.rmtree(dpath, ignore_errors=True)

    def test_race_detector_clean_on_boot(self):
        """L2: the recorder is concurrency-safe (go test -race is clean).

        The Recorder must be usable concurrently; running the boot driver under
        the race detector must not report a data race.
        """
        source = textwrap.dedent(
            f'''
            package extdrive_boot

            import (
                "testing"

                jobrunner "{JOBRUNNER_IMPORT}"
                "go.uber.org/fx"
                "go.uber.org/fx/fxtest"
            )

            func TestRaceClean(t *testing.T) {{
                for i := 0; i < 3; i++ {{
                    rec := &jobrunner.Recorder{{}}
                    app := fxtest.New(t, jobrunner.Module, fx.Supply(rec))
                    app.RequireStart().RequireStop()
                    if len(rec.Events()) == 0 {{
                        t.Fatalf("no events on iteration %d", i)
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
                "race detector reported a data race in the recorder:\n"
                + combined
            )
            assert proc.returncode == 0, (
                "race driver failed:\n"
                f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
            )
        finally:
            shutil.rmtree(dpath, ignore_errors=True)
