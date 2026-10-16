"""Tests for the `cobra-cli-development` skill (variant ext9).

Skill task: add a brand-new, fully offline `gh ledger` cobra command to the
GitHub CLI (github.com/cli/cli/v2). The command:

  * is constructed via `NewCmdLedger(f *cmdutil.Factory) *cobra.Command` and
    registered on the root command in `pkg/cmd/root/root.go`;
  * accepts exactly two positional args `<entry> <amount>` using cobra's
    standard arg-count validation (no hand-rolled count check);
  * has a MAIN run step that validates `<amount>` parses as a *positive*
    integer, returns a non-nil error on invalid amount (printing nothing),
    and on valid input prints a single deterministic "recorded" line naming
    the entry + amount;
  * has a SEPARATE post-run finalizer step (a distinct cobra lifecycle hook,
    e.g. PostRunE) that prints a single deterministic "committed" line, and
    which must run ONLY when the main step returned no error.

Verification strategy (discriminative):
  * L1 checks confirm the deliverable files exist, are well-formed Go, declare
    `package ledger` + `NewCmdLedger`, that root.go registers the command, and
    that the package + root build.
  * L2 checks DO NOT trust the agent's own `ledger_test.go`. Instead each
    relevant case writes an *independent* white-box Go driver test into the
    ledger package directory, builds a FRESH command tree per case via the
    agent's `NewCmdLedger(f)`, drives it with cobra's `SetArgs` + redirected
    streams, and asserts on real captured stdout / stderr / error behavior.

    The critical discriminator is the success-gating of the finalizer: a naive
    implementation that prints "committed" inline at the end of the main step
    (or that does not gate the finalizer on main-step success) will emit the
    "committed" line even on a failing run (`amount 0` / non-numeric) and thus
    FAIL these tests. Hardcoded / input-ignoring implementations also fail,
    because we assert the recorded line names the actual entry+amount and that
    distinct amounts yield distinct recorded output.

Native command: `go test ./pkg/cmd/ledger/...` plus targeted `go build`.
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
LEDGER_PKG_DIR = os.path.join(REPO_DIR, "pkg", "cmd", "ledger")
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
    """Write an independent white-box driver test into the ledger package."""
    name = "zz_skilltest_%s_test.go" % uuid.uuid4().hex[:10]
    path = os.path.join(LEDGER_PKG_DIR, name)
    with open(path, "w") as fh:
        fh.write(go_source)
    return path


def _run_driver(go_source, run_regex, timeout=GO_TIMEOUT):
    """Drop a driver test into the ledger package, run only it, then clean up."""
    assert os.path.isdir(LEDGER_PKG_DIR), (
        "ledger package dir missing: %s" % LEDGER_PKG_DIR
    )
    path = _write_driver(go_source)
    try:
        return _run_go(
            ["go", "test", "-count=1", "-run", run_regex,
             "./pkg/cmd/ledger/"],
            timeout=timeout,
        )
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


# Shared Go preamble for white-box driver tests living in package `ledger`.
#
# buildTree constructs a FRESH ledger command tree per call and wires
# capturable streams onto both the IOStreams (used by the handler) and the
# cobra command itself (used for cobra-emitted output such as arg-count
# errors). It runs the full cobra lifecycle (Pre/Run/Post hooks) via
# ExecuteC, which is what makes the PostRunE finalizer's success-gating
# observable.
_DRIVER_HEADER = textwrap.dedent(
    """
    package ledger

    import (
        "bytes"
        "strings"
        "testing"

        "github.com/cli/cli/v2/pkg/cmdutil"
        "github.com/cli/cli/v2/pkg/iostreams"
    )

    func buildLedger(args []string) (*bytes.Buffer, *bytes.Buffer, error) {
        ios, _, outBuf, errBuf := iostreams.Test()
        f := &cmdutil.Factory{IOStreams: ios}
        cmd := NewCmdLedger(f)
        cmd.SetArgs(args)
        cmd.SetIn(&bytes.Buffer{})
        cmd.SetOut(outBuf)
        cmd.SetErr(errBuf)
        _, err := cmd.ExecuteC()
        return outBuf, errBuf, err
    }

    // hasRecorded reports whether stdout carries a line that looks like the
    // "recorded" main-step output for the given entry, naming entry+amount.
    func hasRecorded(stdout, entry, amount string) bool {
        low := strings.ToLower(stdout)
        if !strings.Contains(low, "record") {
            return false
        }
        return strings.Contains(stdout, entry) && strings.Contains(stdout, amount)
    }

    // hasCommitted reports whether stdout carries the finalizer "committed"
    // line. The finalizer line is the success-gated one.
    func hasCommitted(stdout string) bool {
        return strings.Contains(strings.ToLower(stdout), "commit")
    }

    var _ = strings.TrimSpace
    """
)


class TestCobraCliDevelopment:
    REPO_DIR = _find_repo_dir("/workspace/cli")

    # ------------------------------------------------------------------ L1 ---
    def test_deliverable_files_exist(self):
        """L1: the two new ledger files + modified root.go are present."""
        required = [
            os.path.join(LEDGER_PKG_DIR, "ledger.go"),
            os.path.join(LEDGER_PKG_DIR, "ledger_test.go"),
            os.path.join(REPO_DIR, "pkg", "cmd", "root", "root.go"),
        ]
        missing = [p for p in required if not os.path.isfile(p)]
        assert not missing, "missing deliverable files: %s" % missing

    def test_package_declaration_and_constructor(self):
        """L1: ledger.go declares `package ledger` and exposes NewCmdLedger."""
        ref = os.path.join(LEDGER_PKG_DIR, "ledger.go")
        with open(ref) as fh:
            src = fh.read()
        assert re.search(r"^\s*package\s+ledger\b", src, re.MULTILINE), (
            "ledger.go must declare `package ledger`"
        )
        assert re.search(
            r"func\s+NewCmdLedger\s*\(\s*\w+\s+\*cmdutil\.Factory\s*\)\s*\*cobra\.Command",
            src,
        ), "NewCmdLedger(f *cmdutil.Factory) *cobra.Command signature required"

    def test_finalizer_is_distinct_lifecycle_step(self):
        """L1: a separate post-run lifecycle hook is wired (not inline at run end).

        The doc requires the finalizer be a *distinct* cobra lifecycle step so
        that success-gating is enforced by cobra's ordering. cobra only runs
        PostRun/PostRunE when RunE returned nil, so the presence of a PostRun
        hook is the structural signal we require here. The behavioral proof of
        the gating is verified by the L2 driver tests below.
        """
        ref = os.path.join(LEDGER_PKG_DIR, "ledger.go")
        with open(ref) as fh:
            src = fh.read()
        assert re.search(r"\bPostRunE?\b", src), (
            "ledger command must wire a distinct PostRun/PostRunE finalizer "
            "step; none found in ledger.go"
        )

    def test_no_direct_os_stdout_writes(self):
        """L1: the handler must not write to os.Stdout/os.Stderr directly."""
        ref = os.path.join(LEDGER_PKG_DIR, "ledger.go")
        with open(ref) as fh:
            src = fh.read()
        assert "os.Stdout" not in src, "must not write to os.Stdout directly"
        assert "os.Stderr" not in src, "must not write to os.Stderr directly"

    def test_ledger_package_builds(self):
        """L1: the new package and the modified root package both compile."""
        proc = _run_go(
            ["go", "build", "./pkg/cmd/ledger/...", "./pkg/cmd/root/..."]
        )
        assert proc.returncode == 0, (
            "go build failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_root_registers_ledger(self):
        """L1: root.go imports and registers the ledger command."""
        root = os.path.join(REPO_DIR, "pkg", "cmd", "root", "root.go")
        with open(root) as fh:
            src = fh.read()
        assert "cmd/ledger" in src, "root.go must import the ledger package"
        assert "NewCmdLedger" in src, (
            "root.go must call NewCmdLedger to register the command"
        )

    # ------------------------------------------------------------------ L2 ---
    def test_agent_native_tests_pass(self):
        """L2: the package's own test suite passes (go test ./pkg/cmd/ledger/...)."""
        proc = _run_go(["go", "test", "-count=1", "./pkg/cmd/ledger/..."])
        assert proc.returncode == 0, (
            "go test ./pkg/cmd/ledger/... failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_success_emits_recorded_then_committed_in_order(self):
        """L2: a valid run prints BOTH a recorded and a committed line, recorded first."""
        driver = _DRIVER_HEADER + textwrap.dedent(
            """
            func TestLedgerSuccessOrder(t *testing.T) {
                out, errBuf, err := buildLedger([]string{"rent", "100"})
                if err != nil {
                    t.Fatalf("valid run returned error: %v (stderr=%s)", err, errBuf.String())
                }
                s := out.String()
                if !hasRecorded(s, "rent", "100") {
                    t.Fatalf("expected a recorded line naming entry+amount; got:\\n%s", s)
                }
                if !hasCommitted(s) {
                    t.Fatalf("expected a committed finalizer line on success; got:\\n%s", s)
                }
                // Ordering: recorded must precede committed.
                low := strings.ToLower(s)
                recIdx := strings.Index(low, "record")
                comIdx := strings.Index(low, "commit")
                if recIdx < 0 || comIdx < 0 || recIdx >= comIdx {
                    t.Fatalf("recorded line must precede committed line; got:\\n%s", s)
                }
                if strings.TrimSpace(errBuf.String()) != "" {
                    t.Fatalf("success run wrote to stderr: %q", errBuf.String())
                }
            }
            """
        )
        proc = _run_driver(driver, "TestLedgerSuccessOrder")
        assert proc.returncode == 0, (
            "success-order driver failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_invalid_amount_zero_errors_and_no_committed(self):
        """L2: `ledger rent 0` errors AND the committed finalizer line is absent.

        This is the central discriminator: an inline (non-gated) finalizer
        would still print 'committed' here, so it must NOT appear.
        """
        driver = _DRIVER_HEADER + textwrap.dedent(
            """
            func TestLedgerZeroGated(t *testing.T) {
                out, _, err := buildLedger([]string{"rent", "0"})
                if err == nil {
                    t.Fatalf("amount 0 must return a non-nil error")
                }
                s := out.String()
                if hasCommitted(s) {
                    t.Fatalf("finalizer 'committed' line must NOT appear on a failed run; got:\\n%s", s)
                }
            }
            """
        )
        proc = _run_driver(driver, "TestLedgerZeroGated")
        assert proc.returncode == 0, (
            "zero-gated driver failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_invalid_amount_nonnumeric_errors_and_no_committed(self):
        """L2: `ledger rent x` errors, prints no recorded entry, and no committed line."""
        driver = _DRIVER_HEADER + textwrap.dedent(
            """
            func TestLedgerNonNumericGated(t *testing.T) {
                out, _, err := buildLedger([]string{"rent", "x"})
                if err == nil {
                    t.Fatalf("non-numeric amount must return a non-nil error")
                }
                s := out.String()
                if hasCommitted(s) {
                    t.Fatalf("finalizer must NOT run on a failed run; got committed in:\\n%s", s)
                }
                // The main step prints nothing to stdout on invalid amount.
                if strings.TrimSpace(s) != "" {
                    t.Fatalf("invalid-amount run must print nothing to stdout; got:\\n%s", s)
                }
            }
            """
        )
        proc = _run_driver(driver, "TestLedgerNonNumericGated")
        assert proc.returncode == 0, (
            "nonnumeric-gated driver failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_negative_amount_rejected_no_committed(self):
        """L2: a negative amount is not a positive integer -> error, no committed line."""
        driver = _DRIVER_HEADER + textwrap.dedent(
            """
            func TestLedgerNegativeGated(t *testing.T) {
                out, _, err := buildLedger([]string{"rent", "-5"})
                if err == nil {
                    t.Fatalf("negative amount must return a non-nil error")
                }
                if hasCommitted(out.String()) {
                    t.Fatalf("finalizer must NOT run for a negative amount; got:\\n%s", out.String())
                }
            }
            """
        )
        proc = _run_driver(driver, "TestLedgerNegativeGated")
        assert proc.returncode == 0, (
            "negative-gated driver failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_recorded_line_reflects_actual_input(self):
        """L2: recorded output reflects the real entry+amount (defeats hardcoding).

        Two distinct valid invocations must produce distinct recorded output,
        each naming its own entry and amount. A stub that prints a fixed line
        fails here.
        """
        driver = _DRIVER_HEADER + textwrap.dedent(
            """
            func TestLedgerReflectsInput(t *testing.T) {
                outA, _, errA := buildLedger([]string{"rent", "100"})
                if errA != nil {
                    t.Fatalf("run A errored: %v", errA)
                }
                outB, _, errB := buildLedger([]string{"salary", "250"})
                if errB != nil {
                    t.Fatalf("run B errored: %v", errB)
                }
                sA, sB := outA.String(), outB.String()
                if !hasRecorded(sA, "rent", "100") {
                    t.Fatalf("run A recorded line must name rent+100; got:\\n%s", sA)
                }
                if !hasRecorded(sB, "salary", "250") {
                    t.Fatalf("run B recorded line must name salary+250; got:\\n%s", sB)
                }
                if sA == sB {
                    t.Fatalf("distinct inputs produced identical output (hardcoded?):\\n%s", sA)
                }
                // B's entry/amount must not bleed into A's output.
                if strings.Contains(sA, "salary") || strings.Contains(sA, "250") {
                    t.Fatalf("run A output leaked run B values:\\n%s", sA)
                }
            }
            """
        )
        proc = _run_driver(driver, "TestLedgerReflectsInput")
        assert proc.returncode == 0, (
            "reflects-input driver failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_arg_count_errors_use_cobra_validation(self):
        """L2: zero/one/three args fail with cobra's arg-count error; no committed line."""
        driver = _DRIVER_HEADER + textwrap.dedent(
            """
            func TestLedgerArgCount(t *testing.T) {
                cases := [][]string{
                    {},                          // zero args
                    {"rent"},                    // one arg
                    {"rent", "1", "extra"},      // three args
                }
                for _, args := range cases {
                    out, _, err := buildLedger(args)
                    if err == nil {
                        t.Fatalf("args %v must error (cobra arg-count)", args)
                    }
                    if !strings.Contains(strings.ToLower(err.Error()), "arg") {
                        t.Fatalf("args %v should yield a cobra arg-count error; got: %v", args, err)
                    }
                    if hasCommitted(out.String()) {
                        t.Fatalf("arg-count failure must not run finalizer; args=%v out=%s", args, out.String())
                    }
                }
            }
            """
        )
        proc = _run_driver(driver, "TestLedgerArgCount")
        assert proc.returncode == 0, (
            "arg-count driver failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_single_recorded_and_single_committed_line(self):
        """L2: a success run emits exactly one recorded line and exactly one committed line."""
        driver = _DRIVER_HEADER + textwrap.dedent(
            """
            func countContaining(s, needle string) int {
                n := 0
                for _, ln := range strings.Split(s, "\\n") {
                    if strings.Contains(strings.ToLower(ln), needle) {
                        n++
                    }
                }
                return n
            }

            func TestLedgerSingleLines(t *testing.T) {
                out, _, err := buildLedger([]string{"groceries", "42"})
                if err != nil {
                    t.Fatalf("valid run errored: %v", err)
                }
                s := out.String()
                if c := countContaining(s, "record"); c != 1 {
                    t.Fatalf("expected exactly 1 recorded line, got %d:\\n%s", c, s)
                }
                if c := countContaining(s, "commit"); c != 1 {
                    t.Fatalf("expected exactly 1 committed line, got %d:\\n%s", c, s)
                }
            }
            """
        )
        proc = _run_driver(driver, "TestLedgerSingleLines")
        assert proc.returncode == 0, (
            "single-lines driver failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_fresh_command_no_leaked_state(self):
        """L2: a fresh command per invocation yields identical, deterministic results."""
        driver = _DRIVER_HEADER + textwrap.dedent(
            """
            func TestLedgerNoLeak(t *testing.T) {
                // A failing run first must not poison a subsequent valid run.
                _, _, _ = buildLedger([]string{"rent", "0"})

                a, _, errA := buildLedger([]string{"rent", "100"})
                if errA != nil {
                    t.Fatalf("valid run after a failure errored: %v", errA)
                }
                b, _, errB := buildLedger([]string{"rent", "100"})
                if errB != nil {
                    t.Fatalf("repeat valid run errored: %v", errB)
                }
                if a.String() != b.String() {
                    t.Fatalf("repeated fresh runs differ (state leak?):\\n--a--\\n%s\\n--b--\\n%s",
                        a.String(), b.String())
                }
                if !hasRecorded(a.String(), "rent", "100") || !hasCommitted(a.String()) {
                    t.Fatalf("valid run after failure missing recorded/committed:\\n%s", a.String())
                }
            }
            """
        )
        proc = _run_driver(driver, "TestLedgerNoLeak")
        assert proc.returncode == 0, (
            "no-leak driver failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_finalizer_gating_is_lifecycle_enforced(self):
        """L2: prove gating is structural, not just a coincidence of error returns.

        We assert the contrast directly: identical entry, valid vs invalid
        amount. The valid case yields a committed line; the invalid case must
        not. This holds only if the finalizer is wired as a success-gated
        post-run step rather than printed inline regardless of the main step.
        """
        driver = _DRIVER_HEADER + textwrap.dedent(
            """
            func TestLedgerGatingContrast(t *testing.T) {
                good, _, gerr := buildLedger([]string{"utilities", "30"})
                if gerr != nil {
                    t.Fatalf("valid run errored: %v", gerr)
                }
                bad, _, berr := buildLedger([]string{"utilities", "0"})
                if berr == nil {
                    t.Fatalf("invalid run must error")
                }
                if !hasCommitted(good.String()) {
                    t.Fatalf("valid run must show committed line; got:\\n%s", good.String())
                }
                if hasCommitted(bad.String()) {
                    t.Fatalf("invalid run must NOT show committed line (gating broken); got:\\n%s",
                        bad.String())
                }
            }
            """
        )
        proc = _run_driver(driver, "TestLedgerGatingContrast")
        assert proc.returncode == 0, (
            "gating-contrast driver failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )
