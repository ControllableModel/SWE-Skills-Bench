# Task: Build a Definition-List Specification Extraction Module

## Background
The BeautifulSoup4 repository keeps its tree model under `bs4/` with tests under `bs4/tests/`. This task adds a self-contained utility that reads key/value style markup — definition lists (`<dl>`) and label/value pairs — from a product or article page and returns the specifications as structured Python data.

## Files to Create/Modify
- `bs4/specs.py` (new) — the specification-extraction module described below.
- `bs4/tests/test_specs.py` (new) — the deterministic test suite for the module.

The module must build its tree using `bs4.BeautifulSoup`, operate entirely in-process on an HTML string, perform no network or file access, and work using only Python's standard-library HTML parsing (no third-party parser package required).

## Requirements

The module exposes the public functions below. All functions must work for arbitrary conforming inputs, not only the examples shown.

All extracted text is whitespace-normalized: leading/trailing whitespace removed and internal whitespace runs (including those spanning nested inline tags) collapsed to single spaces.

### `extract_dl(html)`
Parse the first `<dl>` element into a `list[dict]`, one per term/definition pairing, in document order. Each `<dt>` is a term; the `<dd>` elements that follow it (until the next `<dt>`) are its definitions. Each dict has keys:

- `term` — the normalized text of the `<dt>`.
- `values` — a `list[str]` of the normalized text of each following `<dd>` (possibly more than one), in document order.

A `<dt>` followed by no `<dd>` has `values == []`. If there is no `<dl>`, return `[]`.

### `dl_to_dict(html)`
Return a `dict[str, str]` mapping each `<dt>` term to a single value taken from its first following `<dd>` (normalized), using the first `<dl>` in the document.

- A term with no `<dd>` maps to `""`.
- When two `<dt>` elements share the same normalized term text, the first one wins.
- No `<dl>` -> `{}`.

### `spec_table(html)`
Many spec sheets use a two-column `<table>` instead of a `<dl>`: each `<tr>` has a label cell followed by a value cell. Return a `dict[str, str]` mapping the normalized text of the first cell (`<th>` or `<td>`) of each row to the normalized text of the second cell, for the first `<table>` in the document.

- Rows with fewer than two cells are skipped.
- When two rows share the same label, the first wins.
- No `<table>` -> `{}`.

### `find_value(html, label)`
Return the value associated with a given `label` (matched by normalized, case-insensitive text), searching first the first `<dl>` (term match) and then the first two-column `<table>` (first-cell match), returning the first match found. Return `None` if the label is not present in either structure.

### Cross-cutting requirements
- **Term/definition association** in `<dl>` follows document order: each `<dd>` belongs to the most recent preceding `<dt>`.
- **First-wins** on duplicate keys is applied consistently across `dl_to_dict` and `spec_table`.
- **Graceful absence / malformed input**: missing `<dd>`/cells yield documented defaults; malformed or partially recoverable HTML must not raise.

### Expected Functionality
- A `<dl>` where one `<dt>` is followed by two `<dd>` elements -> that term's `values` list has length 2; a `<dt>` with no `<dd>` has `values == []`.
- `dl_to_dict` maps each term to its first definition, mapping a term with no definition to `""` and keeping the first of duplicate terms.
- A two-column `<table>` whose label cells are `<th>` and value cells are `<td>` -> `spec_table` maps label text to value text; a row with a single cell is skipped.
- `find_value(html, "Weight")` returns the matching value whether it lives in the `<dl>` or the spec `<table>`, case-insensitively; an absent label returns `None`.
- A document with neither a `<dl>` nor a `<table>` -> `extract_dl == []`, `dl_to_dict == {}`, `spec_table == {}`, `find_value(...) is None`.

## Acceptance Criteria
- A new module `bs4/specs.py` exists and exposes `extract_dl`, `dl_to_dict`, `spec_table`, and `find_value` with the behavior above.
- A new test file `bs4/tests/test_specs.py` exercises every function, including multi-`<dd>` terms, empty-definition terms, duplicate-key first-wins, two-column table mapping with a short row skipped, case-insensitive cross-structure `find_value`, and the empty-document case.
- All parsing is on in-memory HTML strings; tests perform no network or file access and require no third-party parser package.
- The following command passes from the repository root with all tests collected and green:

  ```
  python -m pytest bs4/tests/test_specs.py -v
  ```
