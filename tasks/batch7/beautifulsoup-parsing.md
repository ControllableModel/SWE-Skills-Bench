# Task: Build a Link Auditing and Classification Module

## Background
The BeautifulSoup4 repository keeps its tree model under `bs4/` with tests under `bs4/tests/`. This task adds a self-contained utility that audits the hyperlinks of an HTML page: resolving them against a base URL, classifying them, and grouping them by host — the kind of pass a crawler runs before deciding what to follow.

## Files to Create/Modify
- `bs4/links.py` (new) — the link-auditing module described below.
- `bs4/tests/test_links.py` (new) — the deterministic test suite for the module.

The module must build its tree using `bs4.BeautifulSoup`, operate entirely in-process on an HTML string (and a base-URL string), perform no network or file access, and work using only Python's standard-library HTML parsing (no third-party parser package required).

## Requirements

The module exposes the public functions below. All functions must work for arbitrary conforming inputs, not only the examples shown.

A "link" is any `<a>` element that has an `href` attribute. The base URL is always an absolute URL such as `"https://shop.example.com/catalog/"`.

### `classify_links(html, base_url)`
Return a `list[dict]`, one per link in document order. Each dict has exactly these keys:

- `href` — the raw `href` attribute value, unmodified.
- `resolved` — the `href` resolved against `base_url` into an absolute URL; an already-absolute href is unchanged.
- `kind` — one of:
  - `"anchor"` if the raw href is empty or begins with `"#"`,
  - `"mailto"` if the raw href begins with `"mailto:"`,
  - `"external"` if the resolved URL's host differs from the base URL's host,
  - `"internal"` otherwise (resolved host equals base host).
- `text` — the link's stripped visible text (`""` if none).

Anchors without an `href` are excluded entirely.

### `internal_links(html, base_url)`
Return a `list[str]` of the `resolved` URLs of all links classified as `"internal"`, in document order, with duplicates removed but original order preserved (first occurrence kept).

### `external_hosts(html, base_url)`
Return a sorted `list[str]` of the distinct hosts of all links classified as `"external"`.

### `broken_anchor_targets(html)`
Return a sorted `list[str]` of fragment names (the part after `#`) referenced by in-page anchor links (`kind == "anchor"` with a non-empty fragment) for which no element in the document has a matching `id`. A page where every in-page anchor points at an existing `id` returns an empty list.

### Cross-cutting requirements
- **Order and dedup rules** are explicit per function and must be honored exactly (document order vs. sorted; with vs. without duplicates).
- **Classification precedence**: an empty-or-`#` href is `"anchor"` and a `mailto:` href is `"mailto"` regardless of host comparison.
- **Graceful absence / malformed input**: missing text/attributes yield documented defaults; malformed or partially recoverable HTML must not raise.

### Expected Functionality
- A relative href `"item/9"` with base `"https://shop.example.com/catalog/"` -> `resolved == "https://shop.example.com/catalog/item/9"`, `kind == "internal"`.
- An href `"https://other.example.com/x"` -> `kind == "external"`, and `"other.example.com"` appears in `external_hosts`.
- Hrefs `"#section-2"` and `"mailto:hi@x.com"` -> kinds `"anchor"` and `"mailto"`.
- `internal_links` collapses two identical internal targets to one entry while keeping first-seen order.
- An anchor `"#missing"` with no element having `id="missing"` -> `"missing"` appears in `broken_anchor_targets`; `"#present"` with a matching id does not.
- An `<a>` with no `href` is omitted from all outputs.

## Acceptance Criteria
- A new module `bs4/links.py` exists and exposes `classify_links`, `internal_links`, `external_hosts`, and `broken_anchor_targets` with the behavior above.
- A new test file `bs4/tests/test_links.py` exercises every function, including each `kind` branch and its precedence, relative/absolute resolution, internal dedup with order preservation, sorted external hosts, broken-vs-present anchor fragments, and omission of href-less anchors.
- All parsing is on in-memory HTML strings; tests perform no network or file access and require no third-party parser package.
- The following command passes from the repository root with all tests collected and green:

  ```
  python -m pytest bs4/tests/test_links.py -v
  ```
