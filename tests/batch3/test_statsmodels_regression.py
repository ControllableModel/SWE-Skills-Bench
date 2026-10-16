"""Tests for the ``statsmodels-regression`` skill (variant ext3).

Verifies the deliverable ``statsmodels/discrete/binary_report.py`` which must
expose a public ``binary_outcome_report(endog, exog, add_intercept=True,
threshold=0.5)`` helper. The helper fits a binary (logit) model of a 0/1
``endog`` on ``exog`` and returns a plain ``dict`` report containing the fitted
log-odds ``params``, multiplicative ``odds_ratios``, in-sample ``fitted_prob``,
thresholded ``predicted_class``, a 2x2 ``confusion`` matrix, ``accuracy``,
``llf`` and ``nobs``.

Verification strategy
---------------------
The tests independently re-derive every numeric quantity from statsmodels' own
``Logit`` / ``add_constant`` machinery and assert agreement to floating-point
tolerance (``params``, ``odds_ratios = exp(params)``, ``fitted_prob``, ``llf``).
They also check the *internal consistency* invariants the doc demands that a
naive/hardcoded implementation cannot fake:

  * ``predicted_class == (fitted_prob > threshold)`` elementwise;
  * ``confusion`` is the true-vs-predicted 2x2 cross-tab and its four entries
    sum to ``nobs``;
  * ``accuracy`` equals ``mean(predicted_class == endog)``;
  * lowering ``threshold`` is monotone non-decreasing in ``sum(predicted_class)``;
  * a redundant constant column is *not* duplicated when ``add_intercept=True``.

L1 cases check the deliverable file exists and the function is importable with
the documented signature/keys/types. L2 cases run the agent's function inside a
fresh subprocess that emits JSON (robust to PYTHONPATH being cleared and to
import-time side effects), then compare against an independent statsmodels
computation done in the same subprocess. The final L2 case drives the variant's
native acceptance command:

    pytest statsmodels/discrete/tests/test_binary_report.py -q
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
    from statsmodels.discrete.binary_report import binary_outcome_report

    def _ref_fit(endog, exog, add_intercept=True):
        '''Reference logit fit mirroring the documented specification.'''
        y = np.asarray(endog, dtype=float).ravel()
        X = np.asarray(exog, dtype=float)
        if X.ndim == 1:
            X = X.reshape(-1, 1)
        if add_intercept:
            X = sm.add_constant(X, has_constant='skip')
        res = sm.Logit(y, X).fit(disp=0)
        return res
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
        REPO_DIR, "statsmodels", "discrete", "binary_report.py"
    )
    TEST_PATH = os.path.join(
        REPO_DIR, "statsmodels", "discrete", "tests", "test_binary_report.py"
    )

    # ------------------------------------------------------------------ L1 ---
    def test_module_file_exists(self):
        """L1: the new binary_report.py deliverable exists and is non-trivial."""
        assert os.path.isfile(self.MODULE_PATH), (
            "expected new module at " + self.MODULE_PATH
        )
        assert os.path.getsize(self.MODULE_PATH) > 0

    def test_function_importable_with_signature(self):
        """L1: binary_outcome_report is importable with the documented params and
        their default values (add_intercept=True, threshold=0.5)."""
        report = _run_driver(
            """
            import inspect
            sig = inspect.signature(binary_outcome_report)
            params = list(sig.parameters)
            ai = sig.parameters.get('add_intercept')
            th = sig.parameters.get('threshold')
            print(json.dumps({
                'params': params,
                'add_intercept_default': (ai.default if ai is not None else None),
                'threshold_default': (th.default if th is not None else None),
            }))
            """
        )
        assert report["params"][:2] == ["endog", "exog"], report["params"]
        assert "add_intercept" in report["params"]
        assert "threshold" in report["params"]
        assert report["add_intercept_default"] is True
        assert report["threshold_default"] == 0.5

    def test_returns_dict_with_required_keys(self):
        """L1: the helper returns a plain dict containing every documented key."""
        report = _run_driver(
            """
            rng = np.random.RandomState(0)
            n = 40
            x = rng.normal(size=n)
            lin = -0.5 + 2.0 * x
            prob = 1.0 / (1.0 + np.exp(-lin))
            y = (prob > 0.5).astype(int)
            out = binary_outcome_report(list(y), list(x))
            print(json.dumps({
                'is_dict': type(out).__name__ == 'dict',
                'keys': sorted(out.keys()),
            }))
            """
        )
        assert report["is_dict"] is True, "must return a plain dict"
        required = {
            "params", "odds_ratios", "fitted_prob", "predicted_class",
            "confusion", "accuracy", "llf", "nobs",
        }
        missing = required - set(report["keys"])
        assert not missing, "missing keys: " + str(sorted(missing))

    def test_array_shapes_and_types(self):
        """L1: vector outputs are 1-D length-n; confusion is 2x2; predicted_class is
        integer-valued; nobs is an int equal to n."""
        report = _run_driver(
            """
            rng = np.random.RandomState(1)
            n = 30
            x = rng.normal(size=n)
            y = (rng.uniform(size=n) > 0.5).astype(int)
            out = binary_outcome_report(y, x)
            fp = np.asarray(out['fitted_prob'], dtype=float)
            pc = np.asarray(out['predicted_class'])
            conf = np.asarray(out['confusion'])
            print(json.dumps({
                'fp_len': int(fp.shape[0]),
                'fp_ndim': int(fp.ndim),
                'pc_len': int(pc.shape[0]),
                'pc_is_int': bool(np.all(pc.astype(float) == pc.astype(int))),
                'pc_only01': bool(set(np.unique(pc.astype(int)).tolist()) <= {0, 1}),
                'conf_shape': list(np.asarray(conf).shape),
                'nobs': int(out['nobs']),
                'n': n,
            }))
            """
        )
        assert report["fp_ndim"] == 1
        assert report["fp_len"] == report["n"]
        assert report["pc_len"] == report["n"]
        assert report["pc_is_int"] is True
        assert report["pc_only01"] is True
        assert report["conf_shape"] == [2, 2]
        assert report["nobs"] == report["n"]

    # ------------------------------------------------------------------ L2 ---
    def test_params_and_llf_match_statsmodels(self):
        """L2: with an intercept, params and llf match a direct statsmodels Logit
        on the intercept-augmented design to fp tolerance; params[0] is the
        intercept (added first)."""
        report = _run_driver(
            """
            rng = np.random.RandomState(2)
            n = 200
            x1 = rng.normal(size=n)
            x2 = rng.uniform(-2, 2, size=n)
            X = np.column_stack([x1, x2])
            lin = 0.4 + 1.8 * x1 - 1.1 * x2
            prob = 1.0 / (1.0 + np.exp(-lin))
            y = (rng.uniform(size=n) < prob).astype(int)

            out = binary_outcome_report(y, X, add_intercept=True)
            ref = _ref_fit(y, X, add_intercept=True)

            params = np.asarray(out['params'], dtype=float)
            print(json.dumps({
                'nparams': int(params.shape[0]),
                'param_max_abs_err': float(np.max(np.abs(params - np.asarray(ref.params)))),
                'first_is_intercept': bool(abs(params[0] - float(ref.params[0])) < 1e-6),
                'llf_err': abs(float(out['llf']) - float(ref.llf)),
            }))
            """
        )
        assert report["nparams"] == 3  # intercept + 2 predictors
        assert report["param_max_abs_err"] < 1e-6
        assert report["first_is_intercept"] is True
        assert report["llf_err"] < 1e-5

    def test_odds_ratios_are_exp_of_params(self):
        """L2: odds_ratios equals exp(params) elementwise (multiplicative odds
        scale) and matches exp of the reference statsmodels coefficients."""
        report = _run_driver(
            """
            rng = np.random.RandomState(3)
            n = 180
            x = rng.normal(size=n)
            lin = -0.3 + 1.5 * x
            y = (rng.uniform(size=n) < 1.0 / (1.0 + np.exp(-lin))).astype(int)

            out = binary_outcome_report(y, x, add_intercept=True)
            params = np.asarray(out['params'], dtype=float)
            orr = np.asarray(out['odds_ratios'], dtype=float)

            ref = _ref_fit(y, x, add_intercept=True)
            ref_or = np.exp(np.asarray(ref.params, dtype=float))
            print(json.dumps({
                'len_match': int(orr.shape[0]) == int(params.shape[0]),
                'self_err': float(np.max(np.abs(orr - np.exp(params)))),
                'ref_err': float(np.max(np.abs(orr - ref_or))),
                'all_positive': bool(np.all(orr > 0.0)),
            }))
            """
        )
        assert report["len_match"] is True
        assert report["self_err"] < 1e-9
        assert report["ref_err"] < 1e-5
        assert report["all_positive"] is True

    def test_fitted_prob_matches_and_in_unit_interval(self):
        """L2: fitted_prob equals the reference Logit in-sample predicted
        probabilities to fp tolerance and lies strictly in (0, 1)."""
        report = _run_driver(
            """
            rng = np.random.RandomState(4)
            n = 220
            x1 = rng.normal(size=n)
            x2 = rng.normal(size=n)
            X = np.column_stack([x1, x2])
            lin = 0.2 + 1.0 * x1 - 0.8 * x2
            y = (rng.uniform(size=n) < 1.0 / (1.0 + np.exp(-lin))).astype(int)

            out = binary_outcome_report(y, X, add_intercept=True)
            fp = np.asarray(out['fitted_prob'], dtype=float)

            ref = _ref_fit(y, X, add_intercept=True)
            ref_fp = np.asarray(ref.predict(), dtype=float)
            print(json.dumps({
                'len': int(fp.shape[0]),
                'max_err': float(np.max(np.abs(fp - ref_fp))),
                'strictly_in_unit': bool(np.all(fp > 0.0) and np.all(fp < 1.0)),
            }))
            """
        )
        assert report["len"] == 220
        assert report["max_err"] < 1e-6
        assert report["strictly_in_unit"] is True

    def test_predicted_class_is_threshold_of_fitted_prob(self):
        """L2: predicted_class is exactly (fitted_prob > threshold) for a
        non-default threshold; a naive helper that ignores threshold fails."""
        report = _run_driver(
            """
            rng = np.random.RandomState(5)
            n = 160
            x = rng.normal(size=n)
            lin = 0.1 + 1.3 * x
            y = (rng.uniform(size=n) < 1.0 / (1.0 + np.exp(-lin))).astype(int)

            thr = 0.3
            out = binary_outcome_report(y, x, add_intercept=True, threshold=thr)
            fp = np.asarray(out['fitted_prob'], dtype=float)
            pc = np.asarray(out['predicted_class']).astype(int)
            expected = (fp > thr).astype(int)
            print(json.dumps({
                'matches': bool(np.array_equal(pc, expected)),
                'n_pred1': int(pc.sum()),
                'expected_pred1': int(expected.sum()),
            }))
            """
        )
        assert report["matches"] is True
        assert report["n_pred1"] == report["expected_pred1"]

    def test_threshold_monotonicity(self):
        """L2: as threshold falls from high to low, the number of predicted-1
        observations is monotone non-decreasing (sign discrimination)."""
        report = _run_driver(
            """
            rng = np.random.RandomState(6)
            n = 200
            x = rng.normal(size=n)
            lin = -0.2 + 1.6 * x
            y = (rng.uniform(size=n) < 1.0 / (1.0 + np.exp(-lin))).astype(int)

            thresholds = [0.9, 0.7, 0.5, 0.3, 0.1]
            counts = []
            for t in thresholds:
                out = binary_outcome_report(y, x, add_intercept=True, threshold=t)
                counts.append(int(np.asarray(out['predicted_class']).astype(int).sum()))
            non_decreasing = all(counts[i] <= counts[i + 1] for i in range(len(counts) - 1))
            print(json.dumps({
                'counts': counts,
                'non_decreasing': non_decreasing,
                'span': counts[-1] - counts[0],
            }))
            """
        )
        assert report["non_decreasing"] is True, report["counts"]
        # a real fit on informative data must move with threshold
        assert report["span"] > 0, report["counts"]

    def test_confusion_consistent_with_classes_and_endog(self):
        """L2: confusion is the true(rows)-vs-predicted(cols) 2x2 cross-tab derived
        from predicted_class and endog; its four entries sum to nobs and it
        matches an independent np-built confusion matrix."""
        report = _run_driver(
            """
            rng = np.random.RandomState(7)
            n = 140
            x = rng.normal(size=n)
            lin = 0.3 + 1.4 * x
            y = (rng.uniform(size=n) < 1.0 / (1.0 + np.exp(-lin))).astype(int)

            out = binary_outcome_report(y, x, add_intercept=True, threshold=0.5)
            conf = np.asarray(out['confusion']).astype(int)
            pc = np.asarray(out['predicted_class']).astype(int)
            yv = np.asarray(y).astype(int)

            ref = np.zeros((2, 2), dtype=int)
            for t in (0, 1):
                for p in (0, 1):
                    ref[t, p] = int(np.sum((yv == t) & (pc == p)))
            print(json.dumps({
                'matches': bool(np.array_equal(conf, ref)),
                'sum': int(conf.sum()),
                'nobs': int(out['nobs']),
                'diag_consistency': bool((conf[0, 0] + conf[1, 1]) == int(np.sum(pc == yv))),
            }))
            """
        )
        assert report["matches"] is True
        assert report["sum"] == report["nobs"]
        assert report["diag_consistency"] is True

    def test_accuracy_matches_predicted_class(self):
        """L2: accuracy equals mean(predicted_class == endog) and equals
        trace(confusion)/nobs; a hardcoded accuracy fails this."""
        report = _run_driver(
            """
            rng = np.random.RandomState(8)
            n = 170
            x = rng.normal(size=n)
            lin = -0.1 + 1.7 * x
            y = (rng.uniform(size=n) < 1.0 / (1.0 + np.exp(-lin))).astype(int)

            out = binary_outcome_report(y, x, add_intercept=True, threshold=0.5)
            pc = np.asarray(out['predicted_class']).astype(int)
            yv = np.asarray(y).astype(int)
            conf = np.asarray(out['confusion']).astype(int)

            acc = float(out['accuracy'])
            expected = float(np.mean(pc == yv))
            from_conf = float((conf[0, 0] + conf[1, 1]) / conf.sum())
            print(json.dumps({
                'acc': acc,
                'acc_err': abs(acc - expected),
                'conf_err': abs(acc - from_conf),
                'in_unit': bool(0.0 <= acc <= 1.0),
            }))
            """
        )
        assert report["in_unit"] is True
        assert report["acc_err"] < 1e-12
        assert report["conf_err"] < 1e-12

    def test_strong_predictor_high_or_and_accuracy(self):
        """L2: on nearly separable data driven by a strong positive predictor, the
        predictor's odds_ratio exceeds 1.0 and in-sample accuracy is high."""
        report = _run_driver(
            """
            n = 120
            x = np.linspace(-3, 3, n)
            # deterministic, strongly separable on x
            y = (x > 0).astype(int)
            out = binary_outcome_report(y, x, add_intercept=True, threshold=0.5)
            orr = np.asarray(out['odds_ratios'], dtype=float)
            print(json.dumps({
                'slope_or': float(orr[1]),  # index 0 is intercept
                'accuracy': float(out['accuracy']),
            }))
            """
        )
        assert report["slope_or"] > 1.0, report
        assert report["accuracy"] > 0.95, report

    def test_no_intercept_param_count(self):
        """L2: add_intercept=False on a single predictor yields exactly one
        coefficient (no constant) and matches a no-constant reference fit."""
        report = _run_driver(
            """
            rng = np.random.RandomState(9)
            n = 150
            x = rng.normal(size=n)
            y = (rng.uniform(size=n) < 1.0 / (1.0 + np.exp(-(2.0 * x)))).astype(int)

            out = binary_outcome_report(y, x, add_intercept=False)
            params = np.asarray(out['params'], dtype=float)
            ref = _ref_fit(y, x, add_intercept=False)
            print(json.dumps({
                'nparams': int(params.shape[0]),
                'param_err': float(np.max(np.abs(params - np.asarray(ref.params)))),
                'nobs': int(out['nobs']),
            }))
            """
        )
        assert report["nparams"] == 1
        assert report["param_err"] < 1e-5
        assert report["nobs"] == 150

    def test_existing_constant_column_not_duplicated(self):
        """L2: add_intercept=True with an exog that already has a constant column
        must not add a duplicate constant; the design stays full-rank and the
        coefficient count equals the supplied columns (has_constant='skip')."""
        report = _run_driver(
            """
            rng = np.random.RandomState(10)
            n = 160
            ones = np.ones(n)
            x = rng.normal(size=n)
            X = np.column_stack([ones, x])  # already contains a constant column
            y = (rng.uniform(size=n) < 1.0 / (1.0 + np.exp(-(0.5 + 2.0 * x)))).astype(int)

            out = binary_outcome_report(y, X, add_intercept=True)
            params = np.asarray(out['params'], dtype=float)

            Xc = sm.add_constant(X, has_constant='skip')
            rank = int(np.linalg.matrix_rank(Xc))
            print(json.dumps({
                'nparams': int(params.shape[0]),
                'ncols': int(X.shape[1]),
                'full_rank': rank == X.shape[1],
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

    def test_accepts_lists_and_1d_exog(self):
        """L2: plain Python lists and a 1-D exog (single column) are accepted and
        produce the same numeric report as the equivalent ndarray 2-D call."""
        report = _run_driver(
            """
            rng = np.random.RandomState(11)
            n = 120
            xv = rng.normal(size=n)
            y = (rng.uniform(size=n) < 1.0 / (1.0 + np.exp(-(0.3 + 1.5 * xv)))).astype(int)

            out_list = binary_outcome_report(list(y), list(xv), add_intercept=True)
            out_arr = binary_outcome_report(
                np.asarray(y), np.asarray(xv).reshape(-1, 1), add_intercept=True)

            pl = np.asarray(out_list['params'], dtype=float)
            pa = np.asarray(out_arr['params'], dtype=float)
            print(json.dumps({
                'list_nparams': int(pl.shape[0]),
                'param_err': float(np.max(np.abs(pl - pa))),
                'llf_err': abs(float(out_list['llf']) - float(out_arr['llf'])),
                'nobs': int(out_list['nobs']),
            }))
            """
        )
        assert report["list_nparams"] == 2  # intercept + single column
        assert report["nobs"] == 120
        assert report["param_err"] < 1e-10
        assert report["llf_err"] < 1e-9

    def test_native_pytest_passes(self):
        """L2: the variant's native acceptance command for the deliverable's own
        unit tests passes (pytest statsmodels/discrete/tests/test_binary_report.py)."""
        if not os.path.isfile(self.TEST_PATH):
            pytest.skip("deliverable test module not present: " + self.TEST_PATH)
        proc = subprocess.run(
            [
                sys.executable, "-m", "pytest",
                os.path.join(
                    "statsmodels", "discrete", "tests",
                    "test_binary_report.py",
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
