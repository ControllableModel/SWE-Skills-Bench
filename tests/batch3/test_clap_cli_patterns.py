"""
Test for 'clap-cli-patterns' skill (variant ext3) — a new enumerated-choice
flag `--path-style` for ripgrep.

The task adds an enumerated CLI flag to ripgrep's hand-rolled clap-style flag
system (crates/core/flags/defs.rs + crates/core/flags/lowargs.rs):

  * long name `path-style`, value placeholder `STYLE`;
  * the *only* accepted values are exactly `absolute`, `relative`, `basename`;
  * those three values must be advertised via `doc_choices()` so help /
    completions can enumerate them;
  * a recognized value maps to a distinct variant of a new enum stored on
    `LowArgs`; the default (flag absent) is the `relative` variant;
  * an unrecognized value (e.g. `full`, empty string, or the wrong-case
    `Absolute`) must make parsing FAIL with a message that names the bad value
    — never a silent fallback to the default;
  * the flag is registered in the global `FLAGS` slice so the parser sees it;
  * when supplied multiple times, the last valid occurrence wins.

The native acceptance command from the requirement doc is:
    cargo test --bin rg flags::defs::test_path_style

Verification strategy (discriminative + dynamic, mirroring the ext1 harness):
We do NOT trust the agent's own `test_path_style`. Instead we inject our OWN
`#[cfg(test)]` test fn into defs.rs that drives the real, crate-private
`parse_low_raw` parser and the real `lookup()` flag registry, then run it
through the native cargo toolchain and restore the file afterwards.

Because we cannot know the exact enum/field identifiers the agent will choose,
the injected Rust asserts on observable behavior that is name-independent:
  * `lookup("path-style")` must resolve (proves FLAGS registration) and its
    `doc_choices()` must equal exactly the three documented values, in some
    order;
  * the *whole* `LowArgs` `Debug` rendering must differ between inputs — the
    default and `absolute` and `basename` produce three distinguishable
    variant tokens, so a naive impl that ignores the value (always default) is
    caught;
  * `--path-style full` / empty / `Absolute` must each return `Err` with the
    offending value named.

A stub that hardcodes one variant, skips registration, omits doc_choices, or
silently defaults on bad input fails these assertions.

L1 cases check the deliverable files exist and are minimally well-formed and
that the agent left a `test_path_style` of its own. L2 cases compile and run
real Rust assertions exercising the new behavior end to end.
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
INJECT_MARKER = "// __BENCH_CLAP_CLI_PATTERNS_EXT3_INJECTED__"

CARGO_BUILD_TIMEOUT = 600

CHOICES = ("absolute", "relative", "basename")


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
    # Determinism: never let a stray RUSTFLAGS / config pull in randomness.
    env.setdefault("RUST_BACKTRACE", "1")
    return env


def _run_injected_rust_test(test_fn_name, rust_body):
    """Inject a Rust test fn into defs.rs, run it via cargo, restore the file.

    `rust_body` is one or more `#[test]` functions. They run inside a child
    module of `crate::flags::defs`, so they may reach:
      * `super::parse_low_raw` is NOT in scope, but the crate path
        `crate::flags::parse::parse_low_raw` is (it is pub(crate));
      * `crate::flags::lookup` (pub(super) within the flags module);
      * the `Flag` trait (in scope as `super::Flag`).

    Returns the CompletedProcess of the cargo invocation. The original file is
    always restored, even on failure.
    """
    original = _read(DEFS_PATH)

    module = "\n".join(
        [
            "",
            INJECT_MARKER,
            "#[cfg(test)]",
            "mod bench_clap_cli_patterns_ext3 {",
            "    #[allow(unused_imports)]",
            "    use crate::flags::parse::parse_low_raw;",
            "    #[allow(unused_imports)]",
            "    use crate::flags::lookup;",
            "    #[allow(unused_imports)]",
            "    use super::Flag;",
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
                "flags::defs::bench_clap_cli_patterns_ext3::" + test_fn_name,
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
    assert "test result: ok" in combined, (
        "no successful test result reported:\n" + combined
    )
    assert re.search(
        r"running\s+%s\s+test" % re.escape(expect_run), combined
    ), (
        "expected %s injected test(s) to actually run, output was:\n%s"
        % (expect_run, combined)
    )


# Shared Rust helper snippets pasted into each injected module.
# `style_token(args)` extracts, from the full LowArgs Debug rendering, which of
# the three expected variant tokens is present. This is name-independent: it
# does not assume the field name, only that a recognized value is stored as one
# of the conceptual variants Absolute / Relative / Basename.
_RUST_HELPERS = r"""
    fn dbg_of(args: &impl std::fmt::Debug) -> String {
        format!("{:?}", args)
    }

    // Returns the set of expected variant tokens that appear in the Debug of
    // the parsed LowArgs. Variant identifiers in Rust are PascalCase, so we
    // look for `Absolute` / `Relative` / `Basename` as whole-ish words.
    fn present_variants(dbg: &str) -> Vec<&'static str> {
        let mut out = Vec::new();
        for tok in ["Absolute", "Relative", "Basename"] {
            if dbg.contains(tok) {
                out.push(tok);
            }
        }
        out
    }
