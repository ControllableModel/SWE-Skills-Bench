# Task: Add a String-Prefix Normalizer

## Background

Black normalizes Python string-literal prefixes (the letters before the opening
quote, such as `f`, `r`, `b`, `u` and their combinations) so that they are
emitted in a canonical, lowercase, ordered form. This task adds a self-contained
helper to the `black` package that parses and canonicalizes such a prefix,
independent of the tokenizer and the rest of the formatter.

## Files to Create/Modify

- `src/black/prefix_normalize.py` (new) — the prefix-normalizer module described below.
- `tests/test_prefix_normalize.py` (new) — the deterministic unit tests for it.

The new module must live in the `black` package and import only from the Python
standard library.

## Requirements

### Public surface

`from black.prefix_normalize import normalize_prefix, split_prefix, PrefixError`
must succeed. The module exposes exactly `normalize_prefix`, `split_prefix`, and
`PrefixError` (a subclass of `ValueError`). Private helpers may begin with `_`.

### Allowed letters

Only the letters `f`, `r`, `b`, `u` (in any letter case) are valid prefix
characters. The recognized two-letter combinations are exactly the case-insensitive
pairs drawn from `{f, r}` and `{b, r}` (i.e. `fr`/`rf` and `br`/`rb`). `u` may only
appear alone. Any other letter, any combination of more than two letters, and any
disallowed pair (e.g. `fb`, `ub`, `ur`) is invalid.

### `split_prefix(token)`

Given a string-literal token such as `Rb"data"` or `'plain'`, `split_prefix`
returns a 2-tuple `(prefix, rest)` where `prefix` is the leading run of prefix
letters (possibly empty) and `rest` is the remainder of the token starting at the
opening quote. The token must contain a single or double quote; a token with no
quote character raises `PrefixError`.

### `normalize_prefix(prefix)`

Given just the prefix substring (which may be empty), return the canonical form:

- All letters lowercased.
- The empty prefix returns `""`.
- A `u` prefix (any case) returns `""` (the `u` is dropped, matching Black's
  behavior of removing redundant `u` prefixes).
- For two-letter prefixes, the letters are emitted in a fixed canonical order:
  the non-`r` letter first, then `r` (so `Rb` -> `br`, `RF` -> `fr`, `fR` -> `fr`).
- A single `f`, `r`, or `b` returns itself lowercased.
- Any invalid prefix (per the rules above) raises `PrefixError`.

### Edge cases

- `normalize_prefix("")` -> `""`; `normalize_prefix("U")` -> `""`.
- `normalize_prefix("RB")` -> `"br"`; `normalize_prefix("rf")` -> `"fr"`.
- `normalize_prefix("fb")`, `normalize_prefix("ru")`, `normalize_prefix("xyz")`
  each raise `PrefixError`.
- `split_prefix('Rb"x"')` -> `("Rb", '"x"')`; `split_prefix("'x'")` -> `("", "'x'")`.

## Acceptance Criteria

- The module exposes `normalize_prefix`, `split_prefix`, and `PrefixError` with
  the behavior above.
- `tests/test_prefix_normalize.py` contains at least 12 independent test cases
  (parametrized cases count individually) covering empty, single, both canonical
  two-letter orderings, `u`-dropping, the split contract, and at least three
  distinct `PrefixError`-raising inputs.
- A naive implementation that merely lowercases without enforcing the allowed-set,
  ordering, and `u`-dropping rules fails the tests.
- The following command passes from the repository root:

  ```bash
  python -m pytest tests/test_prefix_normalize.py -q
  ```

- Running the project's configured type checker over the new module reports no errors:

  ```bash
  mypy src/black/prefix_normalize.py
  ```
