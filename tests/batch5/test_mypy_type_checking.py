"""Tests for skill: mypy-type-checking (task: Add a Target-Version Range Resolver).

The agent must create a self-contained, standard-library-only module
``src/black/version_range.py`` inside the ``black`` repository exposing an
ordered ``enum.Enum`` ``PyVersion``, a ``VersionRange`` class, and a
``RangeError`` exception (subclass of ``ValueError``), plus a deterministic
unit-test file ``tests/test_version_range.py``.

This suite verifies the deliverable from two angles:

* L1 -- the deliverable files exist, are minimally well-formed, and the three
  required public names import with the right shapes.
* L2 -- the runtime behaviour of ``PyVersion`` ordering/``parse``, and of
  ``VersionRange.minimum/maximum/covers/is_contiguous/as_sorted`` is exercised
  independently by driving the module through a fresh Python subprocess. The
  discriminative cases encode the doc's "naive implementation must fail" note:
  a solution that treats the *supplied set* as the coverage set (so
  ``covers`` outside the set returns ``False``) or that ignores the contiguity
  gap (so a gapped range reports ``is_contiguous == True``) fails here. The
  project's configured strict ``mypy`` static-analysis gate is run over the new
  module, and the agent-authored pytest file is executed with the native
  toolchain.

The module is intentionally imported directly from its file location (and also
via the canonical ``black.version_range`` package path) so that the heavy,
optional third-party dependencies of the top-level ``black`` package never gate
these behavioural checks.
"""

import os
import subprocess
import textwrap


