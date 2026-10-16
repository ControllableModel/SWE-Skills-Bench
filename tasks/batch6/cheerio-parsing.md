# Task: Build a pagination-link extractor

## Background

The cheerio repository (`cheeriojs/cheerio`) is a Node.js HTML/XML parsing
library. This task adds a helper that pulls usable "next-page" navigation
targets out of a parsed pagination widget.

## Files to Create/Modify

- `src/api/pagination.ts` (new) — export an `extractPaginationLinks(html)` function.
- `src/api/pagination.spec.ts` (new) — deterministic test cases.

## Requirements

### Function contract

Implement and export `extractPaginationLinks(html: string)` that loads `html`
with cheerio and returns the list of href strings from anchors inside a
`.pagination` container, filtered to those usable for navigation.

### Behavior and constraints

- Only anchors that are descendants of an element with class `pagination` are
  considered.
- The returned array contains the raw `href` attribute strings, in document
  order.
- An anchor with no `href` MUST be excluded.
- An anchor whose `href` contains a `#` character anywhere MUST be excluded
  (these are treated as non-navigational placeholders).
- Duplicate href values MUST be removed: each distinct href appears at most once,
  keeping the first occurrence's position.
- Anchors outside any `.pagination` container MUST be ignored even if they have
  valid hrefs.
- If there is no `.pagination` container, the result MUST be `[]`.

### Expected Functionality

- A `.pagination` block with anchors `?page=1`, `?page=2`, `#`, `?page=2`
  (duplicate), and a missing-href anchor -> `['?page=1', '?page=2']`.
- An anchor with `href="javascript:void(0)#"` -> excluded (contains `#`).
- A document with anchors but no `.pagination` container -> `[]`.

## Acceptance Criteria

- `src/api/pagination.ts` exports `extractPaginationLinks` with the contract
  above.
- `src/api/pagination.spec.ts` covers: filtering out `#` hrefs, excluding
  missing hrefs, de-duplication while preserving order, ignoring anchors outside
  `.pagination`, and the no-container empty result.
- The following command passes from the repo root:

  ```
  npx vitest run src/api/pagination.spec.ts
  ```
