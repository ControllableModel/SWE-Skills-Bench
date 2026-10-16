"""Tests for the ``statsmodels-regression`` skill (variant ext2).

Variant task: build a *count-data model selector*. The deliverable is a new
module ``statsmodels/genmod/count_selector.py`` exposing::

    select_count_model(endog, exog, add_intercept=True, dispersion_threshold=1.5)

which fits a count GLM of non-negative integer ``endog`` on ``exog`` and returns
a plain ``dict`` report with keys ``params`` (log-link coefficients, intercept
first), ``rate_ratios`` (``exp(params)``), ``dispersion`` (a float >~1 estimate
of over-dispersion), ``overdispersed`` (bool, ``dispersion > dispersion_threshold``),
``recommended_model`` (``"poisson"`` / ``"negativebinomial"``), ``aic`` (AIC of
the *recommended* model) and ``nobs``.

Verification strategy
---------------------
This test independently re-derives every reported quantity from statsmodels'
own count-model machinery (``statsmodels.api.GLM`` with a Poisson family and
``statsmodels.discrete.discrete_model.Poisson`` / ``NegativeBinomial``) inside
a fresh subprocess rooted at REPO_DIR, then asserts agreement to floating-point
tolerance. Because the equidispersed Poisson coefficients/AIC are identical
between ``GLM(Poisson)`` and ``discrete.Poisson``, the param/rate-ratio/AIC
checks hold regardless of which estimator the agent uses. Behavioural sign
checks (dispersion ~ 1 on equidispersed data, dispersion well above the
threshold on over-dispersed data, the model recommendation, a rate ratio > 1
for a positive predictor) discriminate a real fit from a stub.

A naive implementation (hardcoded dispersion, ignored inputs, intercept not
added, ``rate_ratios`` not equal to ``exp(params)``, or ``aic`` always taken
from the Poisson model even when over-dispersion is detected) must fail.

L1 cases check the deliverable exists and the function is importable with the
right signature and returns the documented keys/types. L2 cases run the agent's
function in a subprocess that emits JSON (robust to a cleared PYTHONPATH and to
import-time side effects) and compare against an independent statsmodels
computation done in the same subprocess.
"""

import json
import os
import subprocess
import sys
import textwrap

import pytest

REPO_DIR = "/workspace/statsmodels"


# Bootstrap that imports the agent's module from REPO_DIR plus reference
# statsmodels estimators. Each driver script prepends this so it can run from
# anywhere with PYTHONPATH cleared.
_BOOTSTRAP = textwrap.dedent(
    """
    import sys, os, json
    REPO_DIR = {repo!r}
    sys.path.insert(0, REPO_DIR)
    import numpy as np
    import statsmodels.api as sm
    from statsmodels.discrete.discrete_model import Poisson, NegativeBinomial
    from statsmodels.genmod.count_selector import select_count_model

    def _poisson_counts(seed, n, b0, b1):
        rng = np.random.RandomState(seed)
        x = rng.normal(size=n)
        mu = np.exp(b0 + b1 * x)
        y = rng.poisson(mu)
        return x, y

    def _overdispersed_counts(seed, n, b0, b1):
        # Negative-binomial-style counts: variance far exceeds the mean.
        rng = np.random.RandomState(seed)
        x = rng.normal(size=n)
        mu = np.exp(b0 + b1 * x)
        # gamma-mixed Poisson -> strong overdispersion
        shape = 0.4
        lam = rng.gamma(shape=shape, scale=mu / shape)
        y = rng.poisson(lam)
        return x, y
    """
).format(repo=REPO_DIR)


def _run_driver(body, timeout=600):
    """Execute *body* (which must print a single JSON object on its last stdout
    line) in a fresh interpreter rooted at REPO_DIR. Returns the parsed dict."""
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
        REPO_DIR, "statsmodels", "genmod", "count_selector.py"
    )
    TEST_PATH = os.path.join(
        REPO_DIR, "statsmodels", "genmod", "tests", "test_count_selector.py"
    )

    # ------------------------------------------------------------------ L1 ---
    def test_module_file_exists(self):
        """L1: the new count_selector.py deliverable exists and is non-trivial."""
        assert os.path.isfile(self.MODULE_PATH), (
            "expected new module at " + self.MODULE_PATH
        )
        assert os.path.getsize(self.MODULE_PATH) > 0

    def test_function_importable_with_signature(self):
        """L1: select_count_model is importable and has the required parameters
        and documented defaults (add_intercept=True, dispersion_threshold=1.5)."""
        report = _run_driver(
            """
            import inspect
            sig = inspect.signature(select_count_model)
            params = list(sig.parameters)
            ai = sig.parameters.get('add_intercept')
            dt = sig.parameters.get('dispersion_threshold')
            print(json.dumps({
                'params': params,
                'add_intercept_default': (ai.default if ai else None),
                'dispersion_threshold_default':
                    (float(dt.default) if dt is not None else None),
            }))
            """
        )
        assert report["params"][:2] == ["endog", "exog"], report["params"]
        assert "add_intercept" in report["params"]
        assert "dispersion_threshold" in report["params"]
        assert report["add_intercept_default"] is True
        assert abs(report["dispersion_threshold_default"] - 1.5) < 1e-12

    def test_returns_dict_with_required_keys(self):
        """L1: the helper returns a plain dict containing every documented key."""
        report = _run_driver(
            """
            x, y = _poisson_counts(0, 120, 0.3, 0.5)
            out = select_count_model(list(map(int, y)), list(map(float, x)))
            print(json.dumps({
                'is_dict': type(out).__name__ == 'dict',
                'keys': sorted(out.keys()),
            }))
            """
        )
        assert report["is_dict"] is True, "must return a plain dict"
        required = {
            "params", "rate_ratios", "dispersion", "overdispersed",
            "recommended_model", "aic", "nobs",
        }
        missing = required - set(report["keys"])
        assert not missing, "missing keys: " + str(sorted(missing))

    def test_value_types_well_formed(self):
        """L1: params/rate_ratios are 1-D arrays of equal length, dispersion/aic
        are real floats, overdispersed is a bool, nobs is an int == len(endog)."""
        report = _run_driver(
            """
            x, y = _poisson_counts(1, 100, 0.2, 0.4)
            out = select_count_model(y, x)
            params = np.asarray(out['params'], dtype=float)
            rr = np.asarray(out['rate_ratios'], dtype=float)
            print(json.dumps({
                'params_ndim': int(params.ndim),
                'rr_ndim': int(rr.ndim),
                'equal_len': int(params.shape[0]) == int(rr.shape[0]),
                'disp_float': isinstance(out['dispersion'], float)
                    or isinstance(out['dispersion'], (np.floating,)).__bool__(),
                'disp_finite': bool(np.isfinite(float(out['dispersion']))),
                'aic_finite': bool(np.isfinite(float(out['aic']))),
                'overdispersed_is_bool':
                    isinstance(out['overdispersed'], (bool, np.bool_)),
                'nobs': int(out['nobs']),
                'recommended': str(out['recommended_model']),
            }))
            """
        )
        assert report["params_ndim"] == 1
        assert report["rr_ndim"] == 1
        assert report["equal_len"] is True
        assert report["disp_finite"] is True
        assert report["aic_finite"] is True
        assert report["overdispersed_is_bool"] is True
        assert report["nobs"] == 100
        assert report["recommended"] in ("poisson", "negativebinomial")

    # ------------------------------------------------------------------ L2 ---
    def test_intercept_added_and_first(self):
        """L2: with a single predictor and add_intercept=True the fit has two
        coefficients and params[0] is the intercept, matching a Poisson GLM on
        the intercept-augmented design."""
        report = _run_driver(
            """
            x, y = _poisson_counts(2, 300, 0.7, 0.6)
            out = select_count_model(y, x, add_intercept=True)
            p = np.asarray(out['params'], dtype=float)

            Xc = sm.add_constant(np.asarray(x, float))
            ref = sm.GLM(np.asarray(y, float), Xc,
                         family=sm.families.Poisson()).fit()
            print(json.dumps({
                'nparams': int(p.shape[0]),
                'intercept_err': float(abs(p[0] - ref.params[0])),
                'slope_err': float(abs(p[1] - ref.params[1])),
            }))
            """
        )
        assert report["nparams"] == 2
        assert report["intercept_err"] < 1e-6
        assert report["slope_err"] < 1e-6

    def test_no_intercept_param_count(self):
        """L2: add_intercept=False on a single predictor yields exactly one
        coefficient equal to the no-constant Poisson GLM coefficient."""
        report = _run_driver(
            """
            x, y = _poisson_counts(3, 250, 0.0, 0.5)
            out = select_count_model(y, x, add_intercept=False)
            p = np.asarray(out['params'], dtype=float)

            X = np.asarray(x, float).reshape(-1, 1)
            ref = sm.GLM(np.asarray(y, float), X,
                         family=sm.families.Poisson()).fit()
            print(json.dumps({
                'nparams': int(p.shape[0]),
                'param_err': float(abs(p[0] - ref.params[0])),
            }))
            """
        )
        assert report["nparams"] == 1
        assert report["param_err"] < 1e-6

    def test_params_match_poisson_glm(self):
        """L2: on equidispersed multi-predictor data the fitted log-link
        coefficients match a direct intercept-augmented Poisson GLM to fp
        tolerance, with the intercept first."""
        report = _run_driver(
            """
            rng = np.random.RandomState(4)
            n = 400
            x1 = rng.normal(size=n)
            x2 = rng.uniform(-1, 1, size=n)
            X = np.column_stack([x1, x2])
            mu = np.exp(0.4 - 0.6 * x1 + 0.9 * x2)
            y = rng.poisson(mu)

            out = select_count_model(y, X, add_intercept=True)
            p = np.asarray(out['params'], dtype=float)

            Xc = sm.add_constant(X)
            ref = sm.GLM(y.astype(float), Xc,
                         family=sm.families.Poisson()).fit()
            print(json.dumps({
                'nparams': int(p.shape[0]),
                'param_max_abs_err': float(np.max(np.abs(p - ref.params))),
                'first_is_intercept': bool(abs(p[0] - ref.params[0]) < 1e-6),
            }))
            """
        )
        assert report["nparams"] == 3
        assert report["first_is_intercept"] is True
        assert report["param_max_abs_err"] < 1e-5

    def test_rate_ratios_are_exp_of_params(self):
        """L2: rate_ratios equal element-wise exp(params); a positive-effect
        predictor has a rate ratio > 1 and a negative-effect predictor < 1.
        (A stub returning params themselves or all-ones must fail.)"""
        report = _run_driver(
            """
            rng = np.random.RandomState(9)
            n = 500
            x1 = rng.normal(size=n)           # strong positive effect
            x2 = rng.normal(size=n)           # strong negative effect
            X = np.column_stack([x1, x2])
            mu = np.exp(0.2 + 0.8 * x1 - 0.7 * x2)
            y = rng.poisson(mu)

            out = select_count_model(y, X, add_intercept=True)
            p = np.asarray(out['params'], dtype=float)
            rr = np.asarray(out['rate_ratios'], dtype=float)
            print(json.dumps({
                'max_exp_err': float(np.max(np.abs(rr - np.exp(p)))),
                'rr_pos': float(rr[1]),   # x1 coefficient -> >1
                'rr_neg': float(rr[2]),   # x2 coefficient -> <1
                'all_ones': bool(np.allclose(rr, 1.0)),
            }))
            """
        )
        assert report["max_exp_err"] < 1e-9, "rate_ratios must equal exp(params)"
        assert report["all_ones"] is False
        assert report["rr_pos"] > 1.0
        assert report["rr_neg"] < 1.0

    def test_dispersion_near_one_for_equidispersed(self):
        """L2: equidispersed Poisson data -> dispersion close to 1.0,
        overdispersed is False and recommended_model == 'poisson'. The reported
        dispersion is consistent with the Pearson chi2 / df_resid statistic of
        the fitted Poisson GLM (the standard over-dispersion estimate)."""
        report = _run_driver(
            """
            x, y = _poisson_counts(11, 600, 0.3, 0.5)
            out = select_count_model(y, x, add_intercept=True)

            Xc = sm.add_constant(np.asarray(x, float))
            ref = sm.GLM(y.astype(float), Xc,
                         family=sm.families.Poisson()).fit()
            pearson_disp = float(ref.pearson_chi2 / ref.df_resid)
            print(json.dumps({
                'dispersion': float(out['dispersion']),
                'pearson_disp': pearson_disp,
                'overdispersed': bool(out['overdispersed']),
                'recommended': str(out['recommended_model']),
            }))
            """
        )
        # Near equidispersion: statistic should be close to 1.
        assert 0.6 < report["dispersion"] < 1.5, report
        # Consistent with the standard Pearson over-dispersion estimate.
        assert abs(report["dispersion"] - report["pearson_disp"]) < 0.2, report
        assert report["overdispersed"] is False
        assert report["recommended"] == "poisson"

    def test_overdispersed_data_recommends_negativebinomial(self):
        """L2: strongly over-dispersed counts -> dispersion well above the 1.5
        threshold, overdispersed True, recommended_model 'negativebinomial'."""
        report = _run_driver(
            """
            x, y = _overdispersed_counts(21, 600, 0.5, 0.6)
            out = select_count_model(y, x, add_intercept=True)
            # sanity: the empirical variance/mean ratio is large
            vm = float(np.var(y) / np.mean(y))
            print(json.dumps({
                'dispersion': float(out['dispersion']),
                'overdispersed': bool(out['overdispersed']),
                'recommended': str(out['recommended_model']),
                'var_mean_ratio': vm,
            }))
            """
        )
        assert report["var_mean_ratio"] > 2.0, "fixture not over-dispersed enough"
        assert report["dispersion"] > 1.5, report
        assert report["overdispersed"] is True
        assert report["recommended"] == "negativebinomial"

    def test_aic_tracks_recommended_model(self):
        """L2: the reported aic is the AIC of the *recommended* model. For
        equidispersed data it matches the Poisson AIC; for over-dispersed data
        it matches the Negative-Binomial AIC and is strictly lower than the
        Poisson AIC on the same design (so a stub that always reports Poisson
        AIC fails)."""
        report = _run_driver(
            """
            res = {}

            # equidispersed -> poisson AIC
            xe, ye = _poisson_counts(31, 500, 0.3, 0.5)
            oe = select_count_model(ye, xe, add_intercept=True)
            Xe = sm.add_constant(np.asarray(xe, float))
            pois_e = Poisson(ye.astype(float), Xe).fit(disp=0)
            res['eq_aic'] = float(oe['aic'])
            res['eq_pois_aic'] = float(pois_e.aic)
            res['eq_recommended'] = str(oe['recommended_model'])

            # overdispersed -> negativebinomial AIC, below poisson AIC
            xo, yo = _overdispersed_counts(32, 600, 0.5, 0.6)
            oo = select_count_model(yo, xo, add_intercept=True)
            Xo = sm.add_constant(np.asarray(xo, float))
            pois_o = Poisson(yo.astype(float), Xo).fit(disp=0)
            nb_o = NegativeBinomial(yo.astype(float), Xo).fit(disp=0)
            res['od_aic'] = float(oo['aic'])
            res['od_pois_aic'] = float(pois_o.aic)
            res['od_nb_aic'] = float(nb_o.aic)
            res['od_recommended'] = str(oo['recommended_model'])
            print(json.dumps(res))
            """
        )
        # Equidispersed: reported AIC is the Poisson AIC.
        assert report["eq_recommended"] == "poisson"
        assert abs(report["eq_aic"] - report["eq_pois_aic"]) < 1e-3, report
        # Overdispersed: reported AIC is the NB AIC, not the Poisson AIC.
        assert report["od_recommended"] == "negativebinomial"
        assert abs(report["od_aic"] - report["od_nb_aic"]) < 1.0, report
        # NB must genuinely fit the heavier tail better here.
        assert report["od_nb_aic"] < report["od_pois_aic"], report
        # The reported AIC must NOT be the Poisson AIC for the overdispersed set.
        assert abs(report["od_aic"] - report["od_pois_aic"]) > 1.0, report

    def test_params_exclude_nb_dispersion_alpha(self):
        """L2: even when negativebinomial is recommended, 'params' holds only the
        log-link regression coefficients (intercept + k columns), NOT the extra
        NB dispersion 'alpha'. statsmodels' NB result appends alpha as a final
        parameter; the report must drop it."""
        report = _run_driver(
            """
            rng = np.random.RandomState(33)
            n = 600
            x1 = rng.normal(size=n)
            x2 = rng.uniform(-1, 1, size=n)
            X = np.column_stack([x1, x2])
            mu = np.exp(0.5 - 0.4 * x1 + 0.8 * x2)
            shape = 0.4
            lam = rng.gamma(shape=shape, scale=mu / shape)
            y = rng.poisson(lam)

            out = select_count_model(y, X, add_intercept=True)
            p = np.asarray(out['params'], dtype=float)

            Xc = sm.add_constant(X)
            nb = NegativeBinomial(y.astype(float), Xc).fit(disp=0)
            print(json.dumps({
                'recommended': str(out['recommended_model']),
                'nparams': int(p.shape[0]),
                'ncols_with_intercept': int(Xc.shape[1]),
                'nb_param_len': int(len(nb.params)),
                'coef_max_err': float(np.max(np.abs(p - nb.params[:Xc.shape[1]]))),
            }))
            """
        )
        assert report["recommended"] == "negativebinomial"
        # NB result has one extra parameter (alpha) beyond the design columns.
        assert report["nb_param_len"] == report["ncols_with_intercept"] + 1
        # The report must expose only the regression coefficients.
        assert report["nparams"] == report["ncols_with_intercept"], report
        assert report["coef_max_err"] < 1e-3, report

    def test_existing_constant_column_not_duplicated(self):
        """L2: add_intercept=True with an exog that already has a constant column
        must not add a second constant; the fit stays full-rank and the number
        of coefficients equals the supplied columns (has_constant='skip')."""
        report = _run_driver(
            """
            rng = np.random.RandomState(7)
            n = 400
            ones = np.ones(n)
            x = rng.normal(size=n)
            X = np.column_stack([ones, x])   # already contains a constant column
            mu = np.exp(0.6 + 0.5 * x)
            y = rng.poisson(mu)

            out = select_count_model(y, X, add_intercept=True)
            p = np.asarray(out['params'], dtype=float)

            Xc = sm.add_constant(X, has_constant='skip')
            ref = sm.GLM(y.astype(float), Xc,
                         family=sm.families.Poisson()).fit()
            print(json.dumps({
                'nparams': int(p.shape[0]),
                'ncols': int(X.shape[1]),
                'has_nan': bool(np.any(np.isnan(p))),
                'param_err': float(np.max(np.abs(np.sort(p) - np.sort(ref.params)))),
            }))
            """
        )
        assert report["nparams"] == report["ncols"], (
            "duplicate constant was added: %d params for %d supplied columns"
            % (report["nparams"], report["ncols"])
        )
        assert report["has_nan"] is False
        assert report["param_err"] < 1e-5, report

    def test_accepts_lists_and_1d_exog(self):
        """L2: plain Python lists and a 1-D exog (single column) are accepted and
        produce the same numeric report as the equivalent ndarray 2-D call."""
        report = _run_driver(
            """
            x, y = _poisson_counts(8, 200, 0.3, 0.5)
            x_list = [float(v) for v in x]
            y_list = [int(v) for v in y]

            out_list = select_count_model(y_list, x_list, add_intercept=True)
            out_arr = select_count_model(
                np.asarray(y), np.asarray(x, float).reshape(-1, 1),
                add_intercept=True)

            pl = np.asarray(out_list['params'], dtype=float)
            pa = np.asarray(out_arr['params'], dtype=float)
            print(json.dumps({
                'list_nparams': int(pl.shape[0]),
                'param_err': float(np.max(np.abs(pl - pa))),
                'disp_err': abs(float(out_list['dispersion'])
                                - float(out_arr['dispersion'])),
                'nobs': int(out_list['nobs']),
            }))
            """
        )
        assert report["list_nparams"] == 2  # intercept + single column
        assert report["nobs"] == 200
        assert report["param_err"] < 1e-8
        assert report["disp_err"] < 1e-8

    def test_threshold_controls_recommendation(self):
        """L2: dispersion_threshold genuinely drives the recommendation. On
        equidispersed data a very low threshold flips overdispersed to True and
        recommends negativebinomial, while the default keeps poisson. (A stub
        that hardcodes the recommendation or ignores the threshold must fail.)"""
        report = _run_driver(
            """
            x, y = _poisson_counts(41, 600, 0.3, 0.5)
            default = select_count_model(y, x, add_intercept=True)
            low = select_count_model(y, x, add_intercept=True,
                                     dispersion_threshold=0.01)
            high = select_count_model(y, x, add_intercept=True,
                                      dispersion_threshold=100.0)
            print(json.dumps({
                'disp': float(default['dispersion']),
                'default_over': bool(default['overdispersed']),
                'default_rec': str(default['recommended_model']),
                'low_over': bool(low['overdispersed']),
                'low_rec': str(low['recommended_model']),
                'high_over': bool(high['overdispersed']),
                'high_rec': str(high['recommended_model']),
            }))
            """
        )
        # default threshold (1.5) -> equidispersed stays poisson
        assert report["default_over"] is False
        assert report["default_rec"] == "poisson"
        # threshold below the (~1) dispersion -> flips to NB
        assert report["low_over"] is True
        assert report["low_rec"] == "negativebinomial"
        # huge threshold -> never overdispersed
        assert report["high_over"] is False
        assert report["high_rec"] == "poisson"

    def test_native_pytest_passes(self):
        """L2: the variant's native acceptance command passes
        (pytest statsmodels/genmod/tests/test_count_selector.py)."""
        if not os.path.isfile(self.TEST_PATH):
            pytest.skip("deliverable test module not present: " + self.TEST_PATH)
        proc = subprocess.run(
            [
                sys.executable, "-m", "pytest",
                os.path.join(
                    "statsmodels", "genmod", "tests",
                    "test_count_selector.py",
                ),
                "-q",
            ],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=900,
            env={k: v for k, v in os.environ.items() if k != "PYTHONPATH"},
        )
        assert proc.returncode == 0, (
            "native pytest failed\nSTDOUT:\n"
            + proc.stdout[-4000:]
            + "\nSTDERR:\n"
            + proc.stderr[-2000:]
        )
