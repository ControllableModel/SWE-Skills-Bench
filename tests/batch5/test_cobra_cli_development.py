"""Tests for the `cobra-cli-development` skill (variant ext5).

Skill task: add a brand-new, fully offline `gh digest` cobra command to the
GitHub CLI (github.com/cli/cli/v2). The command:
  * is a single command (no subcommands) built via
    `NewCmdDigest(f *cmdutil.Factory) *cobra.Command`, registered on the root;
  * takes exactly one positional argument (the literal input string), enforced
    via cobra's standard args validation;
  * has a **required** `--encoding`/`-e` flag selecting `hex` or `base64`;
  * has boolean `--upper` and `--lower` flags that are **mutually exclusive**;
  * computes a CRC32 (IEEE) checksum of the input bytes and renders it in the
    chosen encoding (lowercase 8-char hex by default, upper/lower controllable;
    standard base64 of the 4 big-endian checksum bytes);
  * prints exactly one line to stdout on success, nothing to stderr;
  * returns errors via `error` (no os.Exit/panic) and leaks no flag state.

Verification strategy (discriminative):
  * L1 checks confirm the deliverable files exist, are well-formed Go, declare
    the required constructor signature, and that the package + root build.
  * L2 checks DO NOT trust the agent's own `digest_test.go`. Each relevant case
    writes an *independent* white-box Go driver into the digest package, builds
    a fresh command per case via the agent's `NewCmdDigest(f)`, drives it with
    cobra's `SetArgs` + redirected streams, and asserts on real captured
    stdout/stderr/error behavior and on the EXACT expected checksum values
    (CRC32("hello") == 0x3610a686). A naive/hardcoded solution that ignores the
    input, omits the required flag, skips mutual-exclusion, or hardcodes output
    fails to compile or produces wrong bytes, failing these tests.

Native command: `go test ./pkg/cmd/digest/...` plus targeted `go build`.
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
DIGEST_PKG_DIR = os.path.join(REPO_DIR, "pkg", "cmd", "digest")
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
    """Write an independent driver test into the digest package; return its path.

    Placed inside the agent-created package so it can call the exported
    NewCmdDigest in package `digest`. Unique name avoids clashes across runs.
    """
    name = "zz_skilltest_%s_test.go" % uuid.uuid4().hex[:10]
    path = os.path.join(DIGEST_PKG_DIR, name)
    with open(path, "w") as fh:
        fh.write(go_source)
    return path


def _run_driver(go_source, run_regex, timeout=GO_TIMEOUT):
    """Drop a driver test into the digest package, run only it, then clean up."""
    assert os.path.isdir(DIGEST_PKG_DIR), (
        "digest package dir missing: %s" % DIGEST_PKG_DIR
    )
    path = _write_driver(go_source)
    try:
        return _run_go(
            ["go", "test", "-count=1", "-run", run_regex,
             "./pkg/cmd/digest/"],
            timeout=timeout,
        )
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


# Shared Go preamble for white-box driver tests living in package `digest`.
# buildCmd constructs a FRESH digest command per call and wires capturable
# streams onto both IOStreams (handler output) and the cobra command (cobra
# emitted output such as required-flag / mutual-exclusion / arg-count errors).
_DRIVER_HEADER = textwrap.dedent(
    """
    package digest

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
        cmd := NewCmdDigest(f)
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
        """L1: digest.go, digest_test.go, and the modified root.go are present."""
        required = [
            os.path.join(DIGEST_PKG_DIR, "digest.go"),
            os.path.join(DIGEST_PKG_DIR, "digest_test.go"),
            os.path.join(REPO_DIR, "pkg", "cmd", "root", "root.go"),
        ]
        missing = [p for p in required if not os.path.isfile(p)]
        assert not missing, "missing deliverable files: %s" % missing

    def test_package_declaration_and_constructor(self):
        """L1: digest.go declares `package digest` and exposes NewCmdDigest."""
        path = os.path.join(DIGEST_PKG_DIR, "digest.go")
        with open(path) as fh:
            src = fh.read()
        assert re.search(r"^\s*package\s+digest\b", src, re.MULTILINE), (
            "digest.go must declare `package digest`"
        )
        assert re.search(
            r"func\s+NewCmdDigest\s*\(\s*\w+\s+\*cmdutil\.Factory\s*\)\s*\*cobra\.Command",
            src,
        ), "NewCmdDigest(f *cmdutil.Factory) *cobra.Command signature required"

    def test_no_direct_os_stdout_writes(self):
        """L1: handler must not write directly to os.Stdout/os.Stderr."""
        path = os.path.join(DIGEST_PKG_DIR, "digest.go")
        with open(path) as fh:
            src = fh.read()
        assert "os.Stdout" not in src, (
            "digest.go must not write directly to os.Stdout (use IOStreams)"
        )
        assert "os.Stderr" not in src, (
            "digest.go must not write directly to os.Stderr (use IOStreams)"
        )
        assert "os.Exit" not in src, (
            "digest.go must not call os.Exit; return an error instead"
        )

    def test_digest_package_builds(self):
        """L1: the new package and the modified root package both compile."""
        proc = _run_go(
            ["go", "build", "./pkg/cmd/digest/...", "./pkg/cmd/root/..."]
        )
        assert proc.returncode == 0, (
            "go build failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_root_registers_digest(self):
        """L1: root.go imports and registers the digest command."""
        root = os.path.join(REPO_DIR, "pkg", "cmd", "root", "root.go")
        with open(root) as fh:
            src = fh.read()
        assert "cmd/digest" in src, "root.go must import the digest package"
        assert "NewCmdDigest" in src, (
            "root.go must call NewCmdDigest to register the command"
        )

    # ------------------------------------------------------------------ L2 ---
    def test_agent_native_tests_pass(self):
        """L2: the package's own test suite passes (go test ./pkg/cmd/digest/...)."""
        proc = _run_go(["go", "test", "-count=1", "./pkg/cmd/digest/..."])
        assert proc.returncode == 0, (
            "go test ./pkg/cmd/digest/... failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_hex_default_lowercase_value(self):
        """L2: `digest hello -e hex` prints exactly CRC32("hello") as 8 lc hex chars."""
        driver = _DRIVER_HEADER + textwrap.dedent(
            """
            func TestDigestHexDefault(t *testing.T) {
                out, errBuf, err := buildCmd([]string{"hello", "-e", "hex"})
                if err != nil {
                    t.Fatalf("hex digest errored: %v (stderr=%s)", err, errBuf.String())
                }
                if strings.TrimSpace(errBuf.String()) != "" {
                    t.Fatalf("nothing should go to stderr on success; got: %q", errBuf.String())
                }
                got := strings.TrimSpace(out.String())
                if got != "3610a686" {
                    t.Fatalf("CRC32(hello) hex must be 3610a686; got %q", got)
                }
                // Exactly one printed line.
                lines := 0
                for _, ln := range strings.Split(strings.TrimRight(out.String(), "\\n"), "\\n") {
                    if strings.TrimSpace(ln) != "" {
                        lines++
                    }
                }
                if lines != 1 {
                    t.Fatalf("expected exactly one output line; got %d:\\n%s", lines, out.String())
                }
            }
            """
        )
        proc = _run_driver(driver, "TestDigestHexDefault")
        assert proc.returncode == 0, (
            "hex-default driver failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_hex_depends_on_input_not_hardcoded(self):
        """L2: a different input yields a different, correct CRC32 (no hardcoding)."""
        driver = _DRIVER_HEADER + textwrap.dedent(
            """
            func TestDigestHexInputSensitive(t *testing.T) {
                // CRC32("hello") = 0x3610a686 ; CRC32("world") = 0x3a771143.
                hOut, _, err := buildCmd([]string{"hello", "-e", "hex"})
                if err != nil {
                    t.Fatalf("hello errored: %v", err)
                }
                wOut, _, err := buildCmd([]string{"world", "-e", "hex"})
                if err != nil {
                    t.Fatalf("world errored: %v", err)
                }
                h := strings.TrimSpace(hOut.String())
                w := strings.TrimSpace(wOut.String())
                if h != "3610a686" {
                    t.Fatalf("hello hex wrong: %q", h)
                }
                if w != "3a771143" {
                    t.Fatalf("world hex wrong (input ignored / hardcoded?): %q", w)
                }
                if h == w {
                    t.Fatalf("different inputs produced identical digests; input ignored")
                }
                // Empty string has CRC32 0 -> 00000000.
                eOut, _, err := buildCmd([]string{"", "-e", "hex"})
                if err != nil {
                    t.Fatalf("empty input errored: %v", err)
                }
                if strings.TrimSpace(eOut.String()) != "00000000" {
                    t.Fatalf("CRC32(empty) hex must be 00000000; got %q", eOut.String())
                }
            }
            """
        )
        proc = _run_driver(driver, "TestDigestHexInputSensitive")
        assert proc.returncode == 0, (
            "hex-input-sensitive driver failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_hex_upper_and_lower_casing(self):
        """L2: --upper uppercases hex, --lower lowercases; value otherwise identical."""
        driver = _DRIVER_HEADER + textwrap.dedent(
            """
            func TestDigestHexCasing(t *testing.T) {
                upOut, _, err := buildCmd([]string{"hello", "-e", "hex", "--upper"})
                if err != nil {
                    t.Fatalf("--upper errored: %v", err)
                }
                up := strings.TrimSpace(upOut.String())
                if up != "3610A686" {
                    t.Fatalf("--upper hex must be 3610A686; got %q", up)
                }
                loOut, _, err := buildCmd([]string{"hello", "-e", "hex", "--lower"})
                if err != nil {
                    t.Fatalf("--lower errored: %v", err)
                }
                lo := strings.TrimSpace(loOut.String())
                if lo != "3610a686" {
                    t.Fatalf("--lower hex must be 3610a686; got %q", lo)
                }
                if strings.ToLower(up) != lo {
                    t.Fatalf("upper/lower disagree on underlying value: %q vs %q", up, lo)
                }
            }
            """
        )
        proc = _run_driver(driver, "TestDigestHexCasing")
        assert proc.returncode == 0, (
            "hex-casing driver failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_base64_value_and_no_casing_effect(self):
        """L2: base64 of the 4 big-endian checksum bytes; --upper has no casing effect."""
        driver = _DRIVER_HEADER + textwrap.dedent(
            """
            func TestDigestBase64(t *testing.T) {
                out, errBuf, err := buildCmd([]string{"hello", "-e", "base64"})
                if err != nil {
                    t.Fatalf("base64 digest errored: %v (stderr=%s)", err, errBuf.String())
                }
                got := strings.TrimSpace(out.String())
                // standard base64 of bytes {0x36,0x10,0xa6,0x86} == "NhCmhg==".
                if got != "NhCmhg==" {
                    t.Fatalf("base64 digest of hello must be NhCmhg==; got %q", got)
                }
                // --upper has NO casing effect under base64.
                upOut, _, err := buildCmd([]string{"hello", "-e", "base64", "--upper"})
                if err != nil {
                    t.Fatalf("base64 --upper errored: %v", err)
                }
                if strings.TrimSpace(upOut.String()) != "NhCmhg==" {
                    t.Fatalf("base64 must be unaffected by --upper; got %q", upOut.String())
                }
            }
            """
        )
        proc = _run_driver(driver, "TestDigestBase64")
        assert proc.returncode == 0, (
            "base64 driver failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_missing_required_encoding_flag_rejected_no_stdout(self):
        """L2: omitting --encoding fails (cobra required-flag) and prints no stdout."""
        driver = _DRIVER_HEADER + textwrap.dedent(
            """
            func TestDigestRequiredFlag(t *testing.T) {
                out, _, err := buildCmd([]string{"hello"})
                if err == nil {
                    t.Fatalf("missing --encoding must fail before the handler")
                }
                if strings.TrimSpace(out.String()) != "" {
                    t.Fatalf("missing-required-flag must not produce stdout; got:\\n%s", out.String())
                }
                msg := strings.ToLower(err.Error())
                if !strings.Contains(msg, "required") || !strings.Contains(msg, "encoding") {
                    t.Fatalf("expected cobra required-flag error naming `encoding`; got: %v", err)
                }
            }
            """
        )
        proc = _run_driver(driver, "TestDigestRequiredFlag")
        assert proc.returncode == 0, (
            "required-flag driver failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_upper_lower_mutually_exclusive_no_stdout(self):
        """L2: --upper + --lower together fails (cobra mutual-exclusion), no stdout."""
        driver = _DRIVER_HEADER + textwrap.dedent(
            """
            func TestDigestMutualExclusion(t *testing.T) {
                out, _, err := buildCmd([]string{"hello", "-e", "hex", "--upper", "--lower"})
                if err == nil {
                    t.Fatalf("--upper with --lower must be rejected")
                }
                if strings.TrimSpace(out.String()) != "" {
                    t.Fatalf("mutual-exclusion error must not produce stdout; got:\\n%s", out.String())
                }
                msg := strings.ToLower(err.Error())
                // cobra emits: "if any flags in the group [upper lower] are set none of the others can be"
                if !strings.Contains(msg, "upper") || !strings.Contains(msg, "lower") {
                    t.Fatalf("expected mutual-exclusion error naming both flags; got: %v", err)
                }
            }
            """
        )
        proc = _run_driver(driver, "TestDigestMutualExclusion")
        assert proc.returncode == 0, (
            "mutual-exclusion driver failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_argument_count_errors(self):
        """L2: zero or two positional args fail with cobra's arg-count error."""
        driver = _DRIVER_HEADER + textwrap.dedent(
            """
            func TestDigestArgCount(t *testing.T) {
                // Zero positional args (but encoding provided).
                out0, _, err0 := buildCmd([]string{"-e", "hex"})
                if err0 == nil {
                    t.Fatalf("zero positional args must error (cobra arg-count)")
                }
                if strings.TrimSpace(out0.String()) != "" {
                    t.Fatalf("arg-count error must not print stdout; got:\\n%s", out0.String())
                }
                // Two positional args.
                out2, _, err2 := buildCmd([]string{"a", "b", "-e", "hex"})
                if err2 == nil {
                    t.Fatalf("two positional args must error (cobra arg-count)")
                }
                if !strings.Contains(strings.ToLower(err0.Error()), "arg") {
                    t.Fatalf("zero-arg error should be a cobra arg-count error; got: %v", err0)
                }
                if !strings.Contains(strings.ToLower(err2.Error()), "arg") {
                    t.Fatalf("two-arg error should be a cobra arg-count error; got: %v", err2)
                }
            }
            """
        )
        proc = _run_driver(driver, "TestDigestArgCount")
        assert proc.returncode == 0, (
            "arg-count driver failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_determinism_and_no_leaked_flag_state(self):
        """L2: identical input+flags -> byte-identical output across fresh commands."""
        driver = _DRIVER_HEADER + textwrap.dedent(
            """
            func TestDigestDeterminism(t *testing.T) {
                a, _, err := buildCmd([]string{"hello", "-e", "hex"})
                if err != nil {
                    t.Fatalf("run a errored: %v", err)
                }
                b, _, err := buildCmd([]string{"hello", "-e", "hex"})
                if err != nil {
                    t.Fatalf("run b errored: %v", err)
                }
                if a.String() != b.String() {
                    t.Fatalf("non-deterministic output:\\n--a--\\n%s\\n--b--\\n%s", a.String(), b.String())
                }
                // A prior --upper invocation must not leak casing into a fresh default run.
                _, _, err = buildCmd([]string{"hello", "-e", "hex", "--upper"})
                if err != nil {
                    t.Fatalf("upper run errored: %v", err)
                }
                c, _, err := buildCmd([]string{"hello", "-e", "hex"})
                if err != nil {
                    t.Fatalf("fresh default run errored: %v", err)
                }
                if strings.TrimSpace(c.String()) != "3610a686" {
                    t.Fatalf("default hex after --upper leaked casing; got %q", c.String())
                }
            }
            """
        )
        proc = _run_driver(driver, "TestDigestDeterminism")
        assert proc.returncode == 0, (
            "determinism driver failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )
