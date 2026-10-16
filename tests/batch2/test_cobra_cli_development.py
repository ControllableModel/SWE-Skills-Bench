"""Tests for the `cobra-cli-development` skill (variant ext2).

Skill task: add a brand-new, fully offline `gh units` cobra command group to the
GitHub CLI (github.com/cli/cli/v2). It exposes a single `convert <amount> <from>
<to>` subcommand that converts between units drawn from a static in-process table
with two families -- a byte family (`b`, `kb`, `mb`, `gb` as powers of 1024) and
a duration family (`s`, `m`, `h`, `d`). The parent prints its own help with no
subcommand; `convert` requires EXACTLY three positional args (cobra arg-count
error otherwise), then a single custom positional-args validator checks that the
amount is a non-negative number and that `<from>`/`<to>` exist in the table AND
belong to the same family (cross-family rejected, no stdout). On success it
prints `amount * (from_multiplier / to_multiplier)` on one line with trailing
zeros trimmed (e.g. `1024 b kb` -> `1`). Unit matching is case-insensitive. The
group is registered on the root command and requires no auth / no network.

Verification strategy (discriminative):
  * L1 checks confirm the deliverable files exist, are well-formed Go, expose the
    `NewCmdUnits(f *cmdutil.Factory) *cobra.Command` constructor, and that the
    package + root build.
  * L2 checks DO NOT trust the agent's own `units_test.go`. Instead each relevant
    case writes an *independent* white-box Go driver into the `units` package,
    builds a fresh command tree per case via the agent's `NewCmdUnits(f)`, drives
    it with cobra's `SetArgs` + redirected streams, and asserts on real captured
    stdout/stderr/error behaviour and concrete numeric results. A naive solution
    (hardcoded output, ignored args, no family check, hand-rolled len(args)
    check) returns wrong values or fails to reject bad input, failing these
    tests.

Native command: `go test ./pkg/cmd/units/...` plus targeted `go build`.
"""

import os
import re
import subprocess
import textwrap
import uuid

import pytest

try:
    from _dependency_utils import ensure_go_dependencies
except Exception:  # pragma: no cover - utils not present in some envs
    ensure_go_dependencies = None


def _find_repo_dir(_fallback):
    """Repo clones to /workspace/<repo-name>, not /workspace/<skill-id>. Prefer the
    harness-provided SWE_REPO_DIR (authoritative); else discover the single real repo
    dir under /workspace; else the known fallback. Reading SWE_REPO_DIR avoids picking
    the wrong repo when a job's rootfs accumulated several repos."""
    _env = os.environ.get("SWE_REPO_DIR")
    if _env and os.path.isdir(_env):
        return _env
    import glob as _glob
    _skip = {"tests", "benchmark_tests", "lost+found"}
    _c = [d for d in sorted(_glob.glob("/workspace/*"))
          if os.path.isdir(d) and os.path.basename(d) not in _skip]
    _git = [d for d in _c if os.path.isdir(os.path.join(d, ".git"))]
    if len(_git) == 1:
        return _git[0]
    if len(_c) == 1:
        return _c[0]
    return _fallback
REPO_DIR = _find_repo_dir("/workspace/cli")
UNITS_PKG_DIR = os.path.join(REPO_DIR, "pkg", "cmd", "units")
GO_TIMEOUT = 600


@pytest.fixture(scope="module", autouse=True)
def _prepare_repo():
    """Ensure go module deps are available before native tests run."""
    if ensure_go_dependencies is not None:
        try:
            ensure_go_dependencies(REPO_DIR)
        except Exception:
            pass
    yield


def _go_env():
    env = dict(os.environ)
    env.setdefault("GOFLAGS", "")
    env.setdefault("CGO_ENABLED", "0")
    return env


def _run_go(args, timeout=GO_TIMEOUT):
    return subprocess.run(
        args,
        cwd=REPO_DIR,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=_go_env(),
    )


def _write_driver(go_source):
    """Write an independent driver test into the units package; return its path.

    The file name is unique so concurrent/repeat runs do not clash, and it is
    placed inside the agent-created package so it can call the unexported and
    exported identifiers in package `units`.
    """
    name = "zz_skilltest_%s_test.go" % uuid.uuid4().hex[:10]
    path = os.path.join(UNITS_PKG_DIR, name)
    with open(path, "w") as fh:
        fh.write(go_source)
    return path


