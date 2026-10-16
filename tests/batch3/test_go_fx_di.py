"""Tests for the `go-fx-di` skill task (ext3 variant): a multi-named database
pool example with interface binding.

Skill under test: go-fx-di (uber-go/fx dependency injection — selecting between
two constructors that build the *same* Go type, plus exposing a concrete type to
consumers only through an interface).

The ext3 task asks the agent to create a new `datapool` package under
`docs/ex/datapool/` inside the `go.uber.org/fx/docs` module. The package must
expose:

  * `Pool`  — a concrete struct with a `Label string` field and a
    `Ping() string` method returning `"pong:" + Label`.
  * `Store` — an interface with a single method `Ping() string`.
  * `NewPrimaryPool` / `NewReplicaPool` — two constructors, *both returning
    `*Pool`*, with labels `"primary"` and `"replica"`.
  * `Report` — a struct with `Primary`, `Replica`, `ViaInterface string` fields,
    plus `NewReport` depending on the primary `*Pool`, the replica `*Pool`, and
    the `Store` interface.
  * `Module` — an `fx.Option` wiring both pools, the interface binding (Store ->
    primary), and the report, such that booting `Module` alone yields a
    `*Report` whose fields are `"pong:primary"`, `"pong:replica"`,
    `"pong:primary"`.

Verification strategy: rather than trusting the agent's own
`datapool_test.go`, the L2 tests write INDEPENDENT Go driver test files into a
fresh sub-directory of the `datapool` package and run them with the native
`go test` toolchain (from the `docs` module). These drivers boot the real
`Module` via `fxtest` / `fx.New` and assert deeply on the resolved values, so a
naive single-pool provider, a hardcoded `Report`, or a `Store` bound to the
replica instead of the primary all fail.
"""

import os
import shutil
import subprocess
import textwrap

import pytest

REPO_DIR = "/workspace/fx"
DOCS_DIR = os.path.join(REPO_DIR, "docs")
PKG_DIR = os.path.join(DOCS_DIR, "ex", "datapool")

GO_TEST_TIMEOUT = 480

# Import path of the datapool package within the docs module.
DATAPOOL_IMPORT = "go.uber.org/fx/docs/ex/datapool"


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
    target = "./ex/datapool/" + subdir_name + "/..."
    return dpath, target


