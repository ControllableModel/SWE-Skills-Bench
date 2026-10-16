"""Tests for skill: mypy-type-checking (task: Add a Changed-Line-Range Merger).

The agent must create a self-contained, standard-library-only module
``src/black/range_merge.py`` inside the ``black`` repository exposing
``LineRange``, ``merge_ranges`` and ``RangeMergeError``, plus a deterministic
unit-test file ``tests/test_range_merge.py``.

This suite verifies the deliverable from two angles:

* L1 -- the deliverable files exist and are minimally well-formed, and the
  three required public names import with the right shapes (``RangeMergeError``
  is a ``ValueError`` subclass).
* L2 -- the runtime behaviour of ``LineRange`` construction/validation and
  ``merge_ranges`` is exercised independently by driving the module through a
  fresh Python subprocess. A naive solution that only sorts without merging, or
  that merges true overlaps but misses adjacency (the ``end + 1`` off-by-one),
  is rejected. The project's configured strict ``mypy`` static-analysis gate is
  run over the new module (the core skill acceptance gate), and the
  agent-authored pytest file is executed with the native toolchain.

The module is loaded directly from its file location (and also via the
canonical ``black.range_merge`` package path) so that the heavy, optional
third-party dependencies of the top-level ``black`` package never gate these
behavioural checks.
"""

import os
import subprocess
import textwrap


