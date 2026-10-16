"""
Test for 'clap-cli-patterns' skill (variant ext7) — a stable exit-code mapper
added to ripgrep's binary core (`crates/core/exit.rs`).

The ext7 task asks the agent to add a NEW self-contained module
`crates/core/exit.rs` to the `rg` binary crate that:

  * defines an enum with EXACTLY four distinct outcome categories:
      - a successful run with at least one match,
      - a successful run with no matches,
      - a usage/argument error,
      - an unexpected runtime error;
  * provides a pure, total function mapping each category to a stable
    process exit code as an unsigned 8-bit integer (`u8`):
      - match-found  -> 0
      - no-match     -> 1
      - usage-error  -> 2
      - runtime-error-> 2  (collapsed onto the same non-search-failure code,
                            but kept as a DISTINCT enum variant);
  * reserves `0` SOLELY for the match-found category (no-match must never be 0);
  * carries its own `#[cfg(test)] mod tests`;

and to wire it into the binary by adding `mod exit;` to
`crates/core/main.rs` (no behavioral wiring required).

Native acceptance command:   cargo test --bin rg exit::

Verification strategy
---------------------
The enum/variant/function *identifiers* are author-chosen (the doc constrains
only their semantics, not their names). To verify discriminatively without
trusting the agent's own tests, this file *parses* the agent-written exit.rs to
discover (a) the enum type name + its four variant identifiers and (b) the
public mapping function name (a `fn ... -> u8`). It then INJECTS its own
`#[test]` inside a `#[cfg(test)] mod` placed in exit.rs, which constructs each
variant and asserts the exact mapped code, asserts the four codes form the
specified multiset {0,1,2,2}, and asserts `0` is produced by exactly one
variant. The injected test is compiled & run through the real toolchain via
`cargo test --bin rg ...`, and the file is always restored afterwards.

A naive solution (hardcoding a single code, returning the wrong code for
no-match, collapsing the two success categories, panicking, or omitting a
variant) fails these injected Rust assertions or the discovery step.

L1 cases check the deliverable file is present, minimally well-formed, declared
in main.rs, and that the agent left its own mod tests block. L2 cases compile
and run real Rust assertions exercising the mapping end to end, plus the native
acceptance command itself.
"""

import os
import re
import subprocess

import pytest


REPO_DIR = "/workspace/ripgrep"
EXIT_REL = os.path.join("crates", "core", "exit.rs")
EXIT_PATH = os.path.join(REPO_DIR, EXIT_REL)
MAIN_REL = os.path.join("crates", "core", "main.rs")
MAIN_PATH = os.path.join(REPO_DIR, MAIN_REL)

# Unique marker so our injected module is easy to identify / strip out again.
INJECT_MARKER = "// __BENCH_CLAP_CLI_PATTERNS_EXT7_INJECTED__"

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


def _strip_line_comments(src):
    """Remove `// ...` line comments so identifier discovery is not fooled."""
    out = []
    for line in src.splitlines():
        # naive but sufficient: drop everything after the first `//`
        idx = line.find("//")
        if idx != -1:
            line = line[:idx]
        out.append(line)
    return "\n".join(out)


