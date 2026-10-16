"""Tests for skill: mypy-type-checking (ext6 task: Add a Comment-Pragma Registry).

The agent must create a self-contained, standard-library-only module
``src/black/pragma_registry.py`` inside the ``black`` repository exposing an
``enum.Enum`` named ``Pragma`` (members ``NONE``, ``FMT_OFF``, ``FMT_ON``,
``FMT_SKIP``, ``TYPE_IGNORE``), a function ``classify_comment(text)``, and an
exception ``PragmaError`` (a subclass of ``ValueError``); plus a deterministic
unit-test file ``tests/test_pragma_registry.py``.

This suite verifies the deliverable from several angles:

* L1 -- the deliverable files exist and are minimally well-formed.
* L2 -- the runtime classification behaviour is exercised independently by
  driving the module through a fresh Python subprocess (so a naive solution that
  merely substring-matches ``fmt`` / ``type`` -- and therefore misclassifies
  ``# format: off`` or ``# typeignore`` -- fails), the project's configured
  (strict) ``mypy`` static-analysis gate is run over the new module, and the
  agent-authored pytest file is executed with the native toolchain via
  ``python -m pytest tests/test_pragma_registry.py -q``.

The module is intentionally imported directly from its file location (and also
via the canonical ``black.pragma_registry`` package path) so that the heavy,
optional third-party dependencies of the top-level ``black`` package never gate
these behavioural checks.
"""

import os
import subprocess
import textwrap


