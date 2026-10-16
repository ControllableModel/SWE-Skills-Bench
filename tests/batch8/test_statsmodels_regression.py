"""Tests for the ``statsmodels-regression`` skill (variant ext8).

Variant task: build a *multicollinearity diagnostics helper*. The deliverable is
a new module ``statsmodels/stats/collinearity.py`` exposing

    def collinearity_report(exog, add_intercept=True, vif_threshold=10.0): ...

which takes a design matrix (array-like ``(n, k)`` or a 1-D ``(n,)`` column) and
returns a plain ``dict`` with the keys ``"vif"`` (1-D ndarray of variance
inflation factors, one per non-intercept predictor, in original column order),
``"max_vif"`` (float), ``"high_vif_columns"`` (list of 0-based int indices whose
VIF exceeds ``vif_threshold``), ``"condition_number"`` (float), and
``"multicollinear"`` (bool == max_vif > vif_threshold). A second deliverable
``statsmodels/stats/tests/test_collinearity.py`` holds the agent's own unit
tests, run via ``pytest statsmodels/stats/tests/test_collinearity.py -q``.

Verification strategy
---------------------
Every reported quantity is independently re-derived from statsmodels' OWN
machinery and compared to floating-point tolerance, so naive/hardcoded
implementations cannot pass:

* ``"vif"`` is checked against ``statsmodels.stats.outliers_influence.
  variance_inflation_factor`` evaluated on the intercept-augmented design, one
  call per supplied (non-intercept) column. A stub returning fixed values, the
  wrong column order, or ignoring the intercept-augmentation diverges.
* ``"condition_number"`` is checked against
  ``sm.OLS(...).fit().condition_number`` for the same (augmented when requested)
  design.
* ``"high_vif_columns"`` / ``"multicollinear"`` are checked for internal
  consistency with ``"vif"`` and ``vif_threshold`` AND against constructed
  orthogonal vs near-collinear designs (sign discrimination).

L1 cases check the deliverable exists and the function is importable with the
right signature, returning the documented keys/types. L2 cases run the agent's
function inside a subprocess that emits JSON (robust to PYTHONPATH being cleared
and to import-time side effects) and compare against an independent statsmodels
computation done in the same subprocess.
"""

import json
import os
import subprocess
import sys
import textwrap

import pytest

REPO_DIR = "/workspace/statsmodels"


# Bootstrap that imports the agent's module from REPO_DIR plus a reference
# statsmodels implementation. Each driver script below prepends this so it can
# run from anywhere with PYTHONPATH cleared.
_BOOTSTRAP = textwrap.dedent(
    """
    import sys, os, json
    REPO_DIR = {repo!r}
    sys.path.insert(0, REPO_DIR)
    import numpy as np
    import statsmodels.api as sm
    from statsmodels.stats.outliers_influence import variance_inflation_factor
    from statsmodels.stats.collinearity import collinearity_report
    """
).format(repo=REPO_DIR)


def _run_driver(body, timeout=300):
    """Execute *body* (which must print a single JSON object) in a fresh
    interpreter rooted at REPO_DIR. Returns the parsed JSON dict."""
    script = _BOOTSTRAP + textwrap.dedent(body)
    proc = subprocess.run(
        [sys.executable, "-c", script],
        cwd=REPO_DIR,
        capture_output=True,
        text=True,
        timeout=timeout,
        env={k: v for k, v in os.environ.items() if k != "PYTHONPATH"},
    )
    assert proc.returncode == 0, (
        "driver failed\nSTDOUT:\n"
        + proc.stdout[-4000:]
        + "\nSTDERR:\n"
        + proc.stderr[-4000:]
    )
    out = proc.stdout.strip().splitlines()
    assert out, "driver produced no stdout:\n" + proc.stderr[-2000:]
    return json.loads(out[-1])


