"""
Test for the 'scipy-scientific-computing' skill (variant ext9).

Verifies the agent added a radius-neighbour local-density estimator to
``scipy/spatial`` as a new private module ``scipy/spatial/_localdensity.py``
exposing::

    local_density(points, *, k=5, radius=None)

The function returns a dict with exactly the keys ``"density"``,
``"knn_distance"`` and ``"outliers"`` (see tasks/ext9 requirement doc).

These tests do NOT trust the agent's own test file or string-match the source.
Instead they exercise the real ``local_density`` function inside the built
SciPy by running each scenario in a fresh ``python`` subprocess with
cwd=REPO_DIR (the same environment the acceptance command uses) and
deep-validate the numeric / structural contract:

  * a tight uniform cluster -> roughly constant density, no outliers;
  * cluster points have higher ``"density"`` and smaller ``"knn_distance"``
    than a far-away isolated point;
  * a single injected far point is the SOLE entry of ``"outliers"`` (by index);
  * ``"density"`` and ``"knn_distance"`` are invariant under a rigid global
    translation of all points;
  * radius-mode on a known integer grid yields a neighbour count of exactly 4
    for interior points;
  * ``"knn_distance"`` matches an independent brute-force recomputation;
  * the caller's ``points`` array is not mutated;
  * each invalid-input case raises ``ValueError``.

A naive implementation (constant density, never flagging outliers, ignoring
``radius``, or breaking under translation) fails these tests.
"""

import json
import os
import subprocess
import textwrap


REPO_DIR = "/workspace/scipy"

# Common preamble used by every driver subprocess. It loads ``local_density``
# preferring the official package import path required by the task, and falling
# back to loading the source file directly (its own ``from scipy.spatial ...``
# imports still resolve through the installed SciPy) so the behavioural tests
# can run even if the editable rebuild has not re-registered the module under
# the package namespace yet.
_LOADER = r"""
import json, sys, importlib.util, os
import numpy as np

REPO_DIR = %r

def _load_local_density():
    try:
        from scipy.spatial._localdensity import local_density as ld
        return ld
    except Exception:
        pass
    src = os.path.join(REPO_DIR, "scipy", "spatial", "_localdensity.py")
    spec = importlib.util.spec_from_file_location("_localdensity_under_test", src)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.local_density

local_density = _load_local_density()
""" % REPO_DIR


