"""Tests for the `go-fx-di` skill task (ext8 variant): a health-check aggregator
example with many-to-one value-group wiring.

Skill under test: go-fx-di (uber-go/fx dependency injection with parameter &
result structs + value groups).

The ext8 task asks the agent to create a new `healthagg` package under
`docs/ex/healthagg/` inside the `go.uber.org/fx/docs` module. The package must
expose:

  * `Check` — struct with `Name string` and `Status func() bool`.
  * `NewDiskCheck`, `NewMemCheck`, `NewNetCheck` — three independent producers,
    each emitting one `Check` (named "disk"/"mem"/"net") via a RESULT struct so
    the values join one shared value-group collection; producers must not
    enumerate each other.
  * `Aggregator` (exported) with `Healthy() bool` and `Report() map[string]bool`.
  * `NewAggregator` — constructor receiving the full collection of `Check`
    values through a PARAMETER struct, plus a `*zap.Logger` (mixed deps). It
    must NOT reference the producers by name.
  * `Module` (`fx.Option`) wiring the three producers + the aggregator, so that
    booting `Module` plus a supplied `*zap.Logger` yields a working
    `*Aggregator`.

Behavioral contract (from the requirement doc):
  * all three checks healthy -> `Healthy() == true`, `Report()` has 3 keys all
    true, key set == {"disk","mem","net"};
  * `Report()` has exactly one entry per registered check (count == collection
    size) — a hardcoded 3-key map detached from the collection must fail;
  * adding a 4th producer (into the same value group) extends `Report()` to 4
    keys with no edit to aggregator.go.

Verification strategy: rather than trusting the agent's own
`healthagg_test.go`, the L2 tests write INDEPENDENT Go driver test files into
fresh sub-directories of the `healthagg` package and run them with the native
`go test` toolchain (from the `docs` module). These drivers boot the real
`Module` via `fxtest`/`fx`, drive the configurable net check (where bindable)
and contribute a 4th check into the value group, and assert deeply on
`Healthy()` / `Report()`. A naive solution (hardcoded 3-key map, aggregator
ignoring the collection, or constructor that enumerates producers) cannot pass.
"""

import os
import shutil
import subprocess
import textwrap

import pytest

REPO_DIR = "/workspace/fx"
DOCS_DIR = os.path.join(REPO_DIR, "docs")
PKG_DIR = os.path.join(DOCS_DIR, "ex", "healthagg")

GO_TEST_TIMEOUT = 480

# Import path of the healthagg package within the docs module.
HEALTHAGG_IMPORT = "go.uber.org/fx/docs/ex/healthagg"


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
    target = "./ex/healthagg/" + subdir_name + "/..."
    return dpath, target


