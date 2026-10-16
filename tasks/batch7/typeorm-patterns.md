# Task: Build a Customer Profile Layer with Embedded Address

## Background

The TypeORM repository (`typeorm/typeorm`) verifies the ORM end-to-end with functional tests under `test/functional/` that run against an in-memory SQLite database via the repo's own public API. This task adds a self-contained "customer profile" feature where a reusable address value is embedded into entities rather than stored as a separate table, verified through that API.

## Files to Create/Modify

- `test/functional/customer-profile/entity/Address.ts` (new) — the reusable embedded address value type.
- `test/functional/customer-profile/entity/Customer.ts` (new) — the customer record type embedding two addresses.
- `test/functional/customer-profile/profile-service.ts` (new) — a service constructed from a `DataSource` exposing the operations below.
- `test/functional/customer-profile/customer-profile.test.ts` (new) — the functional test that wires the entities into a testing `DataSource` and verifies every requirement.

Follow the existing conventions in `test/functional/` (see `test/functional/custom-repository/custom-repository.test.ts` and the existing embedded tests under `test/functional/embedded/`): import decorators/types from the repo's own `src/` via relative paths, use `createTestingConnections`, `reloadTestingDatabases`, and `closeTestingConnections` from `../../utils/test-utils`, and assert with `chai`.

## Requirements

### Domain model

An **Address** is a reusable value with `street`, `city`, and `postalCode` string fields. It is not an independent table; its fields are stored as part of whichever entity embeds it, with each embedding distinguished by a column-name prefix so two addresses can coexist on one row without column collisions.

A **Customer** has a database-generated numeric identity, a `name` string, a `billingAddress` (an embedded Address), and a `shippingAddress` (a second embedded Address). Both embedded addresses must round-trip independently: setting different values on billing vs shipping must persist and read back as distinct values.

### Profile service

`profile-service.ts` must export a class (or factory) built from a `DataSource` providing at least:

- **createCustomer(name, billing, shipping)** — persists a new customer with the two addresses and returns it with its generated id.
- **getCustomer(customerId)** — returns the customer with both embedded addresses populated; returns `null` when not found.
- **updateShipping(customerId, shipping)** — replaces only the shipping address, leaving the billing address untouched.
- **findByCity(city)** — returns customers whose billing city matches the given value, retrieved with a single query filtering on the embedded billing city, ordered by customer id ascending.

### Constraints

- The test must run without any external database server: enable only the SQLite-based driver(s) when creating the testing connections.
- The schema must be derived from the record-type definitions by the ORM during test setup; no hand-written `CREATE TABLE` SQL.
- There must be no separate `address` table; both addresses must materialize as prefixed columns on the customer row, and the two addresses must remain independently addressable.

### Expected Functionality

- Creating a customer with distinct billing and shipping addresses, then reading it back → both addresses come back with their own correct values, not conflated.
- `updateShipping` → the shipping address changes while the billing address stays exactly as it was.
- `findByCity` filtering on a billing city → returns exactly the customers whose billing city matches, ordered by id, and excludes customers who only have that city as their shipping city.
- `getCustomer(<missing id>)` → returns `null`.

## Acceptance Criteria

- The four files exist under `test/functional/customer-profile/`; entities and service are imported by the test from the repo's own `src/` and `utils`.
- All scenarios in **Expected Functionality** are asserted and pass against the SQLite driver.
- An implementation that stores the address in a separate table, that lets the two addresses collide into shared columns, or that filters by city in JavaScript after loading all customers, must fail at least one assertion.
- The test compiles and passes. From the repo root:

```bash
pnpm run compile && npx mocha ./build/compiled/test/functional/customer-profile/customer-profile.test.js
```
