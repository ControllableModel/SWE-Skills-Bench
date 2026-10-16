"""Benchmark test for skill `go-swagger-codegen` (variant ext5).

Task: coerce boolean literals in OpenAPI vendor-extension parameters.
`setExtensionParam` in swaggo/swag's `operation.go` parses a comma-separated
extension attribute (e.g. `x-nullable=true,x-order=3`) into a
`spec.Extensions` map.  Today every `key=value` pair is stored with the value
as a *raw string*, so `x-nullable=true` serialises as the JSON string
`"true"`.  This variant requires that an explicit value of exactly `true`
or `false` (case-sensitive, lowercase) be stored as a Go `bool`, while every
other value (`3`, `True`, `yes`, ...) stays a string.  Pre-existing behaviour
(bare `key` -> bool true, `!key` -> bool false) must be preserved.

Verification strategy
---------------------
The agent edits `operation.go` (and adds a `TestSetExtensionParam` to
`operation_test.go`) inside REPO_DIR = /workspace/swag.  Rather than trust the
test file the agent itself may write, these tests INJECT an independent
in-package Go test driver (`package swag`) into REPO_DIR and run it with the
repo's native toolchain (`go test`).  Each driver calls the package-internal
`setExtensionParam(...)` directly and *type-asserts* the resulting
`spec.Extensions` values, distinguishing a real `bool` from the string
`"true"`/`"false"`.  A naive implementation that stores every value as a
string (the current behaviour) FAILS these assertions, as does one that
over-coerces `True`/`1`/`yes` or that breaks the bare-key / `!key` cases.

L1: deliverable files exist and are well-formed; the package compiles; the
    agent added a `TestSetExtensionParam`.
L2: dynamic execution of injected `go test` drivers that type-check the stored
    extension values (bool vs string), plus the repo's own
    `go test -run TestSetExtensionParam ./...` native acceptance command.
"""

import os
import subprocess
import textwrap
import uuid

import pytest

REPO_DIR = "/workspace/swag"
GO_TIMEOUT = 420


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _go_env():
    env = dict(os.environ)
    env.setdefault("GOFLAGS", "-mod=mod")
    env["CGO_ENABLED"] = "0"
    return env


def _run_go(args, timeout=GO_TIMEOUT):
    """Run a `go ...` command in REPO_DIR and return CompletedProcess."""
    return subprocess.run(
        ["go", *args],
        cwd=REPO_DIR,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=_go_env(),
    )


def _write_driver(body: str) -> str:
    """Write an in-package Go test file (package swag) into REPO_DIR.

    Returns the absolute path so the caller can remove it afterwards.
    `body` must contain one or more `func TestXxx(t *testing.T) { ... }`.
    The header imports `testing`, `fmt`, and `spec` (the extension map type),
    plus a tiny generic helper used by every driver to assert value types.
    """
    fname = f"zz_bench_{uuid.uuid4().hex[:12]}_test.go"
    path = os.path.join(REPO_DIR, fname)
    header = textwrap.dedent(
        """\
        package swag

        import (
        \t"fmt"
        \t"testing"

        \t"github.com/go-openapi/spec"
        )

        // zzBoolVal returns (boolValue, isBool) for the extension entry under
        // any of the supplied candidate keys (go-openapi may lowercase keys).
        func zzBoolVal(ext spec.Extensions, keys ...string) (bool, bool, bool) {
        \tfor _, k := range keys {
        \t\tif v, present := ext[k]; present {
        \t\t\tb, isBool := v.(bool)
        \t\t\treturn b, isBool, true
        \t\t}
        \t}
        \treturn false, false, false
        }

        // zzStrVal returns (stringValue, isString, present) for the entry.
        func zzStrVal(ext spec.Extensions, keys ...string) (string, bool, bool) {
        \tfor _, k := range keys {
        \t\tif v, present := ext[k]; present {
        \t\t\ts, isStr := v.(string)
        \t\t\treturn s, isStr, true
        \t\t}
        \t}
        \treturn "", false, false
        }

        var _ = fmt.Sprintf

        """
    )
    with open(path, "w") as fh:
        fh.write(header + textwrap.dedent(body))
    return path


