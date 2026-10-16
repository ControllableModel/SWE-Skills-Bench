# Task: Assemble a Nested Order Report

## Background
This is the [Sequelize](https://github.com/sequelize/sequelize) monorepo. Inside the `@sequelize/core` package's integration-test tree we need an "orders" domain plus a `loadCustomerOrders` function that returns each customer together with their orders and each order's line items in a single round of loading. Integration tests in this package run against the default test dialect (an in-memory/file database), so the assembled nested objects can be inspected in-process.

## Files to Create/Modify
- `packages/core/test/integration/order-report.ts` (new) — the module defining `Customer`, `Order`, and `LineItem`, and exporting `setupOrders(sequelize)` and `loadCustomerOrders(models, options)`.
- `packages/core/test/integration/order-report.test.ts` (new) — the integration test that exercises the report.

## Requirements

### Module shape
- `setupOrders(sequelize)` must define and return `{ Customer, Order, LineItem }`, wire their relationships, and create their tables.
- `loadCustomerOrders(models, options)` must return the customers with their nested orders and line items eagerly attached.

### Models and relationships
- **Customer** — `name` (text, required). A customer has many **Orders** reachable under the accessor `orders`.
- **Order** — `reference` (text, required), `placedAt` (date, required), `customerId` (integer). An order has many **LineItems** reachable under the accessor `items`; the order belongs to its customer under accessor `customer`.
- **LineItem** — `description` (text, required), `quantity` (integer, required), `orderId` (integer).

### Loading behavior
- `loadCustomerOrders(models)` with no options must return every customer, each with their `orders` populated, and each order with its `items` populated — assembled without issuing a separate per-customer or per-order follow-up query (the related rows must arrive attached to the returned instances).
- When `options.recentOnly` is `true`, only orders whose `placedAt` is on or after `options.since` (a `Date`) must be attached; customers with no qualifying orders must still appear in the result, with an empty `orders` list.
- When `options.recentOnly` is absent or `false`, all of a customer's orders must be attached regardless of date.

### Edge cases and constraints
- A customer with zero orders must still appear with an empty `orders` array.
- Filtering by `since` must not drop customers that have no matching orders (they appear with `orders: []`).
- Line items must always be attached to the orders that are returned.
- A naive implementation that loads relations with follow-up queries per parent, or that drops childless parents when filtering, must fail the tests.

### Expected Functionality
- Seed customers (including one with no orders), orders across two dates, and line items. `loadCustomerOrders(models)` -> every customer present; each order carries its `items`; the no-order customer has `orders: []`.
- `loadCustomerOrders(models, { recentOnly: true, since })` -> only orders on/after `since` are attached; a customer whose orders are all older appears with `orders: []`.

## Acceptance Criteria
- A new self-contained test `packages/core/test/integration/order-report.test.ts` exists, seeds a fixed dataset, and asserts: full nested loading (customers→orders→items) with the childless customer present, attached line items, and the `recentOnly`/`since` date filtering that retains childless customers with empty order lists.
- The implementation lives in `packages/core/test/integration/order-report.ts` and is imported by the test.
- All assertions are objectively verifiable in-process against the default test database (no external server).
- From the `packages/core` directory, the following command runs and passes with no failing tests:

  ```bash
  yarn mocha "test/integration/order-report.test.ts"
  ```
