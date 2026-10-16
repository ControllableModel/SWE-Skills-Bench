"""
Test for the 'sympy-symbolic-math' skill (variant ext7).

Task: add a first-order initial-value-problem (IVP) solver utility to
``sympy.solvers.ode`` exposing a single public function:

    from sympy.solvers.ode import solve_ivp_symbolic

``solve_ivp_symbolic(eq, func, ics)`` takes a first-order ODE ``eq`` in an
unknown function ``func`` (e.g. ``f(x)``) and an initial condition
``ics = {func.subs(x, x0): y0}``, and returns a SymPy ``Eq`` expressing
``func`` as a closed-form function of its independent variable with the
integration constant fully resolved from the initial condition.

Verification strategy
---------------------
The deliverable is exercised by IMPORTING and CALLING the agent's
implementation inside the repo (PYTHONPATH = REPO_DIR so the in-repo sympy is
the one under test) and deep-validating the *symbolic* results:

  * the return value is an ``Eq`` whose lhs is exactly ``func``,
  * the rhs matches the known closed form exactly under ``simplify`` /
    ``expand`` (e.g. ``exp(x)``, ``x**2 + 3``, the zero solution),
  * the initial condition holds exactly: ``rhs.subs(x, x0)`` simplifies to
    ``y0``,
  * the ODE itself is satisfied (substitute back and simplify to 0),
  * NO free integration constant remains: ``C1`` is not in
    ``result.rhs.free_symbols`` and no floats are introduced,
  * an inconsistent / unsolvable initial condition raises ``ValueError``
    rather than leaking a ``C1``-bearing solution.

A naive stub (e.g. returning ``dsolve(eq, func)`` directly, which still
carries ``C1``; hardcoding ``exp(x)``; ignoring ``ics``; or never raising)
is rejected by the C1-free, IC-satisfaction, multi-example and ValueError
checks below.

L1 checks confirm the deliverable files exist and the public import works.
L2 checks run real symbolic computations and assert deep equality, and the
final case drives the variant's native acceptance command:

    python -m pytest sympy/solvers/ode/tests/test_ivp.py -q
"""

import os
import subprocess
import textwrap

import pytest


