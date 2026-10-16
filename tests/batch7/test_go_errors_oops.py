"""Tests for the go-errors-oops skill task (ext7): "Build a Tag-Driven Error Routing Module".

Verifies that the agent created a self-contained Go example module at
examples/alertroute that uses github.com/samber/oops to categorize failures
with tags and route each failure to an alerting channel *purely by inspecting
its tags* (via the oops tag accessors), never by parsing the message, code, or
domain.

Strategy
--------
L1 cases check the required deliverable files exist, are minimally well-formed,
and that go.work / go.mod wiring is present and the module compiles against the
in-repo library.

L2 cases EXERCISE the agent's actual Route function and the four producers
(DatabaseTimeout / RateLimited / DiskFull / ValidationFailed). Rather than
trusting the agent-authored alertroute_test.go, this file injects its own
independent Go driver test (oops_zz_route_driver_test.go) into the module and
runs it with `go test`, deep-validating:

  * Route(nil) == "none"
  * both `critical` producers (DatabaseTimeout, DiskFull) -> "pagerduty"
  * RateLimited (throttling, no critical) -> "slack-ops"
  * ValidationFailed (validation, no critical) -> "slack-dev"
  * a plain (non-oops) error -> "default"
  * the four producers' Code() values are pairwise distinct
  * producers actually carry the spec-mandated tags (HasTag), and each is a
    non-nil oops error with a domain

Discriminative cases defeat naive stubs:
  * a router that routes by Code() rather than tags is caught by a synthetic
    oops error whose code spells "critical"/"pagerduty" but carries NO tags
    (it must route "default"); and by a synthetic oops error tagged "critical"
    whose code/message is innocuous (it must route "pagerduty").
  * a router that hardcodes one channel is caught because the four+nil+plain
    cases demand five distinct channel strings.
  * precedence: a producer tagged both critical and throttling must still go
    to "pagerduty" (critical wins).

The driver is removed in teardown.
"""

import os
import re
import subprocess

import pytest

REPO_DIR = "/workspace/oops"
MODULE_DIR = os.path.join(REPO_DIR, "examples", "alertroute")
ALERTROUTE_GO = os.path.join(MODULE_DIR, "alertroute.go")
ALERTROUTE_TEST_GO = os.path.join(MODULE_DIR, "alertroute_test.go")
MODULE_GO_MOD = os.path.join(MODULE_DIR, "go.mod")
GO_WORK = os.path.join(REPO_DIR, "go.work")

DRIVER_NAME = "oops_zz_route_driver_test.go"
DRIVER_PATH = os.path.join(MODULE_DIR, DRIVER_NAME)