"""


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------

class TestClapCliPatterns:
    """Verify the new enumerated `--path-style` flag end to end."""

    REPO_DIR = REPO_DIR

    # ------------------------------------------------------------------
    # L1 — deliverable presence & shape
    # ------------------------------------------------------------------

    def test_defs_file_exists(self):
        """The flag-definitions file crates/core/flags/defs.rs must exist."""
        assert os.path.isfile(DEFS_PATH), "defs.rs not found at " + DEFS_PATH

    def test_lowargs_file_exists(self):
        """The low-args state file crates/core/flags/lowargs.rs must exist."""
        assert os.path.isfile(LOWARGS_PATH), (
            "lowargs.rs not found at " + LOWARGS_PATH
        )

    def test_flag_long_name_mentioned(self):
        """defs.rs must reference the `path-style` long name and STYLE var."""
        src = _read(DEFS_PATH)
        assert "path-style" in src, (
            "the long flag name 'path-style' is not present in defs.rs"
        )
        # The value placeholder for a value-taking flag.
        assert "STYLE" in src, (
            "the value placeholder 'STYLE' is not present in defs.rs"
        )

    def test_flags_slice_still_present(self):
        """The global FLAGS registry slice must still exist in defs.rs."""
        src = _read(DEFS_PATH)
        assert re.search(r"FLAGS\s*:\s*&\[\s*&dyn\s+Flag\s*\]", src), (
            "the `FLAGS: &[&dyn Flag]` registry slice is missing from defs.rs"
        )

    def test_agent_added_path_style_test(self):
        """The agent must add its own `test_path_style` unit test in defs.rs."""
        src = _read(DEFS_PATH)
        assert "fn test_path_style" in src, (
            "expected an agent-authored `fn test_path_style` in defs.rs "
            "(the native acceptance command targets it)"
        )

    def test_lowargs_grew_an_enum_and_field(self):
        """lowargs.rs should declare a new path-style enum + a field for it."""
        src = _read(LOWARGS_PATH)
        # A new enum type whose name relates to path style. We accept any enum
        # but require at least the three conceptual variants to be present
        # somewhere in lowargs.rs as PascalCase identifiers.
        for variant in ("Absolute", "Relative", "Basename"):
            assert variant in src, (
                "expected the path-style enum variant %r in lowargs.rs"
                % variant
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
    # L2 — dynamic behavioral verification via injected Rust tests
    # ------------------------------------------------------------------

    def test_native_agent_test_passes(self):
        """The agent's own native acceptance test must pass.

        Drives exactly the requirement doc's command:
            cargo test --bin rg flags::defs::test_path_style
        """
        proc = subprocess.run(
            ["cargo", "test", "--bin", "rg", "flags::defs::test_path_style"],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=CARGO_BUILD_TIMEOUT,
            env=_cargo_env(),
        )
        combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
        assert proc.returncode == 0, (
            "native test_path_style failed.\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )
        assert "test result: ok" in combined, combined
        # Guard against the filter matching nothing (e.g. test renamed away).
        assert re.search(r"running\s+1\s+test", combined), (
            "expected exactly the test_path_style test to run; output:\n"
            + combined
        )

    def test_flag_registered_and_choices_exact(self):
        """`lookup("path-style")` resolves and exposes exactly the 3 choices.

        Proves FLAGS registration (else lookup returns None) and that
        doc_choices() enumerates exactly absolute/relative/basename.
        """
        body = _RUST_HELPERS + r"""
    #[test]
    fn t() {
        let flag = lookup("path-style")
            .expect("`--path-style` is not registered in FLAGS");
        assert_eq!(flag.name_long(), "path-style");
        let mut choices: Vec<&str> = flag.doc_choices().to_vec();
        choices.sort_unstable();
        let mut want = vec!["absolute", "basename", "relative"];
        want.sort_unstable();
        assert_eq!(
            choices, want,
            "doc_choices() must be exactly the three documented values"
        );
    }
