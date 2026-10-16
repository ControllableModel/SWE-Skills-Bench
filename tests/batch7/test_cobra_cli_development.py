"""Tests for the `cobra-cli-development` skill (variant ext7).

Skill task: add a brand-new, fully offline `gh stats` cobra command to the
GitHub CLI (github.com/cli/cli/v2). The command:
  * is constructed via `NewCmdStats(f *cmdutil.Factory) *cobra.Command` and
    registered on the root command in `pkg/cmd/root/root.go`;
  * accepts between 1 and 8 positional NUMERIC args, enforced with cobra's
    range argument validation (cobra.RangeArgs) -- zero args and nine args both
    fail with cobra's standard argument-count error before the handler runs;
  * has a `--metric` / `-m` string flag (default `sum`) restricted to one of
    {sum, mean, min, max}; an unsupported value errors before computing;
  * registers a flag-value completion function for `--metric` that suggests
    EXACTLY the four supported metric names with no file-name fallback;
  * computes the requested metric over the parsed numbers and prints the result
    on a single line to stdout, deterministically formatted (trailing zeros
    trimmed; mean of `1 2` -> `1.5`); nothing to stderr on success;
  * returns errors via `error` (no os.Exit/panic), never writes os.Stdout
    directly, and leaks no flag state between fresh invocations.

Verification strategy (discriminative):
  * L1 checks confirm the deliverable files exist, are well-formed Go, expose
    the required constructor signature, and that the new package + the modified
    root package both compile.
  * L2 checks DO NOT trust the agent's own `stats_test.go`. Each relevant case
    writes an *independent* white-box Go driver test into the stats package
    directory, builds a fresh command via the agent's `NewCmdStats(f)`, drives
    it with cobra's `SetArgs` + redirected streams, and asserts on real captured
    stdout/stderr/error and on completion output. A naive/hardcoded solution
    (fixed return value, ignored args, unbounded args, missing metric
    validation, missing flag completion) fails to compile or returns the wrong
    captured output, failing these tests.

Native command: `go test ./pkg/cmd/stats/...` plus targeted `go build`.
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
STATS_PKG_DIR = os.path.join(REPO_DIR, "pkg", "cmd", "stats")
ROOT_GO = os.path.join(REPO_DIR, "pkg", "cmd", "root", "root.go")
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
    """Write an independent white-box driver test into the stats package."""
    name = "zz_skilltest_%s_test.go" % uuid.uuid4().hex[:10]
    path = os.path.join(STATS_PKG_DIR, name)
    with open(path, "w") as fh:
        fh.write(go_source)
    return path


def _run_driver(go_source, run_regex, timeout=GO_TIMEOUT):
    """Drop a driver test into the stats package, run only it, then clean up."""
    assert os.path.isdir(STATS_PKG_DIR), (
        "stats package dir missing: %s" % STATS_PKG_DIR
    )
    path = _write_driver(go_source)
    try:
        return _run_go(
            ["go", "test", "-count=1", "-run", run_regex, "./pkg/cmd/stats/"],
            timeout=timeout,
        )
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


# Shared Go preamble for white-box driver tests living in package `stats`.
# buildTree wires capturable streams onto both IOStreams (used by handlers) and
# the cobra command (used by cobra-emitted output such as arg-count errors and
# the hidden __complete command).
_DRIVER_HEADER = textwrap.dedent(
    """
    package stats

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
        cmd := NewCmdStats(f)
        cmd.SetArgs(args)
        cmd.SetIn(&bytes.Buffer{})
        cmd.SetOut(outBuf)
        cmd.SetErr(errBuf)
        _, err := cmd.ExecuteC()
        return outBuf, errBuf, err
    }

    func firstLine(s string) string {
        for _, ln := range strings.Split(s, "\\n") {
            if strings.TrimSpace(ln) != "" {
                return strings.TrimSpace(ln)
            }
        }
        return ""
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
        """L1: stats.go + stats_test.go + modified root.go are present on disk."""
        required = [
            os.path.join(STATS_PKG_DIR, "stats.go"),
            os.path.join(STATS_PKG_DIR, "stats_test.go"),
            ROOT_GO,
        ]
        missing = [p for p in required if not os.path.isfile(p)]
        assert not missing, "missing deliverable files: %s" % missing

    def test_package_declaration_and_constructor(self):
        """L1: stats.go declares package stats and exposes NewCmdStats(f *cmdutil.Factory) *cobra.Command."""
        with open(os.path.join(STATS_PKG_DIR, "stats.go")) as fh:
            src = fh.read()
        assert re.search(r"^\s*package\s+stats\b", src, re.MULTILINE), (
            "stats.go must declare `package stats`"
        )
        assert re.search(
            r"func\s+NewCmdStats\s*\(\s*\w+\s+\*cmdutil\.Factory\s*\)\s*\*cobra\.Command",
            src,
        ), "NewCmdStats(f *cmdutil.Factory) *cobra.Command signature required"

    def test_uses_range_args_not_handrolled(self):
        """L1: bounded args use cobra.RangeArgs(1, 8), not a hand-rolled len(args) check."""
        with open(os.path.join(STATS_PKG_DIR, "stats.go")) as fh:
            src = fh.read()
        assert re.search(r"cobra\.RangeArgs\s*\(\s*1\s*,\s*8\s*\)", src), (
            "stats.go must enforce 1..8 args via cobra.RangeArgs(1, 8)"
        )

    def test_registers_metric_flag_completion(self):
        """L1: a flag-value completion function is registered for `--metric`."""
        with open(os.path.join(STATS_PKG_DIR, "stats.go")) as fh:
            src = fh.read()
        assert re.search(
            r"RegisterFlagCompletionFunc\s*\(\s*\"metric\"", src
        ), "stats.go must RegisterFlagCompletionFunc for \"metric\""

    def test_stats_package_builds(self):
        """L1: the new stats package and the modified root package both compile."""
        proc = _run_go(
            ["go", "build", "./pkg/cmd/stats/...", "./pkg/cmd/root/..."]
        )
        assert proc.returncode == 0, (
            "go build failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_root_registers_stats(self):
        """L1: root.go imports the stats package and calls NewCmdStats."""
        with open(ROOT_GO) as fh:
            src = fh.read()
        assert "cmd/stats" in src, "root.go must import the stats package"
        assert "NewCmdStats" in src, (
            "root.go must call NewCmdStats to register the command"
        )

    # ------------------------------------------------------------------ L2 ---
    def test_agent_native_tests_pass(self):
        """L2: the package's own test suite passes (go test ./pkg/cmd/stats/...)."""
        proc = _run_go(["go", "test", "-count=1", "./pkg/cmd/stats/..."])
        assert proc.returncode == 0, (
            "go test ./pkg/cmd/stats/... failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_default_metric_sum(self):
        """L2: `stats 1 2 3 4` prints exactly `10` (default metric sum), nothing on stderr."""
        driver = _DRIVER_HEADER + textwrap.dedent(
            """
            func TestStatsDefaultSum(t *testing.T) {
                out, errBuf, err := buildCmd([]string{"1", "2", "3", "4"})
                if err != nil {
                    t.Fatalf("default sum errored: %v (stderr=%s)", err, errBuf.String())
                }
                if strings.TrimSpace(errBuf.String()) != "" {
                    t.Fatalf("success path wrote to stderr: %q", errBuf.String())
                }
                got := firstLine(out.String())
                if got != "10" {
                    t.Fatalf("stats 1 2 3 4 must print 10; got %q (full=%q)", got, out.String())
                }
                // A single non-empty output line, no leftover noise.
                if len(nonEmpty(out.String())) != 1 {
                    t.Fatalf("expected exactly one output line; got:\\n%s", out.String())
                }
            }
            """
        )
        proc = _run_driver(driver, "TestStatsDefaultSum")
        assert proc.returncode == 0, (
            "default-sum driver failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_mean_min_max_metrics(self):
        """L2: -m mean/min/max compute correct values with deterministic formatting (1.5, 1, 9)."""
        driver = _DRIVER_HEADER + textwrap.dedent(
            """
            func TestStatsMeanMinMax(t *testing.T) {
                cases := []struct {
                    args []string
                    want string
                }{
                    {[]string{"1", "2", "-m", "mean"}, "1.5"},
                    {[]string{"5", "1", "9", "-m", "min"}, "1"},
                    {[]string{"5", "1", "9", "-m", "max"}, "9"},
                    {[]string{"2", "4", "6", "-m", "mean"}, "4"},
                    {[]string{"10", "20", "30", "-m", "sum"}, "60"},
                }
                for _, c := range cases {
                    out, errBuf, err := buildCmd(c.args)
                    if err != nil {
                        t.Fatalf("args %v errored: %v (stderr=%s)", c.args, err, errBuf.String())
                    }
                    got := firstLine(out.String())
                    if got != c.want {
                        t.Fatalf("args %v: want %q got %q", c.args, c.want, got)
                    }
                }
            }
            """
        )
        proc = _run_driver(driver, "TestStatsMeanMinMax")
        assert proc.returncode == 0, (
            "mean-min-max driver failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_short_and_long_metric_flag_agree(self):
        """L2: `-m mean` and `--metric mean` produce identical output."""
        driver = _DRIVER_HEADER + textwrap.dedent(
            """
            func TestStatsFlagFormsAgree(t *testing.T) {
                shortOut, _, errS := buildCmd([]string{"1", "2", "3", "-m", "mean"})
                if errS != nil {
                    t.Fatalf("-m form errored: %v", errS)
                }
                longOut, _, errL := buildCmd([]string{"1", "2", "3", "--metric", "mean"})
                if errL != nil {
                    t.Fatalf("--metric form errored: %v", errL)
                }
                if firstLine(shortOut.String()) != firstLine(longOut.String()) {
                    t.Fatalf("-m and --metric disagree: %q vs %q",
                        shortOut.String(), longOut.String())
                }
                if firstLine(shortOut.String()) != "2" {
                    t.Fatalf("mean of 1 2 3 must be 2; got %q", firstLine(shortOut.String()))
                }
            }
            """
        )
        proc = _run_driver(driver, "TestStatsFlagFormsAgree")
        assert proc.returncode == 0, (
            "flag-forms driver failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_unsupported_metric_errors_no_stdout(self):
        """L2: `-m median` is an unsupported-metric error with no statistic printed."""
        driver = _DRIVER_HEADER + textwrap.dedent(
            """
            func TestStatsBadMetric(t *testing.T) {
                out, _, err := buildCmd([]string{"1", "2", "-m", "median"})
                if err == nil {
                    t.Fatalf("unsupported metric `median` must return a non-nil error")
                }
                if strings.TrimSpace(out.String()) != "" {
                    t.Fatalf("unsupported metric must not print a statistic; got:\\n%s", out.String())
                }
                // Another clearly-unsupported value.
                out2, _, err2 := buildCmd([]string{"1", "2", "-m", "stddev"})
                if err2 == nil {
                    t.Fatalf("unsupported metric `stddev` must error")
                }
                if strings.TrimSpace(out2.String()) != "" {
                    t.Fatalf("unsupported metric must not print; got:\\n%s", out2.String())
                }
            }
            """
        )
        proc = _run_driver(driver, "TestStatsBadMetric")
        assert proc.returncode == 0, (
            "bad-metric driver failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_non_numeric_arg_errors_naming_value(self):
        """L2: `stats 1 x 3` returns an error naming `x` with no statistic printed."""
        driver = _DRIVER_HEADER + textwrap.dedent(
            """
            func TestStatsNonNumeric(t *testing.T) {
                out, _, err := buildCmd([]string{"1", "x", "3"})
                if err == nil {
                    t.Fatalf("non-numeric arg must return a non-nil error")
                }
                if !strings.Contains(err.Error(), "x") {
                    t.Fatalf("error must name the bad value `x`; got: %v", err)
                }
                if strings.TrimSpace(out.String()) != "" {
                    t.Fatalf("non-numeric arg must not print a statistic; got:\\n%s", out.String())
                }
            }
            """
        )
        proc = _run_driver(driver, "TestStatsNonNumeric")
        assert proc.returncode == 0, (
            "non-numeric driver failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_arg_count_bounds_zero_and_nine(self):
        """L2: zero args and nine args both fail with cobra's argument-count error, no output."""
        driver = _DRIVER_HEADER + textwrap.dedent(
            """
            func TestStatsArgBounds(t *testing.T) {
                // Zero args.
                out0, _, err0 := buildCmd([]string{})
                if err0 == nil {
                    t.Fatalf("zero args must error (cobra range arg-count)")
                }
                if !strings.Contains(strings.ToLower(err0.Error()), "arg") {
                    t.Fatalf("zero-arg error should be a cobra arg-count error; got: %v", err0)
                }
                if strings.TrimSpace(out0.String()) != "" {
                    t.Fatalf("zero args must not print a statistic; got:\\n%s", out0.String())
                }
                // Nine args (one over the upper bound of 8).
                nine := []string{"1", "2", "3", "4", "5", "6", "7", "8", "9"}
                out9, _, err9 := buildCmd(nine)
                if err9 == nil {
                    t.Fatalf("nine args must error (cobra range arg-count)")
                }
                if !strings.Contains(strings.ToLower(err9.Error()), "arg") {
                    t.Fatalf("nine-arg error should be a cobra arg-count error; got: %v", err9)
                }
                if strings.TrimSpace(out9.String()) != "" {
                    t.Fatalf("nine args must not print a statistic; got:\\n%s", out9.String())
                }
                // Exactly 8 args (upper boundary, inclusive) must succeed.
                eight := []string{"1", "1", "1", "1", "1", "1", "1", "1"}
                out8, _, err8 := buildCmd(eight)
                if err8 != nil {
                    t.Fatalf("exactly 8 args must be accepted; got error: %v", err8)
                }
                if firstLine(out8.String()) != "8" {
                    t.Fatalf("sum of eight 1s must be 8; got %q", firstLine(out8.String()))
                }
                // Exactly 1 arg (lower boundary) must succeed.
                out1, _, err1 := buildCmd([]string{"42"})
                if err1 != nil {
                    t.Fatalf("exactly 1 arg must be accepted; got error: %v", err1)
                }
                if firstLine(out1.String()) != "42" {
                    t.Fatalf("sum of single 42 must be 42; got %q", firstLine(out1.String()))
                }
            }
            """
        )
        proc = _run_driver(driver, "TestStatsArgBounds")
        assert proc.returncode == 0, (
            "arg-bounds driver failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_metric_flag_value_completion(self):
        """L2: completing `--metric` value yields exactly {sum,mean,min,max}, no file fallback."""
        driver = _DRIVER_HEADER + textwrap.dedent(
            """
            func TestStatsMetricCompletion(t *testing.T) {
                // Drive cobra's hidden __complete on a fresh tree, asking to
                // complete the value of --metric.
                out, _, _ := buildCmd([]string{"__complete", "--metric", ""})
                comp := out.String()
                want := []string{"sum", "mean", "min", "max"}
                for _, w := range want {
                    found := false
                    for _, ln := range nonEmpty(comp) {
                        tok := strings.Fields(ln)
                        if len(tok) > 0 && tok[0] == w {
                            found = true
                            break
                        }
                    }
                    if !found {
                        t.Fatalf("metric completion must suggest %q; got:\\n%s", w, comp)
                    }
                }
                // It must offer NOTHING beyond the four metrics (modulo the
                // trailing cobra directive line beginning with ':').
                suggestions := map[string]bool{}
                for _, ln := range nonEmpty(comp) {
                    if strings.HasPrefix(strings.TrimSpace(ln), ":") {
                        continue
                    }
                    tok := strings.Fields(ln)
                    if len(tok) > 0 {
                        suggestions[tok[0]] = true
                    }
                }
                if len(suggestions) != 4 {
                    t.Fatalf("metric completion must offer exactly 4 names; got %d: %v\\n%s",
                        len(suggestions), suggestions, comp)
                }
                for k := range suggestions {
                    if k != "sum" && k != "mean" && k != "min" && k != "max" {
                        t.Fatalf("unexpected completion suggestion %q", k)
                    }
                }
                // No file-name fallback: the directive must include
                // ShellCompDirectiveNoFileComp (value 4). The directive line is
                // emitted as ":<n>" on the final line.
                trimmed := strings.TrimRight(comp, "\\n")
                if strings.HasSuffix(trimmed, ":0") {
                    t.Fatalf("metric completion fell back to default/file completion:\\n%s", comp)
                }
            }
            """
        )
        proc = _run_driver(driver, "TestStatsMetricCompletion")
        assert proc.returncode == 0, (
            "metric-completion driver failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_deterministic_formatting_trims_trailing_zeros(self):
        """L2: integral results print without a trailing `.0`; fractional keep needed digits."""
        driver = _DRIVER_HEADER + textwrap.dedent(
            """
            func TestStatsFormatting(t *testing.T) {
                // mean of 2 4 -> 3 (not 3.0 / 3.00).
                out, _, err := buildCmd([]string{"2", "4", "-m", "mean"})
                if err != nil {
                    t.Fatalf("mean 2 4 errored: %v", err)
                }
                got := firstLine(out.String())
                if got != "3" {
                    t.Fatalf("mean of 2 4 must format as `3` (trimmed); got %q", got)
                }
                // sum of 1 2 3 -> 6, must not be `6.0`.
                outS, _, errS := buildCmd([]string{"1", "2", "3"})
                if errS != nil {
                    t.Fatalf("sum errored: %v", errS)
                }
                if firstLine(outS.String()) != "6" {
                    t.Fatalf("sum 1 2 3 must format as `6`; got %q", firstLine(outS.String()))
                }
                // mean of 1 2 -> 1.5 keeps the needed fractional digit.
                outF, _, errF := buildCmd([]string{"1", "2", "-m", "mean"})
                if errF != nil {
                    t.Fatalf("mean 1 2 errored: %v", errF)
                }
                if firstLine(outF.String()) != "1.5" {
                    t.Fatalf("mean of 1 2 must be `1.5`; got %q", firstLine(outF.String()))
                }
            }
            """
        )
        proc = _run_driver(driver, "TestStatsFormatting")
        assert proc.returncode == 0, (
            "formatting driver failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    def test_no_leaked_flag_state_between_invocations(self):
        """L2: a fresh command per invocation yields identical, metric-independent results (no leaked --metric)."""
        driver = _DRIVER_HEADER + textwrap.dedent(
            """
            func TestStatsNoLeak(t *testing.T) {
                // First run with a non-default metric, then a default run: the
                // default run must NOT inherit the previous --metric value.
                _, _, err := buildCmd([]string{"4", "8", "-m", "min"})
                if err != nil {
                    t.Fatalf("seed run errored: %v", err)
                }
                a, _, errA := buildCmd([]string{"4", "8"})
                if errA != nil {
                    t.Fatalf("default run A errored: %v", errA)
                }
                b, _, errB := buildCmd([]string{"4", "8"})
                if errB != nil {
                    t.Fatalf("default run B errored: %v", errB)
                }
                if a.String() != b.String() {
                    t.Fatalf("repeated default runs differ (state leak?):\\nA=%q\\nB=%q",
                        a.String(), b.String())
                }
                // Default metric is sum: 4 + 8 = 12, NOT min (4).
                if firstLine(a.String()) != "12" {
                    t.Fatalf("default run after `-m min` must use sum (12), not leaked min; got %q",
                        firstLine(a.String()))
                }
            }
            """
        )
        proc = _run_driver(driver, "TestStatsNoLeak")
        assert proc.returncode == 0, (
            "no-leak driver failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )
