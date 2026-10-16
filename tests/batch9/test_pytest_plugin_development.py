"""Benchmark test for the `pytest-plugin-development` skill task (variant ext9).

Task: add a self-contained fixture-scope ranking utility module at
`src/_pytest/_scoperank.py` (pure stdlib, no other `_pytest` imports) exporting
`SCOPES`, `rank`, `is_broader`, `narrowest`, and `sort_by_scope`, plus an
exhaustive test module `testing/test_scoperank_util.py`.

Verification strategy
---------------------
This file independently exercises the agent's implementation by loading the
delivered module directly from its file path (via importlib, avoiding `_pytest`
package side effects) and asserting its real runtime behavior across every
enumerated edge case from the requirement doc:

  * `SCOPES` is the exact broadest-first tuple-like sequence.
  * `rank` is a strictly-increasing 0..4 index with a ValueError (mentioning the
    offending scope) for unknown names.
  * `is_broader` strict-broader semantics, equal -> False, invalid -> ValueError.
  * `narrowest` happy path + empty-iterable error + invalid-member error.
  * `sort_by_scope` broadest-to-narrowest, *stable* within equal scopes, and
    invalid-scope error.

The behavioral checks do NOT trust the agent's own test file, so a partial /
hardcoded / non-stable implementation must fail here. A final L2 case also drives
the doc's native acceptance command so the agent's own suite must collect and
pass.
"""

import ast
import importlib.util
import os
import subprocess
import sys

import pytest


