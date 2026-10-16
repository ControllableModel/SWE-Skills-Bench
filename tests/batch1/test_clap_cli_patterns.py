"""
Test for 'clap-cli-patterns' skill — Recursive file inclusion in ripgrep's
rc-file config parser (crates/core/flags/config.rs).

The task extends the rc-file line parser in `crates/core/flags/config.rs` to
support:
  * trailing inline `" #"` comments (while embedded `#` is preserved),
  * `@path` include directives resolved relative to the including file's dir,
    flattened depth-first / left-to-right,
  * unreadable-include and cyclic-include per-line error reporting (no crash /
    no infinite loop), and a diamond include producing duplicated args.

The native test command is:  cargo test --bin rg flags::config::

Because the parser entry points (`parse` / `parse_reader`) are PRIVATE to the
`rg` binary crate, this test verifies the agent's work *discriminatively* by
injecting its own `#[cfg(test)]` module into config.rs that drives the real
`super::parse` function against freshly-written temp rc files, runs it through
the native toolchain, and then restores the original file. A naive solution
that does not actually implement inclusion / comment-stripping / cycle
protection will fail these injected Rust assertions.

L1 cases check the deliverable file is present and minimally well-formed plus
that the agent left its own `mod tests` block in place. L2 cases compile and
run real Rust assertions exercising the new behavior end to end.
"""

import os
import re
import shutil
import subprocess
import tempfile

import pytest


REPO_DIR = "/workspace/ripgrep"
CONFIG_REL = os.path.join("crates", "core", "flags", "config.rs")
CONFIG_PATH = os.path.join(REPO_DIR, CONFIG_REL)

