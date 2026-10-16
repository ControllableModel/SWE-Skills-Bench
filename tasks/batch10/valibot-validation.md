# Task: Build a Price and Quantity Normalization Module

## Background

This repository (`fabian-hiller/valibot`) is the Valibot schema library, with its full public API exported from `library/src/index.ts`. We need a self-contained module that validates and normalizes a shopping-cart line item, enforcing numeric money rules (integer cents, rounding increments) and clamping the requested quantity into an allowed range.

## Files to Create/Modify

- `library/src/lineItem/lineItem.ts` (new) — the validation function and the schema.
- `library/src/lineItem/index.ts` (new) — re-export the public surface of the module.
- `library/src/lineItem/lineItem.test.ts` (new) — the deterministic test suite described below.

Build the module using the library's own public API by importing from the package source root, e.g. `import * as v from '../index.ts';`. Do not add new third-party dependencies.

## Requirements

Implement and export a function `normalizeLineItem(input: unknown)` plus the underlying schema. The function returns the normalized line item directly and throws on invalid input.

### Input contract

```json
{
  "sku": "ABC-123",
  "unitPriceCents": 1999,
  "quantity": 3,
  "discountPercent": 10
}
```

### Field rules

#### `sku` (required)
- String; trimmed; after trimming it must match the pattern of uppercase letters/digits in groups separated by single hyphens (e.g. `ABC-123`, `A1-B2-C3`). The output `sku` is the trimmed value.

#### `unitPriceCents` (required)
- A number that must be an integer (no fractional cents), `>= 0`, and a multiple of 5 (prices are rounded to the nearest nickel). Values violating any of these are rejected.

#### `quantity` (required)
- A number that must be an integer. The **allowed** range is 1 to 99 inclusive, but instead of rejecting out-of-range integers, the value must be **clamped** into `[1, 99]`: a requested quantity below 1 becomes `1`, above 99 becomes `99`. A non-integer quantity is still rejected.

#### `discountPercent` (optional)
- When present, a number that is an integer clamped into `[0, 100]` (values below 0 become 0, above 100 become 100). Non-integer values are rejected.
- When absent, the output must be `0`.

#### Derived output field — `lineTotalCents`
- The output must additionally contain a computed `lineTotalCents`: `unitPriceCents * quantity`, then reduced by `discountPercent`, rounded to the nearest integer cent. Specifically `lineTotalCents = Math.round(unitPriceCents * quantity * (100 - discountPercent) / 100)`. This must be computed from the already-normalized (clamped) field values.

### Output shape

The output contains exactly `sku`, `unitPriceCents`, `quantity`, `discountPercent`, and `lineTotalCents`. Unknown keys are stripped.

### Expected Functionality

- The example payload above -> `{ sku: "ABC-123", unitPriceCents: 1999... }` is rejected because `1999` is not a multiple of 5. Use `2000` to succeed: `{ sku: "ABC-123", unitPriceCents: 2000, quantity: 3, discountPercent: 10 }` -> `lineTotalCents === Math.round(2000*3*90/100) === 5400`.
- `{ sku: "  X1-Y2  ", unitPriceCents: 0, quantity: 500 }` -> `sku === "X1-Y2"`, `quantity` clamped to `99`, `discountPercent === 0`, `lineTotalCents === 0`.
- `{ sku: "A1", unitPriceCents: 100, quantity: 0 }` -> `quantity` clamped to `1`, `lineTotalCents === 100`.
- `{ sku: "A1", unitPriceCents: 100, quantity: 2, discountPercent: 250 }` -> `discountPercent` clamped to `100`, `lineTotalCents === 0`.
- `{ sku: "abc-123", unitPriceCents: 100, quantity: 1 }` -> throws (lowercase sku not allowed by pattern).
- `{ sku: "A1", unitPriceCents: 100.5, quantity: 1 }` -> throws (non-integer cents).
- `{ sku: "A1", unitPriceCents: 103, quantity: 1 }` -> throws (not a multiple of 5).
- `{ sku: "A1", unitPriceCents: 100, quantity: 1.5 }` -> throws (non-integer quantity).
- `null`, `"x"`, `42` -> throws.

## Acceptance Criteria

- A module exists at `library/src/lineItem/lineItem.ts` exporting `normalizeLineItem` and its schema.
- `unitPriceCents` is validated as a non-negative integer that is a multiple of 5; violations throw.
- `quantity` and `discountPercent` are clamped into `[1, 99]` and `[0, 100]` respectively rather than rejected when out of range, while non-integer values for either still throw; `discountPercent` defaults to `0` when absent.
- The output contains a `lineTotalCents` equal to `Math.round(unitPriceCents * quantity * (100 - discountPercent) / 100)` computed from the clamped values, and unknown keys are stripped.
- `sku` is trimmed and must match the uppercase-hyphen-group pattern; lowercase or malformed skus throw.
- The added test suite contains at least 10 distinct test cases covering: a fully valid item with a computed `lineTotalCents`, the quantity clamp at both ends, the discount clamp and its default, the multiple-of-5 and integer rules on `unitPriceCents`, the non-integer quantity rejection, the sku trimming and pattern rejection, and non-object inputs.
- The following command, run from the `library/` directory, passes with all tests green:

```bash
npx vitest run src/lineItem/lineItem.test.ts
```
