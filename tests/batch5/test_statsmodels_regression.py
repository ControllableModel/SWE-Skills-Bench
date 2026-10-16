"""Tests for the ``statsmodels-regression`` skill (variant ext5).

Variant task: a *nested-model comparison helper*. The deliverable is a new
module ``statsmodels/stats/model_comparison.py`` exporting a single public
function::

    compare_models(reduced_results, full_results, nested=True, alpha=0.05)

``reduced_results`` / ``full_results`` are fitted OLS results objects on the
**same** outcome where the reduced model uses a subset of the full model's
columns. The function returns a plain ``dict`` carrying:

  * ``"aic"`` / ``"bic"``  -> dicts ``{"reduced": ..., "full": ...}`` equal to
    the ``.aic`` / ``.bic`` attributes of the supplied results.
  * ``"preferred_by_aic"`` / ``"preferred_by_bic"`` -> ``"reduced"`` or
    ``"full"`` naming the model with the *lower* criterion.
  * When ``nested=True`` additionally ``"lr_stat"`` (non-negative float),
    ``"lr_df"`` (positive int = parameter-count difference), ``"lr_pvalue"``
    (chi-square p-value) and ``"full_significant"`` (bool, ``lr_pvalue < alpha``).
  * When ``nested=False`` those four keys are *absent*.
  * Mismatched sample sizes -> ``ValueError``.

Verification strategy
---------------------
L1 cases check the deliverable file exists, the function imports with the exact
signature/defaults, returns a plain ``dict`` with the documented keys/types, and
that ``nested=False`` suppresses the LR keys.

L2 cases independently re-derive every reported quantity from statsmodels'
own machinery -- ``.aic`` / ``.bic`` attributes and a likelihood-ratio test
computed directly from the two results' log-likelihoods and parameter counts
(cross-checked against ``RegressionResults.compare_lr_test`` which returns
``(lr_stat, p_value, df_diff)``) -- and assert agreement to floating-point
tolerance. They plant a genuinely predictive extra column (LR significant,
AIC prefers full) versus a pure-noise extra column (LR insignificant) to give
sign discrimination, and assert the ``ValueError`` path. A naive implementation
that hardcodes numbers, ignores ``nested``, copies AIC/BIC blindly, or fabricates
an LR test cannot satisfy these checks.

The deliverable's own native acceptance command
``pytest statsmodels/stats/tests/test_model_comparison.py -q`` is also driven.

Each L2 driver runs in a fresh interpreter rooted at REPO_DIR with PYTHONPATH
cleared, emitting a single JSON object, so the test is robust to import-time
side effects and stray sys.path entries.
"""

import json
import os
import subprocess
import sys
import textwrap

import pytest

REPO_DIR = "/workspace/statsmodels"


# Bootstrap importing numpy, statsmodels, scipy.stats, and the agent's helper
# from REPO_DIR. Each driver prepends this so it can run from anywhere with
# PYTHONPATH cleared. Also defines a reference fit pair builder.
_BOOTSTRAP = textwrap.dedent(
    """
    import sys, os, json
    REPO_DIR = {repo!r}
    sys.path.insert(0, REPO_DIR)
    import numpy as np
    import statsmodels.api as sm
    from scipy import stats
    from statsmodels.stats.model_comparison import compare_models

    def _fit_pair(seed=0, n=80, full_predictive=True, noise=0.5):
        '''Build a reduced (intercept + x1) and a full (intercept + x1 + x2)
        OLS fit on the SAME outcome. If full_predictive, x2 truly drives y;
        otherwise x2 is unrelated noise.'''
        rng = np.random.RandomState(seed)
        x1 = rng.normal(size=n)
        x2 = rng.normal(size=n)
        if full_predictive:
            y = 1.0 + 2.0 * x1 + 3.0 * x2 + rng.normal(scale=noise, size=n)
        else:
            y = 1.0 + 2.0 * x1 + rng.normal(scale=noise, size=n)
        Xr = sm.add_constant(x1.reshape(-1, 1))
        Xf = sm.add_constant(np.column_stack([x1, x2]))
        reduced = sm.OLS(y, Xr).fit()
        full = sm.OLS(y, Xf).fit()
        return reduced, full
    """
).format(repo=REPO_DIR)


