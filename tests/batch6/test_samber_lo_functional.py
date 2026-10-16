"""Benchmark test for skill `samber-lo-functional` (variant ext6).

Verifies the agent-built time-series window aggregator under
`examples/window` of the `github.com/samber/lo` module.

The task asks for `examples/window/window.go` (package window) exporting
`Sample`, `WindowStat` and `func Aggregate(samples []Sample, width int64)
([]WindowStat, error)` with strict rules:
  * Each sample buckets into window Start = (TS/width)*width (integer floor).
  * Output has one WindowStat per NON-EMPTY window, sorted ascending by Start;
    empty intermediate windows are omitted.
  * Per-window Count/Sum/Min/Max with Mean = Sum/Count.
  * width <= 0 -> (nil, non-nil error), no panic.
  * Empty input -> empty NON-nil slice, nil error.
  * Single-sample window: Min==Max==Sum==Mean==value, Count==1.
  * Input slice must not be mutated or reordered.

Strategy for discriminative power: instead of trusting the agent's own
`window_test.go`, the L2 cases write INDEPENDENT Go test files (package
`windowdriver`) into fresh throwaway sub-package directories under REPO_DIR
and run them with the native `go test` toolchain. Each driver imports
`github.com/samber/lo/examples/window` and asserts on the real returned
`[]WindowStat`/error. A naive solution (assumes sorted input, emits empty
windows, miscomputes the floor boundary, mishandles min/max, panics on
non-positive width, or mutates the input) fails these drivers.

Native acceptance command driven by L2:
    go test ./examples/window/ -run TestAggregate -count=1
"""

import os
import shutil
import subprocess
import uuid

import pytest

REPO_DIR_DEFAULT = "/workspace/lo"


