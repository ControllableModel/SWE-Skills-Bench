"""Tests for skill `go-monads-mo` (variant ext10).

Verifies the task "Add a Fold Combinator to the either3 Sub-Package" of
`github.com/samber/mo`.

The task requires ONE new package-level generic function in the `either3`
sub-package (`either3/transforms.go`):

    either3.Fold(onArg1 func(T1) R, onArg2 func(T2) R, onArg3 func(T3) R)
        -> func(mo.Either3[T1, T2, T3]) R

Semantics under test:
  - the returned function inspects which arm is populated (Arg1/Arg2/Arg3)
    and invokes exactly the matching handler, returning its result unchanged;
  - exactly one handler runs per call -- the other two are never invoked;
  - the output type `R` is a fresh type parameter distinct from T1/T2/T3,
    so Fold collapses a three-way union into an ordinary value (it does NOT
    return another Either3), letting it terminate a transform chain.

Strategy: L1 cases check the deliverable source compiles and that `Fold` is a
genuinely declared package-level function (via `go doc`, the toolchain's own
symbol resolver) returning a non-Either3 value. L2 cases inject *independent*
Go driver test files (written by THIS test, not the agent) into the either3/
package directory and run them with `go test`, asserting on the real runtime
behavior: arm selection, value propagation, the "other two handlers never
run" invariant (via counter closures), a type-changing R, and the fact that
the result is a plain value rather than an Either3. A stub that hardcodes an
arm, ignores its input, or returns another Either3 fails these drivers.
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
            ["go", "test", "-count=1", "-run", run_regex, "./..."],
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

    def test_either3_transforms_file_exists(self):
        """L1: either3/transforms.go (the deliverable to modify) exists."""
        assert os.path.isfile(
            os.path.join(REPO_DIR, "either3", "transforms.go")
        )

    def test_fold_symbol_declared_via_go_doc(self):
        """L1: Fold is a declared package-level func in the either3 sub-package.

        Uses `go doc` (the toolchain's symbol resolver) rather than text
        grepping, so only a genuinely exported function declaration counts.
        Also asserts the signature collapses to a plain value: the returned
        function's result type must NOT be another mo.Either3.
        """
        proc = _run(["go", "doc", "./either3", "Fold"], cwd=REPO_DIR)
        assert proc.returncode == 0, (
            f"go doc ./either3 Fold failed: {proc.stdout}\n{proc.stderr}"
        )
        out = proc.stdout
        assert "func " in out, f"Fold is not a function: {out}"
        # It must return a function over mo.Either3 (the input union).
        assert "mo.Either3" in out, (
            f"Fold should accept an mo.Either3 argument: {out}"
        )
        # The final return type must be a plain R, not another Either3.
        # The signature has exactly one Either3 occurrence (the parameter of
        # the returned closure); a Match-style combinator would have two.
        assert out.count("Either3") == 1, (
            "Fold must collapse to an ordinary value of type R, not return "
            f"another Either3: {out}"
        )

    def test_module_builds(self):
        """L1: the whole module compiles with the new Fold code (go build ./...)."""
        proc = _run(["go", "build", "./..."], cwd=REPO_DIR)
        assert proc.returncode == 0, (
            f"go build ./... failed:\n{proc.stdout}\n{proc.stderr}"
        )

    def test_existing_either3_suite_still_passes(self):
        """L1->L2: the existing either3 suite is not broken by the change."""
        proc = _run(
            ["go", "test", "-count=1", "./either3/..."], cwd=REPO_DIR
        )
        assert proc.returncode == 0, (
            f"go test ./either3/... failed:\n{proc.stdout}\n{proc.stderr}"
        )

    # ------------------------------------------------------------------ L2 ---

    def test_fold_selects_arg1(self):
        """L2: an Arg1 union routes through onArg1, propagating its value."""
        src = """
        package either3

        import (
            "testing"

            "github.com/samber/mo"
        )

        func TestBenchFoldArg1(t *testing.T) {
            f1 := func(x int) string { return "one" }
            f2 := func(s string) string { return "two:" + s }
            f3 := func(b bool) string { return "three" }
            got := Fold(f1, f2, f3)(mo.NewEither3Arg1[int, string, bool](7))
            if got != "one" {
                t.Fatalf("Arg1 should select onArg1, got %q", got)
            }
        }
        """
        proc = _run_driver(
            "either3", "bench_fold_arg1_test.go", src, "TestBenchFoldArg1"
        )
        assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"

    def test_fold_selects_arg2(self):
        """L2: an Arg2 union routes through onArg2 with the inner string value."""
        src = """
        package either3

        import (
            "testing"

            "github.com/samber/mo"
        )

        func TestBenchFoldArg2(t *testing.T) {
            f1 := func(x int) string { return "one" }
            f2 := func(s string) string { return "two:" + s }
            f3 := func(b bool) string { return "three" }
            got := Fold(f1, f2, f3)(mo.NewEither3Arg2[int, string, bool]("x"))
            if got != "two:x" {
                t.Fatalf("Arg2 should select onArg2 with inner value, got %q", got)
            }
        }
        """
        proc = _run_driver(
            "either3", "bench_fold_arg2_test.go", src, "TestBenchFoldArg2"
        )
        assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"

    def test_fold_selects_arg3(self):
        """L2: an Arg3 union routes through onArg3 with the inner bool value."""
        src = """
        package either3

        import (
            "testing"

            "github.com/samber/mo"
        )

        func TestBenchFoldArg3(t *testing.T) {
            f1 := func(x int) string { return "one" }
            f2 := func(s string) string { return "two:" + s }
            f3 := func(b bool) string {
                if b {
                    return "three:true"
                }
                return "three:false"
            }
            got := Fold(f1, f2, f3)(mo.NewEither3Arg3[int, string, bool](true))
            if got != "three:true" {
                t.Fatalf("Arg3 should select onArg3 with inner value, got %q", got)
            }
        }
        """
        proc = _run_driver(
            "either3", "bench_fold_arg3_test.go", src, "TestBenchFoldArg3"
        )
        assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"

    def test_fold_other_handlers_never_invoked(self):
        """L2: exactly one handler runs per call; the other two never fire.

        Counter closures detect a stub that calls every handler or routes to
        the wrong arm. Each of the three arms is exercised in turn and the
        invocation counts are asserted to be exactly (1,0,0)/(0,1,0)/(0,0,1).
        """
        src = """
        package either3

        import (
            "testing"

            "github.com/samber/mo"
        )

        func TestBenchFoldExactlyOne(t *testing.T) {
            type counts struct{ a, b, c int }

            run := func(e mo.Either3[int, string, bool]) (string, counts) {
                var cnt counts
                f1 := func(x int) string { cnt.a++; return "A" }
                f2 := func(s string) string { cnt.b++; return "B" }
                f3 := func(b bool) string { cnt.c++; return "C" }
                res := Fold(f1, f2, f3)(e)
                return res, cnt
            }

            res1, c1 := run(mo.NewEither3Arg1[int, string, bool](1))
            if res1 != "A" || c1.a != 1 || c1.b != 0 || c1.c != 0 {
                t.Fatalf("Arg1: res=%q counts=%+v want A (1,0,0)", res1, c1)
            }

            res2, c2 := run(mo.NewEither3Arg2[int, string, bool]("s"))
            if res2 != "B" || c2.a != 0 || c2.b != 1 || c2.c != 0 {
                t.Fatalf("Arg2: res=%q counts=%+v want B (0,1,0)", res2, c2)
            }

            res3, c3 := run(mo.NewEither3Arg3[int, string, bool](false))
            if res3 != "C" || c3.a != 0 || c3.b != 0 || c3.c != 1 {
                t.Fatalf("Arg3: res=%q counts=%+v want C (0,0,1)", res3, c3)
            }
        }
        """
        proc = _run_driver(
            "either3", "bench_fold_exactly_one_test.go", src,
            "TestBenchFoldExactlyOne",
        )
        assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"

    def test_fold_propagates_value_not_hardcoded(self):
        """L2: the inner value reaches the handler (rejects ignored-input stubs).

        Distinct Arg1 inputs must yield distinct handler outputs derived from
        them; a Fold that ignores the inner value or hardcodes a constant fails.
        """
        src = """
        package either3

        import (
            "strconv"
            "testing"

            "github.com/samber/mo"
        )

        func TestBenchFoldValuePropagation(t *testing.T) {
            f1 := func(x int) string { return "n=" + strconv.Itoa(x) }
            f2 := func(s string) string { return "s=" + s }
            f3 := func(b bool) string { return "b" }
            fold := Fold(f1, f2, f3)

            for _, x := range []int{0, 42, -5} {
                got := fold(mo.NewEither3Arg1[int, string, bool](x))
                want := "n=" + strconv.Itoa(x)
                if got != want {
                    t.Fatalf("inner value not propagated: got %q want %q", got, want)
                }
            }
        }
        """
        proc = _run_driver(
            "either3", "bench_fold_propagate_test.go", src,
            "TestBenchFoldValuePropagation",
        )
        assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"

    def test_fold_distinct_output_type_int(self):
        """L2: R is a fresh type param -- here int, distinct from the union types.

        Handlers all return int (a tag per arm); Fold must produce that int,
        confirming R is independent of T1/T2/T3 and not pinned to a union type.
        """
        src = """
        package either3

        import (
            "testing"

            "github.com/samber/mo"
        )

        func TestBenchFoldIntOutput(t *testing.T) {
            f1 := func(x string) int { return 1 }
            f2 := func(x float64) int { return 2 }
            f3 := func(x rune) int { return 3 }
            fold := Fold(f1, f2, f3)

            if g := fold(mo.NewEither3Arg1[string, float64, rune]("hi")); g != 1 {
                t.Fatalf("Arg1 int output = %d want 1", g)
            }
            if g := fold(mo.NewEither3Arg2[string, float64, rune](3.5)); g != 2 {
                t.Fatalf("Arg2 int output = %d want 2", g)
            }
            if g := fold(mo.NewEither3Arg3[string, float64, rune]('z')); g != 3 {
                t.Fatalf("Arg3 int output = %d want 3", g)
            }
        }
        """
        proc = _run_driver(
            "either3", "bench_fold_intout_test.go", src,
            "TestBenchFoldIntOutput",
        )
        assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"

    def test_fold_returns_plain_value_chainable(self):
        """L2: Fold yields an ordinary value usable directly (not an Either3).

        The result is consumed in plain arithmetic / comparison, which only
        type-checks if Fold returns R itself. A Match-style combinator that
        returns mo.Either3 would not compile here.
        """
        src = """
        package either3

        import (
            "testing"

            "github.com/samber/mo"
        )

        func TestBenchFoldPlainValue(t *testing.T) {
            toLen := Fold(
                func(x int) int { return x },
                func(s string) int { return len(s) },
                func(b bool) int {
                    if b {
                        return 1
                    }
                    return 0
                },
            )
            // Use the result as a plain int in arithmetic.
            total := toLen(mo.NewEither3Arg2[int, string, bool]("abcd")) + 10
            if total != 14 {
                t.Fatalf("plain-value chaining failed: got %d want 14", total)
            }
        }
        """
        proc = _run_driver(
            "either3", "bench_fold_plain_test.go", src,
            "TestBenchFoldPlainValue",
        )
        assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"

    def test_fold_returned_function_reusable(self):
        """L2: the folder closure is point-free and reusable across many unions.

        Building the folder once and applying it to a mix of arms must route
        each correctly, catching implementations that capture/leak per-call
        state or only handle the first arm seen.
        """
        src = """
        package either3

        import (
            "testing"

            "github.com/samber/mo"
        )

        func TestBenchFoldReusable(t *testing.T) {
            classify := Fold(
                func(x int) string { return "int" },
                func(s string) string { return "str" },
                func(b bool) string { return "bool" },
            )

            inputs := []mo.Either3[int, string, bool]{
                mo.NewEither3Arg3[int, string, bool](true),
                mo.NewEither3Arg1[int, string, bool](9),
                mo.NewEither3Arg2[int, string, bool]("q"),
                mo.NewEither3Arg1[int, string, bool](0),
            }
            want := []string{"bool", "int", "str", "int"}
            for i, in := range inputs {
                if got := classify(in); got != want[i] {
                    t.Fatalf("at %d: got %q want %q", i, got, want[i])
                }
            }
        }
        """
        proc = _run_driver(
            "either3", "bench_fold_reuse_test.go", src,
            "TestBenchFoldReusable",
        )
        assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"

    def test_fold_uses_public_api_via_default_zero(self):
        """L2: arm detection uses the public API, not raw zero-value inspection.

        An Arg1 holding the zero int (0) and an Arg2 holding the empty string
        must still be routed to their correct handlers -- a buggy impl that
        guesses the arm from non-zero fields would misroute these.
        """
        src = """
        package either3

        import (
            "testing"

            "github.com/samber/mo"
        )

        func TestBenchFoldZeroValues(t *testing.T) {
            fold := Fold(
                func(x int) string { return "i" },
                func(s string) string { return "s" },
                func(b bool) string { return "b" },
            )
            // Arg1 carrying the zero int.
            if g := fold(mo.NewEither3Arg1[int, string, bool](0)); g != "i" {
                t.Fatalf("Arg1(0) misrouted, got %q want i", g)
            }
            // Arg2 carrying the empty string.
            if g := fold(mo.NewEither3Arg2[int, string, bool]("")); g != "s" {
                t.Fatalf("Arg2(\\"\\") misrouted, got %q want s", g)
            }
            // Arg3 carrying false.
            if g := fold(mo.NewEither3Arg3[int, string, bool](false)); g != "b" {
                t.Fatalf("Arg3(false) misrouted, got %q want b", g)
            }
        }
        """
        proc = _run_driver(
            "either3", "bench_fold_zero_test.go", src,
            "TestBenchFoldZeroValues",
        )
        assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"
