"""
Test for the 'sympy-symbolic-math' skill (variant ext5).

Task: add an exact symbolic arc-length utility to ``sympy.calculus`` exposing a
single public function::

    from sympy.calculus import arc_length

``arc_length(expr, x, a, b)`` returns the exact symbolic arc length of the graph
of ``y = expr`` from ``x = a`` to ``x = b`` -- i.e. the definite integral of
``sqrt(1 + (d(expr)/dx)**2)`` over ``[a, b]``, evaluated to a closed form when
SymPy can do so, and returned as an unevaluated ``Integral`` otherwise.

Verification strategy
---------------------
The deliverable is exercised by IMPORTING and RUNNING the agent's implementation
inside the repo (PYTHONPATH = REPO_DIR so the in-repo sympy is under test) and
deep-validating the symbolic results:

  * exact symbolic equality (``simplify(result - expected) == 0``), never floats;
  * the classic exact answers: y=x over [0,1] -> sqrt(2); the semicubical
    parabola example -> Rational(14, 3);
  * a constant curve over [a, b] -> ``b - a``;
  * equal limits -> ``0``;
  * a non-elementary case (sin(x) over [0, pi]) -> an unevaluated ``Integral``;
  * the derivative used is the *exact* symbolic derivative (a naive impl that
    drops/approximates it, returns a float, or returns ``b - a`` unconditionally
    must FAIL these cases);
  * symbolic limits flow through into the result.

L1 checks confirm the deliverable files exist and the public import works.
L2 checks run real symbolic computations and assert deep equality, and finally
run the deliverable's own pytest suite under the repo toolchain.
"""

import os
import subprocess
import textwrap


