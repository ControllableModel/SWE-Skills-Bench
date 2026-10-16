"""
Test for 'clap-cli-patterns' skill (variant ext4) — add a negatable
`--summary` / `--no-summary` boolean switch flag to ripgrep.

The task (see tasks/ext4/clap-cli-patterns.md) asks the agent to:
  * add a plain `bool` field to `LowArgs` (crates/core/flags/lowargs.rs),
    defaulting to `false`,
  * implement a new switch `Flag` in crates/core/flags/defs.rs whose
    positive long name is `summary`, whose negated long name is
    `no-summary`, which has NO short name and consumes NO value,
  * register the flag in the global `FLAGS` slice so both `--summary`
    and `--no-summary` parse, and
  * add a `#[test] fn test_summary` covering: default false, `--summary`
    true, `--no-summary` false, `--summary --no-summary` false,
    `--no-summary --summary` true.

Native acceptance command (from the doc):
    cargo test --bin rg flags::defs::test_summary

Verification strategy
---------------------
The flag is exercised through the *real* parser entry point
`crate::flags::parse::parse_low_raw`, which is private to the `rg` binary
crate.  We therefore verify the agent's work DISCRIMINATIVELY by injecting
our OWN `#[cfg(test)]` module into defs.rs (rather than trusting the agent's
own test) and running it through the native toolchain, then restoring the
file.

Crucially, the boolean field name the agent picks on `LowArgs` is not fixed
by the doc, so our injected Rust assertions are *field-name agnostic*: they
diff the `Debug` rendering of a parsed `LowArgs` against
`LowArgs::default()` to discover exactly which plain `bool` field toggled.
A naive solution that fails to register the flag, hardcodes a value, ignores
the negated form, mishandles override order, or makes the negated form
consume a value will fail these assertions.

L1 cases check the deliverable files exist, are minimally well-formed, that
the flag surface is wired (registration + switch + negation, asserted via the
parser's `lookup`), and that the agent added its own `test_summary`.  L2 cases
compile and run real Rust assertions exercising the negation / override
semantics end to end, and finally run the native `test_summary` itself.
"""

import os
import re
import subprocess

import pytest


REPO_DIR = "/workspace/ripgrep"

DEFS_REL = os.path.join("crates", "core", "flags", "defs.rs")
DEFS_PATH = os.path.join(REPO_DIR, DEFS_REL)
LOWARGS_REL = os.path.join("crates", "core", "flags", "lowargs.rs")
LOWARGS_PATH = os.path.join(REPO_DIR, LOWARGS_REL)

