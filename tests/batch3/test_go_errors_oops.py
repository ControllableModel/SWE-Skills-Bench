"""Tests for the go-errors-oops skill task (ext3 variant): "Build a Config
Validation Module with Assertion Guards".

Verifies that the agent created a self-contained Go example module at
examples/configcheck that uses github.com/samber/oops to validate an in-memory
Config struct, returning the FIRST violated invariant as a richly-structured
oops error (domain "config-validation", a per-invariant Code(), and the
offending value under context key "value").

Strategy
--------
L1 cases check the required deliverable files exist, are minimally well-formed,
and that go.work / go.mod wiring is present (module path
github.com/samber/oops/examples/configcheck; go.work uses ./examples/configcheck).

L2 cases EXERCISE the agent's actual Validate function. Rather than trusting the
agent-authored configcheck_test.go, this file injects its OWN independent Go
driver test (oops_zz_bench_driver_test.go) into the module and runs it with
`go test`, deep-validating for every invariant:
  * oops.AsOops(err) ok == true,
  * Domain() == "config-validation",
  * Code() == the spec code for the violated invariant,
  * Context()["value"] == the offending value (with correct Go type),
  * short-circuit ordering (first violated invariant wins),
  * low cardinality: two different offending values for the same invariant
    produce byte-identical Error() strings but different "value" context.

A naive solution that ignores ordering, omits the "value" context, bakes the
offending value into the message string, or returns plain (non-oops) errors
fails these tests. The driver is removed in teardown.
"""

import os
import re
import subprocess

import pytest

REPO_DIR = "/workspace/oops"
MODULE_DIR = os.path.join(REPO_DIR, "examples", "configcheck")
CONFIGCHECK_GO = os.path.join(MODULE_DIR, "configcheck.go")
CONFIGCHECK_TEST_GO = os.path.join(MODULE_DIR, "configcheck_test.go")
MODULE_GO_MOD = os.path.join(MODULE_DIR, "go.mod")
GO_WORK = os.path.join(REPO_DIR, "go.work")

DRIVER_NAME = "oops_zz_bench_driver_test.go"
DRIVER_PATH = os.path.join(MODULE_DIR, DRIVER_NAME)