class TestMypyTypeChecking:
    REPO_DIR = "/workspace/black"

    MODULE_PATH = os.path.join(REPO_DIR, "src", "black", "version_range.py")
    TEST_PATH = os.path.join(REPO_DIR, "tests", "test_version_range.py")
    SRC_DIR = os.path.join(REPO_DIR, "src")

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _run_driver(self, body, timeout=120):
        """Run a Python snippet that imports the range module directly.

        The module file is loaded by path via importlib so that we do NOT pull
        in the (heavy, optional-dependency-laden) top-level ``black`` package.
        ``PyVersion``/``VersionRange``/``RangeError`` are injected into the
        snippet's globals.
        """
        preamble = textwrap.dedent(
            """
            import importlib.util, sys, os
            _mod_path = {module_path!r}
            spec = importlib.util.spec_from_file_location("_version_range_probe", _mod_path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            PyVersion = mod.PyVersion
            VersionRange = mod.VersionRange
            RangeError = mod.RangeError
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
        """L1: the new range-resolver module file is created at the required path."""
        assert os.path.isfile(self.MODULE_PATH), (
            f"expected version_range module at {self.MODULE_PATH}"
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

        ``PyVersion`` is an Enum subclass, ``VersionRange`` is a class,
        ``RangeError`` is a subclass of ``ValueError``.
        """
        result = self._run_ok(
            """
            import enum
            assert isinstance(PyVersion, type) and issubclass(PyVersion, enum.Enum)
            assert isinstance(VersionRange, type)
            assert isinstance(RangeError, type)
            assert issubclass(RangeError, ValueError)
            print("OK")
            """
        )
        assert "OK" in result.stdout

    def test_canonical_package_import_path(self):
        """L1->L2: ``from black.version_range import ...`` succeeds via the src path.

        The module is required to be importable through the ``black`` package
        namespace WITHOUT importing the (heavy) top-level ``black`` package
        machinery; it is stdlib-only, so a direct submodule import must work.
        """
        script = (
            "from black.version_range import PyVersion, VersionRange, RangeError\n"
            "assert issubclass(RangeError, ValueError)\n"
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
    # L2 -- PyVersion enum members, values, ordering
    # ------------------------------------------------------------------ #
    def test_pyversion_members_and_values(self):
        """L2: PyVersion has the eight members with the exact integer values.

        Maps to: PY36..PY313 with values 6..13, and value ordering matching
        release order.
        """
        self._run_ok(
            """
            expected = {
                "PY36": 6, "PY37": 7, "PY38": 8, "PY39": 9,
                "PY310": 10, "PY311": 11, "PY312": 12, "PY313": 13,
            }
            members = {m.name: m.value for m in PyVersion}
            assert members == expected, members
            # ordering by value matches release order
            ordered = sorted(PyVersion, key=lambda m: m.value)
            assert [m.name for m in ordered] == [
                "PY36", "PY37", "PY38", "PY39", "PY310", "PY311", "PY312", "PY313",
            ], [m.name for m in ordered]
            print("OK")
            """
        )

    def test_pyversion_parse_roundtrip(self):
        """L2: PyVersion.parse maps case-insensitive names to members and rejects junk.

        Maps to: ``parse("py312") is PY312``, ``"PY311"``/``"py311"`` both work,
        and unknown names raise RangeError.
        """
        self._run_ok(
            """
            assert PyVersion.parse("py312") is PyVersion.PY312
            assert PyVersion.parse("PY312") is PyVersion.PY312
            assert PyVersion.parse("py311") is PyVersion.PY311
            assert PyVersion.parse("PY311") is PyVersion.PY311
            assert PyVersion.parse("Py36") is PyVersion.PY36

            for bad in ("py999", "py35", "", "py3", "311", "py 311", None.__class__):
                try:
                    PyVersion.parse(bad)
                except RangeError:
                    pass
                else:
                    raise AssertionError(f"parse({bad!r}) should raise RangeError")
            print("OK")
            """
        )

    # ------------------------------------------------------------------ #
    # L2 -- VersionRange min/max
    # ------------------------------------------------------------------ #
    def test_minimum_and_maximum(self):
        """L2: minimum/maximum return the lowest/highest PyVersion by value.

        Maps to: ``VersionRange([PY38, PY310, PY39]).minimum is PY38`` and
        ``.maximum is PY310`` (order of the input iterable is irrelevant).
        """
        self._run_ok(
            """
            PV = PyVersion
            r = VersionRange([PV.PY38, PV.PY310, PV.PY39])
            assert r.minimum is PV.PY38, r.minimum
            assert r.maximum is PV.PY310, r.maximum

            # reversed input order yields the same min/max
            r2 = VersionRange([PV.PY312, PV.PY36, PV.PY311])
            assert r2.minimum is PV.PY36
            assert r2.maximum is PV.PY312
            print("OK")
            """
        )

    def test_single_element_range(self):
        """L2: a single-element range has minimum is maximum and is contiguous.

        Maps to: the documented single-element edge case.
        """
        self._run_ok(
            """
            PV = PyVersion
            r = VersionRange([PV.PY39])
            assert r.minimum is PV.PY39
            assert r.maximum is PV.PY39
            assert r.minimum is r.maximum
            assert r.is_contiguous is True
            assert r.covers(PV.PY39) is True
            assert r.covers(PV.PY38) is False
            assert r.covers(PV.PY310) is False
            print("OK")
            """
        )

    # ------------------------------------------------------------------ #
    # L2 -- covers: inclusive contiguous range, NOT the supplied set
    # ------------------------------------------------------------------ #
    def test_covers_is_inclusive_range_not_membership(self):
        """L2: covers(v) is min<=v<=max by value, regardless of original membership.

        This is the key discriminator: a naive implementation that returns
        ``version in supplied_set`` fails because PY39 was never supplied to a
        ``[PY38, PY311]`` range yet must be covered, while PY36/PY312 outside
        the bounds must not be covered.
        """
        self._run_ok(
            """
            PV = PyVersion
            # gapped range: only PY38 and PY311 supplied
            r = VersionRange([PV.PY38, PV.PY311])
            # inside the inclusive bounds, even though not supplied
            for v in (PV.PY38, PV.PY39, PV.PY310, PV.PY311):
                assert r.covers(v) is True, ("should cover", v)
            # outside the bounds
            for v in (PV.PY36, PV.PY37, PV.PY312, PV.PY313):
                assert r.covers(v) is False, ("should NOT cover", v)

            # contiguous example from the doc
            r2 = VersionRange([PV.PY38, PV.PY310, PV.PY39])
            assert r2.covers(PV.PY39) is True
            assert r2.covers(PV.PY311) is False
            assert r2.covers(PV.PY37) is False

            # return type is a real bool
            assert type(r2.covers(PV.PY39)) is bool
            print("OK")
            """
        )

    # ------------------------------------------------------------------ #
    # L2 -- is_contiguous: gap detection
    # ------------------------------------------------------------------ #
    def test_is_contiguous_distinguishes_gaps(self):
        """L2: is_contiguous is True only if every in-bounds version was supplied.

        Discriminator: ``[PY38, PY310, PY39]`` is contiguous (True) while
        ``[PY38, PY311]`` has gaps PY39/PY310 missing (False). A naive impl
        that always returns True, or that confuses contiguity with covers,
        fails here.
        """
        self._run_ok(
            """
            PV = PyVersion
            assert VersionRange([PV.PY38, PV.PY310, PV.PY39]).is_contiguous is True
            assert VersionRange([PV.PY38, PV.PY311]).is_contiguous is False
            # missing single interior version
            assert VersionRange([PV.PY38, PV.PY39, PV.PY311]).is_contiguous is False
            # full contiguous span
            assert VersionRange(
                [PV.PY38, PV.PY39, PV.PY310, PV.PY311]
            ).is_contiguous is True
            # two adjacent versions are contiguous
            assert VersionRange([PV.PY312, PV.PY313]).is_contiguous is True
            # two non-adjacent versions are not
            assert VersionRange([PV.PY36, PV.PY38]).is_contiguous is False

            assert type(VersionRange([PV.PY38, PV.PY311]).is_contiguous) is bool
            print("OK")
            """
        )

    def test_duplicates_do_not_affect_results(self):
        """L2: duplicate input versions do not change min/max/is_contiguous.

        Maps to: duplicate collapsing edge case. A contiguous set stays
        contiguous and a gapped set stays gapped despite repeated members.
        """
        self._run_ok(
            """
            PV = PyVersion
            r = VersionRange([PV.PY38, PV.PY38, PV.PY39, PV.PY39, PV.PY310])
            assert r.minimum is PV.PY38
            assert r.maximum is PV.PY310
            assert r.is_contiguous is True

            g = VersionRange([PV.PY38, PV.PY38, PV.PY311, PV.PY311])
            assert g.minimum is PV.PY38
            assert g.maximum is PV.PY311
            assert g.is_contiguous is False
            print("OK")
            """
        )

    def test_as_sorted_distinct_ascending(self):
        """L2: as_sorted returns distinct supplied versions in ascending value order.

        Maps to: duplicates collapsed, ascending by value, and a returned list
        (not the internal storage) of PyVersion members.
        """
        self._run_ok(
            """
            PV = PyVersion
            r = VersionRange([PV.PY310, PV.PY38, PV.PY39, PV.PY38, PV.PY310])
            out = r.as_sorted()
            assert isinstance(out, list)
            assert out == [PV.PY38, PV.PY39, PV.PY310], out
            # distinct
            assert len(out) == len(set(out))
            # all members of PyVersion
            assert all(isinstance(e, PV) for e in out)

            # gapped set: as_sorted lists ONLY supplied versions, not the full span
            g = VersionRange([PV.PY311, PV.PY38])
            assert g.as_sorted() == [PV.PY38, PV.PY311], g.as_sorted()
            print("OK")
            """
        )

    def test_constructor_and_parse_error_cases(self):
        """L2: empty iterable, non-PyVersion element, and bad parse all raise RangeError.

        Maps to: the doc's "at least three distinct RangeError-raising inputs"
        plus the empty-iterable and wrong-type construction rules.
        """
        self._run_ok(
            """
            PV = PyVersion
            # empty iterable
            for empty in ([], (), set()):
                try:
                    VersionRange(empty)
                except RangeError:
                    pass
                else:
                    raise AssertionError(f"empty range {empty!r} must raise RangeError")

            # non-PyVersion element
            for bad in (
                [PV.PY38, 8],
                [PV.PY38, "PY39"],
                ["PY38"],
                [PV.PY38, None],
                [8, 9],
            ):
                try:
                    VersionRange(bad)
                except RangeError:
                    pass
                else:
                    raise AssertionError(f"non-PyVersion element {bad!r} must raise")

            # bad parse inputs
            for name in ("py999", "nope", ""):
                try:
                    PyVersion.parse(name)
                except RangeError:
                    pass
                else:
                    raise AssertionError(f"parse({name!r}) must raise RangeError")

            # RangeError is a ValueError
            try:
                VersionRange([])
            except ValueError:
                pass
            else:
                raise AssertionError("RangeError must be catchable as ValueError")
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
        must satisfy it. Runs exactly the doc's acceptance command.
        """
        result = subprocess.run(
            ["python", "-m", "mypy", "src/black/version_range.py"],
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
        """L2: the agent's tests/test_version_range.py passes under pytest.

        Runs exactly the command from the Acceptance Criteria, scoped to the
        new test file, and asserts a non-empty passing collection.
        """
        result = subprocess.run(
            ["python", "-m", "pytest", "tests/test_version_range.py", "-q"],
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
        """L2: the module imports stdlib only -- it must load with black/click absent.

        We load the module file with a sys.path that does NOT include the repo
        ``src`` dir, so any accidental ``from black import`` / third-party
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
                        "isolated_version_range", {self.MODULE_PATH!r}
                    )
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)
                    PV = mod.PyVersion
                    r = mod.VersionRange([PV.PY38, PV.PY310])
                    assert r.minimum is PV.PY38
                    assert r.maximum is PV.PY310
                    assert r.covers(PV.PY39) is True
                    assert r.is_contiguous is False
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