class TestPytestPluginDevelopment:
    REPO_DIR = "/workspace/pytest"

    EXPECTED_SCOPES = ("session", "package", "module", "class", "function")

    # ------------------------------------------------------------------ #
    # helpers                                                            #
    # ------------------------------------------------------------------ #
    @classmethod
    def _module_path(cls):
        return os.path.join(cls.REPO_DIR, "src", "_pytest", "_scoperank.py")

    @classmethod
    def _test_module_path(cls):
        return os.path.join(cls.REPO_DIR, "testing", "test_scoperank_util.py")

    @classmethod
    def _load_module(cls):
        """Load the delivered _scoperank.py directly from its file path.

        Loading by file path (not `import _pytest._scoperank`) avoids importing
        the whole `_pytest` package and guarantees we exercise the agent's file.
        """
        path = cls._module_path()
        assert os.path.isfile(path), f"missing deliverable: {path}"
        spec = importlib.util.spec_from_file_location("_scoperank_under_test", path)
        assert spec is not None and spec.loader is not None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    # ------------------------------------------------------------------ #
    # L1 — deliverables exist & are minimally well-formed                #
    # ------------------------------------------------------------------ #
    def test_l1_module_file_exists(self):
        """L1: src/_pytest/_scoperank.py deliverable exists."""
        assert os.path.isfile(self._module_path()), self._module_path()

    def test_l1_test_module_exists(self):
        """L1: testing/test_scoperank_util.py deliverable exists."""
        assert os.path.isfile(self._test_module_path()), self._test_module_path()

    def test_l1_exports_required_symbols(self):
        """L1: module exports SCOPES plus the four required callables."""
        mod = self._load_module()
        assert hasattr(mod, "SCOPES"), "missing export: SCOPES"
        for name in ("rank", "is_broader", "narrowest", "sort_by_scope"):
            assert hasattr(mod, name), f"missing export: {name}"
            assert callable(getattr(mod, name)), f"{name} is not callable"

    def test_l1_module_is_dependency_free(self):
        """L1: module imports no other _pytest submodules and no third-party deps."""
        path = self._module_path()
        with open(path, "r", encoding="utf-8") as fh:
            src = fh.read()
        tree = ast.parse(src)
        # Permit only stdlib + __future__. Anything from _pytest or a relative
        # import is forbidden by the doc ("no imports from other _pytest modules").
        allowed_thirdparty_block = {"_pytest"}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.level and node.level > 0:
                    raise AssertionError(
                        "relative import found; module must be dependency-free"
                    )
                base = (node.module or "").split(".")[0]
                assert base not in allowed_thirdparty_block, (
                    f"module must not import from _pytest, found: {node.module}"
                )
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith("_pytest"), (
                        f"module must not import _pytest, found: {alias.name}"
                    )

    # ------------------------------------------------------------------ #
    # L2 — SCOPES sequence                                               #
    # ------------------------------------------------------------------ #
    def test_l2_scopes_exact_order(self):
        """L2: SCOPES equals the exact broadest-first ordering."""
        mod = self._load_module()
        assert tuple(mod.SCOPES) == self.EXPECTED_SCOPES, tuple(mod.SCOPES)

    # ------------------------------------------------------------------ #
    # L2 — rank                                                          #
    # ------------------------------------------------------------------ #
    def test_l2_rank_strictly_increasing(self):
        """L2: rank assigns 0..4 broadest->narrowest, strictly increasing."""
        mod = self._load_module()
        ranks = [mod.rank(s) for s in self.EXPECTED_SCOPES]
        assert ranks == [0, 1, 2, 3, 4], ranks
        # Strictly increasing across the full ordering.
        assert all(ranks[i] < ranks[i + 1] for i in range(len(ranks) - 1)), ranks
        # Spot checks from the doc.
        assert mod.rank("session") < mod.rank("function")

    def test_l2_rank_invalid_raises_with_scope_in_message(self):
        """L2: unknown scope raises ValueError naming the offending scope."""
        mod = self._load_module()
        bad = "nope_scope"
        with pytest.raises(ValueError) as exc:
            mod.rank(bad)
        assert bad in str(exc.value), (
            f"ValueError for rank({bad!r}) must mention the offending scope; "
            f"got: {exc.value}"
        )

    # ------------------------------------------------------------------ #
    # L2 — is_broader                                                    #
    # ------------------------------------------------------------------ #
    def test_l2_is_broader_truth_table(self):
        """L2: strict-broader semantics; equal scopes return False."""
        mod = self._load_module()
        assert mod.is_broader("module", "function") is True
        assert mod.is_broader("function", "module") is False
        assert mod.is_broader("class", "class") is False
        assert mod.is_broader("session", "package") is True
        assert mod.is_broader("package", "session") is False

    def test_l2_is_broader_full_consistency_with_rank(self):
        """L2: is_broader(a,b) iff rank(a) < rank(b) over every ordered pair."""
        mod = self._load_module()
        for a in self.EXPECTED_SCOPES:
            for b in self.EXPECTED_SCOPES:
                expected = mod.rank(a) < mod.rank(b)
                got = mod.is_broader(a, b)
                assert got is expected, f"is_broader({a!r},{b!r})={got}, want {expected}"
                # Reflexive case must be strictly False (not just falsy).
                if a == b:
                    assert got is False

    def test_l2_is_broader_invalid_raises(self):
        """L2: either invalid scope name raises ValueError mentioning that scope."""
        mod = self._load_module()
        with pytest.raises(ValueError) as exc_a:
            mod.is_broader("bogus_a", "function")
        assert "bogus_a" in str(exc_a.value), exc_a.value
        with pytest.raises(ValueError) as exc_b:
            mod.is_broader("session", "bogus_b")
        assert "bogus_b" in str(exc_b.value), exc_b.value

    # ------------------------------------------------------------------ #
    # L2 — narrowest                                                     #
    # ------------------------------------------------------------------ #
    def test_l2_narrowest_happy_path(self):
        """L2: narrowest returns the narrowest member of a non-empty iterable."""
        mod = self._load_module()
        assert mod.narrowest(["session", "module", "class"]) == "class"
        assert mod.narrowest(["function"]) == "function"
        assert mod.narrowest(["function", "session"]) == "function"
        # Order of input must not change the result.
        assert mod.narrowest(["class", "module", "session"]) == "class"
        # Accepts an arbitrary (single-pass) iterable, not just a list.
        assert mod.narrowest(iter(["package", "session", "module"])) == "module"

    def test_l2_narrowest_empty_raises(self):
        """L2: an empty iterable raises ValueError."""
        mod = self._load_module()
        with pytest.raises(ValueError):
            mod.narrowest([])
        with pytest.raises(ValueError):
            mod.narrowest(iter(()))

    def test_l2_narrowest_invalid_member_raises(self):
        """L2: any invalid member raises ValueError naming the offending scope."""
        mod = self._load_module()
        with pytest.raises(ValueError) as exc:
            mod.narrowest(["session", "weird", "class"])
        assert "weird" in str(exc.value), exc.value

    # ------------------------------------------------------------------ #
    # L2 — sort_by_scope                                                 #
    # ------------------------------------------------------------------ #
    def test_l2_sort_by_scope_broadest_to_narrowest(self):
        """L2: items ordered broadest scope first."""
        mod = self._load_module()
        items = [
            ("a", "function"),
            ("b", "session"),
            ("c", "module"),
            ("d", "class"),
            ("e", "package"),
        ]
        out = mod.sort_by_scope(items)
        assert [scope for _, scope in out] == list(self.EXPECTED_SCOPES), out
        assert out == [
            ("b", "session"),
            ("e", "package"),
            ("c", "module"),
            ("d", "class"),
            ("a", "function"),
        ], out

    def test_l2_sort_by_scope_is_stable(self):
        """L2: items sharing a scope keep their original relative order (stable)."""
        mod = self._load_module()
        items = [("a", "function"), ("b", "session"), ("c", "function")]
        out = mod.sort_by_scope(items)
        assert out == [("b", "session"), ("a", "function"), ("c", "function")], out
        # A larger, deliberately interleaved input to defeat a non-stable sort.
        items2 = [
            ("f1", "function"),
            ("m1", "module"),
            ("f2", "function"),
            ("m2", "module"),
            ("f3", "function"),
            ("s1", "session"),
        ]
        out2 = mod.sort_by_scope(items2)
        assert out2 == [
            ("s1", "session"),
            ("m1", "module"),
            ("m2", "module"),
            ("f1", "function"),
            ("f2", "function"),
            ("f3", "function"),
        ], out2

    def test_l2_sort_by_scope_does_not_mutate_input(self):
        """L2: sort_by_scope returns a new list and leaves the input order intact."""
        mod = self._load_module()
        items = [("a", "function"), ("b", "session"), ("c", "function")]
        snapshot = list(items)
        out = mod.sort_by_scope(items)
        assert items == snapshot, "input list must not be mutated in place"
        assert out is not items

    def test_l2_sort_by_scope_invalid_raises(self):
        """L2: any item with an invalid scope raises ValueError naming it."""
        mod = self._load_module()
        with pytest.raises(ValueError) as exc:
            mod.sort_by_scope([("a", "session"), ("b", "frobnicate")])
        assert "frobnicate" in str(exc.value), exc.value

    # ------------------------------------------------------------------ #
    # L2 — cross-function invariants                                     #
    # ------------------------------------------------------------------ #
    def test_l2_narrowest_matches_max_rank(self):
        """L2: narrowest(group) is exactly the member with the greatest rank."""
        mod = self._load_module()
        groups = [
            ["session", "module", "class"],
            ["package", "function"],
            ["session", "package", "module", "class", "function"],
            ["class", "class", "module"],
        ]
        for g in groups:
            expected = max(g, key=mod.rank)
            assert mod.narrowest(g) == expected, (g, mod.narrowest(g), expected)

    def test_l2_sort_by_scope_ranks_nondecreasing(self):
        """L2: the rank sequence of sort_by_scope output is non-decreasing."""
        mod = self._load_module()
        items = [
            ("a", "function"),
            ("b", "session"),
            ("c", "function"),
            ("d", "class"),
            ("e", "module"),
            ("f", "package"),
        ]
        out = mod.sort_by_scope(items)
        ranks = [mod.rank(scope) for _, scope in out]
        assert ranks == sorted(ranks), ranks
        assert all(ranks[i] <= ranks[i + 1] for i in range(len(ranks) - 1)), ranks

    # ------------------------------------------------------------------ #
    # L2 — the task's own acceptance command must pass                   #
    # ------------------------------------------------------------------ #
    def test_l2_native_pytest_suite_passes(self):
        """L2: the agent's testing/test_scoperank_util.py passes via native pytest.

        Drives the exact acceptance command from the requirement doc. Requires at
        least one test collected and zero failures.
        """
        assert os.path.isfile(self._test_module_path()), self._test_module_path()
        env = dict(os.environ)
        # Ensure the repo's src tree is importable for the native suite.
        env["PYTHONPATH"] = os.path.join(self.REPO_DIR, "src")
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "testing/test_scoperank_util.py",
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
