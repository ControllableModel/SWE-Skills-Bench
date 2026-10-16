"""Tests for the `go-fx-di` skill task (ext6 variant): a pre-built config +
test-override example app.

Skill under test: go-fx-di (uber-go/fx dependency injection — pre-built values
that enter the graph without a fabricating constructor, plus swapping a real
dependency for a fake in a test without rewiring the application).

The task asks the agent to create a new `configsvc` package under
`docs/ex/configsvc/` inside the `go.uber.org/fx/docs` module. The package must
expose:

  * `Config` — an exported struct value type with fields `Greeting string`
    and `Suffix string`. It enters the graph as a *pre-built value* (e.g. via
    `fx.Supply`), NOT as the output of a constructor that fabricates it.
  * `Clock` — an exported interface with `Now() string`, a real
    implementation `SystemClock`, and a constructor `NewSystemClock`
    returning a `Clock`.
  * `Greeter` — an exported struct with method `Greet(name string) string`
    returning `Config.Greeting + " " + name + Config.Suffix + " @" + clock.Now()`,
    plus constructor `NewGreeter` depending on `Config` and `Clock`.
  * `Module` — an `fx.Option` that provides `Clock` and `Greeter` and consumes
    `Config`.
  * `Base` — an `fx.Option` that supplies the default pre-built
    `Config{Greeting:"Hello", Suffix:"!"}`.

Verification strategy: rather than trusting the agent's own
`configsvc_test.go`, the L2 tests write INDEPENDENT Go driver test files into a
fresh sub-directory of the `configsvc` package and run them with the native
`go test` toolchain from the `docs` module. These drivers boot the real
`Module` via `fxtest`, override the pre-built `Config` and replace the real
`Clock` with a deterministic fake (returning `"T0"`), and assert the exact
`Greet(...)` string. A naive implementation that hardcodes the greeting inside
`Greeter` (ignoring the supplied `Config`) — or that ignores the injected
`Clock` — cannot pass these drivers.

Native acceptance command (run from the docs module dir):

    cd docs && go test ./ex/configsvc/...
"""

import os
import shutil
import subprocess
import textwrap

import pytest

REPO_DIR = "/workspace/fx"
DOCS_DIR = os.path.join(REPO_DIR, "docs")
PKG_DIR = os.path.join(DOCS_DIR, "ex", "configsvc")

GO_TEST_TIMEOUT = 480

# Import path of the configsvc package under the docs module.
CONFIGSVC_IMPORT = "go.uber.org/fx/docs/ex/configsvc"


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
    target = "./ex/configsvc/" + subdir_name + "/..."
    return dpath, target


