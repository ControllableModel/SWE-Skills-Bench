"""
Test for the 'sympy-symbolic-math' skill (variant ext6).

Task: add a fast tabulated-evaluator builder to ``sympy.utilities`` exposing a
single public function::

    from sympy.utilities import tabulate_expr

``tabulate_expr(expr, x, values)`` builds one reusable numeric callable for an
expression ``expr`` in a single symbol ``x`` and tabulates it over ``values``,
returning a list of ``(input, output)`` pairs where every ``output`` is a
Python ``float``.

This suite verifies the deliverable by actually IMPORTING and EXERCISING the
agent's implementation inside the repo (PYTHONPATH = REPO_DIR so the in-repo
sympy is the one under test) and deep-validating behavior:

  * outputs are real Python floats matching ``float(expr.subs(x, v).evalf())``
    within 1e-9 (numeric correctness, not just shape),
  * output order matches input order,
  * empty input yields ``[]``,
  * constant (x-free) expressions return the constant for every input,
  * a non-numeric value raises ``TypeError``,
  * the implementation works with NumPy disabled (no NumPy-only backend),
  * transcendental expressions (sin/cos/exp) evaluate correctly.

A naive stub that returns a fixed value, ignores ``values`` order, hardcodes
the example list, or returns SymPy objects instead of Python floats MUST fail.

L1 checks confirm the deliverable files exist, are exported, and the import
works. L2 checks run real numeric evaluations and assert deep value equality,
plus drive the deliverable's own pytest file (the native acceptance command).
"""

import os
import subprocess
import textwrap

import pytest


class TestSympySymbolicMath:
    """Verify the tabulate_expr utility in sympy.utilities."""

    REPO_DIR = "/workspace/sympy"

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _run_py(self, body, timeout=300, env_extra=None):
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
        if env_extra:
            env.update(env_extra)
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
    # L1: deliverables exist / minimally well-formed
    # ------------------------------------------------------------------

    def test_evaltable_module_file_exists(self):
        """sympy/utilities/evaltable.py must be created."""
        fpath = os.path.join(
            self.REPO_DIR, "sympy", "utilities", "evaltable.py"
        )
        assert os.path.isfile(fpath), "sympy/utilities/evaltable.py not found"

    def test_evaltable_test_file_exists(self):
        """sympy/utilities/tests/test_evaltable.py must be created."""
        fpath = os.path.join(
            self.REPO_DIR, "sympy", "utilities", "tests", "test_evaltable.py"
        )
        assert os.path.isfile(fpath), "tests/test_evaltable.py not found"

    def test_public_import_succeeds(self):
        """tabulate_expr must import from the sympy.utilities package."""
        proc = self._run_py(
            """
            from sympy.utilities import tabulate_expr
            assert callable(tabulate_expr)
            print("OK")
            """
        )
        self._assert_ok(proc, "from sympy.utilities import tabulate_expr failed")

    # ------------------------------------------------------------------
    # L2: dynamic numeric validation
    # ------------------------------------------------------------------

    def test_basic_polynomial_table(self):
        """tabulate_expr(x**2, x, [0,1,2,3]) -> exact (input, square) pairs."""
        proc = self._run_py(
            """
            from sympy import symbols
            from sympy.utilities import tabulate_expr
            x = symbols('x')
            res = tabulate_expr(x**2, x, [0, 1, 2, 3])
            assert isinstance(res, list), type(res)
            assert len(res) == 4, res
            expected = [(0, 0.0), (1, 1.0), (2, 4.0), (3, 9.0)]
            for (gi, go), (ei, eo) in zip(res, expected):
                assert gi == ei, (gi, ei)
                assert isinstance(go, float), type(go)
                assert abs(go - eo) < 1e-9, (go, eo)
            print("OK")
            """
        )
        self._assert_ok(proc, "x**2 table wrong")

    def test_outputs_are_python_floats_matching_evalf(self):
        """Every output is a Python float == float(expr.subs(x,v).evalf())."""
        proc = self._run_py(
            """
            from sympy import symbols, sin, Rational
            from sympy.utilities import tabulate_expr
            x = symbols('x')
            expr = sin(x) + x/3
            values = [Rational(1, 2), 1, 2, Rational(7, 4), 3]
            res = tabulate_expr(expr, x, values)
            assert len(res) == len(values)
            for (gi, go), v in zip(res, values):
                assert gi == v, (gi, v)
                # Must be a *Python* float, not a SymPy Float/number.
                assert type(go) is float, (type(go), go)
                ref = float(expr.subs(x, v).evalf())
                assert abs(go - ref) < 1e-9, (go, ref, v)
            print("OK")
            """
        )
        self._assert_ok(proc, "outputs not floats matching evalf")

    def test_order_preserved_and_not_hardcoded(self):
        """Output order matches input order; a non-monotone, non-example input
        defeats any hardcoded/sorted/fixed-list stub."""
        proc = self._run_py(
            """
            from sympy import symbols
            from sympy.utilities import tabulate_expr
            x = symbols('x')
            # Deliberately unsorted and not the doc's example list.
            values = [5, -2, 3, 0, -7, 4]
            res = tabulate_expr(x**2, x, values)
            inputs = [p[0] for p in res]
            assert inputs == values, (inputs, values)
            outputs = [p[1] for p in res]
            expected = [25.0, 4.0, 9.0, 0.0, 49.0, 16.0]
            for go, eo in zip(outputs, expected):
                assert isinstance(go, float)
                assert abs(go - eo) < 1e-9, (go, eo)
            print("OK")
            """
        )
        self._assert_ok(proc, "order not preserved / output hardcoded")

    def test_empty_values_returns_empty_list(self):
        """tabulate_expr(x+1, x, []) -> []."""
        proc = self._run_py(
            """
            from sympy import symbols
            from sympy.utilities import tabulate_expr
            x = symbols('x')
            res = tabulate_expr(x + 1, x, [])
            assert res == [], res
            assert isinstance(res, list), type(res)
            print("OK")
            """
        )
        self._assert_ok(proc, "empty input did not yield []")

    def test_constant_expression(self):
        """A constant (x-free) expr yields that constant for every input."""
        proc = self._run_py(
            """
            from sympy import symbols, Integer
            from sympy.utilities import tabulate_expr
            x = symbols('x')
            res = tabulate_expr(Integer(5), x, [1, 2])
            assert len(res) == 2, res
            assert res[0][0] == 1 and res[1][0] == 2, res
            for _, out in res:
                assert isinstance(out, float), type(out)
                assert abs(out - 5.0) < 1e-9, out
            # Different inputs, still constant.
            res2 = tabulate_expr(Integer(5), x, [-3, 0, 10, 100])
            for _, out in res2:
                assert abs(out - 5.0) < 1e-9, out
            print("OK")
            """
        )
        self._assert_ok(proc, "constant expression case wrong")

    def test_transcendental_sin_at_zero(self):
        """tabulate_expr(sin(x), x, [0]) first output within 1e-9 of 0.0."""
        proc = self._run_py(
            """
            from sympy import symbols, sin, pi
            from sympy.utilities import tabulate_expr
            x = symbols('x')
            res = tabulate_expr(sin(x), x, [0])
            assert len(res) == 1, res
            out = res[0][1]
            assert isinstance(out, float), type(out)
            assert abs(out - 0.0) < 1e-9, out
            # sin at pi/2 == 1, cos folded in to ensure real callable build.
            res2 = tabulate_expr(sin(x), x, [pi/2])
            assert abs(res2[0][1] - 1.0) < 1e-9, res2
            print("OK")
            """
        )
        self._assert_ok(proc, "sin tabulation wrong")

    def test_exp_values_match_reference(self):
        """exp(x) tabulated over several points matches evalf reference."""
        proc = self._run_py(
            """
            from sympy import symbols, exp
            from sympy.utilities import tabulate_expr
            x = symbols('x')
            expr = exp(x)
            values = [-1, 0, 1, 2]
            res = tabulate_expr(expr, x, values)
            for (gi, go), v in zip(res, values):
                ref = float(expr.subs(x, v).evalf())
                assert type(go) is float, type(go)
                assert abs(go - ref) < 1e-9, (go, ref, v)
            print("OK")
            """
        )
        self._assert_ok(proc, "exp tabulation wrong")

    def test_non_numeric_value_raises_typeerror(self):
        """A non-numeric entry in values must raise TypeError."""
        proc = self._run_py(
            """
            from sympy import symbols
            from sympy.utilities import tabulate_expr
            x = symbols('x')
            try:
                tabulate_expr(x, x, ["a"])
            except TypeError:
                print("OK")
            else:
                raise AssertionError("expected TypeError for non-numeric value")
            """
        )
        self._assert_ok(proc, "non-numeric value did not raise TypeError")

    def test_works_without_numpy(self):
        """The function must succeed even if NumPy is unavailable.

        We block ``import numpy`` via a meta-path finder before importing the
        utility, proving no NumPy-only backend is required.
        """
        proc = self._run_py(
            """
            import sys
            import importlib.abc, importlib.machinery
            class _BlockNumpy(importlib.abc.MetaPathFinder):
                def find_spec(self, name, path, target=None):
                    if name == 'numpy' or name.startswith('numpy.'):
                        raise ImportError('numpy blocked for test')
                    return None
            # Drop any pre-imported numpy then block future imports.
            for m in list(sys.modules):
                if m == 'numpy' or m.startswith('numpy.'):
                    del sys.modules[m]
            sys.meta_path.insert(0, _BlockNumpy())
            # Sanity: importing numpy now fails.
            try:
                import numpy  # noqa
                raise AssertionError("numpy import should have been blocked")
            except ImportError:
                pass
            from sympy import symbols
            from sympy.utilities import tabulate_expr
            x = symbols('x')
            res = tabulate_expr(x**2, x, [0, 1, 2, 3])
            expected = [0.0, 1.0, 4.0, 9.0]
            for (_, go), eo in zip(res, expected):
                assert type(go) is float, type(go)
                assert abs(go - eo) < 1e-9, (go, eo)
            print("OK")
            """
        )
        self._assert_ok(proc, "tabulate_expr failed without numpy")

    def test_reuses_single_callable_large_table(self):
        """A larger non-trivial table is correct end-to-end (smoke for the
        'build one reusable callable' contract over many inputs)."""
        proc = self._run_py(
            """
            from sympy import symbols, sin, cos
            from sympy.utilities import tabulate_expr
            x = symbols('x')
            expr = sin(x)*cos(x) + x**2
            values = list(range(0, 20))
            res = tabulate_expr(expr, x, values)
            assert len(res) == 20, len(res)
            for (gi, go), v in zip(res, values):
                assert gi == v
                ref = float(expr.subs(x, v).evalf())
                assert type(go) is float
                assert abs(go - ref) < 1e-9, (go, ref, v)
            print("OK")
            """
        )
        self._assert_ok(proc, "large table evaluation wrong")

    def test_native_pytest_suite_passes(self):
        """The deliverable's own pytest file collects and passes (green).

        This is the variant's native acceptance command:
            python -m pytest sympy/utilities/tests/test_evaltable.py -q
        """
        env = dict(os.environ)
        env["PYTHONPATH"] = self.REPO_DIR
        # --noconftest avoids sympy/conftest.py's optional 'hypothesis'
        # dependency, keeping the check scoped to the deliverable file.
        proc = subprocess.run(
            ["python", "-m", "pytest",
             "sympy/utilities/tests/test_evaltable.py", "-q",
             "-p", "no:cacheprovider", "--noconftest"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=600,
            env=env,
        )
        assert proc.returncode == 0, (
            "native test_evaltable.py suite failed\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )
        out = proc.stdout + proc.stderr
        assert "passed" in out, out
        assert "no tests ran" not in out, out
