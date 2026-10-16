"""
Test for 'clap-cli-patterns' skill (variant ext2) — adding a new value-taking
numeric flag `--max-matches-per-line` to ripgrep's hand-rolled clap-style CLI.

Variant task summary
--------------------
ripgrep models every CLI flag as a unit struct implementing the `Flag` trait in
`crates/core/flags/defs.rs`, registers it in the global `FLAGS` slice, and
stores the parsed value on the `LowArgs` struct in
`crates/core/flags/lowargs.rs`. This task adds a brand-new flag:

  * long name `--max-matches-per-line`, taking a single `NUM` value,
  * no short name, no negated form,
  * stored on `LowArgs` as an `Option<u64>` (absent by default),
  * value parsed as a non-negative base-10 integer; non-numeric input
    (`abc`, `1.5`, empty) must error rather than silently default,
  * `0` is a legal, distinct value (NOT "absent"),
  * last occurrence wins on repetition,
  * registered in `FLAGS` so the standard parser recognizes it,
  * plus a `#[test] fn test_max_matches_per_line` covering every scenario.

Native acceptance command (from the doc):

    cargo test --bin rg flags::defs::test_max_matches_per_line

Verification strategy
---------------------
The flag's storage field name on `LowArgs` is not mandated by the doc, and the
real parser entry points are private to the `rg` binary crate. So rather than
trust the agent's own test (which a stub could weaken), this file injects its
OWN `#[cfg(test)]` module into `defs.rs` that drives the real, crate-private
`super::parse::parse_low_raw` parser end-to-end and asserts concrete results.

To stay agnostic to the chosen field name, the injected Rust harness diffs the
derived `Debug` representation of `LowArgs` before/after the flag is supplied
and asserts the *only* change is the expected `Option<u64>` value. This is
strongly discriminative: a naive implementation that ignores the value,
hardcodes a constant, treats `0` as absent, or fails to reject non-numeric
input will fail these assertions. The original file is always restored.

L1 cases check deliverable presence / shape (field declared as `Option<u64>`,
flag struct + `FLAGS` registration + agent's own `#[test]` present, no leftover
injection marker). L2 cases compile and run real Rust assertions through the
native toolchain.
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
INJECT_MARKER = "// __BENCH_CLAP_CLI_PATTERNS_EXT2_INJECTED__"

CARGO_BUILD_TIMEOUT = 900

LONG_NAME = "max-matches-per-line"


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
    # Deterministic, no colorized noise.
    env["CARGO_TERM_COLOR"] = "never"
    return env


# Shared Rust helpers: parse a `LowArgs` for given args, and extract the value
# of whichever `Option<u64>`-shaped field differs from the no-flag baseline.
#
# `parse_low_raw` is crate-private (`pub(crate)`) and reachable from defs.rs via
# `super::parse::parse_low_raw`. `LowArgs` derives `Debug`, so we diff field
# lines. We identify "the flag's field" as the line that differs between a
# baseline parse (flag absent) and a parse where the flag is supplied. We then
# return the inner text of that field so the caller can assert on it.
_RUST_HELPERS = r"""
    #[allow(unused_imports)]
    use super::parse::parse_low_raw;

    // Split a derived-Debug string of LowArgs into `field_name -> rendered`
    // pairs by scanning for `ident: ` at the start of comma-trimmed segments.
    // We avoid a full parser by capturing each "name: Some(NN)" / "name: None"
    // occurrence for Option<u64>-shaped fields via a regex-free scan.
    fn debug_of(args: &[&str]) -> String {
        let parsed = parse_low_raw(args.iter().copied()).expect("parse ok");
        format!("{:?}", parsed)
    }

    // Find the substring `: Some(<digits>)` or `: None` that belongs to the
    // changed field by locating, in `with`, every `Some(<digits>)` token whose
    // immediately-preceding field name does NOT appear identically in `base`.
    // Returns the matched Option value text, e.g. "Some(3)" / "Some(0)" / "None".
    //
    // Strategy: collect the set of `<ident>: Some(<num>)` tokens from each and
    // return the value text of the field whose (name, value) pair is present in
    // `with` but whose name maps to a different value (or None) in `base`.
    fn field_named_value(dump: &str, field: &str) -> Option<String> {
        // Look for `field: ` then read up to the next `, ` or ` }`.
        let needle = format!("{}: ", field);
        let start = dump.find(&needle)? + needle.len();
        let rest = &dump[start..];
        // Value ends at the first top-level ", " or " }". Option<u64> never
        // contains those, so a simple scan suffices.
        let mut end = rest.len();
        for (i, _) in rest.char_indices() {
            if rest[i..].starts_with(", ") || rest[i..].starts_with(" }") {
                end = i;
                break;
            }
        }
        Some(rest[..end].to_string())
    }

    // Discover the snake_case field name the agent used by diffing baseline vs
    // a `--max-matches-per-line 7` parse: the differing `: Some(7)` field is it.
    fn discover_field() -> String {
        let base = debug_of(&[]);
        let with = debug_of(&["--max-matches-per-line", "7"]);
        // Walk fields of `with`; find one rendered as Some(7) that is NOT Some(7)
        // in base.
        let mut idx = 0usize;
        while let Some(pos) = with[idx..].find(": Some(7)") {
            let abs = idx + pos;
            // Back up to the field name (letters/digits/underscore).
            let bytes = with.as_bytes();
            let mut s = abs;
            while s > 0 {
                let c = bytes[s - 1] as char;
                if c.is_ascii_alphanumeric() || c == '_' {
                    s -= 1;
                } else {
                    break;
                }
            }
            let name = &with[s..abs];
            let base_val = field_named_value(&base, name);
            if base_val.as_deref() != Some("Some(7)") {
                return name.to_string();
            }
            idx = abs + 1;
        }
        panic!(
            "could not locate the Option<u64> field that becomes Some(7) when \
             --max-matches-per-line 7 is parsed.\nbase={}\nwith={}",
            base, with
        );
    }
