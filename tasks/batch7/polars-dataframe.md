# Task: Build a Tag and Text Normalization Module

## Background

This repository (`pola-rs/polars`) ships runnable examples under `examples/`. We need a self-contained text-processing module in that area that cleans free-text product titles and explodes delimited tag strings into queryable rows, the way a content-ingestion pipeline would. The module operates purely in-memory and depends only on the `polars` package the repository builds.

## Files to Create/Modify

- `examples/text_normalize/__init__.py` - package marker (new)
- `examples/text_normalize/normalize.py` - the text module implementing the public functions below (new)
- `examples/text_normalize/test_normalize.py` - pytest suite exercising the module (new)

## Requirements

### Module Inputs

Functions accept a single `polars.DataFrame` named `items` and return a `polars.DataFrame`. The `items` columns are:

- `item_id` (Int64, unique)
- `title` (String) — raw product title, may have leading/trailing whitespace and mixed case; may be `null`
- `tags` (String) — comma-separated tag list such as `"red, Sale ,new"`; may be `null` or empty string

### `clean_titles(items: pl.DataFrame) -> pl.DataFrame`

Return every input row plus two columns: `title_clean` (String) and `title_len` (Int64). `title_clean` is the `title` with leading/trailing whitespace removed and converted to lowercase; a `null` title yields a `null` `title_clean`. `title_len` is the character length of `title_clean` (a `null` `title_clean` yields a `null` length). All original columns are preserved; output sorted by `item_id` ascending.

### `explode_tags(items: pl.DataFrame) -> pl.DataFrame`

Split each item's `tags` on commas and return one row per `(item_id, tag)` with columns in this exact order: `item_id` (Int64), `tag` (String). Each emitted `tag` must be stripped of surrounding whitespace and lowercased. Empty tags (produced by consecutive commas, a leading/trailing comma, or an empty/`null` `tags` value) must **not** be emitted. An item with no usable tags contributes zero rows. Output sorted by `item_id` ascending, then `tag` ascending.

### `tag_frequencies(items: pl.DataFrame) -> pl.DataFrame`

Return one row per distinct normalized `tag` with columns in this exact order: `tag` (String), `item_count` (Int64/UInt32). `item_count` is the number of **distinct** `item_id`s carrying that tag (an item listing the same tag twice counts once for that tag). Output sorted by `item_count` descending, then `tag` ascending.

### Expected Functionality

- A `title` of `"  Red Shoe  "` yields `title_clean = "red shoe"` and `title_len = 8`.
- A `null` `title` yields `null` for both `title_clean` and `title_len`.
- A `tags` value `"red, Sale ,new"` for item `1` produces tags `new`, `red`, `sale` (sorted), each lowercased and trimmed.
- A `tags` value `"a,,b,"` produces only `a` and `b`; the empty pieces are dropped.
- An item whose `tags` is `null` or `""` contributes no rows to `explode_tags`.
- An item listing `"red,red"` counts once toward `red` in `tag_frequencies`.
- Empty `items` input — every function returns an empty DataFrame with the correct columns and dtypes rather than raising.

## Acceptance Criteria

- `clean_titles`, `explode_tags`, and `tag_frequencies` exist in `examples/text_normalize/normalize.py` with the signatures above and return `polars.DataFrame` objects.
- `clean_titles` trims and lowercases titles, propagates `null` through both derived columns, and preserves all original columns.
- `explode_tags` splits on commas, trims and lowercases each tag, drops empty tags, and emits zero rows for items with no usable tags.
- `tag_frequencies` counts distinct items per tag (deduplicating repeated tags within one item) and sorts as specified.
- All functions return correctly-shaped empty results on empty input.
- The following command passes from the repository root:

  ```bash
  python -m pytest examples/text_normalize/test_normalize.py -q
  ```
