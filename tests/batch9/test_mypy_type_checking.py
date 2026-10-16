"""Tests for skill: mypy-type-checking (variant ext9 task: Add an Include/Exclude Path Filter).

The agent must create a self-contained, standard-library-only module
``src/black/path_filter.py`` inside the ``black`` repository exposing the class
``PathFilter`` and the exception ``FilterError`` (a subclass of ``ValueError``),
plus a deterministic unit-test file ``tests/test_path_filter.py``.

``PathFilter(includes, excludes)`` composes a set of glob include/exclude
patterns into a single ``is_included(path) -> bool`` decision over POSIX-style
relative paths, with these load-bearing rules:

* include-by-default when the include list is empty,
* exclusion takes precedence over inclusion,
* ``**`` matches across path segments while ``*`` stays within a segment,
* a slash-less pattern matches the final path segment only,
* empty-string / non-``str`` patterns, absolute paths, and non-``str`` paths
  all raise ``FilterError``,
* ``select(paths)`` filters preserving input order.

Verification strategy:

* L1 -- the deliverable files exist and are minimally well-formed; the public
  surface imports and has the right shapes (``FilterError`` subclasses
  ``ValueError``).
* L2 -- the runtime behaviour is exercised independently by driving the module
  through a fresh Python subprocess (an independent verification harness, so a
  naive solution that uses plain ``fnmatch`` without distinguishing ``**`` from
  ``*``/basename matching, or that lets include override exclude, fails); the
  project's configured strict ``mypy`` static-analysis gate is run over the new
  module (``mypy src/black/path_filter.py``); and the agent-authored pytest file
  is executed with the native toolchain (``pytest tests/test_path_filter.py -q``).

The module is imported directly from its file location (and also via the
canonical ``black.path_filter`` package path) so the heavy, optional
third-party dependencies of the top-level ``black`` package never gate these
behavioural checks.
"""

import os
import subprocess
import textwrap


