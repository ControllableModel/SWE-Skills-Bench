# Task: Build a Page Metadata Extraction Module

## Background
The BeautifulSoup4 repository keeps its tree model under `bs4/` with tests under `bs4/tests/`. This task adds a self-contained utility that reads the `<head>` of an HTML page and extracts its metadata — title, meta tags, Open Graph properties, and the canonical link — the kind of data an SEO or link-preview tool collects.

## Files to Create/Modify
- `bs4/meta.py` (new) — the metadata-extraction module described below.
- `bs4/tests/test_meta.py` (new) — the deterministic test suite for the module.

The module must build its tree using `bs4.BeautifulSoup`, operate entirely in-process on an HTML string (and, where noted, a base-URL string), perform no network or file access, and work using only Python's standard-library HTML parsing (no third-party parser package required).

## Requirements

The module exposes the public functions below. All functions must work for arbitrary conforming inputs, not only the examples shown.

### `page_title(html)`
Return the stripped text of the document's first `<title>` element, with internal whitespace collapsed to single spaces, or `""` if there is no title.

### `meta_tags(html)`
Return a `dict[str, str]` built from `<meta>` elements that carry a `name` attribute: mapping the `name` (as written) to the element's `content` attribute (`""` if `content` is absent). When two meta tags share the same `name`, the first one in document order wins. Meta tags without a `name` are ignored here.

### `open_graph(html)`
Return a `dict[str, str]` built from `<meta>` elements whose `property` attribute starts with `"og:"`: mapping the property name with the leading `"og:"` removed (e.g. `property="og:image"` -> key `"image"`) to the element's `content` (`""` if absent). The first occurrence of a given property wins.

### `canonical_url(html, base_url)`
Return the canonical URL as a `str`: take the first `<link>` element whose `rel` attribute contains the token `"canonical"` (an element with `rel="canonical"` or `rel="alternate canonical"` matches), and resolve its `href` against `base_url` into an absolute URL. If there is no canonical link, or it has no `href`, return `None`.

### `describe(html, base_url)`
Return a `dict` summarizing the page with exactly these keys:

- `title` — the page title preferring the Open Graph `title` if present, otherwise `page_title(html)`.
- `description` — the meta `description` (from `meta_tags`) if present, otherwise the Open Graph `description` if present, otherwise `""`.
- `canonical` — the result of `canonical_url(html, base_url)`.
- `image` — the Open Graph `image` resolved against `base_url`, or `None` if there is no `og:image`.

### Cross-cutting requirements
- **Attribute-driven selection**: meta entries are distinguished by `name` vs `property` and must not be conflated; the `og:` prefix is stripped only for `open_graph`.
- **First-occurrence-wins** is applied consistently for duplicate names/properties.
- **Graceful absence / malformed input**: missing elements/attributes yield the documented defaults; malformed or partially recoverable HTML must not raise.

### Expected Functionality
- A head with `<title>  My  Page </title>` -> `page_title == "My Page"`.
- Two `<meta name="keywords" ...>` tags -> `meta_tags["keywords"]` is the first one's content.
- `<meta property="og:image" content="/img/a.png">` with base `"https://x.example.com/p/"` -> `open_graph["image"] == "/img/a.png"` and `describe(...)["image"] == "https://x.example.com/p/img/a.png"`.
- `<link rel="alternate canonical" href="../home">` -> `canonical_url` resolves the relative href against the base URL.
- `describe` prefers the `og:title` over the `<title>` when both exist, and prefers the meta `description` over `og:description`.
- A page with no relevant tags -> `page_title == ""`, `meta_tags == {}`, `open_graph == {}`, `canonical_url is None`, and `describe` returns the documented empty defaults.

## Acceptance Criteria
- A new module `bs4/meta.py` exists and exposes `page_title`, `meta_tags`, `open_graph`, `canonical_url`, and `describe` with the behavior above.
- A new test file `bs4/tests/test_meta.py` exercises every function, including title normalization, name-vs-property separation, og prefix stripping, first-occurrence-wins, multi-token `rel` matching, URL resolution for canonical and image, the `describe` preference rules, and the empty-page case.
- All parsing is on in-memory HTML strings; tests perform no network or file access and require no third-party parser package.
- The following command passes from the repository root with all tests collected and green:

  ```
  python -m pytest bs4/tests/test_meta.py -v
  ```
