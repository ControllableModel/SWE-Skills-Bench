# Task: Add an analytic-geometry tangent-line utility to sympy.geometry

## Background

The `sympy/geometry/` subpackage models points, lines, circles and ellipses as exact symbolic entities. This task adds a new public utility that, given a circle and an external point, returns exact data describing the tangent lines from that point.

## Files to Create/Modify

- `sympy/geometry/tangents.py` (new) — implements the public function described below.
- `sympy/geometry/__init__.py` (modify) — export the new function so it is importable as `from sympy.geometry import tangent_data`.
- `sympy/geometry/tests/test_tangents.py` (new) — the deterministic test file covering the contract and edge cases below.

## Requirements

Implement a single public function `tangent_data(circle, point)` in `sympy/geometry/tangents.py`.

### Behavior

Given a `Circle` and an external `Point` (2D), return a Python `dict` with exactly these string keys:

- `"distance"` — the exact distance from `point` to the circle's center, as a SymPy expression.
- `"tangent_length"` — the exact length of either tangent segment from `point` to the circle (the same for both), as a SymPy expression.
- `"num_tangents"` — the number of distinct tangent lines: `2` if the point is strictly outside, `1` if exactly on the circle, `0` if strictly inside.

### Constraints and edge cases

- All numeric results MUST be exact symbolic values. For a unit circle centered at the origin and the point `(2, 0)`, `"tangent_length"` MUST equal `sqrt(3)`, never `1.732...`.
- The tangent length MUST be derived from the exact relation `sqrt(distance**2 - radius**2)`; the returned expression, after `simplify`, MUST equal that value.
- When the point is strictly inside the circle, `"num_tangents"` MUST be `0` and `"tangent_length"` MUST be a SymPy expression whose squared form is negative (do not raise); document this as the inside case.
- When the point lies exactly on the circle, `"num_tangents"` MUST be `1` and `"tangent_length"` MUST simplify to `0`.
- The circle center and radius, and the point coordinates, may be symbolic; returned expressions may then involve those symbols.
- A non-`Circle` first argument MUST raise `TypeError`.

### Expected Functionality

- For `Circle(Point(0, 0), 1)` and `Point(2, 0)`: `"distance"` -> `2`, `"tangent_length"` -> equal to `sqrt(3)`, `"num_tangents"` -> `2`.
- For `Circle(Point(0, 0), 5)` and `Point(3, 4)` (on the circle): `"num_tangents"` -> `1`, `simplify("tangent_length")` -> `0`.
- For `Circle(Point(0, 0), 10)` and `Point(1, 1)` (inside): `"num_tangents"` -> `0`.
- `tangent_data(Point(0, 0), Point(1, 1))` -> raises `TypeError`.

## Acceptance Criteria

- `from sympy.geometry import tangent_data` succeeds.
- The returned object is a `dict` with exactly the three keys named above.
- For each example, the distance and tangent length match exactly (e.g. `simplify(result["tangent_length"] - sqrt(3)) == 0`), and `num_tangents` is the correct integer.
- A non-`Circle` first argument raises `TypeError`.
- The following command passes with all tests collected and green:

```bash
python -m pytest sympy/geometry/tests/test_tangents.py -q
```
