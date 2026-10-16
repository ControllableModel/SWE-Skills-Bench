"""
Test for 'clap-cli-patterns' skill (variant ext9) — Negation completions in
ripgrep's fish completion generator (crates/core/flags/complete/fish.rs).

The variant task makes the fish completion generator emit, for every flag that
declares a negated long name (`name_negated`), an extra `complete -c rg` line
registering that negated long option (e.g. `--hidden` -> a line for the
`no-hidden` long option), carrying the *same* short description (`doc_short`)
as the flag it negates. Positive lines must be unchanged, flags without a
negation get no negation line, single quotes in descriptions stay escaped, and
generation is deterministic (static metadata only).

The native acceptance command is:

    cargo test --bin rg flags::complete::fish::

Verification strategy
---------------------
`fish::generate()` is `pub(crate)` to the `rg` binary crate and cannot be
called from an out-of-tree integration test. So — exactly like the ext1
template injects a `#[cfg(test)] mod` into config.rs — this test injects its
*own* independent `#[cfg(test)]` module into fish.rs that calls the real
`super::generate()` and asserts on the produced text, runs it through the
native toolchain, then always restores the original file. This is robust
against the agent's own tests: a naive implementation that omits negation
lines, hardcodes a single example, mislabels the description, or emits spurious
negations will fail these injected Rust assertions.

Discriminators encoded here:
  * `--hidden` must yield a negation line for the `no-hidden` long option with
    `--hidden`'s description ("Search hidden files and directories.").
  * `--multiline-dotall` (whose doc_short is `Make '.' match line terminators.`)
    must yield a `no-multiline-dotall` negation line whose embedded single
    quotes remain escaped (`\'`), proving quoting is preserved on the new line.
  * The positive `--hidden` line (registering the `hidden` long option) must be
    retained unchanged.
  * `--max-count` declares no negation and must contribute no negation line.
  * The total number of emitted negation lines must equal the number of flags
    that declare a negated name (no spurious / no missing negations).
  * Two calls to generate() must produce byte-identical output (determinism).

L1 cases check the deliverable file is present / well-formed and that the agent
added its own unit tests. L2 cases compile + run real Rust assertions against
`super::generate()`.
"""

import os
import re
import subprocess

import pytest


REPO_DIR = "/workspace/ripgrep"
FISH_REL = os.path.join("crates", "core", "flags", "complete", "fish.rs")
FISH_PATH = os.path.join(REPO_DIR, FISH_REL)

# Unique marker so our scratch module is easy to identify / strip out again.
INJECT_MARKER = "// __BENCH_CLAP_CLI_PATTERNS_EXT9_INJECTED__"

CARGO_BUILD_TIMEOUT = 600


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read(path):
    with open(path, "r", encoding="utf-8", errors="surrogateescape") as f:
        return f.read()


def _write(path, content):
    with open(path, "w", encoding="utf-8", errors="surrogateescape") as f:
        f.write(content)


def _cargo_env():
    env = dict(os.environ)
    home = env.get("HOME", "/root")
    extra = os.pathsep.join(
        [
            os.path.join(home, ".cargo", "bin"),
            "/usr/local/cargo/bin",
            "/root/.cargo/bin",
        ]
    )
    env["PATH"] = extra + os.pathsep + env.get("PATH", "")
    return env


def _run_injected_rust_test(test_fn_name, rust_body):
    """Inject a Rust test fn into fish.rs, run it via cargo, restore file.

    `rust_body` is the full body (incl. each `#[test]` signature) of one or
    more test functions which may call `super::generate()` (the fish completion
    generator, returning the full completion script as a `String`).

    Returns the CompletedProcess of the cargo invocation. The original file is
    always restored, even on failure.
    """
    original = _read(FISH_PATH)

    module = "\n".join(
        [
            "",
            INJECT_MARKER,
            "#[cfg(test)]",
            "mod bench_clap_cli_patterns_ext9 {",
            "    #[allow(unused_imports)]",
            "    use super::generate;",
            "",
            rust_body,
            "}",
            INJECT_MARKER,
            "",
        ]
    )

    patched = original + module
    try:
        _write(FISH_PATH, patched)
        proc = subprocess.run(
            [
                "cargo",
                "test",
                "--bin",
                "rg",
                "flags::complete::fish::bench_clap_cli_patterns_ext9::"
                + test_fn_name,
                "--",
                "--nocapture",
            ],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=CARGO_BUILD_TIMEOUT,
            env=_cargo_env(),
        )
        return proc
    finally:
        _write(FISH_PATH, original)


