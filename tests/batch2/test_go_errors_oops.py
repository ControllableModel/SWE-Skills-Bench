"""Tests for the go-errors-oops skill task (ext2): "Build a Layered Payment Settlement Module".

Verifies that the agent created a self-contained Go example module at
examples/settlement that uses github.com/samber/oops to model a three-layer
(handler -> service -> gateway) payment-settlement flow where a single failure
propagates outward carrying contextual attributes contributed by every layer.

Strategy
--------
L1 cases check the required deliverable files exist, are minimally well-formed,
and that the go.work / go.mod wiring is present so the new module compiles
against the in-repo github.com/samber/oops library.

L2 cases EXERCISE the agent's actual Settle / NewGateway functions. Rather than
trusting the agent-authored settlement_test.go, this file injects its OWN
independent Go driver test (oops_zz_bench_driver_test.go) into the module and
runs it with `go test`, deep-validating Code()/Domain()/Context()/Owner()/
Hint()/public-message/message-cardinality exactly as the requirement doc
specifies. The driver is removed in teardown.

A naive solution that hardcodes one message/code for every failure, interpolates
variable data (amount/currency/account-id) into the Error() string, or fails to
expose the layered context, fails these tests. The native acceptance command
`go test ./examples/settlement/...` is also driven directly.
"""

import os
import re
import subprocess

import pytest

REPO_DIR = "/workspace/oops"
MODULE_DIR = os.path.join(REPO_DIR, "examples", "settlement")
SETTLEMENT_GO = os.path.join(MODULE_DIR, "settlement.go")
SETTLEMENT_TEST_GO = os.path.join(MODULE_DIR, "settlement_test.go")
MODULE_GO_MOD = os.path.join(MODULE_DIR, "go.mod")
GO_WORK = os.path.join(REPO_DIR, "go.work")

DRIVER_NAME = "oops_zz_bench_driver_test.go"
DRIVER_PATH = os.path.join(MODULE_DIR, DRIVER_NAME)

