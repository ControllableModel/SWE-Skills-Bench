# Task: Build a product-card list extractor

## Background

The cheerio repository (`cheeriojs/cheerio`) is a Node.js HTML/XML parsing
library. This task adds a helper that maps a repeated list of card-shaped HTML
fragments into an array of typed product records using cheerio traversal and
attribute access.

## Files to Create/Modify

- `src/api/products.ts` (new) — export an `extractProducts(html)` function.
- `src/api/products.spec.ts` (new) — deterministic test cases for the new module.

## Requirements

### Function contract

Implement and export `extractProducts(html: string)` that loads `html` with
cheerio, selects every element matching `.product-card`, and returns an array of
objects, one per card, in document order.

### Per-card record shape

For each `.product-card` element, produce an object with these keys:

- `name`: the trimmed text of the descendant `.title`. If absent, `''`.
- `price`: a number parsed from the descendant `.price` text by removing every
  character that is not a digit or a dot, then converting to a number. If the
  `.price` element is absent, `price` MUST be `null`.
- `image`: the `src` attribute of the descendant `<img>`, or `null` if there is
  no `<img>` or it has no `src`.
- `inStock`: a boolean that is `false` when the card contains a descendant
  matching `.out-of-stock`, and `true` otherwise.

### Behavior and constraints

- A card with no `.product-card` matches at all MUST yield `[]`.
- Each lookup MUST be scoped to within the individual card (a `.title` belonging
  to a different card MUST NOT leak into another card's record).
- Price parsing MUST handle currency symbols and thousands separators, e.g.
  `"$1,299.50"` -> `1299.5`.
- When `.price` text contains no digits, `price` MUST be `NaN` (the result of
  numeric conversion of an empty string is a number; document this in a test).

### Expected Functionality

- Two cards (`Apple`/`$1.50`/in stock, `Pear`/`$3`/with an `.out-of-stock` badge)
  -> `[{ name: 'Apple', price: 1.5, image: ..., inStock: true }, { name: 'Pear', price: 3, image: ..., inStock: false }]`.
- A card with no `.price` -> `price` is `null`.

## Acceptance Criteria

- `src/api/products.ts` exports `extractProducts` with the contract above.
- `src/api/products.spec.ts` contains deterministic cases covering: multiple
  cards, missing `.price` yielding `null`, currency/separator stripping, the
  `inStock` flag toggling on `.out-of-stock`, scoping per card, and the empty
  input case.
- The following command passes from the repo root:

  ```
  npx vitest run src/api/products.spec.ts
  ```
