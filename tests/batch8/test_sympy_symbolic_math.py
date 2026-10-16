"""
Test for the 'sympy-symbolic-math' skill (variant ext8).

Task: add a series-coefficient extraction utility to ``sympy.series`` exposing
a single public function::

    from sympy.series import series_coefficients

``series_coefficients(expr, x, n, x0=0)`` returns a Python ``list`` of length
``n + 1`` whose entry at index ``k`` is the *exact* coefficient of
``(x - x0)**k`` in the Maclaurin/Taylor expansion of ``expr`` about ``x = x0``.

This suite verifies the deliverable by actually IMPORTING and EXERCISING the
agent's implementation inside the repo (PYTHONPATH = REPO_DIR so the in-repo
sympy is the one under test) and deep-validating the symbolic results:

  * the returned object is a Python list of length exactly ``n + 1``;
  * exact SymPy values (no Python/SymPy floats: ``Rational(1, 2)`` not ``0.5``);
  * coefficients indexed by ``(x - x0)**k`` (geometric / known expansions);
  * mathematically-zero coefficients returned as the SymPy integer ``0``;
  * polynomials reproduced exactly with ``0`` past their degree;
  * symbolic / constant base points (``x0 = 1`` -> index-0 == ``E``);
  * no ``O(...)`` order/remainder term anywhere in any coefficient;
  * ``ValueError`` on negative ``n``.

A naive implementation that returns floats, a wrong-length list, hardcodes a
fixed output, drops the ``x0`` shift, or leaves an ``O(...)`` term in place
must FAIL these checks.

L1 checks confirm the deliverable files exist and the import works.
L2 checks run real symbolic computations and assert deep equality, then drive
the doc's native acceptance command:

    python -m pytest sympy/series/tests/test_coeffs.py -q
"""

import os
import subprocess
import textwrap


