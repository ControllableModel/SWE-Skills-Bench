# Task: Extend the extract API with value transforms and result limits

## Background

Cheerio's `extract` API (`src/api/extract.ts`) lets callers describe an
`ExtractMap` of selectors and pull structured data out of a parsed document.
This task adds two capabilities to the descriptor so callers can normalize the
data they pull and cap how many matches an array descriptor collects.

## Files to Create/Modify

- `src/api/extract.ts` (modify) — extend the descriptor type and the extraction logic.
- `src/api/extract.spec.ts` (modify) — add deterministic test cases covering the new behavior.

## Requirements

### Transform option

Extend the descriptor object accepted by `extract` so that, in addition to the
existing `selector` and `value` fields, it accepts an optional `transform`
field. `transform` is a function that receives the value that the descriptor
would otherwise have produced (the result of resolving `value`, defaulting to
the element's text content) and returns the final value to store under the key.

- When `transform` is present, the value stored for that key MUST be the return
  value of calling `transform` with the originally-extracted value.
- The original value passed to `transform` MUST be exactly what `extract` would
  have stored if `transform` were absent (i.e. the resolved `value`, whether that
  is a string from a property name, the output of a custom `value` function, or a
  nested extracted object).
- `transform` MUST apply per matched element. For an array descriptor, each
  element's extracted value is passed through `transform` individually, and the
  resulting array contains the transformed values.
- For a single (non-array) descriptor whose selector matches no elements, the
  result MUST remain `undefined` and `transform` MUST NOT be invoked.
- `transform` MUST be allowed to change the value's type (e.g. turn a string into
  a number), and the stored value MUST be whatever `transform` returns, including
  `undefined`.

### Limit option

Extend the array form of a descriptor so it supports an optional `limit` that
caps the number of matched elements collected into the result array.

- For an array descriptor with a `limit` of N, the result array MUST contain at
  most N entries, taken in document order (the first N matches).
- A `limit` greater than or equal to the number of matches MUST behave as if no
  limit were given (all matches collected).
- A `limit` of `0` MUST produce an empty array.
- `limit` MUST have no effect on single (non-array) descriptors.
- When both `limit` and `transform` are supplied on an array descriptor, the
  limit MUST be applied to the set of matched elements and `transform` MUST be
  applied to each collected value.

### Constraints

- Existing `extract` behavior MUST be preserved exactly when neither `transform`
  nor `limit` is supplied; all current tests in `src/api/extract.spec.ts` MUST
  continue to pass unchanged.
- Nested descriptor maps (a `value` that is itself an `ExtractMap`) MUST continue
  to work, and `transform` MUST be applicable to the nested extracted object.
- The implementation MUST NOT collect more elements than necessary when a `limit`
  is given for an array descriptor (do not materialize every match and then slice
  away the excess for the unbounded-vs-bounded distinction to be observable only
  via the public result — observable behavior is the capped array).

### Expected Functionality

- `$.extract({ n: { selector: '.red', value: 'textContent', transform: (v) => v && v.toUpperCase() } })`
  on a document whose first `.red` element has text `Four` -> `{ n: 'FOUR' }`.
- `$.extract({ n: { selector: '.missing', transform: () => 'X' } })` -> `{ n: undefined }`
  (transform not called).
- `$.extract({ n: [{ selector: '.red', limit: 2 }] })` on a document with three
  `.red` matches (`Four`, `Five`, `Nine`) -> `{ n: ['Four', 'Five'] }`.
- `$.extract({ n: [{ selector: '.red', limit: 0 }] })` -> `{ n: [] }`.
- `$.extract({ n: [{ selector: '.red', limit: 2, transform: (v) => v.length }] })`
  -> `{ n: [4, 4] }`.

## Acceptance Criteria

- A modified descriptor type and extraction logic in `src/api/extract.ts` support
  an optional per-descriptor `transform` function and an optional `limit` on array
  descriptors, with the behavior described above.
- New deterministic test cases are added to `src/api/extract.spec.ts` that, at a
  minimum, cover: transform on a single descriptor, transform skipped on a
  non-matching single descriptor, transform changing the value type, transform on
  each element of an array descriptor, `limit` capping an array result to the
  first N document-order matches, `limit` of `0` yielding `[]`, `limit` greater
  than the match count behaving as unlimited, and `limit` combined with
  `transform`.
- All pre-existing tests in `src/api/extract.spec.ts` continue to pass.
- The following command passes (run from the repo root):

  ```
  npx vitest run src/api/extract.spec.ts
  ```
