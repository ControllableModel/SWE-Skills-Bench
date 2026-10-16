"""Tests for skill `go-monads-mo`.

Verifies the task "Add Sequence and Traverse Combinators to the option and
result Sub-Packages" of `github.com/samber/mo`.

The task requires four package-level generic functions:
  - option.Sequence([]mo.Option[T])           -> mo.Option[[]T]
  - option.Traverse([]I, func(I) mo.Option[O]) -> mo.Option[[]O]
  - result.Sequence([]mo.Result[T])           -> mo.Result[[]T]
  - result.Traverse([]I, func(I) mo.Result[O]) -> mo.Result[[]O]

Semantics under test:
  - all-present / all-Ok  -> collected slice preserves input order
  - any absent            -> None (no later element "rescues" it)
  - any error             -> first failing element's error (first-error-wins)
  - empty input           -> present / Ok wrapping a non-nil empty slice

Strategy: L1 cases check the deliverable source compiles and the symbols are
declared. L2 cases inject *independent* Go driver test files into the option/
and result/ package directories and run them with `go test`, asserting on the
real runtime behavior of the agent's implementation. The drivers are written
by THIS test (not by the agent), so a stub or keyword-only solution fails.
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

    def test_option_transforms_file_exists(self):
        """L1: option/transforms.go (the deliverable to modify) exists."""
        assert os.path.isfile(os.path.join(REPO_DIR, "option", "transforms.go"))

    def test_result_transforms_file_exists(self):
        """L1: result/transforms.go (the deliverable to modify) exists."""
        assert os.path.isfile(os.path.join(REPO_DIR, "result", "transforms.go"))

    def test_symbols_declared_via_go_doc(self):
        """L1: Sequence/Traverse are declared package-level funcs in both subpkgs.

        Uses `go doc` (the toolchain's own symbol resolver) rather than text
        grepping, so only genuinely exported declarations count.
        """
        for pkg in ("option", "result"):
            for sym in ("Sequence", "Traverse"):
                proc = _run(["go", "doc", f"./{pkg}", sym], cwd=REPO_DIR)
                assert proc.returncode == 0, (
                    f"go doc ./{pkg} {sym} failed: {proc.stdout}\n{proc.stderr}"
                )
                # go doc prints the func signature for a real function decl.
                assert "func " in proc.stdout, (
                    f"{pkg}.{sym} is not a function: {proc.stdout}"
                )

    def test_module_builds(self):
        """L1: the whole module compiles with the new code (go build ./...)."""
        proc = _run(["go", "build", "./..."], cwd=REPO_DIR)
        assert proc.returncode == 0, (
            f"go build ./... failed:\n{proc.stdout}\n{proc.stderr}"
        )

    def test_existing_suites_still_pass(self):
        """L1->L2: existing option/result suites are not broken by the change."""
        proc = _run(
            ["go", "test", "-count=1", "./option/...", "./result/..."], cwd=REPO_DIR
        )
        assert proc.returncode == 0, (
            f"go test ./option/... ./result/... failed:\n{proc.stdout}\n{proc.stderr}"
        )

    # ------------------------------------------------------------------ L2 ---

    def test_option_sequence_all_present_order(self):
        """L2: option.Sequence over all-Some preserves order and is present."""
        src = """
        package option

        import (
            "testing"

            "github.com/samber/mo"
        )

        func TestBenchOptionSequenceAllPresent(t *testing.T) {
            in := []mo.Option[int]{mo.Some(1), mo.Some(2), mo.Some(3)}
            out := Sequence(in)
            vals, ok := out.Get()
            if !ok {
                t.Fatalf("expected present, got None")
            }
            want := []int{1, 2, 3}
            if len(vals) != len(want) {
                t.Fatalf("len = %d, want %d (%v)", len(vals), len(want), vals)
            }
            for i := range want {
                if vals[i] != want[i] {
                    t.Fatalf("order mismatch at %d: got %v want %v", i, vals, want)
                }
            }
        }
        """
        proc = _run_driver(
            "option", "bench_seq_present_test.go", src,
            "TestBenchOptionSequenceAllPresent",
        )
        assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"

    def test_option_sequence_absent_no_rescue(self):
        """L2: a single None makes it None; a later Some must not rescue it."""
        src = """
        package option

        import (
            "testing"

            "github.com/samber/mo"
        )

        func TestBenchOptionSequenceAbsent(t *testing.T) {
            in := []mo.Option[int]{mo.Some(1), mo.None[int](), mo.Some(3)}
            out := Sequence(in)
            if out.IsPresent() {
                v, _ := out.Get()
                t.Fatalf("expected None, got present %v", v)
            }
        }
        """
        proc = _run_driver(
            "option", "bench_seq_absent_test.go", src,
            "TestBenchOptionSequenceAbsent",
        )
        assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"

    def test_option_sequence_empty_present_nonnil(self):
        """L2: empty input -> present, length-0, non-nil slice."""
        src = """
        package option

        import (
            "testing"

            "github.com/samber/mo"
        )

        func TestBenchOptionSequenceEmpty(t *testing.T) {
            out := Sequence([]mo.Option[int]{})
            vals, ok := out.Get()
            if !ok {
                t.Fatalf("empty input must be present")
            }
            if len(vals) != 0 {
                t.Fatalf("len = %d, want 0", len(vals))
            }
            if vals == nil {
                t.Fatalf("empty result slice must be non-nil")
            }
        }
        """
        proc = _run_driver(
            "option", "bench_seq_empty_test.go", src,
            "TestBenchOptionSequenceEmpty",
        )
        assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"

    def test_option_traverse_doubles(self):
        """L2: option.Traverse applies f in order -> Some([]{2,4,6})."""
        src = """
        package option

        import (
            "testing"

            "github.com/samber/mo"
        )

        func TestBenchOptionTraverseDouble(t *testing.T) {
            out := Traverse([]int{1, 2, 3}, func(x int) mo.Option[int] {
                return mo.Some(x * 2)
            })
            vals, ok := out.Get()
            if !ok {
                t.Fatalf("expected present")
            }
            want := []int{2, 4, 6}
            if len(vals) != len(want) {
                t.Fatalf("len = %d want %d (%v)", len(vals), len(want), vals)
            }
            for i := range want {
                if vals[i] != want[i] {
                    t.Fatalf("got %v want %v", vals, want)
                }
            }
        }
        """
        proc = _run_driver(
            "option", "bench_trav_double_test.go", src,
            "TestBenchOptionTraverseDouble",
        )
        assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"

    def test_option_traverse_negative_absent(self):
        """L2: option.Traverse short-circuits to None on a negative element."""
        src = """
        package option

        import (
            "testing"

            "github.com/samber/mo"
        )

        func parseNonNegative(x int) mo.Option[int] {
            if x < 0 {
                return mo.None[int]()
            }
            return mo.Some(x)
        }

        func TestBenchOptionTraverseNeg(t *testing.T) {
            out := Traverse([]int{1, -1, 2}, parseNonNegative)
            if out.IsPresent() {
                v, _ := out.Get()
                t.Fatalf("expected None, got %v", v)
            }
        }
        """
        proc = _run_driver(
            "option", "bench_trav_neg_test.go", src,
            "TestBenchOptionTraverseNeg",
        )
        assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"

    def test_option_sequence_type_change_traverse(self):
        """L2: Traverse may change element type (int -> string), order kept."""
        src = """
        package option

        import (
            "strconv"
            "testing"

            "github.com/samber/mo"
        )

        func TestBenchOptionTraverseTypeChange(t *testing.T) {
            out := Traverse([]int{10, 20, 30}, func(x int) mo.Option[string] {
                return mo.Some(strconv.Itoa(x))
            })
            vals, ok := out.Get()
            if !ok {
                t.Fatalf("expected present")
            }
            want := []string{"10", "20", "30"}
            if len(vals) != len(want) {
                t.Fatalf("len mismatch: %v", vals)
            }
            for i := range want {
                if vals[i] != want[i] {
                    t.Fatalf("got %v want %v", vals, want)
                }
            }
        }
        """
        proc = _run_driver(
            "option", "bench_trav_typechange_test.go", src,
            "TestBenchOptionTraverseTypeChange",
        )
        assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"

    def test_result_sequence_all_ok_order(self):
        """L2: result.Sequence over all-Ok is Ok and preserves order."""
        src = """
        package result

        import (
            "testing"

            "github.com/samber/mo"
        )

        func TestBenchResultSequenceOk(t *testing.T) {
            in := []mo.Result[int]{mo.Ok(5), mo.Ok(6), mo.Ok(7)}
            out := Sequence(in)
            vals, err := out.Get()
            if err != nil {
                t.Fatalf("expected Ok, got err %v", err)
            }
            want := []int{5, 6, 7}
            if len(vals) != len(want) {
                t.Fatalf("len = %d want %d (%v)", len(vals), len(want), vals)
            }
            for i := range want {
                if vals[i] != want[i] {
                    t.Fatalf("order mismatch: got %v want %v", vals, want)
                }
            }
        }
        """
        proc = _run_driver(
            "result", "bench_seq_ok_test.go", src,
            "TestBenchResultSequenceOk",
        )
        assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"

    def test_result_sequence_first_error_wins(self):
        """L2: result.Sequence surfaces the FIRST failing element's error."""
        src = """
        package result

        import (
            "errors"
            "testing"

            "github.com/samber/mo"
        )

        func TestBenchResultSequenceFirstErr(t *testing.T) {
            errA := errors.New("first-error")
            errB := errors.New("second-error")
            in := []mo.Result[int]{mo.Ok(1), mo.Err[int](errA), mo.Err[int](errB)}
            out := Sequence(in)
            if out.IsOk() {
                t.Fatalf("expected error result")
            }
            got := out.Error()
            if got == nil {
                t.Fatalf("error must be non-nil")
            }
            if !errors.Is(got, errA) && got.Error() != errA.Error() {
                t.Fatalf("expected first error %v, got %v", errA, got)
            }
            if got.Error() == errB.Error() {
                t.Fatalf("second error must not overwrite the first")
            }
        }
        """
        proc = _run_driver(
            "result", "bench_seq_firsterr_test.go", src,
            "TestBenchResultSequenceFirstErr",
        )
        assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"

    def test_result_sequence_empty_ok_nonnil(self):
        """L2: result.Sequence on empty input -> Ok with non-nil empty slice."""
        src = """
        package result

        import (
            "testing"

            "github.com/samber/mo"
        )

        func TestBenchResultSequenceEmpty(t *testing.T) {
            out := Sequence([]mo.Result[int]{})
            vals, err := out.Get()
            if err != nil {
                t.Fatalf("empty input must be Ok, got err %v", err)
            }
            if len(vals) != 0 {
                t.Fatalf("len = %d want 0", len(vals))
            }
            if vals == nil {
                t.Fatalf("empty result slice must be non-nil")
            }
        }
        """
        proc = _run_driver(
            "result", "bench_seq_empty_test.go", src,
            "TestBenchResultSequenceEmpty",
        )
        assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"

    def test_result_traverse_atoi_first_error(self):
        """L2: result.Traverse stops at first failing element ("x") and Ok path works."""
        src = """
        package result

        import (
            "strconv"
            "testing"

            "github.com/samber/mo"
        )

        func atoiResult(s string) mo.Result[int] {
            n, err := strconv.Atoi(s)
            if err != nil {
                return mo.Err[int](err)
            }
            return mo.Ok(n)
        }

        func TestBenchResultTraverseAtoiErr(t *testing.T) {
            out := Traverse([]string{"1", "x", "3"}, atoiResult)
            if out.IsOk() {
                t.Fatalf("expected error result")
            }
            e := out.Error()
            if e == nil {
                t.Fatalf("error must be non-nil")
            }
            // The error must come from parsing "x", which mentions "x".
            if !contains(e.Error(), "\\"x\\"") && !contains(e.Error(), "x") {
                t.Fatalf("error should be from the \\"x\\" element, got %v", e)
            }

            // Ok path: all parseable -> Ok preserving order.
            ok := Traverse([]string{"4", "5", "6"}, atoiResult)
            vals, err := ok.Get()
            if err != nil {
                t.Fatalf("expected Ok, got %v", err)
            }
            want := []int{4, 5, 6}
            for i := range want {
                if vals[i] != want[i] {
                    t.Fatalf("got %v want %v", vals, want)
                }
            }
        }

        func contains(s, sub string) bool {
            for i := 0; i+len(sub) <= len(s); i++ {
                if s[i:i+len(sub)] == sub {
                    return true
                }
            }
            return false
        }
        """
        proc = _run_driver(
            "result", "bench_trav_atoi_test.go", src,
            "TestBenchResultTraverseAtoiErr",
        )
        assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"

    def test_result_traverse_type_change_ok(self):
        """L2: result.Traverse can change element type and keep order on Ok path."""
        src = """
        package result

        import (
            "strconv"
            "testing"

            "github.com/samber/mo"
        )

        func TestBenchResultTraverseTypeChange(t *testing.T) {
            out := Traverse([]int{7, 8, 9}, func(x int) mo.Result[string] {
                return mo.Ok(strconv.Itoa(x))
            })
            vals, err := out.Get()
            if err != nil {
                t.Fatalf("expected Ok, got %v", err)
            }
            want := []string{"7", "8", "9"}
            if len(vals) != len(want) {
                t.Fatalf("len mismatch: %v", vals)
            }
            for i := range want {
                if vals[i] != want[i] {
                    t.Fatalf("got %v want %v", vals, want)
                }
            }
        }
        """
        proc = _run_driver(
            "result", "bench_trav_typechange_test.go", src,
            "TestBenchResultTraverseTypeChange",
        )
        assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"
