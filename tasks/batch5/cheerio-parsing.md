# Task: Build safe element accessors

## Background

The cheerio repository (`cheeriojs/cheerio`) is a Node.js HTML/XML parsing
library. This task adds small defensive accessor helpers that read text and
attributes from a parsed document while tolerating missing elements.

## Files to Create/Modify

- `src/api/safe-access.ts` (new) — export `safeText` and `safeAttr` helpers.
- `src/api/safe-access.spec.ts` (new) — deterministic test cases.

## Requirements

### Function contracts

Both functions take an already-loaded cheerio API object as their first argument
so callers can reuse a single parse.

- `safeText($, selector, defaultValue = '')`: returns the trimmed text of the
  first element matching `selector`. If no element matches, returns
  `defaultValue`.
- `safeAttr($, selector, attr, defaultValue = null)`: returns the value of the
  named attribute on the first element matching `selector`. If no element
  matches, returns `defaultValue`.

### Behavior and constraints

- `safeText` MUST trim leading and trailing whitespace (including newlines) from
  the returned text.
- When the selector matches multiple elements, both helpers operate on the first
  match in document order only.
- For `safeAttr`, when the element matches but does not have the requested
  attribute, the function MUST return `undefined` (this is distinct from the
  no-match case, which returns `defaultValue`).
- The default value of `safeText` is the empty string and of `safeAttr` is
  `null`; callers may override either.
- Neither function may throw on a non-matching selector.

### Expected Functionality

- `safeText($, '.title')` on a document with `<h1 class="title">  Hi \n</h1>`
  -> `'Hi'`.
- `safeText($, '.missing', 'N/A')` -> `'N/A'`.
- `safeAttr($, 'a', 'href')` where the first `<a>` has `href="/x"` -> `'/x'`.
- `safeAttr($, 'a', 'rel')` where the first `<a>` has no `rel` -> `undefined`.
- `safeAttr($, '.missing', 'href', null)` -> `null`.

## Acceptance Criteria

- `src/api/safe-access.ts` exports `safeText` and `safeAttr` with the contract
  above.
- `src/api/safe-access.spec.ts` covers: trimming, the default-value path for
  both helpers, first-match-only selection, the match-but-missing-attribute case
  returning `undefined`, and a custom override default.
- The following command passes from the repo root:

  ```
  npx vitest run src/api/safe-access.spec.ts
  ```
