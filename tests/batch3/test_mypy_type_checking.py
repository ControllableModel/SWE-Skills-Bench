"""Tests for skill: mypy-type-checking (variant ext3, task: Add a String-Prefix Normalizer).

The agent must create a self-contained, standard-library-only module
``src/black/prefix_normalize.py`` inside the ``black`` repository exposing
exactly ``normalize_prefix``, ``split_prefix`` and ``PrefixError`` (a subclass
of ``ValueError``), plus a deterministic unit-test file
``tests/test_prefix_normalize.py``.

Black normalizes Python string-literal prefixes (``f``/``r``/``b``/``u`` and
their valid combinations) to a canonical lowercased, ordered form (non-``r``
letter first, then ``r``), drops a redundant ``u``, and rejects any other
letter / over-long / disallowed-pair prefix. ``split_prefix`` separates the
leading prefix-letter run from the quote-onward remainder of a token.

This suite verifies the deliverable from two angles:

* L1 -- the deliverable files exist and are minimally well-formed, and the
  required public names import with the correct shapes.
* L2 -- the runtime behaviour of ``normalize_prefix`` / ``split_prefix`` is
  exercised independently by driving the module through a fresh Python
  subprocess (so a naive solution that merely lowercases -- without enforcing
  the allowed set, the canonical two-letter ordering, the ``u``-dropping rule,
  and the split contract -- fails). The project's configured strict ``mypy``
  static-analysis gate is run over the new module, and the agent-authored
  pytest file is executed with the native toolchain.

The module is intentionally imported directly from its file location (and also
via the canonical ``black.prefix_normalize`` package path) so that the heavy,
optional third-party dependencies of the top-level ``black`` package never gate
these behavioural checks.
"""

import os
import subprocess
import textwrap


