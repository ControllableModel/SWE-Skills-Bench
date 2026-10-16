"""Tests for skill `go-monads-mo` (variant ext2).

Verifies the task "Add Filtering Combinators to the option Sub-Package" of
`github.com/samber/mo`.

The task requires two package-level generic functions in `option/transforms.go`:
  - option.Filter(func(T) bool) -> func(mo.Option[T]) mo.Option[T]
  - option.Reject(func(T) bool) -> func(mo.Option[T]) mo.Option[T]

Semantics under test:
  - Filter: present + predicate(true)  -> present, same value
            present + predicate(false) -> absent
            absent input               -> absent, predicate NOT invoked
  - Reject: logical inverse of Filter (keeps present only when predicate false)
            absent input               -> absent, predicate NOT invoked
  - Both keep the single-type signature shape of option.Map / option.FlatMap so
    they compose inside option.Pipe2 / option.Pipe3 chains on one element type.
  - The predicate is invoked AT MOST ONCE and only when a value is present.

Strategy: L1 cases check the deliverable source compiles and the symbols are
declared as real package-level functions (via `go doc`). L2 cases inject
*independent* Go driver test files (written by THIS test, not the agent) into
the option/ package directory and run them with `go test -run`, asserting on
the real runtime behavior. A stub that ignores the predicate, hardcodes
presence/absence, or calls the predicate on an absent input fails these tests.
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

    def test_filter_symbol_declared_via_go_doc(self):
        """L1: option.Filter is a real package-level function declaration.

        Uses `go doc` (the toolchain's symbol resolver) rather than text
        grepping, so only a genuinely exported function declaration counts.
        """
        proc = _run(["go", "doc", "./option", "Filter"], cwd=REPO_DIR)
        assert proc.returncode == 0, (
            f"go doc ./option Filter failed: {proc.stdout}\n{proc.stderr}"
        )
        assert "func Filter" in proc.stdout, (
            f"option.Filter is not a function: {proc.stdout}"
        )

    def test_reject_symbol_declared_via_go_doc(self):
        """L1: option.Reject is a real package-level function declaration."""
        proc = _run(["go", "doc", "./option", "Reject"], cwd=REPO_DIR)
        assert proc.returncode == 0, (
            f"go doc ./option Reject failed: {proc.stdout}\n{proc.stderr}"
        )
        assert "func Reject" in proc.stdout, (
            f"option.Reject is not a function: {proc.stdout}"
        )

    def test_module_builds(self):
        """L1: the whole module compiles with the new code (go build ./...)."""
        proc = _run(["go", "build", "./..."], cwd=REPO_DIR)
        assert proc.returncode == 0, (
            f"go build ./... failed:\n{proc.stdout}\n{proc.stderr}"
        )

    def test_existing_option_suite_still_passes(self):
        """L1->L2: existing option suite is not broken by the change."""
        proc = _run(["go", "test", "-count=1", "./option/..."], cwd=REPO_DIR)
        assert proc.returncode == 0, (
            f"go test ./option/... failed:\n{proc.stdout}\n{proc.stderr}"
        )

    # ------------------------------------------------------------------ L2 ---

    def test_filter_keeps_present_when_predicate_true(self):
        """L2: Filter keeps a present value (same value) when predicate true."""
        src = """
        package option

        import (
            "testing"

            "github.com/samber/mo"
        )

        func TestBenchFilterKeepsPresent(t *testing.T) {
            out := Filter(func(n int) bool { return n > 0 })(mo.Some(5))
            v, ok := out.Get()
            if !ok {
                t.Fatalf("expected present, got absent")
            }
            if v != 5 {
                t.Fatalf("expected value 5, got %d", v)
            }
        }
        """
        proc = _run_driver(
            "option", "bench_filter_keep_test.go", src,
            "TestBenchFilterKeepsPresent",
        )
        assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"

    def test_filter_drops_present_when_predicate_false(self):
        """L2: Filter drops a present value (-> absent) when predicate false.

        A stub that always returns its input unchanged fails here.
        """
        src = """
        package option

        import (
            "testing"

            "github.com/samber/mo"
        )

        func TestBenchFilterDropsPresent(t *testing.T) {
            out := Filter(func(n int) bool { return n > 0 })(mo.Some(-1))
            if out.IsPresent() {
                v, _ := out.Get()
                t.Fatalf("expected absent, got present %d", v)
            }
        }
        """
        proc = _run_driver(
            "option", "bench_filter_drop_test.go", src,
            "TestBenchFilterDropsPresent",
        )
        assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"

    def test_filter_absent_input_predicate_not_called(self):
        """L2: Filter on absent input -> absent AND predicate never invoked.

        Uses a counter closure; a naive impl that calls the predicate on the
        zero value (or always returns present) fails.
        """
        src = """
        package option

        import (
            "testing"

            "github.com/samber/mo"
        )

        func TestBenchFilterAbsentNoCall(t *testing.T) {
            calls := 0
            pred := func(n int) bool { calls++; return true }
            out := Filter(pred)(mo.None[int]())
            if out.IsPresent() {
                v, _ := out.Get()
                t.Fatalf("expected absent, got present %d", v)
            }
            if calls != 0 {
                t.Fatalf("predicate must not be called for absent input, got %d calls", calls)
            }
        }
        """
        proc = _run_driver(
            "option", "bench_filter_absent_test.go", src,
            "TestBenchFilterAbsentNoCall",
        )
        assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"

    def test_filter_predicate_called_exactly_once(self):
        """L2: when present, Filter invokes the predicate exactly once."""
        src = """
        package option

        import (
            "testing"

            "github.com/samber/mo"
        )

        func TestBenchFilterCalledOnce(t *testing.T) {
            calls := 0
            pred := func(n int) bool { calls++; return n%2 == 0 }
            out := Filter(pred)(mo.Some(4))
            v, ok := out.Get()
            if !ok || v != 4 {
                t.Fatalf("expected present Some(4), got ok=%v v=%d", ok, v)
            }
            if calls != 1 {
                t.Fatalf("predicate must be called exactly once, got %d", calls)
            }
        }
        """
        proc = _run_driver(
            "option", "bench_filter_once_test.go", src,
            "TestBenchFilterCalledOnce",
        )
        assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"

    def test_reject_drops_present_when_predicate_true(self):
        """L2: Reject drops a present value (-> absent) when predicate true."""
        src = """
        package option

        import (
            "testing"

            "github.com/samber/mo"
        )

        func TestBenchRejectDropsTrue(t *testing.T) {
            out := Reject(func(s string) bool { return s == "" })(mo.Some(""))
            if out.IsPresent() {
                v, _ := out.Get()
                t.Fatalf("expected absent, got present %q", v)
            }
        }
        """
        proc = _run_driver(
            "option", "bench_reject_drop_test.go", src,
            "TestBenchRejectDropsTrue",
        )
        assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"

    def test_reject_keeps_present_when_predicate_false(self):
        """L2: Reject keeps a present value (same value) when predicate false."""
        src = """
        package option

        import (
            "testing"

            "github.com/samber/mo"
        )

        func TestBenchRejectKeepsFalse(t *testing.T) {
            out := Reject(func(s string) bool { return s == "" })(mo.Some("hi"))
            v, ok := out.Get()
            if !ok {
                t.Fatalf("expected present, got absent")
            }
            if v != "hi" {
                t.Fatalf("expected value %q, got %q", "hi", v)
            }
        }
        """
        proc = _run_driver(
            "option", "bench_reject_keep_test.go", src,
            "TestBenchRejectKeepsFalse",
        )
        assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"

    def test_reject_absent_input_predicate_not_called(self):
        """L2: Reject on absent input -> absent AND predicate never invoked."""
        src = """
        package option

        import (
            "testing"

            "github.com/samber/mo"
        )

        func TestBenchRejectAbsentNoCall(t *testing.T) {
            calls := 0
            pred := func(s string) bool { calls++; return false }
            out := Reject(pred)(mo.None[string]())
            if out.IsPresent() {
                v, _ := out.Get()
                t.Fatalf("expected absent, got present %q", v)
            }
            if calls != 0 {
                t.Fatalf("predicate must not be called for absent input, got %d calls", calls)
            }
        }
        """
        proc = _run_driver(
            "option", "bench_reject_absent_test.go", src,
            "TestBenchRejectAbsentNoCall",
        )
        assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"

    def test_filter_reject_are_inverses(self):
        """L2: Filter and Reject are inverses for the same predicate.

        For a present value, exactly one of Filter/Reject keeps it. A stub that
        implements Reject identically to Filter (copy-paste bug) fails here.
        """
        src = """
        package option

        import (
            "testing"

            "github.com/samber/mo"
        )

        func TestBenchFilterRejectInverse(t *testing.T) {
            pred := func(n int) bool { return n > 0 }

            // value 5: predicate true -> Filter keeps, Reject drops
            f5 := Filter(pred)(mo.Some(5))
            r5 := Reject(pred)(mo.Some(5))
            if !f5.IsPresent() {
                t.Fatalf("Filter should keep 5 (pred true)")
            }
            if r5.IsPresent() {
                t.Fatalf("Reject should drop 5 (pred true)")
            }

            // value -3: predicate false -> Filter drops, Reject keeps
            fm := Filter(pred)(mo.Some(-3))
            rm := Reject(pred)(mo.Some(-3))
            if fm.IsPresent() {
                t.Fatalf("Filter should drop -3 (pred false)")
            }
            v, ok := rm.Get()
            if !ok || v != -3 {
                t.Fatalf("Reject should keep -3 (pred false), got ok=%v v=%d", ok, v)
            }
        }
        """
        proc = _run_driver(
            "option", "bench_filter_reject_inverse_test.go", src,
            "TestBenchFilterRejectInverse",
        )
        assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"

    def test_filter_composes_in_pipe_chain(self):
        """L2: Filter keeps the single-type shape and composes in Pipe2.

        Drives the doc's constraint that Filter must slot into option.Pipe2 /
        Pipe3 chains operating on a single element type. Confirms the returned
        closure's type is func(mo.Option[T]) mo.Option[T] by actually using it
        inside Pipe2 alongside Map.
        """
        src = """
        package option

        import (
            "testing"

            "github.com/samber/mo"
        )

        func TestBenchFilterPipe(t *testing.T) {
            // Map(+10) then Filter(>15): Some(2) -> Some(12) -> filtered out.
            mapAdd := Map(func(n int) int { return n + 10 })
            keepBig := Filter(func(n int) bool { return n > 15 })

            out1 := Pipe2(mo.Some(2), mapAdd, keepBig) // 12, fails predicate -> absent
            if out1.IsPresent() {
                v, _ := out1.Get()
                t.Fatalf("expected absent for Some(2), got present %d", v)
            }

            out2 := Pipe2(mo.Some(8), mapAdd, keepBig) // 18, passes predicate -> Some(18)
            v, ok := out2.Get()
            if !ok || v != 18 {
                t.Fatalf("expected Some(18) for Some(8), got ok=%v v=%d", ok, v)
            }
        }
        """
        proc = _run_driver(
            "option", "bench_filter_pipe_test.go", src,
            "TestBenchFilterPipe",
        )
        assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"

    def test_reject_composes_in_pipe_chain(self):
        """L2: Reject also composes in a Pipe2 chain (single-type shape)."""
        src = """
        package option

        import (
            "testing"

            "github.com/samber/mo"
        )

        func TestBenchRejectPipe(t *testing.T) {
            // Map(*2) then Reject(==0): Some(0) -> Some(0) -> rejected (absent).
            mapDouble := Map(func(n int) int { return n * 2 })
            dropZero := Reject(func(n int) bool { return n == 0 })

            out1 := Pipe2(mo.Some(0), mapDouble, dropZero) // 0, predicate true -> rejected -> absent
            if out1.IsPresent() {
                v, _ := out1.Get()
                t.Fatalf("expected absent for Some(0), got present %d", v)
            }

            out2 := Pipe2(mo.Some(3), mapDouble, dropZero) // 6, predicate false -> kept
            v, ok := out2.Get()
            if !ok || v != 6 {
                t.Fatalf("expected Some(6) for Some(3), got ok=%v v=%d", ok, v)
            }
        }
        """
        proc = _run_driver(
            "option", "bench_reject_pipe_test.go", src,
            "TestBenchRejectPipe",
        )
        assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"
