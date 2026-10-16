# Task: Build a Product Search Filter

## Background
This is the [Sequelize](https://github.com/sequelize/sequelize) monorepo. Inside the `@sequelize/core` package's integration-test tree we need a "product" catalog plus a `searchProducts` function that turns a plain filter object into the matching rows. Integration tests in this package run against the default test dialect (an in-memory/file database), so seeding rows and asserting on returned matches can be done entirely in-process.

## Files to Create/Modify
- `packages/core/test/integration/product-search.ts` (new) — the module defining the `Product` model and exporting `setupProducts(sequelize)` and `searchProducts(Product, filter)`.
- `packages/core/test/integration/product-search.test.ts` (new) — the integration test that exercises the search.

## Requirements

### Module shape
- `setupProducts(sequelize)` must define and return the `Product` model and create its table.
- `searchProducts(Product, filter)` must return the matching rows ordered by `price` ascending, then by `name` ascending as a tie-break.

### Model
- **Product** — fields: `name` (text, required), `price` (integer, required), `category` (text, required), `inStock` (boolean, defaults to `true`).

### Filter semantics
The `filter` object is optional and any subset of its keys may be present. Each present key narrows the result set (keys combine with AND):
- `nameContains` (string): match products whose `name` contains the substring (case-sensitive contains).
- `categories` (string[]): match products whose `category` is one of the provided values.
- `minPrice` (number): match products whose `price` is greater than or equal to the value.
- `maxPrice` (number): match products whose `price` is less than or equal to the value.
- `inStockOnly` (boolean): when `true`, restrict to products with `inStock === true`; when absent or `false`, do not restrict on stock.

### Edge cases and constraints
- An empty filter (or `undefined`) must return ALL products, still ordered by price then name.
- `minPrice` and `maxPrice` may be given together to express an inclusive range; a product exactly equal to either bound must be included.
- Passing `categories: []` (empty array) must yield zero results (no category can match).
- A naive implementation that ignores any present filter key, or that returns rows in an unspecified order, must fail the tests.

### Expected Functionality
- Seed a known set of products. `searchProducts(Product, {})` -> all rows, ordered by price asc then name asc.
- `{ minPrice: 10, maxPrice: 20 }` -> only products with `10 <= price <= 20`.
- `{ categories: ['books', 'toys'] }` -> only products in those two categories.
- `{ nameContains: 'Pro' }` -> only products whose name contains `Pro`.
- `{ inStockOnly: true }` -> excludes out-of-stock products.
- A combined filter -> applies all constraints with AND and the specified ordering.

## Acceptance Criteria
- A new self-contained test `packages/core/test/integration/product-search.test.ts` exists, seeds a fixed product set, and asserts each filter key individually, an empty filter, an inclusive price range (including boundary equality), an empty `categories` array yielding no rows, a combined filter, and the price-then-name ordering of every result set.
- The implementation lives in `packages/core/test/integration/product-search.ts` and is imported by the test.
- All assertions are objectively verifiable in-process against the default test database (no external server).
- From the `packages/core` directory, the following command runs and passes with no failing tests:

  ```bash
  yarn mocha "test/integration/product-search.test.ts"
  ```
