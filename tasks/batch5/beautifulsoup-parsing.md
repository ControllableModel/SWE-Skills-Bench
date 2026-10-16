# Task: Build an RSS/Atom Feed Parsing Module

## Background
The BeautifulSoup4 repository ships its parser/tree code under `bs4/` with tests under `bs4/tests/`. This task adds a self-contained utility that reads a syndication feed document (RSS or Atom) and returns its channel metadata and items as structured Python data.

## Files to Create/Modify
- `bs4/feed.py` (new) — the feed-parsing module described below.
- `bs4/tests/test_feed.py` (new) — the deterministic test suite for the module.

The module must build its tree using `bs4.BeautifulSoup`, operate entirely in-process on a markup string, perform no network or file access, and work using only Python's standard-library HTML parsing (no third-party parser package required). Feeds are parsed as markup; element names are matched case-insensitively.

## Requirements

The module exposes the public functions below. All functions must work for arbitrary conforming inputs, not only the examples shown.

A document is treated as RSS when it contains a `<channel>` element and as Atom when it contains a `<feed>` element. Within RSS, entries are `<item>` elements; within Atom, entries are `<entry>` elements.

### `feed_type(html)`
Return `"rss"` when the document contains a `<channel>` element, `"atom"` when it contains a `<feed>` element but no `<channel>`, and `None` otherwise.

### `feed_title(html)`
Return the stripped text of the feed's top-level `<title>` element — the `<title>` that is a direct descendant of the `<channel>` (RSS) or `<feed>` (Atom) container, not a title belonging to an item/entry. Return `""` if there is no such title or no recognizable feed container.

### `feed_entries(html)`
Return a `list[dict]`, one per entry, in document order. Each dict has exactly these keys:

- `title` — the stripped text of the entry's `<title>`, or `""` if absent.
- `link` — the entry's link URL. For RSS this is the stripped text of the entry's `<link>` element. For Atom this is the `href` attribute of the entry's first `<link>` element. If no link is present, `None`.
- `summary` — the stripped text of the entry's `<description>` (RSS) or `<summary>` (Atom) element, or `""` if absent.

### `entry_count(html)`
Return an `int`: the number of entries in the feed (items for RSS, entries for Atom). A document with no recognizable feed returns `0`.

### Cross-cutting requirements
- **Container scoping**: the feed-level title must never be confused with an entry-level title even when both exist; entry fields are read from within each entry element only.
- **Format awareness**: link extraction differs between RSS (element text) and Atom (`href` attribute) and must be selected based on the detected feed type.
- **Graceful absence / malformed input**: missing fields yield the documented defaults; malformed or partially recoverable markup must not raise.

### Expected Functionality
- An RSS document with a channel `<title>` and two `<item>` blocks -> `feed_type == "rss"`, `feed_title` is the channel title, `entry_count == 2`, and each entry's `link` is the `<link>` element's text.
- An Atom document with a feed `<title>` and one `<entry>` whose `<link href="...">` is empty -> `feed_type == "atom"`, the entry's `link` equals the `href`, and `summary` comes from `<summary>`.
- An item missing its `<description>` -> that entry's `summary == ""`; an entry missing any link -> `link is None`.
- A non-feed HTML document -> `feed_type is None`, `feed_title == ""`, `feed_entries == []`, `entry_count == 0`.

## Acceptance Criteria
- A new module `bs4/feed.py` exists and exposes `feed_type`, `feed_title`, `feed_entries`, and `entry_count` with the behavior above.
- A new test file `bs4/tests/test_feed.py` exercises every function for both RSS and Atom inputs, including channel-vs-entry title scoping, RSS-text-vs-Atom-href link extraction, missing-field defaults, and the non-feed case.
- All parsing is on in-memory markup strings; tests perform no network or file access and require no third-party parser package.
- The following command passes from the repository root with all tests collected and green:

  ```
  python -m pytest bs4/tests/test_feed.py -v
  ```
