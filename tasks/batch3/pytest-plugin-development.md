# Task: Add a marker-expression token scanner with an exhaustive test suite

## Background

The pytest codebase (`pytest-dev/pytest`) selects tests using `-m` / `-k`
boolean expressions over identifiers (see `src/_pytest/mark/expression.py`).
This task adds a small, self-contained tokenizer module under `src/_pytest/`
that turns such an expression into a token stream, plus a thorough test module
under `testing/`.

## Files to Create/Modify

- `src/_pytest/_exprscan.py` (new) — the tokenizer module described below.
- `testing/test_exprscan_util.py` (new) — the test module for the tokenizer.

## Requirements

Implement `src/_pytest/_exprscan.py` as a pure, dependency-free module (only the
Python standard library and `from __future__ import annotations` are allowed — no
imports from other `_pytest` modules). It MUST export exactly the following with
the listed behavior. The test module `testing/test_exprscan_util.py` MUST verify
every behavior, constraint, and edge case enumerated here, including each
distinct failure mode.

### `Token` (data type)

A token MUST have two readable attributes: `kind` (a `str`) and `value` (a
`str`). Two tokens with the same `kind` and `value` MUST compare equal.

### `scan(expr: str) -> list[Token]`

Scans a boolean expression into a list of tokens.

- The recognized token kinds are exactly: `"NAME"` (an identifier), `"AND"`,
  `"OR"`, `"NOT"`, `"LPAREN"`, and `"RPAREN"`.
- An identifier matches `[A-Za-z_][A-Za-z0-9_.-]*`; its `value` is the matched
  text.
- The bare words `and`, `or`, `not` (lowercase only) become `AND`/`OR`/`NOT`
  tokens; mixed-case like `And` is a `NAME`.
- `(` and `)` become `LPAREN` / `RPAREN`; their `value` is the literal char.
- Arbitrary whitespace between tokens is skipped and does not appear in the
  output.
- An empty or whitespace-only expression returns an empty list.
- An unexpected character (e.g. `"a & b"` containing `&`) MUST raise
  `ValueError` whose message contains both the offending character and its
  zero-based position in the original string.

### Expected Functionality

- The number of tokens for `"not (slow or fast)"` is 6 with kinds
  `["NOT", "LPAREN", "NAME", "OR", "NAME", "RPAREN"]`.
- Identifiers containing `.` and `-` (e.g. `"web-ui.smoke"`) scan as a single
  `NAME` token.
- Adjacent parentheses without spaces (e.g. `"(a)"`) tokenize correctly into
  `LPAREN NAME RPAREN`.
- The reported error position for the first illegal character is exact (verify
  with at least two inputs where the bad character is not at index 0).

### Constraints

- `scan` is pure (no I/O, no global mutable state, deterministic).
- No third-party packages and no other `_pytest` imports.
- The `ValueError` message MUST include the offending character and its index.

## Acceptance Criteria

- `src/_pytest/_exprscan.py` exists and exports `Token` and `scan` with the
  behavior specified above.
- `testing/test_exprscan_util.py` contains test functions asserting every
  behavior and failure mode: keyword vs identifier disambiguation (including the
  mixed-case `NAME` case), `.`/`-` identifiers, parentheses, whitespace
  skipping, the empty-input empty-list case, token equality, and the
  illegal-character `ValueError` with an exact non-zero position.
- The following command passes with every test collected and no failures:

  ```
  python -m pytest testing/test_exprscan_util.py -p no:cacheprovider -q
  ```

- A partial or hardcoded implementation that does not handle each enumerated edge
  case MUST cause at least one assertion in `testing/test_exprscan_util.py` to
  fail.
