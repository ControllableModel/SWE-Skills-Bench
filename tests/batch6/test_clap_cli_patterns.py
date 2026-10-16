"""
Test for 'clap-cli-patterns' skill (variant ext6) — a layered config-precedence
resolver added to ripgrep's flags module.

The ext6 task asks the agent to add a NEW self-contained module
`crates/core/flags/precedence.rs` exposing a *pure* function that resolves a
single string-valued setting from three optional layered sources plus a
default, with the fixed precedence:

    command-line  >  environment-style  >  config-file  >  default

Only the `None` variant counts as "absent"; a `Some("")` (empty string) is a
present value that still wins over lower layers. The resolver must read no
process environment, files, or global state. The new module must be declared in
`crates/core/flags/mod.rs` and ship its own `#[cfg(test)] mod tests`.

Native acceptance command (from the requirement doc):

    cargo test --bin rg flags::precedence::

Verification strategy
----------------------
* L1 — the deliverable file exists, is wired into `mod.rs`, exposes exactly one
  public resolver with three `Option`-typed layered parameters plus a default,
  carries its own `#[cfg(test)] mod tests`, and the resolver does NOT read any
  external state (no `std::env::var`, file IO, or global mutable state inside
  the module).
* L2 — discriminative *dynamic* verification.  The resolver lives in the private
  `flags` module of the `rg` binary crate, so it cannot be called from an
  external integration test.  Instead, this harness DETECTS the agent's public
  function name and its parameter/return *shape* by parsing the file, then
  INJECTS its own `#[cfg(test)]` module into `precedence.rs` that calls the real
  function with the doc's scenarios and asserts the exact effective value.  The
  injected module is run through the native toolchain and the file is always
  restored afterwards.  A naive implementation (returns the default, ignores a
  layer, treats `Some("")` as absent, or wires precedence in the wrong order)
  fails these injected Rust assertions.
"""

import os
import re
import subprocess

import pytest


REPO_DIR = "/workspace/ripgrep"
PRECEDENCE_REL = os.path.join("crates", "core", "flags", "precedence.rs")
PRECEDENCE_PATH = os.path.join(REPO_DIR, PRECEDENCE_REL)
MOD_REL = os.path.join("crates", "core", "flags", "mod.rs")
MOD_PATH = os.path.join(REPO_DIR, MOD_REL)

# Unique marker so our injected module is easy to identify / strip out again.
INJECT_MARKER = "// __BENCH_CLAP_CLI_PATTERNS_EXT6_INJECTED__"

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
    # Deterministic: explicitly DROP any env that a buggy "pure" resolver might
    # accidentally read, so a non-pure impl cannot pass by luck.
    for k in list(env.keys()):
        if k.startswith("BENCH_PRECEDENCE_"):
            del env[k]
    return env


def _require_precedence_file():
    if not os.path.isfile(PRECEDENCE_PATH):
        pytest.fail("precedence.rs not found at " + PRECEDENCE_PATH)


# --- signature detection ----------------------------------------------------

def _strip_comments(src):
    # Remove // line comments and /* */ block comments (good enough for sig scan).
    src = re.sub(r"/\*.*?\*/", " ", src, flags=re.S)
    src = re.sub(r"//[^\n]*", "", src)
    return src


