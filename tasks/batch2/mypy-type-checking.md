# Task: Add a Line-Width Budget Tracker

## Background

Black wraps source lines to a configured maximum width, and while building a
candidate line it repeatedly needs to know how much horizontal room is left and
whether the next chunk of text still fits. This task adds a small, self-contained
width-budget tracker to the `black` package that models a left-to-right budget
over a fixed line length, independent of the rest of the formatter.

## Files to Create/Modify

- `src/black/width_budget.py` (new) — the budget-tracker module described below.
- `tests/test_width_budget.py` (new) — the deterministic unit tests for it.

The new module must live in the `black` package and must import only from the
Python standard library (no `click`, no other `black` submodule).

## Requirements

### Public surface

`from black.width_budget import WidthBudget, BudgetError` must succeed. The module
must expose exactly the class `WidthBudget` and the exception `BudgetError`
(a subclass of `ValueError`); private helpers may begin with `_`.

### `WidthBudget`

- Constructed as `WidthBudget(limit)` where `limit` is a non-negative `int`
  (the maximum line width). A negative `limit` raises `BudgetError`.
- A read-only `limit` property returns the configured limit.
- A `used` property returns the total width consumed so far (starts at `0`).
- A `remaining` property returns `limit - used`, which may be `0` but is never
  negative once the budget is respected (see `consume`).
- `fits(width)` returns a `bool`: `True` iff a chunk of the given non-negative
  integer `width` would fit in the remaining room (i.e. `width <= remaining`).
  A negative `width` raises `BudgetError`.
- `consume(width)` reduces the remaining room by `width` (a non-negative `int`)
  and returns the new `remaining` value. Consuming more than `remaining` raises
  `BudgetError` and leaves `used` unchanged. A negative `width` raises `BudgetError`.
- `reset()` returns `used` to `0`.

### Expected Functionality

- A fresh `WidthBudget(88)` reports `remaining == 88`, `used == 0`.
- After `consume(10)` then `consume(5)`, `used == 15` and `remaining == 73`.
- `fits(73)` is `True`; `fits(74)` is `False`.
- `consume(1000)` on the same budget raises `BudgetError` and `used` stays `15`.
- `reset()` returns the budget to its initial state.

### Edge cases

- `WidthBudget(0)`: `remaining == 0`, `fits(0) is True`, `fits(1) is False`,
  `consume(0)` succeeds and returns `0`.
- `consume(0)` is always allowed and never changes `used`.

## Acceptance Criteria

- The module exposes `WidthBudget` and `BudgetError` with the behavior above.
- `tests/test_width_budget.py` contains at least 10 independent test cases
  covering the fits/consume boundary, the over-budget rejection (with state left
  unchanged), reset, and the zero-limit edge case.
- A naive implementation that allows over-consumption or mishandles the exact
  boundary fails the tests.
- The following command passes from the repository root:

  ```bash
  python -m pytest tests/test_width_budget.py -q
  ```

- Running the project's configured type checker over the new module reports no errors:

  ```bash
  mypy src/black/width_budget.py
  ```
