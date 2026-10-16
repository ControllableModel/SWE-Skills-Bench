# Task: Build a Query Filter Validation Module

## Background

This repository (`fabian-hiller/valibot`) is the Valibot schema library, with its full public API exported from `library/src/index.ts`. We need a self-contained module that validates a parsed list-endpoint query object containing pagination controls, a sort spec, and an open-ended map of string-equality filters.

## Files to Create/Modify

- `library/src/queryFilter/queryFilter.ts` (new) — the validation function and the schema.
- `library/src/queryFilter/index.ts` (new) — re-export the public surface of the module.
- `library/src/queryFilter/queryFilter.test.ts` (new) — the deterministic test suite described below.

Build the module using the library's own public API by importing from the package source root, e.g. `import * as v from '../index.ts';`. Do not add new third-party dependencies.

## Requirements

Implement and export a function `parseQuery(input: unknown)` plus the underlying schema, and the inferred output type. The function returns the normalized query object directly and throws when the input is invalid.

### Input contract

```json
{
  "page": 2,
  "perPage": 50,
  "sortBy": "createdAt",
  "order": "desc",
  "filters": { "status": "active", "country": "us" }
}
```

### Field rules

#### `page` (optional)
- When present, an integer `>= 1`. Output defaults to `1` when absent.

#### `perPage` (optional)
- When present, an integer in the inclusive range 1 to 100. Output defaults to `20` when absent.

#### `sortBy` (optional)
- When present, one of `"createdAt"`, `"updatedAt"`, or `"name"`. Other values rejected. Output defaults to `"createdAt"` when absent.

#### `order` (optional)
- When present, one of `"asc"` or `"desc"`. Output defaults to `"asc"` when absent.

#### `filters` (optional)
- When present, an object whose keys are arbitrary strings and whose values are each a non-empty string. Any non-string or empty-string value rejects the whole query.
- Output defaults to an empty object `{}` when absent.

### Output shape

The normalized object contains exactly `page`, `perPage`, `sortBy`, `order`, and `filters`, with the defaults above applied. Unknown top-level keys must be stripped.

### Expected Functionality

- The example payload above -> returned unchanged (with `filters` preserving both entries).
- `{}` -> `{ page: 1, perPage: 20, sortBy: "createdAt", order: "asc", filters: {} }`.
- `{ page: 0 }` -> throws (page must be >= 1).
- `{ perPage: 250 }` -> throws (perPage out of range).
- `{ sortBy: "color" }` -> throws (not in allowed sort fields).
- `{ order: "sideways" }` -> throws.
- `{ filters: { status: "" } }` -> throws (empty filter value).
- `{ filters: { status: 5 } }` -> throws (non-string filter value).
- `{ filters: { a: "1", b: "2", c: "3" } }` -> success, all three preserved.
- `{ page: 1, junk: true }` -> success; `junk` not present in output.
- `"hello"`, `null` -> throws.

## Acceptance Criteria

- A module exists at `library/src/queryFilter/queryFilter.ts` exporting `parseQuery` and its schema.
- `filters` validates as an open map of string keys to non-empty string values; any non-string or empty value rejects the input.
- All five fields are defaulted when absent exactly as specified, and unknown top-level keys are stripped.
- `parseQuery` throws on every invalid input listed above and returns the normalized object on valid input.
- The added test suite contains at least 10 distinct test cases covering: the full valid payload, the all-defaults case, range/picklist rejection for `page`/`perPage`/`sortBy`/`order`, the open filter-map success path with multiple keys, the empty-value and non-string-value rejections in `filters`, unknown-key stripping, and non-object inputs.
- The following command, run from the `library/` directory, passes with all tests green:

```bash
npx vitest run src/queryFilter/queryFilter.test.ts
```
