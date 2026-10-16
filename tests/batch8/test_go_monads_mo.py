"""Tests for skill `go-monads-mo` (variant ext8).

Verifies the task "Add Map, FlatMap, and Eval/Exec Methods to the State Monad"
of `github.com/samber/mo`.

The task modifies `state.go` to add four methods on the existing
`State[S, A]` type (which models `func(S) (A, S)`):

  - Map(f func(A) A) State[S, A]
        run receiver -> (a, s2); yield (f(a), s2). State threaded unchanged.
  - FlatMap(f func(A) State[S, A]) State[S, A]
        run receiver -> (a, s2); then run f(a) starting from s2.
        State threads left-to-right.
  - Eval(initial S) A     -> only the result value, discarding final state.
  - Exec(initial S) S     -> only the final state, discarding the value.

Constraints under test:
  - No new type parameters (S and A unchanged), consistent with Go methods.
  - Composition is lazy: Map/FlatMap build a new State and execute nothing
    until Run/Eval/Exec is called.

Strategy: L1 cases check the deliverable source compiles and the four methods
are declared with the right signatures (via `go doc`, the toolchain's own
symbol resolver -- not text grep). L2 cases inject *independent* Go driver
test files (written by THIS test, never by the agent) into the package root
and run them with `go test`, asserting on concrete runtime values: returned
value/state pairs, left-to-right state threading, Eval/Exec projection, and
laziness (no side effect until a runner is invoked). A stub that ignores the
state, hardcodes a value, or eagerly evaluates therefore fails.
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
        cwd = REPO_DIR if rel_dir in ("", ".") else os.path.join(REPO_DIR, rel_dir)
        proc = _run(
            ["go", "test", "-count=1", "-run", run_regex, "."],
            cwd=cwd,
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

    def test_state_source_file_exists(self):
        """L1: state.go (the deliverable to modify) exists."""
        assert os.path.isfile(os.path.join(REPO_DIR, "state.go"))

    def test_state_test_file_created(self):
        """L1: state_test.go (the new test deliverable) was created."""
        assert os.path.isfile(os.path.join(REPO_DIR, "state_test.go")), (
            "state_test.go was not created"
        )

    def test_module_builds(self):
        """L1: the whole module compiles with the new methods (go build ./...)."""
        proc = _run(["go", "build", "./..."], cwd=REPO_DIR)
        assert proc.returncode == 0, (
            f"go build ./... failed:\n{proc.stdout}\n{proc.stderr}"
        )

    def test_methods_declared_via_go_doc(self):
        """L1: Map/FlatMap/Eval/Exec are real methods on State (via `go doc`).

        Uses the toolchain's own symbol resolver rather than text grepping, so
        only genuine method declarations count.
        """
        proc = _run(["go", "doc", ".", "State"], cwd=REPO_DIR)
        assert proc.returncode == 0, (
            f"go doc . State failed:\n{proc.stdout}\n{proc.stderr}"
        )
        out = proc.stdout
        for meth in ("Map", "FlatMap", "Eval", "Exec"):
            assert meth in out, (
                f"State.{meth} not present in `go doc . State`:\n{out}"
            )

    def test_method_signatures_compile(self):
        """L1->L2: the four methods resolve with the documented signatures.

        Injects a compile-only driver that takes each method value with the
        exact documented signature; if any signature differs (wrong param /
        return type, extra type params), the package fails to compile.
        """
        src = """
        package mo

        import "testing"

        func TestBenchStateSignatures(t *testing.T) {
            s := NewState(func(st int) (int, int) { return st, st + 1 })

            // Map: func(A) A -> State[S, A]
            var _ State[int, int] = s.Map(func(a int) int { return a })

            // FlatMap: func(A) State[S, A] -> State[S, A]
            var _ State[int, int] = s.FlatMap(func(a int) State[int, int] {
                return NewState(func(st int) (int, int) { return a, st })
            })

            // Eval(initial S) A
            var _ int = s.Eval(0)

            // Exec(initial S) S
            var _ int = s.Exec(0)
        }
        """
        proc = _run_driver(
            "", "bench_state_sig_test.go", src, "TestBenchStateSignatures"
        )
        assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"

    # ------------------------------------------------------------------ L2 ---

    def test_map_transforms_value_keeps_state(self):
        """L2: Map transforms only the value; the final state is unchanged.

        From the doc: NewState(s*2, s+1).Map(+100).Run(5) -> value 110, state 6.
        A stub that ignores f, or that mutates state, fails.
        """
        src = """
        package mo

        import "testing"

        func TestBenchStateMap(t *testing.T) {
            s := NewState(func(st int) (int, int) { return st * 2, st + 1 })
            mapped := s.Map(func(a int) int { return a + 100 })
            v, st := mapped.Run(5)
            if v != 110 {
                t.Fatalf("value = %d, want 110", v)
            }
            if st != 6 {
                t.Fatalf("state = %d, want 6 (state must thread unchanged through Map)", st)
            }
        }
        """
        proc = _run_driver(
            "", "bench_state_map_test.go", src, "TestBenchStateMap"
        )
        assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"

    def test_map_does_not_mutate_receiver(self):
        """L2: Map returns a NEW State; running the receiver is unaffected."""
        src = """
        package mo

        import "testing"

        func TestBenchStateMapPure(t *testing.T) {
            s := NewState(func(st int) (int, int) { return st, st + 1 })
            _ = s.Map(func(a int) int { return a * 1000 })
            // Receiver unchanged: Run(7) still yields the original (7, 8).
            v, st := s.Run(7)
            if v != 7 || st != 8 {
                t.Fatalf("receiver mutated: got (%d, %d), want (7, 8)", v, st)
            }
        }
        """
        proc = _run_driver(
            "", "bench_state_map_pure_test.go", src, "TestBenchStateMapPure"
        )
        assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"

    def test_flatmap_threads_state_left_to_right(self):
        """L2: FlatMap threads state; second step sees first step's output state.

        Doc example: a counter NewState(s, s+1) flat-mapped to draw two values
        and Run(0) -> value 1, final state 2. Encodes that the second draw
        observes state 1, not the initial 0.
        """
        src = """
        package mo

        import "testing"

        func TestBenchStateFlatMapThread(t *testing.T) {
            counter := NewState(func(st int) (int, int) { return st, st + 1 })
            // Draw first value, then draw a second value from the threaded state.
            comp := counter.FlatMap(func(first int) State[int, int] {
                return counter.Map(func(second int) int { return second })
            })
            v, st := comp.Run(0)
            if v != 1 {
                t.Fatalf("value = %d, want 1 (second draw must see threaded state)", v)
            }
            if st != 2 {
                t.Fatalf("final state = %d, want 2", st)
            }
        }
        """
        proc = _run_driver(
            "", "bench_state_flatmap_thread_test.go", src,
            "TestBenchStateFlatMapThread",
        )
        assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"

    def test_flatmap_uses_first_value_in_second_computation(self):
        """L2: FlatMap passes the receiver's value into f, and f's State runs from s2.

        Builds an accumulator: first step yields the initial state as value and
        advances state by 1; f adds that value to the new state. Distinguishes a
        correct impl (uses both first value AND threaded state) from one that
        drops either.
        """
        src = """
        package mo

        import "testing"

        func TestBenchStateFlatMapValue(t *testing.T) {
            // first: value = st, newState = st + 10
            first := NewState(func(st int) (int, int) { return st, st + 10 })
            comp := first.FlatMap(func(a int) State[int, int] {
                // second observes the threaded state (st2) and the first value a.
                return NewState(func(st2 int) (int, int) { return a + st2, st2 + 1 })
            })
            v, st := comp.Run(3)
            // first: a=3, st2=13. second: value = 3+13 = 16, finalState = 14.
            if v != 16 {
                t.Fatalf("value = %d, want 16 (a=3 + threaded state 13)", v)
            }
            if st != 14 {
                t.Fatalf("final state = %d, want 14", st)
            }
        }
        """
        proc = _run_driver(
            "", "bench_state_flatmap_value_test.go", src,
            "TestBenchStateFlatMapValue",
        )
        assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"

    def test_eval_returns_only_value(self):
        """L2: Eval(initial) returns only the result value (discards final state)."""
        src = """
        package mo

        import "testing"

        func TestBenchStateEval(t *testing.T) {
            s := NewState(func(st int) (int, int) { return st * 2, st + 100 })
            got := s.Eval(4)
            // value = 8 (state would be 104, but Eval discards it).
            if got != 8 {
                t.Fatalf("Eval(4) = %d, want 8 (only the value)", got)
            }
        }
        """
        proc = _run_driver(
            "", "bench_state_eval_test.go", src, "TestBenchStateEval"
        )
        assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"

    def test_exec_returns_only_state(self):
        """L2: Exec(initial) returns only the final state (discards the value)."""
        src = """
        package mo

        import "testing"

        func TestBenchStateExec(t *testing.T) {
            s := NewState(func(st int) (int, int) { return st * 2, st + 100 })
            got := s.Exec(4)
            // finalState = 104 (value would be 8, but Exec discards it).
            if got != 104 {
                t.Fatalf("Exec(4) = %d, want 104 (only the final state)", got)
            }
        }
        """
        proc = _run_driver(
            "", "bench_state_exec_test.go", src, "TestBenchStateExec"
        )
        assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"

    def test_eval_exec_agree_with_run(self):
        """L2: For one computation+initial, (Eval, Exec) equals Run's (value, state).

        Catches an impl where Eval/Exec swap value/state or re-run with a
        different initial.
        """
        src = """
        package mo

        import "testing"

        func TestBenchStateEvalExecAgree(t *testing.T) {
            s := NewState(func(st int) (int, int) { return st + 7, st * 3 })
            v, st := s.Run(5)        // value = 12, state = 15
            if s.Eval(5) != v {
                t.Fatalf("Eval(5) = %d, want %d (== Run value)", s.Eval(5), v)
            }
            if s.Exec(5) != st {
                t.Fatalf("Exec(5) = %d, want %d (== Run state)", s.Exec(5), st)
            }
            // And they must not be the same number here, guarding a value/state mixup.
            if v == st {
                t.Fatalf("test precondition broken: value == state")
            }
        }
        """
        proc = _run_driver(
            "", "bench_state_evalexec_agree_test.go", src,
            "TestBenchStateEvalExecAgree",
        )
        assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"

    def test_composition_is_lazy(self):
        """L2: Map/FlatMap build a State without executing until a runner is called.

        Uses a captured counter incremented inside the underlying run func. After
        composing (no Run/Eval/Exec), the counter must still be 0; after exactly
        one Run, it must reflect one execution of each step.
        """
        src = """
        package mo

        import "testing"

        func TestBenchStateLazy(t *testing.T) {
            calls := 0
            base := NewState(func(st int) (int, int) {
                calls++
                return st, st + 1
            })

            // Build a composed computation but DO NOT run it yet.
            comp := base.
                Map(func(a int) int { return a }).
                FlatMap(func(a int) State[int, int] {
                    return base.Map(func(b int) int { return b })
                })

            if calls != 0 {
                t.Fatalf("composition was not lazy: calls = %d, want 0 before running", calls)
            }

            _, _ = comp.Run(0)
            // base runs twice (once in the Map chain, once inside FlatMap's State).
            if calls != 2 {
                t.Fatalf("after one Run, calls = %d, want 2", calls)
            }
        }
        """
        proc = _run_driver(
            "", "bench_state_lazy_test.go", src, "TestBenchStateLazy"
        )
        assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"

    def test_agent_state_suite_passes(self):
        """L2: the agent's own `go test ./... -run State` (acceptance cmd) passes.

        This is the doc's native acceptance command. It exercises state_test.go
        plus any *State* tests across the module and must be green.
        """
        proc = _run(
            ["go", "test", "-count=1", "-run", "State", "./..."], cwd=REPO_DIR
        )
        assert proc.returncode == 0, (
            f"go test ./... -run State failed:\n{proc.stdout}\n{proc.stderr}"
        )

    def test_existing_module_tests_still_pass(self):
        """L2: the change does not break the rest of the module's test suite."""
        proc = _run(["go", "test", "-count=1", "./..."], cwd=REPO_DIR)
        assert proc.returncode == 0, (
            f"go test ./... failed:\n{proc.stdout}\n{proc.stderr}"
        )
