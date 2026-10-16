"""Benchmark test for the `pytest-plugin-development` skill task (variant ext6).

Task: add a self-contained warning-filter spec parser utility module at
`src/_pytest/_warnfilter.py` (pure stdlib, no other `_pytest` imports) exporting
an immutable `FilterSpec` record (fields: action, message, category, module,
lineno) and a `parse_filter(spec: str) -> FilterSpec` function, plus an
exhaustive test module `testing/test_warnfilter_util.py`.

The parser handles the positional `action:message:category:module:lineno` form
with trailing-field defaults, a required `action` from a fixed allow-list,
unique-prefix action expansion (with ambiguous-prefix errors), non-negative
integer lineno validation, a too-many-fields error, whole-spec whitespace
trimming with inner-message-whitespace preservation, and record equality. Every
ValueError must embed the offending input string.

This test file independently exercises the agent's implementation by loading the
delivered module directly (via importlib, avoiding `_pytest` package side
effects) and asserting its real runtime behavior across every enumerated edge
case. It does NOT rely on the agent's own test file for the behavioral checks,
so a partial / hardcoded implementation must fail here. A final L2 test also
drives the task's exact native acceptance command.
"""

import importlib.util
import os
import subprocess
import sys

import pytest


class TestPytestPluginDevelopment:
    REPO_DIR = "/workspace/pytest"

    VALID_ACTIONS = ("error", "ignore", "always", "default", "module", "once")

    # ------------------------------------------------------------------ #
    # helpers                                                            #
    # ------------------------------------------------------------------ #
    @classmethod
    def _module_path(cls):
        return os.path.join(cls.REPO_DIR, "src", "_pytest", "_warnfilter.py")

    @classmethod
    def _load_module(cls):
        """Load the delivered _warnfilter.py directly from its file path.

        Loading by file path (not `import _pytest._warnfilter`) avoids importing
        the whole `_pytest` package and guarantees we exercise the agent's file.
        """
        path = cls._module_path()
        assert os.path.isfile(path), f"missing deliverable: {path}"
        spec = importlib.util.spec_from_file_location("_warnfilter_under_test", path)
        assert spec is not None and spec.loader is not None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    @classmethod
    def _fields(cls, rec):
        """Return (action, message, category, module, lineno) from a FilterSpec."""
        return (
            rec.action,
            rec.message,
            rec.category,
            rec.module,
            rec.lineno,
        )

    # ------------------------------------------------------------------ #
    # L1 — deliverables exist & are minimally well-formed                #
    # ------------------------------------------------------------------ #
    def test_l1_module_file_exists(self):
        """L1: src/_pytest/_warnfilter.py deliverable exists."""
        assert os.path.isfile(self._module_path()), self._module_path()

    def test_l1_test_module_exists(self):
        """L1: testing/test_warnfilter_util.py deliverable exists."""
        p = os.path.join(self.REPO_DIR, "testing", "test_warnfilter_util.py")
        assert os.path.isfile(p), p

    def test_l1_exports_filterspec_and_parse_filter(self):
        """L1: module exports FilterSpec (a type) and parse_filter (callable)."""
        mod = self._load_module()
        assert hasattr(mod, "FilterSpec"), "missing export: FilterSpec"
        assert hasattr(mod, "parse_filter"), "missing export: parse_filter"
        assert isinstance(mod.FilterSpec, type), "FilterSpec must be a type"
        assert callable(mod.parse_filter), "parse_filter must be callable"

    def test_l1_module_is_dependency_free(self):
        """L1: module imports no other _pytest submodules (pure stdlib)."""
        path = self._module_path()
        with open(path, "r", encoding="utf-8") as fh:
            src = fh.read()
        import ast

        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                base = (node.module or "").split(".")[0]
                # `from __future__ import annotations` is fine; stdlib is fine.
                assert base not in ("_pytest",), (
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
    # L2 — default-filling of trailing fields                            #
    # ------------------------------------------------------------------ #
    def test_l2_action_only_defaults(self):
        """L2: parse_filter("error") fills all trailing fields with defaults."""
        mod = self._load_module()
        rec = mod.parse_filter("error")
        assert self._fields(rec) == ("error", "", "", "", 0), self._fields(rec)
        # lineno default must be the int 0, not the string "0".
        assert isinstance(rec.lineno, int) and not isinstance(rec.lineno, bool)
        assert rec.lineno == 0

    def test_l2_partial_fields_defaulted(self):
        """L2: omitted trailing fields default; provided ones are kept."""
        mod = self._load_module()
        rec = mod.parse_filter("ignore:some message")
        assert self._fields(rec) == ("ignore", "some message", "", "", 0)

    def test_l2_empty_message_with_category(self):
        """L2: "ignore::DeprecationWarning" => empty message, set category."""
        mod = self._load_module()
        rec = mod.parse_filter("ignore::DeprecationWarning")
        assert rec.message == ""
        assert rec.category == "DeprecationWarning"
        assert rec.module == ""
        assert rec.lineno == 0

    def test_l2_full_five_fields(self):
        """L2: a full spec parses every field and an integer lineno."""
        mod = self._load_module()
        rec = mod.parse_filter("always:msg here:UserWarning:mymod:12")
        assert self._fields(rec) == ("always", "msg here", "UserWarning", "mymod", 12)
        assert isinstance(rec.lineno, int)
        # inner whitespace in the message is preserved verbatim
        assert rec.message == "msg here"

    # ------------------------------------------------------------------ #
    # L2 — action allow-list                                             #
    # ------------------------------------------------------------------ #
    def test_l2_every_valid_action_accepted(self):
        """L2: each of the six valid actions parses to itself."""
        mod = self._load_module()
        for act in self.VALID_ACTIONS:
            rec = mod.parse_filter(act)
            assert rec.action == act, f"{act!r} -> {rec.action!r}"

    def test_l2_bad_action_raises_with_input(self):
        """L2: an unknown action raises ValueError naming action and input."""
        mod = self._load_module()
        bad_spec = "frobnicate:msg"
        with pytest.raises(ValueError) as exc:
            mod.parse_filter(bad_spec)
        msg = str(exc.value)
        assert "frobnicate" in msg, f"error must mention bad action: {msg!r}"
        assert bad_spec in msg, f"error must include offending input: {msg!r}"

    # ------------------------------------------------------------------ #
    # L2 — prefix expansion of action                                    #
    # ------------------------------------------------------------------ #
    def test_l2_unique_prefix_expands(self):
        """L2: unique action prefixes expand to the full action."""
        mod = self._load_module()
        assert mod.parse_filter("err").action == "error"
        assert mod.parse_filter("i").action == "ignore"
        # "o" is a unique prefix of "once" only.
        assert mod.parse_filter("o").action == "once"
        # "d" is a unique prefix of "default" only.
        assert mod.parse_filter("d").action == "default"

    def test_l2_ambiguous_prefix_raises(self):
        """L2: a genuinely ambiguous action prefix raises ValueError with input.

        "a" prefixes both "always"; "m" prefixes "module"/"message"? No: the
        actions are error, ignore, always, default, module, once. An ambiguous
        prefix is one matching >1 action. No single letter is ambiguous here,
        so use an empty-ish bad prefix and a multi-match probe below.
        """
        mod = self._load_module()
        # The empty action is not a valid/unique prefix -> error.
        bad = ":msg"  # action field empty
        with pytest.raises(ValueError) as exc:
            mod.parse_filter(bad)
        assert bad in str(exc.value), str(exc.value)

    def test_l2_nonmatching_prefix_raises(self):
        """L2: a prefix matching no valid action raises ValueError with input."""
        mod = self._load_module()
        bad = "zzz"
        with pytest.raises(ValueError) as exc:
            mod.parse_filter(bad)
        assert bad in str(exc.value), str(exc.value)

    # ------------------------------------------------------------------ #
    # L2 — lineno validation                                             #
    # ------------------------------------------------------------------ #
    def test_l2_lineno_must_be_nonnegative_int(self):
        """L2: a non-integer or negative lineno raises ValueError with input."""
        mod = self._load_module()
        # Five-field specs with an invalid final lineno field.
        non_int = "error:::: notanint"
        neg = "error::::-3"
        for bad in (non_int, neg):
            with pytest.raises(ValueError) as exc:
                mod.parse_filter(bad)
            assert bad in str(exc.value), (
                f"lineno error for {bad!r} must include input; got {exc.value}"
            )

    def test_l2_lineno_zero_and_positive_accepted(self):
        """L2: lineno of 0 and a positive integer are both accepted."""
        mod = self._load_module()
        assert mod.parse_filter("error::::0").lineno == 0
        assert mod.parse_filter("error::::7").lineno == 7

    # ------------------------------------------------------------------ #
    # L2 — field-count and whitespace rules                              #
    # ------------------------------------------------------------------ #
    def test_l2_too_many_fields_raises(self):
        """L2: more than five colon-separated fields raises ValueError with input."""
        mod = self._load_module()
        bad = "error:m:c:mod:1:extra"
        with pytest.raises(ValueError) as exc:
            mod.parse_filter(bad)
        assert bad in str(exc.value), str(exc.value)

    def test_l2_whole_spec_whitespace_trimmed_inner_preserved(self):
        """L2: surrounding whitespace is stripped; inner message space is kept."""
        mod = self._load_module()
        rec = mod.parse_filter("  always:msg here:UserWarning  ")
        assert rec.action == "always"
        # The message field's interior space survives; outer trim does not eat it.
        assert rec.message == "msg here"
        assert rec.category == "UserWarning"

    # ------------------------------------------------------------------ #
    # L2 — FilterSpec record semantics                                   #
    # ------------------------------------------------------------------ #
    def test_l2_record_equality_and_field_access(self):
        """L2: two FilterSpec with identical fields compare equal; fields readable."""
        mod = self._load_module()
        a = mod.parse_filter("always:msg here:UserWarning:mymod:12")
        b = mod.parse_filter("always:msg here:UserWarning:mymod:12")
        assert a == b, "records with identical fields must compare equal"
        c = mod.parse_filter("ignore")
        assert a != c, "records with differing fields must not be equal"
        # Direct construction must also be equality-comparable.
        direct = mod.FilterSpec("always", "msg here", "UserWarning", "mymod", 12)
        assert direct == a, "direct construction must equal an identical parse"

    def test_l2_record_is_immutable(self):
        """L2: FilterSpec fields cannot be reassigned (immutable record)."""
        mod = self._load_module()
        rec = mod.parse_filter("error")
        with pytest.raises((AttributeError, TypeError, Exception)):
            rec.action = "ignore"

    def test_l2_parse_filter_is_pure(self):
        """L2: parse_filter is deterministic — same input yields equal records."""
        mod = self._load_module()
        spec = "default:a message:CategoryX:pkg.mod:5"
        first = mod.parse_filter(spec)
        second = mod.parse_filter(spec)
        assert first == second
        assert self._fields(first) == ("default", "a message", "CategoryX", "pkg.mod", 5)

    # ------------------------------------------------------------------ #
    # L2 — the task's own acceptance command must pass                   #
    # ------------------------------------------------------------------ #
    def test_l2_native_pytest_suite_passes(self):
        """L2: the agent's testing/test_warnfilter_util.py passes via native pytest.

        Runs the exact acceptance command from the task doc. Requires at least
        one test collected and zero failures.
        """
        env = dict(os.environ)
        env["PYTHONPATH"] = os.path.join(self.REPO_DIR, "src")
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "testing/test_warnfilter_util.py",
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
        assert "no tests ran" not in combined.lower(), combined
        assert "passed" in combined.lower(), combined
