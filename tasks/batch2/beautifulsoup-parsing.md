# Task: Build a DOM Ancestry and Sibling Navigation Module

## Background
The BeautifulSoup4 repository keeps its tree model under `bs4/` with a matching test suite under `bs4/tests/`. This task adds a small, self-contained navigation utility that, given an HTML document and a way to locate a starting element, walks the surrounding tree to answer questions about ancestors, siblings, and structural position.

## Files to Create/Modify
- `bs4/navigate.py` (new) — the navigation module described below.
- `bs4/tests/test_navigate.py` (new) — the deterministic test suite for the module.

The module must build its document tree using `bs4.BeautifulSoup` and operate entirely in-process: it accepts HTML as a Python string and returns plain Python data structures. It must not perform any network access or file I/O, and it must work using only Python's standard-library HTML parsing (no third-party parser package required).

## Requirements

The module exposes the public functions below. Each accepts an HTML string and returns plain Python objects (`list` / `dict` / `str` / `None`). All functions must work for arbitrary inputs satisfying the contracts, not only the examples shown.

A "target element" is located by an element id: the first element whose `id` attribute equals the given id string.

### `breadcrumb(html, target_id)`
Return a `list[str]` describing the chain of ancestor element tag names from the document's outermost element down to (and including) the target element, in top-to-bottom order.

- The list begins at the highest-level enclosing tag and ends with the target element's own tag name.
- Only element tags are included; text nodes and comments are never included.
- If no element has the given id, return an empty list.

### `nearest_ancestor(html, target_id, tag_name, class_name)`
Return the tag name path is not required; instead return a `dict` describing the closest enclosing ancestor of the target that is a `<tag_name>` element carrying `class_name` among its classes (an element with class attribute `"box card"` carries both `box` and `card`).

- Search ancestors from the target outward (closest first) and stop at the first match.
- The returned dict has keys `id` (the ancestor's `id` attribute, or `None` if absent) and `classes` (a `list[str]` of the ancestor's classes in attribute order).
- If the target is not found, or no matching ancestor exists, return `None`.

### `siblings_of(html, target_id)`
Return a `dict` with keys `previous` and `next`, each a `list[str]` of the tag names of the target's element siblings (sharing the same parent), in document order.

- `previous` lists element siblings that appear before the target; `next` lists those that appear after it. Both exclude the target itself.
- Whitespace/text nodes between elements must never appear in either list.
- If the target is not found, return `{"previous": [], "next": []}`.

### `depth_of(html, target_id)`
Return the nesting depth of the target as an `int`: the number of element ancestors strictly above it. A target whose only enclosing element is the document's top-level tag has depth `1` relative to that top element. If the target is not found, return `-1`.

### Cross-cutting requirements
- **Graceful absence**: a missing target id never raises; it yields the documented empty/`None`/`-1` result.
- **Malformed HTML tolerated**: inputs with unclosed or improperly nested tags must still parse and produce results for the recoverable structure, without raising.
- **Text nodes ignored**: every traversal counts and reports element tags only.

### Expected Functionality
- For `<div><section><p id="t">x</p></section></div>`, `breadcrumb(html, "t")` ends with `"p"` and contains `"section"` and `"div"` in top-to-bottom order.
- `nearest_ancestor` for a target wrapped in `<div class="outer card">...<div class="inner">target</div>` with `tag_name="div", class_name="card"` returns the outer div's info, not the inner one.
- For a target with two element siblings before it and one after, `siblings_of` returns lists of length 2 and 1 respectively, ignoring intervening whitespace.
- `depth_of` for an element three element-levels below the top tag returns `3`.
- A missing id returns `[]` / `None` / the empty-sibling dict / `-1` respectively.

## Acceptance Criteria
- A new module `bs4/navigate.py` exists and exposes `breadcrumb`, `nearest_ancestor`, `siblings_of`, and `depth_of` with the behavior above.
- A new test file `bs4/tests/test_navigate.py` exercises every function, including ancestor-chain ordering, closest-ancestor selection by tag+class, sibling separation with intervening whitespace, depth counting, and all missing-target cases.
- All parsing is performed on in-memory HTML strings; tests perform no network or file access and require no third-party parser package.
- The following command passes from the repository root with all tests collected and green:

  ```
  python -m pytest bs4/tests/test_navigate.py -v
  ```
