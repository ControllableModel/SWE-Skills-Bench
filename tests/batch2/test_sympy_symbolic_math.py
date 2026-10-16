"""
Test for the 'sympy-symbolic-math' skill (variant ext2).

Task: add a public characteristic-data utility to ``sympy.matrices`` exposing a
single function::

    from sympy.matrices import characteristic_data

``characteristic_data(M, lam=None)`` returns, for a square SymPy ``Matrix`` and
an optional symbol ``lam``, a ``dict`` with EXACTLY the four keys:

    "char_poly"    -- characteristic polynomial of M (expanded, in lam)
    "trace"        -- trace of M (exact SymPy expression)
    "determinant"  -- determinant of M (exact SymPy expression)
    "eigenvalues"  -- dict {eigenvalue: algebraic multiplicity}

Verification strategy
---------------------
The suite IMPORTS and EXERCISES the agent's implementation inside the repo
(PYTHONPATH = REPO_DIR so the in-repo sympy is the one under test) and
deep-validates the symbolic results:

  * the returned mapping has EXACTLY the four documented keys (no more/fewer);
  * exact integers/expressions, never floats (det of [[2,0],[0,3]] is 6, not 6.0);
  * char_poly evaluates to exact 0 (after simplify) at every eigenvalue;
  * eigenvalue multiplicities sum to the number of rows;
  * symbolic entries produce symbolic det/trace (a**2, 2*a);
  * a non-square input raises NonSquareMatrixError.

A naive/stub implementation (hardcoded dict, dropped keys, float arithmetic,
ignored matrix) must fail these checks.

L1 checks confirm the deliverable files exist and the public import works.
L2 checks run real symbolic computations and assert deep equality, and finally
drive the deliverable's own native pytest suite.
"""

import os
import subprocess
import textwrap

import pytest


