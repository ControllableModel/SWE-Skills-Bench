# Task: Build an Article Text Extraction Module

## Background
The BeautifulSoup4 repository keeps its tree model under `bs4/` with tests under `bs4/tests/`. This task adds a self-contained "readability"-style utility that turns a noisy HTML page into clean article text and paragraph structure, stripping out boilerplate such as scripts, styles, and navigation chrome.

## Files to Create/Modify
- `bs4/reader.py` (new) — the text-extraction module described below.
- `bs4/tests/test_reader.py` (new) — the deterministic test suite for the module.

The module must build its tree using `bs4.BeautifulSoup`, operate entirely in-process on an HTML string, perform no network or file access, and work using only Python's standard-library HTML parsing (no third-party parser package required).

## Requirements

The module exposes the public functions below. All functions must work for arbitrary conforming inputs, not only the examples shown.

The "article root" is the first `<article>` element if one exists; otherwise the document's `<body>`; otherwise the whole document.

### `clean_text(html)`
Return a single `str`: the visible text of the article root with all noise removed and whitespace normalized.

- The text of any `<script>`, `<style>`, `<noscript>`, and `<template>` element anywhere inside the root must be excluded entirely.
- The remaining text is joined so that the text of separate elements is separated by a single space, with no leading/trailing whitespace and no internal runs of whitespace (spaces, tabs, newlines) longer than one space.
- If the article root contains no visible text, return `""`.

### `paragraphs(html)`
Return a `list[str]` of the cleaned text of each `<p>` element inside the article root, in document order.

- Each paragraph's text is whitespace-normalized exactly as in `clean_text` (collapsed internal whitespace, trimmed ends), and the text of nested inline tags (`<a>`, `<em>`, `<strong>`, …) is included.
- A `<p>` that contains only whitespace (or only removed-noise elements) is omitted from the list.

### `word_count(html)`
Return an `int`: the number of whitespace-delimited tokens in the result of `clean_text(html)`. An empty cleaned text yields `0`.

### `first_paragraph(html)`
Return the cleaned text of the first non-empty `<p>` in the article root, or `""` if there is none. This must be consistent with the first entry of `paragraphs(html)` when that list is non-empty.

### Cross-cutting requirements
- **Noise removal is structural**: script/style/noscript/template content must not leak into any returned text even when those elements are deeply nested or interleaved with article content.
- **Whitespace normalization** is applied uniformly: results never contain leading/trailing whitespace or multi-space gaps.
- **Malformed HTML tolerated**: unclosed or improperly nested tags must still parse and produce results for the recoverable structure, without raising.

### Expected Functionality
- A page where an `<article>` contains a `<script>` between two `<p>` elements -> `clean_text` includes neither the script source text nor stray blank gaps; `paragraphs` returns exactly the two paragraph strings.
- A `<p>` whose text spans nested `<strong>`/`<a>` tags with embedded newlines -> that paragraph is returned as a single space-collapsed string.
- A `<p>` containing only a `<style>` block (no visible text) -> omitted from `paragraphs`.
- `word_count` over text that normalizes to `"hello brave new world"` -> `4`.
- A document with no `<article>` falls back to `<body>`; one with neither falls back to the whole document.

## Acceptance Criteria
- A new module `bs4/reader.py` exists and exposes `clean_text`, `paragraphs`, `word_count`, and `first_paragraph` with the behavior above.
- A new test file `bs4/tests/test_reader.py` exercises every function, including noise-element removal, whitespace collapsing across nested inline tags, empty-paragraph omission, the article/body/document fallback chain, and word counting.
- All parsing is on in-memory HTML strings; tests perform no network or file access and require no third-party parser package.
- The following command passes from the repository root with all tests collected and green:

  ```
  python -m pytest bs4/tests/test_reader.py -v
  ```
