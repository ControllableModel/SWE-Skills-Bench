"""
Test for the 'sympy-symbolic-math' skill (variant ext3).

Task: add a simultaneous-congruence solver to ``sympy.ntheory`` exposing one
public function::

    from sympy.ntheory import solve_congruences

``solve_congruences(congruences)`` takes a list of ``(remainder, modulus)``
integer pairs describing the system ``x == remainder (mod modulus)`` and
returns either:

  * a tuple ``(x0, M)`` with ``0 <= x0 < M``, ``M == lcm(moduli)`` and
    ``x0 % modulus == remainder % modulus`` for every pair, OR
  * ``None`` when the system is contradictory.

Edge cases: non-coprime-but-compatible moduli, contradictions, negative
remainders reduced into ``[0, M)``, empty system -> ``(0, 1)``, and a
non-positive modulus -> ``ValueError``. All outputs MUST be exact integers
(no floats).

Verification strategy
---------------------
Every L2 case runs a fresh python subprocess with ``PYTHONPATH = REPO_DIR`` so
the in-repo sympy is the one under test, IMPORTS the agent's function, and
deep-validates the returned value.  Rather than trusting the agent's own test
file for the behavioral checks we re-derive the contract independently:

  * for every input pair we assert ``x0 % modulus == remainder % modulus``
    (so a stub that ignores some inputs or hardcodes one example fails),
  * we assert ``M`` equals the integer lcm of the moduli computed here,
  * we assert ``0 <= x0 < M`` and that ``x0``/``M`` are exact integers,
  * contradictions must return exactly ``None`` (a stub that always returns a
    tuple fails),
  * a non-positive modulus must raise ``ValueError``.

L1 checks confirm the deliverable files exist and the public import works.
The final L2 check runs the deliverable's own pytest file with the native
acceptance command from the requirement doc.
"""

import os
import subprocess
import textwrap

import pytest


