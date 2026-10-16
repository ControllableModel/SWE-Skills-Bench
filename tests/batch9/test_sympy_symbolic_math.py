"""
Test for the 'sympy-symbolic-math' skill  (variant batch: ext9).

Task: add a vector-field analysis utility to ``sympy.vector`` exposing a single
public function::

    from sympy.vector import field_analysis

``field_analysis(field, coord_sys)`` bundles the standard differential
operators applied to a scalar or vector field in a given ``CoordSys3D``:

  * scalar field  -> dict with exactly keys {"gradient", "laplacian"}
  * vector field  -> dict with exactly keys {"divergence", "curl"}
  * anything else -> raises TypeError

This suite verifies the deliverable by actually IMPORTING and EXERCISING the
agent's implementation inside the repo (PYTHONPATH = REPO_DIR so the in-repo
sympy is the one under test) and deep-validating the symbolic results:

  * exact symbolic gradient / laplacian / divergence / curl,
  * the precise key set per field type (no extra/missing keys -> kills a
    stub that always returns the same dict),
  * curl-free and divergence-free edge cases collapse to the zero element,
  * constant scalar field -> zero gradient and 0 laplacian,
  * TypeError on an unrecognized field (kills a "never validates input" stub),
  * scalar-vs-vector dispatch is real (a stub that ignores the input's type
    and always returns scalar keys must fail).

L1 checks confirm the deliverable files exist and the import works.
L2 checks run real symbolic computations and assert deep equality, then run
the deliverable's own native pytest file.
"""

import os
import subprocess
import textwrap

import pytest


