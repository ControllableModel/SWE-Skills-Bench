"""Benchmark test for skill `samber-lo-functional`.

Verifies the agent-built sales aggregation report generator under
`examples/sales` of the `github.com/samber/lo` module.

The task asks for `examples/sales/report.go` (package sales) exporting
`LineItem`, `RegionSummary`, `Report` and `func BuildReport(items []LineItem) Report`
with strict rules for refund handling, distinct order counting, region
grouping/sorting, product tie-break, and input immutability.

Strategy for discriminative power: rather than trusting the agent's own
`report_test.go`, most L2 cases write an INDEPENDENT Go test file (external
`package sales_test`) into a fresh sub-package directory under REPO_DIR and
run it with the native `go test` toolchain. Each driver imports
`github.com/samber/lo/examples/sales` and asserts on the real returned
`Report` struct. A naive solution (ignores refunds, double-counts orders,
skips tie-break, fails to sort, mutates input) fails these drivers.
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
        # Keep module cache local & avoid network where possible.
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
        """Create a fresh sub-package dir under examples/sales containing only a
        driver test that imports the real `sales` package. Returns the relative
        import-ish path (for `go test ./<dir>/`) and absolute dir for cleanup.

        We place it under examples/ to stay inside the module tree. The package
        name is unique to avoid clashes and is its own directory so it has no
        non-test source (go test allows a test-only package).
        """
        name = "salesverify_" + uuid.uuid4().hex[:10]
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

    # Common Go preamble for drivers: import the real package.
    _IMPORT = (
        'package salesdriver\n\n'
        'import (\n'
        '\t"testing"\n\n'
        '\tsales "github.com/samber/lo/examples/sales"\n'
        ')\n\n'
    )

    # ------------------------------------------------------------------ #
    # L1 — deliverables exist & are minimally well-formed
    # ------------------------------------------------------------------ #
    def test_report_go_exists(self):
        """L1: examples/sales/report.go exists and declares package sales."""
        p = os.path.join(self._repo(), "examples", "sales", "report.go")
        assert os.path.isfile(p), "examples/sales/report.go is missing"
        with open(p) as fh:
            head = fh.read(4000)
        assert "package sales" in head, "report.go must declare `package sales`"

    def test_report_test_go_exists(self):
        """L1: examples/sales/report_test.go exists (agent's own table-driven test)."""
        p = os.path.join(self._repo(), "examples", "sales", "report_test.go")
        assert os.path.isfile(p), "examples/sales/report_test.go is missing"
        with open(p) as fh:
            head = fh.read(4000)
        assert "package sales" in head, "report_test.go must declare `package sales`"

    def test_package_compiles(self):
        """L1: the new package compiles via `go build`."""
        res = self._run_go(["go", "build", "./examples/sales/"], timeout=300)
        assert res.returncode == 0, (
            "package github.com/samber/lo/examples/sales failed to build:\n"
            + res.stdout + res.stderr
        )

    def test_agents_own_tests_pass(self):
        """L1/L2: the exact acceptance command passes.

        `go test ./examples/sales/ -run TestBuildReport -count=1`
        """
        res = self._run_go(
            ["go", "test", "./examples/sales/", "-run", "TestBuildReport", "-count=1"],
            timeout=300,
        )
        assert res.returncode == 0, (
            "acceptance command failed:\n" + res.stdout + res.stderr
        )

    # ------------------------------------------------------------------ #
    # L2 — independent dynamic execution against real BuildReport
    # ------------------------------------------------------------------ #
    def test_multi_region_sorting(self):
        """L2: two regions produce one summary each, sorted ascending by region."""
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	items := []sales.LineItem{
		{OrderID: "o1", Region: "West", Product: "A", Quantity: 2, Unit: 10},
		{OrderID: "o2", Region: "East", Product: "B", Quantity: 1, Unit: 5},
		{OrderID: "o3", Region: "West", Product: "A", Quantity: 1, Unit: 10},
	}
	r := sales.BuildReport(items)
	if len(r.Regions) != 2 {
		t.Fatalf("want 2 regions, got %d (%+v)", len(r.Regions), r.Regions)
	}
	if r.Regions[0].Region != "East" || r.Regions[1].Region != "West" {
		t.Fatalf("regions not sorted ascending: %+v", r.Regions)
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_revenue_units_and_grandtotal(self):
        """L2: Revenue=sum(Qty*Unit), UnitsSold=sum(Qty), GrandTotal=sum(Revenue)."""
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	items := []sales.LineItem{
		{OrderID: "o1", Region: "East", Product: "A", Quantity: 3, Unit: 4},  // 12, 3u
		{OrderID: "o2", Region: "East", Product: "B", Quantity: 2, Unit: 5},  // 10, 2u
		{OrderID: "o3", Region: "West", Product: "C", Quantity: 1, Unit: 7.5},// 7.5,1u
	}
	r := sales.BuildReport(items)
	var east, west *sales.RegionSummary
	for i := range r.Regions {
		switch r.Regions[i].Region {
		case "East":
			east = &r.Regions[i]
		case "West":
			west = &r.Regions[i]
		}
	}
	if east == nil || west == nil {
		t.Fatalf("missing regions: %+v", r.Regions)
	}
	if east.Revenue != 22 {
		t.Fatalf("East revenue want 22 got %v", east.Revenue)
	}
	if east.UnitsSold != 5 {
		t.Fatalf("East units want 5 got %d", east.UnitsSold)
	}
	if west.Revenue != 7.5 {
		t.Fatalf("West revenue want 7.5 got %v", west.Revenue)
	}
	if r.GrandTotal != 29.5 {
		t.Fatalf("GrandTotal want 29.5 got %v", r.GrandTotal)
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_distinct_order_count(self):
        """L2: same OrderID split across multiple line-items counts once."""
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	items := []sales.LineItem{
		{OrderID: "o1", Region: "East", Product: "A", Quantity: 1, Unit: 1},
		{OrderID: "o1", Region: "East", Product: "B", Quantity: 1, Unit: 1},
		{OrderID: "o1", Region: "East", Product: "C", Quantity: 1, Unit: 1},
		{OrderID: "o2", Region: "East", Product: "A", Quantity: 1, Unit: 1},
	}
	r := sales.BuildReport(items)
	if len(r.Regions) != 1 {
		t.Fatalf("want 1 region, got %d", len(r.Regions))
	}
	if r.Regions[0].OrderCount != 2 {
		t.Fatalf("distinct OrderCount want 2 got %d", r.Regions[0].OrderCount)
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_refund_excludes_revenue_units(self):
        """L2: refunded line-items contribute nothing to UnitsSold/Revenue/GrandTotal."""
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	items := []sales.LineItem{
		{OrderID: "o1", Region: "East", Product: "A", Quantity: 5, Unit: 2}, // paid: 10,5u
		{OrderID: "o1", Region: "East", Product: "A", Quantity: 9, Unit: 2, Refunded: true}, // ignored
	}
	r := sales.BuildReport(items)
	if len(r.Regions) != 1 {
		t.Fatalf("want 1 region, got %d", len(r.Regions))
	}
	rs := r.Regions[0]
	if rs.UnitsSold != 5 {
		t.Fatalf("UnitsSold want 5 (refund excluded) got %d", rs.UnitsSold)
	}
	if rs.Revenue != 10 {
		t.Fatalf("Revenue want 10 (refund excluded) got %v", rs.Revenue)
	}
	if r.GrandTotal != 10 {
		t.Fatalf("GrandTotal want 10 got %v", r.GrandTotal)
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_all_refunded_region_omitted(self):
        """L2: a region whose every line-item is refunded must not appear at all."""
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	items := []sales.LineItem{
		{OrderID: "o1", Region: "Ghost", Product: "A", Quantity: 3, Unit: 9, Refunded: true},
		{OrderID: "o2", Region: "Ghost", Product: "B", Quantity: 1, Unit: 9, Refunded: true},
		{OrderID: "o3", Region: "Live", Product: "C", Quantity: 1, Unit: 4},
	}
	r := sales.BuildReport(items)
	for _, rs := range r.Regions {
		if rs.Region == "Ghost" {
			t.Fatalf("all-refunded region 'Ghost' must be omitted: %+v", r.Regions)
		}
	}
	if len(r.Regions) != 1 || r.Regions[0].Region != "Live" {
		t.Fatalf("want only Live region, got %+v", r.Regions)
	}
	if r.GrandTotal != 4 {
		t.Fatalf("GrandTotal want 4 got %v", r.GrandTotal)
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_refunded_order_still_counts_when_order_has_paid(self):
        """L2: a refunded item under an order that also has a paid item still
        counts toward OrderCount; refunded amounts excluded from revenue/units."""
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	items := []sales.LineItem{
		// o1: one paid + one refunded in same region -> counts once, paid only
		{OrderID: "o1", Region: "East", Product: "A", Quantity: 2, Unit: 3}, // 6, 2u
		{OrderID: "o1", Region: "East", Product: "A", Quantity: 10, Unit: 3, Refunded: true},
		// o2: fully refunded only -> must NOT count toward OrderCount
		{OrderID: "o2", Region: "East", Product: "B", Quantity: 1, Unit: 3, Refunded: true},
		// o3: paid -> counts
		{OrderID: "o3", Region: "East", Product: "A", Quantity: 1, Unit: 3}, // 3, 1u
	}
	r := sales.BuildReport(items)
	if len(r.Regions) != 1 {
		t.Fatalf("want 1 region, got %d", len(r.Regions))
	}
	rs := r.Regions[0]
	if rs.OrderCount != 2 {
		t.Fatalf("OrderCount want 2 (o1,o3; o2 fully refunded excluded) got %d", rs.OrderCount)
	}
	if rs.UnitsSold != 3 {
		t.Fatalf("UnitsSold want 3 got %d", rs.UnitsSold)
	}
	if rs.Revenue != 9 {
		t.Fatalf("Revenue want 9 got %v", rs.Revenue)
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_top_product_by_units(self):
        """L2: TopProduct is the product with greatest total UnitsSold (non-refunded)."""
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	items := []sales.LineItem{
		{OrderID: "o1", Region: "East", Product: "Widget", Quantity: 1, Unit: 100}, // high revenue, low units
		{OrderID: "o2", Region: "East", Product: "Gadget", Quantity: 7, Unit: 1},   // most units
		{OrderID: "o3", Region: "East", Product: "Gadget", Quantity: 2, Unit: 1},   // gadget total 9 units
		{OrderID: "o4", Region: "East", Product: "Gizmo", Quantity: 50, Unit: 1, Refunded: true}, // ignored
	}
	r := sales.BuildReport(items)
	if len(r.Regions) != 1 {
		t.Fatalf("want 1 region, got %d", len(r.Regions))
	}
	if r.Regions[0].TopProduct != "Gadget" {
		t.Fatalf("TopProduct want Gadget (9 units) got %q", r.Regions[0].TopProduct)
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_top_product_tie_break_lexicographic(self):
        """L2: on a units tie, TopProduct resolves to the lexicographically smaller name."""
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	// Zebra and Apple each total 4 units. Apple is lexicographically smaller.
	// Insert Zebra first so a naive "first seen wins" impl would pick Zebra.
	items := []sales.LineItem{
		{OrderID: "o1", Region: "East", Product: "Zebra", Quantity: 4, Unit: 1},
		{OrderID: "o2", Region: "East", Product: "Apple", Quantity: 1, Unit: 1},
		{OrderID: "o3", Region: "East", Product: "Apple", Quantity: 3, Unit: 1},
	}
	r := sales.BuildReport(items)
	if len(r.Regions) != 1 {
		t.Fatalf("want 1 region, got %d", len(r.Regions))
	}
	if r.Regions[0].TopProduct != "Apple" {
		t.Fatalf("tie-break: TopProduct want Apple (lexicographically smaller) got %q",
			r.Regions[0].TopProduct)
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_input_not_mutated(self):
        """L2: BuildReport must not mutate or reorder the caller's input slice."""
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	items := []sales.LineItem{
		{OrderID: "o3", Region: "West", Product: "C", Quantity: 1, Unit: 2},
		{OrderID: "o1", Region: "East", Product: "A", Quantity: 5, Unit: 3, Refunded: true},
		{OrderID: "o2", Region: "East", Product: "B", Quantity: 2, Unit: 4},
	}
	// snapshot
	snap := make([]sales.LineItem, len(items))
	copy(snap, items)
	_ = sales.BuildReport(items)
	if len(items) != len(snap) {
		t.Fatalf("input length changed: %d != %d", len(items), len(snap))
	}
	for i := range items {
		if items[i] != snap[i] {
			t.Fatalf("input mutated/reordered at %d: got %+v want %+v", i, items[i], snap[i])
		}
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_empty_input_nonnil_regions(self):
        """L2: empty input -> empty non-nil Regions and GrandTotal == 0."""
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	r := sales.BuildReport([]sales.LineItem{})
	if r.Regions == nil {
		t.Fatalf("Regions must be non-nil for empty input")
	}
	if len(r.Regions) != 0 {
		t.Fatalf("Regions must be empty for empty input, got %+v", r.Regions)
	}
	if r.GrandTotal != 0 {
		t.Fatalf("GrandTotal must be 0 for empty input, got %v", r.GrandTotal)
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_fully_refunded_input_nonnil_empty_regions(self):
        """L2: input that is entirely refunded -> empty non-nil Regions, GrandTotal 0."""
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	items := []sales.LineItem{
		{OrderID: "o1", Region: "East", Product: "A", Quantity: 1, Unit: 9, Refunded: true},
		{OrderID: "o2", Region: "West", Product: "B", Quantity: 2, Unit: 9, Refunded: true},
	}
	r := sales.BuildReport(items)
	if r.Regions == nil {
		t.Fatalf("Regions must be non-nil")
	}
	if len(r.Regions) != 0 {
		t.Fatalf("all-refunded input must yield empty Regions, got %+v", r.Regions)
	}
	if r.GrandTotal != 0 {
		t.Fatalf("GrandTotal want 0 got %v", r.GrandTotal)
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_combined_realistic_report(self):
        """L2: end-to-end multi-region scenario exercising every rule at once."""
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	items := []sales.LineItem{
		// West region
		{OrderID: "w1", Region: "West", Product: "Bolt", Quantity: 3, Unit: 2},   // 6, 3u
		{OrderID: "w1", Region: "West", Product: "Nut", Quantity: 5, Unit: 1},    // same order, 5, 5u
		{OrderID: "w2", Region: "West", Product: "Bolt", Quantity: 2, Unit: 2, Refunded: true}, // ignored amounts
		{OrderID: "w3", Region: "West", Product: "Nut", Quantity: 5, Unit: 1},    // 5, 5u -> Nut total 10u
		// North region (all refunded -> omitted)
		{OrderID: "n1", Region: "North", Product: "X", Quantity: 9, Unit: 9, Refunded: true},
		// East region
		{OrderID: "e1", Region: "East", Product: "Alpha", Quantity: 2, Unit: 5},  // 10, 2u
		{OrderID: "e2", Region: "East", Product: "Beta", Quantity: 2, Unit: 5},   // 10, 2u  (tie on units)
	}
	r := sales.BuildReport(items)

	// North omitted; only East, West, sorted ascending.
	if len(r.Regions) != 2 {
		t.Fatalf("want 2 regions (East,West), got %d: %+v", len(r.Regions), r.Regions)
	}
	if r.Regions[0].Region != "East" || r.Regions[1].Region != "West" {
		t.Fatalf("regions not sorted: %+v", r.Regions)
	}

	east := r.Regions[0]
	west := r.Regions[1]

	// East: 2 orders, 4 units, revenue 20, tie Alpha/Beta -> Alpha.
	if east.OrderCount != 2 {
		t.Fatalf("East OrderCount want 2 got %d", east.OrderCount)
	}
	if east.UnitsSold != 4 {
		t.Fatalf("East UnitsSold want 4 got %d", east.UnitsSold)
	}
	if east.Revenue != 20 {
		t.Fatalf("East Revenue want 20 got %v", east.Revenue)
	}
	if east.TopProduct != "Alpha" {
		t.Fatalf("East TopProduct tie want Alpha got %q", east.TopProduct)
	}

	// West: distinct orders w1,w3 -> 2 (w2 fully refunded excluded).
	if west.OrderCount != 2 {
		t.Fatalf("West OrderCount want 2 got %d", west.OrderCount)
	}
	// units: Bolt 3 + Nut 10 = 13 ; revenue: 6 + 5 + 5 = 16
	if west.UnitsSold != 13 {
		t.Fatalf("West UnitsSold want 13 got %d", west.UnitsSold)
	}
	if west.Revenue != 16 {
		t.Fatalf("West Revenue want 16 got %v", west.Revenue)
	}
	if west.TopProduct != "Nut" {
		t.Fatalf("West TopProduct want Nut (10u) got %q", west.TopProduct)
	}

	// GrandTotal = 20 + 16 = 36 (North contributes nothing).
	if r.GrandTotal != 36 {
		t.Fatalf("GrandTotal want 36 got %v", r.GrandTotal)
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr


if __name__ == "__main__":
    raise SystemExit(pytest.main([os.path.abspath(__file__), "-v", "--tb=short"]))
