# Task: Build a Concurrency-Safe Inventory Layer

## Background

The TypeORM repository (`typeorm/typeorm`) exercises the ORM end-to-end with functional tests under `test/functional/` that run against an in-memory SQLite database via the repo's own public API. This task adds a self-contained "inventory" feature that must reject stale concurrent writes, verified through that API.

## Files to Create/Modify

- `test/functional/inventory-concurrency/entity/StockItem.ts` (new) — the stock-item record type.
- `test/functional/inventory-concurrency/inventory-service.ts` (new) — a service constructed from a `DataSource` exposing the operations below.
- `test/functional/inventory-concurrency/inventory-concurrency.test.ts` (new) — the functional test that wires the entity into a testing `DataSource` and verifies every requirement.

Follow the existing conventions in `test/functional/` (see `test/functional/custom-repository/custom-repository.test.ts` and `test/functional/custom-repository/entity/User.ts`): import decorators/types from the repo's own `src/` via relative paths, use `createTestingConnections`, `reloadTestingDatabases`, and `closeTestingConnections` from `../../utils/test-utils`, and assert with `chai`.

## Requirements

### Domain model

A **StockItem** has a database-generated numeric identity, a `sku` string, and a `quantity` integer. Each item additionally carries a record-revision indicator that the ORM increments automatically on every successful update, so that two writers who both read the same revision and then try to save will not both silently succeed.

### Inventory service

`inventory-service.ts` must export a class (or factory) built from a `DataSource` providing at least:

- **addItem(sku, quantity)** — persists a new stock item and returns it including its current revision indicator.
- **getItem(itemId)** — returns the item including its current revision indicator; returns `null` when not found.
- **adjustQuantity(itemId, expectedRevision, delta)** — applies `delta` to the quantity only if the item's current revision still matches `expectedRevision`; if the stored revision has already moved on (another writer updated the item in between), the operation must fail (rejected promise or thrown error) and leave the quantity unchanged. On success the revision indicator must advance.

### Constraints

- The test must run without any external database server: enable only the SQLite-based driver(s) when creating the testing connections.
- The schema must be derived from the record-type definition by the ORM during test setup; no hand-written `CREATE TABLE` SQL.
- The stale-write detection must rely on the ORM's automatically-managed revision indicator, not on a hand-maintained counter the service mutates by itself.

### Expected Functionality

- Adding an item then reading it back → the revision indicator is populated.
- Two reads of the same item obtain the same revision; the first `adjustQuantity` with that revision succeeds and advances the revision; a second `adjustQuantity` using the now-stale revision fails and leaves the quantity at the value left by the first adjustment.
- A successful `adjustQuantity` → the revision indicator is strictly greater than before.
- `getItem(<missing id>)` → returns `null`.

## Acceptance Criteria

- The three files exist under `test/functional/inventory-concurrency/`; entity and service are imported by the test from the repo's own `src/` and `utils`.
- All scenarios in **Expected Functionality** are asserted and pass against the SQLite driver.
- An implementation that ignores the revision on update (allowing a stale write to overwrite a newer one) must fail at least one assertion.
- The test compiles and passes. From the repo root:

```bash
pnpm run compile && npx mocha ./build/compiled/test/functional/inventory-concurrency/inventory-concurrency.test.js
```
