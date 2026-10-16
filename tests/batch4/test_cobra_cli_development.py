"""Tests for the `cobra-cli-development` skill (variant ext4).

Skill task: add a brand-new, fully offline `gh palette` cobra command group to
the GitHub CLI (github.com/cli/cli/v2). The group holds a static, ordered
in-process color catalog (>=4 entries, each a unique lowercase `name` + a stable
`hex`) and exposes three leaf subcommands organized under TWO distinct titled
help sections:

  * "Query commands:"  -> `name <color>` and `list`
  * "Select commands:" -> `pick <index>`

Behaviour under test (re-derived from tasks/ext4/cobra-cli-development.md):
  * `gh palette --help` renders BOTH titled section headers and lists name/list/pick,
    each subcommand assigned to its correct section (cobra Groups + GroupID).
  * `gh palette list` prints every catalog entry, one per line, `name` then `hex`,
    in catalog order, nothing on stderr.
  * `gh palette name <color>` is case-insensitive; a hit prints the matching `hex`;
    a miss returns a non-nil error naming the unknown color and prints no stdout.
    Its `ValidArgs` completion list equals exactly the catalog names.
  * `gh palette pick <index>` takes a zero-based int; in-range prints that entry's
    `name` and `hex`; out-of-range returns an error and prints no stdout.
  * `name` / `pick` enforce cobra's exactly-one-arg validation.
  * A fresh command tree per invocation yields identical results.

Verification strategy (discriminative):
  * L1 checks confirm the deliverable files exist, are well-formed Go, expose the
    required constructor, register on root, and that the package + root build.
  * L2 checks DO NOT trust the agent's own `palette_test.go`. Instead each case
    writes an *independent* white-box Go driver into the palette package
    directory, builds a fresh command tree per case via the agent's
    `NewCmdPalette(f)`, drives it with cobra's `SetArgs` + redirected streams (and
    cobra's hidden `__complete`), and asserts on real captured
    stdout/stderr/error/exit. A naive or hardcoded solution (fixed output,
    ignored input, no section titles, no completion list, leaked flag state)
    fails to compile or returns wrong output, failing these tests.

Native command: `go test ./pkg/cmd/palette/...` plus a targeted `go build`.
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
PAL_PKG_DIR = os.path.join(REPO_DIR, "pkg", "cmd", "palette")
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
    """Write an independent driver test into the palette package; return its path.

    The file name is unique so concurrent/repeat runs do not clash, and it is
    placed inside the agent-created package so it can call the unexported and
    exported identifiers in package `palette`.
    """
    name = "zz_skilltest_%s_test.go" % uuid.uuid4().hex[:10]
    path = os.path.join(PAL_PKG_DIR, name)
    with open(path, "w") as fh:
        fh.write(go_source)
    return path


def _run_driver(go_source, run_regex, timeout=GO_TIMEOUT):
    """Drop a driver test into the palette package, run only it, then clean up.

    Returns the completed subprocess. The driver's package is `palette`
    (white-box) so it can construct the command tree via NewCmdPalette.
    """
    assert os.path.isdir(PAL_PKG_DIR), (
        "palette package dir missing: %s" % PAL_PKG_DIR
    )
    path = _write_driver(go_source)
    try:
        return _run_go(
            ["go", "test", "-count=1", "-run", run_regex,
             "./pkg/cmd/palette/"],
            timeout=timeout,
        )
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


# Shared Go preamble for white-box driver tests living in package `palette`.
# buildTree wires capturable streams onto BOTH the IOStreams (handler output)
# and the cobra command (cobra-emitted help / arg errors / completion).
_DRIVER_HEADER = textwrap.dedent(
    """
    package palette

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
        cmd := NewCmdPalette(f)
        cmd.SetArgs(args)
        cmd.SetIn(&bytes.Buffer{})
        cmd.SetOut(outBuf)
        cmd.SetErr(errBuf)
        _, err := cmd.ExecuteC()
        return outBuf, errBuf, err
    }

    func nonEmpty(s string) []string {
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
        """L1: the five new palette files + modified root.go are present on disk."""
        required = [
            os.path.join(PAL_PKG_DIR, "palette.go"),
            os.path.join(PAL_PKG_DIR, "name.go"),
            os.path.join(PAL_PKG_DIR, "list.go"),
            os.path.join(PAL_PKG_DIR, "random.go"),
            os.path.join(PAL_PKG_DIR, "palette_test.go"),
            os.path.join(REPO_DIR, "pkg", "cmd", "root", "root.go"),
        ]
        missing = [p for p in required if not os.path.isfile(p)]
        assert not missing, "missing deliverable files: %s" % missing

    def test_package_declaration_and_constructor(self):
        """L1: palette.go declares package palette and exposes NewCmdPalette."""
        pal = os.path.join(PAL_PKG_DIR, "palette.go")
        with open(pal) as fh:
            src = fh.read()
        assert re.search(r"^\s*package\s+palette\b", src, re.MULTILINE), (
            "palette.go must declare `package palette`"
        )
        assert re.search(
            r"func\s+NewCmdPalette\s*\(\s*\w+\s+\*cmdutil\.Factory\s*\)\s*\*cobra\.Command",
            src,
        ), "NewCmdPalette(f *cmdutil.Factory) *cobra.Command signature required"

    def test_palette_package_builds(self):
        """L1: the new package and the modified root package both compile."""
        proc = _run_go(
            ["go", "build", "./pkg/cmd/palette/...", "./pkg/cmd/root/..."]
        )
        assert proc.returncode == 0, (
            "go build failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_root_registers_palette(self):
        """L1: root.go imports and registers the palette command group."""
        root = os.path.join(REPO_DIR, "pkg", "cmd", "root", "root.go")
        with open(root) as fh:
            src = fh.read()
        assert "cmd/palette" in src, (
            "root.go must import the palette package"
        )
        assert "NewCmdPalette" in src, (
            "root.go must call NewCmdPalette to register the group"
        )

    # ------------------------------------------------------------------ L2 ---
    def test_agent_native_tests_pass(self):
        """L2: the package's own test suite passes (go test ./pkg/cmd/palette/...)."""
        proc = _run_go(["go", "test", "-count=1", "./pkg/cmd/palette/..."])
        assert proc.returncode == 0, (
            "go test ./pkg/cmd/palette/... failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_parent_no_args_prints_help_no_error(self):
        """L2: bare `palette` prints help (lists name/list/pick), exits without error."""
        driver = _DRIVER_HEADER + textwrap.dedent(
            """
            func TestPalParentHelp(t *testing.T) {
                out, _, err := buildTree([]string{})
                if err != nil {
                    t.Fatalf("expected no error from bare parent, got %v", err)
                }
                s := out.String()
                for _, sub := range []string{"name", "list", "pick"} {
                    if !strings.Contains(s, sub) {
                        t.Fatalf("help must mention subcommand %q; got:\\n%s", sub, s)
                    }
                }
                low := strings.ToLower(s)
                if !strings.Contains(low, "usage") {
                    t.Fatalf("expected cobra help text (usage), got:\\n%s", s)
                }
            }
            """
        )
        proc = _run_driver(driver, "TestPalParentHelp")
        assert proc.returncode == 0, (
            "parent-help driver failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_help_renders_two_titled_sections_with_correct_membership(self):
        """L2: `palette --help` renders BOTH section titles and assigns each sub correctly."""
        driver = _DRIVER_HEADER + textwrap.dedent(
            """
            func TestPalHelpSections(t *testing.T) {
                out, _, err := buildTree([]string{"--help"})
                if err != nil {
                    t.Fatalf("--help returned error: %v", err)
                }
                s := out.String()

                qi := strings.Index(s, "Query commands:")
                si := strings.Index(s, "Select commands:")
                if qi < 0 {
                    t.Fatalf(`missing titled section "Query commands:"; got:\\n%s`, s)
                }
                if si < 0 {
                    t.Fatalf(`missing titled section "Select commands:"; got:\\n%s`, s)
                }

                // Membership: name & list belong under the Query section, pick
                // under the Select section. We assert position ordering: each
                // subcommand line must appear after its own section header and
                // before the next section header (or end).
                nameIdx := strings.Index(s, "\\n  name")
                listIdx := strings.Index(s, "\\n  list")
                pickIdx := strings.Index(s, "\\n  pick")
                if nameIdx < 0 || listIdx < 0 || pickIdx < 0 {
                    t.Fatalf("expected indented subcommand lines for name/list/pick; got:\\n%s", s)
                }

                // Determine section boundaries.
                first, second := qi, si
                if si < qi {
                    first, second = si, qi
                }

                inFirst := func(idx int) bool { return idx > first && idx < second }
                inSecond := func(idx int) bool { return idx > second }

                // pick must live in the Select section.
                if qi < si {
                    // Query first, Select second.
                    if !inFirst(nameIdx) || !inFirst(listIdx) {
                        t.Fatalf("name/list must be under Query commands; got:\\n%s", s)
                    }
                    if !inSecond(pickIdx) {
                        t.Fatalf("pick must be under Select commands; got:\\n%s", s)
                    }
                } else {
                    // Select first, Query second.
                    if !inFirst(pickIdx) {
                        t.Fatalf("pick must be under Select commands; got:\\n%s", s)
                    }
                    if !inSecond(nameIdx) || !inSecond(listIdx) {
                        t.Fatalf("name/list must be under Query commands; got:\\n%s", s)
                    }
                }
            }
            """
        )
        proc = _run_driver(driver, "TestPalHelpSections")
        assert proc.returncode == 0, (
            "help-sections driver failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_list_prints_all_catalog_entries_in_order(self):
        """L2: `list` prints >=4 entries, name+hex per line, stable catalog order, no stderr."""
        driver = _DRIVER_HEADER + textwrap.dedent(
            """
            func TestPalListOrder(t *testing.T) {
                out, errBuf, err := buildTree([]string{"list"})
                if err != nil {
                    t.Fatalf("list returned error: %v (stderr=%s)", err, errBuf.String())
                }
                if strings.TrimSpace(errBuf.String()) != "" {
                    t.Fatalf("list wrote to stderr on success: %q", errBuf.String())
                }
                lines := nonEmpty(out.String())
                if len(lines) < 4 {
                    t.Fatalf("catalog must have >=4 colors; list printed %d lines:\\n%s",
                        len(lines), out.String())
                }
                // Each line must carry a name AND a hex token (not just a name).
                for i, ln := range lines {
                    fields := strings.Fields(ln)
                    if len(fields) < 2 {
                        t.Fatalf("line %d lacks a hex after the name: %q", i, ln)
                    }
                    // The name must be lowercase (catalog invariant).
                    if fields[0] != strings.ToLower(fields[0]) {
                        t.Fatalf("catalog name not lowercase on line %d: %q", i, ln)
                    }
                    // Some token on the line must look like a hex color.
                    hasHex := false
                    for _, f := range fields {
                        v := strings.TrimPrefix(f, "#")
                        if len(v) >= 3 {
                            okHex := true
                            for _, c := range strings.ToLower(v) {
                                if !((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f')) {
                                    okHex = false
                                    break
                                }
                            }
                            if okHex {
                                hasHex = true
                            }
                        }
                    }
                    if !hasHex {
                        t.Fatalf("line %d has no hex-looking token: %q", i, ln)
                    }
                }
                // Order/content stable across two fresh trees.
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
        proc = _run_driver(driver, "TestPalListOrder")
        assert proc.returncode == 0, (
            "list-order driver failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_name_case_insensitive_hit_prints_hex(self):
        """L2: `name <COLOR>` matches case-insensitively and prints exactly that color's hex."""
        driver = _DRIVER_HEADER + textwrap.dedent(
            """
            func firstColor(t *testing.T) (string, string) {
                out, _, err := buildTree([]string{"list"})
                if err != nil {
                    t.Fatalf("list errored: %v", err)
                }
                lines := nonEmpty(out.String())
                if len(lines) == 0 {
                    t.Fatalf("list produced no colors")
                }
                f := strings.Fields(lines[0])
                if len(f) < 2 {
                    t.Fatalf("could not parse name+hex from %q", lines[0])
                }
                // hex is the token that looks like a color (prefer the last field).
                return f[0], f[len(f)-1]
            }

            func TestPalNameHit(t *testing.T) {
                name, _ := firstColor(t)

                lower, _, err := buildTree([]string{"name", strings.ToLower(name)})
                if err != nil {
                    t.Fatalf("name %q errored: %v", name, err)
                }
                got := strings.TrimSpace(lower.String())
                if got == "" {
                    t.Fatalf("name %q produced no stdout", name)
                }

                // Upper-cased lookup must match the same color: identical stdout.
                upper, eb, err := buildTree([]string{"name", strings.ToUpper(name)})
                if err != nil {
                    t.Fatalf("case-insensitive name %q errored: %v (stderr=%s)",
                        strings.ToUpper(name), err, eb.String())
                }
                if lower.String() != upper.String() {
                    t.Fatalf("case-insensitive name differs:\\nlower:\\n%q\\nupper:\\n%q",
                        lower.String(), upper.String())
                }

                // The printed hex must be the hex listed for that name in `list`.
                lout, _, _ := buildTree([]string{"list"})
                wantHex := ""
                for _, ln := range nonEmpty(lout.String()) {
                    ff := strings.Fields(ln)
                    if len(ff) >= 2 && strings.EqualFold(ff[0], name) {
                        wantHex = ff[len(ff)-1]
                        break
                    }
                }
                if wantHex == "" {
                    t.Fatalf("could not locate hex for %q in list", name)
                }
                if !strings.Contains(got, wantHex) {
                    t.Fatalf("name %q must print its hex %q; got %q", name, wantHex, got)
                }
            }
            """
        )
        proc = _run_driver(driver, "TestPalNameHit")
        assert proc.returncode == 0, (
            "name-hit driver failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_name_miss_errors_with_color_no_stdout(self):
        """L2: `name <unknown>` returns an error naming the color and writes no stdout."""
        token = "definitelynotacolor_zzz"
        driver = _DRIVER_HEADER + textwrap.dedent(
            """
            func TestPalNameMiss(t *testing.T) {
                bogus := "%s"
                out, _, err := buildTree([]string{"name", bogus})
                if err == nil {
                    t.Fatalf("name of unknown color must return a non-nil error")
                }
                if !strings.Contains(err.Error(), bogus) {
                    t.Fatalf("error must name the unknown color %%q; got: %%v", bogus, err)
                }
                if strings.TrimSpace(out.String()) != "" {
                    t.Fatalf("unknown color must not write stdout; got:\\n%%s", out.String())
                }
            }
            """ % token
        )
        proc = _run_driver(driver, "TestPalNameMiss")
        assert proc.returncode == 0, (
            "name-miss driver failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_name_argument_count_errors(self):
        """L2: `name` with zero or two args fails with cobra's exactly-one-arg error."""
        driver = _DRIVER_HEADER + textwrap.dedent(
            """
            func TestPalNameArgCount(t *testing.T) {
                _, _, err0 := buildTree([]string{"name"})
                if err0 == nil {
                    t.Fatalf("name with no args must error (cobra arg-count)")
                }
                _, _, err2 := buildTree([]string{"name", "a", "b"})
                if err2 == nil {
                    t.Fatalf("name with two args must error (cobra arg-count)")
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
        proc = _run_driver(driver, "TestPalNameArgCount")
        assert proc.returncode == 0, (
            "name-argcount driver failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_name_valid_args_completion_equals_catalog(self):
        """L2: `name`'s ValidArgs completion list equals exactly the catalog names (order)."""
        driver = _DRIVER_HEADER + textwrap.dedent(
            """
            func TestPalNameCompletion(t *testing.T) {
                // Catalog names, in order, from `list`.
                lout, _, err := buildTree([]string{"list"})
                if err != nil {
                    t.Fatalf("list errored: %v", err)
                }
                var catalog []string
                for _, ln := range nonEmpty(lout.String()) {
                    f := strings.Fields(ln)
                    if len(f) >= 1 {
                        catalog = append(catalog, strings.ToLower(f[0]))
                    }
                }
                if len(catalog) < 4 {
                    t.Fatalf("need >=4 catalog names; got %d", len(catalog))
                }

                // Drive cobra's hidden __complete on a fresh tree.
                out, _, _ := buildTree([]string{"__complete", "name", ""})
                comp := out.String()

                // Every catalog name must be offered as a completion.
                for _, nm := range catalog {
                    if !strings.Contains(comp, nm) {
                        t.Fatalf("completion must offer catalog name %q; got:\\n%s", nm, comp)
                    }
                }

                // Parse the candidate tokens (cobra prints "<value>\\t<desc>" lines,
                // ending with a ":<directive>" line). Collect first tokens that are
                // catalog members; the set offered must equal the catalog set.
                offered := map[string]bool{}
                for _, ln := range nonEmpty(comp) {
                    if strings.HasPrefix(ln, ":") {
                        continue
                    }
                    tok := strings.Fields(ln)
                    if len(tok) == 0 {
                        continue
                    }
                    offered[strings.ToLower(tok[0])] = true
                }
                catSet := map[string]bool{}
                for _, nm := range catalog {
                    catSet[nm] = true
                }
                for nm := range catSet {
                    if !offered[nm] {
                        t.Fatalf("catalog name %q not in completion candidates:\\n%s", nm, comp)
                    }
                }
                // No EXTRA non-catalog candidates (static ValidArgs == catalog).
                for nm := range offered {
                    if !catSet[nm] {
                        t.Fatalf("completion offered non-catalog candidate %q:\\n%s", nm, comp)
                    }
                }

                // The directive must not be plain file/default completion.
                if strings.Contains(comp, ":0\\n") ||
                    strings.HasSuffix(strings.TrimRight(comp, "\\n"), ":0") {
                    t.Fatalf("name completion fell back to default/file completion:\\n%s", comp)
                }
            }
            """
        )
        proc = _run_driver(driver, "TestPalNameCompletion")
        assert proc.returncode == 0, (
            "name-completion driver failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_pick_in_range_prints_entry_out_of_range_errors(self):
        """L2: `pick 0` prints first entry's name+hex; `pick 99` errors with no stdout."""
        driver = _DRIVER_HEADER + textwrap.dedent(
            """
            func TestPalPick(t *testing.T) {
                // Reference: first and last catalog entries from `list`.
                lout, _, err := buildTree([]string{"list"})
                if err != nil {
                    t.Fatalf("list errored: %v", err)
                }
                lines := nonEmpty(lout.String())
                if len(lines) < 4 {
                    t.Fatalf("need >=4 catalog entries; got %d", len(lines))
                }
                firstFields := strings.Fields(lines[0])
                firstName := firstFields[0]
                firstHex := firstFields[len(firstFields)-1]

                // pick 0 -> first entry: must contain both name and hex.
                out0, eb0, err0 := buildTree([]string{"pick", "0"})
                if err0 != nil {
                    t.Fatalf("pick 0 errored: %v (stderr=%s)", err0, eb0.String())
                }
                s0 := out0.String()
                if !strings.Contains(s0, firstName) || !strings.Contains(s0, firstHex) {
                    t.Fatalf("pick 0 must print first entry name %q and hex %q; got:\\n%s",
                        firstName, firstHex, s0)
                }

                // pick of the last valid index must succeed and print its entry.
                lastIdx := len(lines) - 1
                lastFields := strings.Fields(lines[lastIdx])
                lastName := lastFields[0]
                outL, _, errL := buildTree([]string{"pick", itoa(lastIdx)})
                if errL != nil {
                    t.Fatalf("pick %d (last) errored: %v", lastIdx, errL)
                }
                if !strings.Contains(outL.String(), lastName) {
                    t.Fatalf("pick %d must print last entry %q; got:\\n%s",
                        lastIdx, lastName, outL.String())
                }

                // Distinct indices produce distinct output (no hardcoded entry).
                if out0.String() == outL.String() {
                    t.Fatalf("pick 0 and pick %d produced identical output (hardcoded?):\\n%s",
                        lastIdx, out0.String())
                }

                // Out-of-range index: non-nil error, no stdout.
                outBad, _, errBad := buildTree([]string{"pick", "99"})
                if errBad == nil {
                    t.Fatalf("pick 99 (out of range) must return a non-nil error")
                }
                if strings.TrimSpace(outBad.String()) != "" {
                    t.Fatalf("out-of-range pick must not write stdout; got:\\n%s", outBad.String())
                }
            }

            func itoa(n int) string {
                if n == 0 {
                    return "0"
                }
                neg := n < 0
                if neg {
                    n = -n
                }
                var b []byte
                for n > 0 {
                    b = append([]byte{byte('0' + n%10)}, b...)
                    n /= 10
                }
                if neg {
                    b = append([]byte{'-'}, b...)
                }
                return string(b)
            }
            """
        )
        proc = _run_driver(driver, "TestPalPick")
        assert proc.returncode == 0, (
            "pick driver failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_pick_non_integer_and_arg_count_errors(self):
        """L2: `pick` rejects a non-integer index and enforces exactly one arg."""
        driver = _DRIVER_HEADER + textwrap.dedent(
            """
            func TestPalPickBadArgs(t *testing.T) {
                // Non-integer index -> error, no stdout.
                out, _, err := buildTree([]string{"pick", "notanint"})
                if err == nil {
                    t.Fatalf("pick with non-integer index must error")
                }
                if strings.TrimSpace(out.String()) != "" {
                    t.Fatalf("non-integer pick must not write stdout; got:\\n%s", out.String())
                }

                // Zero args -> cobra arg-count error.
                _, _, err0 := buildTree([]string{"pick"})
                if err0 == nil {
                    t.Fatalf("pick with no args must error (cobra arg-count)")
                }
                if !strings.Contains(strings.ToLower(err0.Error()), "arg") {
                    t.Fatalf("zero-arg pick error should be a cobra arg-count error; got: %v", err0)
                }

                // Two args -> cobra arg-count error.
                _, _, err2 := buildTree([]string{"pick", "0", "1"})
                if err2 == nil {
                    t.Fatalf("pick with two args must error (cobra arg-count)")
                }
            }
            """
        )
        proc = _run_driver(driver, "TestPalPickBadArgs")
        assert proc.returncode == 0, (
            "pick-bad-args driver failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_fresh_tree_is_deterministic_no_state_leak(self):
        """L2: a fresh tree per invocation yields identical results across repeats."""
        driver = _DRIVER_HEADER + textwrap.dedent(
            """
            func TestPalDeterministic(t *testing.T) {
                a, _, err := buildTree([]string{"list"})
                if err != nil {
                    t.Fatalf("list errored: %v", err)
                }
                // Interleave an unrelated command, then repeat list.
                _, _, _ = buildTree([]string{"name", "definitely_missing_xyz"})
                b, _, err := buildTree([]string{"list"})
                if err != nil {
                    t.Fatalf("second list errored: %v", err)
                }
                if a.String() != b.String() {
                    t.Fatalf("repeated fresh list outputs differ (state leak?):\\n--a--\\n%s\\n--b--\\n%s",
                        a.String(), b.String())
                }
                // pick determinism: same index, two fresh trees, identical output.
                p1, _, e1 := buildTree([]string{"pick", "0"})
                if e1 != nil {
                    t.Fatalf("pick 0 errored: %v", e1)
                }
                p2, _, e2 := buildTree([]string{"pick", "0"})
                if e2 != nil {
                    t.Fatalf("pick 0 (2) errored: %v", e2)
                }
                if p1.String() != p2.String() {
                    t.Fatalf("pick 0 not deterministic:\\n%q\\n%q", p1.String(), p2.String())
                }
            }
            """
        )
        proc = _run_driver(driver, "TestPalDeterministic")
        assert proc.returncode == 0, (
            "deterministic driver failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )
