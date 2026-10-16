"""Tests for skill: mypy-type-checking (task: Add a Configuration Value Coercion Helper).

The agent must create a self-contained, standard-library-only module
``src/black/option_coerce.py`` inside the ``black`` repository exposing
``OptionSpec``, ``coerce_value``, ``coerce_mapping`` and ``CoercionError``,
plus a deterministic unit-test file ``tests/test_option_coerce.py``.

This suite verifies the deliverable from two angles:

* L1 -- the deliverable files exist and are minimally well-formed.
* L2 -- the runtime behaviour of every ``kind`` is exercised independently by
  driving the module through a fresh Python subprocess (so a naive solution that
  ignores the int/bool/str distinctions or the numeric-string rejections fails),
  the project's configured ``mypy`` static-analysis gate is run over the new
  module, and the agent-authored pytest file is executed with the native
  toolchain.

The module is intentionally imported directly from its file location (and also
via the canonical ``black.option_coerce`` package path) so that the heavy,
optional third-party dependencies of the top-level ``black`` package never gate
these behavioural checks.
"""

import os
import subprocess
import textwrap

import pytest


class TestMypyTypeChecking:
    REPO_DIR = "/workspace/black"

    MODULE_PATH = os.path.join(REPO_DIR, "src", "black", "option_coerce.py")
    TEST_PATH = os.path.join(REPO_DIR, "tests", "test_option_coerce.py")
    SRC_DIR = os.path.join(REPO_DIR, "src")

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _run_driver(self, body, timeout=120):
        """Run a Python snippet that imports the coercion module directly.

        The module file is loaded by path via importlib so that we do NOT pull
        in the (heavy, optional-dependency-laden) top-level ``black`` package.
        ``CoercionError``/``OptionSpec``/``coerce_value``/``coerce_mapping`` are
        injected into the snippet's globals as ``OptionSpec`` etc.
        """
        preamble = textwrap.dedent(
            """
            import importlib.util, sys, os
            _mod_path = {module_path!r}
            spec = importlib.util.spec_from_file_location("_option_coerce_probe", _mod_path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            OptionSpec = mod.OptionSpec
            coerce_value = mod.coerce_value
            coerce_mapping = mod.coerce_mapping
            CoercionError = mod.CoercionError
            """
        ).format(module_path=self.MODULE_PATH)
        script = preamble + textwrap.dedent(body)
        result = subprocess.run(
            ["python", "-c", script],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result

    def _run_ok(self, body, timeout=120):
        result = self._run_driver(body, timeout=timeout)
        assert result.returncode == 0, (
            "driver exited non-zero\n"
            f"stdout={result.stdout}\nstderr={result.stderr}"
        )
        return result

    # ------------------------------------------------------------------ #
    # L1 -- deliverables exist and are well-formed
    # ------------------------------------------------------------------ #
    def test_module_file_exists(self):
        """L1: the new helper module file is created at the required path."""
        assert os.path.isfile(self.MODULE_PATH), (
            f"expected coercion module at {self.MODULE_PATH}"
        )
        assert os.path.getsize(self.MODULE_PATH) > 0

    def test_unit_test_file_exists(self):
        """L1: the deterministic unit-test file is created at the required path."""
        assert os.path.isfile(self.TEST_PATH), (
            f"expected unit-test file at {self.TEST_PATH}"
        )
        assert os.path.getsize(self.TEST_PATH) > 0

    def test_public_surface_importable(self):
        """L1->L2: the four required public names import and have the right shapes.

        Also asserts CoercionError is a subclass of ValueError, as required.
        """
        result = self._run_ok(
            """
            assert isinstance(OptionSpec, type)
            assert callable(coerce_value)
            assert callable(coerce_mapping)
            assert isinstance(CoercionError, type)
            assert issubclass(CoercionError, ValueError)
            print("OK")
            """
        )
        assert "OK" in result.stdout

    def test_canonical_package_import_path(self):
        """L1->L2: ``from black.option_coerce import ...`` succeeds via the src path.

        The module is required to be importable through the ``black`` package
        namespace WITHOUT importing the (heavy) top-level ``black`` package
        machinery; it is stdlib-only, so a direct submodule import must work.
        """
        script = (
            "from black.option_coerce import "
            "OptionSpec, coerce_value, coerce_mapping, CoercionError\n"
            "assert issubclass(CoercionError, ValueError)\n"
            "print('IMPORT_OK')\n"
        )
        env = dict(os.environ)
        env["PYTHONPATH"] = self.SRC_DIR
        result = subprocess.run(
            ["python", "-c", script],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=120,
            env=env,
        )
        assert result.returncode == 0, (
            "canonical import path failed\n"
            f"stdout={result.stdout}\nstderr={result.stderr}"
        )
        assert "IMPORT_OK" in result.stdout

    # ------------------------------------------------------------------ #
    # L2 -- per-kind runtime behaviour
    # ------------------------------------------------------------------ #
    def test_int_coercion_and_rejections(self):
        """L2: int kind returns int values, parses signed/whitespaced strings, rejects bad input.

        Maps to: int passthrough, base-10 string parse, bool rejection, and the
        ``"3.0"``/``"0x1f"``/``""`` failure edge cases.
        """
        self._run_ok(
            """
            spec = OptionSpec(kind="int")

            # passthrough int (and exact bool/int distinction)
            v = coerce_value(spec, 5)
            assert v == 5 and type(v) is int, v

            # signed / whitespaced string forms
            assert coerce_value(spec, " -7 ") == -7
            assert coerce_value(spec, "+12") == 12
            assert coerce_value(spec, "42") == 42

            # bool must be rejected even though bool is an int subclass
            for bad in (True, False):
                try:
                    coerce_value(spec, bad)
                except CoercionError:
                    pass
                else:
                    raise AssertionError(f"bool {bad!r} should be rejected for int")

            # non-integer strings / floats / empty
            for bad in ("3.0", "0x1f", "", "abc", 3.0, None.__class__):
                try:
                    coerce_value(spec, bad)
                except CoercionError:
                    pass
                else:
                    raise AssertionError(f"int coercion of {bad!r} should fail")
            print("OK")
            """
        )

    def test_bool_coercion_case_insensitive(self):
        """L2: bool kind accepts the documented truthy/falsey tokens case-insensitively.

        Maps to: bool passthrough, the true/1/yes/on and false/0/no/off tables,
        case-insensitivity (``"TRUE"``, ``" On "``), and rejection of junk.
        """
        self._run_ok(
            """
            spec = OptionSpec(kind="bool")

            # passthrough
            assert coerce_value(spec, True) is True
            assert coerce_value(spec, False) is False

            truthy = ["true", "TRUE", "1", "yes", "YES", "on", " On ", "  true "]
            falsey = ["false", "FALSE", "0", "no", "NO", "off", " Off "]
            for s in truthy:
                r = coerce_value(spec, s)
                assert r is True, (s, r)
            for s in falsey:
                r = coerce_value(spec, s)
                assert r is False, (s, r)

            for bad in ("maybe", "2", "", "tru", 1, 0):
                try:
                    coerce_value(spec, bad)
                except CoercionError:
                    pass
                else:
                    raise AssertionError(f"bool coercion of {bad!r} should fail")
            print("OK")
            """
        )

    def test_str_coercion_rejects_numbers(self):
        """L2: str kind returns strings unchanged and refuses to stringify int/bool.

        Maps to: ``"str"`` passthrough plus the explicit int/bool rejection.
        """
        self._run_ok(
            """
            spec = OptionSpec(kind="str")
            assert coerce_value(spec, "hello") == "hello"
            assert coerce_value(spec, "") == ""        # empty string is a valid str

            for bad in (1, 0, True, False, 3.5, ["a"]):
                try:
                    coerce_value(spec, bad)
                except CoercionError:
                    pass
                else:
                    raise AssertionError(f"str coercion of {bad!r} should fail")
            print("OK")
            """
        )

    def test_str_list_split_and_copy(self):
        """L2: str_list splits on commas, trims/drops empties, and copies list input.

        Maps to: ``"a, b ,c"`` -> ``["a","b","c"]``, ``""`` -> ``[]``,
        list/tuple of str accepted and returned as a NEW list, and rejection of
        lists containing a non-str element.
        """
        self._run_ok(
            """
            spec = OptionSpec(kind="str_list")

            assert coerce_value(spec, "a, b ,c") == ["a", "b", "c"]
            assert coerce_value(spec, "") == []
            assert coerce_value(spec, "  ,  ,x ,") == ["x"]
            assert coerce_value(spec, "solo") == ["solo"]

            src = ["x", "y"]
            out = coerce_value(spec, src)
            assert out == ["x", "y"]
            assert out is not src, "must return a brand-new list"
            assert all(isinstance(e, str) for e in out)

            assert coerce_value(spec, ("p", "q")) == ["p", "q"]

            for bad in (["ok", 1], [1, 2], 5, {"a": 1}, [None]):
                try:
                    coerce_value(spec, bad)
                except CoercionError:
                    pass
                else:
                    raise AssertionError(f"str_list coercion of {bad!r} should fail")
            print("OK")
            """
        )

    def test_choice_coercion(self):
        """L2: choice kind matches a stripped string against the allowed set.

        Maps to: canonical value returned, whitespace stripped before matching,
        and rejection of unknown strings / non-string input.
        """
        self._run_ok(
            """
            spec = OptionSpec(kind="choice", choices=["alpha", "beta", "gamma"])
            assert coerce_value(spec, "beta") == "beta"
            assert coerce_value(spec, "  alpha ") == "alpha"

            for bad in ("delta", "Beta", "", 1, None.__class__, ["alpha"]):
                try:
                    coerce_value(spec, bad)
                except CoercionError:
                    pass
                else:
                    raise AssertionError(f"choice coercion of {bad!r} should fail")
            print("OK")
            """
        )

    def test_optionspec_validation(self):
        """L2: OptionSpec construction enforces the kind/choices invariants.

        Maps to: unknown kind tag rejected, empty-choices ``"choice"`` rejected,
        and a non-choice spec carrying choices rejected.
        """
        self._run_ok(
            """
            # valid constructions do not raise
            OptionSpec(kind="int")
            OptionSpec(kind="bool")
            OptionSpec(kind="str")
            OptionSpec(kind="str_list")
            OptionSpec(kind="choice", choices=["a"])

            # unknown tag
            try:
                OptionSpec(kind="float")
            except CoercionError:
                pass
            else:
                raise AssertionError("unknown kind must raise CoercionError")

            # choice with no choices
            for empty in ([], (), set()):
                try:
                    OptionSpec(kind="choice", choices=empty)
                except CoercionError:
                    pass
                else:
                    raise AssertionError("empty-choice spec must raise CoercionError")

            # non-choice kind given choices
            try:
                OptionSpec(kind="str", choices=["a", "b"])
            except CoercionError:
                pass
            else:
                raise AssertionError("non-choice spec with choices must raise")
            print("OK")
            """
        )

    def test_none_and_required_interaction(self):
        """L2: None handling depends on the required flag, across all kinds.

        Maps to: non-required + None -> None regardless of kind; required + None
        -> CoercionError.
        """
        self._run_ok(
            """
            for kind in ("int", "bool", "str", "str_list"):
                spec = OptionSpec(kind=kind)
                assert coerce_value(spec, None) is None, kind
                req = OptionSpec(kind=kind, required=True)
                try:
                    coerce_value(req, None)
                except CoercionError:
                    pass
                else:
                    raise AssertionError(f"required None for {kind} must raise")

            cspec = OptionSpec(kind="choice", choices=["a"])
            assert coerce_value(cspec, None) is None
            creq = OptionSpec(kind="choice", choices=["a"], required=True)
            try:
                coerce_value(creq, None)
            except CoercionError:
                pass
            else:
                raise AssertionError("required None for choice must raise")
            print("OK")
            """
        )

    def test_coerce_mapping_behaviour(self):
        """L2: coerce_mapping covers all specs, defaults missing keys to None, rejects unknowns.

        Maps to: every spec key present in result; absent key treated as None
        (required -> error, optional -> None); unknown raw key -> CoercionError;
        error message mentions the offending option name.
        """
        self._run_ok(
            """
            specs = {
                "line_length": OptionSpec(kind="int"),
                "fast": OptionSpec(kind="bool"),
                "extend": OptionSpec(kind="str_list"),
                "target": OptionSpec(kind="choice", choices=["py310", "py311"]),
            }
            raw = {
                "line_length": "88",
                "fast": "yes",
                "extend": "a, b",
                "target": " py311 ",
            }
            out = coerce_mapping(specs, raw)
            assert set(out) == set(specs), out
            assert out["line_length"] == 88 and type(out["line_length"]) is int
            assert out["fast"] is True
            assert out["extend"] == ["a", "b"]
            assert out["target"] == "py311"

            # missing optional key -> None
            out2 = coerce_mapping(specs, {"line_length": "10"})
            assert out2["fast"] is None
            assert out2["extend"] is None
            assert out2["target"] is None
            assert out2["line_length"] == 10

            # missing required key -> CoercionError mentioning the name
            req_specs = {"width": OptionSpec(kind="int", required=True)}
            try:
                coerce_mapping(req_specs, {})
            except CoercionError as exc:
                assert "width" in str(exc), str(exc)
            else:
                raise AssertionError("missing required key must raise")

            # unknown raw key -> CoercionError mentioning the name
            try:
                coerce_mapping({"a": OptionSpec(kind="str")}, {"a": "x", "bogus": "y"})
            except CoercionError as exc:
                assert "bogus" in str(exc), str(exc)
            else:
                raise AssertionError("unknown option must raise")

            # a coercion failure inside the mapping surfaces with the option name
            try:
                coerce_mapping({"n": OptionSpec(kind="int")}, {"n": "not-an-int"})
            except CoercionError as exc:
                assert "n" in str(exc), str(exc)
            else:
                raise AssertionError("bad value inside mapping must raise")
            print("OK")
            """
        )

    def test_return_types_are_exact(self):
        """L2: returned runtime types match the spec (int/bool/str/list[str]).

        A naive implementation that, e.g., returns the raw string for ``int`` or
        leaves ``bool`` as a string fails here.
        """
        self._run_ok(
            """
            assert type(coerce_value(OptionSpec(kind="int"), "7")) is int
            assert type(coerce_value(OptionSpec(kind="bool"), "on")) is bool
            assert type(coerce_value(OptionSpec(kind="str"), "s")) is str
            r = coerce_value(OptionSpec(kind="str_list"), "a,b")
            assert type(r) is list and all(type(e) is str for e in r)
            assert type(coerce_value(OptionSpec(kind="choice", choices=["c"]), "c")) is str
            print("OK")
            """
        )

    # ------------------------------------------------------------------ #
    # L2 -- static-analysis gate and native unit tests
    # ------------------------------------------------------------------ #
    def test_mypy_clean_on_new_module(self):
        """L2: the project's configured (strict) mypy reports no errors on the new module.

        This is the core acceptance gate for the mypy-type-checking skill. The
        repo's pyproject.toml sets ``strict = true``; the agent's annotations
        must satisfy it.
        """
        result = subprocess.run(
            ["python", "-m", "mypy", "src/black/option_coerce.py"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=600,
        )
        combined = result.stdout + result.stderr
        assert result.returncode == 0, (
            "mypy reported errors on the new module\n" + combined
        )
        assert "error:" not in result.stdout, combined

    def test_native_unit_tests_pass(self):
        """L2: the agent's tests/test_option_coerce.py passes under pytest.

        Runs exactly the command from the Acceptance Criteria, scoped to the
        new test file, and asserts a non-empty passing collection.
        """
        result = subprocess.run(
            ["python", "-m", "pytest", "tests/test_option_coerce.py", "-q"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=600,
        )
        combined = result.stdout + result.stderr
        assert result.returncode == 0, "pytest failed\n" + combined
        # ensure tests actually ran (guard against an empty/placeholder file)
        assert "no tests ran" not in combined.lower(), combined
        assert " passed" in combined, combined

    def test_self_contained_no_third_party_imports(self):
        """L2: the module imports stdlib only -- it must load with click/tomllib/black absent.

        We load the module file with a sys.path that does NOT include the repo
        ``src`` dir, so any accidental ``import click`` / ``from black import``
        / ``import tomllib``-via-black dependency would surface as an ImportError.
        The module file itself is loaded by absolute path.
        """
        result = subprocess.run(
            [
                "python",
                "-c",
                textwrap.dedent(
                    f"""
                    import importlib.util, sys
                    # Make sure the repo source tree is NOT importable as a package.
                    sys.path = [p for p in sys.path if {self.SRC_DIR!r} not in p]
                    spec = importlib.util.spec_from_file_location(
                        "isolated_option_coerce", {self.MODULE_PATH!r}
                    )
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)
                    # exercise it once to ensure no lazy third-party import inside funcs
                    s = mod.OptionSpec(kind="int")
                    assert mod.coerce_value(s, "1") == 1
                    print("ISOLATED_OK")
                    """
                ),
            ],
            cwd="/tmp",
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, (
            "module is not standard-library-only / failed to import in isolation\n"
            f"stdout={result.stdout}\nstderr={result.stderr}"
        )
        assert "ISOLATED_OK" in result.stdout