"""


def _run_injected_rust_test(test_fn_name, rust_body):
    """Inject a Rust test fn into defs.rs, run it via cargo, restore file."""
    original = _read(DEFS_PATH)

    module = "\n".join(
        [
            "",
            INJECT_MARKER,
            "#[cfg(test)]",
            "mod bench_clap_cli_patterns_ext2 {",
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
                "flags::defs::bench_clap_cli_patterns_ext2::" + test_fn_name,
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


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------

class TestClapCliPatterns:
    """Verify the new `--max-matches-per-line` numeric flag end-to-end."""

    REPO_DIR = REPO_DIR

    # ------------------------------------------------------------------
    # L1 — deliverable presence & shape
    # ------------------------------------------------------------------

    def test_deliverable_files_exist(self):
        """Both modified files (defs.rs and lowargs.rs) must exist."""
        assert os.path.isfile(DEFS_PATH), "defs.rs not found at " + DEFS_PATH
        assert os.path.isfile(LOWARGS_PATH), (
            "lowargs.rs not found at " + LOWARGS_PATH
        )

    def test_lowargs_declares_option_u64_field(self):
        """LowArgs must gain an `Option<u64>` field for the new flag.

        The doc mandates the stored type is an Option of an unsigned 64-bit
        integer. We don't require an exact name, but a u64 Option field must be
        present (and the most natural name is checked as a strong hint below).
        """
        src = _read(LOWARGS_PATH)
        # There must be at least one Option<u64> field; baseline already has a
        # few, so require that the natural field name OR an Option<u64> line was
        # added. We check the natural snake_case name primarily.
        natural = "max_matches_per_line"
        assert natural in src, (
            "expected a `%s` field on LowArgs; not found in lowargs.rs" % natural
        )
        # And it must be typed as Option<u64>.
        assert re.search(
            r"max_matches_per_line\s*:\s*Option\s*<\s*u64\s*>", src
        ), "the max_matches_per_line field must be typed Option<u64>"

    def test_defs_defines_and_registers_flag(self):
        """A Flag impl with the long name must exist and be in the FLAGS slice."""
        src = _read(DEFS_PATH)
        # The long name string literal must appear (returned by name_long()).
        assert '"%s"' % LONG_NAME in src, (
            "long name %r not declared in defs.rs" % LONG_NAME
        )
        # A new unit struct + Flag impl. The conventional name is MaxMatchesPerLine.
        assert re.search(r"struct\s+MaxMatchesPerLine\b", src), (
            "expected a `struct MaxMatchesPerLine` flag definition in defs.rs"
        )
        assert re.search(r"impl\s+Flag\s+for\s+MaxMatchesPerLine\b", src), (
            "expected `impl Flag for MaxMatchesPerLine` in defs.rs"
        )
        # Registered in the FLAGS slice (referenced as `&MaxMatchesPerLine`).
        assert re.search(r"&\s*MaxMatchesPerLine\b", src), (
            "MaxMatchesPerLine must be registered in the FLAGS slice"
        )

    def test_agent_added_own_unit_test(self):
        """The agent must add `fn test_max_matches_per_line` per the doc."""
        src = _read(DEFS_PATH)
        assert re.search(r"fn\s+test_max_matches_per_line\b", src), (
            "the required `test_max_matches_per_line` unit test is missing"
        )

    def test_no_leftover_injection(self):
        """Sanity: our scratch injection marker must not be committed."""
        for path in (DEFS_PATH, LOWARGS_PATH):
            src = _read(path)
            assert INJECT_MARKER not in src, (
                "leftover injected module found in %s; a previous run did not "
                "restore the file" % path
            )

    # ------------------------------------------------------------------
    # L2 — the agent's own required test must pass (native command)
    # ------------------------------------------------------------------

    def test_agents_native_test_passes(self):
        """The doc's native acceptance command must succeed.

        Drives exactly: cargo test --bin rg flags::defs::test_max_matches_per_line
        """
        proc = subprocess.run(
            [
                "cargo",
                "test",
                "--bin",
                "rg",
                "flags::defs::test_max_matches_per_line",
                "--",
                "--nocapture",
            ],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=CARGO_BUILD_TIMEOUT,
            env=_cargo_env(),
        )
        combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
        assert proc.returncode == 0, (
            "native test_max_matches_per_line failed.\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )
        assert "test result: ok" in combined, combined
        # Guard against the filter matching zero tests (typo'd fn name, etc.).
        assert re.search(r"running\s+1\s+test", combined), (
            "expected exactly the agent's 1 test to run; got:\n" + combined
        )

    # ------------------------------------------------------------------
    # L2 — independent behavioral verification via injected Rust tests
    # ------------------------------------------------------------------

    def test_absent_by_default_and_value_stored(self):
        """No flag -> None; `--max-matches-per-line 3` -> Some(3)."""
        body = r"""
    #[test]
    fn t() {
        let field = discover_field();
        // Absent by default.
        let base = debug_of(&[]);
        let v = field_named_value(&base, &field)
            .expect("field present in baseline dump");
        assert_eq!(v, "None", "flag must default to absent (None), got {}", v);

        // Supplied with a value -> Some(3).
        let with = debug_of(&["--max-matches-per-line", "3"]);
        let v = field_named_value(&with, &field).unwrap();
        assert_eq!(v, "Some(3)", "expected Some(3), got {}", v);
    }
