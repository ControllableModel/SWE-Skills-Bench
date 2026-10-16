# Task: Add a simultaneous-congruence solver to sympy.ntheory

## Background

The `sympy/ntheory/` subpackage already provides modular-arithmetic helpers in `modular.py` and `residue_ntheory.py`. This task adds a new public utility that solves a system of simultaneous linear congruences and reports the combined solution as an exact residue class.

## Files to Create/Modify

- `sympy/ntheory/congruences.py` (new) — implements the public function described below.
- `sympy/ntheory/__init__.py` (modify) — export the new function so it is importable as `from sympy.ntheory import solve_congruences`.
- `sympy/ntheory/tests/test_congruences.py` (new) — the deterministic test file covering the contract and edge cases below.

## Requirements

Implement a single public function `solve_congruences(congruences)` in `sympy/ntheory/congruences.py`.

### Behavior

`congruences` is a list of `(remainder, modulus)` integer pairs representing the system `x ≡ remainder (mod modulus)`. Return either:

- a tuple `(x0, M)` of Python/SymPy integers, where `0 <= x0 < M`, `M` is the least common combined modulus, and `x0` is the unique smallest non-negative solution, OR
- `None` when the system has no simultaneous solution.

### Constraints and edge cases

- The moduli need NOT be pairwise coprime. The function MUST handle the general case and return `None` when two congruences contradict (e.g. `x ≡ 0 (mod 2)` and `x ≡ 1 (mod 4)`).
- When a solution exists, `M` MUST equal the least common multiple of all moduli, and `x0` MUST satisfy `x0 % modulus == remainder % modulus` for every input pair.
- All moduli MUST be positive integers; a non-positive modulus MUST raise `ValueError`.
- An empty list MUST return `(0, 1)` (every integer satisfies an empty system, normalized modulo 1).
- Remainders may be given as negative integers and MUST be reduced into `[0, M)` in the output.
- Results MUST be exact integers (no floating point).

### Expected Functionality

- `solve_congruences([(2, 3), (3, 5), (2, 7)])` -> `(23, 105)`.
- `solve_congruences([(1, 4), (3, 6)])` -> `(9, 12)` (non-coprime, compatible).
- `solve_congruences([(0, 2), (1, 4)])` -> `None` (contradiction).
- `solve_congruences([(-1, 5)])` -> `(4, 5)`.
- `solve_congruences([])` -> `(0, 1)`.
- `solve_congruences([(1, 0)])` -> raises `ValueError`.

## Acceptance Criteria

- `from sympy.ntheory import solve_congruences` succeeds.
- For every solvable system, the returned `x0` satisfies all input congruences and `0 <= x0 < M` with `M == lcm(moduli)`.
- Contradictory systems return exactly `None`.
- Non-positive moduli raise `ValueError`; the empty system returns `(0, 1)`.
- All returned numbers are exact integers.
- The following command passes with all tests collected and green:

```bash
python -m pytest sympy/ntheory/tests/test_congruences.py -q
```
