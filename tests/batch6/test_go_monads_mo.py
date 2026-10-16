"""Tests for skill `go-monads-mo` (variant ext6).

Verifies the task "Add a Partition Function for Slices of Either" of
`github.com/samber/mo`.

The task requires a single package-level generic function in the ROOT `mo`
package (new file `partition.go`):

    func Partition[L any, R any](items []Either[L, R]) ([]L, []R)

Semantics under test:
  - left values route to the first slice, right values to the second
  - relative order within each side matches input order
  - both returned slices are ALWAYS non-nil (even for empty input)
  - empty input -> two non-nil, length-0 slices
  - all-left / all-right edge cases

Strategy: L1 cases check the deliverable source compiles and the `Partition`
symbol is a real package-level function (via `go doc`, the toolchain's own
symbol resolver, not text grep). L2 cases inject *independent* Go driver test
files into the repo root (package `mo`) and run them with `go test`, asserting
on the real runtime behavior of the agent's implementation. Drivers are written
by THIS test (not the agent), so a stub / hardcoded / keyword-only solution
fails. A naive impl that returns nil slices, ignores order, or mis-routes
left/right is caught.
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

    def test_partition_file_exists(self):
        """L1: partition.go (the new deliverable) exists in the repo root."""
        assert os.path.isfile(os.path.join(REPO_DIR, "partition.go"))

    def test_partition_test_file_exists(self):
        """L1: partition_test.go (the agent's own tests) exists in repo root."""
        assert os.path.isfile(os.path.join(REPO_DIR, "partition_test.go"))

    def test_partition_symbol_declared_via_go_doc(self):
        """L1: Partition is a real package-level func in package `mo`.

        Uses `go doc` (the toolchain's symbol resolver) rather than grepping,
        so only a genuine exported declaration counts.
        """
        proc = _run(["go", "doc", ".", "Partition"], cwd=REPO_DIR)
        assert proc.returncode == 0, (
            f"go doc . Partition failed:\n{proc.stdout}\n{proc.stderr}"
        )
        assert "func Partition" in proc.stdout, (
            f"Partition is not a package-level function: {proc.stdout}"
        )
        # Signature must take a slice of Either and return two slices.
        assert "Either" in proc.stdout, (
            f"Partition signature should mention Either: {proc.stdout}"
        )

    def test_module_builds(self):
        """L1: the whole module compiles with the new code (go build ./...)."""
        proc = _run(["go", "build", "./..."], cwd=REPO_DIR)
        assert proc.returncode == 0, (
            f"go build ./... failed:\n{proc.stdout}\n{proc.stderr}"
        )

    def test_partition_run_suite_passes(self):
        """L1->L2: the doc's native acceptance command passes.

        `go test ./... -run Partition` must succeed, exercising the agent's
        own partition_test.go cases.
        """
        proc = _run(["go", "test", "./...", "-run", "Partition"], cwd=REPO_DIR)
        assert proc.returncode == 0, (
            f"go test ./... -run Partition failed:\n{proc.stdout}\n{proc.stderr}"
        )

    def test_existing_root_suite_still_passes(self):
        """L1->L2: pre-existing root `mo` package tests are not broken."""
        proc = _run(["go", "test", "-count=1", "."], cwd=REPO_DIR)
        assert proc.returncode == 0, (
            f"go test . failed:\n{proc.stdout}\n{proc.stderr}"
        )

    # ------------------------------------------------------------------ L2 ---

    def test_partition_mixed_order_preserved(self):
        """L2: mixed input -> ([1,2],[a,b]) with input order kept per side."""
        src = """
        package mo

        import "testing"

        func TestBenchPartitionMixed(t *testing.T) {
            in := []Either[int, string]{Left[int, string](1), Right[int, string]("a"), Left[int, string](2), Right[int, string]("b")}
            ls, rs := Partition(in)
            wantL := []int{1, 2}
            wantR := []string{"a", "b"}
            if len(ls) != len(wantL) {
                t.Fatalf("left len = %d want %d (%v)", len(ls), len(wantL), ls)
            }
            for i := range wantL {
                if ls[i] != wantL[i] {
                    t.Fatalf("left order mismatch: got %v want %v", ls, wantL)
                }
            }
            if len(rs) != len(wantR) {
                t.Fatalf("right len = %d want %d (%v)", len(rs), len(wantR), rs)
            }
            for i := range wantR {
                if rs[i] != wantR[i] {
                    t.Fatalf("right order mismatch: got %v want %v", rs, wantR)
                }
            }
        }
        """
        proc = _run_driver(
            "", "bench_partition_mixed_test.go", src, "TestBenchPartitionMixed"
        )
        assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"

    def test_partition_empty_nonnil_slices(self):
        """L2: empty input -> two non-nil, length-0 slices (no nil cheat)."""
        src = """
        package mo

        import "testing"

        func TestBenchPartitionEmpty(t *testing.T) {
            ls, rs := Partition([]Either[int, string]{})
            if ls == nil {
                t.Fatalf("left slice must be non-nil for empty input")
            }
            if rs == nil {
                t.Fatalf("right slice must be non-nil for empty input")
            }
            if len(ls) != 0 {
                t.Fatalf("left len = %d want 0", len(ls))
            }
            if len(rs) != 0 {
                t.Fatalf("right len = %d want 0", len(rs))
            }
        }
        """
        proc = _run_driver(
            "", "bench_partition_empty_test.go", src, "TestBenchPartitionEmpty"
        )
        assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"

    def test_partition_all_left(self):
        """L2: all-left input -> all left values in order, empty non-nil right."""
        src = """
        package mo

        import "testing"

        func TestBenchPartitionAllLeft(t *testing.T) {
            ls, rs := Partition([]Either[int, string]{Left[int, string](9), Left[int, string](8)})
            want := []int{9, 8}
            if len(ls) != len(want) {
                t.Fatalf("left len = %d want %d (%v)", len(ls), len(want), ls)
            }
            for i := range want {
                if ls[i] != want[i] {
                    t.Fatalf("left order mismatch: got %v want %v", ls, want)
                }
            }
            if rs == nil {
                t.Fatalf("right slice must be non-nil")
            }
            if len(rs) != 0 {
                t.Fatalf("right len = %d want 0 (%v)", len(rs), rs)
            }
        }
        """
        proc = _run_driver(
            "", "bench_partition_allleft_test.go", src, "TestBenchPartitionAllLeft"
        )
        assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"

    def test_partition_all_right(self):
        """L2: single-right input -> empty non-nil left, [x] right."""
        src = """
        package mo

        import "testing"

        func TestBenchPartitionAllRight(t *testing.T) {
            ls, rs := Partition([]Either[int, string]{Right[int, string]("x")})
            if ls == nil {
                t.Fatalf("left slice must be non-nil")
            }
            if len(ls) != 0 {
                t.Fatalf("left len = %d want 0 (%v)", len(ls), ls)
            }
            want := []string{"x"}
            if len(rs) != len(want) {
                t.Fatalf("right len = %d want %d (%v)", len(rs), len(want), rs)
            }
            if rs[0] != "x" {
                t.Fatalf("right[0] = %q want %q", rs[0], "x")
            }
        }
        """
        proc = _run_driver(
            "", "bench_partition_allright_test.go", src, "TestBenchPartitionAllRight"
        )
        assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"

    def test_partition_interleaved_routing(self):
        """L2: heavy interleaving must route every element to the correct side.

        A naive impl that mis-classifies (e.g. uses IsRight where IsLeft was
        meant, or copies wholesale) is caught by both the per-side values and
        the per-side counts.
        """
        src = """
        package mo

        import "testing"

        func TestBenchPartitionInterleaved(t *testing.T) {
            in := []Either[int, string]{
                Right[int, string]("r0"),
                Left[int, string](1),
                Left[int, string](2),
                Right[int, string]("r1"),
                Left[int, string](3),
                Right[int, string]("r2"),
            }
            ls, rs := Partition(in)
            wantL := []int{1, 2, 3}
            wantR := []string{"r0", "r1", "r2"}
            if len(ls) != len(wantL) {
                t.Fatalf("left count = %d want %d (%v)", len(ls), len(wantL), ls)
            }
            for i := range wantL {
                if ls[i] != wantL[i] {
                    t.Fatalf("left mismatch at %d: got %v want %v", i, ls, wantL)
                }
            }
            if len(rs) != len(wantR) {
                t.Fatalf("right count = %d want %d (%v)", len(rs), len(wantR), rs)
            }
            for i := range wantR {
                if rs[i] != wantR[i] {
                    t.Fatalf("right mismatch at %d: got %v want %v", i, rs, wantR)
                }
            }
        }
        """
        proc = _run_driver(
            "", "bench_partition_interleaved_test.go", src,
            "TestBenchPartitionInterleaved",
        )
        assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"

    def test_partition_string_int_type_params(self):
        """L2: Partition is generic over arbitrary L/R (string-left, int-right)."""
        src = """
        package mo

        import "testing"

        func TestBenchPartitionStringInt(t *testing.T) {
            in := []Either[string, int]{
                Left[string, int]("err1"),
                Right[string, int](10),
                Left[string, int]("err2"),
                Right[string, int](20),
                Right[string, int](30),
            }
            ls, rs := Partition(in)
            wantL := []string{"err1", "err2"}
            wantR := []int{10, 20, 30}
            if len(ls) != len(wantL) {
                t.Fatalf("left len = %d want %d (%v)", len(ls), len(wantL), ls)
            }
            for i := range wantL {
                if ls[i] != wantL[i] {
                    t.Fatalf("left mismatch: got %v want %v", ls, wantL)
                }
            }
            if len(rs) != len(wantR) {
                t.Fatalf("right len = %d want %d (%v)", len(rs), len(wantR), rs)
            }
            for i := range wantR {
                if rs[i] != wantR[i] {
                    t.Fatalf("right mismatch: got %v want %v", rs, wantR)
                }
            }
        }
        """
        proc = _run_driver(
            "", "bench_partition_stringint_test.go", src,
            "TestBenchPartitionStringInt",
        )
        assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"

    def test_partition_total_count_conservation(self):
        """L2: |left| + |right| == |input| for a larger mixed slice.

        Guards against an impl that drops or duplicates elements.
        """
        src = """
        package mo

        import "testing"

        func TestBenchPartitionCount(t *testing.T) {
            in := []Either[int, string]{}
            for i := 0; i < 50; i++ {
                if i%3 == 0 {
                    in = append(in, Right[int, string]("v"))
                } else {
                    in = append(in, Left[int, string](i))
                }
            }
            ls, rs := Partition(in)
            if len(ls)+len(rs) != len(in) {
                t.Fatalf("count not conserved: %d + %d != %d", len(ls), len(rs), len(in))
            }
            // Exactly the multiples-of-3 (0,3,...,48) are right: 17 of them.
            wantRight := 0
            for i := 0; i < 50; i++ {
                if i%3 == 0 {
                    wantRight++
                }
            }
            if len(rs) != wantRight {
                t.Fatalf("right count = %d want %d", len(rs), wantRight)
            }
            if len(ls) != len(in)-wantRight {
                t.Fatalf("left count = %d want %d", len(ls), len(in)-wantRight)
            }
        }
        """
        proc = _run_driver(
            "", "bench_partition_count_test.go", src, "TestBenchPartitionCount"
        )
        assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"

    def test_partition_does_not_mutate_input(self):
        """L2: Partition must not alter the input slice's elements/length."""
        src = """
        package mo

        import "testing"

        func TestBenchPartitionNoMutate(t *testing.T) {
            in := []Either[int, string]{
                Left[int, string](1),
                Right[int, string]("a"),
                Left[int, string](2),
            }
            origLen := len(in)
            _, _ = Partition(in)
            if len(in) != origLen {
                t.Fatalf("input length changed: %d -> %d", origLen, len(in))
            }
            // Elements must still classify the same way after the call.
            if !in[0].IsLeft() || !in[1].IsRight() || !in[2].IsLeft() {
                t.Fatalf("input element identities mutated")
            }
            l0, _ := in[0].Left()
            if l0 != 1 {
                t.Fatalf("input[0] left value changed to %v", l0)
            }
            r1, _ := in[1].Right()
            if r1 != "a" {
                t.Fatalf("input[1] right value changed to %v", r1)
            }
        }
        """
        proc = _run_driver(
            "", "bench_partition_nomutate_test.go", src,
            "TestBenchPartitionNoMutate",
        )
        assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"
