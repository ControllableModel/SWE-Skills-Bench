# Task: Build an absolute-link collector

## Background

The cheerio repository (`cheeriojs/cheerio`) is a Node.js HTML/XML parsing
library. This task adds a helper that collects all hyperlink targets from a
parsed document and resolves relative URLs against a base URL using cheerio's
attribute access.

## Files to Create/Modify

- `src/api/links.ts` (new) — export a `collectLinks(html, baseUrl)` function.
- `src/api/links.spec.ts` (new) — deterministic test cases for the new module.

## Requirements

### Function contract

Implement and export `collectLinks(html: string, baseUrl: string)` that loads
`html` with cheerio, finds every `<a>` element, and returns an array of
absolute URL strings in document order.

### Behavior and constraints

- Each returned entry is the value of the anchor's `href` attribute resolved to
  an absolute URL against `baseUrl` (use the standard WHATWG URL resolution).
- An anchor with no `href` attribute MUST be skipped (not included in the array).
- An anchor whose `href` is the empty string MUST be skipped.
- An anchor whose `href` is a fragment-only link (starts with `#`) MUST be
  skipped.
- An `href` that is already absolute (e.g. `https://other.test/x`) MUST be
  returned unchanged (resolution against the base yields the same absolute URL).
- A relative `href` (e.g. `about`, `/help`, `../up`) MUST be resolved against
  `baseUrl` to produce a full absolute URL.
- If an `href` cannot be parsed as a URL even against the base, that anchor MUST
  be skipped rather than throwing.
- The result MUST preserve duplicates (if two anchors resolve to the same URL,
  both appear) and document order.

### Expected Functionality

- Base `https://example.com/products/` with anchors `item1`, `/help`,
  `#top`, `https://cdn.test/a` -> `['https://example.com/products/item1', 'https://example.com/help', 'https://cdn.test/a']`.
- An `<a>` with no `href` and an `<a href="">` are both omitted.

## Acceptance Criteria

- `src/api/links.ts` exports `collectLinks` with the contract above.
- `src/api/links.spec.ts` contains deterministic cases covering: relative
  resolution, an already-absolute href, a fragment-only href skipped, a missing
  href skipped, an empty href skipped, and order/duplicate preservation.
- The following command passes from the repo root:

  ```
  npx vitest run src/api/links.spec.ts
  ```