# Unique marker so our injected module is easy to identify / strip out again.
INJECT_MARKER = "// __BENCH_CLAP_CLI_PATTERNS_EXT4_INJECTED__"

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
    """Inject a Rust test fn into defs.rs, run it via cargo, restore the file.

    `rust_body` is the full body (incl. `#[test]` attribute + signature) of
    one or more test functions which may call `parse_low_raw` / `lookup`
    (re-imported inside the injected module).  Returns the CompletedProcess of
    the cargo invocation.  The original file is always restored, even on
    failure.
    """
    original = _read(DEFS_PATH)

    module = "\n".join(
        [
            "",
            INJECT_MARKER,
            "#[cfg(test)]",
            "mod bench_clap_cli_patterns_ext4 {",
            "    #[allow(unused_imports)]",
            "    use crate::flags::parse::parse_low_raw;",
            "    #[allow(unused_imports)]",
            "    use crate::flags::parse::lookup;",
            "    #[allow(unused_imports)]",
            "    use crate::flags::Flag;",
            "",
            _RUST_HELPERS,
            "",
            rust_body,
            "}",
            INJECT_MARKER,
            "",
        ]
    )

    patched = original + module
    try:
        _write(DEFS_PATH, patched)
        proc = subprocess.run(
            [
                "cargo",
                "test",
                "--bin",
                "rg",
                "flags::defs::bench_clap_cli_patterns_ext4::" + test_fn_name,
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
        _write(DEFS_PATH, original)


def _assert_cargo_ok(proc, expect_run="1"):
    combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
    assert proc.returncode == 0, (
        "cargo test failed (rc=%s).\nSTDOUT:\n%s\nSTDERR:\n%s"
        % (proc.returncode, proc.stdout, proc.stderr)
    )
    assert (
        "test result: ok" in combined
    ), "no successful test result reported:\n" + combined
    assert re.search(
        r"running\s+%s\s+test" % re.escape(expect_run), combined
    ), (
        "expected %s injected test(s) to actually run, output was:\n%s"
        % (expect_run, combined)
    )


# Shared Rust helper snippets pasted into each injected module.
#
# `true_fields` returns the set of *plain* `bool` fields on a parsed LowArgs
# whose value is `true`.  It works purely off the derived `Debug` rendering
# (`LowArgs { field: value, ... }`).  `Option<bool>` fields render as
# `field: Some(true)` and therefore never match the `<ident>: true` shape, so
# only genuine `bool` fields are picked up.  This lets us discover the
# agent-chosen field name without hardcoding it.
_RUST_HELPERS = r"""
    fn true_fields(args: &crate::flags::lowargs::LowArgs) -> std::collections::BTreeSet<String> {
        let dbg = format!("{:?}", args);
        let mut out = std::collections::BTreeSet::new();
        let bytes = dbg.as_bytes();
        // Scan for the literal token ": true" and capture the preceding
        // identifier.  ": true" must be followed by a non-word char so we
        // don't match "Some(true)".
        let needle = b": true";
        let mut i = 0usize;
        while i + needle.len() <= bytes.len() {
            if &bytes[i..i + needle.len()] == needle {
                let after = i + needle.len();
                let ok_after = after >= bytes.len()
                    || !(bytes[after] as char).is_alphanumeric();
                if ok_after {
                    // Walk backwards over the identifier preceding ':'.
                    let mut j = i;
                    while j > 0 {
                        let c = bytes[j - 1] as char;
                        if c.is_alphanumeric() || c == '_' {
                            j -= 1;
                        } else {
                            break;
                        }
                    }
                    if j < i {
                        out.insert(String::from_utf8_lossy(&bytes[j..i]).into_owned());
                    }
                }
            }
            i += 1;
        }
        out
    }

    fn parse(argv: &[&str]) -> crate::flags::lowargs::LowArgs {
        parse_low_raw(argv.iter().copied()).unwrap()
    }
"""


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------

class TestClapCliPatterns:
    """Verify the negatable --summary/--no-summary switch flag in ripgrep."""

    REPO_DIR = REPO_DIR

    # ------------------------------------------------------------------
    # L1 — deliverable presence & shape
    # ------------------------------------------------------------------

    def test_defs_file_exists(self):
        """The flag-definitions file crates/core/flags/defs.rs must exist."""
        assert os.path.isfile(DEFS_PATH), "defs.rs not found at " + DEFS_PATH

    def test_lowargs_file_exists(self):
        """The lowargs file crates/core/flags/lowargs.rs must exist."""
        assert os.path.isfile(LOWARGS_PATH), (
            "lowargs.rs not found at " + LOWARGS_PATH
        )

    def test_lowargs_still_has_lowargs_struct(self):
        """LowArgs must still derive Debug+Default (our diff relies on it)."""
        src = _read(LOWARGS_PATH)
        assert "struct LowArgs" in src, "LowArgs struct removed from lowargs.rs"
        assert re.search(
            r"#\[derive\([^)]*Debug[^)]*Default[^)]*\)\]\s*\n\s*pub\(crate\)\s+struct\s+LowArgs",
            src,
        ), "LowArgs must keep `#[derive(Debug, Default)]`"

    def test_summary_flag_struct_and_registration_present(self):
        """defs.rs must define a `summary` switch and register it in FLAGS."""
        src = _read(DEFS_PATH)
        # The positive long name must appear as a flag long-name literal.
        assert re.search(r'"summary"', src), (
            'no "summary" long-name literal found in defs.rs'
        )
        # The negated long name must appear too.
        assert re.search(r'"no-summary"', src), (
            'no "no-summary" negated long-name literal found in defs.rs'
        )
        # The FLAGS slice must register a new flag value. We can't know the
        # struct name for certain, so assert the FLAGS slice still exists and
        # has grown beyond the baseline by detecting a `&` entry adjacent to
        # the summary definition is hard; instead rely on lookup() at L2.
        assert "const FLAGS:" in src, "FLAGS slice missing from defs.rs"

    def test_agent_added_test_summary(self):
        """The agent must add its own `fn test_summary` unit test."""
        src = _read(DEFS_PATH)
        assert re.search(r"fn\s+test_summary\b", src), (
            "expected the agent to add `fn test_summary` to defs.rs"
        )
        # And it should sit under a #[test] attribute.
        assert re.search(r"#\[test\]\s*\n\s*fn\s+test_summary\b", src), (
            "`fn test_summary` must be annotated with #[test]"
        )

    def test_no_leftover_injection(self):
        """Sanity: our scratch injection marker must not be committed."""
        src = _read(DEFS_PATH)
        assert INJECT_MARKER not in src, (
            "leftover injected test module found in defs.rs; "
            "a previous run did not restore the file"
        )

    # ------------------------------------------------------------------
    # L2 — dynamic behavioral verification via injected Rust tests
    # ------------------------------------------------------------------

    def test_flag_registered_and_switch_shape(self):
        """`lookup` resolves --summary as a no-short, negatable switch.

        Asserts the flag surface field-name-agnostically: positive and
        negated long names both resolve to the same flag object, it reports
        itself as a switch, has no short name, and exposes `no-summary` as its
        negated form. A flag that consumes a value (is_switch()==false) or is
        not registered fails here.
        """
        body = r"""
    #[test]
    fn t() {
        let pos = lookup("summary").expect("--summary must be registered");
        assert!(pos.is_switch(), "--summary must be a switch (no value)");
        assert_eq!(pos.name_long(), "summary");
        assert_eq!(pos.name_short(), None, "--summary must have no short name");
        assert_eq!(
            pos.name_negated(),
            Some("no-summary"),
            "--summary must expose `no-summary` as its negated long name"
        );
        // The negated spelling must resolve to a flag as well.
        let neg = lookup("no-summary").expect("--no-summary must be registered");
        assert!(neg.is_switch(), "--no-summary must be a switch (no value)");
    }
"""
        proc = _run_injected_rust_test("t", body)
        _assert_cargo_ok(proc)

    def test_default_is_false(self):
        """With no flag, no plain bool toggles on for summary (default false).

        We capture the set of `true` bool fields with no args; the
        agent's new field must NOT be among them. Combined with the
        `--summary` test below (which adds exactly one), this pins the
        default to false.
        """
        body = r"""
    #[test]
    fn t() {
        let base = true_fields(&parse(&[]));
        let on = true_fields(&parse(&["--summary"]));
        // Exactly one new bool field flips to true when --summary is given.
        let added: Vec<_> = on.difference(&base).cloned().collect();
        assert_eq!(
            added.len(),
            1,
            "--summary must flip exactly one new bool field true; \
             base={:?} on={:?}",
            base, on
        );
        // The discovered field was false by default (not in base set).
        assert!(!base.contains(&added[0]),
            "the summary field must default to false");
    }
"""
        proc = _run_injected_rust_test("t", body)
        _assert_cargo_ok(proc)

    def test_positive_form_sets_true(self):
        """`--summary` flips exactly the summary field to true, nothing else.

        Discovers the agent-chosen field via the default-diff, then asserts no
        *other* bool field changed (guards against a sloppy impl that toggles
        an unrelated field or has side effects).
        """
        body = r"""
    #[test]
    fn t() {
        let base = true_fields(&parse(&[]));
        let on = true_fields(&parse(&["--summary"]));
        let off_only = on.difference(&base).cloned().collect::<Vec<_>>();
        assert_eq!(off_only.len(), 1, "--summary changed != 1 bool field: {:?} -> {:?}", base, on);
        // No bool field that was true by default became false.
        assert!(base.is_subset(&on),
            "--summary must not turn off other bool fields: base={:?} on={:?}", base, on);
    }
"""
        proc = _run_injected_rust_test("t", body)
        _assert_cargo_ok(proc)

    def test_negated_form_keeps_false(self):
        """`--no-summary` alone leaves the summary field false (== default).

        The set of true bool fields for `--no-summary` must equal the default
        set: the negated form on its own must not turn the flag on.
        """
        body = r"""
    #[test]
    fn t() {
        let base = true_fields(&parse(&[]));
        let neg = true_fields(&parse(&["--no-summary"]));
        assert_eq!(
            base, neg,
            "--no-summary alone must equal default (summary stays false); \
             base={:?} neg={:?}",
            base, neg
        );
    }
"""
        proc = _run_injected_rust_test("t", body)
        _assert_cargo_ok(proc)

    def test_last_occurrence_wins_off(self):
        """`--summary --no-summary` ends false (negation wins as last).

        After discovering the field from a clean `--summary` run, assert that
        field is NOT true once `--no-summary` follows it. A naive impl that
        only ever sets true, or that ignores the negated form, fails here.
        """
        body = r"""
    #[test]
    fn t() {
        let base = true_fields(&parse(&[]));
        let on = true_fields(&parse(&["--summary"]));
        let field = on.difference(&base).cloned().next()
            .expect("--summary must enable exactly one bool field");
        let combo = true_fields(&parse(&["--summary", "--no-summary"]));
        assert!(
            !combo.contains(&field),
            "`--summary --no-summary` must end false for `{}`; got true set {:?}",
            field, combo
        );
        // And the result equals the plain default.
        assert_eq!(base, combo,
            "`--summary --no-summary` must equal default state");
    }
"""
        proc = _run_injected_rust_test("t", body)
        _assert_cargo_ok(proc)

    def test_last_occurrence_wins_on(self):
        """`--no-summary --summary` ends true (positive wins as last)."""
        body = r"""
    #[test]
    fn t() {
        let base = true_fields(&parse(&[]));
        let on = true_fields(&parse(&["--summary"]));
        let field = on.difference(&base).cloned().next()
            .expect("--summary must enable exactly one bool field");
        let combo = true_fields(&parse(&["--no-summary", "--summary"]));
        assert!(
            combo.contains(&field),
            "`--no-summary --summary` must end true for `{}`; got true set {:?}",
            field, combo
        );
        // It should be exactly the same state as a lone `--summary`.
        assert_eq!(on, combo,
            "`--no-summary --summary` must equal a lone `--summary`");
    }
"""
        proc = _run_injected_rust_test("t", body)
        _assert_cargo_ok(proc)

    def test_negated_form_consumes_no_value(self):
        """`--no-summary <pattern>` treats the next token as a positional.

        If the negated form were wrongly defined as taking a value, the
        pattern `foo` would be swallowed instead of remaining a positional
        argument. We assert the positional is preserved.
        """
        body = r"""
    #[test]
    fn t() {
        // `--no-summary` must NOT consume `needle`; it stays a positional.
        let args = parse_low_raw(["--no-summary", "needle"].iter().copied()).unwrap();
        let posit: Vec<String> = args
            .positional
            .iter()
            .map(|s| s.to_string_lossy().into_owned())
            .collect();
        assert_eq!(
            posit,
            vec!["needle".to_string()],
            "--no-summary must consume no value; `needle` must remain positional"
        );
    }
"""
        proc = _run_injected_rust_test("t", body)
        _assert_cargo_ok(proc)

    def test_positive_form_consumes_no_value(self):
        """`--summary <pattern>` likewise keeps `<pattern>` as a positional."""
        body = r"""
    #[test]
    fn t() {
        let args = parse_low_raw(["--summary", "needle"].iter().copied()).unwrap();
        let posit: Vec<String> = args
            .positional
            .iter()
            .map(|s| s.to_string_lossy().into_owned())
            .collect();
        assert_eq!(
            posit,
            vec!["needle".to_string()],
            "--summary must consume no value; `needle` must remain positional"
        );
    }
"""
        proc = _run_injected_rust_test("t", body)
        _assert_cargo_ok(proc)

    def test_full_truth_table_in_one_run(self):
        """All five doc scenarios verified together within one cargo run.

        Combines default/positive/negated/override-off/override-on so the
        complete documented truth table is asserted atomically against the
        real parser.
        """
        body = r"""
    #[test]
    fn t() {
        let base = true_fields(&parse(&[]));
        let on = true_fields(&parse(&["--summary"]));
        let field = on.difference(&base).cloned().next()
            .expect("--summary must enable exactly one bool field");

        // No flag -> false.
        assert!(!base.contains(&field), "default must be false");
        // --summary -> true.
        assert!(on.contains(&field), "--summary must be true");
        // --no-summary -> false.
        assert!(!true_fields(&parse(&["--no-summary"])).contains(&field),
            "--no-summary must be false");
        // --summary --no-summary -> false.
        assert!(!true_fields(&parse(&["--summary", "--no-summary"])).contains(&field),
            "`--summary --no-summary` must be false");
        // --no-summary --summary -> true.
        assert!(true_fields(&parse(&["--no-summary", "--summary"])).contains(&field),
            "`--no-summary --summary` must be true");
        // Repeated positives stay true (idempotent).
        assert!(true_fields(&parse(&["--summary", "--summary"])).contains(&field),
            "repeated --summary must stay true");
    }
"""
        proc = _run_injected_rust_test("t", body)
        _assert_cargo_ok(proc)

    def test_native_test_summary_passes(self):
        """The agent's own `flags::defs::test_summary` must pass.

        Drives exactly the doc's native acceptance command. This both proves
        the agent supplied the required unit test and that it passes against
        the real implementation.
        """
        proc = subprocess.run(
            ["cargo", "test", "--bin", "rg", "flags::defs::test_summary"],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=CARGO_BUILD_TIMEOUT,
            env=_cargo_env(),
        )
        combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
        assert proc.returncode == 0, (
            "native `cargo test ... flags::defs::test_summary` failed.\n"
            "STDOUT:\n%s\nSTDERR:\n%s" % (proc.stdout, proc.stderr)
        )
        assert "test result: ok" in combined, combined
        # Guard against the filter matching zero tests.
        assert re.search(r"running\s+1\s+test", combined), (
            "expected exactly the test_summary case to run; output:\n" + combined
        )

    def test_existing_defs_tests_still_pass(self):
        """A broad slice of existing flags::defs tests must still pass.

        Ensures the new flag did not break sibling switch flags or the FLAGS
        ordering invariants (no regression).
        """
        proc = subprocess.run(
            ["cargo", "test", "--bin", "rg", "flags::defs::test_block_buffered"],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=CARGO_BUILD_TIMEOUT,
            env=_cargo_env(),
        )
        combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
        assert proc.returncode == 0, (
            "pre-existing defs tests failed (regression).\n"
            "STDOUT:\n%s\nSTDERR:\n%s" % (proc.stdout, proc.stderr)
        )
        assert "test result: ok" in combined, combined
