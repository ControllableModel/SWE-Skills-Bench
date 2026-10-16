"""
Test for the 'sympy-symbolic-math' skill (variant ext4).

Task: add an analytic-geometry tangent-line utility to ``sympy.geometry``
exposing a single public function::

    from sympy.geometry import tangent_data

``tangent_data(circle, point)`` takes a ``Circle`` and an external 2D
``Point`` and returns a plain ``dict`` with EXACTLY these keys:

  * "distance"        -- exact distance from point to the circle center
  * "tangent_length"  -- exact length of either tangent segment, derived
                          from sqrt(distance**2 - radius**2)
  * "num_tangents"    -- 2 (outside), 1 (on circle), 0 (inside)

This suite verifies the deliverable by IMPORTING and EXERCISING the agent's
implementation inside the repo (PYTHONPATH = REPO_DIR so the in-repo sympy is
the one under test) and deep-validating the symbolic results:

  * exact symbolic distance / tangent_length (sqrt(3), never 1.732...),
  * the exact relation tangent_length == sqrt(distance**2 - radius**2),
  * correct num_tangents for outside / on / inside cases,
  * on-circle tangent_length simplifies to 0,
  * inside case: num_tangents == 0 and tangent_length**2 is negative,
  * symbolic center/radius/point support,
  * TypeError when the first argument is not a Circle,
  * the dict has EXACTLY the three documented keys.

A naive/stub implementation (hardcoding num_tangents, returning floats, or
omitting keys) MUST fail these assertions.

L1 checks confirm the deliverable files exist and the import works.
L2 checks run real symbolic computations and assert deep equality, then run
the deliverable's own pytest file with the native acceptance command.
"""

import os
import subprocess
import textwrap

import pytest