class TestSamberLoFunctional:
    REPO_DIR = "/workspace/lo"

    # ------------------------------------------------------------------ #
    # helpers
    # ------------------------------------------------------------------ #
    @classmethod
    def _repo(cls):
        return cls.REPO_DIR if os.path.isdir(cls.REPO_DIR) else REPO_DIR_DEFAULT

    @classmethod
    def _go_env(cls):
        env = dict(os.environ)
        env.setdefault("GOFLAGS", "-mod=mod")
        env.setdefault("GO111MODULE", "on")
        env.setdefault("CGO_ENABLED", "0")
        return env

    @classmethod
    def _run_go(cls, args, timeout=300, cwd=None):
        return subprocess.run(
            args,
            cwd=cwd or cls._repo(),
            capture_output=True,
            text=True,
            timeout=timeout,
            env=cls._go_env(),
        )

    @classmethod
    def _make_driver_pkg(cls, body_go):
        """Create a fresh throwaway sub-package dir under examples/ holding only
        a driver test that imports the real `window` package. Returns the
        `./examples/<name>/` path (for `go test`) and the absolute dir for
        cleanup. A test-only package directory is valid for `go test`.
        """
        name = "windowverify_" + uuid.uuid4().hex[:10]
        abs_dir = os.path.join(cls._repo(), "examples", name)
        os.makedirs(abs_dir, exist_ok=True)
        with open(os.path.join(abs_dir, "driver_test.go"), "w") as fh:
            fh.write(body_go)
        rel = "./examples/" + name + "/"
        return rel, abs_dir

    @classmethod
    def _run_driver(cls, body_go, run="TestDriver", timeout=300):
        rel, abs_dir = cls._make_driver_pkg(body_go)
        try:
            res = cls._run_go(
                ["go", "test", rel, "-run", run, "-count=1", "-v"],
                timeout=timeout,
            )
            return res
        finally:
            shutil.rmtree(abs_dir, ignore_errors=True)

    # Common Go preamble for drivers: import the real package + helpers.
    _IMPORT = (
        'package windowdriver\n\n'
        'import (\n'
        '\t"testing"\n\n'
        '\twindow "github.com/samber/lo/examples/window"\n'
        ')\n\n'
    )

    # ------------------------------------------------------------------ #
    # L1 — deliverables exist & are minimally well-formed
    # ------------------------------------------------------------------ #
    def test_window_go_exists(self):
        """L1: examples/window/window.go exists and declares package window."""
        p = os.path.join(self._repo(), "examples", "window", "window.go")
        assert os.path.isfile(p), "examples/window/window.go is missing"
        with open(p) as fh:
            head = fh.read(8000)
        assert "package window" in head, "window.go must declare `package window`"

    def test_window_test_go_exists(self):
        """L1: examples/window/window_test.go exists (agent's own table tests)."""
        p = os.path.join(self._repo(), "examples", "window", "window_test.go")
        assert os.path.isfile(p), "examples/window/window_test.go is missing"
        with open(p) as fh:
            head = fh.read(8000)
        assert "package window" in head, (
            "window_test.go must declare `package window`"
        )

    def test_package_compiles(self):
        """L1: the new package compiles via `go build`."""
        res = self._run_go(["go", "build", "./examples/window/"], timeout=300)
        assert res.returncode == 0, (
            "package github.com/samber/lo/examples/window failed to build:\n"
            + res.stdout + res.stderr
        )

    def test_agents_own_tests_pass(self):
        """L1/L2: the exact native acceptance command passes.

        `go test ./examples/window/ -run TestAggregate -count=1`
        """
        res = self._run_go(
            ["go", "test", "./examples/window/", "-run", "TestAggregate", "-count=1"],
            timeout=300,
        )
        assert res.returncode == 0, (
            "acceptance command failed:\n" + res.stdout + res.stderr
        )

    # ------------------------------------------------------------------ #
    # L2 — independent dynamic execution against real Aggregate
    # ------------------------------------------------------------------ #
    def test_floor_bucket_assignment(self):
        """L2: Start is floor(TS/width)*width, not the raw min TS in the window."""
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	// width 10. TS 13 -> window 10. TS 17 -> window 10. TS 25 -> window 20.
	out, err := window.Aggregate([]window.Sample{
		{TS: 17, Value: 1},
		{TS: 13, Value: 2},
		{TS: 25, Value: 3},
	}, 10)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(out) != 2 {
		t.Fatalf("want 2 windows, got %d: %+v", len(out), out)
	}
	if out[0].Start != 10 {
		t.Fatalf("first window Start want 10 (floor), got %d", out[0].Start)
	}
	if out[1].Start != 20 {
		t.Fatalf("second window Start want 20 (floor), got %d", out[1].Start)
	}
	if out[0].Count != 2 {
		t.Fatalf("window 10 Count want 2, got %d", out[0].Count)
	}
	if out[1].Count != 1 {
		t.Fatalf("window 20 Count want 1, got %d", out[1].Count)
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_out_of_order_input_sorted_ascending(self):
        """L2: shuffled input across 3 windows -> 3 entries sorted asc by Start."""
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	// width 100. windows 200, 0, 100 inserted out of order.
	out, err := window.Aggregate([]window.Sample{
		{TS: 250, Value: 1}, // win 200
		{TS: 5, Value: 2},   // win 0
		{TS: 150, Value: 3}, // win 100
	}, 100)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(out) != 3 {
		t.Fatalf("want 3 windows, got %d: %+v", len(out), out)
	}
	wantStarts := []int64{0, 100, 200}
	for i, w := range wantStarts {
		if out[i].Start != w {
			t.Fatalf("window %d Start want %d got %d (not sorted asc): %+v",
				i, w, out[i].Start, out)
		}
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_per_window_statistics(self):
        """L2: Count/Sum/Min/Max/Mean reflect every sample in a window."""
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	// width 10, all in window 0: values 4, -2, 10, 0.
	out, err := window.Aggregate([]window.Sample{
		{TS: 1, Value: 4},
		{TS: 2, Value: -2},
		{TS: 3, Value: 10},
		{TS: 9, Value: 0},
	}, 10)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(out) != 1 {
		t.Fatalf("want 1 window, got %d: %+v", len(out), out)
	}
	w := out[0]
	if w.Start != 0 {
		t.Fatalf("Start want 0 got %d", w.Start)
	}
	if w.Count != 4 {
		t.Fatalf("Count want 4 got %d", w.Count)
	}
	if w.Sum != 12 {
		t.Fatalf("Sum want 12 got %v", w.Sum)
	}
	if w.Min != -2 {
		t.Fatalf("Min want -2 got %v", w.Min)
	}
	if w.Max != 10 {
		t.Fatalf("Max want 10 got %v", w.Max)
	}
	if w.Mean != 3 {
		t.Fatalf("Mean want 3 (12/4) got %v", w.Mean)
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_min_max_not_seeded_to_zero(self):
        """L2: Min/Max must come from actual samples, not a 0 seed.

        A naive impl seeding Min/Max to 0.0 fails: all values are positive
        (Min should be 3, not 0) and another window has all-negative values
        (Max should be -1, not 0).
        """
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	out, err := window.Aggregate([]window.Sample{
		// window 0: all positive
		{TS: 0, Value: 5},
		{TS: 1, Value: 3},
		{TS: 2, Value: 8},
		// window 10: all negative
		{TS: 10, Value: -4},
		{TS: 11, Value: -1},
		{TS: 12, Value: -9},
	}, 10)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(out) != 2 {
		t.Fatalf("want 2 windows, got %d: %+v", len(out), out)
	}
	if out[0].Min != 3 {
		t.Fatalf("window0 Min want 3 (not 0 seed), got %v", out[0].Min)
	}
	if out[0].Max != 8 {
		t.Fatalf("window0 Max want 8, got %v", out[0].Max)
	}
	if out[1].Min != -9 {
		t.Fatalf("window10 Min want -9, got %v", out[1].Min)
	}
	if out[1].Max != -1 {
		t.Fatalf("window10 Max want -1 (not 0 seed), got %v", out[1].Max)
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_empty_windows_omitted(self):
        """L2: gaps between populated windows are NOT emitted as empty entries."""
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	// width 10. populated windows: 0 and 50. windows 10,20,30,40 are empty.
	out, err := window.Aggregate([]window.Sample{
		{TS: 3, Value: 1},
		{TS: 55, Value: 2},
	}, 10)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(out) != 2 {
		t.Fatalf("empty windows must be omitted: want 2 entries got %d: %+v",
			len(out), out)
	}
	if out[0].Start != 0 || out[1].Start != 50 {
		t.Fatalf("Starts want [0 50], got [%d %d]", out[0].Start, out[1].Start)
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_single_sample_window(self):
        """L2: a single-sample window: Min==Max==Sum==Mean==value, Count==1."""
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	out, err := window.Aggregate([]window.Sample{
		{TS: 42, Value: 7.5},
	}, 10)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(out) != 1 {
		t.Fatalf("want 1 window, got %d", len(out))
	}
	w := out[0]
	if w.Start != 40 {
		t.Fatalf("Start want 40 got %d", w.Start)
	}
	if w.Count != 1 {
		t.Fatalf("Count want 1 got %d", w.Count)
	}
	if w.Min != 7.5 || w.Max != 7.5 || w.Sum != 7.5 || w.Mean != 7.5 {
		t.Fatalf("single-sample stats want all 7.5, got Min=%v Max=%v Sum=%v Mean=%v",
			w.Min, w.Max, w.Sum, w.Mean)
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_width_zero_and_negative_error(self):
        """L2: width <= 0 returns (nil, non-nil error) without panicking."""
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	for _, w := range []int64{0, -1, -100} {
		out, err := window.Aggregate([]window.Sample{{TS: 1, Value: 1}}, w)
		if err == nil {
			t.Fatalf("width=%d: want non-nil error, got nil (out=%+v)", w, out)
		}
		if out != nil {
			t.Fatalf("width=%d: want nil result on error, got %+v", w, out)
		}
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_empty_input_nonnil_nil_error(self):
        """L2: empty input -> empty NON-nil slice and nil error."""
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	out, err := window.Aggregate([]window.Sample{}, 10)
	if err != nil {
		t.Fatalf("empty input: want nil error, got %v", err)
	}
	if out == nil {
		t.Fatalf("empty input: result slice must be non-nil")
	}
	if len(out) != 0 {
		t.Fatalf("empty input: result must be empty, got %+v", out)
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_input_not_mutated(self):
        """L2: Aggregate must not mutate or reorder the caller's input slice."""
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	in := []window.Sample{
		{TS: 250, Value: 1},
		{TS: 5, Value: 2},
		{TS: 150, Value: 3},
		{TS: 7, Value: 4},
	}
	snap := make([]window.Sample, len(in))
	copy(snap, in)
	_, err := window.Aggregate(in, 100)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(in) != len(snap) {
		t.Fatalf("input length changed: %d != %d", len(in), len(snap))
	}
	for i := range in {
		if in[i] != snap[i] {
			t.Fatalf("input mutated/reordered at %d: got %+v want %+v",
				i, in[i], snap[i])
		}
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_combined_realistic_aggregation(self):
        """L2: end-to-end shuffled multi-window scenario exercising every rule."""
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	// width 60.
	// window 0   (TS 0..59):   values 10, 2, 6        -> n3 sum18 min2 max10 mean6
	// window 120 (TS 120..179): value -5              -> single
	// window 60 is EMPTY -> must be omitted.
	in := []window.Sample{
		{TS: 175, Value: -5}, // win 120
		{TS: 30, Value: 2},   // win 0
		{TS: 0, Value: 10},   // win 0
		{TS: 59, Value: 6},   // win 0
	}
	snap := make([]window.Sample, len(in))
	copy(snap, in)

	out, err := window.Aggregate(in, 60)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(out) != 2 {
		t.Fatalf("want 2 windows (0,120 — 60 empty omitted), got %d: %+v",
			len(out), out)
	}
	if out[0].Start != 0 || out[1].Start != 120 {
		t.Fatalf("Starts want [0 120], got [%d %d]", out[0].Start, out[1].Start)
	}

	w0 := out[0]
	if w0.Count != 3 || w0.Sum != 18 || w0.Min != 2 || w0.Max != 10 || w0.Mean != 6 {
		t.Fatalf("window0 stats: Count=%d Sum=%v Min=%v Max=%v Mean=%v "+
			"(want 3,18,2,10,6)", w0.Count, w0.Sum, w0.Min, w0.Max, w0.Mean)
	}

	w1 := out[1]
	if w1.Count != 1 || w1.Sum != -5 || w1.Min != -5 || w1.Max != -5 || w1.Mean != -5 {
		t.Fatalf("window120 single-sample stats wrong: Count=%d Sum=%v Min=%v "+
			"Max=%v Mean=%v (want 1,-5,-5,-5,-5)",
			w1.Count, w1.Sum, w1.Min, w1.Max, w1.Mean)
	}

	// immutability
	for i := range in {
		if in[i] != snap[i] {
			t.Fatalf("input mutated at %d: got %+v want %+v", i, in[i], snap[i])
		}
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr


if __name__ == "__main__":
    raise SystemExit(pytest.main([os.path.abspath(__file__), "-v", "--tb=short"]))
