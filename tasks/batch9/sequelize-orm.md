# Task: Compute Sales Aggregates by Region

## Background
This is the [Sequelize](https://github.com/sequelize/sequelize) monorepo. Inside the `@sequelize/core` package's integration-test tree we need a "sales" domain plus a `regionSummary` function that returns aggregate statistics grouped by region. Integration tests in this package run against the default test dialect (an in-memory/file database), so seeding rows and asserting on the computed aggregates can be done entirely in-process.

## Files to Create/Modify
- `packages/core/test/integration/sales-summary.ts` (new) — the module defining the `Sale` model and exporting `setupSales(sequelize)` and `regionSummary(Sale)`.
- `packages/core/test/integration/sales-summary.test.ts` (new) — the integration test that exercises the summary.

## Requirements

### Module shape
- `setupSales(sequelize)` must define and return the `Sale` model and create its table.
- `regionSummary(Sale)` must compute and return the per-region aggregates described below.

### Model
- **Sale** — fields: `region` (text, required), `amount` (integer, required), `completed` (boolean, defaults to `true`).

### Aggregation behavior
- `regionSummary(Sale)` must consider only rows where `completed === true`.
- It must return one entry per distinct region (among completed sales), each entry containing: the `region`, the `count` of completed sales in that region, the `total` (sum of `amount`), the `max` amount, and the `min` amount.
- The returned entries must be ordered by `total` descending, with `region` ascending as a tie-break.
- A region that has only non-completed sales must NOT appear in the result.

### Edge cases and constraints
- Numeric aggregate fields (`count`, `total`, `max`, `min`) must be returned as JavaScript numbers, not strings.
- When two regions have an equal `total`, they must appear in ascending region-name order.
- If there are no completed sales at all, the result must be an empty array.
- A naive implementation that counts all rows (ignoring `completed`), or that returns aggregates as strings, or that omits the ordering, must fail the tests.

### Expected Functionality
- Seed sales across regions `east`, `west`, `north`, with some `completed: false`. `regionSummary(Sale)` -> one entry per region that has at least one completed sale, each with correct `count`/`total`/`max`/`min` over completed rows only.
- The result is ordered by `total` descending, ties broken by region ascending.
- A region whose only sales are `completed: false` is absent from the result.

## Acceptance Criteria
- A new self-contained test `packages/core/test/integration/sales-summary.test.ts` exists, seeds a fixed dataset that includes non-completed rows and a tie in totals, and asserts: correct per-region `count`/`total`/`max`/`min` over completed rows only, numeric (non-string) aggregate values, the `total`-desc / `region`-asc ordering, exclusion of all-incomplete regions, and an empty array when no completed sales exist.
- The implementation lives in `packages/core/test/integration/sales-summary.ts` and is imported by the test.
- All assertions are objectively verifiable in-process against the default test database (no external server).
- From the `packages/core` directory, the following command runs and passes with no failing tests:

  ```bash
  yarn mocha "test/integration/sales-summary.test.ts"
  ```