"""
        proc = _run_injected_rust_test("t", body)
        _assert_cargo_ok(proc)

    def test_default_is_relative(self):
        """With no flag, the stored style is the `relative` default variant.

        Discriminative: the default Debug must contain `Relative` and must NOT
        contain `Absolute` or `Basename` (a stub defaulting to Absolute fails).
        """
        body = _RUST_HELPERS + r"""
    #[test]
    fn t() {
        let args = parse_low_raw(None::<&str>).unwrap();
        let dbg = dbg_of(&args);
        let present = present_variants(&dbg);
        assert!(
            present.contains(&"Relative"),
            "default LowArgs must store the Relative path-style variant; \
             Debug was:\n{}",
            dbg
        );
        assert!(
            !present.contains(&"Absolute") && !present.contains(&"Basename"),
            "default must be Relative only, but Debug also showed {:?}:\n{}",
            present, dbg
        );
    }
"""
        proc = _run_injected_rust_test("t", body)
        _assert_cargo_ok(proc)

    def test_explicit_absolute_separated_form(self):
        """`--path-style absolute` stores the Absolute variant (space form).

        Discriminative vs default: Absolute appears, Relative does not.
        """
        body = _RUST_HELPERS + r"""
    #[test]
    fn t() {
        let args = parse_low_raw(["--path-style", "absolute"]).unwrap();
        let dbg = dbg_of(&args);
        let present = present_variants(&dbg);
        assert!(
            present.contains(&"Absolute"),
            "expected Absolute to be stored; Debug:\n{}",
            dbg
        );
        assert!(
            !present.contains(&"Relative") && !present.contains(&"Basename"),
            "value was ignored or extra variants leaked: {:?}\n{}",
            present, dbg
        );
    }
"""
        proc = _run_injected_rust_test("t", body)
        _assert_cargo_ok(proc)

    def test_explicit_basename_equals_form(self):
        """`--path-style=basename` stores the Basename variant (= form)."""
        body = _RUST_HELPERS + r"""
    #[test]
    fn t() {
        let args = parse_low_raw(["--path-style=basename"]).unwrap();
        let dbg = dbg_of(&args);
        let present = present_variants(&dbg);
        assert!(
            present.contains(&"Basename"),
            "expected Basename to be stored; Debug:\n{}",
            dbg
        );
        assert!(
            !present.contains(&"Relative") && !present.contains(&"Absolute"),
            "value was ignored or extra variants leaked: {:?}\n{}",
            present, dbg
        );
    }
