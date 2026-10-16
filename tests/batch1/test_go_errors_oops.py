"""Tests for the go-errors-oops skill task: "Build a Checkout Error-Reporting Module".

Verifies that the agent created a self-contained Go example module at
examples/checkout that uses github.com/samber/oops to surface rich,
machine-inspectable failures from a tiny order-checkout flow.

Strategy
--------
L1 cases check the required deliverable files exist, are minimally well-formed,
and that go.work / go.mod wiring is present.

L2 cases EXERCISE the agent's actual Checkout / SafeCheckout functions. Rather
than trusting the agent-authored checkout_test.go, this file injects its own
independent Go driver test (oops_zz_bench_driver_test.go) into the module and
runs it with `go test`, deep-validating Code()/Domain()/Context()/HasTag()/
public-message/message-cardinality/panic-recovery exactly as the requirement
doc specifies. The driver is removed in teardown.

A naive solution that hardcodes one message/code for every failure, or that
interpolates variable data into the message string, fails these tests.
"""

import os
import re
import subprocess

import pytest

REPO_DIR = "/workspace/oops"
MODULE_DIR = os.path.join(REPO_DIR, "examples", "checkout")
CHECKOUT_GO = os.path.join(MODULE_DIR, "checkout.go")
CHECKOUT_TEST_GO = os.path.join(MODULE_DIR, "checkout_test.go")
MODULE_GO_MOD = os.path.join(MODULE_DIR, "go.mod")
GO_WORK = os.path.join(REPO_DIR, "go.work")

DRIVER_NAME = "oops_zz_bench_driver_test.go"
DRIVER_PATH = os.path.join(MODULE_DIR, DRIVER_NAME)

