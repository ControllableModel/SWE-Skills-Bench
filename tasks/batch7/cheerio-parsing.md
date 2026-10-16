# Task: Build a definition-list to record converter

## Background

The cheerio repository (`cheeriojs/cheerio`) is a Node.js HTML/XML parsing
library. This task adds a helper that flattens an HTML description list
(`<dl>` of `<dt>`/`<dd>` pairs) into a key/value record using cheerio sibling
traversal.

## Files to Create/Modify

- `src/api/deflist.ts` (new) — export a `parseDefinitionList(html, selector)` function.
- `src/api/deflist.spec.ts` (new) — deterministic test cases.

## Requirements

### Function contract

Implement and export `parseDefinitionList(html: string, selector: string)` that
loads `html`, locates the first element matching `selector`, and returns an
object mapping each `<dt>` term to its associated value(s).

### Behavior and constraints

- Each `<dt>` contributes a key equal to its trimmed text.
- The value for a key is built from the `<dd>` element(s) that immediately follow
  that `<dt>` up to (but not including) the next `<dt>`:
  - Exactly one following `<dd>`: the value is that `<dd>`'s trimmed text (a
    string).
  - More than one following `<dd>`: the value is an array of the trimmed texts,
    in document order.
  - Zero following `<dd>` before the next `<dt>` or end of list: the value is the
    empty string `''`.
- If the same term text appears in more than one `<dt>`, the later occurrence
  MUST overwrite the earlier one.
- If the selector matches no element, the function MUST return an empty object
  `{}`.
- Whitespace around both terms and values MUST be trimmed.

### Expected Functionality

- `<dl><dt>Color</dt><dd>Red</dd><dt>Sizes</dt><dd>S</dd><dd>M</dd></dl>` ->
  `{ Color: 'Red', Sizes: ['S', 'M'] }`.
- A `<dt>` followed immediately by another `<dt>` -> that term maps to `''`.
- `parseDefinitionList('<p>x</p>', 'dl')` -> `{}`.

## Acceptance Criteria

- `src/api/deflist.ts` exports `parseDefinitionList` with the contract above.
- `src/api/deflist.spec.ts` covers: single-dd string value, multi-dd array
  value, a term with no dd yielding `''`, duplicate-term overwrite, the
  missing-selector empty-object case, and whitespace trimming.
- The following command passes from the repo root:

  ```
  npx vitest run src/api/deflist.spec.ts
  ```
