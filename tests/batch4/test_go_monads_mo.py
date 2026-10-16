"""Tests for skill `go-monads-mo` (variant ext4).

Verifies the task "Add Error-Recovery Combinators to the result Sub-Package"
of `github.com/samber/mo`.

The task requires two NEW package-level generic functions in the `result`
sub-package (`result/transforms.go`), each keeping a single type parameter `T`
so they compose inside `result.Pipe` chains:

  - result.Recover(func(error) T)   -> func(mo.Result[T]) mo.Result[T]
  - result.MapErr(func(error) error) -> func(mo.Result[T]) mo.Result[T]

Semantics under test (re-derived from THIS variant's doc):
  - Ok input              -> passed through untouched; callback NEVER invoked
  - Recover on error      -> error replaced by Ok(recoveryFn(err))
  - MapErr on error       -> stays an error, but carrying the mapped error
  - MapErr returning nil  -> MUST still be an error (error-to-error contract)
  - callback invoked at most once, and only on the error branch (counter check)

Strategy: L1 cases confirm the deliverable compiles and the two symbols are
declared package-level functions (via `go doc`, not text grep). L2 cases inject
*independent* Go driver test files written by THIS test (not the agent) into the
result/ package directory and run them with `go test -run`, asserting on real
runtime behavior. A stub (e.g. Recover that ignores its fn, MapErr that drops
the error or turns it into Ok) fails these drivers.
"""

import os
import subprocess
import textwrap

import pytest

REPO_DIR = "/workspace/mo"

GO_TIMEOUT = 600


