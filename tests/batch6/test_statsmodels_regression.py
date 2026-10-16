"""Tests for the ``statsmodels-regression`` skill (variant ext6).

Variant task: a heteroskedasticity-aware standard-error helper. The agent must
create ``statsmodels/regression/robust_se_helper.py`` exposing the public
function::

    fit_with_appropriate_se(endog, exog, add_intercept=True, alpha=0.05)

which fits an ordinary linear model from raw arrays, tests the residuals for
non-constant error variance, and returns a plain ``dict`` whose coefficient
inference (``bse`` / ``pvalues`` / ``cov_type``) is *classical* when the errors
look homoskedastic and *heteroskedasticity-consistent* when they do not.
Required keys: ``params``, ``het_pvalue``, ``heteroskedastic``, ``cov_type``,
``bse``, ``pvalues``, ``nobs``.

Verification strategy
---------------------
This is deliberately DIFFERENT from the ext1 variant (which produced a
``regression_report.py`` diagnostics dict). Here we drive the doc's own native
acceptance command::

    pytest statsmodels/regression/tests/test_robust_se_helper.py -q

and, more importantly, inject an INDEPENDENT verification harness: every L2 case
re-derives the expected quantities from statsmodels' own OLS machinery in a
fresh subprocess and compares to floating-point tolerance, so the agent cannot
satisfy the test by hardcoding numbers, returning a fixed covariance type, or
ignoring the heteroskedasticity decision.

Discriminative cases the test pins down:
  * ``params`` must equal the intercept-augmented OLS coefficients (a stub that
    returns zeros / wrong design fails).
  * ``params`` must be IDENTICAL whether or not robust SEs are chosen (a helper
    that mistakenly refits with robust weights for the point estimates fails).
  * On homoskedastic data: ``heteroskedastic is False``, ``cov_type ==
    'nonrobust'``, and ``bse`` equals the CLASSICAL OLS standard errors.
  * On data whose spread grows with a predictor: ``heteroskedastic is True``,
    ``cov_type`` is an HC identifier, and ``bse`` equals the robust SEs of
    ``OLS(...).fit(cov_type=<reported>)`` while DIFFERING from the classical
    ones (a helper that always reports nonrobust SEs fails here).
  * ``het_pvalue`` matches a real statsmodels heteroskedasticity LM test
    (Breusch-Pagan or White) on the model's exog.
  * ``heteroskedastic`` is exactly ``het_pvalue < alpha`` (alpha threshold is
    honoured, not hardcoded to 0.05).
  * ``pvalues`` are recomputed from ``params`` and ``bse`` (two-sided t), so
    they shift when robust SEs are used.

L1 cases (file exists, importable signature, dict + key/type shape) are cheap;
L2 cases run the helper in a subprocess that prints a single JSON line and
compare against an in-subprocess reference statsmodels computation.
"""

import json
import os
import subprocess
import sys
import textwrap

import pytest

REPO_DIR = "/workspace/statsmodels"


# Bootstrap prepended to every driver script: import numpy, statsmodels and the
# agent's helper from REPO_DIR with PYTHONPATH cleared, so the test is robust to
# import-time side effects and stray sys.path entries.
_BOOTSTRAP = textwrap.dedent(
    """
    import sys, os, json
    REPO_DIR = {repo!r}
    sys.path.insert(0, REPO_DIR)
    import numpy as np
    import statsmodels.api as sm
    from statsmodels.regression.robust_se_helper import fit_with_appropriate_se
    """
).format(repo=REPO_DIR)


def _run_driver(body, timeout=300):
    """Execute *body* (which must print one JSON object as its last stdout line)
    in a fresh interpreter rooted at REPO_DIR. Returns the parsed JSON dict."""
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
        REPO_DIR, "statsmodels", "regression", "robust_se_helper.py"
    )
    TEST_PATH = os.path.join(
        REPO_DIR,
        "statsmodels",
        "regression",
        "tests",
        "test_robust_se_helper.py",
    )

    # ------------------------------------------------------------------ L1 ---
    def test_module_file_exists(self):
        """L1: the new robust_se_helper.py deliverable exists and is non-trivial."""
        assert os.path.isfile(self.MODULE_PATH), (
            "expected new module at " + self.MODULE_PATH
        )
        assert os.path.getsize(self.MODULE_PATH) > 0

    def test_function_importable_with_signature(self):
        """L1: fit_with_appropriate_se is importable and exposes the exact
        signature (endog, exog, add_intercept=True, alpha=0.05)."""
        report = _run_driver(
            """
            import inspect
            sig = inspect.signature(fit_with_appropriate_se)
            params = list(sig.parameters)
            ai = sig.parameters.get('add_intercept')
            al = sig.parameters.get('alpha')
            print(json.dumps({
                'params': params,
                'add_intercept_default': (ai.default if ai is not None else None),
                'alpha_default': (al.default if al is not None else None),
            }))
            """
        )
        assert report["params"][:2] == ["endog", "exog"], report["params"]
        assert "add_intercept" in report["params"]
        assert "alpha" in report["params"]
        assert report["add_intercept_default"] is True
        assert abs(float(report["alpha_default"]) - 0.05) < 1e-12

    def test_returns_dict_with_required_keys(self):
        """L1: the helper returns a plain dict containing every documented key."""
        report = _run_driver(
            """
            x = np.linspace(0, 10, 30)
            y = 1.0 + 2.0 * x
            out = fit_with_appropriate_se(list(y), list(x))
            print(json.dumps({
                'is_dict': type(out).__name__ == 'dict',
                'keys': sorted(out.keys()),
            }))
            """
        )
        assert report["is_dict"] is True, "must return a plain dict"
        required = {
            "params", "het_pvalue", "heteroskedastic",
            "cov_type", "bse", "pvalues", "nobs",
        }
        missing = required - set(report["keys"])
        assert not missing, "missing keys: " + str(sorted(missing))

    def test_scalar_key_types(self):
        """L1: het_pvalue is a float in [0,1], heteroskedastic is a bool,
        cov_type is a str, and nobs is an integer equal to the sample size."""
        report = _run_driver(
            """
            rng = np.random.RandomState(0)
            x = np.linspace(0, 5, 25)
            y = 0.5 + 1.5 * x + rng.normal(scale=0.3, size=25)
            out = fit_with_appropriate_se(y, x)
            hp = out['het_pvalue']
            print(json.dumps({
                'hp_is_float': isinstance(hp, float),
                'hp_in_range': bool(0.0 <= float(hp) <= 1.0),
                'het_is_bool': isinstance(out['heteroskedastic'], bool),
                'cov_is_str': isinstance(out['cov_type'], str),
                'nobs_int': bool(float(out['nobs']) == int(out['nobs'])),
                'nobs': int(out['nobs']),
            }))
            """
        )
        assert report["hp_is_float"] is True
        assert report["hp_in_range"] is True
        assert report["het_is_bool"] is True
        assert report["cov_is_str"] is True
        assert report["nobs_int"] is True
        assert report["nobs"] == 25

    # ------------------------------------------------------------------ L2 ---
    def test_params_match_intercept_augmented_ols(self):
        """L2: with add_intercept=True the returned params equal the coefficients
        of sm.OLS on the intercept-augmented design (intercept first), to fp
        tolerance. A stub returning zeros / the wrong design fails."""
        report = _run_driver(
            """
            rng = np.random.RandomState(3)
            n = 60
            x1 = rng.normal(size=n)
            x2 = rng.uniform(-2, 2, size=n)
            X = np.column_stack([x1, x2])
            y = 1.3 - 2.0 * x1 + 0.7 * x2 + rng.normal(scale=0.5, size=n)

            out = fit_with_appropriate_se(y, X, add_intercept=True)
            params = np.asarray(out['params'], dtype=float)

            ref = sm.OLS(y, sm.add_constant(X)).fit()
            print(json.dumps({
                'nparams': int(params.shape[0]),
                'param_max_abs_err': float(np.max(np.abs(params - ref.params))),
                'first_is_intercept': bool(abs(params[0] - ref.params[0]) < 1e-8),
            }))
            """
        )
        assert report["nparams"] == 3  # intercept + 2 columns
        assert report["first_is_intercept"] is True
        assert report["param_max_abs_err"] < 1e-8

    def test_no_intercept_param_count_and_values(self):
        """L2: add_intercept=False on a single predictor -> len(params)==1 and the
        single coefficient matches no-constant OLS exactly."""
        report = _run_driver(
            """
            rng = np.random.RandomState(2)
            x = np.linspace(1, 6, 24)
            y = 2.7 * x + rng.normal(scale=0.4, size=24)
            out = fit_with_appropriate_se(y, x, add_intercept=False)
            params = np.asarray(out['params'], dtype=float)
            ref = sm.OLS(np.asarray(y, float),
                         np.asarray(x, float).reshape(-1, 1)).fit()
            print(json.dumps({
                'nparams': int(params.shape[0]),
                'nobs': int(out['nobs']),
                'param_err': float(abs(params[0] - ref.params[0])),
            }))
            """
        )
        assert report["nparams"] == 1
        assert report["nobs"] == 24
        assert report["param_err"] < 1e-8

    def test_homoskedastic_branch_uses_classical_se(self):
        """L2: on clean constant-variance data the helper reports
        heteroskedastic=False, cov_type=='nonrobust', and bse equals the
        CLASSICAL OLS standard errors (not a robust estimator)."""
        report = _run_driver(
            """
            rng = np.random.RandomState(12)
            n = 200
            x = np.linspace(0, 10, n)
            y = 1.0 + 2.0 * x + rng.normal(scale=0.5, size=n)

            out = fit_with_appropriate_se(y, x, add_intercept=True)
            bse = np.asarray(out['bse'], dtype=float)

            ref = sm.OLS(y, sm.add_constant(x)).fit()
            print(json.dumps({
                'het': bool(out['heteroskedastic']),
                'cov_type': str(out['cov_type']),
                'bse_max_abs_err': float(np.max(np.abs(bse - ref.bse))),
                'het_p': float(out['het_pvalue']),
            }))
            """
        )
        assert report["het_p"] > 0.05, report
        assert report["het"] is False, report
        assert report["cov_type"] == "nonrobust", report
        assert report["bse_max_abs_err"] < 1e-9, (
            "homoskedastic bse must equal classical OLS bse; got max abs err %r"
            % report["bse_max_abs_err"]
        )

    def test_heteroskedastic_branch_uses_robust_se(self):
        """L2: on data whose error spread grows with a predictor the helper
        reports heteroskedastic=True with an HC cov_type, and bse equals the
        robust SEs of OLS.fit(cov_type=<reported>) while DIFFERING materially
        from the classical SEs. A helper that always returns nonrobust SEs fails
        the 'differs from classical' check."""
        report = _run_driver(
            """
            rng = np.random.RandomState(5)
            n = 300
            x = np.linspace(0.5, 10, n)
            y = 1.0 + 2.0 * x + rng.normal(scale=0.05 + 0.9 * x, size=n)

            out = fit_with_appropriate_se(y, x, add_intercept=True)
            bse = np.asarray(out['bse'], dtype=float)
            cov_type = str(out['cov_type'])

            Xc = sm.add_constant(x)
            classical = sm.OLS(y, Xc).fit()
            robust = sm.OLS(y, Xc).fit(cov_type=cov_type)

            print(json.dumps({
                'het': bool(out['heteroskedastic']),
                'cov_type': cov_type,
                'het_p': float(out['het_pvalue']),
                'bse_vs_robust_err': float(np.max(np.abs(bse - robust.bse))),
                'bse_vs_classical_diff': float(np.max(np.abs(bse - classical.bse))),
            }))
            """
        )
        assert report["het_p"] < 0.05, report
        assert report["het"] is True, report
        assert report["cov_type"].upper().startswith("HC"), (
            "robust cov_type must be a heteroskedasticity-consistent identifier; "
            "got %r" % report["cov_type"]
        )
        assert report["bse_vs_robust_err"] < 1e-8, (
            "bse must match OLS.fit(cov_type=%r).bse" % report["cov_type"]
        )
        assert report["bse_vs_classical_diff"] > 1e-4, (
            "robust bse must differ from classical bse (helper appears to ignore "
            "the heteroskedasticity decision)"
        )

    def test_params_invariant_to_covariance_choice(self):
        """L2: point estimates must NOT depend on the covariance choice. Fitting
        the same data and comparing the heteroskedastic-branch params to a plain
        OLS fit on the same design must agree exactly; robust SEs change only
        bse/pvalues, never params."""
        report = _run_driver(
            """
            rng = np.random.RandomState(21)
            n = 250
            x = np.linspace(0.5, 8, n)
            y = -0.5 + 1.7 * x + rng.normal(scale=0.05 + 0.8 * x, size=n)

            out = fit_with_appropriate_se(y, x, add_intercept=True)
            params = np.asarray(out['params'], dtype=float)

            Xc = sm.add_constant(x)
            classical = sm.OLS(y, Xc).fit()
            robust = sm.OLS(y, Xc).fit(cov_type=str(out['cov_type']))
            print(json.dumps({
                'het': bool(out['heteroskedastic']),
                'err_vs_classical': float(np.max(np.abs(params - classical.params))),
                'err_vs_robust_params': float(np.max(np.abs(params - robust.params))),
                'classical_vs_robust': float(np.max(np.abs(classical.params - robust.params))),
            }))
            """
        )
        # this dataset is heteroskedastic, so the robust branch is exercised
        assert report["het"] is True, report
        assert report["err_vs_classical"] < 1e-8, report
        assert report["err_vs_robust_params"] < 1e-8, report
        # sanity: statsmodels itself keeps params identical across cov_type
        assert report["classical_vs_robust"] < 1e-10, report

    def test_het_pvalue_matches_a_real_het_test(self):
        """L2: het_pvalue equals a genuine statsmodels heteroskedasticity LM
        p-value (Breusch-Pagan or White) computed on the model's residuals and
        intercept-augmented exog. Accepts whichever of the two the agent chose,
        but rejects a fabricated/hardcoded value."""
        report = _run_driver(
            """
            from statsmodels.stats.diagnostic import het_breuschpagan, het_white
            rng = np.random.RandomState(4)
            n = 120
            x = rng.uniform(0, 10, size=n)
            y = 2.0 + 1.5 * x + rng.normal(scale=0.2 + 0.4 * x, size=n)

            out = fit_with_appropriate_se(y, x, add_intercept=True)
            hp = float(out['het_pvalue'])

            Xc = sm.add_constant(x)
            ref = sm.OLS(y, Xc).fit()
            bp_p = float(het_breuschpagan(ref.resid, Xc)[1])
            try:
                w_p = float(het_white(ref.resid, Xc)[1])
            except Exception:
                w_p = None
            print(json.dumps({
                'hp': hp,
                'in_range': bool(0.0 <= hp <= 1.0),
                'matches_bp': abs(hp - bp_p) < 1e-7,
                'matches_white': (w_p is not None and abs(hp - w_p) < 1e-7),
                'bp_p': bp_p,
                'w_p': w_p,
            }))
            """
        )
        assert report["in_range"] is True
        assert report["matches_bp"] or report["matches_white"], (
            "het_pvalue %r matches neither Breusch-Pagan %r nor White %r"
            % (report["hp"], report["bp_p"], report["w_p"])
        )

    def test_heteroskedastic_flag_honours_alpha(self):
        """L2: heteroskedastic is exactly (het_pvalue < alpha). On the same data,
        an alpha strictly below het_pvalue must yield False while an alpha above
        it yields True -- so the threshold is the supplied alpha, not a hardcoded
        0.05. Uses moderately heteroskedastic data with a mid-range p-value."""
        report = _run_driver(
            """
            rng = np.random.RandomState(31)
            n = 60
            x = np.linspace(0, 10, n)
            y = 1.0 + 2.0 * x + rng.normal(scale=0.4 + 0.25 * x, size=n)

            base = fit_with_appropriate_se(y, x, add_intercept=True)
            p = float(base['het_pvalue'])
            lo = max(p / 2.0, 1e-6)          # alpha below p  -> not significant
            hi = min(p + (1.0 - p) / 2.0, 1.0)  # alpha above p -> significant

            out_lo = fit_with_appropriate_se(y, x, add_intercept=True, alpha=lo)
            out_hi = fit_with_appropriate_se(y, x, add_intercept=True, alpha=hi)
            print(json.dumps({
                'p': p,
                'flag_lo': bool(out_lo['heteroskedastic']),
                'cov_lo': str(out_lo['cov_type']),
                'flag_hi': bool(out_hi['heteroskedastic']),
                'cov_hi': str(out_hi['cov_type']),
            }))
            """
        )
        assert 0.0 < report["p"] < 1.0, report
        assert report["flag_lo"] is False, report
        assert report["cov_lo"] == "nonrobust", report
        assert report["flag_hi"] is True, report
        assert report["cov_hi"].upper().startswith("HC"), report

    def test_pvalues_recomputed_from_params_and_bse(self):
        """L2: pvalues are two-sided t p-values derived from params/bse, so they
        track the robust bse. We re-derive them independently from the reported
        params and bse (t = param/bse, df = nobs - nparams) and require a match,
        and confirm they equal the robust fit's pvalues -- not the classical
        ones -- under detected heteroskedasticity."""
        report = _run_driver(
            """
            from scipy import stats as scs
            rng = np.random.RandomState(5)
            n = 300
            x = np.linspace(0.5, 10, n)
            y = 1.0 + 2.0 * x + rng.normal(scale=0.05 + 0.9 * x, size=n)

            out = fit_with_appropriate_se(y, x, add_intercept=True)
            params = np.asarray(out['params'], dtype=float)
            bse = np.asarray(out['bse'], dtype=float)
            pvals = np.asarray(out['pvalues'], dtype=float)
            nobs = int(out['nobs'])
            df = nobs - params.shape[0]
            tval = params / bse
            manual = 2.0 * scs.t.sf(np.abs(tval), df)

            Xc = sm.add_constant(x)
            classical = sm.OLS(y, Xc).fit()
            robust = sm.OLS(y, Xc).fit(cov_type=str(out['cov_type']))
            print(json.dumps({
                'het': bool(out['heteroskedastic']),
                'manual_err': float(np.max(np.abs(pvals - manual))),
                'err_vs_robust': float(np.max(np.abs(pvals - robust.pvalues))),
                'diff_vs_classical': float(np.max(np.abs(pvals - classical.pvalues))),
            }))
            """
        )
        assert report["het"] is True, report
        # pvalues consistent with t-distribution on reported params/bse
        assert report["manual_err"] < 1e-6, report
        # and they equal the robust fit's pvalues, not the classical ones
        assert report["err_vs_robust"] < 1e-6, report
        assert report["diff_vs_classical"] > 1e-6, report

    def test_accepts_lists_and_1d_exog(self):
        """L2: plain Python lists and a 1-D exog (single column) are accepted and
        give the same numeric report as the equivalent ndarray 2-D call."""
        report = _run_driver(
            """
            rng = np.random.RandomState(8)
            x = list(np.linspace(0, 3, 30))
            y = list(0.4 + 1.1 * np.asarray(x) + rng.normal(scale=0.2, size=30))

            out_list = fit_with_appropriate_se(y, x, add_intercept=True)
            out_arr = fit_with_appropriate_se(
                np.asarray(y), np.asarray(x).reshape(-1, 1), add_intercept=True)

            pl = np.asarray(out_list['params'], dtype=float)
            pa = np.asarray(out_arr['params'], dtype=float)
            bl = np.asarray(out_list['bse'], dtype=float)
            ba = np.asarray(out_arr['bse'], dtype=float)
            print(json.dumps({
                'list_nparams': int(pl.shape[0]),
                'param_err': float(np.max(np.abs(pl - pa))),
                'bse_err': float(np.max(np.abs(bl - ba))),
                'nobs': int(out_list['nobs']),
            }))
            """
        )
        assert report["list_nparams"] == 2  # intercept + single column
        assert report["nobs"] == 30
        assert report["param_err"] < 1e-12
        assert report["bse_err"] < 1e-12

    def test_existing_constant_column_not_duplicated(self):
        """L2: add_intercept=True with an exog that already contains a constant
        column must not add a second redundant constant; the design stays
        full-rank, params count equals the supplied columns, and the fit matches
        sm.add_constant(..., has_constant='skip')."""
        report = _run_driver(
            """
            rng = np.random.RandomState(7)
            n = 80
            ones = np.ones(n)
            x = rng.normal(size=n)
            X = np.column_stack([ones, x])  # already has a constant column
            y = 2.0 + 3.0 * x + rng.normal(scale=0.4, size=n)

            out = fit_with_appropriate_se(y, X, add_intercept=True)
            params = np.asarray(out['params'], dtype=float)

            Xc = sm.add_constant(X, has_constant='skip')
            ref = sm.OLS(y, Xc).fit()
            print(json.dumps({
                'nparams': int(params.shape[0]),
                'ncols': int(X.shape[1]),
                'has_nan': bool(np.any(np.isnan(params))),
                'param_err': float(np.max(np.abs(np.sort(params) - np.sort(ref.params)))),
            }))
            """
        )
        assert report["nparams"] == report["ncols"], (
            "duplicate constant was added: %d params for %d supplied columns"
            % (report["nparams"], report["ncols"])
        )
        assert report["has_nan"] is False
        assert report["param_err"] < 1e-8

    def test_native_pytest_passes(self):
        """L2: the doc's native acceptance command passes -- the deliverable's own
        unit tests (pytest statsmodels/regression/tests/test_robust_se_helper.py)."""
        if not os.path.isfile(self.TEST_PATH):
            pytest.skip("deliverable test module not present: " + self.TEST_PATH)
        proc = subprocess.run(
            [
                sys.executable, "-m", "pytest",
                os.path.join(
                    "statsmodels", "regression", "tests",
                    "test_robust_se_helper.py",
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
