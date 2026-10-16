# Task: Build an HTML Form Field Extraction Module

## Background
The BeautifulSoup4 repository ships its parser/tree code under `bs4/` with tests under `bs4/tests/`. This task adds a self-contained utility that reads an HTML `<form>` and reports its fields and their attributes as structured Python data, suitable for documenting or auto-filling a form.

## Files to Create/Modify
- `bs4/forms.py` (new) — the form-extraction module described below.
- `bs4/tests/test_forms.py` (new) — the deterministic test suite for the module.

The module must build its tree using `bs4.BeautifulSoup`, operate entirely in-process on an HTML string, perform no network or file access, and work using only Python's standard-library HTML parsing (no third-party parser package required).

## Requirements

The module exposes the public functions below. All functions must work for arbitrary conforming inputs, not only the examples shown.

The module operates on the first `<form>` element in the document.

### `form_action(html)`
Return a `dict` describing the form envelope with exactly these keys:

- `action` — the form's `action` attribute, or `""` if absent.
- `method` — the form's `method` attribute lowercased (e.g. `"POST"` -> `"post"`); default `"get"` when the attribute is absent.
- `enctype` — the form's `enctype` attribute, or `None` if absent.

If the document has no form, return `None`.

### `extract_fields(html)`
Return a `list[dict]`, one entry per field control inside the first form, in document order. A field control is any `<input>`, `<textarea>`, or `<select>` element. Each dict has exactly these keys:

- `tag` — the control's tag name (`"input"`, `"textarea"`, or `"select"`).
- `name` — the `name` attribute, or `None` if absent.
- `type` — for `<input>`, its `type` attribute lowercased, defaulting to `"text"` when absent; for `<textarea>` the literal `"textarea"`; for `<select>` the literal `"select"`.
- `required` — a `bool`, `True` when the control carries a `required` attribute (regardless of the attribute's value), else `False`.
- `value` — the control's `value` attribute, or `None` if absent. (For `<textarea>`, `value` is `None`.)

### `select_options(html, field_name)`
Return a `list[dict]` of the `<option>` elements belonging to the `<select>` whose `name` equals `field_name`, in document order. Each dict has keys:

- `value` — the option's `value` attribute if present, otherwise its stripped visible text.
- `label` — the option's stripped visible text.
- `selected` — a `bool`, `True` when the option carries a `selected` attribute.

If there is no select with that name, return an empty list.

### `required_field_names(html)`
Return a `list[str]` of the `name` values of all required field controls in the first form, in document order. Controls without a `name` are omitted even if required.

### Cross-cutting requirements
- **Missing attributes** yield the documented defaults rather than raising; no function raises on a well-formed-but-incomplete form.
- **Boolean attributes** (`required`, `selected`) are recognized by presence, including the valueless HTML form (`<input required>`).
- **Malformed HTML tolerated**: unclosed or improperly nested tags must still parse and produce results for the recoverable structure.

### Expected Functionality
- `<form method="POST" action="/submit">` -> `form_action` returns `{"action": "/submit", "method": "post", "enctype": None}`.
- An `<input required>` with no explicit value -> field dict has `required is True`, `value is None`, `type == "text"`.
- A `<select name="country">` with three options, the middle one carrying `selected`, and one option lacking a `value` -> `select_options` returns three dicts with the correct `selected` flags and the value-less option's `value` equal to its text.
- `required_field_names` returns only the names of required controls, skipping any required control without a `name`.
- A document with no form -> `form_action` returns `None`, `extract_fields` returns `[]`.

## Acceptance Criteria
- A new module `bs4/forms.py` exists and exposes `form_action`, `extract_fields`, `select_options`, and `required_field_names` with the behavior above.
- A new test file `bs4/tests/test_forms.py` exercises every function, including method defaulting/lowercasing, boolean-attribute detection, option value-fallback and selected flags, required-name filtering, and the no-form case.
- All parsing is on in-memory HTML strings; tests perform no network or file access and require no third-party parser package.
- The following command passes from the repository root with all tests collected and green:

  ```
  python -m pytest bs4/tests/test_forms.py -v
  ```
