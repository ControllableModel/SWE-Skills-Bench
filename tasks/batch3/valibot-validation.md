# Task: Build a CSV Row Coercion Module

## Background

This repository (`fabian-hiller/valibot`) is the Valibot schema library, with its full public API exported from `library/src/index.ts`. We need a self-contained module that takes a single parsed CSV row (an array of raw string cells) and turns it into a typed record, coercing each column to its proper type and tolerating known-recoverable cells via column-specific fallbacks.

## Files to Create/Modify

- `library/src/csvRow/csvRow.ts` (new) — the row-parsing function and the schema it is built on.
- `library/src/csvRow/index.ts` (new) — re-export the public surface of the module.
- `library/src/csvRow/csvRow.test.ts` (new) — the deterministic test suite described below.

Build the module using the library's own public API by importing from the package source root, e.g. `import * as v from '../index.ts';`. Do not add new third-party dependencies.

## Requirements

Implement and export a function `parseRow(cells: unknown)` plus the underlying schema. The input is a positional array of cells `[id, name, price, inStock, category]` — a fixed-shape row where every cell is a raw string. The function must convert the row into a typed object.

### Input contract

A row looks like:

```json
["1042", "Widget", "19.99", "true", "tools"]
```

The input is a fixed-length 5-element array. Rows with a different number of elements are rejected.

### Column rules (by position)

1. `id` — a string that must coerce to a whole number of at least 1. Output key `id` is a `number`. Non-numeric or `< 1` values are rejected.
2. `name` — a string; surrounding whitespace must be trimmed; after trimming it must be non-empty. Output key `name`.
3. `price` — a string that must coerce to a finite number that is `>= 0`. Output key `price` is a `number`. **If the cell cannot be parsed into a valid non-negative number, the output `price` must fall back to `0` rather than failing the whole row.**
4. `inStock` — a string; `"true"`/`"false"` (exact, case-sensitive) coerce to the corresponding `boolean`. Any other value is rejected. Output key `inStock` is a `boolean`.
5. `category` — a string that must be one of `"tools"`, `"food"`, `"books"`, or `"other"`. **Any unrecognized category must fall back to `"other"` rather than failing the row.** Output key `category`.

### Output shape

`parseRow` returns the coerced object `{ id, name, price, inStock, category }` directly and throws when the row is unrecoverably invalid (wrong arity, bad `id`, empty `name`, or invalid `inStock`). The `price` and `category` columns must never cause a throw — they recover via their fallbacks.

### Expected Functionality

- `["1042", "Widget", "19.99", "true", "tools"]` -> `{ id: 1042, name: "Widget", price: 19.99, inStock: true, category: "tools" }`.
- `["7", "  Gadget  ", "abc", "false", "gadgets"]` -> `{ id: 7, name: "Gadget", price: 0, inStock: false, category: "other" }` (price recovered to 0, unknown category recovered to "other", name trimmed).
- `["0", "X", "1", "true", "tools"]` -> throws (`id` must be >= 1).
- `["1", "   ", "1", "true", "tools"]` -> throws (empty name after trim).
- `["1", "X", "1", "maybe", "tools"]` -> throws (invalid `inStock`).
- `["1", "X", "1", "true"]` -> throws (wrong arity).
- `"not an array"` -> throws.

## Acceptance Criteria

- A module exists at `library/src/csvRow/csvRow.ts` exporting `parseRow` and its schema.
- The schema enforces a fixed 5-element positional shape; rows of any other length throw.
- `id` and `price` end up as numbers and `inStock` as a boolean in the output; `name` is trimmed.
- A malformed `price` cell yields `price === 0` and an unknown `category` yields `category === "other"`, neither of which throws, while a bad `id`, empty `name`, invalid `inStock`, or wrong arity does throw.
- The added test suite contains at least 10 distinct test cases covering: a fully valid row, the per-column type coercions, the `price` fallback path, the `category` fallback path, name trimming, and each throwing case (bad id, empty name, invalid inStock, wrong arity, non-array input).
- The following command, run from the `library/` directory, passes with all tests green:

```bash
npx vitest run src/csvRow/csvRow.test.ts
```