# Independent driver test. Package name is filled in at write time to match the
# agent's chosen package. It exercises Checkout / SafeCheckout directly.
DRIVER_TEMPLATE = r'''package %(pkg)s

import (
	"fmt"
	"testing"

	"github.com/samber/oops"
)

func zzCatalog() *Catalog {
	return NewCatalog(map[string]Product{
		"sku-1": {ID: "sku-1", Name: "Widget", Stock: 5},
		"sku-2": {ID: "sku-2", Name: "Gadget", Stock: 2},
	})
}

func zzAsOops(t *testing.T, err error) oops.OopsError {
	t.Helper()
	if err == nil {
		t.Fatalf("expected non-nil error")
	}
	oe, ok := oops.AsOops(err)
	if !ok {
		t.Fatalf("error is not an oops error: %%v", err)
	}
	return oe
}

func TestZZProductNotFound(t *testing.T) {
	cat := zzCatalog()
	err := Checkout(cat, OrderRequest{UserID: "u1", TenantID: "t1", ProductID: "missing", Quantity: 1})
	oe := zzAsOops(t, err)

	if got := fmt.Sprint(oe.Code()); got != "product_not_found" {
		t.Fatalf("Code() = %%q, want product_not_found", got)
	}
	if got := oops.GetPublic(err, "FALLBACK"); got != "That product is unavailable." {
		t.Fatalf("GetPublic() = %%q, want %%q", got, "That product is unavailable.")
	}
	if got := oe.Domain(); got != "checkout-repository" {
		t.Fatalf("Domain() = %%q, want checkout-repository", got)
	}
	ctx := oe.Context()
	if v, ok := ctx["product_id"]; !ok {
		t.Fatalf("Context() missing key product_id; got %%v", ctx)
	} else if fmt.Sprint(v) != "missing" {
		t.Fatalf("Context()[product_id] = %%v, want missing", v)
	}
}

func TestZZInsufficientStock(t *testing.T) {
	cat := zzCatalog()
	err := Checkout(cat, OrderRequest{UserID: "u1", TenantID: "t1", ProductID: "sku-1", Quantity: 99})
	oe := zzAsOops(t, err)

	if got := fmt.Sprint(oe.Code()); got != "insufficient_stock" {
		t.Fatalf("Code() = %%q, want insufficient_stock", got)
	}
	if got := oops.GetPublic(err, "FALLBACK"); got != "Not enough items in stock." {
		t.Fatalf("GetPublic() = %%q, want %%q", got, "Not enough items in stock.")
	}
	ctx := oe.Context()
	rq, ok := ctx["requested"]
	if !ok {
		t.Fatalf("Context() missing key requested; got %%v", ctx)
	}
	if fmt.Sprint(rq) != "99" {
		t.Fatalf("Context()[requested] = %%v, want 99", rq)
	}
	av, ok := ctx["available"]
	if !ok {
		t.Fatalf("Context() missing key available; got %%v", ctx)
	}
	if fmt.Sprint(av) != "5" {
		t.Fatalf("Context()[available] = %%v, want 5", av)
	}
	if !oe.HasTag("checkout") {
		t.Fatalf("HasTag(checkout) = false, want true; tags=%%v", oe.Tags())
	}
}

func TestZZInvalidQuantity(t *testing.T) {
	cat := zzCatalog()
	err := Checkout(cat, OrderRequest{UserID: "u1", TenantID: "t1", ProductID: "sku-1", Quantity: 0})
	oe := zzAsOops(t, err)

	if got := fmt.Sprint(oe.Code()); got != "invalid_quantity" {
		t.Fatalf("Code() = %%q, want invalid_quantity", got)
	}
	if got := oops.GetPublic(err, "FALLBACK"); got != "Quantity must be at least one." {
		t.Fatalf("GetPublic() = %%q, want %%q", got, "Quantity must be at least one.")
	}
}

func TestZZInvalidQuantityNegative(t *testing.T) {
	cat := zzCatalog()
	err := Checkout(cat, OrderRequest{ProductID: "sku-1", Quantity: -7})
	oe := zzAsOops(t, err)
	if got := fmt.Sprint(oe.Code()); got != "invalid_quantity" {
		t.Fatalf("Code() = %%q, want invalid_quantity (negative qty)", got)
	}
}

func TestZZSuccess(t *testing.T) {
	cat := zzCatalog()
	if err := Checkout(cat, OrderRequest{ProductID: "sku-1", Quantity: 3}); err != nil {
		t.Fatalf("Checkout success case returned error: %%v", err)
	}
	// Boundary: quantity exactly equals stock must succeed.
	if err := Checkout(cat, OrderRequest{ProductID: "sku-2", Quantity: 2}); err != nil {
		t.Fatalf("Checkout boundary (qty==stock) returned error: %%v", err)
	}
}

func TestZZSafeCheckoutPanicRecovery(t *testing.T) {
	err := SafeCheckout(nil, OrderRequest{ProductID: "sku-1", Quantity: 1})
	oe := zzAsOops(t, err)
	if got := fmt.Sprint(oe.Code()); got != "checkout_panic" {
		t.Fatalf("Code() = %%q, want checkout_panic", got)
	}
	if got := oe.Domain(); got != "checkout-service" {
		t.Fatalf("Domain() = %%q, want checkout-service", got)
	}
}

func TestZZSafeCheckoutMatchesCheckout(t *testing.T) {
	cat := zzCatalog()
	// success
	if got := SafeCheckout(cat, OrderRequest{ProductID: "sku-1", Quantity: 3}); got != nil {
		t.Fatalf("SafeCheckout success returned error: %%v", got)
	}
	// failure parity: same code as Checkout for the same input
	se := zzAsOops(t, SafeCheckout(cat, OrderRequest{ProductID: "missing", Quantity: 1}))
	ce := zzAsOops(t, Checkout(cat, OrderRequest{ProductID: "missing", Quantity: 1}))
	if fmt.Sprint(se.Code()) != fmt.Sprint(ce.Code()) {
		t.Fatalf("SafeCheckout code %%v != Checkout code %%v", se.Code(), ce.Code())
	}
}

func TestZZMessageCardinalityNotFound(t *testing.T) {
	cat := zzCatalog()
	e1 := Checkout(cat, OrderRequest{UserID: "alice", TenantID: "ta", ProductID: "ghost-a", Quantity: 1})
	e2 := Checkout(cat, OrderRequest{UserID: "bob", TenantID: "tb", ProductID: "ghost-b", Quantity: 4})
	o1 := zzAsOops(t, e1)
	o2 := zzAsOops(t, e2)
	// Same failure category -> byte-identical Error() string.
	if e1.Error() != e2.Error() {
		t.Fatalf("Error() differs across same-category failures: %%q vs %%q", e1.Error(), e2.Error())
	}
	// But the structured product_id must differ.
	if fmt.Sprint(o1.Context()["product_id"]) == fmt.Sprint(o2.Context()["product_id"]) {
		t.Fatalf("expected differing product_id context across the two failures")
	}
	if fmt.Sprint(o1.Context()["product_id"]) != "ghost-a" {
		t.Fatalf("Context product_id = %%v, want ghost-a", o1.Context()["product_id"])
	}
}

func TestZZMessageCardinalityStock(t *testing.T) {
	cat := zzCatalog()
	e1 := Checkout(cat, OrderRequest{UserID: "alice", TenantID: "ta", ProductID: "sku-1", Quantity: 50})
	e2 := Checkout(cat, OrderRequest{UserID: "bob", TenantID: "tb", ProductID: "sku-2", Quantity: 9})
	o1 := zzAsOops(t, e1)
	o2 := zzAsOops(t, e2)
	if e1.Error() != e2.Error() {
		t.Fatalf("insufficient_stock Error() differs across payloads: %%q vs %%q", e1.Error(), e2.Error())
	}
	// Variable data must live in structured context, differing per request.
	if fmt.Sprint(o1.Context()["requested"]) == fmt.Sprint(o2.Context()["requested"]) {
		t.Fatalf("expected differing requested context (50 vs 9)")
	}
	if fmt.Sprint(o1.Context()["available"]) == fmt.Sprint(o2.Context()["available"]) {
		t.Fatalf("expected differing available context (5 vs 2)")
	}
	// And the message must NOT contain the variable numbers (no interpolation).
	msg := e1.Error()
	for _, frag := range []string{"50", "sku-1", "alice"} {
		if zzContains(msg, frag) {
			t.Fatalf("Error() message %%q must not contain variable data %%q", msg, frag)
		}
	}
}

func TestZZCategoriesDistinctPublic(t *testing.T) {
	cat := zzCatalog()
	pNotFound := oops.GetPublic(Checkout(cat, OrderRequest{ProductID: "nope", Quantity: 1}), "X")
	pStock := oops.GetPublic(Checkout(cat, OrderRequest{ProductID: "sku-1", Quantity: 99}), "X")
	pInvalid := oops.GetPublic(Checkout(cat, OrderRequest{ProductID: "sku-1", Quantity: 0}), "X")
	if pNotFound != "That product is unavailable." {
		t.Fatalf("not_found public = %%q", pNotFound)
	}
	if pStock != "Not enough items in stock." {
		t.Fatalf("stock public = %%q", pStock)
	}
	if pInvalid != "Quantity must be at least one." {
		t.Fatalf("invalid public = %%q", pInvalid)
	}
	// The three spec-mandated public messages are mutually distinct.
	if pNotFound == pStock || pNotFound == pInvalid || pStock == pInvalid {
		t.Fatalf("public messages must be distinct per category: %%q / %%q / %%q", pNotFound, pStock, pInvalid)
	}
	// And the three failure codes are mutually distinct.
	cNotFound := fmt.Sprint(zzAsOops(t, Checkout(cat, OrderRequest{ProductID: "nope", Quantity: 1})).Code())
	cStock := fmt.Sprint(zzAsOops(t, Checkout(cat, OrderRequest{ProductID: "sku-1", Quantity: 99})).Code())
	cInvalid := fmt.Sprint(zzAsOops(t, Checkout(cat, OrderRequest{ProductID: "sku-1", Quantity: 0})).Code())
	if cNotFound == cStock || cNotFound == cInvalid || cStock == cInvalid {
		t.Fatalf("codes must be distinct: %%q / %%q / %%q", cNotFound, cStock, cInvalid)
	}
}

func zzContains(s, sub string) bool {
	return len(sub) > 0 && len(s) >= len(sub) && (indexOf(s, sub) >= 0)
}

func indexOf(s, sub string) int {
	for i := 0; i+len(sub) <= len(s); i++ {
		if s[i:i+len(sub)] == sub {
			return i
		}
	}
	return -1
}
'''