class TestMypyTypeChecking:
    REPO_DIR = "/workspace/black"

    MODULE_PATH = os.path.join(REPO_DIR, "src", "black", "pragma_registry.py")
    TEST_PATH = os.path.join(REPO_DIR, "tests", "test_pragma_registry.py")
    SRC_DIR = os.path.join(REPO_DIR, "src")

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _run_driver(self, body, timeout=120):
        """Run a Python snippet that imports the pragma module directly.

        The module file is loaded by path via importlib so that we do NOT pull
        in the (heavy, optional-dependency-laden) top-level ``black`` package.
        ``Pragma``/``classify_comment``/``PragmaError`` are injected into the
        snippet's globals.
        """
        preamble = textwrap.dedent(
            """
            import importlib.util, sys, os
            _mod_path = {module_path!r}
            spec = importlib.util.spec_from_file_location("_pragma_probe", _mod_path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            Pragma = mod.Pragma
            classify_comment = mod.classify_comment
            PragmaError = mod.PragmaError
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
        """L1: the new registry module file is created at the required path."""
        assert os.path.isfile(self.MODULE_PATH), (
            f"expected pragma module at {self.MODULE_PATH}"
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

        ``Pragma`` must be an ``enum.Enum`` subclass, ``classify_comment`` must be
        callable, and ``PragmaError`` must be a subclass of ``ValueError``.
        """
        result = self._run_ok(
            """
            import enum
            assert isinstance(Pragma, type)
            assert issubclass(Pragma, enum.Enum)
            assert callable(classify_comment)
            assert isinstance(PragmaError, type)
            assert issubclass(PragmaError, ValueError)
            print("OK")
            """
        )
        assert "OK" in result.stdout

    def test_pragma_enum_members(self):
        """L1->L2: ``Pragma`` has exactly the five documented members and no more.

        Maps to: NONE, FMT_OFF, FMT_ON, FMT_SKIP, TYPE_IGNORE -- with NONE present
        for ordinary comments. A stub enum that omits a member (e.g. TYPE_IGNORE)
        or adds extras fails here.
        """
        self._run_ok(
            """
            names = {m.name for m in Pragma}
            expected = {"NONE", "FMT_OFF", "FMT_ON", "FMT_SKIP", "TYPE_IGNORE"}
            assert names == expected, (names, expected)
            # each is accessible as an attribute too
            for n in expected:
                assert getattr(Pragma, n).name == n
            print("OK")
            """
        )

    def test_canonical_package_import_path(self):
        """L1->L2: ``from black.pragma_registry import ...`` succeeds via the src path.

        The module is required to be importable through the ``black`` package
        namespace WITHOUT importing the (heavy) top-level ``black`` package
        machinery; it is stdlib-only, so a direct submodule import must work.
        """
        script = (
            "from black.pragma_registry import Pragma, classify_comment, PragmaError\n"
            "import enum\n"
            "assert issubclass(Pragma, enum.Enum)\n"
            "assert issubclass(PragmaError, ValueError)\n"
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
    # L2 -- classification behaviour
    # ------------------------------------------------------------------ #
    def test_fmt_off_on_classification(self):
        """L2: ``fmt: off`` / ``fmt: on`` classify correctly with both spacings.

        Maps to: ``# fmt: off`` and ``# fmt:off`` -> FMT_OFF; ``# fmt: on`` and
        ``#fmt:on`` -> FMT_ON. Exactly one or zero spaces around the colon.
        """
        self._run_ok(
            """
            assert classify_comment("# fmt: off") is Pragma.FMT_OFF
            assert classify_comment("# fmt:off") is Pragma.FMT_OFF
            assert classify_comment("#fmt: off") is Pragma.FMT_OFF
            assert classify_comment("#fmt:off") is Pragma.FMT_OFF

            assert classify_comment("# fmt: on") is Pragma.FMT_ON
            assert classify_comment("# fmt:on") is Pragma.FMT_ON
            assert classify_comment("#fmt:on") is Pragma.FMT_ON
            print("OK")
            """
        )

    def test_fmt_skip_classification(self):
        """L2: ``fmt: skip`` classifies as FMT_SKIP, including trailing-skip form.

        Maps to: ``# fmt: skip`` / ``# fmt:skip`` -> FMT_SKIP; and a trailing
        ``# fmt: skip`` appended to an unrelated comment (e.g.
        ``# noqa: E501 # fmt: skip``) also -> FMT_SKIP.
        """
        self._run_ok(
            """
            assert classify_comment("# fmt: skip") is Pragma.FMT_SKIP
            assert classify_comment("# fmt:skip") is Pragma.FMT_SKIP
            assert classify_comment("# noqa: E501 # fmt: skip") is Pragma.FMT_SKIP
            assert classify_comment("# something else # fmt: skip") is Pragma.FMT_SKIP
            # but a plain unrelated comment is not a skip
            assert classify_comment("# skip this") is Pragma.NONE
            print("OK")
            """
        )

    def test_type_ignore_classification(self):
        """L2: ``type: ignore`` (with optional ``[code]``) classifies as TYPE_IGNORE.

        Maps to: ``# type: ignore`` and ``# type: ignore[arg-type]`` -> TYPE_IGNORE.
        """
        self._run_ok(
            """
            assert classify_comment("# type: ignore") is Pragma.TYPE_IGNORE
            assert classify_comment("# type:ignore") is Pragma.TYPE_IGNORE
            assert classify_comment("# type: ignore[arg-type]") is Pragma.TYPE_IGNORE
            assert classify_comment("# type: ignore[no-any-return]") is Pragma.TYPE_IGNORE
            print("OK")
            """
        )

    def test_none_and_lookalikes(self):
        """L2: ordinary comments and lookalikes classify as NONE (discriminative).

        This is the case that a naive substring-matching implementation fails:
        ``# format: off`` and ``# fmtoff`` must NOT be FMT_OFF, and ``# typeignore``
        / ``# type:ignoreextra`` must NOT be TYPE_IGNORE.
        """
        self._run_ok(
            """
            assert classify_comment("# a normal comment") is Pragma.NONE
            assert classify_comment("# format: off") is Pragma.NONE
            assert classify_comment("# fmtoff") is Pragma.NONE
            assert classify_comment("# fmt") is Pragma.NONE
            assert classify_comment("# typeignore") is Pragma.NONE
            assert classify_comment("# type:ignoreextra") is Pragma.NONE
            assert classify_comment("# typing: ignore") is Pragma.NONE
            print("OK")
            """
        )

    def test_leading_whitespace_allowed(self):
        """L2: leading whitespace before the ``#`` is permitted.

        Maps to: ``"   # fmt: off"`` -> FMT_OFF. Other directives behave the same.
        """
        self._run_ok(
            """
            assert classify_comment("   # fmt: off") is Pragma.FMT_OFF
            assert classify_comment("\\t# type: ignore") is Pragma.TYPE_IGNORE
            assert classify_comment("  # fmt: skip") is Pragma.FMT_SKIP
            assert classify_comment("  # plain") is Pragma.NONE
            print("OK")
            """
        )

    def test_missing_hash_raises_pragma_error(self):
        """L2: a non-comment string (no leading ``#``) raises PragmaError.

        Maps to: the ``PragmaError`` edge case. A bare statement, an empty string,
        and a whitespace-only string all lack a ``#`` and must raise.
        """
        self._run_ok(
            """
            for bad in ("not a comment", "fmt: off", "", "   ", "x = 1  # fmt: off"):
                try:
                    classify_comment(bad)
                except PragmaError:
                    pass
                else:
                    raise AssertionError(f"expected PragmaError for {bad!r}")
            print("OK")
            """
        )

    def test_return_type_is_pragma_enum(self):
        """L2: every classification returns a ``Pragma`` enum member, never a str/None.

        A naive implementation that returns the comment text or a raw string fails
        here.
        """
        self._run_ok(
            """
            samples = [
                "# fmt: off", "#fmt:on", "# fmt: skip",
                "# noqa: E501 # fmt: skip", "# type: ignore",
                "# type: ignore[arg-type]", "# a normal comment", "# format: off",
            ]
            for s in samples:
                r = classify_comment(s)
                assert isinstance(r, Pragma), (s, r, type(r))
            print("OK")
            """
        )

    def test_expected_functionality_table(self):
        """L2: the full Expected-Functionality table from the doc holds exactly.

        Drives every row of the doc's table in one shot as an end-to-end gate.
        """
        self._run_ok(
            """
            cases = {
                "# fmt: off": Pragma.FMT_OFF,
                "#fmt:on": Pragma.FMT_ON,
                "# fmt: skip": Pragma.FMT_SKIP,
                "# noqa: E501 # fmt: skip": Pragma.FMT_SKIP,
                "# type: ignore": Pragma.TYPE_IGNORE,
                "# type: ignore[arg-type]": Pragma.TYPE_IGNORE,
                "# a normal comment": Pragma.NONE,
                "# format: off": Pragma.NONE,
            }
            for text, expected in cases.items():
                got = classify_comment(text)
                assert got is expected, (text, got, expected)
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
        must satisfy it. Drives exactly ``mypy src/black/pragma_registry.py``.
        """
        result = subprocess.run(
            ["python", "-m", "mypy", "src/black/pragma_registry.py"],
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
        """L2: the agent's tests/test_pragma_registry.py passes under pytest.

        Runs exactly the command from the Acceptance Criteria, scoped to the new
        test file, and asserts a non-empty passing collection.
        """
        result = subprocess.run(
            ["python", "-m", "pytest", "tests/test_pragma_registry.py", "-q"],
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
        loaded by absolute path.
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
                        "isolated_pragma_registry", {self.MODULE_PATH!r}
                    )
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)
                    # exercise it once to ensure no lazy third-party import inside funcs
                    assert mod.classify_comment("# fmt: off") is mod.Pragma.FMT_OFF
                    assert mod.classify_comment("# nope") is mod.Pragma.NONE
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