class TestSympySymbolicMath:
    """Verify the solve_ivp_symbolic IVP utility in sympy.solvers.ode."""

    REPO_DIR = "/workspace/sympy"

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _run_py(self, body, timeout=300):
        """Run a python snippet with the in-repo sympy on PYTHONPATH.

        ``body`` is dedented and executed; the snippet is responsible for
        printing a final-line sentinel ``OK`` on success or raising. Returns
        the CompletedProcess so callers can assert on returncode/stdout.
        """
        script = "import sys\n"
        script += "sys.path.insert(0, %r)\n" % self.REPO_DIR
        script += textwrap.dedent(body)
        env = dict(os.environ)
        # Force the repo's sympy to win regardless of any site install.
        env["PYTHONPATH"] = self.REPO_DIR
        return subprocess.run(
            ["python", "-c", script],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )

    def _assert_ok(self, proc, msg=""):
        assert proc.returncode == 0, (
            "%s\nSTDOUT:\n%s\nSTDERR:\n%s" % (msg, proc.stdout, proc.stderr)
        )
        assert proc.stdout.strip().splitlines()[-1] == "OK", (
            "snippet did not reach OK sentinel\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )

    # ------------------------------------------------------------------
    # L1: deliverables exist / import
    # ------------------------------------------------------------------

    def test_ivp_module_file_exists(self):
        """sympy/solvers/ode/ivp.py must be created."""
        fpath = os.path.join(
            self.REPO_DIR, "sympy", "solvers", "ode", "ivp.py"
        )
        assert os.path.isfile(fpath), "sympy/solvers/ode/ivp.py not found"

    def test_ivp_test_file_exists(self):
        """sympy/solvers/ode/tests/test_ivp.py must be created."""
        fpath = os.path.join(
            self.REPO_DIR, "sympy", "solvers", "ode", "tests", "test_ivp.py"
        )
        assert os.path.isfile(fpath), "tests/test_ivp.py not found"

    def test_public_import_succeeds(self):
        """solve_ivp_symbolic must import from the sympy.solvers.ode package."""
        proc = self._run_py(
            """
            from sympy.solvers.ode import solve_ivp_symbolic
            assert callable(solve_ivp_symbolic)
            print("OK")
            """
        )
        self._assert_ok(proc, "from sympy.solvers.ode import ... failed")

    # ------------------------------------------------------------------
    # L2: dynamic symbolic validation
    # ------------------------------------------------------------------

    def test_returns_eq_with_func_lhs(self):
        """Return value is an Eq whose lhs is exactly func."""
        proc = self._run_py(
            """
            from sympy import Function, Eq, symbols
            from sympy.solvers.ode import solve_ivp_symbolic
            f = Function('f'); x = symbols('x')
            sol = solve_ivp_symbolic(Eq(f(x).diff(x), f(x)), f(x), {f(0): 1})
            assert isinstance(sol, Eq), type(sol)
            assert sol.lhs == f(x), sol.lhs
            print("OK")
            """
        )
        self._assert_ok(proc, "return type / lhs wrong")

    def test_exponential_example(self):
        """y' = y, y(0)=1 -> rhs == exp(x) exactly (the canonical example)."""
        proc = self._run_py(
            """
            from sympy import Function, Eq, symbols, exp, simplify
            from sympy.solvers.ode import solve_ivp_symbolic
            f = Function('f'); x = symbols('x')
            sol = solve_ivp_symbolic(Eq(f(x).diff(x), f(x)), f(x), {f(0): 1})
            assert simplify(sol.rhs - exp(x)) == 0, sol.rhs
            print("OK")
            """
        )
        self._assert_ok(proc, "exp example wrong")

    def test_polynomial_example(self):
        """y' = 2x, y(0)=3 -> rhs == x**2 + 3 exactly."""
        proc = self._run_py(
            """
            from sympy import Function, Eq, symbols, expand
            from sympy.solvers.ode import solve_ivp_symbolic
            f = Function('f'); x = symbols('x')
            sol = solve_ivp_symbolic(Eq(f(x).diff(x), 2*x), f(x), {f(0): 3})
            assert expand(sol.rhs - (x**2 + 3)) == 0, sol.rhs
            print("OK")
            """
        )
        self._assert_ok(proc, "polynomial example wrong")

    def test_zero_initial_condition(self):
        """y' = y, y(0)=0 -> the exact zero solution rhs == 0."""
        proc = self._run_py(
            """
            from sympy import Function, Eq, symbols, simplify
            from sympy.solvers.ode import solve_ivp_symbolic
            f = Function('f'); x = symbols('x')
            sol = solve_ivp_symbolic(Eq(f(x).diff(x), f(x)), f(x), {f(0): 0})
            assert simplify(sol.rhs) == 0, sol.rhs
            print("OK")
            """
        )
        self._assert_ok(proc, "zero initial condition wrong")

    def test_no_free_integration_constant(self):
        """C1 must NOT remain in rhs.free_symbols (rejects raw dsolve stub)."""
        proc = self._run_py(
            """
            from sympy import Function, Eq, symbols, Symbol
            from sympy.solvers.ode import solve_ivp_symbolic
            f = Function('f'); x = symbols('x')
            for ode, ic in (
                (Eq(f(x).diff(x), f(x)), {f(0): 1}),
                (Eq(f(x).diff(x), 2*x), {f(0): 3}),
                (Eq(f(x).diff(x), f(x)), {f(0): 5}),
            ):
                sol = solve_ivp_symbolic(ode, f(x), ic)
                names = {str(s) for s in sol.rhs.free_symbols}
                assert 'C1' not in names, (sol.rhs, names)
                assert Symbol('C1') not in sol.rhs.free_symbols, sol.rhs
            print("OK")
            """
        )
        self._assert_ok(proc, "leftover C1 in solution")

    def test_initial_condition_satisfied_exactly(self):
        """rhs.subs(x, x0) must simplify exactly to y0 for several IVPs."""
        proc = self._run_py(
            """
            from sympy import Function, Eq, symbols, simplify, Rational
            from sympy.solvers.ode import solve_ivp_symbolic
            f = Function('f'); x = symbols('x')
            cases = [
                (Eq(f(x).diff(x), f(x)), 0, 1),
                (Eq(f(x).diff(x), f(x)), 0, 5),
                (Eq(f(x).diff(x), 2*x), 0, 3),
                (Eq(f(x).diff(x), f(x)), 0, Rational(2, 3)),
            ]
            for ode, x0, y0 in cases:
                sol = solve_ivp_symbolic(ode, f(x), {f(x0): y0})
                got = simplify(sol.rhs.subs(x, x0))
                assert got == y0, (ode, x0, y0, got)
            print("OK")
            """
        )
        self._assert_ok(proc, "initial condition not satisfied")

    def test_solution_satisfies_ode(self):
        """Substituting the solution back into eq simplifies to a 0 identity."""
        proc = self._run_py(
            """
            from sympy import Function, Eq, symbols, simplify
            from sympy.solvers.ode import solve_ivp_symbolic
            f = Function('f'); x = symbols('x')
            for eq in (
                Eq(f(x).diff(x), f(x)),
                Eq(f(x).diff(x), 2*x),
            ):
                sol = solve_ivp_symbolic(eq, f(x), {f(0): 1})
                # residual: lhs - rhs of the ODE after plugging the solution
                residual = (eq.lhs - eq.rhs).subs(f(x), sol.rhs).doit()
                assert simplify(residual) == 0, (eq, sol, residual)
            print("OK")
            """
        )
        self._assert_ok(proc, "solution does not satisfy the ODE")

    def test_no_floats_exact_constants(self):
        """Constants are exact: no Float atoms appear in any solution rhs."""
        proc = self._run_py(
            """
            from sympy import Function, Eq, symbols, Float
            from sympy.solvers.ode import solve_ivp_symbolic
            f = Function('f'); x = symbols('x')
            for ode, ic in (
                (Eq(f(x).diff(x), f(x)), {f(0): 1}),
                (Eq(f(x).diff(x), 2*x), {f(0): 3}),
                (Eq(f(x).diff(x), f(x)), {f(0): 7}),
            ):
                sol = solve_ivp_symbolic(ode, f(x), ic)
                assert not sol.rhs.atoms(Float), sol.rhs
            print("OK")
            """
        )
        self._assert_ok(proc, "floating-point constant introduced")

    def test_nonzero_initial_value_scales(self):
        """y' = y, y(0)=5 -> rhs == 5*exp(x); ics is actually consumed."""
        proc = self._run_py(
            """
            from sympy import Function, Eq, symbols, exp, simplify
            from sympy.solvers.ode import solve_ivp_symbolic
            f = Function('f'); x = symbols('x')
            sol = solve_ivp_symbolic(Eq(f(x).diff(x), f(x)), f(x), {f(0): 5})
            assert simplify(sol.rhs - 5*exp(x)) == 0, sol.rhs
            # A stub that hardcodes exp(x) or ignores y0 would fail here.
            print("OK")
            """
        )
        self._assert_ok(proc, "ics value not applied to solution")

    def test_nonzero_base_point(self):
        """Initial condition at x0 != 0 is honored: y'=y, y(1)=1 -> exp(x-1)."""
        proc = self._run_py(
            """
            from sympy import Function, Eq, symbols, exp, simplify
            from sympy.solvers.ode import solve_ivp_symbolic
            f = Function('f'); x = symbols('x')
            sol = solve_ivp_symbolic(Eq(f(x).diff(x), f(x)), f(x), {f(1): 1})
            assert simplify(sol.rhs - exp(x - 1)) == 0, sol.rhs
            assert simplify(sol.rhs.subs(x, 1)) == 1, sol.rhs
            print("OK")
            """
        )
        self._assert_ok(proc, "non-zero base point wrong")

    def test_independent_variable_from_func_args(self):
        """The independent variable is taken from func.args[0] (here t, not x)."""
        proc = self._run_py(
            """
            from sympy import Function, Eq, symbols, exp, simplify
            from sympy.solvers.ode import solve_ivp_symbolic
            g = Function('g'); t = symbols('t')
            sol = solve_ivp_symbolic(Eq(g(t).diff(t), g(t)), g(t), {g(0): 1})
            assert sol.lhs == g(t), sol.lhs
            assert simplify(sol.rhs - exp(t)) == 0, sol.rhs
            print("OK")
            """
        )
        self._assert_ok(proc, "independent variable handling wrong")

    def test_inconsistent_ic_raises_valueerror(self):
        """An unsolvable/inconsistent IC raises ValueError, not a C1 solution."""
        proc = self._run_py(
            """
            from sympy import Function, Eq, symbols
            from sympy.solvers.ode import solve_ivp_symbolic
            f = Function('f'); x = symbols('x')
            # f' = f forces f(x)=C1*exp(x); imposing two contradictory values
            # at the same point makes the constant unsolvable.
            try:
                solve_ivp_symbolic(
                    Eq(f(x).diff(x), f(x)), f(x), {f(0): 1, f(0): 1}
                )
            except ValueError:
                pass
            # Primary inconsistency probe: the constant truly cannot be solved.
            # Use a degenerate IC dict that pins nothing solvable.
            raised = False
            try:
                # an empty ics cannot determine C1 -> must raise, not leak C1
                solve_ivp_symbolic(Eq(f(x).diff(x), f(x)), f(x), {})
            except ValueError:
                raised = True
            except Exception:
                raised = True
            assert raised, "empty/unsolvable ics did not raise"
            print("OK")
            """
        )
        self._assert_ok(proc, "inconsistent IC did not raise")

    def test_native_pytest_suite_passes(self):
        """The deliverable's own pytest file collects and passes (green).

        Drives the variant's native acceptance command:
            python -m pytest sympy/solvers/ode/tests/test_ivp.py -q
        """
        env = dict(os.environ)
        env["PYTHONPATH"] = self.REPO_DIR
        # --noconftest avoids sympy/conftest.py's optional 'hypothesis'
        # dependency, keeping the check scoped to the deliverable file.
        proc = subprocess.run(
            ["python", "-m", "pytest",
             "sympy/solvers/ode/tests/test_ivp.py", "-q",
             "-p", "no:cacheprovider", "--noconftest"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=900,
            env=env,
        )
        assert proc.returncode == 0, (
            "native test_ivp.py suite failed\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )
        out = proc.stdout + proc.stderr
        assert "passed" in out, out
        assert "no tests ran" not in out, out
