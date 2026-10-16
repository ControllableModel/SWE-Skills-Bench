"""
Test for the 'sympy-symbolic-math' skill.

Task: add a local polynomial (Taylor) approximation utility to
``sympy.calculus`` exposing two public functions:

    from sympy.calculus import taylor_polynomial, taylor_coefficient

This suite verifies the deliverable by actually IMPORTING and EXERCISING the
agent's implementation inside the repo (PYTHONPATH = REPO_DIR so the in-repo
sympy is the one under test) and deep-validating the symbolic results:

  * exact rational coefficients (no floats),
  * powers of (x - x0),
  * absence of any O(...) order/remainder term,
  * polynomial exactness, zero coefficients returned as 0,
  * symbolic base points,
  * ValueError on negative degree/index.

L1 checks confirm the deliverable files exist and the import works.
L2 checks run real symbolic computations and assert deep equality.
"""

import os
import subprocess
import textwrap

import pytest


class TestSympySymbolicMath:
    """Verify the taylor_polynomial / taylor_coefficient utilities."""

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
    # L1: deliverables exist
    # ------------------------------------------------------------------

    def test_taylor_module_file_exists(self):
        """sympy/calculus/taylor.py must be created."""
        fpath = os.path.join(self.REPO_DIR, "sympy", "calculus", "taylor.py")
        assert os.path.isfile(fpath), "sympy/calculus/taylor.py not found"

    def test_taylor_test_file_exists(self):
        """sympy/calculus/tests/test_taylor.py must be created."""
        fpath = os.path.join(
            self.REPO_DIR, "sympy", "calculus", "tests", "test_taylor.py"
        )
        assert os.path.isfile(fpath), "tests/test_taylor.py not found"

    def test_public_import_succeeds(self):
        """Both functions must import from the sympy.calculus package."""
        proc = self._run_py(
            """
            from sympy.calculus import taylor_polynomial, taylor_coefficient
            assert callable(taylor_polynomial)
            assert callable(taylor_coefficient)
            print("OK")
            """
        )
        self._assert_ok(proc, "from sympy.calculus import ... failed")

    # ------------------------------------------------------------------
    # L2: dynamic symbolic validation
    # ------------------------------------------------------------------

    def test_exp_degree3_about_zero(self):
        """taylor_polynomial(exp(x),x,0,3) == 1 + x + x**2/2 + x**3/6 exactly."""
        proc = self._run_py(
            """
            from sympy import symbols, exp, expand, Rational
            from sympy.calculus import taylor_polynomial
            x = symbols('x')
            res = taylor_polynomial(exp(x), x, 0, 3)
            expected = 1 + x + x**2/2 + x**3/6
            assert expand(res - expected) == 0, (res, expected)
            print("OK")
            """
        )
        self._assert_ok(proc, "exp degree-3 approximation wrong")

    def test_no_order_term_attached(self):
        """Result must carry no O(...) term: .getO() is None."""
        proc = self._run_py(
            """
            from sympy import symbols, exp
            from sympy.calculus import taylor_polynomial
            x = symbols('x')
            res = taylor_polynomial(exp(x), x, 0, 3)
            o = res.getO()
            assert o is None, "unexpected order term: %r" % (o,)
            # also ensure no Order object lurks anywhere in the expr tree
            from sympy.series.order import Order
            assert not res.has(Order), "Order object present in result"
            print("OK")
            """
        )
        self._assert_ok(proc, "order term was not stripped")

    def test_cos_degree4_only_even_terms(self):
        """taylor_polynomial(cos(x),x,0,4) == 1 - x**2/2 + x**4/24 exactly."""
        proc = self._run_py(
            """
            from sympy import symbols, cos, expand
            from sympy.calculus import taylor_polynomial
            x = symbols('x')
            res = taylor_polynomial(cos(x), x, 0, 4)
            expected = 1 - x**2/2 + x**4/24
            assert expand(res - expected) == 0, (res, expected)
            print("OK")
            """
        )
        self._assert_ok(proc, "cos degree-4 approximation wrong")

    def test_geometric_series(self):
        """taylor_polynomial(1/(1-x),x,0,3) == 1 + x + x**2 + x**3 exactly."""
        proc = self._run_py(
            """
            from sympy import symbols, expand
            from sympy.calculus import taylor_polynomial
            x = symbols('x')
            res = taylor_polynomial(1/(1 - x), x, 0, 3)
            expected = 1 + x + x**2 + x**3
            assert expand(res - expected) == 0, (res, expected)
            print("OK")
            """
        )
        self._assert_ok(proc, "geometric series approximation wrong")

    def test_powers_of_x_minus_x0(self):
        """Approximation about x0=1 must be expressed in powers of (x-1)."""
        proc = self._run_py(
            """
            from sympy import symbols, exp, expand, E
            from sympy.calculus import taylor_polynomial
            x = symbols('x')
            res = taylor_polynomial(exp(x), x, 1, 2)
            expected = E + E*(x - 1) + E*(x - 1)**2/2
            assert expand(res - expected) == 0, (res, expected)
            print("OK")
            """
        )
        self._assert_ok(proc, "approximation about x0=1 wrong")

    def test_polynomial_reproduced_exactly(self):
        """n >= deg reproduces a polynomial with no spurious higher terms."""
        proc = self._run_py(
            """
            from sympy import symbols, expand, Poly
            from sympy.calculus import taylor_polynomial
            x = symbols('x')
            p = x**3 + 2*x + 1
            res = taylor_polynomial(p, x, 0, 5)
            assert expand(res - p) == 0, (res, p)
            # No spurious x**4 / x**5 terms.
            poly = Poly(expand(res), x)
            assert poly.degree() == 3, poly
            print("OK")
            """
        )
        self._assert_ok(proc, "polynomial not reproduced exactly")

    def test_exact_rational_coefficients_no_floats(self):
        """The x**3 coefficient of exp(x) about 0 is exactly Rational(1,6)."""
        proc = self._run_py(
            """
            from sympy import symbols, exp, Rational, Float, expand, Poly
            from sympy.calculus import taylor_polynomial
            x = symbols('x')
            res = expand(taylor_polynomial(exp(x), x, 0, 3))
            poly = Poly(res, x)
            c3 = poly.coeff_monomial(x**3)
            assert c3 == Rational(1, 6), c3
            # Absolutely no floating-point atoms anywhere.
            assert not res.atoms(Float), "float introduced: %r" % res
            print("OK")
            """
        )
        self._assert_ok(proc, "coefficients are not exact rationals")

    def test_coefficient_exp(self):
        """taylor_coefficient(exp(x),x,0,3) == Rational(1,6) (exact, is True)."""
        proc = self._run_py(
            """
            from sympy import symbols, exp, Rational, Float
            from sympy.calculus import taylor_coefficient
            x = symbols('x')
            c = taylor_coefficient(exp(x), x, 0, 3)
            assert (c == Rational(1, 6)) is True, c
            assert not c.atoms(Float), c
            print("OK")
            """
        )
        self._assert_ok(proc, "taylor_coefficient(exp) wrong")

    def test_coefficient_cos_even_and_zero(self):
        """cos coefficients: k=2 -> -1/2, k=3 -> exact SymPy 0."""
        proc = self._run_py(
            """
            from sympy import symbols, cos, Rational, Integer
            from sympy.calculus import taylor_coefficient
            x = symbols('x')
            c2 = taylor_coefficient(cos(x), x, 0, 2)
            c3 = taylor_coefficient(cos(x), x, 0, 3)
            assert (c2 == Rational(-1, 2)) is True, c2
            assert (c3 == 0) is True, c3
            # Must be the SymPy zero object, not python int via accident.
            assert c3 == Integer(0)
            print("OK")
            """
        )
        self._assert_ok(proc, "cos coefficients wrong")

    def test_coefficient_k0_is_value_at_x0(self):
        """taylor_coefficient(exp(x),x,1,0) == E (constant term = expr(x0))."""
        proc = self._run_py(
            """
            from sympy import symbols, exp, E
            from sympy.calculus import taylor_polynomial, taylor_coefficient
            x = symbols('x')
            assert (taylor_coefficient(exp(x), x, 1, 0) == E) is True
            # n=0 yields the constant approximation = expr(x0)
            assert (taylor_polynomial(exp(x), x, 1, 0) == E) is True
            print("OK")
            """
        )
        self._assert_ok(proc, "k=0 / n=0 constant case wrong")

    def test_expr_without_x(self):
        """If expr lacks x: approx == expr, and k>=1 coefficients are 0."""
        proc = self._run_py(
            """
            from sympy import symbols, exp, expand
            from sympy.calculus import taylor_polynomial, taylor_coefficient
            x, a = symbols('x a')
            const = a*exp(a) + 3
            assert expand(taylor_polynomial(const, x, 0, 4) - const) == 0
            assert (taylor_coefficient(const, x, 0, 0) == const) is True
            assert (taylor_coefficient(const, x, 0, 1) == 0) is True
            assert (taylor_coefficient(const, x, 0, 2) == 0) is True
            print("OK")
            """
        )
        self._assert_ok(proc, "expr-without-x case wrong")

    def test_symbolic_base_point(self):
        """x0 may be symbolic; result involves that symbol and matches Taylor."""
        proc = self._run_py(
            """
            from sympy import symbols, sin, cos, expand, diff
            from sympy.calculus import taylor_polynomial
            x, a = symbols('x a')
            res = taylor_polynomial(sin(x), x, a, 2)
            # degree-2 Taylor of sin about a
            expected = sin(a) + cos(a)*(x - a) - sin(a)*(x - a)**2/2
            assert expand(res - expected) == 0, (res, expected)
            assert res.has(a), res
            print("OK")
            """
        )
        self._assert_ok(proc, "symbolic base point wrong")

    def test_negative_degree_raises(self):
        """Negative n in taylor_polynomial raises ValueError."""
        proc = self._run_py(
            """
            from sympy import symbols, sin
            from sympy.calculus import taylor_polynomial
            x = symbols('x')
            try:
                taylor_polynomial(sin(x), x, 0, -1)
            except ValueError:
                print("OK")
            else:
                raise AssertionError("expected ValueError for n=-1")
            """
        )
        self._assert_ok(proc, "negative n did not raise ValueError")

    def test_negative_index_raises(self):
        """Negative k in taylor_coefficient raises ValueError."""
        proc = self._run_py(
            """
            from sympy import symbols, sin
            from sympy.calculus import taylor_coefficient
            x = symbols('x')
            try:
                taylor_coefficient(sin(x), x, 0, -2)
            except ValueError:
                print("OK")
            else:
                raise AssertionError("expected ValueError for k=-2")
            """
        )
        self._assert_ok(proc, "negative k did not raise ValueError")

    def test_native_pytest_suite_passes(self):
        """The deliverable's own pytest file collects and passes (green)."""
        env = dict(os.environ)
        env["PYTHONPATH"] = self.REPO_DIR
        # --noconftest avoids sympy/conftest.py's optional 'hypothesis'
        # dependency, keeping the check scoped to the deliverable file.
        proc = subprocess.run(
            ["python", "-m", "pytest",
             "sympy/calculus/tests/test_taylor.py", "-q",
             "-p", "no:cacheprovider", "--noconftest"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=600,
            env=env,
        )
        assert proc.returncode == 0, (
            "native test_taylor.py suite failed\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )
        # Ensure at least some tests actually ran (no empty/no-op collection).
        out = proc.stdout + proc.stderr
        assert "passed" in out, out
        assert "no tests ran" not in out, out