# Independent driver test. Package name is filled in at write time to match the
# agent's chosen package. It exercises Validate(Config{...}) directly.
DRIVER_TEMPLATE = r'''package %(pkg)s

import (
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

// zzCheck asserts a single failing invariant: domain, code, and the
// offending value carried under context key "value".
func zzCheck(t *testing.T, err error, wantCode, wantValue string) oops.OopsError {
	t.Helper()
	oe := zzAsOops(t, err)
	if got := oe.Domain(); got != "config-validation" {
		t.Fatalf("Domain() = %%q, want config-validation", got)
	}
	if got := fmt.Sprint(oe.Code()); got != wantCode {
		t.Fatalf("Code() = %%q, want %%q", got, wantCode)
	}
	ctx := oe.Context()
	v, ok := ctx["value"]
	if !ok {
		t.Fatalf("Context() missing key %%q; got %%v", "value", ctx)
	}
	if fmt.Sprint(v) != wantValue {
		t.Fatalf("Context()[value] = %%v, want %%v", v, wantValue)
	}
	return oe
}

func zzValid() Config {
	return Config{ListenPort: 8080, MaxConnections: 10, LogLevel: "info", ShutdownTimeoutSeconds: 5}
}

// ---- invariant 1: ListenPort in [1,65535] ----

func TestZZPortOutOfRange(t *testing.T) {
	c := zzValid()
	c.ListenPort = 0
	zzCheck(t, Validate(c), "port_out_of_range", "0")

	c = zzValid()
	c.ListenPort = 70000
	zzCheck(t, Validate(c), "port_out_of_range", "70000")

	// Boundary: 1 and 65535 are valid; 0 and 65536 are not.
	c = zzValid()
	c.ListenPort = 1
	if err := Validate(c); err != nil {
		t.Fatalf("ListenPort=1 should be valid, got %%v", err)
	}
	c = zzValid()
	c.ListenPort = 65535
	if err := Validate(c); err != nil {
		t.Fatalf("ListenPort=65535 should be valid, got %%v", err)
	}
	c = zzValid()
	c.ListenPort = 65536
	zzCheck(t, Validate(c), "port_out_of_range", "65536")
}

// ---- invariant 2: MaxConnections > 0 ----

func TestZZNonPositiveMaxConnections(t *testing.T) {
	c := zzValid()
	c.MaxConnections = -1
	zzCheck(t, Validate(c), "non_positive_max_connections", "-1")

	c = zzValid()
	c.MaxConnections = 0
	zzCheck(t, Validate(c), "non_positive_max_connections", "0")

	// Boundary: 1 is valid.
	c = zzValid()
	c.MaxConnections = 1
	if err := Validate(c); err != nil {
		t.Fatalf("MaxConnections=1 should be valid, got %%v", err)
	}
}

// ---- invariant 3: LogLevel in {debug,info,warn,error} ----

func TestZZInvalidLogLevel(t *testing.T) {
	c := zzValid()
	c.LogLevel = "trace"
	zzCheck(t, Validate(c), "invalid_log_level", "trace")

	c = zzValid()
	c.LogLevel = ""
	zzCheck(t, Validate(c), "invalid_log_level", "")

	for _, lvl := range []string{"debug", "info", "warn", "error"} {
		c = zzValid()
		c.LogLevel = lvl
		if err := Validate(c); err != nil {
			t.Fatalf("LogLevel=%%q should be valid, got %%v", lvl, err)
		}
	}
}

// ---- invariant 4: ShutdownTimeoutSeconds in [0,300] ----

func TestZZShutdownTimeoutOutOfRange(t *testing.T) {
	c := zzValid()
	c.ShutdownTimeoutSeconds = 9999
	zzCheck(t, Validate(c), "shutdown_timeout_out_of_range", "9999")

	c = zzValid()
	c.ShutdownTimeoutSeconds = -1
	zzCheck(t, Validate(c), "shutdown_timeout_out_of_range", "-1")

	// Boundary: 0 and 300 inclusive are valid; 301 is not.
	c = zzValid()
	c.ShutdownTimeoutSeconds = 0
	if err := Validate(c); err != nil {
		t.Fatalf("ShutdownTimeoutSeconds=0 should be valid, got %%v", err)
	}
	c = zzValid()
	c.ShutdownTimeoutSeconds = 300
	if err := Validate(c); err != nil {
		t.Fatalf("ShutdownTimeoutSeconds=300 should be valid, got %%v", err)
	}
	c = zzValid()
	c.ShutdownTimeoutSeconds = 301
	zzCheck(t, Validate(c), "shutdown_timeout_out_of_range", "301")
}

// ---- ordering / short-circuit ----

func TestZZOrderingPortBeatsLogLevel(t *testing.T) {
	// Violates invariant 1 (port) AND invariant 3 (loglevel): must report port.
	c := Config{ListenPort: 0, MaxConnections: 10, LogLevel: "trace", ShutdownTimeoutSeconds: 5}
	zzCheck(t, Validate(c), "port_out_of_range", "0")
}

func TestZZOrderingMaxConnBeatsTimeout(t *testing.T) {
	// Violates invariant 2 (maxconn) AND invariant 4 (timeout): must report maxconn.
	c := Config{ListenPort: 8080, MaxConnections: 0, LogLevel: "info", ShutdownTimeoutSeconds: 9999}
	zzCheck(t, Validate(c), "non_positive_max_connections", "0")
}

func TestZZOrderingLogLevelBeatsTimeout(t *testing.T) {
	// Violates invariant 3 (loglevel) AND invariant 4 (timeout): must report loglevel.
	c := Config{ListenPort: 8080, MaxConnections: 10, LogLevel: "nope", ShutdownTimeoutSeconds: -5}
	zzCheck(t, Validate(c), "invalid_log_level", "nope")
}

func TestZZAllFourViolatedReportsPort(t *testing.T) {
	// Every invariant violated: the very first (port) must win.
	c := Config{ListenPort: 0, MaxConnections: 0, LogLevel: "bad", ShutdownTimeoutSeconds: 9999}
	zzCheck(t, Validate(c), "port_out_of_range", "0")
}

// ---- success ----

func TestZZSuccess(t *testing.T) {
	c := Config{ListenPort: 8080, MaxConnections: 10, LogLevel: "warn", ShutdownTimeoutSeconds: 30}
	if err := Validate(c); err != nil {
		t.Fatalf("fully valid config returned error: %%v", err)
	}
	// Another valid combo at the extreme valid boundaries.
	c = Config{ListenPort: 1, MaxConnections: 1, LogLevel: "error", ShutdownTimeoutSeconds: 0}
	if err := Validate(c); err != nil {
		t.Fatalf("boundary-valid config returned error: %%v", err)
	}
}

// ---- low cardinality: message constant per invariant, value lives in context ----

func TestZZCardinalityPort(t *testing.T) {
	c1 := zzValid()
	c1.ListenPort = 0
	c2 := zzValid()
	c2.ListenPort = 70000
	e1 := Validate(c1)
	e2 := Validate(c2)
	o1 := zzAsOops(t, e1)
	o2 := zzAsOops(t, e2)
	// Same invariant -> byte-identical Error() string.
	if e1.Error() != e2.Error() {
		t.Fatalf("Error() differs across same-invariant failures: %%q vs %%q", e1.Error(), e2.Error())
	}
	// But the structured "value" must differ.
	if fmt.Sprint(o1.Context()["value"]) == fmt.Sprint(o2.Context()["value"]) {
		t.Fatalf("expected differing value context across the two failures")
	}
	if fmt.Sprint(o1.Context()["value"]) != "0" || fmt.Sprint(o2.Context()["value"]) != "70000" {
		t.Fatalf("value context = %%v / %%v, want 0 / 70000", o1.Context()["value"], o2.Context()["value"])
	}
	// And the message must NOT contain the variable numbers (no interpolation).
	msg := e1.Error()
	for _, frag := range []string{"70000", "0"} {
		if zzContains(msg, frag) {
			t.Fatalf("Error() message %%q must not contain variable data %%q", msg, frag)
		}
	}
}

func TestZZCardinalityLogLevel(t *testing.T) {
	c1 := zzValid()
	c1.LogLevel = "trace"
	c2 := zzValid()
	c2.LogLevel = "verbose"
	e1 := Validate(c1)
	e2 := Validate(c2)
	o1 := zzAsOops(t, e1)
	o2 := zzAsOops(t, e2)
	if e1.Error() != e2.Error() {
		t.Fatalf("invalid_log_level Error() differs across payloads: %%q vs %%q", e1.Error(), e2.Error())
	}
	if fmt.Sprint(o1.Context()["value"]) == fmt.Sprint(o2.Context()["value"]) {
		t.Fatalf("expected differing value context (trace vs verbose)")
	}
	msg := e1.Error()
	for _, frag := range []string{"trace", "verbose"} {
		if zzContains(msg, frag) {
			t.Fatalf("Error() message %%q must not contain variable data %%q", msg, frag)
		}
	}
}

// ---- the four codes/messages are mutually distinct ----

func TestZZCodesDistinct(t *testing.T) {
	cPort := zzValid()
	cPort.ListenPort = 0
	cConn := zzValid()
	cConn.MaxConnections = 0
	cLog := zzValid()
	cLog.LogLevel = "bad"
	cTimeout := zzValid()
	cTimeout.ShutdownTimeoutSeconds = 9999

	codes := []string{
		fmt.Sprint(zzAsOops(t, Validate(cPort)).Code()),
		fmt.Sprint(zzAsOops(t, Validate(cConn)).Code()),
		fmt.Sprint(zzAsOops(t, Validate(cLog)).Code()),
		fmt.Sprint(zzAsOops(t, Validate(cTimeout)).Code()),
	}
	want := []string{
		"port_out_of_range",
		"non_positive_max_connections",
		"invalid_log_level",
		"shutdown_timeout_out_of_range",
	}
	for i := range want {
		if codes[i] != want[i] {
			t.Fatalf("code[%%d] = %%q, want %%q", i, codes[i], want[i])
		}
	}
	seen := map[string]bool{}
	for _, c := range codes {
		if seen[c] {
			t.Fatalf("codes must be mutually distinct, duplicate: %%q", c)
		}
		seen[c] = true
	}
	// Messages must also be mutually distinct across invariants.
	msgs := []string{
		Validate(cPort).Error(),
		Validate(cConn).Error(),
		Validate(cLog).Error(),
		Validate(cTimeout).Error(),
	}
	seenMsg := map[string]bool{}
	for _, m := range msgs {
		if seenMsg[m] {
			t.Fatalf("Error() messages must be distinct per invariant, duplicate: %%q", m)
		}
		seenMsg[m] = true
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
    """Read the package name the agent used in configcheck.go."""
    with open(CONFIGCHECK_GO, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            m = re.match(r"\s*package\s+([A-Za-z_][A-Za-z0-9_]*)", line)
            if m:
                return m.group(1)
    return "configcheck"


@pytest.fixture(scope="module", autouse=True)
def _driver_lifecycle():
    """Install the independent Go driver test, then remove it on teardown."""
    pkg = "configcheck"
    if os.path.isfile(CONFIGCHECK_GO):
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
        """L1: the examples/configcheck module directory was created."""
        assert os.path.isdir(MODULE_DIR), f"missing module dir {MODULE_DIR}"

    def test_configcheck_go_exists(self):
        """L1: configcheck.go exists; declares a package, Config type, Validate func."""
        assert os.path.isfile(CONFIGCHECK_GO), "missing examples/configcheck/configcheck.go"
        with open(CONFIGCHECK_GO, encoding="utf-8", errors="replace") as f:
            src = f.read()
        assert re.search(r"\bpackage\s+\w+", src), "no package clause in configcheck.go"
        assert re.search(r"type\s+Config\s+struct", src), "no Config struct type"
        assert re.search(r"func\s+Validate\s*\(", src), "no Validate function"

    def test_go_mod_declares_module(self):
        """L1: go.mod declares the exact module path and requires samber/oops."""
        assert os.path.isfile(MODULE_GO_MOD), "missing examples/configcheck/go.mod"
        with open(MODULE_GO_MOD, encoding="utf-8", errors="replace") as f:
            mod = f.read()
        assert "module github.com/samber/oops/examples/configcheck" in mod, mod
        assert "github.com/samber/oops" in mod

    def test_go_work_lists_module(self):
        """L1: go.work uses ./examples/configcheck so the in-repo lib resolves."""
        assert os.path.isfile(GO_WORK), "missing go.work"
        with open(GO_WORK, encoding="utf-8", errors="replace") as f:
            work = f.read()
        assert "./examples/configcheck" in work, "go.work does not use ./examples/configcheck"

    def test_module_compiles(self):
        """L1/L2: the new module builds against the in-repo library."""
        res = _run_go(["build", "./examples/configcheck/..."])
        assert res.returncode == 0, f"build failed:\nSTDOUT:{res.stdout}\nSTDERR:{res.stderr}"

    # ---------- L2: behavior, driven by the injected independent test ----------

    def _run_driver(self, run_filter):
        res = _run_go(
            ["test", "-v", "-count=1", "-run", run_filter, "./examples/configcheck/..."]
        )
        return res

    def test_port_out_of_range_behavior(self):
        """L2: ListenPort outside [1,65535] -> code port_out_of_range, context value, boundaries."""
        res = self._run_driver("TestZZPortOutOfRange$")
        assert res.returncode == 0, f"{res.stdout}\n{res.stderr}"
        assert "PASS: TestZZPortOutOfRange" in res.stdout, (
            f"driver test did not run/pass:\n{res.stdout}\n{res.stderr}"
        )

    def test_non_positive_max_connections_behavior(self):
        """L2: MaxConnections <= 0 -> code non_positive_max_connections, context value."""
        res = self._run_driver("TestZZNonPositiveMaxConnections$")
        assert res.returncode == 0, f"{res.stdout}\n{res.stderr}"

    def test_invalid_log_level_behavior(self):
        """L2: LogLevel not in the allowed set -> code invalid_log_level, context value; valid set accepted."""
        res = self._run_driver("TestZZInvalidLogLevel$")
        assert res.returncode == 0, f"{res.stdout}\n{res.stderr}"

    def test_shutdown_timeout_out_of_range_behavior(self):
        """L2: ShutdownTimeoutSeconds outside [0,300] -> code shutdown_timeout_out_of_range, boundaries."""
        res = self._run_driver("TestZZShutdownTimeoutOutOfRange$")
        assert res.returncode == 0, f"{res.stdout}\n{res.stderr}"

    def test_ordering_short_circuit(self):
        """L2: multi-violation configs report the FIRST violated invariant (4 ordering cases)."""
        res = self._run_driver(
            "TestZZOrderingPortBeatsLogLevel$|TestZZOrderingMaxConnBeatsTimeout$|"
            "TestZZOrderingLogLevelBeatsTimeout$|TestZZAllFourViolatedReportsPort$"
        )
        assert res.returncode == 0, f"{res.stdout}\n{res.stderr}"
        for name in (
            "TestZZOrderingPortBeatsLogLevel",
            "TestZZOrderingMaxConnBeatsTimeout",
            "TestZZOrderingLogLevelBeatsTimeout",
            "TestZZAllFourViolatedReportsPort",
        ):
            assert f"PASS: {name}" in res.stdout, f"{name} did not pass:\n{res.stdout}\n{res.stderr}"

    def test_success_case(self):
        """L2: fully valid configs (incl. valid boundaries) return nil."""
        res = self._run_driver("TestZZSuccess$")
        assert res.returncode == 0, f"{res.stdout}\n{res.stderr}"

    def test_cardinality_port(self):
        """L2: two out-of-range ports -> identical Error(), differing value context, no interpolation."""
        res = self._run_driver("TestZZCardinalityPort$")
        assert res.returncode == 0, f"{res.stdout}\n{res.stderr}"

    def test_cardinality_log_level(self):
        """L2: two invalid log levels -> identical Error(), differing value context, no interpolation."""
        res = self._run_driver("TestZZCardinalityLogLevel$")
        assert res.returncode == 0, f"{res.stdout}\n{res.stderr}"

    def test_codes_and_messages_distinct(self):
        """L2: the four invariant codes (and their Error() messages) are mutually distinct."""
        res = self._run_driver("TestZZCodesDistinct$")
        assert res.returncode == 0, f"{res.stdout}\n{res.stderr}"

    def test_agent_native_suite_passes(self):
        """L2: the spec's native command `go test ./examples/configcheck/...` passes overall."""
        res = _run_go(["test", "-count=1", "./examples/configcheck/..."])
        assert res.returncode == 0, f"native suite failed:\nSTDOUT:{res.stdout}\nSTDERR:{res.stderr}"