def _run_driver(test_name: str, body: str):
    """Inject driver, run `go test -run <test_name>`, clean up."""
    path = _write_driver(body)
    try:
        return _run_go(
            ["test", "-run", f"^{test_name}$", "-v", "-count=1", "."]
        )
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def _purge_stale_drivers():
    """Remove any leftover injected driver files (defensive, e.g. on NFS)."""
    try:
        for name in os.listdir(REPO_DIR):
            if name.startswith("zz_bench_") and name.endswith("_test.go"):
                try:
                    os.remove(os.path.join(REPO_DIR, name))
                except OSError:
                    pass
    except OSError:
        pass


# --------------------------------------------------------------------------- #
# Module-scope sanity: deps available / package compiles.
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module", autouse=True)
def _ensure_build():
    assert os.path.isdir(REPO_DIR), f"REPO_DIR missing: {REPO_DIR}"
    _purge_stale_drivers()
    # `go build ./...` warms the module cache and proves the agent's edit
    # compiles. It does not compile *_test.go, so it is immune to drivers.
    proc = _run_go(["build", "./..."], timeout=GO_TIMEOUT)
    assert proc.returncode == 0, (
        "repository does not build after the change:\n"
        f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    )
    yield
    _purge_stale_drivers()


class TestGoSwaggerCodegen:
    REPO_DIR = "/workspace/swag"

    # ------------------------------------------------------------------ #
    # L1 — deliverables exist and are well-formed.
    # ------------------------------------------------------------------ #
    def test_operation_source_exists(self):
        """L1: operation.go (the file to modify) exists and is non-trivial."""
        path = os.path.join(self.REPO_DIR, "operation.go")
        assert os.path.isfile(path), f"missing {path}"
        assert os.path.getsize(path) > 1000, "operation.go unexpectedly small"

    def test_set_extension_param_still_present(self):
        """L1: the setExtensionParam function definition is still present."""
        path = os.path.join(self.REPO_DIR, "operation.go")
        with open(path) as fh:
            content = fh.read()
        assert "func setExtensionParam(" in content, (
            "setExtensionParam must remain defined in operation.go"
        )

    def test_new_test_named_correctly(self):
        """L1: a `TestSetExtensionParam` was added to operation_test.go
        (the doc requires the new test carry exactly that name)."""
        path = os.path.join(self.REPO_DIR, "operation_test.go")
        assert os.path.isfile(path), f"missing {path}"
        with open(path) as fh:
            content = fh.read()
        assert "func TestSetExtensionParam(" in content, (
            "operation_test.go must contain func TestSetExtensionParam"
        )

    def test_package_compiles(self):
        """L1: the swag package and its commands compile after the change."""
        _purge_stale_drivers()
        proc = _run_go(["build", "./..."], timeout=GO_TIMEOUT)
        assert proc.returncode == 0, (
            f"go build ./... failed:\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    # ------------------------------------------------------------------ #
    # L2 — dynamic behaviour via injected drivers (type-checked).
    # ------------------------------------------------------------------ #
    def test_true_coerced_to_bool(self):
        """L2: `x-nullable=true` stores the boolean true, NOT the string "true".

        A naive (current) implementation stores `"true"` as a string and fails
        the `bool` type assertion below.
        """
        body = r'''
        func TestZZTrueBool(t *testing.T) {
        	ext := setExtensionParam("x-nullable=true")
        	b, isBool, present := zzBoolVal(ext, "x-nullable")
        	if !present {
        		t.Fatalf("x-nullable key missing; ext=%#v", map[string]interface{}(ext))
        	}
        	if !isBool {
        		_, isStr, _ := zzStrVal(ext, "x-nullable")
        		t.Fatalf("x-nullable value is not bool (string=%v); want Go bool true; ext=%#v", isStr, map[string]interface{}(ext))
        	}
        	if b != true {
        		t.Fatalf("x-nullable bool = %v, want true", b)
        	}
        }
        '''
        proc = _run_driver("TestZZTrueBool", body)
        assert proc.returncode == 0, (
            "x-nullable=true must be stored as Go bool true:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "PASS" in proc.stdout

    def test_false_coerced_to_bool(self):
        """L2: `x-internal=false` stores the boolean false (Go bool), not "false"."""
        body = r'''
        func TestZZFalseBool(t *testing.T) {
        	ext := setExtensionParam("x-internal=false")
        	b, isBool, present := zzBoolVal(ext, "x-internal")
        	if !present {
        		t.Fatalf("x-internal key missing; ext=%#v", map[string]interface{}(ext))
        	}
        	if !isBool {
        		t.Fatalf("x-internal value is not bool; ext=%#v", map[string]interface{}(ext))
        	}
        	if b != false {
        		t.Fatalf("x-internal bool = %v, want false", b)
        	}
        }
        '''
        proc = _run_driver("TestZZFalseBool", body)
        assert proc.returncode == 0, (
            "x-internal=false must be stored as Go bool false:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "PASS" in proc.stdout

    def test_numeric_value_stays_string(self):
        """L2: `x-order=3` stores the STRING "3" (no coercion to bool/number).

        Guards against an over-eager implementation that coerces anything.
        """
        body = r'''
        func TestZZNumberString(t *testing.T) {
        	ext := setExtensionParam("x-order=3")
        	s, isStr, present := zzStrVal(ext, "x-order")
        	if !present {
        		t.Fatalf("x-order key missing; ext=%#v", map[string]interface{}(ext))
        	}
        	if !isStr {
        		t.Fatalf("x-order value is not a string; ext=%#v", map[string]interface{}(ext))
        	}
        	if s != "3" {
        		t.Fatalf("x-order string = %q, want %q", s, "3")
        	}
        }
        '''
        proc = _run_driver("TestZZNumberString", body)
        assert proc.returncode == 0, (
            "x-order=3 must remain the string \"3\":\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "PASS" in proc.stdout

    def test_capitalized_true_stays_string(self):
        """L2: `x-name=True` (capital T) is NOT coerced; stays string "True".

        The doc mandates only exact lowercase `true`/`false` are coerced.
        """
        body = r'''
        func TestZZCapTrueString(t *testing.T) {
        	ext := setExtensionParam("x-name=True")
        	s, isStr, present := zzStrVal(ext, "x-name")
        	if !present {
        		t.Fatalf("x-name key missing; ext=%#v", map[string]interface{}(ext))
        	}
        	if !isStr {
        		t.Fatalf("x-name=True was coerced; want string \"True\"; ext=%#v", map[string]interface{}(ext))
        	}
        	if s != "True" {
        		t.Fatalf("x-name string = %q, want %q", s, "True")
        	}
        }
        '''
        proc = _run_driver("TestZZCapTrueString", body)
        assert proc.returncode == 0, (
            "x-name=True must stay the string \"True\" (no coercion):\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "PASS" in proc.stdout

    def test_truthy_lookalikes_stay_string(self):
        """L2: `TRUE`, `1`, and `yes` are all NOT coerced — they stay strings."""
        body = r'''
        func TestZZLookalikes(t *testing.T) {
        	cases := []struct {
        		attr, key, want string
        	}{
        		{"x-a=TRUE", "x-a", "TRUE"},
        		{"x-b=1", "x-b", "1"},
        		{"x-c=yes", "x-c", "yes"},
        		{"x-d=FALSE", "x-d", "FALSE"},
        		{"x-e=truex", "x-e", "truex"},
        	}
        	for _, c := range cases {
        		ext := setExtensionParam(c.attr)
        		s, isStr, present := zzStrVal(ext, c.key)
        		if !present {
        			t.Fatalf("[%s] key %s missing; ext=%#v", c.attr, c.key, map[string]interface{}(ext))
        		}
        		if !isStr {
        			t.Fatalf("[%s] value coerced away from string; ext=%#v", c.attr, map[string]interface{}(ext))
        		}
        		if s != c.want {
        			t.Fatalf("[%s] string = %q, want %q", c.attr, s, c.want)
        		}
        	}
        }
        '''
        proc = _run_driver("TestZZLookalikes", body)
        assert proc.returncode == 0, (
            "non-exact-true/false tokens must remain strings:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "PASS" in proc.stdout

    def test_bare_key_is_bool_true(self):
        """L2: a bare `x-flag` (no `=`) still stores boolean true (unchanged)."""
        body = r'''
        func TestZZBareKey(t *testing.T) {
        	ext := setExtensionParam("x-flag")
        	b, isBool, present := zzBoolVal(ext, "x-flag")
        	if !present {
        		t.Fatalf("x-flag key missing; ext=%#v", map[string]interface{}(ext))
        	}
        	if !isBool || b != true {
        		t.Fatalf("bare x-flag should be bool true; got isBool=%v val=%v; ext=%#v", isBool, b, map[string]interface{}(ext))
        	}
        }
        '''
        proc = _run_driver("TestZZBareKey", body)
        assert proc.returncode == 0, (
            "bare key must still map to bool true:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "PASS" in proc.stdout

    def test_bang_key_is_bool_false(self):
        """L2: a `!x-flag` entry still stores boolean false (unchanged), under key
        `x-flag` (the leading `!` is stripped)."""
        body = r'''
        func TestZZBangKey(t *testing.T) {
        	ext := setExtensionParam("!x-flag")
        	b, isBool, present := zzBoolVal(ext, "x-flag")
        	if !present {
        		t.Fatalf("x-flag key missing for !x-flag; ext=%#v", map[string]interface{}(ext))
        	}
        	if !isBool || b != false {
        		t.Fatalf("!x-flag should be bool false; got isBool=%v val=%v; ext=%#v", isBool, b, map[string]interface{}(ext))
        	}
        	// the literal "!x-flag" must NOT be a key
        	if _, bad := ext["!x-flag"]; bad {
        		t.Fatalf("leading '!' must be stripped from the key; ext=%#v", map[string]interface{}(ext))
        	}
        }
        '''
        proc = _run_driver("TestZZBangKey", body)
        assert proc.returncode == 0, (
            "!key must still map (stripped) to bool false:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "PASS" in proc.stdout

    def test_mixed_attribute_string_types(self):
        """L2: a multi-entry attribute mixes bool and string values correctly,
        proving per-entry coercion (not a global all-bool / all-string switch)."""
        body = r'''
        func TestZZMixed(t *testing.T) {
        	ext := setExtensionParam("x-nullable=true,x-order=3,x-internal=false,x-name=True")

        	// x-nullable -> bool true
        	if b, isBool, ok := zzBoolVal(ext, "x-nullable"); !ok || !isBool || b != true {
        		t.Fatalf("x-nullable wrong: ok=%v isBool=%v b=%v; ext=%#v", ok, isBool, b, map[string]interface{}(ext))
        	}
        	// x-internal -> bool false
        	if b, isBool, ok := zzBoolVal(ext, "x-internal"); !ok || !isBool || b != false {
        		t.Fatalf("x-internal wrong: ok=%v isBool=%v b=%v; ext=%#v", ok, isBool, b, map[string]interface{}(ext))
        	}
        	// x-order -> string "3"
        	if s, isStr, ok := zzStrVal(ext, "x-order"); !ok || !isStr || s != "3" {
        		t.Fatalf("x-order wrong: ok=%v isStr=%v s=%q; ext=%#v", ok, isStr, s, map[string]interface{}(ext))
        	}
        	// x-name -> string "True"
        	if s, isStr, ok := zzStrVal(ext, "x-name"); !ok || !isStr || s != "True" {
        		t.Fatalf("x-name wrong: ok=%v isStr=%v s=%q; ext=%#v", ok, isStr, s, map[string]interface{}(ext))
        	}
        }
        '''
        proc = _run_driver("TestZZMixed", body)
        assert proc.returncode == 0, (
            "per-entry coercion in a mixed attribute is required:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "PASS" in proc.stdout

    def test_value_after_first_equals_preserved(self):
        """L2: only the first `=` splits key/value; `true`/`false` must match the
        WHOLE remainder. `x-q=a=true` keeps the string "a=true" (not bool)."""
        body = r'''
        func TestZZFirstEquals(t *testing.T) {
        	ext := setExtensionParam("x-q=a=true")
        	s, isStr, present := zzStrVal(ext, "x-q")
        	if !present {
        		t.Fatalf("x-q key missing; ext=%#v", map[string]interface{}(ext))
        	}
        	if !isStr {
        		t.Fatalf("x-q value must be string \"a=true\", was coerced; ext=%#v", map[string]interface{}(ext))
        	}
        	if s != "a=true" {
        		t.Fatalf("x-q string = %q, want %q", s, "a=true")
        	}
        }
        '''
        proc = _run_driver("TestZZFirstEquals", body)
        assert proc.returncode == 0, (
            "remainder after the first '=' must be matched whole:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "PASS" in proc.stdout

    def test_serialized_json_is_boolean(self):
        """L2: end-to-end — JSON-marshalling the extensions yields a JSON boolean
        (`true`) for `x-nullable`, not the quoted string `"true"`.

        This is the user-visible OpenAPI output and is the strongest
        discriminator: a string-storing stub serialises `"x-nullable":"true"`.
        """
        body = r'''
        func TestZZJSONBool(t *testing.T) {
        	ext := setExtensionParam("x-nullable=true,x-order=3")
        	out, err := json.Marshal(ext)
        	if err != nil {
        		t.Fatalf("marshal err: %v", err)
        	}
        	js := string(out)
        	// boolean -> unquoted true ; string "3" -> quoted "3"
        	if !strings.Contains(js, "\"x-nullable\":true") {
        		t.Fatalf("expected JSON boolean for x-nullable, got: %s", js)
        	}
        	if strings.Contains(js, "\"x-nullable\":\"true\"") {
        		t.Fatalf("x-nullable serialised as a STRING, want boolean: %s", js)
        	}
        	if !strings.Contains(js, "\"x-order\":\"3\"") {
        		t.Fatalf("expected x-order serialised as string \"3\", got: %s", js)
        	}
        }
        '''
        # This driver needs encoding/json + strings; inject a self-contained file.
        fname = f"zz_bench_{uuid.uuid4().hex[:12]}_test.go"
        path = os.path.join(self.REPO_DIR, fname)
        header = textwrap.dedent(
            """\
            package swag

            import (
            \t"encoding/json"
            \t"strings"
            \t"testing"
            )

            """
        )
        with open(path, "w") as fh:
            fh.write(header + textwrap.dedent(body))
        try:
            proc = _run_go(["test", "-run", "^TestZZJSONBool$", "-v", "-count=1", "."])
        finally:
            try:
                os.remove(path)
            except OSError:
                pass
        assert proc.returncode == 0, (
            "JSON serialisation must emit a boolean for x-nullable:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "PASS" in proc.stdout

    def test_native_acceptance_command(self):
        """L2: the doc's native acceptance command passes (no regression):

            go test -run TestSetExtensionParam ./...
        """
        _purge_stale_drivers()
        proc = _run_go(
            ["test", "-run", "TestSetExtensionParam", "-count=1", "./..."]
        )
        assert proc.returncode == 0, (
            "native `go test -run TestSetExtensionParam ./...` failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        # `go test ./...` prints "ok" for the package(s) that ran a match.
        assert "ok" in proc.stdout, (
            f"expected a passing package line:\nSTDOUT:\n{proc.stdout}"
        )