def _run_driver(body, timeout=300):
    """Execute *body* (which must print a single JSON object on its last
    stdout line) in a fresh interpreter rooted at REPO_DIR. Returns the
    parsed JSON dict."""
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
        REPO_DIR, "statsmodels", "stats", "model_comparison.py"
    )
    TEST_PATH = os.path.join(
        REPO_DIR, "statsmodels", "stats", "tests", "test_model_comparison.py"
    )

    # ------------------------------------------------------------------ L1 ---
    def test_module_file_exists(self):
        """L1: the new model_comparison.py deliverable exists and is non-trivial."""
        assert os.path.isfile(self.MODULE_PATH), (
            "expected new module at " + self.MODULE_PATH
        )
        assert os.path.getsize(self.MODULE_PATH) > 0

    def test_function_importable_with_signature(self):
        """L1: compare_models imports with params (reduced_results, full_results,
        nested, alpha) and the documented defaults nested=True, alpha=0.05."""
        report = _run_driver(
            """
            import inspect
            sig = inspect.signature(compare_models)
            params = list(sig.parameters)
            nested_def = (
                sig.parameters['nested'].default
                if 'nested' in sig.parameters else '__missing__'
            )
            alpha_def = (
                sig.parameters['alpha'].default
                if 'alpha' in sig.parameters else '__missing__'
            )
            print(json.dumps({
                'params': params,
                'nested_default': nested_def,
                'alpha_default': alpha_def,
            }))
            """
        )
        assert report["params"][:2] == ["reduced_results", "full_results"], (
            report["params"]
        )
        assert "nested" in report["params"]
        assert "alpha" in report["params"]
        assert report["nested_default"] is True
        assert report["alpha_default"] == 0.05

    def test_returns_dict_with_required_keys(self):
        """L1: nested=True returns a plain dict containing every documented key
        with the right container/leaf types."""
        report = _run_driver(
            """
            reduced, full = _fit_pair(seed=1)
            out = compare_models(reduced, full, nested=True)
            aic, bic = out.get('aic'), out.get('bic')
            print(json.dumps({
                'is_dict': type(out).__name__ == 'dict',
                'keys': sorted(out.keys()),
                'aic_is_dict': isinstance(aic, dict),
                'bic_is_dict': isinstance(bic, dict),
                'aic_subkeys': sorted(aic.keys()) if isinstance(aic, dict) else None,
                'bic_subkeys': sorted(bic.keys()) if isinstance(bic, dict) else None,
                'pref_aic_is_str': isinstance(out.get('preferred_by_aic'), str),
                'pref_bic_is_str': isinstance(out.get('preferred_by_bic'), str),
                'full_sig_is_bool': isinstance(out.get('full_significant'), bool),
            }))
            """
        )
        assert report["is_dict"] is True, "must return a plain dict"
        required = {
            "aic", "bic", "preferred_by_aic", "preferred_by_bic",
            "lr_stat", "lr_df", "lr_pvalue", "full_significant",
        }
        missing = required - set(report["keys"])
        assert not missing, "missing keys: " + str(sorted(missing))
        assert report["aic_is_dict"] and report["bic_is_dict"]
        assert report["aic_subkeys"] == ["full", "reduced"]
        assert report["bic_subkeys"] == ["full", "reduced"]
        assert report["pref_aic_is_str"] and report["pref_bic_is_str"]
        assert report["full_sig_is_bool"], "full_significant must be a real bool"

    def test_nested_false_omits_lr_keys(self):
        """L1: nested=False returns ONLY the AIC/BIC comparison keys; the four
        likelihood-ratio keys must be absent (no fabricated LR test)."""
        report = _run_driver(
            """
            reduced, full = _fit_pair(seed=2)
            out = compare_models(reduced, full, nested=False)
            print(json.dumps({
                'keys': sorted(out.keys()),
                'is_dict': type(out).__name__ == 'dict',
            }))
            """
        )
        assert report["is_dict"] is True
        keys = set(report["keys"])
        lr_keys = {"lr_stat", "lr_df", "lr_pvalue", "full_significant"}
        leaked = lr_keys & keys
        assert not leaked, "nested=False must not emit LR keys: " + str(sorted(leaked))
        # AIC/BIC comparison keys must still be present.
        for k in ("aic", "bic", "preferred_by_aic", "preferred_by_bic"):
            assert k in keys, "missing comparison key under nested=False: " + k

    # ------------------------------------------------------------------ L2 ---
    def test_aic_bic_values_match_results_attributes(self):
        """L2: the reported aic/bic dicts equal the .aic/.bic attributes of the
        supplied reduced/full results to fp tolerance (no hardcoding)."""
        report = _run_driver(
            """
            reduced, full = _fit_pair(seed=3)
            out = compare_models(reduced, full, nested=True)
            print(json.dumps({
                'aic_red_err': abs(float(out['aic']['reduced']) - float(reduced.aic)),
                'aic_full_err': abs(float(out['aic']['full']) - float(full.aic)),
                'bic_red_err': abs(float(out['bic']['reduced']) - float(reduced.bic)),
                'bic_full_err': abs(float(out['bic']['full']) - float(full.bic)),
                'aic_red': float(reduced.aic),
                'aic_full': float(full.aic),
            }))
            """
        )
        assert report["aic_red_err"] < 1e-9
        assert report["aic_full_err"] < 1e-9
        assert report["bic_red_err"] < 1e-9
        assert report["bic_full_err"] < 1e-9
        # sanity: the two models really have different AIC (not a copy bug)
        assert abs(report["aic_red"] - report["aic_full"]) > 1e-6

    def test_preferred_by_aic_bic_pick_lower_criterion(self):
        """L2: preferred_by_aic / preferred_by_bic name exactly the model with
        the strictly lower AIC / BIC, computed independently."""
        report = _run_driver(
            """
            reduced, full = _fit_pair(seed=4, full_predictive=True)
            out = compare_models(reduced, full, nested=True)
            ref_aic = 'reduced' if reduced.aic < full.aic else 'full'
            ref_bic = 'reduced' if reduced.bic < full.bic else 'full'
            print(json.dumps({
                'pref_aic': out['preferred_by_aic'],
                'pref_bic': out['preferred_by_bic'],
                'ref_aic': ref_aic,
                'ref_bic': ref_bic,
            }))
            """
        )
        assert report["pref_aic"] in ("reduced", "full")
        assert report["pref_bic"] in ("reduced", "full")
        assert report["pref_aic"] == report["ref_aic"]
        assert report["pref_bic"] == report["ref_bic"]

    def test_lr_stat_df_pvalue_match_likelihood_ratio(self):
        """L2: lr_stat == 2*(llf_full - llf_reduced), lr_df == param-count diff,
        lr_pvalue == chi2.sf(lr_stat, lr_df); cross-checked against
        RegressionResults.compare_lr_test (lr_stat, p_value, df_diff)."""
        report = _run_driver(
            """
            reduced, full = _fit_pair(seed=5, full_predictive=True)
            out = compare_models(reduced, full, nested=True)

            ref_stat = 2.0 * (float(full.llf) - float(reduced.llf))
            ref_df = int(len(full.params) - len(reduced.params))
            ref_p = float(stats.chi2.sf(ref_stat, ref_df))
            # statsmodels' own implementation: (lr_stat, p_value, df_diff)
            sm_stat, sm_p, sm_df = full.compare_lr_test(reduced)

            print(json.dumps({
                'lr_stat': float(out['lr_stat']),
                'lr_df': int(out['lr_df']),
                'lr_pvalue': float(out['lr_pvalue']),
                'stat_err': abs(float(out['lr_stat']) - ref_stat),
                'df': ref_df,
                'p_err': abs(float(out['lr_pvalue']) - ref_p),
                'sm_stat_err': abs(float(out['lr_stat']) - float(sm_stat)),
                'sm_df': int(sm_df),
                'sm_p_err': abs(float(out['lr_pvalue']) - float(sm_p)),
            }))
            """
        )
        assert report["lr_df"] == report["df"]
        assert report["df"] == 1  # full adds exactly one column here
        assert report["lr_df"] == report["sm_df"]
        assert report["lr_stat"] >= 0.0, "LR statistic must be non-negative"
        assert report["stat_err"] < 1e-6
        assert report["p_err"] < 1e-9
        assert report["sm_stat_err"] < 1e-6
        assert report["sm_p_err"] < 1e-9
        assert 0.0 <= report["lr_pvalue"] <= 1.0

    def test_predictive_extra_column_is_significant(self):
        """L2: a genuinely predictive extra column -> small lr_pvalue,
        full_significant True, and AIC prefers the full model."""
        report = _run_driver(
            """
            reduced, full = _fit_pair(seed=6, n=120, full_predictive=True, noise=0.5)
            out = compare_models(reduced, full, nested=True, alpha=0.05)
            print(json.dumps({
                'lr_pvalue': float(out['lr_pvalue']),
                'full_significant': bool(out['full_significant']),
                'pref_aic': out['preferred_by_aic'],
                'lr_stat': float(out['lr_stat']),
            }))
            """
        )
        assert report["lr_pvalue"] < 0.01, report
        assert report["full_significant"] is True
        assert report["pref_aic"] == "full", report
        assert report["lr_stat"] > 0.0

    def test_noise_extra_column_is_not_significant(self):
        """L2: a pure-noise extra column -> large lr_pvalue and
        full_significant False (the extra parameter is not justified)."""
        report = _run_driver(
            """
            reduced, full = _fit_pair(seed=7, n=120, full_predictive=False, noise=0.5)
            out = compare_models(reduced, full, nested=True, alpha=0.05)
            print(json.dumps({
                'lr_pvalue': float(out['lr_pvalue']),
                'full_significant': bool(out['full_significant']),
            }))
            """
        )
        assert report["lr_pvalue"] > 0.05, report
        assert report["full_significant"] is False, report

    def test_full_significant_tracks_alpha_threshold(self):
        """L2: full_significant is exactly (lr_pvalue < alpha): with a borderline
        p-value, raising alpha above it flips the flag from False to True while
        lr_pvalue itself stays fixed."""
        report = _run_driver(
            """
            reduced, full = _fit_pair(seed=8, n=120, full_predictive=False, noise=0.5)
            base = compare_models(reduced, full, nested=True, alpha=0.05)
            p = float(base['lr_pvalue'])
            # choose alphas straddling the observed p-value
            lo = compare_models(reduced, full, nested=True, alpha=max(p / 2.0, 1e-6))
            hi = compare_models(reduced, full, nested=True, alpha=min(p + (1.0 - p) / 2.0, 0.999999))
            print(json.dumps({
                'p': p,
                'low_sig': bool(lo['full_significant']),
                'high_sig': bool(hi['full_significant']),
                'p_stable': abs(float(lo['lr_pvalue']) - float(hi['lr_pvalue'])) < 1e-12,
            }))
            """
        )
        assert report["p_stable"] is True, "lr_pvalue must not depend on alpha"
        assert report["low_sig"] is False, "alpha below p must give not-significant"
        assert report["high_sig"] is True, "alpha above p must give significant"

    def test_mismatched_nobs_raises_value_error(self):
        """L2: results fit on different numbers of observations -> ValueError."""
        report = _run_driver(
            """
            rng = np.random.RandomState(9)
            x1 = rng.normal(size=80)
            y1 = 1.0 + 2.0 * x1 + rng.normal(scale=0.5, size=80)
            reduced = sm.OLS(y1, sm.add_constant(x1.reshape(-1, 1))).fit()

            # full fit on a DIFFERENT sample size (70 != 80)
            x1b = rng.normal(size=70); x2b = rng.normal(size=70)
            y2 = 1.0 + 2.0 * x1b + 3.0 * x2b + rng.normal(scale=0.5, size=70)
            full = sm.OLS(y2, sm.add_constant(np.column_stack([x1b, x2b]))).fit()

            raised = False
            etype = None
            try:
                compare_models(reduced, full, nested=True)
            except ValueError as e:
                raised = True; etype = 'ValueError'
            except Exception as e:
                raised = True; etype = type(e).__name__
            print(json.dumps({'raised': raised, 'etype': etype}))
            """
        )
        assert report["raised"] is True, "mismatched nobs must raise"
        assert report["etype"] == "ValueError", (
            "must raise ValueError, got " + str(report["etype"])
        )

    def test_lr_keys_consistent_across_nested_flag(self):
        """L2: nested=True yields a positive-int lr_df equal to the parameter
        difference and a finite non-negative lr_stat; toggling to nested=False on
        the SAME results removes those keys entirely (discriminates a stub that
        always emits the LR block)."""
        report = _run_driver(
            """
            reduced, full = _fit_pair(seed=10, full_predictive=True)
            on = compare_models(reduced, full, nested=True)
            off = compare_models(reduced, full, nested=False)
            import math
            print(json.dumps({
                'lr_df': int(on['lr_df']),
                'param_diff': int(len(full.params) - len(reduced.params)),
                'lr_stat_finite': bool(math.isfinite(float(on['lr_stat']))),
                'lr_stat_nonneg': bool(float(on['lr_stat']) >= 0.0),
                'off_has_lr': any(
                    k in off for k in
                    ('lr_stat', 'lr_df', 'lr_pvalue', 'full_significant')
                ),
            }))
            """
        )
        assert report["lr_df"] == report["param_diff"]
        assert report["lr_df"] > 0, "lr_df must be a positive integer"
        assert report["lr_stat_finite"] and report["lr_stat_nonneg"]
        assert report["off_has_lr"] is False

    def test_native_pytest_passes(self):
        """L2: the deliverable's own native acceptance command passes
        (pytest statsmodels/stats/tests/test_model_comparison.py -q)."""
        if not os.path.isfile(self.TEST_PATH):
            pytest.skip("deliverable test module not present: " + self.TEST_PATH)
        proc = subprocess.run(
            [
                sys.executable, "-m", "pytest",
                os.path.join(
                    "statsmodels", "stats", "tests",
                    "test_model_comparison.py",
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