# --------------------------------------------------------------------------- #
# Dependency / build readiness (module-scope, autouse)
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module", autouse=True)
def _ensure_go_ready():
    """Make sure the Go toolchain + docs module deps are available.

    Runs a cheap compile of the datapool package so that the heavy
    module-download cost is paid once, before the per-test timeouts apply.
    """
    assert os.path.isdir(REPO_DIR), f"missing repo dir {REPO_DIR}"
    assert os.path.isdir(DOCS_DIR), f"missing docs module dir {DOCS_DIR}"
    try:
        subprocess.run(
            ["go", "build", "./ex/datapool/..."],
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
        "extdrive_iface",
        "extdrive_distinct",
        "extdrive_naive",
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
        """L1: the datapool example directory exists under docs/ex."""
        assert os.path.isdir(PKG_DIR), f"expected package dir at {PKG_DIR}"

    def test_required_source_files_present(self):
        """L1: required deliverable .go source files all exist."""
        for fname in ("pool.go", "wiring.go", "datapool_test.go"):
            fpath = os.path.join(PKG_DIR, fname)
            assert os.path.isfile(fpath), f"missing required file {fpath}"

    def test_package_uses_datapool_name_and_no_new_module(self):
        """L1: files declare `package datapool`; no new go.mod was added."""
        go_files = [f for f in os.listdir(PKG_DIR) if f.endswith(".go")]
        assert go_files, "no .go files found in package dir"
        for f in go_files:
            with open(os.path.join(PKG_DIR, f)) as fh:
                head = fh.read()
            assert "package datapool" in head, (
                f"{f} does not declare `package datapool`"
            )
        assert not os.path.isfile(os.path.join(PKG_DIR, "go.mod")), (
            "a new go.mod must NOT be created inside the example dir"
        )

    def test_package_compiles(self):
        """L1: the datapool package compiles under the docs module."""
        proc = subprocess.run(
            ["go", "build", "./ex/datapool/..."],
            cwd=DOCS_DIR,
            capture_output=True,
            text=True,
            timeout=GO_TEST_TIMEOUT,
            env=_go_env(),
        )
        assert proc.returncode == 0, (
            "datapool package failed to compile:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    def test_authors_own_test_passes(self):
        """L1: the task's specified native command passes for this package.

        This drives exactly the doc's Acceptance command:
        `cd docs && go test ./ex/datapool/...`.
        """
        proc = _run_go_test("./ex/datapool/...")
        assert proc.returncode == 0, (
            "`go test ./ex/datapool/...` failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    # ------------------------------------------------------------------ #
    # L2 — independent dynamic execution against the real Module
    # ------------------------------------------------------------------ #
    def test_module_boots_and_report_has_exact_values(self):
        """L2: booting Module via fxtest + fx.Populate yields the exact Report.

        Independent driver: boot only `Module`, populate a `*Report`, and assert
        Primary == "pong:primary", Replica == "pong:replica",
        ViaInterface == "pong:primary". A hardcoded Report or a swapped
        primary/replica wiring fails here.
        """
        source = textwrap.dedent(
            f'''
            package extdrive_boot

            import (
                "testing"

                datapool "{DATAPOOL_IMPORT}"
                "go.uber.org/fx"
                "go.uber.org/fx/fxtest"
            )

            func TestReportExactValues(t *testing.T) {{
                var rep *datapool.Report
                app := fxtest.New(t, datapool.Module, fx.Populate(&rep))
                app.RequireStart().RequireStop()

                if rep == nil {{
                    t.Fatalf("Report was not populated (nil)")
                }}
                if rep.Primary != "pong:primary" {{
                    t.Fatalf("Primary = %q, want %q", rep.Primary, "pong:primary")
                }}
                if rep.Replica != "pong:replica" {{
                    t.Fatalf("Replica = %q, want %q", rep.Replica, "pong:replica")
                }}
                if rep.ViaInterface != "pong:primary" {{
                    t.Fatalf("ViaInterface = %q, want %q",
                        rep.ViaInterface, "pong:primary")
                }}
            }}
            '''
        )
        dpath, target = _write_driver(
            "extdrive_boot", "report_test.go", source
        )
        try:
            proc = _run_go_test(target, extra_args=["-count=1", "-v"])
            assert proc.returncode == 0, (
                "independent report driver failed:\n"
                f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
            )
            assert "TestReportExactValues" in proc.stdout
        finally:
            shutil.rmtree(dpath, ignore_errors=True)

    def test_store_interface_resolves_to_primary(self):
        """L2: a consumer depending on the Store interface receives the primary.

        Independent driver: populate a `datapool.Store` directly from the graph
        and assert its `Ping()` == "pong:primary". If the agent bound Store to
        the replica (or to a fresh pool), this fails. This is the core
        interface-binding invariant, verified WITHOUT going through Report.
        """
        source = textwrap.dedent(
            f'''
            package extdrive_iface

            import (
                "testing"

                datapool "{DATAPOOL_IMPORT}"
                "go.uber.org/fx"
                "go.uber.org/fx/fxtest"
            )

            func TestStoreIsPrimary(t *testing.T) {{
                var s datapool.Store
                app := fxtest.New(t, datapool.Module, fx.Populate(&s))
                app.RequireStart().RequireStop()

                if s == nil {{
                    t.Fatalf("Store was not populated (nil); is Store bound?")
                }}
                if got := s.Ping(); got != "pong:primary" {{
                    t.Fatalf("Store.Ping() = %q, want %q (Store must be the "+
                        "primary pool, not the replica)", got, "pong:primary")
                }}
            }}
            '''
        )
        dpath, target = _write_driver(
            "extdrive_iface", "iface_test.go", source
        )
        try:
            proc = _run_go_test(target, extra_args=["-count=1", "-v"])
            assert proc.returncode == 0, (
                "independent Store-binding driver failed:\n"
                f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
            )
        finally:
            shutil.rmtree(dpath, ignore_errors=True)

    def test_both_pools_selectable_and_distinct(self):
        """L2: both *Pool values coexist, are independently selectable, distinct.

        Independent driver: populate two *Pool values selected as primary and
        replica (via the same selection mechanism the Report consumer must use),
        assert their Ping() differs ("pong:primary" vs "pong:replica") and that
        they are distinct pointer instances. A single shared *Pool provider
        cannot satisfy both the distinct values AND the distinct identities.

        We discover the selection mechanism (named tags) by parsing the agent's
        own wiring.go: both pools have the same Go type, so fx must disambiguate
        them with `name:"..."` tags. We extract the two tag names and bind to
        them. If no named tags are present, the graph would itself be ambiguous
        and the L1 native test would already have failed; here we skip binding
        only when we cannot infer the exact tags rather than guess.
        """
        # Infer the named tags the agent used to disambiguate the two pools.
        wiring_path = os.path.join(PKG_DIR, "wiring.go")
        pool_path = os.path.join(PKG_DIR, "pool.go")
        text = ""
        for p in (wiring_path, pool_path):
            if os.path.isfile(p):
                with open(p) as fh:
                    text += fh.read() + "\n"
        # Find name:"<tag>" occurrences.
        import re

        names = re.findall(r'name:"([^"]+)"', text)
        # Deduplicate preserving order.
        seen = []
        for n in names:
            if n not in seen:
                seen.append(n)
        if len(seen) < 2:
            pytest.skip(
                "could not infer two distinct fx name tags for the pools from "
                f"wiring/pool source (found {seen}); the distinctness and value "
                "invariants are still enforced via Report/Store in other tests"
            )
        # Heuristic: pick the tag mentioning primary and the tag mentioning
        # replica when available, else fall back to the first two.
        primary_tag = next((n for n in seen if "primary" in n.lower()), seen[0])
        replica_tag = next(
            (n for n in seen if "replica" in n.lower() and n != primary_tag),
            None,
        )
        if replica_tag is None:
            replica_tag = next((n for n in seen if n != primary_tag), None)
        if replica_tag is None:
            pytest.skip("only one distinct name tag found; cannot bind both")

        source = textwrap.dedent(
            f'''
            package extdrive_distinct

            import (
                "testing"

                datapool "{DATAPOOL_IMPORT}"
                "go.uber.org/fx"
                "go.uber.org/fx/fxtest"
            )

            type bothPools struct {{
                fx.In
                Primary *datapool.Pool `name:"{primary_tag}"`
                Replica *datapool.Pool `name:"{replica_tag}"`
            }}

            func TestPoolsDistinct(t *testing.T) {{
                var got bothPools
                app := fxtest.New(t, datapool.Module,
                    fx.Populate(&got))
                app.RequireStart().RequireStop()

                if got.Primary == nil || got.Replica == nil {{
                    t.Fatalf("pools not populated: primary=%v replica=%v",
                        got.Primary, got.Replica)
                }}
                if got.Primary.Ping() != "pong:primary" {{
                    t.Fatalf("primary.Ping() = %q, want pong:primary",
                        got.Primary.Ping())
                }}
                if got.Replica.Ping() != "pong:replica" {{
                    t.Fatalf("replica.Ping() = %q, want pong:replica",
                        got.Replica.Ping())
                }}
                if got.Primary == got.Replica {{
                    t.Fatalf("primary and replica are the SAME *Pool instance; "+
                        "two distinct pools are required")
                }}
                if got.Primary.Label != "primary" {{
                    t.Fatalf("primary.Label = %q, want primary",
                        got.Primary.Label)
                }}
                if got.Replica.Label != "replica" {{
                    t.Fatalf("replica.Label = %q, want replica",
                        got.Replica.Label)
                }}
            }}
            '''
        )
        dpath, target = _write_driver(
            "extdrive_distinct", "distinct_test.go", source
        )
        try:
            proc = _run_go_test(target, extra_args=["-count=1", "-v"])
            combined = proc.stdout + proc.stderr
            if proc.returncode != 0:
                runtime_markers = (
                    "pong:primary",
                    "pong:replica",
                    "SAME *Pool instance",
                    "not populated",
                    ".Label",
                )
                if any(m in combined for m in runtime_markers):
                    pytest.fail(
                        "distinct-pools invariant violated:\n" + combined
                    )
                # Binding failure: the agent used a different disambiguation
                # mechanism than `name:` tags we could parse. Distinct values
                # are still enforced through Report; do not penalize.
                pytest.skip(
                    "could not bind both pools via inferred name tags "
                    f"({primary_tag!r}, {replica_tag!r}):\n" + combined
                )
        finally:
            shutil.rmtree(dpath, ignore_errors=True)

    def test_pool_ping_matches_label_property(self):
        """L2: Pool.Ping() is "pong:"+Label for arbitrary labels (not hardcoded).

        Independent driver: construct Pool values directly (no fx) with several
        labels and assert Ping() == "pong:"+Label for each. A Ping() that
        returns a fixed string regardless of Label fails here.
        """
        source = textwrap.dedent(
            f'''
            package extdrive_distinct

            import (
                "testing"

                datapool "{DATAPOOL_IMPORT}"
            )

            func TestPingProperty(t *testing.T) {{
                cases := []string{{"primary", "replica", "shard-7", "x"}}
                for _, lbl := range cases {{
                    p := &datapool.Pool{{Label: lbl}}
                    want := "pong:" + lbl
                    if got := p.Ping(); got != want {{
                        t.Fatalf("Pool{{Label:%q}}.Ping() = %q, want %q",
                            lbl, got, want)
                    }}
                }}
                // A Pool that satisfies Store at the value level.
                var _ datapool.Store = &datapool.Pool{{Label: "z"}}
            }}
            '''
        )
        dpath, target = _write_driver(
            "extdrive_distinct", "ping_test.go", source
        )
        try:
            proc = _run_go_test(target, extra_args=["-count=1", "-v"])
            assert proc.returncode == 0, (
                "independent Ping-property driver failed:\n"
                f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
            )
        finally:
            shutil.rmtree(dpath, ignore_errors=True)

    def test_module_self_contained_no_extra_wiring(self):
        """L2: Module alone is sufficient — no missing-dep, ambiguity, or cycle.

        Independent driver: build the graph with `fx.New(Module, Populate)` and
        check `app.Err()` is nil before start; then Start/Stop cleanly. This
        confirms the composition root wires both pools, the interface binding,
        and the report on its own (per the doc: "boot with only Module").
        """
        source = textwrap.dedent(
            f'''
            package extdrive_boot

            import (
                "context"
                "testing"
                "time"

                datapool "{DATAPOOL_IMPORT}"
                "go.uber.org/fx"
            )

            func TestSelfContained(t *testing.T) {{
                var rep *datapool.Report
                app := fx.New(datapool.Module, fx.Populate(&rep))
                if err := app.Err(); err != nil {{
                    t.Fatalf("graph error (missing dep / ambiguous type / "+
                        "cycle?): %v", err)
                }}
                startCtx, cancel := context.WithTimeout(
                    context.Background(), 10*time.Second)
                defer cancel()
                if err := app.Start(startCtx); err != nil {{
                    t.Fatalf("app.Start failed: %v", err)
                }}
                if rep == nil {{
                    t.Fatalf("Report not populated after start")
                }}
                if rep.Primary != "pong:primary" ||
                    rep.Replica != "pong:replica" ||
                    rep.ViaInterface != "pong:primary" {{
                    t.Fatalf("self-contained boot produced wrong report: "+
                        "%+v", *rep)
                }}
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

    def test_naive_single_pool_provider_is_insufficient(self):
        """L2: a naive single-*Pool design cannot satisfy the graph.

        The doc states: "A naive single-`*Pool` provider must fail." We prove
        this discriminatively: a graph that provides exactly ONE unnamed *Pool
        and tries to populate both a Store and a *Report-shaped consumer must
        FAIL with an fx error (ambiguous selection / missing distinct pool).
        This is a property of the *requirements*, demonstrated independently of
        the agent's Module so it is deterministic regardless of solution.

        Concretely: building a graph where the only *Pool provider is a single
        one, and asking for both `name:"primary"` and `name:"replica"` *Pool,
        must error — confirming two distinct named pools are genuinely required.
        """
        source = textwrap.dedent(
            f'''
            package extdrive_naive

            import (
                "testing"

                datapool "{DATAPOOL_IMPORT}"
                "go.uber.org/fx"
            )

            type needsTwo struct {{
                fx.In
                Primary *datapool.Pool `name:"primary"`
                Replica *datapool.Pool `name:"replica"`
            }}

            func TestNaiveSinglePoolFails(t *testing.T) {{
                // Provide exactly one *unnamed* pool — the naive design.
                single := fx.Provide(func() *datapool.Pool {{
                    return &datapool.Pool{{Label: "only"}}
                }})
                var got needsTwo
                app := fx.New(single, fx.Populate(&got))
                if err := app.Err(); err == nil {{
                    t.Fatalf("a single unnamed *Pool wrongly satisfied a "+
                        "consumer demanding distinct primary+replica pools; "+
                        "the design must require two selectable pools")
                }}
            }}
            '''
        )
        dpath, target = _write_driver(
            "extdrive_naive", "naive_test.go", source
        )
        try:
            proc = _run_go_test(target, extra_args=["-count=1", "-v"])
            assert proc.returncode == 0, (
                "independent naive-insufficiency driver failed:\n"
                f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
            )
        finally:
            shutil.rmtree(dpath, ignore_errors=True)

    def test_required_exported_symbols_present(self):
        """L2: all required exported symbols exist with the right shapes.

        Independent compile-time driver: reference every required exported
        symbol — `Pool` (with `Label`), `Store`, `Report` (three string
        fields), `NewPrimaryPool`/`NewReplicaPool` returning `*Pool`,
        `NewReport`, and `Module` (an fx.Option). If any symbol is missing,
        misnamed, or has the wrong type, this driver fails to compile.
        """
        source = textwrap.dedent(
            f'''
            package extdrive_iface

            import (
                "testing"

                datapool "{DATAPOOL_IMPORT}"
                "go.uber.org/fx"
            )

            func TestExportedSymbols(t *testing.T) {{
                // Module must be an fx.Option.
                var _ fx.Option = datapool.Module

                // Constructors must return *Pool.
                p := datapool.NewPrimaryPool()
                r := datapool.NewReplicaPool()
                var _ *datapool.Pool = p
                var _ *datapool.Pool = r
                if p.Label != "primary" {{
                    t.Fatalf("NewPrimaryPool().Label = %q, want primary",
                        p.Label)
                }}
                if r.Label != "replica" {{
                    t.Fatalf("NewReplicaPool().Label = %q, want replica",
                        r.Label)
                }}

                // *Pool satisfies Store.
                var _ datapool.Store = p

                // Report has the three string fields.
                var rep datapool.Report
                rep.Primary = ""
                rep.Replica = ""
                rep.ViaInterface = ""
                _ = rep
            }}
            '''
        )
        dpath, target = _write_driver(
            "extdrive_iface", "symbols_test.go", source
        )
        try:
            proc = _run_go_test(target, extra_args=["-count=1", "-v"])
            assert proc.returncode == 0, (
                "independent exported-symbols driver failed (a required "
                "symbol is missing or has the wrong shape):\n"
                f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
            )
        finally:
            shutil.rmtree(dpath, ignore_errors=True)

    def test_newreport_depends_on_injected_pools_not_constructed(self):
        """L2: NewReport reflects the INJECTED pools, including overrides.

        Independent driver: boot Module but override the primary pool binding
        with a decorated/replaced value (via fx.Decorate on the named primary
        *Pool) and confirm the Report's Primary and ViaInterface both follow the
        injected primary — proving NewReport consumes injected dependencies
        rather than constructing its own pools or hardcoding strings.

        We discover the primary tag from source; if it cannot be inferred we
        skip the decoration (the exact-value test already pins behavior for the
        default graph).
        """
        wiring_path = os.path.join(PKG_DIR, "wiring.go")
        pool_path = os.path.join(PKG_DIR, "pool.go")
        text = ""
        for p in (wiring_path, pool_path):
            if os.path.isfile(p):
                with open(p) as fh:
                    text += fh.read() + "\n"
        import re

        names = re.findall(r'name:"([^"]+)"', text)
        primary_tag = next((n for n in names if "primary" in n.lower()), None)
        if primary_tag is None:
            pytest.skip(
                "could not infer the primary pool name tag for decoration; "
                "default-graph values are pinned by other tests"
            )

        source = textwrap.dedent(
            f'''
            package extdrive_iface

            import (
                "testing"

                datapool "{DATAPOOL_IMPORT}"
                "go.uber.org/fx"
                "go.uber.org/fx/fxtest"
            )

            func TestReportFollowsInjectedPrimary(t *testing.T) {{
                // Replace the named-primary *Pool with a sentinel pool.
                decorate := fx.Decorate(
                    fx.Annotate(
                        func(orig *datapool.Pool) *datapool.Pool {{
                            return &datapool.Pool{{Label: "decorated"}}
                        }},
                        fx.ParamTags(`name:"{primary_tag}"`),
                        fx.ResultTags(`name:"{primary_tag}"`),
                    ),
                )
                var rep *datapool.Report
                app := fxtest.New(t, datapool.Module, decorate,
                    fx.Populate(&rep))
                app.RequireStart().RequireStop()
                if rep == nil {{
                    t.Fatalf("Report not populated")
                }}
                // Both Primary and ViaInterface must follow the decorated
                // primary, proving they come from the injected named pool /
                // interface binding, not a hardcoded constructor.
                if rep.Primary != "pong:decorated" {{
                    t.Fatalf("Report.Primary did not follow injected primary: "+
                        "got %q, want pong:decorated", rep.Primary)
                }}
                if rep.ViaInterface != "pong:decorated" {{
                    t.Fatalf("Report.ViaInterface did not follow injected "+
                        "primary via Store: got %q, want pong:decorated",
                        rep.ViaInterface)
                }}
                // The replica must be unaffected by the primary decoration.
                if rep.Replica != "pong:replica" {{
                    t.Fatalf("Report.Replica changed unexpectedly: got %q, "+
                        "want pong:replica", rep.Replica)
                }}
            }}
            '''
        )
        dpath, target = _write_driver(
            "extdrive_iface", "decorate_test.go", source
        )
        try:
            proc = _run_go_test(target, extra_args=["-count=1", "-v"])
            combined = proc.stdout + proc.stderr
            if proc.returncode != 0:
                runtime_markers = (
                    "did not follow injected",
                    "changed unexpectedly",
                    "not populated",
                    "pong:decorated",
                )
                if any(m in combined for m in runtime_markers):
                    pytest.fail(
                        "Report does not consume the injected primary pool / "
                        "Store binding:\n" + combined
                    )
                pytest.skip(
                    "could not decorate the named-primary pool with inferred "
                    f"tag {primary_tag!r} (different wiring style); default "
                    "values pinned elsewhere:\n" + combined
                )
        finally:
            shutil.rmtree(dpath, ignore_errors=True)