# Unique marker so our injected module is easy to identify / strip out again.
INJECT_MARKER = "// __BENCH_CLAP_CLI_PATTERNS_INJECTED__"

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
    # Make sure cargo's bin dir is reachable regardless of PYTHONPATH clearing.
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
    """Inject a Rust test fn into config.rs, run it via cargo, restore file.

    `rust_body` is the full body (incl. signature) of one or more `#[test]`
    functions which may call `super::parse` (a `Path`-based parser returning
    `(Vec<OsString>, Vec<anyhow::Error>)`).

    Returns the CompletedProcess of the cargo invocation. The original file is
    always restored, even on failure.
    """
    original = _read(CONFIG_PATH)

    module = "\n".join(
        [
            "",
            INJECT_MARKER,
            "#[cfg(test)]",
            "mod bench_clap_cli_patterns {",
            "    #[allow(unused_imports)]",
            "    use super::parse;",
            "    use std::io::Write as _;",
            "",
            rust_body,
            "}",
            INJECT_MARKER,
            "",
        ]
    )

    patched = original + module
    try:
        _write(CONFIG_PATH, patched)
        proc = subprocess.run(
            [
                "cargo",
                "test",
                "--bin",
                "rg",
                "flags::config::bench_clap_cli_patterns::" + test_fn_name,
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
        _write(CONFIG_PATH, original)


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


# Shared Rust helper snippets pasted into each injected module.
_RUST_HELPERS = r"""
    // Create a unique scratch directory under the system temp dir.
    fn scratch() -> std::path::PathBuf {
        let mut d = std::env::temp_dir();
        let uniq = format!(
            "bench_clap_{}_{}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        );
        d.push(uniq);
        std::fs::create_dir_all(&d).unwrap();
        d
    }

    fn writef(dir: &std::path::Path, name: &str, contents: &str) -> std::path::PathBuf {
        let p = dir.join(name);
        let mut f = std::fs::File::create(&p).unwrap();
        f.write_all(contents.as_bytes()).unwrap();
        p
    }

    fn strs(args: Vec<std::ffi::OsString>) -> Vec<String> {
        args.into_iter().map(|s| s.into_string().unwrap()).collect()
    }
"""


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------

class TestClapCliPatterns:
    """Verify recursive include / comment / cycle handling in config.rs."""

    REPO_DIR = REPO_DIR

    # ------------------------------------------------------------------
    # L1 — deliverable presence & shape
    # ------------------------------------------------------------------

    def test_config_file_exists(self):
        """The parser file crates/core/flags/config.rs must exist."""
        assert os.path.isfile(CONFIG_PATH), "config.rs not found at " + CONFIG_PATH

    def test_config_keeps_parse_reader_entry(self):
        """The original parse/parse_reader entry points must still be present."""
        src = _read(CONFIG_PATH)
        assert "fn parse" in src, "parse function missing from config.rs"
        assert "parse_reader" in src, "parse_reader removed from config.rs"
        assert "pub fn args()" in src, "public args() entry point removed"

    def test_config_has_test_module(self):
        """The agent must add unit tests to the #[cfg(test)] mod tests block."""
        src = _read(CONFIG_PATH)
        # The pre-existing module must still exist (acceptance: existing tests pass).
        assert "#[cfg(test)]" in src, "no #[cfg(test)] block in config.rs"
        assert "mod tests" in src, "mod tests block missing"
        # And the agent should have grown it with at least one new #[test].
        test_count = len(re.findall(r"#\[test\]", src))
        assert test_count >= 3, (
            "expected the agent to add new unit tests; only %d #[test] found"
            % test_count
        )

    def test_no_leftover_injection(self):
        """Sanity: our scratch injection marker must not be committed."""
        src = _read(CONFIG_PATH)
        assert INJECT_MARKER not in src, (
            "leftover injected test module found in config.rs; "
            "a previous run did not restore the file"
        )

    def test_existing_tests_still_pass(self):
        """All pre-existing config tests must still pass (no regression)."""
        proc = subprocess.run(
            ["cargo", "test", "--bin", "rg", "flags::config::"],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=CARGO_BUILD_TIMEOUT,
            env=_cargo_env(),
        )
        combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
        assert proc.returncode == 0, (
            "pre-existing config tests failed.\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )
        assert "test result: ok" in combined, combined

    # ------------------------------------------------------------------
    # L2 — dynamic behavioral verification via injected Rust tests
    # ------------------------------------------------------------------

    def test_basic_include_splices_in_order(self):
        """`@common.rc` between args splices its args at the directive site."""
        body = _RUST_HELPERS + r"""
    #[test]
    fn t() {
        let d = scratch();
        writef(&d, "common.rc", "--ignore-case\n-u\n");
        let main = writef(&d, "main.rc", "--smart-case\n@common.rc\n--hidden\n");
        let (args, errs) = parse(&main).unwrap();
        assert!(errs.is_empty(), "unexpected errors: {:?}", errs);
        assert_eq!(
            strs(args),
            vec!["--smart-case", "--ignore-case", "-u", "--hidden"],
        );
        std::fs::remove_dir_all(&d).ok();
    }
"""
        proc = _run_injected_rust_test("t", body)
        _assert_cargo_ok(proc)

    def test_inline_comment_trimmed(self):
        """`--context=2  # widen context` yields `--context=2` only."""
        body = _RUST_HELPERS + r"""
    #[test]
    fn t() {
        let d = scratch();
        let main = writef(&d, "main.rc", "--context=2  # widen context\n");
        let (args, errs) = parse(&main).unwrap();
        assert!(errs.is_empty(), "unexpected errors: {:?}", errs);
        assert_eq!(strs(args), vec!["--context=2"]);
        std::fs::remove_dir_all(&d).ok();
    }
"""
        proc = _run_injected_rust_test("t", body)
        _assert_cargo_ok(proc)

    def test_embedded_hash_preserved(self):
        """`--glob=*.rs#scratch` keeps the `#` (no space before it)."""
        body = _RUST_HELPERS + r"""
    #[test]
    fn t() {
        let d = scratch();
        // Two cases: hash with no preceding space (kept), and a value that
        // contains a hash followed later by a real " #" comment.
        let main = writef(
            &d,
            "main.rc",
            "--glob=*.rs#scratch\n--glob=*.c#keep # drop this\n",
        );
        let (args, errs) = parse(&main).unwrap();
        assert!(errs.is_empty(), "unexpected errors: {:?}", errs);
        assert_eq!(
            strs(args),
            vec!["--glob=*.rs#scratch", "--glob=*.c#keep"],
        );
        std::fs::remove_dir_all(&d).ok();
    }
"""
        proc = _run_injected_rust_test("t", body)
        _assert_cargo_ok(proc)

    def test_comment_only_line_skipped(self):
        """A line that becomes empty after comment-stripping is skipped."""
        body = _RUST_HELPERS + r"""
    #[test]
    fn t() {
        let d = scratch();
        // Whole-line '#', blank line, a " #"-only trailing comment line that
        // is whitespace before the comment, then a real arg.
        let main = writef(
            &d,
            "main.rc",
            "# whole line comment\n\n   # leading hash comment\n--foo\n",
        );
        let (args, errs) = parse(&main).unwrap();
        assert!(errs.is_empty(), "unexpected errors: {:?}", errs);
        assert_eq!(strs(args), vec!["--foo"]);
        std::fs::remove_dir_all(&d).ok();
    }
"""
        proc = _run_injected_rust_test("t", body)
        _assert_cargo_ok(proc)

    def test_nested_include_depth_first(self):
        """Nested includes flatten depth-first, left-to-right."""
        body = _RUST_HELPERS + r"""
    #[test]
    fn t() {
        let d = scratch();
        writef(&d, "c.rc", "-c1\n-c2\n");
        writef(&d, "b.rc", "-b1\n@c.rc\n-b2\n");
        let main = writef(&d, "a.rc", "-a1\n@b.rc\n-a2\n");
        let (args, errs) = parse(&main).unwrap();
        assert!(errs.is_empty(), "unexpected errors: {:?}", errs);
        assert_eq!(
            strs(args),
            vec!["-a1", "-b1", "-c1", "-c2", "-b2", "-a2"],
        );
        std::fs::remove_dir_all(&d).ok();
    }
"""
        proc = _run_injected_rust_test("t", body)
        _assert_cargo_ok(proc)

    def test_relative_include_resolved_to_including_dir(self):
        """A relative include resolves to the including file's directory."""
        body = _RUST_HELPERS + r"""
    #[test]
    fn t() {
        let d = scratch();
        let sub = d.join("sub");
        std::fs::create_dir_all(&sub).unwrap();
        // included file lives in sub/, and references a sibling via a bare name
        writef(&sub, "child.rc", "-x\n@grandchild.rc\n");
        writef(&sub, "grandchild.rc", "-y\n");
        // main lives in d/ and includes sub/child.rc
        let main = writef(&d, "main.rc", "-m\n@sub/child.rc\n-n\n");
        let (args, errs) = parse(&main).unwrap();
        assert!(
            errs.is_empty(),
            "relative include must resolve to including dir; errs: {:?}",
            errs
        );
        assert_eq!(strs(args), vec!["-m", "-x", "-y", "-n"]);
        std::fs::remove_dir_all(&d).ok();
    }
"""
        proc = _run_injected_rust_test("t", body)
        _assert_cargo_ok(proc)

    def test_unreadable_include_is_per_line_error(self):
        """A missing include file is an error but parsing continues."""
        body = _RUST_HELPERS + r"""
    #[test]
    fn t() {
        let d = scratch();
        let main = writef(
            &d,
            "main.rc",
            "--before\n@does_not_exist.rc\n--after\n",
        );
        let (args, errs) = parse(&main).unwrap();
        // Surrounding ordinary lines still parse.
        assert_eq!(strs(args), vec!["--before", "--after"]);
        // The bad include is surfaced as exactly one per-line error mentioning
        // the failing path.
        assert_eq!(errs.len(), 1, "expected one include error, got {:?}", errs);
        let msg = format!("{}", errs[0]);
        assert!(
            msg.contains("does_not_exist.rc"),
            "error should identify the failing path, got: {}",
            msg
        );
        std::fs::remove_dir_all(&d).ok();
    }
"""
        proc = _run_injected_rust_test("t", body)
        _assert_cargo_ok(proc)

    def test_direct_cycle_terminates_and_reports(self):
        """a.rc -> b.rc -> a.rc: cycle reported, no infinite recursion."""
        body = _RUST_HELPERS + r"""
    #[test]
    fn t() {
        let d = scratch();
        writef(&d, "b.rc", "-b\n@a.rc\n");
        let main = writef(&d, "a.rc", "-a\n@b.rc\n");
        let (args, errs) = parse(&main).unwrap();
        // The non-cyclic args are still collected.
        assert_eq!(strs(args), vec!["-a", "-b"]);
        // The cyclic re-entry of a.rc is reported as at least one error and the
        // parse terminates (the test completing at all proves no infinite loop).
        assert!(
            !errs.is_empty(),
            "expected a cycle to be reported as a per-line error"
        );
        std::fs::remove_dir_all(&d).ok();
    }
"""
        proc = _run_injected_rust_test("t", body)
        _assert_cargo_ok(proc)

    def test_indirect_cycle_terminates(self):
        """a->b->c->a (indirect cycle) terminates and reports an error."""
        body = _RUST_HELPERS + r"""
    #[test]
    fn t() {
        let d = scratch();
        writef(&d, "c.rc", "-c\n@a.rc\n");
        writef(&d, "b.rc", "-b\n@c.rc\n");
        let main = writef(&d, "a.rc", "-a\n@b.rc\n");
        let (args, errs) = parse(&main).unwrap();
        assert_eq!(strs(args), vec!["-a", "-b", "-c"]);
        assert!(
            !errs.is_empty(),
            "indirect cycle must be reported as a per-line error"
        );
        std::fs::remove_dir_all(&d).ok();
    }
"""
        proc = _run_injected_rust_test("t", body)
        _assert_cargo_ok(proc)

    def test_diamond_include_duplicates_shared(self):
        """top->{left,right}->shared: shared args appear twice, in order."""
        body = _RUST_HELPERS + r"""
    #[test]
    fn t() {
        let d = scratch();
        writef(&d, "shared.rc", "-s1\n-s2\n");
        writef(&d, "left.rc", "-l\n@shared.rc\n");
        writef(&d, "right.rc", "-r\n@shared.rc\n");
        let main = writef(&d, "top.rc", "@left.rc\n@right.rc\n");
        let (args, errs) = parse(&main).unwrap();
        assert!(errs.is_empty(), "diamond must not error: {:?}", errs);
        assert_eq!(
            strs(args),
            vec!["-l", "-s1", "-s2", "-r", "-s1", "-s2"],
        );
        std::fs::remove_dir_all(&d).ok();
    }
"""
        proc = _run_injected_rust_test("t", body)
        _assert_cargo_ok(proc)

    def test_ordinary_line_one_arg_with_spaces(self):
        """An ordinary line maps to exactly one arg (internal spaces kept)."""
        body = _RUST_HELPERS + r"""
    #[test]
    fn t() {
        let d = scratch();
        // A flag value containing a space but NO trailing " #" comment must
        // remain a single argument verbatim (after outer trim only).
        let main = writef(&d, "main.rc", "  --glob=foo bar  \n");
        let (args, errs) = parse(&main).unwrap();
        assert!(errs.is_empty(), "unexpected errors: {:?}", errs);
        assert_eq!(strs(args), vec!["--glob=foo bar"]);
        std::fs::remove_dir_all(&d).ok();
    }
"""
        proc = _run_injected_rust_test("t", body)
        _assert_cargo_ok(proc)