class TestMypyTypeChecking:
    REPO_DIR = "/workspace/black"

    MODULE_PATH = os.path.join(REPO_DIR, "src", "black", "prefix_normalize.py")
    TEST_PATH = os.path.join(REPO_DIR, "tests", "test_prefix_normalize.py")
    SRC_DIR = os.path.join(REPO_DIR, "src")

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _run_driver(self, body, timeout=120):
        """Run a Python snippet with the prefix module loaded directly by path.

        The module file is loaded via importlib from its absolute path so that
        we do NOT pull in the (heavy, optional-dependency-laden) top-level
        ``black`` package. ``normalize_prefix`` / ``split_prefix`` /
        ``PrefixError`` are injected into the snippet's globals.
        """
        preamble = textwrap.dedent(
            """
            import importlib.util, sys, os
            _mod_path = {module_path!r}
            spec = importlib.util.spec_from_file_location("_prefix_normalize_probe", _mod_path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            normalize_prefix = mod.normalize_prefix
            split_prefix = mod.split_prefix
            PrefixError = mod.PrefixError
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
            f"expected prefix-normalizer module at {self.MODULE_PATH}"
        )
        assert os.path.getsize(self.MODULE_PATH) > 0

    def test_unit_test_file_exists(self):
        """L1: the deterministic unit-test file is created at the required path."""
        assert os.path.isfile(self.TEST_PATH), (
            f"expected unit-test file at {self.TEST_PATH}"
        )
        assert os.path.getsize(self.TEST_PATH) > 0

    def test_public_surface_importable(self):
        """L1->L2: the three required public names import with the right shapes.

        Also asserts ``PrefixError`` is a subclass of ``ValueError`` as required.
        """
        result = self._run_ok(
            """
            assert callable(normalize_prefix)
            assert callable(split_prefix)
            assert isinstance(PrefixError, type)
            assert issubclass(PrefixError, ValueError)
            print("OK")
            """
        )
        assert "OK" in result.stdout

    def test_canonical_package_import_path(self):
        """L1->L2: ``from black.prefix_normalize import ...`` succeeds via the src path.

        The module is required to live in the ``black`` package and to import
        only the standard library, so a direct submodule import must work
        WITHOUT importing the (heavy) top-level ``black`` package machinery.
        """
        script = (
            "from black.prefix_normalize import "
            "normalize_prefix, split_prefix, PrefixError\n"
            "assert issubclass(PrefixError, ValueError)\n"
            "assert normalize_prefix('') == ''\n"
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
    # L2 -- normalize_prefix runtime behaviour
    # ------------------------------------------------------------------ #
    def test_empty_and_single_letter_normalization(self):
        """L2: empty prefix and single f/r/b each lowercase to themselves.

        Maps to: ``normalize_prefix("")`` -> ``""`` and single ``f``/``r``/``b``
        (any case) -> the lowercased single letter. A stub returning a fixed
        value fails here.
        """
        self._run_ok(
            """
            assert normalize_prefix("") == ""
            for src, want in [
                ("f", "f"), ("F", "f"),
                ("r", "r"), ("R", "r"),
                ("b", "b"), ("B", "b"),
            ]:
                got = normalize_prefix(src)
                assert got == want, (src, got, want)
                assert isinstance(got, str)
            print("OK")
            """
        )

    def test_u_prefix_is_dropped(self):
        """L2: a lone ``u`` prefix (any case) normalizes to the empty string.

        Maps to: Black's removal of redundant ``u`` prefixes. A naive
        lowercaser that returns ``"u"`` fails here.
        """
        self._run_ok(
            """
            for src in ("u", "U"):
                got = normalize_prefix(src)
                assert got == "", (src, got)
            print("OK")
            """
        )

    def test_two_letter_canonical_ordering(self):
        """L2: valid two-letter prefixes are lowercased AND reordered (non-r, then r).

        Maps to: ``Rb`` -> ``br``, ``RF`` -> ``fr``, ``fR`` -> ``fr``,
        ``rb`` -> ``br``, ``rf`` -> ``fr``, ``br`` -> ``br``, ``fr`` -> ``fr``.
        A naive implementation that only lowercases (leaving ``rb``/``rf`` in
        their original order) fails the reorder assertions.
        """
        self._run_ok(
            """
            cases = {
                "Rb": "br", "bR": "br", "rb": "br", "BR": "br", "br": "br",
                "RF": "fr", "fR": "fr", "rf": "fr", "FR": "fr", "fr": "fr",
            }
            for src, want in cases.items():
                got = normalize_prefix(src)
                assert got == want, (src, got, want)
                # canonical form must always put 'r' last when both present
                assert got in ("br", "fr"), (src, got)
                assert got[-1] == "r", (src, got)
            print("OK")
            """
        )

    def test_invalid_prefixes_raise(self):
        """L2: disallowed letters / pairs / over-long prefixes raise PrefixError.

        Maps to: ``fb``, ``ru``/``ur``, ``ub``, ``u`` combined with anything,
        any non-frbu letter, and any 3+ letter run must raise. A permissive
        implementation that returns a lowercased string for these fails.
        """
        self._run_ok(
            """
            bad_inputs = [
                "fb", "bf",          # disallowed b+f pair
                "ru", "ur",          # u may only appear alone
                "ub", "bu",          # disallowed
                "uf", "fu",          # disallowed
                "xyz", "x", "z",     # non prefix letters
                "frb", "rfb", "bbb", # too long
                "ff", "rr", "bb",    # repeated letters are not valid pairs
                "uu",                # repeated u
            ]
            for src in bad_inputs:
                try:
                    out = normalize_prefix(src)
                except PrefixError:
                    pass
                else:
                    raise AssertionError(
                        f"normalize_prefix({src!r}) should raise PrefixError, got {out!r}"
                    )
            print("OK")
            """
        )

    def test_normalize_return_is_plain_str(self):
        """L2: normalize_prefix always returns a plain ``str`` for valid input.

        Guards against returning bytes/None/tuple for the canonical forms.
        """
        self._run_ok(
            """
            for src in ("", "F", "R", "B", "U", "Rb", "fR", "rf", "br"):
                got = normalize_prefix(src)
                assert type(got) is str, (src, type(got))
            print("OK")
            """
        )

    # ------------------------------------------------------------------ #
    # L2 -- split_prefix runtime behaviour
    # ------------------------------------------------------------------ #
    def test_split_prefix_basic_contract(self):
        """L2: split_prefix returns (prefix, rest) splitting at the opening quote.

        Maps to the documented examples: ``split_prefix('Rb"x"')`` ->
        ``("Rb", '"x"')`` and ``split_prefix("'x'")`` -> ``("", "'x'")``.
        ``rest`` must begin at the quote and concatenation must reconstruct the
        token. A stub that returns a constant or drops part of the token fails.
        """
        self._run_ok(
            r"""
            cases = [
                ('Rb"x"', ("Rb", '"x"')),
                ("'x'", ("", "'x'")),
                ('f"hello"', ("f", '"hello"')),
                ("rb'data'", ("rb", "rb'data'"[2:])),
                ('"plain"', ("", '"plain"')),
                ("'plain'", ("", "'plain'")),
            ]
            for token, want in cases:
                got = split_prefix(token)
                assert isinstance(got, tuple) and len(got) == 2, (token, got)
                prefix, rest = got
                assert (prefix, rest) == want, (token, got, want)
                # reconstruction invariant
                assert prefix + rest == token, (token, prefix, rest)
                # rest must start at a quote character
                assert rest[0] in ("'", '"'), (token, rest)
            print("OK")
            """
        )

    def test_split_prefix_preserves_case_of_prefix(self):
        """L2: split_prefix returns the prefix VERBATIM (no normalization here).

        split_prefix only separates; normalization is normalize_prefix's job.
        ``split_prefix('FR"q"')`` must yield prefix ``"FR"`` unchanged, not
        ``"fr"``. This discriminates an agent that conflates the two helpers.
        """
        self._run_ok(
            r"""
            prefix, rest = split_prefix('FR"q"')
            assert prefix == "FR", prefix
            assert rest == '"q"', rest

            prefix2, rest2 = split_prefix("Rb'z'")
            assert prefix2 == "Rb", prefix2
            assert rest2 == "'z'", rest2
            print("OK")
            """
        )

    def test_split_prefix_requires_a_quote(self):
        """L2: a token with no quote character raises PrefixError.

        Maps to the contract: ``split_prefix`` of a quote-less token must raise.
        A naive implementation that always returns ``(token, "")`` fails.
        """
        self._run_ok(
            """
            for token in ("frb", "nope", "", "abc123", "f"):
                try:
                    out = split_prefix(token)
                except PrefixError:
                    pass
                else:
                    raise AssertionError(
                        f"split_prefix({token!r}) should raise PrefixError, got {out!r}"
                    )
            print("OK")
            """
        )

    def test_split_then_normalize_roundtrip(self):
        """L2: composing split_prefix + normalize_prefix yields the canonical token prefix.

        Exercises the two helpers together against a quote, the documented unit
        of work: split a real token, normalize its prefix, confirm canonical
        ordering / case / u-dropping. Discriminates an implementation where one
        helper is correct but the other is a stub.
        """
        self._run_ok(
            r"""
            checks = [
                ('Rb"x"', "br"),
                ('FR"y"', "fr"),
                ('U"z"', ""),
                ("'plain'", ""),
                ('f"a"', "f"),
            ]
            for token, want_norm in checks:
                prefix, rest = split_prefix(token)
                got = normalize_prefix(prefix)
                assert got == want_norm, (token, prefix, got, want_norm)
                assert rest[0] in ("'", '"')
            print("OK")
            """
        )

    # ------------------------------------------------------------------ #
    # L2 -- static-analysis gate and native unit tests
    # ------------------------------------------------------------------ #
    def test_mypy_clean_on_new_module(self):
        """L2: the project's configured (strict) mypy reports no errors on the new module.

        This is the core acceptance gate for the mypy-type-checking skill. The
        repo's pyproject.toml sets ``strict = true`` (python 3.10, mypy_path =
        src); the agent's annotations must satisfy it.
        """
        result = subprocess.run(
            ["python", "-m", "mypy", "src/black/prefix_normalize.py"],
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
        """L2: the agent's tests/test_prefix_normalize.py passes under pytest.

        Runs exactly the command from the Acceptance Criteria, scoped to the
        new test file, and asserts a non-empty passing collection.
        """
        result = subprocess.run(
            ["python", "-m", "pytest", "tests/test_prefix_normalize.py", "-q"],
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
        """L2: the module imports stdlib only -- it must load with click/black absent.

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
                        "isolated_prefix_normalize", {self.MODULE_PATH!r}
                    )
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)
                    # exercise it once to ensure no lazy third-party import inside funcs
                    assert mod.normalize_prefix("Rb") == "br"
                    assert mod.split_prefix("'x'") == ("", "'x'")
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
