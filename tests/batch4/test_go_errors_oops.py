"""Tests for the go-errors-oops skill task (ext4 variant):
"Build a Structured Error JSON-Envelope Module".

Verifies that the agent created a self-contained Go example module at
examples/envelope that uses github.com/samber/oops to turn a rich, structured
failure into a deterministic, JSON-serializable map ("envelope") derived from
the error's *structured accessors* (Code/Public/Domain/Tags/Context) rather
than from parsing err.Error().

Strategy
--------
L1 cases check the required deliverable files exist, are minimally well-formed,
and that go.work / go.mod wiring is present (module path, samber/oops require,
go.work `use ./examples/envelope`).

L2 cases EXERCISE the agent's actual LookupAsset / Envelope functions. Rather
than trusting the agent-authored envelope_test.go, this file injects its OWN
independent Go driver test (oops_zz_envelope_driver_test.go) into the module
and runs it with `go test`. The driver deep-validates, exactly per the
requirement doc:

  * Envelope(LookupAsset("known"))            -> nil
  * Envelope(LookupAsset("xyz"))              -> all five keys with exact values,
                                                 context["asset_id"] == "xyz",
                                                 tags contains "registry"
  * Envelope(errors.New("boom"))              -> code "" and message "boom"
  * message is the STATIC public message and never contains the variable
    asset_id (no interpolation); the id appears ONLY under context
  * the map is json.Marshal-able and marshalling the same error twice yields
    BYTE-IDENTICAL JSON (determinism / round-trip stability)
  * Envelope is derived from structured accessors, not err.Error(): two
    different asset ids produce an identical "message" but differing
    context["asset_id"].

A naive solution that string-parses err.Error(), that places the asset id into
"message", that returns a non-nil map for a nil error, or that produces
non-deterministic JSON, fails these tests. The driver is removed in teardown.
"""

import os
import re
import subprocess

import pytest

REPO_DIR = "/workspace/oops"
MODULE_DIR = os.path.join(REPO_DIR, "examples", "envelope")
ENVELOPE_GO = os.path.join(MODULE_DIR, "envelope.go")
ENVELOPE_TEST_GO = os.path.join(MODULE_DIR, "envelope_test.go")
MODULE_GO_MOD = os.path.join(MODULE_DIR, "go.mod")
GO_WORK = os.path.join(REPO_DIR, "go.work")

DRIVER_NAME = "oops_zz_envelope_driver_test.go"
DRIVER_PATH = os.path.join(MODULE_DIR, DRIVER_NAME)

