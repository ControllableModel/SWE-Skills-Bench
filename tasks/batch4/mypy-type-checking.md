# Task: Add a Numeric-Literal Classifier

## Background

Black inspects Python numeric literals (integers, floats, hex/octal/binary,
scientific notation, complex numbers) so it can apply the right canonicalization
to each kind. This task adds a self-contained classifier to the `black` package
that, given the source text of a numeric literal, reports which category it
belongs to — independent of the rest of the formatter.

## Files to Create/Modify

- `src/black/numeric_kind.py` (new) — the classifier module described below.
- `tests/test_numeric_kind.py` (new) — the deterministic unit tests for it.

The new module must live in the `black` package and import only from the Python
standard library.

## Requirements

### Public surface

`from black.numeric_kind import NumericKind, classify_numeric, NumericError`
must succeed. The module exposes exactly an `enum.Enum` named `NumericKind`, a
function `classify_numeric`, and an exception `NumericError` (a subclass of
`ValueError`). Private helpers may begin with `_`.

### `NumericKind`

An `Enum` with exactly these members (the enum's values are unimportant but must
be distinct): `DECIMAL_INT`, `HEX`, `OCTAL`, `BINARY`, `FLOAT`, `SCIENTIFIC`,
`COMPLEX`.

### `classify_numeric(text)`

Given the literal source `text` (a `str`), return the corresponding `NumericKind`.
Underscores used as digit separators are permitted inside the digit runs and must
not change the classification. Classification rules (case-insensitive on the base
prefix and on `e`/`j`):

- Starts with `0x` -> `HEX`; `0o` -> `OCTAL`; `0b` -> `BINARY`.
- Ends with `j` (and is otherwise a valid int/float magnitude) -> `COMPLEX`.
- Contains an exponent marker `e` (with a valid mantissa) -> `SCIENTIFIC`.
- Contains a `.` but no exponent -> `FLOAT`.
- Otherwise a run of decimal digits -> `DECIMAL_INT`.

Any input that is empty, not a `str`, or not a well-formed numeric literal under
these rules raises `NumericError`.

### Expected Functionality

| Input | Result |
|-------|--------|
| `"42"` | `DECIMAL_INT` |
| `"1_000"` | `DECIMAL_INT` |
| `"0xFF"` | `HEX` |
| `"0o17"` | `OCTAL` |
| `"0b1010"` | `BINARY` |
| `"3.14"` | `FLOAT` |
| `"1.5e10"` | `SCIENTIFIC` |
| `"2E-3"` | `SCIENTIFIC` |
| `"10j"` | `COMPLEX` |
| `"3.0J"` | `COMPLEX` |

### Edge cases

- `"1_0.5_0"` -> `FLOAT`; `"0x_FF"` is rejected only if `text` is not a
  well-formed literal — `"0xFF_FF"` -> `HEX`.
- `""`, `"abc"`, `"0xG1"`, `"1.2.3"`, `"1e"` each raise `NumericError`.
- A non-`str` argument raises `NumericError`.

## Acceptance Criteria

- The module exposes `NumericKind`, `classify_numeric`, and `NumericError` with
  the behavior above.
- `tests/test_numeric_kind.py` contains at least 12 independent test cases
  (parametrized cases count individually) covering every `NumericKind` member, an
  underscore-separated case, and at least three distinct `NumericError`-raising
  inputs (including a malformed literal and a non-string).
- A naive implementation that only checks for a `.` or a leading `0x` (and so
  misclassifies complex, scientific, or underscore-bearing literals) fails the tests.
- The following command passes from the repository root:

  ```bash
  python -m pytest tests/test_numeric_kind.py -q
  ```

- Running the project's configured type checker over the new module reports no errors:

  ```bash
  mypy src/black/numeric_kind.py
  ```
