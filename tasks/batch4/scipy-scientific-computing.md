# Task: Add a two-sample group-comparison reporter to scipy.stats

## Background

The SciPy repository (`scipy/stats`) exposes many individual hypothesis tests,
but has no single helper that compares two numeric samples, automatically picks
a parametric or rank-based test based on a normality screen, and returns a
structured, reproducible report with an effect size. This task adds such a helper
as a new private module inside `scipy/stats`, with its own test suite.

## Files to Create/Modify

- `scipy/stats/_group_compare.py` (new) — implementation of the reporter.
- `scipy/stats/meson.build` (modify) — add `_group_compare.py` to a
  `py3.install_sources([...])` list whose `subdir` is `'scipy/stats'`.
- `scipy/stats/tests/test_group_compare.py` (new) — deterministic unit tests.
- `scipy/stats/tests/meson.build` (modify) — add `test_group_compare.py` to the
  `py3.install_sources([...])` list whose `subdir` is `'scipy/stats/tests'`.

(The test file imports the implementation directly, e.g.
`from scipy.stats._group_compare import compare_groups`. No change to the public
`scipy/stats/__init__.py` API surface is required.)

## Requirements

### Public function

Implement a single function in `scipy/stats/_group_compare.py`:

```
compare_groups(a, b, *, alpha=0.05, force=None)
```

with the following contract.

- `a` and `b` are 1-D, real-valued, finite array-likes (the two samples; they may
  differ in length).
- `alpha` is the significance threshold used to set the `"significant"` flag.
- `force` is either `None` (auto-select the test), `"parametric"`, or
  `"rank"`. Auto-selection must run a normality screen on both samples and pick a
  difference-of-means test when both look normal, otherwise a rank-based test.

The function returns a dictionary with exactly these keys:

- `"test"` — a string, either `"parametric"` or `"rank"`, naming the family of
  test actually performed.
- `"statistic"` — the test statistic as a float.
- `"pvalue"` — the two-sided p-value as a float in `[0, 1]`.
- `"significant"` — a bool: `True` iff `"pvalue" < alpha`.
- `"effect_size"` — a float standardized effect size (a mean difference divided
  by a pooled spread for the parametric case; a rank-based effect measure for the
  rank case), with sign indicating the direction `a` vs `b`.

### Behavioral constraints

- Two samples drawn from the same distribution must yield a large `"pvalue"` and
  `"significant"` == `False`; two samples with a clear shift must yield a small
  `"pvalue"` and `"significant"` == `True`.
- When `force` is given, `"test"` must equal the requested family regardless of
  the normality screen.
- `"effect_size"` sign must flip when `a` and `b` are swapped, and its magnitude
  must be unchanged for the parametric case.
- The function must not mutate `a` or `b`.
- Results must be deterministic: repeated calls on the same inputs return
  identical numbers (no random subsampling).

### Input validation (edge cases)

Raise `ValueError` with an informative message when:

- `a` or `b` is not 1-D, contains non-finite values, or has fewer than 3 samples.
- `alpha` is not in the open interval `(0, 1)`.
- `force` is not one of `None`, `"parametric"`, `"rank"`.

### Expected Functionality

- Two identical-distribution samples -> large `"pvalue"`, `"significant"` False,
  `"effect_size"` ≈ 0.
- A sample and the same sample shifted by a large constant -> tiny `"pvalue"`,
  `"significant"` True, `"effect_size"` of large magnitude.
- `force="rank"` on clearly-normal data -> `"test"` == `"rank"` and a p-value
  consistent with the rank test on those data.
- Swapping `a` and `b` -> `"effect_size"` changes sign; `"pvalue"` unchanged.

## Acceptance Criteria

- A new module `scipy/stats/_group_compare.py` exists and exposes
  `compare_groups` with the signature and return contract above.
- `scipy/stats/tests/test_group_compare.py` exists with at least 10 test cases
  that, using `numpy.testing.assert_allclose` / exact assertions, verify:
  null data is non-significant and shifted data is significant; `force` overrides
  auto-selection; the parametric and rank branches return statistics matching an
  independent recomputation; `"effect_size"` is antisymmetric under swap;
  `"significant"` is consistent with `"pvalue"` and `alpha`; inputs are not
  mutated; results are deterministic; and each invalid-input case raises
  `ValueError`.
- A naive or hardcoded implementation (e.g. always returning a fixed p-value, or
  ignoring `force`, or never flipping the effect-size sign) must fail these tests.
- The following command passes from the repository root after building SciPy:

  ```
  python -m pytest scipy/stats/tests/test_group_compare.py -v
  ```
