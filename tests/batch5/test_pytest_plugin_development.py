"""Benchmark test for the `pytest-plugin-development` skill task (variant ext5).

Task: add a self-contained INI-style option-value coercion utility module at
`src/_pytest/_inivalue.py` (pure stdlib, no other `_pytest` imports) exporting
exactly four public callables -- `to_bool`, `to_int`, `to_list`, and
`to_path_list` -- plus an exhaustive test module `testing/test_inivalue_util.py`.

Verification strategy:
  * L1 checks that both deliverables exist, that the module exports the four
    required callables, and that the module is genuinely dependency-free (no
    `_pytest` imports, no third-party packages) by AST-inspecting its source.
  * L2 loads the delivered `_inivalue.py` DIRECTLY from its file path via
    importlib (avoiding `_pytest` package side effects) and exercises the real
    runtime behaviour across every enumerated edge case: the full truthy/falsey
    vocabularies and the error case for `to_bool`; empty->default vs
    malformed->error (even with a default) plus sign/whitespace handling for
    `to_int`; both split modes, empty-item dropping and empty-input handling for
    `to_list`; and absolute-passthrough, order-preserving dedup, `.`/`//`
    collapse and `..`-preservation for `to_path_list`. These checks do NOT trust
    the agent's own test file, so a partial / hardcoded implementation must fail.
  * The final L2 case drives the task's native acceptance command on the agent's
    own test module to confirm it collects and passes.

Native acceptance command:
    python -m pytest testing/test_inivalue_util.py -p no:cacheprovider -q
"""

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
        return os.path.join(cls.REPO_DIR, "src", "_pytest", "_inivalue.py")

    @classmethod
    def _load_module(cls):
        """Load the delivered _inivalue.py directly from its file path.

        Loading by file path (not `import _pytest._inivalue`) avoids importing
        the whole `_pytest` package and guarantees we exercise the agent's file.
        """
        path = cls._module_path()
        assert os.path.isfile(path), f"missing deliverable: {path}"
        spec = importlib.util.spec_from_file_location("_inivalue_under_test", path)
        assert spec is not None and spec.loader is not None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    # ------------------------------------------------------------------ #
    # L1 — deliverables exist & are minimally well-formed                #
    # ------------------------------------------------------------------ #
    def test_l1_module_file_exists(self):
        """L1: src/_pytest/_inivalue.py deliverable exists."""
        assert os.path.isfile(self._module_path()), self._module_path()

    def test_l1_test_module_exists(self):
        """L1: testing/test_inivalue_util.py deliverable exists."""
        p = os.path.join(self.REPO_DIR, "testing", "test_inivalue_util.py")
        assert os.path.isfile(p), p

    def test_l1_exports_four_public_callables(self):
        """L1: module exports the four required callables."""
        mod = self._load_module()
        for name in ("to_bool", "to_int", "to_list", "to_path_list"):
            assert hasattr(mod, name), f"missing export: {name}"
            assert callable(getattr(mod, name)), f"{name} is not callable"

    def test_l1_module_is_dependency_free(self):
        """L1: module imports no other _pytest submodules and no third-party pkgs."""
        path = self._module_path()
        with open(path, "r", encoding="utf-8") as fh:
            src = fh.read()
        import ast

        # stdlib top-level modules the module is permitted to import.
        allowed_stdlib = {
            "__future__",
            "re",
            "os",
            "posixpath",
            "string",
            "typing",
            "collections",
            "itertools",
            "functools",
        }
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
                assert base in allowed_stdlib, (
                    f"unexpected non-stdlib import: from {node.module} ..."
                )
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    assert not alias.name.startswith("_pytest"), (
                        f"module must not import _pytest, found: {alias.name}"
                    )
                    assert top in allowed_stdlib, (
                        f"unexpected non-stdlib import: {alias.name}"
                    )

    # ------------------------------------------------------------------ #
    # L2 — to_bool                                                       #
    # ------------------------------------------------------------------ #
    def test_l2_to_bool_truthy_vocabulary(self):
        """L2: every truthy token (case-insensitive, whitespace-padded) -> True."""
        mod = self._load_module()
        for tok in ("1", "true", "yes", "on"):
            for variant in (tok, tok.upper(), tok.capitalize(), f"  {tok} ", f"\t{tok}\n"):
                res = mod.to_bool(variant)
                assert res is True or res == True, f"to_bool({variant!r}) -> {res!r}"

    def test_l2_to_bool_falsey_vocabulary(self):
        """L2: every falsey token (case-insensitive, whitespace-padded) -> False."""
        mod = self._load_module()
        for tok in ("0", "false", "no", "off"):
            for variant in (tok, tok.upper(), tok.capitalize(), f"  {tok} ", f"\t{tok}\n"):
                res = mod.to_bool(variant)
                assert res is False or res == False, f"to_bool({variant!r}) -> {res!r}"

    def test_l2_to_bool_rejects_unknown(self):
        """L2: any other value raises ValueError whose message contains the input."""
        mod = self._load_module()
        for bad in ("maybe", "2", "", "truee", "tru", "10", "nope"):
            with pytest.raises(ValueError) as exc:
                mod.to_bool(bad)
            assert bad in str(exc.value), (
                f"ValueError for {bad!r} must contain the offending input; "
                f"got: {exc.value}"
            )

    # ------------------------------------------------------------------ #
    # L2 — to_int                                                        #
    # ------------------------------------------------------------------ #
    def test_l2_to_int_basic_and_whitespace_and_sign(self):
        """L2: base-10 parse, whitespace ignored, +/- sign honored."""
        mod = self._load_module()
        assert mod.to_int("42") == 42
        assert mod.to_int("  42 ") == 42
        assert mod.to_int("\t7\n") == 7
        assert mod.to_int("-13") == -13
        assert mod.to_int("+5") == 5
        assert mod.to_int("  -0 ") == 0

    def test_l2_to_int_empty_uses_default(self):
        """L2: empty / whitespace-only input returns the supplied default."""
        mod = self._load_module()
        assert mod.to_int("", default=7) == 7
        assert mod.to_int("   ", default=-3) == -3
        assert mod.to_int("\t\n", default=0) == 0

    def test_l2_to_int_empty_without_default_raises(self):
        """L2: empty input with no default raises ValueError."""
        mod = self._load_module()
        for empty in ("", "   ", "\t\n"):
            with pytest.raises(ValueError):
                mod.to_int(empty)

    def test_l2_to_int_malformed_raises_even_with_default(self):
        """L2: a malformed non-empty value errors even when a default is given.

        A naive implementation that returns `default` on any parse failure would
        wrongly accept "4.5"/"abc" here and so must fail this case.
        """
        mod = self._load_module()
        for bad in ("4.5", "abc", "1_000", "0x10", "1e3", "12abc"):
            with pytest.raises(ValueError) as exc:
                mod.to_int(bad, default=99)
            assert bad in str(exc.value), (
                f"ValueError for {bad!r} must contain the offending input; "
                f"got: {exc.value}"
            )
            # And likewise without a default supplied.
            with pytest.raises(ValueError):
                mod.to_int(bad)

    # ------------------------------------------------------------------ #
    # L2 — to_list                                                       #
    # ------------------------------------------------------------------ #
    def test_l2_to_list_whitespace_mode(self):
        """L2: sep=None splits on any whitespace run AND newlines, dropping empties."""
        mod = self._load_module()
        assert mod.to_list("a b\n c") == ["a", "b", "c"]
        assert mod.to_list("  a   b  ") == ["a", "b"]
        assert mod.to_list("x\t\ty\nz") == ["x", "y", "z"]
        assert mod.to_list("solo") == ["solo"]

    def test_l2_to_list_explicit_sep_mode(self):
        """L2: explicit sep splits on it, strips each item, drops empties."""
        mod = self._load_module()
        assert mod.to_list("a, ,b ,", sep=",") == ["a", "b"]
        assert mod.to_list("a,b,c", sep=",") == ["a", "b", "c"]
        assert mod.to_list(" a ; b ;; c ", sep=";") == ["a", "b", "c"]
        # With explicit sep the items are stripped but internal spaces survive
        # only after a strip — a single-token padded value collapses to itself.
        assert mod.to_list("  one  ", sep=",") == ["one"]

    def test_l2_to_list_empty_input_both_modes(self):
        """L2: empty / whitespace-only input -> [] in both split modes."""
        mod = self._load_module()
        for empty in ("", "   ", "\t\n"):
            assert mod.to_list(empty) == [], empty
            assert mod.to_list(empty, sep=",") == [], empty

    def test_l2_to_list_never_yields_empty_items(self):
        """L2: output never contains empty strings (separator-heavy inputs)."""
        mod = self._load_module()
        assert "" not in mod.to_list(",,a,,b,,", sep=",")
        assert mod.to_list(",,a,,b,,", sep=",") == ["a", "b"]
        assert "" not in mod.to_list("\n\n a \n\n b \n\n")

    # ------------------------------------------------------------------ #
    # L2 — to_path_list                                                  #
    # ------------------------------------------------------------------ #
    def test_l2_to_path_list_relative_join(self):
        """L2: relative entries are joined onto base with POSIX semantics."""
        mod = self._load_module()
        out = mod.to_path_list("a b", base="/root")
        assert out == ["/root/a", "/root/b"], out

    def test_l2_to_path_list_absolute_passthrough(self):
        """L2: entries already absolute (leading /) are kept as-is, not re-based."""
        mod = self._load_module()
        out = mod.to_path_list("/etc/x rel/y", base="/root")
        assert out == ["/etc/x", "/root/rel/y"], out

    def test_l2_to_path_list_dedup_preserves_order(self):
        """L2: duplicate resulting paths are removed, first-seen order preserved."""
        mod = self._load_module()
        out = mod.to_path_list("b a b c a", base="/r")
        assert out == ["/r/b", "/r/a", "/r/c"], out

    def test_l2_to_path_list_collapses_dot_and_dupsep(self):
        """L2: redundant '.' components and duplicate '/' collapse in each result."""
        mod = self._load_module()
        out = mod.to_path_list("./a/./b //c", base="/root")
        # base + a/b for the first; absolute //c collapses to /c.
        assert out == ["/root/a/b", "/c"], out

    def test_l2_to_path_list_dotdot_preserved(self):
        """L2: a '..' component is kept verbatim, never resolved away."""
        mod = self._load_module()
        out = mod.to_path_list("a/../b", base="/root")
        assert len(out) == 1
        assert ".." in out[0], f"'..' must be preserved, got {out[0]!r}"
        assert out[0] == "/root/a/../b", out

    def test_l2_to_path_list_empty_input(self):
        """L2: empty / whitespace-only input -> []."""
        mod = self._load_module()
        assert mod.to_path_list("", base="/root") == []
        assert mod.to_path_list("   \n ", base="/root") == []

    # ------------------------------------------------------------------ #
    # L2 — the task's own acceptance command must pass                   #
    # ------------------------------------------------------------------ #
    def test_l2_native_pytest_suite_passes(self):
        """L2: the agent's testing/test_inivalue_util.py passes via native pytest.

        Runs the exact acceptance command. Requires at least one test collected
        and zero failures.
        """
        env = dict(os.environ)
        # Ensure the repo's src tree is importable for the native suite.
        env["PYTHONPATH"] = os.path.join(self.REPO_DIR, "src")
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "testing/test_inivalue_util.py",
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