def _run_driver(body, timeout=300):
    """Run ``_LOADER + body`` as a python subprocess in REPO_DIR.

    ``body`` is expected to ``print(json.dumps(...))`` its result on the final
    line. Returns the parsed JSON object. Raises AssertionError with captured
    output on failure.
    """
    script = _LOADER + "\n" + textwrap.dedent(body)
    proc = subprocess.run(
        ["python", "-c", script],
        cwd=REPO_DIR,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    assert proc.returncode == 0, (
        "driver subprocess failed (rc=%d)\n--- STDOUT ---\n%s\n--- STDERR ---\n%s"
        % (proc.returncode, proc.stdout, proc.stderr)
    )
    lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
    assert lines, "driver produced no stdout\nSTDERR:\n%s" % proc.stderr
    try:
        return json.loads(lines[-1])
    except json.JSONDecodeError as exc:
        raise AssertionError(
            "could not parse driver JSON output: %s\nLAST LINE: %r\nFULL STDOUT:\n%s"
            % (exc, lines[-1], proc.stdout)
        )


class TestScipyScientificComputing:
    """Validate the local_density radius-neighbour density estimator."""

    REPO_DIR = REPO_DIR

    # ------------------------------------------------------------------
    # L1 — deliverable files exist and are minimally well-formed
    # ------------------------------------------------------------------

    def test_module_file_exists(self):
        """scipy/spatial/_localdensity.py must exist."""
        fpath = os.path.join(self.REPO_DIR, "scipy", "spatial", "_localdensity.py")
        assert os.path.isfile(fpath), "_localdensity.py not found at %s" % fpath

    def test_test_file_exists(self):
        """scipy/spatial/tests/test_localdensity.py must exist."""
        fpath = os.path.join(
            self.REPO_DIR, "scipy", "spatial", "tests", "test_localdensity.py"
        )
        assert os.path.isfile(fpath), "test_localdensity.py not found at %s" % fpath

    def test_meson_registers_module(self):
        """scipy/spatial/meson.build must list _localdensity.py for installation."""
        fpath = os.path.join(self.REPO_DIR, "scipy", "spatial", "meson.build")
        assert os.path.isfile(fpath), "spatial meson.build missing"
        with open(fpath) as f:
            content = f.read()
        assert "_localdensity.py" in content, (
            "_localdensity.py was not added to scipy/spatial/meson.build "
            "install_sources"
        )

    def test_meson_registers_test(self):
        """scipy/spatial/tests/meson.build must list test_localdensity.py."""
        fpath = os.path.join(
            self.REPO_DIR, "scipy", "spatial", "tests", "meson.build"
        )
        assert os.path.isfile(fpath), "tests meson.build missing"
        with open(fpath) as f:
            content = f.read()
        assert "test_localdensity.py" in content, (
            "test_localdensity.py was not added to tests/meson.build "
            "install_sources"
        )

    def test_function_importable_and_keys(self):
        """local_density must be importable and return a dict with the 3 keys."""
        res = _run_driver(
            r"""
            import numpy as np
            rng = np.arange(20).reshape(-1, 1) * 1.0
            pts = np.column_stack([rng, np.zeros_like(rng)])
            out = local_density(pts, k=3)
            assert isinstance(out, dict), "return value must be a dict"
            print(json.dumps(sorted(out.keys())))
            """
        )
        assert res == ["density", "knn_distance", "outliers"], (
            "local_density must return exactly keys "
            "{'density','knn_distance','outliers'}, got %r" % res
        )

    def test_output_shapes_and_dtypes(self):
        """density & knn_distance are length-n float 1-D; outliers is int 1-D."""
        res = _run_driver(
            r"""
            import numpy as np
            rng = np.random.RandomState(0)
            pts = rng.rand(30, 2)
            out = local_density(pts, k=4)
            dens = np.asarray(out["density"])
            knn = np.asarray(out["knn_distance"])
            outl = np.asarray(out["outliers"])
            print(json.dumps({
                "n_dens": int(dens.size), "ndim_dens": int(dens.ndim),
                "n_knn": int(knn.size), "ndim_knn": int(knn.ndim),
                "ndim_outl": int(outl.ndim),
                "dens_float": bool(np.issubdtype(dens.dtype, np.floating)),
                "knn_float": bool(np.issubdtype(knn.dtype, np.floating)),
                "outl_int": bool(np.issubdtype(outl.dtype, np.integer)),
            }))
            """
        )
        assert res["n_dens"] == 30 and res["ndim_dens"] == 1, (
            "'density' must be a 1-D length-n array, got %r" % res
        )
        assert res["n_knn"] == 30 and res["ndim_knn"] == 1, (
            "'knn_distance' must be a 1-D length-n array, got %r" % res
        )
        assert res["ndim_outl"] == 1, "'outliers' must be 1-D"
        assert res["dens_float"], "'density' must be a float array"
        assert res["knn_float"], "'knn_distance' must be a float array"
        assert res["outl_int"], "'outliers' must be an integer-index array"

    # ------------------------------------------------------------------
    # L2 — dynamic execution / deep behavioural validation
    # ------------------------------------------------------------------

    def test_uniform_cluster_constant_density_no_outliers(self):
        """A uniform tight grid cluster -> ~constant density, no outliers."""
        res = _run_driver(
            r"""
            import numpy as np
            # 7x7 regular grid, unit spacing -> interior density near-constant.
            g = np.arange(7) * 1.0
            xx, yy = np.meshgrid(g, g)
            pts = np.column_stack([xx.ravel(), yy.ravel()])
            out = local_density(pts, k=4)
            dens = np.asarray(out["density"], float)
            outl = list(np.asarray(out["outliers"]).astype(int))
            # coefficient of variation of density over all points
            cv = float(np.std(dens) / np.mean(dens))
            print(json.dumps({"cv": cv, "n_outliers": len(outl)}))
            """
        )
        # No point is far from any cluster -> no statistical outliers.
        assert res["n_outliers"] == 0, (
            "a uniform cluster must have no outliers, got %r" % res["n_outliers"]
        )
        # Density should not vary wildly (a constant-returning stub also passes
        # *this* loose bound, but fails the discriminative tests below).
        assert res["cv"] < 0.5, (
            "uniform-cluster density should be roughly constant, cv=%r" % res["cv"]
        )

    def test_cluster_denser_than_isolated_point(self):
        """Cluster members have higher density / smaller knn_distance than a far point."""
        res = _run_driver(
            r"""
            import numpy as np
            rng = np.random.RandomState(1)
            cluster = rng.rand(40, 2) * 0.1          # tight cluster near origin
            far = np.array([[100.0, 100.0]])         # isolated far point
            pts = np.vstack([cluster, far])
            out = local_density(pts, k=5)
            dens = np.asarray(out["density"], float)
            knn = np.asarray(out["knn_distance"], float)
            far_idx = pts.shape[0] - 1
            cluster_dens = dens[:far_idx]
            cluster_knn = knn[:far_idx]
            print(json.dumps({
                "far_dens": float(dens[far_idx]),
                "min_cluster_dens": float(cluster_dens.min()),
                "far_knn": float(knn[far_idx]),
                "max_cluster_knn": float(cluster_knn.max()),
            }))
            """
        )
        # The far point must be the LEAST dense and have the LARGEST knn distance.
        assert res["far_dens"] < res["min_cluster_dens"], (
            "isolated point density (%r) must be below every cluster point (%r); "
            "a constant-density stub fails here"
            % (res["far_dens"], res["min_cluster_dens"])
        )
        assert res["far_knn"] > res["max_cluster_knn"], (
            "isolated point knn_distance (%r) must exceed every cluster point (%r)"
            % (res["far_knn"], res["max_cluster_knn"])
        )

    def test_injected_far_point_is_sole_outlier(self):
        """One tight cluster + one far point -> outliers == [that index] exactly."""
        res = _run_driver(
            r"""
            import numpy as np
            rng = np.random.RandomState(2)
            cluster = rng.rand(60, 2) * 0.05
            far = np.array([[50.0, -50.0]])
            pts = np.vstack([cluster, far])
            far_idx = pts.shape[0] - 1
            out = local_density(pts, k=5)
            outl = [int(v) for v in np.asarray(out["outliers"]).astype(int)]
            print(json.dumps({"outliers": outl, "far_idx": far_idx}))
            """
        )
        assert res["outliers"] == [res["far_idx"]], (
            "outliers must be exactly [%r] (the injected far point), got %r; "
            "a stub that flags nothing (or everything) fails here"
            % (res["far_idx"], res["outliers"])
        )

    def test_outliers_indices_ascending(self):
        """outliers indices are returned in ascending order."""
        res = _run_driver(
            r"""
            import numpy as np
            rng = np.random.RandomState(3)
            cluster = rng.rand(50, 2) * 0.05
            # two far points injected at non-adjacent positions
            far = np.array([[30.0, 30.0], [-40.0, 10.0]])
            pts = np.vstack([cluster[:20], far[:1], cluster[20:], far[1:]])
            out = local_density(pts, k=5)
            outl = [int(v) for v in np.asarray(out["outliers"]).astype(int)]
            print(json.dumps({"outliers": outl}))
            """
        )
        outl = res["outliers"]
        assert outl == sorted(outl), (
            "outlier indices must be ascending, got %r" % outl
        )
        # Both far points must be detected (and nothing from the tight cluster).
        assert len(outl) == 2, (
            "expected exactly the 2 injected far points as outliers, got %r" % outl
        )

    def test_translation_invariance(self):
        """density and knn_distance are unchanged under a rigid global shift."""
        res = _run_driver(
            r"""
            import numpy as np
            rng = np.random.RandomState(4)
            pts = rng.rand(40, 3) * 2.0
            shift = np.array([1000.0, -250.0, 42.0])
            out0 = local_density(pts, k=5)
            out1 = local_density(pts + shift, k=5)
            d0 = np.asarray(out0["density"], float)
            d1 = np.asarray(out1["density"], float)
            k0 = np.asarray(out0["knn_distance"], float)
            k1 = np.asarray(out1["knn_distance"], float)
            print(json.dumps({
                "max_dens_diff": float(np.max(np.abs(d0 - d1))),
                "max_knn_diff": float(np.max(np.abs(k0 - k1))),
            }))
            """
        )
        assert res["max_dens_diff"] < 1e-8, (
            "density must be translation-invariant; max diff=%r "
            "(an impl that uses absolute coordinates fails)" % res["max_dens_diff"]
        )
        assert res["max_knn_diff"] < 1e-8, (
            "knn_distance must be translation-invariant; max diff=%r"
            % res["max_knn_diff"]
        )

    def test_knn_distance_matches_bruteforce(self):
        """knn_distance equals an independent brute-force k-th nearest distance."""
        res = _run_driver(
            r"""
            import numpy as np
            rng = np.random.RandomState(5)
            pts = rng.rand(35, 2) * 5.0
            k = 4
            out = local_density(pts, k=k)
            knn = np.asarray(out["knn_distance"], float)

            # Independent O(n^2) recomputation (NOT using a KDTree).
            n = pts.shape[0]
            ref = np.empty(n)
            for i in range(n):
                d = np.sqrt(((pts - pts[i]) ** 2).sum(axis=1))
                d_sorted = np.sort(d)        # d_sorted[0] == 0 (self)
                ref[i] = d_sorted[k]          # k-th neighbour excluding self
            max_diff = float(np.max(np.abs(knn - ref)))
            print(json.dumps({"max_diff": max_diff}))
            """
        )
        assert res["max_diff"] < 1e-9, (
            "knn_distance must equal the true distance to the k-th nearest "
            "neighbour (self excluded); max diff vs brute force=%r" % res["max_diff"]
        )

    def test_kmode_density_is_k_over_mean_distance(self):
        """k-mode density == k / mean(distance to the k nearest neighbours)."""
        res = _run_driver(
            r"""
            import numpy as np
            rng = np.random.RandomState(6)
            pts = rng.rand(30, 2) * 3.0
            k = 5
            out = local_density(pts, k=k)
            dens = np.asarray(out["density"], float)

            n = pts.shape[0]
            ref = np.empty(n)
            for i in range(n):
                d = np.sqrt(((pts - pts[i]) ** 2).sum(axis=1))
                d_sorted = np.sort(d)
                nn = d_sorted[1:k+1]           # k nearest, excluding self
                ref[i] = k / nn.mean()
            max_rel = float(np.max(np.abs(dens - ref) / np.abs(ref)))
            print(json.dumps({"max_rel": max_rel}))
            """
        )
        assert res["max_rel"] < 1e-6, (
            "k-mode density must equal k / mean(k nearest distances); "
            "max relative error vs independent recomputation=%r" % res["max_rel"]
        )

    def test_radius_mode_grid_interior_count_is_four(self):
        """Radius-mode on an integer grid: interior points report density count 4."""
        res = _run_driver(
            r"""
            import numpy as np
            # 5x5 unit-spacing grid. radius=1.1 captures only the 4 orthogonal
            # neighbours (distance 1) but not diagonals (distance sqrt(2)~1.414).
            g = np.arange(5) * 1.0
            xx, yy = np.meshgrid(g, g)
            pts = np.column_stack([xx.ravel(), yy.ravel()])
            out = local_density(pts, k=3, radius=1.1)
            dens = np.asarray(out["density"], float)
            # interior point (2,2) is at index 2*5 + 2 = 12
            interior = float(dens[12])
            # a corner, e.g. (0,0) at index 0, has only 2 orthogonal neighbours
            corner = float(dens[0])
            print(json.dumps({"interior": interior, "corner": corner}))
            """
        )
        assert abs(res["interior"] - 4.0) < 1e-9, (
            "radius-mode interior grid point must count exactly 4 neighbours "
            "within radius 1.1, got %r (an impl that ignores radius and returns "
            "a k-distance estimate fails here)" % res["interior"]
        )
        assert abs(res["corner"] - 2.0) < 1e-9, (
            "radius-mode corner grid point must count exactly 2 neighbours, got %r"
            % res["corner"]
        )

    def test_radius_mode_still_reports_knn_distance(self):
        """In radius-mode knn_distance is still computed (the k-th NN distance)."""
        res = _run_driver(
            r"""
            import numpy as np
            g = np.arange(5) * 1.0
            xx, yy = np.meshgrid(g, g)
            pts = np.column_stack([xx.ravel(), yy.ravel()])
            k = 4
            out = local_density(pts, k=k, radius=1.1)
            knn = np.asarray(out["knn_distance"], float)
            # independent k-th nearest distance for the interior point index 12
            i = 12
            d = np.sqrt(((pts - pts[i]) ** 2).sum(axis=1))
            ref = float(np.sort(d)[k])
            print(json.dumps({"got": float(knn[i]), "ref": ref, "size": int(knn.size)}))
            """
        )
        assert res["size"] == 25, "knn_distance must have one entry per point"
        assert abs(res["got"] - res["ref"]) < 1e-9, (
            "knn_distance must be computed even in radius-mode; got %r expected %r"
            % (res["got"], res["ref"])
        )

    def test_input_not_mutated(self):
        """local_density must not mutate the caller's points array."""
        res = _run_driver(
            r"""
            import numpy as np
            rng = np.random.RandomState(7)
            pts = rng.rand(25, 2) * 4.0
            before = pts.copy()
            _ = local_density(pts, k=5)
            _ = local_density(pts, k=3, radius=0.5)
            unchanged = bool(np.array_equal(pts, before))
            print(json.dumps({"unchanged": unchanged}))
            """
        )
        assert res["unchanged"] is True, (
            "local_density must not mutate its input points array"
        )

    def test_invalid_inputs_raise_value_error(self):
        """Each invalid-input case must raise ValueError."""
        res = _run_driver(
            r"""
            import numpy as np
            rng = np.random.RandomState(8)
            good = rng.rand(20, 2)

            def raises_value_error(fn):
                try:
                    fn()
                except ValueError:
                    return True
                except Exception:
                    return False
                return False

            results = {}
            # points not 2-D
            results["pts_1d"] = raises_value_error(
                lambda: local_density(np.arange(10.0), k=3))
            results["pts_3d"] = raises_value_error(
                lambda: local_density(np.ones((4, 4, 2)), k=3))
            # fewer than k+1 points
            results["too_few"] = raises_value_error(
                lambda: local_density(good[:5], k=5))
            # k < 1
            results["k_zero"] = raises_value_error(
                lambda: local_density(good, k=0))
            results["k_neg"] = raises_value_error(
                lambda: local_density(good, k=-2))
            # radius <= 0
            results["radius_zero"] = raises_value_error(
                lambda: local_density(good, k=3, radius=0.0))
            results["radius_neg"] = raises_value_error(
                lambda: local_density(good, k=3, radius=-1.0))
            print(json.dumps(results))
            """
        )
        for case, ok in res.items():
            assert ok is True, (
                "invalid-input case %r did not raise ValueError" % case
            )

    def test_acceptance_pytest_command(self):
        """The agent's own test file passes via the acceptance command."""
        proc = subprocess.run(
            ["python", "-m", "pytest",
             "scipy/spatial/tests/test_localdensity.py", "-v", "--tb=short"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=600,
        )
        assert proc.returncode == 0, (
            "acceptance command failed\n--- STDOUT ---\n%s\n--- STDERR ---\n%s"
            % (proc.stdout[-4000:], proc.stderr[-2000:])
        )
