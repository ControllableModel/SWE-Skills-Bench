"""Tests for the `cobra-cli-development` skill.

Skill task: add a brand-new, fully offline `gh reference` cobra command group to
the GitHub CLI (github.com/cli/cli/v2) with `list` and `show` subcommands, a
static in-process catalog, `--limit` flag, parent-level `--plain` flag,
case-insensitive `show`, dynamic topic completion, and registration on the root
command.

Verification strategy (discriminative):
  * L1 checks confirm the deliverable files exist, are well-formed Go, and that
    the package + root build.
  * L2 checks DO NOT trust the agent's own `reference_test.go`. Instead each
    relevant case writes an *independent* Go driver test into the reference
    package directory, builds a fresh command tree per case via the agent's
    `NewCmdReference(f)`, drives it with cobra's `SetArgs` + redirected streams,
    and asserts on real captured stdout/stderr/error/exit behavior. A naive or
    hardcoded solution that does not implement the required surface fails to
    compile or returns wrong output, failing these tests.

Native command: `go test ./pkg/cmd/reference/...` plus targeted `go build`.
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
REF_PKG_DIR = os.path.join(REPO_DIR, "pkg", "cmd", "reference")
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
    # Keep module mode; the repo vendors via go.sum/module cache.
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
    """Write an independent driver test into the reference package and return its path.

    The file name is unique so concurrent/repeat runs do not clash, and it is
    placed inside the agent-created package so it can call the unexported and
    exported identifiers in package `reference`.
    """
    name = "zz_skilltest_%s_test.go" % uuid.uuid4().hex[:10]
    path = os.path.join(REF_PKG_DIR, name)
    with open(path, "w") as fh:
        fh.write(go_source)
    return path


def _run_driver(go_source, run_regex, timeout=GO_TIMEOUT):
    """Drop a driver test into the reference package, run only it, then clean up.

    Returns the completed subprocess. The driver's package is `reference`
    (white-box) so it can construct the command tree via NewCmdReference.
    """
    assert os.path.isdir(REF_PKG_DIR), (
        "reference package dir missing: %s" % REF_PKG_DIR
    )
    path = _write_driver(go_source)
    try:
        return _run_go(
            ["go", "test", "-count=1", "-run", run_regex,
             "./pkg/cmd/reference/"],
            timeout=timeout,
        )
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


# Shared Go preamble for white-box driver tests living in package `reference`.
_DRIVER_HEADER = textwrap.dedent(
    """
    package reference

    import (
        "bytes"
        "strings"
        "testing"

        "github.com/cli/cli/v2/pkg/cmdutil"
        "github.com/cli/cli/v2/pkg/iostreams"
    )

    // buildTree constructs a fresh reference command tree and wires capturable
    // streams onto both the IOStreams (used by handlers) and the cobra command
    // (used by cobra-emitted output such as help / arg errors).
    func buildTree(args []string) (*bytes.Buffer, *bytes.Buffer, error) {
        ios, _, outBuf, errBuf := iostreams.Test()
        f := &cmdutil.Factory{IOStreams: ios}
        cmd := NewCmdReference(f)
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
        """L1: the four new files + modified root.go are present on disk."""
        required = [
            os.path.join(REF_PKG_DIR, "reference.go"),
            os.path.join(REF_PKG_DIR, "list.go"),
            os.path.join(REF_PKG_DIR, "show.go"),
            os.path.join(REF_PKG_DIR, "reference_test.go"),
            os.path.join(REPO_DIR, "pkg", "cmd", "root", "root.go"),
        ]
        missing = [p for p in required if not os.path.isfile(p)]
        assert not missing, "missing deliverable files: %s" % missing

    def test_package_declaration_and_constructor(self):
        """L1: reference.go declares package reference and exposes NewCmdReference."""
        ref = os.path.join(REF_PKG_DIR, "reference.go")
        with open(ref) as fh:
            src = fh.read()
        assert re.search(r"^\s*package\s+reference\b", src, re.MULTILINE), (
            "reference.go must declare `package reference`"
        )
        assert re.search(
            r"func\s+NewCmdReference\s*\(\s*\w+\s+\*cmdutil\.Factory\s*\)\s*\*cobra\.Command",
            src,
        ), "NewCmdReference(f *cmdutil.Factory) *cobra.Command signature required"

    def test_reference_package_builds(self):
        """L1: the new package and the modified root package both compile."""
        proc = _run_go(
            ["go", "build", "./pkg/cmd/reference/...", "./pkg/cmd/root/..."]
        )
        assert proc.returncode == 0, (
            "go build failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_root_registers_reference(self):
        """L1: root.go imports and registers the reference command group."""
        root = os.path.join(REPO_DIR, "pkg", "cmd", "root", "root.go")
        with open(root) as fh:
            src = fh.read()
        assert "cmd/reference" in src, (
            "root.go must import the reference package"
        )
        assert "NewCmdReference" in src, (
            "root.go must call NewCmdReference to register the group"
        )

    # ------------------------------------------------------------------ L2 ---
    def test_agent_native_tests_pass(self):
        """L2: the package's own test suite passes (go test ./pkg/cmd/reference/...)."""
        proc = _run_go(["go", "test", "-count=1", "./pkg/cmd/reference/..."])
        assert proc.returncode == 0, (
            "go test ./pkg/cmd/reference/... failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_parent_no_args_prints_help_no_error(self):
        """L2: `reference` with no subcommand prints help (lists list+show), no error."""
        driver = _DRIVER_HEADER + textwrap.dedent(
            """
            func TestRefParentHelp(t *testing.T) {
                out, _, err := buildTree([]string{})
                if err != nil {
                    t.Fatalf("expected no error from bare parent, got %v", err)
                }
                s := out.String()
                if !strings.Contains(s, "list") || !strings.Contains(s, "show") {
                    t.Fatalf("help output must mention both subcommands; got:\\n%s", s)
                }
                if !strings.Contains(strings.ToLower(s), "usage") &&
                    !strings.Contains(strings.ToLower(s), "available commands") {
                    t.Fatalf("expected cobra help text, got:\\n%s", s)
                }
            }
            """
        )
        proc = _run_driver(driver, "TestRefParentHelp")
        assert proc.returncode == 0, (
            "parent-help driver failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_list_prints_all_topics_in_order(self):
        """L2: `list` prints >=4 topics, name+summary per line, in stable catalog order."""
        driver = _DRIVER_HEADER + textwrap.dedent(
            """
            func TestRefListOrder(t *testing.T) {
                out, errBuf, err := buildTree([]string{"list"})
                if err != nil {
                    t.Fatalf("list returned error: %v (stderr=%s)", err, errBuf.String())
                }
                if strings.TrimSpace(errBuf.String()) != "" {
                    t.Fatalf("list wrote to stderr on success: %q", errBuf.String())
                }
                lines := []string{}
                for _, ln := range strings.Split(strings.TrimRight(out.String(), "\\n"), "\\n") {
                    if strings.TrimSpace(ln) != "" {
                        lines = append(lines, ln)
                    }
                }
                if len(lines) < 4 {
                    t.Fatalf("catalog must have >=4 topics; list printed %d lines:\\n%s",
                        len(lines), out.String())
                }
                // Each printed line must carry more than just a bare token
                // (name AND summary), so naive name-only output fails here.
                for i, ln := range lines {
                    fields := strings.Fields(ln)
                    if len(fields) < 2 {
                        t.Fatalf("line %d lacks a summary after the name: %q", i, ln)
                    }
                }
                // Order must be stable across two fresh builds.
                out2, _, err2 := buildTree([]string{"list"})
                if err2 != nil {
                    t.Fatalf("second list errored: %v", err2)
                }
                if out.String() != out2.String() {
                    t.Fatalf("list output not stable between fresh trees:\\n--1--\\n%s\\n--2--\\n%s",
                        out.String(), out2.String())
                }
            }
            """
        )
        proc = _run_driver(driver, "TestRefListOrder")
        assert proc.returncode == 0, (
            "list-order driver failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_list_limit_truncates(self):
        """L2: `list --limit 2` prints exactly the first two topics from `list`."""
        driver = _DRIVER_HEADER + textwrap.dedent(
            """
            func nonEmptyLines(s string) []string {
                out := []string{}
                for _, ln := range strings.Split(strings.TrimRight(s, "\\n"), "\\n") {
                    if strings.TrimSpace(ln) != "" {
                        out = append(out, ln)
                    }
                }
                return out
            }

            func TestRefListLimit(t *testing.T) {
                full, _, err := buildTree([]string{"list"})
                if err != nil {
                    t.Fatalf("full list errored: %v", err)
                }
                fullLines := nonEmptyLines(full.String())

                two, _, err := buildTree([]string{"list", "--limit", "2"})
                if err != nil {
                    t.Fatalf("--limit 2 errored: %v", err)
                }
                twoLines := nonEmptyLines(two.String())
                if len(twoLines) != 2 {
                    t.Fatalf("--limit 2 must print exactly 2 topics; got %d:\\n%s",
                        len(twoLines), two.String())
                }
                if len(fullLines) < 2 {
                    t.Fatalf("need >=2 topics to verify truncation")
                }
                // The first two truncated lines must equal the first two full lines.
                if twoLines[0] != fullLines[0] || twoLines[1] != fullLines[1] {
                    t.Fatalf("--limit 2 not the first two catalog topics.\\nfull:\\n%v\\ntwo:\\n%v",
                        fullLines[:2], twoLines)
                }
                // Short flag form must behave identically.
                twoShort, _, err := buildTree([]string{"list", "-L", "2"})
                if err != nil {
                    t.Fatalf("-L 2 errored: %v", err)
                }
                if two.String() != twoShort.String() {
                    t.Fatalf("-L and --limit disagree:\\n%q\\n%q", two.String(), twoShort.String())
                }
            }
            """
        )
        proc = _run_driver(driver, "TestRefListLimit")
        assert proc.returncode == 0, (
            "list-limit driver failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_list_limit_zero_rejected_no_output(self):
        """L2: `list --limit 0` is a flag error and produces no topic output."""
        driver = _DRIVER_HEADER + textwrap.dedent(
            """
            func TestRefListLimitZero(t *testing.T) {
                out, _, err := buildTree([]string{"list", "--limit", "0"})
                if err == nil {
                    t.Fatalf("--limit 0 must be rejected with an error")
                }
                if strings.TrimSpace(out.String()) != "" {
                    t.Fatalf("--limit 0 must not print topics to stdout; got:\\n%s", out.String())
                }
                // Negative is also below 1 and must be rejected.
                out2, _, err2 := buildTree([]string{"list", "--limit", "-3"})
                if err2 == nil {
                    t.Fatalf("--limit -3 must be rejected with an error")
                }
                if strings.TrimSpace(out2.String()) != "" {
                    t.Fatalf("--limit -3 must not print topics; got:\\n%s", out2.String())
                }
            }
            """
        )
        proc = _run_driver(driver, "TestRefListLimitZero")
        assert proc.returncode == 0, (
            "list-limit-zero driver failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_show_case_insensitive_hit_prints_summary_and_aliases(self):
        """L2: `show <TOPIC>` matches case-insensitively and prints summary (+aliases)."""
        driver = _DRIVER_HEADER + textwrap.dedent(
            """
            func nelShow(s string) []string {
                out := []string{}
                for _, ln := range strings.Split(strings.TrimRight(s, "\\n"), "\\n") {
                    if strings.TrimSpace(ln) != "" {
                        out = append(out, ln)
                    }
                }
                return out
            }

            // Discover a real catalog topic name from `list` output (first token).
            func firstTopicName(t *testing.T) string {
                out, _, err := buildTree([]string{"list"})
                if err != nil {
                    t.Fatalf("list errored: %v", err)
                }
                lines := nelShow(out.String())
                if len(lines) == 0 {
                    t.Fatalf("list produced no topics")
                }
                fields := strings.Fields(lines[0])
                if len(fields) == 0 {
                    t.Fatalf("could not parse a topic name")
                }
                return fields[0]
            }

            func TestRefShowHit(t *testing.T) {
                name := firstTopicName(t)

                // Exact-case show.
                outExact, _, err := buildTree([]string{"show", name})
                if err != nil {
                    t.Fatalf("show %q errored: %v", name, err)
                }
                if strings.TrimSpace(outExact.String()) == "" {
                    t.Fatalf("show %q produced no stdout", name)
                }

                // Upper-cased name must match the same topic, identical output.
                upper := strings.ToUpper(name)
                outUpper, errBuf, err := buildTree([]string{"show", upper})
                if err != nil {
                    t.Fatalf("case-insensitive show %q errored: %v (stderr=%s)",
                        upper, err, errBuf.String())
                }
                if outExact.String() != outUpper.String() {
                    t.Fatalf("case-insensitive show differs:\\nexact:\\n%s\\nupper:\\n%s",
                        outExact.String(), outUpper.String())
                }
            }
            """
        )
        proc = _run_driver(driver, "TestRefShowHit")
        assert proc.returncode == 0, (
            "show-hit driver failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_show_miss_errors_with_topic_name_no_stdout(self):
        """L2: `show <unknown>` returns an error naming the topic and writes no stdout."""
        token = "definitelynotatopic_zzz"
        driver = _DRIVER_HEADER + textwrap.dedent(
            """
            func TestRefShowMiss(t *testing.T) {
                bogus := "%s"
                out, _, err := buildTree([]string{"show", bogus})
                if err == nil {
                    t.Fatalf("show of unknown topic must return a non-nil error")
                }
                if !strings.Contains(err.Error(), bogus) {
                    t.Fatalf("error must name the unknown topic %q; got: %v", bogus, err)
                }
                if strings.TrimSpace(out.String()) != "" {
                    t.Fatalf("unknown topic must not write stdout; got:\\n%s", out.String())
                }
            }
            """ % token
        )
        proc = _run_driver(driver, "TestRefShowMiss")
        assert proc.returncode == 0, (
            "show-miss driver failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_show_argument_count_errors(self):
        """L2: `show` with zero or two args fails with cobra's arg-count error."""
        driver = _DRIVER_HEADER + textwrap.dedent(
            """
            func TestRefShowArgCount(t *testing.T) {
                // Zero args.
                out0, _, err0 := buildTree([]string{"show"})
                if err0 == nil {
                    t.Fatalf("show with no args must error (cobra arg-count)")
                }
                // Two args.
                out2, _, err2 := buildTree([]string{"show", "a", "b"})
                if err2 == nil {
                    t.Fatalf("show with two args must error (cobra arg-count)")
                }
                // cobra arg-count errors mention "arg(s)" / "argument".
                msg0 := strings.ToLower(err0.Error())
                msg2 := strings.ToLower(err2.Error())
                if !strings.Contains(msg0, "arg") {
                    t.Fatalf("zero-arg error should be a cobra arg-count error; got: %v", err0)
                }
                if !strings.Contains(msg2, "arg") {
                    t.Fatalf("two-arg error should be a cobra arg-count error; got: %v", err2)
                }
                _ = out0
                _ = out2
            }
            """
        )
        proc = _run_driver(driver, "TestRefShowArgCount")
        assert proc.returncode == 0, (
            "show-argcount driver failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_plain_flag_inherited_by_both_subcommands(self):
        """L2: parent-level `--plain` changes both `list` (names only) and `show` (no aliases)."""
        driver = _DRIVER_HEADER + textwrap.dedent(
            """
            func nelPlain(s string) []string {
                out := []string{}
                for _, ln := range strings.Split(strings.TrimRight(s, "\\n"), "\\n") {
                    if strings.TrimSpace(ln) != "" {
                        out = append(out, ln)
                    }
                }
                return out
            }

            func TestRefPlain(t *testing.T) {
                // list --plain => names only: each line is a single token and
                // differs from the (richer) default list output.
                def, _, err := buildTree([]string{"list"})
                if err != nil {
                    t.Fatalf("list errored: %v", err)
                }
                plain, _, err := buildTree([]string{"list", "--plain"})
                if err != nil {
                    t.Fatalf("list --plain errored (is --plain declared on the parent?): %v", err)
                }
                if def.String() == plain.String() {
                    t.Fatalf("list --plain must differ from default list output")
                }
                for _, ln := range nelPlain(plain.String()) {
                    if len(strings.Fields(ln)) != 1 {
                        t.Fatalf("list --plain must print names only; offending line: %q", ln)
                    }
                }

                // Find a topic that HAS aliases by comparing default vs plain show
                // line counts. Use the first topic name from plain list.
                names := nelPlain(plain.String())
                if len(names) == 0 {
                    t.Fatalf("no topics from plain list")
                }
                foundAliasTopic := false
                for _, nm := range names {
                    name := strings.Fields(nm)[0]
                    showDef, _, e1 := buildTree([]string{"show", name})
                    if e1 != nil {
                        t.Fatalf("show %q errored: %v", name, e1)
                    }
                    showPlain, _, e2 := buildTree([]string{"show", name, "--plain"})
                    if e2 != nil {
                        t.Fatalf("show %q --plain errored: %v", name, e2)
                    }
                    dl := len(nelPlain(showDef.String()))
                    pl := len(nelPlain(showPlain.String()))
                    if pl > dl {
                        t.Fatalf("show --plain printed MORE lines than default for %q", name)
                    }
                    if dl > pl {
                        // Plain omitted alias lines for a topic that has aliases.
                        foundAliasTopic = true
                    }
                }
                if !foundAliasTopic {
                    t.Fatalf("expected at least one topic whose --plain show omits alias lines")
                }
            }
            """
        )
        proc = _run_driver(driver, "TestRefPlain")
        assert proc.returncode == 0, (
            "plain-flag driver failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_show_completion_offers_topics_no_file_fallback(self):
        """L2: dynamic completion of `<topic>` returns catalog names, not file completion."""
        driver = _DRIVER_HEADER + textwrap.dedent(
            """
            func nelComp(s string) []string {
                out := []string{}
                for _, ln := range strings.Split(strings.TrimRight(s, "\\n"), "\\n") {
                    if strings.TrimSpace(ln) != "" {
                        out = append(out, ln)
                    }
                }
                return out
            }

            func TestRefShowCompletion(t *testing.T) {
                // Determine a real topic name.
                lout, _, err := buildTree([]string{"list", "--plain"})
                if err != nil {
                    t.Fatalf("plain list errored: %v", err)
                }
                names := nelComp(lout.String())
                if len(names) == 0 {
                    t.Fatalf("no topics to validate completion against")
                }
                wantName := strings.Fields(names[0])[0]

                // Drive cobra's hidden __complete command on a fresh tree.
                out, _, _ := buildTree([]string{"__complete", "show", ""})
                comp := out.String()
                if !strings.Contains(comp, wantName) {
                    t.Fatalf("topic completion must suggest catalog name %q; got:\\n%s",
                        wantName, comp)
                }
                // The trailing directive line must NOT request default (file) completion.
                // ShellCompDirectiveNoFileComp == 4 ; ShellCompDirectiveDefault == 0.
                if strings.Contains(comp, ":0\\n") || strings.HasSuffix(strings.TrimRight(comp, "\\n"), ":0") {
                    t.Fatalf("topic completion fell back to default/file completion:\\n%s", comp)
                }
            }
            """
        )
        proc = _run_driver(driver, "TestRefShowCompletion")
        assert proc.returncode == 0, (
            "show-completion driver failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_no_leaked_flag_state_between_invocations(self):
        """L2: a fresh tree per invocation yields identical results (no leaked --limit state)."""
        driver = _DRIVER_HEADER + textwrap.dedent(
            """
            func TestRefNoLeak(t *testing.T) {
                // First run with a small limit, then a plain list: the plain list
                // must NOT inherit the previous --limit value.
                _, _, err := buildTree([]string{"list", "--limit", "1"})
                if err != nil {
                    t.Fatalf("list --limit 1 errored: %v", err)
                }
                a, _, err := buildTree([]string{"list"})
                if err != nil {
                    t.Fatalf("list errored: %v", err)
                }
                b, _, err := buildTree([]string{"list"})
                if err != nil {
                    t.Fatalf("list errored: %v", err)
                }
                if a.String() != b.String() {
                    t.Fatalf("repeated fresh list outputs differ (state leak?):\\n--a--\\n%s\\n--b--\\n%s",
                        a.String(), b.String())
                }
                // Count lines; must be >2 (i.e. not stuck at the earlier limit of 1).
                count := 0
                for _, ln := range strings.Split(strings.TrimRight(a.String(), "\\n"), "\\n") {
                    if strings.TrimSpace(ln) != "" {
                        count++
                    }
                }
                if count < 4 {
                    t.Fatalf("fresh list after --limit 1 only printed %d lines; flag state leaked", count)
                }
            }
            """
        )
        proc = _run_driver(driver, "TestRefNoLeak")
        assert proc.returncode == 0, (
            "no-leak driver failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )
