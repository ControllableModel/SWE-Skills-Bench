# Task: Build an Order-Line Composite-Key Layer

## Background

The TypeORM repository (`typeorm/typeorm`) verifies the ORM end-to-end with functional tests under `test/functional/` that run against an in-memory SQLite database via the repo's own public API. This task adds a self-contained "order lines" feature whose line items are identified by a multi-column key, verified through that API.

## Files to Create/Modify

- `test/functional/order-lines/entity/Order.ts` (new) — the order record type.
- `test/functional/order-lines/entity/OrderLine.ts` (new) — the line-item record type with a composite identity.
- `test/functional/order-lines/order-line-service.ts` (new) — a service constructed from a `DataSource` exposing the operations below.
- `test/functional/order-lines/order-lines.test.ts` (new) — the functional test that wires the entities into a testing `DataSource` and verifies every requirement.

Follow the existing conventions in `test/functional/` (see `test/functional/custom-repository/custom-repository.test.ts` and `test/functional/custom-repository/entity/User.ts`): import decorators/types from the repo's own `src/` via relative paths, use `createTestingConnections`, `reloadTestingDatabases`, and `closeTestingConnections` from `../../utils/test-utils`, and assert with `chai`.

## Requirements

### Domain model

An **Order** has a database-generated numeric identity and a `customer` string. An **OrderLine** belongs to an order and is identified by the combination of its `orderId` and a `lineNo` integer that is unique only within that order — together those two columns form the line's primary identity (the same `lineNo` may reappear under a different order, but never twice within the same order). Each line also has a `product` string and a `quantity` integer.

### Order-line service

`order-line-service.ts` must export a class (or factory) built from a `DataSource` providing at least:

- **createOrder(customer)** — persists a new order and returns it with its generated id.
- **addLine(orderId, lineNo, product, quantity)** — persists a new line under the order. Attempting to add a line whose `(orderId, lineNo)` already exists must fail (rejected promise or thrown error), since that pair is the line's identity.
- **getLine(orderId, lineNo)** — returns the single line identified by the composite key, or `null` when no such line exists.
- **linesOf(orderId)** — returns all lines of the order ordered by `lineNo` ascending.
- **removeLine(orderId, lineNo)** — deletes exactly the one line identified by the composite key, leaving every other line of that order intact.

### Constraints

- The test must run without any external database server: enable only the SQLite-based driver(s) when creating the testing connections.
- The schema must be derived from the record-type definitions by the ORM during test setup; no hand-written `CREATE TABLE` SQL.
- A line's identity must be the two columns together, so the same `lineNo` is allowed under two different orders but rejected twice under one order.

### Expected Functionality

- Adding lines 1 and 2 under one order and line 1 under a different order → all three persist (line 1 coexists across the two orders).
- Adding a second line with an already-used `(orderId, lineNo)` pair → fails, and the original line is unchanged.
- `getLine` with an exact composite key → returns that line; with a key that does not exist → returns `null`.
- `linesOf(orderId)` → returns that order's lines in `lineNo` order and none from other orders.
- `removeLine(orderId, lineNo)` → removes exactly that line, leaving the order's other lines retrievable.

## Acceptance Criteria

- The four files exist under `test/functional/order-lines/`; entities and service are imported by the test from the repo's own `src/` and `utils`.
- All scenarios in **Expected Functionality** are asserted and pass against the SQLite driver.
- An implementation that identifies lines by a single column (allowing only globally-unique `lineNo`, or failing the cross-order coexistence case) must fail at least one assertion.
- The test compiles and passes. From the repo root:

```bash
pnpm run compile && npx mocha ./build/compiled/test/functional/order-lines/order-lines.test.js
```