# Independent driver test. Package name is filled in at write time to match the
# agent's chosen package. It exercises Route + the four producers directly, and
# builds adversarial synthetic oops errors to ensure routing is tag-driven.
DRIVER_TEMPLATE = r'''package %(pkg)s

import (
	"errors"
	"fmt"
	"testing"

	"github.com/samber/oops"
)

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

func zzCode(t *testing.T, err error) string {
	t.Helper()
	return fmt.Sprint(zzAsOops(t, err).Code())
}

// ---- nil and plain-error fallback -------------------------------------------

func TestZZRouteNil(t *testing.T) {
	if got := Route(nil); got != "none" {
		t.Fatalf("Route(nil) = %%q, want \"none\"", got)
	}
}

func TestZZRoutePlainError(t *testing.T) {
	if got := Route(errors.New("plain")); got != "default" {
		t.Fatalf("Route(plain) = %%q, want \"default\"", got)
	}
}

// ---- producers route correctly ----------------------------------------------

func TestZZRouteDatabaseTimeout(t *testing.T) {
	err := DatabaseTimeout()
	oe := zzAsOops(t, err)
	if !oe.HasTag("database") {
		t.Fatalf("DatabaseTimeout missing tag \"database\"; tags=%%v", oe.Tags())
	}
	if !oe.HasTag("critical") {
		t.Fatalf("DatabaseTimeout missing tag \"critical\"; tags=%%v", oe.Tags())
	}
	if got := Route(err); got != "pagerduty" {
		t.Fatalf("Route(DatabaseTimeout) = %%q, want \"pagerduty\"", got)
	}
}

func TestZZRouteDiskFull(t *testing.T) {
	err := DiskFull()
	oe := zzAsOops(t, err)
	if !oe.HasTag("storage") {
		t.Fatalf("DiskFull missing tag \"storage\"; tags=%%v", oe.Tags())
	}
	if !oe.HasTag("critical") {
		t.Fatalf("DiskFull missing tag \"critical\"; tags=%%v", oe.Tags())
	}
	if got := Route(err); got != "pagerduty" {
		t.Fatalf("Route(DiskFull) = %%q, want \"pagerduty\"", got)
	}
}

func TestZZRouteRateLimited(t *testing.T) {
	err := RateLimited()
	oe := zzAsOops(t, err)
	if !oe.HasTag("throttling") {
		t.Fatalf("RateLimited missing tag \"throttling\"; tags=%%v", oe.Tags())
	}
	if oe.HasTag("critical") {
		t.Fatalf("RateLimited must NOT carry tag \"critical\"; tags=%%v", oe.Tags())
	}
	if got := Route(err); got != "slack-ops" {
		t.Fatalf("Route(RateLimited) = %%q, want \"slack-ops\"", got)
	}
}

func TestZZRouteValidationFailed(t *testing.T) {
	err := ValidationFailed()
	oe := zzAsOops(t, err)
	if !oe.HasTag("validation") {
		t.Fatalf("ValidationFailed missing tag \"validation\"; tags=%%v", oe.Tags())
	}
	if oe.HasTag("critical") {
		t.Fatalf("ValidationFailed must NOT carry tag \"critical\"; tags=%%v", oe.Tags())
	}
	if got := Route(err); got != "slack-dev" {
		t.Fatalf("Route(ValidationFailed) = %%q, want \"slack-dev\"", got)
	}
}

// ---- distinct codes & domains -----------------------------------------------

func TestZZProducersHaveDomains(t *testing.T) {
	for name, err := range map[string]error{
		"DatabaseTimeout":  DatabaseTimeout(),
		"RateLimited":      RateLimited(),
		"DiskFull":         DiskFull(),
		"ValidationFailed": ValidationFailed(),
	} {
		oe := zzAsOops(t, err)
		if oe.Domain() == "" {
			t.Fatalf("%%s has empty Domain()", name)
		}
	}
}

func TestZZProducerCodesDistinct(t *testing.T) {
	codes := []string{
		zzCode(t, DatabaseTimeout()),
		zzCode(t, RateLimited()),
		zzCode(t, DiskFull()),
		zzCode(t, ValidationFailed()),
	}
	for _, c := range codes {
		if c == "" || c == "<nil>" {
			t.Fatalf("a producer has an empty/nil code; codes=%%v", codes)
		}
	}
	seen := map[string]bool{}
	for _, c := range codes {
		if seen[c] {
			t.Fatalf("producer codes are not pairwise distinct: %%v", codes)
		}
		seen[c] = true
	}
}

// ---- all five outcomes are distinct (defeats hardcoded single channel) ------

func TestZZAllChannelsDistinct(t *testing.T) {
	got := map[string]string{
		"nil":        Route(nil),
		"critical":   Route(DatabaseTimeout()),
		"throttling": Route(RateLimited()),
		"validation": Route(ValidationFailed()),
		"plain":      Route(errors.New("x")),
	}
	want := map[string]string{
		"nil":        "none",
		"critical":   "pagerduty",
		"throttling": "slack-ops",
		"validation": "slack-dev",
		"plain":      "default",
	}
	for k, w := range want {
		if got[k] != w {
			t.Fatalf("Route case %%q = %%q, want %%q (all=%%v)", k, got[k], w, got)
		}
	}
	// five mutually distinct channel strings.
	uniq := map[string]bool{}
	for _, v := range got {
		uniq[v] = true
	}
	if len(uniq) != 5 {
		t.Fatalf("expected 5 distinct channels, got %%d: %%v", len(uniq), got)
	}
}

// ---- discriminative: routing must be by TAGS, not code/message --------------

// A synthetic oops error whose CODE spells "critical" and whose MESSAGE mentions
// pagerduty, but which carries NO tags. A tag-driven Route must return "default";
// a code/message-parsing router would wrongly return "pagerduty".
func TestZZRouteIgnoresCodeAndMessage(t *testing.T) {
	err := oops.Code("critical").In("synthetic").Errorf("escalate to pagerduty slack-ops validation")
	if oe, ok := oops.AsOops(err); !ok || oe.HasTag("critical") {
		t.Fatalf("setup error: synthetic err should be oops w/o critical tag")
	}
	if got := Route(err); got != "default" {
		t.Fatalf("Route(code=critical,no-tags) = %%q, want \"default\" (router must ignore code/message)", got)
	}
}

// A synthetic oops error tagged "critical" but with an innocuous code/message.
// Tag-driven Route must return "pagerduty".
func TestZZRouteUsesTagNotCode(t *testing.T) {
	err := oops.Code("ok_code").Tags("critical").In("synthetic").Errorf("all good")
	if got := Route(err); got != "pagerduty" {
		t.Fatalf("Route(tag=critical) = %%q, want \"pagerduty\"", got)
	}
}

// Precedence: critical must win over throttling/validation when both present.
func TestZZRoutePrecedenceCriticalWins(t *testing.T) {
	err := oops.Tags("throttling", "validation", "critical").In("synthetic").Errorf("multi")
	if got := Route(err); got != "pagerduty" {
		t.Fatalf("Route(throttling+validation+critical) = %%q, want \"pagerduty\"", got)
	}
}

// throttling must win over validation when both present (and no critical).
func TestZZRoutePrecedenceThrottlingOverValidation(t *testing.T) {
	err := oops.Tags("throttling", "validation").In("synthetic").Errorf("multi")
	if got := Route(err); got != "slack-ops" {
		t.Fatalf("Route(throttling+validation) = %%q, want \"slack-ops\"", got)
	}
}

// An oops error with an unrecognized tag and no critical/throttling/validation
// must fall through to "default".
func TestZZRouteUnknownTagDefault(t *testing.T) {
	err := oops.Tags("storage").In("synthetic").Errorf("disk-ish but not critical")
	if got := Route(err); got != "default" {
		t.Fatalf("Route(tag=storage only) = %%q, want \"default\"", got)
	}
}
'''