def _find_resolver():
    """Return (fn_name, params, ret) for the agent's public resolver.

    params is a list of the raw type strings of each parameter (in order).
    ret is the raw return type string ('' if none / unit).

    We pick the public `fn` whose parameter list contains at least three
    `Option<...>` parameters — that is the layered resolver described by the
    doc.  This is robust to the agent naming it `resolve`, `effective`, etc.
    """
    src = _strip_comments(_read(PRECEDENCE_PATH))
    candidates = []
    # Match: pub [(crate)] fn NAME ( ARGS ) [-> RET] {
    pat = re.compile(
        r"\bpub(?:\s*\([^)]*\))?\s+fn\s+([A-Za-z_][A-Za-z0-9_]*)\s*"
        r"(?:<[^>]*>\s*)?"           # optional generics
        r"\(([^)]*)\)"               # param list (no nested parens expected)
        r"\s*(?:->\s*([^\{;]+?))?\s*\{",
        re.S,
    )
    for m in pat.finditer(src):
        name, raw_params, ret = m.group(1), m.group(2), (m.group(3) or "")
        params = []
        if raw_params.strip():
            for chunk in _split_params(raw_params):
                # chunk looks like `name: Type` or just `Type`
                if ":" in chunk:
                    ty = chunk.split(":", 1)[1].strip()
                else:
                    ty = chunk.strip()
                params.append(ty)
        opt_count = sum(1 for p in params if p.startswith("Option"))
        if opt_count >= 3:
            candidates.append((name, params, ret.strip(), opt_count))
    if not candidates:
        pytest.fail(
            "could not find a public resolver fn taking >=3 Option<..> params "
            "in precedence.rs; signatures present:\n"
            + "\n".join(
                m.group(0)[:120] for m in pat.finditer(src)
            )
        )
    # Prefer the one with the most Option params (the 3 layered sources).
    candidates.sort(key=lambda c: -c[3])
    name, params, ret, _ = candidates[0]
    return name, params, ret


def _split_params(raw):
    """Split a parameter list on top-level commas (respecting <...> nesting)."""
    out, depth, cur = [], 0, ""
    for ch in raw:
        if ch in "<([":
            depth += 1
        elif ch in ">)]":
            depth -= 1
        if ch == "," and depth == 0:
            out.append(cur)
            cur = ""
        else:
            cur += ch
    if cur.strip():
        out.append(cur)
    return out


def _opt_arg_expr(param_type, value):
    """Build a Rust expression for an Option<...> parameter.

    `value` is either None (-> Rust `None`) or a python str (-> Some(<lit>)).
    We adapt the inner literal to the declared inner type so it type-checks for
    Option<&str>, Option<String>, Option<&String>, Option<Cow<str>>, etc.
    """
    if value is None:
        return "None"
    lit = _str_literal(param_type, value)
    return "Some(%s)" % lit


def _str_literal(rust_type, value):
    """Produce a Rust string-ish literal matching `rust_type`'s inner element."""
    inner = rust_type
    m = re.match(r"Option\s*<(.+)>\s*$", rust_type.strip(), re.S)
    if m:
        inner = m.group(1).strip()
    esc = value.replace("\\", "\\\\").replace('"', '\\"')
    base = '"%s"' % esc
    inner_l = inner.lower()
    if "string" in inner_l and "&" not in inner_l:
        # owned String
        return "String::from(%s)" % base
    if "cow" in inner_l:
        return "std::borrow::Cow::Borrowed(%s)" % base
    # &str / &String / str — borrowed literal works (&String coerces rarely;
    # treat &String like &str via base, which is the common case).
    return base


def _default_arg_expr(param_type, value):
    """Build the default-argument expression for the last positional param."""
    return _str_literal(param_type, value)


def _build_call(scenario):
    """Build a Rust expression calling the resolver for one scenario.

    scenario = (cli, env, file, default) where each of cli/env/file is None or
    a str, and default is a str.
    """
    name, params, ret = _find_resolver()
    cli, env, fil, default = scenario

    # The three layered Option params are, by the doc, in precedence order
    # cli > env > file.  We map them onto the first three Option-typed params
    # in declaration order.  The default is the first NON-Option param (if any),
    # otherwise appended is not possible — fail loudly.
    opt_indices = [i for i, p in enumerate(params) if p.startswith("Option")]
    non_opt_indices = [i for i, p in enumerate(params) if not p.startswith("Option")]
    if len(opt_indices) < 3:
        pytest.fail("resolver has fewer than 3 Option params: %r" % (params,))

    args = [None] * len(params)
    layered = [cli, env, fil]
    for slot, idx in zip(layered, opt_indices[:3]):
        args[idx] = _opt_arg_expr(params[idx], slot)

    if non_opt_indices:
        didx = non_opt_indices[0]
        args[didx] = _default_arg_expr(params[didx], default)
    else:
        pytest.fail(
            "resolver has no non-Option default parameter: %r" % (params,)
        )

    # Any remaining unfilled Option slots (>3) default to None.
    for i, a in enumerate(args):
        if a is None:
            if params[i].startswith("Option"):
                args[i] = "None"
            else:
                args[i] = _default_arg_expr(params[i], default)

    call = "super::%s(%s)" % (name, ", ".join(args))
    return call, ret