def _run(args, cwd, timeout=GO_TIMEOUT, env_extra=None):
    env = dict(os.environ)
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
    """Ensure the module builds / caches are warm before the behavioral tests."""
    assert os.path.isdir(REPO_DIR), f"repo not found at {REPO_DIR}"
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

    def test_result_transforms_file_exists(self):
        """L1: result/transforms.go (the deliverable to modify) exists."""
        assert os.path.isfile(os.path.join(REPO_DIR, "result", "transforms.go"))

    def test_recover_symbol_declared_via_go_doc(self):
        """L1: result.Recover is a package-level function (resolved by go doc)."""
        proc = _run(["go", "doc", "./result", "Recover"], cwd=REPO_DIR)
        assert proc.returncode == 0, (
            f"go doc ./result Recover failed:\n{proc.stdout}\n{proc.stderr}"
        )
        assert "func Recover" in proc.stdout, (
            f"result.Recover is not a function declaration: {proc.stdout}"
        )

    def test_maperr_symbol_declared_via_go_doc(self):
        """L1: result.MapErr is a package-level function (resolved by go doc)."""
        proc = _run(["go", "doc", "./result", "MapErr"], cwd=REPO_DIR)
        assert proc.returncode == 0, (
            f"go doc ./result MapErr failed:\n{proc.stdout}\n{proc.stderr}"
        )
        assert "func MapErr" in proc.stdout, (
            f"result.MapErr is not a function declaration: {proc.stdout}"
        )

    def test_module_builds(self):
        """L1: the whole module compiles with the new code (go build ./...)."""
        proc = _run(["go", "build", "./..."], cwd=REPO_DIR)
        assert proc.returncode == 0, (
            f"go build ./... failed:\n{proc.stdout}\n{proc.stderr}"
        )

    def test_existing_result_suite_still_passes(self):
        """L1->L2: the existing result suite is not broken by the change."""
        proc = _run(["go", "test", "-count=1", "./result/..."], cwd=REPO_DIR)
        assert proc.returncode == 0, (
            f"go test ./result/... failed:\n{proc.stdout}\n{proc.stderr}"
        )

    # ------------------------------------------------------------------ L2 ---

    def test_recover_ok_passes_through_callback_not_called(self):
        """L2: Recover on Ok input passes value through and never calls fn."""
        src = """
        package result

        import (
            "errors"
            "testing"

            "github.com/samber/mo"
        )

        func TestBenchRecoverOkPassthrough(t *testing.T) {
            calls := 0
            recovered := Recover(func(err error) int {
                calls++
                return -1
            })(mo.Ok(5))

            val, err := recovered.Get()
            if err != nil {
                t.Fatalf("expected Ok, got error %v", err)
            }
            if val != 5 {
                t.Fatalf("expected value 5 unchanged, got %d", val)
            }
            if calls != 0 {
                t.Fatalf("recovery fn must NOT be called on Ok input, called %d times", calls)
            }
            _ = errors.New
        }
        """
        proc = _run_driver(
            "result", "bench_recover_ok_test.go", src,
            "TestBenchRecoverOkPassthrough",
        )
        assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"

    def test_recover_error_becomes_ok_with_recovered_value(self):
        """L2: Recover on an error -> Ok holding recoveryFn(err); fn called once."""
        src = """
        package result

        import (
            "errors"
            "testing"

            "github.com/samber/mo"
        )

        func TestBenchRecoverError(t *testing.T) {
            errBoom := errors.New("boom")
            calls := 0
            recovered := Recover(func(err error) int {
                calls++
                if err != errBoom {
                    t.Fatalf("recovery fn got wrong error: %v", err)
                }
                return -1
            })(mo.Err[int](errBoom))

            if !recovered.IsOk() {
                t.Fatalf("expected Ok after recovery, got error %v", recovered.Error())
            }
            val, err := recovered.Get()
            if err != nil {
                t.Fatalf("expected nil error after recovery, got %v", err)
            }
            if val != -1 {
                t.Fatalf("expected recovered value -1, got %d", val)
            }
            if calls != 1 {
                t.Fatalf("recovery fn must be called exactly once, called %d", calls)
            }
        }
        """
        proc = _run_driver(
            "result", "bench_recover_err_test.go", src,
            "TestBenchRecoverError",
        )
        assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"

    def test_recover_uses_carried_error_not_hardcoded(self):
        """L2: Recover must use the ACTUAL carried error (derives value from it).

        A stub that ignores its input error or hardcodes a constant fails: the
        recovery fn derives its return value from the carried error message.
        """
        src = """
        package result

        import (
            "errors"
            "testing"

            "github.com/samber/mo"
        )

        func TestBenchRecoverUsesError(t *testing.T) {
            recover := Recover(func(err error) int {
                return len(err.Error())
            })

            a := recover(mo.Err[int](errors.New("ab")))     // len 2
            b := recover(mo.Err[int](errors.New("abcdef"))) // len 6

            av, aerr := a.Get()
            bv, berr := b.Get()
            if aerr != nil || berr != nil {
                t.Fatalf("expected Ok results, got %v / %v", aerr, berr)
            }
            if av != 2 {
                t.Fatalf("expected 2 (len of \\"ab\\"), got %d", av)
            }
            if bv != 6 {
                t.Fatalf("expected 6 (len of \\"abcdef\\"), got %d", bv)
            }
        }
        """
        proc = _run_driver(
            "result", "bench_recover_uses_err_test.go", src,
            "TestBenchRecoverUsesError",
        )
        assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"

    def test_maperr_ok_passes_through_mapper_not_called(self):
        """L2: MapErr on Ok input passes value through and never calls mapper."""
        src = """
        package result

        import (
            "fmt"
            "testing"

            "github.com/samber/mo"
        )

        func TestBenchMapErrOkPassthrough(t *testing.T) {
            calls := 0
            out := MapErr(func(e error) error {
                calls++
                return fmt.Errorf("wrapped: %w", e)
            })(mo.Ok(5))

            val, err := out.Get()
            if err != nil {
                t.Fatalf("expected Ok, got error %v", err)
            }
            if val != 5 {
                t.Fatalf("expected value 5 unchanged, got %d", val)
            }
            if calls != 0 {
                t.Fatalf("mapper must NOT be called on Ok input, called %d", calls)
            }
        }
        """
        proc = _run_driver(
            "result", "bench_maperr_ok_test.go", src,
            "TestBenchMapErrOkPassthrough",
        )
        assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"

    def test_maperr_error_transformed_stays_error(self):
        """L2: MapErr on error stays an error but carries the transformed error."""
        src = """
        package result

        import (
            "errors"
            "fmt"
            "strings"
            "testing"

            "github.com/samber/mo"
        )

        func TestBenchMapErrTransform(t *testing.T) {
            errBoom := errors.New("boom")
            calls := 0
            out := MapErr(func(e error) error {
                calls++
                return fmt.Errorf("wrapped: %w", e)
            })(mo.Err[int](errBoom))

            if out.IsOk() {
                t.Fatalf("MapErr on an error must remain an error, got Ok")
            }
            got := out.Error()
            if got == nil {
                t.Fatalf("error must be non-nil after MapErr")
            }
            if !strings.Contains(got.Error(), "wrapped:") {
                t.Fatalf("expected transformed error message, got %q", got.Error())
            }
            if !strings.Contains(got.Error(), "boom") {
                t.Fatalf("wrapped error should still mention original, got %q", got.Error())
            }
            if !errors.Is(got, errBoom) {
                t.Fatalf("wrapped error should wrap the original (errors.Is), got %v", got)
            }
            if calls != 1 {
                t.Fatalf("mapper must be called exactly once, called %d", calls)
            }
        }
        """
        proc = _run_driver(
            "result", "bench_maperr_transform_test.go", src,
            "TestBenchMapErrTransform",
        )
        assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"

    def test_maperr_same_instance_stays_error(self):
        """L2: MapErr returning the SAME error instance keeps it an error branch."""
        src = """
        package result

        import (
            "errors"
            "testing"

            "github.com/samber/mo"
        )

        func TestBenchMapErrSameInstance(t *testing.T) {
            errBoom := errors.New("boom")
            out := MapErr(func(e error) error {
                return e // identity
            })(mo.Err[int](errBoom))

            if out.IsOk() {
                t.Fatalf("MapErr identity on an error must stay an error")
            }
            if out.Error() != errBoom {
                t.Fatalf("expected the same error instance back, got %v", out.Error())
            }
        }
        """
        proc = _run_driver(
            "result", "bench_maperr_same_test.go", src,
            "TestBenchMapErrSameInstance",
        )
        assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"

    def test_maperr_nil_return_still_error(self):
        """L2: MapErr whose mapper returns nil must NOT silently become Ok.

        The doc's contract: MapErr is error-to-error; a nil mapped error must
        still be treated as an error branch (it must not turn into Ok).
        """
        src = """
        package result

        import (
            "errors"
            "testing"

            "github.com/samber/mo"
        )

        func TestBenchMapErrNil(t *testing.T) {
            out := MapErr(func(e error) error {
                return nil
            })(mo.Err[int](errors.New("boom")))

            if out.IsOk() {
                t.Fatalf("MapErr returning nil must NOT become Ok; result must stay an error")
            }
            if !out.IsError() {
                t.Fatalf("result must remain an error branch")
            }
        }
        """
        proc = _run_driver(
            "result", "bench_maperr_nil_test.go", src,
            "TestBenchMapErrNil",
        )
        assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"

    def test_recover_and_maperr_compose_in_pipe(self):
        """L2: both combinators have the func(Result[T]) Result[T] shape and
        compose inside result.Pipe (proves the single-type signature)."""
        src = """
        package result

        import (
            "errors"
            "fmt"
            "strings"
            "testing"

            "github.com/samber/mo"
        )

        func TestBenchRecoverMapErrCompose(t *testing.T) {
            // MapErr then Recover: error -> rewritten error -> recovered Ok.
            f := Pipe2(
                MapErr(func(e error) error { return fmt.Errorf("ctx: %w", e) }),
                Recover(func(e error) int {
                    if !strings.Contains(e.Error(), "ctx:") {
                        return -999
                    }
                    return 42
                }),
            )

            out := f(mo.Err[int](errors.New("boom")))
            val, err := out.Get()
            if err != nil {
                t.Fatalf("expected Ok after compose, got %v", err)
            }
            if val != 42 {
                t.Fatalf("expected recovered value 42 (error seen by Recover was rewritten), got %d", val)
            }

            // Ok input flows through both untouched.
            out2 := f(mo.Ok(7))
            v2, e2 := out2.Get()
            if e2 != nil || v2 != 7 {
                t.Fatalf("Ok must pass through compose untouched, got %d / %v", v2, e2)
            }
        }
        """
        proc = _run_driver(
            "result", "bench_compose_test.go", src,
            "TestBenchRecoverMapErrCompose",
        )
        assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"

    def test_recover_invoked_at_most_once(self):
        """L2: across many error inputs, Recover invokes fn exactly once per call."""
        src = """
        package result

        import (
            "errors"
            "testing"

            "github.com/samber/mo"
        )

        func TestBenchRecoverCallCount(t *testing.T) {
            calls := 0
            r := Recover(func(e error) int {
                calls++
                return 0
            })
            // 3 error inputs -> exactly 3 invocations.
            r(mo.Err[int](errors.New("a")))
            r(mo.Err[int](errors.New("b")))
            r(mo.Err[int](errors.New("c")))
            // 2 Ok inputs -> no additional invocations.
            r(mo.Ok(1))
            r(mo.Ok(2))
            if calls != 3 {
                t.Fatalf("expected exactly 3 invocations (one per error input), got %d", calls)
            }
        }
        """
        proc = _run_driver(
            "result", "bench_recover_count_test.go", src,
            "TestBenchRecoverCallCount",
        )
        assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"