# Independent driver test. Package name is filled in at write time to match the
# agent's chosen package. It exercises LookupAsset / Envelope directly.
DRIVER_TEMPLATE = r'''package %(pkg)s

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"testing"
)

func zzToString(v any) string {
	if v == nil {
		return ""
	}
	if s, ok := v.(string); ok {
		return s
	}
	return fmt.Sprint(v)
}

// TestZZNilCase: a resolvable asset must yield a nil envelope.
func TestZZNilCase(t *testing.T) {
	if env := Envelope(LookupAsset("known")); env != nil {
		t.Fatalf("Envelope(LookupAsset(\"known\")) = %%v, want nil", env)
	}
	// And LookupAsset("known") itself must be nil.
	if err := LookupAsset("known"); err != nil {
		t.Fatalf("LookupAsset(\"known\") = %%v, want nil error", err)
	}
}

// TestZZNilErrorEnvelope: Envelope(nil) must be nil regardless of LookupAsset.
func TestZZNilErrorEnvelope(t *testing.T) {
	if env := Envelope(nil); env != nil {
		t.Fatalf("Envelope(nil) = %%v, want nil", env)
	}
}

// TestZZOopsAllKeys: the oops failure path must populate all five keys exactly.
func TestZZOopsAllKeys(t *testing.T) {
	err := LookupAsset("xyz")
	if err == nil {
		t.Fatalf("LookupAsset(\"xyz\") returned nil, want an error")
	}
	env := Envelope(err)
	if env == nil {
		t.Fatalf("Envelope(LookupAsset(\"xyz\")) = nil, want a map")
	}

	if got := zzToString(env["code"]); got != "asset_missing" {
		t.Fatalf("env[code] = %%q, want asset_missing", got)
	}
	if got := zzToString(env["message"]); got != "The requested asset is unavailable." {
		t.Fatalf("env[message] = %%q, want %%q", got, "The requested asset is unavailable.")
	}
	if got := zzToString(env["domain"]); got != "asset-registry" {
		t.Fatalf("env[domain] = %%q, want asset-registry", got)
	}

	// tags -> []string containing "registry".
	tagsRaw, ok := env["tags"]
	if !ok {
		t.Fatalf("env missing key tags; got %%v", env)
	}
	tags, ok := tagsRaw.([]string)
	if !ok {
		t.Fatalf("env[tags] has type %%T, want []string", tagsRaw)
	}
	foundReg := false
	for _, tg := range tags {
		if tg == "registry" {
			foundReg = true
		}
	}
	if !foundReg {
		t.Fatalf("env[tags] = %%v, want it to contain \"registry\"", tags)
	}

	// context -> map[string]any with asset_id == "xyz".
	ctxRaw, ok := env["context"]
	if !ok {
		t.Fatalf("env missing key context; got %%v", env)
	}
	ctx, ok := ctxRaw.(map[string]any)
	if !ok {
		t.Fatalf("env[context] has type %%T, want map[string]any", ctxRaw)
	}
	if got := zzToString(ctx["asset_id"]); got != "xyz" {
		t.Fatalf("env[context][asset_id] = %%q, want xyz", got)
	}
}

// TestZZPlainErrorFallback: a non-oops error -> code "" and message err.Error().
func TestZZPlainErrorFallback(t *testing.T) {
	env := Envelope(errors.New("boom"))
	if env == nil {
		t.Fatalf("Envelope(errors.New(\"boom\")) = nil, want a map")
	}
	if got := zzToString(env["code"]); got != "" {
		t.Fatalf("env[code] = %%q, want empty string for plain error", got)
	}
	if got := zzToString(env["message"]); got != "boom" {
		t.Fatalf("env[message] = %%q, want boom", got)
	}
}

// TestZZNoInterpolation: the message is the STATIC public message; the variable
// id appears only under context, never inside message. Derived from structured
// accessors, not err.Error().
func TestZZNoInterpolation(t *testing.T) {
	env := Envelope(LookupAsset("super-secret-id-123"))
	if env == nil {
		t.Fatalf("Envelope(LookupAsset(\"super-secret-id-123\")) = nil")
	}
	msg := zzToString(env["message"])
	if msg != "The requested asset is unavailable." {
		t.Fatalf("env[message] = %%q, want static public message", msg)
	}
	// The variable id must NOT leak into the message.
	if zzIndexOf(msg, "super-secret-id-123") >= 0 {
		t.Fatalf("env[message] %%q must not contain the variable asset id", msg)
	}
	ctx, _ := env["context"].(map[string]any)
	if got := zzToString(ctx["asset_id"]); got != "super-secret-id-123" {
		t.Fatalf("env[context][asset_id] = %%q, want super-secret-id-123", got)
	}
}

// TestZZStructuredNotParsed: two different ids yield IDENTICAL message but
// DIFFERING context[asset_id]. This kills a string-parsing implementation that
// derives message from err.Error() (which embeds the id).
func TestZZStructuredNotParsed(t *testing.T) {
	a := Envelope(LookupAsset("alpha"))
	b := Envelope(LookupAsset("bravo"))
	if a == nil || b == nil {
		t.Fatalf("Envelope returned nil for a failure path")
	}
	if zzToString(a["message"]) != zzToString(b["message"]) {
		t.Fatalf("message differs across ids (%%q vs %%q); must be static",
			zzToString(a["message"]), zzToString(b["message"]))
	}
	if zzToString(a["code"]) != "asset_missing" || zzToString(b["code"]) != "asset_missing" {
		t.Fatalf("code must be asset_missing for both; got %%q / %%q",
			zzToString(a["code"]), zzToString(b["code"]))
	}
	ca, _ := a["context"].(map[string]any)
	cb, _ := b["context"].(map[string]any)
	if zzToString(ca["asset_id"]) != "alpha" {
		t.Fatalf("a context asset_id = %%q, want alpha", zzToString(ca["asset_id"]))
	}
	if zzToString(cb["asset_id"]) != "bravo" {
		t.Fatalf("b context asset_id = %%q, want bravo", zzToString(cb["asset_id"]))
	}
	if zzToString(ca["asset_id"]) == zzToString(cb["asset_id"]) {
		t.Fatalf("context asset_id must differ across the two ids")
	}
}

// TestZZJSONSerializable: the envelope must marshal without error.
func TestZZJSONSerializable(t *testing.T) {
	env := Envelope(LookupAsset("a"))
	if env == nil {
		t.Fatalf("Envelope(LookupAsset(\"a\")) = nil")
	}
	raw, err := json.Marshal(env)
	if err != nil {
		t.Fatalf("json.Marshal(envelope) error: %%v", err)
	}
	if len(raw) == 0 {
		t.Fatalf("json.Marshal produced empty output")
	}
	// Sanity: the marshalled JSON must carry the structured data.
	var back map[string]any
	if err := json.Unmarshal(raw, &back); err != nil {
		t.Fatalf("round-trip Unmarshal error: %%v on %%s", err, raw)
	}
	if zzToString(back["code"]) != "asset_missing" {
		t.Fatalf("unmarshalled code = %%q, want asset_missing", zzToString(back["code"]))
	}
}

// TestZZJSONDeterministic: marshalling the SAME error twice must be byte-identical.
func TestZZJSONDeterministic(t *testing.T) {
	r1, err := json.Marshal(Envelope(LookupAsset("a")))
	if err != nil {
		t.Fatalf("first marshal error: %%v", err)
	}
	r2, err := json.Marshal(Envelope(LookupAsset("a")))
	if err != nil {
		t.Fatalf("second marshal error: %%v", err)
	}
	if !bytes.Equal(r1, r2) {
		t.Fatalf("JSON not deterministic:\n  %%s\n  %%s", r1, r2)
	}
}

func zzIndexOf(s, sub string) int {
	if len(sub) == 0 {
		return -1
	}
	for i := 0; i+len(sub) <= len(s); i++ {
		if s[i:i+len(sub)] == sub {
			return i
		}
	}
	return -1
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
    """Read the package name the agent used in envelope.go."""
    try:
        with open(ENVELOPE_GO, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                m = re.match(r"\s*package\s+([A-Za-z_][A-Za-z0-9_]*)", line)
                if m:
                    return m.group(1)
    except OSError:
        pass
    return "envelope"


@pytest.fixture(scope="module", autouse=True)
def _driver_lifecycle():
    """Install the independent Go driver test, then remove it on teardown."""
    pkg = "envelope"
    if os.path.isfile(ENVELOPE_GO):
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
        """L1: the examples/envelope module directory was created."""
        assert os.path.isdir(MODULE_DIR), f"missing module dir {MODULE_DIR}"

    def test_envelope_go_exists(self):
        """L1: envelope.go declares a package and LookupAsset + Envelope funcs."""
        assert os.path.isfile(ENVELOPE_GO), "missing examples/envelope/envelope.go"
        with open(ENVELOPE_GO, encoding="utf-8", errors="replace") as f:
            src = f.read()
        assert re.search(r"\bpackage\s+\w+", src), "no package clause in envelope.go"
        assert re.search(r"func\s+LookupAsset\s*\(", src), "no LookupAsset function"
        assert re.search(r"func\s+Envelope\s*\(", src), "no Envelope function"

    def test_envelope_test_exists(self):
        """L1: the agent authored envelope_test.go as required."""
        assert os.path.isfile(ENVELOPE_TEST_GO), "missing examples/envelope/envelope_test.go"

    def test_go_mod_declares_module(self):
        """L1: go.mod declares the exact module path and requires samber/oops."""
        assert os.path.isfile(MODULE_GO_MOD), "missing examples/envelope/go.mod"
        with open(MODULE_GO_MOD, encoding="utf-8", errors="replace") as f:
            mod = f.read()
        assert "module github.com/samber/oops/examples/envelope" in mod, mod
        assert "github.com/samber/oops" in mod, "go.mod must require github.com/samber/oops"

    def test_go_work_lists_module(self):
        """L1: go.work uses ./examples/envelope so the in-repo lib resolves."""
        assert os.path.isfile(GO_WORK), "missing go.work"
        with open(GO_WORK, encoding="utf-8", errors="replace") as f:
            work = f.read()
        assert "./examples/envelope" in work, "go.work does not use ./examples/envelope"

    def test_module_compiles(self):
        """L1/L2: the new module builds against the in-repo library."""
        res = _run_go(["build", "./examples/envelope/..."])
        assert res.returncode == 0, (
            f"build failed:\nSTDOUT:{res.stdout}\nSTDERR:{res.stderr}"
        )

    # ---------- L2: behavior, driven by the injected independent test ----------

    def _run_driver(self, run_filter, timeout=600):
        return _run_go(
            ["test", "-v", "-count=1", "-run", run_filter, "./examples/envelope/..."],
            timeout=timeout,
        )

    def test_nil_cases(self):
        """L2: Envelope(LookupAsset("known")) and Envelope(nil) both return nil."""
        res = self._run_driver("TestZZNilCase$|TestZZNilErrorEnvelope$")
        assert res.returncode == 0, f"{res.stdout}\n{res.stderr}"
        assert "PASS: TestZZNilCase" in res.stdout, (
            f"driver test did not run/pass:\n{res.stdout}\n{res.stderr}"
        )

    def test_oops_all_keys(self):
        """L2: oops failure -> all five keys exact (code/message/domain/tags/context)."""
        res = self._run_driver("TestZZOopsAllKeys$")
        assert res.returncode == 0, f"{res.stdout}\n{res.stderr}"
        assert "PASS: TestZZOopsAllKeys" in res.stdout, (
            f"all-keys driver did not pass:\n{res.stdout}\n{res.stderr}"
        )

    def test_plain_error_fallback(self):
        """L2: non-oops error -> code "" and message == err.Error()."""
        res = self._run_driver("TestZZPlainErrorFallback$")
        assert res.returncode == 0, f"{res.stdout}\n{res.stderr}"

    def test_no_interpolation(self):
        """L2: message is the static public message; the variable id is not in it."""
        res = self._run_driver("TestZZNoInterpolation$")
        assert res.returncode == 0, f"{res.stdout}\n{res.stderr}"

    def test_structured_not_parsed(self):
        """L2: differing ids -> identical message, differing context[asset_id]
        (kills an err.Error()-parsing implementation)."""
        res = self._run_driver("TestZZStructuredNotParsed$")
        assert res.returncode == 0, f"{res.stdout}\n{res.stderr}"

    def test_json_serializable(self):
        """L2: the envelope marshals to JSON and round-trips its structured data."""
        res = self._run_driver("TestZZJSONSerializable$")
        assert res.returncode == 0, f"{res.stdout}\n{res.stderr}"

    def test_json_deterministic(self):
        """L2: marshalling the same error twice yields byte-identical JSON."""
        res = self._run_driver("TestZZJSONDeterministic$")
        assert res.returncode == 0, f"{res.stdout}\n{res.stderr}"

    def test_agent_native_suite_passes(self):
        """L2: the spec's native command `go test ./examples/envelope/...` passes."""
        res = _run_go(["test", "-count=1", "./examples/envelope/..."])
        assert res.returncode == 0, (
            f"native suite failed:\nSTDOUT:{res.stdout}\nSTDERR:{res.stderr}"
        )
