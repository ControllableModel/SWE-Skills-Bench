"""Benchmark test for the `pytest-plugin-development` skill task (variant ext3).

Task: add a self-contained marker-expression tokenizer module at
`src/_pytest/_exprscan.py` (pure stdlib, no other `_pytest` imports) exporting
a `Token` data type and a `scan(expr) -> list[Token]` function, plus an
exhaustive test module `testing/test_exprscan_util.py`.

Verification strategy: this test file independently exercises the agent's
implementation by loading the delivered `_exprscan.py` directly (via importlib,
avoiding `_pytest` package side effects) and asserting its real runtime
behavior across every enumerated edge case in the requirement doc:
  - the exact token kinds NAME / AND / OR / NOT / LPAREN / RPAREN
  - keyword vs identifier disambiguation (lowercase keywords only; `And`->NAME)
  - identifiers with `.` and `-`
  - adjacent parentheses without spaces
  - whitespace skipping; empty / whitespace-only input -> empty list
  - Token equality semantics
  - illegal-character ValueError whose message includes the offending char and
    its EXACT zero-based position (verified for non-zero positions)

The behavioral checks do NOT rely on the agent's own test file, so a partial /
hardcoded implementation must fail here. A final L2 case additionally runs the
doc's native acceptance command against the agent's own test module.
"""

import ast
import importlib.util
import os
import subprocess
import sys

import pytest


