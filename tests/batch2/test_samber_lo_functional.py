"""Benchmark test for skill `samber-lo-functional` (variant ext2).

Verifies the agent-built log-line batch dispatcher under `examples/logbatch`
of the `github.com/samber/lo` module.

The ext2 task asks for `examples/logbatch/batch.go` (package logbatch)
exporting the types `LogRecord{ID,Level,Msg}` and `Batch{Index,Records}`,
plus:

    func PrepareBatches(records []LogRecord, size int, keepLevels []string) ([]Batch, error)

with strict rules:
  * Level filtering: keep only records whose Level is in keepLevels
    (case-sensitive, exact). Empty keepLevels => no filtering.
  * Deduplication: first occurrence of each ID wins among retained records;
    later duplicates dropped; surviving order preserved.
  * Batching: surviving records split into consecutive batches of at most
    `size`; final batch may be smaller; Batch.Index == 0-based position.
  * Errors: size <= 0 -> (nil, non-nil error), no panic.
  * Zero survivors -> empty non-nil []Batch, nil error.
  * Input slice must not be mutated or reordered.

Discriminative strategy (mirrors the ext1 harness): rather than trusting the
agent's own `batch_test.go`, most L2 cases write an INDEPENDENT Go test file
(`package logbatchdriver`) into a fresh throwaway sub-package directory under
REPO_DIR and run it with the native `go test` toolchain. Each driver imports
`github.com/samber/lo/examples/logbatch` and asserts on the real returned
([]Batch, error). A naive solution (keeps duplicate IDs, mis-sizes the final
batch, ignores level filtering, panics on non-positive size, mutates input,
or returns nil on the empty-result path) fails these drivers.

Native acceptance command driven at L2:
    go test ./examples/logbatch/ -run TestPrepareBatches -count=1
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
        """Create a fresh test-only sub-package under examples/ containing only a
        driver test that imports the real `logbatch` package. Returns the
        `go test ./...`-style relative path and the absolute dir for cleanup.

        Placed inside the module tree so the import path resolves. Unique name
        avoids clashes; the dir holds only a *_test.go so go test treats it as a
        test-only package.
        """
        name = "logbatchverify_" + uuid.uuid4().hex[:10]
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
        'package logbatchdriver\n\n'
        'import (\n'
        '\t"testing"\n\n'
        '\tlogbatch "github.com/samber/lo/examples/logbatch"\n'
        ')\n\n'
    )

    # ------------------------------------------------------------------ #
    # L1 — deliverables exist & are minimally well-formed
    # ------------------------------------------------------------------ #
    def test_batch_go_exists(self):
        """L1: examples/logbatch/batch.go exists and declares package logbatch."""
        p = os.path.join(self._repo(), "examples", "logbatch", "batch.go")
        assert os.path.isfile(p), "examples/logbatch/batch.go is missing"
        with open(p) as fh:
            head = fh.read(8000)
        assert "package logbatch" in head, "batch.go must declare `package logbatch`"
        # The exported API must be present (not a hollow stub file).
        assert "func PrepareBatches" in head, "PrepareBatches must be defined in batch.go"

    def test_batch_test_go_exists(self):
        """L1: examples/logbatch/batch_test.go exists (agent's own table-driven test)."""
        p = os.path.join(self._repo(), "examples", "logbatch", "batch_test.go")
        assert os.path.isfile(p), "examples/logbatch/batch_test.go is missing"
        with open(p) as fh:
            head = fh.read(8000)
        assert "package logbatch" in head, "batch_test.go must declare `package logbatch`"

    def test_package_compiles(self):
        """L1: the new package compiles via `go build`."""
        res = self._run_go(["go", "build", "./examples/logbatch/"], timeout=300)
        assert res.returncode == 0, (
            "package github.com/samber/lo/examples/logbatch failed to build:\n"
            + res.stdout + res.stderr
        )

    def test_agents_own_tests_pass(self):
        """L1/L2: the exact acceptance command passes.

        `go test ./examples/logbatch/ -run TestPrepareBatches -count=1`
        """
        res = self._run_go(
            ["go", "test", "./examples/logbatch/", "-run", "TestPrepareBatches", "-count=1"],
            timeout=300,
        )
        assert res.returncode == 0, (
            "acceptance command failed:\n" + res.stdout + res.stderr
        )

    # ------------------------------------------------------------------ #
    # L2 — independent dynamic execution against real PrepareBatches
    # ------------------------------------------------------------------ #
    def test_chunk_sizing_and_index(self):
        """L2: 7 survivors, size 3 -> batches of 3,3,1 with sequential Index."""
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	recs := []logbatch.LogRecord{
		{ID: "a", Level: "info", Msg: "1"},
		{ID: "b", Level: "info", Msg: "2"},
		{ID: "c", Level: "info", Msg: "3"},
		{ID: "d", Level: "info", Msg: "4"},
		{ID: "e", Level: "info", Msg: "5"},
		{ID: "f", Level: "info", Msg: "6"},
		{ID: "g", Level: "info", Msg: "7"},
	}
	batches, err := logbatch.PrepareBatches(recs, 3, nil)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(batches) != 3 {
		t.Fatalf("want 3 batches, got %d: %+v", len(batches), batches)
	}
	wantSizes := []int{3, 3, 1}
	for i, b := range batches {
		if b.Index != i {
			t.Fatalf("batch %d has Index %d", i, b.Index)
		}
		if len(b.Records) != wantSizes[i] {
			t.Fatalf("batch %d want size %d got %d", i, wantSizes[i], len(b.Records))
		}
	}
	// order must be preserved end-to-end
	if batches[0].Records[0].ID != "a" || batches[2].Records[0].ID != "g" {
		t.Fatalf("order not preserved: %+v", batches)
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_exact_multiple_no_trailing_batch(self):
        """L2: when survivors are an exact multiple of size, no empty trailing batch."""
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	recs := []logbatch.LogRecord{
		{ID: "a", Level: "info"}, {ID: "b", Level: "info"},
		{ID: "c", Level: "info"}, {ID: "d", Level: "info"},
	}
	batches, err := logbatch.PrepareBatches(recs, 2, nil)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(batches) != 2 {
		t.Fatalf("4 records size 2 -> want 2 batches, got %d", len(batches))
	}
	if len(batches[0].Records) != 2 || len(batches[1].Records) != 2 {
		t.Fatalf("want batches 2,2 got %d,%d", len(batches[0].Records), len(batches[1].Records))
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_size_larger_than_input(self):
        """L2: size greater than survivor count -> single batch with all records."""
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	recs := []logbatch.LogRecord{
		{ID: "a", Level: "info"}, {ID: "b", Level: "info"},
	}
	batches, err := logbatch.PrepareBatches(recs, 100, nil)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(batches) != 1 {
		t.Fatalf("want 1 batch, got %d", len(batches))
	}
	if batches[0].Index != 0 || len(batches[0].Records) != 2 {
		t.Fatalf("want single batch idx 0 with 2 records, got %+v", batches[0])
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_level_filtering_case_sensitive_exact(self):
        """L2: only records whose Level is in keepLevels survive; match is exact/case-sensitive."""
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	recs := []logbatch.LogRecord{
		{ID: "1", Level: "info", Msg: "keep"},
		{ID: "2", Level: "debug", Msg: "drop"},
		{ID: "3", Level: "error", Msg: "keep"},
		{ID: "4", Level: "INFO", Msg: "drop-case"},  // wrong case -> excluded
		{ID: "5", Level: "warn", Msg: "drop"},
		{ID: "6", Level: "error", Msg: "keep"},
	}
	batches, err := logbatch.PrepareBatches(recs, 10, []string{"info", "error"})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	var got []string
	for _, b := range batches {
		for _, r := range b.Records {
			got = append(got, r.ID)
		}
	}
	want := []string{"1", "3", "6"}
	if len(got) != len(want) {
		t.Fatalf("level filter: want IDs %v got %v", want, got)
	}
	for i := range want {
		if got[i] != want[i] {
			t.Fatalf("level filter ordering: want %v got %v", want, got)
		}
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_empty_keeplevels_no_filtering(self):
        """L2: empty keepLevels means no level filtering -> every (deduped) record survives."""
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	recs := []logbatch.LogRecord{
		{ID: "1", Level: "info"},
		{ID: "2", Level: "debug"},
		{ID: "3", Level: "trace"},   // arbitrary level still kept
		{ID: "4", Level: "warn"},
	}
	batches, err := logbatch.PrepareBatches(recs, 10, []string{})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	total := 0
	for _, b := range batches {
		total += len(b.Records)
	}
	if total != 4 {
		t.Fatalf("empty keepLevels should keep all 4 records, got %d", total)
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_dedup_first_wins_order_preserved(self):
        """L2: duplicate IDs in retained stream -> first occurrence wins, order preserved."""
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	recs := []logbatch.LogRecord{
		{ID: "x", Level: "info", Msg: "first-x"},
		{ID: "y", Level: "info", Msg: "first-y"},
		{ID: "x", Level: "info", Msg: "dup-x"},   // dropped
		{ID: "z", Level: "info", Msg: "first-z"},
		{ID: "y", Level: "info", Msg: "dup-y"},   // dropped
	}
	batches, err := logbatch.PrepareBatches(recs, 10, nil)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	var ids, msgs []string
	for _, b := range batches {
		for _, r := range b.Records {
			ids = append(ids, r.ID)
			msgs = append(msgs, r.Msg)
		}
	}
	wantIDs := []string{"x", "y", "z"}
	wantMsgs := []string{"first-x", "first-y", "first-z"}
	if len(ids) != 3 {
		t.Fatalf("dedup: want 3 survivors got %d (%v)", len(ids), ids)
	}
	for i := range wantIDs {
		if ids[i] != wantIDs[i] {
			t.Fatalf("dedup order: want %v got %v", wantIDs, ids)
		}
		if msgs[i] != wantMsgs[i] {
			t.Fatalf("dedup first-wins: want %v got %v", wantMsgs, msgs)
		}
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_filter_then_dedup_then_batch_pipeline(self):
        """L2: filtering happens before dedup before batching; verify combined sizing."""
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	recs := []logbatch.LogRecord{
		{ID: "1", Level: "info"},
		{ID: "2", Level: "debug"},  // filtered out
		{ID: "1", Level: "info"},   // dup of survivor -> dropped
		{ID: "3", Level: "error"},
		{ID: "4", Level: "debug"},  // filtered out
		{ID: "5", Level: "info"},
		{ID: "3", Level: "error"},  // dup -> dropped
		{ID: "6", Level: "error"},
		{ID: "7", Level: "info"},
	}
	// survivors after filter(info,error)+dedup: 1,3,5,6,7  => 5 records
	batches, err := logbatch.PrepareBatches(recs, 2, []string{"info", "error"})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(batches) != 3 {
		t.Fatalf("5 survivors size 2 -> want 3 batches, got %d", len(batches))
	}
	sizes := []int{len(batches[0].Records), len(batches[1].Records), len(batches[2].Records)}
	if sizes[0] != 2 || sizes[1] != 2 || sizes[2] != 1 {
		t.Fatalf("want sizes 2,2,1 got %v", sizes)
	}
	var ids []string
	for _, b := range batches {
		for _, r := range b.Records {
			ids = append(ids, r.ID)
		}
	}
	want := []string{"1", "3", "5", "6", "7"}
	for i := range want {
		if ids[i] != want[i] {
			t.Fatalf("pipeline survivors: want %v got %v", want, ids)
		}
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_nonpositive_size_errors_no_panic(self):
        """L2: size <= 0 -> nil batches + non-nil error, never a panic."""
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	recs := []logbatch.LogRecord{{ID: "a", Level: "info"}}
	for _, size := range []int{0, -1, -5} {
		batches, err := logbatch.PrepareBatches(recs, size, nil)
		if err == nil {
			t.Fatalf("size=%d must return a non-nil error", size)
		}
		if batches != nil {
			t.Fatalf("size=%d must return nil batches, got %+v", size, batches)
		}
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_zero_survivors_nonnil_empty(self):
        """L2: zero surviving records -> empty NON-nil []Batch and nil error."""
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	// All records filtered out by keepLevels.
	recs := []logbatch.LogRecord{
		{ID: "1", Level: "debug"},
		{ID: "2", Level: "trace"},
	}
	batches, err := logbatch.PrepareBatches(recs, 3, []string{"info"})
	if err != nil {
		t.Fatalf("zero-survivor case must return nil error, got %v", err)
	}
	if batches == nil {
		t.Fatalf("zero-survivor case must return a non-nil empty slice")
	}
	if len(batches) != 0 {
		t.Fatalf("want empty batch slice, got %+v", batches)
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_empty_input_nonnil_empty(self):
        """L2: empty input slice -> empty non-nil []Batch, nil error."""
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	batches, err := logbatch.PrepareBatches([]logbatch.LogRecord{}, 5, nil)
	if err != nil {
		t.Fatalf("empty input must not error, got %v", err)
	}
	if batches == nil {
		t.Fatalf("empty input must return a non-nil empty slice")
	}
	if len(batches) != 0 {
		t.Fatalf("empty input must return zero batches, got %+v", batches)
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_input_not_mutated(self):
        """L2: PrepareBatches must not mutate or reorder the caller's input slice."""
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	recs := []logbatch.LogRecord{
		{ID: "b", Level: "info", Msg: "B"},
		{ID: "a", Level: "debug", Msg: "A"}, // filtered
		{ID: "b", Level: "info", Msg: "Bdup"},
		{ID: "c", Level: "error", Msg: "C"},
	}
	snap := make([]logbatch.LogRecord, len(recs))
	copy(snap, recs)
	_, err := logbatch.PrepareBatches(recs, 2, []string{"info", "error"})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(recs) != len(snap) {
		t.Fatalf("input length changed: %d != %d", len(recs), len(snap))
	}
	for i := range recs {
		if recs[i] != snap[i] {
			t.Fatalf("input mutated/reordered at %d: got %+v want %+v", i, recs[i], snap[i])
		}
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_records_independent_of_input_backing_array(self):
        """L2: mutating the returned batch records must not corrupt the input, and
        vice-versa — guards against handing back sub-slices that alias the caller's
        array in a way that lets the size<=0/dedup logic silently share state."""
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	recs := []logbatch.LogRecord{
		{ID: "1", Level: "info", Msg: "orig1"},
		{ID: "2", Level: "info", Msg: "orig2"},
		{ID: "3", Level: "info", Msg: "orig3"},
	}
	batches, err := logbatch.PrepareBatches(recs, 1, nil)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(batches) != 3 {
		t.Fatalf("want 3 batches, got %d", len(batches))
	}
	// Mutate every returned record's Msg.
	for bi := range batches {
		for ri := range batches[bi].Records {
			batches[bi].Records[ri].Msg = "TOUCHED"
		}
	}
	// Original input messages must be unchanged.
	want := []string{"orig1", "orig2", "orig3"}
	for i := range recs {
		if recs[i].Msg != want[i] {
			t.Fatalf("input record %d corrupted via aliased output: got %q want %q",
				i, recs[i].Msg, want[i])
		}
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr


if __name__ == "__main__":
    raise SystemExit(pytest.main([os.path.abspath(__file__), "-v", "--tb=short"]))
