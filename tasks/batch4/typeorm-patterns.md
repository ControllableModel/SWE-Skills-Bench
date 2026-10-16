# Task: Build a Sales Analytics Query Layer

## Background

The TypeORM repository (`typeorm/typeorm`) verifies the ORM end-to-end with functional tests under `test/functional/` that run against an in-memory SQLite database via the repo's own public API. This task adds a self-contained "sales analytics" feature whose reporting queries must be computed in the database and verified through that API.

## Files to Create/Modify

- `test/functional/sales-analytics/entity/Order.ts` (new) — the order record type.
- `test/functional/sales-analytics/analytics-service.ts` (new) — a service constructed from a `DataSource` exposing the reporting operations below.
- `test/functional/sales-analytics/sales-analytics.test.ts` (new) — the functional test that wires the entity into a testing `DataSource` and verifies every requirement.

Follow the existing conventions in `test/functional/` (see `test/functional/custom-repository/custom-repository.test.ts` and `test/functional/custom-repository/entity/User.ts`): import decorators/types from the repo's own `src/` via relative paths, use `createTestingConnections`, `reloadTestingDatabases`, and `closeTestingConnections` from `../../utils/test-utils`, and assert with `chai`.

## Requirements

### Domain model

An **Order** has a database-generated numeric identity, a `region` string, a `product` string, an `amount` decimal value (monetary, two fractional digits), a `quantity` integer, and a `placedAt` date. All reporting below must be produced by database-side aggregation, not by loading orders into memory and computing in JavaScript.

### Analytics service

`analytics-service.ts` must export a class (or factory) built from a `DataSource` providing at least:

- **revenueByRegion()** — returns one row per region with the summed `amount` across that region's orders; regions with no orders must not appear; rows ordered by region name ascending.
- **topProductsByQuantity(limit)** — returns up to `limit` products ordered by total `quantity` sold descending, where the per-product total is a database aggregate; the list must be globally ordered and never exceed `limit`.
- **averageOrderValue(region)** — returns the mean `amount` of the given region's orders as a number, or `null` when the region has no orders.
- **regionsAboveThreshold(threshold)** — returns the set of region names whose summed `amount` strictly exceeds `threshold`, computed with a database-side grouped filter (i.e. the threshold comparison applies to the aggregate, not to individual rows).

### Constraints

- The test must run without any external database server: enable only the SQLite-based driver(s) when creating the testing connections.
- The schema must be derived from the record-type definition by the ORM during test setup; no hand-written `CREATE TABLE` SQL.
- Every reporting method must obtain its numbers from the database engine; an implementation that calls a plain "find all" and reduces in JavaScript must fail.

### Expected Functionality

- A mixed dataset across three regions → `revenueByRegion()` returns one correctly summed row per region, ordered by region name, with the sum equal to the JavaScript-side total for that region.
- `topProductsByQuantity(2)` over four products with differing totals → returns exactly the two highest-quantity products in descending order.
- `averageOrderValue` for a region with known orders → returns the correct mean; for an unknown region → returns `null`.
- `regionsAboveThreshold(t)` → returns exactly those regions whose total revenue exceeds `t`, and excludes a region whose individual orders each exceed `t` but whose total does not (proving the threshold is applied to the aggregate).

## Acceptance Criteria

- The three files exist under `test/functional/sales-analytics/`; entity and service are imported by the test from the repo's own `src/` and `utils`.
- All scenarios in **Expected Functionality** are asserted and pass against the SQLite driver.
- An implementation that computes any report by summing/averaging in JavaScript instead of via database aggregation must fail at least one assertion.
- The test compiles and passes. From the repo root:

```bash
pnpm run compile && npx mocha ./build/compiled/test/functional/sales-analytics/sales-analytics.test.js
```