"""
        proc = _run_injected_rust_test("t", body)
        _assert_cargo_ok(proc)

    def test_equals_form_and_zero_is_real_value(self):
        """`--max-matches-per-line=0` stores Some(0), not None."""
        body = r"""
    #[test]
    fn t() {
        let field = discover_field();
        let with = debug_of(&["--max-matches-per-line=0"]);
        let v = field_named_value(&with, &field).unwrap();
        assert_eq!(
            v, "Some(0)",
            "0 must be a real, distinct value (Some(0)), not absent; got {}", v
        );
        // And it must differ from the absent baseline.
        let base = debug_of(&[]);
        let b = field_named_value(&base, &field).unwrap();
        assert_eq!(b, "None");
        assert_ne!(b, v, "Some(0) must be distinguishable from None");
    }
"""
        proc = _run_injected_rust_test("t", body)
        _assert_cargo_ok(proc)

    def test_last_occurrence_wins(self):
        """Repeated flag: the last value wins (Some(9))."""
        body = r"""
    #[test]
    fn t() {
        let field = discover_field();
        let with = debug_of(&[
            "--max-matches-per-line", "2",
            "--max-matches-per-line=9",
        ]);
        let v = field_named_value(&with, &field).unwrap();
        assert_eq!(
            v, "Some(9)",
            "last occurrence must win (expected Some(9)); got {}", v
        );
    }
"""
        proc = _run_injected_rust_test("t", body)
        _assert_cargo_ok(proc)

    def test_non_numeric_inputs_error(self):
        """`abc`, `1.5`, and empty string must each fail to parse."""
        body = r"""
    #[test]
    fn t() {
        // A non-numeric value, a float, and an empty string must all be
        // rejected with an error (NOT silently defaulting to absent / 0).
        for bad in ["foo", "1.5", "", "abc", "-1"] {
            let res = parse_low_raw(
                ["--max-matches-per-line", bad].iter().copied(),
            );
            assert!(
                res.is_err(),
                "value {:?} must be rejected as a parse error, but it parsed Ok",
                bad
            );
        }
        // The equals form of a bad value must also error.
        let res = parse_low_raw(["--max-matches-per-line=1.5"].iter().copied());
        assert!(res.is_err(), "--max-matches-per-line=1.5 must error");
    }
