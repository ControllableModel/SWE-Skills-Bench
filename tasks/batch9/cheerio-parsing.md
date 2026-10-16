# Task: Build a data-attribute collector

## Background

The cheerio repository (`cheeriojs/cheerio`) is a Node.js HTML/XML parsing
library. This task adds a helper that reads `data-*` attributes off matched
elements and returns them as camelCased record objects.

## Files to Create/Modify

- `src/api/data-collect.ts` (new) — export a `collectData(html, selector)` function.
- `src/api/data-collect.spec.ts` (new) — deterministic test cases.

## Requirements

### Function contract

Implement and export `collectData(html: string, selector: string)` that loads
`html`, selects every element matching `selector`, and returns an array of
objects (one per matched element, in document order) holding that element's
`data-*` attributes.

### Behavior and constraints

- For each matched element, build an object containing one entry per `data-*`
  attribute on that element.
- The object key MUST be the attribute name with the `data-` prefix removed and
  the remainder converted to camelCase across hyphen boundaries (e.g.
  `data-product-id` -> `productId`, `data-id` -> `id`).
- The value MUST be the raw attribute string value as written in the HTML (no
  numeric coercion; `data-id="123"` stores the string `'123'`).
- An element with no `data-*` attributes contributes an empty object `{}` (still
  one entry per matched element).
- Non-`data-` attributes (e.g. `class`, `id`, `href`) MUST NOT appear in the
  result objects.
- If the selector matches nothing, the function MUST return `[]`.

### Expected Functionality

- `<li data-id="1" data-product-name="Apple" class="x"></li>` ->
  `[{ id: '1', productName: 'Apple' }]`.
- An element with only a `class` and no `data-*` -> `[{}]`.
- `collectData('<p></p>', '.none')` -> `[]`.

## Acceptance Criteria

- `src/api/data-collect.ts` exports `collectData` with the contract above.
- `src/api/data-collect.spec.ts` covers: hyphenated key camelCasing, string
  values left uncoerced, exclusion of non-data attributes, an element with no
  data attributes yielding `{}`, multiple matched elements, and the empty-result
  case.
- The following command passes from the repo root:

  ```
  npx vitest run src/api/data-collect.spec.ts
  ```