def _run_go(args, timeout=420):
    env = dict(os.environ)
    env.setdefault("GOFLAGS", "")
    # Allow module cache + build cache to live under a writable location if needed.
    return subprocess.run(
        ["go"] + args,
        cwd=REPO_DIR,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )


def _detect_package():
    """Read the package name the agent used in checkout.go."""
    with open(CHECKOUT_GO, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            m = re.match(r"\s*package\s+([A-Za-z_][A-Za-z0-9_]*)", line)
            if m:
                return m.group(1)
    return "checkout"


@pytest.fixture(scope="module", autouse=True)
def _driver_lifecycle():
    """Install the independent Go driver test, then remove it on teardown."""
    pkg = "checkout"
    if os.path.isfile(CHECKOUT_GO):
        pkg = _detect_package()
    if os.path.isdir(MODULE_DIR):
        with open(DRIVER_PATH, "w", encoding="utf-8") as f:
            f.write(DRIVER_TEMPLATE % {"pkg": pkg})
    yield
    try:
        os.remove(DRIVER_PATH)
    except OSError:
        pass


class TestGoErrorsOops:
    REPO_DIR = "/workspace/oops"

    # ---------- L1: deliverables exist and are well-formed ----------

    def test_module_dir_exists(self):
        """L1: the examples/checkout module directory was created."""
        assert os.path.isdir(MODULE_DIR), f"missing module dir {MODULE_DIR}"

    def test_checkout_go_exists(self):
        """L1: checkout.go exists and declares a package and a Checkout func."""
        assert os.path.isfile(CHECKOUT_GO), "missing examples/checkout/checkout.go"
        with open(CHECKOUT_GO, encoding="utf-8", errors="replace") as f:
            src = f.read()
        assert re.search(r"\bpackage\s+\w+", src), "no package clause in checkout.go"
        assert re.search(r"func\s+Checkout\s*\(", src), "no Checkout function"
        assert re.search(r"func\s+SafeCheckout\s*\(", src), "no SafeCheckout function"

    def test_go_mod_declares_module(self):
        """L1: go.mod declares the exact module path and requires samber/oops."""
        assert os.path.isfile(MODULE_GO_MOD), "missing examples/checkout/go.mod"
        with open(MODULE_GO_MOD, encoding="utf-8", errors="replace") as f:
            mod = f.read()
        assert "module github.com/samber/oops/examples/checkout" in mod, mod
        assert "github.com/samber/oops" in mod

    def test_go_work_lists_module(self):
        """L1: go.work uses ./examples/checkout so the in-repo lib resolves."""
        assert os.path.isfile(GO_WORK), "missing go.work"
        with open(GO_WORK, encoding="utf-8", errors="replace") as f:
            work = f.read()
        assert "./examples/checkout" in work, "go.work does not use ./examples/checkout"

    def test_module_compiles(self):
        """L1/L2: the new module builds against the in-repo library."""
        res = _run_go(["build", "./examples/checkout/..."])
        assert res.returncode == 0, f"build failed:\nSTDOUT:{res.stdout}\nSTDERR:{res.stderr}"

    # ---------- L2: behavior, driven by the injected independent test ----------

    def _run_driver(self, run_filter):
        res = _run_go(
            ["test", "-v", "-count=1", "-run", run_filter, "./examples/checkout/..."]
        )
        return res

    def test_product_not_found_behavior(self):
        """L2: missing product -> code/public/domain/context per spec."""
        res = self._run_driver("TestZZProductNotFound$")
        assert res.returncode == 0, f"{res.stdout}\n{res.stderr}"
        assert "PASS: TestZZProductNotFound" in res.stdout, (
            f"driver test did not run/pass:\n{res.stdout}\n{res.stderr}"
        )

    def test_insufficient_stock_behavior(self):
        """L2: over-order -> code/public/context(requested,available)/tag checkout."""
        res = self._run_driver("TestZZInsufficientStock$")
        assert res.returncode == 0, f"{res.stdout}\n{res.stderr}"

    def test_invalid_quantity_behavior(self):
        """L2: quantity 0 and negative -> code invalid_quantity + public msg."""
        res = self._run_driver("TestZZInvalidQuantity$|TestZZInvalidQuantityNegative$")
        assert res.returncode == 0, f"{res.stdout}\n{res.stderr}"

    def test_success_and_boundary(self):
        """L2: valid order and qty==stock boundary both return nil."""
        res = self._run_driver("TestZZSuccess$")
        assert res.returncode == 0, f"{res.stdout}\n{res.stderr}"

    def test_panic_recovery_behavior(self):
        """L2: SafeCheckout(nil,...) recovers -> code checkout_panic, domain checkout-service."""
        res = self._run_driver("TestZZSafeCheckoutPanicRecovery$")
        assert res.returncode == 0, f"{res.stdout}\n{res.stderr}"

    def test_safecheckout_parity(self):
        """L2: SafeCheckout matches Checkout for non-nil catalog (success + failure code)."""
        res = self._run_driver("TestZZSafeCheckoutMatchesCheckout$")
        assert res.returncode == 0, f"{res.stdout}\n{res.stderr}"

    def test_message_cardinality_not_found(self):
        """L2: two product_not_found failures w/ different payloads -> identical Error(), differing context."""
        res = self._run_driver("TestZZMessageCardinalityNotFound$")
        assert res.returncode == 0, f"{res.stdout}\n{res.stderr}"

    def test_message_cardinality_stock(self):
        """L2: two insufficient_stock failures -> identical Error(), differing structured data, no interpolation."""
        res = self._run_driver("TestZZMessageCardinalityStock$")
        assert res.returncode == 0, f"{res.stdout}\n{res.stderr}"

    def test_categories_have_distinct_public_and_codes(self):
        """L2: each category exposes its spec public message; the 3 public msgs and 3 codes are mutually distinct."""
        res = self._run_driver("TestZZCategoriesDistinctPublic$")
        assert res.returncode == 0, f"{res.stdout}\n{res.stderr}"

    def test_agent_native_suite_passes(self):
        """L2: the spec's native command `go test ./examples/checkout/...` passes overall."""
        res = _run_go(["test", "-count=1", "./examples/checkout/..."])
        assert res.returncode == 0, f"native suite failed:\nSTDOUT:{res.stdout}\nSTDERR:{res.stderr}"