class TestSympySymbolicMath:
    """Verify the arc_length utility in sympy.calculus."""

    REPO_DIR = "/workspace/sympy"

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _run_py(self, body, timeout=300):
        """Run a python snippet with the in-repo sympy on PYTHONPATH.

        ``body`` is dedented and executed; the snippet must print a final-line
        sentinel ``OK`` on success or raise. Returns the CompletedProcess so
        callers can assert on returncode/stdout.
        """
        script = "import sys\n"
        script += "sys.path.insert(0, %r)\n" % self.REPO_DIR
        script += textwrap.dedent(body)
        env = dict(os.environ)
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
    # L1: deliverables exist / import well-formed
    # ------------------------------------------------------------------

    def test_arclength_module_file_exists(self):
        """sympy/calculus/arclength.py must be created."""
        fpath = os.path.join(
            self.REPO_DIR, "sympy", "calculus", "arclength.py"
        )
        assert os.path.isfile(fpath), "sympy/calculus/arclength.py not found"

    def test_arclength_test_file_exists(self):
        """sympy/calculus/tests/test_arclength.py must be created."""
        fpath = os.path.join(
            self.REPO_DIR, "sympy", "calculus", "tests", "test_arclength.py"
        )
        assert os.path.isfile(fpath), "tests/test_arclength.py not found"

    def test_public_import_succeeds(self):
        """arc_length must import from the sympy.calculus package and be callable."""
        proc = self._run_py(
            """
            from sympy.calculus import arc_length
            assert callable(arc_length)
            print("OK")
            """
        )
        self._assert_ok(proc, "from sympy.calculus import arc_length failed")

    def test_exported_in___all__(self):
        """arc_length must be listed in sympy.calculus.__all__ (real export)."""
        proc = self._run_py(
            """
            import sympy.calculus as c
            assert 'arc_length' in c.__all__, c.__all__
            print("OK")
            """
        )
        self._assert_ok(proc, "arc_length missing from sympy.calculus.__all__")

    # ------------------------------------------------------------------
    # L2: dynamic symbolic validation
    # ------------------------------------------------------------------

    def test_straight_line_is_sqrt2(self):
        """arc_length(x, x, 0, 1) == sqrt(2) exactly (never 1.4142...).

        A naive impl that returns b - a unconditionally would give 1 and fail.
        A float impl would carry a Float atom and fail.
        """
        proc = self._run_py(
            """
            from sympy import symbols, sqrt, simplify, Float
            from sympy.calculus import arc_length
            x = symbols('x')
            res = arc_length(x, x, 0, 1)
            assert simplify(res - sqrt(2)) == 0, res
            assert not res.atoms(Float), "float introduced: %r" % res
            print("OK")
            """
        )
        self._assert_ok(proc, "arc_length(x,x,0,1) != sqrt(2)")

    def test_constant_curve_is_b_minus_a(self):
        """arc_length(Integer(3), x, 0, 5) simplifies to 5 (constant curve)."""
        proc = self._run_py(
            """
            from sympy import symbols, Integer, simplify
            from sympy.calculus import arc_length
            x = symbols('x')
            res = arc_length(Integer(3), x, 0, 5)
            assert simplify(res - 5) == 0, res
            print("OK")
            """
        )
        self._assert_ok(proc, "constant curve arc length != b - a")

    def test_constant_curve_symbolic_limits(self):
        """Constant expr over symbolic [a, b] yields exactly b - a.

        Discriminates a real integral of sqrt(1+0)=1 from a hardcoded number.
        """
        proc = self._run_py(
            """
            from sympy import symbols, Integer, simplify
            from sympy.calculus import arc_length
            x, a, b = symbols('x a b')
            res = arc_length(Integer(7), x, a, b)
            assert simplify(res - (b - a)) == 0, res
            print("OK")
            """
        )
        self._assert_ok(proc, "constant curve over [a,b] != b - a")

    def test_equal_limits_is_zero(self):
        """arc_length(x, x, 2, 2) simplifies to 0 (degenerate interval)."""
        proc = self._run_py(
            """
            from sympy import symbols, simplify
            from sympy.calculus import arc_length
            x = symbols('x')
            res = arc_length(x, x, 2, 2)
            assert simplify(res) == 0, res
            print("OK")
            """
        )
        self._assert_ok(proc, "equal limits did not give 0")

    def test_semicubical_parabola_exact_rational(self):
        """arc_length((2*x**(3/2))/3, x, 0, 3) == Rational(14, 3) exactly.

        This is the canonical closed-form arc-length integral; only an exact
        derivative + exact integration reaches 14/3. A float or wrong-derivative
        impl will not match.
        """
        proc = self._run_py(
            """
            from sympy import symbols, Rational, simplify, Float
            from sympy.calculus import arc_length
            x = symbols('x')
            expr = (2 * x**Rational(3, 2)) / 3
            res = arc_length(expr, x, 0, 3)
            assert simplify(res - Rational(14, 3)) == 0, res
            assert not res.atoms(Float), "float introduced: %r" % res
            print("OK")
            """
        )
        self._assert_ok(proc, "semicubical parabola arc length != 14/3")

    def test_uses_exact_symbolic_derivative(self):
        """Result matches Integral(sqrt(1 + diff(expr,x)**2), (x,a,b)) numerically.

        Cross-checks against an INDEPENDENT formula built here (not the agent's
        code), pinning the integrand to the exact symbolic derivative. We use a
        curve with an elementary closed form so we can compare exact values.
        """
        proc = self._run_py(
            """
            from sympy import symbols, sqrt, diff, integrate, simplify, Rational
            from sympy.calculus import arc_length
            x = symbols('x')
            # y = x**2/2 has a known elementary arc length over [0, 1].
            expr = x**2 / 2
            res = arc_length(expr, x, 0, 1)
            # Independent reference: integral of sqrt(1 + (dy/dx)**2).
            yprime = diff(expr, x)
            ref = integrate(sqrt(1 + yprime**2), (x, 0, 1))
            assert simplify(res - ref) == 0, (res, ref)
            # The reference must itself be non-trivial (asinh / sqrt terms),
            # i.e. NOT equal to the naive b - a = 1.
            assert simplify(ref - 1) != 0, ref
            print("OK")
            """
        )
        self._assert_ok(proc, "result does not match exact-derivative integrand")

    def test_nonelementary_returns_Integral(self):
        """sin(x) over [0, pi] has no elementary arc length -> Integral instance.

        A naive impl that always evaluates to a number (or raises, or returns a
        Float) fails: the contract requires an unevaluated sympy.Integral here.
        """
        proc = self._run_py(
            """
            from sympy import symbols, sin, pi, Integral
            from sympy.calculus import arc_length
            x = symbols('x')
            res = arc_length(sin(x), x, 0, pi)
            assert isinstance(res, Integral), (type(res), res)
            print("OK")
            """
        )
        self._assert_ok(proc, "non-elementary case did not return Integral")

    def test_nonelementary_integral_has_correct_integrand(self):
        """The unevaluated Integral must carry the correct sqrt(1+y'**2) integrand.

        Guards against returning an arbitrary/placeholder Integral. We check the
        integrand difference is exactly zero and the limits are (x, 0, pi).
        """
        proc = self._run_py(
            """
            from sympy import symbols, sin, cos, pi, sqrt, Integral, simplify
            from sympy.calculus import arc_length
            x = symbols('x')
            res = arc_length(sin(x), x, 0, pi)
            assert isinstance(res, Integral), res
            integrand = res.function
            expected = sqrt(1 + cos(x)**2)
            assert simplify(integrand - expected) == 0, (integrand, expected)
            # Limits tuple: (symbol, lower, upper)
            assert res.limits == ((x, 0, pi),), res.limits
            print("OK")
            """
        )
        self._assert_ok(proc, "non-elementary Integral integrand/limits wrong")

    def test_symbolic_limits_flow_through(self):
        """Symbolic upper limit appears in the closed form for y = x.

        For y=x the integrand is sqrt(2); arc length over [0, t] = sqrt(2)*t.
        """
        proc = self._run_py(
            """
            from sympy import symbols, sqrt, simplify
            from sympy.calculus import arc_length
            x, t = symbols('x t', positive=True)
            res = arc_length(x, x, 0, t)
            assert simplify(res - sqrt(2) * t) == 0, res
            assert res.has(t), res
            print("OK")
            """
        )
        self._assert_ok(proc, "symbolic limit did not flow through")

    def test_does_not_raise_and_not_float_on_hard_case(self):
        """Non-elementary case must not raise and must not silently return float."""
        proc = self._run_py(
            """
            from sympy import symbols, exp, Float
            from sympy.calculus import arc_length
            x = symbols('x')
            # exp(x) arc length has no elementary closed form on a generic range.
            res = arc_length(exp(x), x, 0, 1)
            assert not isinstance(res, float), "returned a python float"
            # If symbolic, ensure no Float atoms snuck in (would mean numeric eval).
            try:
                has_float = bool(res.atoms(Float))
            except AttributeError:
                has_float = False
            assert not has_float, "Float atom present: %r" % res
            print("OK")
            """
        )
        self._assert_ok(proc, "hard case raised or returned a float")

    def test_native_pytest_suite_passes(self):
        """The deliverable's own pytest file collects and passes (green)."""
        env = dict(os.environ)
        env["PYTHONPATH"] = self.REPO_DIR
        # --noconftest avoids sympy/conftest.py's optional 'hypothesis'
        # dependency, keeping the check scoped to the deliverable file.
        proc = subprocess.run(
            ["python", "-m", "pytest",
             "sympy/calculus/tests/test_arclength.py", "-q",
             "-p", "no:cacheprovider", "--noconftest"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=600,
            env=env,
        )
        assert proc.returncode == 0, (
            "native test_arclength.py suite failed\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )
        out = proc.stdout + proc.stderr
        assert "passed" in out, out
        assert "no tests ran" not in out, out