class TestSympySymbolicMath:
    """Verify the tangent_data analytic-geometry utility."""

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

    def test_tangents_module_file_exists(self):
        """sympy/geometry/tangents.py must be created."""
        fpath = os.path.join(
            self.REPO_DIR, "sympy", "geometry", "tangents.py"
        )
        assert os.path.isfile(fpath), "sympy/geometry/tangents.py not found"

    def test_tangents_test_file_exists(self):
        """sympy/geometry/tests/test_tangents.py must be created."""
        fpath = os.path.join(
            self.REPO_DIR, "sympy", "geometry", "tests", "test_tangents.py"
        )
        assert os.path.isfile(fpath), "tests/test_tangents.py not found"

    def test_public_import_succeeds(self):
        """tangent_data must import from the sympy.geometry package."""
        proc = self._run_py(
            """
            from sympy.geometry import tangent_data
            assert callable(tangent_data)
            print("OK")
            """
        )
        self._assert_ok(proc, "from sympy.geometry import tangent_data failed")

    # ------------------------------------------------------------------
    # L2: dynamic symbolic validation
    # ------------------------------------------------------------------

    def test_return_is_dict_with_exact_keys(self):
        """Return is a dict with EXACTLY the three documented string keys."""
        proc = self._run_py(
            """
            from sympy.geometry import tangent_data, Circle, Point
            res = tangent_data(Circle(Point(0, 0), 1), Point(2, 0))
            assert isinstance(res, dict), type(res)
            assert set(res.keys()) == {"distance", "tangent_length", "num_tangents"}, res.keys()
            print("OK")
            """
        )
        self._assert_ok(proc, "result is not a dict with exactly 3 keys")

    def test_outside_unit_circle_exact_values(self):
        """Unit circle + (2,0): distance==2, tangent_length==sqrt(3) exact, n==2."""
        proc = self._run_py(
            """
            from sympy import sqrt, simplify, Float, Integer
            from sympy.geometry import tangent_data, Circle, Point
            res = tangent_data(Circle(Point(0, 0), 1), Point(2, 0))
            # exact distance
            assert simplify(res["distance"] - 2) == 0, res["distance"]
            # exact tangent length, NOT a float approximation
            tl = res["tangent_length"]
            assert simplify(tl - sqrt(3)) == 0, tl
            assert not tl.atoms(Float), "float introduced: %r" % tl
            # number of tangents from a strictly outside point
            assert res["num_tangents"] == 2, res["num_tangents"]
            print("OK")
            """
        )
        self._assert_ok(proc, "outside unit-circle exact values wrong")

    def test_tangent_length_matches_pythagorean_relation(self):
        """tangent_length must equal sqrt(distance**2 - radius**2) exactly."""
        proc = self._run_py(
            """
            from sympy import sqrt, simplify, Rational
            from sympy.geometry import tangent_data, Circle, Point
            # radius 5/2, external point (7, 0); distance 7
            c = Circle(Point(0, 0), Rational(5, 2))
            res = tangent_data(c, Point(7, 0))
            dist = res["distance"]
            assert simplify(dist - 7) == 0, dist
            expected_tl = sqrt(dist**2 - c.radius**2)
            assert simplify(res["tangent_length"] - expected_tl) == 0, (
                res["tangent_length"], expected_tl)
            print("OK")
            """
        )
        self._assert_ok(proc, "tangent_length does not match sqrt(d^2 - r^2)")

    def test_offaxis_external_point(self):
        """Off-axis external point: distance 5, radius 3 -> tangent_length 4."""
        proc = self._run_py(
            """
            from sympy import simplify
            from sympy.geometry import tangent_data, Circle, Point
            # point (3,4) is distance 5 from origin; radius 3 -> tl = 4
            res = tangent_data(Circle(Point(0, 0), 3), Point(3, 4))
            assert simplify(res["distance"] - 5) == 0, res["distance"]
            assert simplify(res["tangent_length"] - 4) == 0, res["tangent_length"]
            assert res["num_tangents"] == 2, res["num_tangents"]
            print("OK")
            """
        )
        self._assert_ok(proc, "off-axis external point wrong")

    def test_point_on_circle_single_tangent(self):
        """Point exactly on circle: num_tangents==1, tangent_length simplifies to 0."""
        proc = self._run_py(
            """
            from sympy import simplify
            from sympy.geometry import tangent_data, Circle, Point
            # (3,4) lies on the radius-5 circle centered at origin
            res = tangent_data(Circle(Point(0, 0), 5), Point(3, 4))
            assert res["num_tangents"] == 1, res["num_tangents"]
            assert simplify(res["tangent_length"]) == 0, res["tangent_length"]
            assert simplify(res["distance"] - 5) == 0, res["distance"]
            print("OK")
            """
        )
        self._assert_ok(proc, "point-on-circle case wrong")

    def test_point_inside_circle_zero_tangents(self):
        """Point strictly inside: num_tangents==0 and tangent_length**2 is negative."""
        proc = self._run_py(
            """
            from sympy import simplify, sqrt
            from sympy.geometry import tangent_data, Circle, Point
            res = tangent_data(Circle(Point(0, 0), 10), Point(1, 1))
            assert res["num_tangents"] == 0, res["num_tangents"]
            # distance = sqrt(2); tangent_length**2 = 2 - 100 = -98 < 0
            tl = res["tangent_length"]
            sq = simplify(tl**2)
            assert sq == -98, sq
            assert simplify(res["distance"] - sqrt(2)) == 0, res["distance"]
            print("OK")
            """
        )
        self._assert_ok(proc, "inside-circle case wrong")

    def test_num_tangents_is_genuine_not_hardcoded(self):
        """Across outside/on/inside, num_tangents distinguishes 2/1/0 (not hardcoded)."""
        proc = self._run_py(
            """
            from sympy.geometry import tangent_data, Circle, Point
            c = Circle(Point(0, 0), 5)
            outside = tangent_data(c, Point(10, 0))["num_tangents"]
            on = tangent_data(c, Point(5, 0))["num_tangents"]
            inside = tangent_data(c, Point(1, 0))["num_tangents"]
            assert (outside, on, inside) == (2, 1, 0), (outside, on, inside)
            print("OK")
            """
        )
        self._assert_ok(proc, "num_tangents is hardcoded / not discriminative")

    def test_offset_center(self):
        """Circle not at origin: distance/tangent computed from the actual center."""
        proc = self._run_py(
            """
            from sympy import simplify
            from sympy.geometry import tangent_data, Circle, Point
            # center (1,2), radius 3; point (1,7) -> distance 5 -> tl = 4
            c = Circle(Point(1, 2), 3)
            res = tangent_data(c, Point(1, 7))
            assert simplify(res["distance"] - 5) == 0, res["distance"]
            assert simplify(res["tangent_length"] - 4) == 0, res["tangent_length"]
            assert res["num_tangents"] == 2, res["num_tangents"]
            print("OK")
            """
        )
        self._assert_ok(proc, "offset-center case wrong (center ignored?)")

    def test_symbolic_radius_and_point(self):
        """Symbolic radius/coordinates flow into the returned expressions."""
        proc = self._run_py(
            """
            from sympy import symbols, sqrt, simplify
            from sympy.geometry import tangent_data, Circle, Point
            r, a = symbols('r a', positive=True)
            c = Circle(Point(0, 0), r)
            res = tangent_data(c, Point(a, 0))
            # distance from origin to (a,0) is |a|; a positive -> a
            assert simplify(res["distance"] - a) == 0, res["distance"]
            # tangent_length == sqrt(a**2 - r**2)
            assert simplify(res["tangent_length"] - sqrt(a**2 - r**2)) == 0, res["tangent_length"]
            assert res["tangent_length"].has(r), res["tangent_length"]
            assert res["tangent_length"].has(a), res["tangent_length"]
            print("OK")
            """
        )
        self._assert_ok(proc, "symbolic radius/point case wrong")

    def test_non_circle_first_arg_raises_typeerror(self):
        """A non-Circle first argument must raise TypeError."""
        proc = self._run_py(
            """
            from sympy.geometry import tangent_data, Point
            try:
                tangent_data(Point(0, 0), Point(1, 1))
            except TypeError:
                print("OK")
            else:
                raise AssertionError("expected TypeError for non-Circle first arg")
            """
        )
        self._assert_ok(proc, "non-Circle first arg did not raise TypeError")

    def test_no_float_pollution_on_rational_inputs(self):
        """With exact (rational) inputs the results carry no floating-point atoms."""
        proc = self._run_py(
            """
            from sympy import Float
            from sympy.geometry import tangent_data, Circle, Point
            res = tangent_data(Circle(Point(0, 0), 1), Point(2, 0))
            for key in ("distance", "tangent_length"):
                val = res[key]
                assert not val.atoms(Float), "%s has a float: %r" % (key, val)
            print("OK")
            """
        )
        self._assert_ok(proc, "exact inputs produced floating-point results")

    def test_native_pytest_suite_passes(self):
        """The deliverable's own pytest file collects and passes (green).

        Native acceptance command:
            python -m pytest sympy/geometry/tests/test_tangents.py -q
        """
        env = dict(os.environ)
        env["PYTHONPATH"] = self.REPO_DIR
        # --noconftest avoids sympy/conftest.py's optional 'hypothesis'
        # dependency, keeping the check scoped to the deliverable file.
        proc = subprocess.run(
            ["python", "-m", "pytest",
             "sympy/geometry/tests/test_tangents.py", "-q",
             "-p", "no:cacheprovider", "--noconftest"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=600,
            env=env,
        )
        assert proc.returncode == 0, (
            "native test_tangents.py suite failed\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )
        # Ensure at least some tests actually ran (no empty/no-op collection).
        out = proc.stdout + proc.stderr
        assert "passed" in out, out
        assert "no tests ran" not in out, out