"""
        proc = _run_injected_rust_test("t", body)
        _assert_cargo_ok(proc)

    def test_three_values_are_distinguishable(self):
        """absolute / relative / basename each yield a DIFFERENT stored variant.

        This is the strongest anti-stub check: if the agent hardcodes a fixed
        variant or ignores the value, two of these three Debug renderings would
        collide. We require all three to be pairwise distinct in the variant
        token that appears.
        """
        body = _RUST_HELPERS + r"""
    #[test]
    fn t() {
        let a = present_variants(&dbg_of(
            &parse_low_raw(["--path-style=absolute"]).unwrap()));
        let r = present_variants(&dbg_of(
            &parse_low_raw(["--path-style=relative"]).unwrap()));
        let b = present_variants(&dbg_of(
            &parse_low_raw(["--path-style=basename"]).unwrap()));
        assert_eq!(a, vec!["Absolute"], "absolute -> {:?}", a);
        assert_eq!(r, vec!["Relative"], "relative -> {:?}", r);
        assert_eq!(b, vec!["Basename"], "basename -> {:?}", b);
        assert!(a != r && r != b && a != b,
            "the three styles must map to distinct variants");
    }
"""
        proc = _run_injected_rust_test("t", body)
        _assert_cargo_ok(proc)

    def test_last_valid_occurrence_wins(self):
        """`--path-style relative --path-style=absolute` -> Absolute wins."""
        body = _RUST_HELPERS + r"""
    #[test]
    fn t() {
        let args = parse_low_raw(
            ["--path-style", "relative", "--path-style=absolute"]
        ).unwrap();
        let present = present_variants(&dbg_of(&args));
        assert_eq!(
            present, vec!["Absolute"],
            "last valid occurrence must win (expected Absolute), got {:?}",
            present
        );
    }
"""
        proc = _run_injected_rust_test("t", body)
        _assert_cargo_ok(proc)

    def test_unknown_value_errors_and_names_it(self):
        """`--path-style full` must FAIL and the error must mention `full`.

        A silent fallback to the default (Ok with Relative) is rejected.
        """
        body = _RUST_HELPERS + r"""
    #[test]
    fn t() {
        let res = parse_low_raw(["--path-style", "full"]);
        let err = res.expect_err(
            "an unrecognized path style must be a parse error, not a default");
        let msg = format!("{:#}", err);
        assert!(
            msg.contains("full"),
            "the error must name the offending value 'full'; got: {}",
            msg
        );
    }
"""
        proc = _run_injected_rust_test("t", body)
        _assert_cargo_ok(proc)

    def test_empty_value_errors(self):
        """An empty `--path-style=` value must be rejected (not defaulted)."""
        body = _RUST_HELPERS + r"""
    #[test]
    fn t() {
        let res = parse_low_raw(["--path-style="]);
        assert!(
            res.is_err(),
            "an empty path style value must be a parse error, not a default"
        );
    }
"""
        proc = _run_injected_rust_test("t", body)
        _assert_cargo_ok(proc)

    def test_matching_is_case_sensitive(self):
        """`Absolute` (capitalized) must be rejected — matching is case-sensitive."""
        body = _RUST_HELPERS + r"""
    #[test]
    fn t() {
        let res = parse_low_raw(["--path-style", "Absolute"]);
        assert!(
            res.is_err(),
            "case-sensitive matching: 'Absolute' must NOT be accepted"
        );
        // And the lowercase form *is* accepted (control), proving the rejection
        // above is about case and not about the flag being broken entirely.
        let ok = parse_low_raw(["--path-style", "absolute"]);
        assert!(ok.is_ok(), "lowercase 'absolute' must be accepted");
    }
"""
        proc = _run_injected_rust_test("t", body)
        _assert_cargo_ok(proc)

    def test_existing_defs_tests_still_pass(self):
        """No regression: the pre-existing flag-definition tests still pass."""
        proc = subprocess.run(
            ["cargo", "test", "--bin", "rg", "flags::defs::test_engine"],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=CARGO_BUILD_TIMEOUT,
            env=_cargo_env(),
        )
        combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
        assert proc.returncode == 0, (
            "a pre-existing defs test (test_engine) regressed.\n"
            "STDOUT:\n%s\nSTDERR:\n%s" % (proc.stdout, proc.stderr)
        )
        assert "test result: ok" in combined, combined
