"""
Test for 'clap-cli-patterns' skill (variant ext8) — Emit choice lists into
ripgrep's *bash* completion output (crates/core/flags/complete/bash.rs).

The variant task makes the bash completion generator (`generate()` in
crates/core/flags/complete/bash.rs) emit, for every flag that declares a
non-empty `doc_choices()` list, a `case` arm whose `compgen -W` word list is
exactly that flag's choices, space-separated, in declaration order — while
leaving filename-style and switch flags on their existing file-completion arm
and keeping the overall `_rg()` structure + `complete -F _rg` registration
line intact.

Native acceptance command (from the requirement doc):

    cargo test --bin rg flags::complete::bash::

Verification strategy
---------------------
`generate()` is `pub(crate)` and returns the full bash script as a `String`,
so it cannot be reached from an external integration test. As with the ext1
harness, this test verifies the agent's work *discriminatively* by injecting
its own `#[cfg(test)] mod` into bash.rs that calls the real `super::generate()`
and asserts on the produced script text, then runs it through the native
toolchain and always restores the original file.

A naive implementation that ignores `doc_choices()` (and therefore renders
`--engine` / `--sort` with the generic `compgen -f` file arm, or with an empty
`-W ""` list) will FAIL the injected Rust assertions, which require the exact
choice word lists in declaration order.

L1 cases check the deliverable file is present / minimally well-formed and that
the agent left a `#[cfg(test)]` unit-test block in bash.rs. L2 cases compile and
run real Rust assertions over the generated script end to end.
"""

import os
import re
import subprocess

import pytest


REPO_DIR = "/workspace/ripgrep"
BASH_REL = os.path.join("crates", "core", "flags", "complete", "bash.rs")
BASH_PATH = os.path.join(REPO_DIR, BASH_REL)

