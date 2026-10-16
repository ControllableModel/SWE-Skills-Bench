# Task: Build an HTML Catalog Extraction Module

## Background
The BeautifulSoup4 repository ships its parser/tree code under `bs4/` with a matching test suite under `bs4/tests/`. This task adds a small, self-contained utility module that turns raw catalog HTML (as produced by an online store's product-listing pages) into clean, structured Python data, together with a deterministic test suite.

## Files to Create/Modify
- `bs4/extract.py` (new) — the extraction module described below.
- `bs4/tests/test_extract.py` (new) — the deterministic test suite for the module.

The module must build its document tree using `bs4.BeautifulSoup` and operate entirely in-process: it accepts HTML as a Python string (and a base URL string) and returns plain Python data structures. It must not perform any network access, file I/O, or use of external services, and it must not require any third-party parser package to be installed.

## Requirements

The module exposes the following public functions. Each accepts an HTML string `html` (and, where noted, a `base_url` string) and returns plain Python objects (`dict` / `list` / `str` / `float` / `None`). All functions must work for arbitrary inputs that satisfy the stated contracts, not only the examples shown.

A "product card" is any element matching the CSS class `product-card`. Within a card:
- the product name is the text of the element with class `name`,
- the price is the text of the element with class `price`,
- the primary link is the `href` of the first `<a>` element,
- the image source is the `src` of the first `<img>` element,
- a card is considered out of stock if (and only if) it contains an element with class `out-of-stock`.

### `extract_cards(html, base_url)`
Return a `list` of dictionaries, one per product card, in document order. Each dictionary has exactly these keys:

- `name` — the card's name text, with leading/trailing whitespace removed and any internal runs of whitespace (including newlines produced by nested inline markup) collapsed to single spaces. If the card has no name element, the value must be the empty string `""`.
- `price` — the numeric price as a `float`, parsed from the price text. The price text may include a leading currency symbol (`$`), thousands separators (`,`), and surrounding whitespace (e.g. `"$1,299.00"` -> `1299.0`). If there is no price element, or the price text cannot be parsed as a number, the value must be `None`.
- `url` — the card's primary link resolved against `base_url` into an absolute URL. A link that is already absolute must be returned unchanged. If the card has no link, the value must be `None`.
- `image` — the card's image source resolved against `base_url` into an absolute URL, or `None` if the card has no image.
- `in_stock` — a `bool` that is `False` when the card contains an out-of-stock marker and `True` otherwise.

Cards must be located by their class regardless of what other classes are also present on the element (e.g. an element whose class attribute is `"product-card featured"` is still a card). A document with no product cards must yield an empty list.

### `extract_table(html)`
Parse the first `<table>` in the document into a `list` of dictionaries — one dictionary per body data row.

- Column keys come from the header cells (`<th>`) in document order, each as whitespace-stripped text.
- For each data row, the dictionaries pair each header key with the stripped text of the corresponding data cell (`<td>`) by position.
- Header rows (rows containing only header cells) must not appear as data rows.
- If a data row has fewer data cells than there are headers, the surplus header keys must still be present with value `""`. Extra data cells beyond the number of headers must be ignored.
- If the document contains no table, return an empty list.

### `extract_links(html, base_url)`
Return a `list` of absolute URLs for every `<a>` element in the document that has an `href`, in document order.

- Each `href` is resolved against `base_url`; already-absolute URLs are returned unchanged.
- Anchors without an `href` attribute are skipped entirely (no `None` entries).
- The result preserves duplicates and document order.

### Cross-cutting requirements
- **Missing data is handled gracefully**: absent elements/attributes yield the documented defaults rather than raising. None of these functions may raise an exception on well-formed-but-incomplete input (e.g. a card missing its price/link/image).
- **Malformed HTML is tolerated**: inputs with unclosed tags or improperly nested markup must still be parsed and produce results for whatever structure is recoverable, without raising. The module must not depend on a parser that requires an optional third-party package — it must work using only Python's standard-library HTML parsing.
- **Text normalization**: extracted text must be free of surrounding whitespace; for `name`, internal whitespace runs spanning nested tags collapse to single spaces.

### Expected Functionality
- A card whose name is split across nested inline tags (`<span>Wireless</span> <span>Mouse</span>`) -> `name == "Wireless Mouse"`.
- A card with `price` text `"$1,299.00"` -> `price == 1299.0`; a card with price text `"Call us"` -> `price is None`; a card with no price element -> `price is None`.
- A card with a relative link `"item/42"` and `base_url == "https://shop.example.com/catalog/"` -> `url == "https://shop.example.com/catalog/item/42"`; a card with `href == "https://other.example.com/x"` -> that absolute URL unchanged.
- A card containing an `out-of-stock` marker -> `in_stock is False`; otherwise `True`.
- `extract_table` over a table whose body row has one fewer `<td>` than there are `<th>` -> the missing trailing column key is present with value `""`.
- `extract_links` over a document mixing absolute hrefs, relative hrefs, and an `<a>` with no `href` -> a list of resolved absolute URLs in order, with the href-less anchor omitted.
- A document with no product cards / no table -> the corresponding function returns `[]`.

## Acceptance Criteria
- A new module `bs4/extract.py` exists and exposes `extract_cards`, `extract_table`, and `extract_links` with the signatures and behavior above.
- A new test file `bs4/tests/test_extract.py` exercises every function, including the missing-data, malformed-HTML, multi-class card, price-parsing (success and failure), relative/absolute URL resolution, ragged-table, and empty-document cases described under Expected Functionality.
- All extraction is performed on in-memory HTML strings; the tests perform no network or file access and require no third-party parser package.
- The following command passes from the repository root with all tests collected and green:

  ```
  python -m pytest bs4/tests/test_extract.py -v
  ```