class TestSympySymbolicMath:
    """Verify the sympy.ntheory.solve_congruences utility (ext3 variant)."""

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

    # Shared snippet preamble: an INDEPENDENT verifier of the (x0, M) contract.
    _VERIFY = """
    from math import gcd

    def _lcm(nums):
        out = 1
        for n in nums:
            out = out * n // gcd(out, n)
        return out

    def check_solution(congruences, result):
        # result must be a 2-tuple of integers describing residue class.
        assert isinstance(result, tuple) and len(result) == 2, result
        x0, M = result
        # Exact integers only -- reject floats / Float outright.
        assert int(x0) == x0, ('x0 not integral', x0)
        assert int(M) == M, ('M not integral', M)
        x0i, Mi = int(x0), int(M)
        moduli = [int(m) for (_, m) in congruences]
        assert Mi == _lcm(moduli), ('M != lcm', Mi, _lcm(moduli))
        assert 0 <= x0i < Mi, ('x0 out of range', x0i, Mi)
        for (r, m) in congruences:
            assert x0i % int(m) == int(r) % int(m), (
                'congruence violated', r, m, x0i)
    """

    # ------------------------------------------------------------------
    # L1: deliverables exist
    # ------------------------------------------------------------------

    def test_congruences_module_file_exists(self):
        """sympy/ntheory/congruences.py must be created."""
        fpath = os.path.join(
            self.REPO_DIR, "sympy", "ntheory", "congruences.py"
        )
        assert os.path.isfile(fpath), "sympy/ntheory/congruences.py not found"

    def test_congruences_test_file_exists(self):
        """sympy/ntheory/tests/test_congruences.py must be created."""
        fpath = os.path.join(
            self.REPO_DIR, "sympy", "ntheory", "tests", "test_congruences.py"
        )
        assert os.path.isfile(fpath), "tests/test_congruences.py not found"

    def test_public_import_succeeds(self):
        """solve_congruences must import from the sympy.ntheory package."""
        proc = self._run_py(
            """
            from sympy.ntheory import solve_congruences
            assert callable(solve_congruences)
            print("OK")
            """
        )
        self._assert_ok(proc, "from sympy.ntheory import solve_congruences failed")

    # ------------------------------------------------------------------
    # L2: dynamic behavioral validation (independent oracle)
    # ------------------------------------------------------------------

    def test_classic_crt_coprime(self):
        """solve_congruences([(2,3),(3,5),(2,7)]) -> exactly (23, 105)."""
        proc = self._run_py(
            self._VERIFY
            + """
            from sympy.ntheory import solve_congruences
            sys_ = [(2, 3), (3, 5), (2, 7)]
            res = solve_congruences(sys_)
            check_solution(sys_, res)
            assert (int(res[0]), int(res[1])) == (23, 105), res
            print("OK")
            """
        )
        self._assert_ok(proc, "coprime CRT result wrong")

    def test_noncoprime_compatible(self):
        """Non-coprime but compatible: [(1,4),(3,6)] -> (9, 12)."""
        proc = self._run_py(
            self._VERIFY
            + """
            from sympy.ntheory import solve_congruences
            sys_ = [(1, 4), (3, 6)]
            res = solve_congruences(sys_)
            check_solution(sys_, res)
            assert (int(res[0]), int(res[1])) == (9, 12), res
            print("OK")
            """
        )
        self._assert_ok(proc, "non-coprime compatible result wrong")

    def test_contradiction_returns_none(self):
        """Contradictory system [(0,2),(1,4)] -> exactly None (not a tuple)."""
        proc = self._run_py(
            """
            from sympy.ntheory import solve_congruences
            res = solve_congruences([(0, 2), (1, 4)])
            assert res is None, ("expected None for contradiction, got", res)
            print("OK")
            """
        )
        self._assert_ok(proc, "contradiction did not return None")

    def test_second_contradiction_returns_none(self):
        """A different contradiction [(2,6),(1,4)] also -> None.

        2 mod gcd(6,4)=2 is 0 but 1 mod 2 is 1, so incompatible. Guards
        against a stub that special-cases only the doc's example.
        """
        proc = self._run_py(
            """
            from sympy.ntheory import solve_congruences
            res = solve_congruences([(2, 6), (1, 4)])
            assert res is None, ("expected None, got", res)
            print("OK")
            """
        )
        self._assert_ok(proc, "second contradiction did not return None")

    def test_negative_remainder_reduced(self):
        """Negative remainders reduced into [0,M): [(-1,5)] -> (4, 5)."""
        proc = self._run_py(
            self._VERIFY
            + """
            from sympy.ntheory import solve_congruences
            sys_ = [(-1, 5)]
            res = solve_congruences(sys_)
            check_solution(sys_, res)
            assert (int(res[0]), int(res[1])) == (4, 5), res
            print("OK")
            """
        )
        self._assert_ok(proc, "negative remainder not reduced correctly")

    def test_empty_system(self):
        """Empty list -> exactly (0, 1)."""
        proc = self._run_py(
            """
            from sympy.ntheory import solve_congruences
            res = solve_congruences([])
            assert isinstance(res, tuple) and len(res) == 2, res
            assert (int(res[0]), int(res[1])) == (0, 1), res
            print("OK")
            """
        )
        self._assert_ok(proc, "empty system did not return (0, 1)")

    def test_nonpositive_modulus_raises(self):
        """A zero / non-positive modulus must raise ValueError."""
        proc = self._run_py(
            """
            from sympy.ntheory import solve_congruences
            for bad in ([(1, 0)], [(2, -3)]):
                try:
                    solve_congruences(bad)
                except ValueError:
                    pass
                else:
                    raise AssertionError(
                        "expected ValueError for modulus in %r" % (bad,))
            print("OK")
            """
        )
        self._assert_ok(proc, "non-positive modulus did not raise ValueError")

    def test_single_congruence_normalized(self):
        """Single pair with remainder >= modulus is normalized: [(7,3)] -> (1,3)."""
        proc = self._run_py(
            self._VERIFY
            + """
            from sympy.ntheory import solve_congruences
            sys_ = [(7, 3)]
            res = solve_congruences(sys_)
            check_solution(sys_, res)
            assert (int(res[0]), int(res[1])) == (1, 3), res
            print("OK")
            """
        )
        self._assert_ok(proc, "single congruence not normalized")

    def test_exact_integer_no_float(self):
        """Outputs must be exact integers; no float/Float atoms anywhere."""
        proc = self._run_py(
            """
            from sympy import Float, sympify
            from sympy.ntheory import solve_congruences
            res = solve_congruences([(2, 3), (3, 5), (2, 7)])
            x0, M = res
            # Reject python floats outright.
            assert not isinstance(x0, float) and not isinstance(M, float), res
            # And reject SymPy Float atoms if these are sympy Integers.
            for v in (sympify(x0), sympify(M)):
                assert not v.atoms(Float), ("float atom in", v)
                assert v.is_integer, ("not integer", v)
            print("OK")
            """
        )
        self._assert_ok(proc, "outputs are not exact integers")

    def test_cross_check_against_brute_force(self):
        """Result matches an independent brute-force search over [0, lcm).

        This is the strongest discriminator: a stub returning a fixed/partial
        answer cannot match the unique brute-force solution for an arbitrary
        non-trivial three-congruence system.
        """
        proc = self._run_py(
            self._VERIFY
            + """
            from sympy.ntheory import solve_congruences
            sys_ = [(4, 6), (7, 10), (3, 15)]
            res = solve_congruences(sys_)
            # Brute-force the unique smallest solution over the lcm period.
            M = _lcm([m for (_, m) in sys_])
            brute = None
            for cand in range(M):
                if all(cand % m == r % m for (r, m) in sys_):
                    brute = cand
                    break
            assert brute is not None, "test system was unsolvable -- fix test"
            check_solution(sys_, res)
            assert int(res[0]) == brute, (res, brute)
            assert int(res[1]) == M, (res, M)
            print("OK")
            """
        )
        self._assert_ok(proc, "result disagrees with brute-force oracle")

    def test_brute_force_detects_no_solution(self):
        """A system with no brute-force solution must return None.

        [(1,9),(2,12)] : gcd(9,12)=3; 1 mod 3 = 1, 2 mod 3 = 2 -> incompatible.
        """
        proc = self._run_py(
            self._VERIFY
            + """
            from sympy.ntheory import solve_congruences
            sys_ = [(1, 9), (2, 12)]
            M = _lcm([m for (_, m) in sys_])
            brute = [c for c in range(M)
                     if all(c % m == r % m for (r, m) in sys_)]
            assert brute == [], "test system unexpectedly solvable -- fix test"
            res = solve_congruences(sys_)
            assert res is None, ("expected None, got", res)
            print("OK")
            """
        )
        self._assert_ok(proc, "unsolvable system did not return None")

    # ------------------------------------------------------------------
    # L2: the deliverable's own native pytest suite (acceptance command)
    # ------------------------------------------------------------------

    def test_native_pytest_suite_passes(self):
        """The deliverable's own pytest file collects and passes (green).

        Drives the native acceptance command from the requirement doc:
            python -m pytest sympy/ntheory/tests/test_congruences.py -q
        """
        env = dict(os.environ)
        env["PYTHONPATH"] = self.REPO_DIR
        # --noconftest avoids sympy/conftest.py's optional 'hypothesis'
        # dependency, keeping the check scoped to the deliverable file.
        proc = subprocess.run(
            ["python", "-m", "pytest",
             "sympy/ntheory/tests/test_congruences.py", "-q",
             "-p", "no:cacheprovider", "--noconftest"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=600,
            env=env,
        )
        assert proc.returncode == 0, (
            "native test_congruences.py suite failed\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )
        out = proc.stdout + proc.stderr
        assert "passed" in out, out
        assert "no tests ran" not in out, out
