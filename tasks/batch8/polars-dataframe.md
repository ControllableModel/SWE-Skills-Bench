# Task: Build a Multi-Source Feed Merger

## Background

This repository (`pola-rs/polars`) ships runnable examples under `examples/`. We need a self-contained merging module in that area that unions partner product feeds whose schemas overlap but differ, the way an aggregator stitches together several suppliers into one catalog. The module operates purely in-memory and depends only on the `polars` package the repository builds.

## Files to Create/Modify

- `examples/feed_merge/__init__.py` - package marker (new)
- `examples/feed_merge/merge.py` - the merging module implementing the public functions below (new)
- `examples/feed_merge/test_merge.py` - pytest suite exercising the module (new)

## Requirements

### Module Inputs

Functions accept a Python `list[pl.DataFrame]` of partner feeds and return a `polars.DataFrame`. Each feed has at least a `sku` (String) and `price` (Float64) column, but feeds may carry **different extra columns** (e.g. one feed has `color`, another has `weight`). The feeds are passed in a fixed list order that defines source precedence (earlier = higher priority).

### `union_feeds(feeds: list[pl.DataFrame]) -> pl.DataFrame`

Stack all feeds into one frame that contains the **union of all columns** across every feed. Where a feed lacks a column another feed has, that feed's rows get `null` in the missing column. The result column order is: first the columns common to every feed in their first-seen order, then the remaining columns in first-seen order across the feed list. Row order is the feeds concatenated in list order, preserving each feed's internal row order. An empty feed list returns an empty DataFrame with **zero** columns.

### `tag_source(feeds: list[pl.DataFrame]) -> pl.DataFrame`

Like `union_feeds`, but add a leading `source_idx` (Int64) column whose value is the zero-based index of the feed each row came from. The remaining columns follow the same union-and-order rules as `union_feeds`. Row order follows feed list order.

### `dedupe_by_priority(feeds: list[pl.DataFrame]) -> pl.DataFrame`

Produce the union of all feeds (same column union as `union_feeds`) but keep **at most one row per `sku`**: when the same `sku` appears in more than one feed (or more than once within a feed), keep the occurrence from the earliest feed in the list, and within a single feed keep its first occurrence. The kept row retains its own column values (including nulls for columns its feed lacked). Output sorted by `sku` ascending. No `source_idx` column in this output.

### Expected Functionality

- Feed A has columns `sku, price, color`; Feed B has `sku, price, weight`. `union_feeds([A, B])` has columns `sku, price, color, weight`, with B's rows null under `color` and A's rows null under `weight`.
- `tag_source([A, B])` prepends `source_idx` with `0` for A's rows and `1` for B's rows.
- A `sku` present in both A and B survives `dedupe_by_priority` exactly once, carrying A's values (A is earlier).
- A `sku` appearing twice inside one feed survives once, keeping that feed's first occurrence.
- An empty feed list yields a zero-column empty DataFrame from `union_feeds`.

## Acceptance Criteria

- `union_feeds`, `tag_source`, and `dedupe_by_priority` exist in `examples/feed_merge/merge.py` with the signatures above and return `polars.DataFrame` objects.
- `union_feeds` produces the full column union with `null` fills for columns absent from a given feed, using the specified column and row ordering.
- `tag_source` adds a correct zero-based `source_idx` leading column over the same union.
- `dedupe_by_priority` keeps one row per `sku`, resolving cross-feed and intra-feed duplicates by earliest feed then first occurrence, sorted by `sku`.
- An empty feed list returns a zero-column empty DataFrame.
- The following command passes from the repository root:

  ```bash
  python -m pytest examples/feed_merge/test_merge.py -q
  ```
