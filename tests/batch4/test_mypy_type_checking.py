"""Tests for skill: mypy-type-checking (variant ext4 -- Add a Numeric-Literal Classifier).

The agent must create a self-contained, standard-library-only module
``src/black/numeric_kind.py`` inside the ``black`` repository exposing an
``enum.Enum`` named ``NumericKind``, a function ``classify_numeric`` and an
exception ``NumericError`` (a subclass of ``ValueError``), plus a deterministic
unit-test file ``tests/test_numeric_kind.py``.

``classify_numeric(text)`` returns the ``NumericKind`` member matching a numeric
literal's source text, honouring underscore digit separators and case-insensitive
base prefixes / ``e`` / ``j`` markers, and raises ``NumericError`` for empty,
non-``str``, or malformed input.

Verification strategy (this is DISTINCT from ext1's coercion task):

* L1 -- the two deliverable files exist and are minimally well-formed; the public
  surface imports and has the right shapes (``NumericKind`` is an ``enum.Enum``
  with exactly the seven required members; ``NumericError`` subclasses
  ``ValueError``).
* L2 -- the runtime classification of every ``NumericKind`` category is exercised
  independently by driving the module through a fresh Python subprocess (so a
  naive implementation that only checks for ``.`` or a leading ``0x`` -- and thus
  misclassifies complex / scientific / underscore-bearing literals -- fails),
  every malformed/non-string input is checked to raise ``NumericError``, the
  project's configured strict ``mypy`` gate is run over the new module, and the
  agent-authored pytest file is executed with the native toolchain.

The module is imported directly from its file location (and also via the
canonical ``black.numeric_kind`` package path) so the heavy, optional
third-party dependencies of the top-level ``black`` package never gate these
behavioural checks.
"""

import os
import subprocess
import textwrap


