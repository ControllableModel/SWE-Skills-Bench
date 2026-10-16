"""
Test for 'clap-cli-patterns' skill (variant ext10) — Add a `complete-elvish`
target to ripgrep's `--generate` flag.

The task adds a new generate target for the Elvish shell:
  * a new `GenerateMode` variant in `crates/core/flags/lowargs.rs`,
  * acceptance of a new `complete-elvish` KIND in the `--generate` flag in
    `crates/core/flags/defs.rs`, mapping it onto the new mode,
  * the new value appended to the flag's documented `doc_choices()` list while
    keeping the original five (`man`, `complete-bash`, `complete-zsh`,
    `complete-fish`, `complete-powershell`) intact and in order,
  * preserved override semantics (later `--generate` wins; a later
    search-selecting flag still overrides a generate mode),
  * an unrecognized KIND (e.g. `complete-elv`, `complete-elvis`) still errors.

The native acceptance command is:  cargo test --bin rg flags::defs::test_generate

Because the flag plumbing (`parse_low_raw`, the `Mode`/`GenerateMode` enums and
the private `Generate` struct) all live INSIDE the `rg` binary crate and are not
public, this test verifies the agent's work *discriminatively* by injecting its
own `#[cfg(test)]` module into `defs.rs` that drives the real
`crate::flags::parse::parse_low_raw` function and inspects the real
`Generate::doc_choices()` output. It compiles and runs through the native
toolchain, then restores the original file.

A naive solution (e.g. one that maps `complete-elvish` onto an *existing*
variant such as `CompleteFish`, or that drops/reorders the original choices, or
that fails to error on a misspelling) is caught by the injected Rust assertions
below.

L1 cases check the deliverable files are present, minimally well-formed, and
that the agent grew the native `test_generate` test. L2 cases compile and run
real Rust assertions exercising the new behavior end to end, plus the native
acceptance command itself.
"""

import os
import re
import subprocess

import pytest


REPO_DIR = "/workspace/ripgrep"
DEFS_REL = os.path.join("crates", "core", "flags", "defs.rs")
LOWARGS_REL = os.path.join("crates", "core", "flags", "lowargs.rs")
DEFS_PATH = os.path.join(REPO_DIR, DEFS_REL)
LOWARGS_PATH = os.path.join(REPO_DIR, LOWARGS_REL)

# Unique marker so our injected module is easy to identify / strip out again.
INJECT_MARKER = "// __BENCH_CLAP_CLI_PATTERNS_EXT10_INJECTED__"