def _run_injected(test_body):
    """Inject `test_body` as a #[cfg(test)] module into precedence.rs, run it."""
    _require_precedence_file()
    original = _read(PRECEDENCE_PATH)
    module = "\n".join(
        [
            "",
            INJECT_MARKER,
            "#[cfg(test)]",
            "mod bench_precedence_ext6 {",
            test_body,
            "}",
            INJECT_MARKER,
            "",
        ]
    )
    patched = original + module
    try:
        _write(PRECEDENCE_PATH, patched)
        proc = subprocess.run(
            [
                "cargo",
                "test",
                "--bin",
                "rg",
                "flags::precedence::bench_precedence_ext6::",
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
        _write(PRECEDENCE_PATH, original)


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
            "expected %s injected test(s) to actually run, output:\n%s"
            % (expect_run, combined)
        )


def _assert_value(scenario, expected):
    """Inject a single #[test] asserting the resolver returns `expected`."""
    call, _ret = _build_call(scenario)
    exp = expected.replace("\\", "\\\\").replace('"', '\\"')
    body = (
        "    #[test]\n"
        "    fn t() {\n"
        "        let got = %s;\n"
        "        let got_s: String = got.to_string();\n"
        "        assert_eq!(got_s, \"%s\".to_string(),\n"
        "            \"resolver returned {:?}, expected %s\", got_s);\n"
        "    }\n"
    ) % (call, exp, exp)
    proc = _run_injected(body)
    _assert_cargo_ok(proc, expect_run=1)


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------

class TestClapCliPatterns:
    """Verify the layered config-precedence resolver (ext6 variant)."""

    REPO_DIR = REPO_DIR

    # ------------------------------------------------------------------
    # L1 — deliverable presence & shape
    # ------------------------------------------------------------------

    def test_precedence_file_exists(self):
        """The new module crates/core/flags/precedence.rs must exist."""
        assert os.path.isfile(PRECEDENCE_PATH), (
            "precedence.rs not found at " + PRECEDENCE_PATH
        )

    def test_module_declared_in_mod_rs(self):
        """mod.rs must declare `mod precedence;` so it compiles into the crate."""
        assert os.path.isfile(MOD_PATH), "mod.rs missing at " + MOD_PATH
        src = _strip_comments(_read(MOD_PATH))
        assert re.search(r"\bmod\s+precedence\s*;", src), (
            "mod.rs does not declare the new `precedence` module; "
            "found mod declarations:\n"
            + "\n".join(re.findall(r"\b(?:pub\s+)?mod\s+\w+\s*;", src))
        )

    def test_resolver_signature_is_layered(self):
        """A public resolver taking >=3 Option params + a default must exist."""
        _require_precedence_file()
        name, params, ret = _find_resolver()
        opt = [p for p in params if p.startswith("Option")]
        assert len(opt) >= 3, (
            "resolver %s should take three Option<..> layered sources, got %r"
            % (name, params)
        )
        non_opt = [p for p in params if not p.startswith("Option")]
        assert len(non_opt) >= 1, (
            "resolver %s should take a non-Option default parameter, got %r"
            % (name, params)
        )

    def test_module_has_test_block(self):
        """precedence.rs must ship its own #[cfg(test)] mod tests with tests."""
        src = _read(PRECEDENCE_PATH)
        assert "#[cfg(test)]" in src, "no #[cfg(test)] block in precedence.rs"
        assert re.search(r"\bmod\s+tests\b", src), (
            "precedence.rs missing its own `mod tests` block"
        )
        test_count = len(re.findall(r"#\[test\]", src))
        assert test_count >= 3, (
            "expected the module to carry its own unit tests; "
            "only %d #[test] found" % test_count
        )

    def test_resolver_is_pure_no_external_state(self):
        """The resolver module must not read env / files / global state."""
        src = _strip_comments(_read(PRECEDENCE_PATH))
        # Strip out the agent's own #[cfg(test)] test module — those tests may
        # legitimately set up scenarios; purity applies to the resolver code.
        idx = src.find("mod tests")
        prod = src[:idx] if idx != -1 else src
        forbidden = [
            r"std::env::var",
            r"std::env::vars",
            r"env::var\b",
            r"std::fs::",
            r"File::open",
            r"::read_to_string",
            r"OpenOptions",
        ]
        hits = [pat for pat in forbidden if re.search(pat, prod)]
        assert not hits, (
            "resolver module appears to read external state (must be a pure "
            "function of its inputs); matched: %r" % hits
        )

    def test_no_leftover_injection(self):
        """Sanity: our scratch injection marker must not be committed."""
        src = _read(PRECEDENCE_PATH)
        assert INJECT_MARKER not in src, (
            "leftover injected test module in precedence.rs; a previous run "
            "did not restore the file"
        )

    # ------------------------------------------------------------------
    # L2 — dynamic behavioral verification via injected Rust tests
    # ------------------------------------------------------------------

    def test_agent_unit_tests_pass(self):
        """The agent's own precedence unit tests must pass (native command)."""
        proc = subprocess.run(
            ["cargo", "test", "--bin", "rg", "flags::precedence::"],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=CARGO_BUILD_TIMEOUT,
            env=_cargo_env(),
        )
        combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
        assert proc.returncode == 0, (
            "native `cargo test --bin rg flags::precedence::` failed.\n"
            "STDOUT:\n%s\nSTDERR:\n%s" % (proc.stdout, proc.stderr)
        )
        assert "test result: ok" in combined, combined
        # The filter must actually have matched the module's tests.
        assert re.search(r"running\s+[1-9]\d*\s+test", combined), (
            "no precedence tests were executed by the native command:\n"
            + combined
        )

    def test_cli_wins_over_all(self):
        """cli=Some(a), env=Some(b), file=Some(c), default=d -> a."""
        _assert_value(("a", "b", "c", "d"), "a")

    def test_env_wins_when_cli_absent(self):
        """cli=None, env=Some(b), file=Some(c), default=d -> b."""
        _assert_value((None, "b", "c", "d"), "b")

    def test_file_wins_when_cli_env_absent(self):
        """cli=None, env=None, file=Some(c), default=d -> c."""
        _assert_value((None, None, "c", "d"), "c")

    def test_default_when_all_absent(self):
        """cli=None, env=None, file=None, default=d -> d."""
        _assert_value((None, None, None, "d"), "d")

    def test_empty_string_is_present_and_wins(self):
        """cli=Some(\"\"), env=Some(b), file=None, default=d -> \"\" (present)."""
        _assert_value(("", "b", None, "d"), "")

    def test_empty_env_wins_over_file_and_default(self):
        """A present empty env value beats a present file value and default."""
        _assert_value((None, "", "c", "d"), "")

    def test_higher_layer_overrides_lower_when_both_present(self):
        """env present beats file present when cli absent (no fall-through)."""
        _assert_value((None, "ENV", "FILE", "DEF"), "ENV")

    def test_fallthrough_skips_absent_middle_layer(self):
        """cli absent, env absent -> falls through to present file value."""
        _assert_value((None, None, "FILE", "DEF"), "FILE")
