"""
Test for the 'clap-cli-patterns' skill (variant ext5) — add an aliased
`--threads-cap` flag with human-readable size parsing to ripgrep's flag
definitions (crates/core/flags/defs.rs + crates/core/flags/lowargs.rs).

Variant task summary
--------------------
The agent must add a brand-new logical flag with:
  * long name  `threads-cap`
  * single alias `thread-cap`
  * short name  `-J`
  * a value (`NUM`) parsed via ripgrep's *existing* human-readable size
    converter (`convert::human_readable_u64` / `human_readable_usize`), so
    `1K` -> `1024`, and invalid input ERRORS (does not silently default),
  * stored on `LowArgs` as an `Option` of an unsigned integer, default absent,
  * "last occurrence wins" override semantics across every spelling,
  * registration in the global `FLAGS` slice,
  * a `#[test] fn test_threads_cap` covering the scenarios.

Native acceptance command (the doc's Acceptance Criteria):
    cargo test --bin rg flags::defs::test_threads_cap

Verification strategy
---------------------
L1 cases check the deliverable files exist and are minimally well-formed: the
new flag's three spellings appear in `defs.rs`, it is wired into `FLAGS`, a new
`LowArgs` field of `Option<unsigned>` exists, and the agent's own
`test_threads_cap` is present.

L2 cases are *dynamic and discriminative*. Rather than trust the agent's own
test, we INJECT our own `#[test]` module into `defs.rs` that drives the real
(but crate-private) `parse_low_raw` entry point against each spelling and reads
back the agent's new `LowArgs` field — whose name we discover dynamically from
the modified `lowargs.rs`. We assert exact stored values:
    no flag           -> None
    --threads-cap 4   -> Some(4)
    --thread-cap=1K   -> Some(1024)   (alias + human-readable suffix)
    -J 8              -> Some(8)       (short name)
    ... 2 -J 5        -> Some(5)       (last wins across spellings)
    --threads-cap nonsense -> parse error (does not default)
A naive stub that hardcodes a value, ignores the alias/short name, skips the
human-readable conversion, or never errors will fail these injected assertions.
We always restore the original file afterwards. We also run the agent's own
native acceptance test as a final gate.
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

INJECT_MARKER = "// __BENCH_CLAP_CLI_PATTERNS_EXT5_INJECTED__"

CARGO_BUILD_TIMEOUT = 900

# Pre-existing Option<...> fields on LowArgs in the upstream repo. We use this
# to *discover* the agent's newly added field (the one not in this set).
_KNOWN_OPTION_FIELDS = {
    "path_separator", "pre", "regex_size_limit", "replace", "sort",
    "with_filename", "dfa_size_limit", "max_filesize", "max_depth",
    "max_count", "color", "threads", "context_separator",
    "field_context_separator", "field_match_separator", "engine",
    "encoding", "hostname_bin", "mmap", "logging",
}


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


def _discover_cap_field():
    """Return the name of the new Option<unsigned> field on LowArgs.

    The agent adds exactly one new field to hold the parsed cap. We pick the
    field whose name is not in the known upstream set and whose type is an
    Option of an unsigned integer (u64/usize/u32/u16/u8/NonZero...).
    """
    src = _read(LOWARGS_PATH)
    candidates = []
    for m in re.finditer(
        r"(?:pub(?:\s*\([^)]*\))?\s+)?([a-z_][a-z0-9_]*)\s*:\s*"
        r"Option\s*<\s*(?:std::num::NonZero)?[uU](?:size|8|16|32|64|128)?\s*>",
        src,
    ):
        name = m.group(1)
        if name not in _KNOWN_OPTION_FIELDS:
            candidates.append(name)
    # Prefer a name that clearly relates to the task if multiple appear.
    for c in candidates:
        if "cap" in c or "thread" in c:
            return c
    if candidates:
        return candidates[0]
    return None


def _run_native_filter(test_filter):
    """Run a single cargo test by full path filter."""
    proc = subprocess.run(
        ["cargo", "test", "--bin", "rg", test_filter, "--", "--nocapture"],
        cwd=REPO_DIR,
        capture_output=True,
        text=True,
        timeout=CARGO_BUILD_TIMEOUT,
        env=_cargo_env(),
    )
    return proc


def _run_injected_rust_test(test_fn_name, rust_body):
    """Inject `rust_body` (one or more #[test] fns) into defs.rs, run, restore.

    The injected fns may call `parse_low_raw` (crate-private, but in scope via
    `use super::parse_low_raw;`).
    """
    original = _read(DEFS_PATH)
    module = "\n".join(
        [
            "",
            INJECT_MARKER,
            "#[cfg(test)]",
            "mod bench_ext5_threads_cap {",
            "    #[allow(unused_imports)]",
            "    use super::*;",
            "    #[allow(unused_imports)]",
            "    use crate::flags::parse::parse_low_raw;",
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
                "flags::defs::bench_ext5_threads_cap::" + test_fn_name,
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
    assert re.search(r"running\s+%s\s+test" % re.escape(expect_run), combined), (
        "expected %s injected test(s) to actually run, output was:\n%s"
        % (expect_run, combined)
    )


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------

class TestClapCliPatterns:
    """Verify the aliased, human-readable `--threads-cap` flag."""

    REPO_DIR = REPO_DIR

    # ------------------------------------------------------------------
    # L1 — deliverable presence & static shape
    # ------------------------------------------------------------------

    def test_defs_file_exists(self):
        """The flag-definitions file defs.rs must exist."""
        assert os.path.isfile(DEFS_PATH), "defs.rs not found at " + DEFS_PATH
        assert os.path.isfile(LOWARGS_PATH), (
            "lowargs.rs not found at " + LOWARGS_PATH
        )

    def test_long_name_present(self):
        """The long name `threads-cap` must be declared in defs.rs."""
        src = _read(DEFS_PATH)
        assert re.search(r'"threads-cap"', src), (
            "long name \"threads-cap\" not found in defs.rs"
        )

    def test_alias_present(self):
        """The alias `thread-cap` must be declared (via aliases())."""
        src = _read(DEFS_PATH)
        assert re.search(r'"thread-cap"', src), (
            "alias \"thread-cap\" not found in defs.rs"
        )
        # And it must be an alias, not a second independent long-name flag.
        assert "fn aliases" in src, "no aliases() implementation present"

    def test_short_name_present(self):
        """The short name `-J` (b'J') must be declared via name_short()."""
        src = _read(DEFS_PATH)
        assert re.search(r"name_short\b", src), "no name_short() in defs.rs"
        assert re.search(r"b'J'", src), (
            "short name b'J' for -J not found in defs.rs"
        )

    def test_uses_human_readable_converter(self):
        """The value must go through the existing human-readable converter."""
        src = _read(DEFS_PATH)
        assert re.search(r"human_readable_(?:u64|usize)", src), (
            "flag does not parse its value with convert::human_readable_*; "
            "human-readable suffixes would not be honored"
        )

    def test_registered_in_flags_slice(self):
        """The new flag struct must be wired into the global FLAGS slice."""
        src = _read(DEFS_PATH)
        # Find the new flag's struct identifier from its impl that declares the
        # long name "threads-cap".
        m = re.search(
            r"impl\s+Flag\s+for\s+([A-Za-z0-9_]+)\s*\{(?:[^}]|\}(?!\s*\n))*?"
            r'"threads-cap"',
            src,
            re.DOTALL,
        )
        assert m, "could not locate the impl Flag block for threads-cap"
        struct_name = m.group(1)
        # FLAGS is a `&[&dyn Flag]` of `&StructName` entries.
        assert re.search(r"&\s*%s\b" % re.escape(struct_name), src), (
            "flag struct %s not registered in FLAGS slice" % struct_name
        )

    def test_new_lowargs_field_added(self):
        """A new Option<unsigned-int> field must exist on LowArgs, default absent."""
        field = _discover_cap_field()
        assert field is not None, (
            "no new Option<unsigned> field found on LowArgs; the parsed cap "
            "must be stored as Option of an unsigned integer"
        )

    def test_agent_added_native_test(self):
        """The agent's own #[test] fn test_threads_cap must be present."""
        src = _read(DEFS_PATH)
        assert re.search(r"fn\s+test_threads_cap\b", src), (
            "expected agent unit test `fn test_threads_cap` in defs.rs"
        )

    def test_no_leftover_injection(self):
        """Sanity: our scratch injection marker must not have leaked in."""
        for p in (DEFS_PATH, LOWARGS_PATH):
            assert INJECT_MARKER not in _read(p), (
                "leftover injected module in %s; a prior run failed to restore"
                % p
            )

    # ------------------------------------------------------------------
    # L2 — dynamic behavioral verification via injected Rust tests
    # ------------------------------------------------------------------

    def test_default_absent_and_long_name(self):
        """No flag -> None; `--threads-cap 4` -> Some(4) on the new field."""
        field = _discover_cap_field()
        assert field is not None, "new LowArgs field not found"
        body = r"""
    #[test]
    fn t() {
        let args = parse_low_raw(None::<&str>).unwrap();
        assert_eq!(None, args.%(f)s, "default must be absent");

        let args = parse_low_raw(["--threads-cap", "4"]).unwrap();
        assert_eq!(Some(4), args.%(f)s, "--threads-cap 4 should store Some(4)");

        let args = parse_low_raw(["--threads-cap=4"]).unwrap();
        assert_eq!(Some(4), args.%(f)s, "--threads-cap=4 should store Some(4)");
    }
""" % {"f": field}
        _assert_cargo_ok(_run_injected_rust_test("t", body))

    def test_alias_resolves_to_same_field_with_suffix(self):
        """`--thread-cap=1K` -> Some(1024): alias + human-readable suffix."""
        field = _discover_cap_field()
        assert field is not None, "new LowArgs field not found"
        body = r"""
    #[test]
    fn t() {
        // Alias updates the SAME field as the long name.
        let args = parse_low_raw(["--thread-cap=1K"]).unwrap();
        assert_eq!(
            Some(1024), args.%(f)s,
            "alias --thread-cap with 1K must parse to 1024 on the same field"
        );

        // And the alias without a suffix still works as a plain number.
        let args = parse_low_raw(["--thread-cap", "7"]).unwrap();
        assert_eq!(Some(7), args.%(f)s, "alias plain numeric value");

        // The long name honors the suffix identically.
        let args = parse_low_raw(["--threads-cap=2K"]).unwrap();
        assert_eq!(Some(2048), args.%(f)s, "long name must honor K suffix");
    }
""" % {"f": field}
        _assert_cargo_ok(_run_injected_rust_test("t", body))

    def test_short_name_resolves_to_same_field(self):
        """`-J 8` -> Some(8): the short name maps to the same logical flag."""
        field = _discover_cap_field()
        assert field is not None, "new LowArgs field not found"
        body = r"""
    #[test]
    fn t() {
        let args = parse_low_raw(["-J", "8"]).unwrap();
        assert_eq!(Some(8), args.%(f)s, "-J 8 must store Some(8)");

        // Short name also accepts the attached form and human-readable suffix.
        let args = parse_low_raw(["-J", "1M"]).unwrap();
        assert_eq!(
            Some(1024 * 1024), args.%(f)s,
            "-J should honor M suffix via the human-readable converter"
        );
    }
""" % {"f": field}
        _assert_cargo_ok(_run_injected_rust_test("t", body))

    def test_last_occurrence_wins_across_spellings(self):
        """`--threads-cap 2 -J 5` -> Some(5): last wins across any spelling."""
        field = _discover_cap_field()
        assert field is not None, "new LowArgs field not found"
        body = r"""
    #[test]
    fn t() {
        let args = parse_low_raw(["--threads-cap", "2", "-J", "5"]).unwrap();
        assert_eq!(Some(5), args.%(f)s, "last (-J 5) must win");

        // Reverse order: -J first, long name last.
        let args = parse_low_raw(["-J", "5", "--threads-cap", "2"]).unwrap();
        assert_eq!(Some(2), args.%(f)s, "last (--threads-cap 2) must win");

        // Alias participates in the same override chain.
        let args =
            parse_low_raw(["--threads-cap", "9", "--thread-cap", "3"]).unwrap();
        assert_eq!(Some(3), args.%(f)s, "alias last occurrence must win");
    }
""" % {"f": field}
        _assert_cargo_ok(_run_injected_rust_test("t", body))

    def test_invalid_value_errors_not_default(self):
        """`--threads-cap nonsense` must error, not silently default to None."""
        field = _discover_cap_field()
        assert field is not None, "new LowArgs field not found"
        body = r"""
    #[test]
    fn t() {
        let result = parse_low_raw(["--threads-cap", "nonsense"]);
        assert!(
            result.is_err(),
            "invalid value must error, got: {:?}",
            result.ok().map(|a| a.%(f)s)
        );

        // Errors on every spelling.
        let result = parse_low_raw(["--thread-cap", "12x9"]);
        assert!(result.is_err(), "alias must also reject invalid input");

        let result = parse_low_raw(["-J", "abc"]);
        assert!(result.is_err(), "-J must also reject invalid input");
    }
""" % {"f": field}
        _assert_cargo_ok(_run_injected_rust_test("t", body))

    def test_alias_is_not_a_separate_flag(self):
        """The alias must resolve to the same flag, not register a 2nd one.

        We confirm both spellings produce identical state for the same value,
        which a stub that wired `thread-cap` to a different/independent field
        (or to nothing) would fail.
        """
        field = _discover_cap_field()
        assert field is not None, "new LowArgs field not found"
        body = r"""
    #[test]
    fn t() {
        let a = parse_low_raw(["--threads-cap", "64"]).unwrap();
        let b = parse_low_raw(["--thread-cap", "64"]).unwrap();
        assert_eq!(
            a.%(f)s, b.%(f)s,
            "alias and long name must update the same field identically"
        );
        assert_eq!(Some(64), a.%(f)s);
    }
""" % {"f": field}
        _assert_cargo_ok(_run_injected_rust_test("t", body))

    def test_native_acceptance_test_passes(self):
        """The doc's native command: agent's own test_threads_cap must pass."""
        proc = _run_native_filter("flags::defs::test_threads_cap")
        combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
        assert proc.returncode == 0, (
            "native acceptance test failed.\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )
        assert "test result: ok" in combined, combined
        # Make sure the test actually ran (was not filtered to zero).
        assert re.search(r"running\s+1\s+test", combined), (
            "expected test_threads_cap to actually execute:\n" + combined
        )

    def test_existing_defs_tests_still_pass(self):
        """No regression: pre-existing flags::defs tests must still pass."""
        proc = _run_native_filter("flags::defs::")
        combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
        assert proc.returncode == 0, (
            "pre-existing defs tests failed.\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )
        assert "test result: ok" in combined, combined
