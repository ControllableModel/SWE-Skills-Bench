# Task: Add a radius-neighbor density estimator to scipy.spatial

## Background

The SciPy repository (`scipy/spatial`) provides spatial data structures for
nearest-neighbor queries, but has no single helper that computes a per-point
local density and flags isolated outliers from a point cloud. This task adds such
a helper as a new private module inside `scipy/spatial`, with its own test suite.

## Files to Create/Modify

- `scipy/spatial/_localdensity.py` (new) — implementation of the estimator.
- `scipy/spatial/meson.build` (modify) — add `_localdensity.py` to a
  `py3.install_sources([...])` list whose `subdir` is `'scipy/spatial'`.
- `scipy/spatial/tests/test_localdensity.py` (new) — deterministic unit tests.
- `scipy/spatial/tests/meson.build` (modify) — add `test_localdensity.py` to the
  `py3.install_sources([...])` list whose `subdir` is `'scipy/spatial/tests'`.

(The test file imports the implementation directly, e.g.
`from scipy.spatial._localdensity import local_density`. No change to the public
`scipy/spatial/__init__.py` API surface is required.)

## Requirements

### Public function

Implement a single function in `scipy/spatial/_localdensity.py`:

```
local_density(points, *, k=5, radius=None)
```

with the following contract.

- `points` is a 2-D array-like of shape `(n, d)` of `n` points in `d`-dimensional
  space.
- `k` is the neighbor count used for the distance-based density estimate (a point
  is not its own neighbor).
- `radius`, when given, switches the estimate to a fixed-radius count instead of a
  `k`-distance estimate.

The function returns a dictionary with exactly these keys:

- `"density"` — a 1-D float array of length `n`. In `k`-mode, each entry is
  `k / (mean distance to the k nearest neighbors)` (larger where points are
  closer together); in radius-mode, each entry is the count of other points within
  `radius`.
- `"knn_distance"` — a 1-D float array of length `n`: the distance to the `k`-th
  nearest neighbor of each point (always computed, even in radius-mode).
- `"outliers"` — a 1-D integer array of the indices (ascending) of points whose
  `"knn_distance"` exceeds the mean plus three standard deviations of all
  `"knn_distance"` values.

### Behavioral constraints

- Neighbor queries must use a spatial index, not an explicit all-pairs distance
  matrix materialized in Python loops.
- Points inside a dense cluster must have higher `"density"` and smaller
  `"knn_distance"` than points placed far away from every cluster.
- A point cloud of one tight cluster plus one far-away injected point must list
  exactly that injected point's index in `"outliers"`.
- Results must be invariant to a rigid translation of all `points` (densities and
  knn distances unchanged under a global shift).
- The function must not mutate the caller's `points` array.

### Input validation (edge cases)

Raise `ValueError` with an informative message when:

- `points` is not 2-D, or has fewer than `k+1` points.
- `k < 1`.
- `radius` is provided and is `<= 0`.

### Expected Functionality

- A uniform tight cluster -> `"density"` roughly constant across its members,
  `"outliers"` empty.
- That cluster plus a single point placed far away -> the far point has the
  largest `"knn_distance"` and appears (alone) in `"outliers"`.
- Translating every point by a constant vector -> identical `"density"` and
  `"knn_distance"` arrays.
- Radius-mode on a grid with `radius` chosen to capture the 4 orthogonal
  neighbours -> interior points report a `"density"` count of 4.

## Acceptance Criteria

- A new module `scipy/spatial/_localdensity.py` exists and exposes `local_density`
  with the signature and return contract above.
- `scipy/spatial/tests/test_localdensity.py` exists with at least 10 test cases
  that, using `numpy.testing.assert_allclose` / exact assertions, verify:
  cluster points have higher density and smaller knn distance than isolated
  points; the injected far point is the sole `"outliers"` entry; translation
  invariance of both arrays; radius-mode neighbour counts on a known grid;
  `"knn_distance"` matches an independent recomputation; inputs are not mutated;
  and each invalid-input case raises `ValueError`.
- A naive or hardcoded implementation (e.g. returning a constant density, or
  flagging no outliers, or breaking under translation) must fail these tests.
- The following command passes from the repository root after building SciPy:

  ```
  python -m pytest scipy/spatial/tests/test_localdensity.py -v
  ```
