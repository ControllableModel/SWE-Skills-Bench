"""Tests for skill: mypy-type-checking (ext2 task: Add a Line-Width Budget Tracker).

The agent must create a self-contained, standard-library-only module
``src/black/width_budget.py`` inside the ``black`` repository exposing a
``WidthBudget`` class and a ``BudgetError`` exception (a subclass of
``ValueError``), plus a deterministic unit-test file
``tests/test_width_budget.py``.

``WidthBudget(limit)`` models a left-to-right horizontal budget over a fixed
line length:

* ``limit`` (read-only) -- the configured non-negative max width; negative
  ``limit`` raises ``BudgetError``.
* ``used`` -- total width consumed so far (starts at 0).
* ``remaining`` -- ``limit - used`` (never negative once the budget is
  respected).
* ``fits(width)`` -- ``True`` iff ``width <= remaining`` (negative -> error).
* ``consume(width)`` -- reduces ``remaining`` by ``width`` and returns the new
  ``remaining``; over-consumption raises ``BudgetError`` and leaves ``used``
  UNCHANGED; negative -> error.
* ``reset()`` -- returns ``used`` to 0.

Verification strategy:

* L1 -- the two deliverable files exist and are minimally well-formed, and the
  required public surface imports with the right shapes.
* L2 -- the runtime behaviour is exercised independently by driving the module
  through a fresh Python subprocess (so a naive solution that mishandles the
  exact fits/consume boundary, allows over-consumption, or fails to leave
  ``used`` unchanged on rejection, fails); the project's configured ``mypy``
  static-analysis gate is run over the new module; and the agent-authored
  pytest file is executed with the native toolchain.

The module is loaded directly from its file location (and also via the
canonical ``black.width_budget`` package path) so that the heavy, optional
third-party dependencies of the top-level ``black`` package never gate these
behavioural checks.
"""

import os
import subprocess
import textwrap


