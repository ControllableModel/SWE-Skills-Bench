"""Tests for skill `go-monads-mo` (variant ext7).

Verifies the task "Add Map, FlatMap, and ToResult Methods to the IO Monad" of
`github.com/samber/mo`.

The task adds three methods to the existing `IO[R]` type in `io.go`, keeping
the single type parameter `R` and the existing `NewIO`/`Run` semantics:

  - func (io IO[R]) Map(mapper func(R) R) IO[R]
        lazy: builds a new IO that, on Run(), runs the receiver then applies
        mapper. Constructing it must NOT run the receiver or mapper.
  - func (io IO[R]) FlatMap(mapper func(R) IO[R]) IO[R]
        lazy: on Run(), runs the receiver, feeds its value to mapper to get a
        second IO, runs that, returns its value.
  - func (io IO[R]) ToResult() Result[R]
        runs the receiver; Ok(value) on success; on panic captures the panic
        into an error Result (an error panic preserves the error, a non-error
        panic is wrapped into an error).

Verification strategy:
  - L1: the deliverable file `io.go` exists, the three methods are declared
    with real signatures (checked via `go doc`, the toolchain's own symbol
    resolver, not text grep), and the whole module still builds.
  - L2: this test injects its OWN independent Go driver test files into the
    repo root package `mo` and runs them with `go test -run`. The drivers
    exercise concrete runtime behavior: composition results (42), laziness via
    a side-effect counter, exactly-once execution, and panic capture into a
    Result carrying the original error. Drivers are authored HERE (not by the
    agent), so a stub (eager construction, ignored mapper, hardcoded return,
    swallowed panic) fails.
"""

import os
import subprocess
import textwrap

import pytest

REPO_DIR = "/workspace/mo"

GO_TIMEOUT = 600


def _run(args, cwd, timeout=GO_TIMEOUT, env_extra=None):
    env = dict(os.environ)
    # Make sure go has a writable cache/home even with a cleared environment.
    env.setdefault("HOME", "/root")
    env.setdefault("GOFLAGS", "")
    if "GOCACHE" not in env:
        env["GOCACHE"] = os.path.join(REPO_DIR, ".gocache_bench")
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        args, cwd=cwd, capture_output=True, text=True, timeout=timeout, env=env
    )


@pytest.fixture(scope="module", autouse=True)
def _go_env_ready():
    """Ensure the module builds and dependencies are available before tests."""
    assert os.path.isdir(REPO_DIR), f"repo not found at {REPO_DIR}"
    # Populate the module/build cache once; ignore failures here (individual
    # tests assert on their own commands).
    _run(["go", "build", "./..."], cwd=REPO_DIR, timeout=GO_TIMEOUT)
    yield


def _write_driver(rel_dir, filename, src):
    """Write a Go test driver into REPO_DIR/<rel_dir>/<filename>."""
    path = os.path.join(REPO_DIR, rel_dir, filename)
    with open(path, "w") as fh:
        fh.write(textwrap.dedent(src))
    return path


def _run_driver(rel_dir, filename, src, run_regex):
    """Write a driver, run only its test via `go test -run`, then clean up."""
    path = _write_driver(rel_dir, filename, src)
    try:
        proc = _run(
            ["go", "test", "-count=1", "-run", run_regex, "."],
            cwd=os.path.join(REPO_DIR, rel_dir),
        )
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
    return proc


