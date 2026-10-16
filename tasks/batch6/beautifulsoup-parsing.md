# Task: Build a CSS-Selector Query Helper Module

## Background
The BeautifulSoup4 repository keeps its tree model under `bs4/` with tests under `bs4/tests/`. This task adds a self-contained query helper that runs CSS-style selectors against an HTML document and returns convenient, structured results for the matched elements.

## Files to Create/Modify
- `bs4/query.py` (new) — the query-helper module described below.
- `bs4/tests/test_query.py` (new) — the deterministic test suite for the module.

The module must build its tree using `bs4.BeautifulSoup`, operate entirely in-process on an HTML string, perform no network or file access, and work using only Python's standard-library HTML parsing (no third-party parser package required).

## Requirements

The module exposes the public functions below. All functions must work for arbitrary conforming inputs, not only the examples shown.

### `count_matches(html, selector)`
Return an `int`: the number of elements in the document matching the given CSS selector. A selector matching nothing returns `0`.

### `texts(html, selector)`
Return a `list[str]` of the stripped visible text of every element matching `selector`, in document order. Elements matching the selector but containing no visible text contribute the empty string `""` (they are not dropped). The order corresponds one-to-one with the matched elements.

### `attrs_of(html, selector, attr)`
Return a `list` containing, for each element matching `selector` in document order, the value of attribute `attr` if the element has it, otherwise `None`. The returned list has exactly one entry per matched element (including `None` entries), preserving order and duplicates.

### `first_text(html, selector, default="")`
Return the stripped text of the first element matching `selector`, or `default` if nothing matches. This must equal the first entry of `texts(html, selector)` when there is at least one match.

### `pluck(html, row_selector, fields)`
Return a `list[dict]`, one dict per element matching `row_selector` in document order. `fields` is a `dict` mapping output key -> sub-selector string. For each matched "row" element and each `(key, sub_selector)`:

- the value is the stripped text of the first descendant of the row matching `sub_selector`,
- or `""` when the row has no descendant matching that sub-selector.

Every output dict has exactly the keys present in `fields`.

### Cross-cutting requirements
- **Scoping**: in `pluck`, each sub-selector is resolved relative to its row element, so two rows with the same internal structure produce independent values.
- **Stable cardinality**: `texts`, `attrs_of`, and `pluck` always return one entry per matched element/row — empty matches become `""`/`None`/`""` rather than being skipped.
- **Malformed HTML tolerated**: unclosed or improperly nested tags must still parse and produce results for the recoverable structure, without raising.

### Expected Functionality
- `count_matches(html, "ul.menu > li")` returns the number of direct `<li>` children of any `<ul class="menu">`.
- For three matched elements where the middle one is empty, `texts` returns a length-3 list with `""` in the middle position.
- `attrs_of(html, "a", "href")` over anchors where one lacks `href` returns a list with `None` in that anchor's position.
- `pluck(html, ".card", {"title": "h3", "price": ".price"})` over two cards, the second of which has no `.price`, returns two dicts, the second with `price == ""`.
- A selector matching nothing -> `count_matches == 0`, `texts == []`, `attrs_of == []`, `pluck == []`, and `first_text` returns the default.

## Acceptance Criteria
- A new module `bs4/query.py` exists and exposes `count_matches`, `texts`, `attrs_of`, `first_text`, and `pluck` with the behavior above.
- A new test file `bs4/tests/test_query.py` exercises every function, including descendant/child/class selectors, empty-match placeholders for `texts`/`attrs_of`, row-scoped `pluck` with a missing sub-field, the `first_text` default, and the no-match case.
- All parsing is on in-memory HTML strings; tests perform no network or file access and require no third-party parser package.
- The following command passes from the repository root with all tests collected and green:

  ```
  python -m pytest bs4/tests/test_query.py -v
  ```
