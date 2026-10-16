"""Benchmark test for skill `samber-lo-functional` (variant ext10).

Verifies the agent-built shopping-cart pricing calculator under
`examples/cart` of the `github.com/samber/lo` module.

The task asks for `examples/cart/cart.go` (package cart) exporting
`CartLine`, `PercentOff`, `LineTotal`, `Receipt`, and
`func Price(lines []CartLine, discounts PercentOff) (Receipt, error)`
with strict rules:
  - consolidate lines sharing a SKU (summed Quantity);
  - error (non-panic) on conflicting UnitPrice for one SKU;
  - SKU with consolidated Quantity 0 omitted, contributes nothing;
  - Discount = (Gross*pct)/100 floor-division, applied to the
    *consolidated* gross (not per-line); Net = Gross - Discount;
  - error on a discount percent outside [0,100];
  - Lines sorted ascending by SKU, non-nil even when empty;
  - NetTotal = sum of Net;
  - Price must not mutate the caller's lines slice or discounts map.

Strategy for discriminative power: rather than trusting the agent's own
`cart_test.go`, the L2 cases write an INDEPENDENT external Go test
(`package cartdriver`) into a fresh sub-package directory under REPO_DIR
and run it with the native `go test` toolchain. Each driver imports
`github.com/samber/lo/examples/cart` and asserts on the real returned
`Receipt`/error. A naive solution (discounts per-line, rounds the wrong
way, keeps zero-quantity SKUs, fails to sort, ignores conflicting unit
prices or out-of-range percents, or mutates input) fails these drivers.

The L1/acceptance case drives exactly the doc's native command:
    go test ./examples/cart/ -run TestPrice -count=1
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
        driver test that imports the real `cart` package. Returns the relative
        path (for `go test ./<dir>/`) and absolute dir for cleanup.
        """
        name = "cartverify_" + uuid.uuid4().hex[:10]
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

    # Common Go preamble for drivers: import the real package + sort/reflect.
    _IMPORT = (
        'package cartdriver\n\n'
        'import (\n'
        '\t"testing"\n\n'
        '\tcart "github.com/samber/lo/examples/cart"\n'
        ')\n\n'
    )

    # ------------------------------------------------------------------ #
    # L1 — deliverables exist & are minimally well-formed
    # ------------------------------------------------------------------ #
    def test_cart_go_exists(self):
        """L1: examples/cart/cart.go exists and declares package cart."""
        p = os.path.join(self._repo(), "examples", "cart", "cart.go")
        assert os.path.isfile(p), "examples/cart/cart.go is missing"
        with open(p) as fh:
            head = fh.read(8000)
        assert "package cart" in head, "cart.go must declare `package cart`"
        # Sanity: the exported Price function must be declared somewhere.
        assert "func Price(" in head, "cart.go must declare `func Price(`"

    def test_cart_test_go_exists(self):
        """L1: examples/cart/cart_test.go exists (agent's own table-driven test)."""
        p = os.path.join(self._repo(), "examples", "cart", "cart_test.go")
        assert os.path.isfile(p), "examples/cart/cart_test.go is missing"
        with open(p) as fh:
            head = fh.read(8000)
        assert "package cart" in head, "cart_test.go must declare `package cart`"

    def test_package_compiles(self):
        """L1: the new package compiles via `go build`."""
        res = self._run_go(["go", "build", "./examples/cart/"], timeout=300)
        assert res.returncode == 0, (
            "package github.com/samber/lo/examples/cart failed to build:\n"
            + res.stdout + res.stderr
        )

    def test_agents_own_tests_pass(self):
        """L1/L2: the exact acceptance command passes.

        `go test ./examples/cart/ -run TestPrice -count=1`
        """
        res = self._run_go(
            ["go", "test", "./examples/cart/", "-run", "TestPrice", "-count=1"],
            timeout=300,
        )
        assert res.returncode == 0, (
            "acceptance command failed:\n" + res.stdout + res.stderr
        )

    # ------------------------------------------------------------------ #
    # L2 — independent dynamic execution against real Price()
    # ------------------------------------------------------------------ #
    def test_consolidation_sums_quantity(self):
        """L2: two lines sharing a SKU merge into one LineTotal with summed Quantity."""
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	lines := []cart.CartLine{
		{SKU: "A", UnitPrice: 100, Quantity: 2},
		{SKU: "A", UnitPrice: 100, Quantity: 3},
	}
	r, err := cart.Price(lines, cart.PercentOff{})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(r.Lines) != 1 {
		t.Fatalf("want 1 consolidated line, got %d (%+v)", len(r.Lines), r.Lines)
	}
	lt := r.Lines[0]
	if lt.SKU != "A" {
		t.Fatalf("SKU want A got %q", lt.SKU)
	}
	if lt.Quantity != 5 {
		t.Fatalf("consolidated Quantity want 5 got %d", lt.Quantity)
	}
	if lt.Gross != 500 {
		t.Fatalf("Gross want 500 got %d", lt.Gross)
	}
	if lt.Net != 500 {
		t.Fatalf("Net want 500 (no discount) got %d", lt.Net)
	}
	if r.NetTotal != 500 {
		t.Fatalf("NetTotal want 500 got %d", r.NetTotal)
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_simple_percent_discount(self):
        """L2: 25% discount on gross 1000 -> Discount 250, Net 750."""
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	lines := []cart.CartLine{
		{SKU: "X", UnitPrice: 250, Quantity: 4}, // gross 1000
	}
	r, err := cart.Price(lines, cart.PercentOff{"X": 25})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(r.Lines) != 1 {
		t.Fatalf("want 1 line, got %d", len(r.Lines))
	}
	lt := r.Lines[0]
	if lt.Gross != 1000 {
		t.Fatalf("Gross want 1000 got %d", lt.Gross)
	}
	if lt.Discount != 250 {
		t.Fatalf("Discount want 250 got %d", lt.Discount)
	}
	if lt.Net != 750 {
		t.Fatalf("Net want 750 got %d", lt.Net)
	}
	if r.NetTotal != 750 {
		t.Fatalf("NetTotal want 750 got %d", r.NetTotal)
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_discount_floor_rounding(self):
        """L2: 33% of gross 1000 floor-rounds to Discount 330 (not 330.0 ceil/round)."""
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	// 33% of 1000 = 330 exactly; use a non-divisible case too.
	lines := []cart.CartLine{
		{SKU: "P", UnitPrice: 1000, Quantity: 1}, // gross 1000
	}
	r, err := cart.Price(lines, cart.PercentOff{"P": 33})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if r.Lines[0].Discount != 330 {
		t.Fatalf("33%% of 1000 want Discount 330 got %d", r.Lines[0].Discount)
	}
	if r.Lines[0].Net != 670 {
		t.Fatalf("Net want 670 got %d", r.Lines[0].Net)
	}

	// Non-divisible: 33% of 1001 = 330.33 -> floor 330.
	lines2 := []cart.CartLine{{SKU: "Q", UnitPrice: 1001, Quantity: 1}}
	r2, err := cart.Price(lines2, cart.PercentOff{"Q": 33})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if r2.Lines[0].Discount != 330 {
		t.Fatalf("floor(33%% of 1001) want 330 got %d", r2.Lines[0].Discount)
	}
	if r2.Lines[0].Net != 671 {
		t.Fatalf("Net want 671 got %d", r2.Lines[0].Net)
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_discount_on_consolidated_gross_not_per_line(self):
        """L2: discount is applied to the summed gross, not per-line.

        Per-line floor rounding would give a different (larger) total discount
        than rounding once on the consolidated gross, so a per-line naive
        implementation fails this case.
        """
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	// Two lines, same SKU, each gross 50 -> consolidated gross 100.
	// 33% on consolidated 100 = floor(33) = 33.
	// A per-line impl: floor(33% of 50)=16 twice = 32 (WRONG).
	lines := []cart.CartLine{
		{SKU: "Z", UnitPrice: 50, Quantity: 1},
		{SKU: "Z", UnitPrice: 50, Quantity: 1},
	}
	r, err := cart.Price(lines, cart.PercentOff{"Z": 33})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(r.Lines) != 1 {
		t.Fatalf("want 1 consolidated line, got %d", len(r.Lines))
	}
	lt := r.Lines[0]
	if lt.Gross != 100 {
		t.Fatalf("consolidated Gross want 100 got %d", lt.Gross)
	}
	if lt.Discount != 33 {
		t.Fatalf("discount on consolidated gross want 33 (per-line would be 32) got %d", lt.Discount)
	}
	if lt.Net != 67 {
		t.Fatalf("Net want 67 got %d", lt.Net)
	}
	if r.NetTotal != 67 {
		t.Fatalf("NetTotal want 67 got %d", r.NetTotal)
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_zero_quantity_omitted(self):
        """L2: a SKU whose consolidated quantity is 0 is omitted and adds nothing."""
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	lines := []cart.CartLine{
		{SKU: "Gone", UnitPrice: 999, Quantity: 0},
		{SKU: "Keep", UnitPrice: 10, Quantity: 2}, // gross 20
	}
	r, err := cart.Price(lines, cart.PercentOff{})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	for _, lt := range r.Lines {
		if lt.SKU == "Gone" {
			t.Fatalf("zero-quantity SKU must be omitted: %+v", r.Lines)
		}
	}
	if len(r.Lines) != 1 || r.Lines[0].SKU != "Keep" {
		t.Fatalf("want only Keep line, got %+v", r.Lines)
	}
	if r.NetTotal != 20 {
		t.Fatalf("NetTotal want 20 got %d", r.NetTotal)
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_zero_quantity_via_cancellation(self):
        """L2: lines for one SKU summing to 0 (e.g. +3 and -3 are not allowed; use 0+0)
        consolidate to 0 and are omitted. Quantities are non-negative, so we use
        multiple zero-qty lines to force consolidated 0."""
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	lines := []cart.CartLine{
		{SKU: "A", UnitPrice: 5, Quantity: 0},
		{SKU: "A", UnitPrice: 5, Quantity: 0},
		{SKU: "B", UnitPrice: 7, Quantity: 1},
	}
	r, err := cart.Price(lines, cart.PercentOff{})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(r.Lines) != 1 || r.Lines[0].SKU != "B" {
		t.Fatalf("want only B, got %+v", r.Lines)
	}
	if r.NetTotal != 7 {
		t.Fatalf("NetTotal want 7 got %d", r.NetTotal)
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_ascending_sku_sorting(self):
        """L2: Lines are sorted ascending by SKU regardless of input order."""
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	lines := []cart.CartLine{
		{SKU: "delta", UnitPrice: 1, Quantity: 1},
		{SKU: "alpha", UnitPrice: 1, Quantity: 1},
		{SKU: "charlie", UnitPrice: 1, Quantity: 1},
		{SKU: "bravo", UnitPrice: 1, Quantity: 1},
	}
	r, err := cart.Price(lines, cart.PercentOff{})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	want := []string{"alpha", "bravo", "charlie", "delta"}
	if len(r.Lines) != len(want) {
		t.Fatalf("want %d lines got %d", len(want), len(r.Lines))
	}
	for i, w := range want {
		if r.Lines[i].SKU != w {
			t.Fatalf("Lines not sorted ascending at %d: want %q got %q (%+v)", i, w, r.Lines[i].SKU, r.Lines)
		}
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_conflicting_unit_price_errors(self):
        """L2: same SKU with differing UnitPrice -> non-nil error, empty Receipt, no panic."""
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	lines := []cart.CartLine{
		{SKU: "A", UnitPrice: 100, Quantity: 1},
		{SKU: "A", UnitPrice: 101, Quantity: 1}, // conflict
	}
	r, err := cart.Price(lines, cart.PercentOff{})
	if err == nil {
		t.Fatalf("conflicting UnitPrice must return a non-nil error, got receipt %+v", r)
	}
	if len(r.Lines) != 0 || r.NetTotal != 0 {
		t.Fatalf("on error, Receipt must be zero-value, got %+v", r)
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_out_of_range_percent_errors(self):
        """L2: discount percent > 100 or < 0 -> non-nil error, no panic."""
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	lines := []cart.CartLine{{SKU: "A", UnitPrice: 100, Quantity: 1}}

	if _, err := cart.Price(lines, cart.PercentOff{"A": 101}); err == nil {
		t.Fatalf("percent 101 must error")
	}
	if _, err := cart.Price(lines, cart.PercentOff{"A": -1}); err == nil {
		t.Fatalf("percent -1 must error")
	}
	// Boundaries 0 and 100 are valid.
	if _, err := cart.Price(lines, cart.PercentOff{"A": 0}); err != nil {
		t.Fatalf("percent 0 must be valid, got %v", err)
	}
	r, err := cart.Price(lines, cart.PercentOff{"A": 100})
	if err != nil {
		t.Fatalf("percent 100 must be valid, got %v", err)
	}
	if r.Lines[0].Net != 0 {
		t.Fatalf("100%% discount -> Net 0, got %d", r.Lines[0].Net)
	}
	if r.Lines[0].Discount != 100 {
		t.Fatalf("100%% discount -> Discount 100, got %d", r.Lines[0].Discount)
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_empty_cart_nonnil_lines(self):
        """L2: empty cart -> empty non-nil Lines, NetTotal 0, nil error."""
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	r, err := cart.Price([]cart.CartLine{}, cart.PercentOff{})
	if err != nil {
		t.Fatalf("empty cart must not error, got %v", err)
	}
	if r.Lines == nil {
		t.Fatalf("Lines must be non-nil for empty cart")
	}
	if len(r.Lines) != 0 {
		t.Fatalf("Lines must be empty, got %+v", r.Lines)
	}
	if r.NetTotal != 0 {
		t.Fatalf("NetTotal want 0 got %d", r.NetTotal)
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_absent_discount_means_zero(self):
        """L2: a SKU absent from discounts gets 0% (full Net == Gross)."""
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	lines := []cart.CartLine{
		{SKU: "A", UnitPrice: 30, Quantity: 3}, // gross 90
		{SKU: "B", UnitPrice: 10, Quantity: 1}, // gross 10, discounted
	}
	r, err := cart.Price(lines, cart.PercentOff{"B": 50})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	var a, b *cart.LineTotal
	for i := range r.Lines {
		switch r.Lines[i].SKU {
		case "A":
			a = &r.Lines[i]
		case "B":
			b = &r.Lines[i]
		}
	}
	if a == nil || b == nil {
		t.Fatalf("missing lines: %+v", r.Lines)
	}
	if a.Discount != 0 || a.Net != 90 {
		t.Fatalf("A absent-discount want Discount 0 Net 90, got %+v", *a)
	}
	if b.Discount != 5 || b.Net != 5 {
		t.Fatalf("B 50%% want Discount 5 Net 5, got %+v", *b)
	}
	if r.NetTotal != 95 {
		t.Fatalf("NetTotal want 95 got %d", r.NetTotal)
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_input_not_mutated(self):
        """L2: Price must not mutate the caller's lines slice or discounts map."""
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	lines := []cart.CartLine{
		{SKU: "delta", UnitPrice: 5, Quantity: 2},
		{SKU: "alpha", UnitPrice: 3, Quantity: 1},
		{SKU: "delta", UnitPrice: 5, Quantity: 4},
	}
	snapLines := make([]cart.CartLine, len(lines))
	copy(snapLines, lines)

	disc := cart.PercentOff{"alpha": 10, "delta": 20}
	snapDisc := map[string]int{}
	for k, v := range disc {
		snapDisc[k] = v
	}

	_, err := cart.Price(lines, disc)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	if len(lines) != len(snapLines) {
		t.Fatalf("lines length changed: %d != %d", len(lines), len(snapLines))
	}
	for i := range lines {
		if lines[i] != snapLines[i] {
			t.Fatalf("lines mutated/reordered at %d: got %+v want %+v", i, lines[i], snapLines[i])
		}
	}
	if len(disc) != len(snapDisc) {
		t.Fatalf("discounts map size changed: %d != %d", len(disc), len(snapDisc))
	}
	for k, v := range snapDisc {
		if disc[k] != v {
			t.Fatalf("discounts map mutated at %q: got %d want %d", k, disc[k], v)
		}
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr

    def test_combined_realistic_receipt(self):
        """L2: end-to-end scenario exercising consolidation, floor discount on
        consolidated gross, zero-quantity omission, sorting, and NetTotal."""
        body = self._IMPORT + r'''
func TestDriver(t *testing.T) {
	lines := []cart.CartLine{
		// SKU "pen": two lines, same price -> consolidated qty 5, gross 500.
		{SKU: "pen", UnitPrice: 100, Quantity: 2},
		{SKU: "pen", UnitPrice: 100, Quantity: 3},
		// SKU "ink": qty 0 across all -> omitted.
		{SKU: "ink", UnitPrice: 999, Quantity: 0},
		// SKU "book": single line, gross 1000.
		{SKU: "book", UnitPrice: 500, Quantity: 2},
	}
	disc := cart.PercentOff{
		"pen":  10, // floor(10% of 500) = 50 -> net 450
		"book": 33, // floor(33% of 1000) = 330 -> net 670
		// ink absent / omitted anyway
	}
	r, err := cart.Price(lines, disc)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	// ink omitted; book, pen sorted ascending.
	if len(r.Lines) != 2 {
		t.Fatalf("want 2 lines (book,pen), got %d: %+v", len(r.Lines), r.Lines)
	}
	if r.Lines[0].SKU != "book" || r.Lines[1].SKU != "pen" {
		t.Fatalf("lines not sorted ascending: %+v", r.Lines)
	}

	book := r.Lines[0]
	pen := r.Lines[1]

	if book.Quantity != 2 || book.Gross != 1000 || book.Discount != 330 || book.Net != 670 {
		t.Fatalf("book line wrong: %+v", book)
	}
	if pen.Quantity != 5 || pen.Gross != 500 || pen.Discount != 50 || pen.Net != 450 {
		t.Fatalf("pen line wrong: %+v", pen)
	}

	if r.NetTotal != 670+450 {
		t.Fatalf("NetTotal want %d got %d", 670+450, r.NetTotal)
	}
}
'''
        res = self._run_driver(body)
        assert res.returncode == 0, res.stdout + res.stderr


if __name__ == "__main__":
    raise SystemExit(pytest.main([os.path.abspath(__file__), "-v", "--tb=short"]))
