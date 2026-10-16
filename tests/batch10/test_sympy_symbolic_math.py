"""
Test for the 'sympy-symbolic-math' skill (variant ext10).

Task: add a calculus LaTeX-report utility to ``sympy.printing`` exposing two
public functions:

    from sympy.printing import latex_derivative_report, latex_integral_report

Each function returns a ``dict`` with exactly the keys
``{"operation", "result", "equation"}`` (all ``str``):

  * ``operation`` is the LaTeX of the UNEVALUATED Derivative/Integral object
    (so it must carry the ``\\frac{d}{d x}`` / ``\\int`` notation);
  * ``result``    is the LaTeX of the EVALUATED expression, and must equal
    ``latex(Derivative(expr, x).doit())`` (resp. the integral) EXACTLY;
  * ``equation``  is exactly ``operation + " = " + result``.

For a definite integral both ``a`` and ``b`` must be supplied; supplying only
one raises ``ValueError``.

Verification strategy:
  * L1 confirms the deliverable files exist and the public import works.
  * L2 IMPORTS the agent's implementation inside the repo (PYTHONPATH=REPO_DIR
    so the in-repo sympy is under test) and deep-validates concrete LaTeX
    strings against an INDEPENDENT recomputation with ``sympy.latex`` +
    unevaluated ``Derivative``/``Integral`` objects. A stub that hardcodes a
    string, returns the evaluated form in ``operation``, skips the ``" = "``
    join, or ignores the limits will fail. The deliverable's own pytest file
    is also run green.
"""

import os
import subprocess
import textwrap

import pytest