class TestGoMonadsMo:
    REPO_DIR = "/workspace/mo"

    # ------------------------------------------------------------------ L1 ---

    def test_io_file_exists(self):
        """L1: io.go (the deliverable to modify) exists."""
        assert os.path.isfile(os.path.join(REPO_DIR, "io.go"))

    def test_map_method_declared(self):
        """L1: IO[R].Map is a declared method with a func signature.

        Uses `go doc` so only a genuine method declaration counts, not a
        comment or string mention.
        """
        proc = _run(["go", "doc", "IO.Map"], cwd=REPO_DIR)
        assert proc.returncode == 0, (
            f"go doc IO.Map failed:\n{proc.stdout}\n{proc.stderr}"
        )
        assert "func " in proc.stdout, f"IO.Map is not a method: {proc.stdout}"
        assert "Map" in proc.stdout

    def test_flatmap_method_declared(self):
        """L1: IO[R].FlatMap is a declared method with a func signature."""
        proc = _run(["go", "doc", "IO.FlatMap"], cwd=REPO_DIR)
        assert proc.returncode == 0, (
            f"go doc IO.FlatMap failed:\n{proc.stdout}\n{proc.stderr}"
        )
        assert "func " in proc.stdout, f"IO.FlatMap is not a method: {proc.stdout}"
        assert "FlatMap" in proc.stdout

    def test_toresult_method_declared(self):
        """L1: IO[R].ToResult is a declared method returning a Result."""
        proc = _run(["go", "doc", "IO.ToResult"], cwd=REPO_DIR)
        assert proc.returncode == 0, (
            f"go doc IO.ToResult failed:\n{proc.stdout}\n{proc.stderr}"
        )
        assert "func " in proc.stdout, f"IO.ToResult is not a method: {proc.stdout}"
        # ToResult must return a Result type.
        assert "Result" in proc.stdout, (
            f"IO.ToResult must return Result, got: {proc.stdout}"
        )

    def test_module_builds(self):
        """L1: the whole module compiles with the new code (go build ./...)."""
        proc = _run(["go", "build", "./..."], cwd=REPO_DIR)
        assert proc.returncode == 0, (
            f"go build ./... failed:\n{proc.stdout}\n{proc.stderr}"
        )

    def test_existing_io_suite_still_passes(self):
        """L1->L2: existing IO suite is not broken by the change."""
        proc = _run(["go", "test", "-count=1", "-run", "IO", "."], cwd=REPO_DIR)
        assert proc.returncode == 0, (
            f"go test -run IO . failed:\n{proc.stdout}\n{proc.stderr}"
        )

    # ------------------------------------------------------------------ L2 ---

    def test_map_composes_value(self):
        """L2: Map applies the mapper to the receiver's result.

        21 then *2 -> 42. A stub that ignores the mapper or returns the
        receiver's value unchanged fails.
        """
        src = """
        package mo

        import "testing"

        func TestBenchIOMapValue(t *testing.T) {
            got := NewIO(func() int { return 21 }).
                Map(func(n int) int { return n * 2 }).
                Run()
            if got != 42 {
                t.Fatalf("Map result = %d, want 42", got)
            }
        }
        """
        proc = _run_driver(".", "bench_io_map_value_test.go", src,
                           "TestBenchIOMapValue")
        assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"

    def test_map_chains(self):
        """L2: Map is chainable and each stage feeds the next in order.

        3 -> +1 (4) -> *10 (40) -> -2 (38). A stub returning a fixed value or
        applying a single mapper fails.
        """
        src = """
        package mo

        import "testing"

        func TestBenchIOMapChain(t *testing.T) {
            got := NewIO(func() int { return 3 }).
                Map(func(n int) int { return n + 1 }).
                Map(func(n int) int { return n * 10 }).
                Map(func(n int) int { return n - 2 }).
                Run()
            if got != 38 {
                t.Fatalf("chained Map result = %d, want 38", got)
            }
        }
        """
        proc = _run_driver(".", "bench_io_map_chain_test.go", src,
                           "TestBenchIOMapChain")
        assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"

    def test_map_is_lazy_and_runs_once(self):
        """L2: building via Map runs nothing; Run() executes effects exactly once.

        A counter starts at 0. After construction (Map without Run) it must
        still be 0 -> proves laziness. After one Run() both the receiver effect
        and the mapper effect have fired exactly once each. An eager impl that
        runs the receiver at construction time fails the pre-Run assertion; an
        impl that double-runs fails the post-Run count.
        """
        src = """
        package mo

        import "testing"

        func TestBenchIOMapLazyOnce(t *testing.T) {
            recvCalls := 0
            mapCalls := 0
            io := NewIO(func() int {
                recvCalls++
                return 5
            }).Map(func(n int) int {
                mapCalls++
                return n + 1
            })
            // Construction must not have executed anything.
            if recvCalls != 0 || mapCalls != 0 {
                t.Fatalf("construction not lazy: recv=%d map=%d", recvCalls, mapCalls)
            }
            got := io.Run()
            if got != 6 {
                t.Fatalf("Run result = %d, want 6", got)
            }
            if recvCalls != 1 {
                t.Fatalf("receiver ran %d times, want exactly 1", recvCalls)
            }
            if mapCalls != 1 {
                t.Fatalf("mapper ran %d times, want exactly 1", mapCalls)
            }
        }
        """
        proc = _run_driver(".", "bench_io_map_lazy_test.go", src,
                           "TestBenchIOMapLazyOnce")
        assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"

    def test_map_run_twice_reexecutes(self):
        """L2: each Run() re-executes the effect (no memoization).

        Running the same IO twice increments the counter to 2. An impl that
        caches the value after the first Run would leave it at 1 and fail.
        """
        src = """
        package mo

        import "testing"

        func TestBenchIOMapRunTwice(t *testing.T) {
            calls := 0
            io := NewIO(func() int {
                calls++
                return 10
            }).Map(func(n int) int { return n * 2 })
            if a := io.Run(); a != 20 {
                t.Fatalf("first Run = %d, want 20", a)
            }
            if b := io.Run(); b != 20 {
                t.Fatalf("second Run = %d, want 20", b)
            }
            if calls != 2 {
                t.Fatalf("receiver ran %d times across two Run() calls, want 2", calls)
            }
        }
        """
        proc = _run_driver(".", "bench_io_map_twice_test.go", src,
                           "TestBenchIOMapRunTwice")
        assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"

    def test_flatmap_composes_value(self):
        """L2: FlatMap runs the receiver, feeds its value to mapper, runs result.

        2 -> mapper builds NewIO(n+40) -> 42. A stub returning the receiver's
        value or ignoring the inner IO fails.
        """
        src = """
        package mo

        import "testing"

        func TestBenchIOFlatMapValue(t *testing.T) {
            got := NewIO(func() int { return 2 }).
                FlatMap(func(n int) IO[int] {
                    return NewIO(func() int { return n + 40 })
                }).
                Run()
            if got != 42 {
                t.Fatalf("FlatMap result = %d, want 42", got)
            }
        }
        """
        proc = _run_driver(".", "bench_io_flatmap_value_test.go", src,
                           "TestBenchIOFlatMapValue")
        assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"

    def test_flatmap_is_lazy_and_runs_each_stage_once(self):
        """L2: FlatMap is lazy; on Run() receiver, mapper and inner IO each fire once.

        Three separate counters track the receiver effect, the mapper call, and
        the inner IO's effect. All are 0 after construction (laziness) and each
        is exactly 1 after a single Run(). An eager impl, or one that runs the
        inner IO twice / never, fails.
        """
        src = """
        package mo

        import "testing"

        func TestBenchIOFlatMapLazyOnce(t *testing.T) {
            recvCalls := 0
            mapperCalls := 0
            innerCalls := 0
            io := NewIO(func() int {
                recvCalls++
                return 4
            }).FlatMap(func(n int) IO[int] {
                mapperCalls++
                return NewIO(func() int {
                    innerCalls++
                    return n * 3
                })
            })
            if recvCalls != 0 || mapperCalls != 0 || innerCalls != 0 {
                t.Fatalf("construction not lazy: recv=%d mapper=%d inner=%d",
                    recvCalls, mapperCalls, innerCalls)
            }
            got := io.Run()
            if got != 12 {
                t.Fatalf("Run result = %d, want 12", got)
            }
            if recvCalls != 1 {
                t.Fatalf("receiver ran %d times, want 1", recvCalls)
            }
            if mapperCalls != 1 {
                t.Fatalf("mapper called %d times, want 1", mapperCalls)
            }
            if innerCalls != 1 {
                t.Fatalf("inner IO ran %d times, want 1", innerCalls)
            }
        }
        """
        proc = _run_driver(".", "bench_io_flatmap_lazy_test.go", src,
                           "TestBenchIOFlatMapLazyOnce")
        assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"

    def test_toresult_ok_path(self):
        """L2: ToResult on a normal computation yields Ok(value).

        NewIO(()->7).ToResult() -> Ok(7): IsOk true, IsError false, Get returns
        (7, nil). A stub returning a fixed/zero value or always-error fails.
        """
        src = """
        package mo

        import "testing"

        func TestBenchIOToResultOk(t *testing.T) {
            res := NewIO(func() int { return 7 }).ToResult()
            if !res.IsOk() {
                t.Fatalf("expected Ok, got error %v", res.Error())
            }
            if res.IsError() {
                t.Fatalf("IsError must be false on Ok path")
            }
            v, err := res.Get()
            if err != nil {
                t.Fatalf("Get err = %v, want nil", err)
            }
            if v != 7 {
                t.Fatalf("Get value = %d, want 7", v)
            }
        }
        """
        proc = _run_driver(".", "bench_io_toresult_ok_test.go", src,
                           "TestBenchIOToResultOk")
        assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"

    def test_toresult_captures_error_panic(self):
        """L2: a panic with an error value is captured into an error Result.

        The captured error must be (or wrap) the original errBoom, not a fresh
        unrelated error. A stub that lets the panic propagate fails (the test
        would crash); one that returns Ok or a generic error fails the asserts.
        """
        src = """
        package mo

        import (
            "errors"
            "testing"
        )

        func TestBenchIOToResultPanicError(t *testing.T) {
            errBoom := errors.New("boom-sentinel")
            res := NewIO(func() int { panic(errBoom) }).ToResult()
            if res.IsOk() {
                t.Fatalf("expected error Result after panic, got Ok")
            }
            if !res.IsError() {
                t.Fatalf("IsError must be true after panic")
            }
            got := res.Error()
            if got == nil {
                t.Fatalf("captured error must be non-nil")
            }
            if !errors.Is(got, errBoom) && got.Error() != errBoom.Error() {
                t.Fatalf("captured error = %v, want it to carry %v", got, errBoom)
            }
        }
        """
        proc = _run_driver(".", "bench_io_toresult_panic_err_test.go", src,
                           "TestBenchIOToResultPanicError")
        assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"

    def test_toresult_wraps_nonerror_panic(self):
        """L2: a panic with a non-error value is wrapped into an error Result.

        panic("string-boom") -> error Result whose error message mentions the
        panic payload. A stub that only handles error panics, or swallows the
        value, fails.
        """
        src = """
        package mo

        import (
            "strings"
            "testing"
        )

        func TestBenchIOToResultPanicNonError(t *testing.T) {
            res := NewIO(func() int { panic("string-boom") }).ToResult()
            if res.IsOk() {
                t.Fatalf("expected error Result after non-error panic, got Ok")
            }
            got := res.Error()
            if got == nil {
                t.Fatalf("captured error must be non-nil")
            }
            if !strings.Contains(got.Error(), "string-boom") {
                t.Fatalf("wrapped error must mention the panic value, got %q",
                    got.Error())
            }
        }
        """
        proc = _run_driver(".", "bench_io_toresult_panic_nonerr_test.go", src,
                           "TestBenchIOToResultPanicNonError")
        assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"

    def test_toresult_runs_effect_exactly_once(self):
        """L2: ToResult runs the wrapped computation exactly once on the Ok path.

        A counter incremented inside the wrapped func must be 1 after one
        ToResult() call -- not 0 (would mean a hardcoded Ok) and not 2 (double
        execution).
        """
        src = """
        package mo

        import "testing"

        func TestBenchIOToResultOnce(t *testing.T) {
            calls := 0
            res := NewIO(func() int {
                calls++
                return 99
            }).ToResult()
            if !res.IsOk() {
                t.Fatalf("expected Ok, got %v", res.Error())
            }
            if v := res.MustGet(); v != 99 {
                t.Fatalf("value = %d, want 99", v)
            }
            if calls != 1 {
                t.Fatalf("wrapped computation ran %d times, want exactly 1", calls)
            }
        }
        """
        proc = _run_driver(".", "bench_io_toresult_once_test.go", src,
                           "TestBenchIOToResultOnce")
        assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"

    def test_map_then_toresult_integration(self):
        """L2: Map and ToResult compose; the whole pipeline is lazy until used.

        Build NewIO(10).Map(*2).Map(+1) and convert with ToResult only after
        construction. Effects fire exactly once and the Ok value is 21. A stub
        that breaks laziness or mis-orders the maps fails.
        """
        src = """
        package mo

        import "testing"

        func TestBenchIOMapToResult(t *testing.T) {
            recv := 0
            io := NewIO(func() int {
                recv++
                return 10
            }).Map(func(n int) int { return n * 2 }).
                Map(func(n int) int { return n + 1 })
            if recv != 0 {
                t.Fatalf("pipeline not lazy: recv=%d before use", recv)
            }
            res := io.ToResult()
            if !res.IsOk() {
                t.Fatalf("expected Ok, got %v", res.Error())
            }
            if v, _ := res.Get(); v != 21 {
                t.Fatalf("pipeline value = %d, want 21", v)
            }
            if recv != 1 {
                t.Fatalf("receiver ran %d times, want exactly 1", recv)
            }
        }
        """
        proc = _run_driver(".", "bench_io_map_toresult_test.go", src,
                           "TestBenchIOMapToResult")
        assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"
