"""Tests for skill `go-monads-mo` (variant ext3).

Verifies the task "Add Filter and FlatMapNone Methods to Option" of
`github.com/samber/mo`.

The task requires two NEW instance methods on the core `Option[T]` type
(declared in `option.go`, package `mo`):

  - func (o Option[T]) Filter(predicate func(value T) bool) Option[T]
  - func (o Option[T]) FlatMapNone(mapper func() Option[T]) Option[T]

Semantics under test:
  Filter:
    - present && predicate(value) == true   -> option unchanged (same value)
    - present && predicate(value) == false  -> None
    - absent                                 -> None, predicate NEVER called
    - predicate invoked at most once, only for a present value
  FlatMapNone:
    - present                                -> option unchanged, mapper NEVER called
    - absent                                 -> result of mapper() (Some or None)
    - mapper invoked at most once, only for an absent option

Verification strategy:
  L1 cases check the deliverable source compiles and that the two methods are
  declared on Option with the correct signatures (resolved by the Go toolchain
  via `go doc`, not by text grepping).

  L2 cases inject INDEPENDENT Go driver test files (written by THIS file, not by
  the agent) into the repo root `package mo` and run them with `go test`,
  asserting on real runtime behavior. Counter-closure drivers prove the callback
  is skipped on the no-op branch, so a stub that always calls the callback, that
  returns the receiver unchanged, or that ignores the predicate result fails.
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
    """Ensure the module builds and dependencies are available before tests."""
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

    def test_option_go_file_exists(self):
        """L1: option.go (the deliverable to modify) exists in the repo root."""
        assert os.path.isfile(os.path.join(REPO_DIR, "option.go"))

    def test_filter_declared_via_go_doc(self):
        """L1: Filter is a declared method on Option with the expected shape.

        Uses `go doc` so only a genuine method declaration counts, and asserts
        the predicate signature `func(value T) bool` and `Option[T]` return.
        """
        proc = _run(["go", "doc", ".", "Option.Filter"], cwd=REPO_DIR)
        assert proc.returncode == 0, (
            f"go doc Option.Filter failed:\n{proc.stdout}\n{proc.stderr}"
        )
        out = proc.stdout
        assert "func " in out and "Filter" in out, f"not a method: {out}"
        assert ") bool)" in out.replace(" ", " "), f"predicate must return bool: {out}"
        assert "Option[T]" in out, f"Filter must return Option[T]: {out}"

    def test_flatmapnone_declared_via_go_doc(self):
        """L1: FlatMapNone is a declared method on Option returning Option[T].

        The mapper must be a zero-arg func returning Option[T]
        (`func() Option[T]`), distinguishing it from MapNone's
        `func() (T, bool)` signature.
        """
        proc = _run(["go", "doc", ".", "Option.FlatMapNone"], cwd=REPO_DIR)
        assert proc.returncode == 0, (
            f"go doc Option.FlatMapNone failed:\n{proc.stdout}\n{proc.stderr}"
        )
        out = proc.stdout
        assert "func " in out and "FlatMapNone" in out, f"not a method: {out}"
        # mapper returns Option[T] and the method returns Option[T] -> at least
        # two occurrences of Option[T] in the signature line.
        assert out.count("Option[T]") >= 2, (
            f"FlatMapNone mapper must produce Option[T]: {out}"
        )
        # Must NOT be the MapNone (T, bool) shape.
        assert "(T, bool)" not in out, (
            f"FlatMapNone mapper must be func() Option[T], not (T, bool): {out}"
        )

    def test_module_builds(self):
        """L1: the whole module compiles with the new methods (go build ./...)."""
        proc = _run(["go", "build", "./..."], cwd=REPO_DIR)
        assert proc.returncode == 0, (
            f"go build ./... failed:\n{proc.stdout}\n{proc.stderr}"
        )

    def test_existing_suite_still_passes(self):
        """L1->L2: the existing root package suite is not broken by the change."""
        proc = _run(["go", "test", "-count=1", "."], cwd=REPO_DIR)
        assert proc.returncode == 0, (
            f"go test . failed:\n{proc.stdout}\n{proc.stderr}"
        )

    # ------------------------------------------------------------------ L2 ---

    def test_filter_present_true_unchanged(self):
        """L2: Some(10).Filter(even) keeps the present value (10) unchanged."""
        src = """
        package mo

        import "testing"

        func TestBenchFilterPresentTrue(t *testing.T) {
            in := Some(10)
            out := in.Filter(func(n int) bool { return n%2 == 0 })
            v, ok := out.Get()
            if !ok {
                t.Fatalf("expected present, got None")
            }
            if v != 10 {
                t.Fatalf("value changed: got %d want 10", v)
            }
        }
        """
        proc = _run_driver(
            "", "bench_filter_present_true_test.go", src,
            "TestBenchFilterPresentTrue",
        )
        assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"

    def test_filter_present_false_becomes_none(self):
        """L2: Some(7).Filter(even) -> None (predicate false discards the value).

        A stub that returns the receiver unchanged or ignores the predicate
        result fails here.
        """
        src = """
        package mo

        import "testing"

        func TestBenchFilterPresentFalse(t *testing.T) {
            out := Some(7).Filter(func(n int) bool { return n%2 == 0 })
            if out.IsPresent() {
                v, _ := out.Get()
                t.Fatalf("expected None, got present %v", v)
            }
        }
        """
        proc = _run_driver(
            "", "bench_filter_present_false_test.go", src,
            "TestBenchFilterPresentFalse",
        )
        assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"

    def test_filter_absent_skips_predicate(self):
        """L2: None.Filter(p) -> None and the predicate is NEVER invoked.

        Counter closure proves the no-op branch does not call the predicate; a
        stub that always evaluates the predicate fails.
        """
        src = """
        package mo

        import "testing"

        func TestBenchFilterAbsentNoCall(t *testing.T) {
            calls := 0
            out := None[int]().Filter(func(n int) bool {
                calls++
                return true
            })
            if out.IsPresent() {
                t.Fatalf("expected None")
            }
            if calls != 0 {
                t.Fatalf("predicate must not run on absent option, ran %d times", calls)
            }
        }
        """
        proc = _run_driver(
            "", "bench_filter_absent_test.go", src,
            "TestBenchFilterAbsentNoCall",
        )
        assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"

    def test_filter_present_predicate_called_once(self):
        """L2: on a present value the predicate is invoked exactly once."""
        src = """
        package mo

        import "testing"

        func TestBenchFilterCalledOnce(t *testing.T) {
            calls := 0
            in := Some("hello")
            out := in.Filter(func(s string) bool {
                calls++
                return len(s) == 5
            })
            if calls != 1 {
                t.Fatalf("predicate must run exactly once, ran %d times", calls)
            }
            v, ok := out.Get()
            if !ok || v != "hello" {
                t.Fatalf("expected Some(\\"hello\\"), got ok=%v v=%q", ok, v)
            }
        }
        """
        proc = _run_driver(
            "", "bench_filter_once_test.go", src,
            "TestBenchFilterCalledOnce",
        )
        assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"

    def test_flatmapnone_present_unchanged_skips_mapper(self):
        """L2: Some("a").FlatMapNone(...) -> Some("a"), mapper NEVER called.

        Counter closure proves the present branch is a no-op; a stub that always
        calls the mapper or replaces the value fails.
        """
        src = """
        package mo

        import "testing"

        func TestBenchFlatMapNonePresent(t *testing.T) {
            calls := 0
            out := Some("a").FlatMapNone(func() Option[string] {
                calls++
                return Some("b")
            })
            v, ok := out.Get()
            if !ok {
                t.Fatalf("expected present")
            }
            if v != "a" {
                t.Fatalf("present option must be unchanged: got %q want \\"a\\"", v)
            }
            if calls != 0 {
                t.Fatalf("mapper must not run on present option, ran %d times", calls)
            }
        }
        """
        proc = _run_driver(
            "", "bench_fmn_present_test.go", src,
            "TestBenchFlatMapNonePresent",
        )
        assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"

    def test_flatmapnone_absent_returns_mapper_some(self):
        """L2: None.FlatMapNone(-> Some("b")) -> Some("b"), mapper called once."""
        src = """
        package mo

        import "testing"

        func TestBenchFlatMapNoneAbsentSome(t *testing.T) {
            calls := 0
            out := None[string]().FlatMapNone(func() Option[string] {
                calls++
                return Some("b")
            })
            v, ok := out.Get()
            if !ok {
                t.Fatalf("expected present from mapper, got None")
            }
            if v != "b" {
                t.Fatalf("got %q want \\"b\\"", v)
            }
            if calls != 1 {
                t.Fatalf("mapper must run exactly once on absent, ran %d times", calls)
            }
        }
        """
        proc = _run_driver(
            "", "bench_fmn_absent_some_test.go", src,
            "TestBenchFlatMapNoneAbsentSome",
        )
        assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"

    def test_flatmapnone_absent_mapper_returns_none(self):
        """L2: None.FlatMapNone(-> None) -> None (mapper's absent result honored)."""
        src = """
        package mo

        import "testing"

        func TestBenchFlatMapNoneAbsentNone(t *testing.T) {
            out := None[string]().FlatMapNone(func() Option[string] {
                return None[string]()
            })
            if out.IsPresent() {
                v, _ := out.Get()
                t.Fatalf("expected None, got present %q", v)
            }
        }
        """
        proc = _run_driver(
            "", "bench_fmn_absent_none_test.go", src,
            "TestBenchFlatMapNoneAbsentNone",
        )
        assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"

    def test_filter_int_and_string_instantiations(self):
        """L2: Filter behaves correctly across int and string type instantiations."""
        src = """
        package mo

        import "testing"

        func TestBenchFilterMultiType(t *testing.T) {
            // int: keep even
            if v, ok := Some(4).Filter(func(n int) bool { return n%2 == 0 }).Get(); !ok || v != 4 {
                t.Fatalf("int keep failed: ok=%v v=%d", ok, v)
            }
            if Some(3).Filter(func(n int) bool { return n%2 == 0 }).IsPresent() {
                t.Fatalf("int drop failed: expected None")
            }
            // string: keep non-empty
            if v, ok := Some("x").Filter(func(s string) bool { return s != "" }).Get(); !ok || v != "x" {
                t.Fatalf("string keep failed: ok=%v v=%q", ok, v)
            }
            if Some("").Filter(func(s string) bool { return s != "" }).IsPresent() {
                t.Fatalf("string drop failed: expected None")
            }
        }
        """
        proc = _run_driver(
            "", "bench_filter_multitype_test.go", src,
            "TestBenchFilterMultiType",
        )
        assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"

    def test_filter_then_flatmapnone_compose(self):
        """L2: Filter that drops a value can be rescued by FlatMapNone.

        Some(3).Filter(even) -> None -> FlatMapNone(-> Some(-1)) -> Some(-1).
        This exercises the two new methods composed end-to-end, ensuring the
        absent state produced by Filter feeds the FlatMapNone fallback branch.
        """
        src = """
        package mo

        import "testing"

        func TestBenchFilterFlatMapNoneCompose(t *testing.T) {
            mapperCalls := 0
            out := Some(3).
                Filter(func(n int) bool { return n%2 == 0 }).
                FlatMapNone(func() Option[int] {
                    mapperCalls++
                    return Some(-1)
                })
            v, ok := out.Get()
            if !ok {
                t.Fatalf("expected present from fallback")
            }
            if v != -1 {
                t.Fatalf("got %d want -1", v)
            }
            if mapperCalls != 1 {
                t.Fatalf("fallback mapper must run once, ran %d", mapperCalls)
            }

            // And when Filter keeps the value, FlatMapNone is a no-op.
            mapperCalls = 0
            out2 := Some(4).
                Filter(func(n int) bool { return n%2 == 0 }).
                FlatMapNone(func() Option[int] {
                    mapperCalls++
                    return Some(-1)
                })
            v2, ok2 := out2.Get()
            if !ok2 || v2 != 4 {
                t.Fatalf("kept value path failed: ok=%v v=%d", ok2, v2)
            }
            if mapperCalls != 0 {
                t.Fatalf("mapper must not run when value kept, ran %d", mapperCalls)
            }
        }
        """
        proc = _run_driver(
            "", "bench_filter_fmn_compose_test.go", src,
            "TestBenchFilterFlatMapNoneCompose",
        )
        assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"