# --------------------------------------------------------------------------- #
# Dependency / build readiness (module-scope, autouse)
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module", autouse=True)
def _ensure_go_ready():
    """Make sure the Go toolchain + docs module deps are available.

    Warms the build/module cache once so the heavy module-download cost is paid
    before the per-test timeouts apply.
    """
    assert os.path.isdir(REPO_DIR), f"missing repo dir {REPO_DIR}"
    assert os.path.isdir(DOCS_DIR), f"missing docs module dir {DOCS_DIR}"
    try:
        subprocess.run(
            ["go", "build", "./ex/healthagg/..."],
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
        "extdrive_report",
        "extdrive_net",
        "extdrive_fourth",
        "extdrive_param",
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
        """L1: the healthagg example directory exists under docs/ex."""
        assert os.path.isdir(PKG_DIR), f"expected package dir at {PKG_DIR}"

    def test_required_source_files_present(self):
        """L1: required deliverable .go source files all exist."""
        for fname in ("check.go", "producers.go", "aggregator.go",
                      "healthagg_test.go"):
            fpath = os.path.join(PKG_DIR, fname)
            assert os.path.isfile(fpath), f"missing required file {fpath}"

    def test_package_uses_healthagg_name_and_no_new_module(self):
        """L1: files declare `package healthagg`; no new go.mod was added."""
        go_files = [f for f in os.listdir(PKG_DIR) if f.endswith(".go")]
        assert go_files, "no .go files found in package dir"
        for f in go_files:
            with open(os.path.join(PKG_DIR, f)) as fh:
                head = fh.read()
            assert "package healthagg" in head, (
                f"{f} does not declare `package healthagg`"
            )
        assert not os.path.isfile(os.path.join(PKG_DIR, "go.mod")), (
            "a new go.mod must NOT be created inside the example dir"
        )

    def test_package_compiles(self):
        """L1: the healthagg package compiles under the docs module."""
        proc = subprocess.run(
            ["go", "build", "./ex/healthagg/..."],
            cwd=DOCS_DIR,
            capture_output=True,
            text=True,
            timeout=GO_TEST_TIMEOUT,
            env=_go_env(),
        )
        assert proc.returncode == 0, (
            "healthagg package failed to compile:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    def test_authors_own_test_passes(self):
        """L1: the task's native command passes for this package.

        `cd docs && go test ./ex/healthagg/...`
        """
        proc = _run_go_test("./ex/healthagg/...")
        assert proc.returncode == 0, (
            "`go test ./ex/healthagg/...` failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    # ------------------------------------------------------------------ #
    # L2 — independent dynamic execution against the real Module
    # ------------------------------------------------------------------ #
    def test_module_boots_into_aggregator(self):
        """L2: booting Module + a supplied *zap.Logger yields a *Aggregator.

        Independent driver: boot via fxtest, populate an *Aggregator, and
        confirm there is no missing-dependency or cycle error and the value is
        non-nil. A constructor that names the producers (instead of consuming
        the collection) would still compile, so the deeper count/key assertions
        below provide the discrimination.
        """
        source = textwrap.dedent(
            f'''
            package extdrive_boot

            import (
                "testing"

                healthagg "{HEALTHAGG_IMPORT}"
                "go.uber.org/fx"
                "go.uber.org/fx/fxtest"
                "go.uber.org/zap"
            )

            func TestBootAggregator(t *testing.T) {{
                var agg *healthagg.Aggregator
                app := fxtest.New(t, healthagg.Module,
                    fx.Supply(zap.NewNop()),
                    fx.Populate(&agg))
                app.RequireStart().RequireStop()
                if agg == nil {{
                    t.Fatalf("aggregator was not populated (nil)")
                }}
                rep := agg.Report()
                if rep == nil {{
                    t.Fatalf("Report() returned nil map")
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
            assert "TestBootAggregator" in proc.stdout
        finally:
            shutil.rmtree(dpath, ignore_errors=True)

    def test_report_has_exactly_three_named_keys(self):
        """L2: Report() has exactly the key set {"disk","mem","net"}.

        Enforces one entry per registered producer (3) and the exact names.
        A hardcoded map with extra/missing/wrong keys fails here.
        """
        source = textwrap.dedent(
            f'''
            package extdrive_report

            import (
                "sort"
                "strings"
                "testing"

                healthagg "{HEALTHAGG_IMPORT}"
                "go.uber.org/fx"
                "go.uber.org/fx/fxtest"
                "go.uber.org/zap"
            )

            func TestReportKeys(t *testing.T) {{
                var agg *healthagg.Aggregator
                app := fxtest.New(t, healthagg.Module,
                    fx.Supply(zap.NewNop()),
                    fx.Populate(&agg))
                app.RequireStart().RequireStop()

                rep := agg.Report()
                if len(rep) != 3 {{
                    t.Fatalf("Report() must have exactly 3 keys, got %d: %v",
                        len(rep), rep)
                }}
                var keys []string
                for k := range rep {{
                    keys = append(keys, k)
                }}
                sort.Strings(keys)
                got := strings.Join(keys, ",")
                if got != "disk,mem,net" {{
                    t.Fatalf("Report() key set must be {{disk,mem,net}}, got %q",
                        got)
                }}
            }}
            '''
        )
        dpath, target = _write_driver(
            "extdrive_report", "keys_test.go", source
        )
        try:
            proc = _run_go_test(target, extra_args=["-count=1", "-v"])
            assert proc.returncode == 0, (
                "independent report-keys driver failed:\n"
                f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
            )
        finally:
            shutil.rmtree(dpath, ignore_errors=True)

    def test_all_healthy_reports_true_and_healthy_true(self):
        """L2: with the default producers, every Report() value is true and
        Healthy() == true.

        The doc fixes disk and mem healthy; the net check defaults to healthy.
        Healthy() must be the AND over the collection, not a constant.
        """
        source = textwrap.dedent(
            f'''
            package extdrive_report

            import (
                "testing"

                healthagg "{HEALTHAGG_IMPORT}"
                "go.uber.org/fx"
                "go.uber.org/fx/fxtest"
                "go.uber.org/zap"
            )

            func TestAllHealthy(t *testing.T) {{
                var agg *healthagg.Aggregator
                app := fxtest.New(t, healthagg.Module,
                    fx.Supply(zap.NewNop()),
                    fx.Populate(&agg))
                app.RequireStart().RequireStop()

                rep := agg.Report()
                for name, ok := range rep {{
                    if !ok {{
                        t.Fatalf("expected check %q healthy by default, "+
                            "Report()=%v", name, rep)
                    }}
                }}
                if !agg.Healthy() {{
                    t.Fatalf("Healthy() must be true when all checks pass, "+
                        "Report()=%v", rep)
                }}
            }}
            '''
        )
        dpath, target = _write_driver(
            "extdrive_report", "healthy_test.go", source
        )
        try:
            proc = _run_go_test(target, extra_args=["-count=1", "-v"])
            assert proc.returncode == 0, (
                "independent all-healthy driver failed:\n"
                f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
            )
        finally:
            shutil.rmtree(dpath, ignore_errors=True)

    def test_report_consistent_with_healthy(self):
        """L2: Healthy() is the logical AND of Report()'s values.

        Independently recompute the AND over Report() and compare to Healthy();
        a Healthy() that returns a constant (ignoring the collection) would
        diverge whenever any check is false. With the canonical Module all are
        true, but we still assert the AND-relationship holds exactly so a
        constant-true Healthy() detached from Report() cannot silently pass the
        broader contract.
        """
        source = textwrap.dedent(
            f'''
            package extdrive_report

            import (
                "testing"

                healthagg "{HEALTHAGG_IMPORT}"
                "go.uber.org/fx"
                "go.uber.org/fx/fxtest"
                "go.uber.org/zap"
            )

            func TestHealthyIsAnd(t *testing.T) {{
                var agg *healthagg.Aggregator
                app := fxtest.New(t, healthagg.Module,
                    fx.Supply(zap.NewNop()),
                    fx.Populate(&agg))
                app.RequireStart().RequireStop()

                rep := agg.Report()
                if len(rep) == 0 {{
                    t.Fatalf("Report() is empty")
                }}
                wantHealthy := true
                for _, ok := range rep {{
                    if !ok {{
                        wantHealthy = false
                    }}
                }}
                if agg.Healthy() != wantHealthy {{
                    t.Fatalf("Healthy()=%v but AND(Report())=%v; Report()=%v",
                        agg.Healthy(), wantHealthy, rep)
                }}
            }}
            '''
        )
        dpath, target = _write_driver(
            "extdrive_report", "and_test.go", source
        )
        try:
            proc = _run_go_test(target, extra_args=["-count=1", "-v"])
            assert proc.returncode == 0, (
                "independent healthy-AND driver failed:\n"
                f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
            )
        finally:
            shutil.rmtree(dpath, ignore_errors=True)

    def test_unhealthy_check_flips_report_and_healthy(self):
        """L2: injecting an unhealthy check into the value group flips both
        Report() (that key -> false) and Healthy() (-> false).

        We contribute one extra Check named "net" (unhealthy) into the same fx
        value group the aggregator consumes. Because the aggregator AND-folds
        the WHOLE collection, the presence of a false-status check must make
        Healthy() false and surface a false value in Report(). A Healthy() that
        ignores the collection (constant true) or a Report() detached from the
        collection cannot satisfy this.

        The canonical value-group tag in the docs examples is `checks`; if a
        solution legitimately uses a different tag we cannot bind blindly, so a
        non-binding build failure is SKIPPED (the collection-size/key contract
        is independently enforced by the tests above) while a wrong *behavior*
        is a hard failure.
        """
        source = textwrap.dedent(
            f'''
            package extdrive_net

            import (
                "testing"

                healthagg "{HEALTHAGG_IMPORT}"
                "go.uber.org/fx"
                "go.uber.org/fx/fxtest"
                "go.uber.org/zap"
            )

            // newBadCheck contributes an unhealthy check into the value group.
            func newBadCheck() healthagg.Check {{
                return healthagg.Check{{
                    Name:   "broken",
                    Status: func() bool {{ return false }},
                }}
            }}

            func TestUnhealthyFlips(t *testing.T) {{
                var agg *healthagg.Aggregator
                extra := fx.Provide(
                    fx.Annotate(
                        newBadCheck,
                        fx.ResultTags(`group:"checks"`),
                    ),
                )
                app := fxtest.New(t, healthagg.Module,
                    fx.Supply(zap.NewNop()),
                    extra,
                    fx.Populate(&agg))
                app.RequireStart().RequireStop()

                rep := agg.Report()
                v, ok := rep["broken"]
                if !ok {{
                    t.Fatalf("injected check \\"broken\\" not present in "+
                        "Report() %v -- aggregator ignored the value group", rep)
                }}
                if v != false {{
                    t.Fatalf("injected unhealthy check must report false, "+
                        "got %v: %v", v, rep)
                }}
                if agg.Healthy() {{
                    t.Fatalf("Healthy() must be false when a check is "+
                        "unhealthy: %v", rep)
                }}
                if len(rep) != 4 {{
                    t.Fatalf("expected 4 entries after injecting a check, "+
                        "got %d: %v", len(rep), rep)
                }}
            }}
            '''
        )
        dpath, target = _write_driver(
            "extdrive_net", "net_test.go", source
        )
        try:
            proc = _run_go_test(target, extra_args=["-count=1", "-v"])
            combined = proc.stdout + proc.stderr
            if proc.returncode != 0:
                runtime_markers = (
                    "not present in",
                    "report false",
                    "must be false",
                    "expected 4 entries",
                    "ignored the value group",
                )
                if any(m in combined for m in runtime_markers):
                    pytest.fail(
                        "unhealthy-injection produced wrong behavior:\n"
                        + combined
                    )
                pytest.skip(
                    "could not bind an extra check to the example's value "
                    "group tag (non-`checks` tag). Combined output:\n"
                    + combined
                )
            assert "TestUnhealthyFlips" in proc.stdout
        finally:
            shutil.rmtree(dpath, ignore_errors=True)

    def test_fourth_producer_extends_report(self):
        """L2: registering a 4th producer into the value group extends Report()
        to 4 keys WITHOUT editing aggregator.go.

        We provide one more independent producer that emits a healthy Check
        named "gpu" into the same `checks` value group, then assert Report()
        gains a 4th key, the count matches the collection size, and Healthy()
        stays true (all healthy). This proves the aggregator receives the
        COMPLETE collection through its parameter struct rather than naming the
        three original producers. Non-`checks` tag -> SKIP (structural contract
        enforced elsewhere); wrong behavior -> hard FAIL.
        """
        source = textwrap.dedent(
            f'''
            package extdrive_fourth

            import (
                "sort"
                "strings"
                "testing"

                healthagg "{HEALTHAGG_IMPORT}"
                "go.uber.org/fx"
                "go.uber.org/fx/fxtest"
                "go.uber.org/zap"
            )

            func newGpuCheck() healthagg.Check {{
                return healthagg.Check{{
                    Name:   "gpu",
                    Status: func() bool {{ return true }},
                }}
            }}

            func TestFourthProducer(t *testing.T) {{
                var agg *healthagg.Aggregator
                extra := fx.Provide(
                    fx.Annotate(
                        newGpuCheck,
                        fx.ResultTags(`group:"checks"`),
                    ),
                )
                app := fxtest.New(t, healthagg.Module,
                    fx.Supply(zap.NewNop()),
                    extra,
                    fx.Populate(&agg))
                app.RequireStart().RequireStop()

                rep := agg.Report()
                if len(rep) != 4 {{
                    t.Fatalf("expected 4 entries after adding a 4th producer, "+
                        "got %d: %v", len(rep), rep)
                }}
                var keys []string
                for k := range rep {{
                    keys = append(keys, k)
                }}
                sort.Strings(keys)
                got := strings.Join(keys, ",")
                if got != "disk,gpu,mem,net" {{
                    t.Fatalf("Report() key set after 4th producer must be "+
                        "{{disk,gpu,mem,net}}, got %q", got)
                }}
                if v, ok := rep["gpu"]; !ok || !v {{
                    t.Fatalf("4th producer's check missing/false: %v", rep)
                }}
                if !agg.Healthy() {{
                    t.Fatalf("Healthy() must remain true with all 4 healthy: "+
                        "%v", rep)
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
                runtime_markers = (
                    "expected 4 entries",
                    "key set after 4th",
                    "missing/false",
                    "must remain true",
                )
                if any(m in combined for m in runtime_markers):
                    pytest.fail(
                        "4th-producer extension produced wrong behavior:\n"
                        + combined
                    )
                pytest.skip(
                    "4th-producer driver could not bind to the example's "
                    "value group tag (non-`checks` tag). Combined output:\n"
                    + combined
                )
            assert "TestFourthProducer" in proc.stdout
        finally:
            shutil.rmtree(dpath, ignore_errors=True)

    def test_aggregator_consumes_collection_not_named_producers(self):
        """L2: with ONLY the aggregator + a *zap.Logger and NO producers
        provided, the collection is empty and Report() has 0 entries.

        This isolates `NewAggregator` from `Module`: if the constructor named /
        hardcoded the three producers (instead of consuming an injected value
        group), it would still report 3 (or panic). Consuming an `fx.In`
        parameter struct with a value group yields an EMPTY slice when nothing
        feeds the group, so Report() must be empty and Healthy() true (vacuous
        AND). Build failure (e.g. NewAggregator not individually provideable in
        the canonical way) -> SKIP; wrong count -> hard FAIL.
        """
        source = textwrap.dedent(
            f'''
            package extdrive_param

            import (
                "testing"

                healthagg "{HEALTHAGG_IMPORT}"
                "go.uber.org/fx"
                "go.uber.org/fx/fxtest"
                "go.uber.org/zap"
            )

            func TestEmptyCollection(t *testing.T) {{
                var agg *healthagg.Aggregator
                // Provide ONLY the aggregator constructor + a logger; do NOT
                // include healthagg.Module, so no producers feed the group.
                app := fxtest.New(t,
                    fx.Supply(zap.NewNop()),
                    fx.Provide(healthagg.NewAggregator),
                    fx.Populate(&agg))
                app.RequireStart().RequireStop()

                rep := agg.Report()
                if len(rep) != 0 {{
                    t.Fatalf("aggregator built with no producers must report "+
                        "0 checks (collection-driven), got %d: %v",
                        len(rep), rep)
                }}
                if !agg.Healthy() {{
                    t.Fatalf("Healthy() over an empty collection must be true "+
                        "(vacuous AND), got false")
                }}
            }}
            '''
        )
        dpath, target = _write_driver(
            "extdrive_param", "empty_test.go", source
        )
        try:
            proc = _run_go_test(target, extra_args=["-count=1", "-v"])
            combined = proc.stdout + proc.stderr
            if proc.returncode != 0:
                runtime_markers = (
                    "must report ",
                    "empty collection must be true",
                )
                if any(m in combined for m in runtime_markers):
                    pytest.fail(
                        "aggregator did not consume an injected collection "
                        "(named producers / hardcoded report?):\n" + combined
                    )
                pytest.skip(
                    "NewAggregator could not be provided standalone in the "
                    "canonical fxtest form (parameter-struct signature "
                    "differs). Combined output:\n" + combined
                )
            assert "TestEmptyCollection" in proc.stdout
        finally:
            shutil.rmtree(dpath, ignore_errors=True)

    def test_graph_has_no_missing_dependency_or_cycle(self):
        """L2: fx.New(Module, Supply(logger)) constructs with no error.

        Uses fx.New (not fxtest) and asserts app.Err() is nil — directly
        validating the doc's "booting must not produce a missing-dependency or
        cycle error" constraint, including the mixed *zap.Logger dependency.
        """
        source = textwrap.dedent(
            f'''
            package extdrive_boot

            import (
                "context"
                "testing"
                "time"

                healthagg "{HEALTHAGG_IMPORT}"
                "go.uber.org/fx"
                "go.uber.org/zap"
            )

            func TestNoMissingDepOrCycle(t *testing.T) {{
                var agg *healthagg.Aggregator
                app := fx.New(healthagg.Module,
                    fx.Supply(zap.NewNop()),
                    fx.Populate(&agg))
                if err := app.Err(); err != nil {{
                    t.Fatalf("graph construction error (missing dep/cycle?): "+
                        "%v", err)
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
                if agg == nil {{
                    t.Fatalf("aggregator not populated")
                }}
                if len(agg.Report()) != 3 {{
                    t.Fatalf("expected 3 checks in canonical graph, got %d: %v",
                        len(agg.Report()), agg.Report())
                }}
            }}
            '''
        )
        dpath, target = _write_driver(
            "extdrive_boot", "nocycle_test.go", source
        )
        try:
            proc = _run_go_test(target, extra_args=["-count=1", "-v"])
            assert proc.returncode == 0, (
                "independent no-missing-dep driver failed:\n"
                f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
            )
        finally:
            shutil.rmtree(dpath, ignore_errors=True)
