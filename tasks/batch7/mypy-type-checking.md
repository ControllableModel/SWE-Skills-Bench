# Task: Add a Bracket-Balance Scanner

## Background

Black tracks the nesting of `()`, `[]`, and `{}` brackets while splitting lines,
and needs to know the running depth and whether a fragment of code is
bracket-balanced. This task adds a self-contained bracket-balance scanner to the
`black` package that computes nesting depth over a string of source text,
independent of the tokenizer.

## Files to Create/Modify

- `src/black/bracket_scan.py` (new) — the scanner module described below.
- `tests/test_bracket_scan.py` (new) — the deterministic unit tests for it.

The new module must live in the `black` package and import only from the Python
standard library.

## Requirements

### Public surface

`from black.bracket_scan import max_depth, is_balanced, BracketError` must succeed.
The module exposes exactly the functions `max_depth` and `is_balanced` and the
exception `BracketError` (a subclass of `ValueError`). Private helpers may begin
with `_`.

### Bracket semantics

The recognized bracket pairs are `()`, `[]`, and `{}`. A closing bracket must
match the most recently opened, still-open bracket of the same pair (proper LIFO
nesting). Any bracket characters that appear inside a Python string literal — a
single- or double-quoted run, honoring backslash escapes — must be ignored.

### `is_balanced(text)`

Returns a `bool`: `True` iff every opening bracket in `text` (outside string
literals) is closed by a matching closing bracket in correct nesting order, with
none left open and no stray closing bracket. A closing bracket that does not match
the current open bracket means the text is **not** balanced and `is_balanced`
returns `False` (it does not raise).

### `max_depth(text)`

Returns the maximum bracket nesting depth (an `int` >= 0) reached anywhere in
`text`, considering only correctly nested brackets outside string literals. If
`text` is not balanced, `max_depth` raises `BracketError`.

### Expected Functionality

| Input | `is_balanced` | `max_depth` |
|-------|---------------|-------------|
| `"f(x)"` | `True` | `1` |
| `"a[b[c]]"` | `True` | `2` |
| `"{[()]}"` | `True` | `3` |
| `"()"` then `"()"` (i.e. `"()()"`) | `True` | `1` |
| `"plain text"` | `True` | `0` |
| `'"(" + ")"'` (brackets inside strings) | `True` | `0` |
| `"f(x]"` | `False` | raises `BracketError` |
| `"("` | `False` | raises `BracketError` |
| `")("` | `False` | raises `BracketError` |

### Edge cases

- Brackets inside quoted strings are ignored: `'a = "([{"'` is balanced with
  depth `0`.
- A backslash-escaped quote inside a string does not end the string:
  `'a = "x\\"(y)"'` is balanced with depth `0`.
- An unterminated string literal raises `BracketError` from `max_depth` and makes
  `is_balanced` return `False`.

## Acceptance Criteria

- The module exposes `max_depth`, `is_balanced`, and `BracketError` with the
  behavior above.
- `tests/test_bracket_scan.py` contains at least 12 independent test cases
  (parametrized cases count individually) covering nested depth, mismatched pairs,
  unclosed/stray brackets, brackets inside string literals, an escaped quote, and
  at least three distinct `BracketError`-raising inputs.
- A naive implementation that only counts opens vs. closes (ignoring pair matching
  or string literals) fails the tests.
- The following command passes from the repository root:

  ```bash
  python -m pytest tests/test_bracket_scan.py -q
  ```

- Running the project's configured type checker over the new module reports no errors:

  ```bash
  mypy src/black/bracket_scan.py
  ```