# Unique marker so our injected module is easy to identify / strip out again.
INJECT_MARKER = "// __BENCH_CLAP_CLI_PATTERNS_EXT8_INJECTED__"

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
    """Inject a Rust test fn into bash.rs, run it via cargo, restore the file.

    `rust_body` is the full body (incl. `#[test]` attribute + signature) of one
    or more test functions, which may call `super::generate()` -> String.

    Returns the CompletedProcess of the cargo invocation. The original file is
    always restored, even on failure.
    """
    original = _read(BASH_PATH)

    module = "\n".join(
        [
            "",
            INJECT_MARKER,
            "#[cfg(test)]",
            "mod bench_clap_cli_patterns_ext8 {",
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
        _write(BASH_PATH, patched)
        proc = subprocess.run(
            [
                "cargo",
                "test",
                "--bin",
                "rg",
                "flags::complete::bash::bench_clap_cli_patterns_ext8::"
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
        _write(BASH_PATH, original)


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


# A small Rust helper pasted into each injected module: collapse runs of
# whitespace so assertions are robust to template indentation/newlines while
# still being exact about token content + ordering.
_RUST_HELPERS = r"""
    fn flat(s: &str) -> String {
        s.split_whitespace().collect::<Vec<_>>().join(" ")
    }
"""


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------

class TestClapCliPatterns:
    """Verify choice-aware bash completion arms in bash.rs."""

    REPO_DIR = REPO_DIR

    # ------------------------------------------------------------------
    # L1 — deliverable presence & shape
    # ------------------------------------------------------------------

    def test_bash_file_exists(self):
        """The bash generator file must exist at the documented path."""
        assert os.path.isfile(BASH_PATH), "bash.rs not found at " + BASH_PATH

    def test_generate_entry_present(self):
        """The `generate()` entry point must still be present and crate-visible."""
        src = _read(BASH_PATH)
        assert re.search(r"fn\s+generate\s*\(", src), (
            "generate() function missing from bash.rs"
        )
        # It is the entry the rest of the completion machinery calls; keep it.
        assert "pub(crate)" in src or "pub(super)" in src or "pub " in src, (
            "generate() must remain visible to the crate"
        )

    def test_choice_template_present(self):
        """A choices-aware template / branch must exist (not just the file arm).

        The implementation must produce a `compgen -W` (word-list) completion
        for choice-bearing flags, distinct from the generic `compgen -f` file
        arm. Source must reference both the file arm and a word-list arm.
        """
        src = _read(BASH_PATH)
        assert "compgen -f" in src, "file-completion arm (compgen -f) missing"
        assert "compgen -W" in src, (
            "no word-list (compgen -W) arm in bash.rs; choices were not emitted"
        )
        assert "doc_choices" in src, (
            "generator must consult flag.doc_choices() to emit choice arms"
        )

    def test_registration_line_in_source(self):
        """The `complete -F _rg ... rg` registration line must be templated."""
        src = _read(BASH_PATH)
        assert re.search(r"complete\s+-F\s+_rg", src), (
            "the `complete -F _rg` registration line is missing from the template"
        )

    def test_no_leftover_injection(self):
        """Sanity: our scratch injection marker must not be committed."""
        src = _read(BASH_PATH)
        assert INJECT_MARKER not in src, (
            "leftover injected test module found in bash.rs; "
            "a previous run did not restore the file"
        )

    def test_has_unit_tests(self):
        """The agent must add a #[cfg(test)] mod with unit tests to bash.rs.

        Per the acceptance criteria the added/updated unit test asserts the
        --engine / --sort choice arms and the registration line. Our injected
        marker is excluded so this measures the agent's own additions.
        """
        src = _read(BASH_PATH)
        # Strip any (defensively) leftover injected block before counting.
        if INJECT_MARKER in src:
            parts = src.split(INJECT_MARKER)
            src = parts[0] + (parts[-1] if len(parts) > 2 else "")
        assert "#[cfg(test)]" in src, "no #[cfg(test)] block added to bash.rs"
        assert "mod tests" in src or re.search(r"\bmod\s+\w+\s*\{", src), (
            "no test module added to bash.rs"
        )
        test_count = len(re.findall(r"#\[test\]", src))
        assert test_count >= 1, (
            "expected the agent to add a unit test for the choice arms; "
            "found %d #[test]" % test_count
        )

    def test_pre_existing_complete_tests_pass(self):
        """The full bash completion test path must compile & pass (no regression)."""
        proc = subprocess.run(
            ["cargo", "test", "--bin", "rg", "flags::complete::bash::"],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=CARGO_BUILD_TIMEOUT,
            env=_cargo_env(),
        )
        combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
        assert proc.returncode == 0, (
            "native bash completion tests failed.\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )
        assert "test result: ok" in combined, combined

    # ------------------------------------------------------------------
    # L2 — dynamic behavioral verification via injected Rust tests
    # ------------------------------------------------------------------

    def test_engine_choice_arm(self):
        """`--engine` arm offers exactly `default pcre2 auto` via `compgen -W`."""
        body = _RUST_HELPERS + r"""
    #[test]
    fn t() {
        let script = generate();
        let flat = flat(&script);
        // The exact choice word list, in declaration order, attached to a
        // word-list (compgen -W) arm. A naive impl using `compgen -f` for
        // --engine, or a reordered/partial list, fails here.
        let needle = "--engine) COMPREPLY=($(compgen -W \"default pcre2 auto\"";
        assert!(
            flat.contains(needle),
            "missing --engine choice arm `default pcre2 auto`.\nflat:\n{}",
            flat
        );
    }
"""
        proc = _run_injected_rust_test("t", body)
        _assert_cargo_ok(proc)

    def test_sort_choice_arm(self):
        """`--sort` arm offers exactly `none path modified accessed created`."""
        body = _RUST_HELPERS + r"""
    #[test]
    fn t() {
        let script = generate();
        let flat = flat(&script);
        let needle =
            "--sort) COMPREPLY=($(compgen -W \"none path modified accessed created\"";
        assert!(
            flat.contains(needle),
            "missing --sort choice arm.\nflat:\n{}",
            flat
        );
    }
"""
        proc = _run_injected_rust_test("t", body)
        _assert_cargo_ok(proc)

    def test_choices_in_declaration_order_not_sorted(self):
        """Choice words keep declaration order (NOT alphabetical sorting).

        `default pcre2 auto` is deliberately not alphabetical. A stub that sorts
        the choices would emit `auto default pcre2` and must fail.
        """
        body = _RUST_HELPERS + r"""
    #[test]
    fn t() {
        let flat = flat(&generate());
        assert!(
            flat.contains("compgen -W \"default pcre2 auto\""),
            "engine choices must be in declaration order"
        );
        assert!(
            !flat.contains("compgen -W \"auto default pcre2\""),
            "choices must NOT be alphabetically sorted"
        );
    }
"""
        proc = _run_injected_rust_test("t", body)
        _assert_cargo_ok(proc)

    def test_registration_line_emitted(self):
        """Generated script still ends with the `complete -F _rg ... rg` line."""
        body = _RUST_HELPERS + r"""
    #[test]
    fn t() {
        let script = generate();
        assert!(
            script.contains("complete -F _rg"),
            "registration line missing from generated script"
        );
        assert!(
            script.trim_end().ends_with("rg"),
            "script must end with the `... rg` registration"
        );
    }
"""
        proc = _run_injected_rust_test("t", body)
        _assert_cargo_ok(proc)

    def test_rg_function_structure_intact(self):
        """Generated script is a single `_rg()` function with the opts/case shell."""
        body = _RUST_HELPERS + r"""
    #[test]
    fn t() {
        let script = generate();
        assert!(script.contains("_rg() {"), "missing _rg() function opener");
        assert_eq!(
            script.matches("_rg() {").count(),
            1,
            "expected exactly one _rg() function"
        );
        assert!(
            script.contains("case \"${prev}\" in"),
            "missing per-flag case dispatch on ${prev}"
        );
        assert!(
            script.contains("compgen -W \"${opts}\""),
            "missing top-level option completion"
        );
    }
"""
        proc = _run_injected_rust_test("t", body)
        _assert_cargo_ok(proc)

    def test_filename_flag_keeps_file_arm(self):
        """A filename-style flag must keep its `compgen -f` arm, not a choice arm.

        `--file` takes a filename value and declares no choices; it must offer
        file completion (`compgen -f`) and must NOT be turned into a `-W` arm.
        """
        body = _RUST_HELPERS + r"""
    #[test]
    fn t() {
        let flat = flat(&generate());
        // The --file arm must be the file-completion variant.
        let file_arm = "--file) COMPREPLY=($(compgen -f";
        assert!(
            flat.contains(file_arm),
            "expected --file to keep its file-completion arm.\nflat:\n{}",
            flat
        );
        // And it must not have been converted into a word-list arm.
        assert!(
            !flat.contains("--file) COMPREPLY=($(compgen -W"),
            "filename flag --file was incorrectly turned into a choice arm"
        );
    }
"""
        proc = _run_injected_rust_test("t", body)
        _assert_cargo_ok(proc)

    def test_no_empty_choice_word_list(self):
        """No flag is rendered with an empty `compgen -W ""` choices arm.

        A flag with no choices and no filename type must not get a choices arm
        offering an empty word list.
        """
        body = _RUST_HELPERS + r"""
    #[test]
    fn t() {
        let flat = flat(&generate());
        assert!(
            !flat.contains("compgen -W \"\""),
            "found an empty `compgen -W \"\"` choices arm; \
             only choice-bearing flags should get a -W arm"
        );
    }
"""
        proc = _run_injected_rust_test("t", body)
        _assert_cargo_ok(proc)

    def test_color_choice_arm(self):
        """`--color` (another choice flag) offers `never auto always ansi`.

        Independent of --engine/--sort to prove the behavior is general, not
        a pair of hardcoded special cases.
        """
        body = _RUST_HELPERS + r"""
    #[test]
    fn t() {
        let flat = flat(&generate());
        let needle =
            "--color) COMPREPLY=($(compgen -W \"never auto always ansi\"";
        assert!(
            flat.contains(needle),
            "missing --color choice arm `never auto always ansi`.\nflat:\n{}",
            flat
        );
    }
"""
        proc = _run_injected_rust_test("t", body)
        _assert_cargo_ok(proc)

    def test_determinism_identical_runs(self):
        """`generate()` is pure: two calls yield byte-identical output."""
        body = _RUST_HELPERS + r"""
    #[test]
    fn t() {
        let a = generate();
        let b = generate();
        assert_eq!(a, b, "generate() must be deterministic across calls");
        assert!(!a.is_empty(), "generated script must be non-empty");
    }
"""
        proc = _run_injected_rust_test("t", body)
        _assert_cargo_ok(proc)

    def test_choice_arm_uses_word_list_not_file_completion(self):
        """Choice arms must use `-W` (word list) and a `-- "${cur}"` filter.

        Ties the two required choice flags together in one run and asserts the
        full shell shape, so a partial impl (e.g. emitting choices but dropping
        the `-- "${cur}"` filter, or using `compgen -f`) fails.
        """
        body = _RUST_HELPERS + r"""
    #[test]
    fn t() {
        let flat = flat(&generate());
        for needle in [
            "--engine) COMPREPLY=($(compgen -W \"default pcre2 auto\" -- \"${cur}\"))",
            "--sort) COMPREPLY=($(compgen -W \"none path modified accessed created\" -- \"${cur}\"))",
        ] {
            assert!(
                flat.contains(needle),
                "missing full choice arm shape:\n  expected substring: {}\n  flat:\n{}",
                needle, flat
            );
        }
    }
"""
        proc = _run_injected_rust_test("t", body)
        _assert_cargo_ok(proc)
