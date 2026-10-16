"""Tests for the `cobra-cli-development` skill (variant ext8).

Skill task: add a brand-new, fully offline `gh redact` cobra command group to the
GitHub CLI (github.com/cli/cli/v2). The group has:
  * a parent `NewCmdRedact(f *cmdutil.Factory) *cobra.Command` that with no
    subcommand prints help and exits without error, and declares a single
    *persistent* string flag `--token`/`-t` inherited by BOTH subcommands;
  * a `mask <text>` subcommand with a *local* string flag `--with` (default `*`)
    that replaces each occurrence of the token with a run of that single mask
    character of equal length;
  * a `scan <text>` subcommand with a *local* boolean flag `--count` that prints
    the number of non-overlapping occurrences of the token (human line by
    default, bare integer with --count);
  * registration on the root command in pkg/cmd/root/root.go.
The defining property of this variant is FLAG SCOPING: `--token` is persistent
(usable on both leaves), `--with` is local to `mask` (rejected on `scan`), and
`--count` is local to `scan` (rejected on `mask`).

Verification strategy (discriminative):
  * L1 checks confirm the deliverable files exist, are well-formed Go, expose the
    required constructor signature, and that the package + root build.
  * L2 checks DO NOT trust the agent's own `redact_test.go`. Instead each case
    writes an *independent* white-box Go driver test into the redact package,
    builds a fresh command tree per case via the agent's `NewCmdRedact(f)`,
    drives it with cobra's `SetArgs` + redirected streams, and asserts on the
    real captured stdout/stderr/error behavior. A naive implementation that
    hardcodes output, ignores `--with`, miscounts, treats the token as
    overlapping, or wires the flags at the wrong scope fails these tests.

Native command: `go test ./pkg/cmd/redact/...` plus targeted `go build`.
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
REDACT_PKG_DIR = os.path.join(REPO_DIR, "pkg", "cmd", "redact")
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
    """Write an independent white-box driver test into the redact package."""
    name = "zz_skilltest_%s_test.go" % uuid.uuid4().hex[:10]
    path = os.path.join(REDACT_PKG_DIR, name)
    with open(path, "w") as fh:
        fh.write(go_source)
    return path


def _run_driver(go_source, run_regex, timeout=GO_TIMEOUT):
    """Drop a driver test into the redact package, run only it, then clean up."""
    assert os.path.isdir(REDACT_PKG_DIR), (
        "redact package dir missing: %s" % REDACT_PKG_DIR
    )
    path = _write_driver(go_source)
    try:
        return _run_go(
            ["go", "test", "-count=1", "-run", run_regex,
             "./pkg/cmd/redact/"],
            timeout=timeout,
        )
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


# Shared Go preamble for white-box driver tests living in package `redact`.
# buildTree constructs a FRESH command tree per call (no leaked flag state) and
# wires capturable streams onto both the IOStreams (handler output) and the
# cobra command (help / arg / flag errors).
_DRIVER_HEADER = textwrap.dedent(
    """
    package redact

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
        cmd := NewCmdRedact(f)
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
        """L1: the four new redact files + modified root.go are present on disk."""
        required = [
            os.path.join(REDACT_PKG_DIR, "redact.go"),
            os.path.join(REDACT_PKG_DIR, "mask.go"),
            os.path.join(REDACT_PKG_DIR, "scan.go"),
            os.path.join(REDACT_PKG_DIR, "redact_test.go"),
            os.path.join(REPO_DIR, "pkg", "cmd", "root", "root.go"),
        ]
        missing = [p for p in required if not os.path.isfile(p)]
        assert not missing, "missing deliverable files: %s" % missing

    def test_package_declaration_and_constructor(self):
        """L1: redact.go declares package redact and exposes NewCmdRedact."""
        ref = os.path.join(REDACT_PKG_DIR, "redact.go")
        with open(ref) as fh:
            src = fh.read()
        assert re.search(r"^\s*package\s+redact\b", src, re.MULTILINE), (
            "redact.go must declare `package redact`"
        )
        assert re.search(
            r"func\s+NewCmdRedact\s*\(\s*\w+\s+\*cmdutil\.Factory\s*\)\s*\*cobra\.Command",
            src,
        ), "NewCmdRedact(f *cmdutil.Factory) *cobra.Command signature required"

    def test_redact_package_builds(self):
        """L1: the new package and the modified root package both compile."""
        proc = _run_go(
            ["go", "build", "./pkg/cmd/redact/...", "./pkg/cmd/root/..."]
        )
        assert proc.returncode == 0, (
            "go build failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_root_registers_redact(self):
        """L1: root.go imports and registers the redact command group."""
        root = os.path.join(REPO_DIR, "pkg", "cmd", "root", "root.go")
        with open(root) as fh:
            src = fh.read()
        assert "cmd/redact" in src, (
            "root.go must import the redact package"
        )
        assert "NewCmdRedact" in src, (
            "root.go must call NewCmdRedact to register the group"
        )

    # ------------------------------------------------------------------ L2 ---
    def test_agent_native_tests_pass(self):
        """L2: the package's own test suite passes (go test ./pkg/cmd/redact/...)."""
        proc = _run_go(["go", "test", "-count=1", "./pkg/cmd/redact/..."])
        assert proc.returncode == 0, (
            "go test ./pkg/cmd/redact/... failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_parent_no_args_prints_help_no_error(self):
        """L2: `redact` with no subcommand prints help (lists mask+scan), no error."""
        driver = _DRIVER_HEADER + textwrap.dedent(
            """
            func TestRedactParentHelp(t *testing.T) {
                out, _, err := buildTree([]string{})
                if err != nil {
                    t.Fatalf("expected no error from bare parent, got %v", err)
                }
                s := out.String()
                if !strings.Contains(s, "mask") || !strings.Contains(s, "scan") {
                    t.Fatalf("help output must mention both subcommands; got:\\n%s", s)
                }
                low := strings.ToLower(s)
                if !strings.Contains(low, "usage") && !strings.Contains(low, "available commands") {
                    t.Fatalf("expected cobra help text, got:\\n%s", s)
                }
            }
            """
        )
        proc = _run_driver(driver, "TestRedactParentHelp")
        assert proc.returncode == 0, (
            "parent-help driver failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_token_persistent_flag_usable_on_both_subcommands(self):
        """L2: `--token` is persistent on the parent: usable from both mask and scan."""
        driver = _DRIVER_HEADER + textwrap.dedent(
            """
            func TestRedactTokenInherited(t *testing.T) {
                // mask must accept --token / -t.
                outM, errM, err := buildTree([]string{"mask", "abXYab", "-t", "ab"})
                if err != nil {
                    t.Fatalf("mask with -t errored (token not inherited?): %v (stderr=%s)",
                        err, errM.String())
                }
                if strings.TrimSpace(outM.String()) == "" {
                    t.Fatalf("mask with valid token produced no stdout")
                }
                // scan must also accept --token / -t.
                outS, errS, err := buildTree([]string{"scan", "ababab", "--token", "ab"})
                if err != nil {
                    t.Fatalf("scan with --token errored (token not inherited?): %v (stderr=%s)",
                        err, errS.String())
                }
                if strings.TrimSpace(outS.String()) == "" {
                    t.Fatalf("scan with valid token produced no stdout")
                }
            }
            """
        )
        proc = _run_driver(driver, "TestRedactTokenInherited")
        assert proc.returncode == 0, (
            "token-inherited driver failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_with_flag_local_to_mask_rejected_on_scan(self):
        """L2: `--with` is local to mask; supplying it on scan is an unknown-flag error."""
        driver = _DRIVER_HEADER + textwrap.dedent(
            """
            func TestRedactWithLocalToMask(t *testing.T) {
                // Accepted on mask.
                _, _, errOk := buildTree([]string{"mask", "abXYab", "-t", "ab", "--with", "#"})
                if errOk != nil {
                    t.Fatalf("mask must accept its own local --with flag; got: %v", errOk)
                }
                // Rejected on scan with cobra's unknown-flag error.
                out, _, err := buildTree([]string{"scan", "x", "-t", "z", "--with", "#"})
                if err == nil {
                    t.Fatalf("--with must be unknown on scan (it is local to mask)")
                }
                msg := strings.ToLower(err.Error())
                if !strings.Contains(msg, "unknown flag") && !strings.Contains(msg, "--with") {
                    t.Fatalf("expected unknown-flag error for --with on scan; got: %v", err)
                }
                if strings.TrimSpace(out.String()) != "" {
                    t.Fatalf("rejected scan --with must not write stdout; got:\\n%s", out.String())
                }
            }
            """
        )
        proc = _run_driver(driver, "TestRedactWithLocalToMask")
        assert proc.returncode == 0, (
            "with-local driver failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_count_flag_local_to_scan_rejected_on_mask(self):
        """L2: `--count` is local to scan; supplying it on mask is an unknown-flag error."""
        driver = _DRIVER_HEADER + textwrap.dedent(
            """
            func TestRedactCountLocalToScan(t *testing.T) {
                // Accepted on scan.
                _, _, errOk := buildTree([]string{"scan", "ababab", "-t", "ab", "--count"})
                if errOk != nil {
                    t.Fatalf("scan must accept its own local --count flag; got: %v", errOk)
                }
                // Rejected on mask with cobra's unknown-flag error.
                out, _, err := buildTree([]string{"mask", "x", "-t", "z", "--count"})
                if err == nil {
                    t.Fatalf("--count must be unknown on mask (it is local to scan)")
                }
                msg := strings.ToLower(err.Error())
                if !strings.Contains(msg, "unknown flag") && !strings.Contains(msg, "--count") {
                    t.Fatalf("expected unknown-flag error for --count on mask; got: %v", err)
                }
                if strings.TrimSpace(out.String()) != "" {
                    t.Fatalf("rejected mask --count must not write stdout; got:\\n%s", out.String())
                }
            }
            """
        )
        proc = _run_driver(driver, "TestRedactCountLocalToScan")
        assert proc.returncode == 0, (
            "count-local driver failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_mask_default_and_custom_char_replacement(self):
        """L2: mask replaces every token occurrence with an equal-length run of the mask char."""
        driver = _DRIVER_HEADER + textwrap.dedent(
            """
            func TestRedactMaskReplace(t *testing.T) {
                // Default mask char '*': token "ab" (len 2) -> "**".
                outDef, _, err := buildTree([]string{"mask", "abXYab", "-t", "ab"})
                if err != nil {
                    t.Fatalf("mask default errored: %v", err)
                }
                if strings.TrimSpace(outDef.String()) != "**XY**" {
                    t.Fatalf("mask default: want %q got %q", "**XY**", strings.TrimSpace(outDef.String()))
                }
                // Custom mask char '#'.
                outHash, _, err := buildTree([]string{"mask", "abXYab", "-t", "ab", "--with", "#"})
                if err != nil {
                    t.Fatalf("mask --with # errored: %v", err)
                }
                if strings.TrimSpace(outHash.String()) != "##XY##" {
                    t.Fatalf("mask --with #: want %q got %q", "##XY##", strings.TrimSpace(outHash.String()))
                }
                // Equal-length property for a longer token: replacement length == token length.
                outLong, _, err := buildTree([]string{"mask", "Xsecretsecret", "-t", "secret"})
                if err != nil {
                    t.Fatalf("mask long-token errored: %v", err)
                }
                if strings.TrimSpace(outLong.String()) != "X"+strings.Repeat("*", 6)+strings.Repeat("*", 6) {
                    t.Fatalf("mask long token want %q got %q",
                        "X"+strings.Repeat("*", 12), strings.TrimSpace(outLong.String()))
                }
            }
            """
        )
        proc = _run_driver(driver, "TestRedactMaskReplace")
        assert proc.returncode == 0, (
            "mask-replace driver failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_mask_requires_single_char_and_nonempty_token(self):
        """L2: mask errors (no stdout) when --with is not one char, or token is empty."""
        driver = _DRIVER_HEADER + textwrap.dedent(
            """
            func TestRedactMaskValidation(t *testing.T) {
                // Multi-char mask must error, no stdout.
                out1, _, err1 := buildTree([]string{"mask", "x", "-t", "z", "--with", "ab"})
                if err1 == nil {
                    t.Fatalf("multi-char --with must produce an error")
                }
                if strings.TrimSpace(out1.String()) != "" {
                    t.Fatalf("multi-char --with must not write stdout; got:\\n%s", out1.String())
                }
                // Empty token must error before output.
                out2, _, err2 := buildTree([]string{"mask", "x"})
                if err2 == nil {
                    t.Fatalf("empty --token must produce an error")
                }
                if strings.TrimSpace(out2.String()) != "" {
                    t.Fatalf("empty token must not write stdout; got:\\n%s", out2.String())
                }
                // Exactly-one-arg requirement: zero args must error.
                _, _, err3 := buildTree([]string{"mask", "-t", "z"})
                if err3 == nil {
                    t.Fatalf("mask with no positional arg must error (cobra arg-count)")
                }
            }
            """
        )
        proc = _run_driver(driver, "TestRedactMaskValidation")
        assert proc.returncode == 0, (
            "mask-validation driver failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_scan_counts_non_overlapping_occurrences(self):
        """L2: scan counts non-overlapping token occurrences; --count prints the bare integer."""
        driver = _DRIVER_HEADER + textwrap.dedent(
            """
            func TestRedactScanCount(t *testing.T) {
                // Human line must contain the count 3 for "ababab" / token "ab".
                outH, _, err := buildTree([]string{"scan", "ababab", "-t", "ab"})
                if err != nil {
                    t.Fatalf("scan human errored: %v", err)
                }
                if !strings.Contains(outH.String(), "3") {
                    t.Fatalf("scan human output must contain count 3; got:\\n%s", outH.String())
                }
                // Bare --count must be exactly "3".
                outC, _, err := buildTree([]string{"scan", "ababab", "-t", "ab", "--count"})
                if err != nil {
                    t.Fatalf("scan --count errored: %v", err)
                }
                if strings.TrimSpace(outC.String()) != "3" {
                    t.Fatalf("scan --count must print bare 3; got %q", strings.TrimSpace(outC.String()))
                }
                // Non-overlapping semantics: "aaaa" / token "aa" -> 2, not 3.
                outNO, _, err := buildTree([]string{"scan", "aaaa", "-t", "aa", "--count"})
                if err != nil {
                    t.Fatalf("scan non-overlap errored: %v", err)
                }
                if strings.TrimSpace(outNO.String()) != "2" {
                    t.Fatalf("non-overlapping count of \\"aa\\" in \\"aaaa\\" must be 2; got %q",
                        strings.TrimSpace(outNO.String()))
                }
                // Zero occurrences -> bare 0.
                outZ, _, err := buildTree([]string{"scan", "xyz", "-t", "ab", "--count"})
                if err != nil {
                    t.Fatalf("scan zero errored: %v", err)
                }
                if strings.TrimSpace(outZ.String()) != "0" {
                    t.Fatalf("zero occurrences must print 0; got %q", strings.TrimSpace(outZ.String()))
                }
            }
            """
        )
        proc = _run_driver(driver, "TestRedactScanCount")
        assert proc.returncode == 0, (
            "scan-count driver failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_scan_empty_token_and_arg_count_errors(self):
        """L2: scan errors (no stdout) on empty token and on wrong positional arg count."""
        driver = _DRIVER_HEADER + textwrap.dedent(
            """
            func TestRedactScanValidation(t *testing.T) {
                // Empty token must error before output.
                out1, _, err1 := buildTree([]string{"scan", "ababab"})
                if err1 == nil {
                    t.Fatalf("scan with empty --token must error")
                }
                if strings.TrimSpace(out1.String()) != "" {
                    t.Fatalf("empty-token scan must not write stdout; got:\\n%s", out1.String())
                }
                // Zero positional args must error (cobra arg-count).
                _, _, err2 := buildTree([]string{"scan", "-t", "ab"})
                if err2 == nil {
                    t.Fatalf("scan with no positional arg must error")
                }
                if !strings.Contains(strings.ToLower(err2.Error()), "arg") {
                    t.Fatalf("expected cobra arg-count error; got: %v", err2)
                }
                // Two positional args must error.
                _, _, err3 := buildTree([]string{"scan", "a", "b", "-t", "ab"})
                if err3 == nil {
                    t.Fatalf("scan with two positional args must error")
                }
            }
            """
        )
        proc = _run_driver(driver, "TestRedactScanValidation")
        assert proc.returncode == 0, (
            "scan-validation driver failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_deterministic_fresh_tree_no_state_leak(self):
        """L2: a fresh tree per invocation yields identical results (no leaked flag state)."""
        driver = _DRIVER_HEADER + textwrap.dedent(
            """
            func TestRedactNoLeak(t *testing.T) {
                // Run mask with a custom --with, then a default mask: the second
                // must NOT inherit the previous '#' mask char.
                _, _, err := buildTree([]string{"mask", "abXYab", "-t", "ab", "--with", "#"})
                if err != nil {
                    t.Fatalf("first mask errored: %v", err)
                }
                a, _, err := buildTree([]string{"mask", "abXYab", "-t", "ab"})
                if err != nil {
                    t.Fatalf("default mask errored: %v", err)
                }
                if strings.TrimSpace(a.String()) != "**XY**" {
                    t.Fatalf("default mask after custom --with leaked '#'; got %q",
                        strings.TrimSpace(a.String()))
                }
                // Repeated identical invocations must be byte-identical.
                b, _, err := buildTree([]string{"mask", "abXYab", "-t", "ab"})
                if err != nil {
                    t.Fatalf("repeat mask errored: %v", err)
                }
                if a.String() != b.String() {
                    t.Fatalf("repeated fresh mask outputs differ:\\n--a--\\n%s\\n--b--\\n%s",
                        a.String(), b.String())
                }
                // Same for scan --count.
                s1, _, _ := buildTree([]string{"scan", "ababab", "-t", "ab", "--count"})
                s2, _, _ := buildTree([]string{"scan", "ababab", "-t", "ab", "--count"})
                if s1.String() != s2.String() {
                    t.Fatalf("repeated scan --count differ: %q vs %q", s1.String(), s2.String())
                }
            }
            """
        )
        proc = _run_driver(driver, "TestRedactNoLeak")
        assert proc.returncode == 0, (
            "no-leak driver failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )
