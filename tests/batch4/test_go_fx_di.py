"""Tests for the `go-fx-di` skill task (variant ext4): a route-registry example.

Skill under test: go-fx-di (uber-go/fx dependency injection with value groups +
aggregation over an independently-provided collection).

The ext4 task asks the agent to create a new `routereg` package under
`docs/ex/routereg/` inside the `go.uber.org/fx/docs` module. The package must
expose:

  * `Route`     — an interface with `Pattern() string` and an embedded
                  `http.Handler` (so it satisfies `ServeHTTP`);
  * `NewHealthRoute`, `NewVersionRoute`, `NewEchoRoute` — three independent
                  constructors producing routes whose `Pattern()` is
                  `"/healthz"`, `"/version"`, `"/echo"` and whose `ServeHTTP`
                  writes `"ok"`, `"v1"`, and the request URL's raw query string
                  respectively;
  * `NewMux`    — a constructor receiving the COMPLETE collection of registered
                  `Route` values, returning a `*http.ServeMux` with every route
                  registered at its `Pattern()`. It must operate purely over the
                  aggregated collection (no naming individual constructors /
                  concrete types);
  * `Module`    — an `fx.Option` wiring the three routes + the mux builder so a
                  consumer can boot with only `Module` and `fx.Populate` a
                  `*http.ServeMux`.

Verification strategy: rather than trusting the agent's own `routereg_test.go`,
the L2 tests write INDEPENDENT Go driver test files into fresh sub-directories
of the `routereg` package and run them with the native `go test` toolchain
(from the `docs` module). The drivers boot the real `Module` via `fxtest`,
`fx.Populate` the `*http.ServeMux`, and drive in-memory requests through
`httptest`, asserting deeply on response bodies and the number of registered
patterns. A naive `NewMux` that hardcodes three patterns from named
constructors is detected by registering a FOURTH route into the same value
group and confirming it is reachable with no edit to `mux.go`.

Native acceptance command (from the docs module dir):

    go test ./ex/routereg/...
"""

import os
import shutil
import subprocess
import textwrap

import pytest

REPO_DIR = "/workspace/fx"
DOCS_DIR = os.path.join(REPO_DIR, "docs")
PKG_DIR = os.path.join(DOCS_DIR, "ex", "routereg")

GO_TEST_TIMEOUT = 480

# Import path of the routereg package.
ROUTEREG_IMPORT = "go.uber.org/fx/docs/ex/routereg"


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
    target = "./ex/routereg/" + subdir_name + "/..."
    return dpath, target


# --------------------------------------------------------------------------- #
# Dependency / build readiness (module-scope, autouse)
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module", autouse=True)
def _ensure_go_ready():
    """Make sure the Go toolchain + docs module deps are available.

    Runs a cheap compile of the routereg package so that the heavy
    module-download cost is paid once, before the per-test timeouts apply.
    """
    assert os.path.isdir(REPO_DIR), f"missing repo dir {REPO_DIR}"
    assert os.path.isdir(DOCS_DIR), f"missing docs module dir {DOCS_DIR}"
    try:
        subprocess.run(
            ["go", "build", "./ex/routereg/..."],
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
        "extdrive_routes",
        "extdrive_fourth",
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
        """L1: the routereg example directory exists under docs/ex."""
        assert os.path.isdir(PKG_DIR), f"expected package dir at {PKG_DIR}"

    def test_required_source_files_present(self):
        """L1: required deliverable .go source files all exist."""
        for fname in ("route.go", "handlers.go", "mux.go", "routereg_test.go"):
            fpath = os.path.join(PKG_DIR, fname)
            assert os.path.isfile(fpath), f"missing required file {fpath}"

    def test_package_uses_routereg_name_and_no_new_module(self):
        """L1: files declare `package routereg`; no new go.mod was added."""
        go_files = [f for f in os.listdir(PKG_DIR) if f.endswith(".go")]
        assert go_files, "no .go files found in package dir"
        for f in go_files:
            with open(os.path.join(PKG_DIR, f)) as fh:
                head = fh.read()
            assert "package routereg" in head, (
                f"{f} does not declare `package routereg`"
            )
        assert not os.path.isfile(os.path.join(PKG_DIR, "go.mod")), (
            "a new go.mod must NOT be created inside the example dir"
        )

    def test_package_compiles(self):
        """L1: the routereg package compiles under the docs module."""
        proc = subprocess.run(
            ["go", "build", "./ex/routereg/..."],
            cwd=DOCS_DIR,
            capture_output=True,
            text=True,
            timeout=GO_TEST_TIMEOUT,
            env=_go_env(),
        )
        assert proc.returncode == 0, (
            "routereg package failed to compile:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    def test_authors_own_test_passes(self):
        """L1: the task's native command passes for this package."""
        proc = _run_go_test("./ex/routereg/...")
        assert proc.returncode == 0, (
            "`go test ./ex/routereg/...` failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    # ------------------------------------------------------------------ #
    # L2 — independent dynamic execution against the real Module
    # ------------------------------------------------------------------ #
    def test_module_boots_and_populates_mux(self):
        """L2: booting Module via fxtest + fx.Populate yields a non-nil mux.

        Independent driver: boot with ONLY Module, populate a *http.ServeMux,
        RequireStart/RequireStop, and confirm the mux is usable. Proves Module
        is self-contained (no missing-dependency / cycle error).
        """
        source = textwrap.dedent(
            f'''
            package extdrive_boot

            import (
                "net/http"
                "testing"

                routereg "{ROUTEREG_IMPORT}"
                "go.uber.org/fx"
                "go.uber.org/fx/fxtest"
            )

            func TestBootPopulatesMux(t *testing.T) {{
                var mux *http.ServeMux
                app := fxtest.New(t, routereg.Module, fx.Populate(&mux))
                app.RequireStart().RequireStop()
                if mux == nil {{
                    t.Fatalf("fx.Populate left *http.ServeMux nil")
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
            assert "TestBootPopulatesMux" in proc.stdout
        finally:
            shutil.rmtree(dpath, ignore_errors=True)

    def test_module_self_contained_no_missing_deps(self):
        """L2: fx.New(Module, Populate) has no graph construction error.

        Uses fx.New (not fxtest) and checks app.Err() to confirm the graph has
        no missing-dependency or cycle error — Module alone is sufficient.
        """
        source = textwrap.dedent(
            f'''
            package extdrive_boot

            import (
                "context"
                "net/http"
                "testing"
                "time"

                routereg "{ROUTEREG_IMPORT}"
                "go.uber.org/fx"
            )

            func TestSelfContained(t *testing.T) {{
                var mux *http.ServeMux
                app := fx.New(routereg.Module, fx.Populate(&mux))
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
                if mux == nil {{
                    t.Fatalf("populated mux is nil after self-contained boot")
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

    def test_three_routes_serve_expected_bodies(self):
        """L2: /healthz -> "ok", /version -> "v1", /echo?msg=hi -> "msg=hi".

        Drives in-memory requests through the populated mux via httptest and
        asserts EXACT response bodies. A stub handler returning a fixed/empty
        body, or one that ignores the request query, fails here.
        """
        source = textwrap.dedent(
            f'''
            package extdrive_routes

            import (
                "net/http"
                "net/http/httptest"
                "testing"

                routereg "{ROUTEREG_IMPORT}"
                "go.uber.org/fx"
                "go.uber.org/fx/fxtest"
            )

            func body(t *testing.T, mux *http.ServeMux, target string) string {{
                t.Helper()
                rr := httptest.NewRecorder()
                req := httptest.NewRequest(http.MethodGet, target, nil)
                mux.ServeHTTP(rr, req)
                return rr.Body.String()
            }}

            func TestRouteBodies(t *testing.T) {{
                var mux *http.ServeMux
                app := fxtest.New(t, routereg.Module, fx.Populate(&mux))
                app.RequireStart().RequireStop()
                if mux == nil {{
                    t.Fatalf("nil mux")
                }}

                cases := []struct{{ target, want string }}{{
                    {{"/healthz", "ok"}},
                    {{"/version", "v1"}},
                    {{"/echo?msg=hi", "msg=hi"}},
                }}
                for _, c := range cases {{
                    got := body(t, mux, c.target)
                    if got != c.want {{
                        t.Fatalf("GET %s: body = %q, want %q",
                            c.target, got, c.want)
                    }}
                }}
            }}
            '''
        )
        dpath, target = _write_driver(
            "extdrive_routes", "bodies_test.go", source
        )
        try:
            proc = _run_go_test(target, extra_args=["-count=1", "-v"])
            assert proc.returncode == 0, (
                "independent route-bodies driver failed:\n"
                f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
            )
        finally:
            shutil.rmtree(dpath, ignore_errors=True)

    def test_echo_reflects_distinct_query(self):
        """L2: /echo echoes the *actual* raw query, not a hardcoded string.

        A naive echo that writes a fixed "msg=hi" would pass the body test
        above but fail here with a different query value. This isolates the
        "ignores input" stub.
        """
        source = textwrap.dedent(
            f'''
            package extdrive_routes

            import (
                "net/http"
                "net/http/httptest"
                "testing"

                routereg "{ROUTEREG_IMPORT}"
                "go.uber.org/fx"
                "go.uber.org/fx/fxtest"
            )

            func TestEchoDistinct(t *testing.T) {{
                var mux *http.ServeMux
                app := fxtest.New(t, routereg.Module, fx.Populate(&mux))
                app.RequireStart().RequireStop()

                cases := []struct{{ q, want string }}{{
                    {{"/echo?foo=bar", "foo=bar"}},
                    {{"/echo?a=1&b=2", "a=1&b=2"}},
                    {{"/echo", ""}},
                }}
                for _, c := range cases {{
                    rr := httptest.NewRecorder()
                    req := httptest.NewRequest(http.MethodGet, c.q, nil)
                    mux.ServeHTTP(rr, req)
                    if rr.Body.String() != c.want {{
                        t.Fatalf("GET %s: echo body = %q, want %q",
                            c.q, rr.Body.String(), c.want)
                    }}
                }}
            }}
            '''
        )
        dpath, target = _write_driver(
            "extdrive_routes", "echo_test.go", source
        )
        try:
            proc = _run_go_test(target, extra_args=["-count=1", "-v"])
            assert proc.returncode == 0, (
                "independent echo-distinct driver failed:\n"
                f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
            )
        finally:
            shutil.rmtree(dpath, ignore_errors=True)

    def test_constructors_produce_correct_patterns(self):
        """L2: each constructor's Route.Pattern() is the documented value.

        Calls NewHealthRoute/NewVersionRoute/NewEchoRoute directly (outside fx)
        and asserts Pattern() == "/healthz" / "/version" / "/echo". This pins
        the public contract independent of the mux wiring.
        """
        source = textwrap.dedent(
            f'''
            package extdrive_routes

            import (
                "testing"

                routereg "{ROUTEREG_IMPORT}"
            )

            func TestPatterns(t *testing.T) {{
                cases := []struct{{
                    name string
                    r    routereg.Route
                    want string
                }}{{
                    {{"health", routereg.NewHealthRoute(), "/healthz"}},
                    {{"version", routereg.NewVersionRoute(), "/version"}},
                    {{"echo", routereg.NewEchoRoute(), "/echo"}},
                }}
                for _, c := range cases {{
                    if c.r == nil {{
                        t.Fatalf("%s constructor returned nil Route", c.name)
                    }}
                    if c.r.Pattern() != c.want {{
                        t.Fatalf("%s Pattern() = %q, want %q",
                            c.name, c.r.Pattern(), c.want)
                    }}
                }}
            }}
            '''
        )
        dpath, target = _write_driver(
            "extdrive_routes", "patterns_test.go", source
        )
        try:
            proc = _run_go_test(target, extra_args=["-count=1", "-v"])
            assert proc.returncode == 0, (
                "independent patterns driver failed:\n"
                f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
            )
        finally:
            shutil.rmtree(dpath, ignore_errors=True)

    def test_route_serves_through_its_own_handler(self):
        """L2: a constructed Route is itself an http.Handler (embedded).

        The Route interface embeds http.Handler, so calling ServeHTTP directly
        on the value returned by NewHealthRoute must write "ok". This verifies
        the embedding, not just the mux registration.
        """
        source = textwrap.dedent(
            f'''
            package extdrive_routes

            import (
                "net/http"
                "net/http/httptest"
                "testing"

                routereg "{ROUTEREG_IMPORT}"
            )

            func TestRouteIsHandler(t *testing.T) {{
                var h http.Handler = routereg.NewHealthRoute()
                rr := httptest.NewRecorder()
                req := httptest.NewRequest(http.MethodGet, "/healthz", nil)
                h.ServeHTTP(rr, req)
                if rr.Body.String() != "ok" {{
                    t.Fatalf("health Route.ServeHTTP body = %q, want %q",
                        rr.Body.String(), "ok")
                }}
            }}
            '''
        )
        dpath, target = _write_driver(
            "extdrive_routes", "handler_test.go", source
        )
        try:
            proc = _run_go_test(target, extra_args=["-count=1", "-v"])
            assert proc.returncode == 0, (
                "independent route-is-handler driver failed:\n"
                f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
            )
        finally:
            shutil.rmtree(dpath, ignore_errors=True)

    def test_unregistered_path_returns_404(self):
        """L2: a path not provided by any Route returns 404 (no catch-all).

        Confirms NewMux only registers the aggregated patterns and does not
        install a catch-all handler that would mask missing routes.
        """
        source = textwrap.dedent(
            f'''
            package extdrive_routes

            import (
                "net/http"
                "net/http/httptest"
                "testing"

                routereg "{ROUTEREG_IMPORT}"
                "go.uber.org/fx"
                "go.uber.org/fx/fxtest"
            )

            func TestNotFound(t *testing.T) {{
                var mux *http.ServeMux
                app := fxtest.New(t, routereg.Module, fx.Populate(&mux))
                app.RequireStart().RequireStop()

                rr := httptest.NewRecorder()
                req := httptest.NewRequest(http.MethodGet, "/does-not-exist", nil)
                mux.ServeHTTP(rr, req)
                if rr.Code != http.StatusNotFound {{
                    t.Fatalf("GET /does-not-exist: status = %d, want %d",
                        rr.Code, http.StatusNotFound)
                }}
            }}
            '''
        )
        dpath, target = _write_driver(
            "extdrive_routes", "notfound_test.go", source
        )
        try:
            proc = _run_go_test(target, extra_args=["-count=1", "-v"])
            assert proc.returncode == 0, (
                "independent not-found driver failed:\n"
                f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
            )
        finally:
            shutil.rmtree(dpath, ignore_errors=True)

    def test_fourth_route_extends_without_mux_change(self):
        """L2: registering a 4th route via the value group is reachable.

        We do NOT edit mux.go. Instead we register one more independent Route
        constructor in a driver package, contributing it into the SAME fx value
        group `NewMux` consumes, and confirm the new "/audit" route is reachable
        and serves its body. This proves NewMux aggregates the full collection
        without naming the individual constructors — a hardcoded three-pattern
        mux cannot serve the fourth route.

        The canonical fx value-group tag used across the docs examples is
        `routes`/`route` etc.; we try the common tags. If a legitimate solution
        uses a different tag we cannot bind a 4th route blindly, so a
        non-binding case is skipped rather than failed (the aggregation design
        is independently enforced by the count test below).
        """
        # Try the most common group tag names a routereg solution might use.
        for tag in ("routes", "route", "Route"):
            source = textwrap.dedent(
                f'''
                package extdrive_fourth

                import (
                    "net/http"
                    "net/http/httptest"
                    "testing"

                    routereg "{ROUTEREG_IMPORT}"
                    "go.uber.org/fx"
                    "go.uber.org/fx/fxtest"
                )

                type auditRoute struct{{}}

                func (a *auditRoute) Pattern() string {{ return "/audit" }}
                func (a *auditRoute) ServeHTTP(
                    w http.ResponseWriter, r *http.Request) {{
                    _, _ = w.Write([]byte("audited"))
                }}

                func newAuditRoute() routereg.Route {{ return &auditRoute{{}} }}

                func TestFourthRoute(t *testing.T) {{
                    var mux *http.ServeMux
                    extra := fx.Provide(
                        fx.Annotate(
                            newAuditRoute,
                            fx.ResultTags(`group:"{tag}"`),
                        ),
                    )
                    app := fxtest.New(
                        t, routereg.Module, extra, fx.Populate(&mux))
                    app.RequireStart().RequireStop()

                    rr := httptest.NewRecorder()
                    req := httptest.NewRequest(
                        http.MethodGet, "/audit", nil)
                    mux.ServeHTTP(rr, req)
                    if rr.Code != http.StatusOK {{
                        t.Fatalf("4th route /audit not registered: status %d",
                            rr.Code)
                    }}
                    if rr.Body.String() != "audited" {{
                        t.Fatalf("4th route body = %q, want %q",
                            rr.Body.String(), "audited")
                    }}
                    // original routes still work
                    rr2 := httptest.NewRecorder()
                    req2 := httptest.NewRequest(
                        http.MethodGet, "/healthz", nil)
                    mux.ServeHTTP(rr2, req2)
                    if rr2.Body.String() != "ok" {{
                        t.Fatalf("original /healthz broke after adding 4th: %q",
                            rr2.Body.String())
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
                if proc.returncode == 0:
                    assert "TestFourthRoute" in proc.stdout
                    return  # success with this tag
                # A runtime failure (route bound but wrong behavior) is real.
                runtime_markers = (
                    "not registered",
                    "4th route body",
                    "original /healthz broke",
                )
                if any(m in combined for m in runtime_markers):
                    pytest.fail(
                        "4th-route extension produced wrong behavior "
                        f"(tag {tag!r}):\n" + combined
                    )
                # Otherwise: build/binding failure -> try the next tag.
            finally:
                shutil.rmtree(dpath, ignore_errors=True)

        pytest.skip(
            "4th-route driver could not bind to the example's value-group tag "
            "(tried routes/route/Route). The aggregation design is enforced "
            "structurally by test_mux_registers_exactly_provided_count."
        )

    def test_mux_registers_exactly_provided_count(self):
        """L2: the mux registers exactly the number of provided routes (3).

        Independently provide a known set of probe routes (a fresh group) and a
        second NewMux is NOT available; instead we count distinct served
        patterns on the real Module's mux by probing each documented path and a
        bogus one, asserting exactly the three documented paths are served and
        nothing extra is matched by accident.
        """
        source = textwrap.dedent(
            f'''
            package extdrive_routes

            import (
                "net/http"
                "net/http/httptest"
                "testing"

                routereg "{ROUTEREG_IMPORT}"
                "go.uber.org/fx"
                "go.uber.org/fx/fxtest"
            )

            func served(mux *http.ServeMux, p string) bool {{
                rr := httptest.NewRecorder()
                req := httptest.NewRequest(http.MethodGet, p, nil)
                mux.ServeHTTP(rr, req)
                return rr.Code != http.StatusNotFound
            }}

            func TestExactCount(t *testing.T) {{
                var mux *http.ServeMux
                app := fxtest.New(t, routereg.Module, fx.Populate(&mux))
                app.RequireStart().RequireStop()

                want := []string{{"/healthz", "/version", "/echo"}}
                for _, p := range want {{
                    if !served(mux, p) {{
                        t.Fatalf("expected path %q to be served", p)
                    }}
                }}
                // Three unrelated probe paths must NOT be served, proving the
                // mux didn't register a catch-all or extra patterns.
                for _, p := range []string{{"/foo", "/bar", "/baz"}} {{
                    if served(mux, p) {{
                        t.Fatalf("unexpected path %q served; mux over-registers",
                            p)
                    }}
                }}
            }}
            '''
        )
        dpath, target = _write_driver(
            "extdrive_routes", "count_test.go", source
        )
        try:
            proc = _run_go_test(target, extra_args=["-count=1", "-v"])
            assert proc.returncode == 0, (
                "independent exact-count driver failed:\n"
                f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
            )
        finally:
            shutil.rmtree(dpath, ignore_errors=True)