# Independent driver test. Package name is filled in at write time to match the
# agent's chosen package. It exercises Settle / NewGateway directly.
DRIVER_TEMPLATE = r'''package %(pkg)s

import (
	"fmt"
	"testing"

	"github.com/samber/oops"
)

// zzGateway builds a gateway with a single known account "acc-1" holding 500 cents.
func zzGateway() *Gateway {
	return NewGateway(map[string]int{
		"acc-1": 500,
		"acc-2": 1000,
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

func zzCtxVal(t *testing.T, oe oops.OopsError, key string) any {
	t.Helper()
	ctx := oe.Context()
	v, ok := ctx[key]
	if !ok {
		t.Fatalf("Context() missing key %%q; got %%v", key, ctx)
	}
	return v
}

func TestZZAccountNotFound(t *testing.T) {
	g := zzGateway()
	err := Settle(g, Charge{ID: "chg-1", AccountID: "ghost", AmountCents: 100, Currency: "USD"})
	oe := zzAsOops(t, err)

	if got := fmt.Sprint(oe.Code()); got != "account_not_found" {
		t.Fatalf("Code() = %%q, want account_not_found", got)
	}
	if got := fmt.Sprint(zzCtxVal(t, oe, "account_id")); got != "ghost" {
		t.Fatalf("Context()[account_id] = %%q, want ghost", got)
	}
	// The deepest (originating) layer must be the gateway domain.
	if got := oe.Domain(); got != "settlement-gateway" {
		t.Fatalf("Domain() = %%q, want settlement-gateway", got)
	}
}

func TestZZInsufficientFunds(t *testing.T) {
	g := zzGateway()
	err := Settle(g, Charge{ID: "chg-2", AccountID: "acc-1", AmountCents: 9999, Currency: "USD"})
	oe := zzAsOops(t, err)

	if got := fmt.Sprint(oe.Code()); got != "insufficient_funds" {
		t.Fatalf("Code() = %%q, want insufficient_funds", got)
	}
	if got := fmt.Sprint(zzCtxVal(t, oe, "amount_cents")); got != "9999" {
		t.Fatalf("Context()[amount_cents] = %%q, want 9999", got)
	}
	if got := fmt.Sprint(zzCtxVal(t, oe, "balance_cents")); got != "500" {
		t.Fatalf("Context()[balance_cents] = %%q, want 500", got)
	}
	if got := oops.GetPublic(err, "FALLBACK"); got != "Payment could not be completed." {
		t.Fatalf("GetPublic() = %%q, want %%q", got, "Payment could not be completed.")
	}
}

func TestZZUnsupportedCurrency(t *testing.T) {
	g := zzGateway()
	err := Settle(g, Charge{ID: "chg-3", AccountID: "acc-1", AmountCents: 100, Currency: "EUR"})
	oe := zzAsOops(t, err)

	if got := fmt.Sprint(oe.Code()); got != "unsupported_currency" {
		t.Fatalf("Code() = %%q, want unsupported_currency", got)
	}
	if got := fmt.Sprint(zzCtxVal(t, oe, "currency")); got != "EUR" {
		t.Fatalf("Context()[currency] = %%q, want EUR", got)
	}
}

func TestZZSuccess(t *testing.T) {
	g := zzGateway()
	if err := Settle(g, Charge{ID: "ok-1", AccountID: "acc-1", AmountCents: 100, Currency: "USD"}); err != nil {
		t.Fatalf("Settle success case returned error: %%v", err)
	}
	// Boundary: amount exactly equal to balance must succeed.
	if err := Settle(g, Charge{ID: "ok-2", AccountID: "acc-1", AmountCents: 500, Currency: "USD"}); err != nil {
		t.Fatalf("Settle boundary (amount==balance) returned error: %%v", err)
	}
	// Different known account.
	if err := Settle(g, Charge{ID: "ok-3", AccountID: "acc-2", AmountCents: 999, Currency: "USD"}); err != nil {
		t.Fatalf("Settle second-account case returned error: %%v", err)
	}
}

func TestZZOwnerHintConstant(t *testing.T) {
	g := zzGateway()
	notFound := zzAsOops(t, Settle(g, Charge{ID: "a", AccountID: "ghost", AmountCents: 100, Currency: "USD"}))
	funds := zzAsOops(t, Settle(g, Charge{ID: "b", AccountID: "acc-1", AmountCents: 9999, Currency: "USD"}))
	currency := zzAsOops(t, Settle(g, Charge{ID: "c", AccountID: "acc-1", AmountCents: 100, Currency: "EUR"}))

	// Owner and Hint must be non-empty for every failure ...
	for name, oe := range map[string]oops.OopsError{"account_not_found": notFound, "insufficient_funds": funds, "unsupported_currency": currency} {
		if oe.Owner() == "" {
			t.Fatalf("%%s: Owner() is empty, want non-empty", name)
		}
		if oe.Hint() == "" {
			t.Fatalf("%%s: Hint() is empty, want non-empty", name)
		}
	}
	// ... and identical regardless of which failure category occurred.
	if notFound.Owner() != funds.Owner() || funds.Owner() != currency.Owner() {
		t.Fatalf("Owner() differs across categories: %%q / %%q / %%q", notFound.Owner(), funds.Owner(), currency.Owner())
	}
	if notFound.Hint() != funds.Hint() || funds.Hint() != currency.Hint() {
		t.Fatalf("Hint() differs across categories: %%q / %%q / %%q", notFound.Hint(), funds.Hint(), currency.Hint())
	}
}

func TestZZCodesDistinct(t *testing.T) {
	g := zzGateway()
	c1 := fmt.Sprint(zzAsOops(t, Settle(g, Charge{AccountID: "ghost", AmountCents: 100, Currency: "USD"})).Code())
	c2 := fmt.Sprint(zzAsOops(t, Settle(g, Charge{AccountID: "acc-1", AmountCents: 9999, Currency: "USD"})).Code())
	c3 := fmt.Sprint(zzAsOops(t, Settle(g, Charge{AccountID: "acc-1", AmountCents: 100, Currency: "EUR"})).Code())
	if c1 == c2 || c1 == c3 || c2 == c3 {
		t.Fatalf("codes must be mutually distinct: %%q / %%q / %%q", c1, c2, c3)
	}
}

func TestZZMessageCardinalityNotFound(t *testing.T) {
	g := zzGateway()
	e1 := Settle(g, Charge{ID: "x1", AccountID: "ghost-a", AmountCents: 100, Currency: "USD"})
	e2 := Settle(g, Charge{ID: "x2", AccountID: "ghost-b", AmountCents: 400, Currency: "USD"})
	o1 := zzAsOops(t, e1)
	o2 := zzAsOops(t, e2)
	// Same failure category -> byte-identical Error() string.
	if e1.Error() != e2.Error() {
		t.Fatalf("account_not_found Error() differs across payloads: %%q vs %%q", e1.Error(), e2.Error())
	}
	// But the structured account_id must differ.
	if fmt.Sprint(o1.Context()["account_id"]) == fmt.Sprint(o2.Context()["account_id"]) {
		t.Fatalf("expected differing account_id context across the two failures")
	}
	// And the message must NOT contain the variable account ids (no interpolation).
	for _, frag := range []string{"ghost-a", "ghost-b"} {
		if zzContains(e1.Error()+e2.Error(), frag) {
			t.Fatalf("Error() message must not contain variable account id %%q", frag)
		}
	}
}

func TestZZMessageCardinalityFunds(t *testing.T) {
	g := zzGateway()
	// Two different over-charge requests, both insufficient_funds.
	e1 := Settle(g, Charge{ID: "f1", AccountID: "acc-1", AmountCents: 9999, Currency: "USD"})
	e2 := Settle(g, Charge{ID: "f2", AccountID: "acc-2", AmountCents: 55555, Currency: "USD"})
	o1 := zzAsOops(t, e1)
	o2 := zzAsOops(t, e2)
	if e1.Error() != e2.Error() {
		t.Fatalf("insufficient_funds Error() differs across payloads: %%q vs %%q", e1.Error(), e2.Error())
	}
	// Variable data must live in structured context, differing per request.
	if fmt.Sprint(o1.Context()["amount_cents"]) == fmt.Sprint(o2.Context()["amount_cents"]) {
		t.Fatalf("expected differing amount_cents context (9999 vs 55555)")
	}
	if fmt.Sprint(o1.Context()["balance_cents"]) == fmt.Sprint(o2.Context()["balance_cents"]) {
		t.Fatalf("expected differing balance_cents context (500 vs 1000)")
	}
	// And the message must NOT contain the variable numbers (no interpolation).
	msg := e1.Error()
	for _, frag := range []string{"9999", "500"} {
		if zzContains(msg, frag) {
			t.Fatalf("Error() message %%q must not contain variable data %%q", msg, frag)
		}
	}
}

func TestZZLayeredContextAggregated(t *testing.T) {
	// A single returned error must aggregate context contributed by all three
	// layers. For insufficient_funds the gateway contributes balance_cents and
	// the inner layers contribute amount_cents (and currency); confirm the one
	// error simultaneously exposes keys that only distinct layers can supply.
	g := zzGateway()
	oe := zzAsOops(t, Settle(g, Charge{ID: "agg", AccountID: "acc-1", AmountCents: 9999, Currency: "USD"}))
	ctx := oe.Context()
	for _, key := range []string{"amount_cents", "balance_cents"} {
		if _, ok := ctx[key]; !ok {
			t.Fatalf("aggregated Context() missing key %%q from a layer; got %%v", key, ctx)
		}
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
    return subprocess.run(
        ["go"] + args,
        cwd=REPO_DIR,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )


def _detect_package():
    """Read the package name the agent used in settlement.go."""
    with open(SETTLEMENT_GO, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            m = re.match(r"\s*package\s+([A-Za-z_][A-Za-z0-9_]*)", line)
            if m:
                return m.group(1)
    return "settlement"


@pytest.fixture(scope="module", autouse=True)
def _driver_lifecycle():
    """Install the independent Go driver test, then remove it on teardown."""
    pkg = "settlement"
    if os.path.isfile(SETTLEMENT_GO):
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
        """L1: the examples/settlement module directory was created."""
        assert os.path.isdir(MODULE_DIR), f"missing module dir {MODULE_DIR}"

    def test_settlement_go_exists(self):
        """L1: settlement.go exists and declares package + Settle/NewGateway funcs and Charge type."""
        assert os.path.isfile(SETTLEMENT_GO), "missing examples/settlement/settlement.go"
        with open(SETTLEMENT_GO, encoding="utf-8", errors="replace") as f:
            src = f.read()
        assert re.search(r"\bpackage\s+\w+", src), "no package clause in settlement.go"
        assert re.search(r"func\s+Settle\s*\(", src), "no Settle function"
        assert re.search(r"func\s+NewGateway\s*\(", src), "no NewGateway constructor"
        assert re.search(r"type\s+Charge\s+struct", src), "no Charge struct type"

    def test_settlement_test_go_exists(self):
        """L1: the agent's own settlement_test.go deliverable exists."""
        assert os.path.isfile(SETTLEMENT_TEST_GO), "missing examples/settlement/settlement_test.go"

    def test_go_mod_declares_module(self):
        """L1: go.mod declares the exact module path and requires samber/oops."""
        assert os.path.isfile(MODULE_GO_MOD), "missing examples/settlement/go.mod"
        with open(MODULE_GO_MOD, encoding="utf-8", errors="replace") as f:
            mod = f.read()
        assert "module github.com/samber/oops/examples/settlement" in mod, mod
        assert "github.com/samber/oops" in mod

    def test_go_work_lists_module(self):
        """L1: go.work uses ./examples/settlement so the in-repo lib resolves."""
        assert os.path.isfile(GO_WORK), "missing go.work"
        with open(GO_WORK, encoding="utf-8", errors="replace") as f:
            work = f.read()
        assert "./examples/settlement" in work, "go.work does not use ./examples/settlement"

    def test_module_compiles(self):
        """L1/L2: the new module builds against the in-repo library."""
        res = _run_go(["build", "./examples/settlement/..."])
        assert res.returncode == 0, f"build failed:\nSTDOUT:{res.stdout}\nSTDERR:{res.stderr}"

    # ---------- L2: behavior, driven by the injected independent test ----------

    def _run_driver(self, run_filter):
        res = _run_go(
            ["test", "-v", "-count=1", "-run", run_filter, "./examples/settlement/..."]
        )
        return res

    def test_account_not_found_behavior(self):
        """L2: unknown account -> code account_not_found, context account_id, deepest domain settlement-gateway."""
        res = self._run_driver("TestZZAccountNotFound$")
        assert res.returncode == 0, f"{res.stdout}\n{res.stderr}"
        assert "PASS: TestZZAccountNotFound" in res.stdout, (
            f"driver test did not run/pass:\n{res.stdout}\n{res.stderr}"
        )

    def test_insufficient_funds_behavior(self):
        """L2: over-charge -> code insufficient_funds, context amount_cents+balance_cents, spec public message."""
        res = self._run_driver("TestZZInsufficientFunds$")
        assert res.returncode == 0, f"{res.stdout}\n{res.stderr}"

    def test_unsupported_currency_behavior(self):
        """L2: non-USD currency -> code unsupported_currency, context currency."""
        res = self._run_driver("TestZZUnsupportedCurrency$")
        assert res.returncode == 0, f"{res.stdout}\n{res.stderr}"

    def test_success_and_boundary(self):
        """L2: valid USD charge, amount==balance boundary, and second account all return nil."""
        res = self._run_driver("TestZZSuccess$")
        assert res.returncode == 0, f"{res.stdout}\n{res.stderr}"

    def test_owner_hint_constant(self):
        """L2: Owner()/Hint() are non-empty and identical across all three failure categories."""
        res = self._run_driver("TestZZOwnerHintConstant$")
        assert res.returncode == 0, f"{res.stdout}\n{res.stderr}"

    def test_codes_distinct(self):
        """L2: the three failure codes are mutually distinct (no hardcoded single code)."""
        res = self._run_driver("TestZZCodesDistinct$")
        assert res.returncode == 0, f"{res.stdout}\n{res.stderr}"

    def test_message_cardinality_not_found(self):
        """L2: two account_not_found failures w/ different payloads -> identical Error(), differing context, no interpolation."""
        res = self._run_driver("TestZZMessageCardinalityNotFound$")
        assert res.returncode == 0, f"{res.stdout}\n{res.stderr}"

    def test_message_cardinality_funds(self):
        """L2: two insufficient_funds failures -> identical Error(), differing structured amount/balance, no interpolation."""
        res = self._run_driver("TestZZMessageCardinalityFunds$")
        assert res.returncode == 0, f"{res.stdout}\n{res.stderr}"

    def test_layered_context_aggregated(self):
        """L2: a single returned error aggregates context keys contributed by distinct layers."""
        res = self._run_driver("TestZZLayeredContextAggregated$")
        assert res.returncode == 0, f"{res.stdout}\n{res.stderr}"

    def test_agent_native_suite_passes(self):
        """L2: the spec's native command `go test ./examples/settlement/...` passes overall."""
        res = _run_go(["test", "-count=1", "./examples/settlement/..."])
        assert res.returncode == 0, f"native suite failed:\nSTDOUT:{res.stdout}\nSTDERR:{res.stderr}"