class TestMypyTypeChecking:
    REPO_DIR = "/workspace/black"

    MODULE_PATH = os.path.join(REPO_DIR, "src", "black", "path_filter.py")
    TEST_PATH = os.path.join(REPO_DIR, "tests", "test_path_filter.py")
    SRC_DIR = os.path.join(REPO_DIR, "src")

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _run_driver(self, body, timeout=120):
        """Run a Python snippet that imports the path-filter module directly.

        The module file is loaded by path via importlib so we do NOT pull in
        the (heavy, optional-dependency-laden) top-level ``black`` package.
        ``PathFilter`` and ``FilterError`` are injected into the snippet's
        globals.
        """
        preamble = textwrap.dedent(
            """
            import importlib.util, sys, os
            _mod_path = {module_path!r}
            spec = importlib.util.spec_from_file_location("_path_filter_probe", _mod_path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            PathFilter = mod.PathFilter
            FilterError = mod.FilterError
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
        """L1: the new path-filter module file is created at the required path."""
        assert os.path.isfile(self.MODULE_PATH), (
            f"expected path-filter module at {self.MODULE_PATH}"
        )
        assert os.path.getsize(self.MODULE_PATH) > 0

    def test_unit_test_file_exists(self):
        """L1: the deterministic unit-test file is created at the required path."""
        assert os.path.isfile(self.TEST_PATH), (
            f"expected unit-test file at {self.TEST_PATH}"
        )
        assert os.path.getsize(self.TEST_PATH) > 0

    def test_public_surface_importable(self):
        """L1->L2: the two required public names import and have the right shapes.

        ``PathFilter`` must be a class and ``FilterError`` must be a subclass of
        ``ValueError`` as required by the doc.
        """
        result = self._run_ok(
            """
            assert isinstance(PathFilter, type)
            assert isinstance(FilterError, type)
            assert issubclass(FilterError, ValueError)
            # constructable with empty include/exclude sequences
            pf = PathFilter([], [])
            assert hasattr(pf, "is_included")
            assert hasattr(pf, "select")
            assert callable(pf.is_included)
            assert callable(pf.select)
            print("OK")
            """
        )
        assert "OK" in result.stdout

    def test_canonical_package_import_path(self):
        """L1->L2: ``from black.path_filter import ...`` succeeds via the src path.

        The module is required to be importable through the ``black`` package
        namespace WITHOUT importing the (heavy) top-level ``black`` package
        machinery; it is stdlib-only, so a direct submodule import must work.
        """
        script = (
            "from black.path_filter import PathFilter, FilterError\n"
            "assert issubclass(FilterError, ValueError)\n"
            "assert isinstance(PathFilter, type)\n"
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
    # L2 -- runtime matching behaviour
    # ------------------------------------------------------------------ #
    def test_include_by_default_when_empty_includes(self):
        """L2: an empty include list means "include everything by default".

        ``PathFilter([], ["**/*.pyi"])`` includes ``a/b.py`` but not ``a/b.pyi``;
        ``PathFilter([], [])`` includes any valid relative path.
        """
        self._run_ok(
            """
            pf = PathFilter([], ["**/*.pyi"])
            assert pf.is_included("a/b.py") is True
            assert pf.is_included("a/b.pyi") is False

            allpf = PathFilter([], [])
            for p in ("x.py", "a/b/c.txt", "deep/nested/path/file"):
                assert allpf.is_included(p) is True, p
            print("OK")
            """
        )

    def test_double_star_crosses_segments(self):
        """L2: ``**`` matches across path segments, while a basename glob does not.

        ``PathFilter(["**/*.py"], [])`` includes the deeply nested
        ``src/black/x.py``; a slash-less ``*.py`` matches the basename of a deep
        path; but ``tests/*`` (with a slash) does NOT match ``a/b/c.py``.

        A naive plain-``fnmatch`` implementation that does not special-case
        ``**`` / basename matching fails here.
        """
        self._run_ok(
            """
            deep = PathFilter(["**/*.py"], [])
            assert deep.is_included("src/black/x.py") is True
            assert deep.is_included("a/b/c.py") is True
            assert deep.is_included("a/b/c.txt") is False

            base = PathFilter(["*.py"], [])
            # slash-less pattern matches the FINAL segment only
            assert base.is_included("a/b/c.py") is True
            assert base.is_included("a/b/c.txt") is False
            assert base.is_included("top.py") is True

            # a slashed pattern is anchored across segments and must NOT match
            # an unrelated deep path
            slashed = PathFilter(["tests/*"], [])
            assert slashed.is_included("a/b/c.py") is False
            print("OK")
            """
        )

    def test_star_stays_within_segment(self):
        """L2: a single ``*`` matches within one segment and does not cross a slash.

        ``src/*.py`` matches ``src/x.py`` but not ``src/black/x.py`` (the single
        star cannot span the ``black/`` segment boundary).
        """
        self._run_ok(
            """
            pf = PathFilter(["src/*.py"], [])
            assert pf.is_included("src/x.py") is True
            assert pf.is_included("src/black/x.py") is False

            deep = PathFilter(["src/**/*.py"], [])
            assert deep.is_included("src/black/x.py") is True
            assert deep.is_included("src/x.py") is True
            print("OK")
            """
        )

    def test_exclude_beats_include(self):
        """L2: exclusion takes precedence even when a path also matches an include.

        ``PathFilter(["**/*.py"], ["**/test_*.py"]).is_included("tests/test_x.py")``
        is ``False``. A naive implementation that lets include override exclude
        fails here.
        """
        self._run_ok(
            """
            pf = PathFilter(["**/*.py"], ["**/test_*.py"])
            # ordinary .py is included
            assert pf.is_included("src/black/x.py") is True
            # but a test_*.py matches both include and exclude -> excluded wins
            assert pf.is_included("tests/test_x.py") is False
            assert pf.is_included("a/b/test_thing.py") is False

            # exclude precedence holds even with a directly-matching include
            pf2 = PathFilter(["a/b/c.py"], ["a/b/c.py"])
            assert pf2.is_included("a/b/c.py") is False
            print("OK")
            """
        )

    def test_is_included_returns_bool(self):
        """L2: ``is_included`` returns a genuine ``bool``, not a truthy match object.

        Guards against implementations returning ``re.Match`` / ``None`` /
        integers instead of ``True``/``False``.
        """
        self._run_ok(
            """
            pf = PathFilter(["**/*.py"], ["**/skip.py"])
            for p in ("src/x.py", "src/skip.py", "src/x.txt"):
                r = pf.is_included(p)
                assert type(r) is bool, (p, type(r))
            print("OK")
            """
        )

    def test_select_filters_and_preserves_order(self):
        """L2: ``select`` returns a list of the included paths in input order.

        Maps to the doc's "select filters and preserves order" requirement; the
        result must be a new ``list`` containing exactly the included entries.
        """
        self._run_ok(
            """
            pf = PathFilter(["**/*.py"], ["**/test_*.py"])
            paths = [
                "src/z.py",
                "tests/test_a.py",
                "src/a.py",
                "README.md",
                "src/b.py",
                "tests/test_b.py",
            ]
            out = pf.select(paths)
            assert out == ["src/z.py", "src/a.py", "src/b.py"], out
            assert isinstance(out, list)

            # include-by-default: select returns all valid paths unchanged-order
            allpf = PathFilter([], [])
            assert allpf.select(["b", "a", "c"]) == ["b", "a", "c"]

            # empty input -> empty list
            assert pf.select([]) == []
            print("OK")
            """
        )

    def test_multiple_includes_are_union(self):
        """L2: a path is included if it matches AT LEAST ONE include pattern.

        With includes ``["**/*.py", "**/*.pyi"]`` both ``a.py`` and ``a.pyi``
        are included, while ``a.txt`` is not.
        """
        self._run_ok(
            """
            pf = PathFilter(["**/*.py", "**/*.pyi"], [])
            assert pf.is_included("pkg/a.py") is True
            assert pf.is_included("pkg/a.pyi") is True
            assert pf.is_included("pkg/a.txt") is False
            print("OK")
            """
        )

    def test_filter_error_on_bad_patterns(self):
        """L2: empty-string and non-``str`` patterns raise ``FilterError`` at construction.

        Covers the doc's "an empty-string pattern, a non-``str`` pattern ...
        raise FilterError" for both the include and exclude lists.
        """
        self._run_ok(
            """
            bad_pattern_sets = [
                (["", "*.py"], []),
                (["*.py"], [""]),
                ([123], []),
                (["*.py"], [None]),
                ([["*.py"]], []),
            ]
            for inc, exc in bad_pattern_sets:
                try:
                    PathFilter(inc, exc)
                except FilterError:
                    pass
                else:
                    raise AssertionError(f"bad patterns {inc!r}/{exc!r} should raise FilterError")

            # FilterError is a ValueError subclass: catching ValueError also works
            try:
                PathFilter([""], [])
            except ValueError:
                pass
            else:
                raise AssertionError("FilterError must be catchable as ValueError")
            print("OK")
            """
        )

    def test_filter_error_on_bad_paths(self):
        """L2: absolute paths and non-``str`` paths raise ``FilterError`` at match time.

        Covers "a path that is not a ``str``, or is an absolute path (begins
        with ``/``), raises FilterError" — for both ``is_included`` and
        ``select``.
        """
        self._run_ok(
            """
            pf = PathFilter(["**/*.py"], [])

            for bad in ("/abs/x.py", "/x.py"):
                try:
                    pf.is_included(bad)
                except FilterError:
                    pass
                else:
                    raise AssertionError(f"absolute path {bad!r} should raise FilterError")

            for bad in (123, None, ["a/b.py"], b"a/b.py"):
                try:
                    pf.is_included(bad)
                except FilterError:
                    pass
                else:
                    raise AssertionError(f"non-str path {bad!r} should raise FilterError")

            # the same validation applies through select()
            try:
                pf.select(["src/a.py", "/abs/b.py"])
            except FilterError:
                pass
            else:
                raise AssertionError("select must validate each path and raise on absolute")
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
        must satisfy it. Drives exactly ``mypy src/black/path_filter.py``.
        """
        result = subprocess.run(
            ["python", "-m", "mypy", "src/black/path_filter.py"],
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
        """L2: the agent's tests/test_path_filter.py passes under pytest.

        Runs exactly the command from the Acceptance Criteria, scoped to the
        new test file, and asserts a non-empty passing collection (the doc
        requires at least 12 independent cases).
        """
        result = subprocess.run(
            ["python", "-m", "pytest", "tests/test_path_filter.py", "-q"],
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
                        "isolated_path_filter", {self.MODULE_PATH!r}
                    )
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)
                    # exercise it once to ensure no lazy third-party import inside funcs
                    pf = mod.PathFilter(["**/*.py"], ["**/test_*.py"])
                    assert pf.is_included("src/a.py") is True
                    assert pf.is_included("tests/test_a.py") is False
                    assert pf.select(["src/a.py", "tests/test_a.py"]) == ["src/a.py"]
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