class TestMypyTypeChecking:
    REPO_DIR = "/workspace/black"

    MODULE_PATH = os.path.join(REPO_DIR, "src", "black", "range_merge.py")
    TEST_PATH = os.path.join(REPO_DIR, "tests", "test_range_merge.py")
    SRC_DIR = os.path.join(REPO_DIR, "src")

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _run_driver(self, body, timeout=120):
        """Run a Python snippet that imports the merger module directly.

        The module file is loaded by path via importlib so we do NOT pull in
        the (heavy, optional-dependency-laden) top-level ``black`` package.
        ``LineRange``/``merge_ranges``/``RangeMergeError`` are injected into the
        snippet's globals.
        """
        preamble = textwrap.dedent(
            """
            import importlib.util, sys, os
            _mod_path = {module_path!r}
            spec = importlib.util.spec_from_file_location("_range_merge_probe", _mod_path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            LineRange = mod.LineRange
            merge_ranges = mod.merge_ranges
            RangeMergeError = mod.RangeMergeError

            def _mk(start, end):
                # Build a LineRange via .of(...) if provided, else the constructor.
                of = getattr(LineRange, "of", None)
                if callable(of):
                    return of(start, end)
                return LineRange(start, end)

            def _spans(result):
                # Normalise a list[LineRange] to a list[(start, end)] tuple list.
                return [(r.start, r.end) for r in result]
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
        """L1: the new merger module file is created at the required path."""
        assert os.path.isfile(self.MODULE_PATH), (
            f"expected merger module at {self.MODULE_PATH}"
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

        ``LineRange`` is a type, ``merge_ranges`` is callable, and
        ``RangeMergeError`` is a subclass of ``ValueError`` (as required).
        """
        result = self._run_ok(
            """
            assert isinstance(LineRange, type)
            assert callable(merge_ranges)
            assert isinstance(RangeMergeError, type)
            assert issubclass(RangeMergeError, ValueError)
            print("OK")
            """
        )
        assert "OK" in result.stdout

    def test_canonical_package_import_path(self):
        """L1->L2: ``from black.range_merge import ...`` succeeds via the src path.

        The module must be importable through the ``black`` package namespace
        WITHOUT importing the (heavy) top-level ``black`` package machinery; it
        is stdlib-only, so a direct submodule import must work.
        """
        script = (
            "from black.range_merge import "
            "LineRange, merge_ranges, RangeMergeError\n"
            "assert issubclass(RangeMergeError, ValueError)\n"
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
    # L2 -- LineRange construction / validation
    # ------------------------------------------------------------------ #
    def test_linerange_fields_and_valid_construction(self):
        """L2: a valid LineRange carries int start/end and accepts boundary 1..n.

        Maps to: ``start >= 1`` and ``end >= start`` accepted, including the
        single-line span ``(1, 1)``.
        """
        self._run_ok(
            """
            r = _mk(3, 7)
            assert r.start == 3 and r.end == 7
            assert type(r.start) is int and type(r.end) is int

            # boundary: smallest valid start, single-line span
            r1 = _mk(1, 1)
            assert r1.start == 1 and r1.end == 1
            print("OK")
            """
        )

    def test_linerange_rejects_invalid(self):
        """L2: invalid LineRange construction raises RangeMergeError.

        Maps to: ``start=0`` (below 1) and ``end < start`` (e.g. 5..3) both
        rejected. A naive impl that skips validation fails here.
        """
        self._run_ok(
            """
            for bad in [(0, 4), (-1, 2), (5, 3), (2, 1), (0, 0)]:
                try:
                    _mk(*bad)
                except RangeMergeError:
                    pass
                else:
                    raise AssertionError(f"LineRange{bad} should raise RangeMergeError")
            print("OK")
            """
        )

    # ------------------------------------------------------------------ #
    # L2 -- merge_ranges behaviour
    # ------------------------------------------------------------------ #
    def test_merge_overlap(self):
        """L2: overlapping spans are combined into one.

        Maps to: ``[(1,3),(2,5)]`` -> ``[(1,5)]`` and full containment
        ``[(1,10),(3,4)]`` -> ``[(1,10)]``.
        """
        self._run_ok(
            """
            out = merge_ranges([_mk(1, 3), _mk(2, 5)])
            assert _spans(out) == [(1, 5)], _spans(out)

            out2 = merge_ranges([_mk(1, 10), _mk(3, 4)])
            assert _spans(out2) == [(1, 10)], _spans(out2)
            print("OK")
            """
        )

    def test_merge_adjacency_offbyone(self):
        """L2: adjacent spans (next.start == cur.end + 1) merge -- the key gate.

        Maps to: ``[(1,3),(4,6)]`` -> ``[(1,6)]`` because 4 == 3 + 1, and the
        three-span chain ``[(1,2),(3,4),(5,6)]`` -> ``[(1,6)]``. A naive impl
        that merges only true overlaps (using ``<`` / ``<=`` without the +1)
        fails: it would leave these separate.
        """
        self._run_ok(
            """
            out = merge_ranges([_mk(1, 3), _mk(4, 6)])
            assert _spans(out) == [(1, 6)], _spans(out)

            chain = merge_ranges([_mk(1, 2), _mk(3, 4), _mk(5, 6)])
            assert _spans(chain) == [(1, 6)], _spans(chain)
            print("OK")
            """
        )

    def test_merge_preserves_real_gap(self):
        """L2: a genuine gap is preserved -- the merger must not over-merge.

        Maps to: ``[(1,3),(5,6)]`` -> ``[(1,3),(5,6)]`` (gap at line 4). A stub
        that always collapses everything into one span fails here.
        """
        self._run_ok(
            """
            out = merge_ranges([_mk(1, 3), _mk(5, 6)])
            assert _spans(out) == [(1, 3), (5, 6)], _spans(out)

            # larger mixed case: one merge, one preserved gap
            out2 = merge_ranges([_mk(1, 2), _mk(3, 5), _mk(10, 12)])
            assert _spans(out2) == [(1, 5), (10, 12)], _spans(out2)
            print("OK")
            """
        )

    def test_merge_sorts_out_of_order(self):
        """L2: out-of-order input is sorted ascending by start before/while merging.

        Maps to: ``[(10,12),(1,2)]`` -> ``[(1,2),(10,12)]``. A naive impl that
        merges in input order without sorting fails.
        """
        self._run_ok(
            """
            out = merge_ranges([_mk(10, 12), _mk(1, 2)])
            assert _spans(out) == [(1, 2), (10, 12)], _spans(out)

            # unsorted overlap that only merges once sorted
            out2 = merge_ranges([_mk(4, 6), _mk(1, 5)])
            assert _spans(out2) == [(1, 6)], _spans(out2)
            print("OK")
            """
        )

    def test_merge_empty_and_single(self):
        """L2: empty input -> [] and a single range is returned as a NEW list.

        Maps to: ``[]`` -> ``[]`` and the single-range-returned-unchanged edge
        case (must be a fresh list, not the input object).
        """
        self._run_ok(
            """
            assert merge_ranges([]) == []

            src = [_mk(2, 4)]
            out = merge_ranges(src)
            assert _spans(out) == [(2, 4)], _spans(out)
            assert out is not src, "must return a brand-new list"

            # iterables other than list are accepted (tuple / generator)
            out_t = merge_ranges((_mk(1, 1),))
            assert _spans(out_t) == [(1, 1)], _spans(out_t)
            print("OK")
            """
        )

    def test_merge_rejects_non_linerange(self):
        """L2: a non-LineRange element raises RangeMergeError.

        Maps to: passing tuples/ints/None as elements is rejected (the function
        must validate element types, not silently access ``.start``).
        """
        self._run_ok(
            """
            for bad in [(1, 2), 5, None, "x", [1, 2]]:
                try:
                    merge_ranges([_mk(1, 2), bad])
                except RangeMergeError:
                    pass
                else:
                    raise AssertionError(f"element {bad!r} should raise RangeMergeError")
            print("OK")
            """
        )

    def test_merge_result_is_minimal_and_sorted(self):
        """L2: the result is always minimal (no overlap/adjacency) and sorted.

        Independent property check over a non-trivial input: every consecutive
        pair in the output must satisfy ``next.start > cur.end + 1`` and starts
        must be strictly ascending. This rejects any partial-merge solution.
        """
        self._run_ok(
            """
            inp = [
                _mk(5, 6), _mk(1, 2), _mk(2, 3), _mk(20, 22),
                _mk(7, 7), _mk(8, 10), _mk(100, 100),
            ]
            out = merge_ranges(inp)
            spans = _spans(out)
            # known minimal cover: (1,3) from 1-2/2-3, then 5-6/7-7/8-10 chain -> (5,10)
            assert spans == [(1, 3), (5, 10), (20, 22), (100, 100)], spans

            for a, b in zip(out, out[1:]):
                assert b.start > a.end + 1, (a.start, a.end, b.start, b.end)
                assert a.start < b.start
            print("OK")
            """
        )

    # ------------------------------------------------------------------ #
    # L2 -- static-analysis gate and native unit tests
    # ------------------------------------------------------------------ #
    def test_mypy_clean_on_new_module(self):
        """L2: the project's configured (strict) mypy reports no errors on the module.

        This is the core acceptance gate for the mypy-type-checking skill. The
        repo's pyproject.toml sets ``[tool.mypy] strict = true``; the agent's
        annotations must satisfy it. Drives exactly the doc's command.
        """
        result = subprocess.run(
            ["python", "-m", "mypy", "src/black/range_merge.py"],
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
        """L2: the agent's tests/test_range_merge.py passes under pytest.

        Runs exactly the command from the Acceptance Criteria, scoped to the
        new test file, and asserts a non-empty passing collection.
        """
        result = subprocess.run(
            ["python", "-m", "pytest", "tests/test_range_merge.py", "-q"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=600,
        )
        combined = result.stdout + result.stderr
        assert result.returncode == 0, "pytest failed\n" + combined
        assert "no tests ran" not in combined.lower(), combined
        assert " passed" in combined, combined

    def test_self_contained_no_third_party_imports(self):
        """L2: the module imports stdlib only -- loads with click/black absent.

        We load the module file with a sys.path that does NOT include the repo
        ``src`` dir, so any accidental ``import click`` / ``from black import``
        / ``from black.ranges import`` dependency surfaces as an ImportError.
        The module file itself is loaded by absolute path.
        """
        result = subprocess.run(
            [
                "python",
                "-c",
                textwrap.dedent(
                    f"""
                    import importlib.util, sys
                    sys.path = [p for p in sys.path if {self.SRC_DIR!r} not in p]
                    spec = importlib.util.spec_from_file_location(
                        "isolated_range_merge", {self.MODULE_PATH!r}
                    )
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)
                    of = getattr(mod.LineRange, "of", None)
                    lr = of(1, 3) if callable(of) else mod.LineRange(1, 3)
                    out = mod.merge_ranges([lr, (of(4, 5) if callable(of) else mod.LineRange(4, 5))])
                    assert [(r.start, r.end) for r in out] == [(1, 5)]
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