def _run_driver(go_source, run_regex, timeout=GO_TIMEOUT):
    """Drop a driver test into the units package, run only it, then clean up.

    Returns the completed subprocess. The driver's package is `units`
    (white-box) so it can construct the command tree via NewCmdUnits.
    """
    assert os.path.isdir(UNITS_PKG_DIR), (
        "units package dir missing: %s" % UNITS_PKG_DIR
    )
    path = _write_driver(go_source)
    try:
        return _run_go(
            ["go", "test", "-count=1", "-run", run_regex,
             "./pkg/cmd/units/"],
            timeout=timeout,
        )
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


# Shared Go preamble for white-box driver tests living in package `units`.
# buildTree constructs a fresh units command tree and wires capturable streams
# onto both the IOStreams (used by handlers) and the cobra command (used by
# cobra-emitted output such as help / arg errors).
_DRIVER_HEADER = textwrap.dedent(
    """
    package units

    import (
        "bytes"
        "strings"
        "testing"

        "github.com/cli/cli/v2/pkg/cmdutil"
        "github.com/cli/cli/v2/pkg/iostreams"
    )

    func buildTree(args []string) (*bytes.Buffer, *bytes.Buffer, error) {
        ios, _, outBuf, errBuf := iostreams.Test()
        f := &cmdutil.Factory{IOStreams: ios}
        cmd := NewCmdUnits(f)
        cmd.SetArgs(args)
        cmd.SetIn(&bytes.Buffer{})
        cmd.SetOut(outBuf)
        cmd.SetErr(errBuf)
        _, err := cmd.ExecuteC()
        return outBuf, errBuf, err
    }

    var _ = strings.TrimSpace
    """
)


