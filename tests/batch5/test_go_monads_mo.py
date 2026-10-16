"""Tests for skill `go-monads-mo` (variant ext5).

Verifies the task "Add a Fold Combinator to the either Sub-Package" of
`github.com/samber/mo`.

The task requires ONE new package-level generic function in
`either/transforms.go`:

  either.Fold[L, R, T any](onLeft func(L) T, onRight func(R) T) func(mo.Either[L, R]) T

Semantics under test:
  - left input  -> invokes onLeft with the left value, returns its result (type T)
  - right input -> invokes onRight with the right value, returns its result
  - exactly one handler runs per call; the non-matching handler is NEVER invoked
  - the result is an ordinary value of a fresh output type T (NOT another Either),
    so it can terminate a Pipe chain by extracting a final value
  - the return value is propagated unchanged

Strategy: L1 cases confirm the deliverable file exists, the module builds, the
`Fold` symbol is a real package-level function (via `go doc`, not text
grepping), and the existing either suite still passes. L2 cases inject
*independent* Go driver test files (written by THIS test, not the agent) into
the either/ package directory and run them with `go test`, asserting on the
real runtime behavior. A stub that returns a fixed value, ignores an input,
calls the wrong handler, or wraps the result back into an Either will fail.
"""

import os
import subprocess
import textwrap

import pytest

REPO_DIR = "/workspace/mo"

GO_TIMEOUT = 600


