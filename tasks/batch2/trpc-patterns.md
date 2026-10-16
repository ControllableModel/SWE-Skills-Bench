# Task: Build a Catalog Pricing Router with Output Contracts

## Background

This repository is the tRPC monorepo. Its server package (`@trpc/server`) exposes `initTRPC`, `TRPCError`, and a caller factory that the in-process test suite under `packages/tests/server/` exercises. This task adds a self-contained product-catalog pricing API whose procedures declare and enforce an explicit output shape, plus a deterministic test that drives it through callers.

## Files to Create/Modify

- `packages/tests/server/catalog.ts` (new) — the catalog module: an in-memory product/discount store, the tRPC instance and helpers, the router, and an exported caller factory.
- `packages/tests/server/catalog.test.ts` (new) — the deterministic test suite that imports only the public surface re-exported from `catalog.ts` and verifies behavior through callers.

All implementation lives in `catalog.ts`. The test file must only consume the exported caller factory and exported types; it must not re-declare routers or procedures.

## Requirements

### Data Layer

`catalog.ts` must keep an in-memory store of products and discount rules, with no external services, no network, and no filesystem. Each product has a string `sku`, a `name`, a non-negative integer `priceCents`, and a `currency` (one of `"USD"`, `"EUR"`). Expose a factory that produces a fresh, isolated store per call so independent tests start clean. The store must be reachable inside procedures through the request context, not via module-level access inside the procedures.

### Procedures

Expose a single root router (suitable for an exported `AppRouter` type) nesting a `catalog` sub-router with:

- `getProduct` — input `{ sku: string }`; returns the product as `{ sku, name, priceCents, currency }`.
- `quote` — input `{ sku: string; quantity: number; discountCode?: string }`; computes a price quote and returns `{ sku, quantity, unitPriceCents, subtotalCents, discountCents, totalCents, currency }`.
- `listByCurrency` — input `{ currency: "USD" | "EUR" }`; returns an array of products in that currency.

### Output Contract

Every procedure must declare its return shape so that a return value not matching the declared shape is rejected by the framework rather than silently returned. The declared output for `quote` must require all of the listed numeric fields to be present and numeric, and `currency` to be one of the allowed values. A procedure body that returns a partial object, an extra unexpected field where the contract forbids it, or a wrongly typed field must fail at the output boundary, not reach the caller.

### Pricing Rules

- `subtotalCents = unitPriceCents * quantity`.
- A `discountCode` of `"SAVE10"` removes 10% of the subtotal (floored to a whole cent); `"SAVE25"` removes 25% (floored). Any other non-empty code is invalid input. Omitting the code means zero discount.
- `totalCents = subtotalCents - discountCents` and must never go negative.
- `quantity` must be an integer `>= 1`.

### Input Validation

`sku` must be a non-empty string; `quantity` must be an integer `>= 1`; `currency` must be exactly one of the two allowed values; `discountCode`, when present, must be one of the recognized codes. Malformed input must be rejected as a validation failure before any pricing logic runs.

### Error Semantics

- A `getProduct` / `quote` for an unknown `sku` reports a not-found condition.
- Invalid input reports a validation failure (distinct from not-found).
- Internal store details must not appear in messages exposed to the caller.

### Expected Functionality

- `getProduct({ sku })` for a seeded product → returns the exact `{ sku, name, priceCents, currency }`.
- `quote({ sku, quantity: 3 })` with no code → `discountCents === 0`, `totalCents === unitPriceCents * 3`.
- `quote({ sku, quantity: 4, discountCode: "SAVE25" })` → `discountCents` equals 25% of subtotal floored, and `totalCents === subtotalCents - discountCents`.
- `quote` with `quantity: 0` or a fractional quantity → validation failure.
- `quote` with `discountCode: "BOGUS"` → validation failure.
- `getProduct({ sku: "does-not-exist" })` → not-found.
- `listByCurrency({ currency: "EUR" })` → only EUR products.

## Acceptance Criteria

- A new module `packages/tests/server/catalog.ts` exports a caller factory and the router type, implemented on the repository's existing `@trpc/server` primitives with declared procedure output shapes.
- A new test file `packages/tests/server/catalog.test.ts` contains at least 12 cases covering: each procedure, the discount math (both codes and the no-code path), the non-negative-total guard, not-found vs validation distinction, output-contract enforcement (a deliberately malformed return rejected at the boundary), and store isolation between independent stores.
- Tests assert on tRPC error **codes** where an error is expected (not substring matching of messages).
- The following command passes with all assertions green:

  ```bash
  pnpm vitest run packages/tests/server/catalog.test.ts
  ```

- A naive implementation that ignores the output contract, skips validation, returns hardcoded totals, or lets `totalCents` go negative must fail the suite.