def _assert_cargo_ok(proc, expect_run="1"):
    combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
    assert proc.returncode == 0, (
        "cargo test failed (rc=%s).\nSTDOUT:\n%s\nSTDERR:\n%s"
        % (proc.returncode, proc.stdout, proc.stderr)
    )
    # Guard against the test silently being filtered out / never executed.
    assert (
        "test result: ok" in combined
    ), "no successful test result reported:\n" + combined
    assert re.search(
        r"running\s+%s\s+test" % re.escape(expect_run), combined
    ), (
        "expected %s injected test(s) to actually run, output was:\n%s"
        % (expect_run, combined)
    )


# Shared Rust helper snippets pasted into each injected module. These reach
# into the *real* flag metadata so the assertions stay in sync with whatever
# flags exist, rather than hardcoding a brittle list.
_RUST_HELPERS = r"""
    use crate::flags::defs::FLAGS;

    // Collect every distinct line of the generated fish script.
    fn lines() -> Vec<String> {
        generate().lines().map(|s| s.to_string()).collect()
    }

    // A "negation" completion line is one produced by TEMPLATE_NEGATED: it
    // registers a long option and is gated by the __rg_contains_opt predicate
    // (which positive lines never carry). We detect such a line for a given
    // negated long name.
    fn negation_line_for<'a>(ls: &'a [String], negated: &str) -> Option<&'a String> {
        let needle = format!("-l {} ", negated);
        ls.iter().find(|l| {
            l.starts_with("complete -c rg")
                && l.contains(&needle)
                && l.contains("__rg_contains_opt")
        })
    }

    // A positive completion line registers `-l <long>` and is NOT a negation
    // line (no __rg_contains_opt predicate).
    fn positive_line_for<'a>(ls: &'a [String], long: &str) -> Option<&'a String> {
        let needle = format!("-l {} ", long);
        ls.iter().find(|l| {
            l.starts_with("complete -c rg")
                && l.contains(&needle)
                && !l.contains("__rg_contains_opt")
        })
    }
"""


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------