class TestSympySymbolicMath:
    """Verify the latex_derivative_report / latex_integral_report utilities."""

    REPO_DIR = "/workspace/sympy"

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _run_py(self, body, timeout=300):
        """Run a python snippet with the in-repo sympy on PYTHONPATH.

        ``body`` is dedented and executed; the snippet must print a final-line
        sentinel ``OK`` on success or raise. Returns the CompletedProcess.
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
    # L1: deliverables exist / minimally well-formed
    # ------------------------------------------------------------------

    def test_mathreport_module_file_exists(self):
        """sympy/printing/mathreport.py must be created."""
        fpath = os.path.join(
            self.REPO_DIR, "sympy", "printing", "mathreport.py"
        )
        assert os.path.isfile(fpath), "sympy/printing/mathreport.py not found"

    def test_mathreport_test_file_exists(self):
        """sympy/printing/tests/test_mathreport.py must be created."""
        fpath = os.path.join(
            self.REPO_DIR, "sympy", "printing", "tests", "test_mathreport.py"
        )
        assert os.path.isfile(fpath), "tests/test_mathreport.py not found"

    def test_public_import_succeeds(self):
        """Both functions must import from the sympy.printing package."""
        proc = self._run_py(
            """
            from sympy.printing import (
                latex_derivative_report, latex_integral_report
            )
            assert callable(latex_derivative_report)
            assert callable(latex_integral_report)
            print("OK")
            """
        )
        self._assert_ok(proc, "from sympy.printing import ... failed")

    def test_return_shape_is_exact_dict(self):
        """Each report is a dict with EXACTLY the three string keys."""
        proc = self._run_py(
            """
            from sympy import symbols
            from sympy.printing import (
                latex_derivative_report, latex_integral_report
            )
            x = symbols('x')
            for rep in (
                latex_derivative_report(x**2, x),
                latex_integral_report(x**2, x),
                latex_integral_report(x**2, x, 0, 1),
            ):
                assert isinstance(rep, dict), type(rep)
                assert set(rep.keys()) == {"operation", "result", "equation"}, rep
                for v in rep.values():
                    assert isinstance(v, str), (rep, v)
            print("OK")
            """
        )
        self._assert_ok(proc, "report dict shape/keys/types wrong")

    # ------------------------------------------------------------------
    # L2: deep behavioral verification (independent recomputation)
    # ------------------------------------------------------------------

    def test_derivative_result_matches_doit_latex(self):
        """derivative 'result' == latex(Derivative(expr,x).doit()) exactly."""
        proc = self._run_py(
            """
            from sympy import symbols, sin, Derivative, latex
            from sympy.printing import latex_derivative_report
            x = symbols('x')
            for expr in (x**2, sin(x), x*sin(x), x**3 + 2*x):
                rep = latex_derivative_report(expr, x)
                expected = latex(Derivative(expr, x).doit())
                assert rep["result"] == expected, (expr, rep["result"], expected)
            # concrete spot check from the doc
            assert latex_derivative_report(x**2, x)["result"] == "2 x"
            print("OK")
            """
        )
        self._assert_ok(proc, "derivative result does not match doit latex")

    def test_derivative_operation_is_unevaluated(self):
        """derivative 'operation' carries the unevaluated d/dx notation."""
        proc = self._run_py(
            r"""
            from sympy import symbols, sin, Derivative, latex
            from sympy.printing import latex_derivative_report
            x = symbols('x')
            rep = latex_derivative_report(sin(x), x)
            # must be the UNEVALUATED Derivative LaTeX, not the result
            assert rep["operation"] == latex(Derivative(sin(x), x)), rep
            assert "\\frac{d}{d x}" in rep["operation"], rep["operation"]
            # a stub returning the evaluated form would NOT contain d/dx
            assert rep["operation"] != rep["result"], rep
            print("OK")
            """
        )
        self._assert_ok(proc, "derivative operation not the unevaluated form")

    def test_derivative_equation_is_join(self):
        """derivative 'equation' == operation + ' = ' + result exactly."""
        proc = self._run_py(
            """
            from sympy import symbols, sin
            from sympy.printing import latex_derivative_report
            x = symbols('x')
            for expr in (x**2, sin(x), x*sin(x)):
                rep = latex_derivative_report(expr, x)
                assert rep["equation"] == rep["operation"] + " = " + rep["result"], rep
                # exactly one ' = ' separating the two halves
                assert rep["equation"].count(" = ") >= 1, rep
            print("OK")
            """
        )
        self._assert_ok(proc, "derivative equation join wrong")

    def test_indefinite_integral_result_and_operation(self):
        """indefinite integral 'result'/'operation' match independent latex."""
        proc = self._run_py(
            r"""
            from sympy import symbols, Integral, latex
            from sympy.printing import latex_integral_report
            x = symbols('x')
            rep = latex_integral_report(x**2, x)
            assert rep["result"] == latex(Integral(x**2, x).doit()), rep
            assert rep["result"] == "\\frac{x^{3}}{3}", rep["result"]
            # operation = UNEVALUATED indefinite integral
            assert rep["operation"] == latex(Integral(x**2, x)), rep
            assert "\\int" in rep["operation"], rep["operation"]
            print("OK")
            """
        )
        self._assert_ok(proc, "indefinite integral report wrong")

    def test_definite_integral_uses_limits(self):
        """definite integral encodes the limits and evaluates to a number."""
        proc = self._run_py(
            r"""
            from sympy import symbols, Integral, latex
            from sympy.printing import latex_integral_report
            x = symbols('x')
            rep = latex_integral_report(x**2, x, 0, 1)
            # operation = UNEVALUATED definite integral with limits 0..1
            assert rep["operation"] == latex(Integral(x**2, (x, 0, 1))), rep
            assert "\\int" in rep["operation"], rep["operation"]
            assert "0" in rep["operation"] and "1" in rep["operation"], rep
            # result = evaluated definite integral = 1/3
            assert rep["result"] == latex(Integral(x**2, (x, 0, 1)).doit()), rep
            assert rep["result"] == "\\frac{1}{3}", rep["result"]
            # equation join
            assert rep["equation"] == rep["operation"] + " = " + rep["result"], rep
            print("OK")
            """
        )
        self._assert_ok(proc, "definite integral report wrong")

    def test_definite_differs_from_indefinite(self):
        """A stub ignoring a,b would give the same operation for both forms."""
        proc = self._run_py(
            """
            from sympy import symbols
            from sympy.printing import latex_integral_report
            x = symbols('x')
            indef = latex_integral_report(x**2, x)
            defin = latex_integral_report(x**2, x, 0, 1)
            # limits must actually change both the operation and the result
            assert indef["operation"] != defin["operation"], (indef, defin)
            assert indef["result"] != defin["result"], (indef, defin)
            print("OK")
            """
        )
        self._assert_ok(proc, "definite/indefinite not distinguished (limits ignored)")

    def test_definite_limits_affect_value(self):
        """Different bounds must yield different evaluated results."""
        proc = self._run_py(
            r"""
            from sympy import symbols, Integral, latex
            from sympy.printing import latex_integral_report
            x = symbols('x')
            r1 = latex_integral_report(x**2, x, 0, 1)
            r2 = latex_integral_report(x**2, x, 0, 2)
            assert r1["result"] == latex(Integral(x**2, (x, 0, 1)).doit()), r1
            assert r2["result"] == latex(Integral(x**2, (x, 0, 2)).doit()), r2
            assert r1["result"] != r2["result"], (r1, r2)
            # 0..2 of x**2 = 8/3
            assert r2["result"] == "\\frac{8}{3}", r2["result"]
            print("OK")
            """
        )
        self._assert_ok(proc, "definite bounds not honored")

    def test_partial_limit_raises_valueerror(self):
        """Supplying only one of a/b must raise ValueError."""
        proc = self._run_py(
            """
            from sympy import symbols
            from sympy.printing import latex_integral_report
            x = symbols('x')
            n_raised = 0
            for args in [(x**2, x, 0), (x**2, x, None, 1)]:
                try:
                    latex_integral_report(*args)
                except ValueError:
                    n_raised += 1
                else:
                    raise AssertionError("expected ValueError for %r" % (args,))
            assert n_raised == 2
            print("OK")
            """
        )
        self._assert_ok(proc, "partial definite limit did not raise ValueError")

    def test_symbolic_inputs_reflected(self):
        """Symbolic inputs flow into the LaTeX output (not hardcoded)."""
        proc = self._run_py(
            r"""
            from sympy import symbols, sin, Derivative, Integral, latex
            from sympy.printing import (
                latex_derivative_report, latex_integral_report
            )
            x, a = symbols('x a')
            d = latex_derivative_report(a*sin(x), x)
            assert d["operation"] == latex(Derivative(a*sin(x), x)), d
            assert d["result"] == latex(Derivative(a*sin(x), x).doit()), d
            assert "a" in d["result"], d["result"]
            i = latex_integral_report(a*x, x)
            assert i["result"] == latex(Integral(a*x, x).doit()), i
            assert "a" in i["result"], i["result"]
            print("OK")
            """
        )
        self._assert_ok(proc, "symbolic inputs not reflected in output")

    def test_values_are_plain_str_type(self):
        """Every returned value must be a builtin str, not a sympy/LaTeX wrapper."""
        proc = self._run_py(
            """
            from sympy import symbols, sin
            from sympy.printing import (
                latex_derivative_report, latex_integral_report
            )
            x = symbols('x')
            reps = [
                latex_derivative_report(sin(x), x),
                latex_integral_report(sin(x), x),
                latex_integral_report(x**2, x, 0, 1),
            ]
            for rep in reps:
                for k, v in rep.items():
                    assert type(v) is str, (k, type(v))
            print("OK")
            """
        )
        self._assert_ok(proc, "values are not plain str")

    def test_native_pytest_suite_passes(self):
        """The deliverable's own pytest file collects and passes (green)."""
        env = dict(os.environ)
        env["PYTHONPATH"] = self.REPO_DIR
        # --noconftest avoids sympy/conftest.py's optional 'hypothesis'
        # dependency, keeping the check scoped to the deliverable file.
        proc = subprocess.run(
            ["python", "-m", "pytest",
             "sympy/printing/tests/test_mathreport.py", "-q",
             "-p", "no:cacheprovider", "--noconftest"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=600,
            env=env,
        )
        assert proc.returncode == 0, (
            "native test_mathreport.py suite failed\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )
        out = proc.stdout + proc.stderr
        assert "passed" in out, out
        assert "no tests ran" not in out, out