class TestStatsmodelsRegression:
    REPO_DIR = "/workspace/statsmodels"

    MODULE_PATH = os.path.join(
        REPO_DIR, "statsmodels", "stats", "collinearity.py"
    )
    TEST_PATH = os.path.join(
        REPO_DIR, "statsmodels", "stats", "tests", "test_collinearity.py"
    )

    # ------------------------------------------------------------------ L1 ---
    def test_module_file_exists(self):
        """L1: the new collinearity.py deliverable exists and is non-trivial."""
        assert os.path.isfile(self.MODULE_PATH), (
            "expected new module at " + self.MODULE_PATH
        )
        assert os.path.getsize(self.MODULE_PATH) > 0

    def test_function_importable_with_signature(self):
        """L1: collinearity_report importable with the exact required params and
        the documented default values (add_intercept=True, vif_threshold=10.0)."""
        report = _run_driver(
            """
            import inspect
            sig = inspect.signature(collinearity_report)
            params = list(sig.parameters)
            ai = sig.parameters.get('add_intercept')
            vt = sig.parameters.get('vif_threshold')
            print(json.dumps({
                'params': params,
                'add_intercept_default': (ai.default if ai is not None else None),
                'vif_threshold_default': (
                    float(vt.default) if vt is not None and vt.default is not inspect._empty
                    else None),
            }))
            """
        )
        assert report["params"][0] == "exog", report["params"]
        assert "add_intercept" in report["params"]
        assert "vif_threshold" in report["params"]
        assert report["add_intercept_default"] is True
        assert report["vif_threshold_default"] == 10.0

    def test_returns_dict_with_required_keys(self):
        """L1: the helper returns a plain dict containing every documented key."""
        report = _run_driver(
            """
            rng = np.random.RandomState(0)
            X = rng.normal(size=(40, 3))
            out = collinearity_report(X)
            print(json.dumps({
                'is_dict': type(out).__name__ == 'dict',
                'keys': sorted(out.keys()),
            }))
            """
        )
        assert report["is_dict"] is True, "must return a plain dict"
        required = {
            "vif", "max_vif", "high_vif_columns",
            "condition_number", "multicollinear",
        }
        missing = required - set(report["keys"])
        assert not missing, "missing keys: " + str(sorted(missing))

    def test_value_types_are_well_formed(self):
        """L1: vif is a 1-D ndarray, max_vif/condition_number are floats,
        high_vif_columns is a list, multicollinear is a bool."""
        report = _run_driver(
            """
            rng = np.random.RandomState(1)
            X = rng.normal(size=(50, 4))
            out = collinearity_report(X)
            vif = out['vif']
            print(json.dumps({
                'vif_is_ndarray': isinstance(vif, np.ndarray),
                'vif_ndim': int(np.asarray(vif).ndim),
                'vif_len': int(np.asarray(vif).shape[0]),
                'max_vif_is_float': isinstance(out['max_vif'], float),
                'cond_is_float': isinstance(out['condition_number'], float),
                'high_is_list': isinstance(out['high_vif_columns'], list),
                'multi_is_bool': isinstance(out['multicollinear'], bool),
            }))
            """
        )
        assert report["vif_is_ndarray"] is True, "'vif' must be a numpy.ndarray"
        assert report["vif_ndim"] == 1, "'vif' must be 1-D"
        assert report["vif_len"] == 4, "one vif per supplied column"
        assert report["max_vif_is_float"] is True
        assert report["cond_is_float"] is True
        assert report["high_is_list"] is True
        assert report["multi_is_bool"] is True

    # ------------------------------------------------------------------ L2 ---
    def test_vif_length_matches_supplied_columns(self):
        """L2: len(vif) equals the number of SUPPLIED (non-intercept) columns in
        both the add_intercept=True and add_intercept=False cases."""
        report = _run_driver(
            """
            rng = np.random.RandomState(2)
            X = rng.normal(size=(60, 5))
            out_t = collinearity_report(X, add_intercept=True)
            out_f = collinearity_report(X, add_intercept=False)
            print(json.dumps({
                'len_t': int(np.asarray(out_t['vif']).shape[0]),
                'len_f': int(np.asarray(out_f['vif']).shape[0]),
                'ncols': int(X.shape[1]),
            }))
            """
        )
        assert report["len_t"] == report["ncols"]
        assert report["len_f"] == report["ncols"]

    def test_vif_matches_statsmodels_with_intercept(self):
        """L2: each vif entry equals statsmodels' variance_inflation_factor on
        the intercept-augmented design, in original column order, to fp tol."""
        report = _run_driver(
            """
            rng = np.random.RandomState(3)
            n, k = 80, 4
            base = rng.normal(size=(n, k))
            # make column 2 partly dependent on cols 0 and 1 for spread
            base[:, 2] = 0.6 * base[:, 0] - 0.4 * base[:, 1] + 0.3 * base[:, 2]
            X = base

            out = collinearity_report(X, add_intercept=True)
            reported = np.asarray(out['vif'], dtype=float)

            Xc = sm.add_constant(X)  # design used for VIF includes the constant
            # the constant lives at column 0 of Xc; supplied cols are 1..k
            ref = np.array([
                variance_inflation_factor(Xc, i + 1) for i in range(k)
            ])
            print(json.dumps({
                'max_abs_err': float(np.max(np.abs(reported - ref))),
                'reported': reported.tolist(),
                'ref': ref.tolist(),
            }))
            """
        )
        assert report["max_abs_err"] < 1e-6, (
            "vif mismatch\nreported=%r\nref=%r"
            % (report["reported"], report["ref"])
        )

    def test_vif_matches_statsmodels_no_intercept(self):
        """L2: with add_intercept=False the vif entries equal
        variance_inflation_factor computed on the supplied design as-is."""
        report = _run_driver(
            """
            rng = np.random.RandomState(4)
            n, k = 70, 3
            X = rng.normal(size=(n, k))
            X[:, 1] = 0.5 * X[:, 0] + 0.5 * X[:, 2]

            out = collinearity_report(X, add_intercept=False)
            reported = np.asarray(out['vif'], dtype=float)
            ref = np.array([variance_inflation_factor(X, i) for i in range(k)])
            print(json.dumps({
                'max_abs_err': float(np.max(np.abs(reported - ref))),
                'reported': reported.tolist(),
                'ref': ref.tolist(),
            }))
            """
        )
        assert report["max_abs_err"] < 1e-6, (
            "no-intercept vif mismatch\nreported=%r\nref=%r"
            % (report["reported"], report["ref"])
        )

    def test_column_order_preserved(self):
        """L2: vif entries follow the ORIGINAL column order; permuting columns
        permutes the vif vector identically (a stub that sorts or hardcodes
        order fails). Uses a design with sharply distinct per-column VIFs."""
        report = _run_driver(
            """
            rng = np.random.RandomState(9)
            n = 120
            a = rng.normal(size=n)
            b = rng.normal(size=n)
            c = a + 0.001 * rng.normal(size=n)   # nearly collinear with a
            X = np.column_stack([a, b, c])
            out0 = collinearity_report(X, add_intercept=True)
            v0 = np.asarray(out0['vif'], dtype=float)

            perm = [2, 0, 1]
            Xp = X[:, perm]
            outp = collinearity_report(Xp, add_intercept=True)
            vp = np.asarray(outp['vif'], dtype=float)

            print(json.dumps({
                'v0': v0.tolist(),
                'vp': vp.tolist(),
                'perm_match': float(np.max(np.abs(vp - v0[perm]))),
                # a and c huge VIF, b ~1
                'a_high': bool(v0[0] > 50),
                'b_low': bool(v0[1] < 3),
                'c_high': bool(v0[2] > 50),
            }))
            """
        )
        assert report["a_high"] is True, report["v0"]
        assert report["b_low"] is True, report["v0"]
        assert report["c_high"] is True, report["v0"]
        assert report["perm_match"] < 1e-6, (
            "permuting columns did not permute vif identically: %r vs %r"
            % (report["vp"], report["v0"])
        )

    def test_condition_number_matches_statsmodels(self):
        """L2: condition_number equals sm.OLS(...).fit().condition_number on the
        intercept-augmented design to fp tolerance."""
        report = _run_driver(
            """
            rng = np.random.RandomState(5)
            n, k = 90, 4
            X = rng.normal(size=(n, k))
            X[:, 3] = 0.8 * X[:, 0] + 0.2 * X[:, 1]  # ill-conditioned
            y = rng.normal(size=n)

            out = collinearity_report(X, add_intercept=True)
            Xc = sm.add_constant(X)
            ref = sm.OLS(y, Xc).fit().condition_number

            cn = float(out['condition_number'])
            print(json.dumps({
                'cn': cn,
                'ref': float(ref),
                'rel_err': abs(cn - float(ref)) / float(ref),
            }))
            """
        )
        assert report["rel_err"] < 1e-6, (
            "condition_number %r != statsmodels %r"
            % (report["cn"], report["ref"])
        )

    def test_orthogonal_design_low_vif(self):
        """L2: nearly-orthogonal columns -> all vif near 1, multicollinear False,
        high_vif_columns empty (the 'clean' arm of the discrimination)."""
        report = _run_driver(
            """
            # orthonormal columns via QR -> VIF ~ 1 exactly
            rng = np.random.RandomState(10)
            n, k = 50, 4
            Q, _ = np.linalg.qr(rng.normal(size=(n, k)))
            X = Q  # orthonormal columns
            out = collinearity_report(X, add_intercept=True, vif_threshold=10.0)
            vif = np.asarray(out['vif'], dtype=float)
            print(json.dumps({
                'max_vif': float(out['max_vif']),
                'all_near_1': bool(np.all(np.abs(vif - 1.0) < 0.5)),
                'multicollinear': bool(out['multicollinear']),
                'high_cols': list(out['high_vif_columns']),
            }))
            """
        )
        assert report["all_near_1"] is True, report["max_vif"]
        assert report["max_vif"] < 10.0
        assert report["multicollinear"] is False
        assert report["high_cols"] == []

    def test_collinear_design_flags_offending_column(self):
        """L2: when one column is nearly a linear combination of the others, its
        0-based index appears in high_vif_columns, multicollinear is True, and
        max_vif == max(vif). Also condition_number markedly exceeds the
        orthogonal design's (sign discrimination)."""
        report = _run_driver(
            """
            rng = np.random.RandomState(11)
            n = 150
            x0 = rng.normal(size=n)
            x1 = rng.normal(size=n)
            x2 = rng.normal(size=n)
            x3 = 2.0 * x0 - 1.0 * x1 + 1e-4 * rng.normal(size=n)  # ~ collinear
            X = np.column_stack([x0, x1, x2, x3])
            out = collinearity_report(X, add_intercept=True, vif_threshold=10.0)
            vif = np.asarray(out['vif'], dtype=float)

            # reference orthogonal design condition number for comparison
            Q, _ = np.linalg.qr(rng.normal(size=(n, 4)))
            out_ortho = collinearity_report(Q, add_intercept=True)

            print(json.dumps({
                'high_cols': sorted(int(i) for i in out['high_vif_columns']),
                'multicollinear': bool(out['multicollinear']),
                'argmax_vif': int(np.argmax(vif)),
                'max_vif_consistent': bool(
                    abs(float(out['max_vif']) - float(np.max(vif))) < 1e-9),
                'cond_collinear': float(out['condition_number']),
                'cond_ortho': float(out_ortho['condition_number']),
            }))
            """
        )
        # x0, x1, x3 are mutually collinear; index 3 must be flagged.
        assert 3 in report["high_cols"], report["high_cols"]
        assert 0 in report["high_cols"] and 1 in report["high_cols"]
        assert 2 not in report["high_cols"]
        assert report["multicollinear"] is True
        assert report["max_vif_consistent"] is True
        assert report["cond_collinear"] > 10.0 * report["cond_ortho"]

    def test_high_vif_columns_consistent_with_threshold(self):
        """L2: high_vif_columns is EXACTLY {i: vif[i] > vif_threshold} and
        multicollinear == (max_vif > vif_threshold) for an arbitrary threshold.
        A stub using a fixed cutoff or ignoring vif_threshold fails."""
        report = _run_driver(
            """
            rng = np.random.RandomState(13)
            n = 200
            x0 = rng.normal(size=n)
            x1 = rng.normal(size=n)
            x2 = 0.95 * x0 + 0.1 * rng.normal(size=n)  # moderate collinearity
            X = np.column_stack([x0, x1, x2])
            thr = 4.0
            out = collinearity_report(X, add_intercept=True, vif_threshold=thr)
            vif = np.asarray(out['vif'], dtype=float)
            expected = sorted(int(i) for i in np.where(vif > thr)[0])
            print(json.dumps({
                'reported': sorted(int(i) for i in out['high_vif_columns']),
                'expected': expected,
                'multi': bool(out['multicollinear']),
                'multi_expected': bool(float(np.max(vif)) > thr),
            }))
            """
        )
        assert report["reported"] == report["expected"], (
            "high_vif_columns %r != threshold-derived %r"
            % (report["reported"], report["expected"])
        )
        assert report["multi"] == report["multi_expected"]

    def test_accepts_lists_and_1d_exog(self):
        """L2: a plain Python list and a 1-D exog (single column) are accepted;
        a single column has vif of length 1 equal to 1.0 (no other regressors)
        and matches the equivalent 2-D ndarray call."""
        report = _run_driver(
            """
            rng = np.random.RandomState(8)
            x = list(np.linspace(0, 3, 30) + rng.normal(scale=0.1, size=30))
            out_1d = collinearity_report(x, add_intercept=True)
            out_2d = collinearity_report(
                np.asarray(x).reshape(-1, 1), add_intercept=True)
            v1 = np.asarray(out_1d['vif'], dtype=float)
            v2 = np.asarray(out_2d['vif'], dtype=float)
            print(json.dumps({
                'len1': int(v1.shape[0]),
                'vif0': float(v1[0]),
                'multi': bool(out_1d['multicollinear']),
                'match': float(np.max(np.abs(v1 - v2))),
                'cond_match': abs(
                    float(out_1d['condition_number'])
                    - float(out_2d['condition_number'])),
            }))
            """
        )
        assert report["len1"] == 1, "single column -> one vif entry"
        assert abs(report["vif0"] - 1.0) < 1e-6, (
            "a lone predictor cannot be inflated by others; vif must be ~1.0, got %r"
            % report["vif0"]
        )
        assert report["multi"] is False
        assert report["match"] < 1e-12
        assert report["cond_match"] < 1e-9

    def test_existing_constant_column_not_duplicated(self):
        """L2: add_intercept=True with an exog that already contains a constant
        column must not add a second constant. The vif for the genuine predictor
        still matches statsmodels and no NaN/inf is produced from a rank-deficient
        double-constant design."""
        report = _run_driver(
            """
            rng = np.random.RandomState(7)
            n = 60
            ones = np.ones(n)
            x = rng.normal(size=n)
            z = rng.normal(size=n)
            X = np.column_stack([ones, x, z])  # col 0 is already constant

            out = collinearity_report(X, add_intercept=True)
            vif = np.asarray(out['vif'], dtype=float)

            # reference: skip the duplicate constant; VIF of the real predictors
            Xc = sm.add_constant(X, has_constant='skip')
            # Xc columns: [const, ones?, x, z] -> with skip, ones IS the const so
            # Xc == X (already has constant). VIF of x and z computed on X.
            ref_x = variance_inflation_factor(X, 1)
            ref_z = variance_inflation_factor(X, 2)

            print(json.dumps({
                'nvif': int(vif.shape[0]),
                'ncols': int(X.shape[1]),
                'any_nan': bool(np.any(~np.isfinite(vif))),
                'cond': float(out['condition_number']),
                'cond_finite': bool(np.isfinite(out['condition_number'])),
                'vif_x_err': abs(float(vif[1]) - float(ref_x)),
                'vif_z_err': abs(float(vif[2]) - float(ref_z)),
            }))
            """
        )
        assert report["nvif"] == report["ncols"], (
            "vif length %d != supplied column count %d"
            % (report["nvif"], report["ncols"])
        )
        assert report["any_nan"] is False, (
            "a duplicated constant produced a rank-deficient / NaN design"
        )
        assert report["cond_finite"] is True
        assert report["vif_x_err"] < 1e-6
        assert report["vif_z_err"] < 1e-6

    def test_native_pytest_passes(self):
        """L2: the acceptance command for the deliverable's own unit tests passes
        (pytest statsmodels/stats/tests/test_collinearity.py)."""
        if not os.path.isfile(self.TEST_PATH):
            pytest.skip("deliverable test module not present: " + self.TEST_PATH)
        proc = subprocess.run(
            [
                sys.executable, "-m", "pytest",
                os.path.join(
                    "statsmodels", "stats", "tests",
                    "test_collinearity.py",
                ),
                "-q",
            ],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=600,
            env={k: v for k, v in os.environ.items() if k != "PYTHONPATH"},
        )
        assert proc.returncode == 0, (
            "native pytest failed\nSTDOUT:\n"
            + proc.stdout[-4000:]
            + "\nSTDERR:\n"
            + proc.stderr[-2000:]
        )