class TestSympySymbolicMath:
    """Verify the sympy.series.series_coefficients utility (ext8 variant)."""

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

    def test_coeffs_module_file_exists(self):
        """sympy/series/coeffs.py must be created."""
        fpath = os.path.join(self.REPO_DIR, "sympy", "series", "coeffs.py")
        assert os.path.isfile(fpath), "sympy/series/coeffs.py not found"

    def test_coeffs_test_file_exists(self):
        """sympy/series/tests/test_coeffs.py must be created."""
        fpath = os.path.join(
            self.REPO_DIR, "sympy", "series", "tests", "test_coeffs.py"
        )
        assert os.path.isfile(fpath), "tests/test_coeffs.py not found"

    def test_public_import_succeeds(self):
        """series_coefficients must import from the sympy.series package."""
        proc = self._run_py(
            """
            from sympy.series import series_coefficients
            assert callable(series_coefficients)
            print("OK")
            """
        )
        self._assert_ok(proc, "from sympy.series import series_coefficients failed")

    # ------------------------------------------------------------------
    # L2: dynamic symbolic validation
    # ------------------------------------------------------------------

    def test_returns_list_of_correct_length(self):
        """Result is a Python list of length exactly n + 1 for several n."""
        proc = self._run_py(
            """
            from sympy import symbols, exp, sin
            from sympy.series import series_coefficients
            x = symbols('x')
            for n in (0, 1, 2, 5, 7):
                res = series_coefficients(exp(x), x, n)
                assert isinstance(res, list), type(res)
                assert len(res) == n + 1, (n, len(res))
            # also for a different expr
            assert len(series_coefficients(sin(x), x, 4)) == 5
            print("OK")
            """
        )
        self._assert_ok(proc, "list length is not n + 1")

    def test_exp_coefficients_exact(self):
        """series_coefficients(exp(x),x,3) == [1, 1, 1/2, 1/6] exactly."""
        proc = self._run_py(
            """
            from sympy import symbols, exp, Rational, sympify
            from sympy.series import series_coefficients
            x = symbols('x')
            res = series_coefficients(exp(x), x, 3)
            expected = [sympify(1), sympify(1), Rational(1, 2), Rational(1, 6)]
            assert res == expected, res
            # index-2 entry MUST be the exact rational, verified explicitly.
            assert (res[2] == Rational(1, 2)) is True, res[2]
            print("OK")
            """
        )
        self._assert_ok(proc, "exp coefficients wrong")

    def test_cos_coefficients_with_zeros(self):
        """series_coefficients(cos(x),x,4) == [1, 0, -1/2, 0, 1/24]."""
        proc = self._run_py(
            """
            from sympy import symbols, cos, Rational, Integer
            from sympy.series import series_coefficients
            x = symbols('x')
            res = series_coefficients(cos(x), x, 4)
            expected = [Integer(1), Integer(0), Rational(-1, 2),
                        Integer(0), Rational(1, 24)]
            assert res == expected, res
            # zero coefficients must be the SymPy Integer 0, not a float/None.
            assert res[1] == Integer(0) and res[3] == Integer(0)
            assert (res[2] == Rational(-1, 2)) is True, res[2]
            print("OK")
            """
        )
        self._assert_ok(proc, "cos coefficients wrong")

    def test_no_float_atoms(self):
        """No coefficient may contain a floating-point atom (0.5 forbidden)."""
        proc = self._run_py(
            """
            from sympy import symbols, exp, cos, sin, Float, sympify
            from sympy.series import series_coefficients
            x = symbols('x')
            for expr in (exp(x), cos(x), sin(x), 1/(1 - x)):
                for c in series_coefficients(expr, x, 5):
                    c = sympify(c)
                    assert not c.atoms(Float), (expr, c)
            print("OK")
            """
        )
        self._assert_ok(proc, "float coefficient introduced")

    def test_geometric_series_all_ones(self):
        """series_coefficients(1/(1-x),x,4) == [1, 1, 1, 1, 1]."""
        proc = self._run_py(
            """
            from sympy import symbols, Integer
            from sympy.series import series_coefficients
            x = symbols('x')
            res = series_coefficients(1/(1 - x), x, 4)
            assert res == [Integer(1)] * 5, res
            print("OK")
            """
        )
        self._assert_ok(proc, "geometric series coefficients wrong")

    def test_polynomial_exact_and_padded_with_zeros(self):
        """series_coefficients(x**2+3,x,5) == [3, 0, 1, 0, 0, 0] exactly."""
        proc = self._run_py(
            """
            from sympy import symbols, Integer
            from sympy.series import series_coefficients
            x = symbols('x')
            res = series_coefficients(x**2 + 3, x, 5)
            expected = [Integer(3), Integer(0), Integer(1),
                        Integer(0), Integer(0), Integer(0)]
            assert res == expected, res
            # length must extend past the polynomial degree, padded with 0.
            assert len(res) == 6, len(res)
            print("OK")
            """
        )
        self._assert_ok(proc, "polynomial coefficients not exact / not padded")

    def test_no_order_term_in_any_coefficient(self):
        """No coefficient may carry an O(...) order/remainder term."""
        proc = self._run_py(
            """
            from sympy import symbols, exp, sin, sympify
            from sympy.series.order import Order
            from sympy.series import series_coefficients
            x = symbols('x')
            for expr in (exp(x), sin(x), 1/(1 - x)):
                res = series_coefficients(expr, x, 6)
                for c in res:
                    c = sympify(c)
                    assert c.getO() is None, (expr, c)
                    assert not c.has(Order), (expr, c)
            print("OK")
            """
        )
        self._assert_ok(proc, "order term present in coefficients")

    def test_base_point_x0_one_index0_is_E(self):
        """series_coefficients(exp(x),x,2,x0=1) index-0 entry == E (exact)."""
        proc = self._run_py(
            """
            from sympy import symbols, exp, E, Rational
            from sympy.series import series_coefficients
            x = symbols('x')
            res = series_coefficients(exp(x), x, 2, x0=1)
            assert len(res) == 3, res
            assert (res[0] == E) is True, res[0]
            # coefficient of (x - 1)**1 and (x - 1)**2 for exp about 1.
            assert (res[1] == E) is True, res[1]
            assert (res[2] == E * Rational(1, 2)) is True, res[2]
            print("OK")
            """
        )
        self._assert_ok(proc, "x0=1 expansion (powers of (x-1)) wrong")

    def test_x0_shift_changes_result(self):
        """A correct x0 shift must differ from the x0=0 expansion.

        Guards against a stub that ignores x0 and always expands about 0:
        for exp, every coefficient about 0 is 1/k! (a number), whereas about
        x0=2 each coefficient involves E**2 -- so they cannot all coincide.
        """
        proc = self._run_py(
            """
            from sympy import symbols, exp, sympify
            from sympy.series import series_coefficients
            x = symbols('x')
            about0 = series_coefficients(exp(x), x, 3)
            about2 = series_coefficients(exp(x), x, 3, x0=2)
            assert about0 != about2, (about0, about2)
            # the x0=2 coefficients must depend on the exponential constant.
            assert any(sympify(c).has(exp(sympify(2))) or
                       'exp' in str(c) for c in about2), about2
            print("OK")
            """
        )
        self._assert_ok(proc, "x0 shift was ignored")

    def test_symbolic_base_point(self):
        """x0 may be a symbol; coefficients then involve that symbol.

        For sin about a symbolic point ``a`` the degree-2 coefficients are
        ``[sin(a), cos(a), -sin(a)/2]``.
        """
        proc = self._run_py(
            """
            from sympy import symbols, sin, cos, Rational, simplify
            from sympy.series import series_coefficients
            x, a = symbols('x a')
            res = series_coefficients(sin(x), x, 2, x0=a)
            assert len(res) == 3, res
            assert simplify(res[0] - sin(a)) == 0, res[0]
            assert simplify(res[1] - cos(a)) == 0, res[1]
            assert simplify(res[2] - (-sin(a) * Rational(1, 2))) == 0, res[2]
            assert res[1].has(a), res[1]
            print("OK")
            """
        )
        self._assert_ok(proc, "symbolic base point wrong")

    def test_negative_n_raises_value_error(self):
        """A negative n must raise ValueError (not return [], not crash)."""
        proc = self._run_py(
            """
            from sympy import symbols, sin
            from sympy.series import series_coefficients
            x = symbols('x')
            for bad in (-1, -3):
                try:
                    series_coefficients(sin(x), x, bad)
                except ValueError:
                    pass
                else:
                    raise AssertionError("expected ValueError for n=%r" % bad)
            print("OK")
            """
        )
        self._assert_ok(proc, "negative n did not raise ValueError")

    def test_n_zero_returns_constant_term(self):
        """n=0 returns a single-element list [expr(x0)]."""
        proc = self._run_py(
            """
            from sympy import symbols, cos, Integer
            from sympy.series import series_coefficients
            x = symbols('x')
            res = series_coefficients(cos(x), x, 0)
            assert res == [Integer(1)], res
            assert len(res) == 1, res
            print("OK")
            """
        )
        self._assert_ok(proc, "n=0 constant-term case wrong")

    def test_native_pytest_suite_passes(self):
        """The deliverable's own pytest file collects and passes (green).

        Drives the doc's native acceptance command:
            python -m pytest sympy/series/tests/test_coeffs.py -q
        """
        env = dict(os.environ)
        env["PYTHONPATH"] = self.REPO_DIR
        # --noconftest avoids sympy/conftest.py's optional 'hypothesis'
        # dependency, keeping the check scoped to the deliverable file.
        proc = subprocess.run(
            ["python", "-m", "pytest",
             "sympy/series/tests/test_coeffs.py", "-q",
             "-p", "no:cacheprovider", "--noconftest"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=600,
            env=env,
        )
        assert proc.returncode == 0, (
            "native test_coeffs.py suite failed\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )
        # Ensure at least some tests actually ran (no empty/no-op collection).
        out = proc.stdout + proc.stderr
        assert "passed" in out, out
        assert "no tests ran" not in out, out