# --------------------------------------------------------------------------- #
# Dependency / build readiness (module-scope, autouse)
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module", autouse=True)
def _ensure_go_ready():
    """Make sure the Go toolchain + docs module deps are available.

    Runs a cheap compile of the configsvc package so the heavy module-download
    cost is paid once, before the per-test timeouts apply.
    """
    assert os.path.isdir(REPO_DIR), f"missing repo dir {REPO_DIR}"
    assert os.path.isdir(DOCS_DIR), f"missing docs module dir {DOCS_DIR}"
    try:
        subprocess.run(
            ["go", "build", "./ex/configsvc/..."],
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
        "extdrive_default",
        "extdrive_override",
        "extdrive_clock",
        "extdrive_wiring",
        "extdrive_prebuilt",
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
        """L1: the configsvc example directory exists under docs/ex."""
        assert os.path.isdir(PKG_DIR), f"expected package dir at {PKG_DIR}"

    def test_required_source_files_present(self):
        """L1: required deliverable .go source files all exist."""
        for fname in ("config.go", "service.go", "app.go",
                      "configsvc_test.go"):
            fpath = os.path.join(PKG_DIR, fname)
            assert os.path.isfile(fpath), f"missing required file {fpath}"

    def test_package_uses_configsvc_name_and_no_new_module(self):
        """L1: every .go file declares `package configsvc`; no new go.mod."""
        go_files = [f for f in os.listdir(PKG_DIR) if f.endswith(".go")]
        assert go_files, "no .go files found in package dir"
        for f in go_files:
            with open(os.path.join(PKG_DIR, f)) as fh:
                head = fh.read()
            assert "package configsvc" in head, (
                f"{f} does not declare `package configsvc`"
            )
        assert not os.path.isfile(os.path.join(PKG_DIR, "go.mod")), (
            "a new go.mod must NOT be created inside the example dir"
        )

    def test_package_compiles(self):
        """L1: the configsvc package compiles under the docs module."""
        proc = subprocess.run(
            ["go", "build", "./ex/configsvc/..."],
            cwd=DOCS_DIR,
            capture_output=True,
            text=True,
            timeout=GO_TEST_TIMEOUT,
            env=_go_env(),
        )
        assert proc.returncode == 0, (
            "configsvc package failed to compile:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    def test_authors_own_test_passes(self):
        """L1: the task's native command passes for this package.

        Drives exactly `go test ./ex/configsvc/...` from the docs module.
        """
        proc = _run_go_test("./ex/configsvc/...")
        assert proc.returncode == 0, (
            "`go test ./ex/configsvc/...` failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    # ------------------------------------------------------------------ #
    # L2 — independent dynamic execution against the real Module
    # ------------------------------------------------------------------ #
    def test_default_config_with_fake_clock(self):
        """L2: Base + Module + fake clock yields the exact default greeting.

        Independent driver: boot `Module` with the default pre-built `Config`
        ({Greeting:"Hello", Suffix:"!"}) and a fake clock returning "T0",
        populate a *Greeter, and assert Greet("Sam") == "Hello Sam! @T0".

        A solution that hardcodes the clock value (ignores the injected Clock)
        cannot produce the "@T0" suffix and fails here.
        """
        source = textwrap.dedent(
            f'''
            package extdrive_default

            import (
                "testing"

                configsvc "{CONFIGSVC_IMPORT}"
                "go.uber.org/fx"
                "go.uber.org/fx/fxtest"
            )

            type fakeClock struct{{}}

            func (fakeClock) Now() string {{ return "T0" }}

            func newFakeClock() configsvc.Clock {{ return fakeClock{{}} }}

            func TestDefaultConfig(t *testing.T) {{
                var g *configsvc.Greeter
                app := fxtest.New(
                    t,
                    configsvc.Module,
                    // default pre-built config, supplied independently
                    fx.Supply(configsvc.Config{{Greeting: "Hello", Suffix: "!"}}),
                    // replace the real Clock provided by Module with a fake
                    fx.Decorate(newFakeClock),
                    fx.Populate(&g),
                )
                app.RequireStart().RequireStop()

                if g == nil {{
                    t.Fatalf("Greeter was not populated")
                }}
                got := g.Greet("Sam")
                want := "Hello Sam! @T0"
                if got != want {{
                    t.Fatalf("Greet mismatch: got %q want %q", got, want)
                }}
            }}
            '''
        )
        dpath, target = _write_driver(
            "extdrive_default", "default_test.go", source
        )
        try:
            proc = _run_go_test(target, extra_args=["-count=1", "-v"])
            assert proc.returncode == 0, (
                "independent default-config driver failed:\n"
                f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
            )
            assert "TestDefaultConfig" in proc.stdout
        finally:
            shutil.rmtree(dpath, ignore_errors=True)

    def test_overridden_config_changes_output(self):
        """L2: swapping the pre-built Config (no Module edit) changes output.

        Boot `Module` with an overridden pre-built Config{Greeting:"Hi",
        Suffix:"?"} plus the same fake clock and assert
        Greet("Sam") == "Hi Sam? @T0".

        This is the discriminative case from the doc: a naive implementation
        that hardcodes the greeting inside Greeter (ignoring the supplied
        Config) still emits "Hello Sam! ..." and FAILS this assertion.
        """
        source = textwrap.dedent(
            f'''
            package extdrive_override

            import (
                "testing"

                configsvc "{CONFIGSVC_IMPORT}"
                "go.uber.org/fx"
                "go.uber.org/fx/fxtest"
            )

            type fakeClock struct{{}}

            func (fakeClock) Now() string {{ return "T0" }}

            func newFakeClock() configsvc.Clock {{ return fakeClock{{}} }}

            func TestOverriddenConfig(t *testing.T) {{
                var g *configsvc.Greeter
                app := fxtest.New(
                    t,
                    configsvc.Module,
                    fx.Supply(configsvc.Config{{Greeting: "Hi", Suffix: "?"}}),
                    fx.Decorate(newFakeClock),
                    fx.Populate(&g),
                )
                app.RequireStart().RequireStop()

                if g == nil {{
                    t.Fatalf("Greeter was not populated")
                }}
                got := g.Greet("Sam")
                want := "Hi Sam? @T0"
                if got != want {{
                    t.Fatalf("Greet did not reflect overridden config: "+
                        "got %q want %q (hardcoded greeting?)", got, want)
                }}
            }}
            '''
        )
        dpath, target = _write_driver(
            "extdrive_override", "override_test.go", source
        )
        try:
            proc = _run_go_test(target, extra_args=["-count=1", "-v"])
            assert proc.returncode == 0, (
                "independent overridden-config driver failed:\n"
                f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
            )
            assert "TestOverriddenConfig" in proc.stdout
        finally:
            shutil.rmtree(dpath, ignore_errors=True)

    def test_clock_is_actually_injected(self):
        """L2: the Greeter uses the injected Clock, not a hardcoded value.

        Replace the Clock with a fake returning a distinctive sentinel and
        confirm that sentinel appears verbatim in the output. A solution that
        ignores the Clock dependency (hardcodes the timestamp portion) fails.
        """
        source = textwrap.dedent(
            f'''
            package extdrive_clock

            import (
                "strings"
                "testing"

                configsvc "{CONFIGSVC_IMPORT}"
                "go.uber.org/fx"
                "go.uber.org/fx/fxtest"
            )

            type sentinelClock struct{{}}

            func (sentinelClock) Now() string {{ return "ZZZ-SENTINEL-9" }}

            func newSentinelClock() configsvc.Clock {{ return sentinelClock{{}} }}

            func TestClockInjected(t *testing.T) {{
                var g *configsvc.Greeter
                app := fxtest.New(
                    t,
                    configsvc.Module,
                    fx.Supply(configsvc.Config{{Greeting: "Hey", Suffix: "."}}),
                    fx.Decorate(newSentinelClock),
                    fx.Populate(&g),
                )
                app.RequireStart().RequireStop()

                if g == nil {{
                    t.Fatalf("Greeter was not populated")
                }}
                got := g.Greet("Ann")
                want := "Hey Ann. @ZZZ-SENTINEL-9"
                if got != want {{
                    t.Fatalf("clock not injected / wrong format: got %q want %q",
                        got, want)
                }}
                if !strings.Contains(got, "@ZZZ-SENTINEL-9") {{
                    t.Fatalf("injected clock value missing from output: %q", got)
                }}
            }}
            '''
        )
        dpath, target = _write_driver(
            "extdrive_clock", "clock_test.go", source
        )
        try:
            proc = _run_go_test(target, extra_args=["-count=1", "-v"])
            assert proc.returncode == 0, (
                "independent clock-injection driver failed:\n"
                f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
            )
            assert "TestClockInjected" in proc.stdout
        finally:
            shutil.rmtree(dpath, ignore_errors=True)

    def test_base_plus_module_boots_with_real_clock(self):
        """L2: Base + Module (real SystemClock) boots with no missing-dep/cycle.

        Uses fx.New (not fxtest) so we can inspect app.Err() directly: booting
        the default Base together with Module must construct cleanly, populate a
        non-nil *Greeter, and Greet must start with the default greeting and the
        default suffix even though the real clock value is non-deterministic.
        """
        source = textwrap.dedent(
            f'''
            package extdrive_wiring

            import (
                "context"
                "strings"
                "testing"
                "time"

                configsvc "{CONFIGSVC_IMPORT}"
                "go.uber.org/fx"
            )

            func TestBasePlusModule(t *testing.T) {{
                var g *configsvc.Greeter
                app := fx.New(
                    configsvc.Base,
                    configsvc.Module,
                    fx.Populate(&g),
                )
                if err := app.Err(); err != nil {{
                    t.Fatalf("graph construction error "+
                        "(missing dep/cycle?): %v", err)
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

                if g == nil {{
                    t.Fatalf("Greeter not populated by Base+Module")
                }}
                got := g.Greet("Sam")
                // default Base config is {{Greeting:"Hello", Suffix:"!"}}
                if !strings.HasPrefix(got, "Hello Sam!") {{
                    t.Fatalf("default Base config not applied: got %q "+
                        "(want prefix %q)", got, "Hello Sam!")
                }}
                if !strings.Contains(got, " @") {{
                    t.Fatalf("clock suffix marker ' @' missing from %q", got)
                }}
            }}
            '''
        )
        dpath, target = _write_driver(
            "extdrive_wiring", "wiring_test.go", source
        )
        try:
            proc = _run_go_test(target, extra_args=["-count=1", "-v"])
            assert proc.returncode == 0, (
                "independent Base+Module wiring driver failed:\n"
                f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
            )
            assert "TestBasePlusModule" in proc.stdout
        finally:
            shutil.rmtree(dpath, ignore_errors=True)

    def test_module_requires_a_config_to_be_supplied(self):
        """L2: Module consumes Config; without any Config the graph errors.

        Booting `Module` alone (no Base, no supplied Config) must fail graph
        construction with a missing-dependency error. This proves Module does
        NOT fabricate the Config itself via a constructor — the value must be
        pre-built and supplied from outside.
        """
        source = textwrap.dedent(
            f'''
            package extdrive_prebuilt

            import (
                "testing"

                configsvc "{CONFIGSVC_IMPORT}"
                "go.uber.org/fx"
            )

            func TestModuleNeedsConfig(t *testing.T) {{
                var g *configsvc.Greeter
                // Module alone, with NO Config supplied: must be a missing dep.
                app := fx.New(
                    configsvc.Module,
                    fx.Populate(&g),
                )
                if err := app.Err(); err == nil {{
                    t.Fatalf("expected a missing-Config error when booting "+
                        "Module without any supplied Config; got nil "+
                        "(Module must not fabricate Config)")
                }}
            }}
            '''
        )
        dpath, target = _write_driver(
            "extdrive_prebuilt", "needsconfig_test.go", source
        )
        try:
            proc = _run_go_test(target, extra_args=["-count=1", "-v"])
            assert proc.returncode == 0, (
                "independent missing-config driver failed:\n"
                f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
            )
            assert "TestModuleNeedsConfig" in proc.stdout
        finally:
            shutil.rmtree(dpath, ignore_errors=True)

    def test_greet_format_concatenation_is_exact(self):
        """L2: Greet builds Greeting + ' ' + name + Suffix + ' @' + Now().

        Drives several (greeting, suffix, name) triples with a fixed fake clock
        and asserts the exact concatenation for each, pinning the spacing and
        the literal '@' separator. A stub that drops the name, the suffix, or
        the space-before-@ fails at least one case.
        """
        source = textwrap.dedent(
            f'''
            package extdrive_clock

            import (
                "testing"

                configsvc "{CONFIGSVC_IMPORT}"
                "go.uber.org/fx"
                "go.uber.org/fx/fxtest"
            )

            type fixedClock struct{{ v string }}

            func (c fixedClock) Now() string {{ return c.v }}

            func build(t *testing.T, cfg configsvc.Config,
                clk configsvc.Clock) *configsvc.Greeter {{
                var g *configsvc.Greeter
                app := fxtest.New(
                    t,
                    configsvc.Module,
                    fx.Supply(cfg),
                    fx.Decorate(func() configsvc.Clock {{ return clk }}),
                    fx.Populate(&g),
                )
                app.RequireStart().RequireStop()
                if g == nil {{
                    t.Fatalf("Greeter not populated")
                }}
                return g
            }}

            func TestGreetFormat(t *testing.T) {{
                cases := []struct {{
                    greeting, suffix, name, now, want string
                }}{{
                    {{"Hello", "!", "Sam", "T0", "Hello Sam! @T0"}},
                    {{"Hi", "?", "Sam", "T0", "Hi Sam? @T0"}},
                    {{"Yo", "", "Bee", "CLK1", "Yo Bee @CLK1"}},
                    {{"Welcome", ".", "Dr. X", "9", "Welcome Dr. X. @9"}},
                }}
                for _, c := range cases {{
                    g := build(t, configsvc.Config{{
                        Greeting: c.greeting, Suffix: c.suffix,
                    }}, fixedClock{{v: c.now}})
                    got := g.Greet(c.name)
                    if got != c.want {{
                        t.Fatalf("Greet(%q) with greeting=%q suffix=%q now=%q: "+
                            "got %q want %q", c.name, c.greeting, c.suffix,
                            c.now, got, c.want)
                    }}
                }}
            }}
            '''
        )
        dpath, target = _write_driver(
            "extdrive_clock", "format_test.go", source
        )
        try:
            proc = _run_go_test(target, extra_args=["-count=1", "-v"])
            assert proc.returncode == 0, (
                "independent greet-format driver failed:\n"
                f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
            )
            assert "TestGreetFormat" in proc.stdout
        finally:
            shutil.rmtree(dpath, ignore_errors=True)

    def test_system_clock_now_is_nonempty(self):
        """L2: NewSystemClock returns a real Clock whose Now() is non-empty.

        Confirms the real implementation actually produces a value (so the
        '@<time>' portion is never blank for the production wiring), exercising
        NewSystemClock / SystemClock directly without fx.
        """
        source = textwrap.dedent(
            f'''
            package extdrive_clock

            import (
                "testing"

                configsvc "{CONFIGSVC_IMPORT}"
            )

            func TestSystemClockNonEmpty(t *testing.T) {{
                c := configsvc.NewSystemClock()
                if c == nil {{
                    t.Fatalf("NewSystemClock returned nil Clock")
                }}
                if got := c.Now(); got == "" {{
                    t.Fatalf("SystemClock.Now() returned empty string")
                }}
            }}
            '''
        )
        dpath, target = _write_driver(
            "extdrive_clock", "sysclock_test.go", source
        )
        try:
            proc = _run_go_test(target, extra_args=["-count=1", "-v"])
            assert proc.returncode == 0, (
                "independent system-clock driver failed:\n"
                f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
            )
            assert "TestSystemClockNonEmpty" in proc.stdout
        finally:
            shutil.rmtree(dpath, ignore_errors=True)
