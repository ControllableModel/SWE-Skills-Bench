"""Tests for skill `go-monads-mo` (variant ext9).

Verifies the task "Add First-Success Aggregation Helpers for Option and Result
Slices" of `github.com/samber/mo`.

The task requires two NEW package-level generic functions in the *root* `mo`
package, declared in a new file `aggregate.go`:

  - mo.FirstSome[T any](options []mo.Option[T]) mo.Option[T]
  - mo.FirstOk[T any](results []mo.Result[T]) mo.Result[T]

Semantics under test (re-derived from the ext9 requirement doc):

  FirstSome:
    - returns the FIRST present option encountered, value preserved
    - scanning short-circuits at the first present element
    - all-absent input  -> None
    - empty input       -> None

  FirstOk:
    - returns the FIRST Ok result encountered, value preserved
    - scanning short-circuits at the first Ok element
    - all-error input   -> error Result carrying the LAST element's error
    - empty input       -> error Result with a non-nil sentinel error

Strategy: L1 cases confirm the deliverable file exists, that the two symbols
are real package-level functions (resolved via `go doc`, not text grep), and
that the module compiles. L2 cases inject *independent* Go driver test files
(written by THIS test, not the agent) into the repo root `mo` package and run
them with `go test -run`, asserting concrete runtime values, ordering,
short-circuit behavior, and the last-error / sentinel-error contract. A stub
that hardcodes a value, ignores the input, returns the wrong (e.g. first)
error, or fails to short-circuit will fail these assertions.
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
            cwd=os.path.join(REPO_DIR, rel_dir) if rel_dir else REPO_DIR,
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

    def test_aggregate_file_exists(self):
        """L1: aggregate.go (the new deliverable) exists in the repo root."""
        assert os.path.isfile(os.path.join(REPO_DIR, "aggregate.go")), (
            "expected new file aggregate.go in the mo package root"
        )

    def test_aggregate_in_mo_package(self):
        """L1: aggregate.go declares `package mo` (top-level, not a subpkg)."""
        path = os.path.join(REPO_DIR, "aggregate.go")
        assert os.path.isfile(path)
        with open(path) as fh:
            head = fh.read()
        # First non-comment package clause must be `package mo`.
        assert "package mo" in head, (
            f"aggregate.go must be in package mo, head was:\n{head[:200]}"
        )

    def test_symbols_declared_via_go_doc(self):
        """L1: FirstSome/FirstOk are exported funcs of package mo.

        Uses `go doc` (the toolchain's own symbol resolver) rather than text
        grepping, so only genuinely exported declarations count.
        """
        for sym in ("FirstSome", "FirstOk"):
            proc = _run(["go", "doc", ".", sym], cwd=REPO_DIR)
            assert proc.returncode == 0, (
                f"go doc . {sym} failed: {proc.stdout}\n{proc.stderr}"
            )
            assert "func " in proc.stdout, (
                f"mo.{sym} is not a function: {proc.stdout}"
            )

    def test_module_builds(self):
        """L1: the whole module compiles with the new code (go build ./...)."""
        proc = _run(["go", "build", "./..."], cwd=REPO_DIR)
        assert proc.returncode == 0, (
            f"go build ./... failed:\n{proc.stdout}\n{proc.stderr}"
        )

    def test_native_first_suite_passes(self):
        """L1->L2: the native acceptance command `go test ./... -run First`.

        Drives exactly the command from the doc's Acceptance Criteria. This
        runs the agent's own First* tests plus any other First-matching tests
        in the module and must pass.
        """
        proc = _run(["go", "test", "./...", "-run", "First", "-count=1"], cwd=REPO_DIR)
        assert proc.returncode == 0, (
            f"go test ./... -run First failed:\n{proc.stdout}\n{proc.stderr}"
        )

    # ------------------------------------------------------------------ L2 ---

    def test_first_some_returns_first_present(self):
        """L2: FirstSome returns the first present option, value preserved."""
        src = """
        package mo

        import "testing"

        func TestBenchFirstSomeFirstPresent(t *testing.T) {
            in := []Option[int]{None[int](), None[int](), Some(3), Some(4)}
            out := FirstSome(in)
            v, ok := out.Get()
            if !ok {
                t.Fatalf("expected present, got None")
            }
            if v != 3 {
                t.Fatalf("expected first present value 3, got %d", v)
            }
        }
        """
        proc = _run_driver(
            "", "bench_firstsome_present_test.go", src,
            "TestBenchFirstSomeFirstPresent",
        )
        assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"

    def test_first_some_short_circuits(self):
        """L2: FirstSome stops at the first present element (no later inspect).

        A naive impl that scans to the end (e.g. returns the LAST present, or
        re-evaluates) would pick Some(9) instead of Some(3) here.
        """
        src = """
        package mo

        import "testing"

        func TestBenchFirstSomeShortCircuit(t *testing.T) {
            in := []Option[int]{None[int](), Some(3), Some(9)}
            out := FirstSome(in)
            v, ok := out.Get()
            if !ok {
                t.Fatalf("expected present, got None")
            }
            if v != 3 {
                t.Fatalf("short-circuit failed: expected 3 (first present), got %d", v)
            }
        }
        """
        proc = _run_driver(
            "", "bench_firstsome_shortcircuit_test.go", src,
            "TestBenchFirstSomeShortCircuit",
        )
        assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"

    def test_first_some_all_absent_is_none(self):
        """L2: all-absent input -> None."""
        src = """
        package mo

        import "testing"

        func TestBenchFirstSomeAllAbsent(t *testing.T) {
            in := []Option[int]{None[int](), None[int]()}
            out := FirstSome(in)
            if out.IsPresent() {
                v, _ := out.Get()
                t.Fatalf("expected None, got present %d", v)
            }
        }
        """
        proc = _run_driver(
            "", "bench_firstsome_allabsent_test.go", src,
            "TestBenchFirstSomeAllAbsent",
        )
        assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"

    def test_first_some_empty_is_none(self):
        """L2: empty input -> None (must not panic / return Some(zero))."""
        src = """
        package mo

        import "testing"

        func TestBenchFirstSomeEmpty(t *testing.T) {
            out := FirstSome([]Option[int]{})
            if out.IsPresent() {
                v, _ := out.Get()
                t.Fatalf("empty input must be None, got present %d", v)
            }
        }
        """
        proc = _run_driver(
            "", "bench_firstsome_empty_test.go", src,
            "TestBenchFirstSomeEmpty",
        )
        assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"

    def test_first_some_value_preserved_string(self):
        """L2: FirstSome works for a non-int type and preserves the value."""
        src = """
        package mo

        import "testing"

        func TestBenchFirstSomeString(t *testing.T) {
            in := []Option[string]{None[string](), Some("hello"), Some("world")}
            out := FirstSome(in)
            v, ok := out.Get()
            if !ok {
                t.Fatalf("expected present")
            }
            if v != "hello" {
                t.Fatalf("expected first present \\"hello\\", got %q", v)
            }
        }
        """
        proc = _run_driver(
            "", "bench_firstsome_string_test.go", src,
            "TestBenchFirstSomeString",
        )
        assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"

    def test_first_ok_returns_first_ok(self):
        """L2: FirstOk returns the first Ok result, value preserved."""
        src = """
        package mo

        import (
            "errors"
            "testing"
        )

        func TestBenchFirstOkFirst(t *testing.T) {
            e1 := errors.New("e1")
            in := []Result[int]{Err[int](e1), Ok(2), Ok(3)}
            out := FirstOk(in)
            if !out.IsOk() {
                t.Fatalf("expected Ok, got error %v", out.Error())
            }
            v, err := out.Get()
            if err != nil {
                t.Fatalf("expected nil error, got %v", err)
            }
            if v != 2 {
                t.Fatalf("expected first Ok value 2, got %d", v)
            }
        }
        """
        proc = _run_driver(
            "", "bench_firstok_first_test.go", src,
            "TestBenchFirstOkFirst",
        )
        assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"

    def test_first_ok_short_circuits(self):
        """L2: FirstOk stops at the first Ok (does not pick a later Ok)."""
        src = """
        package mo

        import "testing"

        func TestBenchFirstOkShortCircuit(t *testing.T) {
            in := []Result[int]{Ok(7), Ok(8)}
            out := FirstOk(in)
            if !out.IsOk() {
                t.Fatalf("expected Ok")
            }
            v, _ := out.Get()
            if v != 7 {
                t.Fatalf("short-circuit failed: expected 7 (first Ok), got %d", v)
            }
        }
        """
        proc = _run_driver(
            "", "bench_firstok_shortcircuit_test.go", src,
            "TestBenchFirstOkShortCircuit",
        )
        assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"

    def test_first_ok_all_error_carries_last(self):
        """L2: all-error input -> error Result carrying the LAST element's error.

        A naive impl that returns the FIRST error (or a generic sentinel here)
        would carry e1 / a sentinel instead of e2 and fail.
        """
        src = """
        package mo

        import (
            "errors"
            "testing"
        )

        func TestBenchFirstOkLastError(t *testing.T) {
            e1 := errors.New("first-error")
            e2 := errors.New("last-error")
            in := []Result[int]{Err[int](e1), Err[int](e2)}
            out := FirstOk(in)
            if out.IsOk() {
                t.Fatalf("expected error result")
            }
            got := out.Error()
            if got == nil {
                t.Fatalf("error must be non-nil")
            }
            if !errors.Is(got, e2) && got.Error() != e2.Error() {
                t.Fatalf("expected LAST error %v, got %v", e2, got)
            }
            if got.Error() == e1.Error() {
                t.Fatalf("must carry the last error, not the first (%v)", e1)
            }
        }
        """
        proc = _run_driver(
            "", "bench_firstok_lasterr_test.go", src,
            "TestBenchFirstOkLastError",
        )
        assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"

    def test_first_ok_empty_sentinel_error(self):
        """L2: empty input -> error Result with a non-nil sentinel error."""
        src = """
        package mo

        import "testing"

        func TestBenchFirstOkEmpty(t *testing.T) {
            out := FirstOk([]Result[int]{})
            if out.IsOk() {
                t.Fatalf("empty input must be an error result, got Ok")
            }
            if out.Error() == nil {
                t.Fatalf("empty input must carry a non-nil sentinel error")
            }
        }
        """
        proc = _run_driver(
            "", "bench_firstok_empty_test.go", src,
            "TestBenchFirstOkEmpty",
        )
        assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"

    def test_first_ok_mixed_ok_after_errors(self):
        """L2: leading errors then an Ok -> the Ok wins, value preserved."""
        src = """
        package mo

        import (
            "errors"
            "testing"
        )

        func TestBenchFirstOkMixed(t *testing.T) {
            in := []Result[string]{
                Err[string](errors.New("a")),
                Err[string](errors.New("b")),
                Ok("payload"),
                Ok("ignored"),
            }
            out := FirstOk(in)
            if !out.IsOk() {
                t.Fatalf("expected Ok, got error %v", out.Error())
            }
            v, _ := out.Get()
            if v != "payload" {
                t.Fatalf("expected first Ok \\"payload\\", got %q", v)
            }
        }
        """
        proc = _run_driver(
            "", "bench_firstok_mixed_test.go", src,
            "TestBenchFirstOkMixed",
        )
        assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"

    def test_existing_suite_still_passes(self):
        """L2: the existing root mo package suite is not broken by the change."""
        proc = _run(["go", "test", "-count=1", "."], cwd=REPO_DIR)
        assert proc.returncode == 0, (
            f"go test . failed after the change:\n{proc.stdout}\n{proc.stderr}"
        )