class TestCobraCliDevelopment:
    REPO_DIR = _find_repo_dir("/workspace/cli")

    # ------------------------------------------------------------------ L1 ---
    def test_deliverable_files_exist(self):
        """L1: the three new units files + modified root.go are present on disk."""
        required = [
            os.path.join(UNITS_PKG_DIR, "units.go"),
            os.path.join(UNITS_PKG_DIR, "convert.go"),
            os.path.join(UNITS_PKG_DIR, "units_test.go"),
            os.path.join(REPO_DIR, "pkg", "cmd", "root", "root.go"),
        ]
        missing = [p for p in required if not os.path.isfile(p)]
        assert not missing, "missing deliverable files: %s" % missing

    def test_package_declaration_and_constructor(self):
        """L1: units.go declares package units and exposes NewCmdUnits."""
        ref = os.path.join(UNITS_PKG_DIR, "units.go")
        with open(ref) as fh:
            src = fh.read()
        assert re.search(r"^\s*package\s+units\b", src, re.MULTILINE), (
            "units.go must declare `package units`"
        )
        assert re.search(
            r"func\s+NewCmdUnits\s*\(\s*\w+\s+\*cmdutil\.Factory\s*\)\s*\*cobra\.Command",
            src,
        ), "NewCmdUnits(f *cmdutil.Factory) *cobra.Command signature required"

    def test_units_package_builds(self):
        """L1: the new package and the modified root package both compile."""
        proc = _run_go(
            ["go", "build", "./pkg/cmd/units/...", "./pkg/cmd/root/..."]
        )
        assert proc.returncode == 0, (
            "go build failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_root_registers_units(self):
        """L1: root.go imports and registers the units command group."""
        root = os.path.join(REPO_DIR, "pkg", "cmd", "root", "root.go")
        with open(root) as fh:
            src = fh.read()
        assert "cmd/units" in src, (
            "root.go must import the units package"
        )
        assert "NewCmdUnits" in src, (
            "root.go must call NewCmdUnits to register the group"
        )

    # ------------------------------------------------------------------ L2 ---
    def test_agent_native_tests_pass(self):
        """L2: the package's own test suite passes (go test ./pkg/cmd/units/...)."""
        proc = _run_go(["go", "test", "-count=1", "./pkg/cmd/units/..."])
        assert proc.returncode == 0, (
            "go test ./pkg/cmd/units/... failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_parent_no_args_prints_help_no_error(self):
        """L2: `units` with no subcommand prints help (lists convert), no error."""
        driver = _DRIVER_HEADER + textwrap.dedent(
            """
            func TestUnitsParentHelp(t *testing.T) {
                out, _, err := buildTree([]string{})
                if err != nil {
                    t.Fatalf("expected no error from bare parent, got %v", err)
                }
                s := out.String()
                if !strings.Contains(s, "convert") {
                    t.Fatalf("help output must mention the convert subcommand; got:\\n%s", s)
                }
                low := strings.ToLower(s)
                if !strings.Contains(low, "usage") &&
                    !strings.Contains(low, "available commands") {
                    t.Fatalf("expected cobra help text, got:\\n%s", s)
                }
            }
            """
        )
        proc = _run_driver(driver, "TestUnitsParentHelp")
        assert proc.returncode == 0, (
            "parent-help driver failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_byte_conversion_value_and_clean_streams(self):
        """L2: `convert 1024 b kb` -> exactly `1`, nothing on stderr, no error."""
        driver = _DRIVER_HEADER + textwrap.dedent(
            """
            func TestUnitsByteConvert(t *testing.T) {
                out, errBuf, err := buildTree([]string{"convert", "1024", "b", "kb"})
                if err != nil {
                    t.Fatalf("convert 1024 b kb errored: %v (stderr=%s)", err, errBuf.String())
                }
                if strings.TrimSpace(errBuf.String()) != "" {
                    t.Fatalf("success path must not write stderr; got: %q", errBuf.String())
                }
                got := strings.TrimSpace(out.String())
                if got != "1" {
                    t.Fatalf("convert 1024 b kb must print 1; got %q", got)
                }
                // gb->b is 1024^3; verify a larger power so a stub returning a
                // fixed value cannot pass both this and the previous assertion.
                out2, _, err2 := buildTree([]string{"convert", "1", "gb", "b"})
                if err2 != nil {
                    t.Fatalf("convert 1 gb b errored: %v", err2)
                }
                if strings.TrimSpace(out2.String()) != "1073741824" {
                    t.Fatalf("convert 1 gb b must print 1073741824; got %q",
                        strings.TrimSpace(out2.String()))
                }
            }
            """
        )
        proc = _run_driver(driver, "TestUnitsByteConvert")
        assert proc.returncode == 0, (
            "byte-convert driver failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_duration_conversion_value(self):
        """L2: `convert 2 h m` -> exactly `120`, and `convert 1 d h` -> `24`."""
        driver = _DRIVER_HEADER + textwrap.dedent(
            """
            func TestUnitsDurationConvert(t *testing.T) {
                out, _, err := buildTree([]string{"convert", "2", "h", "m"})
                if err != nil {
                    t.Fatalf("convert 2 h m errored: %v", err)
                }
                if strings.TrimSpace(out.String()) != "120" {
                    t.Fatalf("convert 2 h m must print 120; got %q",
                        strings.TrimSpace(out.String()))
                }
                out2, _, err2 := buildTree([]string{"convert", "1", "d", "h"})
                if err2 != nil {
                    t.Fatalf("convert 1 d h errored: %v", err2)
                }
                if strings.TrimSpace(out2.String()) != "24" {
                    t.Fatalf("convert 1 d h must print 24; got %q",
                        strings.TrimSpace(out2.String()))
                }
                // Inverse direction must reciprocate (60 m -> 1 h), exercising
                // the from/to multiplier ratio rather than a fixed direction.
                out3, _, err3 := buildTree([]string{"convert", "60", "m", "h"})
                if err3 != nil {
                    t.Fatalf("convert 60 m h errored: %v", err3)
                }
                if strings.TrimSpace(out3.String()) != "1" {
                    t.Fatalf("convert 60 m h must print 1; got %q",
                        strings.TrimSpace(out3.String()))
                }
            }
            """
        )
        proc = _run_driver(driver, "TestUnitsDurationConvert")
        assert proc.returncode == 0, (
            "duration-convert driver failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_case_insensitive_units(self):
        """L2: `convert 1 MB KB` (mixed case) -> `1024`, matching lowercase output."""
        driver = _DRIVER_HEADER + textwrap.dedent(
            """
            func TestUnitsCaseInsensitive(t *testing.T) {
                outUpper, _, err := buildTree([]string{"convert", "1", "MB", "KB"})
                if err != nil {
                    t.Fatalf("convert 1 MB KB errored (case-insensitive?): %v", err)
                }
                if strings.TrimSpace(outUpper.String()) != "1024" {
                    t.Fatalf("convert 1 MB KB must print 1024; got %q",
                        strings.TrimSpace(outUpper.String()))
                }
                // Lowercase form must yield identical output.
                outLower, _, err2 := buildTree([]string{"convert", "1", "mb", "kb"})
                if err2 != nil {
                    t.Fatalf("convert 1 mb kb errored: %v", err2)
                }
                if outUpper.String() != outLower.String() {
                    t.Fatalf("mixed-case and lowercase must agree:\\nUPPER=%q\\nlower=%q",
                        outUpper.String(), outLower.String())
                }
                // Mixed case on one side only.
                outMix, _, err3 := buildTree([]string{"convert", "1", "Gb", "Mb"})
                if err3 != nil {
                    t.Fatalf("convert 1 Gb Mb errored: %v", err3)
                }
                if strings.TrimSpace(outMix.String()) != "1024" {
                    t.Fatalf("convert 1 Gb Mb must print 1024; got %q",
                        strings.TrimSpace(outMix.String()))
                }
            }
            """
        )
        proc = _run_driver(driver, "TestUnitsCaseInsensitive")
        assert proc.returncode == 0, (
            "case-insensitive driver failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_cross_family_rejected_no_stdout(self):
        """L2: `convert 5 mb h` errors naming both units (cross-family), no stdout."""
        driver = _DRIVER_HEADER + textwrap.dedent(
            """
            func TestUnitsCrossFamily(t *testing.T) {
                out, _, err := buildTree([]string{"convert", "5", "mb", "h"})
                if err == nil {
                    t.Fatalf("cross-family convert (mb -> h) must return a non-nil error")
                }
                if strings.TrimSpace(out.String()) != "" {
                    t.Fatalf("cross-family convert must not write stdout; got:\\n%s", out.String())
                }
                msg := strings.ToLower(err.Error())
                if !strings.Contains(msg, "mb") || !strings.Contains(msg, "h") {
                    t.Fatalf("cross-family error must name both units (mb, h); got: %v", err)
                }
                // Reverse direction must also fail with no stdout.
                out2, _, err2 := buildTree([]string{"convert", "5", "s", "kb"})
                if err2 == nil {
                    t.Fatalf("cross-family convert (s -> kb) must error")
                }
                if strings.TrimSpace(out2.String()) != "" {
                    t.Fatalf("cross-family convert must not write stdout; got:\\n%s", out2.String())
                }
            }
            """
        )
        proc = _run_driver(driver, "TestUnitsCrossFamily")
        assert proc.returncode == 0, (
            "cross-family driver failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_negative_amount_rejected_no_stdout(self):
        """L2: `convert -3 s m` errors (negative amount) and prints no stdout."""
        driver = _DRIVER_HEADER + textwrap.dedent(
            """
            func TestUnitsNegative(t *testing.T) {
                // Use "--" so cobra treats -3 as a positional, not a flag, exercising
                // the validator's non-negative check rather than a flag-parse error.
                out, _, err := buildTree([]string{"convert", "--", "-3", "s", "m"})
                if err == nil {
                    t.Fatalf("negative amount must be rejected with an error")
                }
                if strings.TrimSpace(out.String()) != "" {
                    t.Fatalf("negative amount must not write stdout; got:\\n%s", out.String())
                }
                // Zero is a valid non-negative amount and must succeed -> 0.
                out2, _, err2 := buildTree([]string{"convert", "0", "h", "m"})
                if err2 != nil {
                    t.Fatalf("convert 0 h m must succeed; got error %v", err2)
                }
                if strings.TrimSpace(out2.String()) != "0" {
                    t.Fatalf("convert 0 h m must print 0; got %q",
                        strings.TrimSpace(out2.String()))
                }
            }
            """
        )
        proc = _run_driver(driver, "TestUnitsNegative")
        assert proc.returncode == 0, (
            "negative-amount driver failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_unknown_unit_rejected_no_stdout(self):
        """L2: an unknown unit (e.g. `convert 1 b zz`) errors and prints no stdout."""
        driver = _DRIVER_HEADER + textwrap.dedent(
            """
            func TestUnitsUnknownUnit(t *testing.T) {
                out, _, err := buildTree([]string{"convert", "1", "b", "zz"})
                if err == nil {
                    t.Fatalf("unknown <to> unit must be rejected with an error")
                }
                if strings.TrimSpace(out.String()) != "" {
                    t.Fatalf("unknown unit must not write stdout; got:\\n%s", out.String())
                }
                out2, _, err2 := buildTree([]string{"convert", "1", "qq", "b"})
                if err2 == nil {
                    t.Fatalf("unknown <from> unit must be rejected with an error")
                }
                if strings.TrimSpace(out2.String()) != "" {
                    t.Fatalf("unknown unit must not write stdout; got:\\n%s", out2.String())
                }
                // Non-numeric amount must also fail.
                out3, _, err3 := buildTree([]string{"convert", "abc", "b", "kb"})
                if err3 == nil {
                    t.Fatalf("non-numeric amount must be rejected with an error")
                }
                if strings.TrimSpace(out3.String()) != "" {
                    t.Fatalf("non-numeric amount must not write stdout; got:\\n%s", out3.String())
                }
            }
            """
        )
        proc = _run_driver(driver, "TestUnitsUnknownUnit")
        assert proc.returncode == 0, (
            "unknown-unit driver failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_argument_count_errors(self):
        """L2: `convert 1 b` and `convert 1 b kb extra` fail with cobra arg-count errors."""
        driver = _DRIVER_HEADER + textwrap.dedent(
            """
            func TestUnitsArgCount(t *testing.T) {
                // Too few (two args).
                outFew, _, errFew := buildTree([]string{"convert", "1", "b"})
                if errFew == nil {
                    t.Fatalf("convert with two args must error (cobra arg-count)")
                }
                if strings.TrimSpace(outFew.String()) != "" {
                    t.Fatalf("arg-count failure must not print result; got:\\n%s", outFew.String())
                }
                // Too many (four args).
                outMany, _, errMany := buildTree([]string{"convert", "1", "b", "kb", "extra"})
                if errMany == nil {
                    t.Fatalf("convert with four args must error (cobra arg-count)")
                }
                if strings.TrimSpace(outMany.String()) != "" {
                    t.Fatalf("arg-count failure must not print result; got:\\n%s", outMany.String())
                }
                // Zero args.
                _, _, errZero := buildTree([]string{"convert"})
                if errZero == nil {
                    t.Fatalf("convert with zero args must error (cobra arg-count)")
                }
                // Errors should look like cobra arg-count errors.
                for _, e := range []error{errFew, errMany, errZero} {
                    if !strings.Contains(strings.ToLower(e.Error()), "arg") {
                        t.Fatalf("expected a cobra arg-count error; got: %v", e)
                    }
                }
            }
            """
        )
        proc = _run_driver(driver, "TestUnitsArgCount")
        assert proc.returncode == 0, (
            "arg-count driver failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_trailing_zero_trimming(self):
        """L2: fractional results trim trailing zeros (e.g. `512 b kb` -> `0.5`)."""
        driver = _DRIVER_HEADER + textwrap.dedent(
            """
            func TestUnitsTrim(t *testing.T) {
                // 512 b -> kb = 0.5, must NOT be "0.500000" and must NOT be "0".
                out, _, err := buildTree([]string{"convert", "512", "b", "kb"})
                if err != nil {
                    t.Fatalf("convert 512 b kb errored: %v", err)
                }
                got := strings.TrimSpace(out.String())
                if got != "0.5" {
                    t.Fatalf("convert 512 b kb must print 0.5 (trimmed); got %q", got)
                }
                // A whole-number result must have no decimal point at all.
                out2, _, err2 := buildTree([]string{"convert", "2048", "b", "kb"})
                if err2 != nil {
                    t.Fatalf("convert 2048 b kb errored: %v", err2)
                }
                got2 := strings.TrimSpace(out2.String())
                if got2 != "2" {
                    t.Fatalf("convert 2048 b kb must print 2 (no trailing .0); got %q", got2)
                }
                if strings.Contains(got2, ".") {
                    t.Fatalf("whole-number result must not contain a decimal point; got %q", got2)
                }
            }
            """
        )
        proc = _run_driver(driver, "TestUnitsTrim")
        assert proc.returncode == 0, (
            "trim driver failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_no_leaked_state_between_invocations(self):
        """L2: a fresh tree per invocation yields identical results (no leaked arg state)."""
        driver = _DRIVER_HEADER + textwrap.dedent(
            """
            func TestUnitsNoLeak(t *testing.T) {
                // First run a conversion, then repeat an independent one twice; the
                // repeated outputs must be byte-identical (no leaked positional state).
                _, _, err := buildTree([]string{"convert", "1024", "b", "kb"})
                if err != nil {
                    t.Fatalf("seed conversion errored: %v", err)
                }
                a, _, err := buildTree([]string{"convert", "2", "h", "m"})
                if err != nil {
                    t.Fatalf("convert 2 h m errored: %v", err)
                }
                b, _, err := buildTree([]string{"convert", "2", "h", "m"})
                if err != nil {
                    t.Fatalf("convert 2 h m errored: %v", err)
                }
                if a.String() != b.String() {
                    t.Fatalf("repeated fresh conversions differ (state leak?):\\n--a--\\n%s\\n--b--\\n%s",
                        a.String(), b.String())
                }
                if strings.TrimSpace(a.String()) != "120" {
                    t.Fatalf("convert 2 h m must still be 120 after a prior call; got %q",
                        strings.TrimSpace(a.String()))
                }
            }
            """
        )
        proc = _run_driver(driver, "TestUnitsNoLeak")
        assert proc.returncode == 0, (
            "no-leak driver failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )
