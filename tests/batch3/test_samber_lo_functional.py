"""Benchmark test for skill `samber-lo-functional` (variant ext3).

Verifies the agent-built **inventory reconciliation engine** under
`examples/inventory` of the `github.com/samber/lo` module.

Task summary (from tasks/ext3/samber-lo-functional.md):
  Create `examples/inventory/reconcile.go` (package inventory) exporting:
    type Snapshot map[string]int
    type Diff struct {
        AddedSKUs     []string       // only in new, sorted ascending, non-nil
        RemovedSKUs   []string       // only in old, sorted ascending, non-nil
        ChangedQty    map[string]int // sku -> (new-old) for differing qty, non-nil
        UnchangedSKUs []string       // in both with equal qty, sorted ascending, non-nil
    }
    func Reconcile(oldSnap, newSnap Snapshot) Diff
  Rules: set membership for added/removed, signed delta (new-old) for changed,
  unchanged SKUs excluded from ChangedQty, all three slices sorted ascending and
  non-nil even when empty, ChangedQty non-nil even when empty, inputs not mutated.

Native acceptance command (driven by L1/L2):
    go test ./examples/inventory/ -run TestReconcile -count=1

Strategy for discriminative power: rather than trusting the agent's own
`reconcile_test.go`, the L2 cases write an INDEPENDENT external Go test file
(`package inventorydriver`) into a fresh sub-package directory under
examples/ and run it with the native `go test` toolchain. Each driver imports
`github.com/samber/lo/examples/inventory` and asserts on the real returned
`Diff` value. A naive solution (returns nil slices/maps, leaves unchanged SKUs
in ChangedQty, fails to sort, computes the delta in the wrong direction, or
mutates an input map) fails these drivers.
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
        """Create a fresh sub-package dir under examples/ containing only a
        driver test that imports the real `inventory` package. Returns the
        relative path for `go test ./<dir>/` and the absolute dir for cleanup.

        Placed under examples/ to stay inside the module tree. The directory
        holds only a *_test.go file (a test-only package is valid for go test).
        """
        name = "invverify_" + uuid.uuid4().hex[:10]
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
        'package inventorydriver\n\n'
        'import (\n'
        '\t"reflect"\n'
        '\t"testing"\n\n'
        '\tinventory "github.com/samber/lo/examples/inventory"\n'
        ')\n\n'
    )

    # ------------------------------------------------------------------ #
    # L1 — deliverables exist & are minimally well-formed
    # ------------------------------------------------------------------ #
    def test_reconcile_go_exists(self):
        """L1: examples/inventory/reconcile.go exists and declares package inventory."""
        p = os.path.join(self._repo(), "examples", "inventory", "reconcile.go")
        assert os.path.isfile(p), "examples/inventory/reconcile.go is missing"
        with open(p) as fh:
            head = fh.read(8000)
        assert "package inventory" in head, "reconcile.go must declare `package inventory`"

    def test_reconcile_test_go_exists(self):
        """L1: examples/inventory/reconcile_test.go exists (agent's own table-driven test)."""
        p = os.path.join(self._repo(), "examples", "inventory", "reconcile_test.go")
        assert os.path.isfile(p), "examples/inventory/reconcile_test.go is missing"
        with open(p) as fh:
            head = fh.read(8000)
        assert "package inventory" in head, "reconcile_test.go must declare `package inventory`"

    def test_package_compiles(self):
        """L1: the new package compiles via `go build`."""
        res = self._run_go(["go", "build", "./examples/inventory/"], timeout=300)
        assert res.returncode == 0, (
            "package github.com/samber/lo/examples/inventory failed to build:\n"
            + res.stdout + res.stderr
        )

    def test_agents_own_tests_pass(self):
        """L1/L2: the exact acceptance command passes.

        `go test ./examples/inventory/ -run TestReconcile -count=1`
        """
        res = self._run_go(
            ["go", "test", "./examples/inventory/", "-run", "TestReconcile", "-count=1"],
            timeout=300,
        )
        assert res.returncode == 0, (
            "acceptance command failed:\n" + res.stdout + res.stderr
        )

    # ------------------------------------------------------------------ #
    # L2 — independent dynamic execution against the real Reconcile
    # ------------------------------------------------------------------ #
    def test_added_and_removed_membership(self):
        """L2: SKUs only-in-new go to AddedSKUs, only-in-old go to RemovedSKUs."""
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	old := inventory.Snapshot{"keep": 1, "gone": 4}
	new := inventory.Snapshot{"keep": 1, "fresh": 9}
	d := inventory.Reconcile(old, new)
	if !reflect.DeepEqual(d.AddedSKUs, []string{"fresh"}) {
		t.Fatalf("AddedSKUs want [fresh] got %#v", d.AddedSKUs)
	}
	if !reflect.DeepEqual(d.RemovedSKUs, []string{"gone"}) {
		t.Fatalf("RemovedSKUs want [gone] got %#v", d.RemovedSKUs)
	}
	if !reflect.DeepEqual(d.UnchangedSKUs, []string{"keep"}) {
		t.Fatalf("UnchangedSKUs want [keep] got %#v", d.UnchangedSKUs)
	}
	if len(d.ChangedQty) != 0 {
		t.Fatalf("ChangedQty want empty got %#v", d.ChangedQty)
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_positive_delta(self):
        """L2: qty increase 5 -> 8 yields ChangedQty == +3 and no UnchangedSKUs."""
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	d := inventory.Reconcile(
		inventory.Snapshot{"sku": 5},
		inventory.Snapshot{"sku": 8},
	)
	if got, ok := d.ChangedQty["sku"]; !ok || got != 3 {
		t.Fatalf("ChangedQty[sku] want 3 got %d (ok=%v)", got, ok)
	}
	if len(d.UnchangedSKUs) != 0 {
		t.Fatalf("UnchangedSKUs must be empty, got %#v", d.UnchangedSKUs)
	}
	if len(d.AddedSKUs) != 0 || len(d.RemovedSKUs) != 0 {
		t.Fatalf("Added/Removed must be empty, got %#v / %#v", d.AddedSKUs, d.RemovedSKUs)
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_negative_delta_direction(self):
        """L2: qty decrease 8 -> 5 yields ChangedQty == -3 (delta = new - old).

        Pins the delta direction; a wrong-direction impl (old-new) would give +3
        and fail.
        """
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	d := inventory.Reconcile(
		inventory.Snapshot{"sku": 8},
		inventory.Snapshot{"sku": 5},
	)
	if got, ok := d.ChangedQty["sku"]; !ok || got != -3 {
		t.Fatalf("ChangedQty[sku] want -3 (new-old) got %d (ok=%v)", got, ok)
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_unchanged_excluded_from_changedqty(self):
        """L2: a SKU with identical qty appears in UnchangedSKUs and NOT in ChangedQty."""
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	d := inventory.Reconcile(
		inventory.Snapshot{"same": 7, "moved": 1},
		inventory.Snapshot{"same": 7, "moved": 4},
	)
	if _, ok := d.ChangedQty["same"]; ok {
		t.Fatalf("unchanged SKU 'same' must be absent from ChangedQty: %#v", d.ChangedQty)
	}
	if !reflect.DeepEqual(d.UnchangedSKUs, []string{"same"}) {
		t.Fatalf("UnchangedSKUs want [same] got %#v", d.UnchangedSKUs)
	}
	if got, ok := d.ChangedQty["moved"]; !ok || got != 3 {
		t.Fatalf("ChangedQty[moved] want 3 got %d (ok=%v)", got, ok)
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_all_slices_sorted_ascending(self):
        """L2: AddedSKUs, RemovedSKUs, UnchangedSKUs are each sorted ascending.

        Inputs are inserted in non-sorted order so an unsorted (map-iteration)
        impl is highly likely to fail.
        """
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	old := inventory.Snapshot{"d_un": 1, "b_un": 1, "z_rm": 1, "m_rm": 1}
	new := inventory.Snapshot{"d_un": 1, "b_un": 1, "y_add": 1, "a_add": 1}
	d := inventory.Reconcile(old, new)
	if !reflect.DeepEqual(d.AddedSKUs, []string{"a_add", "y_add"}) {
		t.Fatalf("AddedSKUs not sorted ascending: %#v", d.AddedSKUs)
	}
	if !reflect.DeepEqual(d.RemovedSKUs, []string{"m_rm", "z_rm"}) {
		t.Fatalf("RemovedSKUs not sorted ascending: %#v", d.RemovedSKUs)
	}
	if !reflect.DeepEqual(d.UnchangedSKUs, []string{"b_un", "d_un"}) {
		t.Fatalf("UnchangedSKUs not sorted ascending: %#v", d.UnchangedSKUs)
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_empty_inputs_nonnil_empty(self):
        """L2: two empty snapshots -> all slices non-nil & empty, ChangedQty non-nil & empty."""
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	d := inventory.Reconcile(inventory.Snapshot{}, inventory.Snapshot{})
	if d.AddedSKUs == nil {
		t.Fatalf("AddedSKUs must be non-nil for empty input")
	}
	if d.RemovedSKUs == nil {
		t.Fatalf("RemovedSKUs must be non-nil for empty input")
	}
	if d.UnchangedSKUs == nil {
		t.Fatalf("UnchangedSKUs must be non-nil for empty input")
	}
	if d.ChangedQty == nil {
		t.Fatalf("ChangedQty must be non-nil for empty input")
	}
	if len(d.AddedSKUs) != 0 || len(d.RemovedSKUs) != 0 ||
		len(d.UnchangedSKUs) != 0 || len(d.ChangedQty) != 0 {
		t.Fatalf("all outputs must be empty for empty input: %+v", d)
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_nonnil_when_only_one_category_populated(self):
        """L2: when only additions occur, the other slices/map are still non-nil & empty."""
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	d := inventory.Reconcile(inventory.Snapshot{}, inventory.Snapshot{"new1": 2, "new2": 3})
	if !reflect.DeepEqual(d.AddedSKUs, []string{"new1", "new2"}) {
		t.Fatalf("AddedSKUs want [new1 new2] got %#v", d.AddedSKUs)
	}
	if d.RemovedSKUs == nil || len(d.RemovedSKUs) != 0 {
		t.Fatalf("RemovedSKUs must be non-nil & empty, got %#v", d.RemovedSKUs)
	}
	if d.UnchangedSKUs == nil || len(d.UnchangedSKUs) != 0 {
		t.Fatalf("UnchangedSKUs must be non-nil & empty, got %#v", d.UnchangedSKUs)
	}
	if d.ChangedQty == nil || len(d.ChangedQty) != 0 {
		t.Fatalf("ChangedQty must be non-nil & empty, got %#v", d.ChangedQty)
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_inputs_not_mutated(self):
        """L2: Reconcile must not mutate either input map (keys or values)."""
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	old := inventory.Snapshot{"a": 1, "b": 2, "c": 3}
	new := inventory.Snapshot{"b": 5, "c": 3, "d": 9}
	oldCopy := inventory.Snapshot{"a": 1, "b": 2, "c": 3}
	newCopy := inventory.Snapshot{"b": 5, "c": 3, "d": 9}
	_ = inventory.Reconcile(old, new)
	if !reflect.DeepEqual(map[string]int(old), map[string]int(oldCopy)) {
		t.Fatalf("old snapshot mutated: %#v != %#v", old, oldCopy)
	}
	if !reflect.DeepEqual(map[string]int(new), map[string]int(newCopy)) {
		t.Fatalf("new snapshot mutated: %#v != %#v", new, newCopy)
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_zero_quantities_treated_as_membership_not_change(self):
        """L2: a SKU present in both with value 0 in both is Unchanged, not Changed.

        Guards against impls that conflate "value 0" / "key absent". The key
        exists in both maps with equal value, so it must be Unchanged.
        """
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	d := inventory.Reconcile(
		inventory.Snapshot{"z": 0, "p": 1},
		inventory.Snapshot{"z": 0, "p": 1},
	)
	if !reflect.DeepEqual(d.UnchangedSKUs, []string{"p", "z"}) {
		t.Fatalf("UnchangedSKUs want [p z] got %#v", d.UnchangedSKUs)
	}
	if len(d.ChangedQty) != 0 {
		t.Fatalf("ChangedQty must be empty, got %#v", d.ChangedQty)
	}
	if len(d.AddedSKUs) != 0 || len(d.RemovedSKUs) != 0 {
		t.Fatalf("Added/Removed must be empty, got %#v / %#v", d.AddedSKUs, d.RemovedSKUs)
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_combined_realistic_reconcile(self):
        """L2: end-to-end scenario exercising every category and rule at once."""
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	// added: x_new, a_new ; removed: q_old, c_old ;
	// changed: up (2->5 = +3), down (9->4 = -5) ;
	// unchanged: same1, same2
	old := inventory.Snapshot{
		"q_old": 3, "c_old": 7,
		"up": 2, "down": 9,
		"same1": 4, "same2": 8,
	}
	new := inventory.Snapshot{
		"x_new": 1, "a_new": 6,
		"up": 5, "down": 4,
		"same1": 4, "same2": 8,
	}
	d := inventory.Reconcile(old, new)

	if !reflect.DeepEqual(d.AddedSKUs, []string{"a_new", "x_new"}) {
		t.Fatalf("AddedSKUs want [a_new x_new] got %#v", d.AddedSKUs)
	}
	if !reflect.DeepEqual(d.RemovedSKUs, []string{"c_old", "q_old"}) {
		t.Fatalf("RemovedSKUs want [c_old q_old] got %#v", d.RemovedSKUs)
	}
	if !reflect.DeepEqual(d.UnchangedSKUs, []string{"same1", "same2"}) {
		t.Fatalf("UnchangedSKUs want [same1 same2] got %#v", d.UnchangedSKUs)
	}
	wantChanged := map[string]int{"up": 3, "down": -5}
	if !reflect.DeepEqual(d.ChangedQty, wantChanged) {
		t.Fatalf("ChangedQty want %#v got %#v", wantChanged, d.ChangedQty)
	}
	// unchanged SKUs must not leak into ChangedQty
	for _, k := range []string{"same1", "same2"} {
		if _, ok := d.ChangedQty[k]; ok {
			t.Fatalf("unchanged %q must not appear in ChangedQty", k)
		}
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr


if __name__ == "__main__":
    raise SystemExit(pytest.main([os.path.abspath(__file__), "-v", "--tb=short"]))