class TestMypyTypeChecking:
    REPO_DIR = "/workspace/black"

    MODULE_PATH = os.path.join(REPO_DIR, "src", "black", "width_budget.py")
    TEST_PATH = os.path.join(REPO_DIR, "tests", "test_width_budget.py")
    SRC_DIR = os.path.join(REPO_DIR, "src")

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _run_driver(self, body, timeout=120):
        """Run a Python snippet that imports the width-budget module directly.

        The module file is loaded by path via importlib so that we do NOT pull
        in the (heavy, optional-dependency-laden) top-level ``black`` package.
        ``WidthBudget`` and ``BudgetError`` are injected into the snippet's
        globals.
        """
        preamble = textwrap.dedent(
            """
            import importlib.util, sys, os
            _mod_path = {module_path!r}
            spec = importlib.util.spec_from_file_location("_width_budget_probe", _mod_path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            WidthBudget = mod.WidthBudget
            BudgetError = mod.BudgetError
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
        """L1: the new width-budget module file is created at the required path."""
        assert os.path.isfile(self.MODULE_PATH), (
            f"expected width-budget module at {self.MODULE_PATH}"
        )
        assert os.path.getsize(self.MODULE_PATH) > 0

    def test_unit_test_file_exists(self):
        """L1: the deterministic unit-test file is created at the required path."""
        assert os.path.isfile(self.TEST_PATH), (
            f"expected unit-test file at {self.TEST_PATH}"
        )
        assert os.path.getsize(self.TEST_PATH) > 0

    def test_public_surface_importable(self):
        """L1->L2: the two required public names import with the right shapes.

        ``WidthBudget`` is a class, ``BudgetError`` is an exception type that
        subclasses ``ValueError`` (so callers can catch it as a ``ValueError``).
        """
        result = self._run_ok(
            """
            assert isinstance(WidthBudget, type)
            assert isinstance(BudgetError, type)
            assert issubclass(BudgetError, ValueError)
            print("OK")
            """
        )
        assert "OK" in result.stdout

    def test_canonical_package_import_path(self):
        """L1->L2: ``from black.width_budget import ...`` succeeds via the src path.

        The module is required to be importable through the ``black`` package
        namespace WITHOUT importing the (heavy) top-level ``black`` package
        machinery; it is stdlib-only, so a direct submodule import must work.
        """
        script = (
            "from black.width_budget import WidthBudget, BudgetError\n"
            "assert issubclass(BudgetError, ValueError)\n"
            "b = WidthBudget(88)\n"
            "assert b.remaining == 88\n"
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
    # L2 -- per-feature runtime behaviour
    # ------------------------------------------------------------------ #
    def test_initial_state(self):
        """L2: a fresh budget reports the configured limit, zero used, full remaining.

        Maps to: ``WidthBudget(88)`` -> ``remaining == 88``, ``used == 0``,
        ``limit == 88``. Also checks that ``limit`` reflects the constructor arg
        for an unrelated value (so a hardcoded constant fails).
        """
        self._run_ok(
            """
            b = WidthBudget(88)
            assert b.limit == 88, b.limit
            assert b.used == 0, b.used
            assert b.remaining == 88, b.remaining

            b2 = WidthBudget(120)
            assert b2.limit == 120 and b2.used == 0 and b2.remaining == 120
            print("OK")
            """
        )

    def test_negative_limit_rejected(self):
        """L2: constructing with a negative limit raises BudgetError.

        Maps to: ``WidthBudget(-1)`` -> ``BudgetError``. A naive constructor
        that stores the value unconditionally fails here.
        """
        self._run_ok(
            """
            for bad in (-1, -5, -88):
                try:
                    WidthBudget(bad)
                except BudgetError:
                    pass
                else:
                    raise AssertionError(f"limit={bad} should raise BudgetError")
            print("OK")
            """
        )

    def test_consume_accumulates_used_and_returns_remaining(self):
        """L2: consume() reduces remaining, accumulates used, and returns new remaining.

        Maps to: after ``consume(10)`` then ``consume(5)``, ``used == 15`` and
        ``remaining == 73`` for an 88 budget; each call returns the post-consume
        remaining value (so a stub that ignores the input or returns a constant
        fails).
        """
        self._run_ok(
            """
            b = WidthBudget(88)
            r1 = b.consume(10)
            assert r1 == 78, r1
            assert b.used == 10 and b.remaining == 78

            r2 = b.consume(5)
            assert r2 == 73, r2
            assert b.used == 15 and b.remaining == 73
            assert b.limit == 88
            print("OK")
            """
        )

    def test_fits_boundary(self):
        """L2: fits() is exact at the remaining boundary.

        Maps to: with remaining 73, ``fits(73) is True`` and ``fits(74) is
        False``; ``fits(0) is True``. A naive ``width < remaining`` (strict)
        implementation fails the equal-to-remaining case.
        """
        self._run_ok(
            """
            b = WidthBudget(88)
            b.consume(10)
            b.consume(5)
            assert b.remaining == 73
            assert b.fits(73) is True
            assert b.fits(74) is False
            assert b.fits(0) is True
            assert b.fits(72) is True
            # return type must be a real bool, not a truthy int
            assert type(b.fits(73)) is bool
            print("OK")
            """
        )

    def test_fits_negative_width_rejected(self):
        """L2: fits() with a negative width raises BudgetError.

        Maps to: ``fits(-1)`` -> ``BudgetError``.
        """
        self._run_ok(
            """
            b = WidthBudget(88)
            for bad in (-1, -10):
                try:
                    b.fits(bad)
                except BudgetError:
                    pass
                else:
                    raise AssertionError(f"fits({bad}) should raise BudgetError")
            print("OK")
            """
        )

    def test_over_consume_rejected_and_state_preserved(self):
        """L2: over-consuming raises BudgetError and leaves used UNCHANGED.

        Maps to: on a budget with ``used == 15`` (remaining 73), ``consume(1000)``
        raises ``BudgetError`` and ``used`` stays 15; the budget remains usable
        afterwards. A naive implementation that mutates state before validating
        (or clamps instead of raising) fails here.
        """
        self._run_ok(
            """
            b = WidthBudget(88)
            b.consume(10)
            b.consume(5)
            assert b.used == 15 and b.remaining == 73

            try:
                b.consume(1000)
            except BudgetError:
                pass
            else:
                raise AssertionError("over-consume must raise BudgetError")

            # state untouched by the rejected consume
            assert b.used == 15, b.used
            assert b.remaining == 73, b.remaining

            # consuming exactly remaining is still allowed afterwards
            r = b.consume(73)
            assert r == 0, r
            assert b.used == 88 and b.remaining == 0
            print("OK")
            """
        )

    def test_consume_exact_remaining_then_one_more_fails(self):
        """L2: consuming exactly to zero succeeds; any further positive consume fails.

        Maps to: ``remaining`` may be 0 but never negative; once at 0,
        ``consume(1)`` raises while ``consume(0)`` still succeeds.
        """
        self._run_ok(
            """
            b = WidthBudget(10)
            assert b.consume(10) == 0
            assert b.remaining == 0
            assert b.fits(0) is True
            assert b.fits(1) is False

            try:
                b.consume(1)
            except BudgetError:
                pass
            else:
                raise AssertionError("consume past zero must raise BudgetError")
            assert b.used == 10

            # zero-width consume at the boundary is always allowed
            assert b.consume(0) == 0
            assert b.used == 10
            print("OK")
            """
        )

    def test_consume_negative_width_rejected(self):
        """L2: consume() with a negative width raises BudgetError and preserves state.

        Maps to: ``consume(-1)`` -> ``BudgetError`` with ``used`` unchanged.
        """
        self._run_ok(
            """
            b = WidthBudget(88)
            b.consume(20)
            assert b.used == 20
            for bad in (-1, -20):
                try:
                    b.consume(bad)
                except BudgetError:
                    pass
                else:
                    raise AssertionError(f"consume({bad}) should raise BudgetError")
            assert b.used == 20, b.used
            print("OK")
            """
        )

    def test_consume_zero_is_always_allowed(self):
        """L2: consume(0) is always allowed and never changes used.

        Maps to: the explicit "consume(0) is always allowed and never changes
        used" edge case, checked at several budget states.
        """
        self._run_ok(
            """
            b = WidthBudget(5)
            assert b.consume(0) == 5
            assert b.used == 0 and b.remaining == 5

            b.consume(5)
            assert b.consume(0) == 0
            assert b.used == 5 and b.remaining == 0
            print("OK")
            """
        )

    def test_reset_restores_initial_state(self):
        """L2: reset() returns used to 0 and remaining to limit, reusably.

        Maps to: after consuming, ``reset()`` puts the budget back to its initial
        state; ``limit`` is unchanged and the budget can be consumed again.
        """
        self._run_ok(
            """
            b = WidthBudget(88)
            b.consume(40)
            b.consume(8)
            assert b.used == 48 and b.remaining == 40
            b.reset()
            assert b.used == 0, b.used
            assert b.remaining == 88, b.remaining
            assert b.limit == 88
            # reusable after reset
            assert b.consume(88) == 0
            assert b.remaining == 0
            b.reset()
            assert b.remaining == 88
            print("OK")
            """
        )

    def test_zero_limit_budget(self):
        """L2: a zero-limit budget behaves at the documented degenerate boundary.

        Maps to: ``WidthBudget(0)`` -> ``remaining == 0``, ``fits(0) is True``,
        ``fits(1) is False``, ``consume(0)`` returns 0, ``consume(1)`` raises.
        """
        self._run_ok(
            """
            b = WidthBudget(0)
            assert b.limit == 0 and b.used == 0 and b.remaining == 0
            assert b.fits(0) is True
            assert b.fits(1) is False
            assert b.consume(0) == 0
            assert b.used == 0
            try:
                b.consume(1)
            except BudgetError:
                pass
            else:
                raise AssertionError("consume(1) on zero budget must raise")
            print("OK")
            """
        )

    def test_limit_is_read_only(self):
        """L2: the limit property is read-only (cannot be reassigned).

        The doc requires a "read-only ``limit`` property". A plain mutable
        attribute would let callers corrupt the budget; assigning to ``limit``
        must raise AttributeError.
        """
        self._run_ok(
            """
            b = WidthBudget(88)
            raised = False
            try:
                b.limit = 100
            except AttributeError:
                raised = True
            assert raised, "limit must be read-only (assignment should raise)"
            assert b.limit == 88
            print("OK")
            """
        )

    # ------------------------------------------------------------------ #
    # L2 -- static-analysis gate and native unit tests
    # ------------------------------------------------------------------ #
    def test_mypy_clean_on_new_module(self):
        """L2: the project's configured mypy reports no errors on the new module.

        This is the core acceptance gate for the mypy-type-checking skill and is
        exactly the second native command from the Acceptance Criteria. The
        agent's annotations must satisfy the repo's mypy configuration.
        """
        result = subprocess.run(
            ["python", "-m", "mypy", "src/black/width_budget.py"],
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
        """L2: the agent's tests/test_width_budget.py passes under pytest.

        Runs exactly the first command from the Acceptance Criteria, scoped to
        the new test file, and asserts a non-empty passing collection (guarding
        against an empty/placeholder file).
        """
        result = subprocess.run(
            ["python", "-m", "pytest", "tests/test_width_budget.py", "-q"],
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
        """L2: the module imports stdlib only -- it must load with click/black absent.

        We load the module file with a sys.path that does NOT include the repo
        ``src`` dir, so any accidental ``import click`` / ``from black import``
        dependency would surface as an ImportError. The module file itself is
        loaded by absolute path and then exercised once.
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
                        "isolated_width_budget", {self.MODULE_PATH!r}
                    )
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)
                    b = mod.WidthBudget(10)
                    assert b.remaining == 10
                    assert b.consume(4) == 6
                    assert b.used == 4
                    assert b.fits(6) is True and b.fits(7) is False
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