class TestClapCliPatterns:
    """Verify negation completion emission in fish.rs's generate()."""

    REPO_DIR = REPO_DIR

    # ------------------------------------------------------------------
    # L1 — deliverable presence & shape
    # ------------------------------------------------------------------

    def test_fish_file_exists(self):
        """The fish completion generator file must exist."""
        assert os.path.isfile(FISH_PATH), "fish.rs not found at " + FISH_PATH

    def test_generate_entry_point_present(self):
        """The `generate()` entry point and flag iteration must remain."""
        src = _read(FISH_PATH)
        assert "fn generate" in src, "generate() function missing from fish.rs"
        assert "FLAGS" in src, "fish.rs no longer iterates the FLAGS metadata"
        # The positive completion template (or an equivalent) must remain so the
        # primary lines are still produced.
        assert "complete -c rg" in src, (
            "fish.rs no longer emits any `complete -c rg` completion text"
        )

    def test_references_negated_metadata(self):
        """fish.rs must consult each flag's negated name to emit negations."""
        src = _read(FISH_PATH)
        assert "name_negated" in src, (
            "fish.rs does not reference name_negated(); negation lines cannot "
            "be derived from flag metadata"
        )

    def test_has_unit_tests(self):
        """The agent must add a #[cfg(test)] mod tests with negation tests."""
        src = _read(FISH_PATH)
        assert "#[cfg(test)]" in src, "no #[cfg(test)] block added to fish.rs"
        assert "mod tests" in src, "mod tests block missing from fish.rs"
        test_count = len(re.findall(r"#\[test\]", src))
        assert test_count >= 1, (
            "expected the agent to add at least one #[test]; found %d"
            % test_count
        )

    def test_no_leftover_injection(self):
        """Sanity: our scratch injection marker must not be committed."""
        src = _read(FISH_PATH)
        assert INJECT_MARKER not in src, (
            "leftover injected test module found in fish.rs; "
            "a previous run did not restore the file"
        )

    def test_existing_completion_suite_passes(self):
        """The whole fish completion test path must compile and pass."""
        proc = subprocess.run(
            ["cargo", "test", "--bin", "rg", "flags::complete::fish::"],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=CARGO_BUILD_TIMEOUT,
            env=_cargo_env(),
        )
        combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
        assert proc.returncode == 0, (
            "fish completion tests failed.\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )
        assert "test result: ok" in combined, combined

    # ------------------------------------------------------------------
    # L2 — dynamic behavioral verification via injected Rust tests
    # ------------------------------------------------------------------

    def test_hidden_negation_line_emitted(self):
        """`--hidden` yields a `no-hidden` negation line with its description."""
        body = _RUST_HELPERS + r"""
    #[test]
    fn t() {
        let ls = lines();
        let line = negation_line_for(&ls, "no-hidden")
            .expect("missing negation completion line for `no-hidden`");
        // Must carry the negated flag's *own* short description.
        assert!(
            line.contains("Search hidden files and directories."),
            "no-hidden negation line must carry --hidden's doc_short; got: {}",
            line
        );
    }
"""
        proc = _run_injected_rust_test("t", body)
        _assert_cargo_ok(proc)

    def test_positive_hidden_line_retained(self):
        """The primary positive `hidden` completion line is still emitted."""
        body = _RUST_HELPERS + r"""
    #[test]
    fn t() {
        let ls = lines();
        let pos = positive_line_for(&ls, "hidden")
            .expect("primary positive completion line for `hidden` missing");
        // Positive line registers -l hidden and carries the description, and is
        // distinct from the negation line.
        assert!(
            pos.contains("Search hidden files and directories."),
            "positive hidden line lost its description: {}",
            pos
        );
        assert!(
            !pos.contains("__rg_contains_opt"),
            "positive line must not be a negation line: {}",
            pos
        );
        // The positive `-l hidden ` token must not accidentally match
        // `no-hidden` (word boundary): ensure both lines coexist distinctly.
        assert!(
            negation_line_for(&ls, "no-hidden").is_some(),
            "expected both positive `hidden` and negation `no-hidden` lines"
        );
    }
"""
        proc = _run_injected_rust_test("t", body)
        _assert_cargo_ok(proc)

    def test_no_ignore_vcs_long_option_present(self):
        """The `no-ignore-vcs` long option line must be present in output."""
        body = _RUST_HELPERS + r"""
    #[test]
    fn t() {
        // Per the acceptance doc, output must contain a `complete -c rg` line
        // registering the `no-ignore-vcs` long option (the NoIgnoreVcs flag's
        // primary line). This line must exist and carry its description.
        let ls = lines();
        let line = positive_line_for(&ls, "no-ignore-vcs")
            .or_else(|| negation_line_for(&ls, "no-ignore-vcs"))
            .expect("missing completion line for `no-ignore-vcs` long option");
        assert!(
            line.contains("Don't use ignore files from source control.")
                || line.contains("Don\\'t use ignore files from source control."),
            "no-ignore-vcs line missing its description: {}",
            line
        );
    }
"""
        proc = _run_injected_rust_test("t", body)
        _assert_cargo_ok(proc)

    def test_negation_line_quotes_escaped(self):
        """A negation line preserves escaped single quotes in its description."""
        body = _RUST_HELPERS + r"""
    #[test]
    fn t() {
        // `--multiline-dotall` has doc_short `Make '.' match line terminators.`
        // and a negation `no-multiline-dotall`. The negation line must keep the
        // single quotes escaped (\') so the fish script stays valid.
        let ls = lines();
        let line = negation_line_for(&ls, "no-multiline-dotall")
            .expect("missing negation line for `no-multiline-dotall`");
        assert!(
            line.contains(r"Make \'.\' match line terminators."),
            "single quotes must remain escaped on the negation line; got: {}",
            line
        );
        // It must NOT contain a raw unescaped `'.'` token from the description.
        assert!(
            !line.contains("Make '.' match"),
            "negation line contains unescaped single quotes: {}",
            line
        );
    }
"""
        proc = _run_injected_rust_test("t", body)
        _assert_cargo_ok(proc)

    def test_flag_without_negation_has_no_negation_line(self):
        """`--max-count` (no negation) contributes no negation line."""
        body = _RUST_HELPERS + r"""
    #[test]
    fn t() {
        let ls = lines();
        // max-count declares no negated name; it must still have its positive
        // line, but no negation line registering a negated form for it.
        assert!(
            positive_line_for(&ls, "max-count").is_some(),
            "positive max-count line should still exist"
        );
        // No emitted negation line should be gated on `__rg_contains_opt
        // max-count` (i.e. there must be no negation derived from max-count).
        let spurious = ls.iter().any(|l| {
            l.contains("__rg_contains_opt")
                && l.contains("max-count")
        });
        assert!(
            !spurious,
            "max-count must not produce any negation completion line"
        );
    }
"""
        proc = _run_injected_rust_test("t", body)
        _assert_cargo_ok(proc)

    def test_negation_line_count_matches_metadata(self):
        """#negation lines == #flags declaring a negated name (no spurious)."""
        body = _RUST_HELPERS + r"""
    #[test]
    fn t() {
        // Ground truth: count flags that declare a negated long name.
        let expected: usize = FLAGS
            .iter()
            .filter(|f| f.name_negated().is_some())
            .count();
        assert!(expected > 1, "fixture sanity: expected several negated flags");

        let ls = lines();
        // Count emitted negation lines (those gated by __rg_contains_opt and
        // registering a long option).
        let got = ls
            .iter()
            .filter(|l| {
                l.starts_with("complete -c rg")
                    && l.contains("__rg_contains_opt")
                    && l.contains(" -l ")
            })
            .count();
        assert_eq!(
            got, expected,
            "expected exactly one negation line per negated flag \
             ({} flags) but found {} negation lines",
            expected, got
        );
    }
"""
        proc = _run_injected_rust_test("t", body)
        _assert_cargo_ok(proc)

    def test_every_negated_flag_has_its_line(self):
        """Each negated flag's specific negated name appears as a line."""
        body = _RUST_HELPERS + r"""
    #[test]
    fn t() {
        let ls = lines();
        // For every flag with a negated name, a negation line registering that
        // exact negated long option must exist, carrying that flag's doc_short.
        for f in FLAGS.iter() {
            if let Some(neg) = f.name_negated() {
                let line = negation_line_for(&ls, neg).unwrap_or_else(|| {
                    panic!(
                        "no negation completion line for negated name `{}` \
                         (long `{}`)",
                        neg,
                        f.name_long()
                    )
                });
                let want = f.doc_short().replace("'", "\\'");
                assert!(
                    line.contains(&want),
                    "negation line for `{}` must carry its flag's escaped \
                     doc_short `{}`; got: {}",
                    neg, want, line
                );
            }
        }
    }
"""
        proc = _run_injected_rust_test("t", body)
        _assert_cargo_ok(proc)

    def test_generation_is_deterministic(self):
        """generate() yields byte-identical output across repeated calls."""
        body = _RUST_HELPERS + r"""
    #[test]
    fn t() {
        let a = generate();
        let b = generate();
        assert_eq!(a, b, "fish completion output must be deterministic");
        // And it must actually contain negation content (non-empty work).
        assert!(
            a.contains("__rg_contains_opt"),
            "output contains no negation completion lines at all"
        );
    }
"""
        proc = _run_injected_rust_test("t", body)
        _assert_cargo_ok(proc)

    def test_negation_uses_negated_not_positive_long(self):
        """Negation line registers the negated name, not the positive long."""
        body = _RUST_HELPERS + r"""
    #[test]
    fn t() {
        // A naive impl might emit a "negation" line that still registers the
        // positive long option (e.g. -l hidden) instead of -l no-hidden. Make
        // sure the no-hidden line registers `no-hidden` and that there is no
        // negation-style line (gated by __rg_contains_opt) that registers the
        // bare positive `hidden` long option.
        let ls = lines();
        let neg = negation_line_for(&ls, "no-hidden")
            .expect("missing no-hidden negation line");
        assert!(
            neg.contains("-l no-hidden "),
            "negation line must register `-l no-hidden`: {}",
            neg
        );
        let bad = ls.iter().any(|l| {
            l.contains("__rg_contains_opt") && l.contains("-l hidden ")
        });
        assert!(
            !bad,
            "a negation-style line wrongly registers the positive `hidden` long"
        );
    }
"""
        proc = _run_injected_rust_test("t", body)
        _assert_cargo_ok(proc)

    def test_positive_lines_unchanged_for_negated_flags(self):
        """Negated flags still emit their unchanged positive line."""
        body = _RUST_HELPERS + r"""
    #[test]
    fn t() {
        let ls = lines();
        // For each negated flag, BOTH its positive line (long name) AND its
        // negation line must be present: adding negations must not remove or
        // replace the original positive completion.
        for f in FLAGS.iter() {
            if let Some(neg) = f.name_negated() {
                let long = f.name_long();
                assert!(
                    positive_line_for(&ls, long).is_some(),
                    "positive line for negated flag `{}` went missing",
                    long
                );
                assert!(
                    negation_line_for(&ls, neg).is_some(),
                    "negation line for `{}` missing",
                    neg
                );
            }
        }
    }
"""
        proc = _run_injected_rust_test("t", body)
        _assert_cargo_ok(proc)