CARGO_BUILD_TIMEOUT = 900


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
    """Inject a Rust test fn into defs.rs, run it via cargo, restore file.

    `rust_body` is the full body (including `#[test]` + signature) of one test
    function. It runs in a module that has `parse_low_raw`, the `Mode` /
    `GenerateMode` / `SearchMode` enums, the private `Generate` flag struct and
    the `Flag` trait in scope.

    Returns the CompletedProcess of the cargo invocation. The original file is
    always restored, even on failure.
    """
    original = _read(DEFS_PATH)

    module = "\n".join(
        [
            "",
            INJECT_MARKER,
            "#[cfg(test)]",
            "mod bench_clap_cli_patterns_ext10 {",
            "    #[allow(unused_imports)]",
            "    use crate::flags::parse::parse_low_raw;",
            "    #[allow(unused_imports)]",
            "    use crate::flags::lowargs::{Mode, GenerateMode, SearchMode};",
            "    #[allow(unused_imports)]",
            "    use crate::flags::Flag;",
            "    #[allow(unused_imports)]",
            "    use super::Generate;",
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
                "flags::defs::bench_clap_cli_patterns_ext10::" + test_fn_name,
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


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------

class TestClapCliPatterns:
    """Verify the new `complete-elvish` --generate target in ripgrep."""

    REPO_DIR = REPO_DIR

    # ------------------------------------------------------------------
    # L1 — deliverable presence & shape
    # ------------------------------------------------------------------

    def test_deliverable_files_exist(self):
        """Both flag files (lowargs.rs and defs.rs) must still be present."""
        assert os.path.isfile(LOWARGS_PATH), "lowargs.rs missing at " + LOWARGS_PATH
        assert os.path.isfile(DEFS_PATH), "defs.rs missing at " + DEFS_PATH

    def test_generate_mode_enum_grew_a_variant(self):
        """`GenerateMode` must gain a new variant beyond the original five.

        The original enum has exactly Man, CompleteBash, CompleteZsh,
        CompleteFish, CompletePowerShell. The agent must ADD a new variant
        (it must not merely reuse one of those names).
        """
        src = _read(LOWARGS_PATH)
        # Isolate the GenerateMode enum body.
        m = re.search(
            r"enum\s+GenerateMode\s*\{(.*?)\}", src, re.DOTALL
        )
        assert m, "GenerateMode enum not found in lowargs.rs"
        body = m.group(1)
        # The original variants must all still be present.
        for orig in (
            "Man",
            "CompleteBash",
            "CompleteZsh",
            "CompleteFish",
            "CompletePowerShell",
        ):
            assert re.search(r"\b%s\b" % orig, body), (
                "original GenerateMode variant %s missing" % orig
            )
        # Count distinct top-level variant identifiers (lines ending in `,`).
        variants = re.findall(r"^\s*([A-Z][A-Za-z0-9]*)\s*,", body, re.MULTILINE)
        assert len(set(variants)) >= 6, (
            "expected a NEW GenerateMode variant to be added; found variants: %r"
            % variants
        )

    def test_defs_accepts_complete_elvish_token(self):
        """defs.rs must mention the literal `complete-elvish` choice token."""
        src = _read(DEFS_PATH)
        assert "complete-elvish" in src, (
            "the `complete-elvish` value is not referenced in defs.rs"
        )

    def test_native_test_was_extended(self):
        """The native `test_generate` fn must reference complete-elvish.

        The acceptance criteria require the existing #[test] to be extended to
        cover the new target; a stub that leaves the test untouched fails here.
        """
        src = _read(DEFS_PATH)
        m = re.search(r"fn\s+test_generate\s*\(\s*\)\s*\{(.*?)\n\}", src, re.DOTALL)
        assert m, "test_generate function not found in defs.rs"
        body = m.group(1)
        assert "complete-elvish" in body, (
            "test_generate was not extended to cover complete-elvish"
        )

    def test_no_leftover_injection(self):
        """Sanity: our scratch injection marker must not be committed."""
        for path in (DEFS_PATH, LOWARGS_PATH):
            src = _read(path)
            assert INJECT_MARKER not in src, (
                "leftover injected test module found in %s; a previous run "
                "did not restore the file" % path
            )

    # ------------------------------------------------------------------
    # L2 — dynamic behavioral verification via the native toolchain
    # ------------------------------------------------------------------

    def test_native_test_generate_passes(self):
        """The native acceptance command must pass: test_generate."""
        proc = subprocess.run(
            ["cargo", "test", "--bin", "rg", "flags::defs::test_generate"],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=CARGO_BUILD_TIMEOUT,
            env=_cargo_env(),
        )
        combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
        assert proc.returncode == 0, (
            "native test_generate failed.\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )
        assert "test result: ok" in combined, combined
        # Make sure the test actually ran (not filtered to zero).
        assert re.search(r"running\s+1\s+test", combined), combined

    def test_complete_elvish_selects_a_new_generate_mode(self):
        """`--generate complete-elvish` -> a Generate mode distinct from all five.

        A naive impl that maps complete-elvish onto an existing variant (e.g.
        CompleteFish) is caught: the resulting mode must NOT equal any of the
        five pre-existing generate modes, yet must be a Generate(_) mode.
        """
        body = r"""
    #[test]
    fn t() {
        let args = parse_low_raw(["--generate", "complete-elvish"]).unwrap();
        // Must be a generate mode.
        let gm = match args.mode {
            Mode::Generate(gm) => gm,
            other => panic!("expected Mode::Generate, got {:?}", other),
        };
        // Must be a NEW variant, distinct from every pre-existing one.
        assert_ne!(gm, GenerateMode::Man);
        assert_ne!(gm, GenerateMode::CompleteBash);
        assert_ne!(gm, GenerateMode::CompleteZsh);
        assert_ne!(gm, GenerateMode::CompleteFish);
        assert_ne!(gm, GenerateMode::CompletePowerShell);
    }
"""
        proc = _run_injected_rust_test("t", body)
        _assert_cargo_ok(proc)

    def test_existing_targets_unchanged(self):
        """All five pre-existing targets still map to their original modes."""
        body = r"""
    #[test]
    fn t() {
        let a = parse_low_raw(["--generate", "man"]).unwrap();
        assert_eq!(Mode::Generate(GenerateMode::Man), a.mode);

        let a = parse_low_raw(["--generate", "complete-bash"]).unwrap();
        assert_eq!(Mode::Generate(GenerateMode::CompleteBash), a.mode);

        let a = parse_low_raw(["--generate", "complete-zsh"]).unwrap();
        assert_eq!(Mode::Generate(GenerateMode::CompleteZsh), a.mode);

        let a = parse_low_raw(["--generate", "complete-fish"]).unwrap();
        assert_eq!(Mode::Generate(GenerateMode::CompleteFish), a.mode);

        let a = parse_low_raw(["--generate", "complete-powershell"]).unwrap();
        assert_eq!(Mode::Generate(GenerateMode::CompletePowerShell), a.mode);
    }
"""
        proc = _run_injected_rust_test("t", body)
        _assert_cargo_ok(proc)

    def test_elvish_is_distinct_from_each_existing(self):
        """complete-elvish must differ from EVERY existing target individually.

        Drives each existing target and complete-elvish through the parser and
        asserts elvish's mode is not equal to any of them. Catches a mapping
        that aliases elvish onto, say, fish or powershell.
        """
        body = r"""
    #[test]
    fn t() {
        let elv = match parse_low_raw(["--generate", "complete-elvish"]).unwrap().mode {
            Mode::Generate(gm) => gm,
            other => panic!("elvish not a generate mode: {:?}", other),
        };
        for kind in ["man", "complete-bash", "complete-zsh", "complete-fish", "complete-powershell"] {
            let other = match parse_low_raw(["--generate", kind]).unwrap().mode {
                Mode::Generate(gm) => gm,
                m => panic!("{} not a generate mode: {:?}", kind, m),
            };
            assert_ne!(elv, other, "complete-elvish must differ from {}", kind);
        }
    }
"""
        proc = _run_injected_rust_test("t", body)
        _assert_cargo_ok(proc)

    def test_later_generate_wins(self):
        """A later `--generate` value replaces an earlier one (both directions)."""
        body = r"""
    #[test]
    fn t() {
        // earlier bash, later elvish -> elvish wins (a generate mode, not bash)
        let a = parse_low_raw(["--generate", "complete-bash", "--generate=complete-elvish"]).unwrap();
        let gm = match a.mode {
            Mode::Generate(gm) => gm,
            other => panic!("expected generate, got {:?}", other),
        };
        assert_ne!(gm, GenerateMode::CompleteBash, "later complete-elvish must override bash");

        // earlier elvish, later man -> man wins (proves elvish is not sticky)
        let a = parse_low_raw(["--generate", "complete-elvish", "--generate=man"]).unwrap();
        assert_eq!(Mode::Generate(GenerateMode::Man), a.mode);
    }
"""
        proc = _run_injected_rust_test("t", body)
        _assert_cargo_ok(proc)

    def test_search_flag_overrides_elvish(self):
        """A later search-selecting flag overrides the generate-elvish mode."""
        body = r"""
    #[test]
    fn t() {
        // -l selects FilesWithMatches; it must override a prior generate mode.
        let a = parse_low_raw(["--generate", "complete-elvish", "-l"]).unwrap();
        assert_eq!(Mode::Search(SearchMode::FilesWithMatches), a.mode);
    }
"""
        proc = _run_injected_rust_test("t", body)
        _assert_cargo_ok(proc)

    def test_unrecognized_kinds_error(self):
        """Misspellings (complete-elv / complete-elvis) must error out.

        Only the exact spelling selects the target; a too-loose match that
        accepts a prefix or a near-miss is caught here.
        """
        body = r"""
    #[test]
    fn t() {
        assert!(
            parse_low_raw(["--generate", "complete-elv"]).is_err(),
            "complete-elv must be rejected"
        );
        assert!(
            parse_low_raw(["--generate", "complete-elvis"]).is_err(),
            "complete-elvis must be rejected"
        );
        assert!(
            parse_low_raw(["--generate", "elvish"]).is_err(),
            "bare 'elvish' must be rejected"
        );
        // And the exact spelling is accepted (a generate mode).
        assert!(matches!(
            parse_low_raw(["--generate", "complete-elvish"]).unwrap().mode,
            Mode::Generate(_)
        ));
    }
"""
        proc = _run_injected_rust_test("t", body)
        _assert_cargo_ok(proc)

    def test_doc_choices_appends_elvish_in_order(self):
        """`Generate::doc_choices()` must list the original five then elvish.

        The original order must be preserved and complete-elvish appended.
        This inspects the *real* trait output, so a doc list that is reordered,
        missing entries, or missing the new choice fails.
        """
        body = r"""
    #[test]
    fn t() {
        let choices = Generate.doc_choices();
        // The first five must be exactly the original list in the original order.
        let expected_prefix = [
            "man",
            "complete-bash",
            "complete-zsh",
            "complete-fish",
            "complete-powershell",
        ];
        assert!(
            choices.len() >= 6,
            "expected at least 6 choices, got {:?}",
            choices
        );
        for (i, want) in expected_prefix.iter().enumerate() {
            assert_eq!(
                &choices[i], want,
                "choice at position {} changed: got {:?}, want {}",
                i, choices[i], want
            );
        }
        // complete-elvish must be present (and, per the spec, appended).
        assert!(
            choices.contains(&"complete-elvish"),
            "doc_choices missing complete-elvish: {:?}",
            choices
        );
        assert_eq!(
            choices[5], "complete-elvish",
            "complete-elvish must be appended after the original five: {:?}",
            choices
        );
    }
"""
        proc = _run_injected_rust_test("t", body)
        _assert_cargo_ok(proc)

    def test_no_generate_flag_is_default_search(self):
        """Without --generate the default mode is unchanged (Standard search).

        Guards against an agent accidentally making elvish (or any generate
        mode) the default.
        """
        body = r"""
    #[test]
    fn t() {
        let a = parse_low_raw(None::<&str>).unwrap();
        assert_eq!(Mode::Search(SearchMode::Standard), a.mode);
    }
"""
        proc = _run_injected_rust_test("t", body)
        _assert_cargo_ok(proc)