class TestSympySymbolicMath:
    """Verify the field_analysis vector-field utility."""

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

    def test_fieldanalysis_module_file_exists(self):
        """sympy/vector/fieldanalysis.py must be created."""
        fpath = os.path.join(
            self.REPO_DIR, "sympy", "vector", "fieldanalysis.py"
        )
        assert os.path.isfile(fpath), "sympy/vector/fieldanalysis.py not found"

    def test_native_test_file_exists(self):
        """sympy/vector/tests/test_fieldanalysis.py must be created."""
        fpath = os.path.join(
            self.REPO_DIR, "sympy", "vector", "tests", "test_fieldanalysis.py"
        )
        assert os.path.isfile(fpath), "tests/test_fieldanalysis.py not found"

    def test_public_import_succeeds(self):
        """field_analysis must import from the sympy.vector package."""
        proc = self._run_py(
            """
            from sympy.vector import field_analysis
            assert callable(field_analysis)
            print("OK")
            """
        )
        self._assert_ok(proc, "from sympy.vector import field_analysis failed")

    # ------------------------------------------------------------------
    # L2: dynamic symbolic validation
    # ------------------------------------------------------------------

    def test_scalar_key_set_exact(self):
        """A scalar field yields EXACTLY {'gradient','laplacian'} keys.

        Kills a stub that returns a fixed dict with all four operators.
        """
        proc = self._run_py(
            """
            from sympy.vector import CoordSys3D, field_analysis
            C = CoordSys3D('C')
            res = field_analysis(C.x**2 + C.y**2 + C.z**2, C)
            assert isinstance(res, dict), type(res)
            assert set(res.keys()) == {"gradient", "laplacian"}, res.keys()
            print("OK")
            """
        )
        self._assert_ok(proc, "scalar key set wrong")

    def test_vector_key_set_exact(self):
        """A vector field yields EXACTLY {'divergence','curl'} keys.

        A stub that always returns scalar keys (ignoring the field type)
        must fail here.
        """
        proc = self._run_py(
            """
            from sympy.vector import CoordSys3D, field_analysis
            C = CoordSys3D('C')
            res = field_analysis(C.y*C.i + C.x*C.j, C)
            assert isinstance(res, dict), type(res)
            assert set(res.keys()) == {"divergence", "curl"}, res.keys()
            print("OK")
            """
        )
        self._assert_ok(proc, "vector key set wrong")

    def test_scalar_laplacian_value(self):
        """laplacian of C.x**2+C.y**2+C.z**2 simplifies to exactly 6."""
        proc = self._run_py(
            """
            from sympy import simplify, Integer
            from sympy.vector import CoordSys3D, field_analysis
            C = CoordSys3D('C')
            res = field_analysis(C.x**2 + C.y**2 + C.z**2, C)
            lap = res["laplacian"]
            assert simplify(lap - 6) == 0, lap
            print("OK")
            """
        )
        self._assert_ok(proc, "scalar laplacian wrong")

    def test_scalar_gradient_value(self):
        """gradient equals 2*C.x*C.i + 2*C.y*C.j + 2*C.z*C.k exactly."""
        proc = self._run_py(
            """
            from sympy.vector import CoordSys3D, field_analysis
            C = CoordSys3D('C')
            res = field_analysis(C.x**2 + C.y**2 + C.z**2, C)
            grad = res["gradient"]
            expected = 2*C.x*C.i + 2*C.y*C.j + 2*C.z*C.k
            assert (grad - expected).simplify() == 0*C.i, (grad, expected)
            print("OK")
            """
        )
        self._assert_ok(proc, "scalar gradient wrong")

    def test_constant_scalar_field(self):
        """Constant scalar field -> zero gradient and 0 laplacian.

        A naive implementation that hardcodes the parabola answer fails here.
        """
        proc = self._run_py(
            """
            from sympy import simplify, Integer
            from sympy.vector import CoordSys3D, field_analysis, Vector
            C = CoordSys3D('C')
            res = field_analysis(Integer(5), C)
            assert set(res.keys()) == {"gradient", "laplacian"}, res.keys()
            assert res["gradient"] == Vector.zero, res["gradient"]
            assert simplify(res["laplacian"]) == 0, res["laplacian"]
            print("OK")
            """
        )
        self._assert_ok(proc, "constant scalar field wrong")

    def test_curl_free_vector_field(self):
        """curl of C.y*C.i + C.x*C.j is the zero vector."""
        proc = self._run_py(
            """
            from sympy.vector import CoordSys3D, field_analysis, Vector
            C = CoordSys3D('C')
            res = field_analysis(C.y*C.i + C.x*C.j, C)
            curl = res["curl"]
            assert curl == Vector.zero, curl
            print("OK")
            """
        )
        self._assert_ok(proc, "curl-free case wrong")

    def test_divergence_free_vector_field(self):
        """divergence of C.y*C.i - C.x*C.j simplifies to 0."""
        proc = self._run_py(
            """
            from sympy import simplify
            from sympy.vector import CoordSys3D, field_analysis
            C = CoordSys3D('C')
            res = field_analysis(C.y*C.i - C.x*C.j, C)
            div = res["divergence"]
            assert simplify(div) == 0, div
            print("OK")
            """
        )
        self._assert_ok(proc, "divergence-free case wrong")

    def test_nontrivial_divergence_and_curl(self):
        """Non-trivial field: divergence and curl are computed, not hardcoded.

        For F = C.x*C.y*C.i + C.z*C.j + C.x*C.z*C.k:
          div = C.y + C.x   (d/dx(xy) + d/dy(z) + d/dz(xz))
          curl = -C.i + (-C.z)*C.j ... computed exactly and compared.
        A stub returning 0 for both (as in the divergence/curl-free cases)
        must fail here.
        """
        proc = self._run_py(
            """
            from sympy import simplify
            from sympy.vector import CoordSys3D, field_analysis, Vector
            C = CoordSys3D('C')
            F = C.x*C.y*C.i + C.z*C.j + C.x*C.z*C.k
            res = field_analysis(F, C)
            div = res["divergence"]
            assert simplify(div - (C.x + C.y)) == 0, div
            curl = res["curl"]
            # curl of F: i:(d/dy(xz)-d/dz(z))=-1 ; j:(d/dz(xy)-d/dx(xz))=-z ;
            #            k:(d/dx(z)-d/dy(xy))=-x
            expected = (-1)*C.i + (-C.z)*C.j + (-C.x)*C.k
            assert (curl - expected).simplify() == Vector.zero, (curl, expected)
            assert curl != Vector.zero, "curl collapsed to zero"
            print("OK")
            """
        )
        self._assert_ok(proc, "non-trivial divergence/curl wrong")

    def test_gradient_is_a_vector_and_laplacian_is_scalar(self):
        """Type contract: gradient/curl are Vector; laplacian/divergence are not.

        Guards against a stub that swaps results or returns plain numbers.
        """
        proc = self._run_py(
            """
            from sympy.vector import CoordSys3D, field_analysis, Vector
            C = CoordSys3D('C')
            s = field_analysis(C.x**2 + C.y, C)
            assert isinstance(s["gradient"], Vector), type(s["gradient"])
            assert not isinstance(s["laplacian"], Vector), type(s["laplacian"])
            v = field_analysis(C.x*C.i + C.y*C.j + C.z*C.k, C)
            assert isinstance(v["curl"], Vector), type(v["curl"])
            assert not isinstance(v["divergence"], Vector), type(v["divergence"])
            print("OK")
            """
        )
        self._assert_ok(proc, "result types wrong")

    def test_dispatch_distinguishes_scalar_from_vector(self):
        """Scalar and vector inputs produce DIFFERENT key sets (real dispatch).

        Directly contrasts the two branches so a constant-output stub cannot
        pass both at once.
        """
        proc = self._run_py(
            """
            from sympy.vector import CoordSys3D, field_analysis
            C = CoordSys3D('C')
            scalar_keys = set(field_analysis(C.x*C.y, C).keys())
            vector_keys = set(field_analysis(C.x*C.i, C).keys())
            assert scalar_keys == {"gradient", "laplacian"}, scalar_keys
            assert vector_keys == {"divergence", "curl"}, vector_keys
            assert scalar_keys != vector_keys
            print("OK")
            """
        )
        self._assert_ok(proc, "scalar/vector dispatch not distinct")

    def test_unrecognized_field_raises_typeerror(self):
        """An unrecognized field type raises TypeError (input is validated)."""
        proc = self._run_py(
            """
            from sympy.vector import CoordSys3D, field_analysis
            C = CoordSys3D('C')
            try:
                field_analysis(object(), C)
            except TypeError:
                print("OK")
            else:
                raise AssertionError("expected TypeError for object() field")
            """
        )
        self._assert_ok(proc, "unrecognized field did not raise TypeError")

    def test_native_pytest_suite_passes(self):
        """The deliverable's own pytest file collects and passes (green)."""
        env = dict(os.environ)
        env["PYTHONPATH"] = self.REPO_DIR
        # --noconftest avoids sympy/conftest.py's optional 'hypothesis'
        # dependency, keeping the check scoped to the deliverable file.
        proc = subprocess.run(
            ["python", "-m", "pytest",
             "sympy/vector/tests/test_fieldanalysis.py", "-q",
             "-p", "no:cacheprovider", "--noconftest"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=600,
            env=env,
        )
        assert proc.returncode == 0, (
            "native test_fieldanalysis.py suite failed\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )
        out = proc.stdout + proc.stderr
        assert "passed" in out, out
        assert "no tests ran" not in out, out
