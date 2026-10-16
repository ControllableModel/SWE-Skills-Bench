# Task: Build a Document Heading Outline Module

## Background
The BeautifulSoup4 repository keeps its tree model under `bs4/` with tests under `bs4/tests/`. This task adds a self-contained utility that scans an HTML document's headings (`<h1>`..`<h6>`) and produces a structured outline / table of contents, the way a documentation tool builds a nav sidebar.

## Files to Create/Modify
- `bs4/outline.py` (new) — the outline module described below.
- `bs4/tests/test_outline.py` (new) — the deterministic test suite for the module.

The module must build its tree using `bs4.BeautifulSoup`, operate entirely in-process on an HTML string, perform no network or file access, and work using only Python's standard-library HTML parsing (no third-party parser package required).

## Requirements

The module exposes the public functions below. All functions must work for arbitrary conforming inputs, not only the examples shown.

A "heading" is any of `<h1>`, `<h2>`, `<h3>`, `<h4>`, `<h5>`, `<h6>`. Its level is the digit in its tag name (1..6).

### `headings(html)`
Return a `list[dict]`, one per heading in document order. Each dict has exactly these keys:

- `level` — an `int` 1..6.
- `text` — the heading's stripped visible text, with internal whitespace runs (including those spanning nested inline tags) collapsed to single spaces; `""` if empty.
- `id` — the heading's `id` attribute, or `None` if absent.

### `slugify_anchor(text)`
Return a URL-fragment slug `str` for a heading title:

- lowercase the text,
- replace every maximal run of non-alphanumeric characters with a single hyphen `"-"`,
- strip leading and trailing hyphens.

For example `"  Getting Started: Part 2!  "` -> `"getting-started-part-2"`. An input that reduces to nothing returns `""`.

### `table_of_contents(html)`
Return a `list[dict]` of entries for building a TOC, one per heading in document order. Each entry has keys:

- `level` — the heading level (`int`).
- `text` — the heading's normalized text (as in `headings`).
- `anchor` — the heading's `id` attribute if it has one; otherwise `slugify_anchor` of its text.

### `nest_outline(html)`
Return a nested tree built from the headings, as a `list` of root nodes. Each node is a `dict` with keys `level` (`int`), `text` (`str`), and `children` (`list` of nodes). A heading becomes a child of the nearest preceding heading whose level is strictly smaller; headings with no smaller-level predecessor are roots. Document order is preserved among siblings.

### Cross-cutting requirements
- **Level is derived structurally** from the tag name and must be correct for any of h1..h6.
- **Text normalization** matches across all functions (trimmed, single-spaced, nested inline tags included).
- **Malformed HTML tolerated**: unclosed or improperly nested tags must still parse and produce results for the recoverable structure, without raising.

### Expected Functionality
- A document with `h1`, then `h2`, then `h2`, then `h3` -> `headings` lists four dicts with levels `[1,2,2,3]` in order.
- A heading `<h2 id="intro">Intro</h2>` -> its TOC `anchor` is `"intro"`; a heading without an id uses its slug.
- `slugify_anchor("Getting Started: Part 2!")` -> `"getting-started-part-2"`.
- `nest_outline` for `h1 > (h2, h2 > h3)` -> one root (`h1`) with two children, the second child having one child (`h3`).
- An `<h3>` whose text spans `<code>` and `<em>` tags with newlines -> normalized single-spaced text.
- A document with no headings -> every function returns `[]` (and `slugify_anchor("")` returns `""`).

## Acceptance Criteria
- A new module `bs4/outline.py` exists and exposes `headings`, `slugify_anchor`, `table_of_contents`, and `nest_outline` with the behavior above.
- A new test file `bs4/tests/test_outline.py` exercises every function, including level derivation across h1..h6, text normalization across nested tags, id-vs-slug anchor selection, slug edge cases (punctuation runs, leading/trailing separators, empty), and the nesting rule for skipped/repeated levels.
- All parsing is on in-memory HTML strings; tests perform no network or file access and require no third-party parser package.
- The following command passes from the repository root with all tests collected and green:

  ```
  python -m pytest bs4/tests/test_outline.py -v
  ```