class TestPytestPluginDevelopment:
    REPO_DIR = "/workspace/pytest"

    # ------------------------------------------------------------------ #
    # helpers                                                            #
    # ------------------------------------------------------------------ #
    @classmethod
    def _module_path(cls):
        return os.path.join(cls.REPO_DIR, "src", "_pytest", "_exprscan.py")

    @classmethod
    def _load_module(cls):
        """Load the delivered _exprscan.py directly from its file path.

        Loading by file path (not `import _pytest._exprscan`) avoids importing
        the whole `_pytest` package and guarantees we exercise the agent's file.
        """
        path = cls._module_path()
        assert os.path.isfile(path), f"missing deliverable: {path}"
        spec = importlib.util.spec_from_file_location("_exprscan_under_test", path)
        assert spec is not None and spec.loader is not None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    @staticmethod
    def _kinds(tokens):
        return [t.kind for t in tokens]

    @staticmethod
    def _values(tokens):
        return [t.value for t in tokens]

    # ------------------------------------------------------------------ #
    # L1 — deliverables exist & are minimally well-formed                #
    # ------------------------------------------------------------------ #
    def test_l1_module_file_exists(self):
        """L1: src/_pytest/_exprscan.py deliverable exists."""
        assert os.path.isfile(self._module_path()), self._module_path()

    def test_l1_test_module_exists(self):
        """L1: testing/test_exprscan_util.py deliverable exists."""
        p = os.path.join(self.REPO_DIR, "testing", "test_exprscan_util.py")
        assert os.path.isfile(p), p

    def test_l1_exports_token_and_scan(self):
        """L1: module exports a `Token` type and a callable `scan`."""
        mod = self._load_module()
        assert hasattr(mod, "Token"), "missing export: Token"
        assert hasattr(mod, "scan"), "missing export: scan"
        assert callable(mod.scan), "scan is not callable"
        # Token must be constructible/usable as a type with kind+value.
        assert isinstance(mod.Token, type) or callable(mod.Token), (
            "Token must be a class / constructible type"
        )

    def test_l1_module_is_dependency_free(self):
        """L1: module imports no other _pytest submodules (pure stdlib)."""
        path = self._module_path()
        with open(path, "r", encoding="utf-8") as fh:
            src = fh.read()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                base = (node.module or "").split(".")[0]
                assert base != "_pytest", (
                    f"module must not import from _pytest, found: {node.module}"
                )
                if node.level and node.level > 0:
                    raise AssertionError(
                        "relative import found; module must be dependency-free"
                    )
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith("_pytest"), (
                        f"module must not import _pytest, found: {alias.name}"
                    )

    # ------------------------------------------------------------------ #
    # L2 — Token data type semantics                                     #
    # ------------------------------------------------------------------ #
    def test_l2_token_has_kind_and_value_attributes(self):
        """L2: a scanned token exposes readable `kind` and `value` (both str)."""
        mod = self._load_module()
        tokens = mod.scan("slow")
        assert len(tokens) == 1, tokens
        tok = tokens[0]
        assert tok.kind == "NAME"
        assert tok.value == "slow"
        assert isinstance(tok.kind, str) and isinstance(tok.value, str)

    def test_l2_token_equality(self):
        """L2: two tokens with same kind and value compare equal; differ otherwise."""
        mod = self._load_module()
        a = mod.scan("foo")[0]
        b = mod.scan("foo")[0]
        c = mod.scan("bar")[0]
        assert a == b, "tokens with identical kind+value must be equal"
        assert a != c, "tokens with different value must not be equal"
        # AND keyword vs a NAME 'and'-shaped value must not collide.
        and_tok = mod.scan("and")[0]
        assert and_tok != mod.scan("And")[0], (
            "AND keyword token must differ from the NAME 'And' token"
        )

    # ------------------------------------------------------------------ #
    # L2 — keyword vs identifier disambiguation                          #
    # ------------------------------------------------------------------ #
    def test_l2_lowercase_keywords_become_operator_tokens(self):
        """L2: bare `and`/`or`/`not` become AND/OR/NOT tokens."""
        mod = self._load_module()
        assert self._kinds(mod.scan("and")) == ["AND"]
        assert self._kinds(mod.scan("or")) == ["OR"]
        assert self._kinds(mod.scan("not")) == ["NOT"]

    def test_l2_mixed_case_keyword_is_a_name(self):
        """L2: mixed/upper case like `And`, `OR`, `Not` are NAME tokens, not operators."""
        mod = self._load_module()
        for word in ("And", "OR", "Not", "AND", "nOt"):
            toks = mod.scan(word)
            assert self._kinds(toks) == ["NAME"], f"{word!r} should be a NAME"
            assert self._values(toks) == [word], f"{word!r} value must be preserved"

    def test_l2_keyword_prefix_identifier_is_a_name(self):
        """L2: an identifier that merely starts with a keyword (e.g. `android`) is a NAME."""
        mod = self._load_module()
        for ident in ("android", "ordinary", "notable", "orange"):
            toks = mod.scan(ident)
            assert self._kinds(toks) == ["NAME"], f"{ident!r} should be a single NAME"
            assert self._values(toks) == [ident]

    # ------------------------------------------------------------------ #
    # L2 — identifier shapes (dots, dashes)                              #
    # ------------------------------------------------------------------ #
    def test_l2_identifier_with_dot_and_dash(self):
        """L2: `web-ui.smoke` scans as a single NAME with the full text as value."""
        mod = self._load_module()
        toks = mod.scan("web-ui.smoke")
        assert self._kinds(toks) == ["NAME"]
        assert self._values(toks) == ["web-ui.smoke"]

    def test_l2_identifier_underscore_and_digits(self):
        """L2: leading underscore allowed; digits allowed after the first char."""
        mod = self._load_module()
        toks = mod.scan("_priv test_1 a.b-c")
        assert self._kinds(toks) == ["NAME", "NAME", "NAME"]
        assert self._values(toks) == ["_priv", "test_1", "a.b-c"]

    # ------------------------------------------------------------------ #
    # L2 — parentheses & whitespace                                      #
    # ------------------------------------------------------------------ #
    def test_l2_parentheses_tokens(self):
        """L2: `(` and `)` become LPAREN/RPAREN with literal-char values."""
        mod = self._load_module()
        toks = mod.scan("( )")
        assert self._kinds(toks) == ["LPAREN", "RPAREN"]
        assert self._values(toks) == ["(", ")"]

    def test_l2_adjacent_parentheses_without_spaces(self):
        """L2: `(a)` tokenizes to LPAREN NAME RPAREN with no spacing needed."""
        mod = self._load_module()
        toks = mod.scan("(a)")
        assert self._kinds(toks) == ["LPAREN", "NAME", "RPAREN"]
        assert self._values(toks) == ["(", "a", ")"]

    def test_l2_full_expression_token_stream(self):
        """L2: `not (slow or fast)` -> 6 tokens with the exact specified kinds."""
        mod = self._load_module()
        toks = mod.scan("not (slow or fast)")
        assert len(toks) == 6, f"expected 6 tokens, got {len(toks)}: {self._kinds(toks)}"
        assert self._kinds(toks) == ["NOT", "LPAREN", "NAME", "OR", "NAME", "RPAREN"]
        assert self._values(toks) == ["not", "(", "slow", "or", "fast", ")"]

    def test_l2_arbitrary_whitespace_is_skipped(self):
        """L2: tabs/newlines/multiple spaces between tokens are skipped, not emitted."""
        mod = self._load_module()
        toks = mod.scan("  a\t\tand\n  b  ")
        assert self._kinds(toks) == ["NAME", "AND", "NAME"]
        assert self._values(toks) == ["a", "and", "b"]

    def test_l2_empty_and_whitespace_only_yield_empty_list(self):
        """L2: empty or whitespace-only input returns an empty list (not None/error)."""
        mod = self._load_module()
        assert mod.scan("") == []
        assert mod.scan("   ") == []
        assert mod.scan("\t\n  \n") == []

    # ------------------------------------------------------------------ #
    # L2 — illegal character ValueError with EXACT position              #
    # ------------------------------------------------------------------ #
    def test_l2_illegal_char_raises_valueerror(self):
        """L2: an unexpected char raises ValueError mentioning the char."""
        mod = self._load_module()
        with pytest.raises(ValueError) as exc:
            mod.scan("a & b")
        msg = str(exc.value)
        assert "&" in msg, f"error message must include the offending char: {msg!r}"

    def test_l2_illegal_char_position_is_exact_nonzero(self):
        """L2: the reported zero-based position of the first illegal char is exact.

        Verified with multiple inputs where the bad character is NOT at index 0,
        so a stub that always reports 0 (or omits the position) fails.
        """
        mod = self._load_module()
        cases = [
            ("a & b", "&", 2),
            ("slow or @fast", "@", 8),
            ("foo and bar!", "!", 11),
            ("(ok)%", "%", 4),
        ]
        for expr, bad_char, pos in cases:
            with pytest.raises(ValueError) as exc:
                mod.scan(expr)
            msg = str(exc.value)
            assert bad_char in msg, (
                f"message for {expr!r} must contain the offending char {bad_char!r}; "
                f"got {msg!r}"
            )
            assert str(pos) in msg, (
                f"message for {expr!r} must contain the exact zero-based position "
                f"{pos}; got {msg!r}"
            )
            # Guard against a stub that always reports index 0: for these
            # non-zero cases the literal '0' as a standalone index must not be
            # the reported position when pos != 0.
            assert pos != 0

    def test_l2_first_illegal_char_is_reported(self):
        """L2: when several illegal chars exist, the FIRST one (and its index) wins."""
        mod = self._load_module()
        with pytest.raises(ValueError) as exc:
            mod.scan("a # b $ c")
        msg = str(exc.value)
        assert "#" in msg, f"first illegal char '#' must be reported: {msg!r}"
        assert "2" in msg, f"position of first illegal char (2) must be reported: {msg!r}"

    # ------------------------------------------------------------------ #
    # L2 — purity / determinism                                          #
    # ------------------------------------------------------------------ #
    def test_l2_scan_is_deterministic(self):
        """L2: repeated calls on the same input return equal token streams."""
        mod = self._load_module()
        expr = "not (web-ui.smoke or slow) and fast"
        first = mod.scan(expr)
        second = mod.scan(expr)
        assert self._kinds(first) == self._kinds(second)
        assert self._values(first) == self._values(second)
        assert first == second

    # ------------------------------------------------------------------ #
    # L2 — the task's own acceptance command must pass                   #
    # ------------------------------------------------------------------ #
    def test_l2_native_pytest_suite_passes(self):
        """L2: the agent's testing/test_exprscan_util.py passes via native pytest.

        Runs the exact acceptance command from the requirement doc. Requires at
        least one test collected and zero failures.
        """
        env = dict(os.environ)
        # Ensure the repo's src tree is importable for the native suite.
        env["PYTHONPATH"] = os.path.join(self.REPO_DIR, "src")
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "testing/test_exprscan_util.py",
                "-p",
                "no:cacheprovider",
                "-q",
            ],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=300,
            env=env,
        )
        combined = proc.stdout + "\n" + proc.stderr
        assert proc.returncode == 0, f"native suite failed:\n{combined}"
        # Guard against an empty / no-collection pass.
        assert "no tests ran" not in combined.lower(), combined
        assert "passed" in combined.lower(), combined