def _run_go(args, timeout=600):
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
    """Read the package name the agent used in alertroute.go."""
    with open(ALERTROUTE_GO, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            m = re.match(r"\s*package\s+([A-Za-z_][A-Za-z0-9_]*)", line)
            if m:
                return m.group(1)
    return "alertroute"


@pytest.fixture(scope="module", autouse=True)
def _driver_lifecycle():
    """Install the independent Go driver test, then remove it on teardown."""
    pkg = "alertroute"
    if os.path.isfile(ALERTROUTE_GO):
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
        """L1: the examples/alertroute module directory was created."""
        assert os.path.isdir(MODULE_DIR), f"missing module dir {MODULE_DIR}"

    def test_alertroute_go_exists(self):
        """L1: alertroute.go exists, declares a package, the Route func and the four producers."""
        assert os.path.isfile(ALERTROUTE_GO), "missing examples/alertroute/alertroute.go"
        with open(ALERTROUTE_GO, encoding="utf-8", errors="replace") as f:
            src = f.read()
        assert re.search(r"\bpackage\s+\w+", src), "no package clause in alertroute.go"
        assert re.search(r"func\s+Route\s*\(", src), "no Route function"
        for fn in ("DatabaseTimeout", "RateLimited", "DiskFull", "ValidationFailed"):
            assert re.search(r"func\s+" + fn + r"\s*\(", src), f"no {fn} producer function"

    def test_test_file_exists(self):
        """L1: the agent authored alertroute_test.go (deterministic tests)."""
        assert os.path.isfile(ALERTROUTE_TEST_GO), "missing examples/alertroute/alertroute_test.go"

    def test_go_mod_declares_module(self):
        """L1: go.mod declares the exact module path and requires samber/oops."""
        assert os.path.isfile(MODULE_GO_MOD), "missing examples/alertroute/go.mod"
        with open(MODULE_GO_MOD, encoding="utf-8", errors="replace") as f:
            mod = f.read()
        assert "module github.com/samber/oops/examples/alertroute" in mod, mod
        assert "github.com/samber/oops" in mod

    def test_go_work_lists_module(self):
        """L1: go.work uses ./examples/alertroute so the in-repo lib resolves."""
        assert os.path.isfile(GO_WORK), "missing go.work"
        with open(GO_WORK, encoding="utf-8", errors="replace") as f:
            work = f.read()
        assert "./examples/alertroute" in work, "go.work does not use ./examples/alertroute"

    def test_module_compiles(self):
        """L1/L2: the new module builds against the in-repo library."""
        res = _run_go(["build", "./examples/alertroute/..."])
        assert res.returncode == 0, f"build failed:\nSTDOUT:{res.stdout}\nSTDERR:{res.stderr}"

    # ---------- L2: behavior, driven by the injected independent test ----------

    def _run_driver(self, run_filter):
        return _run_go(
            ["test", "-v", "-count=1", "-run", run_filter, "./examples/alertroute/..."]
        )

    def test_route_nil_and_plain(self):
        """L2: Route(nil) -> "none"; Route(plain non-oops error) -> "default"."""
        res = self._run_driver("TestZZRouteNil$|TestZZRoutePlainError$")
        assert res.returncode == 0, f"{res.stdout}\n{res.stderr}"
        assert "PASS: TestZZRouteNil" in res.stdout, f"driver did not run:\n{res.stdout}\n{res.stderr}"
        assert "PASS: TestZZRoutePlainError" in res.stdout, f"{res.stdout}\n{res.stderr}"

    def test_route_critical_producers_pagerduty(self):
        """L2: both critical producers (DatabaseTimeout, DiskFull) carry their tags and route to "pagerduty"."""
        res = self._run_driver("TestZZRouteDatabaseTimeout$|TestZZRouteDiskFull$")
        assert res.returncode == 0, f"{res.stdout}\n{res.stderr}"
        assert "PASS: TestZZRouteDatabaseTimeout" in res.stdout, f"{res.stdout}\n{res.stderr}"
        assert "PASS: TestZZRouteDiskFull" in res.stdout, f"{res.stdout}\n{res.stderr}"

    def test_route_throttling_slack_ops(self):
        """L2: RateLimited is tagged throttling (not critical) and routes to "slack-ops"."""
        res = self._run_driver("TestZZRouteRateLimited$")
        assert res.returncode == 0, f"{res.stdout}\n{res.stderr}"
        assert "PASS: TestZZRouteRateLimited" in res.stdout, f"{res.stdout}\n{res.stderr}"

    def test_route_validation_slack_dev(self):
        """L2: ValidationFailed is tagged validation (not critical) and routes to "slack-dev"."""
        res = self._run_driver("TestZZRouteValidationFailed$")
        assert res.returncode == 0, f"{res.stdout}\n{res.stderr}"
        assert "PASS: TestZZRouteValidationFailed" in res.stdout, f"{res.stdout}\n{res.stderr}"

    def test_producer_codes_distinct_and_domains(self):
        """L2: the four producers expose non-empty domains and pairwise-distinct Code() values."""
        res = self._run_driver("TestZZProducersHaveDomains$|TestZZProducerCodesDistinct$")
        assert res.returncode == 0, f"{res.stdout}\n{res.stderr}"
        assert "PASS: TestZZProducerCodesDistinct" in res.stdout, f"{res.stdout}\n{res.stderr}"

    def test_all_channels_distinct(self):
        """L2: nil/critical/throttling/validation/plain map to five distinct, spec-mandated channels (defeats hardcoding)."""
        res = self._run_driver("TestZZAllChannelsDistinct$")
        assert res.returncode == 0, f"{res.stdout}\n{res.stderr}"
        assert "PASS: TestZZAllChannelsDistinct" in res.stdout, f"{res.stdout}\n{res.stderr}"

    def test_routing_ignores_code_and_message(self):
        """L2 (discriminative): an oops error whose code spells "critical" but has NO tags must route to "default"."""
        res = self._run_driver("TestZZRouteIgnoresCodeAndMessage$")
        assert res.returncode == 0, f"{res.stdout}\n{res.stderr}"
        assert "PASS: TestZZRouteIgnoresCodeAndMessage" in res.stdout, f"{res.stdout}\n{res.stderr}"

    def test_routing_uses_tag_not_code(self):
        """L2 (discriminative): an oops error tagged "critical" with innocuous code/message must route to "pagerduty"."""
        res = self._run_driver("TestZZRouteUsesTagNotCode$")
        assert res.returncode == 0, f"{res.stdout}\n{res.stderr}"
        assert "PASS: TestZZRouteUsesTagNotCode" in res.stdout, f"{res.stdout}\n{res.stderr}"

    def test_route_precedence(self):
        """L2: critical wins over throttling/validation; throttling wins over validation."""
        res = self._run_driver(
            "TestZZRoutePrecedenceCriticalWins$|TestZZRoutePrecedenceThrottlingOverValidation$"
        )
        assert res.returncode == 0, f"{res.stdout}\n{res.stderr}"
        assert "PASS: TestZZRoutePrecedenceCriticalWins" in res.stdout, f"{res.stdout}\n{res.stderr}"
        assert "PASS: TestZZRoutePrecedenceThrottlingOverValidation" in res.stdout, f"{res.stdout}\n{res.stderr}"

    def test_route_unknown_tag_default(self):
        """L2: an oops error carrying only an unrecognized tag falls through to "default"."""
        res = self._run_driver("TestZZRouteUnknownTagDefault$")
        assert res.returncode == 0, f"{res.stdout}\n{res.stderr}"
        assert "PASS: TestZZRouteUnknownTagDefault" in res.stdout, f"{res.stdout}\n{res.stderr}"

    def test_agent_native_suite_passes(self):
        """L2: the spec's native command `go test ./examples/alertroute/...` passes overall (incl. agent's own tests + injected driver)."""
        res = _run_go(["test", "-count=1", "./examples/alertroute/..."])
        assert res.returncode == 0, f"native suite failed:\nSTDOUT:{res.stdout}\nSTDERR:{res.stderr}"