class TestMypyTypeChecking:
    REPO_DIR = "/workspace/black"

    MODULE_PATH = os.path.join(REPO_DIR, "src", "black", "numeric_kind.py")
    TEST_PATH = os.path.join(REPO_DIR, "tests", "test_numeric_kind.py")
    SRC_DIR = os.path.join(REPO_DIR, "src")

    # The seven required enum members.
    REQUIRED_MEMBERS = [
        "DECIMAL_INT",
        "HEX",
        "OCTAL",
        "BINARY",
        "FLOAT",
        "SCIENTIFIC",
        "COMPLEX",
    ]

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _run_driver(self, body, timeout=120):
        """Run a Python snippet that imports the classifier module directly.

        The module file is loaded by path via importlib so that we do NOT pull
        in the (heavy, optional-dependency-laden) top-level ``black`` package.
        ``NumericKind`` / ``classify_numeric`` / ``NumericError`` are injected
        into the snippet's globals.
        """
        preamble = textwrap.dedent(
            """
            import importlib.util, sys, os
            _mod_path = {module_path!r}
            spec = importlib.util.spec_from_file_location("_numeric_kind_probe", _mod_path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            NumericKind = mod.NumericKind
            classify_numeric = mod.classify_numeric
            NumericError = mod.NumericError
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
        """L1: the new classifier module file is created at the required path."""
        assert os.path.isfile(self.MODULE_PATH), (
            f"expected classifier module at {self.MODULE_PATH}"
        )
        assert os.path.getsize(self.MODULE_PATH) > 0

    def test_unit_test_file_exists(self):
        """L1: the deterministic unit-test file is created at the required path."""
        assert os.path.isfile(self.TEST_PATH), (
            f"expected unit-test file at {self.TEST_PATH}"
        )
        assert os.path.getsize(self.TEST_PATH) > 0

    def test_public_surface_importable(self):
        """L1->L2: the three required public names import and have the right shapes.

        ``NumericKind`` must be an ``enum.Enum`` subclass, ``classify_numeric``
        callable, and ``NumericError`` a subclass of ``ValueError``.
        """
        result = self._run_ok(
            """
            import enum
            assert isinstance(NumericKind, type)
            assert issubclass(NumericKind, enum.Enum)
            assert callable(classify_numeric)
            assert isinstance(NumericError, type)
            assert issubclass(NumericError, ValueError)
            print("OK")
            """
        )
        assert "OK" in result.stdout

    def test_enum_has_exactly_required_members(self):
        """L1->L2: NumericKind has exactly the seven documented members, with distinct values.

        Guards against a stub enum missing categories (e.g. no SCIENTIFIC /
        COMPLEX) or carrying extras.
        """
        required = ",".join(repr(m) for m in self.REQUIRED_MEMBERS)
        self._run_ok(
            f"""
            required = set([{required}])
            names = set(m.name for m in NumericKind)
            assert names == required, (sorted(names), sorted(required))
            # values distinct
            vals = [m.value for m in NumericKind]
            assert len(set(vals)) == len(vals), vals
            print("OK")
            """
        )

    def test_canonical_package_import_path(self):
        """L1->L2: ``from black.numeric_kind import ...`` succeeds via the src path.

        The module is required to be importable through the ``black`` package
        namespace WITHOUT importing the (heavy) top-level ``black`` package
        machinery; it is stdlib-only, so a direct submodule import must work.
        """
        script = (
            "from black.numeric_kind import "
            "NumericKind, classify_numeric, NumericError\n"
            "import enum\n"
            "assert issubclass(NumericKind, enum.Enum)\n"
            "assert issubclass(NumericError, ValueError)\n"
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
    # L2 -- per-category runtime classification
    # ------------------------------------------------------------------ #
    def test_decimal_int_classification(self):
        """L2: plain and underscore-separated decimal integers -> DECIMAL_INT.

        A naive 'has a dot or 0x' classifier still gets these, but the
        underscore form pins that digit separators are tolerated.
        """
        self._run_ok(
            """
            for s in ("42", "0", "7", "1_000", "123_456_789"):
                r = classify_numeric(s)
                assert r is NumericKind.DECIMAL_INT, (s, r)
            print("OK")
            """
        )

    def test_base_prefix_classification(self):
        """L2: hex/octal/binary prefixes (case-insensitive) classify correctly.

        Covers ``0xFF`` -> HEX, ``0o17`` -> OCTAL, ``0b1010`` -> BINARY, plus
        upper/lower-case prefixes and an underscore-bearing hex (``0xFF_FF``).
        """
        self._run_ok(
            """
            cases = {
                "0xFF": NumericKind.HEX,
                "0XfF": NumericKind.HEX,
                "0xFF_FF": NumericKind.HEX,
                "0o17": NumericKind.OCTAL,
                "0O17": NumericKind.OCTAL,
                "0o1_7": NumericKind.OCTAL,
                "0b1010": NumericKind.BINARY,
                "0B1010": NumericKind.BINARY,
                "0b1_010": NumericKind.BINARY,
            }
            for s, want in cases.items():
                r = classify_numeric(s)
                assert r is want, (s, r, want)
            print("OK")
            """
        )

    def test_float_classification(self):
        """L2: a dot without an exponent -> FLOAT, including underscore-bearing forms.

        ``"1_0.5_0"`` -> FLOAT is a documented edge case; the naive
        'has a dot' check would also pass these, so this guards the common path.
        """
        self._run_ok(
            """
            for s in ("3.14", "0.0", ".5", "5.", "1_0.5_0"):
                r = classify_numeric(s)
                assert r is NumericKind.FLOAT, (s, r)
            print("OK")
            """
        )

    def test_scientific_classification(self):
        """L2: an exponent marker ``e`` (case-insensitive, signed) -> SCIENTIFIC.

        Critically NOT FLOAT: a naive 'has a dot' classifier would call
        ``"1.5e10"`` a FLOAT and ``"2E-3"`` a DECIMAL_INT, so these fail it.
        """
        self._run_ok(
            """
            for s in ("1.5e10", "2E-3", "1e5", "6.022E23", "2e+3", "0e0"):
                r = classify_numeric(s)
                assert r is NumericKind.SCIENTIFIC, (s, r)
            print("OK")
            """
        )

    def test_complex_classification(self):
        """L2: a trailing ``j``/``J`` over a valid magnitude -> COMPLEX.

        ``"10j"`` and ``"3.0J"`` are COMPLEX, not DECIMAL_INT/FLOAT -- a naive
        classifier that ignores the ``j`` suffix misclassifies both.
        """
        self._run_ok(
            """
            for s in ("10j", "3.0J", "0j", "1_000j", "2.5e3j"):
                r = classify_numeric(s)
                assert r is NumericKind.COMPLEX, (s, r)
            print("OK")
            """
        )

    def test_full_documented_table(self):
        """L2: the exact Expected-Functionality table from the doc holds end-to-end.

        Drives every row of the doc's table in one shot so the seven categories
        are all distinguished by a single consistent implementation.
        """
        self._run_ok(
            """
            table = [
                ("42", NumericKind.DECIMAL_INT),
                ("1_000", NumericKind.DECIMAL_INT),
                ("0xFF", NumericKind.HEX),
                ("0o17", NumericKind.OCTAL),
                ("0b1010", NumericKind.BINARY),
                ("3.14", NumericKind.FLOAT),
                ("1.5e10", NumericKind.SCIENTIFIC),
                ("2E-3", NumericKind.SCIENTIFIC),
                ("10j", NumericKind.COMPLEX),
                ("3.0J", NumericKind.COMPLEX),
            ]
            for s, want in table:
                r = classify_numeric(s)
                assert r is want, (s, r, want)
            # every category must have been produced at least once
            produced = set(classify_numeric(s) for s, _ in table)
            assert produced == {
                NumericKind.DECIMAL_INT, NumericKind.HEX, NumericKind.OCTAL,
                NumericKind.BINARY, NumericKind.FLOAT, NumericKind.SCIENTIFIC,
                NumericKind.COMPLEX,
            }, produced
            print("OK")
            """
        )

    def test_malformed_inputs_raise(self):
        """L2: empty / malformed literals raise NumericError (a ValueError subclass).

        Covers ``""``, ``"abc"``, ``"0xG1"``, ``"1.2.3"``, ``"1e"`` from the doc
        plus a few more, asserting the raised type is exactly the project's
        ``NumericError`` (not a bare ValueError/TypeError).
        """
        self._run_ok(
            """
            bad = ["", "abc", "0xG1", "1.2.3", "1e", "0x", "0b", "0o",
                   "1.2e", "j", "1ej", "..", "++1", "1_", "_1", "1__0"]
            for s in bad:
                try:
                    r = classify_numeric(s)
                except NumericError as exc:
                    assert isinstance(exc, ValueError)
                else:
                    raise AssertionError(f"malformed {s!r} should raise, got {r!r}")
            print("OK")
            """
        )

    def test_non_string_inputs_raise(self):
        """L2: a non-``str`` argument raises NumericError (never silently coerced).

        Numbers, bytes, None and containers must all be rejected -- a naive
        implementation that does ``str(text)`` first would wrongly classify
        ``42`` (int) or ``3.14`` (float).
        """
        self._run_ok(
            """
            for bad in (42, 3.14, b"42", None, ["1"], ("1",), {"1": 1}, 1j, True):
                try:
                    r = classify_numeric(bad)
                except NumericError as exc:
                    assert isinstance(exc, ValueError)
                else:
                    raise AssertionError(f"non-str {bad!r} should raise, got {r!r}")
            print("OK")
            """
        )

    def test_underscore_does_not_change_category(self):
        """L2: digit separators never alter the category vs. their unseparated form.

        Pins that a naive implementation cannot just strip-and-guess wrongly:
        each underscore variant must match its plain counterpart's category.
        """
        self._run_ok(
            """
            pairs = [
                ("1000", "1_000"),
                ("123456", "123_456"),
                ("0xFFFF", "0xFF_FF"),
                ("0b10101010", "0b1010_1010"),
                ("10.50", "1_0.5_0"),
                ("100000j", "100_000j"),
                ("15e10", "1_5e10"),
            ]
            for plain, sep in pairs:
                a = classify_numeric(plain)
                b = classify_numeric(sep)
                assert a is b, (plain, a, sep, b)
            print("OK")
            """
        )

    def test_return_values_are_enum_members(self):
        """L2: classify_numeric returns NumericKind members, not strings/ints.

        A stub that returns the category name as a plain string fails here.
        """
        self._run_ok(
            """
            for s in ("42", "0xFF", "0o17", "0b1010", "3.14", "1e3", "2j"):
                r = classify_numeric(s)
                assert isinstance(r, NumericKind), (s, type(r), r)
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
        must satisfy it. Drives the doc's exact ``mypy`` command.
        """
        result = subprocess.run(
            ["python", "-m", "mypy", "src/black/numeric_kind.py"],
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
        """L2: the agent's tests/test_numeric_kind.py passes under pytest.

        Runs exactly the command from the Acceptance Criteria, scoped to the
        new test file, and asserts a non-empty passing collection.
        """
        result = subprocess.run(
            ["python", "-m", "pytest", "tests/test_numeric_kind.py", "-q"],
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

    def test_native_unit_tests_have_enough_cases(self):
        """L2: the agent's test file actually collects >= 12 cases as the doc requires.

        Parametrized cases count individually. Guards against a one-assertion
        placeholder masquerading as the required suite.
        """
        result = subprocess.run(
            ["python", "-m", "pytest", "tests/test_numeric_kind.py",
             "--collect-only", "-q"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=300,
        )
        combined = result.stdout + result.stderr
        assert result.returncode == 0, "collection failed\n" + combined
        # count collected test node ids (lines containing '::')
        collected = [
            ln for ln in result.stdout.splitlines() if "::" in ln
        ]
        assert len(collected) >= 12, (
            f"expected >=12 collected cases, got {len(collected)}\n" + combined
        )

    def test_self_contained_no_third_party_imports(self):
        """L2: the module imports stdlib only -- it must load with click/tomllib/black absent.

        We load the module file with a sys.path that does NOT include the repo
        ``src`` dir, so any accidental ``import click`` / ``from black import``
        dependency would surface as an ImportError. The module file itself is
        loaded by absolute path and exercised once.
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
                        "isolated_numeric_kind", {self.MODULE_PATH!r}
                    )
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)
                    # exercise it once to ensure no lazy third-party import inside funcs
                    assert mod.classify_numeric("42") is mod.NumericKind.DECIMAL_INT
                    assert mod.classify_numeric("2j") is mod.NumericKind.COMPLEX
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