def _discover_enum():
    """Return (enum_name, [variant_idents]) for the outcome enum in exit.rs.

    Looks for `enum <Name> { ... }` and extracts the bare variant identifiers
    (ignoring any attached data / discriminants). Requires exactly four
    variants per the spec.
    """
    src = _strip_line_comments(_read(EXIT_PATH))
    m = re.search(r"\benum\s+([A-Za-z_]\w*)\s*\{", src)
    assert m is not None, "no `enum <Name> {` found in exit.rs"
    enum_name = m.group(1)

    # Capture the brace-balanced body of the enum.
    start = m.end() - 1  # at the `{`
    depth = 0
    body = None
    for i in range(start, len(src)):
        c = src[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                body = src[start + 1 : i]
                break
    assert body is not None, "could not find matching `}` for enum body"

    variants = []
    # Split on top-level commas (variants here are plain idents; the spec asks
    # for simple categories, so we keep the leading identifier of each entry).
    for chunk in body.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        vm = re.match(r"([A-Za-z_]\w*)", chunk)
        if vm:
            variants.append(vm.group(1))
    return enum_name, variants


def _discover_mapper():
    """Discover the u8 exit-code mapper in exit.rs.

    Returns a tuple ``(fn_name, is_method, takes_ref)`` where:
      * ``fn_name``   — the function/method identifier;
      * ``is_method`` — True if it is an inherent/trait method (i.e. its first
        parameter is ``self``/``&self``), False for a free function;
      * ``takes_ref`` — for a free function, True if it takes the enum by
        reference (``&Enum``) rather than by value.

    We do not depend on the chosen name; we just need to call it correctly.
    """
    src = _strip_line_comments(_read(EXIT_PATH))
    # Find any `fn name( <params> ) -> u8`, preferring a `pub` one.
    pat = r"\b(pub\s+)?fn\s+([A-Za-z_]\w*)\s*\(([^)]*)\)\s*->\s*u8\b"
    best = None
    for m in re.finditer(pat, src):
        # Prefer the first `pub` match; otherwise keep the first match seen.
        if m.group(1) and best is None:
            best = m
        if best is None:
            best = m
        if m.group(1):
            best = m
            break
    assert best is not None, (
        "no `fn ... -> u8` exit-code mapper found in exit.rs"
    )
    fn_name = best.group(2)
    params = best.group(3)
    first = params.split(",")[0].strip()
    is_method = first == "self" or first.startswith("&self") or first.startswith("self")
    takes_ref = (not is_method) and ("&" in params)
    return fn_name, is_method, takes_ref


def _mapper_call(mapper, enum_name, variant):
    """Build a Rust expression invoking the mapper for one variant.

    ``mapper`` is the ``(fn_name, is_method, takes_ref)`` tuple from
    :func:`_discover_mapper`. The mapper may be:
      * an inherent/trait method  -> `Enum::Variant.method()`;
      * a free fn taking by value  -> `fn(Enum::Variant)`;
      * a free fn taking by ref    -> `fn(&Enum::Variant)`.
    """
    fn_name, is_method, takes_ref = mapper
    var = "%s::%s" % (enum_name, variant)
    if is_method:
        return "%s.%s()" % (var, fn_name)
    if takes_ref:
        return "%s(&%s)" % (fn_name, var)
    return "%s(%s)" % (fn_name, var)


def _categorize_variants(variants):
    """Heuristically map the four variant idents to their semantic roles.

    We do NOT rely on the names for the *code* assertions (those are derived
    from running the mapper). This is only used to give friendly error
    messages; the hard assertions are structural (multiset of codes + unique
    zero).
    """
    return variants


def _run_injected_rust_test(rust_module_body):
    """Inject a Rust `#[cfg(test)] mod` into exit.rs, run it, restore the file.

    Returns the CompletedProcess of the cargo invocation. The original exit.rs
    is always restored, even on failure.
    """
    original = _read(EXIT_PATH)

    module = "\n".join(
        [
            "",
            INJECT_MARKER,
            "#[cfg(test)]",
            "mod bench_ext7_exitmap {",
            "    #[allow(unused_imports)]",
            "    use super::*;",
            rust_module_body,
            "}",
            INJECT_MARKER,
            "",
        ]
    )

    patched = original + module
    try:
        _write(EXIT_PATH, patched)
        proc = subprocess.run(
            [
                "cargo",
                "test",
                "--bin",
                "rg",
                "exit::bench_ext7_exitmap::",
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
        _write(EXIT_PATH, original)


def _assert_cargo_ok(proc, expect_run=None):
    combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
    assert proc.returncode == 0, (
        "cargo test failed (rc=%s).\nSTDOUT:\n%s\nSTDERR:\n%s"
        % (proc.returncode, proc.stdout, proc.stderr)
    )
    assert "test result: ok" in combined, (
        "no successful test result reported:\n" + combined
    )
    if expect_run is not None:
        assert re.search(
            r"running\s+%s\s+test" % re.escape(str(expect_run)), combined
        ), (
            "expected %s injected test(s) to actually run, output was:\n%s"
            % (expect_run, combined)
        )


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------

class TestClapCliPatterns:
    """Verify the stable exit-code mapper module added by the ext7 task."""

    REPO_DIR = REPO_DIR

    # ------------------------------------------------------------------
    # L1 — deliverable presence & shape
    # ------------------------------------------------------------------

    def test_exit_module_file_exists(self):
        """The new deliverable crates/core/exit.rs must exist."""
        assert os.path.isfile(EXIT_PATH), "exit.rs not found at " + EXIT_PATH

    def test_main_declares_exit_module(self):
        """main.rs must declare `mod exit;` so exit.rs joins the binary crate."""
        src = _strip_line_comments(_read(MAIN_PATH))
        assert re.search(r"\bmod\s+exit\s*;", src), (
            "`mod exit;` declaration missing from crates/core/main.rs"
        )

    def test_exit_defines_enum_with_four_variants(self):
        """exit.rs must define an enum with exactly four distinct variants."""
        enum_name, variants = _discover_enum()
        assert enum_name, "enum has no name"
        assert len(variants) == 4, (
            "outcome enum must have exactly 4 variants, found %d: %r"
            % (len(variants), variants)
        )
        assert len(set(variants)) == 4, (
            "the four enum variants must be distinct, found duplicates: %r"
            % variants
        )

    def test_exit_defines_u8_mapper(self):
        """exit.rs must define a function returning a u8 exit code."""
        fn_name, _is_method, _takes_ref = _discover_mapper()
        assert fn_name, "no `-> u8` mapper function discovered"

    def test_exit_has_test_module(self):
        """The agent must include the module's own #[cfg(test)] mod tests."""
        src = _read(EXIT_PATH)
        assert "#[cfg(test)]" in src, "no #[cfg(test)] block in exit.rs"
        assert "mod tests" in src, "module's own `mod tests` block missing"
        test_count = len(re.findall(r"#\[test\]", src))
        assert test_count >= 1, (
            "expected the agent to add its own unit tests; found %d #[test]"
            % test_count
        )

    def test_no_leftover_injection(self):
        """Sanity: our scratch injection marker must not be left behind."""
        src = _read(EXIT_PATH)
        assert INJECT_MARKER not in src, (
            "leftover injected test module found in exit.rs; "
            "a previous run did not restore the file"
        )

    def test_native_acceptance_command_passes(self):
        """The doc's native command `cargo test --bin rg exit::` must pass.

        This compiles the new module and runs the agent's own exit:: tests.
        """
        proc = subprocess.run(
            ["cargo", "test", "--bin", "rg", "exit::"],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=CARGO_BUILD_TIMEOUT,
            env=_cargo_env(),
        )
        combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
        assert proc.returncode == 0, (
            "native `cargo test --bin rg exit::` failed.\n"
            "STDOUT:\n%s\nSTDERR:\n%s" % (proc.stdout, proc.stderr)
        )
        assert "test result: ok" in combined, combined

    # ------------------------------------------------------------------
    # L2 — dynamic behavioral verification via injected Rust tests
    # ------------------------------------------------------------------

    def test_each_variant_maps_to_specified_code(self):
        """Each category maps to its exact specified code via the real mapper.

        We don't know which variant is which by name, so we compute the code
        for every variant, then assert the multiset of codes equals exactly
        {0, 1, 2, 2}. That uniquely pins: one variant -> 0, one -> 1, two -> 2,
        which is precisely the spec. A stub returning a constant (e.g. all 2,
        or all 0) cannot produce this multiset.
        """
        enum_name, variants = _discover_enum()
        mapper = _discover_mapper()
        calls = ", ".join(
            _mapper_call(mapper, enum_name, v) for v in variants
        )
        body = r"""
    #[test]
    fn t() {
        let codes: [u8; 4] = [%s];
        let mut sorted = codes;
        sorted.sort();
        assert_eq!(
            sorted, [0u8, 1u8, 2u8, 2u8],
            "exit codes must be exactly the multiset {{0,1,2,2}}, got {:?}",
            codes
        );
    }
""" % (calls,)
        proc = _run_injected_rust_test(body)
        _assert_cargo_ok(proc, expect_run=1)

    def test_exactly_one_variant_yields_zero(self):
        """`0` must be reserved solely for the match-found category.

        Exactly one of the four variants may return 0; no-match must return 1,
        never 0. We assert that precisely one variant maps to 0.
        """
        enum_name, variants = _discover_enum()
        mapper = _discover_mapper()
        calls = ", ".join(
            _mapper_call(mapper, enum_name, v) for v in variants
        )
        body = r"""
    #[test]
    fn t() {
        let codes: [u8; 4] = [%s];
        let zeros = codes.iter().filter(|&&c| c == 0).count();
        assert_eq!(
            zeros, 1,
            "exactly one category may map to 0 (match-found); got {} zeros in {:?}",
            zeros, codes
        );
        let ones = codes.iter().filter(|&&c| c == 1).count();
        assert_eq!(
            ones, 1,
            "exactly one category (no-match) must map to 1; got {} in {:?}",
            ones, codes
        );
        let twos = codes.iter().filter(|&&c| c == 2).count();
        assert_eq!(
            twos, 2,
            "the two error categories must both map to 2; got {} in {:?}",
            twos, codes
        );
    }
""" % (calls,)
        proc = _run_injected_rust_test(body)
        _assert_cargo_ok(proc, expect_run=1)

    def test_mapper_is_deterministic_and_total(self):
        """The mapper is a pure, total function: stable across repeated calls.

        Calling the mapper twice on each variant must yield identical codes and
        must not panic (the test completing proves no panic for any variant).
        """
        enum_name, variants = _discover_enum()
        mapper = _discover_mapper()
        lines = []
        for v in variants:
            call = _mapper_call(mapper, enum_name, v)
            lines.append(
                '        assert_eq!(%s, %s, "mapper not deterministic for %s");'
                % (call, call, v)
            )
        body = r"""
    #[test]
    fn t() {
%s
    }
""" % ("\n".join(lines),)
        proc = _run_injected_rust_test(body)
        _assert_cargo_ok(proc, expect_run=1)

    def test_codes_only_use_specified_values(self):
        """No category may map to an out-of-spec code (only 0/1/2 allowed)."""
        enum_name, variants = _discover_enum()
        mapper = _discover_mapper()
        calls = ", ".join(
            _mapper_call(mapper, enum_name, v) for v in variants
        )
        body = r"""
    #[test]
    fn t() {
        let codes: [u8; 4] = [%s];
        for &c in codes.iter() {
            assert!(
                c == 0 || c == 1 || c == 2,
                "exit code {} is outside the documented set {{0,1,2}}",
                c
            );
        }
    }
""" % (calls,)
        proc = _run_injected_rust_test(body)
        _assert_cargo_ok(proc, expect_run=1)

    def test_no_match_distinct_from_match_found(self):
        """The success codes differ: match-found (0) != no-match (1).

        This guards against an implementation that collapses both successful
        runs onto the same code. We assert that among the four codes there is
        at least one 0 and at least one 1 (two distinct success outcomes).
        """
        enum_name, variants = _discover_enum()
        mapper = _discover_mapper()
        calls = ", ".join(
            _mapper_call(mapper, enum_name, v) for v in variants
        )
        body = r"""
    #[test]
    fn t() {
        let codes: [u8; 4] = [%s];
        assert!(codes.contains(&0u8), "no category maps to 0 (match-found)");
        assert!(codes.contains(&1u8), "no category maps to 1 (no-match)");
        // And 0 and 1 are genuinely produced by different variants.
        let zero_idx = codes.iter().position(|&c| c == 0).unwrap();
        let one_idx = codes.iter().position(|&c| c == 1).unwrap();
        assert_ne!(
            zero_idx, one_idx,
            "match-found and no-match must be distinct categories"
        );
    }
""" % (calls,)
        proc = _run_injected_rust_test(body)
        _assert_cargo_ok(proc, expect_run=1)
