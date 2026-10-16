# Task: Add a vector-field analysis utility to sympy.vector

## Background

The `sympy/vector/` subpackage models 3D coordinate systems, scalar fields and vector fields with exact symbolic differential operators (`operators.py`, `functions.py`). This task adds a public utility that bundles the standard differential operators applied to a field in a given coordinate system.

## Files to Create/Modify

- `sympy/vector/fieldanalysis.py` (new) — implements the public function described below.
- `sympy/vector/__init__.py` (modify) — export the new function so it is importable as `from sympy.vector import field_analysis`.
- `sympy/vector/tests/test_fieldanalysis.py` (new) — the deterministic test file covering the contract and edge cases below.

## Requirements

Implement a single public function `field_analysis(field, coord_sys)` in `sympy/vector/fieldanalysis.py`.

### Behavior

Given a `field` (either a scalar field expression or a vector field) and a `CoordSys3D` instance `coord_sys`, return a Python `dict` whose contents depend on whether `field` is scalar or vector:

- If `field` is a **scalar** field: keys `"gradient"` (a vector field) and `"laplacian"` (a scalar field).
- If `field` is a **vector** field: keys `"divergence"` (a scalar field) and `"curl"` (a vector field).

### Constraints and edge cases

- All results MUST be computed with exact symbolic differentiation in the given coordinate system.
- For the scalar field `C.x**2 + C.y**2 + C.z**2` (with `C = CoordSys3D('C')`), `"laplacian"` MUST simplify to `6`, and `"gradient"` MUST equal `2*C.x*C.i + 2*C.y*C.j + 2*C.z*C.k`.
- For a constant scalar field, `"gradient"` MUST be the zero vector and `"laplacian"` MUST be `0`.
- For a curl-free vector field such as `C.y*C.i + C.x*C.j`, `"curl"` MUST be the zero vector.
- For a divergence-free vector field such as `C.y*C.i - C.x*C.j`, `"divergence"` MUST simplify to `0`.
- If `field` is neither a recognized scalar expression nor a vector, the function MUST raise `TypeError`.
- The dict MUST contain exactly the two keys appropriate to the field's type and no others.

### Expected Functionality

- With `C = CoordSys3D('C')`: `field_analysis(C.x**2 + C.y**2 + C.z**2, C)["laplacian"]` -> simplifies to `6`.
- `field_analysis(C.x**2 + C.y**2 + C.z**2, C)["gradient"]` -> equals `2*C.x*C.i + 2*C.y*C.j + 2*C.z*C.k`.
- `field_analysis(C.y*C.i + C.x*C.j, C)["curl"]` -> the zero vector.
- `field_analysis(C.y*C.i - C.x*C.j, C)["divergence"]` -> simplifies to `0`.
- `field_analysis(object(), C)` -> raises `TypeError`.

## Acceptance Criteria

- `from sympy.vector import field_analysis` succeeds.
- For a scalar input the dict has exactly keys `{"gradient", "laplacian"}`; for a vector input exactly `{"divergence", "curl"}`.
- Each example matches exactly (e.g. `simplify(result["laplacian"] - 6) == 0`; vector equalities hold via `==` or by simplifying the difference to the zero vector).
- An unrecognized field type raises `TypeError`.
- The following command passes with all tests collected and green:

```bash
python -m pytest sympy/vector/tests/test_fieldanalysis.py -q
```
