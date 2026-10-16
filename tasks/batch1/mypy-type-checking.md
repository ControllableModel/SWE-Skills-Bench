# Task: Add a Configuration Value Coercion Helper

## Background

Black reads configuration from `pyproject.toml` and from command-line flags, and the values that arrive from these two sources are not uniformly typed: a TOML file may yield a real `int`, `bool`, or `list`, while an equivalent value coming from an environment override or a raw string flag arrives as text. This task adds a small, self-contained helper module to the `black` package that turns these loosely-typed raw inputs into well-defined Python values, with predictable behavior for every supported option kind.

## Files to Create/Modify

- `src/black/option_coerce.py` (new) — the coercion helper module described below.
- `tests/test_option_coerce.py` (new) — the deterministic unit tests for the new module.

The new module must live in the `black` package and must not import anything outside the Python standard library (it must not depend on `click`, `tomllib`, or any other part of `black`).

## Requirements

### Public surface

The module must expose exactly the following names (and may add private helpers beginning with `_`):

- A class `OptionSpec` describing how a single option is coerced.
- A function `coerce_value`.
- A function `coerce_mapping`.
- An exception type `CoercionError` (a subclass of `ValueError`).

`from black.option_coerce import OptionSpec, coerce_value, coerce_mapping, CoercionError` must succeed.

### `OptionSpec`

`OptionSpec` describes one option and carries three pieces of information:

- `kind` — one of the string tags `"int"`, `"bool"`, `"str"`, `"str_list"`, or `"choice"`. No other tag is permitted; constructing an `OptionSpec` with any other tag must raise `CoercionError`.
- `required` — a boolean (default `False`).
- `choices` — for `kind == "choice"`, the ordered collection of allowed string values; for every other kind it must be empty/absent.

Constructing a `"choice"` spec with an empty set of choices must raise `CoercionError`. Constructing a non-`"choice"` spec that is nevertheless given choices must also raise `CoercionError`.

### `coerce_value(spec, raw)`

`coerce_value` takes an `OptionSpec` and a single raw input value and returns the coerced value. The returned runtime type depends on `spec.kind`:

- `"int"` -> an `int`.
- `"bool"` -> a `bool`.
- `"str"` and `"choice"` -> a `str`.
- `"str_list"` -> a `list` of `str`.

Coercion rules per kind:

- `"int"`: an input that is already an `int` (but not a `bool`) is returned unchanged; a `str` that represents a base-10 integer (optionally signed, surrounding whitespace allowed) is converted; anything else raises `CoercionError`. A `bool` input must be rejected even though Python treats `bool` as an `int`.
- `"bool"`: an input that is already a `bool` is returned unchanged; the strings `"true"`, `"1"`, `"yes"`, `"on"` (case-insensitive, surrounding whitespace allowed) become `True`, and `"false"`, `"0"`, `"no"`, `"off"` become `False`; anything else raises `CoercionError`.
- `"str"`: an input that is already a `str` is returned unchanged; an `int` or `bool` input is rejected with `CoercionError` (numbers are not silently stringified).
- `"str_list"`: a `list`/`tuple` whose every element is a `str` is returned as a new `list` of those strings; a single `str` is split on commas with surrounding whitespace stripped from each piece and empty pieces dropped (so `"a, b ,c"` -> `["a", "b", "c"]` and `""` -> `[]`); any other input, or a list containing a non-`str` element, raises `CoercionError`.
- `"choice"`: the input must be a `str` that, after stripping surrounding whitespace, is one of `spec.choices`; the matched canonical choice value is returned. Any non-string input, or a string not in the allowed set, raises `CoercionError`.

When `raw` is `None`: if `spec.required` is `True`, raise `CoercionError`; otherwise return `None`.

### `coerce_mapping(specs, raw_values)`

`coerce_mapping` takes a mapping from option name to `OptionSpec` and a mapping from option name to raw value, and returns a new mapping from option name to coerced value.

- Every key present in `specs` must appear in the result. If a name is missing from `raw_values`, it is treated as if its raw value were `None` (so a required option that is absent raises `CoercionError`, and a non-required absent option maps to `None`).
- A key present in `raw_values` but absent from `specs` is an unknown option and must raise `CoercionError`.
- Coercion failures must surface as `CoercionError`; the error message must mention the offending option name.

### Edge cases

- `"int"` coercion of the strings `" -7 "` and `"+12"` succeeds (yielding `-7` and `12`); `"3.0"`, `"0x1f"`, and `""` fail.
- `"bool"` coercion is case-insensitive: `"TRUE"`, `" On "` succeed.
- `"str_list"` coercion of `["x", "y"]` yields a brand-new list equal to `["x", "y"]` (not the same object as the input).
- A non-required option whose raw value is `None` yields `None` regardless of `kind`.

## Acceptance Criteria

- The new module exposes `OptionSpec`, `coerce_value`, `coerce_mapping`, and `CoercionError` with the behavior described above.
- All behaviors and edge cases above are exercised by `tests/test_option_coerce.py`, which must contain at least 12 independent test cases (parametrized cases count individually) covering every `kind`, the `None`/`required` interaction, the unknown-option path, and at least three distinct `CoercionError`-raising inputs.
- The implementation is fully self-contained (standard library only) and a naive implementation that ignores the `kind` distinctions or skips the `bool`/`int` and numeric-`str` rejections fails the tests.
- The following command passes from the repository root:

  ```bash
  python -m pytest tests/test_option_coerce.py -q
  ```

- The new module is consistent with the repository's existing static-analysis gate: running the project's configured type checker over the new module reports no errors:

  ```bash
  mypy src/black/option_coerce.py
  ```