"""
        proc = _run_injected_rust_test("t", body)
        _assert_cargo_ok(proc)

    def test_large_u64_value_roundtrips(self):
        """A value near u64::MAX must parse exactly (real u64 storage)."""
        body = r"""
    #[test]
    fn t() {
        let field = discover_field();
        // 18446744073709551615 == u64::MAX; must store exactly.
        let big = "18446744073709551615";
        let with = debug_of(&["--max-matches-per-line", big]);
        let v = field_named_value(&with, &field).unwrap();
        assert_eq!(
            v, format!("Some({})", big),
            "u64::MAX must round-trip exactly; got {}", v
        );
        // One beyond u64 range must error (proves it is a u64, not e.g. i64).
        let res = parse_low_raw(
            ["--max-matches-per-line", "18446744073709551616"].iter().copied(),
        );
        assert!(res.is_err(), "value > u64::MAX must error");
    }
"""
        proc = _run_injected_rust_test("t", body)
        _assert_cargo_ok(proc)

    def test_flag_is_recognized_not_unknown(self):
        """The parser must recognize the long name (registered in FLAGS).

        An unregistered flag would surface as an 'unrecognized flag' error; a
        registered one parses cleanly. We also confirm it is value-taking by
        checking that omitting the value is itself an error rather than 'unknown'.
        """
        body = r"""
    #[test]
    fn t() {
        // Recognized + value-taking -> Ok with a value present.
        let ok = parse_low_raw(["--max-matches-per-line", "4"].iter().copied());
        assert!(ok.is_ok(), "registered flag with value must parse: {:?}", ok.err());

        // Missing value must be an error whose message references the flag,
        // proving it's a recognized value-taking flag (not 'unknown flag').
        let res = parse_low_raw(["--max-matches-per-line"].iter().copied());
        assert!(res.is_err(), "value-taking flag with no value must error");
        let msg = format!("{}", res.unwrap_err());
        assert!(
            msg.contains("max-matches-per-line"),
            "error should reference the flag name, got: {}", msg
        );
    }
"""
        proc = _run_injected_rust_test("t", body)
        _assert_cargo_ok(proc)

    def test_only_target_field_changes(self):
        """Supplying the flag must change ONLY its own field, nothing else.

        This is the key discriminative check against a stub that, say, reuses an
        existing field (max_count) or perturbs unrelated state. We diff the full
        Debug dump line-by-line and require exactly one differing field, whose
        value is the expected Some(5).
        """
        body = r"""
    #[test]
    fn t() {
        let base = debug_of(&[]);
        let with = debug_of(&["--max-matches-per-line", "5"]);
        assert_ne!(base, with, "supplying the flag must change LowArgs");

        // The dumps are single-line; split into field tokens on ", " and find
        // the differing fields. Exactly one field may differ.
        let split = |s: &str| -> Vec<String> {
            s.trim_start_matches(|c| c != '{')
                .trim_start_matches('{')
                .trim_end_matches('}')
                .split(", ")
                .map(|x| x.trim().to_string())
                .collect()
        };
        let a = split(&base);
        let b = split(&with);
        assert_eq!(
            a.len(), b.len(),
            "field count changed between parses:\nbase={:?}\nwith={:?}", a, b
        );
        let mut diffs = Vec::new();
        for (x, y) in a.iter().zip(b.iter()) {
            if x != y {
                diffs.push((x.clone(), y.clone()));
            }
        }
        assert_eq!(
            diffs.len(), 1,
            "exactly one field must change; diffs were: {:?}", diffs
        );
        let (before, after) = &diffs[0];
        assert!(
            before.ends_with("None"),
            "the changed field must have been None before; was {}", before
        );
        assert!(
            after.ends_with("Some(5)"),
            "the changed field must become Some(5); was {}", after
        );
    }
"""
        proc = _run_injected_rust_test("t", body)
        _assert_cargo_ok(proc)

    def test_no_regression_in_defs_tests(self):
        """All pre-existing flags::defs unit tests must still pass."""
        proc = subprocess.run(
            ["cargo", "test", "--bin", "rg", "flags::defs::"],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=CARGO_BUILD_TIMEOUT,
            env=_cargo_env(),
        )
        combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
        assert proc.returncode == 0, (
            "pre-existing flags::defs tests regressed.\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )
        assert "test result: ok" in combined, combined
