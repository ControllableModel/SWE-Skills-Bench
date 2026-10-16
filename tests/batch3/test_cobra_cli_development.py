"""Tests for the `cobra-cli-development` skill (variant ext3).

Skill task: add a brand-new, fully offline `gh budget` cobra command group to the
GitHub CLI (github.com/cli/cli/v2) with two subcommands `spend <amount>` and
`report`, a parent persistent integer flag `--cap` (default 100) inherited by
both subcommands, a parent-level pre-run hook validating `--cap >= 1`, and a
child-level pre-run on `spend` validating its positional amount (non-negative).
Crucially the parent's cap validation must STILL fire for `spend` even though the
child installs its own pre-run hook (cobra does not chain a child's persistent
pre-run with the parent's automatically). The group is registered on the root
command (`gh`).

Verification strategy (discriminative):
  * L1 checks confirm the deliverable files exist, are well-formed Go, expose the
    `NewCmdBudget` constructor, and that the budget + root packages build.
  * L2 checks DO NOT trust the agent's own `budget_test.go`. Instead each case
    writes an *independent* white-box Go driver test into the budget package
    directory, builds a fresh command tree per case via the agent's
    `NewCmdBudget(f)`, drives it with cobra's `SetArgs` + redirected IOStreams,
    and asserts on real captured stdout/stderr/error behavior:
      - report prints the resolved cap (`--cap 250` -> "250"),
      - spend computes remaining = cap - amount (`spend 30` default cap -> "70"),
      - INHERITED parent cap-validation still fires for spend (`spend 30 --cap 0`
        errors, no stdout) AND for report (`report --cap 0` errors),
      - child negative-amount validation (`spend -5` errors, no stdout) is
        DISTINCT from the cap error,
      - overspend (`spend 150 --cap 100`) errors with no stdout,
      - cobra arg-count errors for `spend` with 0 or 2 args,
      - a fresh tree per invocation yields identical results (no leaked state).
    A naive/stub solution (hardcoded remaining, missing inherited cap check,
    skipped amount parsing) fails to compile or returns wrong output here.

Native command: `go test ./pkg/cmd/budget/...` plus targeted `go build`.
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
BUDGET_PKG_DIR = os.path.join(REPO_DIR, "pkg", "cmd", "budget")
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
    """Write an independent driver test into the budget package; return its path.

    The file name is unique so concurrent/repeat runs do not clash, and it is
    placed inside the agent-created package so it can call the exported and
    unexported identifiers in package `budget`.
    """
    name = "zz_skilltest_%s_test.go" % uuid.uuid4().hex[:10]
    path = os.path.join(BUDGET_PKG_DIR, name)
    with open(path, "w") as fh:
        fh.write(go_source)
    return path


def _run_driver(go_source, run_regex, timeout=GO_TIMEOUT):
    """Drop a driver test into the budget package, run only it, then clean up.

    Returns the completed subprocess. The driver's package is `budget`
    (white-box) so it can construct the command tree via NewCmdBudget.
    """
    assert os.path.isdir(BUDGET_PKG_DIR), (
        "budget package dir missing: %s" % BUDGET_PKG_DIR
    )
    path = _write_driver(go_source)
    try:
        return _run_go(
            ["go", "test", "-count=1", "-run", run_regex,
             "./pkg/cmd/budget/"],
            timeout=timeout,
        )
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


# Shared Go preamble for white-box driver tests living in package `budget`.
# buildTree constructs a fresh budget command tree per call and wires capturable
# streams onto both the IOStreams (used by handlers) and the cobra command (used
# by cobra-emitted output such as help / arg errors). A FRESH tree per call is
# essential to prove the doc's "fresh command tree per invocation" requirement.
_DRIVER_HEADER = textwrap.dedent(
    """
    package budget

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
        cmd := NewCmdBudget(f)
        cmd.SetArgs(args)
        cmd.SetIn(&bytes.Buffer{})
        cmd.SetOut(outBuf)
        cmd.SetErr(errBuf)
        _, err := cmd.ExecuteC()
        return outBuf, errBuf, err
    }

    func nonEmptyLines(s string) []string {
        out := []string{}
        for _, ln := range strings.Split(strings.TrimRight(s, "\\n"), "\\n") {
            if strings.TrimSpace(ln) != "" {
                out = append(out, ln)
            }
        }
        return out
    }

    // findInt returns the first integer token appearing in s (ignoring '-' that
    // is not part of a number), or false if none is found.
    func findInt(s string, want int) bool {
        toks := strings.FieldsFunc(s, func(r rune) bool {
            return !(r >= '0' && r <= '9')
        })
        target := itoa(want)
        for _, tk := range toks {
            if tk == target {
                return true
            }
        }
        return false
    }

    func itoa(n int) string {
        if n == 0 {
            return "0"
        }
        neg := n < 0
        if neg {
            n = -n
        }
        b := []byte{}
        for n > 0 {
            b = append([]byte{byte('0' + n%10)}, b...)
            n /= 10
        }
        if neg {
            b = append([]byte{'-'}, b...)
        }
        return string(b)
    }

    var _ = nonEmptyLines
    var _ = findInt
    """
)


class TestCobraCliDevelopment:
    REPO_DIR = _find_repo_dir("/workspace/cli")

    # ------------------------------------------------------------------ L1 ---
    def test_deliverable_files_exist(self):
        """L1: the four new budget files + modified root.go are present on disk."""
        required = [
            os.path.join(BUDGET_PKG_DIR, "budget.go"),
            os.path.join(BUDGET_PKG_DIR, "spend.go"),
            os.path.join(BUDGET_PKG_DIR, "report.go"),
            os.path.join(BUDGET_PKG_DIR, "budget_test.go"),
            os.path.join(REPO_DIR, "pkg", "cmd", "root", "root.go"),
        ]
        missing = [p for p in required if not os.path.isfile(p)]
        assert not missing, "missing deliverable files: %s" % missing

    def test_package_declaration_and_constructor(self):
        """L1: budget.go declares package budget and exposes NewCmdBudget signature."""
        bg = os.path.join(BUDGET_PKG_DIR, "budget.go")
        with open(bg) as fh:
            src = fh.read()
        assert re.search(r"^\s*package\s+budget\b", src, re.MULTILINE), (
            "budget.go must declare `package budget`"
        )
        assert re.search(
            r"func\s+NewCmdBudget\s*\(\s*\w+\s+\*cmdutil\.Factory\s*\)\s*\*cobra\.Command",
            src,
        ), "NewCmdBudget(f *cmdutil.Factory) *cobra.Command signature required"

    def test_no_direct_os_stdout_writes(self):
        """L1: handlers must not write to os.Stdout/os.Stderr directly (per doc)."""
        offenders = []
        for fname in ("budget.go", "spend.go", "report.go"):
            p = os.path.join(BUDGET_PKG_DIR, fname)
            if not os.path.isfile(p):
                continue
            with open(p) as fh:
                src = fh.read()
            # Strip import lines so that an `os` import (e.g. for strconv-free
            # parsing) does not produce a false positive; we only flag actual
            # writes to os.Stdout / os.Stderr.
            if re.search(r"os\.Stdout", src) or re.search(r"os\.Stderr", src):
                offenders.append(fname)
        assert not offenders, (
            "handlers must use f.IOStreams, not os.Stdout/os.Stderr: %s" % offenders
        )

    def test_budget_package_builds(self):
        """L1: the new budget package and the modified root package both compile."""
        proc = _run_go(
            ["go", "build", "./pkg/cmd/budget/...", "./pkg/cmd/root/..."]
        )
        assert proc.returncode == 0, (
            "go build failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_root_registers_budget(self):
        """L1: root.go imports and registers the budget command group."""
        root = os.path.join(REPO_DIR, "pkg", "cmd", "root", "root.go")
        with open(root) as fh:
            src = fh.read()
        assert "cmd/budget" in src, (
            "root.go must import the budget package"
        )
        assert "NewCmdBudget" in src, (
            "root.go must call NewCmdBudget to register the group"
        )

    # ------------------------------------------------------------------ L2 ---
    def test_agent_native_tests_pass(self):
        """L2: the package's own test suite passes (go test ./pkg/cmd/budget/...)."""
        proc = _run_go(["go", "test", "-count=1", "./pkg/cmd/budget/..."])
        assert proc.returncode == 0, (
            "go test ./pkg/cmd/budget/... failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_parent_no_args_prints_help_lists_subcommands(self):
        """L2: bare `budget` prints help listing both `spend` and `report`, no error."""
        driver = _DRIVER_HEADER + textwrap.dedent(
            """
            func TestBudgetParentHelp(t *testing.T) {
                out, _, err := buildTree([]string{})
                if err != nil {
                    t.Fatalf("expected no error from bare parent, got %v", err)
                }
                s := out.String()
                if !strings.Contains(s, "spend") || !strings.Contains(s, "report") {
                    t.Fatalf("help must mention both subcommands; got:\\n%s", s)
                }
                low := strings.ToLower(s)
                if !strings.Contains(low, "usage") &&
                    !strings.Contains(low, "available commands") {
                    t.Fatalf("expected cobra help text, got:\\n%s", s)
                }
            }
            """
        )
        proc = _run_driver(driver, "TestBudgetParentHelp")
        assert proc.returncode == 0, (
            "parent-help driver failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_report_prints_resolved_cap(self):
        """L2: `report --cap 250` prints a line stating cap 250; default cap is 100."""
        driver = _DRIVER_HEADER + textwrap.dedent(
            """
            func TestBudgetReportCap(t *testing.T) {
                // Explicit cap value is echoed.
                out, errBuf, err := buildTree([]string{"report", "--cap", "250"})
                if err != nil {
                    t.Fatalf("report --cap 250 errored: %v (stderr=%s)", err, errBuf.String())
                }
                if strings.TrimSpace(errBuf.String()) != "" {
                    t.Fatalf("report wrote to stderr on success: %q", errBuf.String())
                }
                if !findInt(out.String(), 250) {
                    t.Fatalf("report --cap 250 must report cap 250; got:\\n%s", out.String())
                }
                if findInt(out.String(), 100) {
                    t.Fatalf("report --cap 250 must not echo the default 100; got:\\n%s", out.String())
                }
                // Default cap (no flag) resolves to 100.
                outDef, _, err := buildTree([]string{"report"})
                if err != nil {
                    t.Fatalf("report (default) errored: %v", err)
                }
                if !findInt(outDef.String(), 100) {
                    t.Fatalf("default report must report cap 100; got:\\n%s", outDef.String())
                }
                // report takes no positional args.
                _, _, errArg := buildTree([]string{"report", "extra"})
                if errArg == nil {
                    t.Fatalf("report with a positional arg must error (cobra arg-count)")
                }
            }
            """
        )
        proc = _run_driver(driver, "TestBudgetReportCap")
        assert proc.returncode == 0, (
            "report-cap driver failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_spend_computes_remaining(self):
        """L2: `spend 30` (default cap 100) -> spent 30, remaining 70; cap affects it."""
        driver = _DRIVER_HEADER + textwrap.dedent(
            """
            func TestBudgetSpendRemaining(t *testing.T) {
                out, errBuf, err := buildTree([]string{"spend", "30"})
                if err != nil {
                    t.Fatalf("spend 30 errored: %v (stderr=%s)", err, errBuf.String())
                }
                if strings.TrimSpace(errBuf.String()) != "" {
                    t.Fatalf("spend wrote to stderr on success: %q", errBuf.String())
                }
                s := out.String()
                // Must report both the spent amount and the computed remaining.
                if !findInt(s, 30) {
                    t.Fatalf("spend 30 must report the spent amount 30; got:\\n%s", s)
                }
                if !findInt(s, 70) {
                    t.Fatalf("spend 30 (cap 100) must report remaining 70; got:\\n%s", s)
                }
                // Remaining is cap-dependent: with --cap 50, remaining = 20 (not 70).
                out2, _, err := buildTree([]string{"spend", "30", "--cap", "50"})
                if err != nil {
                    t.Fatalf("spend 30 --cap 50 errored: %v", err)
                }
                s2 := out2.String()
                if !findInt(s2, 20) {
                    t.Fatalf("spend 30 --cap 50 must report remaining 20; got:\\n%s", s2)
                }
                if findInt(s2, 70) {
                    t.Fatalf("remaining must depend on cap; --cap 50 leaked 70:\\n%s", s2)
                }
                // Exact-budget spend: remaining 0.
                out3, _, err := buildTree([]string{"spend", "100"})
                if err != nil {
                    t.Fatalf("spend 100 (cap 100) errored: %v", err)
                }
                if !findInt(out3.String(), 0) {
                    t.Fatalf("spend 100 (cap 100) must report remaining 0; got:\\n%s", out3.String())
                }
            }
            """
        )
        proc = _run_driver(driver, "TestBudgetSpendRemaining")
        assert proc.returncode == 0, (
            "spend-remaining driver failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_inherited_cap_validation_fires_for_spend(self):
        """L2: `spend 30 --cap 0` triggers the PARENT cap check -> error, no stdout.

        This is the crux of the task: cobra does not chain a child's persistent
        pre-run with the parent's automatically, so the agent must explicitly
        preserve the parent's cap validation for `spend`. A stub that only
        installs the child's amount check will NOT error here and fails this test.
        """
        driver = _DRIVER_HEADER + textwrap.dedent(
            """
            func TestBudgetInheritedCap(t *testing.T) {
                out, _, err := buildTree([]string{"spend", "30", "--cap", "0"})
                if err == nil {
                    t.Fatalf("spend 30 --cap 0 must error via inherited parent cap validation")
                }
                if strings.TrimSpace(out.String()) != "" {
                    t.Fatalf("spend with cap<1 must not write stdout; got:\\n%s", out.String())
                }
                // A negative cap is also below 1 and must be rejected for spend.
                out2, _, err2 := buildTree([]string{"spend", "30", "--cap", "-4"})
                if err2 == nil {
                    t.Fatalf("spend 30 --cap -4 must error via inherited cap validation")
                }
                if strings.TrimSpace(out2.String()) != "" {
                    t.Fatalf("spend with cap<1 must not write stdout; got:\\n%s", out2.String())
                }
                // Sanity: a valid cap >= 1 for the same spend succeeds, proving the
                // failure above is specifically the cap check, not a broken spend.
                outOK, _, errOK := buildTree([]string{"spend", "30", "--cap", "1"})
                if errOK != nil {
                    // cap 1 < amount 30 -> overspend error is acceptable, but it must
                    // NOT be silent-no-error; ensure no stdout was produced either way.
                    if strings.TrimSpace(outOK.String()) != "" {
                        t.Fatalf("overspend must not write stdout; got:\\n%s", outOK.String())
                    }
                }
            }
            """
        )
        proc = _run_driver(driver, "TestBudgetInheritedCap")
        assert proc.returncode == 0, (
            "inherited-cap driver failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_report_cap_validation_fires(self):
        """L2: `report --cap 0` (and negative) is rejected by the parent cap check."""
        driver = _DRIVER_HEADER + textwrap.dedent(
            """
            func TestBudgetReportCapValidation(t *testing.T) {
                out, _, err := buildTree([]string{"report", "--cap", "0"})
                if err == nil {
                    t.Fatalf("report --cap 0 must error via parent cap validation")
                }
                if strings.TrimSpace(out.String()) != "" {
                    t.Fatalf("report with cap<1 must not write stdout; got:\\n%s", out.String())
                }
                out2, _, err2 := buildTree([]string{"report", "--cap", "-1"})
                if err2 == nil {
                    t.Fatalf("report --cap -1 must error via parent cap validation")
                }
                if strings.TrimSpace(out2.String()) != "" {
                    t.Fatalf("report with cap<1 must not write stdout; got:\\n%s", out2.String())
                }
                // cap exactly 1 is the boundary and must be accepted.
                outOK, _, errOK := buildTree([]string{"report", "--cap", "1"})
                if errOK != nil {
                    t.Fatalf("report --cap 1 (boundary) must succeed; got err %v", errOK)
                }
                if !findInt(outOK.String(), 1) {
                    t.Fatalf("report --cap 1 must report cap 1; got:\\n%s", outOK.String())
                }
            }
            """
        )
        proc = _run_driver(driver, "TestBudgetReportCapValidation")
        assert proc.returncode == 0, (
            "report-cap-validation driver failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_spend_negative_amount_distinct_from_cap_error(self):
        """L2: `spend -5` errors via the CHILD amount check (distinct from cap), no stdout.

        With a valid cap, a negative amount must still be rejected by the spend
        child's own pre-run, proving the two pre-run steps are independent.
        """
        driver = _DRIVER_HEADER + textwrap.dedent(
            """
            func TestBudgetNegativeAmount(t *testing.T) {
                // Valid cap, negative amount -> child amount validation must fire.
                out, _, err := buildTree([]string{"spend", "-5", "--cap", "100"})
                if err == nil {
                    t.Fatalf("spend -5 must error via child negative-amount validation")
                }
                if strings.TrimSpace(out.String()) != "" {
                    t.Fatalf("negative amount must not write stdout; got:\\n%s", out.String())
                }
                // Same with default cap.
                out2, _, err2 := buildTree([]string{"spend", "-5"})
                if err2 == nil {
                    t.Fatalf("spend -5 (default cap) must error via child amount validation")
                }
                if strings.TrimSpace(out2.String()) != "" {
                    t.Fatalf("negative amount must not write stdout; got:\\n%s", out2.String())
                }
                // Amount 0 is non-negative and within budget -> success, remaining == cap.
                out3, _, err3 := buildTree([]string{"spend", "0", "--cap", "100"})
                if err3 != nil {
                    t.Fatalf("spend 0 --cap 100 should succeed; got err %v", err3)
                }
                if !findInt(out3.String(), 100) {
                    t.Fatalf("spend 0 (cap 100) must leave remaining 100; got:\\n%s", out3.String())
                }
            }
            """
        )
        proc = _run_driver(driver, "TestBudgetNegativeAmount")
        assert proc.returncode == 0, (
            "negative-amount driver failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_spend_overspend_errors_no_stdout(self):
        """L2: `spend 150 --cap 100` returns a non-nil error and prints nothing."""
        driver = _DRIVER_HEADER + textwrap.dedent(
            """
            func TestBudgetOverspend(t *testing.T) {
                out, _, err := buildTree([]string{"spend", "150", "--cap", "100"})
                if err == nil {
                    t.Fatalf("spend 150 --cap 100 must error (overspend)")
                }
                if strings.TrimSpace(out.String()) != "" {
                    t.Fatalf("overspend must not write stdout; got:\\n%s", out.String())
                }
                // Just over the edge: cap+1 also overspends.
                out2, _, err2 := buildTree([]string{"spend", "101", "--cap", "100"})
                if err2 == nil {
                    t.Fatalf("spend 101 --cap 100 must error (overspend by 1)")
                }
                if strings.TrimSpace(out2.String()) != "" {
                    t.Fatalf("overspend-by-1 must not write stdout; got:\\n%s", out2.String())
                }
            }
            """
        )
        proc = _run_driver(driver, "TestBudgetOverspend")
        assert proc.returncode == 0, (
            "overspend driver failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_spend_argument_count_errors(self):
        """L2: `spend` with zero or two positional args fails with cobra arg-count error."""
        driver = _DRIVER_HEADER + textwrap.dedent(
            """
            func TestBudgetSpendArgCount(t *testing.T) {
                _, _, err0 := buildTree([]string{"spend"})
                if err0 == nil {
                    t.Fatalf("spend with no args must error (cobra arg-count)")
                }
                _, _, err2 := buildTree([]string{"spend", "1", "2"})
                if err2 == nil {
                    t.Fatalf("spend with two args must error (cobra arg-count)")
                }
                // Cobra arg-count errors mention "arg".
                if !strings.Contains(strings.ToLower(err0.Error()), "arg") {
                    t.Fatalf("zero-arg error should be cobra arg-count; got: %v", err0)
                }
                if !strings.Contains(strings.ToLower(err2.Error()), "arg") {
                    t.Fatalf("two-arg error should be cobra arg-count; got: %v", err2)
                }
            }
            """
        )
        proc = _run_driver(driver, "TestBudgetSpendArgCount")
        assert proc.returncode == 0, (
            "spend-argcount driver failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_cap_flag_inherited_by_both_subcommands(self):
        """L2: `--cap` is a parent persistent flag visible to both spend and report."""
        driver = _DRIVER_HEADER + textwrap.dedent(
            """
            func TestBudgetCapInherited(t *testing.T) {
                // Both subcommands must accept --cap without an "unknown flag" error.
                outR, _, errR := buildTree([]string{"report", "--cap", "42"})
                if errR != nil {
                    t.Fatalf("report must inherit --cap; got err %v", errR)
                }
                if !findInt(outR.String(), 42) {
                    t.Fatalf("report --cap 42 must report 42; got:\\n%s", outR.String())
                }
                outS, _, errS := buildTree([]string{"spend", "10", "--cap", "42"})
                if errS != nil {
                    t.Fatalf("spend must inherit --cap; got err %v", errS)
                }
                // remaining = 42 - 10 = 32
                if !findInt(outS.String(), 32) {
                    t.Fatalf("spend 10 --cap 42 must report remaining 32; got:\\n%s", outS.String())
                }
                // An unknown flag must still be rejected (proves it's a real flag set).
                _, _, errU := buildTree([]string{"report", "--definitelyunknownflag"})
                if errU == nil {
                    t.Fatalf("unknown flag must be rejected")
                }
            }
            """
        )
        proc = _run_driver(driver, "TestBudgetCapInherited")
        assert proc.returncode == 0, (
            "cap-inherited driver failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_no_leaked_state_between_invocations(self):
        """L2: a fresh tree per invocation yields identical results (no leaked cap/amount)."""
        driver = _DRIVER_HEADER + textwrap.dedent(
            """
            func TestBudgetNoLeak(t *testing.T) {
                // Run spend with a non-default cap first, then a default report:
                // the default report must NOT inherit the previous --cap 50.
                _, _, err := buildTree([]string{"spend", "10", "--cap", "50"})
                if err != nil {
                    t.Fatalf("spend 10 --cap 50 errored: %v", err)
                }
                a, _, err := buildTree([]string{"report"})
                if err != nil {
                    t.Fatalf("report errored: %v", err)
                }
                b, _, err := buildTree([]string{"report"})
                if err != nil {
                    t.Fatalf("report errored: %v", err)
                }
                if a.String() != b.String() {
                    t.Fatalf("repeated fresh report outputs differ (state leak?):\\n--a--\\n%s\\n--b--\\n%s",
                        a.String(), b.String())
                }
                // Default report must report cap 100, not the earlier 50.
                if !findInt(a.String(), 100) {
                    t.Fatalf("fresh default report must report cap 100; got:\\n%s", a.String())
                }
                if findInt(a.String(), 50) {
                    t.Fatalf("default report leaked previous --cap 50:\\n%s", a.String())
                }
            }
            """
        )
        proc = _run_driver(driver, "TestBudgetNoLeak")
        assert proc.returncode == 0, (
            "no-leak driver failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )
