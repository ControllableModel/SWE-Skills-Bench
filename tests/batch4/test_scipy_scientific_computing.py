"""
Test for the 'scipy-scientific-computing' skill (variant ext4).

Verifies the agent added a two-sample group-comparison reporter to
``scipy/stats`` as a new private module ``scipy/stats/_group_compare.py``
exposing::

    compare_groups(a, b, *, alpha=0.05, force=None)

The reporter compares two 1-D numeric samples, auto-selects a parametric
(difference-of-means) or rank-based test using a normality screen, and returns
a structured dict with keys ``{"test", "statistic", "pvalue", "significant",
"effect_size"}``.

Verification strategy (mirrors the ext1 harness):

  * The tests do NOT trust the agent's own test file and do NOT string-match the
    source. Each behavioural scenario runs in a fresh ``python`` subprocess with
    cwd=REPO_DIR (the exact environment the acceptance command uses), loading the
    real ``compare_groups`` (preferring the installed package path, falling back
    to loading the source file directly).
  * Deep numeric/structural validation: null data is non-significant and shifted
    data is significant; the parametric and rank branches reproduce an
    INDEPENDENT recomputation via ``scipy.stats.ttest_ind`` /
    ``scipy.stats.mannwhitneyu``; ``force`` overrides auto-selection; effect-size
    is antisymmetric under swapping ``a``/``b`` (and its magnitude is invariant
    for the parametric case); ``"significant"`` is consistent with ``pvalue`` and
    ``alpha``; inputs are not mutated; results are deterministic; and every
    invalid-input case raises ``ValueError``.

A naive / hardcoded implementation (always returning a fixed p-value, ignoring
``force``, never flipping the effect-size sign, or not screening normality)
fails these tests.

L2 native acceptance command driven at the end:
    python -m pytest scipy/stats/tests/test_group_compare.py -v
"""

import json
import os
import subprocess
import textwrap

import pytest


REPO_DIR = "/workspace/scipy"

# Common preamble used by every driver subprocess. Prefer the official package
# import path the task requires; fall back to loading the source file directly
# (its own ``from scipy.stats ...`` imports still resolve through the installed
# SciPy) so behavioural tests run even if the editable rebuild has not
# re-registered the new module under the package namespace yet.
_LOADER = r"""
import json, sys, importlib.util, os
import numpy as np

def _load_compare_groups():
    try:
        from scipy.stats._group_compare import compare_groups as cg
        return cg
    except Exception:
        pass
    src = os.path.join(REPO_DIR, "scipy", "stats", "_group_compare.py")
    spec = importlib.util.spec_from_file_location("_group_compare_under_test", src)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.compare_groups

REPO_DIR = %r
compare_groups = _load_compare_groups()

# Deterministic, fixed sample fixtures (no randomness). Two distinct, clearly
# non-identical-by-eye but distribution-matched-ish samples for null cases, and
# a shifted copy for the alternative.
def _normalish(n, seed):
    # Deterministic pseudo-normal via a fixed Generator seed (NOT used at call
    # time inside compare_groups; only to BUILD the static test data here).
    rng = np.random.default_rng(seed)
    return rng.standard_normal(n)
""" % REPO_DIR


def _run_driver(body, timeout=300):
    """Run ``_LOADER + body`` as a python subprocess in REPO_DIR.

    ``body`` must ``print(json.dumps(...))`` its result on the final line.
    Returns the parsed JSON object. Raises AssertionError with captured output
    on failure.
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
    """Validate the compare_groups two-sample group-comparison reporter."""

    REPO_DIR = REPO_DIR

    # ------------------------------------------------------------------
    # L1 — deliverable files exist and are minimally well-formed
    # ------------------------------------------------------------------

    def test_module_file_exists(self):
        """scipy/stats/_group_compare.py must exist."""
        fpath = os.path.join(self.REPO_DIR, "scipy", "stats", "_group_compare.py")
        assert os.path.isfile(fpath), "_group_compare.py not found at %s" % fpath

    def test_test_file_exists(self):
        """scipy/stats/tests/test_group_compare.py must exist."""
        fpath = os.path.join(
            self.REPO_DIR, "scipy", "stats", "tests", "test_group_compare.py"
        )
        assert os.path.isfile(fpath), (
            "test_group_compare.py not found at %s" % fpath
        )

    def test_meson_registers_module(self):
        """scipy/stats/meson.build must list _group_compare.py for installation."""
        fpath = os.path.join(self.REPO_DIR, "scipy", "stats", "meson.build")
        assert os.path.isfile(fpath), "stats meson.build missing"
        with open(fpath) as f:
            content = f.read()
        assert "_group_compare.py" in content, (
            "_group_compare.py was not added to scipy/stats/meson.build "
            "install_sources"
        )

    def test_meson_registers_test(self):
        """scipy/stats/tests/meson.build must list test_group_compare.py."""
        fpath = os.path.join(
            self.REPO_DIR, "scipy", "stats", "tests", "meson.build"
        )
        assert os.path.isfile(fpath), "tests meson.build missing"
        with open(fpath) as f:
            content = f.read()
        assert "test_group_compare.py" in content, (
            "test_group_compare.py was not added to tests/meson.build "
            "install_sources"
        )

    def test_function_importable_and_return_keys(self):
        """compare_groups must be importable and return a dict with EXACTLY the
        five contract keys."""
        res = _run_driver(
            r"""
            import numpy as np
            a = _normalish(40, 1)
            b = _normalish(45, 2)
            out = compare_groups(a, b)
            assert isinstance(out, dict), "return value must be a dict"
            print(json.dumps(sorted(out.keys())))
            """
        )
        assert res == sorted(
            ["effect_size", "pvalue", "significant", "statistic", "test"]
        ), (
            "compare_groups must return exactly keys "
            "{'test','statistic','pvalue','significant','effect_size'}, got %r"
            % res
        )

    def test_return_value_types(self):
        """Each returned field has its contract type and pvalue is in [0, 1]."""
        res = _run_driver(
            r"""
            import numpy as np
            a = _normalish(40, 3)
            b = _normalish(50, 4)
            out = compare_groups(a, b)
            info = {
                "test": out["test"],
                "test_is_str": isinstance(out["test"], str),
                "stat_is_num": isinstance(float(out["statistic"]), float),
                "pvalue": float(out["pvalue"]),
                "sig_is_bool": isinstance(out["significant"], bool),
                "eff_is_num": isinstance(float(out["effect_size"]), float),
            }
            print(json.dumps(info))
            """
        )
        assert res["test"] in ("parametric", "rank"), (
            "'test' must be 'parametric' or 'rank', got %r" % res["test"]
        )
        assert res["test_is_str"], "'test' must be a string"
        assert res["stat_is_num"], "'statistic' must be a float"
        assert 0.0 <= res["pvalue"] <= 1.0, (
            "'pvalue' must be in [0, 1], got %r" % res["pvalue"]
        )
        assert res["sig_is_bool"], "'significant' must be a bool"
        assert res["eff_is_num"], "'effect_size' must be a float"

    # ------------------------------------------------------------------
    # L2 — dynamic execution / deep behavioural validation
    # ------------------------------------------------------------------

    def test_null_data_not_significant(self):
        """Two samples from the SAME distribution -> large pvalue, not
        significant, effect_size ~= 0."""
        res = _run_driver(
            r"""
            import numpy as np
            # Two independent draws from the same standard-normal distribution.
            a = _normalish(120, 11)
            b = _normalish(130, 12)
            out = compare_groups(a, b, alpha=0.05)
            print(json.dumps({
                "pvalue": float(out["pvalue"]),
                "significant": bool(out["significant"]),
                "effect_size": float(out["effect_size"]),
            }))
            """
        )
        assert res["pvalue"] > 0.05, (
            "null data should yield a large pvalue, got %r "
            "(a hardcoded tiny-pvalue impl fails here)" % res["pvalue"]
        )
        assert res["significant"] is False, (
            "null data must not be flagged significant, got significant=%r"
            % res["significant"]
        )
        assert abs(res["effect_size"]) < 0.4, (
            "null-data effect_size should be near 0, got %r" % res["effect_size"]
        )

    def test_shifted_data_is_significant(self):
        """A sample and a large-constant-shifted copy -> tiny pvalue, significant
        True, large-magnitude effect_size."""
        res = _run_driver(
            r"""
            import numpy as np
            a = _normalish(120, 21)
            b = a + 5.0          # large, unambiguous mean shift
            out = compare_groups(a, b, alpha=0.05)
            print(json.dumps({
                "pvalue": float(out["pvalue"]),
                "significant": bool(out["significant"]),
                "effect_size": float(out["effect_size"]),
            }))
            """
        )
        assert res["pvalue"] < 0.01, (
            "clearly-shifted data should yield a tiny pvalue, got %r "
            "(a hardcoded large-pvalue impl fails here)" % res["pvalue"]
        )
        assert res["significant"] is True, (
            "shifted data must be flagged significant, got significant=%r"
            % res["significant"]
        )
        assert abs(res["effect_size"]) > 1.0, (
            "shifted data effect_size must be large in magnitude, got %r"
            % res["effect_size"]
        )

    def test_significant_consistent_with_pvalue_and_alpha(self):
        """'significant' must be exactly (pvalue < alpha) for several alphas."""
        res = _run_driver(
            r"""
            import numpy as np
            a = _normalish(60, 31)
            b = a + 0.6          # moderate shift, p somewhere mid-range
            rows = []
            for alpha in (0.001, 0.01, 0.05, 0.1, 0.5):
                out = compare_groups(a, b, alpha=alpha)
                rows.append({
                    "alpha": alpha,
                    "pvalue": float(out["pvalue"]),
                    "significant": bool(out["significant"]),
                })
            print(json.dumps(rows))
            """
        )
        for row in res:
            expected = row["pvalue"] < row["alpha"]
            assert row["significant"] is expected, (
                "significant must equal (pvalue < alpha): alpha=%r pvalue=%r "
                "significant=%r expected=%r"
                % (row["alpha"], row["pvalue"], row["significant"], expected)
            )

    def test_parametric_branch_matches_ttest(self):
        """force='parametric' must reproduce scipy.stats.ttest_ind exactly."""
        res = _run_driver(
            r"""
            import numpy as np
            from scipy.stats import ttest_ind
            a = _normalish(80, 41)
            b = _normalish(85, 42) + 0.8
            out = compare_groups(a, b, force="parametric")
            ref = ttest_ind(a, b)
            print(json.dumps({
                "test": out["test"],
                "stat": float(out["statistic"]),
                "pvalue": float(out["pvalue"]),
                "ref_stat": float(ref.statistic),
                "ref_pvalue": float(ref.pvalue),
            }))
            """
        )
        assert res["test"] == "parametric", (
            "force='parametric' must set test='parametric', got %r" % res["test"]
        )
        # The statistic should match a standard two-sample t-test up to sign
        # (orientation of a vs b). p-value must match closely.
        assert abs(abs(res["stat"]) - abs(res["ref_stat"])) < 1e-6, (
            "parametric statistic must match ttest_ind (|t|=%r vs %r)"
            % (res["stat"], res["ref_stat"])
        )
        assert abs(res["pvalue"] - res["ref_pvalue"]) < 1e-6, (
            "parametric pvalue must match ttest_ind (%r vs %r)"
            % (res["pvalue"], res["ref_pvalue"])
        )

    def test_rank_branch_matches_mannwhitneyu(self):
        """force='rank' must reproduce scipy.stats.mannwhitneyu's two-sided
        p-value on the same data."""
        res = _run_driver(
            r"""
            import numpy as np
            from scipy.stats import mannwhitneyu
            a = _normalish(70, 51)
            b = _normalish(75, 52) + 0.7
            out = compare_groups(a, b, force="rank")
            ref = mannwhitneyu(a, b, alternative="two-sided")
            print(json.dumps({
                "test": out["test"],
                "pvalue": float(out["pvalue"]),
                "ref_pvalue": float(ref.pvalue),
            }))
            """
        )
        assert res["test"] == "rank", (
            "force='rank' must set test='rank', got %r" % res["test"]
        )
        assert abs(res["pvalue"] - res["ref_pvalue"]) < 1e-6, (
            "rank-branch pvalue must match mannwhitneyu two-sided "
            "(%r vs %r); an impl that silently runs a t-test fails"
            % (res["pvalue"], res["ref_pvalue"])
        )

    def test_force_overrides_auto_selection(self):
        """On clearly-normal data the auto branch is parametric, yet
        force='rank' must produce a DIFFERENT test and a rank-consistent
        p-value."""
        res = _run_driver(
            r"""
            import numpy as np
            from scipy.stats import mannwhitneyu
            a = _normalish(90, 61)        # clean normal data
            b = _normalish(95, 62) + 0.5
            auto = compare_groups(a, b)                 # should auto-pick parametric
            forced = compare_groups(a, b, force="rank")
            ref = mannwhitneyu(a, b, alternative="two-sided")
            print(json.dumps({
                "auto_test": auto["test"],
                "forced_test": forced["test"],
                "forced_pvalue": float(forced["pvalue"]),
                "ref_pvalue": float(ref.pvalue),
            }))
            """
        )
        assert res["auto_test"] == "parametric", (
            "auto-selection on clean normal data should pick 'parametric', got %r "
            "(an impl that ignores the normality screen fails)" % res["auto_test"]
        )
        assert res["forced_test"] == "rank", (
            "force='rank' must override auto-selection, got %r "
            "(an impl that ignores force fails)" % res["forced_test"]
        )
        assert abs(res["forced_pvalue"] - res["ref_pvalue"]) < 1e-6, (
            "forced rank pvalue must match mannwhitneyu, %r vs %r"
            % (res["forced_pvalue"], res["ref_pvalue"])
        )

    def test_auto_selects_rank_on_nonnormal_data(self):
        """Heavily non-normal (skewed/heavy-tailed) data -> auto branch is
        'rank'."""
        res = _run_driver(
            r"""
            import numpy as np
            rng = np.random.default_rng(71)
            # Strongly skewed, definitely-not-normal samples.
            a = rng.exponential(scale=1.0, size=120) ** 2
            b = rng.exponential(scale=1.0, size=130) ** 2
            out = compare_groups(a, b)
            print(json.dumps({"test": out["test"]}))
            """
        )
        assert res["test"] == "rank", (
            "auto-selection on strongly non-normal data must pick 'rank', got %r "
            "(an impl that always returns parametric ignores the normality "
            "screen)" % res["test"]
        )

    def test_effect_size_antisymmetric_under_swap(self):
        """Swapping a and b flips effect_size sign; for the parametric case the
        magnitude is unchanged and pvalue is unchanged."""
        res = _run_driver(
            r"""
            import numpy as np
            a = _normalish(80, 81)
            b = _normalish(85, 82) + 1.0
            ab = compare_groups(a, b, force="parametric")
            ba = compare_groups(b, a, force="parametric")
            print(json.dumps({
                "eff_ab": float(ab["effect_size"]),
                "eff_ba": float(ba["effect_size"]),
                "p_ab": float(ab["pvalue"]),
                "p_ba": float(ba["pvalue"]),
            }))
            """
        )
        eff_ab, eff_ba = res["eff_ab"], res["eff_ba"]
        assert eff_ab != 0.0, "effect_size should be non-zero for shifted data"
        assert (eff_ab > 0) != (eff_ba > 0), (
            "effect_size sign must flip under swap, got %r and %r "
            "(an impl that always returns |effect| fails)" % (eff_ab, eff_ba)
        )
        assert abs(abs(eff_ab) - abs(eff_ba)) < 1e-9, (
            "parametric effect_size magnitude must be invariant under swap, "
            "got |%r| vs |%r|" % (eff_ab, eff_ba)
        )
        assert abs(res["p_ab"] - res["p_ba"]) < 1e-9, (
            "two-sided pvalue must be unchanged under swap, got %r vs %r"
            % (res["p_ab"], res["p_ba"])
        )

    def test_input_not_mutated(self):
        """compare_groups must not mutate either input array."""
        res = _run_driver(
            r"""
            import numpy as np
            a = _normalish(60, 91)
            b = _normalish(65, 92) + 0.5
            a0, b0 = a.copy(), b.copy()
            _ = compare_groups(a, b, force="rank")
            _ = compare_groups(a, b, force="parametric")
            _ = compare_groups(a, b)
            print(json.dumps({
                "a_unchanged": bool(np.array_equal(a, a0)),
                "b_unchanged": bool(np.array_equal(b, b0)),
            }))
            """
        )
        assert res["a_unchanged"] is True, "compare_groups must not mutate 'a'"
        assert res["b_unchanged"] is True, "compare_groups must not mutate 'b'"

    def test_deterministic_repeated_calls(self):
        """Repeated calls on identical inputs return identical numbers."""
        res = _run_driver(
            r"""
            import numpy as np
            a = _normalish(100, 101)
            b = _normalish(110, 102) + 0.6
            outs = [compare_groups(a, b) for _ in range(3)]
            keys = ["test", "statistic", "pvalue", "significant", "effect_size"]
            same = all(
                outs[0]["test"] == o["test"]
                and outs[0]["significant"] == o["significant"]
                and abs(float(outs[0]["statistic"]) - float(o["statistic"])) == 0.0
                and abs(float(outs[0]["pvalue"]) - float(o["pvalue"])) == 0.0
                and abs(float(outs[0]["effect_size"]) - float(o["effect_size"])) == 0.0
                for o in outs[1:]
            )
            print(json.dumps({"deterministic": bool(same)}))
            """
        )
        assert res["deterministic"] is True, (
            "compare_groups must be deterministic across repeated calls "
            "(no random subsampling)"
        )

    def test_invalid_inputs_raise_value_error(self):
        """Each invalid-input case must raise ValueError."""
        res = _run_driver(
            r"""
            import numpy as np
            good_a = _normalish(30, 111)
            good_b = _normalish(35, 112)

            def raises_value_error(fn):
                try:
                    fn()
                except ValueError:
                    return True
                except Exception:
                    return False
                return False

            results = {}
            # a not 1-D
            results["a_2d"] = raises_value_error(
                lambda: compare_groups(np.ones((4, 4)), good_b))
            # b not 1-D
            results["b_2d"] = raises_value_error(
                lambda: compare_groups(good_a, np.ones((4, 4))))
            # a too few samples (< 3)
            results["a_short"] = raises_value_error(
                lambda: compare_groups(np.array([1.0, 2.0]), good_b))
            # b too few samples (< 3)
            results["b_short"] = raises_value_error(
                lambda: compare_groups(good_a, np.array([1.0, 2.0])))
            # a contains non-finite
            results["a_nan"] = raises_value_error(
                lambda: compare_groups(np.array([1.0, 2.0, np.nan, 4.0]), good_b))
            results["a_inf"] = raises_value_error(
                lambda: compare_groups(np.array([1.0, 2.0, np.inf, 4.0]), good_b))
            # b contains non-finite
            results["b_nan"] = raises_value_error(
                lambda: compare_groups(good_a, np.array([1.0, 2.0, np.nan, 4.0])))
            # alpha out of (0, 1)
            results["alpha_zero"] = raises_value_error(
                lambda: compare_groups(good_a, good_b, alpha=0.0))
            results["alpha_one"] = raises_value_error(
                lambda: compare_groups(good_a, good_b, alpha=1.0))
            results["alpha_neg"] = raises_value_error(
                lambda: compare_groups(good_a, good_b, alpha=-0.1))
            results["alpha_big"] = raises_value_error(
                lambda: compare_groups(good_a, good_b, alpha=1.5))
            # force not in {None, "parametric", "rank"}
            results["force_bad"] = raises_value_error(
                lambda: compare_groups(good_a, good_b, force="nonparametric"))
            results["force_bad2"] = raises_value_error(
                lambda: compare_groups(good_a, good_b, force="ttest"))
            print(json.dumps(results))
            """
        )
        for case, ok in res.items():
            assert ok is True, (
                "invalid-input case %r did not raise ValueError" % case
            )

    def test_acceptance_pytest_command(self):
        """The agent's own test file passes via the native acceptance command."""
        proc = subprocess.run(
            ["python", "-m", "pytest",
             "scipy/stats/tests/test_group_compare.py", "-v", "--tb=short"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=900,
        )
        assert proc.returncode == 0, (
            "acceptance command failed\n--- STDOUT ---\n%s\n--- STDERR ---\n%s"
            % (proc.stdout[-4000:], proc.stderr[-2000:])
        )