class TestSympySymbolicMath:
    """Verify the characteristic_data utility in sympy.matrices."""

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

    def test_charutil_module_file_exists(self):
        """sympy/matrices/charutil.py must be created."""
        fpath = os.path.join(self.REPO_DIR, "sympy", "matrices", "charutil.py")
        assert os.path.isfile(fpath), "sympy/matrices/charutil.py not found"

    def test_charutil_test_file_exists(self):
        """sympy/matrices/tests/test_charutil.py must be created."""
        fpath = os.path.join(
            self.REPO_DIR, "sympy", "matrices", "tests", "test_charutil.py"
        )
        assert os.path.isfile(fpath), "tests/test_charutil.py not found"

    def test_public_import_succeeds(self):
        """characteristic_data must import from the sympy.matrices package."""
        proc = self._run_py(
            """
            from sympy.matrices import characteristic_data
            assert callable(characteristic_data)
            print("OK")
            """
        )
        self._assert_ok(proc, "from sympy.matrices import characteristic_data failed")

    # ------------------------------------------------------------------
    # L2: dynamic symbolic validation
    # ------------------------------------------------------------------

    def test_returns_dict_with_exactly_four_keys(self):
        """Result must be a dict with EXACTLY the four documented keys."""
        proc = self._run_py(
            """
            from sympy import Matrix
            from sympy.matrices import characteristic_data
            res = characteristic_data(Matrix([[1, 2], [2, 1]]))
            assert isinstance(res, dict), type(res)
            assert set(res.keys()) == {
                "char_poly", "trace", "determinant", "eigenvalues"
            }, sorted(res.keys())
            assert isinstance(res["eigenvalues"], dict), res["eigenvalues"]
            print("OK")
            """
        )
        self._assert_ok(proc, "result is not a dict with exactly four keys")

    def test_trace_and_determinant_exact_integers(self):
        """For [[2,0],[0,3]]: trace==5, determinant==6 as exact Integers (not floats)."""
        proc = self._run_py(
            """
            from sympy import Matrix, Integer, Float
            from sympy.matrices import characteristic_data
            res = characteristic_data(Matrix([[2, 0], [0, 3]]))
            tr = res["trace"]
            det = res["determinant"]
            assert (tr == 5) is True, tr
            assert (det == 6) is True, det
            # Must be exact SymPy integers, no float atoms anywhere.
            assert det == Integer(6), det
            assert not det.atoms(Float), "float in determinant: %r" % det
            assert not tr.atoms(Float), "float in trace: %r" % tr
            print("OK")
            """
        )
        self._assert_ok(proc, "trace/determinant not exact integers")

    def test_eigenvalues_symmetric_matrix(self):
        """characteristic_data([[1,2],[2,1]])['eigenvalues'] == {3:1, -1:1}."""
        proc = self._run_py(
            """
            from sympy import Matrix, Integer
            from sympy.matrices import characteristic_data
            ev = characteristic_data(Matrix([[1, 2], [2, 1]]))["eigenvalues"]
            assert ev == {3: 1, -1: 1}, ev
            # multiplicities must be (sympy/python) integers
            for mult in ev.values():
                assert int(mult) == mult, mult
            print("OK")
            """
        )
        self._assert_ok(proc, "eigenvalues of symmetric matrix wrong")

    def test_multiplicities_sum_to_rows(self):
        """Sum of eigenvalue algebraic multiplicities == number of rows."""
        proc = self._run_py(
            """
            from sympy import Matrix
            from sympy.matrices import characteristic_data
            M = Matrix([[2, 0, 0], [0, 2, 0], [0, 0, 5]])
            ev = characteristic_data(M)["eigenvalues"]
            assert sum(ev.values()) == M.rows == 3, ev
            # repeated eigenvalue 2 has multiplicity 2
            assert ev.get(2) == 2, ev
            assert ev.get(5) == 1, ev
            print("OK")
            """
        )
        self._assert_ok(proc, "multiplicities do not sum to rows")

    def test_char_poly_vanishes_at_eigenvalues(self):
        """For every eigenvalue e: simplify(char_poly.subs(lam, e)) == 0."""
        proc = self._run_py(
            """
            from sympy import Matrix, symbols, simplify
            from sympy.matrices import characteristic_data
            lam = symbols('mu')
            M = Matrix([[1, 2], [2, 1]])
            res = characteristic_data(M, lam)
            cp = res["char_poly"]
            assert cp.has(lam), "char_poly does not depend on lam: %r" % cp
            for e in res["eigenvalues"]:
                assert simplify(cp.subs(lam, e)) == 0, (e, cp)
            print("OK")
            """
        )
        self._assert_ok(proc, "char_poly does not vanish at eigenvalues")

    def test_char_poly_is_expanded_monomials(self):
        """char_poly equals the expanded det(M - lam*I), a sum of monomials."""
        proc = self._run_py(
            """
            from sympy import Matrix, symbols, expand, eye
            from sympy.matrices import characteristic_data
            lam = symbols('mu')
            M = Matrix([[1, 2], [2, 1]])
            cp = characteristic_data(M, lam)["char_poly"]
            # det(M - lam*I) for this matrix = (1-lam)**2 - 4 = lam**2 - 2*lam - 3
            expected = (M - lam*eye(2)).det()
            assert expand(cp - expected) == 0, (cp, expected)
            # Already expanded: equal to its own expansion.
            assert expand(cp) == cp, "char_poly not returned expanded: %r" % cp
            print("OK")
            """
        )
        self._assert_ok(proc, "char_poly is not the expanded det(M - lam*I)")

    def test_rotation_matrix_complex_eigenvalues(self):
        """[[0,-1],[1,0]]: substituting an eigenvalue into char_poly gives 0."""
        proc = self._run_py(
            """
            from sympy import Matrix, symbols, simplify, I
            from sympy.matrices import characteristic_data
            lam = symbols('mu')
            M = Matrix([[0, -1], [1, 0]])
            res = characteristic_data(M, lam)
            cp = res["char_poly"]
            ev = res["eigenvalues"]
            # eigenvalues are +-I, each with multiplicity 1
            assert set(ev.keys()) == {I, -I}, ev
            assert sum(ev.values()) == 2, ev
            for e in ev:
                assert simplify(cp.subs(lam, e)) == 0, (e, cp)
            print("OK")
            """
        )
        self._assert_ok(proc, "rotation-matrix complex eigenvalue case wrong")

    def test_default_lambda_symbol(self):
        """When lam is None a symbol named 'lambda' is used internally."""
        proc = self._run_py(
            """
            from sympy import Matrix, Symbol, simplify
            from sympy.matrices import characteristic_data
            M = Matrix([[1, 2], [2, 1]])
            res = characteristic_data(M)
            cp = res["char_poly"]
            free = {s.name for s in cp.free_symbols}
            assert "lambda" in free, "default symbol not named 'lambda': %r" % free
            lam = Symbol("lambda")
            for e in res["eigenvalues"]:
                assert simplify(cp.subs(lam, e)) == 0, (e, cp)
            print("OK")
            """
        )
        self._assert_ok(proc, "default lambda symbol handling wrong")

    def test_symbolic_entries(self):
        """For [[a,0],[0,a]]: determinant==a**2, trace==2*a (symbolic, exact)."""
        proc = self._run_py(
            """
            from sympy import Matrix, symbols, expand, Float
            from sympy.matrices import characteristic_data
            a = symbols('a')
            res = characteristic_data(Matrix([[a, 0], [0, a]]))
            det = res["determinant"]
            tr = res["trace"]
            assert expand(det - a**2) == 0, det
            assert expand(tr - 2*a) == 0, tr
            assert det.has(a) and tr.has(a)
            assert not det.atoms(Float) and not tr.atoms(Float)
            # eigenvalue a has multiplicity 2
            ev = res["eigenvalues"]
            assert ev.get(a) == 2, ev
            print("OK")
            """
        )
        self._assert_ok(proc, "symbolic-entry handling wrong")

    def test_non_square_raises(self):
        """A non-square matrix raises NonSquareMatrixError (importable from sympy.matrices)."""
        proc = self._run_py(
            """
            from sympy import Matrix
            from sympy.matrices import characteristic_data, NonSquareMatrixError
            try:
                characteristic_data(Matrix([[1, 2, 3], [4, 5, 6]]))
            except NonSquareMatrixError:
                print("OK")
            else:
                raise AssertionError("expected NonSquareMatrixError for 2x3 matrix")
            """
        )
        self._assert_ok(proc, "non-square input did not raise NonSquareMatrixError")

    def test_not_a_hardcoded_stub(self):
        """A second, distinct matrix yields its own correct data (defeats hardcoding)."""
        proc = self._run_py(
            """
            from sympy import Matrix
            from sympy.matrices import characteristic_data
            # Upper-triangular: eigenvalues on the diagonal, det = product.
            M = Matrix([[4, 7], [0, 9]])
            res = characteristic_data(M)
            assert (res["trace"] == 13) is True, res["trace"]
            assert (res["determinant"] == 36) is True, res["determinant"]
            assert res["eigenvalues"] == {4: 1, 9: 1}, res["eigenvalues"]
            print("OK")
            """
        )
        self._assert_ok(proc, "implementation appears hardcoded / matrix-insensitive")

    def test_native_pytest_suite_passes(self):
        """The deliverable's own pytest file collects and passes (green)."""
        env = dict(os.environ)
        env["PYTHONPATH"] = self.REPO_DIR
        # --noconftest avoids sympy/conftest.py's optional 'hypothesis'
        # dependency, keeping the check scoped to the deliverable file.
        proc = subprocess.run(
            ["python", "-m", "pytest",
             "sympy/matrices/tests/test_charutil.py", "-q",
             "-p", "no:cacheprovider", "--noconftest"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=600,
            env=env,
        )
        assert proc.returncode == 0, (
            "native test_charutil.py suite failed\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )
        out = proc.stdout + proc.stderr
        assert "passed" in out, out
        assert "no tests ran" not in out, out