def _run(args, cwd, timeout=GO_TIMEOUT, env_extra=None):
    env = dict(os.environ)
    # Ensure go has a writable cache/home even with a cleared environment.
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

    def test_either_transforms_file_exists(self):
        """L1: either/transforms.go (the deliverable to modify) exists."""
        assert os.path.isfile(
            os.path.join(REPO_DIR, "either", "transforms.go")
        )

    def test_either_transforms_test_file_exists(self):
        """L1: either/transforms_test.go (the deliverable to modify) exists."""
        assert os.path.isfile(
            os.path.join(REPO_DIR, "either", "transforms_test.go")
        )

    def test_fold_symbol_declared_via_go_doc(self):
        """L1: either.Fold is a declared package-level function.

        Uses `go doc` (the toolchain's own symbol resolver) rather than text
        grepping, so only a genuinely exported function declaration counts.
        """
        proc = _run(["go", "doc", "./either", "Fold"], cwd=REPO_DIR)
        assert proc.returncode == 0, (
            f"go doc ./either Fold failed: {proc.stdout}\n{proc.stderr}"
        )
        # go doc prints the func signature for a real function decl.
        assert "func Fold" in proc.stdout, (
            f"either.Fold is not a package-level function: {proc.stdout}"
        )

    def test_module_builds(self):
        """L1: the whole module compiles with the new code (go build ./...)."""
        proc = _run(["go", "build", "./..."], cwd=REPO_DIR)
        assert proc.returncode == 0, (
            f"go build ./... failed:\n{proc.stdout}\n{proc.stderr}"
        )

    def test_existing_either_suite_still_passes(self):
        """L1->L2: the existing either suite is not broken by the change.

        This is the variant's native acceptance command: `go test ./either/...`.
        """
        proc = _run(["go", "test", "-count=1", "./either/..."], cwd=REPO_DIR)
        assert proc.returncode == 0, (
            f"go test ./either/... failed:\n{proc.stdout}\n{proc.stderr}"
        )

    # ------------------------------------------------------------------ L2 ---

    def test_fold_left_returns_onleft_result(self):
        """L2: a Left input invokes onLeft and returns its result ("L")."""
        src = """
        package either

        import (
            "testing"

            "github.com/samber/mo"
        )

        func TestBenchFoldLeftResult(t *testing.T) {
            f := Fold(
                func(int) string { return "L" },
                func(bool) string { return "R" },
            )
            got := f(mo.Left[int, bool](3))
            if got != "L" {
                t.Fatalf("Fold on Left = %q, want %q", got, "L")
            }
        }
        """
        proc = _run_driver(
            "either", "bench_fold_left_test.go", src,
            "TestBenchFoldLeftResult",
        )
        assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"

    def test_fold_right_returns_onright_result(self):
        """L2: a Right input invokes onRight and returns its result ("R")."""
        src = """
        package either

        import (
            "testing"

            "github.com/samber/mo"
        )

        func TestBenchFoldRightResult(t *testing.T) {
            f := Fold(
                func(int) string { return "L" },
                func(bool) string { return "R" },
            )
            got := f(mo.Right[int, bool](true))
            if got != "R" {
                t.Fatalf("Fold on Right = %q, want %q", got, "R")
            }
        }
        """
        proc = _run_driver(
            "either", "bench_fold_right_test.go", src,
            "TestBenchFoldRightResult",
        )
        assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"

    def test_fold_propagates_value_unchanged(self):
        """L2: the handler's return value is propagated unchanged (Right(42)->42).

        Uses an identity-ish onRight so a stub that hardcodes an output would
        fail; the result must depend on the actual right value.
        """
        src = """
        package either

        import (
            "testing"

            "github.com/samber/mo"
        )

        func TestBenchFoldPropagateRight(t *testing.T) {
            f := Fold(
                func(error) int { return -1 },
                func(n int) int { return n },
            )
            if got := f(mo.Right[error, int](42)); got != 42 {
                t.Fatalf("Fold on Right(42) = %d, want 42", got)
            }
            // A different value must flow through unchanged too.
            if got := f(mo.Right[error, int](7)); got != 7 {
                t.Fatalf("Fold on Right(7) = %d, want 7", got)
            }
            // Left path takes the other branch.
            if got := f(mo.Left[error, int](nil)); got != -1 {
                t.Fatalf("Fold on Left = %d, want -1", got)
            }
        }
        """
        proc = _run_driver(
            "either", "bench_fold_propagate_test.go", src,
            "TestBenchFoldPropagateRight",
        )
        assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"

    def test_fold_left_does_not_call_right_handler(self):
        """L2: for a Left input the right handler is NEVER invoked (counter)."""
        src = """
        package either

        import (
            "testing"

            "github.com/samber/mo"
        )

        func TestBenchFoldLeftNoRightCall(t *testing.T) {
            leftCalls := 0
            rightCalls := 0
            f := Fold(
                func(x int) string { leftCalls++; return "left" },
                func(b bool) string { rightCalls++; return "right" },
            )
            got := f(mo.Left[int, bool](99))
            if rightCalls != 0 {
                t.Fatalf("right handler called %d times on Left input; must be 0", rightCalls)
            }
            if leftCalls != 1 {
                t.Fatalf("left handler called %d times; want exactly 1", leftCalls)
            }
            if got != "left" {
                t.Fatalf("got %q want %q", got, "left")
            }
        }
        """
        proc = _run_driver(
            "either", "bench_fold_left_nocall_test.go", src,
            "TestBenchFoldLeftNoRightCall",
        )
        assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"

    def test_fold_right_does_not_call_left_handler(self):
        """L2: for a Right input the left handler is NEVER invoked (counter)."""
        src = """
        package either

        import (
            "testing"

            "github.com/samber/mo"
        )

        func TestBenchFoldRightNoLeftCall(t *testing.T) {
            leftCalls := 0
            rightCalls := 0
            f := Fold(
                func(x int) string { leftCalls++; return "left" },
                func(b bool) string { rightCalls++; return "right" },
            )
            got := f(mo.Right[int, bool](true))
            if leftCalls != 0 {
                t.Fatalf("left handler called %d times on Right input; must be 0", leftCalls)
            }
            if rightCalls != 1 {
                t.Fatalf("right handler called %d times; want exactly 1", rightCalls)
            }
            if got != "right" {
                t.Fatalf("got %q want %q", got, "right")
            }
        }
        """
        proc = _run_driver(
            "either", "bench_fold_right_nocall_test.go", src,
            "TestBenchFoldRightNoLeftCall",
        )
        assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"

    def test_fold_distinct_output_type(self):
        """L2: T is a fresh output type distinct from L and R.

        Folds an Either[string, int] down to a bool, proving Fold introduces a
        third type parameter rather than reusing L or R. A naive impl reusing
        L/R for the output would not compile here.
        """
        src = """
        package either

        import (
            "testing"

            "github.com/samber/mo"
        )

        func TestBenchFoldDistinctType(t *testing.T) {
            // Output type bool is neither string (L) nor int (R).
            f := Fold(
                func(s string) bool { return len(s) > 0 },
                func(n int) bool { return n > 0 },
            )
            if got := f(mo.Left[string, int]("hello")); got != true {
                t.Fatalf("Fold(Left(\\"hello\\")) = %v, want true", got)
            }
            if got := f(mo.Left[string, int]("")); got != false {
                t.Fatalf("Fold(Left(\\"\\")) = %v, want false", got)
            }
            if got := f(mo.Right[string, int](5)); got != true {
                t.Fatalf("Fold(Right(5)) = %v, want true", got)
            }
            if got := f(mo.Right[string, int](-1)); got != false {
                t.Fatalf("Fold(Right(-1)) = %v, want false", got)
            }
        }
        """
        proc = _run_driver(
            "either", "bench_fold_distinct_type_test.go", src,
            "TestBenchFoldDistinctType",
        )
        assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"

    def test_fold_result_is_not_either(self):
        """L2: Fold returns an ordinary value, NOT another mo.Either.

        Assigns the result to a plain int variable. If the agent's Fold instead
        returned mo.Either[...]/some wrapper, this driver would fail to compile,
        which surfaces as a non-zero return code.
        """
        src = """
        package either

        import (
            "testing"

            "github.com/samber/mo"
        )

        func TestBenchFoldPlainValue(t *testing.T) {
            f := Fold(
                func(s string) int { return -len(s) },
                func(n int) int { return n * 10 },
            )
            // Must assign directly to a plain int (no .Get()/.MustRight()).
            var v int = f(mo.Right[string, int](4))
            if v != 40 {
                t.Fatalf("plain value = %d, want 40", v)
            }
            var w int = f(mo.Left[string, int]("abc"))
            if w != -3 {
                t.Fatalf("plain value = %d, want -3", w)
            }
        }
        """
        proc = _run_driver(
            "either", "bench_fold_plain_value_test.go", src,
            "TestBenchFoldPlainValue",
        )
        assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"

    def test_fold_terminates_pipe_chain(self):
        """L2: Fold can terminate a transform chain by extracting a final value.

        Combines Swap (existing either transform) with Fold over the swapped
        Either, confirming Fold composes with the package's point-free API and
        yields a single value of type T.
        """
        src = """
        package either

        import (
            "testing"

            "github.com/samber/mo"
        )

        func TestBenchFoldComposes(t *testing.T) {
            // Swap turns Either[int, string] into Either[string, int].
            swap := Swap[int, string]()
            fold := Fold(
                func(s string) string { return "L:" + s },
                func(n int) string { return "R" },
            )

            // Original Right(string "hi") -> after Swap becomes Left(string "hi").
            in := mo.Right[int, string]("hi")
            got := fold(swap(in))
            if got != "L:hi" {
                t.Fatalf("composed Fold = %q, want %q", got, "L:hi")
            }

            // Original Left(int 5) -> after Swap becomes Right(int 5).
            in2 := mo.Left[int, string](5)
            got2 := fold(swap(in2))
            if got2 != "R" {
                t.Fatalf("composed Fold = %q, want %q", got2, "R")
            }
        }
        """
        proc = _run_driver(
            "either", "bench_fold_composes_test.go", src,
            "TestBenchFoldComposes",
        )
        assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"

    def test_fold_struct_output_type(self):
        """L2: Fold works when T is a struct; both branches reach the same T.

        Guards against a stub that special-cases primitive return types or
        ignores one branch's argument.
        """
        src = """
        package either

        import (
            "testing"

            "github.com/samber/mo"
        )

        type tag struct {
            side string
            n    int
        }

        func TestBenchFoldStruct(t *testing.T) {
            f := Fold(
                func(e error) tag { return tag{side: "left", n: -1} },
                func(n int) tag { return tag{side: "right", n: n} },
            )
            got := f(mo.Right[error, int](21))
            if got.side != "right" || got.n != 21 {
                t.Fatalf("Right -> %+v, want {right 21}", got)
            }
            got2 := f(mo.Left[error, int](nil))
            if got2.side != "left" || got2.n != -1 {
                t.Fatalf("Left -> %+v, want {left -1}", got2)
            }
        }
        """
        proc = _run_driver(
            "either", "bench_fold_struct_test.go", src,
            "TestBenchFoldStruct",
        )
        assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"
