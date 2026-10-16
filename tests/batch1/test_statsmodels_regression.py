"""Tests for the ``statsmodels-regression`` skill.

Verifies the deliverable ``statsmodels/stats/regression_report.py`` which must
expose a public ``regression_diagnostics(endog, exog, add_intercept=True)``
helper that fits an OLS linear model from raw arrays and returns a structured
``dict`` diagnostics report.

The tests independently re-derive every reported quantity (params, rsquared,
aic, bic, resid, heteroskedasticity p-value, max-Cook's-distance index,
max-leverage index) from statsmodels' own OLS / OLSInfluence / het_breuschpagan
machinery and assert agreement to floating-point tolerance. They also plant
known high-influence and high-leverage observations and assert the returned
integer indices recover them. Naive / hardcoded approximations cannot satisfy
these checks.

Strategy: L1 cases check the deliverable file exists and the function is
importable with the right signature and returns the documented keys/types. L2
cases run the agent's function in a subprocess that emits JSON (so the test is
robust to PYTHONPATH being cleared and to import-time side effects), then
compare against an independent statsmodels computation done in the same
subprocess.
"""

import json
import os
import subprocess
import sys
import textwrap

import pytest

REPO_DIR = "/workspace/statsmodels"


# Bootstrap that imports the agent's module from REPO_DIR and exposes both the
# helper under test and a reference statsmodels implementation. Each driver
# script below prepends this so it can run from anywhere with PYTHONPATH cleared.
_BOOTSTRAP = textwrap.dedent(
    """
    import sys, os, json
    REPO_DIR = {repo!r}
    sys.path.insert(0, REPO_DIR)
    import numpy as np
    import statsmodels.api as sm
    from statsmodels.stats.diagnostic import het_breuschpagan
    from statsmodels.stats.outliers_influence import OLSInfluence
    from statsmodels.stats.regression_report import regression_diagnostics
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
        REPO_DIR, "statsmodels", "stats", "regression_report.py"
    )
    TEST_PATH = os.path.join(
        REPO_DIR, "statsmodels", "stats", "tests", "test_regression_report.py"
    )

    # ------------------------------------------------------------------ L1 ---
    def test_module_file_exists(self):
        """L1: the new regression_report.py deliverable exists and is non-trivial."""
        assert os.path.isfile(self.MODULE_PATH), (
            "expected new module at " + self.MODULE_PATH
        )
        assert os.path.getsize(self.MODULE_PATH) > 0

    def test_function_importable_with_signature(self):
        """L1: regression_diagnostics is importable and has the required params."""
        report = _run_driver(
            """
            import inspect
            sig = inspect.signature(regression_diagnostics)
            params = list(sig.parameters)
            has_default = (
                sig.parameters['add_intercept'].default is True
                if 'add_intercept' in sig.parameters else False
            )
            print(json.dumps({'params': params, 'add_intercept_default': has_default}))
            """
        )
        assert report["params"][:2] == ["endog", "exog"], report["params"]
        assert "add_intercept" in report["params"]
        assert report["add_intercept_default"] is True

    def test_returns_dict_with_required_keys(self):
        """L1: the helper returns a plain dict containing every documented key."""
        report = _run_driver(
            """
            x = np.linspace(0, 10, 30)
            y = 1.0 + 2.0 * x
            out = regression_diagnostics(list(y), list(x))
            print(json.dumps({
                'is_dict': type(out).__name__ == 'dict',
                'keys': sorted(out.keys()),
            }))
            """
        )
        assert report["is_dict"] is True, "must return a plain dict"
        required = {
            "params", "nobs", "df_resid", "rsquared", "aic", "bic",
            "resid", "het_pvalue", "max_cooks_obs", "max_leverage_obs",
        }
        missing = required - set(report["keys"])
        assert not missing, "missing keys: " + str(sorted(missing))

    def test_index_keys_are_python_ints(self):
        """L1: max_cooks_obs / max_leverage_obs are integer-typed and in range."""
        report = _run_driver(
            """
            rng = np.random.RandomState(0)
            x = np.linspace(0, 5, 20)
            y = 0.5 + 1.5 * x + rng.normal(scale=0.3, size=20)
            out = regression_diagnostics(y, x)
            ck, lv = out['max_cooks_obs'], out['max_leverage_obs']
            print(json.dumps({
                'cooks_int': bool(float(ck) == int(ck)),
                'lev_int': bool(float(lv) == int(lv)),
                'cooks': int(ck), 'lev': int(lv),
            }))
            """
        )
        assert report["cooks_int"] and report["lev_int"]
        assert 0 <= report["cooks"] < 20
        assert 0 <= report["lev"] < 20

    # ------------------------------------------------------------------ L2 ---
    def test_intercept_first_and_near_perfect_fit(self):
        """L2: single near-linear predictor + intercept -> len(params)==2,
        rsquared ~ 1.0, and params[0] is the intercept."""
        report = _run_driver(
            """
            rng = np.random.RandomState(1)
            x = np.linspace(0, 10, 50)
            y = 4.0 + 3.0 * x + rng.normal(scale=0.001, size=50)
            out = regression_diagnostics(y, x, add_intercept=True)
            p = list(np.asarray(out['params'], dtype=float))
            print(json.dumps({
                'nparams': len(p),
                'rsquared': float(out['rsquared']),
                'intercept': p[0],
                'slope': p[1],
            }))
            """
        )
        assert report["nparams"] == 2
        assert report["rsquared"] > 0.9999
        assert abs(report["intercept"] - 4.0) < 0.05
        assert abs(report["slope"] - 3.0) < 0.05

    def test_no_intercept_param_count_and_df(self):
        """L2: add_intercept=False on a single predictor -> len(params)==1 and
        df_resid == nobs - 1 (matching statsmodels' no-constant OLS)."""
        report = _run_driver(
            """
            rng = np.random.RandomState(2)
            x = np.linspace(1, 6, 24)
            y = 2.7 * x + rng.normal(scale=0.4, size=24)
            out = regression_diagnostics(y, x, add_intercept=False)
            ref = sm.OLS(np.asarray(y, float),
                         np.asarray(x, float).reshape(-1, 1)).fit()
            print(json.dumps({
                'nparams': len(np.asarray(out['params'])),
                'nobs': int(out['nobs']),
                'df_resid': int(out['df_resid']),
                'param0': float(np.asarray(out['params'], float)[0]),
                'ref_param0': float(ref.params[0]),
            }))
            """
        )
        assert report["nparams"] == 1
        assert report["nobs"] == 24
        assert report["df_resid"] == 24 - 1
        assert abs(report["param0"] - report["ref_param0"]) < 1e-8

    def test_params_rsq_aic_bic_resid_match_statsmodels(self):
        """L2: with an intercept, params/rsquared/aic/bic/resid match a direct
        statsmodels OLS on the intercept-augmented design to fp tolerance."""
        report = _run_driver(
            """
            rng = np.random.RandomState(3)
            n = 60
            x1 = rng.normal(size=n)
            x2 = rng.uniform(-2, 2, size=n)
            X = np.column_stack([x1, x2])
            y = 1.3 - 2.0 * x1 + 0.7 * x2 + rng.normal(scale=0.5, size=n)

            out = regression_diagnostics(y, X, add_intercept=True)

            Xc = sm.add_constant(X)
            ref = sm.OLS(y, Xc).fit()

            params = np.asarray(out['params'], dtype=float)
            resid = np.asarray(out['resid'], dtype=float)
            print(json.dumps({
                'param_max_abs_err': float(np.max(np.abs(params - ref.params))),
                'first_is_intercept': bool(abs(params[0] - ref.params[0]) < 1e-8),
                'rsq_err': abs(float(out['rsquared']) - float(ref.rsquared)),
                'aic_err': abs(float(out['aic']) - float(ref.aic)),
                'bic_err': abs(float(out['bic']) - float(ref.bic)),
                'resid_len': int(resid.shape[0]),
                'resid_max_abs_err': float(np.max(np.abs(resid - ref.resid))),
                'n': n,
            }))
            """
        )
        assert report["param_max_abs_err"] < 1e-8
        assert report["first_is_intercept"] is True
        assert report["rsq_err"] < 1e-9
        assert report["aic_err"] < 1e-6
        assert report["bic_err"] < 1e-6
        assert report["resid_len"] == report["n"]
        assert report["resid_max_abs_err"] < 1e-8

    def test_het_pvalue_matches_breuschpagan(self):
        """L2: het_pvalue equals the statsmodels Breusch-Pagan LM p-value for the
        same residuals and intercept-augmented design."""
        report = _run_driver(
            """
            rng = np.random.RandomState(4)
            n = 80
            x = rng.uniform(0, 10, size=n)
            # heteroskedastic noise: variance grows with x
            y = 2.0 + 1.5 * x + rng.normal(scale=0.2 + 0.4 * x, size=n)

            out = regression_diagnostics(y, x, add_intercept=True)

            Xc = sm.add_constant(x)
            ref = sm.OLS(y, Xc).fit()
            bp = het_breuschpagan(ref.resid, Xc)  # (lm, lm_pvalue, f, f_pvalue)

            hp = float(out['het_pvalue'])
            print(json.dumps({
                'hp': hp,
                'bp_lm_p': float(bp[1]),
                'matches_lm_p': abs(hp - float(bp[1])) < 1e-9,
                'is_prob': 0.0 <= hp <= 1.0,
            }))
            """
        )
        assert report["is_prob"] is True
        assert report["matches_lm_p"], (
            "het_pvalue %r != Breusch-Pagan LM p-value %r"
            % (report["hp"], report["bp_lm_p"])
        )

    def test_het_pvalue_small_under_heteroskedasticity(self):
        """L2: strongly non-constant variance yields a small het p-value while a
        clean homoskedastic fit yields a large one (sign discrimination)."""
        report = _run_driver(
            """
            n = 150
            x = np.linspace(0, 10, n)
            rng_het = np.random.RandomState(5)
            y_het = 1.0 + 2.0 * x + rng_het.normal(scale=0.05 + 0.9 * x, size=n)
            rng_hom = np.random.RandomState(12)
            y_hom = 1.0 + 2.0 * x + rng_hom.normal(scale=0.5, size=n)
            p_het = float(regression_diagnostics(y_het, x)['het_pvalue'])
            p_hom = float(regression_diagnostics(y_hom, x)['het_pvalue'])
            print(json.dumps({'p_het': p_het, 'p_hom': p_hom}))
            """
        )
        assert report["p_het"] < 0.05, report
        assert report["p_hom"] > 0.10, report

    def test_max_cooks_identifies_planted_outlier(self):
        """L2: a single off-trend observation is recovered as max_cooks_obs and
        agrees with np.argmax of OLSInfluence.cooks_distance."""
        report = _run_driver(
            """
            n = 35
            planted = 11
            x = np.linspace(0, 10, n)
            y = 1.0 + 2.0 * x
            y = y.astype(float).copy()
            y[planted] += 30.0  # large off-trend jump -> high influence

            out = regression_diagnostics(y, x, add_intercept=True)

            Xc = sm.add_constant(x)
            ref = sm.OLS(y, Xc).fit()
            infl = OLSInfluence(ref)
            ref_idx = int(np.argmax(infl.cooks_distance[0]))
            print(json.dumps({
                'reported': int(out['max_cooks_obs']),
                'planted': planted,
                'ref_idx': ref_idx,
            }))
            """
        )
        assert report["reported"] == report["planted"]
        assert report["reported"] == report["ref_idx"]

    def test_max_leverage_identifies_extreme_predictor(self):
        """L2: an observation whose predictor is far from all others is recovered
        as max_leverage_obs and agrees with argmax of the hat-matrix diagonal."""
        report = _run_driver(
            """
            n = 40
            planted = 27
            rng = np.random.RandomState(6)
            x = np.linspace(0, 5, n).astype(float).copy()
            x[planted] = 120.0  # extreme leverage point
            y = 0.5 + 1.2 * x + rng.normal(scale=0.5, size=n)

            out = regression_diagnostics(y, x, add_intercept=True)

            Xc = sm.add_constant(x)
            ref = sm.OLS(y, Xc).fit()
            infl = OLSInfluence(ref)
            ref_idx = int(np.argmax(infl.hat_matrix_diag))
            print(json.dumps({
                'reported': int(out['max_leverage_obs']),
                'planted': planted,
                'ref_idx': ref_idx,
            }))
            """
        )
        assert report["reported"] == report["planted"]
        assert report["reported"] == report["ref_idx"]

    def test_existing_constant_column_not_duplicated(self):
        """L2: add_intercept=True with an exog that already has a constant column
        must not add a duplicate constant; the fit stays full-rank and params
        count equals the supplied columns (matches has_constant='skip')."""
        report = _run_driver(
            """
            rng = np.random.RandomState(7)
            n = 50
            ones = np.ones(n)
            x = rng.normal(size=n)
            X = np.column_stack([ones, x])  # already contains a constant column
            y = 2.0 + 3.0 * x + rng.normal(scale=0.4, size=n)

            out = regression_diagnostics(y, X, add_intercept=True)
            params = np.asarray(out['params'], dtype=float)

            # reference: skip duplicate constant
            Xc = sm.add_constant(X, has_constant='skip')
            ref = sm.OLS(y, Xc).fit()

            rank = int(np.linalg.matrix_rank(Xc))
            print(json.dumps({
                'nparams': int(params.shape[0]),
                'ncols': int(X.shape[1]),
                'full_rank': rank == X.shape[1],
                'rsq': float(out['rsquared']),
                'ref_rsq': float(ref.rsquared),
                'param_err': float(np.max(np.abs(np.sort(params) - np.sort(ref.params)))),
                'has_nan': bool(np.any(np.isnan(params))),
            }))
            """
        )
        assert report["nparams"] == report["ncols"], (
            "duplicate constant was added: %d params for %d supplied columns"
            % (report["nparams"], report["ncols"])
        )
        assert report["full_rank"] is True
        assert report["has_nan"] is False
        assert abs(report["rsq"] - report["ref_rsq"]) < 1e-9
        assert report["param_err"] < 1e-8

    def test_accepts_lists_and_1d_exog(self):
        """L2: plain Python lists and a 1-D exog (single column) are accepted and
        produce the same numeric report as the equivalent ndarray 2-D call."""
        report = _run_driver(
            """
            rng = np.random.RandomState(8)
            x = list(np.linspace(0, 3, 30))
            y = list(0.4 + 1.1 * np.asarray(x) + rng.normal(scale=0.2, size=30))

            out_list = regression_diagnostics(y, x, add_intercept=True)
            out_arr = regression_diagnostics(
                np.asarray(y), np.asarray(x).reshape(-1, 1), add_intercept=True)

            pl = np.asarray(out_list['params'], dtype=float)
            pa = np.asarray(out_arr['params'], dtype=float)
            print(json.dumps({
                'list_nparams': int(pl.shape[0]),
                'param_err': float(np.max(np.abs(pl - pa))),
                'rsq_err': abs(float(out_list['rsquared']) - float(out_arr['rsquared'])),
                'nobs': int(out_list['nobs']),
            }))
            """
        )
        assert report["list_nparams"] == 2  # intercept + single column
        assert report["nobs"] == 30
        assert report["param_err"] < 1e-12
        assert report["rsq_err"] < 1e-12

    def test_native_pytest_passes(self):
        """L2: the acceptance command for the deliverable's own unit tests passes
        (pytest statsmodels/stats/tests/test_regression_report.py)."""
        if not os.path.isfile(self.TEST_PATH):
            pytest.skip("deliverable test module not present: " + self.TEST_PATH)
        proc = subprocess.run(
            [
                sys.executable, "-m", "pytest",
                os.path.join(
                    "statsmodels", "stats", "tests",
                    "test_regression_report.py",
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
