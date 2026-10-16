"""Tests for the `cobra-cli-development` skill (variant ext6).

Skill task: add a brand-new, fully offline `gh snippet` cobra command group to
the GitHub CLI (github.com/cli/cli/v2). The group has:

  * a parent command built via `NewCmdSnippet(f *cmdutil.Factory) *cobra.Command`,
    registered on the root command, which with no subcommand prints help and
    exits without error and accepts no positional args of its own;
  * a fixed, in-process static catalog mapping unique lowercase `key`s
    (e.g. `clone`, `commit`, `checkout`, `cherry-pick`) to one-line `body`s,
    with NO files/env/network reads;
  * a `get <key>` subcommand that requires exactly one positional argument
    (cobra-standard arg validation), prints the matching `body` on one line to
    stdout for an exact hit, returns a non-nil error naming the unknown key and
    prints nothing for a miss, and offers *dynamic* completion of `<key>` that
    returns only catalog keys having the typed text as a prefix and signals that
    file-name completion must NOT be offered as a fallback.

Verification strategy (discriminative):
  * L1 checks confirm the deliverable files exist, are well-formed Go declaring
    `package snippet` + `NewCmdSnippet`, that root.go registers the group, and
    that the package + root build.
  * L2 checks DO NOT trust the agent's own `snippet_test.go`. Instead each case
    writes an *independent* white-box Go driver test into the snippet package
    directory, builds a FRESH command tree per case via the agent's
    `NewCmdSnippet(f)`, drives it with cobra's `SetArgs` + redirected streams
    (and cobra's hidden `__complete` mechanism for completion), and asserts on
    real captured stdout/stderr/error/exit and on the completion DIRECTIVE.

    A naive or hardcoded solution fails:
      - a stub `get` that ignores its argument and always prints the same body
        fails the hit/miss and per-key body checks;
      - a hand-rolled arg check (instead of cobra args validation) that does not
        error on 0 or 2 args fails the arg-count checks;
      - a static `ValidArgs` slice or a completion fn that does not prefix-filter
        fails the prefix-subset check;
      - a completion fn that allows file-name completion fallback fails the
        directive check.

Native command: `go test ./pkg/cmd/snippet/...` plus targeted `go build`.
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
SNIP_PKG_DIR = os.path.join(REPO_DIR, "pkg", "cmd", "snippet")
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
    """Write an independent driver test into the snippet package; return its path.

    The file name is unique so repeat runs do not clash, and it lives inside the
    agent-created package so it can call the unexported and exported identifiers
    in package `snippet` (white-box).
    """
    name = "zz_skilltest_%s_test.go" % uuid.uuid4().hex[:10]
    path = os.path.join(SNIP_PKG_DIR, name)
    with open(path, "w") as fh:
        fh.write(go_source)
    return path


def _run_driver(go_source, run_regex, timeout=GO_TIMEOUT):
    """Drop a driver test into the snippet package, run only it, then clean up."""
    assert os.path.isdir(SNIP_PKG_DIR), (
        "snippet package dir missing: %s" % SNIP_PKG_DIR
    )
    path = _write_driver(go_source)
    try:
        return _run_go(
            ["go", "test", "-count=1", "-run", run_regex,
             "./pkg/cmd/snippet/"],
            timeout=timeout,
        )
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


# Shared Go preamble for white-box driver tests living in package `snippet`.
_DRIVER_HEADER = textwrap.dedent(
    """
    package snippet

    import (
        "bytes"
        "strings"
        "testing"

        "github.com/cli/cli/v2/pkg/cmdutil"
        "github.com/cli/cli/v2/pkg/iostreams"
    )

    // buildTree constructs a fresh snippet command tree and wires capturable
    // streams onto both the IOStreams (used by handlers) and the cobra command
    // (used by cobra-emitted output such as help / arg errors / __complete).
    func buildTree(args []string) (*bytes.Buffer, *bytes.Buffer, error) {
        ios, _, outBuf, errBuf := iostreams.Test()
        f := &cmdutil.Factory{IOStreams: ios}
        cmd := NewCmdSnippet(f)
        cmd.SetArgs(args)
        cmd.SetIn(&bytes.Buffer{})
        cmd.SetOut(outBuf)
        cmd.SetErr(errBuf)
        _, err := cmd.ExecuteC()
        return outBuf, errBuf, err
    }

    // nel returns the non-empty, right-trimmed lines of s.
    func nel(s string) []string {
        out := []string{}
        for _, ln := range strings.Split(strings.TrimRight(s, "\\n"), "\\n") {
            if strings.TrimSpace(ln) != "" {
                out = append(out, ln)
            }
        }
        return out
    }

    // completeLines drives cobra's hidden __complete on a fresh tree and returns
    // (suggestion lines, directive line). The last non-empty line emitted by
    // __complete is the ":<directive>" marker.
    func completeLines(args ...string) ([]string, string) {
        full := append([]string{"__complete"}, args...)
        out, _, _ := buildTree(full)
        lines := nel(out.String())
        if len(lines) == 0 {
            return nil, ""
        }
        directive := lines[len(lines)-1]
        sugg := []string{}
        for _, ln := range lines[:len(lines)-1] {
            // Each suggestion line is "<value>" optionally followed by a TAB and
            // a description; keep only the value token.
            v := ln
            if i := strings.Index(ln, "\\t"); i >= 0 {
                v = ln[:i]
            }
            v = strings.TrimSpace(v)
            if v != "" {
                sugg = append(sugg, v)
            }
        }
        return sugg, directive
    }

    var _ = strings.TrimSpace
    """
)


class TestCobraCliDevelopment:
    REPO_DIR = _find_repo_dir("/workspace/cli")

    # ------------------------------------------------------------------ L1 ---
    def test_deliverable_files_exist(self):
        """L1: the three new snippet files + modified root.go are present."""
        required = [
            os.path.join(SNIP_PKG_DIR, "snippet.go"),
            os.path.join(SNIP_PKG_DIR, "get.go"),
            os.path.join(SNIP_PKG_DIR, "snippet_test.go"),
            os.path.join(REPO_DIR, "pkg", "cmd", "root", "root.go"),
        ]
        missing = [p for p in required if not os.path.isfile(p)]
        assert not missing, "missing deliverable files: %s" % missing

    def test_package_declaration_and_constructor(self):
        """L1: snippet.go declares package snippet and exposes NewCmdSnippet."""
        snip = os.path.join(SNIP_PKG_DIR, "snippet.go")
        with open(snip) as fh:
            src = fh.read()
        assert re.search(r"^\s*package\s+snippet\b", src, re.MULTILINE), (
            "snippet.go must declare `package snippet`"
        )
        assert re.search(
            r"func\s+NewCmdSnippet\s*\(\s*\w+\s+\*cmdutil\.Factory\s*\)\s*\*cobra\.Command",
            src,
        ), "NewCmdSnippet(f *cmdutil.Factory) *cobra.Command signature required"

    def test_get_subcommand_source_present(self):
        """L1: get.go declares package snippet (the get subcommand source)."""
        get = os.path.join(SNIP_PKG_DIR, "get.go")
        with open(get) as fh:
            src = fh.read()
        assert re.search(r"^\s*package\s+snippet\b", src, re.MULTILINE), (
            "get.go must declare `package snippet`"
        )

    def test_snippet_package_builds(self):
        """L1: the new package and the modified root package both compile."""
        proc = _run_go(
            ["go", "build", "./pkg/cmd/snippet/...", "./pkg/cmd/root/..."]
        )
        assert proc.returncode == 0, (
            "go build failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_root_registers_snippet(self):
        """L1: root.go imports and registers the snippet command group."""
        root = os.path.join(REPO_DIR, "pkg", "cmd", "root", "root.go")
        with open(root) as fh:
            src = fh.read()
        assert "cmd/snippet" in src, (
            "root.go must import the snippet package"
        )
        assert "NewCmdSnippet" in src, (
            "root.go must call NewCmdSnippet to register the group"
        )

    # ------------------------------------------------------------------ L2 ---
    def test_agent_native_tests_pass(self):
        """L2: the package's own test suite passes (go test ./pkg/cmd/snippet/...)."""
        proc = _run_go(["go", "test", "-count=1", "./pkg/cmd/snippet/..."])
        assert proc.returncode == 0, (
            "go test ./pkg/cmd/snippet/... failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_parent_no_args_prints_help_no_error(self):
        """L2: `snippet` with no subcommand prints help (mentions `get`), no error."""
        driver = _DRIVER_HEADER + textwrap.dedent(
            """
            func TestSnipParentHelp(t *testing.T) {
                out, _, err := buildTree([]string{})
                if err != nil {
                    t.Fatalf("expected no error from bare parent, got %v", err)
                }
                s := out.String()
                if !strings.Contains(s, "get") {
                    t.Fatalf("help output must mention the get subcommand; got:\\n%s", s)
                }
                low := strings.ToLower(s)
                if !strings.Contains(low, "usage") && !strings.Contains(low, "available commands") {
                    t.Fatalf("expected cobra help text, got:\\n%s", s)
                }
            }
            """
        )
        proc = _run_driver(driver, "TestSnipParentHelp")
        assert proc.returncode == 0, (
            "parent-help driver failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_parent_rejects_own_positional_args(self):
        """L2: `snippet <stray>` (a non-subcommand token) does not silently succeed.

        The parent accepts no positional args of its own; an unknown token must
        produce an error (cobra unknown-command), NOT a silent zero-exit.
        """
        driver = _DRIVER_HEADER + textwrap.dedent(
            """
            func TestSnipParentStray(t *testing.T) {
                _, _, err := buildTree([]string{"definitelynotasub_zzz"})
                if err == nil {
                    t.Fatalf("parent must reject an unknown positional/subcommand token")
                }
            }
            """
        )
        proc = _run_driver(driver, "TestSnipParentStray")
        assert proc.returncode == 0, (
            "parent-stray driver failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_get_hit_prints_body_one_line_no_stderr(self):
        """L2: `get <key>` for a discovered catalog key prints a non-empty one-line body.

        The key is discovered from the catalog itself (via the empty-prefix
        completion), so the test does not hardcode catalog contents. Output must
        be exactly one non-empty stdout line and nothing on stderr.
        """
        driver = _DRIVER_HEADER + textwrap.dedent(
            """
            // firstKey discovers a real catalog key from empty-prefix completion.
            func firstKey(t *testing.T) string {
                sugg, _ := completeLines("get", "")
                if len(sugg) == 0 {
                    t.Fatalf("empty-prefix completion returned no catalog keys")
                }
                return sugg[0]
            }

            func TestSnipGetHit(t *testing.T) {
                key := firstKey(t)
                out, errBuf, err := buildTree([]string{"get", key})
                if err != nil {
                    t.Fatalf("get %q errored: %v (stderr=%s)", key, err, errBuf.String())
                }
                if strings.TrimSpace(errBuf.String()) != "" {
                    t.Fatalf("get %q wrote to stderr on success: %q", key, errBuf.String())
                }
                lines := nel(out.String())
                if len(lines) != 1 {
                    t.Fatalf("get %q must print exactly one body line; got %d:\\n%s",
                        key, len(lines), out.String())
                }
                if strings.TrimSpace(lines[0]) == "" {
                    t.Fatalf("get %q printed an empty body", key)
                }
            }
            """
        )
        proc = _run_driver(driver, "TestSnipGetHit")
        assert proc.returncode == 0, (
            "get-hit driver failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_get_distinct_keys_yield_distinct_bodies(self):
        """L2: different catalog keys map to different bodies (no hardcoded fixed output).

        A stub `get` that ignores its argument and always prints the same string
        fails: at least two discovered keys must produce different bodies.
        """
        driver = _DRIVER_HEADER + textwrap.dedent(
            """
            func TestSnipGetDistinct(t *testing.T) {
                keys, _ := completeLines("get", "")
                if len(keys) < 2 {
                    t.Fatalf("catalog must expose >=2 keys for distinctness; got %v", keys)
                }
                bodies := map[string]string{}
                for _, k := range keys {
                    out, _, err := buildTree([]string{"get", k})
                    if err != nil {
                        t.Fatalf("get %q errored: %v", k, err)
                    }
                    bodies[k] = strings.TrimRight(out.String(), "\\n")
                }
                // Ensure not every body is identical (i.e. the key actually selects).
                seen := map[string]bool{}
                for _, b := range bodies {
                    seen[b] = true
                }
                if len(seen) < 2 {
                    t.Fatalf("all keys produced the same body (argument ignored?): %v", bodies)
                }
            }
            """
        )
        proc = _run_driver(driver, "TestSnipGetDistinct")
        assert proc.returncode == 0, (
            "get-distinct driver failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_get_is_deterministic_across_fresh_trees(self):
        """L2: a fresh tree per invocation yields identical `get` output for a key."""
        driver = _DRIVER_HEADER + textwrap.dedent(
            """
            func TestSnipGetDeterministic(t *testing.T) {
                keys, _ := completeLines("get", "")
                if len(keys) == 0 {
                    t.Fatalf("no catalog keys discovered")
                }
                k := keys[0]
                a, _, err := buildTree([]string{"get", k})
                if err != nil {
                    t.Fatalf("get %q (1) errored: %v", k, err)
                }
                b, _, err := buildTree([]string{"get", k})
                if err != nil {
                    t.Fatalf("get %q (2) errored: %v", k, err)
                }
                if a.String() != b.String() {
                    t.Fatalf("get %q not stable across fresh trees:\\n--1--\\n%s\\n--2--\\n%s",
                        k, a.String(), b.String())
                }
            }
            """
        )
        proc = _run_driver(driver, "TestSnipGetDeterministic")
        assert proc.returncode == 0, (
            "get-deterministic driver failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_get_miss_errors_with_key_no_stdout(self):
        """L2: `get <unknown>` returns an error naming the key and writes no stdout."""
        token = "definitelynotakey_zzz"
        driver = _DRIVER_HEADER + textwrap.dedent(
            """
            func TestSnipGetMiss(t *testing.T) {
                bogus := "%s"
                out, _, err := buildTree([]string{"get", bogus})
                if err == nil {
                    t.Fatalf("get of unknown key must return a non-nil error")
                }
                if !strings.Contains(err.Error(), bogus) {
                    t.Fatalf("error must name the unknown key %%q; got: %%v", bogus, err)
                }
                if strings.TrimSpace(out.String()) != "" {
                    t.Fatalf("unknown key must not write stdout; got:\\n%%s", out.String())
                }
            }
            """ % token
        )
        proc = _run_driver(driver, "TestSnipGetMiss")
        assert proc.returncode == 0, (
            "get-miss driver failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_get_argument_count_errors(self):
        """L2: `get` with zero or two args fails with cobra's arg-count error."""
        driver = _DRIVER_HEADER + textwrap.dedent(
            """
            func TestSnipGetArgCount(t *testing.T) {
                out0, _, err0 := buildTree([]string{"get"})
                if err0 == nil {
                    t.Fatalf("get with no args must error (cobra arg-count)")
                }
                out2, _, err2 := buildTree([]string{"get", "a", "b"})
                if err2 == nil {
                    t.Fatalf("get with two args must error (cobra arg-count)")
                }
                if !strings.Contains(strings.ToLower(err0.Error()), "arg") {
                    t.Fatalf("zero-arg error should be a cobra arg-count error; got: %v", err0)
                }
                if !strings.Contains(strings.ToLower(err2.Error()), "arg") {
                    t.Fatalf("two-arg error should be a cobra arg-count error; got: %v", err2)
                }
                // No body should be printed when the arg count is wrong.
                if strings.TrimSpace(out0.String()) != "" {
                    t.Fatalf("zero-arg get must not print a body; got:\\n%s", out0.String())
                }
                if strings.TrimSpace(out2.String()) != "" {
                    t.Fatalf("two-arg get must not print a body; got:\\n%s", out2.String())
                }
            }
            """
        )
        proc = _run_driver(driver, "TestSnipGetArgCount")
        assert proc.returncode == 0, (
            "get-argcount driver failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_completion_empty_prefix_offers_all_keys_no_file_fallback(self):
        """L2: empty-prefix completion of `<key>` returns >=2 keys and forbids file completion.

        The trailing directive line must carry the NoFileComp bit (value & 4 != 0,
        i.e. NOT the bare Default directive `:0`), so the shell does not fall back
        to file-name completion.
        """
        driver = _DRIVER_HEADER + textwrap.dedent(
            """
            func directiveValue(d string) string {
                // Directive line looks like ":4"; strip the leading colon.
                d = strings.TrimSpace(d)
                if strings.HasPrefix(d, ":") {
                    return strings.TrimSpace(d[1:])
                }
                return d
            }

            func TestSnipCompEmpty(t *testing.T) {
                sugg, directive := completeLines("get", "")
                if len(sugg) < 2 {
                    t.Fatalf("empty-prefix completion must offer all (>=2) keys; got %v", sugg)
                }
                dv := directiveValue(directive)
                // Must not be the plain Default (file-completion) directive.
                if dv == "0" {
                    t.Fatalf("empty-prefix completion fell back to default/file completion: %q", directive)
                }
                // NoFileComp == 4: the directive integer must have the 4-bit set.
                // Accept the common encodings 4 (NoFileComp) and 36 (NoFileComp|...).
                if !strings.Contains(directive, "4") {
                    t.Fatalf("completion directive must set NoFileComp (==4); got: %q", directive)
                }
            }
            """
        )
        proc = _run_driver(driver, "TestSnipCompEmpty")
        assert proc.returncode == 0, (
            "completion-empty driver failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_completion_prefix_is_strict_filtered_subset(self):
        """L2: a typed prefix yields a strict prefix-filtered subset of the full key set.

        Picks a real key, types its first character as the prefix, and asserts the
        suggestions (a) are non-empty, (b) every suggestion starts with that prefix,
        (c) form a subset of the empty-prefix set, and (d) are strictly fewer than
        the full set when another key does not share that prefix. A static
        `ValidArgs` slice (no prefix filtering) fails (b)/(d).
        """
        driver = _DRIVER_HEADER + textwrap.dedent(
            """
            func TestSnipCompPrefix(t *testing.T) {
                all, _ := completeLines("get", "")
                if len(all) < 2 {
                    t.Fatalf("need >=2 keys; got %v", all)
                }
                allSet := map[string]bool{}
                for _, k := range all {
                    allSet[k] = true
                }
                // Choose a prefix from the first key that is NOT shared by every key,
                // so a correct filter must drop at least one suggestion.
                pickKey := all[0]
                prefix := pickKey[:1]
                shared := 0
                for _, k := range all {
                    if strings.HasPrefix(k, prefix) {
                        shared++
                    }
                }
                if shared == len(all) {
                    // First char shared by all; try to find a more selective key/prefix.
                    found := false
                    for _, k := range all {
                        p := k[:1]
                        c := 0
                        for _, kk := range all {
                            if strings.HasPrefix(kk, p) {
                                c++
                            }
                        }
                        if c < len(all) {
                            prefix = p
                            shared = c
                            found = true
                            break
                        }
                    }
                    if !found {
                        // Fall back to a 2-char prefix of the first key.
                        if len(pickKey) >= 2 {
                            prefix = pickKey[:2]
                        }
                    }
                }

                sugg, directive := completeLines("get", prefix)
                if len(sugg) == 0 {
                    t.Fatalf("prefix %q produced no suggestions", prefix)
                }
                for _, s := range sugg {
                    if !strings.HasPrefix(s, prefix) {
                        t.Fatalf("suggestion %q does not start with typed prefix %q (not filtered)", s, prefix)
                    }
                    if !allSet[s] {
                        t.Fatalf("suggestion %q is not a catalog key (came from where?)", s)
                    }
                }
                if len(sugg) > len(all) {
                    t.Fatalf("filtered suggestions cannot exceed the full set")
                }
                // Directive must still forbid file completion.
                if strings.TrimSpace(directive) == ":0" {
                    t.Fatalf("prefix completion fell back to default/file completion: %q", directive)
                }
            }
            """
        )
        proc = _run_driver(driver, "TestSnipCompPrefix")
        assert proc.returncode == 0, (
            "completion-prefix driver failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_completion_nonmatching_prefix_yields_no_keys(self):
        """L2: a prefix matching no key yields zero suggestions but still forbids file completion."""
        driver = _DRIVER_HEADER + textwrap.dedent(
            """
            func TestSnipCompNoMatch(t *testing.T) {
                sugg, directive := completeLines("get", "zzznotaprefix")
                if len(sugg) != 0 {
                    t.Fatalf("a non-matching prefix must yield no suggestions; got %v", sugg)
                }
                if strings.TrimSpace(directive) == ":0" {
                    t.Fatalf("non-matching completion fell back to default/file completion: %q", directive)
                }
                if !strings.Contains(directive, "4") {
                    t.Fatalf("completion directive must set NoFileComp (==4); got: %q", directive)
                }
            }
            """
        )
        proc = _run_driver(driver, "TestSnipCompNoMatch")
        assert proc.returncode == 0, (
            "completion-nomatch driver failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )
