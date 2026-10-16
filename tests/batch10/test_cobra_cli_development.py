"""Tests for the `cobra-cli-development` skill (variant ext10).

Skill task: add a brand-new, fully offline `gh roster` cobra command to the
GitHub CLI (github.com/cli/cli/v2). The command, constructed via
`NewCmdRoster(f *cmdutil.Factory) *cobra.Command` and registered on the root
command, declares a fixed closed set of valid role tokens through cobra's
`ValidArgs` (e.g. lead, dev, qa, ops) and validates its positional arguments
with TWO validators *composed into the single Args slot*:

  1. cobra's "only valid args" check against `ValidArgs` -> an unknown token
     must fail with cobra's standard invalid-argument error.
  2. a custom validator requiring at least one argument and rejecting any
     repeated role token, naming the duplicate in the error.

Both rules run BEFORE the handler; supplying zero args, an unknown token, or a
duplicate token must all fail with nothing written to stdout. On valid input
the handler prints each accepted role token on its own line, in the supplied
order, to stdout (nothing on stderr).

Verification strategy (discriminative):
  * L1 checks confirm the deliverable files exist, declare `package roster`,
    expose `NewCmdRoster`, that root.go registers the command, and that the
    package + root build.
  * L2 checks DO NOT trust the agent's own `roster_test.go`. Each relevant case
    writes an *independent* white-box Go driver test into the roster package,
    builds a FRESH command per case via `NewCmdRoster(f)`, drives it with
    cobra's `SetArgs` + redirected streams, and asserts on real captured
    stdout / stderr / error / completion behaviour.

    A naive/stub solution fails here: e.g. one that checks duplicates inside the
    handler (so stdout leaks before the error), or that omits the closed-set
    `ValidArgs` validation, or that prints a fixed roster ignoring the args
    order, or that allows zero args, all fail concrete assertions below.

Native command: `go test ./pkg/cmd/roster/...` plus targeted `go build`.
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
ROSTER_PKG_DIR = os.path.join(REPO_DIR, "pkg", "cmd", "roster")
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
    """Write an independent white-box driver test into the roster package."""
    name = "zz_skilltest_%s_test.go" % uuid.uuid4().hex[:10]
    path = os.path.join(ROSTER_PKG_DIR, name)
    with open(path, "w") as fh:
        fh.write(go_source)
    return path


def _run_driver(go_source, run_regex, timeout=GO_TIMEOUT):
    """Drop a driver test into the roster package, run only it, then clean up."""
    assert os.path.isdir(ROSTER_PKG_DIR), (
        "roster package dir missing: %s" % ROSTER_PKG_DIR
    )
    path = _write_driver(go_source)
    try:
        return _run_go(
            ["go", "test", "-count=1", "-run", run_regex, "./pkg/cmd/roster/"],
            timeout=timeout,
        )
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


# Shared Go preamble for white-box driver tests living in package `roster`.
# buildCmd builds a FRESH command per call (proving no leaked state) and wires
# capturable streams onto both the IOStreams (used by the handler) and the cobra
# command (used by cobra-emitted output such as arg-validation errors).
_DRIVER_HEADER = textwrap.dedent(
    """
    package roster

    import (
        "bytes"
        "strings"
        "testing"

        "github.com/cli/cli/v2/pkg/cmdutil"
        "github.com/cli/cli/v2/pkg/iostreams"
    )

    func buildCmd(args []string) (*bytes.Buffer, *bytes.Buffer, error) {
        ios, _, outBuf, errBuf := iostreams.Test()
        f := &cmdutil.Factory{IOStreams: ios}
        cmd := NewCmdRoster(f)
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

    var _ = strings.TrimSpace
    """
)


class TestCobraCliDevelopment:
    REPO_DIR = _find_repo_dir("/workspace/cli")

    # ------------------------------------------------------------------ L1 ---
    def test_deliverable_files_exist(self):
        """L1: roster.go + roster_test.go and modified root.go are present."""
        required = [
            os.path.join(ROSTER_PKG_DIR, "roster.go"),
            os.path.join(ROSTER_PKG_DIR, "roster_test.go"),
            os.path.join(REPO_DIR, "pkg", "cmd", "root", "root.go"),
        ]
        missing = [p for p in required if not os.path.isfile(p)]
        assert not missing, "missing deliverable files: %s" % missing

    def test_package_declaration_and_constructor(self):
        """L1: roster.go declares `package roster` and exposes NewCmdRoster."""
        ref = os.path.join(ROSTER_PKG_DIR, "roster.go")
        with open(ref) as fh:
            src = fh.read()
        assert re.search(r"^\s*package\s+roster\b", src, re.MULTILINE), (
            "roster.go must declare `package roster`"
        )
        assert re.search(
            r"func\s+NewCmdRoster\s*\(\s*\w+\s+\*cmdutil\.Factory\s*\)\s*\*cobra\.Command",
            src,
        ), "NewCmdRoster(f *cmdutil.Factory) *cobra.Command signature required"

    def test_no_direct_os_stdout_writes(self):
        """L1: handler must use IOStreams, not write os.Stdout/os.Stderr directly."""
        ref = os.path.join(ROSTER_PKG_DIR, "roster.go")
        with open(ref) as fh:
            src = fh.read()
        assert "os.Stdout" not in src, (
            "roster.go must not write directly to os.Stdout"
        )
        assert "os.Stderr" not in src, (
            "roster.go must not write directly to os.Stderr"
        )

    def test_roster_package_builds(self):
        """L1: the new package and the modified root package both compile."""
        proc = _run_go(
            ["go", "build", "./pkg/cmd/roster/...", "./pkg/cmd/root/..."]
        )
        assert proc.returncode == 0, (
            "go build failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_root_registers_roster(self):
        """L1: root.go imports and registers the roster command."""
        root = os.path.join(REPO_DIR, "pkg", "cmd", "root", "root.go")
        with open(root) as fh:
            src = fh.read()
        assert "cmd/roster" in src, "root.go must import the roster package"
        assert "NewCmdRoster" in src, (
            "root.go must call NewCmdRoster to register the command"
        )

    # ------------------------------------------------------------------ L2 ---
    def test_agent_native_tests_pass(self):
        """L2: the package's own test suite passes (go test ./pkg/cmd/roster/...)."""
        proc = _run_go(["go", "test", "-count=1", "./pkg/cmd/roster/..."])
        assert proc.returncode == 0, (
            "go test ./pkg/cmd/roster/... failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_valid_roster_prints_tokens_in_supplied_order(self):
        """L2: valid tokens print one-per-line in the SUPPLIED order, nothing on stderr."""
        driver = _DRIVER_HEADER + textwrap.dedent(
            """
            func TestRosterValidOrder(t *testing.T) {
                // Two different orderings of the same valid tokens must produce
                // different (order-preserving) output -- a fixed/sorted roster fails.
                out1, errBuf1, err1 := buildCmd([]string{"dev", "lead", "qa"})
                if err1 != nil {
                    t.Fatalf("valid roster errored: %v (stderr=%s)", err1, errBuf1.String())
                }
                if strings.TrimSpace(errBuf1.String()) != "" {
                    t.Fatalf("valid roster wrote to stderr: %q", errBuf1.String())
                }
                got1 := nonEmptyLines(out1.String())
                want1 := []string{"dev", "lead", "qa"}
                if len(got1) != len(want1) {
                    t.Fatalf("expected %d lines, got %d:\\n%s", len(want1), len(got1), out1.String())
                }
                for i := range want1 {
                    if strings.TrimSpace(got1[i]) != want1[i] {
                        t.Fatalf("line %d: want %q got %q (full:\\n%s)", i, want1[i], got1[i], out1.String())
                    }
                }

                out2, _, err2 := buildCmd([]string{"qa", "dev", "lead"})
                if err2 != nil {
                    t.Fatalf("second valid roster errored: %v", err2)
                }
                got2 := nonEmptyLines(out2.String())
                want2 := []string{"qa", "dev", "lead"}
                for i := range want2 {
                    if strings.TrimSpace(got2[i]) != want2[i] {
                        t.Fatalf("order not preserved: want %q got %q", want2[i], got2[i])
                    }
                }
                if out1.String() == out2.String() {
                    t.Fatalf("different argument orders yielded identical output -> order ignored")
                }
            }
            """
        )
        proc = _run_driver(driver, "TestRosterValidOrder")
        assert proc.returncode == 0, (
            "valid-order driver failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_single_valid_token_succeeds(self):
        """L2: a single valid token is accepted and printed (>=1 arg requirement met)."""
        driver = _DRIVER_HEADER + textwrap.dedent(
            """
            func TestRosterSingle(t *testing.T) {
                out, _, err := buildCmd([]string{"lead"})
                if err != nil {
                    t.Fatalf("single valid token errored: %v", err)
                }
                got := nonEmptyLines(out.String())
                if len(got) != 1 || strings.TrimSpace(got[0]) != "lead" {
                    t.Fatalf("expected exactly one line 'lead', got:\\n%s", out.String())
                }
            }
            """
        )
        proc = _run_driver(driver, "TestRosterSingle")
        assert proc.returncode == 0, (
            "single-token driver failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_zero_args_rejected_no_stdout(self):
        """L2: no args -> error (at least one role required) and NO stdout."""
        driver = _DRIVER_HEADER + textwrap.dedent(
            """
            func TestRosterZeroArgs(t *testing.T) {
                out, _, err := buildCmd([]string{})
                if err == nil {
                    t.Fatalf("zero args must be rejected (at least one role required)")
                }
                if strings.TrimSpace(out.String()) != "" {
                    t.Fatalf("zero args must print nothing to stdout; got:\\n%s", out.String())
                }
            }
            """
        )
        proc = _run_driver(driver, "TestRosterZeroArgs")
        assert proc.returncode == 0, (
            "zero-args driver failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_unknown_token_rejected_closed_set_no_stdout(self):
        """L2: an unknown token fails the closed-set check, names the token, no stdout."""
        driver = _DRIVER_HEADER + textwrap.dedent(
            """
            func TestRosterUnknown(t *testing.T) {
                // 'lead' is valid, 'boss' is not -> closed-set validation must reject
                // BEFORE the handler runs, so nothing is printed for the valid prefix.
                out, _, err := buildCmd([]string{"lead", "boss"})
                if err == nil {
                    t.Fatalf("unknown token 'boss' must be rejected by closed-set validation")
                }
                if !strings.Contains(err.Error(), "boss") {
                    t.Fatalf("error must name the invalid token 'boss'; got: %v", err)
                }
                if strings.TrimSpace(out.String()) != "" {
                    t.Fatalf("rejected roster must not leak stdout (handler ran early?); got:\\n%s",
                        out.String())
                }
                // A lone unknown token must also fail.
                out2, _, err2 := buildCmd([]string{"nope"})
                if err2 == nil {
                    t.Fatalf("lone unknown token must be rejected")
                }
                if strings.TrimSpace(out2.String()) != "" {
                    t.Fatalf("lone unknown token must not print stdout; got:\\n%s", out2.String())
                }
            }
            """
        )
        proc = _run_driver(driver, "TestRosterUnknown")
        assert proc.returncode == 0, (
            "unknown-token driver failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_duplicate_token_rejected_names_token_no_stdout(self):
        """L2: a repeated valid token fails the CUSTOM validator, naming it, no stdout."""
        driver = _DRIVER_HEADER + textwrap.dedent(
            """
            func TestRosterDuplicate(t *testing.T) {
                // 'lead' twice: both tokens are in the valid set, so this must fail
                // the *custom* uniqueness rule -- proving the two validators are
                // composed (closed-set alone would NOT catch this).
                out, _, err := buildCmd([]string{"lead", "lead"})
                if err == nil {
                    t.Fatalf("duplicate token must be rejected by the custom validator")
                }
                if !strings.Contains(err.Error(), "lead") {
                    t.Fatalf("duplicate error must name the repeated token 'lead'; got: %v", err)
                }
                if strings.TrimSpace(out.String()) != "" {
                    t.Fatalf("duplicate roster must not leak stdout; got:\\n%s", out.String())
                }
                // Duplicate not adjacent, mixed with other valid tokens.
                out2, _, err2 := buildCmd([]string{"dev", "qa", "dev"})
                if err2 == nil {
                    t.Fatalf("non-adjacent duplicate 'dev' must be rejected")
                }
                if !strings.Contains(err2.Error(), "dev") {
                    t.Fatalf("error must name repeated token 'dev'; got: %v", err2)
                }
                if strings.TrimSpace(out2.String()) != "" {
                    t.Fatalf("duplicate roster must not leak stdout; got:\\n%s", out2.String())
                }
            }
            """
        )
        proc = _run_driver(driver, "TestRosterDuplicate")
        assert proc.returncode == 0, (
            "duplicate driver failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_valid_args_set_is_the_intended_role_set(self):
        """L2: the command's declared ValidArgs equals the intended closed role set."""
        driver = _DRIVER_HEADER + textwrap.dedent(
            """
            func TestRosterValidArgsSet(t *testing.T) {
                ios, _, _, _ := iostreams.Test()
                f := &cmdutil.Factory{IOStreams: ios}
                cmd := NewCmdRoster(f)
                got := map[string]bool{}
                for _, v := range cmd.ValidArgs {
                    got[v] = true
                }
                want := []string{"lead", "dev", "qa", "ops"}
                for _, w := range want {
                    if !got[w] {
                        t.Fatalf("ValidArgs must contain %q; got %v", w, cmd.ValidArgs)
                    }
                }
                if len(cmd.ValidArgs) != len(want) {
                    t.Fatalf("ValidArgs must equal the intended set %v; got %v", want, cmd.ValidArgs)
                }
            }
            """
        )
        proc = _run_driver(driver, "TestRosterValidArgsSet")
        assert proc.returncode == 0, (
            "validargs-set driver failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_completion_offers_valid_role_tokens(self):
        """L2: static positional completion offers exactly the valid role tokens."""
        driver = _DRIVER_HEADER + textwrap.dedent(
            """
            func TestRosterCompletion(t *testing.T) {
                // Drive cobra's hidden __complete on a fresh tree (empty prefix).
                out, _, _ := buildCmd([]string{"__complete", ""})
                comp := out.String()
                for _, want := range []string{"lead", "dev", "qa", "ops"} {
                    if !strings.Contains(comp, want) {
                        t.Fatalf("completion must offer valid token %q; got:\\n%s", want, comp)
                    }
                }
                // An unrelated token must NOT be offered.
                if strings.Contains(comp, "boss") {
                    t.Fatalf("completion offered an invalid token 'boss':\\n%s", comp)
                }
            }
            """
        )
        proc = _run_driver(driver, "TestRosterCompletion")
        assert proc.returncode == 0, (
            "completion driver failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_fresh_command_per_invocation_deterministic(self):
        """L2: a fresh command per invocation yields identical results (no leaked state)."""
        driver = _DRIVER_HEADER + textwrap.dedent(
            """
            func TestRosterFresh(t *testing.T) {
                a, _, err := buildCmd([]string{"lead", "dev"})
                if err != nil {
                    t.Fatalf("first invocation errored: %v", err)
                }
                // A failing invocation in between must not corrupt later state.
                _, _, ferr := buildCmd([]string{"lead", "lead"})
                if ferr == nil {
                    t.Fatalf("expected duplicate to fail")
                }
                b, _, err := buildCmd([]string{"lead", "dev"})
                if err != nil {
                    t.Fatalf("third invocation errored: %v", err)
                }
                if a.String() != b.String() {
                    t.Fatalf("fresh-command outputs differ (state leak?):\\n--a--\\n%s\\n--b--\\n%s",
                        a.String(), b.String())
                }
            }
            """
        )
        proc = _run_driver(driver, "TestRosterFresh")
        assert proc.returncode == 0, (
            "fresh-command driver failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )
